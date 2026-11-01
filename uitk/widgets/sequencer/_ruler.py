# !/usr/bin/python
# coding=utf-8
"""Ruler item for the timeline header area."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from qtpy import QtWidgets, QtGui, QtCore

if TYPE_CHECKING:
    from uitk.widgets.sequencer._timeline import TimelineView

from uitk.widgets.sequencer._data import _RULER_HEIGHT

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
    """Draws the timeline header: the frame ruler, and the layers' lanes below it.

    Separate strips.  The ruler proper is frame numbers, frame ticks and key
    ticks, and every row of it belongs to the scrub.  A layer's lane sits
    UNDER it (``SequencerWidget.add_layer``), stacked in registration order,
    and the layer paints it (``SequencerLayer.paint_lane``); the item only
    gives each lane its strip and the baselines between them.
    """

    _MIN_WIDTH = 100000.0  # floor; preserves prior behaviour for small scenes

    def __init__(self, timeline: "TimelineView"):
        super().__init__()
        self._timeline = timeline
        #: The header's height: the ruler, and every lane under it
        #: (:meth:`set_height`, from the widget's lane stack).
        self._height = float(_RULER_HEIGHT)
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

    def set_height(self, height: float) -> None:
        """Set the header's height: the ruler and the lanes under it.

        Announced to the scene index first, as every bounds change of a
        held rect must be (``set_content_width``).
        """
        height = float(height)
        if height == self._height:
            return
        self.prepareGeometryChange()
        self._height = height
        self.update()

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
        rect opens up room before frame 0 (content padded or rippled backwards
        lives there), so the ticks and the lanes reach that far too.
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
        return QtCore.QRectF(self._content_left, 0, self._content_width, self._height)

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
            QtCore.QRectF(vis_left, 0, vis_right - vis_left, self._height)
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
        self._paint_lanes(painter, vis_left, vis_right)

        # Hard baselines: the header's bottom, and the ruler's when lanes sit
        # under it.  Without the lower one a lane and the range highlight
        # directly beneath it merge into one block, which reads as the
        # highlight overshooting the header; the upper one keeps the numbers
        # from running into the lane.
        lines = [(self._height - 1.0, 140)]
        if self._height > _RULER_HEIGHT:
            lines.insert(0, (_RULER_HEIGHT - 1.0, 90))
        for y, alpha in lines:
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

    def _paint_lanes(self, painter, vis_left: float, vis_right: float) -> None:
        """Hand each layer's lane its strip under the ruler, top to bottom.

        The painter's state is the lane's to change: it is restored after
        each one, so a lane cannot leak a pen or font into the next.
        """
        top = float(_RULER_HEIGHT)
        for layer, height in self._timeline.parent_sequencer._lane_stack:
            paint = getattr(layer, "paint_lane", None)
            if paint is not None:
                painter.save()
                try:
                    paint(
                        painter,
                        QtCore.QRectF(vis_left, top, vis_right - vis_left, height),
                    )
                finally:
                    painter.restore()
            top += height

    @staticmethod
    def _nice_interval(raw: float) -> int:
        for candidate in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
            if candidate >= raw:
                return candidate
        return int(raw)
