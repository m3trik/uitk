# !/usr/bin/python
# coding=utf-8
"""Range-related overlay items: static ranges, gap hatching, and highlights."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from qtpy import QtWidgets, QtGui, QtCore

if TYPE_CHECKING:
    from uitk.widgets.sequencer._timeline import TimelineView

from uitk.widgets.sequencer._data import (
    _SHOT_LANE_HEIGHT,
    MenuUtils,
    PatternRegistry,
    HATCH_SPARSE,
)
from uitk.widgets.sequencer._drag_tooltip import FrameTooltip
from uitk.widgets.sequencer._draggable import DraggableItemMixin
from uitk.managers.cursor_manager import CursorManager

# ---------------------------------------------------------------------------
#  _StaticRangeOverlay
# ---------------------------------------------------------------------------


class _StaticRangeOverlay(QtWidgets.QGraphicsItem):
    """Non-interactive range overlay for non-active shots."""

    def __init__(self, timeline, start: float, end: float, color: str, alpha: int):
        super().__init__()
        self._timeline = timeline
        self._start = start
        self._end = end
        self._color = QtGui.QColor(color)
        self._color.setAlpha(alpha)
        self.setZValue(-2)
        self.setAcceptedMouseButtons(QtCore.Qt.NoButton)

    def _rect(self) -> QtCore.QRectF:
        tl = self._timeline
        sq = tl.parent_sequencer
        x0 = tl.time_to_x(self._start)
        x1 = tl.time_to_x(self._end)
        top = sq._content_top
        h = max(sq._total_row_height(), tl.viewport().height() - top)
        return QtCore.QRectF(x0, top, x1 - x0, h)

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


class _SnapGuideItem(QtWidgets.QGraphicsItem):
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
        self.prepareGeometryChange()
        self._times = list(times)
        self.update()

    def _span(self) -> tuple:
        sq = self._timeline.parent_sequencer
        top = sq._content_top
        h = max(sq._total_row_height(), self._timeline.viewport().height() - top)
        return top, h

    def boundingRect(self) -> QtCore.QRectF:
        top, h = self._span()
        if not self._times:
            return QtCore.QRectF(0, top, 0, h)
        xs = [self._timeline.time_to_x(t) for t in self._times]
        pad = self._WIDTH + 1
        return QtCore.QRectF(min(xs) - pad, top, (max(xs) - min(xs)) + 2 * pad, h)

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        if not self._times:
            return
        top, h = self._span()
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        pen = QtGui.QPen(self._color, self._WIDTH)
        painter.setPen(pen)
        for t in self._times:
            x = self._timeline.time_to_x(t)
            painter.drawLine(QtCore.QPointF(x, top), QtCore.QPointF(x, top + h))


# ---------------------------------------------------------------------------
#  _GapOverlayItem
# ---------------------------------------------------------------------------


class _GapOverlayItem(DraggableItemMixin, QtWidgets.QGraphicsItem):
    """Diagonal-hatch overlay for gaps between shots.

    Displays the gap duration as centered text and a tooltip on hover.
    Supports three drag modes:
    - **Right edge**: resize gap (shifts the next shot and all downstream).
    - **Left edge**: resize gap from the left (shifts the prev shot end).
    - **Center** (body drag): reposition the gap, keeping gap size constant.
      Automatically disabled when the gap is too narrow for a center zone.

    ``tail=True`` marks the zero-width overlay a consumer can place after
    the LAST shot, which has no following shot to form a real gap with.
    It exposes only the left edge — i.e. that shot's ``end`` — so the final
    shot gets the same drag handle every other shot already has.
    """

    _EDGE_WIDTH = 6  # px from each edge that triggers resize cursor

    def __init__(
        self,
        timeline,
        start: float,
        end: float,
        color: str,
        alpha: int,
        locked: bool = False,
        tail: bool = False,
    ):
        super().__init__()
        self._timeline = timeline
        self._start = start
        self._end = end
        self._tail = tail
        self._base_alpha = alpha
        self._color = QtGui.QColor(color)
        self._color.setAlpha(alpha)
        self._line_color = QtGui.QColor(color)
        self._line_color.setAlpha(min(255, alpha + 40))
        self._hovered = False
        # A tail handle is not a gap — it has no right-hand shot to key a
        # lock on, and a locked tail would leave the LAST shot without its
        # only end handle.  Locking is refused at the source.
        self._locked = locked and not tail
        self._drag_mode: Optional[str] = None  # "left", "right", "move", or None
        self._drag_origin_x: float = 0.0
        self._drag_origin_start: float = 0.0
        self._drag_origin_end: float = 0.0
        self.setZValue(-3)
        self.setAcceptHoverEvents(True)
        self._gap_frames = int(round(end - start))
        self._update_tooltip()
        self._drag_tooltip = FrameTooltip()

    def _update_tooltip(self):
        self._gap_frames = max(0, int(round(self._end - self._start)))
        lock_label = " [Locked]" if self._locked else ""
        mode = self._drag_mode
        if self._tail:
            frame = int(round(self._start))
            self.setToolTip(
                f"Shot end: frame {frame}{lock_label}"
                "\nDrag to resize the last shot"
                "\nRight-click for options"
            )
            return
        if mode == "left":
            frame = int(round(self._start))
            info = f"◀ Left edge → frame {frame}"
        elif mode == "right":
            frame = int(round(self._end))
            info = f"Right edge ▶ → frame {frame}"
        elif mode == "move":
            info = f"Sliding → {int(round(self._start))}–{int(round(self._end))}"
        else:
            info = "Drag edges to resize · Drag center to reposition"
        self.setToolTip(
            f"Gap: {self._gap_frames} frame{'s' if self._gap_frames != 1 else ''}{lock_label}"
            f"\n{info}"
            "\nRight-click for options"
        )

    _MIN_PX = 4  # minimum visual width so zero-width gaps remain visible

    def _rect(self) -> QtCore.QRectF:
        tl = self._timeline
        sq = tl.parent_sequencer
        x0 = tl.time_to_x(self._start)
        x1 = tl.time_to_x(self._end)
        w = x1 - x0
        if w < self._MIN_PX:
            mid = (x0 + x1) * 0.5
            x0 = mid - self._MIN_PX * 0.5
            w = self._MIN_PX
        top = sq._content_top
        h = max(sq._total_row_height(), tl.viewport().height() - top)
        return QtCore.QRectF(x0, top, w, h)

    def boundingRect(self) -> QtCore.QRectF:
        r = self._rect()
        return r.adjusted(-self._EDGE_WIDTH, 0, self._EDGE_WIDTH, 0)

    def _hit_zone(self, pos: QtCore.QPointF) -> str:
        # A tail handle has no following shot, so "right" (move the next
        # shot's start) and "body" (slide the whole gap) have no target --
        # every press on it is a drag of the preceding shot's end.
        if self._tail:
            return "left"
        r = self._rect()
        local_x = pos.x() - r.left()
        if local_x <= self._EDGE_WIDTH:
            return "left"
        if local_x >= r.width() - self._EDGE_WIDTH:
            return "right"
        return "body"

    def hoverEnterEvent(self, event):
        self._hovered = True
        self._color.setAlpha(min(255, self._base_alpha + 50))
        self._line_color.setAlpha(min(255, self._base_alpha + 90))
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self._color.setAlpha(self._base_alpha)
        self._line_color.setAlpha(min(255, self._base_alpha + 40))
        self.unsetCursor()
        self.update()

    def hoverMoveEvent(self, event):
        # A locked gap advertises no drag/resize affordance — keep the
        # plain arrow so the SizeHor/OpenHand cursors don't imply an
        # interaction the press handler now refuses.
        if self._locked or self._clip_at(event.scenePos()):
            self.setCursor(QtCore.Qt.ArrowCursor)
            return
        zone = self._hit_zone(event.pos())
        if zone in ("left", "right"):
            self.setCursor(QtCore.Qt.SizeHorCursor)
        elif zone == "body":
            self.setCursor(QtCore.Qt.OpenHandCursor)
        else:
            self.setCursor(QtCore.Qt.ArrowCursor)

    def _clip_at(self, scene_pos: QtCore.QPointF) -> bool:
        """Return True if a ClipItem exists at *scene_pos*."""
        from uitk.widgets.sequencer._clip import ClipItem

        for item in self.scene().items(scene_pos):
            if isinstance(item, ClipItem):
                return True
        return False

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        # A locked gap must not move or resize.  Ignore the press so it
        # falls through (e.g. to marquee) instead of starting a drag —
        # the drag/resize handlers and their gap_* signal emissions all
        # hang off the drag mode set below.
        if self._locked:
            event.ignore()
            return
        zone = self._hit_zone(event.pos())
        self._drag_mode = "move" if zone == "body" else zone  # "left"/"right"
        self._drag_origin_x = event.scenePos().x()
        self._drag_origin_start = self._start
        self._drag_origin_end = self._end
        # The grab cursor and the floating frame label are what a DRAG looks
        # like, and a press is not one until the pointer clears Qt's drag
        # distance — showing them at press made every plain click (and the
        # first half of every double-click) flicker through a grab it never
        # performed.  Armed on the first real move, like the clip body.
        self._grab_armed = False
        self._press_screen_pos = event.screenPos()
        sq = self._timeline.parent_sequencer
        sq.record_press_modifiers(event.modifiers())
        # Undo snapshot is captured lazily on the first real move — a
        # plain click must not burn an undo step or wipe redo.
        self._undo_captured = False
        event.accept()

    def _arm_gap_grab(self, event) -> None:
        """Show the grab, now that the gesture is one."""
        self._grab_armed = True
        if self._drag_mode == "move":
            CursorManager.push(self, QtCore.Qt.ClosedHandCursor)
        self._show_gap_drag_tooltip(event.scenePos())

    def mouseMoveEvent(self, event):
        if self._drag_mode is None:
            event.ignore()
            return
        if not self._grab_armed:
            if not self._past_drag_threshold(event):
                event.accept()  # still a click, as far as anyone can tell
                return
            self._arm_gap_grab(event)
        if not self._undo_captured:
            self._undo_captured = True
            self._timeline.parent_sequencer._capture_undo()
        dx = event.scenePos().x() - self._drag_origin_x
        ppu = self._timeline._pixels_per_unit
        dt = dx / ppu if ppu else 0

        if self._drag_mode == "right":
            new_end = DraggableItemMixin.snap_time(
                self._drag_origin_end + dt, self._timeline
            )
            if new_end >= self._start:
                self.prepareGeometryChange()
                self._end = new_end
                self._update_tooltip()
                self.update()
        elif self._drag_mode == "left":
            new_start = DraggableItemMixin.snap_time(
                self._drag_origin_start + dt, self._timeline
            )
            if self._tail:
                # A tail handle has no right edge to clamp against — it IS
                # the end of the timeline.  Clamping it against ``_end``
                # (which equals ``_start`` on a zero-width tail) would let
                # the last shot shrink but never grow.  Drag both edges so
                # the handle simply follows the cursor.
                self.prepareGeometryChange()
                self._start = self._end = new_start
                self._update_tooltip()
                self.update()
            elif new_start <= self._end:
                self.prepareGeometryChange()
                self._start = new_start
                self._update_tooltip()
                self.update()
        elif self._drag_mode == "move":
            span = self._drag_origin_end - self._drag_origin_start
            new_start = DraggableItemMixin.snap_time(
                self._drag_origin_start + dt, self._timeline
            )
            self.prepareGeometryChange()
            self._start = new_start
            self._end = new_start + span
            self._update_tooltip()
            self.update()
        self._update_gap_drag_tooltip(event.scenePos())
        event.accept()

    def _gap_drag_frame(self) -> float:
        if self._drag_mode == "right":
            return float(self._end)
        return float(self._start)

    def _gap_drag_label(self) -> str:
        """``"<verb> <frame>"`` -- what this drag does under the modifiers
        recorded at press, so the gesture reads at the cursor."""
        sq = self._timeline.parent_sequencer
        if self._drag_mode == "move":
            verb = "Slide gap"
        elif sq.ctrl_held_at_press:
            verb = "Trim"
        elif sq.shift_held_at_press:
            verb = "Retime"
        else:
            verb = "Slide"
        return f"{verb} {FrameTooltip.format_frame(self._gap_drag_frame())}"

    def _show_gap_drag_tooltip(self, scene_pos):
        self._drag_tooltip.show(
            self.scene(),
            scene_pos,
            label=self._gap_drag_label(),
            color=self._line_color.name(),
        )

    def _update_gap_drag_tooltip(self, scene_pos):
        self._drag_tooltip.update(scene_pos, label=self._gap_drag_label())

    def _is_drag_active(self) -> bool:
        return self._drag_mode is not None

    def _restore_drag_state(self) -> None:
        self.prepareGeometryChange()
        self._start = self._drag_origin_start
        self._end = self._drag_origin_end
        CursorManager.pop(self)  # no-op when the grab never armed
        self._drag_mode = None
        self._grab_armed = False
        self._update_tooltip()

    def mouseReleaseEvent(self, event):
        if self._drag_mode is not None:
            sq = self._timeline.parent_sequencer
            # The consumer rebuilds from here, retiring this item while Qt
            # is still inside the release -- safe because SequencerWidget
            # routes removals through ``ItemRetirement.retire`` (see _draggable).
            if self._drag_mode == "right":
                if abs(self._end - self._drag_origin_end) > 0.01:
                    sq.gap_resized.emit(self._drag_origin_end, self._end)
            elif self._drag_mode == "left":
                if abs(self._start - self._drag_origin_start) > 0.01:
                    sq.gap_left_resized.emit(self._drag_origin_start, self._start)
            elif self._drag_mode == "move":
                delta = self._start - self._drag_origin_start
                if abs(delta) > 0.01:
                    sq.gap_moved.emit(
                        self._drag_origin_start,
                        self._drag_origin_end,
                        self._start,
                        self._end,
                    )
            CursorManager.pop(self)  # no-op when the grab never armed
            self._drag_mode = None
            self._grab_armed = False
            self._update_tooltip()
            self._drag_tooltip.hide()
        event.accept()

    def contextMenuEvent(self, event):
        menu = MenuUtils._styled_menu()
        act_lock = act_lock_all = act_unlock_all = None
        if not self._tail:
            # A tail handle exposes no lock actions — it is a shot-end
            # handle, not a gap, and a "locked" tail would be an inert
            # last-shot handle backed by no persistable store state.
            act_lock = menu.addAction("Unlock Gap" if self._locked else "Lock Gap")
            menu.addSeparator()
            act_lock_all = menu.addAction("Lock All Gaps")
            act_unlock_all = menu.addAction("Unlock All Gaps")

        # Extensibility hook — let consumers add domain-specific actions
        sq = self._timeline.parent_sequencer
        sq.gap_menu_requested.emit(menu, self._start, self._end)
        if not menu.actions():
            return

        chosen = menu.exec_(MenuUtils._menu_exec_pos(event))
        if chosen is None or self.scene() is None:
            # Dismissed, or a rebuild retired this overlay while the menu's
            # nested event loop ran — a None==None match below would
            # otherwise toggle the lock on dismissal of a tail menu.
            return
        if chosen == act_lock:
            self._locked = not self._locked
            self._update_tooltip()
            self.update()
            sq.gap_lock_changed.emit(self._start, self._end, self._locked)
        elif chosen == act_lock_all:
            sq.gap_lock_all_requested.emit()
        elif chosen == act_unlock_all:
            sq.gap_unlock_all_requested.emit()

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        r = self._rect()
        if r.width() < 1:
            return
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        painter.save()
        painter.setClipRect(r)
        painter.fillRect(r, self._color)
        painter.fillRect(
            r, PatternRegistry.pattern_brush("diagonal", self._line_color, HATCH_SPARSE)
        )
        # Edge handle highlights
        w = r.width()
        hw = min(self._EDGE_WIDTH, w / 2)
        handle_alpha = self._base_alpha + 80 if self._hovered else self._base_alpha + 50
        handle_color = QtGui.QColor(self._line_color)
        handle_color.setAlpha(min(255, handle_alpha))
        painter.fillRect(QtCore.QRectF(r.left(), r.top(), hw, r.height()), handle_color)
        painter.fillRect(
            QtCore.QRectF(r.right() - hw, r.top(), hw, r.height()), handle_color
        )
        # Draw gap frame count label if wide enough
        if w > 30:
            label = str(self._gap_frames)
            font = painter.font()
            font.setPixelSize(10)
            painter.setFont(font)
            text_color = QtGui.QColor("#dddddd" if self._hovered else "#aaaaaa")
            painter.setPen(text_color)
            painter.drawText(r, QtCore.Qt.AlignCenter, label)
            # Paint lock icon to right of label when locked
            if self._locked and w > 40:
                self._paint_lock_icon(painter, r, text_color)
        painter.restore()

    def _paint_lock_icon(self, painter, rect, fg):
        """Draw a small lock glyph centered above the frame-count label."""
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        icon_w, icon_h = 8, 10  # body(6) + shackle(4)
        ix = rect.center().x() - icon_w / 2
        iy = rect.center().y() - icon_h - 2  # just above the centered text
        painter.setPen(QtGui.QPen(fg, 1.2))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawArc(QtCore.QRectF(ix + 1, iy, 6, 6), 0 * 16, 180 * 16)
        painter.setBrush(fg)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(QtCore.QRectF(ix, iy + 4, 8, 6))
        painter.restore()


# ---------------------------------------------------------------------------
#  RangeHighlightItem
# ---------------------------------------------------------------------------
_RANGE_HANDLE_WIDTH = 4  # pixels from edge that activates resize cursor


class RangeHighlightItem(DraggableItemMixin, QtWidgets.QGraphicsItem):
    """A semi-transparent rectangle highlighting a time range on the timeline.

    Supports dragging (move) and edge-handle resizing.  Sits behind clips
    (``zValue = -1``) so it acts as a tinted background region.
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
    def sync(self):
        self.prepareGeometryChange()
        self.update()

    def _rect(self) -> QtCore.QRectF:
        """Compute the painted rectangle from current range and track layout.

        Starts at ``_content_top`` -- the highlight stays clear of the whole
        header; what shares its accent up there is the shot lane's band.
        """
        tl = self._timeline
        sq = tl.parent_sequencer
        x0 = tl.time_to_x(self._start)
        x1 = tl.time_to_x(self._end)
        top = sq._content_top
        h = max(sq._total_row_height(), _SHOT_LANE_HEIGHT)
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
        # the selected shot's extent legible without brightening the fill and
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
        item.  Exposed so the SHOT LANE can offer the same three grabs: the
        shot's bounds and extent are drawn up there on its band, so that is
        where a user reaches for them, but the item's own hit area stops at
        ``_content_top`` and must keep doing so -- reaching it up into the
        header means a view-dependent ``boundingRect``, which re-enters the
        scene index on scroll and dies natively.  The view drives the drag
        through :meth:`begin_edge_drag` instead.
        """
        tl = self._timeline
        for edge, t in (("left", self._start), ("right", self._end)):
            if abs(scene_x - tl.time_to_x(t)) <= _RANGE_HANDLE_WIDTH:
                return edge
        if tl.time_to_x(self._start) <= scene_x <= tl.time_to_x(self._end):
            return "move"
        return ""

    def begin_edge_drag(self, edge: str, scene_x: float) -> None:
        """Start a bound drag from outside the item (the shot lane's handles).

        The same state ``mousePressEvent`` sets, so every later step --
        move, release, cancel, undo capture -- is the one code path.  The
        caller has recorded the press modifiers (``record_press_modifiers``).
        """
        self._grab_zone = edge
        self._drag_mode = edge
        self._drag_origin_x = scene_x
        self._drag_origin_start = self._start
        self._drag_origin_end = self._end
        self._undo_captured = False
        self._show_range_drag_tooltip(QtCore.QPointF(scene_x, self._rect().top()))

    def _drag_verb(self) -> str:
        """What this drag does, as the consumers apply the modifiers recorded
        at press: a plain bound drag resizes the shot (the neighbours ripple
        to keep the gaps), Ctrl trims the bound alone, Shift retimes.  A
        body/band drag moves the shot."""
        sq = self._timeline.parent_sequencer
        if self._drag_mode == "move":
            return "Move"
        if sq.shift_held_at_press:
            return "Retime"
        return "Trim" if sq.ctrl_held_at_press else "Resize"

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
            # the marquee, so advertising a drag here would be a lie.  The
            # shot lane offers the move, and shows the hand.
            self.unsetCursor()

    # -- mouse interaction --------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        zone = self._hit_zone(event.pos())
        # The BODY never claims a press, with or without Shift.  This item
        # spans the whole active shot -- every track row, for the shot's full
        # width -- so claiming Shift+drag here made the timeline's additive
        # marquee impossible anywhere inside the current shot, which is where
        # the user is working.  Marquee wins; the shot is moved by dragging
        # its band on the shot lane, where its bounds are already drawn and
        # nothing else competes for the gesture.
        if zone == "move":
            event.ignore()
            return
        # If a clip item exists under the cursor, defer to it instead of
        # capturing the press on the range highlight.  This ensures clip
        # handles are always preferred over the range-highlight handles
        # when they overlap at the same screen position.
        from uitk.widgets.sequencer._clip import ClipItem

        for item in self._timeline._scene.items(event.scenePos()):
            if isinstance(item, ClipItem) and item is not self:
                event.ignore()
                return
        # Same deferral for an unlocked gap overlay's PAINTED rect: those
        # pixels are drawn as the gap's edge handle, so they must deliver
        # gap semantics (no ripple).  Without this, which of two overlapping
        # handles answers a plain edge drag — this one ripples the timeline,
        # the gap's does not — was decided by z-order and ~4px of cursor.
        for item in self._timeline._scene.items(event.scenePos()):
            if (
                isinstance(item, _GapOverlayItem)
                and not item._locked
                and item._rect().contains(event.scenePos())
            ):
                event.ignore()
                return
        sq = self._timeline.parent_sequencer
        sq.record_press_modifiers(event.modifiers())
        self._grab_zone = zone
        self._drag_mode = zone
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
        if not self._undo_captured:
            self._undo_captured = True
            self._timeline.parent_sequencer._capture_undo()
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
        elif self._drag_mode == "left":
            new_start = DraggableItemMixin.snap_time(
                self._drag_origin_start + dt, self._timeline
            )
            if new_start < self._end:
                self._start = new_start
        elif self._drag_mode == "right":
            new_end = DraggableItemMixin.snap_time(
                self._drag_origin_end + dt, self._timeline
            )
            if new_end > self._start:
                self._end = new_end

        self.sync()
        self._update_range_drag_tooltip(event.scenePos())
        event.accept()

    def update_edge_drag(self, scene_x: float) -> None:
        """Advance a drag begun with :meth:`begin_edge_drag`."""
        if self._drag_mode is None:
            return
        if not self._undo_captured:
            self._undo_captured = True
            self._timeline.parent_sequencer._capture_undo()
        dt = (scene_x - self._drag_origin_x) / (self._timeline._pixels_per_unit or 1)
        if self._drag_mode == "left":
            new_start = DraggableItemMixin.snap_time(
                self._drag_origin_start + dt, self._timeline
            )
            if new_start < self._end:
                self._start = new_start
        elif self._drag_mode == "right":
            new_end = DraggableItemMixin.snap_time(
                self._drag_origin_end + dt, self._timeline
            )
            if new_end > self._start:
                self._end = new_end
        elif self._drag_mode == "move":
            # Both bounds by the same snapped delta, so the shot's DURATION
            # is untouched -- measuring the delta off the start and adding it
            # to the raw end would let rounding stretch the shot a frame.
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
            # scrollable extent (a shot grown past the end, or back
            # before frame 0) -- widen it before the consumer reacts.
            sq._refresh_extent()
            sq.range_highlight_changed.emit(self._start, self._end)
        CursorManager.pop(self)
        self._drag_mode = None
        self._drag_tooltip.hide()
        return moved

    def _range_drag_frame(self) -> float:
        # The bound under the hand: a plain edge grab moves the whole shot,
        # but the frame that reads at the cursor is still the edge grabbed.
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
        # Emit only on an actual change (mirrors the gap overlay's 0.01
        # gate) — a zero-motion click otherwise triggers a full save +
        # resize + widget rebuild in the consumer.
        self.finish_edge_drag()
        event.accept()
