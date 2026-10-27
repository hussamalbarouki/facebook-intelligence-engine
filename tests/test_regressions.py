import sys
import types
import unittest
from unittest.mock import patch

from app.engine import (
    ExtractionError, _legacy_scrape, parse_post_reference, scrape_post,
)

URL='https://www.facebook.com/NASA/posts/1234567890'

class AdapterRegressions(unittest.TestCase):
    def test_reference_parsing(self):
        self.assertEqual(parse_post_reference(URL),('id','1234567890'))
        self.assertEqual(parse_post_reference('https://www.facebook.com/story.php?story_fbid=9876543210&id=111111111'),('id','9876543210'))
        self.assertEqual(parse_post_reference('https://www.facebook.com/user/posts/pfbid02abcdef1234567890'),('pfbid','pfbid02abcdef1234567890'))
        self.assertIsNone(parse_post_reference('https://facebook.com/share/p/asdfgh'))
    def test_legacy_empty_shell_must_fail(self):
        fake=types.SimpleNamespace(get_posts=lambda **kw: iter([{'post_url':URL,'original_request_url':URL}]))
        with patch.dict(sys.modules,{'facebook_scraper':fake}):
            with self.assertRaises(ExtractionError) as ctx:
                _legacy_scrape(URL,5,5,None)
        self.assertEqual(ctx.exception.code,'POST_NOT_PARSED')
    def test_scrape_not_completed_when_empty(self):
        fake=types.SimpleNamespace(get_posts=lambda **kw:iter([{'post_url':URL,'original_request_url':URL}]))
        with patch.dict(sys.modules,{'facebook_scraper':fake}):
            with self.assertRaises(ExtractionError):
                scrape_post(URL,5,5,None)
    def test_gql_adapter_normalizes_data(self):
        class Profile:
            name='Amina'
            url='https://facebook.com/amina'
        class Comment:
            owner=Profile()
            id='c1';text='مرحبا';created_time=1793110000;reply_count=0
        class Reactor:
            profile=Profile();reaction_type_id='1'
        class Post:
            id='1234567890';url=URL;text='Post';creation_time=1793110000
            owner=Profile();comments_count=1;reaction_count='1';share_count=0
            top_reaction_breakdown=[{'name':'Like','count':1}]
            @classmethod
            def from_post_id(cls,ctx,post_id):return cls()
            def get_comments(self):return iter([Comment()])
            def get_reactors(self):return iter([Reactor()])
        fake=types.SimpleNamespace(Post=Post,FacebookContext=lambda **kw:object())
        with patch.dict(sys.modules,{'facebook_gql_scraper':fake}):
            result=scrape_post(URL,2,2,'/tmp/fakecookie.json')
        self.assertEqual(result['comments'][0]['name'],'Amina')
        self.assertEqual(result['reactors'][0]['type'],'like')
        self.assertEqual(result['coverage']['adapter'],'graphql')

if __name__=='__main__':unittest.main()