# !/usr/bin/python
# coding=utf-8
"""Tests for TableWidget display-only column truncation.

The contract the consumers (mayatk / blendertk Texture Path Editor) depend on:
truncation is a paint-time transform only — the item keeps the full value, so
cell edits, tooltips, formatters and the commands reading ``item.text()`` are
never handed a shortened path.

Run standalone: python -m test.test_table_widget_truncation
"""

import unittest

from qtpy import QtWidgets

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

LONG = "O:/Cloud/Projects/jets/c130j/sourceimages/textures/c130j_body_DIFF.png"


class _TruncationTestCase(QtBaseTestCase):
    def _table(self):
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(TableWidget())
        table.add(
            [["shader1", LONG], ["shader2", "short.png"]],
            headers=["Shader", "Path"],
        )
        return table

    def _paint_option(self, table, row, col):
        """The style option the item delegate would paint a cell with."""
        option = QtWidgets.QStyleOptionViewItem()
        index = table.model().index(row, col)
        table.itemDelegate().initStyleOption(option, index)
        return option

    def _painted_text(self, table, row, col):
        """The text the item delegate would paint for a cell."""
        return self._paint_option(table, row, col).text


class TestColumnTruncationData(_TruncationTestCase):
    """Truncation must never reach the item's data."""

    def test_item_text_keeps_the_full_value(self):
        table = self._table()
        table.set_column_truncation(1, length=24)
        self.assertEqual(table.item(0, 1).text(), LONG)

    def test_truncated_column_text_shortens_only_configured_columns(self):
        table = self._table()
        table.set_column_truncation(1, length=24)
        self.assertEqual(table.truncated_column_text(0, LONG), LONG)
        self.assertLess(len(table.truncated_column_text(1, LONG)), len(LONG))

    def test_start_mode_keeps_the_filename(self):
        table = self._table()
        table.set_column_truncation(1, length=24, mode="start")
        self.assertTrue(
            table.truncated_column_text(1, LONG).endswith("c130j_body_DIFF.png")
        )

    def test_path_mode_keeps_whole_components_at_both_ends(self):
        """The mode the Texture Path Editor uses: drive+dirs in, filename out."""
        table = self._table()
        table.set_column_truncation(1, length=48, mode="path", insert="…")
        shown = table.truncated_column_text(1, LONG)
        self.assertEqual(shown, "O:/Cloud/Projects/…/textures/c130j_body_DIFF.png")
        self.assertLessEqual(len(shown), 48)

    def test_value_shorter_than_length_is_untouched(self):
        table = self._table()
        table.set_column_truncation(1, length=24)
        self.assertEqual(table.truncated_column_text(1, "short.png"), "short.png")


class TestColumnTruncationConfig(_TruncationTestCase):
    """set/clear/query round-trip."""

    def test_spec_is_queryable(self):
        table = self._table()
        table.set_column_truncation(1, length=24, mode="middle", insert="…")
        self.assertEqual(table.column_truncation(1), (24, "middle", "…"))

    def test_none_length_clears(self):
        table = self._table()
        table.set_column_truncation(1, length=24)
        table.set_column_truncation(1, length=None)
        self.assertIsNone(table.column_truncation(1))
        self.assertEqual(table.truncated_column_text(1, LONG), LONG)

    def test_header_text_resolves_to_the_column(self):
        table = self._table()
        table.set_column_truncation("Path", length=24)
        self.assertEqual(table.column_truncation(1), (24, "start", ".."))

    def test_unset_column_returns_none(self):
        table = self._table()
        self.assertIsNone(table.column_truncation(1))


class TestColumnTruncationPaint(_TruncationTestCase):
    """The delegate is what actually shortens the display."""

    def test_delegate_paints_the_truncated_form(self):
        table = self._table()
        table.set_column_truncation(1, length=24)
        painted = self._painted_text(table, 0, 1)
        self.assertNotEqual(painted, LONG)
        self.assertEqual(painted, table.truncated_column_text(1, LONG))

    def test_other_columns_paint_verbatim(self):
        table = self._table()
        table.set_column_truncation(1, length=24)
        self.assertEqual(self._painted_text(table, 0, 0), "shader1")

    def test_no_truncation_paints_verbatim(self):
        table = self._table()
        self.assertEqual(self._painted_text(table, 0, 1), LONG)


class TestColumnTruncationElide(_TruncationTestCase):
    """The width elide must trim the same end the truncation mode does.

    A column too narrow for even the truncated text is elided by the style on
    top of the truncation; with Qt's default ElideRight a path shortened *to*
    its filename would lose that filename again.
    """

    def _elide(self, mode):
        table = self._table()
        table.set_column_truncation(1, length=24, mode=mode)
        return self._paint_option(table, 0, 1).textElideMode

    def test_start_mode_elides_left(self):
        from qtpy import QtCore

        self.assertEqual(self._elide("start"), QtCore.Qt.ElideLeft)

    def test_path_mode_elides_middle(self):
        from qtpy import QtCore

        self.assertEqual(self._elide("path"), QtCore.Qt.ElideMiddle)

    def test_middle_mode_elides_middle(self):
        from qtpy import QtCore

        self.assertEqual(self._elide("middle"), QtCore.Qt.ElideMiddle)

    def test_end_mode_elides_right(self):
        from qtpy import QtCore

        self.assertEqual(self._elide("end"), QtCore.Qt.ElideRight)

    def test_untruncated_column_is_left_alone(self):
        """Untouched, so the mode the view stamps on the option still governs."""
        table = self._table()
        table.set_column_truncation(1, length=24, mode="start")
        untouched = QtWidgets.QStyleOptionViewItem().textElideMode
        self.assertEqual(self._paint_option(table, 0, 0).textElideMode, untouched)


if __name__ == "__main__":
    unittest.main()
