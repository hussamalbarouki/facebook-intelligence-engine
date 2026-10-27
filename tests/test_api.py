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
        self.assertNotIn('123',str(self.req('GET','/v1/status').json()))
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
    def test_facebook_url_only(self):
        for u in ['https://facebook.com.evil.example/a','http://facebook.com/x','https://example.com/x']:
            self.assertEqual(self.req('POST','/v1/jobs',json={'url':u}).status_code,422)