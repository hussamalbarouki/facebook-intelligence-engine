import unittest
from app.engine import validate_facebook_url, normalize_post

class EngineTest(unittest.TestCase):
    def test_facebook_only(self):
        self.assertEqual(validate_facebook_url('https://www.facebook.com/test/posts/123'), 'https://www.facebook.com/test/posts/123')
        for link in ['http://facebook.com/post/1', 'https://facebook.com.evil.com/x', 'https://example.com/x', 'https://facebook.com/']:
            with self.subTest(link=link), self.assertRaises(ValueError):
                validate_facebook_url(link)

    def test_normalize(self):
        post = {'post_id':'12','comments':1,'reactors':[{'name':'A','link':'https://fb.com/a','type':'like'}],
                'comments_full':[{'commenter_name':'B','comment_text':'سلام','replies':[]}]}
        result = normalize_post(post, 'https://facebook.com/p/1',100,100)
        self.assertEqual(result['reactors'][0]['name'], 'A')
        self.assertEqual(result['comments'][0]['text'], 'سلام')
        self.assertFalse(result['coverage']['complete'])

if __name__ == '__main__': unittest.main()