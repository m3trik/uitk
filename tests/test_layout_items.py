# !/usr/bin/python
# coding=utf-8
"""Tests for ``_LayoutItems``: reading a layout without leaving item wrappers behind.

PySide's ``QLayout.itemAt`` keeps the wrapper of the item it returns alive under
the layout, and Qt deletes that item natively when the widget it holds dies, so
the wrapper stays registered at a freed address (the uitk suite's intermittent
exit 139). ``_LayoutItems`` reads the same contents through tracked objects.
"""

import ast
import unittest
from pathlib import Path

from conftest import QtBaseTestCase
from qtpy import QtCore, QtWidgets, shiboken

from uitk.widgets._layout_items import _LayoutItems


def _item_wrappers():
    """Every registered wrapper of a layout item that is not a layout."""
    return [
        w
        for w in shiboken.getAllValidWrappers()
        if isinstance(w, QtWidgets.QLayoutItem) and not isinstance(w, QtWidgets.QLayout)
    ]


class TestLayoutItems(QtBaseTestCase):
    """``a | stretch | [nested] | b`` in a horizontal layout on a host widget.

    ``a`` carries an object name and ``b`` none: a lookup by name (Qt matches
    an EMPTY name literally) would drop one of them.
    """

    def setUp(self):
        super().setUp()
        self.host = self.track_widget(QtWidgets.QWidget())
        self.layout = QtWidgets.QHBoxLayout(self.host)
        self.a = QtWidgets.QLabel("a")
        self.a.setObjectName("lbl_a")
        self.layout.addWidget(self.a)
        self.layout.addStretch(1)
        self.sub = QtWidgets.QVBoxLayout()
        self.layout.addLayout(self.sub)
        self.nested = QtWidgets.QLabel("nested")
        self.sub.addWidget(self.nested)
        self.b = QtWidgets.QLabel("b")
        self.layout.addWidget(self.b)

    def test_item_at_leaves_a_registered_wrapper_once_qt_deletes_the_item(self):
        # The PySide behavior _LayoutItems exists for. If this starts failing,
        # PySide stopped parenting itemAt's item to the layout and the reads in
        # _LayoutItems could go back to itemAt.
        known = _item_wrappers()  # held, so no id below can be reused
        known_ids = {id(w) for w in known}
        self.layout.itemAt(0)  # itemAt on purpose: a's item, dropped at once
        self.a.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        kept = [w for w in _item_wrappers() if id(w) not in known_ids]
        still_valid = [shiboken.isValid(w) for w in kept]
        for w in kept:  # never leave the hazard behind for a later test
            shiboken.invalidate(w)
        self.assertEqual(self.layout.count(), 3, "Qt dropped a's item itself")
        self.assertEqual(still_valid, [True])

    def test_widgets_are_the_layouts_own_widgets_in_order(self):
        self.assertEqual(_LayoutItems.widgets(self.layout), [self.a, self.b])
        self.assertEqual(_LayoutItems.widgets(self.sub), [self.nested])

    def test_widget_at_is_none_for_a_spacer_a_layout_or_a_bad_index(self):
        self.assertIs(_LayoutItems.widget_at(self.layout, 0), self.a)
        self.assertIsNone(_LayoutItems.widget_at(self.layout, 1))
        self.assertIsNone(_LayoutItems.widget_at(self.layout, 2))
        self.assertIs(_LayoutItems.widget_at(self.layout, 3), self.b)
        self.assertIsNone(_LayoutItems.widget_at(self.layout, 9))

    def test_layouts_are_the_nested_layouts_in_order(self):
        first = QtWidgets.QHBoxLayout()
        self.layout.insertLayout(0, first)
        self.assertEqual(_LayoutItems.layouts(self.layout), [first, self.sub])
        self.assertEqual(_LayoutItems.layouts(self.sub), [])

    def test_entries_keep_every_item_in_its_place(self):
        entries = _LayoutItems.entries(self.layout)
        self.assertEqual(len(entries), self.layout.count())
        self.assertIs(entries[0], self.a)
        self.assertIsNotNone(entries[1].spacerItem())
        self.assertIs(entries[2], self.sub)
        self.assertIs(entries[3], self.b)

    def test_is_empty_answers_as_the_layout_item_does(self):
        self.b.hide()
        policy = self.a.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.a.setSizePolicy(policy)
        self.a.hide()
        items = [self.layout.itemAt(i) for i in range(4)]  # itemAt on purpose
        expected = [item.isEmpty() for item in items]
        got = [_LayoutItems.is_empty(e) for e in _LayoutItems.entries(self.layout)]
        self.assertEqual(got, expected)
        self.assertEqual(got, [False, True, False, True])

    def test_reads_leave_no_item_wrapper_behind(self):
        grid_host = self.track_widget(QtWidgets.QWidget())
        grid = QtWidgets.QGridLayout(grid_host)
        grid.addWidget(QtWidgets.QLabel("cell"), 0, 0)
        known = _item_wrappers()
        known_ids = {id(w) for w in known}
        _LayoutItems.widgets(self.layout)
        _LayoutItems.widget_at(self.layout, 3)
        _LayoutItems.layouts(self.layout)
        _LayoutItems.first_free_row(grid, 0)
        self.assertEqual([w for w in _item_wrappers() if id(w) not in known_ids], [])
        # entries() wraps the spacer, and only the spacer: no widget dies under it.
        _LayoutItems.entries(self.layout)
        minted = [w for w in _item_wrappers() if id(w) not in known_ids]
        self.assertEqual([w.spacerItem() is not None for w in minted], [True])

    def test_an_uninstalled_layout_has_no_widgets_to_report(self):
        orphan = QtWidgets.QHBoxLayout()
        label = self.track_widget(QtWidgets.QLabel("loose"))
        orphan.addWidget(label)
        self.assertEqual(_LayoutItems.widgets(orphan), [])

    def test_first_free_row_matches_item_at_position_with_spans(self):
        grid_host = self.track_widget(QtWidgets.QWidget())
        grid = QtWidgets.QGridLayout(grid_host)
        grid.addWidget(QtWidgets.QLabel("top"), 0, 0)
        grid.addWidget(QtWidgets.QLabel("tall"), 1, 0, 2, 1)
        grid.addWidget(QtWidgets.QLabel("right"), 3, 1)
        grid.addWidget(QtWidgets.QLabel("wide"), 4, 0, 1, 2)
        self.assertEqual(_LayoutItems.first_free_row(grid, 0), 3)
        self.assertEqual(_LayoutItems.first_free_row(grid, 1), 0)
        empty = QtWidgets.QGridLayout(self.track_widget(QtWidgets.QWidget()))
        self.assertEqual(_LayoutItems.first_free_row(empty, 0), 0)

    def test_widget_at_position_matches_item_at_position_with_spans(self):
        grid_host = self.track_widget(QtWidgets.QWidget())
        grid = QtWidgets.QGridLayout(grid_host)
        top, tall = QtWidgets.QLabel("top"), QtWidgets.QLabel("tall")
        grid.addWidget(top, 0, 0)
        grid.addWidget(tall, 1, 0, 2, 1)
        grid.addItem(QtWidgets.QSpacerItem(4, 4), 0, 1)
        self.assertIs(_LayoutItems.widget_at_position(grid, 0, 0), top)
        self.assertIs(_LayoutItems.widget_at_position(grid, 2, 0), tall)
        self.assertIsNone(_LayoutItems.widget_at_position(grid, 0, 1))  # a spacer
        self.assertIsNone(_LayoutItems.widget_at_position(grid, 5, 0))


