# !/usr/bin/python
# coding=utf-8
"""Regression tests for TableWidget.add() signal-block lifecycle.

Run standalone: python -m test.test_table_widget_add
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()


class TestTableAddSignalRestore(QtBaseTestCase):
    """add() must restore the prior signal-block state even if population raises.

    Regression: blockSignals(True)/blockSignals(False) sat inside a try whose
    finally only restored setUpdatesEnabled — an exception mid-populate skipped
    the unblock, leaving the table permanently signal-dead.
    """

    def test_signals_restored_after_exception(self):
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(TableWidget())
        self.assertFalse(table.signalsBlocked())

        class _Boom:
            def __str__(self):
                raise ValueError("boom during populate")

        with self.assertRaises(ValueError):
            table.add([_Boom()])

        self.assertFalse(
            table.signalsBlocked(),
            "signals must be restored after a mid-populate exception",
        )

    def test_signals_restored_after_normal_add(self):
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(TableWidget())
        table.add(["a", "b", "c"])
        self.assertFalse(table.signalsBlocked())


class TestTableAddEmptyDict(QtBaseTestCase):
    """add({}) must yield an empty table, not raise.

    Regression: an empty dict satisfies the dict-of-lists guard (all() is
    vacuously True over empty .values()), so it entered that branch and
    max(len(col) for col in {}.values()) raised ValueError on the empty
    generator. Fixed with a default=0 so an empty dict produces an empty
    table like the other empty-input paths.
    """

    def test_empty_dict_yields_empty_table(self):
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(TableWidget())
        table.add({})  # must not raise
        self.assertEqual(table.rowCount(), 0)
        self.assertEqual(table.columnCount(), 0)


class TestHeaderFormatterColumnRef(QtBaseTestCase):
    """set_header_formatter must key by resolved header text.

    Regression: it stored the formatter under the raw ``header`` argument, but
    _get_formatters looks it up by ``self._header(col)`` (always the header
    *text*). An integer column ref (set_header_formatter(1, fmt)) was therefore
    stored under the int key 1 and never matched the text-keyed lookup, so the
    formatter silently never ran.
    """

    def _formatter_calls(self, table, column_ref):
        seen = []
        table.set_header_formatter(
            column_ref, lambda item, value, row, col, tbl: seen.append(value)
        )
        table.apply_formatting()
        return seen

    def test_int_column_ref_formatter_is_applied(self):
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(TableWidget())
        table.add([["a", "1"], ["b", "2"]], headers=["Name", "Value"])

        # Reference the second column by integer index.
        seen = self._formatter_calls(table, 1)
        self.assertEqual(sorted(seen), ["1", "2"])

    def test_text_column_ref_formatter_still_applied(self):
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(TableWidget())
        table.add([["a", "1"], ["b", "2"]], headers=["Name", "Value"])

        # Text ref must keep working (unchanged behavior).
        seen = self._formatter_calls(table, "Value")
        self.assertEqual(sorted(seen), ["1", "2"])


class TestTableWidgetSignalSurface(QtBaseTestCase):
    """Pin the real signal surface.

    Regression: the module ``__main__`` demo connected to on_cell_edited /
    on_row_selected / on_context_menu, none of which exist on TableWidget, so
    running the module raised AttributeError. The real signals are the
    cellScrub*/cellWheelScrolled family.
    """

    def test_real_scrub_and_wheel_signals_present(self):
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(TableWidget())
        for name in (
            "cellScrubStarted",
            "cellScrubMoved",
            "cellScrubFinished",
            "cellWheelScrolled",
        ):
            self.assertTrue(hasattr(table, name), f"missing real signal {name!r}")

    def test_stale_demo_signals_absent(self):
        from uitk.widgets.tableWidget import TableWidget

        table = self.track_widget(TableWidget())
        for name in ("on_cell_edited", "on_row_selected", "on_context_menu"):
            self.assertFalse(
                hasattr(table, name), f"stale demo signal {name!r} should not exist"
            )


if __name__ == "__main__":
    unittest.main()
