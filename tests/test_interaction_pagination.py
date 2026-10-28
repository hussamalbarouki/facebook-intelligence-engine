"""Regression tests for honest, read-only comment/reaction pagination."""
import re
import unittest
from app.interaction_pagination import (
    _explicit_more,MAX_STALLED_PASSES,ALL_COMMENT_LABELS,
    REACTION_LIST_LABEL,REACTION_DIALOG,select_all_comments,select_all_reactions)
from app.read_only_v2 import _is_safe_open_label

class PaginationSafetyTests(unittest.TestCase):
    def test_explicit_more_is_read_only(self):
        for label in ('View 20 more comments','Load more replies',
                      'Voir plus de commentaires','عرض المزيد من التعليقات'):
            with self.subTest(label=label):
                self.assertTrue(_explicit_more(label))
        for label in ('Like','Share','Reply','Send','Follow','J’aime',
                      'أعجبني','مشاركة','إرسال','लाइक','شیئر'):
            with self.subTest(label=label):
                self.assertFalse(_explicit_more(label))

    def test_bounded_stalls_not_single_virtualized_batch(self):
        self.assertGreaterEqual(MAX_STALLED_PASSES,8)

    def test_sort_selection_languages(self):
        for label in ('All comments','Tous les commentaires',
                      'جميع التعليقات','सभी टिप्पणियाँ','تمام تبصرے'):
            self.assertIn(label,ALL_COMMENT_LABELS)

    def test_reaction_chooser_requires_positive_evidence(self):
        self.assertTrue(REACTION_DIALOG.search('Reactions'))
        self.assertTrue(REACTION_LIST_LABEL.search('View all reactions'))
        self.assertFalse(REACTION_LIST_LABEL.search('Like'))
        self.assertFalse(REACTION_LIST_LABEL.search('Follow'))

    def test_reel_comment_control_not_state_change(self):
        self.assertTrue(_is_safe_open_label('Commenter',video=True))
        for unsafe in ('Like','Send comment','Reply','Follow','Share'):
            self.assertFalse(_is_safe_open_label(unsafe,video=True))

if __name__=='__main__':
    unittest.main()
