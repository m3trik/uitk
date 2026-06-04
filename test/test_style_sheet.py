# !/usr/bin/python
# coding=utf-8
import unittest
from unittest.mock import MagicMock
from qtpy import QtWidgets, QtGui, QtCore
from conftest import QtBaseTestCase, setup_qt_application
from uitk.widgets.mixins.style_sheet import StyleSheet

# Ensure QApplication exists
app = setup_qt_application()


class TestStyleSheetOverrides(QtBaseTestCase):
    """Tests for StyleSheet variable overrides and theme management."""

    def test_get_defaults(self):
        """Should retrieve default theme variables."""
        # Check a known variable from the 'light' theme
        bg_color = StyleSheet.get_variable("PANEL_BACKGROUND", theme="light")
        self.assertEqual(bg_color, "rgb(70,70,70)")

    def test_global_override(self):
        """Should respect theme-specific variable overrides."""
        # Set a global override (defaults to theme='light')
        StyleSheet.set_variable("BUTTON_HOVER", "#FF0000")

        # Verify it overrides the default for light theme
        val = StyleSheet.get_variable("BUTTON_HOVER", theme="light")
        self.assertEqual(val, "#FF0000")

        # Verify it DOES NOT apply to dark theme (overrides are now theme-specific)
        val_dark = StyleSheet.get_variable("BUTTON_HOVER", theme="dark")
        self.assertNotEqual(val_dark, "#FF0000")

        # Set specific override for dark theme
        StyleSheet.set_variable("BUTTON_HOVER", "#0000FF", theme="dark")
        val_dark_new = StyleSheet.get_variable("BUTTON_HOVER", theme="dark")
        self.assertEqual(val_dark_new, "#0000FF")

        # Clean up
        StyleSheet.reset_overrides()

    def test_widget_override(self):
        """Should respect widget-specific overrides."""
        widget = self.track_widget(QtWidgets.QWidget())

        # Set override for this widget only
        StyleSheet.set_variable("TEXT_COLOR", "#00FF00", widget=widget)

        # Verify widget sees the override
        val = StyleSheet.get_variable("TEXT_COLOR", theme="light", widget=widget)
        self.assertEqual(val, "#00FF00")

        # Verify global context still sees default
        global_val = StyleSheet.get_variable("TEXT_COLOR", theme="light")
        self.assertNotEqual(global_val, "#00FF00")

        # Clean up
        StyleSheet.reset_overrides()

    def test_override_resolution_order(self):
        """Should resolve overrides in correct order: Widget > Global > Theme."""
        widget = self.track_widget(QtWidgets.QWidget())

        # 1. Base Theme
        default_val = StyleSheet.get_variable("SELECTION_FG", theme="light")

        # 2. Global Override
        StyleSheet.set_variable("SELECTION_FG", "#111111")
        val = StyleSheet.get_variable("SELECTION_FG", theme="light", widget=widget)
        self.assertEqual(val, "#111111")

        # 3. Widget Override (should beat global)
        StyleSheet.set_variable("SELECTION_FG", "#222222", widget=widget)
        val = StyleSheet.get_variable("SELECTION_FG", theme="light", widget=widget)
        self.assertEqual(val, "#222222")

        # Clean up
        StyleSheet.reset_overrides()

    def test_color_object_handling(self):
        """Should handle QColor objects passed to set_variable."""
        color = QtGui.QColor(255, 0, 0)  # Red
        StyleSheet.set_variable("TEST_COLOR", color)

        val = StyleSheet.get_variable("TEST_COLOR")
        self.assertEqual(val, "#ff0000")

        StyleSheet.reset_overrides()

    def test_get_variable_px(self):
        """``get_variable_px`` parses a length token to int, honoring
        overrides and the ``default`` for missing/non-numeric values."""
        # Real px token from the theme.
        self.assertEqual(
            StyleSheet.get_variable_px("COMBOBOX_ITEM_HEIGHT", theme="light"), 19
        )
        # Missing token → default (None unless given).
        self.assertIsNone(StyleSheet.get_variable_px("NOPE_DOES_NOT_EXIST"))
        self.assertEqual(
            StyleSheet.get_variable_px("NOPE_DOES_NOT_EXIST", default=7), 7
        )
        # Non-numeric (a colour) → default.
        self.assertEqual(
            StyleSheet.get_variable_px("PANEL_BACKGROUND", theme="light", default=0), 0
        )
        # Override is resolved and parsed.
        StyleSheet.set_variable("COMBOBOX_ITEM_HEIGHT", "23px", theme="light")
        self.assertEqual(
            StyleSheet.get_variable_px("COMBOBOX_ITEM_HEIGHT", theme="light"), 23
        )
        StyleSheet.reset_overrides()

    def test_reset_overrides(self):
        """Should clear overrides correctly."""
        widget = self.track_widget(QtWidgets.QWidget())

        StyleSheet.set_variable("VAR1", "A")  # Global
        StyleSheet.set_variable("VAR2", "B", widget=widget)  # Widget

        # Reset widget only
        StyleSheet.reset_overrides(widget=widget)
        self.assertEqual(StyleSheet.get_variable("VAR2", widget=widget), "")  # Cleared
        self.assertEqual(StyleSheet.get_variable("VAR1"), "A")  # Global persists

        # Reset all
        StyleSheet.reset_overrides()
        self.assertEqual(StyleSheet.get_variable("VAR1"), "")  # Cleared


