# !/usr/bin/python
# coding=utf-8
"""MarkingMenu ↔ unified shortcut-editor register.

Covers the "hotkey register" integration: the marking menu surfaces its
activation key (visible, editable) and its chord→menu routes (hidden,
read-only) in the Switchboard command registry, and centralizes the
cross-cutting activation-key rewrite in :meth:`MarkingMenu.set_activation_key`.

Uses a lightweight ``MarkingMenu`` subclass that keeps the real binding /
register method bodies (and the real host-namespaced persistence via a real
Switchboard) but skips the QWidget / overlay / GlobalShortcut boot — so the
logic is exercised offscreen without a DCC host.

Run standalone: python -m test.test_marking_menu_shortcuts
"""
import logging

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtCore

from uitk.switchboard import Switchboard
from uitk.examples.example import ExampleSlots
from uitk.widgets.marking_menu._marking_menu import MarkingMenu


BINDINGS = {
    "Key_F12": "hud#startmenu",
    "Key_F12|LeftButton": "cameras#startmenu",
    "Key_F12|MiddleButton": "editors#startmenu",
    "Key_F12|RightButton": "main#startmenu",
    "Key_F12|LeftButton|RightButton": "maya#startmenu",
}


class _LiteMarkingMenu(MarkingMenu):
    """Real binding/register logic, no QWidget/overlay boot.

    With ``parent=None`` the activation ``GlobalShortcut`` install is skipped
    (binding/register logic only). Pass a real parent widget to exercise the
    activation-shortcut install + re-install (see TestActivationShortcut).
    """

    def __init__(self, sb, bindings, parent=None):
        self.logger = logging.getLogger("lite_marking_menu")
        self.sb = sb
        self._bindings = {}
        self._activation_key = None
        self._activation_key_str = None
        self._initial_bindings = bindings
        self._default_bindings = bindings
        self._activation_parent = parent  # real GlobalShortcut host when provided
        self._shortcut_instance = None
        self.key_show = None
        # Seed the (host-namespaced) store, then build: parses the activation key
        # and registers the editor bindings (mirrors MarkingMenu.__init__).
        self._bindings_store.set(dict(bindings))
        self._bindings_store.changed.connect(self._build_bindings)
        self._build_bindings()
        if parent is not None:
            self._install_activation_shortcut()


