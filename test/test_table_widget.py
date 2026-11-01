# !/usr/bin/python
# coding=utf-8
"""Tests for ``TableWidget``'s public surface: header sorting, cell formatting,
the opt-in mouse gestures (MMB scrub, wheel scrub, single-click edit, cell-widget
click forwarding, column click actions), the selection rules, the data and
selection payload API, the context-menu action registry and the stretch column.

The topic modules (``test_table_widget_add``, ``_autofit``, ``_click_forward``,
``_edit_as``, ``_truncation``, ``_wheel``, ``test_table_formatting``,
``test_table_actions``) pin specific fixes; this one pins what every public
method does, so the widget's internals can be reorganized behind it.

Run standalone: python -m pytest test/test_table_widget.py -v
"""

import unittest
from unittest import mock

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtTest import QTest


class _TableCase(QtBaseTestCase):
    def table(self, rows=None, headers=("Name", "Node"), show=False):
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(TableWidget())
        rows = rows if rows is not None else [["b", "n_b"], ["a", "n_a"], ["c", "n_c"]]
        table.add(rows, headers=list(headers))
        if show:
            table.resize(400, 200)
            table.show()
            app.processEvents()
        return table

    def center(self, table, row, col):
        return table.visualRect(table.model().index(row, col)).center()

    def click(self, table, row, col, button=QtCore.Qt.LeftButton):
        QTest.mouseClick(
            table.viewport(), button, QtCore.Qt.NoModifier, self.center(table, row, col)
        )
        app.processEvents()

    def column(self, table, col=0):
        return [table.item(r, col).text() for r in range(table.rowCount())]


class TestHeaderSort(_TableCase):
    def test_each_header_click_flips_that_columns_order(self):
        table = self.table()
        table.default_header_click_behavior(0)
        self.assertEqual(self.column(table), ["c", "b", "a"], "first click: descending")
        table.default_header_click_behavior(0)
        self.assertEqual(self.column(table), ["a", "b", "c"])

    def test_the_click_behavior_is_replaceable(self):
        table = self.table()
        clicked = []
        table.header_click_behavior = clicked.append
        table.horizontalHeader().sectionClicked.emit(1)
        self.assertEqual(clicked, [1])


class TestCellFormatters(_TableCase):
    def test_a_cell_formatter_runs_on_apply_and_on_edit(self):
        table = self.table()
        seen = []
        table.set_cell_formatter(0, 1, lambda *a: seen.append(a))
        table.apply_formatting()
        item, value, row, col, view = seen[-1]
        self.assertEqual((value, row, col), ("n_b", 0, 1))
        self.assertIs(item, table.item(0, 1))
        self.assertIs(view, table)
        seen.clear()
        table.item(0, 1).setText("edited")
        self.assertEqual([a[1] for a in seen], ["edited"])

    def test_the_value_is_the_user_data_when_present(self):
        table = self.table()
        table.item(1, 0).setData(QtCore.Qt.UserRole, {"id": 7})
        seen = []
        table.set_column_formatter("Name", lambda item, value, *_: seen.append(value))
        table.apply_formatting()
        self.assertEqual(seen, ["b", {"id": 7}, "c"])

    def test_append_adds_and_a_plain_set_replaces(self):
        table = self.table()
        seen = []
        table.set_column_formatter(0, lambda *a: seen.append("first"))
        table.set_column_formatter(0, lambda *a: seen.append("second"), append=True)
        table.set_cell_formatter(0, 0, lambda *a: seen.append("cell"))
        table.set_header_formatter("Name", lambda *a: seen.append("header"))
        table.apply_formatting()
        # Per cell: the cell's own, then the column's, then the header's.
        self.assertEqual(seen[:4], ["cell", "first", "second", "header"])
        seen.clear()
        table.set_column_formatter(0, lambda *a: seen.append("only"))
        table.apply_formatting()
        self.assertEqual(seen.count("first") + seen.count("second"), 0)
        self.assertEqual(seen.count("only"), 3)

    def test_an_unknown_column_name_registers_nothing(self):
        table = self.table()
        seen = []
        table.set_column_formatter("Missing", lambda *a: seen.append(a))
        table.set_header_formatter("Missing", lambda *a: seen.append(a))
        table.apply_formatting()
        self.assertEqual(seen, [])

    def test_clear_formatters_stops_them_all(self):
        table = self.table()
        seen = []
        table.set_column_formatter(0, lambda *a: seen.append(a))
        table.set_cell_formatter(1, 1, lambda *a: seen.append(a))
        table.set_header_formatter("Node", lambda *a: seen.append(a))
        table.clear_formatters()
        table.apply_formatting()
        table.item(0, 0).setText("x")
        self.assertEqual(seen, [])


