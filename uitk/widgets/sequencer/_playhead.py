# !/usr/bin/python
# coding=utf-8
"""PlayheadItem — vertical playhead line with frame-number badge."""
from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy import QtWidgets, QtGui, QtCore

from uitk.widgets.sequencer._data import _RULER_HEIGHT

if TYPE_CHECKING:
    from uitk.widgets.sequencer._timeline import TimelineView


class PlayheadItem(QtWidgets.QGraphicsItem):
    """A vertical line with a frame-number badge at the ruler."""

    _COLOR = QtGui.QColor("#E8E84A")
    _BADGE_HEIGHT = 18
    _BADGE_RADIUS = 4
    _POINTER_SIZE = 6  # triangle pointer below badge

    def __init__(self, timeline: "TimelineView"):
        super().__init__()
        self._timeline = timeline
        self._time = 0.0
        self._label = "0"
        self._badge_width = 30.0
        self.setZValue(20)

    @property
    def time(self) -> float:
        return self._time

    @time.setter
    def time(self, value: float):
        self.prepareGeometryChange()  # mark OLD rect before data changes
        self._time = max(0.0, value)
        t = self._time
        self._label = str(int(t)) if t == int(t) else f"{t:.1f}"
        self._update_badge_width()
        self.update()

    def _update_badge_width(self):
        fm = QtGui.QFontMetrics(QtGui.QFont("", 8))
        text_w = (
            fm.horizontalAdvance(self._label)
            if hasattr(fm, "horizontalAdvance")
            else fm.width(self._label)
        )
        self._badge_width = max(text_w + 12, 24)

    def boundingRect(self) -> QtCore.QRectF:
        x = self._timeline.time_to_x(self._time)
        hw = self._badge_width / 2.0 + 2
        return QtCore.QRectF(x - hw, 0, hw * 2, 10000)

    def sync(self):
        self.prepareGeometryChange()
        self.update()

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        x = self._timeline.time_to_x(self._time)
        color = self._COLOR
        bh = self._BADGE_HEIGHT
        bw = self._badge_width
        ptr = self._POINTER_SIZE
        br = self._BADGE_RADIUS

        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Badge (rounded rect centered on x, anchored at ruler top)
        badge_y = (_RULER_HEIGHT - bh - ptr) / 2.0
        badge_rect = QtCore.QRectF(x - bw / 2, badge_y, bw, bh)
        painter.setBrush(color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(badge_rect, br, br)

        # Pointer triangle below badge
        tri_top = badge_y + bh
        tri = QtGui.QPolygonF(
            [
                QtCore.QPointF(x - ptr / 2, tri_top),
                QtCore.QPointF(x + ptr / 2, tri_top),
                QtCore.QPointF(x, tri_top + ptr),
            ]
        )
        painter.drawPolygon(tri)

        # Frame number text (dark on yellow)
        painter.setPen(QtGui.QColor("#1E1E1E"))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(
            badge_rect,
            QtCore.Qt.AlignCenter,
            self._label,
        )

        # Vertical line from pointer tip to bottom
        line_top = tri_top + ptr
        scene_h = self._timeline._scene.height() if self._timeline._scene else 2000
        painter.setPen(QtGui.QPen(color, 1.5))
        painter.drawLine(
            QtCore.QPointF(x, line_top),
            QtCore.QPointF(x, scene_h),
        )
