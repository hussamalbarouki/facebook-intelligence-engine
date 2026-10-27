import os
import tempfile
import time
import unittest
from fastapi.testclient import TestClient

os.environ['API_KEY']='A'*48
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='fb-import-test-')
from app.main import create_app
from app.engine import normalize_post

KEY='T'*48
POST='https://www.facebook.com/example/posts/123456789'

def fake_scraper(url, comments, reactors, cookie_path=None):
    return normalize_post({'post_id':'123456789','available':True,'comments':2,'likes':1,
                           'comments_full':[{'comment_id':'c1','commenter_name':'Arabic','comment_text':'تجربة','replies':[]}],
                           'reactors':[{'name':'User','link':'https://facebook.com/test','type':'like'}]},url,comments,reactors)

class ApiTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=create_app(self.temp.name,KEY,fake_scraper)
        self.client=TestClient(self.app)
        self.client.__enter__()
        self.headers={'X-API-Key':KEY}
    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.temp.cleanup()
    def req(self,method,path,**kwargs):
        return self.client.request(method,path,headers=self.headers,**kwargs)
    def test_auth_and_cookie_roundtrip(self):
        self.assertEqual(self.client.get('/v1/status').status_code,401)
        data=self.req('PUT','/v1/facebook/cookies',json={'cookies':{'c_user':'123','xs':'abc','datr':'abcde'}})
        self.assertEqual(data.status_code,200,data.text)
        self.assertNotIn('abcde',str(data.json()))
        # Reject actual secret values only in the status payload, not arbitrary
        # digit fragments that may also occur in timestamps.
        status=self.req('GET','/v1/status').json()
        self.assertNotIn("'c_user': '123'",str(status))
        self.assertNotIn("'xs': 'abc'",str(status))
        self.assertNotIn("'datr': 'abcde'",str(status))
        with self.app.state.vault.temporary_cookie_file() as path:
            import json
            with open(path) as f: cookies=json.load(f)
            self.assertTrue(any(c['name']=='c_user' for c in cookies))
        self.assertFalse(__import__('os').path.exists(path))
        self.assertFalse(self.req('DELETE','/v1/facebook/cookies').json()['configured'])
    def test_settings(self):
        x=self.req('PATCH','/v1/settings',json={'default_comments_limit':800,'max_comments_limit':200})
        self.assertEqual(x.status_code,422)
        x=self.req('PATCH','/v1/settings',json={'default_comments_limit':10,'request_cooldown_seconds':0})
        self.assertEqual(x.status_code,200)
        self.assertEqual(x.json()['default_comments_limit'],10)
    def test_queue_and_pagination(self):
        self.req('PATCH','/v1/settings',json={'request_cooldown_seconds':0})
        body={'url':POST,'comments_limit':10,'reactors_limit':10,'client_job_id':'php-unique-99'}
        r=self.req('POST','/v1/jobs',json=body)
        self.assertEqual(r.status_code,202,r.text)
        jid=r.json()['job_id']
        r2=self.req('POST','/v1/jobs',json=body)
        self.assertTrue(r2.json()['reused'])
        self.assertEqual(jid,r2.json()['job_id'])
        for _ in range(50):
            state=self.req('GET',f'/v1/jobs/{jid}').json()['status']
            if state=='completed':break
            time.sleep(0.05)
        self.assertEqual(state,'completed')
        result=self.req('GET',f'/v1/jobs/{jid}/result?limit=1').json()
        self.assertEqual(result['comments'][0]['text'],'تجربة')
        self.assertEqual(result['reactors'][0]['name'],'User')
        self.assertFalse(result['coverage']['complete'])
        self.assertEqual(self.req('GET','/v1/jobs').json()['total'],1)
        self.assertEqual(self.req('POST',f'/v1/jobs/{jid}/retry').status_code,409)
    def test_browser_diagnostics_endpoint_uses_saved_job_and_never_exposes_secrets(self):
        from unittest.mock import patch
        self.req('PUT','/v1/facebook/cookies',
                 json={'cookies':{'c_user':'sensitive-user-id','xs':'sensitive-cookie-token'}})
        job=self.req('POST','/v1/jobs',
                     json={'url':POST,'comments_limit':3,'reactors_limit':3}).json()
        jid=job['job_id']
        report={'source':'browser','status':'interaction_shapes_unrecognized',
                'graphql_seen':9,'graphql_decoded':9,
                'comment_shape_nodes':2,'comment_containers':4,'reactor_containers':1,
                'comments_extracted':0,'reactors_extracted':0,
                'rendered':{'comment_permalink_links':0}}
        with patch('app.browser_engine.scrape_with_browser',return_value=report) as browser:
            response=self.req('POST',f"/v1/jobs/{jid}/browser-diagnostics")
        self.assertEqual(response.status_code,200,response.text)
        value=response.json()
        self.assertEqual(value['status'],'interaction_shapes_unrecognized')
        self.assertEqual(value['graphql_seen'],9)
        self.assertNotIn('sensitive-user-id',response.text)
        self.assertNotIn('sensitive-cookie-token',response.text)
        browser.assert_called_once()
        self.assertEqual(browser.call_args.kwargs['diagnostic_only'],True)
        unauth=self.client.post(f"/v1/jobs/{jid}/browser-diagnostics")
        self.assertEqual(unauth.status_code,401)

    def test_facebook_url_only(self):
        for u in ['https://facebook.com.evil.example/a','http://facebook.com/x','https://example.com/x']:
            self.assertEqual(self.req('POST','/v1/jobs',json={'url':u}).status_code,422)