# !/usr/bin/python
# coding=utf-8
"""Range-related overlay items: static ranges, snap guides, and the range highlight."""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from qtpy import QtWidgets, QtGui, QtCore

if TYPE_CHECKING:
    from uitk.widgets.sequencer._sequencer import SequencerWidget
    from uitk.widgets.sequencer._timeline import TimelineView

from uitk.widgets.sequencer._drag_tooltip import FrameTooltip
from uitk.widgets.sequencer._draggable import (
    DraggableItemMixin,
    HeldGeometryMixin,
    ItemRetirement,
)
from uitk.managers.cursor_manager import CursorManager

# ---------------------------------------------------------------------------
#  _StaticRangeOverlay
# ---------------------------------------------------------------------------


class _StaticRangeOverlay(HeldGeometryMixin, QtWidgets.QGraphicsItem):
    """Non-interactive range overlay: a tinted span over the content area
    (a host's inactive ranges)."""

    def __init__(self, timeline, start: float, end: float, color: str, alpha: int):
        super().__init__()
        self._timeline = timeline
        self._start = start
        self._end = end
        self._color = QtGui.QColor(color)
        self._color.setAlpha(alpha)
        self.setZValue(-2)
        self.setAcceptedMouseButtons(QtCore.Qt.NoButton)

    def _layout_geometry(self) -> QtCore.QRectF:
        tl = self._timeline
        sq = tl.parent_sequencer
        x0 = tl.time_to_x(self._start)
        x1 = tl.time_to_x(self._end)
        top, h = sq.content_span()
        return QtCore.QRectF(x0, top, x1 - x0, h)

    def _rect(self) -> QtCore.QRectF:
        return self._geometry()

    def boundingRect(self) -> QtCore.QRectF:
        return self._rect()

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        r = self._rect()
        if r.width() < 1:
            return
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        painter.fillRect(r, self._color)


# ---------------------------------------------------------------------------
#  _SnapGuideItem
# ---------------------------------------------------------------------------


class _SnapGuideItem(HeldGeometryMixin, QtWidgets.QGraphicsItem):
    """Vertical guides marking frames a live drag is aligned with.

    Purely an affordance: the guides say "the value you are dragging sits
    on a frame that already carries keys" without altering the drag.  A
    consumer that also wants the drag pulled onto those frames turns on
    :attr:`SequencerWidget.snap_to_keys`.
    """

    _WIDTH = 1.0

    def __init__(self, timeline, color: str = "#FFD24A"):
        super().__init__()
        self._timeline = timeline
        self._times: list = []
        self._color = QtGui.QColor(color)
        self.setZValue(9)  # above clips/overlays, below the ruler (10)
        self.setAcceptedMouseButtons(QtCore.Qt.NoButton)

    def set_times(self, times) -> None:
        self._times = list(times)
        self.sync()

    def _layout_geometry(self) -> tuple:
        """``(bounds, top, height, xs)`` -- one guide line per x."""
        top, h = self._timeline.parent_sequencer.content_span()
        xs = [self._timeline.time_to_x(t) for t in self._times]
        if not xs:
            return QtCore.QRectF(0, top, 0, h), top, h, xs
        pad = self._WIDTH + 1
        bounds = QtCore.QRectF(min(xs) - pad, top, (max(xs) - min(xs)) + 2 * pad, h)
        return bounds, top, h, xs

    def boundingRect(self) -> QtCore.QRectF:
        return self._geometry()[0]

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        _bounds, top, h, xs = self._geometry()
        if not xs:
            return
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        pen = QtGui.QPen(self._color, self._WIDTH)
        painter.setPen(pen)
        for x in xs:
            painter.drawLine(QtCore.QPointF(x, top), QtCore.QPointF(x, top + h))


# ---------------------------------------------------------------------------
#  RangeHighlightItem
# ---------------------------------------------------------------------------
_RANGE_HANDLE_WIDTH = 4  # pixels from edge that activates resize cursor
#: The highlight's least height: with no rows it is still a band to grab.
_RANGE_MIN_HEIGHT = 12


