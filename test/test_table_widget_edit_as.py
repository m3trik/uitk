# !/usr/bin/python
# coding=utf-8
"""Tests for TableWidget's host hooks around editing and its context menu.

``edit_cell_as`` opens a cell's inline editor on text other than the cell's own
and hands the commit to the host -- the Texture Path Editor renames a texture by
its FILE NAME, in its path cell. ``context_menu_about_to_show`` lets a host fit
the menu to the selection before it opens.

Run standalone: python -m test.test_table_widget_edit_as
"""

import unittest

from qtpy import QtCore, QtWidgets
from qtpy.QtTest import QTest

from conftest import QtBaseTestCase, QtWait, setup_qt_application

app = setup_qt_application()

PATH = "D:/proj/sourceimages/rock_Base_Color.png"


class _EditAsCase(QtBaseTestCase):
    def table(self):
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(TableWidget())
        table.add([["rock_MAT", PATH]], headers=["Shader", "Path"])
        table.resize(500, 120)
        table.show()
        QtWidgets.QApplication.processEvents()
        return table

    def open(self, table, on_commit, **kwargs):
        self.assertTrue(
            table.edit_cell_as(0, 1, "rock_Base_Color.png", on_commit, **kwargs)
        )
        QtWidgets.QApplication.processEvents()  # the deferred selection lands
        editor = table.active_editor()
        self.assertIsInstance(editor, QtWidgets.QLineEdit)
        return editor


class TestEditCellAs(_EditAsCase):
    def test_the_editor_holds_the_given_text_with_the_stem_selected(self):
        table = self.table()
        editor = self.open(table, lambda text: None)
        self.assertEqual(editor.text(), "rock_Base_Color.png")
        self.assertEqual(editor.selectedText(), "rock_Base_Color")

    def test_a_commit_goes_to_the_host_and_never_into_the_cell(self):
        table = self.table()
        committed, changed = [], []
        table.cellChanged.connect(lambda r, c: changed.append((r, c)))
        editor = self.open(table, committed.append)
        editor.setText("stone_Base_Color.png")
        QTest.keyClick(editor, QtCore.Qt.Key_Return)
        QtWait.until(lambda: committed, "the commit never reached the host")
        self.assertEqual(committed, ["stone_Base_Color.png"])
        self.assertEqual(table.item(0, 1).text(), PATH, "the cell keeps its text")
        self.assertEqual(changed, [], "no cellChanged: nothing was written")

    def test_escape_or_an_unchanged_name_commits_nothing(self):
        table = self.table()
        committed = []
        editor = self.open(table, committed.append)
        editor.setText("stone.png")
        QTest.keyClick(editor, QtCore.Qt.Key_Escape)
        QtWidgets.QApplication.processEvents()
        editor = self.open(table, committed.append)
        QTest.keyClick(editor, QtCore.Qt.Key_Return)
        QTest.qWait(100)  # what a deferred commit would have needed
        self.assertEqual(committed, [])

    def test_the_next_ordinary_edit_writes_the_cell_again(self):
        """The substitute is for ONE edit: the double-click edit after it
        holds and writes the cell's own text."""
        table = self.table()
        editor = self.open(table, lambda text: None)
        QTest.keyClick(editor, QtCore.Qt.Key_Escape)
        QtWidgets.QApplication.processEvents()
        table.editItem(table.item(0, 1))
        QtWidgets.QApplication.processEvents()
        editor = table.active_editor()
        self.assertEqual(editor.text(), PATH)
        editor.setText("D:/elsewhere.png")
        QTest.keyClick(editor, QtCore.Qt.Key_Return)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(table.item(0, 1).text(), "D:/elsewhere.png")

    def test_an_explicit_selection_and_a_refused_cell(self):
        table = self.table()
        editor = self.open(table, lambda text: None, select=(0, 4))
        self.assertEqual(editor.selectedText(), "rock")
        QTest.keyClick(editor, QtCore.Qt.Key_Escape)
        QtWidgets.QApplication.processEvents()
        table.item(0, 0).setFlags(table.item(0, 0).flags() & ~QtCore.Qt.ItemIsEditable)
        self.assertFalse(table.edit_cell_as(0, 0, "x", lambda text: None))
        self.assertFalse(table.edit_cell_as(5, 0, "x", lambda text: None))

    def test_a_cell_under_another_delegate_is_refused(self):
        """The substitute text and the hand-back are the table's own editor
        delegate's. Under another (a ``RowSelectionBorderDelegate``) the
        editor opened on the cell's own text and Enter wrote the edit into
        the cell -- and the call had answered True.
        Fixed: 2026-10-04
        """
        from uitk.widgets.delegates.row_selection import RowSelectionBorderDelegate

        table = self.table()
        table.setItemDelegate(RowSelectionBorderDelegate(table))
        self.assertFalse(table.edit_cell_as(0, 1, "rock.png", lambda text: None))
        self.assertNotEqual(table.state(), QtWidgets.QAbstractItemView.EditingState)

    def test_rows_removed_under_the_editor_take_the_request_with_them(self):
        """The request waited on the table until its editor committed or
        closed, and an editor whose row is removed does neither: the next
        ordinary edit of a cell in the same place opened on the old substitute
        text and handed its commit to the old callback.
        Fixed: 2026-10-04
        """
        table = self.table()
        committed = []
        self.open(table, committed.append)
        table.add([["moss_MAT", "D:/moss.png"]], headers=["Shader", "Path"])  # rebuilt
        QtWidgets.QApplication.processEvents()
        table.editItem(table.item(0, 1))
        QtWidgets.QApplication.processEvents()
        editor = table.active_editor()
        self.assertEqual(editor.text(), "D:/moss.png")
        editor.setText("D:/elsewhere.png")
        QTest.keyClick(editor, QtCore.Qt.Key_Return)
        QTest.qWait(50)  # what a deferred commit would have needed
        self.assertEqual(table.item(0, 1).text(), "D:/elsewhere.png")
        self.assertEqual(committed, [])

    def test_refreshing_the_open_editor_keeps_the_substitute_text(self):
        """``refresh_active_editor`` re-reads the CELL into the editor, which
        put the whole path into a rename of its file name."""
        table = self.table()
        committed = []
        editor = self.open(table, committed.append)
        editor.setText("stone_Base_Color.png")
        table.refresh_active_editor()
        self.assertEqual(editor.text(), "stone_Base_Color.png")
        QTest.keyClick(editor, QtCore.Qt.Key_Return)
        QtWait.until(lambda: committed, "the commit never reached the host")
        self.assertEqual(committed, ["stone_Base_Color.png"])


