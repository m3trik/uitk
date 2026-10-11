# !/usr/bin/python
# coding=utf-8
"""Regression tests for TreeFormatMixin.apply_formatting.

Run standalone: python -m test.test_tree_formatting
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtGui


class TestTreeApplyFormattingRecursion(QtBaseTestCase):
    """apply_formatting must not recurse when formatters write item roles.

    Formatters call item.setForeground/setBackground, which fires itemChanged
    -> _on_item_edited -> formatters -> ... Without a signal-block guard (which
    CellFormatMixin already had but TreeFormatMixin lacked), two formatters
    setting differing colors flip-flop forever -> RecursionError.
    """

    def test_conflicting_formatters_do_not_recurse(self):
        from uitk.widgets.treeWidget import TreeWidget

        tree = self.track_widget(TreeWidget())
        tree.setColumnCount(1)
        item = QtWidgets.QTreeWidgetItem(["node"])
        tree.addTopLevelItem(item)

        def paint_red(it, value, col, *_):
            it.setForeground(col, QtGui.QColor("red"))

        def paint_blue(it, value, col, *_):
            it.setForeground(col, QtGui.QColor("blue"))

        tree.set_column_formatter(0, paint_red, append=True)
        tree.set_column_formatter(0, paint_blue, append=True)

        # Must complete without RecursionError.
        tree.apply_formatting()

        # Last formatter wins; the point is that it terminated at all.
        self.assertEqual(item.foreground(0).color().name(), QtGui.QColor("blue").name())


class TestTreeAddSignalBlocking(QtBaseTestCase):
    """add() must keep signals blocked through its whole body.

    Regression: an inner blockSignals(True)/blockSignals(False) pair ran before
    the tail (set_attributes/apply_formatting), unblocking signals mid-method
    and defeating the @Signals.blockSignals decorator — letting itemChanged
    escape during the tail of add().
    """

    def test_item_changed_does_not_escape_during_add(self):
        from uitk.widgets.treeWidget import TreeWidget

        tree = self.track_widget(TreeWidget())
        received = []
        tree.itemChanged.connect(lambda *a: received.append(a))

        # A formatter makes apply_formatting() (part of add's tail) write item
        # roles; those must not surface as external itemChanged emissions.
        tree.set_column_formatter(
            0, lambda it, v, col, *_: it.setForeground(col, QtGui.QColor("red"))
        )
        tree.add(["a", "b", "c"], headers=["Name"])

        self.assertEqual(received, [], "itemChanged must not escape during add()")


if __name__ == "__main__":
    unittest.main()


class TestTreeElidedTooltips(QtBaseTestCase):
    """``TreeWidget.elided_tooltips``: a cell cut short shows its full text in
    its tooltip -- through ``TooltipPresenter``, whether the tree was managed
    already (a registered widget) or turning it on manages it -- and its own
    tooltip follows the text."""

    LONG = "Selecting the top lock triggers the Top Lock Open animation " * 3

    def _tree(self, managed: bool):
        from uitk.widgets.treeWidget import TreeWidget
        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        tree = self.track_widget(TreeWidget())
        tree.setColumnCount(2)
        tree.setHeaderLabels(["Step", "Description"])
        tree.resize(300, 120)
        tree.header().resizeSection(0, 60)
        tree.header().resizeSection(1, 120)
        self.short = QtWidgets.QTreeWidgetItem(["A01", "Open"])
        self.long = QtWidgets.QTreeWidgetItem(["A02", self.LONG])
        tree.addTopLevelItems([self.short, self.long])
        if managed:
            TooltipPresenter.manage(tree)
        tree.show()
        QtWidgets.QApplication.processEvents()
        return tree

    def _hover(self, tree, item, col) -> str:
        import time
        from qtpy import QtCore

        QtWidgets.QToolTip.hideText()  # hides on a timer: wait it out
        deadline = time.monotonic() + 2.0
        while QtWidgets.QToolTip.isVisible() and time.monotonic() < deadline:
            QtWidgets.QApplication.processEvents()
            time.sleep(0.01)
        index = tree.indexFromItem(item, col)
        pos = tree.visualRect(index).center()
        event = QtGui.QHelpEvent(
            QtCore.QEvent.ToolTip, pos, tree.viewport().mapToGlobal(pos)
        )
        QtWidgets.QApplication.sendEvent(tree.viewport(), event)
        return QtWidgets.QToolTip.text() if QtWidgets.QToolTip.isVisible() else ""

    def test_off_by_default(self):
        tree = self._tree(managed=True)
        self.assertFalse(tree.elided_tooltips)
        self.assertEqual(self._hover(tree, self.long, 1), "")

    def test_an_elided_cell_shows_its_full_text_managed_or_not(self):
        for managed in (True, False):
            with self.subTest(managed=managed):
                tree = self._tree(managed)
                tree.elided_tooltips = True
                self.assertTrue(tree.is_elided(tree.indexFromItem(self.long, 1)))
                self.assertFalse(tree.is_elided(tree.indexFromItem(self.short, 1)))
                shown = self._hover(tree, self.long, 1)
                self.assertIn("Top Lock Open", shown)
                self.assertEqual(self._hover(tree, self.short, 1), "")

    def test_the_cells_own_tooltip_follows_unless_it_holds_the_text(self):
        tree = self._tree(managed=True)
        tree.elided_tooltips = True
        index = tree.indexFromItem(self.long, 1)
        self.assertEqual(
            tree.item_tooltip(index, "Missing object"),
            f"{self.LONG.strip()}\n\nMissing object",
        )
        self.assertEqual(
            tree.item_tooltip(index, f"x {self.LONG} y"), f"x {self.LONG} y"
        )
        self.assertTrue(
            tree.item_tooltip(index, "<b>Status</b>").endswith("<br><br><b>Status</b>")
        )
        self.long.setText(1, "line one\nline two")
        self.assertTrue(tree.is_elided(index))
