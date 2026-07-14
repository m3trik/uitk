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


if __name__ == "__main__":
    unittest.main()
