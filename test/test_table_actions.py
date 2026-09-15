# !/usr/bin/python
# coding=utf-8
"""Tests for ``TableWidget`` action columns (``table_actions.TableActions``)."""

import unittest

from qtpy import QtCore, QtWidgets
from qtpy.QtTest import QTest
from conftest import QtBaseTestCase, setup_qt_application

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


class TestAltPressReachesTheAction(QtBaseTestCase):
    """An Alt press or Alt-drag on an action column fires the action like a plain one.

    Panels read Alt as "clear" (the Channels Lock / Key columns: a press sets,
    Alt+press clears, a drag applies either to every row it crosses), reading
    the modifier from ``QApplication.keyboardModifiers()`` inside the action.
    So Alt must stay out of the modifiers that turn a drag into a selection
    gesture -- a Shift / Ctrl drag fires nothing.
    """

    ROWS = 4

    def setUp(self):
        super().setUp()
        self.hits = []
        table = self.track_widget(TableWidget())
        table.setColumnCount(2)
        table.setRowCount(self.ROWS)
        table.actions.add(1, states=self._states())
        for row in range(self.ROWS):
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(f"row{row}"))
            table.actions.set(row, 1, "on")
        table.resize(300, 260)
        table.show()
        app.processEvents()
        self.table = table

    def _states(self):
        return {
            "on": {"icon": "lock", "action": self._record},
            "off": {"icon": "unlock"},  # no action -> inert
        }

    def _record(self, row, _col):
        alt = QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.AltModifier
        self.hits.append((row, bool(alt)))

    def _center(self, row):
        return self.table.visualRect(self.table.model().index(row, 1)).center()

    def _drag(self, rows, modifier):
        viewport = self.table.viewport()
        QTest.mousePress(
            viewport, QtCore.Qt.LeftButton, modifier, self._center(rows[0])
        )
        for row in rows[1:]:
            QTest.mouseMove(viewport, self._center(row))
        QTest.mouseRelease(
            viewport, QtCore.Qt.LeftButton, modifier, self._center(rows[-1])
        )
        app.processEvents()

    def test_alt_click_fires_the_action_with_alt_held(self):
        QTest.mouseClick(
            self.table.viewport(),
            QtCore.Qt.LeftButton,
            QtCore.Qt.AltModifier,
            self._center(1),
        )
        app.processEvents()
        self.assertEqual(self.hits, [(1, True)])

    def test_alt_drag_fires_every_crossed_row_with_alt_held(self):
        self._drag([0, 1, 2], QtCore.Qt.AltModifier)
        self.assertEqual(self.hits, [(0, True), (1, True), (2, True)])

    def test_plain_drag_fires_every_crossed_row(self):
        self._drag([0, 1, 2], QtCore.Qt.NoModifier)
        self.assertEqual(self.hits, [(0, False), (1, False), (2, False)])

    def test_ctrl_drag_fires_nothing(self):
        self._drag([0, 1, 2], QtCore.Qt.ControlModifier)
        self.assertEqual(self.hits, [])

    def _add_drag_action(self):
        batches = []
        self.table.actions.add(
            1,
            states=self._states(),
            drag_action=lambda rows, col: batches.append(rows),
        )
        return batches

    def test_a_drag_action_gets_every_crossed_row_in_one_call(self):
        batches = self._add_drag_action()
        self._drag([0, 1, 2], QtCore.Qt.AltModifier)
        self.assertEqual(batches, [[0, 1, 2]])
        self.assertEqual(self.hits, [], "the per-row actions must not fire too")

    def test_a_drag_action_leaves_out_rows_without_an_action(self):
        batches = self._add_drag_action()
        self.table.actions.set(1, 1, "off")
        self._drag([0, 1, 2], QtCore.Qt.NoModifier)
        self.assertEqual(batches, [[0, 2]])

    def test_a_click_still_fires_the_state_action(self):
        batches = self._add_drag_action()
        QTest.mouseClick(
            self.table.viewport(),
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
            self._center(2),
        )
        app.processEvents()
        self.assertEqual((self.hits, batches), ([(2, False)], []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
