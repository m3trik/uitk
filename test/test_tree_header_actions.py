# !/usr/bin/python
# coding=utf-8
"""Tests for TreeWidget header action bar."""

import unittest
from conftest import QtBaseTestCase
from qtpy import QtWidgets, QtCore

from uitk.widgets.treeWidget import TreeWidget, _HeaderActionBar


class TestHeaderActionBar(QtBaseTestCase):
    """Verify the _HeaderActionBar overlay on TreeWidget headers."""

    def _make_tree(self, headers=None):
        headers = headers or ["Name", "Type"]
        tree = TreeWidget()
        tree.setHeaderLabels(headers)
        tree.add({"row1": "a", "row2": "b"}, headers=headers, clear=True)
        tree.resize(400, 300)
        self.track_widget(tree)
        return tree

    # -- lazy creation -------------------------------------------------------

    def test_header_actions_not_created_until_accessed(self):
        """_header_actions should be None until the property is accessed."""
        tree = self._make_tree()
        self.assertIsNone(tree._header_actions)

    def test_header_actions_property_creates_bar(self):
        """Accessing header_actions should create a _HeaderActionBar."""
        tree = self._make_tree()
        bar = tree.header_actions
        self.assertIsInstance(bar, _HeaderActionBar)
        self.assertIs(tree._header_actions, bar)

    def test_header_actions_returns_same_instance(self):
        """Repeated access returns the same bar instance."""
        tree = self._make_tree()
        bar1 = tree.header_actions
        bar2 = tree.header_actions
        self.assertIs(bar1, bar2)

    # -- add / remove --------------------------------------------------------

    def test_add_creates_button(self):
        """add() should create a QToolButton and show the bar."""
        tree = self._make_tree()
        btn = tree.header_actions.add("lock", icon="lock", tooltip="Lock")
        self.assertIsInstance(btn, QtWidgets.QToolButton)
        self.assertEqual(btn.toolTip(), "Lock")

    def test_add_replaces_existing(self):
        """add() with the same name should replace the old button."""
        tree = self._make_tree()
        btn1 = tree.header_actions.add("lock", icon="lock", tooltip="v1")
        btn2 = tree.header_actions.add("lock", icon="lock", tooltip="v2")
        self.assertIsNot(btn1, btn2)
        self.assertEqual(tree.header_actions.get("lock"), btn2)

    def test_remove_deletes_button(self):
        """remove() should delete the button from the bar."""
        tree = self._make_tree()
        tree.header_actions.add("lock", icon="lock")
        tree.header_actions.remove("lock")
        self.assertIsNone(tree.header_actions.get("lock"))

    def test_remove_nonexistent_is_noop(self):
        """remove() on a missing name should not raise."""
        tree = self._make_tree()
        tree.header_actions.remove("does_not_exist")  # should not raise

    def test_clear_removes_all(self):
        """clear() should remove every button."""
        tree = self._make_tree()
        tree.header_actions.add("a", icon="lock")
        tree.header_actions.add("b", icon="lock")
        tree.header_actions.clear()
        self.assertIsNone(tree.header_actions.get("a"))
        self.assertIsNone(tree.header_actions.get("b"))

    def test_get_returns_button(self):
        """get() should return the button by name."""
        tree = self._make_tree()
        btn = tree.header_actions.add("lock", icon="lock")
        self.assertIs(tree.header_actions.get("lock"), btn)

    def test_get_returns_none_for_missing(self):
        """get() for an unknown name should return None."""
        tree = self._make_tree()
        self.assertIsNone(tree.header_actions.get("nope"))

    # -- toggle state --------------------------------------------------------

    def test_toggle_button(self):
        """A toggle=True button should be checkable."""
        tree = self._make_tree()
        btn = tree.header_actions.add("f", icon="filter", toggle=True)
        self.assertTrue(btn.isCheckable())

    def test_toggle_initial_checked(self):
        """checked=True should set button initially checked."""
        tree = self._make_tree()
        tree.header_actions.add("f", icon="filter", toggle=True, checked=True)
        self.assertTrue(tree.header_actions.is_checked("f"))

    def test_set_checked(self):
        """set_checked() should change button state."""
        tree = self._make_tree()
        tree.header_actions.add("f", icon="filter", toggle=True)
        tree.header_actions.set_checked("f", True)
        self.assertTrue(tree.header_actions.is_checked("f"))
        tree.header_actions.set_checked("f", False)
        self.assertFalse(tree.header_actions.is_checked("f"))

    def test_is_checked_non_toggle(self):
        """is_checked() on a non-toggle button should return False."""
        tree = self._make_tree()
        tree.header_actions.add("x", icon="lock")
        self.assertFalse(tree.header_actions.is_checked("x"))

    # -- callback dispatch ---------------------------------------------------

    def test_callback_fires(self):
        """Clicking a button should invoke its callback."""
        tree = self._make_tree()
        result = []
        tree.header_actions.add(
            "act", icon="lock", callback=lambda: result.append(True)
        )
        btn = tree.header_actions.get("act")
        btn.click()
        self.assertEqual(result, [True])

    def test_toggle_callback_receives_checked(self):
        """Toggle callback receives the checked state as bool arg."""
        tree = self._make_tree()
        states = []
        tree.header_actions.add(
            "t",
            icon="filter",
            toggle=True,
            callback=lambda checked: states.append(checked),
        )
        btn = tree.header_actions.get("t")
        btn.click()  # check
        btn.click()  # uncheck
        self.assertEqual(states, [True, False])

    # -- positioning ---------------------------------------------------------

    def test_reposition_on_resize(self):
        """Bar should reposition when tree is resized."""
        tree = self._make_tree()
        tree.header_actions.add("a", icon="lock")
        tree.resize(600, 400)
        # Bar should be within the header viewport bounds
        vp_width = tree.header().viewport().width()
        bar = tree.header_actions
        self.assertGreaterEqual(bar.x() + bar.width(), 0)
        self.assertLessEqual(bar.x() + bar.width(), vp_width + 10)


if __name__ == "__main__":
    unittest.main()