class TestItemColours(_TableCase):
    def item(self):
        table = self.table()
        return table, table.item(0, 0)

    def test_a_key_sets_both_roles(self):
        table, item = self.item()
        table.format_item(item, key="valid", bold=True, italic=True)
        fg, bg = table.ACTION_COLOR_MAP["valid"]
        self.assertEqual(item.foreground().color().name().lower(), fg.lower())
        self.assertEqual(item.background().color().name().lower(), bg.lower())
        self.assertTrue(item.font().bold())
        self.assertTrue(item.font().italic())

    def test_a_key_without_a_background_leaves_it(self):
        table, item = self.item()
        item.setBackground(QtGui.QColor("#123456"))
        table.format_item(item, key="inactive")
        self.assertEqual(item.background().color().name(), "#123456")
        self.assertEqual(
            item.foreground().color().name().lower(),
            table.ACTION_COLOR_MAP["inactive"][0].lower(),
        )

    def test_explicit_colours_override_the_key(self):
        table, item = self.item()
        table.format_item(item, key="valid", fg="#ff0000", bg="#00ff00")
        self.assertEqual(item.foreground().color().name(), "#ff0000")
        self.assertEqual(item.background().color().name(), "#00ff00")

    def test_reset_clears_the_roles(self):
        table, item = self.item()
        table.format_item(item, key="valid")
        table.format_item(item, key="reset")
        self.assertIsNone(item.data(QtCore.Qt.ForegroundRole))
        self.assertIsNone(item.data(QtCore.Qt.BackgroundRole))

    def test_set_action_color_paints_the_background_only_on_request(self):
        table, item = self.item()
        item.setBackground(QtGui.QColor("#123456"))
        table.set_action_color(item, "invalid", 0, 0)
        fg, bg = table.ACTION_COLOR_MAP["invalid"]
        self.assertEqual(item.foreground().color().name().lower(), fg.lower())
        self.assertEqual(item.background().color().name(), "#123456")
        table.set_action_color(item, "invalid", 0, 0, use_bg=True)
        self.assertEqual(item.background().color().name().lower(), bg.lower())

    def test_set_action_color_skips_an_empty_reset(self):
        table, item = self.item()
        item.setForeground(QtGui.QColor("#123456"))
        table.set_action_color(item, "reset", 0, 0)
        self.assertEqual(item.foreground().color().name(), "#123456")

    def test_the_action_color_formatter_paints_by_value(self):
        table, item = self.item()
        table.action_color_formatter(item, "Warning")
        fg, bg = table.ACTION_COLOR_MAP["warning"]
        self.assertEqual(item.foreground().color().name().lower(), fg.lower())
        self.assertEqual(item.background().color().name().lower(), bg.lower())

    def test_ensure_valid_color_falls_back_to_the_cells_first_colour(self):
        table, item = self.item()
        item.setForeground(QtGui.QColor("#abcdef"))
        self.assertEqual(
            table.ensure_valid_color("#010203", "fg", item, 0, 0).name(), "#010203"
        )
        # The defaults are read (and cached) on the first fallback...
        self.assertEqual(
            table.ensure_valid_color(None, "fg", item, 0, 0).name(), "#abcdef"
        )
        # ...and stay what they were, whatever the cell is painted since.
        item.setForeground(QtGui.QColor("#ff0000"))
        self.assertEqual(
            table.ensure_valid_color(None, "fg", item, 0, 0).name(), "#abcdef"
        )
        table.clear_formatters()  # which forgets them
        self.assertEqual(
            table.ensure_valid_color(None, "fg", item, 0, 0).name(), "#ff0000"
        )

    def test_overrides_on_the_instance_reach_the_internal_callers(self):
        """``format_item`` and the map formatters resolve ``ensure_valid_color``
        on the table, so an override (or a test's patch) reaches them all."""
        table, item = self.item()
        calls = []
        real = table.ensure_valid_color

        def spy(*args):
            calls.append(args[1])
            return real(*args)

        with mock.patch.object(table, "ensure_valid_color", new=spy):
            table.format_item(item, key="valid")
            table.set_action_color(item, "valid", 0, 0)
            table.action_color_formatter(item, "valid")
            table.make_color_map_formatter({"x": ("#111111", "#222222")})(item, "x")
        self.assertEqual(calls.count("fg"), 4, calls)


