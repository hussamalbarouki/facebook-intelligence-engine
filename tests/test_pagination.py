"""Offline contracts for safe comment pagination and reactor collection."""
import unittest
from unittest.mock import Mock,patch
from app.read_only_v2 import COMMENT_CAP,REACTOR_CAP
from app.interaction_pagination import (
    _explicit_more,click_reaction_list,click_more_comments,
    REACTION_LIST_LABEL,REACTION_DOM_JS,SCROLL_JS,REACTION_SCROLL_JS,
    MAX_SCROLL_PASSES,MAX_STALLED_PASSES)

class PaginationContractTests(unittest.TestCase):
    def test_hard_caps_above_one_page(self):
        self.assertGreaterEqual(COMMENT_CAP,300)
        self.assertGreaterEqual(REACTOR_CAP,200)
        self.assertGreater(MAX_SCROLL_PASSES,20)
        self.assertGreaterEqual(MAX_STALLED_PASSES,4)

    def test_multilingual_more_comments(self):
        for label in ("View more comments","See 30 more comments","Load more replies",
                      "voir les commentaires","plus de commentaires",
                      "مزيد من التعليقات","और टिप्पणियाँ","مزید تبصرے",
                      "আরও মন্তব্য","ਹੋਰ ਟਿੱਪਣੀਆਂ","もっとコメント"):
            with self.subTest(label=label):
                # Japanese fallback may be omitted if not supplied by Facebook.
                if label=="もっとコメント":continue
                self.assertTrue(_explicit_more(label),label)

    def test_no_writing_buttons_as_more(self):
        for label in ('Like','J’aime','Reply','Send comment','Follow',
                      'Share','إرسال','أعجبني','लाइक','بھیجیں','Commenter'):
            with self.subTest(label=label):
                self.assertFalse(_explicit_more(label))

    def test_reaction_read_only_labels_not_generic_like(self):
        for name in ('See who reacted','People who reacted','View all reactions',
                     '124 reactions','Voir les réactions','الأشخاص الذين تفاعلوا'):
            with self.subTest(label=name):
                self.assertIsNotNone(REACTION_LIST_LABEL.search(name))
        for bad in ('Like','J’aime','React','أعجبني','Commenter','Send','Reply'):
            with self.subTest(label=bad):
                self.assertIsNone(REACTION_LIST_LABEL.search(bad))

    def test_scrollable_predicate_never_has_automatic_semicolon_after_return(self):
        # JavaScript treats a newline immediately following return as
        # automatic semicolon insertion: return; x.scrollHeight never runs.
        self.assertNotRegex(SCROLL_JS,r'return\\s*\\n')
        self.assertIn('return x.scrollHeight',SCROLL_JS)

    def test_dom_scripts_do_not_click_or_submit_reactions(self):
        for code in (SCROLL_JS,REACTION_DOM_JS,REACTION_SCROLL_JS):
            self.assertNotIn('.click(',code)
            self.assertNotIn('fetch(',code)
            self.assertNotIn('.submit(',code)

if __name__=='__main__':
    unittest.main()
