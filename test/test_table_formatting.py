# !/usr/bin/python
# coding=utf-8
"""Regression tests for CellFormatMixin's colour formatting.

These two mixins -- ``CellFormatMixin`` (tableWidget) and ``TreeFormatMixin``
(treeWidget) -- are forked copies of one formatter, and the fork has a history
of one-sided changes in both directions: ``test_tree_formatting`` covers a
recursion guard the TREE lacked and the TABLE had, and the colour map below had
a key the TABLE had and the TREE lacked. These cases pin the parts that must
stay in step until the two share a base.

Run standalone: python -m test.test_table_formatting
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtGui


class TestColorMapFormatterNoneEntries(QtBaseTestCase):
    """A ``(None, None)`` map entry means LEAVE IT ALONE, not "paint a default".

    ``make_color_map_formatter`` fed an unmapped value -- or one deliberately
    mapped to ``(None, None)``, which is exactly what ``reset`` is -- must not
    touch the item's brushes.

    These pin behaviour rather than fix a bug, and that distinction is worth
    recording. The tree copy guards on the raw value (uitk 793f8df,
    2026-03-19); the table copy does NOT, and an audit read that asymmetry as
    an un-back-ported fix. Measured 2026-09-16 it is not one: the table's
    ``ensure_valid_color(None, ...)`` falls back to
    ``_get_default_colors(item, row, col)``, so the unconditional
    ``setForeground`` re-assigns the colour the item already had. Same outcome,
    different route. What makes it worth a test is that the equivalence is
    incidental -- it rests entirely on that fallback, and anyone "simplifying"
    ``ensure_valid_color`` to return ``None`` for a ``None`` input would turn
    every reset into a repaint with nothing to catch it.
    """

    def _table_with_colored_item(self):
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(TableWidget())
        table.setRowCount(1)
        table.setColumnCount(1)
        item = QtWidgets.QTableWidgetItem("value")
        table.setItem(0, 0, item)
        item.setForeground(QtGui.QColor("#FF00FF"))
        item.setBackground(QtGui.QColor("#00FF00"))
        return table, item

    def test_none_entry_leaves_foreground_untouched(self):
        table, item = self._table_with_colored_item()
        fmt = table.make_color_map_formatter({"value": (None, None)})
        fmt(item, "value")
        self.assertEqual(
            item.foreground().color().name().upper(),
            "#FF00FF",
            "a (None, None) map entry must not repaint the foreground",
        )

    def test_none_entry_leaves_background_untouched(self):
        table, item = self._table_with_colored_item()
        fmt = table.make_color_map_formatter({"value": (None, None)})
        fmt(item, "value")
        self.assertEqual(
            item.background().color().name().upper(),
            "#00FF00",
            "a (None, None) map entry must not repaint the background",
        )

    def test_unmapped_value_leaves_colors_untouched(self):
        table, item = self._table_with_colored_item()
        fmt = table.make_color_map_formatter({"other": ("#123456", "#654321")})
        fmt(item, "value")
        self.assertEqual(item.foreground().color().name().upper(), "#FF00FF")
        self.assertEqual(item.background().color().name().upper(), "#00FF00")

    def test_a_mapped_value_still_paints(self):
        """The guard must not turn the formatter into a no-op."""
        table, item = self._table_with_colored_item()
        fmt = table.make_color_map_formatter({"value": ("#112233", None)})
        fmt(item, "value")
        self.assertEqual(item.foreground().color().name().upper(), "#112233")
        self.assertEqual(
            item.background().color().name().upper(),
            "#00FF00",
            "bg was None in the map, so it must survive",
        )


class TestActionColorMapParity(unittest.TestCase):
    """The two forked maps must at least agree on which keys exist.

    ``mayatk``'s reference_manager reads ``widget.ACTION_COLOR_MAP["current"]``.
    That key exists on the table copy and was never added to the tree copy, so
    the same call against a tree widget is a ``KeyError`` -- the fork's cost,
    paid by a consumer that reasonably assumed one contract.
    """

    def test_both_mixins_define_the_same_keys(self):
        from uitk.widgets.tableWidget import CellFormatMixin
        from uitk.widgets.treeWidget import TreeFormatMixin

        self.assertEqual(
            set(CellFormatMixin.ACTION_COLOR_MAP),
            set(TreeFormatMixin.ACTION_COLOR_MAP),
            "CellFormatMixin and TreeFormatMixin action colour maps have "
            "diverged; a consumer cannot rely on either.",
        )

    def test_shared_keys_carry_the_same_values(self):
        from uitk.widgets.tableWidget import CellFormatMixin
        from uitk.widgets.treeWidget import TreeFormatMixin

        for key in set(CellFormatMixin.ACTION_COLOR_MAP) & set(
            TreeFormatMixin.ACTION_COLOR_MAP
        ):
            with self.subTest(key=key):
                self.assertEqual(
                    CellFormatMixin.ACTION_COLOR_MAP[key],
                    TreeFormatMixin.ACTION_COLOR_MAP[key],
                    "'%s' resolves to a different colour per widget type" % key,
                )


if __name__ == "__main__":
    unittest.main()
