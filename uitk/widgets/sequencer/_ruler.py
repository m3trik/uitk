# !/usr/bin/python
# coding=utf-8
"""Ruler and shot-lane items for the timeline header area."""
from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy import QtWidgets, QtGui, QtCore

if TYPE_CHECKING:
    from uitk.widgets.sequencer._timeline import TimelineView

from uitk.widgets.sequencer._data import _RULER_HEIGHT, _SHOT_LANE_HEIGHT

# -- local constants -------------------------------------------------------
_SHOT_BLOCK_RADIUS = 3
_SHOT_BLOCK_ACTIVE_COLOR = "#5B8BD4"
_SHOT_BLOCK_INACTIVE_COLOR = "#888888"
_SHOT_GAP_COLOR = "#3A3A3A"


# ---------------------------------------------------------------------------
#  ShotLaneItem
# ---------------------------------------------------------------------------


class ShotLaneItem(QtWidgets.QGraphicsItem):
    """Renders coloured shot blocks in a thin lane below the ruler.

    Always visible regardless of whether any tracks exist, giving the
    user a persistent overview of the shot layout.
    """

    def __init__(self, timeline: "TimelineView"):
        super().__init__()
        self._timeline = timeline
        self._blocks: list = []  # [{name, start, end, active}, ...]
        self.setZValue(9)  # above overlays, just below ruler (10)
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)

    # -- data --------------------------------------------------------------

    def set_blocks(self, blocks: list) -> None:
        self._blocks = list(blocks)
        self.prepareGeometryChange()
        self.update()

    def clear_blocks(self) -> None:
        self._blocks.clear()
        self.prepareGeometryChange()
        self.update()

    # -- interaction --------------------------------------------------------

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        x = event.pos().x()
        time = self._timeline.x_to_time(x)
        for blk in self._blocks:
            if blk["start"] <= time <= blk["end"]:
                sq = self._timeline.parent_sequencer
                if sq is not None:
                    sq.shot_block_clicked.emit(blk["name"])
                event.accept()
                return
        event.ignore()

    # -- geometry ----------------------------------------------------------

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(0, 0, 100000, _SHOT_LANE_HEIGHT)

    # -- paint -------------------------------------------------------------

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        if not self._blocks:
            return

        tl = self._timeline
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)

        vp_rect = tl.mapToScene(tl.viewport().rect()).boundingRect()
        vis_left, vis_right = vp_rect.left(), vp_rect.right()

        # Dark background
        painter.fillRect(
            QtCore.QRectF(vis_left, 0, vis_right - vis_left, _SHOT_LANE_HEIGHT),
            QtGui.QColor("#252525"),
        )

        # Sort blocks by start time for gap drawing
        sorted_blocks = sorted(self._blocks, key=lambda b: b["start"])

        # Draw gaps between shots
        gap_color = QtGui.QColor(_SHOT_GAP_COLOR)
        for i in range(len(sorted_blocks) - 1):
            gap_x0 = tl.time_to_x(sorted_blocks[i]["end"])
            gap_x1 = tl.time_to_x(sorted_blocks[i + 1]["start"])
            if gap_x1 - gap_x0 > 1:
                r = QtCore.QRectF(gap_x0, 2, gap_x1 - gap_x0, _SHOT_LANE_HEIGHT - 4)
                # Diagonal hatching
                painter.save()
                painter.setClipRect(r)
                painter.fillRect(r, gap_color)
                pen = QtGui.QPen(QtGui.QColor("#4A4A4A"), 1)
                painter.setPen(pen)
                spacing = 8
                x0, y0, w, h = r.x(), r.y(), r.width(), r.height()
                d = int(w + h)
                for j in range(-int(h), d, spacing):
                    painter.drawLine(
                        QtCore.QPointF(x0 + j, y0 + h),
                        QtCore.QPointF(x0 + j + h, y0),
                    )
                painter.restore()

        # Draw shot blocks
        font = painter.font()
        font.setPixelSize(9)
        painter.setFont(font)

        for blk in sorted_blocks:
            x0 = tl.time_to_x(blk["start"])
            x1 = tl.time_to_x(blk["end"])
            if x1 < vis_left or x0 > vis_right:
                continue  # off-screen
            is_active = blk.get("active", False)
            color = QtGui.QColor(
                _SHOT_BLOCK_ACTIVE_COLOR if is_active else _SHOT_BLOCK_INACTIVE_COLOR
            )
            alpha = 180 if is_active else 100
            color.setAlpha(alpha)
            r = QtCore.QRectF(x0, 1, x1 - x0, _SHOT_LANE_HEIGHT - 2)
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(r, _SHOT_BLOCK_RADIUS, _SHOT_BLOCK_RADIUS)

            # Shot name label
            if r.width() > 20:
                text_color = QtGui.QColor("#FFFFFF" if is_active else "#BBBBBB")
                painter.setPen(text_color)
                label_rect = r.adjusted(4, 0, -4, 0)
                painter.drawText(
                    label_rect,
                    QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                    blk.get("name", ""),
                )


