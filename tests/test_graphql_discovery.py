import unittest

from app.graphql_discovery import (find_javascript_sources, allowed_js_url,
                                   alias_operation_id, extend_discovery)

BASE='https://www.facebook.com/example/posts/123456789012'

class JsOperationDiscoveryTest(unittest.TestCase):
    def test_facebook_bootloader_scripts_embedded_in_html(self):
        html=r'''<html><head>
        <script>bigPipe.onPageletArrive({"rsrcMap":{"Ab":{"type":"js","src":"https:\/\/static.xx.fbcdn.net\/rsrc.php\/v5\/hello.js"}}})</script>
        <script src="https://static.xx.fbcdn.net/rsrc.php/v3/regular.js"></script>
        </head></html>'''
        found=find_javascript_sources(html,BASE)
        self.assertEqual(len(found),2)
        self.assertIn('https://static.xx.fbcdn.net/rsrc.php/v3/regular.js',found)
        self.assertIn('https://static.xx.fbcdn.net/rsrc.php/v5/hello.js',found)

    def test_escaped_embedded_json_attributes(self):
        html=r'''<script>var a={\"src\":\"https:\\/\\/static.xx.fbcdn.net\\/rsrc.php\\/v7\\/double.js\"};</script>'''
        urls=find_javascript_sources(html,BASE)
        self.assertEqual(urls,['https://static.xx.fbcdn.net/rsrc.php/v7/double.js'])

    def test_reject_external_or_unsafe_script_targets(self):
        for url in ('https://attacker.example/secret.js',
                    'http://static.xx.fbcdn.net/evil.js',
                    'https://static.xx.fbcdn.net.evil.net/payload.js',
                    'https://user:pass@static.xx.fbcdn.net/a.js',
                    'https://www.facebook.com/profile.php'):
            with self.subTest(url=url):
                self.assertIsNone(allowed_js_url(url,BASE))

    def test_limit_and_dedupe(self):
        html='<script src="https://static.xx.fbcdn.net/a.js"></script>'*20
        urls=find_javascript_sources(html,BASE,limit=3)
        self.assertEqual(urls,['https://static.xx.fbcdn.net/a.js'])

    def test_alias_only_exact_document_identity(self):
        target='CometSinglePostDialogContentQuery_facebookRelayOperation'
        self.assertEqual(alias_operation_id({
            'CometSinglePostDialogContentQuery.graphql':'123456789012345'},target),
            '123456789012345')
        self.assertIsNone(alias_operation_id({
            'SomeOtherQuery.graphql':'123456789012345'},target))
        self.assertIsNone(alias_operation_id({
            'CometSinglePostDialogContentQuery.graphql':'123456789012345',
            'CometSinglePostDialogContentQuery$Parameters':'987654321098765'},target))
        self.assertIsNone(alias_operation_id({
            'CometSinglePostDialogContentQuery.graphql':'not-a-doc-id'},target))

    def test_extend_discovery_uses_facebook_script_urls(self):
        class Fake:
            def _get_javascript_links(self,text):
                return []
        class Ctx:
            operation_discovery=Fake()
        c=Ctx()
        extend_discovery(c,BASE)
        src='<script>({"src":"https:\\/\\/static.xx.fbcdn.net\\/a.js"})</script>'
        self.assertEqual(c.operation_discovery._get_javascript_links(src),
                         ['https://static.xx.fbcdn.net/a.js'])
        self.assertEqual(c.operation_discovery.last_candidate_count,1)

if __name__=='__main__':
    unittest.main()
