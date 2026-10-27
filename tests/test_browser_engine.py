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
    parse_graphql_interactions
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

    def test_reactor_requires_reaction_context(self):
        payload={"data":{"users":{"edges":[{"node":{
            "name":"not-reactor","url":"https://www.facebook.com/normal"}}]}}}
        _,reactors=parse_graphql_interactions(json.dumps(payload),0,10)
        self.assertEqual(reactors,[])

class HybridPipelineTests(unittest.TestCase):
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
        self.assertEqual(x.exception.code,'GRAPHQL_DOC_ID_UNAVAILABLE')

    def test_browser_disabled_stays_explicitly_unavailable(self):
        with patch('app.engine._graphql_scrape',side_effect=ExtractionError('GRAPHQL_DOC_ID_UNAVAILABLE')), \
             patch('app.engine._legacy_scrape',side_effect=ExtractionError('POST_NOT_PARSED')), \
             patch('app.browser_engine.scrape_with_browser',side_effect=RuntimeError('BROWSER_DISABLED')):
            with self.assertRaises(ExtractionError) as x:
                scrape_post(URL,5,5,'/tmp/fake.json')
        self.assertEqual(x.exception.code,'GRAPHQL_DOC_ID_UNAVAILABLE')

if __name__=='__main__':
    unittest.main()