class TestSectionRows(_TableCase):
    def test_a_section_row_spans_the_columns_and_reads_back(self):
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(QtWidgets.QTableWidget(2, 3))
        after = TableWidget.add_section_row(table, "Group", row=1, height=30)
        self.assertEqual(after, 2)
        self.assertEqual(table.rowCount(), 3)
        self.assertTrue(TableWidget.is_section_row(table, 1))
        self.assertFalse(TableWidget.is_section_row(table, 0))
        self.assertFalse(TableWidget.is_section_row(table, 2))
        self.assertEqual(table.columnSpan(1, 0), 3)
        self.assertEqual(table.rowHeight(1), 30)
        self.assertEqual(table.cellWidget(1, 0).text(), "Group")
        self.assertFalse(table.item(1, 0).flags() & QtCore.Qt.ItemIsSelectable)

    def test_the_default_appends(self):
        table = self.table()
        self.assertEqual(table.add_section_row(table, "End"), 4)
        self.assertTrue(table.is_section_row(table, 3))


class TestMiddleMouseScrub(_TableCase):
    def scrub(self, table, col, dx=12, dy=-3):
        events = []
        table.cellScrubStarted.connect(lambda r, c: events.append(("start", r, c)))
        table.cellScrubMoved.connect(lambda *a: events.append(("move",) + a))
        table.cellScrubFinished.connect(lambda r, c: events.append(("finish", r, c)))
        viewport = table.viewport()
        start = self.center(table, 1, col)
        QTest.mousePress(viewport, QtCore.Qt.MiddleButton, QtCore.Qt.NoModifier, start)
        during = table.is_scrubbing()
        QTest.mouseMove(viewport, start + QtCore.QPoint(dx, dy))
        QTest.mouseRelease(
            viewport,
            QtCore.Qt.MiddleButton,
            QtCore.Qt.NoModifier,
            start + QtCore.QPoint(dx, dy),
        )
        app.processEvents()
        return events, during

    def test_a_scrub_column_reports_the_drag(self):
        table = self.table(show=True)
        table.set_scrub_columns([1])
        events, during = self.scrub(table, 1)
        self.assertTrue(during)
        self.assertFalse(table.is_scrubbing())
        self.assertEqual(
            events, [("start", 1, 1), ("move", 1, 1, 12, -3), ("finish", 1, 1)]
        )

    def test_add_and_remove_a_column(self):
        table = self.table(show=True)
        table.add_scrub_column(0)
        self.assertEqual(self.scrub(table, 0)[0][0], ("start", 1, 0))
        table.remove_scrub_column(0)
        events, during = self.scrub(table, 0)
        self.assertEqual((events, during), ([], False))

    def test_an_empty_set_disables(self):
        table = self.table(show=True)
        table.set_scrub_columns([0, 1])
        table.set_scrub_columns([])
        self.assertEqual(self.scrub(table, 1)[0], [])


