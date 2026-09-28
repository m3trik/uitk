# !/usr/bin/python
# coding=utf-8
"""Tests for ColumnConfig -- a view's header menu of columns to show or hide.

Driven the way a user does it: right-click the header, click a column's row in
the menu it opens (``QMenu.exec_`` is answered by triggering that row, which is
what a click does). One primitive serves a plain ``QTableWidget`` and
``QTreeWidget`` as well as uitk's ``TableWidget`` / ``TreeWidget`` options.
"""

import unittest
from unittest import mock

from conftest import QtBaseTestCase, QtWait, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets  # noqa: E402
from qtpy.QtTest import QTest  # noqa: E402

from uitk.managers.settings_manager import SettingsManager  # noqa: E402
from uitk.widgets.column_config import ColumnConfig  # noqa: E402
from uitk.widgets.tableWidget import TableWidget  # noqa: E402
from uitk.widgets.treeWidget import TreeWidget  # noqa: E402

HEADERS = ["Name", "Type", "Value", "Notes"]
VIEWS = (QtWidgets.QTableWidget, QtWidgets.QTreeWidget)


class _ColumnCase(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.settings = SettingsManager(
            org="uitk_test", app="column_config", namespace=self._testMethodName
        )
        self.settings.clear()
        self.addCleanup(self.settings.clear)

    def make(self, cls, name="view"):
        view = self.track_widget(cls())
        view.setObjectName(name)
        if isinstance(view, QtWidgets.QTreeWidget):
            view.setHeaderLabels(HEADERS)
        else:
            view.setColumnCount(len(HEADERS))
            view.setHorizontalHeaderLabels(HEADERS)
        return view

    @staticmethod
    def header(view):
        if isinstance(view, QtWidgets.QTreeView):
            return view.header()
        return view.horizontalHeader()

    def pick(self, view, label=None):
        """Right-click *view*'s header, click *label*'s row (``None``: dismiss).

        Returns:
            ``{text: action}`` of the menu that opened.
        """
        rows = {}

        def exec_(menu, _pos):
            rows.update({a.text(): a for a in menu.actions()})
            row = rows.get(label)
            if row is None or not row.isEnabled():
                return None
            row.trigger()  # a click: the check flips, then the menu returns it
            return row

        with mock.patch.object(QtWidgets.QMenu, "exec_", exec_):
            self.header(view).customContextMenuRequested.emit(QtCore.QPoint(4, 4))
        return rows

    def hidden(self, view):
        header = self.header(view)
        return [HEADERS[c] for c in range(len(HEADERS)) if header.isSectionHidden(c)]

    def order(self, view):
        header = self.header(view)
        return [HEADERS[header.logicalIndex(v)] for v in range(header.count())]

    def in_menu(self, view, act=None):
        """Right-click *view*'s header and, while the menu is up, call
        ``act(rows)`` with its list of rows (a reorderable menu's).

        Returns:
            The row labels, top to bottom, as the menu opened.
        """
        seen, errors = [], []

        def exec_(menu, pos):
            try:
                return run(menu, pos)
            except BaseException as e:  # a slot's exception is only printed
                errors.append(e)

        def run(menu, pos):
            menu.popup(pos)
            QtWait.until(menu.isVisible, "the column menu never showed")
            rows = menu.findChild(QtWidgets.QListWidget)
            self.assertIsNotNone(rows, "not a reorderable menu")
            seen.extend(rows.item(i).text() for i in range(rows.count()))
            if act is not None:
                act(rows)
                self.assertTrue(menu.isVisible(), "the menu stays up for more")
            menu.hide()
            return None

        with mock.patch.object(QtWidgets.QMenu, "exec_", exec_):
            self.header(view).customContextMenuRequested.emit(QtCore.QPoint(4, 4))
        if errors:
            raise errors[0]
        return seen

    @staticmethod
    def row_point(rows, label):
        [item] = rows.findItems(label, QtCore.Qt.MatchExactly)
        return rows.visualItemRect(item).center()

    def click_row(self, rows, label):
        QTest.mouseClick(
            rows.viewport(),
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
            self.row_point(rows, label),
        )

    def drag_row(self, rows, label, onto):
        """Press on *label*'s row, move over *onto*'s, release there."""
        viewport = rows.viewport()
        start, end = self.row_point(rows, label), self.row_point(rows, onto)
        left, none = QtCore.Qt.LeftButton, QtCore.Qt.NoModifier
        QTest.mousePress(viewport, left, none, start)
        QTest.mouseMove(viewport, start + QtCore.QPoint(0, 1))
        QTest.mouseMove(viewport, end)
        QTest.mouseRelease(viewport, left, none, end)

    def fill_table(self, modes, stretch_last=False):
        """A shown 600px table whose columns take *modes* (60px when not
        stretching); returns it and its header."""
        view = self.make(QtWidgets.QTableWidget)
        header = self.header(view)
        header.setStretchLastSection(stretch_last)
        for column, mode in enumerate(modes):
            header.setSectionResizeMode(column, mode)
            if mode != QtWidgets.QHeaderView.Stretch:
                view.setColumnWidth(column, 60)
        view.resize(600, 200)
        view.show()
        QtWidgets.QApplication.processEvents()
        return view, header

    @staticmethod
    def widths(view):
        header = view.horizontalHeader()
        QtWidgets.QApplication.processEvents()
        return {HEADERS[c]: header.sectionSize(c) for c in range(header.count())}


class ColumnConfigTest(_ColumnCase):
    def test_the_menu_lists_every_column_ticked_while_shown(self):
        for cls in VIEWS:
            with self.subTest(view=cls.__name__):
                view = self.make(cls)
                ColumnConfig.attach(view, settings=self.settings)
                rows = self.pick(view)
                self.assertEqual(list(rows), HEADERS)
                self.assertTrue(all(a.isChecked() for a in rows.values()))

    def test_unticking_hides_the_column_and_the_next_view_restores_it(self):
        for cls in VIEWS:
            with self.subTest(view=cls.__name__):
                key = f"{cls.__name__}_layout"
                view = self.make(cls)
                ColumnConfig.attach(view, settings=self.settings, settings_key=key)
                self.pick(view, "Type")
                self.assertEqual(self.hidden(view), ["Type"])
                self.assertFalse(self.pick(view)["Type"].isChecked())

                again = self.make(cls)
                ColumnConfig.attach(again, settings=self.settings, settings_key=key)
                self.assertEqual(self.hidden(again), [])
                ColumnConfig.of(again).restore()
                self.assertEqual(self.hidden(again), ["Type"])

                self.pick(again, "Type")  # ticking it shows it again
                self.assertEqual(self.hidden(again), [])

    def test_the_last_visible_column_cannot_be_hidden(self):
        view = self.make(QtWidgets.QTableWidget)
        ColumnConfig.attach(view, settings=self.settings)
        for label in ("Type", "Value", "Notes"):
            self.pick(view, label)
        rows = self.pick(view, "Name")
        self.assertFalse(rows["Name"].isEnabled())
        self.assertEqual(self.hidden(view), ["Type", "Value", "Notes"])

    def test_a_locked_column_cannot_be_hidden(self):
        view = self.make(QtWidgets.QTableWidget)
        ColumnConfig.attach(view, settings=self.settings, locked=[0])
        rows = self.pick(view, "Name")
        self.assertFalse(rows["Name"].isEnabled())
        self.assertTrue(rows["Name"].isChecked())
        self.assertEqual(self.hidden(view), [])
        self.assertFalse(ColumnConfig.of(view).set_hidden(0, True))
        self.assertEqual(self.hidden(view), [])

    def test_dismissing_the_menu_changes_nothing(self):
        view = self.make(QtWidgets.QTableWidget)
        ColumnConfig.attach(view, settings=self.settings)
        self.pick(view, None)
        self.assertEqual(self.hidden(view), [])
        self.assertIsNone(ColumnConfig.of(view).settings.value("hidden_columns"))

    def test_a_dragged_order_is_saved_and_restored(self):
        view = self.make(QtWidgets.QTableWidget)
        ColumnConfig.attach(view, settings=self.settings)
        self.header(view).moveSection(0, 3)  # Name dragged to the end
        again = self.make(QtWidgets.QTableWidget)
        ColumnConfig.attach(again, settings=self.settings).restore()
        header = self.header(again)
        self.assertEqual([header.logicalIndex(v) for v in range(4)], [1, 2, 3, 0])

    def test_attach_is_idempotent_and_of_finds_it(self):
        view = self.make(QtWidgets.QTableWidget)
        self.assertIsNone(ColumnConfig.of(view))
        first = ColumnConfig.attach(view, settings=self.settings)
        self.assertIs(ColumnConfig.attach(view, settings=self.settings), first)
        self.assertIs(ColumnConfig.of(view), first)
        self.assertTrue(self.header(view).sectionsMovable())


class ColumnReorderTest(_ColumnCase):
    """``reorderable``: the menu's rows are dragged into the column order."""

    def test_a_row_dragged_in_the_menu_moves_its_column_and_is_kept(self):
        for cls in VIEWS:
            with self.subTest(view=cls.__name__):
                key = f"{cls.__name__}_order"
                view = self.make(cls)
                ColumnConfig.attach(
                    view, settings=self.settings, settings_key=key, reorderable=True
                )
                self.in_menu(view, lambda rows: self.drag_row(rows, "Name", "Notes"))
                self.assertEqual(self.order(view), ["Type", "Value", "Notes", "Name"])
                self.assertEqual(self.in_menu(view), ["Type", "Value", "Notes", "Name"])
                again = self.make(cls)
                ColumnConfig.attach(
                    again, settings=self.settings, settings_key=key, reorderable=True
                ).restore()
                self.assertEqual(self.order(again), ["Type", "Value", "Notes", "Name"])

    def test_a_click_on_a_row_shows_or_hides_its_column(self):
        view = self.make(QtWidgets.QTableWidget)
        ColumnConfig.attach(view, settings=self.settings, reorderable=True)

        def toggle_twice(rows):
            self.click_row(rows, "Type")
            self.assertEqual(self.hidden(view), ["Type"])
            [item] = rows.findItems("Type", QtCore.Qt.MatchExactly)
            self.assertFalse(item.data(ColumnConfig.SHOWN_ROLE), "its tick is gone")
            self.click_row(rows, "Value")
            self.assertEqual(self.hidden(view), ["Type", "Value"])

        self.in_menu(view, toggle_twice)
        self.in_menu(view, lambda rows: self.click_row(rows, "Type"))
        self.assertEqual(self.hidden(view), ["Value"])

    def test_the_rows_follow_the_view_order(self):
        view = self.make(QtWidgets.QTableWidget)
        ColumnConfig.attach(view, settings=self.settings, reorderable=True)
        self.header(view).moveSection(3, 0)
        self.assertEqual(self.in_menu(view), ["Notes", "Name", "Type", "Value"])

    def test_a_locked_row_is_not_toggled_but_still_moves(self):
        view = self.make(QtWidgets.QTableWidget)
        ColumnConfig.attach(view, settings=self.settings, locked=[0], reorderable=True)

        def act(rows):
            self.click_row(rows, "Name")
            self.assertEqual(self.hidden(view), [])
            self.drag_row(rows, "Name", "Value")

        self.in_menu(view, act)
        self.assertEqual(self.order(view), ["Type", "Value", "Name", "Notes"])

    def test_without_the_option_the_menu_is_a_list_of_toggles(self):
        view = self.make(QtWidgets.QTableWidget)
        ColumnConfig.attach(view, settings=self.settings)
        self.assertEqual(list(self.pick(view)), HEADERS)


class ColumnFillTest(_ColumnCase):
    """A column's width behaviour -- fixed, or taking the spare width -- stays
    with the column wherever it is moved."""

    H = QtWidgets.QHeaderView

    def test_the_last_column_filling_keeps_filling_after_it_moves(self):
        # Qt's stretchLastSection fills a POSITION: dragged elsewhere, the old
        # last column would shrink back and whatever landed last would fill.
        view, header = self.fill_table([self.H.Interactive] * 4, stretch_last=True)
        config = ColumnConfig.attach(view, settings=self.settings, reorderable=True)
        self.in_menu(view, lambda rows: self.drag_row(rows, "Notes", "Name"))
        self.assertEqual(self.order(view), ["Notes", "Name", "Type", "Value"])
        widths = self.widths(view)
        self.assertEqual(widths["Value"], 60, "a fixed column moved last stays fixed")
        self.assertGreater(widths["Notes"], 300, "the filling column still fills")
        view.resize(800, 200)
        self.assertGreater(self.widths(view)["Notes"], 500)
        self.assertIs(ColumnConfig.of(view), config)

    def test_a_header_drag_keeps_the_fill_with_its_column(self):
        view, header = self.fill_table([self.H.Interactive] * 4, stretch_last=True)
        ColumnConfig.attach(view, settings=self.settings)
        header.moveSection(3, 0)  # what a drag of the Notes section does
        widths = self.widths(view)
        self.assertEqual(widths["Value"], 60)
        self.assertGreater(widths["Notes"], 300)

    def test_a_stretch_column_moved_anywhere_still_stretches(self):
        modes = [self.H.Interactive, self.H.Interactive, self.H.Stretch]
        view, header = self.fill_table(modes + [self.H.Interactive])
        config = ColumnConfig.attach(view, settings=self.settings)
        config.set_order([2, 0, 1, 3])
        self.assertEqual(self.order(view), ["Value", "Name", "Type", "Notes"])
        self.assertGreater(self.widths(view)["Value"], 300)
        self.assertEqual(self.widths(view)["Notes"], 60)

    def test_with_every_filling_column_hidden_the_last_shown_fills_until_one_returns(
        self,
    ):
        modes = [self.H.Interactive, self.H.Stretch, self.H.Interactive]
        view, header = self.fill_table(modes + [self.H.Interactive])
        config = ColumnConfig.attach(view, settings=self.settings)
        config.set_hidden(1, True)
        widths = self.widths(view)
        self.assertEqual(
            sum(widths.values()), view.viewport().width(), "no gap at the right"
        )
        self.assertGreater(widths["Notes"], 300)
        config.set_hidden(1, False)
        widths = self.widths(view)
        self.assertEqual(widths["Notes"], 60, "back to its own width")
        self.assertGreater(widths["Type"], 300)

    def test_a_view_that_never_filled_is_left_as_it_is(self):
        view, header = self.fill_table([self.H.Interactive] * 4)
        config = ColumnConfig.attach(view, settings=self.settings)
        config.set_hidden(3, True)
        config.set_order([3, 2, 1, 0])
        self.assertFalse(header.stretchLastSection())
        self.assertEqual(
            {c: w for c, w in self.widths(view).items() if c != "Notes"},
            {"Name": 60, "Type": 60, "Value": 60},
        )


class TableWidgetColumnConfigTest(_ColumnCase):
    """uitk's TableWidget carries the option, the way TreeWidget does."""

    def test_the_table_option_hides_persists_and_restores(self):
        table = self.make(TableWidget, name="tbl_things")
        table.enable_column_config(settings=self.settings)
        self.pick(table, "Value")
        self.assertEqual(self.hidden(table), ["Value"])

        again = self.make(TableWidget, name="tbl_things")
        again.enable_column_config(settings=self.settings)
        again.restore_column_state()
        self.assertEqual(self.hidden(again), ["Value"])

    def test_the_table_option_takes_locked_columns(self):
        table = self.make(TableWidget)
        table.enable_column_config(settings=self.settings, locked=[0])
        self.assertFalse(self.pick(table, "Name")["Name"].isEnabled())

    def test_both_options_take_a_reorderable_menu(self):
        for cls in (TreeWidget, TableWidget):
            with self.subTest(view=cls.__name__):
                view = self.make(cls)
                view.enable_column_config(settings=self.settings, reorderable=True)
                self.assertEqual(self.in_menu(view), HEADERS)

    def test_tree_and_table_share_the_primitive(self):
        tree = self.make(TreeWidget)
        table = self.make(TableWidget)
        tree.enable_column_config(settings=self.settings)
        table.enable_column_config(settings=self.settings)
        self.assertIsInstance(ColumnConfig.of(tree), ColumnConfig)
        self.assertIsInstance(ColumnConfig.of(table), ColumnConfig)


if __name__ == "__main__":
    unittest.main()
