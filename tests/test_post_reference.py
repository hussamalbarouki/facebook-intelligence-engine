import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.engine import (ExtractionError, parse_post_reference, is_share_link,
                        resolve_share_link, resolve_pfbid_numeric_id)

SHARE="https://www.facebook.com/share/p/AbCdEfGh/"
POST="https://www.facebook.com/example/posts/1234567890123"
PFBID="pfbid02abcdefghijklmnopqrstuvwx"

class Response:
    def __init__(self,text='',status_code=200,headers=None,url=None):
        self.text=text
        self.status_code=status_code
        self.headers=headers or {}
        self.url=url

class ShareResolutionTest(unittest.TestCase):
    def _cookie_file(self):
        temp=tempfile.NamedTemporaryFile('w',suffix='.json',delete=False)
        json.dump([{'name':'c_user','value':'u','domain':'.facebook.com','path':'/'},
                   {'name':'xs','value':'x','domain':'.facebook.com','path':'/'}],temp)
        temp.close()
        return temp.name

    def test_share_marked_opaque(self):
        self.assertTrue(is_share_link(SHARE))
        self.assertIsNone(parse_post_reference(SHARE))
        self.assertFalse(is_share_link(POST))

    def test_canonical_og_url_resolves_post(self):
        with tempfile.TemporaryDirectory() as directory:
            path=directory+'/cookies.json'
            with open(path,'w') as f:json.dump([],f)
            session=Mock()
            session.__enter__=Mock(return_value=session)
            session.__exit__=Mock(return_value=False)
            session.get.return_value=Response('<meta property="og:url" content="'+POST+'">',url=SHARE)
            with patch('requests.Session',return_value=session):
                result=resolve_share_link(SHARE,path)
        self.assertEqual(result,(POST,('id','1234567890123')))

    def test_reject_external_redirect(self):
        with tempfile.TemporaryDirectory() as directory:
            path=directory+'/cookies.json'
            with open(path,'w') as f:json.dump([],f)
            session=Mock()
            session.__enter__=Mock(return_value=session)
            session.__exit__=Mock(return_value=False)
            session.get.return_value=Response(status_code=302,headers={'Location':'https://evil.test/steal'})
            with patch('requests.Session',return_value=session):
                with self.assertRaises(ValueError):
                    resolve_share_link(SHARE,path)
        session.get.assert_called_once()

    def test_numeric_id_from_matching_pfbid_hydration(self):
        html='{"post_id":"123456789012345","url":"https://www.facebook.com/example/posts/'+PFBID+'"}'
        ctx=Mock()
        ctx.get.return_value=Response(html,url='https://www.facebook.com/example/posts/'+PFBID)
        self.assertEqual(resolve_pfbid_numeric_id(ctx,'https://www.facebook.com/example/posts/'+PFBID,PFBID),'123456789012345')

    def test_numeric_id_ambiguous_fails_closed(self):
        html='{"post_id":"123456789012345","url":"'+PFBID+'"},{"postId":"987654321000000","url":"'+PFBID+'"}'
        ctx=Mock()
        ctx.get.return_value=Response(html,url='https://www.facebook.com/example/posts/'+PFBID)
        with self.assertRaises(ExtractionError) as result:
            resolve_pfbid_numeric_id(ctx,'https://www.facebook.com/example/posts/'+PFBID,PFBID)
        self.assertEqual(result.exception.code,'FACEBOOK_PFBID_AMBIGUOUS')

if __name__=='__main__':
    unittest.main()