class RangeHighlightItem(
    HeldGeometryMixin, DraggableItemMixin, QtWidgets.QGraphicsItem
):
    """A semi-transparent rectangle highlighting a time range on the timeline.

    Supports dragging (move) and edge-handle resizing.  Sits behind clips
    (``zValue = -1``) so it acts as a tinted background region.  A layer's
    lane can offer the same grabs from the header (:meth:`zone_at`,
    :meth:`begin_edge_drag`), and a layer's item can keep a press on an edge
    from it (``SequencerLayer.claims_press``).
    """

    def __init__(self, timeline: "TimelineView"):
        super().__init__()
        self._timeline = timeline
        self._start: float = 0.0
        self._end: float = 100.0
        self._color = QtGui.QColor(90, 140, 220, 30)  # semi-transparent blue
        self._handle_color = QtGui.QColor(90, 140, 220, 80)
        self._drag_mode: Optional[str] = None  # "move" | "left" | "right"
        self._grab_zone: str = "move"  # the handle the gesture started on
        self._drag_origin_x: float = 0.0
        self._drag_origin_start: float = 0.0
        self._drag_origin_end: float = 0.0
        self.setZValue(-1)
        self.setAcceptHoverEvents(True)
        self._drag_tooltip = FrameTooltip()

    # -- properties ---------------------------------------------------------
    @property
    def start(self) -> float:
        return self._start

    @start.setter
    def start(self, value: float):
        self._start = value
        self.sync()

    @property
    def end(self) -> float:
        return self._end

    @end.setter
    def end(self, value: float):
        self._end = value
        self.sync()

    def set_range(self, start: float, end: float):
        self._start = start
        self._end = end
        self.sync()

    @property
    def color(self) -> QtGui.QColor:
        return self._color

    @color.setter
    def color(self, value):
        if isinstance(value, str):
            c = QtGui.QColor(value)
            c.setAlpha(self._color.alpha())
            self._color = c
            self._handle_color = QtGui.QColor(c)
            self._handle_color.setAlpha(min(255, c.alpha() * 3))
        else:
            self._color = QtGui.QColor(value)
            self._handle_color = QtGui.QColor(value)
            self._handle_color.setAlpha(min(255, value.alpha() * 3))
        self.update()

    @property
    def opacity_value(self) -> int:
        return self._color.alpha()

    @opacity_value.setter
    def opacity_value(self, alpha: int):
        self._color.setAlpha(max(0, min(255, alpha)))
        self._handle_color.setAlpha(max(0, min(255, alpha * 3)))
        self.update()

    # -- geometry -----------------------------------------------------------
    def _rect(self) -> QtCore.QRectF:
        return self._geometry()

    def _layout_geometry(self) -> QtCore.QRectF:
        """The painted rectangle the current range and track layout give.

        Starts at the content top -- the highlight stays clear of the whole
        header, the ruler and every lane under it.
        """
        tl = self._timeline
        sq = tl.parent_sequencer
        x0 = tl.time_to_x(self._start)
        x1 = tl.time_to_x(self._end)
        top = sq._content_top
        h = max(sq._total_row_height(), _RANGE_MIN_HEIGHT)
        return QtCore.QRectF(x0, top, x1 - x0, h)

    def boundingRect(self) -> QtCore.QRectF:
        return self._rect().adjusted(-_RANGE_HANDLE_WIDTH, 0, _RANGE_HANDLE_WIDTH, 0)

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        r = self._rect()
        if r.width() < 1:
            return
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        # Fill
        painter.fillRect(r, self._color)
        # Left/right edge handles
        hw = min(_RANGE_HANDLE_WIDTH, r.width() / 2)
        painter.fillRect(
            QtCore.QRectF(r.left(), r.top(), hw, r.height()), self._handle_color
        )
        painter.fillRect(
            QtCore.QRectF(r.right() - hw, r.top(), hw, r.height()), self._handle_color
        )
        # A hairline around the whole span.  The fill alone is a 30-alpha wash
        # that disappears against a busy track area; the outline is what makes
        # the range's extent legible without brightening the fill and
        # drowning the clips inside it.
        edge = QtGui.QColor(self._handle_color)
        edge.setAlpha(min(255, max(90, self._color.alpha() * 5)))
        painter.setPen(QtGui.QPen(edge, 1))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(r.adjusted(0, 0, -1, -1))

    # -- hit zone -----------------------------------------------------------
    def zone_at(self, scene_x: float) -> str:
        """``"left"`` / ``"right"`` / ``"move"`` for *scene_x*, else ``""``.

        The x-only twin of :meth:`_hit_zone`, which needs a point inside the
        item.  Exposed so a LANE can offer the same three grabs (a layer that
        draws the range's bounds and extent on its band, where a user reaches
        for them), but the item's own hit area stops at the content top and
        must keep doing so -- reaching it up into the header means a
        view-dependent ``boundingRect``, which re-enters the scene index on
        scroll and dies natively.  The layer drives the drag through
        :meth:`begin_edge_drag` instead.
        """
        tl = self._timeline
        for edge, t in (("left", self._start), ("right", self._end)):
            if abs(scene_x - tl.time_to_x(t)) <= _RANGE_HANDLE_WIDTH:
                return edge
        if tl.time_to_x(self._start) <= scene_x <= tl.time_to_x(self._end):
            return "move"
        return ""

    def begin_edge_drag(self, edge: str, scene_x: float) -> None:
        """Start a bound drag from outside the item (a lane's handles).

        The same state ``mousePressEvent`` sets, so every later step --
        move, release, cancel, undo capture -- is the one code path.  The
        caller has recorded the press modifiers (``record_press_modifiers``).
        """
        self._grab_zone = edge
        self._drag_mode = edge
        self._about_centre = False
        self._drag_origin_x = scene_x
        self._drag_origin_start = self._start
        self._drag_origin_end = self._end
        self._undo_captured = False
        self._show_range_drag_tooltip(QtCore.QPointF(scene_x, self._rect().top()))

    def _drag_verb(self) -> str:
        """What this drag does, as a host applies the modifiers recorded at
        press: a plain bound drag resizes, Ctrl trims the bound alone, Shift
        retimes.  A body drag (a lane's band) moves the range."""
        sq = self._timeline.parent_sequencer
        if self._drag_mode == "move":
            return "Move"
        if sq.shift_held_at_press:
            verb = "Retime"
        else:
            verb = "Trim" if sq.ctrl_held_at_press else "Resize"
        return f"{verb} about centre" if self._about_centre else verb

    #: Alt held on the last move of a bound drag (:meth:`_drag_bound`).
    _about_centre = False

    def _drag_bound(self, dt: float, modifiers) -> None:
        """Move the grabbed bound by *dt* (snapped).  With Alt held the other
        bound moves as far the other way -- a resize about the range's centre,
        as the Graph Editor's scale manipulator does with Alt.  Both bounds
        come from the drag's origin, so Alt pressed or let go mid-drag
        switches cleanly."""
        centre = bool(modifiers & QtCore.Qt.AltModifier)
        self._about_centre = centre
        o_start, o_end = self._drag_origin_start, self._drag_origin_end
        if self._drag_mode == "left":
            start = DraggableItemMixin.snap_time(o_start + dt, self._timeline)
            end = o_end - (start - o_start) if centre else o_end
        else:
            end = DraggableItemMixin.snap_time(o_end + dt, self._timeline)
            start = o_start - (end - o_end) if centre else o_start
        if start < end:
            self._start, self._end = start, end

    def _hit_zone(self, pos: QtCore.QPointF) -> str:
        r = self._rect()
        local_x = pos.x() - r.left()
        if local_x <= _RANGE_HANDLE_WIDTH:
            return "left"
        elif local_x >= r.width() - _RANGE_HANDLE_WIDTH:
            return "right"
        return "move"

    # -- hover cursor -------------------------------------------------------
    def hoverMoveEvent(self, event):
        zone = self._hit_zone(event.pos())
        if zone in ("left", "right"):
            # SplitH (vs the gap overlay's SizeHor): this handle ripples the
            # rest of the timeline, the gap's edge does not — the cursor is
            # the affordance that tells the two apart.
            self.setCursor(QtCore.Qt.SplitHCursor)
        else:
            # No grab cursor over the body: it passes every press through to
            # the marquee, so advertising a drag here would be a lie.  A lane
            # can offer the move, and show the hand.
            self.unsetCursor()

    # -- mouse interaction --------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        zone = self._hit_zone(event.pos())
        # The BODY never claims a press, with or without Shift.  This item
        # spans the whole range -- every track row, for its full width -- so
        # claiming Shift+drag here made the timeline's additive marquee
        # impossible anywhere inside it, which is where the user is working.
        # Marquee wins; a lane that draws the range moves it from its band,
        # where nothing else competes for the gesture.
        if zone == "move":
            event.ignore()
            return
        # No deferral to a clip under the cursor: every clip sits ABOVE this
        # item, so one that wanted the press already took it.  Reaching here
        # means each clip there declined -- a read-only clip (which takes no
        # press) -- or the press is past the clip whose edge sits on this
        # bound (the clip keeps its own pixels; this handle reaches outside
        # the range).  Deferring to those anyway left the press with nobody:
        # where the next clips start on this bound, the end could not be
        # dragged in any row with content (2026-10-06).
        #
        # The one deferral is to a layer that claims the pixel for an item of
        # its own drawn under this one (``SequencerLayer.claims_press``): a
        # handle painted there answers with ITS meaning, rather than the
        # z-order and a few pixels of cursor deciding which handle does.
        sq = self._timeline.parent_sequencer
        if sq._layer_claims_press(event.scenePos()):
            event.ignore()
            return
        sq.record_press_modifiers(event.modifiers())
        self._grab_zone = zone
        self._drag_mode = zone
        self._about_centre = False
        self._drag_origin_x = event.scenePos().x()
        self._drag_origin_start = self._start
        self._drag_origin_end = self._end
        # Undo snapshot is captured lazily on the first real move — a
        # plain click must not burn an undo step or wipe redo.
        self._undo_captured = False
        self._show_range_drag_tooltip(event.scenePos())
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_mode is None:
            event.ignore()
            return
        self._capture_drag_undo()
        dx = event.scenePos().x() - self._drag_origin_x
        dt = (
            dx / self._timeline._pixels_per_unit
            if self._timeline._pixels_per_unit
            else 0
        )

        if self._drag_mode == "move":
            span = self._drag_origin_end - self._drag_origin_start
            new_start = DraggableItemMixin.snap_time(
                self._drag_origin_start + dt, self._timeline
            )
            self._start = new_start
            self._end = new_start + span
        elif self._drag_mode in ("left", "right"):
            self._drag_bound(dt, event.modifiers())

        self.sync()
        self._update_range_drag_tooltip(event.scenePos())
        event.accept()

    def update_edge_drag(self, scene_x: float, modifiers=None) -> None:
        """Advance a drag begun with :meth:`begin_edge_drag` (*modifiers*:
        the move's own; Alt resizes about the centre)."""
        if self._drag_mode is None:
            return
        self._capture_drag_undo()
        if modifiers is None:
            modifiers = QtWidgets.QApplication.keyboardModifiers()
        dt = (scene_x - self._drag_origin_x) / (self._timeline._pixels_per_unit or 1)
        if self._drag_mode in ("left", "right"):
            self._drag_bound(dt, modifiers)
        elif self._drag_mode == "move":
            # Both bounds by the same snapped delta, so the range's DURATION
            # is untouched -- measuring the delta off the start and adding it
            # to the raw end would let rounding stretch it a frame.
            new_start = DraggableItemMixin.snap_time(
                self._drag_origin_start + dt, self._timeline
            )
            shift = new_start - self._drag_origin_start
            self._start = new_start
            self._end = self._drag_origin_end + shift
        self.sync()
        self._update_range_drag_tooltip(QtCore.QPointF(scene_x, self._rect().top()))

    def finish_edge_drag(self) -> bool:
        """End the drag and emit if a bound actually moved.

        The shared tail of every bound drag, however it started.
        """
        moved = self._drag_mode is not None and (
            abs(self._start - self._drag_origin_start) > 0.01
            or abs(self._end - self._drag_origin_end) > 0.01
        )
        if moved:
            sq = self._timeline.parent_sequencer
            # The span the user just dragged to may reach past the
            # scrollable extent (grown past the end, or back before frame
            # 0) -- widen it before the consumer reacts.
            sq.refresh_extent()
            sq.range_highlight_changed.emit(self._start, self._end)
        CursorManager.pop(self)
        self._drag_mode = None
        self._drag_tooltip.hide()
        return moved

    def _range_drag_frame(self) -> float:
        # The bound under the hand: the frame that reads at the cursor is the
        # edge grabbed, whatever the host does with the rest of the range.
        return float(self._end if self._grab_zone == "right" else self._start)

    def _range_drag_label(self) -> str:
        return (
            f"{self._drag_verb()} {FrameTooltip.format_frame(self._range_drag_frame())}"
        )

    def _show_range_drag_tooltip(self, scene_pos):
        self._drag_tooltip.show(
            self.scene(),
            scene_pos,
            label=self._range_drag_label(),
            color=self._handle_color.name(),
        )

    def _update_range_drag_tooltip(self, scene_pos):
        self._drag_tooltip.update(scene_pos, label=self._range_drag_label())

    def _is_drag_active(self) -> bool:
        return self._drag_mode is not None

    def _restore_drag_state(self) -> None:
        self._start = self._drag_origin_start
        self._end = self._drag_origin_end
        CursorManager.pop(self)
        self._drag_mode = None
        self.sync()

    def mouseReleaseEvent(self, event):
        # Emit only on an actual change (a 0.01 gate) — a zero-motion click
        # otherwise triggers a full save + resize + widget rebuild in the
        # consumer.
        self.finish_edge_drag()
        event.accept()