class TestSortedCell(_EditAsCase):
    def test_a_cell_sorts_by_its_key_not_its_text(self):
        """ "900 KB" sorts after "2 MB" by text; a size column must not."""
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(TableWidget())
        table.add([["a", ""], ["b", ""], ["c", ""]], headers=["Name", "Size"])
        for row, (text, key) in enumerate(
            (("2 MB", 2_000_000), ("900 KB", 900_000), ("", None))
        ):
            item = table.set_sorted_cell(row, 1, text, key)
            self.assertFalse(item.flags() & QtCore.Qt.ItemIsEditable)
        table.sortItems(1, QtCore.Qt.AscendingOrder)
        self.assertEqual([table.item(r, 0).text() for r in range(3)], ["c", "b", "a"])
        table.set_sorted_cell(0, 1, "1 B", 1)  # re-keyed in place
        self.assertEqual(table.item(0, 1).text(), "1 B")


class TestContextMenuAboutToShow(_EditAsCase):
    def test_the_host_hears_before_the_menu_opens(self):
        table = self.table()
        table.menu.add("QPushButton", setText="Browse...", setObjectName="b")
        seen = []
        table.context_menu_about_to_show.connect(
            lambda: seen.append(table.menu.isVisible())
        )
        table.customContextMenuRequested.emit(QtCore.QPoint(5, 5))
        self.assertEqual(seen, [False], "announced before it shows")
        table.menu.hide()


if __name__ == "__main__":
    unittest.main()