# ---------------------------------------------------------------------------
#  RulerItem
# ---------------------------------------------------------------------------


class RulerItem(QtWidgets.QGraphicsItem):
    """Draws the frame-number ruler at the top of the timeline.

    Also renders coloured shot-block indicators in the bottom strip
    of the ruler so the user always sees the shot layout.
    """

    _BLOCK_STRIP_H = 6  # height of the shot indicator strip at ruler bottom

    def __init__(self, timeline: "TimelineView"):
        super().__init__()
        self._timeline = timeline
        self._shot_blocks: list = []  # [{name, start, end, active}, ...]
        self.setZValue(10)

    # -- shot block data ---------------------------------------------------

    def set_shot_blocks(self, blocks: list) -> None:
        self._shot_blocks = list(blocks)
        self.update()

    def clear_shot_blocks(self) -> None:
        self._shot_blocks.clear()
        self.update()

    def boundingRect(self):
        return QtCore.QRectF(0, 0, 100000, _RULER_HEIGHT)

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        tl = self._timeline
        ppu = tl.pixels_per_unit

        vp_rect = tl.mapToScene(tl.viewport().rect()).boundingRect()
        vis_left = vp_rect.left()
        vis_right = vp_rect.right()

        # Background
        painter.setBrush(QtGui.QColor("#2B2B2B"))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(
            QtCore.QRectF(vis_left, 0, vis_right - vis_left, _RULER_HEIGHT)
        )

        if ppu <= 0:
            return

        raw = 60.0 / ppu
        interval = max(1, self._nice_interval(raw))

        painter.setPen(QtGui.QColor("#999999"))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        t_start = tl.x_to_time(vis_left)
        t_end = tl.x_to_time(vis_right)

        t = int(t_start / interval) * interval
        while t <= t_end:
            x = tl.time_to_x(t)
            painter.drawLine(
                QtCore.QPointF(x, _RULER_HEIGHT - 8),
                QtCore.QPointF(x, _RULER_HEIGHT),
            )
            painter.drawText(
                QtCore.QPointF(x + 3, _RULER_HEIGHT - 10),
                str(int(t)),
            )
            t += interval

        # -- shot name labels at bottom of ruler ----------------------------
        if self._shot_blocks:
            sorted_blocks = sorted(self._shot_blocks, key=lambda b: b["start"])

            label_font = QtGui.QFont(painter.font())
            label_font.setPointSize(7)
            label_font.setBold(True)

            for blk in sorted_blocks:
                bx0 = tl.time_to_x(blk["start"])
                bx1 = tl.time_to_x(blk["end"])
                if bx1 < vis_left or bx0 > vis_right:
                    continue
                name = blk.get("name", "")
                if name:
                    is_active = blk.get("active", False)
                    painter.setFont(label_font)
                    tc = QtGui.QColor("#FFFFFF" if is_active else "#CCCCCC")
                    tc.setAlpha(220 if is_active else 160)
                    painter.setPen(tc)
                    painter.drawText(QtCore.QPointF(bx0 + 3, _RULER_HEIGHT - 2), name)

    @staticmethod
    def _nice_interval(raw: float) -> int:
        for candidate in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
            if candidate >= raw:
                return candidate
        return int(raw)
