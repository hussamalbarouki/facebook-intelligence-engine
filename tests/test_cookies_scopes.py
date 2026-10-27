import requests
import unittest

from app.secrets import _normalize_cookies
from app.facebook_session import apply_facebook_cookies

class CookieScopeTest(unittest.TestCase):
    def test_preserves_original_exported_browser_scopes(self):
        source=[
            {'name':'c_user','value':'user','domain':'.facebook.com','path':'/','secure':True},
            {'name':'xs','value':'token','domain':'.facebook.com','path':'/','secure':True},
            {'name':'scoped','value':'private','domain':'web.facebook.com','path':'/settings','secure':True},
        ]
        normalized=_normalize_cookies(source)
        self.assertEqual(normalized[2]['domain'],'web.facebook.com')
        self.assertEqual(normalized[2]['path'],'/settings')
        with requests.Session() as session:
            apply_facebook_cookies(session,normalized)
            public=session.prepare_request(requests.Request('GET','https://www.facebook.com/posts/123'))
            scoped=session.prepare_request(requests.Request('GET','https://web.facebook.com/settings/'))
            other=session.prepare_request(requests.Request('GET','https://web.facebook.com/posts/123'))
        self.assertIn('c_user=user', public.headers.get('Cookie',''))
        self.assertNotIn('scoped=private', public.headers.get('Cookie',''))
        self.assertIn('scoped=private',scoped.headers.get('Cookie',''))
        self.assertNotIn('scoped=private',other.headers.get('Cookie',''))

    def test_rejects_untrusted_domains_and_invalid_paths(self):
        base=[{'name':'c_user','value':'123'},{'name':'xs','value':'safe'}]
        for domain in ('facebook.com.evil.test','notfacebook.com','..facebook.com','a..facebook.com'):
            with self.subTest(domain=domain):
                with self.assertRaises(ValueError):
                    _normalize_cookies(base+[{'name':'t','value':'1','domain':domain}])
        with self.assertRaises(ValueError):
            _normalize_cookies(base+[{'name':'t','value':'1','path':'admin'}])

    def test_simple_cookie_inputs_still_work(self):
        normalized=_normalize_cookies({'c_user':'123','xs':'token'})
        self.assertEqual(len(normalized),2)
        self.assertTrue(all(c['domain']=='.facebook.com' and c['path']=='/' for c in normalized))

if __name__=='__main__':
    unittest.main()
