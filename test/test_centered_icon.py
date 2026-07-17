# !/usr/bin/python
# coding=utf-8
"""Tests for the shared centered-icon delegate primitives.

``fill_cell_background`` and ``paint_centered_icon`` back both
``CenteredIconActionDelegate`` (shortcut editor) and
``table_actions._CenteredIconDelegate`` (TableWidget action columns), so the
per-state background tint + centered icon render the same way everywhere.
"""
import unittest
from unittest import mock

from qtpy import QtGui, QtCore
from conftest import setup_qt_application

from uitk.widgets.delegates.centered_icon import (
    fill_cell_background,
    paint_centered_icon,
    ICON_OPACITY_ROLE,
)

app = setup_qt_application()


class TestFillCellBackground(unittest.TestCase):
    """A delegate must paint the item's BackgroundRole tint itself — the
    stylesheet style drops it, silently losing per-state colour cues."""

    def _index(self, brush):
        idx = mock.Mock()
        idx.data.return_value = brush
        return idx

    def test_paints_a_set_colour_brush(self):
        painter = mock.Mock()
        rect = QtCore.QRect(0, 0, 10, 10)
        idx = self._index(QtGui.QBrush(QtGui.QColor("#3a5a3a")))
        self.assertTrue(fill_cell_background(painter, rect, idx))
        painter.fillRect.assert_called_once()

    def test_skips_unset_background(self):
        painter = mock.Mock()
        rect = QtCore.QRect(0, 0, 10, 10)
        self.assertFalse(fill_cell_background(painter, rect, self._index(None)))
        painter.fillRect.assert_not_called()

    def test_skips_nobrush(self):
        """A default (NoBrush) brush — what an item with no background yields —
        must not paint an opaque black fill over the cell."""
        painter = mock.Mock()
        rect = QtCore.QRect(0, 0, 10, 10)
        self.assertFalse(
            fill_cell_background(painter, rect, self._index(QtGui.QBrush()))
        )
        painter.fillRect.assert_not_called()


class TestPaintCenteredIcon(unittest.TestCase):
    def test_null_icon_is_noop(self):
        painter = mock.Mock()
        paint_centered_icon(
            painter, QtGui.QIcon(), QtCore.QRect(0, 0, 22, 22), QtCore.QSize(14, 14)
        )
        painter.drawPixmap.assert_not_called()

    def test_dim_opacity_wraps_draw(self):
        """A sub-1.0 opacity saves/sets/restores the painter around the draw."""
        from uitk.managers.icon_manager import IconManager

        icon = IconManager.get("undo", size=(14, 14))
        painter = mock.Mock()
        paint_centered_icon(
            painter,
            icon,
            QtCore.QRect(0, 0, 22, 22),
            QtCore.QSize(14, 14),
            opacity=0.4,
        )
        painter.setOpacity.assert_called_once_with(0.4)
        painter.save.assert_called_once()
        painter.restore.assert_called_once()
        painter.drawPixmap.assert_called_once()

    def test_full_opacity_no_save(self):
        from uitk.managers.icon_manager import IconManager

        icon = IconManager.get("undo", size=(14, 14))
        painter = mock.Mock()
        paint_centered_icon(
            painter, icon, QtCore.QRect(0, 0, 22, 22), QtCore.QSize(14, 14)
        )
        painter.setOpacity.assert_not_called()
        painter.drawPixmap.assert_called_once()


if __name__ == "__main__":
    unittest.main()
