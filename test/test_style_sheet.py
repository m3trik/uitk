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
        bg_color = StyleSheet.get_variable("MAIN_BACKGROUND", theme="light")
        self.assertEqual(bg_color, "rgb(70,70,70)")

    def test_global_override(self):
        """Should respect global variable overrides."""
        # Set a global override
        StyleSheet.set_variable("BUTTON_HOVER", "#FF0000")

        # Verify it overrides the default
        val = StyleSheet.get_variable("BUTTON_HOVER", theme="light")
        self.assertEqual(val, "#FF0000")

        # Verify it applies to dark theme too (since it's a variable override)
        val_dark = StyleSheet.get_variable("BUTTON_HOVER", theme="dark")
        self.assertEqual(val_dark, "#FF0000")

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
        default_val = StyleSheet.get_variable("HIGHLIGHT_COLOR", theme="light")

        # 2. Global Override
        StyleSheet.set_variable("HIGHLIGHT_COLOR", "#111111")
        val = StyleSheet.get_variable("HIGHLIGHT_COLOR", theme="light", widget=widget)
        self.assertEqual(val, "#111111")

        # 3. Widget Override (should beat global)
        StyleSheet.set_variable("HIGHLIGHT_COLOR", "#222222", widget=widget)
        val = StyleSheet.get_variable("HIGHLIGHT_COLOR", theme="light", widget=widget)
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