class TestWheelScrubColumns(_TableCase):
    def wheel(self, table, col):
        pos = QtCore.QPointF(self.center(table, 0, col))
        event = QtGui.QWheelEvent(
            pos,
            QtCore.QPointF(table.viewport().mapToGlobal(pos.toPoint())),
            QtCore.QPoint(),
            QtCore.QPoint(0, 120),
            QtCore.Qt.NoButton,
            QtCore.Qt.ShiftModifier,
            QtCore.Qt.NoScrollPhase,
            False,
        )
        table.wheelEvent(event)
        return event

    def test_add_and_remove_a_column(self):
        table = self.table(show=True)
        scrolled = []
        table.cellWheelScrolled.connect(lambda r, c, s, m: scrolled.append((r, c, s)))
        table.add_wheel_scrub_column(1)
        self.assertTrue(self.wheel(table, 1).isAccepted())
        self.assertEqual(scrolled, [(0, 1, 1)])
        self.wheel(table, 0)
        self.assertEqual(len(scrolled), 1, "column 0 is not a wheel-scrub column")
        table.remove_wheel_scrub_column(1)
        self.wheel(table, 1)
        self.assertEqual(len(scrolled), 1)


class TestSingleClickEdit(_TableCase):
    def editing(self, table):
        return table.state() == QtWidgets.QAbstractItemView.EditingState

    def test_a_registered_column_edits_on_one_click(self):
        table = self.table(show=True)
        table.set_single_click_edit_columns([1])
        self.click(table, 0, 0)
        self.assertFalse(self.editing(table))
        self.click(table, 0, 1)
        self.assertTrue(self.editing(table))

    def test_add_and_remove_a_column(self):
        table = self.table(show=True)
        table.add_single_click_edit_column(0)
        self.click(table, 1, 0)
        self.assertTrue(self.editing(table))
        table.closePersistentEditor(table.item(1, 0))
        table.setFocus()
        QTest.keyClick(table.viewport().focusWidget(), QtCore.Qt.Key_Escape)
        app.processEvents()
        table.remove_single_click_edit_column(0)
        self.click(table, 2, 0)
        self.assertFalse(self.editing(table))


class TestCellWidgetClickColumns(_TableCase):
    def test_add_and_remove_a_column(self):
        table = self.table(show=True)
        table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        button = QtWidgets.QPushButton("go")
        button.setFixedWidth(30)
        pressed = []
        button.clicked.connect(lambda: pressed.append(True))
        table.setCellWidget(0, 0, button)
        app.processEvents()
        rect = table.visualRect(table.model().index(0, 0))
        deadspace = QtCore.QPoint(rect.right() - 4, rect.center().y())

        def click():
            QTest.mouseClick(
                table.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, deadspace
            )
            app.processEvents()

        table.add_cell_widget_click_column(0)
        click()
        self.assertEqual(pressed, [True])
        table.remove_cell_widget_click_column(0)
        click()
        self.assertEqual(pressed, [True])


class TestColumnClickAction(_TableCase):
    def test_a_click_reaches_the_columns_action(self):
        table = self.table(show=True)
        hits = []
        table.set_column_click_action(0, lambda r, c: hits.append((r, c)))
        self.click(table, 2, 0)
        self.click(table, 2, 1)
        self.assertEqual(hits, [(2, 0)])

    def test_a_drag_back_onto_its_first_cell_is_no_click(self):
        table = self.table(show=True)
        hits = []
        table.set_column_click_action(0, lambda r, c: hits.append((r, c)))
        viewport = table.viewport()
        start = self.center(table, 0, 0)
        QTest.mousePress(viewport, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, start)
        QTest.mouseMove(viewport, self.center(table, 2, 0))
        QTest.mouseMove(viewport, start)
        QTest.mouseRelease(viewport, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, start)
        app.processEvents()
        self.assertEqual(hits, [])
        # The latch is released with the gesture: the next click fires.
        table.closePersistentEditor(table.item(0, 0))
        self.click(table, 1, 0)
        self.assertIn((1, 0), hits)


