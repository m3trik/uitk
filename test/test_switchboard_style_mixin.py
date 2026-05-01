# !/usr/bin/python
# coding=utf-8
"""Tests for ``SwitchboardStyleMixin`` and lazy ``EditorPanel.style``.

Covers:
- ``sb.style`` returns the StyleSheet class
- ``sb.style.set_theme(...)`` works (classmethod proxy)
- EditorPanel.style is lazy-instantiated on first access
- EditorPanel applies the default dark theme on first show
- An explicit ``set(theme="light")`` before show is preserved
"""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets
from uitk.switchboard import Switchboard
from uitk.widgets.editors.editor_panel import EditorPanel
from uitk.widgets.mixins.style_sheet import StyleSheet


class SwitchboardStyleProperty(QtBaseTestCase):
    def test_style_returns_stylesheet_class(self):
        sb = Switchboard(log_level="WARNING")
        # Property must return the class (not an instance) — callers use
        # the classmethod surface (set_theme, reload, set_variable, ...)
        self.assertIs(sb.style, StyleSheet)

    def test_classmethod_callable_via_proxy(self):
        sb = Switchboard(log_level="WARNING")
        # set_theme is a classmethod; should be reachable through the
        # property without throwing.
        sb.style.set_theme("dark")  # smoke test, no widgets registered

    def test_get_variable_via_proxy(self):
        sb = Switchboard(log_level="WARNING")
        # A known dark-theme variable should resolve through the proxy
        value = sb.style.get_variable("ICON_COLOR", theme="dark")
        self.assertTrue(value)  # non-empty string


class EditorPanelStyleLazy(QtBaseTestCase):
    def test_style_not_created_in_init(self):
        panel = EditorPanel(title="lazy test")
        try:
            # Until the property is accessed, no instance exists in the dict.
            self.assertNotIn("_style", panel.__dict__)
        finally:
            panel.deleteLater()

    def test_style_property_returns_stylesheet_instance(self):
        panel = EditorPanel(title="lazy test")
        try:
            style = panel.style
            self.assertIsInstance(style, StyleSheet)
            self.assertIs(panel.style, style)  # cached on second access
        finally:
            panel.deleteLater()

    def test_style_property_rebuilds_after_explicit_none(self):
        # Defensive: if anything (subclass cleanup, test mock) sets
        # ``_style = None``, the property must recover by building a
        # fresh instance rather than handing the caller a None.
        panel = EditorPanel(title="reset test")
        try:
            first = panel.style
            self.assertIsNotNone(first)
            panel._style = None  # simulate accidental reset
            second = panel.style
            self.assertIsInstance(second, StyleSheet)
            self.assertIsNotNone(second)
        finally:
            panel.deleteLater()

    def test_dark_theme_applied_on_first_show(self):
        panel = EditorPanel(title="dark test")
        try:
            # Before show: no default theme applied (the panel may not
            # even have a style instance yet).
            self.assertFalse(getattr(panel, "_default_theme_applied", False))
            panel.show()
            QtWidgets.QApplication.processEvents()
            self.assertTrue(panel._default_theme_applied)
            # The default-theme path went through the StyleSheet, so the
            # panel must be in the configs registry now.
            self.assertIn(panel, StyleSheet._widget_configs)
            self.assertEqual(StyleSheet._widget_configs[panel]["theme"], "dark")
        finally:
            panel.hide()
            panel.deleteLater()

    def test_explicit_theme_before_show_is_preserved(self):
        panel = EditorPanel(title="explicit theme test")
        try:
            # Set light theme explicitly before showing
            panel.style.set(theme="light")
            self.assertEqual(StyleSheet._widget_configs[panel]["theme"], "light")
            # showEvent's default-theme block must NOT clobber this
            panel.show()
            QtWidgets.QApplication.processEvents()
            self.assertEqual(StyleSheet._widget_configs[panel]["theme"], "light")
        finally:
            panel.hide()
            panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