class _Ranges:
    """The time ranges drawn over the rows: the interactive highlight (the
    active shot's), the static overlays, and the active range's column tint,
    with the highlight's and the overlays' visibility toggles."""

    def __init__(self, sequencer: "SequencerWidget"):
        self._sequencer = sequencer
        self.highlight: Optional[RangeHighlightItem] = None
        self.overlays: List[QtWidgets.QGraphicsItem] = []
        self.show_overlays: bool = True  # toggle for the range overlays
        self.show_highlight: bool = True  # toggle for the range highlight
        self.active: Optional[tuple] = None  # (start, end) in frames
        self.active_color = QtGui.QColor(90, 140, 220, 25)  # semi-transparent blue

    def set_highlight(
        self, start: float, end: float, color: Optional[str], alpha: int
    ) -> None:
        sq = self._sequencer
        if self.highlight is None:
            self.highlight = RangeHighlightItem(sq._timeline)
            sq.add_track_item(self.highlight)
        self.highlight.set_range(start, end)
        self.highlight.setVisible(self.show_highlight)
        if color is not None:
            c = QtGui.QColor(color)
            c.setAlpha(alpha)
            self.highlight.color = c
        elif alpha != self.highlight.opacity_value:
            self.highlight.opacity_value = alpha
        sq.refresh_extent()

    def clear_highlight(self) -> None:
        if self.highlight is not None:
            ItemRetirement.retire(self.highlight)
            self.highlight = None

    def highlight_span(self) -> Optional[tuple]:
        if self.highlight is None:
            return None
        return (self.highlight.start, self.highlight.end)

    def add_overlay(self, start: float, end: float, color: str, alpha: int) -> None:
        sq = self._sequencer
        item = _StaticRangeOverlay(sq._timeline, start, end, color, alpha)
        item.setVisible(self.show_overlays)
        sq.add_track_item(item)
        self.overlays.append(item)
        sq.refresh_extent()

    def clear_overlays(self) -> None:
        for item in self.overlays:
            ItemRetirement.retire(item)
        self.overlays.clear()

    def set_show_overlays(self, value: bool) -> None:
        self.show_overlays = value
        for item in self.overlays:
            item.setVisible(value)

    def set_show_highlight(self, value: bool) -> None:
        self.show_highlight = value
        if self.highlight is not None:
            self.highlight.setVisible(value)

    def set_active(self, start: float, end: float) -> None:
        sq = self._sequencer
        self.active = (start, end)
        sq.refresh_extent()
        sq._timeline.viewport().update()

    def clear_active(self) -> None:
        self.active = None
        self._sequencer._timeline.viewport().update()


