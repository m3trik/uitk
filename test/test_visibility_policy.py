# !/usr/bin/python
# coding=utf-8
"""Tests for the Phase-5 visibility policies (BLENDER_PORT_PLAN §3 Phase 5):

1. ``requires`` tag — a widget carrying a ``requires`` Designer property is hidden at
   registration when the switchboard's ``context_tags`` shares no tag with it.
2. Nav auto-hide — a ``MenuButton`` whose ``target`` doesn't resolve against the UI
   registry hides itself.
3. Missing-slot policy hook — ``connect_slot``'s no-slot branch invokes the switchboard's
   ``on_missing_slot`` hook (production default: None/no-op; ``mark_missing_slot`` greys).

All assertions are deterministic product state (``isHidden``/``isEnabled``/recorder lists) —
no OS-dependent visibility/focus outcomes (offscreen-QPA safe).

Run standalone: python -m test.test_visibility_policy
"""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets
from uitk.switchboard import Switchboard
from uitk.widgets.menuButton import MenuButton
from uitk.examples.example import ExampleSlots


class _PolicyTestBase(QtBaseTestCase):
    context_tags = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=ExampleSlots,
            context_tags=self.context_tags,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def register(self, widget, name):
        widget.setObjectName(name)
        self.ui.register_widget(widget)
        return widget


class TestRequiresTag(_PolicyTestBase):
    """`requires` Designer-property filtering against the switchboard's context_tags."""

    context_tags = {"maya"}

    def _button(self, name, requires):
        b = QtWidgets.QPushButton(self.ui)
        b.setProperty("requires", requires)
        return self.register(b, name)

    def test_unmatched_requires_hides(self):
        b = self._button("b900", "blender")
        self.assertTrue(b.isHidden())
        self.assertEqual(getattr(b, "hidden_by_policy", None), "requires")

    def test_matched_requires_stays_visible(self):
        b = self._button("b901", "maya")
        self.assertFalse(b.isHidden())

    def test_alternatives_match_any(self):
        b = self._button("b902", "maya|blender")
        self.assertFalse(b.isHidden())
        b2 = self._button("b903", "blender, max")
        self.assertTrue(b2.isHidden())

    def test_no_requires_property_untouched(self):
        b = QtWidgets.QPushButton(self.ui)
        self.register(b, "b904")
        self.assertFalse(b.isHidden())


class TestRequiresIgnoredWithoutContext(_PolicyTestBase):
    """Empty context_tags (standalone/dev) disables requires filtering entirely."""

    context_tags = None

    def test_requires_ignored(self):
        b = QtWidgets.QPushButton(self.ui)
        b.setProperty("requires", "maya")
        self.register(b, "b905")
        self.assertFalse(b.isHidden())


class TestNavAutoHide(_PolicyTestBase):
    """MenuButton auto-hide when its target doesn't resolve in the UI registry."""

    def test_unresolved_target_hides(self):
        b = MenuButton(self.ui, target="no_such_menu#submenu")
        self.register(b, "b906")
        self.assertTrue(b.isHidden())
        self.assertEqual(getattr(b, "hidden_by_policy", None), "nav-unresolved")

    def test_resolved_target_stays_visible(self):
        self.assertTrue(self.sb.is_registered_ui("example"))
        b = MenuButton(self.ui, target="example")
        self.register(b, "b907")
        self.assertFalse(b.isHidden())

    def test_empty_target_untouched(self):
        b = MenuButton(self.ui)  # may be wired at runtime — never auto-hidden
        self.register(b, "b908")
        self.assertFalse(b.isHidden())


class TestMissingSlotHook(_PolicyTestBase):
    """connect_slot's no-slot branch routes through the on_missing_slot policy hook."""

    def test_default_is_silent_noop(self):
        self.assertIsNone(self.sb.on_missing_slot)
        b = QtWidgets.QPushButton(self.ui)
        self.register(b, "b909")  # no slot in ExampleSlots
        self.assertTrue(b.isEnabled())

    def test_hook_invoked_for_unwired_widget(self):
        seen = []
        self.sb.on_missing_slot = seen.append
        b = QtWidgets.QPushButton(self.ui)
        self.register(b, "b910")
        self.assertIn(b, seen)

    def test_hook_skips_nav_menubutton(self):
        seen = []
        self.sb.on_missing_slot = seen.append
        b = MenuButton(self.ui, target="example")
        self.register(b, "b911")
        self.assertNotIn(b, seen)

    def test_mark_missing_slot_greys_widget(self):
        self.sb.on_missing_slot = self.sb.mark_missing_slot
        b = QtWidgets.QPushButton(self.ui)
        self.register(b, "b912")
        self.assertFalse(b.isEnabled())
        self.assertIn("b912", b.toolTip())


if __name__ == "__main__":
    unittest.main()
