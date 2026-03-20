# !/usr/bin/python
# coding=utf-8
"""Tests for TreeWidget column configuration (visibility, reorder, persistence)."""

import unittest
from unittest.mock import patch, MagicMock
from conftest import QtBaseTestCase
from qtpy import QtWidgets, QtCore

from uitk.widgets.treeWidget import TreeWidget
from uitk.widgets.mixins.settings_manager import SettingsManager


class TestTreeColumnConfig(QtBaseTestCase):
    """Verify column visibility menu, drag reorder, and settings persistence."""

    def _make_tree(self, headers=None, name="test_tree"):
        headers = headers or ["Name", "Type", "Value"]
        tree = TreeWidget()
        tree.setObjectName(name)
        tree.setHeaderLabels(headers)
        tree.add({"row1": "a", "row2": "b"}, headers=headers, clear=True)
        self.track_widget(tree)
        return tree

    # -- enable_column_config -------------------------------------------------

    def test_enable_sets_movable(self):
        """After enable_column_config, header sections should be movable."""
        tree = self._make_tree()
        tree.enable_column_config()
        self.assertTrue(tree.header().sectionsMovable())

    def test_enable_sets_header_context_menu_policy(self):
        """Header should use CustomContextMenu policy after enable."""
        tree = self._make_tree()
        tree.enable_column_config()
        self.assertEqual(
            tree.header().contextMenuPolicy(),
            QtCore.Qt.CustomContextMenu,
        )

    def test_enable_with_custom_settings(self):
        """enable_column_config should accept external SettingsManager."""
        tree = self._make_tree()
        sm = SettingsManager(org="test_org", app="test_app")
        tree.enable_column_config(settings=sm, settings_key="my_tree")
        self.assertIsNotNone(tree._column_settings)

    # -- visibility toggle ----------------------------------------------------

    def test_hide_column_via_header(self):
        """Hiding a column through the header should persist."""
        tree = self._make_tree()
        tree.enable_column_config()
        header = tree.header()

        # Manually hide column 1
        header.setSectionHidden(1, True)
        tree._save_column_state()

        hidden = tree._column_settings.value("hidden_columns", [])
        self.assertIn(1, hidden)
        self.assertNotIn(0, hidden)

    def test_restore_column_visibility(self):
        """restore_column_state should re-hide previously hidden columns."""
        tree = self._make_tree()
        tree.enable_column_config()
        header = tree.header()

        # Hide column 2, save, then un-hide (simulating a new session)
        header.setSectionHidden(2, True)
        tree._save_column_state()
        header.setSectionHidden(2, False)
        self.assertFalse(header.isSectionHidden(2))

        # Restore — column 2 should be hidden again
        tree.restore_column_state()
        self.assertTrue(header.isSectionHidden(2))

    # -- column reorder -------------------------------------------------------

    def test_restore_column_order(self):
        """restore_column_state should reorder columns to saved arrangement."""
        tree = self._make_tree()
        tree.enable_column_config()
        header = tree.header()

        # Save a custom order: logical columns [2, 0, 1]
        tree._column_settings.setValue("column_order", [2, 0, 1])

        tree.restore_column_state()

        # visual 0 → logical 2, visual 1 → logical 0, visual 2 → logical 1
        self.assertEqual(header.logicalIndex(0), 2)
        self.assertEqual(header.logicalIndex(1), 0)
        self.assertEqual(header.logicalIndex(2), 1)

    def test_save_preserves_order_after_move(self):
        """After a section move, _save_column_state should record the new order."""
        tree = self._make_tree()
        tree.enable_column_config()
        header = tree.header()

        # Move logical column 0 from visual 0 to visual 2
        header.moveSection(0, 2)
        tree._save_column_state()

        order = tree._column_settings.value("column_order", [])
        # After moving column 0 to end: visual order is [1, 2, 0]
        self.assertEqual(order, [1, 2, 0])

    # -- context menu content -------------------------------------------------

    def test_column_menu_has_all_columns(self):
        """_show_column_menu should create actions for every column."""
        tree = self._make_tree(["A", "B", "C"])
        tree.enable_column_config()

        actions = []
        original_exec = QtWidgets.QMenu.exec_

        def capture_menu(menu_self, _pos):
            nonlocal actions
            actions = menu_self.actions()
            return None  # simulate cancel

        with patch.object(QtWidgets.QMenu, "exec_", capture_menu):
            tree._show_column_menu(QtCore.QPoint(0, 0))

        self.assertEqual(len(actions), 3)
        self.assertEqual(actions[0].text(), "A")
        self.assertEqual(actions[1].text(), "B")
        self.assertEqual(actions[2].text(), "C")
        # All should be checked (visible) by default
        for a in actions:
            self.assertTrue(a.isChecked())

    def test_column_menu_prevents_hiding_last_column(self):
        """The last visible column's action should be disabled."""
        tree = self._make_tree(["Only", "Other"])
        tree.enable_column_config()
        header = tree.header()

        # Hide "Other" so only "Only" is visible
        header.setSectionHidden(1, True)

        actions = []

        def capture_menu(menu_self, _pos):
            nonlocal actions
            actions = menu_self.actions()
            return None

        with patch.object(QtWidgets.QMenu, "exec_", capture_menu):
            tree._show_column_menu(QtCore.QPoint(0, 0))

        # "Only" (col 0) should be checked but disabled
        self.assertTrue(actions[0].isChecked())
        self.assertFalse(actions[0].isEnabled())
        # "Other" (col 1) should be unchecked but enabled
        self.assertFalse(actions[1].isChecked())
        self.assertTrue(actions[1].isEnabled())

    # -- persistence isolation ------------------------------------------------

    def test_separate_trees_use_separate_keys(self):
        """Two trees with different names should not share column settings."""
        sm = SettingsManager(org="test_iso", app="test_iso_app")
        t1 = self._make_tree(name="tree_alpha")
        t2 = self._make_tree(name="tree_beta")
        t1.enable_column_config(settings=sm)
        t2.enable_column_config(settings=sm)

        t1.header().setSectionHidden(1, True)
        t1._save_column_state()

        # tree_beta should not have column 1 hidden
        t2.restore_column_state()
        self.assertFalse(t2.header().isSectionHidden(1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