class _Snapping:
    """Where a drag lands: the time grid (:attr:`SequencerWidget.snap_interval`)
    and the frames that already carry a key -- the candidates a drag aligns
    to, the capture radius that makes one a match, and the guide drawn at it."""

    def __init__(self, sequencer: "SequencerWidget"):
        self._sequencer = sequencer
        self.interval: float = 1.0  # 1 = per-frame snap (default)
        self.guide = None  # _SnapGuideItem, created lazily
        self.guides_enabled: bool = True  # draw alignment guides on drag
        self.to_keys: bool = False  # also SNAP the drag to those frames
        self.capture_px: float = 6.0  # guide/snap capture radius, px

    def set_guides_enabled(self, value: bool) -> None:
        self.guides_enabled = bool(value)
        if not value:
            self._sequencer.clear_snap_guides()

    def alignment_times(
        self, exclude_clip_ids=(), exclude_times=(), exclude_spans=()
    ) -> List[float]:
        exclude = set(exclude_clip_ids)
        ex_times = {round(float(t), 3) for t in exclude_times}
        spans = [(tid, lo - 1e-3, hi + 1e-3) for tid, lo, hi in exclude_spans]

        def _dropped(track_id, t):
            if t in ex_times:
                return True
            return any(tid == track_id and lo <= t <= hi for tid, lo, hi in spans)

        times: set = set()
        for cd in self._sequencer._clips.values():
            if cd.clip_id in exclude:
                continue
            for t in self._clip_candidate_times(cd):
                if not _dropped(cd.track_id, t):
                    times.add(t)
        return sorted(times)

    @staticmethod
    def _clip_candidate_times(cd):
        """Yield one clip's alignment candidates, rounded to the grain."""
        yield round(cd.start, 3)
        if cd.duration > 0:
            yield round(cd.end, 3)
        for t in cd.shown_key_times():
            yield round(t, 3)

    def nearest_alignment(
        self, time: float, candidates, tolerance: Optional[float] = None
    ) -> Optional[float]:
        if not candidates:
            return None
        if tolerance is None:
            ppu = self._sequencer._timeline.pixels_per_unit or 1.0
            tolerance = self.capture_px / ppu
        best = None
        best_d = tolerance
        for t in candidates:
            d = abs(t - time)
            if d <= best_d:
                best, best_d = t, d
        return best

    def set_guides(self, times) -> None:
        if not self.guides_enabled:
            return
        times = [float(t) for t in times]
        if not times:
            if self.guide is not None:
                self.guide.set_times([])
            return
        if self.guide is None:
            sq = self._sequencer
            self.guide = _SnapGuideItem(sq._timeline, color=sq.SNAP_GUIDE_COLOR)
            sq._timeline._scene.addItem(self.guide)
        self.guide.set_times(times)

    def clear_guides(self) -> None:
        if self.guide is not None:
            ItemRetirement.retire(self.guide)
            self.guide = None
