# !/usr/bin/python
# coding=utf-8
"""Unit tests for the tooltip mixin helpers (fmt / kbd / hl).

These are pure HTML-building helpers — no Qt widgets needed — so the tests
stay fast and don't require setup_qt_application().
"""

import unittest

from uitk.widgets.mixins.tooltip_mixin import TooltipFormat


class TestKbd(unittest.TestCase):
    """Tests for kbd() keyboard chip helper."""

    def test_single_key_renders_as_chip(self):
        html = TooltipFormat.kbd("Enter")
        self.assertIn("Enter", html)
        self.assertIn("<span", html)
        # The chip styling distinguishes it from normal text
        self.assertIn("border-radius", html)

    def test_multiple_keys_joined_with_plus(self):
        html = TooltipFormat.kbd("Ctrl", "Z")
        self.assertIn("Ctrl", html)
        self.assertIn("Z", html)
        self.assertIn(" + ", html)
        # Each key gets its own <span>
        self.assertEqual(html.count("<span"), 2)

    def test_no_keys_returns_empty(self):
        self.assertEqual(TooltipFormat.kbd(), "")


class TestHl(unittest.TestCase):
    """Tests for hl() inline-highlight helper."""

    def test_wraps_text_with_color_span(self):
        html = TooltipFormat.hl("foo")
        self.assertIn("foo", html)
        self.assertIn("<span", html)
        self.assertIn("color:", html)

    def test_custom_color(self):
        html = TooltipFormat.hl("warn", color="#f00")
        self.assertIn("#f00", html)
        self.assertIn("warn", html)


