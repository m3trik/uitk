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
        self.assertEqual(
            item.foreground(0).color().name(), QtGui.QColor("blue").name()
        )


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
