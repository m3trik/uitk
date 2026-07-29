# !/usr/bin/python
# coding=utf-8
"""Unit tests for the tooltip mixin helpers (fmt / kbd / hl) and the bind surface.

The formatting helpers are pure HTML builders — no Qt widgets needed — so most of
this file stays fast. Only the ``bind`` tests, which install a real event filter,
need a QApplication.
"""

import unittest

from qtpy import QtWidgets

from conftest import setup_qt_application
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


class TestReachability(unittest.TestCase):
    """The DSL must be reachable without importing uitk internals — consumers
    (tentacle slots, DCC panels) build tooltips off the objects they already
    hold: a registered widget, or the Switchboard."""

    def test_proxy_carries_the_format_dsl(self):
        from uitk.widgets.mixins.tooltip_mixin import TooltipProxy

        # widget.tooltip.fmt(...) alongside widget.tooltip.bind(...)
        self.assertTrue(issubclass(TooltipProxy, TooltipFormat))
        for name in ("fmt", "kbd", "hl", "placeholder_preview", "bind"):
            self.assertTrue(hasattr(TooltipProxy, name), name)

    def test_switchboard_namespace_is_the_superset(self):
        """sb owns the surface; the per-widget proxy is the convenience form.

        The switchboard namespace must carry everything the widget proxy does
        (so `sb.tooltip.<x>` never surprises), plus the batch `bind` only it can
        serve — resolving a "chk000-2" range needs the switchboard's resolver.
        """
        from uitk.switchboard import Switchboard
        from uitk.widgets.mixins.tooltip_mixin import TooltipNamespace, TooltipProxy

        self.assertTrue(issubclass(TooltipNamespace, TooltipFormat))
        proxy_surface = {n for n in dir(TooltipProxy) if not n.startswith("_")}
        ns_surface = {n for n in dir(TooltipNamespace) if not n.startswith("_")}
        self.assertTrue(
            proxy_surface <= ns_surface,
            f"widget.tooltip exposes what sb.tooltip lacks: {proxy_surface - ns_surface}",
        )
        sb = Switchboard()
        self.assertIsInstance(sb.tooltip, TooltipNamespace)
        self.assertIn("<b>Title</b>", sb.tooltip.fmt(title="Title"))


class TestModuleInvariant(unittest.TestCase):
    """The module states it carries no top-level function definitions (helpers live
    on classes, per the package standard). Pin it — it was broken once already."""

    def test_no_top_level_functions(self):
        import ast
        import inspect

        from uitk.widgets.mixins import tooltip_mixin

        tree = ast.parse(inspect.getsource(tooltip_mixin))
        offenders = [
            n.name
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(offenders, [], f"module-level def(s): {offenders}")


class TestBind(unittest.TestCase):
    """`bind` installs a lazy provider; both entry points share one installer."""

    @classmethod
    def setUpClass(cls):
        cls.app = setup_qt_application()

    def _widget(self):
        from uitk.widgets.mixins.tooltip_mixin import TooltipProxy

        w = QtWidgets.QWidget()
        w.tooltip = TooltipProxy(w)
        return w

    @staticmethod
    def _filter_of(widget):
        from uitk.widgets.mixins.tooltip_mixin import TooltipProxy

        return widget.property(TooltipProxy._FILTER_PROP)

    @staticmethod
    def _hover(widget):
        """Deliver a real QEvent.ToolTip so the installed provider(s) actually run."""
        from qtpy import QtCore, QtGui

        pos = QtCore.QPoint(0, 0)
        QtWidgets.QApplication.sendEvent(
            widget, QtGui.QHelpEvent(QtCore.QEvent.ToolTip, pos, pos)
        )

    def test_widget_bind_installs_a_provider(self):
        w = self._widget()
        w.tooltip.bind(lambda: "live")
        self.assertIsNotNone(self._filter_of(w))
        self._hover(w)
        self.assertEqual(w.toolTip(), "live")

    def test_provider_is_re_evaluated_on_every_hover(self):
        w = self._widget()
        state = {"n": 0}

        def provider():
            state["n"] += 1
            return f"call {state['n']}"

        w.tooltip.bind(provider)
        self._hover(w)
        self.assertEqual(w.toolTip(), "call 1")
        self._hover(w)
        self.assertEqual(w.toolTip(), "call 2")

    def test_rebinding_replaces_rather_than_stacks(self):
        """Regression: the filter is tracked on the WIDGET, so binding twice — by
        either route — swaps the provider instead of layering event filters.

        Asserted through behavior, not identity: Qt runs event filters
        newest-first, so a *stacked* older provider would run LAST and win,
        leaving the stale "first" text. Seeing "second" proves replacement.
        """
        from uitk.switchboard import Switchboard

        w = self._widget()
        w.tooltip.bind(lambda: "first")
        first = self._filter_of(w)
        Switchboard().tooltip.bind(w, lambda: "second")
        self.assertIsNot(first, self._filter_of(w))
        self._hover(w)
        self.assertEqual(w.toolTip(), "second")

    def test_switchboard_bind_accepts_one_widget_or_many(self):
        from uitk.switchboard import Switchboard

        sb = Switchboard()
        a, b = self._widget(), self._widget()
        self.assertEqual(sb.tooltip.bind(a, lambda: "x"), [a])
        self.assertEqual(sb.tooltip.bind([a, b], lambda: "x"), [a, b])
        self.assertIsNotNone(self._filter_of(b))

    def test_unresolvable_name_pattern_says_what_to_do(self):
        """A range needs a UI to resolve against; the failure must name the fix
        rather than surface the resolver's bare 'expected QWidget, got NoneType'."""
        from uitk.switchboard import Switchboard

        sb = Switchboard()  # no ui_source, so current_ui resolves to None
        self.assertIsNone(sb.current_ui)
        with self.assertRaises(ValueError) as ctx:
            sb.tooltip.bind("chk000-2", lambda: "x")
        self.assertIn("ui=", str(ctx.exception))

    def test_bind_tolerates_a_dead_widget(self):
        from uitk.widgets.mixins.tooltip_mixin import TooltipProxy

        w = QtWidgets.QWidget()
        proxy = TooltipProxy(w)
        del w
        proxy.bind(lambda: "x")  # must not raise


if __name__ == "__main__":
    unittest.main()
