# !/usr/bin/python
# coding=utf-8
"""Ruler item for the timeline header area."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from qtpy import QtWidgets, QtGui, QtCore

if TYPE_CHECKING:
    from uitk.widgets.sequencer._timeline import TimelineView

from uitk.widgets.sequencer._data import _RULER_HEIGHT


# ---------------------------------------------------------------------------
#  RulerItem
# ---------------------------------------------------------------------------


class RulerItem(QtWidgets.QGraphicsItem):
    """Draws the frame-number ruler at the top of the timeline.

    Also renders shot-block name labels along the ruler bottom so the
    user always sees the shot layout.
    """

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

    def shot_block_at(self, time: float) -> Optional[dict]:
        """Return the shot block containing *time*, or ``None``.

        Used by the timeline's context-menu dispatch to refine the
        "ruler" zone into "shot_lane" when the click lands on a shot
        block, so consumers can present a shot-specific menu.
        """
        for blk in self._shot_blocks:
            if blk["start"] <= time <= blk["end"]:
                return blk
        return None

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
            painter.setFont(label_font)
            metrics = QtGui.QFontMetrics(label_font)

            for blk in sorted_blocks:
                bx0 = tl.time_to_x(blk["start"])
                bx1 = tl.time_to_x(blk["end"])
                if bx1 < vis_left or bx0 > vis_right:
                    continue
                name = blk.get("name", "")
                if not name:
                    continue
                s = round(blk["start"])
                e = round(blk["end"])
                label = f"{name}  {s}-{e}  {e - s}f"
                avail = max(0, int(bx1 - bx0) - 6)
                label = metrics.elidedText(label, QtCore.Qt.ElideRight, avail)
                is_active = blk.get("active", False)
                tc = QtGui.QColor("#FFFFFF" if is_active else "#CCCCCC")
                tc.setAlpha(220 if is_active else 160)
                painter.setPen(tc)
                painter.drawText(QtCore.QPointF(bx0 + 3, _RULER_HEIGHT - 2), label)

    @staticmethod
    def _nice_interval(raw: float) -> int:
        for candidate in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
            if candidate >= raw:
                return candidate
        return int(raw)
