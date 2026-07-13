# !/usr/bin/python
# coding=utf-8
"""Unit tests for ``TableWidget`` cell-widget click-forwarding.

A cell widget installed via ``setCellWidget`` can be narrower than its cell —
e.g. a combobox with ``AdjustToContents`` self-resizes to its content width
after the view's layout and isn't re-stretched until the next relayout. The
rest of the cell then reads as inert dead space: a click there reaches the
table, not the widget.

``set_cell_widget_click_columns`` opts a column into forwarding those
dead-space clicks to the embedded widget — a combobox opens its popup, a
button is clicked, other controls take focus.

Run standalone: python -m pytest test/test_table_widget_click_forward.py -v
"""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets
from qtpy.QtTest import QTest


class _Fixture(QtBaseTestCase):
    def _make_table(self, cols=2):
        from uitk.widgets.tableWidget import TableWidget

        tbl = self.track_widget(TableWidget())
        tbl.setRowCount(2)
        tbl.setColumnCount(cols)
        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        for c in range(1, cols):
            hdr.setSectionResizeMode(c, QtWidgets.QHeaderView.Interactive)
            tbl.setColumnWidth(c, 60)
        for r in range(2):
            for c in range(cols):
                tbl.setItem(r, c, QtWidgets.QTableWidgetItem("x"))
        return tbl


class TestForwardHelper(_Fixture):
    """The forwarding primitive resolves and activates the right control."""

    def test_combo_opens_popup(self):
        tbl = self._make_table()
        combo = QtWidgets.QComboBox()
        combo.addItems(["A", "B"])
        opened = []
        combo.showPopup = lambda: opened.append(True)
        tbl.setCellWidget(0, 0, combo)

        tbl._forward_click_to_cell_widget(combo)
        self.assertEqual(len(opened), 1)

    def test_button_is_clicked(self):
        tbl = self._make_table()
        btn = QtWidgets.QPushButton("R")
        clicks = []
        btn.clicked.connect(lambda: clicks.append(True))
        tbl.setCellWidget(0, 0, btn)

        tbl._forward_click_to_cell_widget(btn)
        self.assertEqual(len(clicks), 1)

    def test_wrapped_control_is_resolved(self):
        """Cells often center the real control in a plain container; the
        forward must reach the interactive descendant, not the wrapper."""
        tbl = self._make_table()
        container = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        combo = QtWidgets.QComboBox()
        combo.addItems(["A", "B"])
        opened = []
        combo.showPopup = lambda: opened.append(True)
        lay.addWidget(combo)
        tbl.setCellWidget(0, 0, container)

        tbl._forward_click_to_cell_widget(container)
        self.assertEqual(len(opened), 1)

    def test_non_interactive_widget_is_noop(self):
        tbl = self._make_table()
        label = QtWidgets.QLabel("plain")
        tbl.setCellWidget(0, 0, label)
        # Must not raise on a widget with no interactive descendant.
        tbl._forward_click_to_cell_widget(label)


class TestForwardOnClick(_Fixture):
    """End-to-end: a bare click on the cell's dead space forwards."""

    def _click_deadspace(self, tbl, row):
        # Right edge of the (stretched, wide) column 0 — past the narrow
        # widget, so the click lands on the viewport, not the widget.
        rect = tbl.visualRect(tbl.model().index(row, 0))
        pt = QtCore.QPoint(rect.right() - 4, rect.center().y())
        QTest.mouseClick(
            tbl.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pt
        )

    def test_deadspace_click_opens_narrow_combo(self):
        tbl = self._make_table()
        combo = QtWidgets.QComboBox()
        combo.addItems(["A", "B", "C"])
        combo.setFixedWidth(50)  # narrower than the stretched cell
        opened = []
        combo.showPopup = lambda: opened.append(True)
        tbl.setCellWidget(0, 0, combo)
        tbl.set_cell_widget_click_columns([0])

        tbl.resize(500, 120)
        tbl.show()
        app.processEvents()

        # Sanity: the combo must not span the cell, or there'd be no dead space.
        self.assertLess(combo.width(), tbl.columnWidth(0))

        self._click_deadspace(tbl, 0)
        self.assertEqual(len(opened), 1)

    def test_disabled_column_does_not_forward(self):
        tbl = self._make_table()
        combo = QtWidgets.QComboBox()
        combo.addItems(["A", "B"])
        combo.setFixedWidth(50)
        opened = []
        combo.showPopup = lambda: opened.append(True)
        tbl.setCellWidget(0, 0, combo)
        # Not registered → no forwarding.

        tbl.resize(500, 120)
        tbl.show()
        app.processEvents()

        self._click_deadspace(tbl, 0)
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
