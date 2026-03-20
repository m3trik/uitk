# !/usr/bin/python
# coding=utf-8
"""An NLE-style timeline sequencer widget.

Provides a split-view with track labels on the left and a QGraphicsView
timeline on the right.  Clips can be dragged to reposition, and their
edges can be dragged to resize.

Example
-------
>>> from uitk.widgets.sequencer import SequencerWidget
>>> w = SequencerWidget()
>>> t = w.add_track("Arrow 01")
>>> w.add_clip(t, start=100, duration=50, label="Fade In/Out")
>>> w.show()
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qtpy import QtWidgets, QtGui, QtCore

from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.settings_manager import SettingsManager
from uitk.widgets.mixins.shortcuts import ShortcutManager


# ---------------------------------------------------------------------------
#  Data
# ---------------------------------------------------------------------------
@dataclass
class ClipData:
    """Lightweight data record for a single clip on a track."""

    clip_id: int
    track_id: int
    start: float
    duration: float
    label: str = ""
    color: Optional[str] = None
    locked: bool = False
    sub_row: str = ""  # empty = main track row, non-empty = expanded sub-row name
    data: Dict[str, Any] = field(default_factory=dict)

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class TrackData:
    """Lightweight data record for a track row."""

    track_id: int
    name: str
    clips: List[int] = field(default_factory=list)


@dataclass
class MarkerData:
    """Lightweight data record for a timeline marker."""

    marker_id: int
    time: float
    note: str = ""
    color: str = "#E8A84A"
    draggable: bool = True
    style: str = "triangle"  # triangle | diamond | line | bracket
    line_style: str = "dashed"  # dashed | solid | dotted | none
    opacity: float = 1.0


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
_TRACK_HEIGHT = 28
_SUB_ROW_HEIGHT = 14  # default height for expanded attribute sub-rows
_TRACK_PADDING = 2
_RULER_HEIGHT = 24
_HANDLE_WIDTH = 5  # pixels from edge that activates resize cursor
_MIN_CLIP_DURATION = 1.0
_MIN_POINT_CLIP_WIDTH = 4  # minimum pixel width for zero-duration clips
_DEFAULT_CLIP_COLORS = [
    "#5B8BD4",
    "#6EBF6E",
    "#D4A65B",
    "#C45C5C",
    "#8E6FBF",
    "#5BBFB4",
    "#BF6E8E",
    "#8EB05B",
]

# Attribute color configuration
_COMMON_ATTRIBUTES = [
    "translateX",
    "translateY",
    "translateZ",
    "rotateX",
    "rotateY",
    "rotateZ",
    "scaleX",
    "scaleY",
    "scaleZ",
    "visibility",
]

_DEFAULT_ATTRIBUTE_COLORS = {
    "translateX": "#E06666",
    "translateY": "#6AA84F",
    "translateZ": "#6FA8DC",
    "rotateX": "#CC4125",
    "rotateY": "#38761D",
    "rotateZ": "#3D85C6",
    "scaleX": "#F6B26B",
    "scaleY": "#93C47D",
    "scaleZ": "#76A5AF",
    "visibility": "#FFD966",
}


# ---------------------------------------------------------------------------
#  ClipItem
# ---------------------------------------------------------------------------
class ClipItem(QtWidgets.QGraphicsRectItem):
    """A draggable, resizable rectangle representing one clip on the timeline."""

    def __init__(self, clip_data: ClipData, timeline: "TimelineView"):
        super().__init__()
        self._data = clip_data
        self._timeline = timeline
        self._drag_mode = None  # "move", "resize_left", "resize_right"
        self._drag_origin_x = 0.0
        self._drag_origin_start = 0.0
        self._drag_origin_duration = 0.0
        self._drag_peers: list = []  # [(ClipItem, original_start), ...]
        self._waveform_pixmap: Optional[QtGui.QPixmap] = None
        self._waveform_pixmap_size: Optional[tuple] = None
        self.setAcceptHoverEvents(True)
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        # Dimmed (non-active shot) clips sit behind active clips
        if clip_data.data.get("dimmed"):
            self.setZValue(-0.5)
        # Sub-row clips show label as tooltip instead of inline text
        if clip_data.sub_row and clip_data.label:
            self.setToolTip(clip_data.label)
        self._sync_geometry()

    def _snap(self, value: float) -> float:
        """Snap *value* to the nearest grid interval if snapping is enabled.

        Holding **Ctrl** while dragging forces the interval to 1 (per-frame).
        """
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & QtCore.Qt.ControlModifier:
            return round(value)
        interval = self._timeline.parent_sequencer.snap_interval
        if interval > 0:
            return round(value / interval) * interval
        return value

    # -- data access --------------------------------------------------------
    @property
    def clip_data(self) -> ClipData:
        return self._data

    # -- geometry sync ------------------------------------------------------
    def _sync_geometry(self):
        """Recalculate rect from data using the timeline's mapper."""
        tl = self._timeline
        x = tl.time_to_x(self._data.start)
        w = tl.time_to_x(self._data.start + self._data.duration) - x
        widget = tl.parent_sequencer
        track_y, row_h = widget._row_position(self._data.track_id, self._data.sub_row)
        # Zero-duration (point) clips get a minimum visual width, centered
        if w < _MIN_POINT_CLIP_WIDTH:
            x -= (_MIN_POINT_CLIP_WIDTH - w) / 2.0
            w = _MIN_POINT_CLIP_WIDTH
        new_rect = QtCore.QRectF(x, track_y, max(w, 1), row_h)
        # Invalidate waveform cache when width changes (zoom/resize)
        if self.rect().width() != new_rect.width():
            self._waveform_pixmap = None
        self.setRect(new_rect)

    def _track_index(self) -> int:
        widget = self._timeline.parent_sequencer
        for i, td in enumerate(widget._tracks):
            if td.track_id == self._data.track_id:
                return i
        return 0

    def _resolve_color(self) -> QtGui.QColor:
        """Resolve clip color from attributes.

        Uses the attribute color map only when every attribute on the clip
        resolves to the *same* color (e.g. a single-attribute clip or a
        group where all attrs share a color).  Mixed-attribute clips stay
        neutral so the color scheme remains meaningful.
        """
        attrs = self._data.data.get("attributes")
        if attrs:
            color_map = self._timeline.parent_sequencer.attribute_colors
            matched = {color_map[a] for a in attrs if a in color_map}
            if len(matched) == 1:
                return QtGui.QColor(matched.pop())
        return QtGui.QColor(self._data.color or "#CCCCCC")

    @staticmethod
    def _foreground_for(color: QtGui.QColor) -> QtGui.QColor:
        """Return black or white depending on the background luminance."""
        lum = 0.299 * color.redF() + 0.587 * color.greenF() + 0.114 * color.blueF()
        return QtGui.QColor("#1E1E1E") if lum > 0.55 else QtGui.QColor("#FFFFFF")

    # -- painting -----------------------------------------------------------
    def paint(self, painter: QtGui.QPainter, option, widget=None):
        rect = self.rect()
        color = self._resolve_color()
        if self._data.data.get("dimmed"):
            color = color.darker(250)
        if self.isSelected():
            color = color.lighter(130)

        fg = self._foreground_for(color)

        painter.setBrush(color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(rect)

        # Waveform overlay (if envelope data is present)
        waveform = self._data.data.get("waveform")
        if waveform and rect.width() > 4:
            self._paint_waveform(painter, rect, waveform, color)

        # Label
        if rect.width() > 30:
            painter.setPen(fg)
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            text_rect = rect.adjusted(6, 0, -6, 0)
            painter.drawText(
                text_rect,
                QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                self._data.label,
            )

        # Lock indicator (skip for read-only clips from non-active shots)
        if (
            self._data.locked
            and not self._data.data.get("read_only")
            and rect.width() > 14
            and rect.height() > 10
        ):
            self._paint_lock_icon(painter, rect, fg)

    def _paint_lock_icon(self, painter, rect, fg=None):
        """Draw a small lock glyph at the right edge of the clip."""
        if fg is None:
            fg = QtGui.QColor("#FFFFFF")
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        # Position at top-right
        ix = rect.right() - 12
        iy = rect.top() + 3
        painter.setPen(QtGui.QPen(fg, 1.2))
        painter.setBrush(QtCore.Qt.NoBrush)
        # Shackle arc
        painter.drawArc(
            QtCore.QRectF(ix + 1, iy, 6, 6),
            0 * 16,
            180 * 16,
        )
        # Body rectangle
        painter.setBrush(fg)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(QtCore.QRectF(ix, iy + 4, 8, 6))
        painter.restore()

    def _paint_waveform(self, painter, rect, waveform, base_color):
        """Render a waveform envelope inside the clip rectangle.

        The waveform is pre-rendered to a QPixmap and cached.  The cache
        is invalidated when the clip width changes (zoom/resize).
        """
        n_bins = len(waveform)
        if n_bins == 0:
            return

        w = int(rect.width() - 2)
        h = int(rect.height() - 4)
        if w < 1 or h < 1:
            return

        size_key = (w, h)
        if self._waveform_pixmap is None or self._waveform_pixmap_size != size_key:
            self._waveform_pixmap = self._render_waveform_pixmap(
                waveform, w, h, base_color
            )
            self._waveform_pixmap_size = size_key

        painter.drawPixmap(
            QtCore.QPointF(rect.x() + 1, rect.y() + 2),
            self._waveform_pixmap,
        )

    @staticmethod
    def _render_waveform_pixmap(waveform, w, h, base_color):
        """Pre-render waveform lines into a transparent QPixmap."""
        pixmap = QtGui.QPixmap(w, h)
        pixmap.fill(QtCore.Qt.transparent)

        n_bins = len(waveform)
        cy = h / 2.0

        wave_color = base_color.lighter(170)
        wave_color.setAlpha(200)

        p = QtGui.QPainter(pixmap)
        p.setPen(QtGui.QPen(wave_color, 1))

        for col in range(w):
            idx = min(int(col * n_bins / w), n_bins - 1)
            lo, hi = waveform[idx]
            y_top = cy - hi * (h / 2)
            y_bot = cy - lo * (h / 2)
            p.drawLine(QtCore.QPointF(col, y_top), QtCore.QPointF(col, y_bot))

        p.end()
        return pixmap

    # -- hover cursor -------------------------------------------------------
    def hoverMoveEvent(self, event):
        if self._data.locked:
            self.setCursor(QtCore.Qt.ArrowCursor)
            super().hoverMoveEvent(event)
            return
        zone = self._hit_zone(event.pos())
        if zone in ("resize_left", "resize_right"):
            self.setCursor(QtCore.Qt.SizeHorCursor)
        else:
            self.setCursor(QtCore.Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    # -- drag interaction ---------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if self._data.locked:
                # Allow selection but prevent drag
                super().mousePressEvent(event)
                return
            self._drag_mode = self._hit_zone(event.pos())
            self._drag_origin_x = event.scenePos().x()
            self._drag_origin_start = self._data.start
            self._drag_origin_duration = self._data.duration
            sq = self._timeline.parent_sequencer
            sq._shift_at_press = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
            # Capture peer clips for group move
            self._drag_peers = []
            if self._drag_mode == "move" and self.isSelected():
                for item in self._timeline._scene.selectedItems():
                    if (
                        isinstance(item, ClipItem)
                        and item is not self
                        and not item._data.locked
                    ):
                        self._drag_peers.append((item, item._data.start))
            # Capture pre-drag snapshot for undo
            self._timeline.parent_sequencer._capture_undo()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_mode is None:
            return super().mouseMoveEvent(event)

        tl = self._timeline
        dx_time = tl.x_to_time(event.scenePos().x()) - tl.x_to_time(self._drag_origin_x)

        if self._drag_mode == "move":
            new_start = self._snap(max(0.0, self._drag_origin_start + dx_time))
            self._data.start = new_start
            # Move peer clips by the same snapped delta
            snapped_delta = new_start - self._drag_origin_start
            for peer, origin_start in self._drag_peers:
                peer._data.start = max(0.0, origin_start + snapped_delta)
                peer._sync_geometry()
                peer.update()

        elif self._drag_mode == "resize_left":
            new_start = min(
                self._drag_origin_start + dx_time,
                self._drag_origin_start
                + self._drag_origin_duration
                - _MIN_CLIP_DURATION,
            )
            new_start = self._snap(max(0.0, new_start))
            delta = new_start - self._drag_origin_start
            self._data.start = new_start
            self._data.duration = self._drag_origin_duration - delta

        elif self._drag_mode == "resize_right":
            raw_end = self._drag_origin_start + self._drag_origin_duration + dx_time
            snapped_end = self._snap(raw_end)
            new_dur = max(_MIN_CLIP_DURATION, snapped_end - self._data.start)
            self._data.duration = new_dur

        self._sync_geometry()
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._drag_mode:
            mode = self._drag_mode
            peers = self._drag_peers
            self._drag_mode = None
            self._drag_peers = []
            self.unsetCursor()
            widget = self._timeline.parent_sequencer
            if mode == "move":
                if peers:
                    moves = [(self._data.clip_id, self._data.start)]
                    for peer, _ in peers:
                        moves.append((peer._data.clip_id, peer._data.start))
                    widget.clips_batch_moved.emit(moves)
                else:
                    widget.clip_moved.emit(self._data.clip_id, self._data.start)
            else:
                widget.clip_resized.emit(
                    self._data.clip_id, self._data.start, self._data.duration
                )
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # -- context menu -------------------------------------------------------
    def contextMenuEvent(self, event):
        if self._data.data.get("read_only"):
            event.ignore()
            return
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(
            "QMenu { background:#333; color:#CCC; }"
            "QMenu::item:selected { background:#555; }"
        )

        # Lock / Unlock
        if self._data.locked:
            action_lock = menu.addAction("Unlock")
        else:
            action_lock = menu.addAction("Lock")

        # Rename
        action_rename = menu.addAction("Rename")
        if self._data.locked:
            action_rename.setEnabled(False)

        chosen = menu.exec_(
            event.screenPos() if hasattr(event, "screenPos") else QtGui.QCursor.pos()
        )
        if chosen == action_lock:
            self._data.locked = not self._data.locked
            self.update()
            widget = self._timeline.parent_sequencer
            widget.clip_locked.emit(self._data.clip_id, self._data.locked)
        elif chosen == action_rename:
            self._start_inline_rename()

    # -- double-click to rename --------------------------------------------
    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if self._data.locked:
                return
            self._start_inline_rename()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _start_inline_rename(self):
        """Spawn a QLineEdit proxy widget over the clip for inline renaming."""
        rect = self.rect()
        edit = QtWidgets.QLineEdit()
        edit.setText(self._data.label)
        edit.selectAll()
        edit.setFrame(False)
        edit.setStyleSheet(
            "background:#333; color:#FFF; padding:0 4px; font-size:10px;"
        )
        edit.setFixedHeight(int(rect.height()))

        proxy = self.scene().addWidget(edit)
        proxy.setPos(rect.x(), rect.y())
        proxy.setZValue(100)
        edit.setFixedWidth(max(int(rect.width()), 60))
        edit.setFocus()

        finished = [False]

        def _finish():
            if finished[0]:
                return
            finished[0] = True
            new_label = edit.text()
            self._data.label = new_label
            self.update()
            widget = self._timeline.parent_sequencer
            widget.clip_renamed.emit(self._data.clip_id, new_label)
            if proxy.scene():
                proxy.scene().removeItem(proxy)

        edit.editingFinished.connect(_finish)

    # -- utilities ----------------------------------------------------------
    def _hit_zone(self, pos) -> str:
        rect = self.rect()
        local_x = pos.x() - rect.x()
        if local_x <= _HANDLE_WIDTH and self._data.data.get("resizable_left", True):
            return "resize_left"
        elif local_x >= rect.width() - _HANDLE_WIDTH and self._data.data.get(
            "resizable_right", True
        ):
            return "resize_right"
        return "move"


# ---------------------------------------------------------------------------
#  RangeHighlightItem
# ---------------------------------------------------------------------------
_RANGE_HANDLE_WIDTH = 4  # pixels from edge that activates resize cursor


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
        x0 = tl.time_to_x(self._start)
        x1 = tl.time_to_x(self._end)
        h = tl.parent_sequencer._total_row_height()
        return QtCore.QRectF(x0, _RULER_HEIGHT, x1 - x0, h)

    def boundingRect(self) -> QtCore.QRectF:
        return self._rect()

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        r = self._rect()
        if r.width() < 1:
            return
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        painter.fillRect(r, self._color)


class _GapOverlayItem(QtWidgets.QGraphicsItem):
    """Diagonal-hatch overlay for gaps between shots.

    Displays the gap duration as centered text and a tooltip on hover.
    Supports right-edge dragging to resize the gap (shifts the next shot).
    """

    _EDGE_WIDTH = 6  # px from right edge that triggers resize cursor

    def __init__(self, timeline, start: float, end: float, color: str, alpha: int):
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
        self._drag_mode: Optional[str] = None  # "right" or None
        self._drag_origin_x: float = 0.0
        self._drag_origin_end: float = 0.0
        self.setZValue(-3)
        self.setAcceptHoverEvents(True)
        self._gap_frames = int(round(end - start))
        self._update_tooltip()

    def _update_tooltip(self):
        self._gap_frames = max(0, int(round(self._end - self._start)))
        self.setToolTip(
            f"Gap: {self._gap_frames} frame{'s' if self._gap_frames != 1 else ''}"
            "\nDrag right edge to resize"
        )

    def _rect(self) -> QtCore.QRectF:
        tl = self._timeline
        x0 = tl.time_to_x(self._start)
        x1 = tl.time_to_x(self._end)
        h = tl.parent_sequencer._total_row_height()
        return QtCore.QRectF(x0, _RULER_HEIGHT, x1 - x0, h)

    def boundingRect(self) -> QtCore.QRectF:
        r = self._rect()
        return r.adjusted(0, 0, self._EDGE_WIDTH, 0)

    def _hit_zone(self, pos: QtCore.QPointF) -> str:
        r = self._rect()
        local_x = pos.x() - r.left()
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
        zone = self._hit_zone(event.pos())
        if zone == "right":
            self.setCursor(QtCore.Qt.SizeHorCursor)
        else:
            self.setCursor(QtCore.Qt.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        zone = self._hit_zone(event.pos())
        if zone != "right":
            event.ignore()
            return
        self._drag_mode = "right"
        self._drag_origin_x = event.scenePos().x()
        self._drag_origin_end = self._end
        # Capture undo snapshot before drag
        sq = self._timeline.parent_sequencer
        sq._capture_undo()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_mode is None:
            event.ignore()
            return
        dx = event.scenePos().x() - self._drag_origin_x
        ppu = self._timeline._pixels_per_unit
        dt = dx / ppu if ppu else 0
        new_end = self._snap(self._drag_origin_end + dt)
        # Don't allow gap smaller than 0 frames
        if new_end > self._start:
            self.prepareGeometryChange()
            self._end = new_end
            self._update_tooltip()
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_mode is not None:
            original_end = self._drag_origin_end
            new_end = self._end
            if abs(new_end - original_end) > 0.01:
                sq = self._timeline.parent_sequencer
                sq.gap_resized.emit(original_end, new_end)
            self._drag_mode = None
        event.accept()

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        r = self._rect()
        if r.width() < 1:
            return
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        painter.save()
        painter.setClipRect(r)
        painter.fillRect(r, self._color)
        pen = QtGui.QPen(self._line_color, 1)
        painter.setPen(pen)
        spacing = 12
        x0, y0, w, h = r.x(), r.y(), r.width(), r.height()
        # Diagonal lines from bottom-left to top-right
        d = int(w + h)
        for i in range(-int(h), d, spacing):
            painter.drawLine(
                QtCore.QPointF(x0 + i, y0 + h),
                QtCore.QPointF(x0 + i + h, y0),
            )
        # Right edge handle highlight
        hw = min(self._EDGE_WIDTH, w / 2)
        handle_alpha = self._base_alpha + 80 if self._hovered else self._base_alpha + 50
        handle_color = QtGui.QColor(self._line_color)
        handle_color.setAlpha(min(255, handle_alpha))
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
        painter.restore()


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
        x0 = tl.time_to_x(self._start)
        x1 = tl.time_to_x(self._end)
        h = tl.parent_sequencer._total_row_height()
        return QtCore.QRectF(x0, _RULER_HEIGHT, x1 - x0, h)

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


# ---------------------------------------------------------------------------
#  RulerItem
# ---------------------------------------------------------------------------
class RulerItem(QtWidgets.QGraphicsItem):
    """Draws the frame-number ruler at the top of the timeline."""

    def __init__(self, timeline: "TimelineView"):
        super().__init__()
        self._timeline = timeline
        self.setZValue(10)

    def boundingRect(self):
        # Use a large static width; paint() computes the visible range
        # from the viewport so ticks always render correctly regardless.
        return QtCore.QRectF(0, 0, 100000, _RULER_HEIGHT)

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        tl = self._timeline
        ppu = tl.pixels_per_unit

        # Determine the visible X-range in scene coordinates from the
        # viewport so ticks are always drawn across whatever is visible.
        vp_rect = tl.mapToScene(tl.viewport().rect()).boundingRect()
        vis_left = vp_rect.left()
        vis_right = vp_rect.right()

        # Background — cover the full visible width
        painter.setBrush(QtGui.QColor("#2B2B2B"))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(
            QtCore.QRectF(vis_left, 0, vis_right - vis_left, _RULER_HEIGHT)
        )

        if ppu <= 0:
            return

        # Determine tick spacing in domain units
        raw = 60.0 / ppu
        interval = max(1, self._nice_interval(raw))

        painter.setPen(QtGui.QColor("#999999"))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        # Convert visible pixel range to time range
        t_start = tl.x_to_time(vis_left)
        t_end = tl.x_to_time(vis_right)

        # Snap to the nearest interval boundary
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

    @staticmethod
    def _nice_interval(raw: float) -> int:
        for candidate in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
            if candidate >= raw:
                return candidate
        return int(raw)


# ---------------------------------------------------------------------------
#  PlayheadItem
# ---------------------------------------------------------------------------
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
        self._time = max(0.0, value)
        t = self._time
        self._label = str(int(t)) if t == int(t) else f"{t:.1f}"
        self._update_badge_width()
        self.sync()

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


# ---------------------------------------------------------------------------
#  MarkerItem
# ---------------------------------------------------------------------------
_MARKER_TRI_SIZE = 8  # size of the triangle pennant in pixels


class MarkerItem(QtWidgets.QGraphicsItem):
    """A named marker on the timeline: triangle at the ruler + dashed line."""

    def __init__(self, marker_data: MarkerData, timeline: "TimelineView"):
        super().__init__()
        self._data = marker_data
        self._timeline = timeline
        self._drag_active = False
        self._drag_origin_x = 0.0
        self._drag_origin_time = 0.0
        self._drag_tooltip: Optional[QtWidgets.QGraphicsSimpleTextItem] = None
        self.setZValue(15)
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable)
        self.setOpacity(marker_data.opacity)
        if marker_data.note:
            self.setToolTip(marker_data.note)
        self.sync()

    @property
    def marker_data(self) -> MarkerData:
        return self._data

    # -- geometry -----------------------------------------------------------

    def boundingRect(self) -> QtCore.QRectF:
        """Interactive area: just the triangle region at the ruler."""
        x = self._timeline.time_to_x(self._data.time)
        return QtCore.QRectF(
            x - _MARKER_TRI_SIZE,
            0,
            _MARKER_TRI_SIZE * 2,
            _RULER_HEIGHT,
        )

    def sync(self):
        self.prepareGeometryChange()

    # -- painting -----------------------------------------------------------

    # -- line-style mapping -------------------------------------------------

    _LINE_STYLES = {
        "dashed": QtCore.Qt.DashLine,
        "solid": QtCore.Qt.SolidLine,
        "dotted": QtCore.Qt.DotLine,
    }

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        color = QtGui.QColor(self._data.color)
        x = self._timeline.time_to_x(self._data.time)
        style = self._data.style

        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Head glyph at the ruler
        if style == "diamond":
            half = _MARKER_TRI_SIZE / 2
            cy = _RULER_HEIGHT - _MARKER_TRI_SIZE / 2
            diamond = QtGui.QPolygonF(
                [
                    QtCore.QPointF(x, cy - half),
                    QtCore.QPointF(x + half, cy),
                    QtCore.QPointF(x, cy + half),
                    QtCore.QPointF(x - half, cy),
                ]
            )
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPolygon(diamond)
        elif style == "line":
            painter.setPen(QtGui.QPen(color, 2))
            painter.drawLine(
                QtCore.QPointF(x, _RULER_HEIGHT - _MARKER_TRI_SIZE),
                QtCore.QPointF(x, _RULER_HEIGHT),
            )
        elif style == "bracket":
            bh = _MARKER_TRI_SIZE
            bw = 4
            painter.setPen(QtGui.QPen(color, 1.5))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawLine(
                QtCore.QPointF(x - bw, _RULER_HEIGHT - bh),
                QtCore.QPointF(x - bw, _RULER_HEIGHT),
            )
            painter.drawLine(
                QtCore.QPointF(x - bw, _RULER_HEIGHT),
                QtCore.QPointF(x + bw, _RULER_HEIGHT),
            )
            painter.drawLine(
                QtCore.QPointF(x + bw, _RULER_HEIGHT),
                QtCore.QPointF(x + bw, _RULER_HEIGHT - bh),
            )
        else:  # triangle (default)
            tri = QtGui.QPolygonF(
                [
                    QtCore.QPointF(x, _RULER_HEIGHT),
                    QtCore.QPointF(
                        x - _MARKER_TRI_SIZE / 2, _RULER_HEIGHT - _MARKER_TRI_SIZE
                    ),
                    QtCore.QPointF(
                        x + _MARKER_TRI_SIZE / 2, _RULER_HEIGHT - _MARKER_TRI_SIZE
                    ),
                ]
            )
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPolygon(tri)

        # Vertical line below ruler
        qt_line = self._LINE_STYLES.get(self._data.line_style)
        if qt_line is not None:
            pen = QtGui.QPen(color, 1, qt_line)
            painter.setPen(pen)
            scene_h = self._timeline._scene.height() if self._timeline._scene else 2000
            painter.drawLine(
                QtCore.QPointF(x, _RULER_HEIGHT),
                QtCore.QPointF(x, scene_h),
            )

        # Optional note label beside the head
        if self._data.note:
            painter.setPen(color)
            font = painter.font()
            font.setPointSize(7)
            painter.setFont(font)
            label = self._data.note[:8]
            painter.drawText(
                QtCore.QPointF(x + _MARKER_TRI_SIZE / 2 + 2, _RULER_HEIGHT - 2),
                label,
            )

    # -- hover --------------------------------------------------------------

    def hoverEnterEvent(self, event):
        if self._data.draggable:
            self.setCursor(QtCore.Qt.OpenHandCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    # -- drag (horizontal only) ---------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._data.draggable:
            self._drag_active = True
            self._drag_origin_x = event.scenePos().x()
            self._drag_origin_time = self._data.time
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            self._show_drag_tooltip(event.scenePos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._drag_active:
            return super().mouseMoveEvent(event)
        tl = self._timeline
        dx_time = tl.x_to_time(event.scenePos().x()) - tl.x_to_time(self._drag_origin_x)
        new_time = max(0.0, self._drag_origin_time + dx_time)
        modifiers = event.modifiers()
        if modifiers & QtCore.Qt.ControlModifier:
            new_time = round(new_time)
        else:
            interval = tl.parent_sequencer.snap_interval
            if interval > 0:
                new_time = round(new_time / interval) * interval
        self._data.time = new_time
        self.sync()
        self.update()
        self._update_drag_tooltip(event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._drag_active:
            self._drag_active = False
            self.unsetCursor()
            self._hide_drag_tooltip()
            widget = self._timeline.parent_sequencer
            widget.marker_moved.emit(self._data.marker_id, self._data.time)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # -- drag tooltip -------------------------------------------------------

    def _show_drag_tooltip(self, scene_pos):
        """Show a small text badge near the cursor with the current time."""
        self._drag_tooltip = QtWidgets.QGraphicsSimpleTextItem()
        self._drag_tooltip.setZValue(100)
        font = self._drag_tooltip.font()
        font.setPointSize(8)
        font.setBold(True)
        self._drag_tooltip.setFont(font)
        self._drag_tooltip.setBrush(QtGui.QColor(self._data.color))
        if self.scene():
            self.scene().addItem(self._drag_tooltip)
        self._update_drag_tooltip(scene_pos)

    def _update_drag_tooltip(self, scene_pos):
        """Reposition the drag tooltip and update its text."""
        if self._drag_tooltip is None:
            return
        t = self._data.time
        label = str(int(t)) if t == int(t) else f"{t:.1f}"
        self._drag_tooltip.setText(label)
        self._drag_tooltip.setPos(scene_pos.x() + 10, scene_pos.y() - 18)

    def _hide_drag_tooltip(self):
        """Remove the drag tooltip from the scene."""
        if self._drag_tooltip is not None:
            if self._drag_tooltip.scene():
                self._drag_tooltip.scene().removeItem(self._drag_tooltip)
            self._drag_tooltip = None

    # -- context menu -------------------------------------------------------

    def contextMenuEvent(self, event):
        widget = self._timeline.parent_sequencer
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(
            "QMenu { background:#333; color:#CCC; }"
            "QMenu::item:selected { background:#555; }"
        )

        # Inline note editor
        note_edit = QtWidgets.QLineEdit(self._data.note)
        note_edit.setPlaceholderText("Note")
        note_edit.setFixedWidth(140)
        note_action = QtWidgets.QWidgetAction(menu)
        note_action.setDefaultWidget(note_edit)
        menu.addAction(note_action)

        # Inline time editor
        time_edit = QtWidgets.QLineEdit(f"{self._data.time:.1f}")
        time_edit.setPlaceholderText("Time")
        time_edit.setFixedWidth(140)
        time_action = QtWidgets.QWidgetAction(menu)
        time_action.setDefaultWidget(time_edit)
        menu.addAction(time_action)

        menu.addSeparator()

        # Color picker
        color_action = menu.addAction(f"Color: {self._data.color}")

        # Style submenu
        style_menu = menu.addMenu("Style")
        for s in ("triangle", "diamond", "line", "bracket"):
            a = style_menu.addAction(s.capitalize())
            a.setCheckable(True)
            a.setChecked(s == self._data.style)
            a.setData(s)

        # Line style submenu
        ls_menu = menu.addMenu("Line")
        for ls in ("dashed", "solid", "dotted", "none"):
            a = ls_menu.addAction(ls.capitalize())
            a.setCheckable(True)
            a.setChecked(ls == self._data.line_style)
            a.setData(ls)

        # Draggable toggle
        drag_action = menu.addAction("Draggable")
        drag_action.setCheckable(True)
        drag_action.setChecked(self._data.draggable)

        menu.addSeparator()
        remove_action = menu.addAction("Remove Marker")

        # Close the menu when Enter is pressed in either line edit
        note_edit.returnPressed.connect(menu.close)
        time_edit.returnPressed.connect(menu.close)

        chosen = menu.exec_(event.screenPos())

        # Apply edits regardless of which action closed the menu
        new_note = note_edit.text()
        if new_note != self._data.note:
            self._data.note = new_note
            self.setToolTip(new_note)
            self.update()
            widget.marker_changed.emit(self._data.marker_id)

        try:
            new_time = float(time_edit.text())
        except ValueError:
            new_time = self._data.time
        if abs(new_time - self._data.time) > 1e-6:
            self._data.time = max(0.0, new_time)
            self.sync()
            self.update()
            widget.marker_moved.emit(self._data.marker_id, self._data.time)

        if chosen == remove_action:
            widget.remove_marker(self._data.marker_id)
        elif chosen == color_action:
            c = QtWidgets.QColorDialog.getColor(
                QtGui.QColor(self._data.color), None, "Marker Color"
            )
            if c.isValid():
                self._data.color = c.name()
                self.update()
                widget.marker_changed.emit(self._data.marker_id)
        elif chosen == drag_action:
            self._data.draggable = drag_action.isChecked()
            widget.marker_changed.emit(self._data.marker_id)
        elif chosen is not None and chosen.parent() == style_menu:
            self._data.style = chosen.data()
            self.sync()
            self.update()
            widget.marker_changed.emit(self._data.marker_id)
        elif chosen is not None and chosen.parent() == ls_menu:
            self._data.line_style = chosen.data()
            self.update()
            widget.marker_changed.emit(self._data.marker_id)


# ---------------------------------------------------------------------------
#  _ElidingLabel
# ---------------------------------------------------------------------------
class _ElidingLabel(QtWidgets.QLabel):
    """QLabel that elides text with ``\u2026`` when space is tight."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full_text = text

    def setText(self, text):
        self._full_text = text
        super().setText(text)
        self.update()

    def paintEvent(self, event):
        from qtpy.QtWidgets import QStyle

        painter = QtGui.QPainter(self)
        metrics = painter.fontMetrics()
        available = self.width() - 2  # small margin
        elided = metrics.elidedText(self._full_text, QtCore.Qt.ElideRight, available)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(
            self.rect(), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, elided
        )
        painter.end()


# ---------------------------------------------------------------------------
#  TrackHeaderWidget
# ---------------------------------------------------------------------------
class TrackHeaderWidget(QtWidgets.QWidget):
    """Left-pane widget showing track labels, vertically synced to the timeline."""

    track_hide_requested = QtCore.Signal(list)  # [track_name, ...]
    track_show_requested = QtCore.Signal(str)  # track_name to un-hide
    track_selected = QtCore.Signal(list)  # [track_name, ...] clicked
    track_expand_requested = QtCore.Signal(int)  # label index double-clicked
    track_menu_requested = QtCore.Signal(object, list)  # (QMenu, [track_name, ...])

    _STYLE_NORMAL = (
        "padding-left:6px; color:#CCCCCC; background:#333333; border-radius:3px;"
    )
    _STYLE_DIMMED = (
        "padding-left:6px; color:#777777; background:#2A2A2A; border-radius:3px;"
    )
    _STYLE_SELECTED = (
        "padding-left:6px; color:#FFFFFF; background:#505050; border-radius:3px;"
    )
    _STYLE_SUB_ROW = (
        "padding-left:16px; color:#999999; background:#2D2D2D; "
        "border-radius:2px; font-size:10px;"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.ClickFocus)
        self._labels: List[QtWidgets.QLabel] = []
        self._names: List[str] = []  # parallel to _labels
        self._dimmed: List[bool] = []  # parallel to _labels
        self._selected: List[int] = []  # indices of selected labels
        self._hidden_track_names: List[str] = []  # set by SequencerWidget
        self._sub_labels: Dict[int, List[QtWidgets.QLabel]] = {}  # idx → sub-row labels
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, _RULER_HEIGHT, 0, 0)
        self._layout.setSpacing(_TRACK_PADDING)
        self._layout.addStretch()

    def add_track_label(
        self, name: str, icon=None, dimmed: bool = False, italic: bool = False
    ):
        base_style = self._STYLE_DIMMED if dimmed else self._STYLE_NORMAL
        if italic:
            base_style += " font-style:italic;"
        lbl = QtWidgets.QLabel(name)
        lbl.setFixedHeight(_TRACK_HEIGHT)
        lbl.setStyleSheet(base_style)
        if icon is not None and not icon.isNull():
            px = icon.pixmap(16, 16)
            if px.width() > 16 or px.height() > 16:
                px = px.scaled(
                    16, 16, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
                )
            lbl.setPixmap(QtGui.QPixmap())  # ensure no stale pixmap
            # Use a small horizontal layout: icon + text
            container = QtWidgets.QWidget()
            container.setFixedHeight(_TRACK_HEIGHT)
            container.setStyleSheet(base_style)
            h = QtWidgets.QHBoxLayout(container)
            h.setContentsMargins(4, 0, 2, 0)
            h.setSpacing(4)
            ico_lbl = QtWidgets.QLabel()
            ico_lbl.setPixmap(px)
            ico_lbl.setFixedSize(22, _TRACK_HEIGHT)
            ico_lbl.setAlignment(QtCore.Qt.AlignCenter)
            ico_lbl.setStyleSheet("background:transparent; border:none; padding:0;")
            txt_color = "#777777" if dimmed else "#CCCCCC"
            if italic:
                txt_color = "#999977" if not dimmed else "#777766"
            txt_lbl = _ElidingLabel(name)
            txt_lbl.setStyleSheet(
                f"padding:0; color:{txt_color}; background:transparent; border:none;"
                + (" font-style:italic;" if italic else "")
            )
            h.addWidget(ico_lbl)
            h.addWidget(txt_lbl, 1)  # stretch so text fills available space
            container.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            container.customContextMenuRequested.connect(
                lambda pos, w=container: self._show_label_menu(w, pos)
            )
            container.installEventFilter(self)
            idx = self._layout.count() - 1
            self._layout.insertWidget(idx, container)
            self._labels.append(container)
            self._names.append(name)
            self._dimmed.append(dimmed)
            return
        lbl.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        lbl.customContextMenuRequested.connect(
            lambda pos, w=lbl: self._show_label_menu(w, pos)
        )
        lbl.installEventFilter(self)
        idx = self._layout.count() - 1  # before the stretch
        self._layout.insertWidget(idx, lbl)
        self._labels.append(lbl)
        self._names.append(name)
        self._dimmed.append(dimmed)

    # -- sub-row expansion -------------------------------------------------

    @staticmethod
    def _label_text_widget(lbl) -> QtWidgets.QLabel:
        """Return the QLabel that holds the visible text.

        For plain QLabel entries this is *lbl* itself.  For icon-container
        widgets the text label is the second child QLabel.
        """
        if isinstance(lbl, QtWidgets.QLabel):
            return lbl
        # Container with HBoxLayout: [icon_lbl, text_lbl, stretch]
        for child in lbl.findChildren(QtWidgets.QLabel):
            if child.pixmap() is None or child.pixmap().isNull():
                return child
        # Fallback — shouldn't happen
        return lbl

    def set_track_expanded(self, track_idx: int, sub_names: List[str], sub_height: int):
        """Show sub-row labels beneath the track at *track_idx*."""
        self.set_track_collapsed(track_idx)
        main_lbl = self._labels[track_idx]
        name = self._names[track_idx]
        self._label_text_widget(main_lbl).setText(f"\u25bc {name}")
        insert_at = self._layout.indexOf(main_lbl) + 1
        sub_lbls: List[QtWidgets.QLabel] = []
        for sr_name in sub_names:
            lbl = QtWidgets.QLabel(sr_name)
            lbl.setFixedHeight(sub_height)
            lbl.setStyleSheet(self._STYLE_SUB_ROW)
            self._layout.insertWidget(insert_at, lbl)
            insert_at += 1
            sub_lbls.append(lbl)
        self._sub_labels[track_idx] = sub_lbls

    def set_track_collapsed(self, track_idx: int):
        """Remove sub-row labels for the track at *track_idx*."""
        name = self._names[track_idx]
        self._label_text_widget(self._labels[track_idx]).setText(name)
        for lbl in self._sub_labels.pop(track_idx, []):
            self._layout.removeWidget(lbl)
            lbl.deleteLater()

    # -- selection ---------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj not in self._labels:
            return super().eventFilter(obj, event)
        if event.type() == QtCore.QEvent.MouseButtonDblClick and obj in self._labels:
            idx = self._labels.index(obj)
            self.track_expand_requested.emit(idx)
            return True
        if event.type() == QtCore.QEvent.MouseButtonPress and obj in self._labels:
            idx = self._labels.index(obj)
            mods = event.modifiers()
            ctrl = mods & QtCore.Qt.ControlModifier
            shift = mods & QtCore.Qt.ShiftModifier
            if shift and self._selected:
                # Range select from last selected to clicked
                anchor = self._selected[-1]
                lo, hi = sorted((anchor, idx))
                self._selected = list(range(lo, hi + 1))
            elif ctrl:
                # Toggle individual
                if idx in self._selected:
                    self._selected.remove(idx)
                else:
                    self._selected.append(idx)
            else:
                self._selected = [idx]
            self._refresh_styles()
            self.track_selected.emit(self.selected_names())
            return True  # consumed
        return super().eventFilter(obj, event)

    def selected_names(self) -> List[str]:
        """Return names of all selected tracks."""
        return [self._names[i] for i in self._selected if i < len(self._names)]

    def _refresh_styles(self):
        for i, lbl in enumerate(self._labels):
            if i in self._selected:
                style = self._STYLE_SELECTED
            elif i < len(self._dimmed) and self._dimmed[i]:
                style = self._STYLE_DIMMED
            else:
                style = self._STYLE_NORMAL
            lbl.setStyleSheet(style)

    # -- context menu ------------------------------------------------------

    def _show_label_menu(self, widget, pos):
        idx = self._labels.index(widget)
        # Ensure the right-clicked label is part of the selection
        if idx not in self._selected:
            self._selected = [idx]
            self._refresh_styles()
        names = self.selected_names()
        count = len(names)
        menu = QtWidgets.QMenu(self)
        hide_label = f"Hide {count} Tracks" if count > 1 else "Hide Track"
        menu.addAction(hide_label, lambda: self.track_hide_requested.emit(names))

        # Let consumers add custom actions
        self.track_menu_requested.emit(menu, names)

        # "Show Hidden" submenu — only when hidden tracks exist
        hidden = self._hidden_track_names
        if hidden:
            sub = menu.addMenu(f"Show Hidden ({len(hidden)})")
            for name in sorted(hidden):
                sub.addAction(name, lambda n=name: self.track_show_requested.emit(n))

        menu.exec_(widget.mapToGlobal(pos))

    def clear_tracks(self):
        # Remove sub-row labels first
        for idx in list(self._sub_labels):
            self.set_track_collapsed(idx)
        for lbl in self._labels:
            lbl.removeEventFilter(self)
            self._layout.removeWidget(lbl)
            lbl.deleteLater()
        self._labels.clear()
        self._names.clear()
        self._dimmed.clear()
        self._selected.clear()


# ---------------------------------------------------------------------------
#  TimelineScene
# ---------------------------------------------------------------------------
class TimelineScene(QtWidgets.QGraphicsScene):
    """Scene that owns the ruler, playhead, and all clip items."""

    def __init__(self, timeline: "TimelineView", parent=None):
        super().__init__(parent)
        self._timeline = timeline
        self._ruler = RulerItem(timeline)
        self.addItem(self._ruler)
        self._playhead = PlayheadItem(timeline)
        self.addItem(self._playhead)

    @property
    def ruler(self) -> RulerItem:
        return self._ruler

    @property
    def playhead(self) -> PlayheadItem:
        return self._playhead


# ---------------------------------------------------------------------------
#  TimelineView
# ---------------------------------------------------------------------------
class TimelineView(QtWidgets.QGraphicsView):
    """QGraphicsView providing zoom, pan, and coordinate mapping."""

    def __init__(self, parent_sequencer: "SequencerWidget", parent=None):
        self.parent_sequencer = parent_sequencer
        self._pixels_per_unit = 2.0  # default zoom
        self._scene = TimelineScene(self)
        super().__init__(self._scene, parent)
        self.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.SmartViewportUpdate)
        self.setStyleSheet("background:#1E1E1E; border:none;")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._pan_active = False
        self._pan_start = QtCore.QPoint()
        self._ruler_drag = False
        self._shortcut_sequences: List[QtGui.QKeySequence] = []
        self._ctrl_subtract_snapshot: Optional[set] = None  # for Ctrl+marquee subtract
        # Now that the scene/view wiring is complete, sync deferred items
        self._scene.playhead.sync()
        # Keep ruler pinned to the viewport top during vertical scroll
        self.verticalScrollBar().valueChanged.connect(self._sync_ruler_pos)

    # -- event override: consume shortcut keys so they don't leak to host --
    def event(self, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.ShortcutOverride:
            mods = event.modifiers()
            mod_int = mods.value if hasattr(mods, "value") else int(mods)
            key = QtGui.QKeySequence(event.key() | mod_int)
            for seq in self._shortcut_sequences:
                if key.matches(seq) == QtGui.QKeySequence.ExactMatch:
                    event.accept()
                    return True
        return super().event(event)

    def keyPressEvent(self, event):
        """Dispatch registered shortcut keys directly.

        After ShortcutOverride accepts a key, Qt delivers it as a normal
        KeyPress instead of activating QShortcuts.  We must handle it
        here so it doesn't propagate to the host app (e.g. Maya).
        """
        mods = event.modifiers()
        mod_int = mods.value if hasattr(mods, "value") else int(mods)
        key_seq = QtGui.QKeySequence(event.key() | mod_int)
        for seq in self._shortcut_sequences:
            if key_seq.matches(seq) == QtGui.QKeySequence.ExactMatch:
                seq_str = seq.toString()
                mgr = self.parent_sequencer._shortcut_mgr
                entry = mgr.shortcuts.get(seq_str)
                if entry:
                    entry["action"]()
                event.accept()
                return
        super().keyPressEvent(event)

    def enterEvent(self, event):
        """Grab focus on mouse-enter so shortcut keys are captured here."""
        self.setFocus(QtCore.Qt.MouseFocusReason)
        super().enterEvent(event)

    # -- mapper -------------------------------------------------------------
    @property
    def pixels_per_unit(self) -> float:
        return self._pixels_per_unit

    @pixels_per_unit.setter
    def pixels_per_unit(self, value: float):
        self._pixels_per_unit = max(0.01, value)
        self._refresh_all()

    def time_to_x(self, t: float) -> float:
        return t * self._pixels_per_unit

    def x_to_time(self, x: float) -> float:
        return x / self._pixels_per_unit if self._pixels_per_unit else 0.0

    # -- resize: preserve scroll position ------------------------------------
    def resizeEvent(self, event):
        h = self.horizontalScrollBar().value()
        super().resizeEvent(event)
        self.horizontalScrollBar().setValue(h)

    # -- zoom ---------------------------------------------------------------
    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        old_ppu = self._pixels_per_unit

        # Mouse position in the viewport and the timeline time under it
        view_x = event.position().x() if hasattr(event, "position") else event.pos().x()
        scene_x_before = self.mapToScene(int(view_x), 0).x()
        time_under_cursor = scene_x_before / old_ppu if old_ppu else 0.0

        self._pixels_per_unit = max(0.01, min(100.0, old_ppu * factor))
        self._refresh_all()

        # Scroll so the same timeline time stays under the cursor
        scene_x_after = time_under_cursor * self._pixels_per_unit
        self.horizontalScrollBar().setValue(int(scene_x_after - view_x))
        event.accept()

    # -- clicking / dragging ruler area sets playhead -----------------------
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self._pan_active = True
            self._pan_start = event.pos()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            event.accept()
            return
        # Use viewport Y so the hit-test works even when scrolled
        if event.button() == QtCore.Qt.LeftButton and event.pos().y() <= _RULER_HEIGHT:
            self._ruler_drag = True
            scene_pos = self.mapToScene(event.pos())
            t = round(self.x_to_time(scene_pos.x()))
            self._scene.playhead.time = t
            self.parent_sequencer.playhead_moved.emit(t)
            event.accept()
        else:
            # Ctrl+drag = subtract from selection (rubber band to deselect)
            if (
                event.button() == QtCore.Qt.LeftButton
                and event.modifiers() & QtCore.Qt.ControlModifier
            ):
                self._ctrl_subtract_snapshot = {
                    item
                    for item in self._scene.selectedItems()
                    if isinstance(item, ClipItem)
                }
            else:
                self._ctrl_subtract_snapshot = None
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_active:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            hs = self.horizontalScrollBar()
            vs = self.verticalScrollBar()
            hs.setValue(hs.value() - delta.x())
            vs.setValue(vs.value() - delta.y())
            # Grow the scene when panning toward the right edge so the
            # user can always scroll further into the future.
            if hs.value() >= hs.maximum() - 10:
                self._update_scene_rect()
            event.accept()
        elif self._ruler_drag:
            scene_pos = self.mapToScene(event.pos())
            t = round(self.x_to_time(scene_pos.x()))
            self._scene.playhead.time = t
            self.parent_sequencer.playhead_moved.emit(t)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self._pan_active = False
            self.unsetCursor()
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton and self._ruler_drag:
            self._ruler_drag = False
            event.accept()
        else:
            snapshot = self._ctrl_subtract_snapshot
            super().mouseReleaseEvent(event)
            # Ctrl+marquee: subtract newly-banded items from pre-drag selection
            if snapshot is not None:
                newly_selected = {
                    item
                    for item in self._scene.selectedItems()
                    if isinstance(item, ClipItem)
                }
                keep = snapshot - newly_selected
                self._scene.blockSignals(True)
                for item in self._scene.selectedItems():
                    item.setSelected(False)
                for item in keep:
                    item.setSelected(True)
                self._scene.blockSignals(False)
                self.parent_sequencer._on_scene_selection()
                self._ctrl_subtract_snapshot = None

    def mouseDoubleClickEvent(self, event):
        """Double-click on the ruler area to add a marker."""
        if event.button() == QtCore.Qt.LeftButton and event.pos().y() <= _RULER_HEIGHT:
            scene_pos = self.mapToScene(event.pos())
            t = self.x_to_time(scene_pos.x())
            interval = self.parent_sequencer.snap_interval
            if interval > 0:
                t = round(t / interval) * interval
            mid = self.parent_sequencer.add_marker(t)
            self.parent_sequencer.marker_added.emit(mid, t)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        """Right-click on the timeline background."""
        # Defer to clip/marker context menus
        item = self.itemAt(event.pos())
        if isinstance(item, (ClipItem, MarkerItem)):
            super().contextMenuEvent(event)
            return

        sq = self.parent_sequencer
        scene_pos = self.mapToScene(event.pos())
        t = self.x_to_time(scene_pos.x())
        interval = sq.snap_interval
        if interval > 0:
            t = round(t / interval) * interval

        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#333; color:#CCC; }"
            "QMenu::item:selected { background:#555; }"
        )
        add_action = menu.addAction(f"Add Marker at {int(t)}\u2026")

        menu.addSeparator()

        act_ranges = menu.addAction("Show Shot Ranges")
        act_ranges.setCheckable(True)
        act_ranges.setChecked(sq.show_range_overlays)

        act_highlight = menu.addAction("Show Active Range")
        act_highlight.setCheckable(True)
        act_highlight.setChecked(sq.show_range_highlight)

        act_gaps = menu.addAction("Show Gap Overlays")
        act_gaps.setCheckable(True)
        act_gaps.setChecked(sq.show_gap_overlays)

        chosen = menu.exec_(event.globalPos())

        if chosen == add_action:
            note, ok = QtWidgets.QInputDialog.getText(
                sq,
                "Marker Note",
                "Note:",
                QtWidgets.QLineEdit.Normal,
                "",
            )
            if ok:
                mid = sq.add_marker(t, note=note)
                sq.marker_added.emit(mid, t)
        elif chosen == act_ranges:
            sq.show_range_overlays = act_ranges.isChecked()
        elif chosen == act_highlight:
            sq.show_range_highlight = act_highlight.isChecked()
        elif chosen == act_gaps:
            sq.show_gap_overlays = act_gaps.isChecked()

    # -- ruler pinning ------------------------------------------------------
    def _sync_ruler_pos(self):
        """Keep the ruler pinned to the top of the visible area."""
        top = self.mapToScene(0, 0).y()
        self._scene.ruler.setPos(0, top)
        self._scene.ruler.update()

    # -- internal refresh ---------------------------------------------------
    def _refresh_all(self):
        """Reposition all items after a zoom or data change."""
        for item in self._scene.items():
            if isinstance(item, ClipItem):
                item._sync_geometry()
            elif isinstance(item, MarkerItem):
                item.sync()
            elif isinstance(item, RangeHighlightItem):
                item.sync()
            elif isinstance(item, (_StaticRangeOverlay, _GapOverlayItem)):
                item.prepareGeometryChange()
                item.update()
        self._sync_ruler_pos()
        self._scene.playhead.sync()
        self._update_scene_rect()
        self.viewport().update()

    def _update_scene_rect(self):
        """Ensure the scene is large enough to contain all clips and markers.

        Also extends the right edge beyond the visible viewport so the
        user can always middle-mouse pan further into the future.
        """
        sq = self.parent_sequencer
        max_end = 100.0
        for cd in sq._clips.values():
            max_end = max(max_end, cd.end)
        for md in sq._markers.values():
            max_end = max(max_end, md.time)
        if sq._range_highlight is not None:
            max_end = max(max_end, sq._range_highlight.end)
        for gap in sq._gap_overlays:
            max_end = max(max_end, gap._end)
        # Include the visible viewport right edge so users can scroll
        # forward beyond existing content.
        visible_right = self.x_to_time(
            self.horizontalScrollBar().value() + self.viewport().width()
        )
        max_end = max(max_end, visible_right)
        w = self.time_to_x(max_end) + self.viewport().width()
        h = _RULER_HEIGHT + sq._total_row_height() + 40
        self._scene.setSceneRect(0, 0, w, h)

    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF):
        """Draw alternating track row backgrounds."""
        painter.fillRect(rect, QtGui.QColor("#1E1E1E"))
        sq = self.parent_sequencer
        _BG_MAIN = (QtGui.QColor("#262626"), QtGui.QColor("#2A2A2A"))
        _BG_SUB = (QtGui.QColor("#222222"), QtGui.QColor("#252525"))
        for i, (y, h, is_sub) in enumerate(sq._visual_rows()):
            palette = _BG_SUB if is_sub else _BG_MAIN
            bg = palette[i % 2]
            painter.fillRect(QtCore.QRectF(rect.left(), y, rect.width(), h), bg)


# ---------------------------------------------------------------------------
#  AttributeColorDialog
# ---------------------------------------------------------------------------
class AttributeColorDialog(QtWidgets.QDialog):
    """A dialog for configuring attribute-type color mappings.

    Parameters
    ----------
    defaults : dict
        Factory-default ``{attr_name: hex_color}`` mapping.
    common_attrs : list
        Attribute names always displayed regardless of scene content.
    active_attrs : list, optional
        Additional attribute names currently keyed in the scene.
    settings : SettingsManager, optional
        Pre-configured settings manager for persistence.
    parent : QWidget, optional
        Parent widget.
    """

    colors_changed = QtCore.Signal(dict)

    _SETTINGS_NS = "sequencer/attribute_colors"
    _SWATCH_SIZE = 22

    def __init__(
        self,
        defaults: Optional[Dict[str, str]] = None,
        common_attrs: Optional[List[str]] = None,
        active_attrs: Optional[List[str]] = None,
        settings: Optional["SettingsManager"] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Attribute Colors")
        self.setMinimumWidth(280)

        self._defaults = defaults or dict(_DEFAULT_ATTRIBUTE_COLORS)
        self._common = common_attrs or list(_COMMON_ATTRIBUTES)
        self._active = active_attrs or []
        self._settings = settings or SettingsManager(namespace=self._SETTINGS_NS)
        self._swatches: Dict[str, QtWidgets.QPushButton] = {}

        self._build_ui()
        self._load_from_settings()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Scrollable attribute list
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        container = QtWidgets.QWidget()
        self._grid = QtWidgets.QGridLayout(container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(3)

        # Common attributes section
        row = 0
        header = QtWidgets.QLabel("Common")
        header.setStyleSheet("color:#999; font-size:10px; font-weight:bold;")
        self._grid.addWidget(header, row, 0, 1, 2)
        row += 1

        for attr in self._common:
            row = self._add_color_row(attr, row)

        # Active-only attributes (keyed in scene but not in common list)
        extra = sorted(set(self._active) - set(self._common))
        if extra:
            sep = QtWidgets.QLabel("Scene Attributes")
            sep.setStyleSheet("color:#999; font-size:10px; font-weight:bold;")
            self._grid.addWidget(sep, row, 0, 1, 2)
            row += 1
            for attr in extra:
                row = self._add_color_row(attr, row)

        self._grid.setRowStretch(row, 1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Bottom buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_defaults = QtWidgets.QPushButton("Restore Defaults")
        btn_defaults.clicked.connect(self._restore_defaults)
        btn_row.addWidget(btn_defaults)
        btn_row.addStretch()
        btn_close = QtWidgets.QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _add_color_row(self, attr: str, row: int) -> int:
        label = QtWidgets.QLabel(attr)
        label.setStyleSheet("color:#CCC; font-size:11px;")

        swatch = QtWidgets.QPushButton()
        swatch.setFixedSize(self._SWATCH_SIZE, self._SWATCH_SIZE)
        swatch.setCursor(QtCore.Qt.PointingHandCursor)
        swatch.clicked.connect(lambda checked=False, a=attr: self._pick_color(a))
        self._swatches[attr] = swatch

        self._grid.addWidget(label, row, 0)
        self._grid.addWidget(swatch, row, 1, QtCore.Qt.AlignRight)
        return row + 1

    def _update_swatch(self, attr: str, hex_color: str):
        btn = self._swatches.get(attr)
        if btn:
            btn.setStyleSheet(
                f"background-color:{hex_color}; border:1px solid #555; "
                f"border-radius:3px;"
            )

    def _pick_color(self, attr: str):
        current = self._current_color(attr)
        color = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(current),
            self,
            f"Color for {attr}",
        )
        if color.isValid():
            hex_val = color.name()
            self._settings.setValue(attr, hex_val)
            self._update_swatch(attr, hex_val)
            self.colors_changed.emit(self.color_map())

    def _current_color(self, attr: str) -> str:
        val = self._settings.value(attr)
        return val if val else self._defaults.get(attr, "#5B8BD4")

    def _load_from_settings(self):
        for attr in self._swatches:
            self._update_swatch(attr, self._current_color(attr))

    def _restore_defaults(self):
        for attr in self._swatches:
            self._settings.clear(attr)
        self._load_from_settings()
        self.colors_changed.emit(self.color_map())

    def color_map(self) -> Dict[str, str]:
        """Return the full attribute → hex-color mapping."""
        result = dict(self._defaults)
        for key in self._settings.keys():
            val = self._settings.value(key)
            if val:
                result[key] = val
        return result


# ---------------------------------------------------------------------------
#  SequencerWidget  (the public API)
# ---------------------------------------------------------------------------
class SequencerWidget(QtWidgets.QSplitter, AttributesMixin):
    """A split-view NLE sequencer widget.

    Signals
    -------
    clip_moved(int, float)
        Emitted when a single clip is repositioned.  Args: ``(clip_id, new_start)``.
    clips_batch_moved(list)
        Emitted when multiple clips are moved together.  Args: ``[(clip_id, new_start), ...]``.
    clip_resized(int, float, float)
        Emitted when a clip edge is dragged.  Args: ``(clip_id, new_start, new_duration)``.
    clip_selected(int)
        Emitted when a clip is clicked.  Args: ``(clip_id,)``.
    playhead_moved(float)
        Emitted when the playhead is repositioned.  Args: ``(time,)``.
    """

    clip_moved = QtCore.Signal(int, float)
    clips_batch_moved = QtCore.Signal(list)  # [(clip_id, new_start), ...]
    clips_reordered = QtCore.Signal(int, int)  # (clip_id_a, clip_id_b) swap request
    clip_resized = QtCore.Signal(int, float, float)
    clip_selected = QtCore.Signal(int)
    clip_renamed = QtCore.Signal(int, str)  # (clip_id, new_label)
    clip_locked = QtCore.Signal(int, bool)  # (clip_id, is_locked)
    selection_changed = QtCore.Signal(list)
    playhead_moved = QtCore.Signal(float)
    track_hidden = QtCore.Signal(list)  # [track_name, ...] hidden via context menu
    track_shown = QtCore.Signal(str)  # track_name un-hidden via menu
    track_selected = QtCore.Signal(list)  # [track_name, ...] clicked in header
    track_menu_requested = QtCore.Signal(object, list)  # (QMenu, [track_name, ...])
    undo_requested = QtCore.Signal()
    redo_requested = QtCore.Signal()
    track_expanded = QtCore.Signal(int)  # (track_id) after expansion complete
    track_collapsed = QtCore.Signal(int)  # (track_id) after collapse complete
    marker_added = QtCore.Signal(int, float)  # (marker_id, time)
    marker_moved = QtCore.Signal(int, float)  # (marker_id, new_time)
    marker_changed = QtCore.Signal(int)  # (marker_id) after note/color edit
    marker_removed = QtCore.Signal(int)  # (marker_id)
    shots_changed = QtCore.Signal()  # shot definitions added/removed/modified
    app_event = QtCore.Signal(str, object)  # (event_name, payload) generic bridge
    range_highlight_changed = QtCore.Signal(
        float, float
    )  # (start, end) after move/resize
    gap_resized = QtCore.Signal(
        float, float
    )  # (original_next_shot_start, new_next_shot_start)

    def __init__(self, parent=None, **kwargs):
        super().__init__(QtCore.Qt.Horizontal, parent)

        # -- state ----------------------------------------------------------
        self._tracks: List[TrackData] = []
        self._clips: Dict[int, ClipData] = {}
        self._clip_items: Dict[int, ClipItem] = {}
        self._next_track_id = 0
        self._next_clip_id = 0
        self._snap_interval: float = 1.0  # 1 = per-frame snap (default)
        self._gap_threshold: float = 10.0  # flat keys to constitute a gap
        self._undo_stack: List[Dict[int, tuple]] = []  # (start, duration) per clip_id
        self._redo_stack: List[Dict[int, tuple]] = []
        self._max_undo = 50
        self._markers: Dict[int, MarkerData] = {}
        self._marker_items: Dict[int, MarkerItem] = {}
        self._next_marker_id = 0
        self._attribute_colors: Dict[str, str] = dict(_DEFAULT_ATTRIBUTE_COLORS)
        self._expanded_tracks: Dict[int, List[str]] = {}  # track_id → sub-row names
        self._sub_row_height: int = _SUB_ROW_HEIGHT
        self._sub_row_provider = None  # callable(track_id, track_name) → [(sub_name, [(start,dur,label,color), ...]), ...]
        self._range_highlight: Optional[RangeHighlightItem] = None
        self._range_overlays: List[QtWidgets.QGraphicsItem] = []
        self._gap_overlays: List[QtWidgets.QGraphicsItem] = []
        self._shift_at_press: bool = False  # Shift held when last drag started
        self._show_range_overlays: bool = True  # toggle for shot range overlays
        self._show_gap_overlays: bool = True  # toggle for gap overlays
        self._show_range_highlight: bool = True  # toggle for active shot highlight

        # -- sub-widgets ----------------------------------------------------
        self._header = TrackHeaderWidget()
        self._header_scroll = QtWidgets.QScrollArea()
        self._header_scroll.setWidget(self._header)
        self._header_scroll.setWidgetResizable(True)
        self._header_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._header_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._header_scroll.setStyleSheet("background:#2B2B2B; border:none;")
        self._header_scroll.setMinimumWidth(0)

        self._timeline = TimelineView(self)

        self.addWidget(self._header_scroll)
        self.addWidget(self._timeline)
        self.setSizes([140, 600])
        self.setHandleWidth(2)
        self.setCollapsible(0, True)
        self.setCollapsible(1, False)

        # Snap-close: collapse the header pane when dragged below threshold
        self._header_snap_width = 140  # default / open width
        self._header_snap_threshold = 60  # collapse if narrower
        self.splitterMoved.connect(self._on_splitter_moved)

        # -- sync vertical scroll -------------------------------------------
        self._timeline.verticalScrollBar().valueChanged.connect(
            self._header_scroll.verticalScrollBar().setValue
        )

        # -- forward track-hide/show/select from header ----------------------
        self._header.track_hide_requested.connect(self.track_hidden.emit)
        self._header.track_show_requested.connect(self.track_shown.emit)
        self._header.track_selected.connect(self.track_selected.emit)
        self._header.track_menu_requested.connect(self.track_menu_requested.emit)
        self._header.track_expand_requested.connect(self._on_header_expand)

        # -- right-click on header background: show hidden tracks -----------
        self._hidden_tracks: List[str] = []
        self._header.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._header.customContextMenuRequested.connect(self._show_hidden_menu)

        # -- selection forwarding -------------------------------------------
        self._timeline._scene.selectionChanged.connect(self._on_scene_selection)

        # -- keyboard shortcuts via ShortcutManager -------------------------
        _shortcut_defs = [
            ("Ctrl+Z", self.undo, "Undo last clip edit"),
            ("Ctrl+Shift+Z", self.redo, "Redo last undone edit"),
            ("Left", self.step_backward, "Step playhead backward"),
            ("Right", self.step_forward, "Step playhead forward"),
            ("Home", self.go_to_start, "Jump playhead to start"),
            ("End", self.go_to_end, "Jump playhead to last clip end"),
            ("M", self.add_marker_at_playhead, "Add marker at playhead"),
            ("F", self.frame_shot, "Frame the active shot range"),
        ]
        self._shortcut_mgr = ShortcutManager(self)
        _ctx = QtCore.Qt.WidgetWithChildrenShortcut
        self._shortcut_mgr.add_shortcuts_batch(
            [(k, fn, desc, _ctx) for k, fn, desc in _shortcut_defs]
        )
        # Tell the TimelineView which keys to claim via ShortcutOverride
        self._timeline._shortcut_sequences = [
            QtGui.QKeySequence(k) for k, *_ in _shortcut_defs
        ]

        # -- apply kwargs via AttributesMixin --------------------------------
        if kwargs:
            self.set_attributes(self, **kwargs)

    # -- consume assigned hotkeys so they don't leak to the host app --------
    def event(self, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.ShortcutOverride:
            mods = event.modifiers()
            mod_int = mods.value if hasattr(mods, "value") else int(mods)
            key = QtGui.QKeySequence(event.key() | mod_int)
            for seq in self._timeline._shortcut_sequences:
                if key.matches(seq) == QtGui.QKeySequence.ExactMatch:
                    event.accept()
                    return True
        return super().event(event)

    # -- public API ---------------------------------------------------------
    def add_track(
        self, name: str, icon=None, dimmed: bool = False, italic: bool = False
    ) -> int:
        """Add a new track row.  Returns the ``track_id``.

        Parameters
        ----------
        icon : QIcon, optional
            Icon shown to the left of the track label.
        dimmed : bool
            If True the track label is rendered with reduced contrast.
        italic : bool
            If True the track label text is italicised (e.g. missing objects).
        """
        tid = self._next_track_id
        self._next_track_id += 1
        td = TrackData(track_id=tid, name=name)
        self._tracks.append(td)
        self._header.add_track_label(name, icon=icon, dimmed=dimmed, italic=italic)
        self._timeline._update_scene_rect()
        return tid

    def add_clip(
        self,
        track_id: int,
        start: float,
        duration: float,
        label: str = "",
        color: Optional[str] = None,
        sub_row: str = "",
        locked: bool = False,
        **data,
    ) -> int:
        """Add a clip to an existing track.  Returns the ``clip_id``.

        Parameters
        ----------
        sub_row : str
            When non-empty, places the clip on the named sub-row of an
            expanded track instead of the main track row.
        locked : bool
            If True the clip cannot be dragged or resized.
        """
        cid = self._next_clip_id
        self._next_clip_id += 1
        if color is None:
            color = "#CCCCCC"
        cd = ClipData(
            clip_id=cid,
            track_id=track_id,
            start=start,
            duration=duration,
            label=label,
            color=color,
            locked=locked,
            sub_row=sub_row,
            data=data,
        )
        self._clips[cid] = cd

        # register on track
        for td in self._tracks:
            if td.track_id == track_id:
                td.clips.append(cid)
                break

        # create visual item
        item = ClipItem(cd, self._timeline)
        self._clip_items[cid] = item
        self._timeline._scene.addItem(item)
        self._timeline._update_scene_rect()
        return cid

    def remove_clip(self, clip_id: int):
        """Remove a clip by id."""
        if clip_id not in self._clips:
            return
        cd = self._clips.pop(clip_id)
        item = self._clip_items.pop(clip_id, None)
        if item and item.scene():
            item.scene().removeItem(item)
        for td in self._tracks:
            if cd.clip_id in td.clips:
                td.clips.remove(cd.clip_id)

    def set_clip_label(self, clip_id: int, label: str):
        """Set the display label for a clip."""
        cd = self._clips.get(clip_id)
        if cd is None:
            return
        cd.label = label
        item = self._clip_items.get(clip_id)
        if item:
            item.update()

    def set_clip_locked(self, clip_id: int, locked: bool):
        """Lock or unlock a clip, preventing drag/resize/rename."""
        cd = self._clips.get(clip_id)
        if cd is None:
            return
        cd.locked = locked
        item = self._clip_items.get(clip_id)
        if item:
            item.update()

    def remove_track(self, track_id: int):
        """Remove a track and all its clips."""
        td = None
        for i, t in enumerate(self._tracks):
            if t.track_id == track_id:
                td = t
                self._tracks.pop(i)
                break
        if td is None:
            return
        self._expanded_tracks.pop(track_id, None)
        for cid in list(td.clips):
            self.remove_clip(cid)
        # Also remove sub-row clips
        sub_cids = [
            cid
            for cid, cd in self._clips.items()
            if cd.track_id == track_id and cd.sub_row
        ]
        for cid in sub_cids:
            self.remove_clip(cid)
        self._header.clear_tracks()
        for t in self._tracks:
            self._header.add_track_label(t.name)
        self._timeline._refresh_all()

    def get_clip(self, clip_id: int) -> Optional[ClipData]:
        """Return the data for a clip, or None."""
        return self._clips.get(clip_id)

    def get_track(self, track_id: int) -> Optional[TrackData]:
        """Return the data for a track, or None."""
        for td in self._tracks:
            if td.track_id == track_id:
                return td
        return None

    def tracks(self) -> List[TrackData]:
        """Return a list of all track data."""
        return list(self._tracks)

    def clips(self, track_id: Optional[int] = None) -> List[ClipData]:
        """Return clip data, optionally filtered by track."""
        if track_id is None:
            return list(self._clips.values())
        return [cd for cd in self._clips.values() if cd.track_id == track_id]

    def swap_clips(self, clip_id_a: int, clip_id_b: int) -> None:
        """Swap the timeline positions of two clips and emit ``clips_reordered``.

        Each clip adopts the other's ``start``, preserving its own
        duration.  The gap between them is maintained: the shorter clip
        gains trailing space, shifted so the layout stays contiguous.

        This is a visual-only operation; the controller should listen
        to ``clips_reordered`` to perform the actual keyframe swap in
        the backend.
        """
        a = self._clips.get(clip_id_a)
        b = self._clips.get(clip_id_b)
        if a is None or b is None or clip_id_a == clip_id_b:
            return

        # Identify earlier / later by start
        if a.start > b.start:
            a, b = b, a

        gap = b.start - (a.start + a.duration)
        new_b_start = a.start
        new_a_start = a.start + b.duration + gap

        a.start = new_a_start
        b.start = new_b_start

        # Refresh visual items
        for cid in (a.clip_id, b.clip_id):
            item = self._clip_items.get(cid)
            if item:
                item._sync_geometry()
                item.update()

        self._capture_undo()
        self.clips_reordered.emit(clip_id_a, clip_id_b)

    def set_playhead(self, time: float):
        """Move the playhead to a specific time."""
        self._timeline._scene.playhead.time = time

    def clear(self):
        """Remove all tracks, clips, and markers."""
        for cid in list(self._clips):
            item = self._clip_items.pop(cid, None)
            if item and item.scene():
                item.scene().removeItem(item)
        self._clips.clear()
        self._tracks.clear()
        self._expanded_tracks.clear()
        self._header.clear_tracks()
        self._next_track_id = 0
        self._next_clip_id = 0
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.clear_markers()
        self.clear_range_highlight()
        self.clear_range_overlays()
        self.clear_gap_overlays()
        self._timeline._refresh_all()

    # -- marker API ---------------------------------------------------------

    def add_marker(
        self,
        time: float,
        note: str = "",
        color: Optional[str] = None,
        draggable: bool = True,
        style: str = "triangle",
        line_style: str = "dashed",
        opacity: float = 1.0,
    ) -> int:
        """Add a marker at *time*. Returns the ``marker_id``."""
        mid = self._next_marker_id
        self._next_marker_id += 1
        md = MarkerData(
            marker_id=mid,
            time=time,
            note=note,
            color=color or "#E8A84A",
            draggable=draggable,
            style=style,
            line_style=line_style,
            opacity=opacity,
        )
        self._markers[mid] = md
        item = MarkerItem(md, self._timeline)
        self._marker_items[mid] = item
        self._timeline._scene.addItem(item)
        return mid

    def remove_marker(self, marker_id: int):
        """Remove a marker by id."""
        self._markers.pop(marker_id, None)
        item = self._marker_items.pop(marker_id, None)
        if item and item.scene():
            item.scene().removeItem(item)
        self.marker_removed.emit(marker_id)

    def get_marker(self, marker_id: int) -> Optional[MarkerData]:
        """Return marker data, or None."""
        return self._markers.get(marker_id)

    def markers(self) -> List[MarkerData]:
        """Return all markers."""
        return list(self._markers.values())

    def clear_markers(self):
        """Remove all markers."""
        for mid in list(self._markers):
            item = self._marker_items.pop(mid, None)
            if item and item.scene():
                item.scene().removeItem(item)
        self._markers.clear()
        self._next_marker_id = 0

    # -- range highlight API ------------------------------------------------

    def set_range_highlight(
        self,
        start: float,
        end: float,
        color: Optional[str] = None,
        alpha: int = 30,
    ):
        """Show or update a translucent highlight over a time range.

        Parameters
        ----------
        start, end : float
            Time boundaries of the highlighted region.
        color : str, optional
            Hex color string (e.g. ``"#5A8CDC"``).  Default blue.
        alpha : int
            Opacity 0-255 for the fill (default 30).
        """
        if self._range_highlight is None:
            self._range_highlight = RangeHighlightItem(self._timeline)
            self._timeline._scene.addItem(self._range_highlight)
        self._range_highlight.set_range(start, end)
        self._range_highlight.setVisible(self._show_range_highlight)
        if color is not None:
            c = QtGui.QColor(color)
            c.setAlpha(alpha)
            self._range_highlight.color = c
        elif alpha != self._range_highlight.opacity_value:
            self._range_highlight.opacity_value = alpha

    def clear_range_highlight(self):
        """Remove the range highlight from the timeline."""
        if self._range_highlight is not None:
            if self._range_highlight.scene():
                self._range_highlight.scene().removeItem(self._range_highlight)
            self._range_highlight = None

    def add_range_overlay(
        self,
        start: float,
        end: float,
        color: str = "#888888",
        alpha: int = 15,
    ):
        """Add a non-interactive range overlay (e.g. for non-active shots)."""
        item = _StaticRangeOverlay(self._timeline, start, end, color, alpha)
        item.setVisible(self._show_range_overlays)
        self._timeline._scene.addItem(item)
        self._range_overlays.append(item)

    def clear_range_overlays(self):
        """Remove all non-interactive range overlays."""
        for item in self._range_overlays:
            if item.scene():
                item.scene().removeItem(item)
        self._range_overlays.clear()

    def add_gap_overlay(
        self,
        start: float,
        end: float,
        color: str = "#555555",
        alpha: int = 120,
    ):
        """Add a diagonal-hatch overlay for a gap between shots."""
        item = _GapOverlayItem(self._timeline, start, end, color, alpha)
        item.setVisible(self._show_gap_overlays)
        self._timeline._scene.addItem(item)
        self._gap_overlays.append(item)

    def clear_gap_overlays(self):
        """Remove all gap overlays."""
        for item in self._gap_overlays:
            if item.scene():
                item.scene().removeItem(item)
        self._gap_overlays.clear()

    def range_highlight(self) -> Optional[tuple]:
        """Return ``(start, end)`` of the active highlight, or ``None``."""
        if self._range_highlight is None:
            return None
        return (self._range_highlight.start, self._range_highlight.end)

    def set_hidden_tracks(self, names: List[str]):
        """Store a list of hidden track names for the 'show hidden' menu."""
        self._hidden_tracks = list(names)
        self._header._hidden_track_names = list(names)

    def _show_hidden_menu(self, pos):
        """Right-click on header background → menu listing hidden tracks."""
        if not self._hidden_tracks:
            return
        menu = QtWidgets.QMenu(self._header)
        menu.setTitle("Show Hidden Tracks")
        for name in sorted(self._hidden_tracks):
            menu.addAction(f"Show: {name}", lambda n=name: self.track_shown.emit(n))
        menu.exec_(self._header.mapToGlobal(pos))

    # -- playhead navigation -----------------------------------------------
    def _move_playhead(self, time: float):
        """Set the playhead to *time* and emit ``playhead_moved``."""
        self._timeline._scene.playhead.time = time
        self.playhead_moved.emit(self._timeline._scene.playhead.time)

    def step_forward(self):
        """Advance the playhead by one step (snap_interval or 1 frame)."""
        step = self._snap_interval if self._snap_interval > 0 else 1.0
        self._move_playhead(self._timeline._scene.playhead.time + step)

    def step_backward(self):
        """Move the playhead back by one step (snap_interval or 1 frame)."""
        step = self._snap_interval if self._snap_interval > 0 else 1.0
        self._move_playhead(max(0.0, self._timeline._scene.playhead.time - step))

    def go_to_start(self):
        """Jump the playhead to frame 0."""
        self._move_playhead(0.0)

    def go_to_end(self):
        """Jump the playhead to the end of the last clip."""
        self._move_playhead(max((cd.end for cd in self._clips.values()), default=0.0))

    def add_marker_at_playhead(self):
        """Add a marker at the current playhead position."""
        t = self._timeline._scene.playhead.time
        mid = self.add_marker(t)
        self.marker_added.emit(mid, t)

    def frame_shot(self):
        """Zoom and scroll the timeline to frame the active shot range.

        If a range highlight is set, frames that range.  Otherwise falls
        back to framing all clips.
        """
        rh = self.range_highlight()
        if rh is not None:
            t_min, t_max = rh
        elif self._clips:
            t_min = min(cd.start for cd in self._clips.values())
            t_max = max(cd.end for cd in self._clips.values())
        else:
            return
        span = t_max - t_min
        if span < 1.0:
            span = 1.0
        vp_w = self._timeline.viewport().width()
        padding = 40  # pixels of margin on each side
        usable = max(vp_w - padding * 2, 1)
        self._timeline._pixels_per_unit = usable / span
        self._timeline._refresh_all()
        self._timeline.horizontalScrollBar().setValue(
            int(self._timeline.time_to_x(t_min) - padding)
        )

    # Keep legacy alias so external callers aren't broken
    frame_all = frame_shot

    # -- undo / redo -------------------------------------------------------
    def _snapshot(self) -> Dict[int, tuple]:
        """Return a snapshot of all clip positions: ``{clip_id: (start, duration)}``."""
        return {cid: (cd.start, cd.duration) for cid, cd in self._clips.items()}

    def _capture_undo(self):
        """Push current clip positions onto the undo stack."""
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _restore_snapshot(self, snapshot: Dict[int, tuple]):
        """Apply a saved snapshot to all clips."""
        for cid, (start, dur) in snapshot.items():
            cd = self._clips.get(cid)
            if cd is not None:
                cd.start = start
                cd.duration = dur
        self._timeline._refresh_all()

    def undo(self):
        """Revert to the previous clip state.

        Emits :signal:`undo_requested` first.  When a controller handles
        that signal and rebuilds the widget (calling :meth:`clear`), the
        internal stack is wiped and the fallback below becomes a no-op.
        """
        self.undo_requested.emit()
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot())
        self._restore_snapshot(self._undo_stack.pop())

    def redo(self):
        """Re-apply a previously undone change.

        See :meth:`undo` for signal/fallback semantics.
        """
        self.redo_requested.emit()
        if not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        self._restore_snapshot(self._redo_stack.pop())

    # -- snapping -----------------------------------------------------------
    @property
    def snap_interval(self) -> float:
        """Time-snap interval.  0 disables snapping."""
        return self._snap_interval

    @snap_interval.setter
    def snap_interval(self, value: float):
        self._snap_interval = max(0.0, value)

    # -- gap threshold ------------------------------------------------------
    @property
    def gap_threshold(self) -> float:
        """Number of flat keys that constitute a gap between sequences."""
        return self._gap_threshold

    @gap_threshold.setter
    def gap_threshold(self, value: float):
        self._gap_threshold = max(1.0, value)

    # -- overlay visibility -------------------------------------------------
    @property
    def show_range_overlays(self) -> bool:
        return self._show_range_overlays

    @show_range_overlays.setter
    def show_range_overlays(self, value: bool):
        self._show_range_overlays = value
        for item in self._range_overlays:
            item.setVisible(value)

    @property
    def show_gap_overlays(self) -> bool:
        return self._show_gap_overlays

    @show_gap_overlays.setter
    def show_gap_overlays(self, value: bool):
        self._show_gap_overlays = value
        for item in self._gap_overlays:
            item.setVisible(value)

    @property
    def show_range_highlight(self) -> bool:
        return self._show_range_highlight

    @show_range_highlight.setter
    def show_range_highlight(self, value: bool):
        self._show_range_highlight = value
        if self._range_highlight is not None:
            self._range_highlight.setVisible(value)

    # -- attribute colors ---------------------------------------------------
    @property
    def attribute_colors(self) -> Dict[str, str]:
        """Mapping of attribute name to hex color string."""
        return self._attribute_colors

    @attribute_colors.setter
    def attribute_colors(self, value: Dict[str, str]):
        self._attribute_colors = dict(value)
        self._timeline._scene.update()

    # -- sub-row expansion --------------------------------------------------
    @property
    def sub_row_height(self) -> int:
        """Pixel height of expanded attribute sub-rows (default half track height)."""
        return self._sub_row_height

    @sub_row_height.setter
    def sub_row_height(self, value: int):
        self._sub_row_height = max(8, value)
        self._timeline._refresh_all()

    @property
    def sub_row_provider(self):
        """Callable providing sub-row data for track expansion.

        Signature: ``(track_id, track_name) -> [(sub_name, [(start, dur, label, color), ...]), ...]``

        When set, double-clicking (or toggling) a track header calls this
        function, creates the sub-rows and their clips automatically, and
        emits ``track_expanded``.  Set to ``None`` to disable expansion.
        """
        return self._sub_row_provider

    @sub_row_provider.setter
    def sub_row_provider(self, fn):
        self._sub_row_provider = fn

    def expand_track(self, track_id: int, sub_row_data=None):
        """Expand *track_id* to show sub-rows beneath it.

        Parameters
        ----------
        sub_row_data : list, optional
            ``[(sub_name, [(start, dur, label, color), ...]), ...]``.
            If omitted, the ``sub_row_provider`` callback is used.
            If neither is available, does nothing.
        """
        if sub_row_data is None and self._sub_row_provider:
            td = self.get_track(track_id)
            if td is None:
                return
            sub_row_data = self._sub_row_provider(track_id, td.name)
        if not sub_row_data:
            return

        sub_names = [name for name, _ in sub_row_data]
        self._expanded_tracks[track_id] = sub_names

        # Remove stale sub-row clips for this track
        stale = [
            cid
            for cid, cd in self._clips.items()
            if cd.track_id == track_id and cd.sub_row
        ]
        for cid in stale:
            self.remove_clip(cid)

        # Create clips for each sub-row
        for sub_name, segments in sub_row_data:
            for seg in segments:
                start, dur = seg[0], seg[1]
                label = seg[2] if len(seg) > 2 else sub_name
                color = seg[3] if len(seg) > 3 else None
                extra = seg[4] if len(seg) > 4 else {}
                # Single-key (zero-duration) sub-row clips are fixed
                is_point = dur < 1e-6
                if is_point:
                    extra.setdefault("locked", True)
                    extra.setdefault("resizable_left", False)
                    extra.setdefault("resizable_right", False)
                self.add_clip(
                    track_id,
                    start,
                    dur,
                    label=label,
                    color=color,
                    sub_row=sub_name,
                    **extra,
                )

        idx = self._track_index(track_id)
        if idx is not None:
            self._header.set_track_expanded(idx, sub_names, self._sub_row_height)
        self._timeline._refresh_all()
        self.track_expanded.emit(track_id)

    def collapse_track(self, track_id: int):
        """Collapse a previously expanded track, removing its sub-row clips."""
        if track_id not in self._expanded_tracks:
            return
        self._expanded_tracks.pop(track_id)
        # Remove sub-row clips
        to_remove = [
            cid
            for cid, cd in self._clips.items()
            if cd.track_id == track_id and cd.sub_row
        ]
        for cid in to_remove:
            self.remove_clip(cid)
        idx = self._track_index(track_id)
        if idx is not None:
            self._header.set_track_collapsed(idx)
        self._timeline._refresh_all()
        self.track_collapsed.emit(track_id)

    def is_track_expanded(self, track_id: int) -> bool:
        """Return True if the track is currently expanded."""
        return track_id in self._expanded_tracks

    def toggle_track_expanded(self, track_id: int):
        """Toggle expansion state.  Uses ``sub_row_provider`` when expanding."""
        if self.is_track_expanded(track_id):
            self.collapse_track(track_id)
        else:
            self.expand_track(track_id)

    def _row_position(self, track_id: int, sub_row: str = "") -> tuple:
        """Return ``(y, height)`` for a given track and optional sub-row."""
        y = _RULER_HEIGHT
        for td in self._tracks:
            if td.track_id == track_id:
                if not sub_row:
                    return y, _TRACK_HEIGHT
                y += _TRACK_HEIGHT + _TRACK_PADDING
                for sr in self._expanded_tracks.get(td.track_id, []):
                    if sr == sub_row:
                        return y, self._sub_row_height
                    y += self._sub_row_height + _TRACK_PADDING
                return y, self._sub_row_height
            y += _TRACK_HEIGHT + _TRACK_PADDING
            sub_rows = self._expanded_tracks.get(td.track_id, [])
            y += len(sub_rows) * (self._sub_row_height + _TRACK_PADDING)
        return y, _TRACK_HEIGHT

    def _total_row_height(self) -> float:
        """Total pixel height of all tracks including expanded sub-rows."""
        h = 0.0
        for td in self._tracks:
            h += _TRACK_HEIGHT + _TRACK_PADDING
            sub_rows = self._expanded_tracks.get(td.track_id, [])
            h += len(sub_rows) * (self._sub_row_height + _TRACK_PADDING)
        return h

    def _visual_rows(self) -> List[tuple]:
        """Return ``[(y, height, is_sub_row), ...]`` for background painting."""
        rows = []
        y = _RULER_HEIGHT
        for td in self._tracks:
            rows.append((y, _TRACK_HEIGHT, False))
            y += _TRACK_HEIGHT + _TRACK_PADDING
            for sr in self._expanded_tracks.get(td.track_id, []):
                rows.append((y, self._sub_row_height, True))
                y += self._sub_row_height + _TRACK_PADDING
        return rows

    def _track_index(self, track_id: int) -> Optional[int]:
        """Return the list index for *track_id*, or None."""
        for i, td in enumerate(self._tracks):
            if td.track_id == track_id:
                return i
        return None

    def _on_header_expand(self, label_idx: int):
        """Handle double-click on a header label to toggle expansion."""
        if label_idx < len(self._tracks):
            self.toggle_track_expanded(self._tracks[label_idx].track_id)

    # -- selection ----------------------------------------------------------
    def selected_clips(self) -> List[int]:
        """Return clip IDs for all currently selected clips."""
        try:
            items = self._timeline._scene.selectedItems()
        except RuntimeError:
            return []
        return [item.clip_data.clip_id for item in items if isinstance(item, ClipItem)]

    # -- internal -----------------------------------------------------------
    def _on_scene_selection(self):
        sel = self.selected_clips()
        self.selection_changed.emit(sel)
        # Backwards-compat: also emit clip_selected for the first item
        if sel:
            self.clip_selected.emit(sel[0])

    def _on_splitter_moved(self, pos: int, index: int):
        """Snap-close the header pane when dragged below threshold."""
        if index != 1:  # only respond to the first handle
            return
        if pos < self._header_snap_threshold:
            self.setSizes([0, self.width()])
        elif pos > 0 and self.sizes()[0] == 0:
            # Re-opening from collapsed: restore default width
            self.setSizes(
                [self._header_snap_width, self.width() - self._header_snap_width]
            )
