"""Security and persistence contracts for interactive remote browser login."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.browser_login import LoginSession,profile_ready
from app.browser_login_routes import _origin_allowed
from app.main import create_app
from app.engine import scrape_post

KEY='B'*48

class BrowserLoginTests(unittest.TestCase):
    def test_same_origin_required(self):
        self.assertTrue(_origin_allowed('https://dia.ee-link.info','dia.ee-link.info'))
        self.assertFalse(_origin_allowed('https://evil.example','dia.ee-link.info'))
        self.assertFalse(_origin_allowed(None,'dia.ee-link.info'))
        self.assertFalse(_origin_allowed('http://dia.ee-link.info','dia.ee-link.info'))
        self.assertTrue(_origin_allowed('https://testserver','testserver'))

    def test_profile_marker_requires_directory_and_marker(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(profile_ready(d))
            p=Path(d)/'facebook-profile'
            p.mkdir()
            self.assertFalse(profile_ready(d))
            (Path(d)/'facebook-profile-ready.json').write_text('{"saved":true}')
            self.assertTrue(profile_ready(d))

    def test_no_shared_password_or_session_token_in_public_html(self):
        with tempfile.TemporaryDirectory() as d:
            app=create_app(d,KEY,lambda *a,**kw:{})
            with TestClient(app,base_url='https://testserver') as client:
                html=client.get('/browser-login')
                self.assertEqual(html.status_code,200)
                self.assertNotIn(KEY,html.text)
                self.assertIn('no-store',html.headers['cache-control'])
                self.assertIn("frame-ancestors 'none'",html.headers['content-security-policy'])
                self.assertEqual(client.post('/v1/browser-session/start',
                    headers={'Origin':'https://testserver'}).status_code,401)
                self.assertEqual(client.post('/v1/browser-session/start',
                    headers={'X-API-Key':KEY,'Origin':'https://evil.test'}).status_code,403)
                self.assertEqual(client.get('/v1/browser-session/status').status_code,401)

    def test_admin_cookie_is_httponly_secure_and_same_site(self):
        with tempfile.TemporaryDirectory() as d:
            app=create_app(d,KEY,lambda *a,**kw:{})
            mgr=app.state.login_manager
            with TestClient(app,base_url='https://testserver') as client, \
                 patch.object(mgr,'start',return_value='random-test-session'), \
                 patch.object(mgr,'authorize',return_value=True), \
                 patch.object(mgr,'status',return_value={
                    'profile_saved':False,'login_active':True,'controller_authorized':True,
                    'remaining_seconds':100}), \
                 patch.object(mgr,'save',return_value={'saved':True}):
                r=client.post('/v1/browser-session/start',
                  headers={'Origin':'https://testserver','X-API-Key':KEY})
                self.assertEqual(r.status_code,200,r.text)
                self.assertIn('httponly',r.headers['set-cookie'].lower())
                self.assertIn('secure',r.headers['set-cookie'].lower())
                self.assertIn('samesite=strict',r.headers['set-cookie'].lower())
                self.assertNotIn('random-test-session',r.text)
                self.assertTrue(client.get('/v1/browser-session/status').json()['controller_authorized'])
                self.assertEqual(client.post('/v1/browser-session/save',
                    headers={'Origin':'https://other.test'}).status_code,403)
                self.assertTrue(client.post('/v1/browser-session/save',
                    headers={'Origin':'https://testserver'}).json()['saved'])

    def test_saved_profile_counts_as_configured_session_in_admin_api(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'facebook-profile'
            p.mkdir()
            (Path(d)/'facebook-profile-ready.json').write_text('{"saved":true}')
            app=create_app(d,KEY,lambda *a,**kw:{})
            with TestClient(app,base_url='https://testserver') as client:
                out=client.get('/v1/status',headers={'X-API-Key':KEY}).json()
                self.assertTrue(out['saved_browser_profile'])
                self.assertTrue(out['cookies']['configured'])
                self.assertEqual(out['cookies']['source'],'saved_browser_profile')
                diag=client.get('/v1/facebook/session-check',
                               headers={'X-API-Key':KEY}).json()
                self.assertTrue(diag['browser_profile_saved'])
                self.assertFalse(diag['token_available'])

    def test_saved_profile_routing_without_any_manual_cookie_export(self):
        url='https://www.facebook.com/share/v/1EcqWbUzGA/'
        with patch.dict(os.environ,{'FB_ENGINE':'read_only_v2'}), \
             patch('app.browser_login.profile_ready',return_value=True), \
             patch('app.read_only_v2.run',return_value={'comments':[{'id':'12345'}]}) as mock:
            result=scrape_post(url,5,0,None)
            self.assertEqual(result['comments'][0]['id'],'12345')
            self.assertEqual(mock.call_args.args[0],url)
            self.assertIsNone(mock.call_args.args[3])

if __name__=='__main__':
    unittest.main()
