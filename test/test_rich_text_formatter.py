# !/usr/bin/python
# coding=utf-8
"""Unit tests for the stateless RichTextFormatter HTML pipeline.

RichTextFormatter is the single source of truth for uitk's rich-text
vocabulary (used by MessageBox, TextViewBox, Footer). These tests lock its
pure string transforms so a future refactor can't silently change the
rendered output.

Run standalone: python -m test.test_rich_text_formatter
"""
import unittest

from conftest import BaseTestCase, QtBaseTestCase

from uitk.widgets.mixins.text import RichTextFormatter


class TestResolveBackground(BaseTestCase):
    """resolve_background maps a background param to a CSS colour or None."""

    def test_false_and_zero_disable(self):
        self.assertIsNone(RichTextFormatter.resolve_background(False))
        self.assertIsNone(RichTextFormatter.resolve_background(0))

    def test_true_is_opaque_default_grey(self):
        self.assertEqual(
            RichTextFormatter.resolve_background(True), "rgba(50,50,50,255)"
        )

    def test_float_sets_alpha_on_default_grey(self):
        self.assertEqual(
            RichTextFormatter.resolve_background(0.5), "rgba(50,50,50,127)"
        )
        self.assertEqual(
            RichTextFormatter.resolve_background(1.0), "rgba(50,50,50,255)"
        )

    def test_alpha_is_clamped(self):
        self.assertEqual(
            RichTextFormatter.resolve_background(2), "rgba(50,50,50,255)"
        )
        self.assertEqual(
            RichTextFormatter.resolve_background(-1), "rgba(50,50,50,0)"
        )

    def test_string_passes_through_verbatim(self):
        self.assertEqual(RichTextFormatter.resolve_background("red"), "red")
        self.assertEqual(
            RichTextFormatter.resolve_background("rgba(1,2,3,4)"), "rgba(1,2,3,4)"
        )


class TestInlineStyles(BaseTestCase):
    """apply_inline_styles swaps bare tags for style-bearing equivalents."""

    def test_bold_tag(self):
        self.assertEqual(
            RichTextFormatter.apply_inline_styles("<b>x</b>"),
            '<b style="font-weight: bold;">x</b>',
        )

    def test_mark_open_and_close(self):
        self.assertEqual(
            RichTextFormatter.apply_inline_styles("<mark>m</mark>"),
            '<font style="background-color: grey;">m</font>',
        )

    def test_untouched_text(self):
        self.assertEqual(RichTextFormatter.apply_inline_styles("plain"), "plain")


class TestPrefixStyles(BaseTestCase):
    """apply_prefix_styles colours level-prefix tokens via <hl> spans."""

    def test_error_prefix_wrapped(self):
        out = RichTextFormatter.apply_prefix_styles("Error: boom")
        self.assertTrue(out.startswith('<hl style="color:'))
        self.assertIn(">Error:</hl> boom", out)

    def test_all_known_tokens_covered(self):
        for token in ("Error:", "Warning:", "Note:", "Result:"):
            out = RichTextFormatter.apply_prefix_styles(token)
            self.assertEqual(out, RichTextFormatter.prefix_styles()[token])

    def test_unknown_prefix_untouched(self):
        self.assertEqual(
            RichTextFormatter.apply_prefix_styles("Debug: x"), "Debug: x"
        )


class TestFormat(BaseTestCase):
    """format() runs the full pipeline: align div + tokens + font wrap."""

    def test_wraps_in_alignment_div_when_absent(self):
        out = RichTextFormatter.format("hello", align="center", font_color="")
        self.assertEqual(out, "<div align='center'>hello</div>")

    def test_existing_align_is_not_double_wrapped(self):
        out = RichTextFormatter.format(
            "<div align='right'>x</div>", font_color=""
        )
        self.assertEqual(out, "<div align='right'>x</div>")

    def test_font_color_wraps_outermost(self):
        out = RichTextFormatter.format("hi", font_color="white")
        self.assertEqual(out, "<font color=white><div align='left'>hi</div></font>")

    def test_empty_font_color_skips_wrap(self):
        self.assertNotIn("<font color=", RichTextFormatter.format("hi", font_color=""))
        self.assertNotIn("<font color=", RichTextFormatter.format("hi", font_color=None))

    def test_font_size_applied_when_set(self):
        out = RichTextFormatter.format("hi", font_color="", font_size=3)
        self.assertEqual(out, "<font size=3><div align='left'>hi</div></font>")

    def test_font_size_skipped_when_none(self):
        self.assertNotIn(
            "<font size=", RichTextFormatter.format("hi", font_color="", font_size=None)
        )

    def test_prefix_and_inline_combine(self):
        out = RichTextFormatter.format("Error: <b>bad</b>", font_color="")
        self.assertIn('<b style="font-weight: bold;">bad</b>', out)
        self.assertIn(">Error:</hl>", out)


