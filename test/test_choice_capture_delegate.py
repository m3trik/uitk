# !/usr/bin/python
# coding=utf-8
"""Tests for in-cell choice capture (uitk.widgets.choice_capture_delegate).

The dropdown sibling of the hotkey capture delegate: a plain cell that
opens a ``QComboBox`` editor on double-click and commits the picked /
typed value via ``captured(row, col, value)`` — replacing a persistent
combo cell widget (which grabs hover/select).
"""
import unittest

from qtpy import QtWidgets, QtCore
from conftest import QtBaseTestCase, setup_qt_application
from uitk.widgets.choice_capture_delegate import (
    ChoiceCaptureDelegate,
    BorderedChoiceCaptureDelegate,
    install_choice_capture,
)

app = setup_qt_application()

CHOICES = ["Display", "Edit", "Selection"]


class TestInstallChoiceCapture(QtBaseTestCase):
    """The turnkey ``install_choice_capture`` helper on a real table."""

    def _table(self, value=""):
        table = QtWidgets.QTableWidget(1, 2)
        table.setItem(0, 0, QtWidgets.QTableWidgetItem("Macro"))
        item = QtWidgets.QTableWidgetItem(value)
        # editItem requires the item to be editable.
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        table.setItem(0, 1, item)
        return table

    def _open_editor(self, table):
        table.editItem(table.item(0, 1))
        QtWidgets.QApplication.processEvents()
        editor = table.viewport().focusWidget()
        self.assertIsInstance(editor, QtWidgets.QComboBox)
        return editor

    def test_pick_emits_row_col_value_and_sets_cell(self):
        table = self._table()
        captured = []
        install_choice_capture(
            table, 1, CHOICES, lambda r, c, v: captured.append((r, c, v))
        )

        editor = self._open_editor(table)
        self.assertEqual([editor.itemText(i) for i in range(editor.count())], CHOICES)

        # Simulate the user picking "Selection" from the dropdown.
        editor.setCurrentIndex(CHOICES.index("Selection"))
        editor.activated.emit(CHOICES.index("Selection"))
        # captured is deferred one tick (singleShot) so a slot may rebuild
        # the table — drain the event loop to deliver it.
        QtWidgets.QApplication.processEvents()

        self.assertEqual(captured, [(0, 1, "Selection")])
        self.assertEqual(table.item(0, 1).text(), "Selection")

    def test_editable_allows_typed_value(self):
        table = self._table()
        captured = []
        install_choice_capture(
            table, 1, CHOICES, lambda r, c, v: captured.append(v), editable=True
        )

        editor = self._open_editor(table)
        self.assertTrue(editor.isEditable())
        editor.setCurrentText("Animation")  # not in CHOICES
        # Focus-out / commit path: drive the delegate directly the way the
        # view's editor event filter does on commit.
        delegate = table.itemDelegateForColumn(1)
        delegate.setModelData(editor, table.model(), table.model().index(0, 1))
        QtWidgets.QApplication.processEvents()

        self.assertEqual(captured, ["Animation"])
        self.assertEqual(table.item(0, 1).text(), "Animation")

    def test_non_editable_combo(self):
        table = self._table()
        install_choice_capture(
            table, 1, CHOICES, lambda *a: None, editable=False
        )
        editor = self._open_editor(table)
        self.assertFalse(editor.isEditable())

    def test_stored_custom_value_is_preserved_in_editor(self):
        """A pre-existing value outside CHOICES must show up as selectable."""
        table = self._table(value="Custom")
        install_choice_capture(table, 1, CHOICES, lambda *a: None)
        editor = self._open_editor(table)
        self.assertEqual(editor.currentText(), "Custom")
        self.assertGreaterEqual(editor.findText("Custom"), 0)

    def test_bordered_delegate_captures(self):
        table = self._table()
        captured = []
        delegate = install_choice_capture(
            table, 1, CHOICES, lambda r, c, v: captured.append(v), bordered=True
        )
        self.assertIsInstance(delegate, BorderedChoiceCaptureDelegate)

        editor = self._open_editor(table)
        editor.setCurrentIndex(0)
        editor.activated.emit(0)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(captured, [CHOICES[0]])

    def test_noedit_triggers_still_opens_via_edititem(self):
        table = self._table()
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        captured = []
        install_choice_capture(
            table, 1, CHOICES, lambda r, c, v: captured.append(v)
        )

        editor = self._open_editor(table)
        editor.setCurrentIndex(1)
        editor.activated.emit(1)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(captured, [CHOICES[1]])

    def test_set_choices_updates_next_edit(self):
        table = self._table()
        delegate = install_choice_capture(table, 1, CHOICES, lambda *a: None)
        delegate.set_choices(["A", "B"])
        editor = self._open_editor(table)
        self.assertEqual([editor.itemText(i) for i in range(editor.count())], ["A", "B"])


class TestChoiceCaptureOnTableWidget(QtBaseTestCase):
    """Integration against the real uitk ``TableWidget`` (custom mouse
    handling) used by the macro-manager — the column is a plain item, no
    persistent cell widget that would grab hover/select."""

    def test_double_click_opens_dropdown_no_cell_widget(self):
        from uitk.widgets.tableWidget import TableWidget

        table = TableWidget()
        table.setColumnCount(2)
        table.setRowCount(1)
        table.setItem(0, 0, QtWidgets.QTableWidgetItem("m_wireframe"))
        table.setItem(0, 1, QtWidgets.QTableWidgetItem("Display"))
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        captured = []
        install_choice_capture(
            table, 1, CHOICES, lambda r, c, v: captured.append(v)
        )
        # The category cell is a plain item, never a cell widget.
        self.assertIsNone(table.cellWidget(0, 1))

        # Double-click is wired to open regardless of NoEditTriggers.
        table.cellDoubleClicked.emit(0, 1)
        QtWidgets.QApplication.processEvents()
        editor = table.viewport().focusWidget()
        self.assertIsInstance(editor, QtWidgets.QComboBox)

        editor.setCurrentIndex(CHOICES.index("Edit"))
        editor.activated.emit(CHOICES.index("Edit"))
        QtWidgets.QApplication.processEvents()
        self.assertEqual(captured, ["Edit"])
        self.assertEqual(table.item(0, 1).text(), "Edit")


if __name__ == "__main__":
    unittest.main()
