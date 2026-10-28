"""Offline tests for the independent browser observation fallback.

No Facebook account, credentials, browser binary, or live pages are required.
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from app.browser_engine import (
    MAX_RESPONSE_BYTES, _parse_json_fragments, _browser_cookie_entries,
    parse_graphql_interactions, graphql_response_shape, _valid_profile_url,
    _COMMENT_ENTRY_LABELS, _browser_page_classification
)
from app.engine import scrape_post, ExtractionError

URL='https://www.facebook.com/NASA/posts/1234567890'

class BrowserParsingTests(unittest.TestCase):
    def test_xssi_graphql_jsonl_comments_and_reactors(self):
        payload={"data":{"post":{"comments":{"edges":[{"node":{
            "__typename":"Comment","id":"comment01",
            "author":{"name":"Layla","url":"https://www.facebook.com/layla"},
            "body":{"text":"This is an actual comment"},
            "created_time":1780000000}}]},
            "reactors":{"edges":[{"node":{
                "name":"Hani","url":"https://www.facebook.com/hani"}}]}}}}
        raw='for (;;);'+json.dumps(payload)
        comments,reactors=parse_graphql_interactions(raw,5,5)
        self.assertEqual(len(comments),1)
        self.assertEqual(comments[0]['id'],'comment01')
        self.assertEqual(comments[0]['name'],'Layla')
        self.assertEqual(len(reactors),1)
        self.assertEqual(reactors[0]['name'],'Hani')

    def test_excludes_unverified_unrelated_nodes(self):
        payload={"data":{"viewer":{"name":"User","url":"https://www.facebook.com/user"},
                         "random":{"name":"Hacker","url":"https://www.facebook.com/hacker"},
                         "comment":{"__typename":"Comment","id":"c0","body":{},"author":{"name":"A"}}}}
        comments,reactors=parse_graphql_interactions(json.dumps(payload),10,10)
        self.assertEqual(comments,[])
        self.assertEqual(reactors,[])

    def test_does_not_trust_nonfacebook_profile(self):
        payload={"data":{"comments":{"edges":[{"node":{
            "__typename":"Comment","id":"c1",
            "author":{"name":"Victim","url":"https://facebook.com.evil.test/victim"},
            "body":{"text":"Hello"}}}]}}}
        comments,reactors=parse_graphql_interactions(json.dumps(payload),5,5)
        self.assertEqual(len(comments),1)
        self.assertIsNone(comments[0]['profile_url'])
        self.assertEqual(reactors,[])

    def test_multipart_jsonl_and_bounded_payload(self):
        raw='for (;;);{"data":{"ignored":{}}}\n{"data":{"ignored":{"name":"not a comment"}}}'
        self.assertEqual(len(_parse_json_fragments(raw)),2)
        self.assertEqual(_parse_json_fragments('{'+'x'*MAX_RESPONSE_BYTES+'}'),[])

    def test_cookie_domain_paths_retained_for_browser(self):
        cookies=[{"name":"c_user","value":"private","domain":".facebook.com","path":"/","secure":True},
                 {"name":"xs","value":"x","domain":"www.facebook.com","path":"/private","secure":True},
                 {"name":"bad","value":"x","domain":"facebook.com.evil.test","path":"/"}]
        with tempfile.TemporaryDirectory() as d:
            path=d+'/cookie.json'
            with open(path,'w') as fp: json.dump(cookies,fp)
            loaded=_browser_cookie_entries(path)
        self.assertEqual(len(loaded),2)
        self.assertEqual(loaded[1]['domain'],'www.facebook.com')
        self.assertEqual(loaded[1]['path'],'/private')
        self.assertNotIn('evil.test',str(loaded))

    def test_realistic_nested_comet_comment_and_reactor_without_url(self):
        payload={"data":{"feedback":{"display_comments":{"edges":[{"node":{
           "__typename":"XFBComment","id":"Y29tbWVudDo0Mg",
           "author":{"id":"234","name":"Samira"},
           "body":{"text":{"text":"Nested Comet message"}}}}]},
           "reactors":{"edges":[{"node":{
           "actor":{"id":"5512771","name":"Fadi"},
           "reaction_type":{"name":"LIKE"}}}]}}}}
        comments,reactors=parse_graphql_interactions(json.dumps(payload),8,8)
        self.assertEqual(len(comments),1)
        self.assertEqual(comments[0]['text'],'Nested Comet message')
        self.assertEqual(len(reactors),1)
        self.assertEqual(reactors[0]['name'],'Fadi')
        self.assertIsNone(reactors[0]['profile_url'])
        shape=graphql_response_shape(json.dumps(payload))
        self.assertGreater(shape['comment_nodes'],0)
        self.assertGreater(shape['reactor_containers'],0)
        self.assertNotIn('Samira',str(shape))

    def test_shape_report_never_includes_user_values(self):
        body={"data":{"feedback":{"display_comments":[{"__typename":"Comment",
                 "author":{"name":"SECRET_PERSON","id":"999"},
                 "body":{"text":"SECRET_BODY"}}]}}}
        shape=graphql_response_shape(json.dumps(body))
        self.assertTrue(shape['comment_containers']>=1)
        self.assertNotIn('SECRET_PERSON',str(shape))
        self.assertNotIn('SECRET_BODY',str(shape))
        self.assertEqual(shape['graphql_errors'],0)

    def test_numeric_profile_php_id_and_comment_permalink(self):
        url='https://www.facebook.com/profile.php?id=12345678&fbclid=tracker'
        self.assertIn('id=12345678',_valid_profile_url(url))
        self.assertNotIn('fbclid',_valid_profile_url(url))
        comment='https://www.facebook.com/example/posts/12345678?comment_id=789456123&fbclid=tracking'
        self.assertIn('comment_id=789456123',_valid_profile_url(comment,comment_permalink=True))
        self.assertNotIn('fbclid',_valid_profile_url(comment,comment_permalink=True))

    def test_comment_entry_patterns_cover_current_dialog_counts(self):
        for label in ('View all 12 comments','See 34 comments',
                      'View more comments','12 comments',
                      'عرض كل التعليقات','Voir les commentaires',
                      'Mostra i commenti'):
            with self.subTest(label=label):
                self.assertIsNotNone(_COMMENT_ENTRY_LABELS.search(label))
        # Never auto-click the composer or an unrelated state-changing action.
        for label in ('Comment','Reply','Like','Follow','Send comment'):
            with self.subTest(label=label):
                self.assertIsNone(_COMMENT_ENTRY_LABELS.search(label))

    def test_safe_browser_classification_uses_counts_only(self):
        from unittest.mock import Mock
        page=Mock()
        page.evaluate.return_value={
            'login_input':False,'page_title_is_login':False,
            'comment_permalink_links':0,'comment_articles':2,
            'comment_entry_candidates':3,'reaction_entry_candidates':4,'lang':'en-US'}
        value=_browser_page_classification(page)
        self.assertEqual(value['status'],'comment_controls_visible')
        self.assertEqual(value['comment_entry_candidates'],3)
        self.assertNotIn('post_text',str(value))
        page.evaluate.return_value={**page.evaluate.return_value,'login_input':True}
        self.assertEqual(_browser_page_classification(page)['status'],'login_wall')

    def test_reactor_requires_reaction_context(self):
        payload={"data":{"users":{"edges":[{"node":{
            "name":"not-reactor","url":"https://www.facebook.com/normal"}}]}}}
        _,reactors=parse_graphql_interactions(json.dumps(payload),0,10)
        self.assertEqual(reactors,[])

class HybridPipelineTests(unittest.TestCase):
    def setUp(self):
        self._legacy=patch.dict(os.environ,{'FB_ENGINE':'legacy'})
        self._legacy.start()
        self.addCleanup(self._legacy.stop)

    def _good(self):
        return {
            'post':{'id':None,'url':URL,'counts':{'comments':None,'likes':None}},
            'comments':[{'id':'c1','name':'Maya','text':'hello'}],
            'reactors':[],
            'coverage':{'comments_returned':1,'reactors_returned':0,
                        'comments_requested':5,'reactors_requested':5,'complete':False,
                        'adapter':'browser'}
        }

    def test_browser_works_when_doc_id_discovery_fails(self):
        with patch('app.engine._graphql_scrape',side_effect=ExtractionError('GRAPHQL_DOC_ID_UNAVAILABLE')), \
             patch('app.engine._legacy_scrape',side_effect=ExtractionError('POST_NOT_PARSED')), \
             patch('app.browser_engine.scrape_with_browser',return_value=self._good()) as browser:
            data=scrape_post(URL,5,5,'/tmp/fake_cookie_file.json')
        browser.assert_called_once()
        self.assertEqual(data['coverage']['adapter'],'browser')
        self.assertEqual(data['comments'][0]['name'],'Maya')

    def test_browser_no_results_cannot_be_reported_as_success(self):
        empty=self._good()
        empty['comments']=[]
        with patch('app.engine._graphql_scrape',side_effect=ExtractionError('GRAPHQL_DOC_ID_UNAVAILABLE')), \
             patch('app.engine._legacy_scrape',side_effect=ExtractionError('POST_NOT_PARSED')), \
             patch('app.browser_engine.scrape_with_browser',return_value=empty):
            with self.assertRaises(ExtractionError) as x:
                scrape_post(URL,5,5,'/tmp/fake.json')
        self.assertEqual(x.exception.code,'BROWSER_NO_VERIFIABLE_INTERACTIONS')

    def test_browser_disabled_stays_explicitly_unavailable(self):
        with patch('app.engine._graphql_scrape',side_effect=ExtractionError('GRAPHQL_DOC_ID_UNAVAILABLE')), \
             patch('app.engine._legacy_scrape',side_effect=ExtractionError('POST_NOT_PARSED')), \
             patch('app.browser_engine.scrape_with_browser',side_effect=RuntimeError('BROWSER_DISABLED')):
            with self.assertRaises(ExtractionError) as x:
                scrape_post(URL,5,5,'/tmp/fake.json')
        self.assertEqual(x.exception.code,'GRAPHQL_DOC_ID_UNAVAILABLE')

if __name__=='__main__':
    unittest.main()