class TestLineBreaks(BaseTestCase):
    """A newline must render as a line break, not collapse to a space.

    Both bodies are ``Qt.RichText`` and HTML collapses whitespace, so every
    intended break was silently lost. Measured 2026-09-10 across the six
    packages: of 667 rich-text strings carrying a real newline, 654 are plain
    text that wants the break and 11 pair one with inline tags; only a single
    ``__main__`` demo pairs one with block-level HTML, and its newlines sit
    inside ``<pre>``.
    """

    def test_a_newline_becomes_a_break(self):
        out = RichTextFormatter.format("one\ntwo", font_color="")
        self.assertEqual(out, "<div align='left'>one<br>two</div>")

    def test_text_without_a_newline_is_untouched(self):
        self.assertEqual(
            RichTextFormatter.format("one two", font_color=""),
            "<div align='left'>one two</div>",
        )

    def test_an_explicit_break_does_not_double(self):
        """``<br>`` then a newline is how three extapps tooltips wrap SOURCE."""
        out = RichTextFormatter.format("<b>Title</b><br>\nbody", font_color="")
        self.assertEqual(out.count("<br>"), 1)

    def test_a_newline_before_an_explicit_break_does_not_double(self):
        out = RichTextFormatter.format("a\n<br>b", font_color="")
        self.assertEqual(out.count("<br>"), 1)

    def test_a_CRLF_line_ending_makes_ONE_break(self):
        """`TextViewBox` shows captured subprocess output, which is CRLF on
        Windows -- a stray CR would become a second break, i.e. a blank line
        between every line of a build log."""
        out = RichTextFormatter.format("one\r\ntwo", font_color="")
        self.assertEqual(out, "<div align='left'>one<br>two</div>")

    def test_a_bare_CR_still_breaks(self):
        out = RichTextFormatter.format("one\rtwo", font_color="")
        self.assertEqual(out, "<div align='left'>one<br>two</div>")

    def test_an_explicit_break_absorbs_a_CRLF_too(self):
        out = RichTextFormatter.format("a<br>\r\nb", font_color="")
        self.assertEqual(out.count("<br>"), 1)

    def test_preformatted_newlines_are_left_alone(self):
        """HTML already honours a newline inside ``<pre>``; a break doubles it."""
        out = RichTextFormatter.format("<pre>a\nb</pre>", font_color="")
        self.assertNotIn("<br>", out)
        self.assertIn("a\nb", out)

    def test_text_outside_a_pre_block_still_converts(self):
        out = RichTextFormatter.format(
            "head\n<pre>a\nb</pre>\ntail", font_color=""
        )
        self.assertEqual(out.count("<br>"), 2)
        self.assertIn("a\nb", out)


class TestLineBreaksRender(QtBaseTestCase):
    """The reported symptom, measured through Qt's own layout engine.

    ``blockCount`` is NOT the metric: ``<br>`` opens a line inside the current
    block, not a new block, so it reads 1 either way. What moves is the laid
    out text and the height -- measured offscreen, 22 px before and 36 px
    after on the same two words.
    """

    @staticmethod
    def _document(html):
        from qtpy import QtGui

        doc = QtGui.QTextDocument()
        doc.setHtml(html)
        doc.setTextWidth(400)
        return doc

    def test_an_unconverted_newline_collapses_to_a_space(self):
        """The defect itself, so the test below cannot pass vacuously."""
        doc = self._document("<div align='left'>one\ntwo</div>")
        self.assertEqual(doc.toPlainText(), "one two")

    def test_a_formatted_newline_survives_qt_layout(self):
        before = self._document("<div align='left'>one\ntwo</div>")
        after = self._document(RichTextFormatter.format("one\ntwo", font_color=""))
        self.assertEqual(after.toPlainText(), "one\ntwo")
        self.assertGreater(after.size().height(), before.size().height())


class TestPaletteOverride(BaseTestCase):
    """Subclasses retheme via class attrs without touching transform logic."""

    def test_subclass_palette_flows_into_prefix(self):
        class Neon(RichTextFormatter):
            LOG_COLORS = {"ERROR": "#ff00ff"}

        self.assertIn("#ff00ff", Neon.apply_prefix_styles("Error: x"))
        # Base class is unaffected by the subclass override.
        self.assertNotIn("#ff00ff", RichTextFormatter.apply_prefix_styles("Error: x"))


if __name__ == "__main__":
    unittest.main()