class TestNoLayoutWalkMintsItemWrappers(unittest.TestCase):
    """Guard: uitk and its tests read layouts through ``_LayoutItems``.

    Flags ``.itemAtPosition(...)`` and a one-argument ``.itemAt(...)`` whose
    argument is not a position (a view's ``itemAt(event.pos())`` is a
    different API). ``QFormLayout.itemAt(row, role)`` keeps no wrapper, so the
    two-argument form passes. A test that needs the item itself (one that
    proves the hazard, or compares against Qt's own answer) says so with
    :attr:`MARKER` on the call's line.
    """

    MARKER = "itemAt on purpose"
    MESSAGE = (
        "a layout read through itemAt/itemAtPosition leaves the item's wrapper "
        "registered past the item; use _LayoutItems"
    )

    @classmethod
    def _offenders(cls, root):
        """``"<path>:<line>"`` for every unmarked layout ``itemAt`` under *root*."""
        offenders = []
        for path in sorted(root.rglob("*.py")):
            if path.name == "_layout_items.py" or "temp_tests" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            lines = source.splitlines()
            for node in ast.walk(ast.parse(source)):
                if not (
                    isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                ):
                    continue
                name = node.func.attr
                if not (
                    name == "itemAtPosition"
                    or (
                        name == "itemAt"
                        and len(node.args) == 1
                        and "pos" not in ast.unparse(node.args[0]).lower()
                    )
                ):
                    continue
                if cls.MARKER not in lines[node.lineno - 1]:
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}")
        return offenders

    def test_no_uitk_module_calls_layout_item_at(self):
        root = Path(__file__).resolve().parent.parent / "uitk"
        self.assertEqual(self._offenders(root), [], self.MESSAGE)

    def test_no_test_reads_a_layout_through_item_at(self):
        root = Path(__file__).resolve().parent
        self.assertEqual(self._offenders(root), [], self.MESSAGE)


if __name__ == "__main__":
    unittest.main()