class TestStyleSheetTemplateEngine(QtBaseTestCase):
    """Tests for the parsed-template substitution engine."""

    def test_template_caches_by_resource(self):
        """``_get_template`` populates ``_template_cache`` once per resource."""
        StyleSheet._template_cache.clear()
        parts_a = StyleSheet._get_template()
        parts_b = StyleSheet._get_template()
        # Same list object — cache hit, not rebuilt
        self.assertIs(parts_a, parts_b)
        self.assertEqual(len(StyleSheet._template_cache), 1)

    def test_template_alternates_literals_and_tokens(self):
        """Even indices are literals, odd indices are UPPER_SNAKE token names."""
        parts = StyleSheet._token_pat.split("foo {BAR} baz {QUX_2} end")
        self.assertEqual(parts, ["foo ", "BAR", " baz ", "QUX_2", " end"])

    def test_apply_template_leaves_unknown_token_as_literal(self):
        """Missing tokens render as ``{TOKEN}`` so the gap is visible."""
        parts = ["pre ", "MISSING", " post"]
        out = StyleSheet._apply_template(parts, {})
        self.assertEqual(out, "pre {MISSING} post")

    def test_apply_template_substitutes_known_tokens(self):
        parts = ["color: ", "BG", "; border: ", "BORDER_W", " solid;"]
        out = StyleSheet._apply_template(parts, {"BG": "red", "BORDER_W": "1px"})
        self.assertEqual(out, "color: red; border: 1px solid;")

    def test_slider_handle_radius_is_literal_not_token(self):
        """Slider handle keeps a literal radius (it's width:10px — {RADIUS} > 5 distorts it)."""
        import re

        parts = StyleSheet._get_template()
        qss_high_radius = StyleSheet._apply_template(
            parts, {**StyleSheet.themes["light"], "RADIUS": "10px"}
        )
        m = re.search(
            r"QAbstractSlider::handle\s*\{[^}]*?border-radius:\s*([^;]+);",
            qss_high_radius,
        )
        self.assertIsNotNone(m, "slider handle rule must exist")
        self.assertNotIn(
            "10px",
            m.group(1),
            "slider handle picked up the {RADIUS} override — it should be a literal",
        )

    def test_text_inset_is_uniform_across_form_widgets(self):
        """Labels, comboboxes, line edits and spin boxes share the single
        ``{TEXT_INSET}`` horizontal padding so their text aligns in a layout.
        A distinctive override proves each base rule reads the token rather
        than a coincidental literal."""
        import re

        parts = StyleSheet._get_template()
        qss = StyleSheet._apply_template(
            parts, {**StyleSheet.themes["light"], "TEXT_INSET": "7px"}
        )
        for selector in ("QLabel", "QComboBox", "QLineEdit", "QAbstractSpinBox"):
            # ``selector\s*\{`` matches only the bare base rule, not the
            # ``:hover`` / ``::drop-down`` / descendant variants.
            m = re.search(rf"(?:^|\n){re.escape(selector)}\s*\{{([^}}]*)\}}", qss)
            self.assertIsNotNone(m, f"{selector} base rule must exist")
            pad = re.search(r"padding:\s*([^;]+);", m.group(1))
            self.assertIsNotNone(pad, f"{selector} must declare padding")
            self.assertIn(
                "7px",
                pad.group(1),
                f"{selector} padding must use {{TEXT_INSET}} (got {pad.group(1)!r})",
            )

    def test_qss_has_no_unresolved_tokens(self):
        """Every ``{TOKEN}`` in style.qss resolves against the themes dict
        (plus any internally-derived tokens injected at assembly time)."""
        import re

        parts = StyleSheet._get_template()
        used = {p for i, p in enumerate(parts) if i % 2 == 1}
        derived = {f"{name}_TINT" for name in StyleSheet._tint_sources}
        for theme_name in StyleSheet.themes:
            known = set(StyleSheet.themes[theme_name].keys()) | derived
            missing = used - known
            self.assertFalse(
                missing,
                f"theme '{theme_name}' is missing tokens used in style.qss: {sorted(missing)}",
            )

    def test_reload_assembles_qss_once_per_config_group(self):
        """``reload()`` should call ``_apply_template`` once per unique config,
        not once per widget. Verifies the grouping optimization."""
        # Register 5 widgets sharing the same config
        widgets = [self.track_widget(QtWidgets.QWidget()) for _ in range(5)]
        styler = StyleSheet()
        for w in widgets:
            styler.set(w, theme="light")

        # Wrap _apply_template to count invocations. Save the descriptor
        # itself (not the resolved attribute) so the restore puts the
        # staticmethod wrapper back, not a plain function that would bind
        # ``self`` on later calls and break subsequent tests.
        original_desc = StyleSheet.__dict__["_apply_template"]
        original = StyleSheet._apply_template
        call_count = [0]

        def counting(parts, vars):
            call_count[0] += 1
            return original(parts, vars)

        # Isolate the registry to just our 5 widgets — other tests in the
        # full suite leave widgets registered, which would split into
        # multiple config groups and break this assertion.
        saved_configs = StyleSheet._widget_configs
        StyleSheet._widget_configs = {w: saved_configs[w] for w in widgets}
        StyleSheet._apply_template = staticmethod(counting)
        try:
            StyleSheet.reload()
            self.assertEqual(
                call_count[0],
                1,
                "5 widgets sharing a config should trigger 1 template-apply, not 5",
            )
        finally:
            StyleSheet._apply_template = original_desc
            StyleSheet._widget_configs = saved_configs


class TestStyleSheetSignals(QtBaseTestCase):
    """Tests for StyleSheet signals."""

    def test_theme_changed_signal(self):
        """Should emit theme_changed signal with resolved variables."""
        widget = self.track_widget(QtWidgets.QWidget())
        styler = StyleSheet()

        # Set an override to verify it comes through in the signal
        StyleSheet.set_variable("BUTTON_HOVER", "#123456", widget=widget)

        # Mock slot
        mock_slot = MagicMock()
        styler.theme_changed.connect(mock_slot)

        # Apply style
        styler.set(widget, theme="light")

        # Verify signal emission
        self.assertTrue(mock_slot.called)
        args = mock_slot.call_args[0]
        emitted_widget, emitted_theme, emitted_vars = args

        self.assertEqual(emitted_widget, widget)
        self.assertEqual(emitted_theme, "light")
        self.assertEqual(emitted_vars.get("BUTTON_HOVER"), "#123456")


if __name__ == "__main__":
    unittest.main()
