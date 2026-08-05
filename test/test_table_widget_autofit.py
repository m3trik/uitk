# !/usr/bin/python
# coding=utf-8
"""Tests for TableWidget's auto-fit-window sizing.

Regression: consumers (the Maya / Blender Channels panels) grew their window
to the full content height unconditionally, so a long attribute list produced
a window taller than the screen with the bottom rows unreachable — and the
measurement double-counted the frame, the horizontal header and the
scrollbars, leaving dead space below the last row.

Run standalone: python -m test.test_table_widget_autofit
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()


class TestComputeAutofitSize(QtBaseTestCase):
    """Pure arithmetic — the sizing policy, independent of any live widget."""

    def setUp(self):
        super().setUp()
        from uitk.widgets.tableWidget import TableWidget

        self.fit = TableWidget.compute_autofit_size

    def test_content_smaller_than_cap_fits_exactly(self):
        self.assertEqual(
            self.fit(
                content=(200, 300),
                chrome=(10, 20),
                scrollbar=(14, 14),
                maximum=(900, 900),
                minimum=(0, 0),
            ),
            (210, 320),
        )

    def test_height_cap_clamps_and_widens_for_the_scrollbar(self):
        """Clipping rows brings in the vscrollbar, which eats column width."""
        self.assertEqual(
            self.fit(
                content=(200, 5000),
                chrome=(10, 20),
                scrollbar=(14, 14),
                maximum=(900, 600),
                minimum=(0, 0),
            ),
            (224, 600),
        )

    def test_width_cap_clamps_and_grows_for_the_scrollbar(self):
        self.assertEqual(
            self.fit(
                content=(5000, 300),
                chrome=(10, 20),
                scrollbar=(14, 14),
                maximum=(600, 900),
                minimum=(0, 0),
            ),
            (600, 334),
        )

    def test_both_capped_stays_within_the_ceiling(self):
        self.assertEqual(
            self.fit(
                content=(5000, 5000),
                chrome=(10, 20),
                scrollbar=(14, 14),
                maximum=(600, 400),
                minimum=(0, 0),
            ),
            (600, 400),
        )

    def test_minimum_wins_over_maximum(self):
        self.assertEqual(
            self.fit(
                content=(10, 10),
                chrome=(0, 0),
                scrollbar=(14, 14),
                maximum=(100, 100),
                minimum=(300, 200),
            ),
            (300, 200),
        )

    def test_chrome_is_added_exactly_once(self):
        """Chrome is measured, not derived — it must not be double-counted."""
        base = self.fit(
            content=(100, 100),
            chrome=(0, 0),
            scrollbar=(0, 0),
            maximum=(9999, 9999),
            minimum=(0, 0),
        )
        with_chrome = self.fit(
            content=(100, 100),
            chrome=(37, 41),
            scrollbar=(0, 0),
            maximum=(9999, 9999),
            minimum=(0, 0),
        )
        self.assertEqual(
            (with_chrome[0] - base[0], with_chrome[1] - base[1]), (37, 41)
        )


class TestChromeMeasurement(QtBaseTestCase):
    """The viewport-based chrome measurement, against a real widget.

    ``win - viewport`` already contains the frame, the table's headers (they
    live in the viewport margins, not the viewport) and the visible
    scrollbars.  These pin that, so a future "helpful" re-addition of
    ``frameWidth * 2 + header`` reintroduces a measurable failure.
    """

    def _table(self, rows=60, cols=3):
        from qtpy import QtWidgets
        from uitk.widgets.tableWidget import TableWidget

        win = self.track_widget(QtWidgets.QMainWindow())
        cw = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(cw)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)
        table = TableWidget()
        table.setRowCount(rows)
        table.setColumnCount(cols)
        for r in range(rows):
            for c in range(cols):
                table.setItem(r, c, QtWidgets.QTableWidgetItem(f"cell{r}{c}"))
        lay.addWidget(table)
        win.setCentralWidget(cw)
        win.resize(400, 300)
        win.show()
        app.processEvents()
        return win, table

    def test_chrome_height_already_includes_the_horizontal_header(self):
        win, table = self._table()
        table.horizontalHeader().setVisible(True)
        app.processEvents()

        chrome_h = win.height() - table.viewport().height()
        hhdr_h = table.horizontalHeader().height()
        self.assertGreater(hhdr_h, 0)
        self.assertGreaterEqual(
            chrome_h,
            hhdr_h,
            "win - viewport must already account for the horizontal header",
        )

    def test_chrome_width_already_includes_a_visible_scrollbar(self):
        win, table = self._table(rows=200)
        app.processEvents()

        vbar = table.verticalScrollBar()
        self.assertTrue(vbar.isVisible(), "200 rows in a 300px window must scroll")
        chrome_w = win.width() - table.viewport().width()
        self.assertGreaterEqual(
            chrome_w,
            vbar.width(),
            "win - viewport must already account for the vertical scrollbar",
        )


class TestFitWindowToContents(QtBaseTestCase):
    """End-to-end sizing against a live window."""

    def _table(self, rows):
        from qtpy import QtWidgets
        from uitk.widgets.tableWidget import TableWidget

        win = self.track_widget(QtWidgets.QMainWindow())
        cw = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(cw)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        table = TableWidget()
        table.setRowCount(rows)
        table.setColumnCount(2)
        for r in range(rows):
            for c in range(2):
                table.setItem(r, c, QtWidgets.QTableWidgetItem(f"r{r}c{c}"))
        lay.addWidget(table)
        win.setCentralWidget(cw)
        win.resize(400, 300)
        win.show()
        app.processEvents()
        return win, table

    def test_short_content_shrinks_the_window_without_dead_space(self):
        win, table = self._table(rows=4)
        table.fit_window_to_contents(defer=False)
        app.processEvents()

        rows_h = sum(table.rowHeight(r) for r in range(table.rowCount()))
        chrome_h = win.height() - table.viewport().height()
        # Every window pixel is either a row or measured chrome.
        self.assertEqual(win.height(), rows_h + chrome_h)
        self.assertFalse(table.verticalScrollBar().isVisible())

    def test_long_content_is_capped_and_scrolls(self):
        win, table = self._table(rows=400)
        # An explicit, screen-independent ceiling keeps this deterministic
        # across the CI display and a developer's monitor.
        cap = table.max_autofit_size()
        table.fit_window_to_contents(defer=False)
        app.processEvents()

        rows_h = sum(table.rowHeight(r) for r in range(table.rowCount()))
        self.assertGreater(rows_h, cap[1], "fixture must overflow the cap")
        self.assertLessEqual(win.height(), cap[1])
        self.assertTrue(
            table.verticalScrollBar().isVisible(),
            "a capped window must hand overflow to the scrollbar",
        )
        self.assertGreater(table.verticalScrollBar().maximum(), 0)

    def test_capped_window_widens_for_the_scrollbar(self):
        """The scrollbar the cap brings in must not eat column width."""
        short_win, short_tbl = self._table(rows=2)
        short_tbl.fit_window_to_contents(defer=False)
        app.processEvents()
        narrow = short_win.width()

        tall_win, tall_tbl = self._table(rows=400)
        tall_tbl.fit_window_to_contents(defer=False)
        app.processEvents()

        self.assertGreater(
            tall_win.width(),
            narrow,
            "the capped window must grow by the vertical scrollbar's width",
        )

    def test_deferred_call_is_safe_on_a_destroyed_table(self):
        """The deferred fit must not raise once its widget is gone."""
        win, table = self._table(rows=10)
        table.fit_window_to_contents()  # deferred
        win.close()
        win.deleteLater()
        app.processEvents()
        app.processEvents()
        app.processEvents()  # let both singleShot ticks drain


if __name__ == "__main__":
    unittest.main()