class TestSelectionRules(_TableCase):
    def selected(self, table):
        return sorted((i.row(), i.column()) for i in table.selectedIndexes())

    def test_a_non_selectable_column(self):
        table = self.table(show=True)
        table.set_column_selectable(0, False)
        self.click(table, 1, 0)
        self.assertEqual(self.selected(table), [])
        table.set_column_selectable(0, True)
        self.click(table, 1, 0)
        self.assertEqual(self.selected(table), [(1, 0)])

    def test_a_selection_validator(self):
        table = self.table(show=True)
        table.set_selection_validator(lambda index: index.row() != 1)
        self.click(table, 1, 1)
        self.assertEqual(self.selected(table), [])
        self.click(table, 2, 1)
        self.assertEqual(self.selected(table), [(2, 1)])

    def test_left_click_select_only(self):
        table = self.table(show=True)
        self.assertFalse(table.leftClickSelectOnly)
        table.set_left_click_select_only(True)
        self.assertTrue(table.leftClickSelectOnly)
        self.click(table, 1, 1, QtCore.Qt.RightButton)
        self.assertEqual(self.selected(table), [])
        table.setLeftClickSelectOnly(False)
        self.assertFalse(table.leftClickSelectOnly)
        self.click(table, 1, 1, QtCore.Qt.RightButton)
        self.assertEqual(self.selected(table), [(1, 1)])

    def test_selection_mode_by_name(self):
        view = QtWidgets.QAbstractItemView
        table = self.table()
        self.assertEqual(table.selectionMode(), view.ExtendedSelection)
        for name, mode in (
            ("single", view.SingleSelection),
            ("none", view.NoSelection),
            ("MULTI", view.MultiSelection),
            ("bogus", view.ExtendedSelection),
        ):
            table.set_selection_mode(name)
            self.assertEqual(table.selectionMode(), mode, name)
            self.assertEqual(table.selectionBehavior(), view.SelectItems)


