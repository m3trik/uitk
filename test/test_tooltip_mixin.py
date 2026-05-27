# !/usr/bin/python
# coding=utf-8
"""Unit tests for the tooltip mixin helpers (fmt / kbd / hl).

These are pure HTML-building helpers — no Qt widgets needed — so the tests
stay fast and don't require setup_qt_application().
"""

import unittest

from uitk.widgets.mixins.tooltip_mixin import fmt, kbd, hl


class TestKbd(unittest.TestCase):
    """Tests for kbd() keyboard chip helper."""

    def test_single_key_renders_as_chip(self):
        html = kbd("Enter")
        self.assertIn("Enter", html)
        self.assertIn("<span", html)
        # The chip styling distinguishes it from normal text
        self.assertIn("border-radius", html)

    def test_multiple_keys_joined_with_plus(self):
        html = kbd("Ctrl", "Z")
        self.assertIn("Ctrl", html)
        self.assertIn("Z", html)
        self.assertIn(" + ", html)
        # Each key gets its own <span>
        self.assertEqual(html.count("<span"), 2)

    def test_no_keys_returns_empty(self):
        self.assertEqual(kbd(), "")


class TestHl(unittest.TestCase):
    """Tests for hl() inline-highlight helper."""

    def test_wraps_text_with_color_span(self):
        html = hl("foo")
        self.assertIn("foo", html)
        self.assertIn("<span", html)
        self.assertIn("color:", html)

    def test_custom_color(self):
        html = hl("warn", color="#f00")
        self.assertIn("#f00", html)
        self.assertIn("warn", html)


class TestFmt(unittest.TestCase):
    """Tests for fmt() rich-text tooltip builder."""

    def test_empty_call_returns_empty(self):
        self.assertEqual(fmt(), "")

    def test_title_only(self):
        html = fmt(title="My Tool")
        self.assertIn("My Tool", html)
        self.assertIn("<b>", html)

    def test_body_only(self):
        html = fmt(body="Tool description.")
        self.assertIn("Tool description.", html)
        self.assertIn("<p", html)

    def test_bullets_render_as_unordered_list(self):
        html = fmt(bullets=["First", "Second"])
        self.assertIn("<ul", html)
        self.assertIn("<li>First</li>", html)
        self.assertIn("<li>Second</li>", html)

    def test_steps_render_as_ordered_list(self):
        html = fmt(steps=["Open file", "Click button"])
        self.assertIn("<ol", html)
        self.assertIn("<li>Open file</li>", html)
        self.assertIn("<li>Click button</li>", html)

    def test_rows_render_as_table(self):
        html = fmt(rows=[("Type", "int"), ("Default", "0")])
        self.assertIn("<table", html)
        self.assertIn("<td", html)
        self.assertIn("Type", html)
        self.assertIn("int", html)

    def test_sections_render_with_headings(self):
        html = fmt(sections=[("Quick Start", ["Step 1", "Step 2"])])
        self.assertIn("Quick Start", html)
        self.assertIn("<li>Step 1</li>", html)
        self.assertIn("<li>Step 2</li>", html)

    def test_notes_render_after_main_content(self):
        html = fmt(title="X", notes=["Tip: use Ctrl-click."])
        self.assertIn("Tip: use Ctrl-click.", html)
        self.assertIn("note:", html)
        # Notes come after the title
        self.assertLess(html.index("X"), html.index("Tip: use Ctrl-click."))

    def test_ordering_title_body_bullets_steps_rows_sections_notes(self):
        html = fmt(
            title="T",
            body="B",
            bullets=["bul"],
            steps=["stp"],
            rows=[("k", "v")],
            sections=[("Sec", ["si"])],
            notes=["nt"],
        )
        # Verify each segment appears in declared order.
        order = ["T", "B", "bul", "stp", "k", "Sec", "si", "nt"]
        positions = [html.index(s) for s in order]
        self.assertEqual(positions, sorted(positions))

    def test_inline_html_in_bullets_is_preserved(self):
        html = fmt(bullets=["<b>Bold</b> — desc"])
        self.assertIn("<b>Bold</b>", html)

    def test_kbd_embeds_into_bullets(self):
        html = fmt(bullets=[f"{kbd('Ctrl', 'Z')} — Undo"])
        self.assertIn("Ctrl", html)
        self.assertIn("Z", html)
        self.assertIn("Undo", html)


if __name__ == "__main__":
    unittest.main()
