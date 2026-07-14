# !/usr/bin/python
# coding=utf-8
"""Regression: ``Region.visible_on_mouse_over`` must track its own
connection state.

Bug (live report, Blender/PySide6 6.10.1): every ``Region`` construction
flooded the host console with two ``libpyside: Failed to disconnect``
RuntimeWarnings — ``__init__`` assigns the property its default ``False``,
and the setter unconditionally tried to disconnect signals that were never
connected. PySide2 raises ``RuntimeError`` there (silenced by the existing
``except``); PySide6 6.10 instead *emits a warning per call* and the except
silences nothing. The marking-menu overlay builds many Regions per page, so
a single DCC launch produced hundreds of warning lines. The same
by-current-value logic also double-connected on a repeated ``True`` (slots
fired twice per enter/leave).

Fix: the setter tracks ``_mouse_over_connected`` and connects/disconnects
only on a real state change.
"""
import unittest
import warnings

from qtpy import QtWidgets, QtCore, QtGui

from conftest import QtBaseTestCase
from uitk.widgets.region import Region


class TestRegionMouseOverConnections(QtBaseTestCase):
    def _make_region(self, **kwargs):
        region = Region(None, **kwargs)
        self.track_widget(region)
        return region

    def test_construction_emits_no_disconnect_warning(self):
        """Default ``visible_on_mouse_over=False`` must not attempt a
        disconnect (PySide6 6.10 emits a RuntimeWarning per attempt)."""
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            self._make_region()  # would raise pre-fix on PySide6 6.10

    def test_repeated_false_emits_no_disconnect_warning(self):
        region = self._make_region()
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            region.visible_on_mouse_over = False

    def test_repeated_true_does_not_double_connect(self):
        """A second ``True`` must not stack a duplicate connection. Detected
        through behavior: with a stacked duplicate, ONE opt-out disconnect
        leaves a live connection behind and enter still shows the child."""
        region = self._make_region()
        child = QtWidgets.QWidget(region)
        region.visible_on_mouse_over = True
        region.visible_on_mouse_over = True
        self.assertTrue(region._mouse_over_connected)

        region.visible_on_mouse_over = False
        self.assertFalse(region._mouse_over_connected)
        region.on_enter.emit()
        self.assertFalse(
            child.isVisible(),
            "a single opt-out must fully disconnect — a shown child means "
            "the repeated True stacked a duplicate connection",
        )

    def test_toggle_cycle_connects_and_disconnects(self):
        region = self._make_region()
        child = QtWidgets.QWidget(region)
        region.show()
        region.visible_on_mouse_over = True
        self.assertFalse(child.isVisible(), "children start hidden")
        region.on_enter.emit()
        self.assertTrue(child.isVisible(), "enter shows children while on")
        region.visible_on_mouse_over = False
        child.hide()
        region.on_enter.emit()
        self.assertFalse(child.isVisible(), "enter is inert after opt-out")


class TestRegionShapeMask(QtBaseTestCase):
    """Regression: the ``shape`` region must be applied as a widget mask.

    Bug: ``__init__`` computed ``self.region = QRegion(rect, shape)`` but never
    called ``setMask``, so despite the documented elliptical shape the widget
    stayed rectangular for hit-testing — ``enterEvent`` / ``on_enter`` fired in
    the corners that the ellipse excludes. Fix: apply the region as the mask in
    ``__init__`` and re-apply it on show / resize.
    """

    def _make_region(self, size=(50, 50), **kwargs):
        region = Region(None, size=size, **kwargs)
        self.track_widget(region)
        return region

    def test_ellipse_mask_is_applied(self):
        """A mask must be set (was never applied at all)."""
        region = self._make_region()
        mask = region.mask()
        self.assertFalse(
            mask.isEmpty(), "no mask applied — hit-testing uses the full rect"
        )

    def test_ellipse_mask_excludes_corners(self):
        """The inscribed ellipse must exclude the bounding-box corners."""
        region = self._make_region(size=(50, 50))
        mask = region.mask()
        self.assertFalse(mask.contains(QtCore.QPoint(0, 0)), "top-left corner masked in")
        self.assertFalse(
            mask.contains(QtCore.QPoint(49, 49)), "bottom-right corner masked in"
        )
        self.assertTrue(
            mask.contains(QtCore.QPoint(25, 25)), "center must be inside the ellipse"
        )

    def test_rectangle_shape_keeps_corners(self):
        """A Rectangle shape masks nothing away (corners stay hittable)."""
        region = self._make_region(size=(40, 40), shape=QtGui.QRegion.Rectangle)
        mask = region.mask()
        self.assertTrue(mask.contains(QtCore.QPoint(0, 0)))
        self.assertTrue(mask.contains(QtCore.QPoint(39, 39)))

    def test_mask_reapplied_on_resize(self):
        """Resizing the region rebuilds the mask for the new size."""
        region = self._make_region(size=(50, 50))
        region.show()
        QtWidgets.QApplication.processEvents()
        region.resize(80, 80)
        QtWidgets.QApplication.processEvents()
        mask = region.mask()
        self.assertFalse(mask.isEmpty())
        # New-size corner excluded, new-size center included.
        self.assertFalse(mask.contains(QtCore.QPoint(0, 0)))
        self.assertTrue(mask.contains(QtCore.QPoint(40, 40)))


if __name__ == "__main__":
    unittest.main()