class _MarkingMenuRegisterFixture(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        from uitk import examples

        self.sb = Switchboard(ui_source=examples, slot_source=ExampleSlots)
        self.sb._command_settings().clear()
        self.mm = _LiteMarkingMenu(self.sb, BINDINGS)

    def _reg(self):
        return {e["method"]: e for e in self.sb.get_command_registry()}


class TestRegisterEntries(_MarkingMenuRegisterFixture):
    def test_activation_entry_visible_editable_with_live_value(self):
        entry = self._reg()["marking_menu_show"]
        self.assertFalse(entry["hidden"])
        self.assertTrue(entry["editable"])
        self.assertEqual(entry["current"], "F12")  # from value_getter

    def test_route_entries_hidden_readonly_with_target_doc(self):
        reg = self._reg()
        for gesture in ("left", "middle", "right", "left_right"):
            entry = reg[f"marking_menu_route_{gesture}"]
            self.assertTrue(entry["hidden"], gesture)
            self.assertFalse(entry["editable"], gesture)
        # The target menu is surfaced (tag-stripped) in the description.
        self.assertIn("cameras", reg["marking_menu_route_left"]["doc"])
        self.assertIn("maya", reg["marking_menu_route_left_right"]["doc"])

    def test_route_value_is_the_chord_trigger(self):
        # A route's Shortcut column shows the (read-only) gesture, not the menu.
        self.assertEqual(self._reg()["marking_menu_route_left"]["current"], "F12 + Left")
        self.assertEqual(
            self._reg()["marking_menu_route_left_right"]["current"], "F12 + Left + Right"
        )

    def test_no_default_route_entry(self):
        # The key-only default menu is not a mouse chord — the activation entry
        # already represents the F12 trigger; no redundant route row.
        self.assertNotIn("marking_menu_route_default", self._reg())


class TestActivationKey(_MarkingMenuRegisterFixture):
    def test_set_activation_key_rewrites_all_chords_preserving_targets(self):
        self.mm.set_activation_key("F11")
        keys = set(self.mm.bindings)
        self.assertTrue(all("Key_F11" in k for k in keys))
        self.assertFalse(any("Key_F12" in k for k in keys))
        self.assertEqual(self.mm._activation_key_str, "Key_F11")
        # Targets are untouched.
        self.assertEqual(self.mm.bindings["Key_F11|LeftButton"], "cameras#startmenu")
        self.assertEqual(self._reg()["marking_menu_show"]["current"], "F11")

    def test_set_activation_key_noop_on_invalid(self):
        before = dict(self.mm.bindings)
        self.mm.set_activation_key("NotARealKey")
        self.assertEqual(self.mm.bindings, before)
        self.assertEqual(self.mm._activation_key_str, "Key_F12")

    def test_set_activation_key_accepts_prefixed_and_bare(self):
        self.mm.set_activation_key("Key_F11")  # prefixed form also accepted
        self.assertEqual(self.mm._activation_key_str, "Key_F11")

    def test_editing_activation_entry_calls_set_activation_key(self):
        # The editor edits marking_menu_show via set_command_shortcut → on_rebind.
        self.sb.set_command_shortcut("marking_menu_show", "F11", "application")
        self.assertEqual(self.mm._activation_key_str, "Key_F11")
        self.assertIn("Key_F11|RightButton", self.mm.bindings)


class TestActivationShortcut(_MarkingMenuRegisterFixture):
    """The activation GlobalShortcut installs and *re-installs* on the new key.

    Regression: set_activation_key must move the live shortcut, not just the
    persisted bindings — a stale ``key_show`` left the shortcut on F12 after the
    user picked F11 (caught only with a real parent, so the install actually
    runs; the no-parent fixtures skip it)."""

    def _mm_with_host(self):
        parent = QtWidgets.QWidget()
        self.track_widget(parent)
        return _LiteMarkingMenu(self.sb, BINDINGS, parent=parent)

    def test_installs_on_activation_key(self):
        mm = self._mm_with_host()
        self.assertIsNotNone(mm._shortcut_instance)
        self.assertEqual(int(mm.key_show), int(QtCore.Qt.Key_F12))

    def test_reinstalls_on_new_key(self):
        mm = self._mm_with_host()
        first = mm._shortcut_instance
        mm.set_activation_key("F11")
        self.assertEqual(int(mm.key_show), int(QtCore.Qt.Key_F11))
        self.assertIsNot(mm._shortcut_instance, first)  # a fresh shortcut on F11


class TestRouteApi(_MarkingMenuRegisterFixture):
    def test_get_route_target(self):
        self.assertEqual(self.mm.get_route_target(("LeftButton",)), "cameras#startmenu")
        self.assertEqual(self.mm.get_route_target(()), "hud#startmenu")

    def test_set_route_target(self):
        self.mm.set_route_target(("MiddleButton",), "main#startmenu")
        self.assertEqual(self.mm.get_route_target(("MiddleButton",)), "main#startmenu")

    def test_route_lookup_is_key_agnostic_after_activation_change(self):
        self.mm.set_activation_key("F11")
        # The gesture still resolves — lookup is by button combo, not a fixed key.
        self.assertEqual(self.mm.get_route_target(("LeftButton",)), "cameras#startmenu")
        self.mm.set_route_target(("RightButton",), "editors#startmenu")
        self.assertEqual(self.mm.bindings["Key_F11|RightButton"], "editors#startmenu")


if __name__ == "__main__":
    import unittest

    unittest.main()