class TestDataAndSelection(_TableCase):
    def test_item_data_round_trip(self):
        table = self.table()
        table.set_item_data(0, 1, 42, user_data={"node": 1})
        self.assertEqual(table.item(0, 1).text(), "42")
        self.assertTrue(table.item(0, 1).flags() & QtCore.Qt.ItemIsEditable)
        self.assertEqual(table.item_data(0, 1), {"node": 1})
        table.set_item_data(1, 1, None)
        self.assertEqual(table.item_data(1, 1), "")
        self.assertEqual(table.item_data(0, 0), "b")
        table.setItem(2, 0, None)
        self.assertIsNone(table.item_data(2, 0))

    def test_current_row_accessors(self):
        table = self.table()
        self.assertIsNone(table.selected_node())
        self.assertIsNone(table.selected_label())
        table.item(1, 1).setData(QtCore.Qt.UserRole, "node_a")
        table.setCurrentCell(1, 0)
        self.assertEqual(table.selected_node(), "node_a")
        self.assertEqual(table.selected_label(), "a")

    def test_selected_rows_labels_and_nodes(self):
        table = self.table()
        for row in range(3):
            table.item(row, 1).setData(QtCore.Qt.UserRole, f"node{row}")
        self.assertEqual(table.selected_rows(), [])
        table.setCurrentCell(1, 1, QtCore.QItemSelectionModel.NoUpdate)
        self.assertEqual(table.selected_rows(include_current=True), [1])
        for row in (2, 0):
            table.item(row, 0).setSelected(True)
            table.item(row, 1).setSelected(True)
        self.assertEqual(table.selected_rows(), [0, 2])
        self.assertEqual(sorted(table.selected_labels()), ["b", "c"])
        self.assertEqual(sorted(table.selected_nodes()), ["node0", "node2"])

    def test_get_selected_data_and_get_selection(self):
        table = self.table()
        table.item(0, 1).setData(QtCore.Qt.UserRole, {"n": 0})
        table.item(0, 0).setSelected(True)
        self.assertEqual(table.get_selected_data(), [{0: "b", 1: {"n": 0}}])
        self.assertEqual(table.get_selected_data(columns=[1]), [{1: {"n": 0}}])
        (sel,) = table.get_selection(columns={"label": 0, "path": "Node"})
        self.assertEqual(sel.row, 0)
        self.assertEqual(sel["label"], "b")
        self.assertEqual(sel.get("path"), {"n": 0})
        self.assertEqual(sel.text("path"), "n_b")
        self.assertIs(sel.item("label"), table.item(0, 0))
        (sel,) = table.get_selection()
        self.assertEqual(set(sel.values), {"Name", "Node"})

    def test_duplicate_header_keys_get_a_suffix_and_unknown_columns_drop(self):
        table = self.table(rows=[["x", "y", "z"]], headers=("A", "A", "B"))
        table.item(0, 0).setSelected(True)
        (sel,) = table.get_selection()
        self.assertEqual(list(sel.values), ["A", "A_2", "B"])
        (sel,) = table.get_selection(columns=[2, "Missing", "A"])
        self.assertEqual(list(sel.values), ["B", "A"])

    def test_selection_falls_back_to_the_current_row(self):
        table = self.table()
        table.setCurrentCell(2, 0, QtCore.QItemSelectionModel.NoUpdate)
        self.assertEqual([s.row for s in table.get_selection()], [2])
        self.assertEqual(table.get_selection(include_current=False), [])

    def test_clear_all_drops_the_rows_only(self):
        table = self.table()
        table.clear_all()
        self.assertEqual((table.rowCount(), table.columnCount()), (0, 2))


class TestContextMenuActions(_TableCase):
    def trigger(self, table, name):
        button = QtWidgets.QPushButton()
        button.setObjectName(name)
        self.track_widget(button)
        table.menu.on_item_interacted.emit(button)
        return button

    def test_a_registered_action_receives_the_selection(self):
        table = self.table()
        got = []
        table.register_menu_action("act", got.append, columns={"label": 0})
        table.item(1, 0).setSelected(True)
        self.trigger(table, "act")
        (sel,) = got[0]
        self.assertEqual((sel.row, sel["label"]), (1, "a"))
        self.trigger(table, "other")
        self.assertEqual(len(got), 1, "an unregistered name dispatches nothing")

    def test_no_selection_skips_unless_allowed(self):
        table = self.table()
        got = []
        table.register_menu_action("act", got.append, include_current=False)
        self.trigger(table, "act")
        self.assertEqual(got, [])
        table.register_menu_action(
            "act", got.append, include_current=False, allow_empty=True
        )
        self.trigger(table, "act")
        self.assertEqual(got, [[]])

    def test_transform_widget_and_arity(self):
        table = self.table()
        table.item(0, 0).setSelected(True)
        got = []
        table.register_menu_action(
            "rows",
            lambda data, widget: got.append((data, widget)),
            transform=lambda sels: [s.row for s in sels],
            pass_widget=True,
        )
        button = self.trigger(table, "rows")
        self.assertEqual(got, [([0], button)])
        table.register_menu_action("bare", lambda: got.append("bare"), pass_widget=True)
        self.trigger(table, "bare")
        self.assertEqual(got[-1], "bare")
        table.register_menu_action(
            "star", lambda *a: got.append(len(a)), pass_widget=True
        )
        self.trigger(table, "star")
        self.assertEqual(got[-1], 2)

    def test_a_host_rewiring_the_request_reconnects_the_popup(self):
        """tentacle's Channels disconnects ``customContextMenuRequested``, runs
        its own pass first, then reconnects ``_show_context_menu``."""
        table = self.table()
        table.menu.add("QPushButton", setText="Go", setObjectName="go")
        seen = []
        table.customContextMenuRequested.disconnect()
        table.customContextMenuRequested.connect(lambda _pos: seen.append("host"))
        table.customContextMenuRequested.connect(table._show_context_menu)
        table.context_menu_about_to_show.connect(lambda: seen.append("popup"))
        table.customContextMenuRequested.emit(QtCore.QPoint(5, 5))
        self.assertEqual(seen, ["host", "popup"])
        table.menu.hide()

    def test_an_outside_menu_outlives_the_table_quietly(self):
        """The dispatch hook rides on the table, so a menu handed in from
        outside -- one that outlives the table -- loses it with the table,
        instead of calling into a deleted one."""
        from uitk.widgets.menu import Menu
        from uitk.widgets.tableWidget import TableWidget

        menu = self.track_widget(Menu())
        table = TableWidget()  # untracked: deleted below
        table.menu = menu
        got = []
        table.register_menu_action("act", got.append, allow_empty=True)
        signal = QtCore.SIGNAL("on_item_interacted(PyObject)")
        self.assertEqual(menu.receivers(signal), 1)
        table.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertEqual(menu.receivers(signal), 0)
        button = self.track_widget(QtWidgets.QPushButton())
        button.setObjectName("act")
        errors = []
        with mock.patch("sys.excepthook", new=lambda *exc: errors.append(exc[1])):
            menu.on_item_interacted.emit(button)
        self.assertEqual((got, errors), ([], []))

    def test_unregister_and_validation(self):
        table = self.table()
        got = []
        table.register_menu_action("act", got.append, allow_empty=True)
        table.unregister_menu_action("act")
        table.unregister_menu_action("never")
        self.trigger(table, "act")
        self.assertEqual(got, [])
        with self.assertRaises(ValueError):
            table.register_menu_action("", got.append)
        with self.assertRaises(TypeError):
            table.register_menu_action("act", "not callable")