class TestFmt(unittest.TestCase):
    """Tests for fmt() rich-text tooltip builder."""

    def test_empty_call_returns_empty(self):
        self.assertEqual(TooltipFormat.fmt(), "")

    def test_title_only(self):
        html = TooltipFormat.fmt(title="My Tool")
        self.assertIn("My Tool", html)
        self.assertIn("<b>", html)

    def test_body_only(self):
        html = TooltipFormat.fmt(body="Tool description.")
        self.assertIn("Tool description.", html)
        self.assertIn("<p", html)

    def test_bullets_render_as_unordered_list(self):
        html = TooltipFormat.fmt(bullets=["First", "Second"])
        self.assertIn("<ul", html)
        self.assertIn("<li>First</li>", html)
        self.assertIn("<li>Second</li>", html)

    def test_steps_render_as_ordered_list(self):
        html = TooltipFormat.fmt(steps=["Open file", "Click button"])
        self.assertIn("<ol", html)
        self.assertIn("<li>Open file</li>", html)
        self.assertIn("<li>Click button</li>", html)

    def test_rows_render_as_table(self):
        html = TooltipFormat.fmt(rows=[("Type", "int"), ("Default", "0")])
        self.assertIn("<table", html)
        self.assertIn("<td", html)
        self.assertIn("Type", html)
        self.assertIn("int", html)

    def test_sections_render_with_headings(self):
        html = TooltipFormat.fmt(sections=[("Quick Start", ["Step 1", "Step 2"])])
        self.assertIn("Quick Start", html)
        self.assertIn("<li>Step 1</li>", html)
        self.assertIn("<li>Step 2</li>", html)

    def test_notes_render_after_main_content(self):
        html = TooltipFormat.fmt(title="X", notes=["Tip: use Ctrl-click."])
        self.assertIn("Tip: use Ctrl-click.", html)
        self.assertIn("note:", html)
        # Notes come after the title
        self.assertLess(html.index("X"), html.index("Tip: use Ctrl-click."))

    def test_ordering_title_body_bullets_steps_rows_sections_notes(self):
        html = TooltipFormat.fmt(
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
        html = TooltipFormat.fmt(bullets=["<b>Bold</b> — desc"])
        self.assertIn("<b>Bold</b>", html)

    def test_kbd_embeds_into_bullets(self):
        html = TooltipFormat.fmt(bullets=[f"{TooltipFormat.kbd('Ctrl', 'Z')} — Undo"])
        self.assertIn("Ctrl", html)
        self.assertIn("Z", html)
        self.assertIn("Undo", html)


class TestPlaceholderPreview(unittest.TestCase):
    """Tests for placeholder_preview() live resolved-token tooltip builder."""

    def test_resolved_tokens_render_as_rows_with_values(self):
        html = TooltipFormat.placeholder_preview(
            "{scenes}/{name}",
            {"scenes": "scenes", "name": "shot"},
        )
        self.assertIn("{scenes}", html)
        self.assertIn("{name}", html)
        self.assertIn("scenes", html)
        self.assertIn("shot", html)
        self.assertIn("<table", html)

    def test_final_line_shows_resolved_path(self):
        html = TooltipFormat.placeholder_preview(
            "{scenes}/{name}",
            {"scenes": "scenes", "name": "shot"},
            final="C:/proj/scenes/shot",
            final_label="save dir →",
        )
        self.assertIn("C:/proj/scenes/shot", html)
        self.assertIn("save dir →", html)

    def test_final_defaults_to_resolved_result(self):
        html = TooltipFormat.placeholder_preview(
            "{scenes}/{name}", {"scenes": "scenes", "name": "shot"}
        )
        self.assertIn("scenes/shot", html)

    def test_final_empty_string_suppresses_line(self):
        html = TooltipFormat.placeholder_preview(
            "{name}", {"name": "shot"}, final=""
        )
        # The value still appears in the table, but there is no "→" final line.
        self.assertIn("shot", html)
        self.assertNotIn("→", html)

    def test_unresolved_token_flagged_in_note(self):
        html = TooltipFormat.placeholder_preview("{name}/{missing}", {"name": "shot"})
        self.assertIn("unresolved", html)
        self.assertIn("{missing}", html)
        self.assertIn("note:", html)

    def test_extra_notes_appended(self):
        html = TooltipFormat.placeholder_preview(
            "{scenes}", {"scenes": "scenes"}, notes=["<b>{scene}</b> is a typo"]
        )
        self.assertIn("is a typo", html)

    def test_descriptions_show_all_keys_even_if_unused_in_pattern(self):
        """The instructional view lists every supported key + meaning + value,
        even keys the current pattern doesn't use (so the help isn't lost)."""
        html = TooltipFormat.placeholder_preview(
            "{scenes}",  # pattern uses only one key
            {"scenes": "scenes", "name": "shot", "ws": "MyGame"},
            title="Folder Structure",
            body="Subfolder pattern for Save.",
            descriptions={
                "scenes": "workspace scenes folder",
                "name": "scene name (excludes the suffix)",
                "ws": "workspace folder name",
            },
        )
        # purpose (body) + every key's meaning + every key's current value.
        self.assertIn("Subfolder pattern for Save.", html)
        for token, meaning, value in (
            ("{scenes}", "workspace scenes folder", "scenes"),
            ("{name}", "scene name (excludes the suffix)", "shot"),
            ("{ws}", "workspace folder name", "MyGame"),
        ):
            self.assertIn(token, html)
            self.assertIn(meaning, html)
            self.assertIn(value, html)

    def test_descriptions_flag_unknown_typed_token(self):
        """A typed token that isn't a supported key is appended + flagged unknown."""
        html = TooltipFormat.placeholder_preview(
            "{scenes}/{nmae}",  # typo: nmae
            {"scenes": "scenes", "name": "shot"},
            descriptions={"scenes": "the scenes folder", "name": "the scene name"},
        )
        self.assertIn("{nmae}", html)
        self.assertIn("unknown", html)

    def test_body_renders_without_title(self):
        html = TooltipFormat.placeholder_preview(
            "{name}", {"name": "x"}, body="What this field does."
        )
        self.assertIn("What this field does.", html)

    def test_meanings_are_not_escaped(self):
        """Descriptions are author markup — inline HTML must survive."""
        html = TooltipFormat.placeholder_preview(
            "{name}",
            {"name": "x"},
            descriptions={"name": "the <b>scene</b> name"},
        )
        self.assertIn("the <b>scene</b> name", html)

    def test_blank_template_with_instruction_still_shows_help(self):
        """Clearing the field must not wipe the purpose/keys — instruction persists."""
        html = TooltipFormat.placeholder_preview(
            "",
            {"scenes": "scenes"},
            title="Folder Structure",
            body="Subfolder pattern.",
            descriptions={"scenes": "the scenes folder"},
        )
        self.assertIn("Folder Structure", html)
        self.assertIn("the scenes folder", html)
        self.assertNotIn("Type a pattern", html)

    def test_blank_template_returns_hint(self):
        html = TooltipFormat.placeholder_preview("   ", {"name": "x"})
        self.assertIn("Type a pattern", html)

    def test_blank_template_custom_empty_text(self):
        html = TooltipFormat.placeholder_preview("", {}, empty_text="nothing yet")
        self.assertEqual(html, "nothing yet")

    def test_empty_value_marked(self):
        html = TooltipFormat.placeholder_preview("{suffix}", {"suffix": ""})
        self.assertIn("(empty)", html)

    def test_data_values_are_html_escaped(self):
        """Token values are data: '<none>' / '&' must render literally, not as markup."""
        html = TooltipFormat.placeholder_preview(
            "{name}/{ws}",
            {"name": "<none>", "ws": "Rock & Roll"},
            final="C:/x/<none>/Rock & Roll",
        )
        self.assertIn("&lt;none&gt;", html)
        self.assertNotIn("<none>", html)  # would be eaten by Qt's tag parser
        self.assertIn("Rock &amp; Roll", html)

    def test_notes_are_not_escaped(self):
        """Notes are caller markup — bold etc. must survive."""
        html = TooltipFormat.placeholder_preview(
            "{name}", {"name": "x"}, notes=["<b>{scene}</b> is a typo"]
        )
        self.assertIn("<b>{scene}</b>", html)

    def test_invalid_pattern_reports_note(self):
        # A lone '{' is a malformed format string.
        html = TooltipFormat.placeholder_preview("{name}/{", {"name": "x"})
        self.assertIn("invalid pattern", html)

    def test_ordering_table_before_final_before_notes(self):
        html = TooltipFormat.placeholder_preview(
            "{name}/{missing}",
            {"name": "shot"},
            title="Resolves to:",
            final="X_FINAL_X",
        )
        # table (name) -> final line -> unresolved note ("note:" anchors the note,
        # since "unresolved" also appears in the missing token's table cell).
        self.assertLess(html.index("shot"), html.index("X_FINAL_X"))
        self.assertLess(html.index("X_FINAL_X"), html.index("note:"))


if __name__ == "__main__":
    unittest.main()
