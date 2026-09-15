# !/usr/bin/python
# coding=utf-8
"""Tests for OverflowIndicator -- arrows at a scroll view's cropped edges.

Run standalone: python -m test.test_overflow_indicator
"""

import unittest

from conftest import QtBaseTestCase, QtWait, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtTest import QTest

from uitk.widgets.overflow_indicator import OverflowIndicator


class _ListCase(QtBaseTestCase):
    """A shown list too short for its rows, and a way to see what the
    overlay paints."""

    def _list(self, rows=40, size=(160, 120)):
        view = self.track_widget(QtWidgets.QListWidget())
        view.addItems([f"row {i}" for i in range(rows)])
        view.setFixedSize(*size)
        view.show()
        QtWait.pump()
        return view

    @staticmethod
    def _rendered(overlay):
        """The overlay's own paint over nothing: alpha 0 wherever it draws
        nothing. (``grab()`` fills the backing pixmap opaque, so it cannot
        tell a painted band from an untouched area.)"""
        img = QtGui.QImage(overlay.size(), QtGui.QImage.Format_ARGB32_Premultiplied)
        img.fill(QtCore.Qt.transparent)
        overlay.render(
            img, QtCore.QPoint(), QtGui.QRegion(), QtWidgets.QWidget.DrawChildren
        )
        return img


class TestOverflowIndicatorAttach(_ListCase):
    def test_attach_returns_the_one_indicator(self):
        view = self._list()
        ind = OverflowIndicator.attach(view)
        self.assertIs(OverflowIndicator.attach(view), ind, "attach is idempotent")
        self.assertIs(OverflowIndicator.of(view), ind)
        self.assertIs(ind.area, view)

    def test_it_is_a_child_of_the_area_not_of_the_viewport(self):
        """``viewport().scroll()`` drags viewport children along with the
        rows; a sibling stacked above the viewport stays put."""
        view = self._list()
        ind = OverflowIndicator.attach(view)
        self.assertIs(ind.parent(), view)
        self.assertIsNot(ind.parent(), view.viewport())

    def test_of_is_none_before_attach(self):
        view = self._list()
        self.assertIsNone(OverflowIndicator.of(view))

    def test_detach_removes_it(self):
        view = self._list()
        ind = OverflowIndicator.attach(view)
        ind.detach()
        QtWait.pump()
        self.assertIsNone(OverflowIndicator.of(view))

    def test_it_is_exported_from_the_package_root(self):
        import uitk

        self.assertIs(uitk.OverflowIndicator, OverflowIndicator)

    def test_survives_a_runtime_loader_build(self):
        """A view built by the runtime loader is reparented after its
        constructor ran, which invalidates any child wrapper taken there
        (the scrollbar's) although the C++ object lives on. An overlay that
        cached one raised inside ``eventFilter`` on ``show()`` -- an access
        violation, not a traceback -- so this test used to take the runner
        down rather than fail."""
        from uitk import examples
        from uitk.examples.example import ExampleSlots
        from uitk.switchboard import Switchboard

        sb = Switchboard(ui_source=examples, slot_source=ExampleSlots)
        ui = self.track_widget(sb.loaded_ui.example)
        tree = ui.findChild(QtWidgets.QTreeWidget)
        ind = OverflowIndicator.of(tree)
        self.assertIsNotNone(ind, "TreeWidget attaches one on construction")
        ui.show()
        QtWait.pump()
        try:
            ind.refresh()
            self.assertEqual(ind.geometry(), tree.viewport().geometry())
        finally:
            ui.close()


