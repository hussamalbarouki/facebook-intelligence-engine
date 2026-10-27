import unittest
from app.facebook_session import extract_dtsg, inspect_session, _page_status, configure_facebook_session
import requests

class Response:
    def __init__(self, text, code=200, url='https://www.facebook.com/'):
        self.text=text
        self.status_code=code
        self.url=url

class SessionTest(unittest.TestCase):
    def test_token_formats(self):
        for body in (
            '{"name":"fb_dtsg","value":"AQH-test-abcde12345"}',
            '["DTSGInitialData",[],{"token":"AQH-test-abcde12345"}]',
            '["DTSGInitData",[],{"token":"AQH-test-abcde12345"}]',
            '<input name="fb_dtsg" value="AQH-test-abcde12345">',
            '"DTSGInitialData":{"token":"AQH-test-abcde12345"}',
        ):
            with self.subTest(body=body):self.assertEqual(extract_dtsg(body),'AQH-test-abcde12345')
        self.assertIsNone(extract_dtsg('<html>No auth here</html>'))
    def test_session_status_no_secret(self):
        report,token=inspect_session(lambda u:Response('["DTSGInitialData",[],{"token":"secret-abcdef123456"}]'))
        self.assertEqual(report['status'],'token_available')
        self.assertTrue(report['token_available'])
        self.assertEqual(token,'secret-abcdef123456')
        self.assertNotIn(token,str(report))
    def test_login_wall_is_not_successful_session(self):
        report,token=inspect_session(lambda u:Response('<form><input name="email"><input name="pass"></form>'))
        self.assertEqual(report['status'],'facebook_login_required')
        self.assertIsNone(token)
    def test_http_400_distinct_from_missing_token(self):
        self.assertEqual(_page_status(Response('Bad Request', 400)), 'facebook_http_bad_request')

    def test_use_actual_requests_ua_not_fake_chrome(self):
        session=requests.Session()
        session.headers.update({
            'User-Agent':'Mozilla/5.0 Fake Chrome',
            'sec-ch-ua':'\"Chromium\";v=\"152\"',
            'sec-fetch-site':'same-origin',
            'priority':'u=1, i',
        })
        configured=configure_facebook_session(session)
        self.assertIs(configured,session)
        self.assertEqual(session.headers['User-Agent'],requests.utils.default_headers()['User-Agent'])
        for key in session.headers:
            self.assertFalse(key.lower().startswith(('sec-ch-ua','sec-fetch-')))

    def test_restricted(self):
        report,token=inspect_session(lambda u:Response('Restricted',429))
        self.assertEqual(report['status'],'facebook_access_restricted')
    def test_missing_token_not_valid(self):
        report,token=inspect_session(lambda u:Response('<html>Hello</html>'))
        self.assertEqual(report['status'],'fb_dtsg_unavailable')
        self.assertFalse(report['token_available'])

if __name__=='__main__':unittest.main()

class IntegrationUnitTest(unittest.TestCase):
    def test_endpoint_requires_auth_and_is_redacted(self):
        import os, tempfile
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as tmp:
            os.environ['DATA_DIR']=tmp
            os.environ['API_KEY']='J'*48
            from app.main import create_app
            app=create_app(tmp,'J'*48,lambda *args:None)
            with TestClient(app) as c:
                self.assertEqual(c.get('/v1/facebook/session-check').status_code,401)
                with patch('app.main.probe_cookie_file', return_value={'status':'token_available','token_available':True}) as f:
                    r=c.get('/v1/facebook/session-check',headers={'X-API-Key':'J'*48})
                    self.assertEqual(r.status_code,200)
                    self.assertTrue(r.json()['token_available'])
                    self.assertEqual(f.call_count,1)