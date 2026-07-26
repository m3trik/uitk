# !/usr/bin/python
# coding=utf-8
"""Tests for ``TableWidget`` action columns (``table_actions.TableActions``)."""

import unittest

from qtpy import QtWidgets
from conftest import setup_qt_application

from uitk.widgets.tableWidget import TableWidget
from uitk.widgets.delegates.centered_icon import ACTION_NONINTERACTIVE_ROLE

app = setup_qt_application()


class TestAddBeforeColumnsExist(unittest.TestCase):
    """``actions.add`` on a not-yet-populated table must be safe.

    Panels register their action columns at ``*_init`` time, often before
    ``setColumnCount`` / ``TableWidget.add`` has created the columns. Qt 6.5's
    ``QHeaderView.setSectionResizeMode`` on a nonexistent section is a native
    access violation (hard-crashed Maya 2025 at Reference Manager launch), so
    ``_apply_sizing`` must skip out-of-range columns and rely on ``_reapply``
    once the columns exist.
    """

    def setUp(self):
        self.table = TableWidget()

    def tearDown(self):
        self.table.deleteLater()

    def test_add_on_zero_column_table_does_not_touch_the_header(self):
        self.assertEqual(self.table.columnCount(), 0)
        # Would access-violate on Qt 6.5 without the out-of-range guard.
        self.table.actions.add(1, states={"on": {"icon": "link"}})
        self.assertIn(1, self.table.actions._columns)

    def test_reapply_sizes_the_column_once_it_exists(self):
        self.table.actions.add(1, states={"on": {"icon": "link"}})
        self.table.setColumnCount(3)
        self.table.actions._reapply()
        header = self.table.horizontalHeader()
        self.assertEqual(
            header.sectionResizeMode(1), QtWidgets.QHeaderView.ResizeMode.Fixed
        )

    def test_sizing_applies_immediately_when_columns_already_exist(self):
        self.table.setColumnCount(3)
        self.table.actions.add(2, states={"on": {"icon": "link"}})
        header = self.table.horizontalHeader()
        self.assertEqual(
            header.sectionResizeMode(2), QtWidgets.QHeaderView.ResizeMode.Fixed
        )


class TestNonInteractiveStateSuppressesHover(unittest.TestCase):
    """A state without an ``action`` callback must flag its cell non-interactive.

    Regression: the display-mode column's ``"unavailable"`` state (no action)
    still showed a mouse-hover brighten, reading as clickable even though the
    override isn't applicable to that row. ``set`` now marks such cells via
    ``ACTION_NONINTERACTIVE_ROLE`` so the icon delegate suppresses the hover cue.
    """

    def setUp(self):
        self.table = TableWidget()
        self.table.setColumnCount(2)
        self.table.setRowCount(1)
        self.table.actions.add(
            1,
            states={
                "active": {"icon": "grid", "action": lambda r, c: None},
                "unavailable": {"icon": "grid"},  # no action -> inert
            },
        )

    def tearDown(self):
        self.table.deleteLater()

    def test_actionless_state_flags_cell_noninteractive(self):
        self.table.actions.set(0, 1, "unavailable")
        item = self.table.item(0, 1)
        self.assertTrue(item.data(ACTION_NONINTERACTIVE_ROLE))

    def test_action_state_clears_the_flag(self):
        # Reusing a cell that was previously inert must restore interactivity.
        self.table.actions.set(0, 1, "unavailable")
        self.table.actions.set(0, 1, "active")
        item = self.table.item(0, 1)
        self.assertFalse(item.data(ACTION_NONINTERACTIVE_ROLE))


if __name__ == "__main__":
    unittest.main(verbosity=2)
