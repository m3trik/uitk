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

from conftest import BaseTestCase

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
