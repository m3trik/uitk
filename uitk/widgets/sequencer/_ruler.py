# !/usr/bin/python
# coding=utf-8
"""Ruler item for the timeline header area."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from qtpy import QtWidgets, QtGui, QtCore

if TYPE_CHECKING:
    from uitk.widgets.sequencer._timeline import TimelineView

from uitk.widgets.sequencer._data import (
    SELECTED_ACCENT as _SELECTED_ACCENT,
    _RULER_HEIGHT,
    _SHOT_LANE_HEIGHT,
    _HEADER_HEIGHT,
)

#: Key-tick red, deliberately desaturated: the ruler is read at a glance and
#: a saturated red there competes with the playhead for attention.
_KEY_TICK_COLOR = QtGui.QColor(225, 70, 70, 255)

#: How far a key tick drops from the top of the ruler.  Short of the frame
#: ticks below it, so the two rows of marks stay readable as two rows.
_KEY_TICK_BOTTOM = 11.0


# ---------------------------------------------------------------------------
#  RulerItem
# ---------------------------------------------------------------------------


class RulerItem(QtWidgets.QGraphicsItem):
    """Draws the timeline header: the frame ruler, and the shot lane below it.

    The two are separate strips.  The ruler proper is frame numbers, frame
    ticks and key ticks, and every row of it belongs to the scrub.  The shot
    lane sits UNDER it and carries one band per shot -- the layout, the
    active shot's accent, and (driven by the view) the grabs that move and
    resize it.  They used to share the ruler's 24px, which put the active
    shot's blue rule inside the ruler and made its bottom half un-scrubbable.
    """

    _MIN_WIDTH = 100000.0  # floor; preserves prior behaviour for small scenes

    def __init__(self, timeline: "TimelineView"):
        super().__init__()
        self._timeline = timeline
        # [{name, start, end, active, id?}, ...] -- ``active`` marks the
        # selected shot; an optional ``id`` is carried through untouched so a
        # consumer can get its own identifier back.
        self._shot_blocks: list = []
        # Horizontal extent the ruler paints across; kept in sync with the
        # scene rect by the view's ``_update_scene_rect``.  ``_content_left``
        # is normally 0 but goes negative whenever content sits before frame
        # 0, so the ruler keeps painting there instead of stopping at the
        # origin.
        self._content_width = self._MIN_WIDTH
        self._content_left = 0.0
        #: Frames carrying a key, drawn as Maya-style ticks.  Sorted.
        self._key_ticks: list = []
        self.setZValue(10)

    # -- shot block data ---------------------------------------------------

    def set_shot_blocks(self, blocks: list) -> None:
        self._shot_blocks = list(blocks)
        self.update()

    def clear_shot_blocks(self) -> None:
        self._shot_blocks.clear()
        self.update()

    def selected_block(self) -> Optional[dict]:
        """The block marked ``active``, or ``None`` when nothing is selected."""
        for blk in self._shot_blocks:
            if blk.get("active"):
                return blk
        return None

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

    def set_content_width(self, width: float) -> None:
        """Set the horizontal extent the ruler covers (scene pixels).

        Called by the view's ``_update_scene_rect`` with the current scene
        width so ticks/labels/background keep painting past the old fixed
        cap at high zoom.  A stored value (rather than querying
        ``scene().sceneRect()`` from :meth:`boundingRect`) avoids the
        recursion where an unset scene rect is derived from item bounds.
        """
        width = max(self._MIN_WIDTH, float(width))
        if width == self._content_width:
            return
        self.prepareGeometryChange()
        self._content_width = width

    def set_key_ticks(self, times) -> None:
        """Frames that carry a key, drawn as faint red ticks (Maya's idiom).

        The ruler answers "is there a key here?" at a glance, which is what
        the timeline is read for while scrubbing; the clips answer "where
        does this segment run?".  Empty clears them.
        """
        times = sorted(float(t) for t in times)
        if times == self._key_ticks:
            return
        self._key_ticks = times
        self.update()

    def set_content_left(self, left: float) -> None:
        """Set the left edge of the extent the ruler covers (scene pixels).

        Zero for the ordinary all-positive timeline; negative once the scene
        rect opens up room before frame 0 (a shot padded or rippled backwards
        lives there), so the ticks and shot labels reach that far too.
        """
        left = min(0.0, float(left))
        if left == self._content_left:
            return
        self.prepareGeometryChange()
        self._content_left = left

    def boundingRect(self):
        # Extent tracks the scene rect (pushed in via set_content_left /
        # set_content_width) so the ruler keeps painting at high zoom and
        # before frame 0; a fixed cap stopped it past frame
        # ``width / pixels_per_unit``.  The item sits at scene x=0, so local
        # coordinates == scene coordinates.
        return QtCore.QRectF(self._content_left, 0, self._content_width, _HEADER_HEIGHT)

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
            QtCore.QRectF(vis_left, 0, vis_right - vis_left, _HEADER_HEIGHT)
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

        # floor, not int(): int() truncates toward zero, which drops the
        # first tick left of frame 0 once the timeline reaches back there.
        t = math.floor(t_start / interval) * interval
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

        self._paint_key_ticks(painter, t_start, t_end)

        # -- shot lane at the bottom of the ruler ---------------------------
        if self._shot_blocks:
            self._paint_shot_lane(painter, vis_left, vis_right)

        # Hard baselines under each strip.  Without the lower one the shot
        # lane and the range highlight directly beneath it merge into one
        # block, which reads as the highlight overshooting the header; the
        # upper one keeps the numbers from running into the lane.
        for y, alpha in ((_RULER_HEIGHT - 1.0, 90), (_HEADER_HEIGHT - 1.0, 140)):
            painter.fillRect(
                QtCore.QRectF(vis_left, y, vis_right - vis_left, 1.0),
                QtGui.QColor(0, 0, 0, alpha),
            )

    def _paint_key_ticks(self, painter, t_start: float, t_end: float) -> None:
        """One faint red tick per keyed frame, in the number band.

        Kept above the frame ticks and clipped to the visible span: a scene
        can hold tens of thousands of keys and painting the ones off-screen
        costs the same as painting the ones on it.
        """
        if not self._key_ticks:
            return
        import bisect

        lo = bisect.bisect_left(self._key_ticks, t_start)
        hi = bisect.bisect_right(self._key_ticks, t_end)
        if lo >= hi:
            return
        tl = self._timeline
        painter.setPen(QtGui.QPen(_KEY_TICK_COLOR, 1))
        top = 1.0
        bottom = _KEY_TICK_BOTTOM
        for t in self._key_ticks[lo:hi]:
            x = tl.time_to_x(t)
            painter.drawLine(QtCore.QPointF(x, top), QtCore.QPointF(x, bottom))

    def _paint_shot_lane(self, painter, vis_left: float, vis_right: float) -> None:
        """Draw one band per shot, in the strip below the ruler.

        Selection has to read at a glance without turning the ruler into a
        second timeline, so it is carried by three quiet cues that agree with
        each other: a tinted band, a solid rule along the top of the lane, and
        bright ticks at the shot's two bounds.  Unselected shots get a flat
        dim band and a hairline separator -- enough to show the layout and
        nothing more.
        """
        tl = self._timeline
        top = _RULER_HEIGHT

        label_font = QtGui.QFont(painter.font())
        label_font.setPointSize(7)
        label_font.setBold(True)
        painter.setFont(label_font)
        metrics = QtGui.QFontMetrics(label_font)

        accent = QtGui.QColor(_SELECTED_ACCENT)
        # NO accent wash on the active band: every band gets the same neutral
        # tint, so the lane shows the LAYOUT and nothing else.  Which shot is
        # selected is said by the accent rule and bound ticks below, which are
        # lines rather than a background -- a second blue box stacked on the
        # range highlight read as one oversized block.
        band_fill = QtGui.QColor("#FFFFFF")
        band_fill.setAlpha(12)
        for blk in sorted(self._shot_blocks, key=lambda b: b["start"]):
            bx0 = tl.time_to_x(blk["start"])
            bx1 = tl.time_to_x(blk["end"])
            if bx1 < vis_left or bx0 > vis_right:
                continue
            is_active = bool(blk.get("active", False))
            band = QtCore.QRectF(bx0, top, max(1.0, bx1 - bx0), _SHOT_LANE_HEIGHT)

            painter.fillRect(band, band_fill)

            painter.setPen(QtCore.Qt.NoPen)
            if is_active:
                # The rule says WHICH lane is selected; the ticks say exactly
                # where it starts and ends -- the band alone blurs at low zoom.
                rule = QtGui.QColor(accent)
                rule.setAlpha(230)
                painter.fillRect(QtCore.QRectF(bx0, top, band.width(), 2.0), rule)
                for x in (bx0, bx1 - 1.0):
                    painter.fillRect(
                        QtCore.QRectF(x, top, 1.0, _SHOT_LANE_HEIGHT), rule
                    )
            else:
                sep = QtGui.QColor("#000000")
                sep.setAlpha(90)
                painter.fillRect(
                    QtCore.QRectF(bx1 - 1.0, top, 1.0, _SHOT_LANE_HEIGHT), sep
                )

            name = blk.get("name", "")
            if not name:
                continue
            s = round(blk["start"])
            e = round(blk["end"])
            label = f"{name}  {s}-{e}  {e - s}f"
            avail = max(0, int(bx1 - bx0) - 6)
            label = metrics.elidedText(label, QtCore.Qt.ElideRight, avail)
            tc = QtGui.QColor("#FFFFFF" if is_active else "#CCCCCC")
            tc.setAlpha(240 if is_active else 150)
            painter.setPen(tc)
            painter.drawText(QtCore.QPointF(bx0 + 3, _HEADER_HEIGHT - 3), label)

    @staticmethod
    def _nice_interval(raw: float) -> int:
        for candidate in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
            if candidate >= raw:
                return candidate
        return int(raw)