class TestOverflowIndicatorEdges(_ListCase):
    def test_only_the_bottom_edge_while_the_first_row_shows(self):
        view = self._list()
        ind = OverflowIndicator.attach(view)
        self.assertEqual(ind.shown_edges, ("bottom",))
        self.assertTrue(ind.isVisible())

    def test_both_edges_mid_scroll(self):
        view = self._list()
        ind = OverflowIndicator.attach(view)
        bar = view.verticalScrollBar()
        bar.setValue((bar.minimum() + bar.maximum()) // 2)
        self.assertEqual(ind.shown_edges, ("top", "bottom"))

    def test_only_the_top_edge_at_the_end(self):
        view = self._list()
        ind = OverflowIndicator.attach(view)
        view.scrollToBottom()
        self.assertEqual(ind.shown_edges, ("top",))

    def test_hidden_while_everything_fits(self):
        view = self._list(rows=3)
        ind = OverflowIndicator.attach(view)
        self.assertEqual(ind.shown_edges, ())
        self.assertFalse(ind.isVisible())

    def test_follows_the_range_as_rows_come_and_go(self):
        view = self._list(rows=3)
        ind = OverflowIndicator.attach(view)
        view.addItems([f"more {i}" for i in range(40)])
        QtWait.until(
            lambda: ind.shown_edges == ("bottom",),
            "adding rows never showed the bottom arrow",
        )
        view.clear()
        QtWait.until(
            lambda: ind.shown_edges == () and not ind.isVisible(),
            "clearing the rows never hid the arrows",
        )

    def test_hidden_rows_do_not_count(self):
        """It reads the scroll RANGE, not the row count: 40 rows of which
        37 are hidden fit, so nothing is cropped."""
        view = self._list(rows=40)
        ind = OverflowIndicator.attach(view)
        for row in range(3, 40):
            view.setRowHidden(row, True)
        QtWait.until(
            lambda: ind.shown_edges == (), "hidden rows still counted as overflow"
        )


class TestOverflowIndicatorGeometry(_ListCase):
    def test_covers_the_viewport(self):
        view = self._list()
        ind = OverflowIndicator.attach(view)
        self.assertEqual(ind.geometry(), view.viewport().geometry())

    def test_follows_the_viewport_when_the_area_resizes(self):
        view = self._list()
        ind = OverflowIndicator.attach(view)
        view.setFixedSize(220, 80)
        QtWait.pump()
        self.assertEqual(ind.geometry(), view.viewport().geometry())
        self.assertLess(ind.width(), view.width(), "the bar's column is not covered")

    def test_stays_put_across_a_scroll(self):
        view = self._list()
        ind = OverflowIndicator.attach(view)
        before = ind.geometry()
        bar = view.verticalScrollBar()
        bar.setValue(bar.maximum() // 2)
        QtWait.pump()
        self.assertEqual(ind.geometry(), before)
        self.assertEqual(ind.geometry(), view.viewport().geometry())


class TestOverflowIndicatorPaint(_ListCase):
    def test_paints_only_the_edges_it_marks(self):
        view = self._list()
        ind = OverflowIndicator.attach(view)
        img = self._rendered(ind)
        cx, h = img.width() // 2, img.height()
        self.assertEqual(img.pixelColor(cx, h // 2).alpha(), 0, "middle untouched")
        self.assertGreater(img.pixelColor(cx, h - 1).alpha(), 0, "bottom band")
        self.assertEqual(img.pixelColor(cx, 0).alpha(), 0, "no top band yet")
        view.scrollToBottom()
        img = self._rendered(ind)
        self.assertGreater(img.pixelColor(cx, 0).alpha(), 0, "top band once cropped")
        self.assertEqual(img.pixelColor(cx, h - 1).alpha(), 0, "no bottom band at end")

    def test_the_arrow_is_the_text_colour_over_a_band_of_the_base_colour(self):
        view = self._list()
        ind = OverflowIndicator.attach(view)
        img = self._rendered(ind)
        band, (arrow_w, _arrow_h) = ind._metrics()
        cx, h = img.width() // 2, img.height()
        mid = int(h - band / 2)
        arrow = img.pixelColor(cx, mid)
        beside = img.pixelColor(int(cx + arrow_w * 2), mid)
        text = view.palette().color(QtGui.QPalette.Text)
        base = view.palette().color(QtGui.QPalette.Base)
        self.assertLess(
            abs(arrow.red() - text.red()), 40, "arrow is not the text colour"
        )
        self.assertLess(
            abs(beside.red() - base.red()), 40, "band is not the base colour"
        )
        self.assertNotEqual(arrow.rgb(), beside.rgb())


class TestOverflowIndicatorInput(_ListCase):
    def test_a_click_through_the_band_reaches_the_row_beneath(self):
        view = self._list()
        ind = OverflowIndicator.attach(view)
        self.assertTrue(ind.isVisible())
        in_band = QtCore.QPoint(20, view.viewport().height() - 3)
        index = view.indexAt(in_band)
        self.assertTrue(index.isValid(), "fixture: a row must sit under the band")
        self.assertNotEqual(view.currentRow(), index.row())
        pos = view.viewport().mapTo(view, in_band)
        QTest.mouseClick(
            view.windowHandle(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pos
        )
        QtWait.until(
            lambda: view.currentRow() == index.row(),
            "the click did not reach the row under the band",
        )


if __name__ == "__main__":
    unittest.main()
