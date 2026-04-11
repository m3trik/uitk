# !/usr/bin/python
# coding=utf-8
"""Tests for TreeWidget selection behaviour (ctrl_toggle, Ctrl+click deselect)."""

import unittest
from conftest import QtBaseTestCase
from qtpy import QtWidgets, QtCore, QtGui

from uitk.widgets.treeWidget import TreeWidget


class TestTreeWidgetCtrlToggle(QtBaseTestCase):
    """Verify Ctrl+click toggle-deselect and the ctrl_toggle parameter."""

    def _make_tree(self, ctrl_toggle=True):
        tree = TreeWidget(ctrl_toggle=ctrl_toggle)
        tree.setHeaderLabels(["Name"])
        for name in ("Alpha", "Beta", "Gamma"):
            tree.create_item([name])
        tree.resize(200, 200)
        tree.show()
        self.app.processEvents()
        self.track_widget(tree)
        return tree

    def _item_rect_center(self, tree, item):
        rect = tree.visualItemRect(item)
        return tree.viewport().mapToGlobal(rect.center())

    def _item_viewport_center(self, tree, item):
        return tree.visualItemRect(item).center()

    # -- constructor / property -----------------------------------------------

    def test_ctrl_toggle_default_true(self):
        """ctrl_toggle should default to True."""
        tree = self._make_tree()
        self.assertTrue(tree.ctrl_toggle)

    def test_ctrl_toggle_init_false(self):
        """ctrl_toggle=False at construction should stick."""
        tree = self._make_tree(ctrl_toggle=False)
        self.assertFalse(tree.ctrl_toggle)

    def test_ctrl_toggle_property_setter(self):
        """ctrl_toggle property can be changed after construction."""
        tree = self._make_tree()
        tree.ctrl_toggle = False
        self.assertFalse(tree.ctrl_toggle)
        tree.ctrl_toggle = True
        self.assertTrue(tree.ctrl_toggle)

    # -- Ctrl+click deselect (ctrl_toggle=True) -------------------------------

    def test_ctrl_click_deselects_selected_item(self):
        """Ctrl+click on an already-selected item should deselect it when ctrl_toggle=True.

        Bug: Deselection was done in mousePressEvent but Qt's ExtendedSelection
        re-selected the item during mouseReleaseEvent, undoing the deselection.
        Fixed: 2026-04-10 — toggle logic moved to mouseReleaseEvent.
        """
        tree = self._make_tree(ctrl_toggle=True)
        item = tree.topLevelItem(0)
        pos = self._item_viewport_center(tree, item)

        # First: select the item with a plain click
        press = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(pos),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        release = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(pos),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        tree.viewport().mapFromParent(pos)
        tree.mousePressEvent(press)
        tree.mouseReleaseEvent(release)
        self.app.processEvents()
        self.assertTrue(item.isSelected(), "Item should be selected after plain click")

        # Second: Ctrl+click to deselect
        ctrl_press = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(pos),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.ControlModifier,
        )
        ctrl_release = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(pos),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.ControlModifier,
        )
        tree.mousePressEvent(ctrl_press)
        tree.mouseReleaseEvent(ctrl_release)
        self.app.processEvents()
        self.assertFalse(
            item.isSelected(),
            "Ctrl+click should deselect when ctrl_toggle=True",
        )

    # -- Ctrl+click keeps selection (ctrl_toggle=False) -----------------------

    def test_ctrl_click_keeps_selected_when_toggle_false(self):
        """Ctrl+click should NOT deselect when ctrl_toggle=False."""
        tree = self._make_tree(ctrl_toggle=False)
        item = tree.topLevelItem(0)
        pos = self._item_viewport_center(tree, item)

        # Select the item
        item.setSelected(True)
        self.app.processEvents()
        self.assertTrue(item.isSelected())

        # Ctrl+click — should stay selected
        ctrl_press = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(pos),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.ControlModifier,
        )
        ctrl_release = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(pos),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.ControlModifier,
        )
        tree.mousePressEvent(ctrl_press)
        tree.mouseReleaseEvent(ctrl_release)
        self.app.processEvents()
        self.assertTrue(
            item.isSelected(),
            "Ctrl+click should keep item selected when ctrl_toggle=False",
        )

    # -- Right-click clears stale state ---------------------------------------

    def test_right_click_clears_stale_press_state(self):
        """Right-click should clear _last_clicked_item to prevent stale release handling.

        Bug: Right-click early-return skipped resetting stored state, so a
        subsequent left-button release could act on stale values.
        Fixed: 2026-04-10
        """
        tree = self._make_tree()
        item = tree.topLevelItem(0)
        pos = self._item_viewport_center(tree, item)

        # Select the item first
        item.setSelected(True)
        self.app.processEvents()

        # Simulate a right-click press
        right_press = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(pos),
            QtCore.Qt.RightButton,
            QtCore.Qt.RightButton,
            QtCore.Qt.NoModifier,
        )
        tree.mousePressEvent(right_press)
        self.assertIsNone(
            tree._last_clicked_item,
            "_last_clicked_item should be None after right-click",
        )

    # -- Release consumes press state -----------------------------------------

    def test_release_consumes_press_state(self):
        """mouseReleaseEvent should consume _last_clicked_item (set to None)."""
        tree = self._make_tree()
        item = tree.topLevelItem(0)
        pos = self._item_viewport_center(tree, item)

        press = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(pos),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        release = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(pos),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        tree.mousePressEvent(press)
        self.assertIsNotNone(tree._last_clicked_item)
        tree.mouseReleaseEvent(release)
        self.assertIsNone(
            tree._last_clicked_item,
            "_last_clicked_item should be consumed after release",
        )

    # -- Ctrl+click adds unselected item to selection -------------------------

    def test_ctrl_click_selects_unselected_item(self):
        """Ctrl+click on an unselected item adds it to selection (standard Qt behaviour)."""
        tree = self._make_tree(ctrl_toggle=True)
        item0 = tree.topLevelItem(0)
        item1 = tree.topLevelItem(1)
        pos0 = self._item_viewport_center(tree, item0)
        pos1 = self._item_viewport_center(tree, item1)

        # Select first item
        item0.setSelected(True)
        self.app.processEvents()

        # Ctrl+click second item — should add to selection
        ctrl_press = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(pos1),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.ControlModifier,
        )
        ctrl_release = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(pos1),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.ControlModifier,
        )
        tree.mousePressEvent(ctrl_press)
        tree.mouseReleaseEvent(ctrl_release)
        self.app.processEvents()

        self.assertTrue(item0.isSelected(), "First item should remain selected")
        self.assertTrue(item1.isSelected(), "Second item should now be selected")


if __name__ == "__main__":
    unittest.main()
