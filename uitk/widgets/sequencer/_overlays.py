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
    _styled_menu,
    _menu_exec_pos,
    hatch_brush,
    HATCH_SPARSE,
)

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
#  _GapOverlayItem
# ---------------------------------------------------------------------------


class _GapOverlayItem(QtWidgets.QGraphicsItem):
    """Diagonal-hatch overlay for gaps between shots.

    Displays the gap duration as centered text and a tooltip on hover.
    Supports three drag modes:
    - **Right edge**: resize gap (shifts the next shot and all downstream).
    - **Left edge**: resize gap from the left (shifts the prev shot end).
    - **Body** (Shift+drag): slide the cut point between adjacent shots,
      keeping gap size constant.
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
    ):
        super().__init__()
        self._timeline = timeline
        self._start = start
        self._end = end
        self._base_alpha = alpha
        self._color = QtGui.QColor(color)
        self._color.setAlpha(alpha)
        self._line_color = QtGui.QColor(color)
        self._line_color.setAlpha(min(255, alpha + 40))
        self._hovered = False
        self._locked = locked
        self._drag_mode: Optional[str] = None  # "left", "right", "move", or None
        self._drag_origin_x: float = 0.0
        self._drag_origin_start: float = 0.0
        self._drag_origin_end: float = 0.0
        self.setZValue(-3)
        self.setAcceptHoverEvents(True)
        self._gap_frames = int(round(end - start))
        self._update_tooltip()

    def _update_tooltip(self):
        self._gap_frames = max(0, int(round(self._end - self._start)))
        lock_label = " [Locked]" if self._locked else ""
        mode = self._drag_mode
        if mode == "left":
            frame = int(round(self._start))
            info = f"◀ Left edge → frame {frame}"
        elif mode == "right":
            frame = int(round(self._end))
            info = f"Right edge ▶ → frame {frame}"
        elif mode == "move":
            info = f"Sliding → {int(round(self._start))}–{int(round(self._end))}"
        else:
            info = "Drag edges to resize · Shift+drag body to slide"
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
        r = self._rect()
        local_x = pos.x() - r.left()
        if local_x <= self._EDGE_WIDTH:
            return "left"
        if local_x >= r.width() - self._EDGE_WIDTH:
            return "right"
        return "body"

    def _snap(self, value: float) -> float:
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & QtCore.Qt.ControlModifier:
            return round(value)
        interval = self._timeline.parent_sequencer.snap_interval
        if interval > 0:
            return round(value / interval) * interval
        return value

    def hoverEnterEvent(self, event):
        self._hovered = True
        self._color.setAlpha(min(255, self._base_alpha + 50))
        self._line_color.setAlpha(min(255, self._base_alpha + 90))
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self._color.setAlpha(self._base_alpha)
        self._line_color.setAlpha(min(255, self._base_alpha + 40))
        self.setCursor(QtCore.Qt.ArrowCursor)
        self.update()

    def hoverMoveEvent(self, event):
        if self._clip_at(event.scenePos()):
            self.setCursor(QtCore.Qt.ArrowCursor)
            return
        zone = self._hit_zone(event.pos())
        if zone in ("left", "right"):
            self.setCursor(QtCore.Qt.SizeHorCursor)
        elif event.modifiers() & QtCore.Qt.ShiftModifier:
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
        zone = self._hit_zone(event.pos())
        if zone == "body":
            if not (event.modifiers() & QtCore.Qt.ShiftModifier):
                event.ignore()
                return
            self._drag_mode = "move"
            self.setCursor(QtCore.Qt.ClosedHandCursor)
        else:
            self._drag_mode = zone  # "left" or "right"
        self._drag_origin_x = event.scenePos().x()
        self._drag_origin_start = self._start
        self._drag_origin_end = self._end
        sq = self._timeline.parent_sequencer
        sq._shift_at_press = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
        sq._capture_undo()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_mode is None:
            event.ignore()
            return
        dx = event.scenePos().x() - self._drag_origin_x
        ppu = self._timeline._pixels_per_unit
        dt = dx / ppu if ppu else 0

        if self._drag_mode == "right":
            new_end = self._snap(self._drag_origin_end + dt)
            if new_end >= self._start:
                self.prepareGeometryChange()
                self._end = new_end
                self._update_tooltip()
                self.update()
        elif self._drag_mode == "left":
            new_start = self._snap(self._drag_origin_start + dt)
            if new_start <= self._end:
                self.prepareGeometryChange()
                self._start = new_start
                self._update_tooltip()
                self.update()
        elif self._drag_mode == "move":
            span = self._drag_origin_end - self._drag_origin_start
            new_start = self._snap(self._drag_origin_start + dt)
            self.prepareGeometryChange()
            self._start = new_start
            self._end = new_start + span
            self._update_tooltip()
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_mode is not None:
            sq = self._timeline.parent_sequencer
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
            if self._drag_mode == "move":
                self.setCursor(QtCore.Qt.OpenHandCursor)
            self._drag_mode = None
            self._update_tooltip()
        event.accept()

    def contextMenuEvent(self, event):
        menu = _styled_menu()
        act_lock = menu.addAction("Unlock Gap" if self._locked else "Lock Gap")
        menu.addSeparator()
        act_lock_all = menu.addAction("Lock All Gaps")
        act_unlock_all = menu.addAction("Unlock All Gaps")

        # Extensibility hook — let consumers add domain-specific actions
        sq = self._timeline.parent_sequencer
        sq.gap_menu_requested.emit(menu, self._start, self._end)

        chosen = menu.exec_(_menu_exec_pos(event))
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
        painter.fillRect(r, hatch_brush(self._line_color, HATCH_SPARSE))
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
            label = (
                f"\U0001f512 {self._gap_frames}"
                if self._locked
                else str(self._gap_frames)
            )
            font = painter.font()
            font.setPixelSize(10)
            painter.setFont(font)
            text_color = QtGui.QColor("#dddddd" if self._hovered else "#aaaaaa")
            painter.setPen(text_color)
            painter.drawText(r, QtCore.Qt.AlignCenter, label)
        painter.restore()


# ---------------------------------------------------------------------------
#  RangeHighlightItem
# ---------------------------------------------------------------------------
_RANGE_HANDLE_WIDTH = 4  # pixels from edge that activates resize cursor


class RangeHighlightItem(QtWidgets.QGraphicsItem):
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
        self._drag_origin_x: float = 0.0
        self._drag_origin_start: float = 0.0
        self._drag_origin_end: float = 0.0
        self._locked: bool = False
        self.setZValue(-1)
        self.setAcceptHoverEvents(True)

    @property
    def locked(self) -> bool:
        return self._locked

    @locked.setter
    def locked(self, value: bool):
        self._locked = value
        if value:
            self.unsetCursor()

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
        """Compute the painted rectangle from current range and track layout."""
        tl = self._timeline
        sq = tl.parent_sequencer
        x0 = tl.time_to_x(self._start)
        x1 = tl.time_to_x(self._end)
        top = sq._content_top
        h = max(sq._total_row_height(), _SHOT_LANE_HEIGHT)
        return QtCore.QRectF(x0, top, x1 - x0, h)

    def boundingRect(self) -> QtCore.QRectF:
        r = self._rect()
        return r.adjusted(-_RANGE_HANDLE_WIDTH, 0, _RANGE_HANDLE_WIDTH, 0)

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

    # -- snapping helper ----------------------------------------------------
    def _snap(self, value: float) -> float:
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & QtCore.Qt.ControlModifier:
            return round(value)
        interval = self._timeline.parent_sequencer.snap_interval
        if interval > 0:
            return round(value / interval) * interval
        return value

    # -- hit zone -----------------------------------------------------------
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
        if self._locked:
            event.ignore()
            return
        zone = self._hit_zone(event.pos())
        if zone in ("left", "right"):
            self.setCursor(QtCore.Qt.SizeHorCursor)
        elif event.modifiers() & QtCore.Qt.ShiftModifier:
            self.setCursor(QtCore.Qt.OpenHandCursor)
        else:
            self.unsetCursor()

    # -- mouse interaction --------------------------------------------------
    def mousePressEvent(self, event):
        if self._locked:
            event.ignore()
            return
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        zone = self._hit_zone(event.pos())
        # Body clicks without Shift pass through for rubber-band selection;
        # Shift+click on the body activates move mode.
        if zone == "move":
            if not (event.modifiers() & QtCore.Qt.ShiftModifier):
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
        self._drag_mode = zone
        self._drag_origin_x = event.scenePos().x()
        self._drag_origin_start = self._start
        self._drag_origin_end = self._end
        sq = self._timeline.parent_sequencer
        sq._shift_at_press = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
        # Capture widget-level undo snapshot before drag begins
        sq._capture_undo()
        if self._drag_mode == "move":
            self.setCursor(QtCore.Qt.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._locked or self._drag_mode is None:
            event.ignore()
            return
        dx = event.scenePos().x() - self._drag_origin_x
        dt = (
            dx / self._timeline._pixels_per_unit
            if self._timeline._pixels_per_unit
            else 0
        )

        if self._drag_mode == "move":
            span = self._drag_origin_end - self._drag_origin_start
            new_start = self._snap(self._drag_origin_start + dt)
            self._start = new_start
            self._end = new_start + span
        elif self._drag_mode == "left":
            new_start = self._snap(self._drag_origin_start + dt)
            if new_start < self._end:
                self._start = new_start
        elif self._drag_mode == "right":
            new_end = self._snap(self._drag_origin_end + dt)
            if new_end > self._start:
                self._end = new_end

        self.sync()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._locked:
            event.ignore()
            return
        if self._drag_mode is not None:
            sq = self._timeline.parent_sequencer
            sq.range_highlight_changed.emit(self._start, self._end)
        if self._drag_mode == "move":
            self.setCursor(QtCore.Qt.OpenHandCursor)
        self._drag_mode = None
        event.accept()
