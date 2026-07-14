# !/usr/bin/python
# coding=utf-8
"""Regression tests for the RichText widget mixin (uitk.widgets.mixins.text).

Covers ``richTextSizeHint`` when ``has_rich_text`` was flipped True by
``_createRichTextLabel`` (reachable via ``setAlignment`` / ``getRichTextLabel``)
without any ``setRichText`` call populating the size-hint dict. The size hint
must fall back to the base widget's sizeHint instead of raising
AttributeError/KeyError.

Run standalone: python test/test_rich_text.py
"""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore  # noqa: E402
from uitk.widgets.checkBox import CheckBox  # noqa: E402


class TestRichTextSizeHintFallback(QtBaseTestCase):
    """``CheckBox.sizeHint`` is aliased to ``richTextSizeHint`` (text.py)."""

    def test_size_hint_after_set_alignment_before_set_text(self):
        cb = self.track_widget(CheckBox())
        # setAlignment creates a rich-text label (has_rich_text -> True) but
        # never populates the size-hint dict. sizeHint() must not raise.
        cb.setAlignment("AlignRight")
        self.assertTrue(cb.has_rich_text)
        size = cb.sizeHint()  # was: AttributeError
        self.assertIsInstance(size, QtCore.QSize)
        self.assertTrue(size.isValid())

    def test_size_hint_uses_populated_value_after_set_text(self):
        cb = self.track_widget(CheckBox())
        cb.setText("<b>Bold</b> label")  # setRichText populates the dict
        self.assertTrue(cb.has_rich_text)
        size = cb.sizeHint()
        self.assertIsInstance(size, QtCore.QSize)

    def test_size_hint_plain_widget(self):
        cb = self.track_widget(CheckBox())
        # No rich text at all -> base widget sizeHint path.
        size = cb.sizeHint()
        self.assertIsInstance(size, QtCore.QSize)


if __name__ == "__main__":
    unittest.main()
