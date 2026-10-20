# !/usr/bin/python
# coding=utf-8
"""Tests for uitk.widgets.delegates.value_bar: a cell's number drawn as a bar."""

import math
import unittest

from qtpy import QtCore, QtGui, QtWidgets

from conftest import QtBaseTestCase, QtWait, setup_qt_application
from uitk.widgets.delegates.value_bar import ValueBarDelegate

app = setup_qt_application()

GHOST = QtCore.Qt.UserRole + 7
FILL = "#20c020"


class TestValueBarDelegate(QtBaseTestCase):
    def table(self, value, **delegate):
        table = self.track_widget(QtWidgets.QTableWidget(1, 1))
        table.horizontalHeader().setVisible(False)
        table.verticalHeader().setVisible(False)
        table.setColumnWidth(0, 200)
        table.setRowHeight(0, 24)
        table.resize(220, 40)
        item = QtWidgets.QTableWidgetItem()
        item.setData(QtCore.Qt.EditRole, value)
        table.setItem(0, 0, item)
        table.setItemDelegateForColumn(0, ValueBarDelegate(table, **delegate))
        table.show()
        QtWait.pump()
        return table, item

    def pixel(self, table, fraction):
        """The colour at *fraction* along the cell's bar track, mid-height."""
        rect = table.visualItemRect(table.item(0, 0))
        track = rect.adjusted(3, 4, -3, -4)
        x = int(track.left() + fraction * track.width())
        shot = table.viewport().grab().toImage()
        return QtGui.QColor(shot.pixel(x, track.center().y() - 6))

    def is_fill(self, color):
        """The bar's green showing through, over whatever the theme's background is."""
        return color.green() - max(color.red(), color.blue()) > 40

    def test_the_bar_fills_to_the_value(self):
        table, _ = self.table(0.5, color=FILL)
        self.assertTrue(self.is_fill(self.pixel(table, 0.25)))
        self.assertFalse(self.is_fill(self.pixel(table, 0.75)))

    def test_a_log_scale_gives_equal_ratios_equal_lengths(self):
        bar = ValueBarDelegate(minimum=0.01, maximum=10.0, scale="log")
        self.assertAlmostEqual(bar.fraction(0.1), 1 / 3, places=6)
        self.assertAlmostEqual(bar.fraction(1.0), 2 / 3, places=6)
        self.assertEqual((bar.fraction(0.0), bar.fraction(100.0)), (0.0, 1.0))
        table, _ = self.table(1.0, minimum=0.01, maximum=10.0, scale="log", color=FILL)
        self.assertTrue(self.is_fill(self.pixel(table, 0.6)))
        self.assertFalse(self.is_fill(self.pixel(table, 0.72)))

    def test_what_cannot_be_drawn_is_refused(self):
        for kwargs in (
            {"scale": "cubic"},
            {"scale": "log", "minimum": 0.0},
            {"minimum": 2.0, "maximum": 1.0},
        ):
            with self.subTest(**kwargs), self.assertRaises(ValueError):
                ValueBarDelegate(**kwargs)

    def test_a_gradient_track_marks_the_value(self):
        table, _ = self.table(
            0.5, gradient=[(0.0, "#ff8000"), (1.0, "#80c0ff")], formatter=lambda v: ""
        )
        left, right = self.pixel(table, 0.1), self.pixel(table, 0.9)
        self.assertGreater(left.red(), left.blue())  # warm end
        self.assertGreater(right.blue(), right.red())  # cool end

    def test_a_ghost_value_is_drawn_beside_the_value(self):
        table, item = self.table(0.2, color=FILL, ghost_role=GHOST, formatter=lambda v: "")
        before = self.pixel(table, 0.8)
        item.setData(GHOST, 0.8)
        QtWait.pump()
        self.assertNotEqual(self.pixel(table, 0.8).getRgb(), before.getRgb())

    def test_typing_a_value_into_the_cell_moves_the_bar(self):
        table, item = self.table(0.2, color=FILL)
        table.editItem(item)
        QtWait.pump()
        editor = table.viewport().focusWidget()
        self.assertIsNotNone(editor)
        QtWidgets.QApplication.sendEvent(  # select what is there, as a user would
            editor, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        )
        for char in "0.9":
            QtWidgets.QApplication.sendEvent(
                editor,
                QtGui.QKeyEvent(QtCore.QEvent.KeyPress, 0, QtCore.Qt.NoModifier, char),
            )
        QtWidgets.QApplication.sendEvent(
            editor, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Return, QtCore.Qt.NoModifier)
        )
        QtWait.pump()
        self.assertTrue(math.isclose(float(item.data(QtCore.Qt.EditRole)), 0.9, abs_tol=1e-6))
        self.assertTrue(self.is_fill(self.pixel(table, 0.8)))

    def test_a_cell_with_no_number_draws_as_any_cell(self):
        table, item = self.table("n/a", color=FILL)
        self.assertIsNone(table.itemDelegateForColumn(0).value_of(table.model().index(0, 0)))
        self.assertFalse(self.is_fill(self.pixel(table, 0.25)))


if __name__ == "__main__":
    unittest.main()