class TestStretchColumn(_TableCase):
    def test_the_column_fills_the_rest_and_follows_a_resize(self):
        table = self.table(show=True)
        table.setColumnWidth(0, 80)
        table.set_stretch_column(1)
        self.assertEqual(table.columnWidth(1), table.viewport().width() - 80)
        table.resize(600, 200)
        app.processEvents()
        self.assertEqual(table.columnWidth(1), table.viewport().width() - 80)
        table.stretch_column_to_fill(5)  # out of range: ignored
        self.assertEqual(table.columnWidth(1), table.viewport().width() - 80)


class TestFacadeOverrides(_TableCase):
    """Internal callers resolve public methods on the table, so an instance
    override (or a test's patch) reaches every one of them."""

    def test_add_reaches_apply_formatting(self):
        table = self.table()
        calls = []
        with mock.patch.object(table, "apply_formatting", new=lambda: calls.append(1)):
            table.add([["x", "y"]], headers=["A", "B"])
        self.assertEqual(calls, [1])

    def test_a_drag_fill_reaches_apply_formatting(self):
        table = self.table(show=True)
        viewport = table.viewport()
        QTest.mousePress(
            viewport,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
            self.center(table, 0, 1),
        )
        QTest.mouseMove(viewport, self.center(table, 2, 1))
        QTest.mouseRelease(
            viewport,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
            self.center(table, 2, 1),
        )
        app.processEvents()
        editor = table.active_editor()
        self.assertIsInstance(editor, QtWidgets.QLineEdit, "the drag opened no editor")
        editor.setText("filled")
        calls = []
        with mock.patch.object(table, "apply_formatting", new=lambda: calls.append(1)):
            QTest.keyClick(editor, QtCore.Qt.Key_Return)
            app.processEvents()
        self.assertEqual(calls, [1])
        self.assertEqual(self.column(table, 1), ["filled"] * 3)


if __name__ == "__main__":
    unittest.main()
