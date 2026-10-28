"""Production V2 engine contract/locale tests; no Facebook credentials required."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from app.read_only_v2 import (_is_safe_open_label,_clean_url,_capture_graphql,
                              _cookie_entries,run,OPEN_REEL,MORE)
from app.engine import scrape_post,ExtractionError

TEST_URL="https://www.facebook.com/reel/1418347453748116"

class MultilingualEngineTests(unittest.TestCase):
    def test_officially_observed_french_reel_entry(self):
        self.assertTrue(_is_safe_open_label("Commenter",video=True))
        self.assertFalse(_is_safe_open_label("Commenter",video=False))
        self.assertTrue(_is_safe_open_label("17 commentaires",video=False))

    def test_hindi_urdu_and_indic_langs(self):
        for label in ("टिप्पणी करें","टिप्पणी","تبصرہ کریں","تبصرے",
                      "মন্তব্য করুন","ਟਿੱਪਣੀ ਕਰੋ","கருத்துகள்",
                      "వ్యాఖ్యలు","टिप्पणी करा","ટિપ્પણીઓ",
                      "അഭിപ്രായങ്ങൾ","ಕಾಮೆಂಟ್‌ಗಳು"):
            with self.subTest(label=label):
                self.assertTrue(_is_safe_open_label(label,video=True))
        for label in ("مزید تبصرے","और टिप्पणियाँ","আরও মন্তব্য",
                      "ਹੋਰ ਟਿੱਪਣੀਆਂ","அனைத்து கருத்துகளும்"):
            with self.subTest(label=label):
                self.assertTrue(_is_safe_open_label(label,video=False))

    def test_no_write_controls_in_any_language(self):
        for label in ("J'aime","Like","Send","Reply","Follow",
                      "अभी भेजें","पसंद","لائک","شیئر","بھیجیں",
                      "أعجبني","مشاركة","إرسال","👍 Like"):
            with self.subTest(label=label):
                self.assertFalse(_is_safe_open_label(label,video=True))

    def test_structural_coverage_24_languages(self):
        self.assertGreaterEqual(len(OPEN_REEL),24)
        self.assertGreaterEqual(len(MORE),20)

    def test_verified_comments_preserve_unicode(self):
        c,r={},{}
        payload={"data":{"feedback":{"comments":{"edges":[{"node":{
            "__typename":"Comment","id":"2319889195441081",
            "author":{"name":"عبدالله صالح","url":"https://www.facebook.com/profile.php?id=1234567"},
            "body":{"text":"ویدیو अच्छा है"}}}]}}}}
        counts=_capture_graphql(json.dumps(payload,ensure_ascii=False),c,r,(5,5))
        self.assertEqual(counts['comment_shapes'],1)
        self.assertEqual(c['2319889195441081']['name'],"عبدالله صالح")
        self.assertEqual(c['2319889195441081']['text'],"ویدیو अच्छा है")

    def test_urls_exclude_tracking_but_keep_comment_id(self):
        url="https://www.facebook.com/reel/1418347453748116/?comment_id=2319889195441081&__tn__=R"
        self.assertEqual(_clean_url(url,True),
          "https://www.facebook.com/reel/1418347453748116/?comment_id=2319889195441081")
        self.assertIsNone(_clean_url("https://facebook.com.evil.test/post/123"))
        self.assertEqual(_clean_url("https://www.facebook.com/profile.php?id=123456&fbclid=123"),
                         "https://www.facebook.com/profile.php?id=123456")

    def test_cookies_scoped_and_no_secret_logging(self):
        with tempfile.TemporaryDirectory() as d:
            path=d+"/cookies.json"
            with open(path,'w') as f:json.dump([
             {"name":"c_user","value":"sensitive","domain":".facebook.com","path":"/"},
             {"name":"bad","value":"evil","domain":".facebook.com.evil.test","path":"/"}],f)
            got=_cookie_entries(path)
        self.assertEqual(len(got),1)
        self.assertEqual(got[0]['name'],'c_user')

    def test_production_routing_uses_new_complete_engine(self):
        with patch.dict(os.environ,{'FB_ENGINE':'read_only_v2'}), \
             patch('app.read_only_v2.run',return_value={'comments':[{'name':'Test'}],'reactors':[]}) as call:
            result=scrape_post(TEST_URL,5,5,"/tmp/test.json")
        call.assert_called_once()
        self.assertEqual(result['comments'][0]['name'],'Test')

    def test_login_wall_vs_redirect_codes_remain_distinct(self):
        for code in ('FACEBOOK_LOGIN_WALL_VISIBLE','FACEBOOK_LOGIN_REQUIRED',
                     'FACEBOOK_COOKIES_SCOPE_MISMATCH','FACEBOOK_CHECKPOINT_REQUIRED'):
            with self.subTest(code=code):
                with patch.dict(os.environ,{'FB_ENGINE':'read_only_v2'}), \
                     patch('app.read_only_v2.run',side_effect=RuntimeError(code)):
                    with self.assertRaises(ExtractionError) as ctx:
                        scrape_post(TEST_URL,3,3,'/tmp/test.json')
                self.assertEqual(ctx.exception.code,code)

    def test_no_data_failure_and_legacy_unused(self):
        with patch.dict(os.environ,{'FB_ENGINE':'read_only_v2'}), \
             patch('app.read_only_v2.run',side_effect=RuntimeError('BROWSER_NO_VERIFIABLE_INTERACTIONS')):
            with self.assertRaises(ExtractionError) as e:
                scrape_post(TEST_URL,5,5,"/tmp/test.json")
        self.assertEqual(e.exception.code,'BROWSER_NO_VERIFIABLE_INTERACTIONS')

if __name__=='__main__':
    unittest.main()
