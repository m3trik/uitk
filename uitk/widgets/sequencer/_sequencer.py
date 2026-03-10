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


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
_TRACK_HEIGHT = 28
_TRACK_PADDING = 2
_RULER_HEIGHT = 24
_HANDLE_WIDTH = 6  # pixels from edge that activates resize cursor
_MIN_CLIP_DURATION = 1.0
_MIN_POINT_CLIP_WIDTH = 8  # minimum pixel width for zero-duration clips
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
        self._waveform_pixmap: Optional[QtGui.QPixmap] = None
        self._waveform_pixmap_size: Optional[tuple] = None
        self.setAcceptHoverEvents(True)
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        self._sync_geometry()

    def _snap(self, value: float) -> float:
        """Snap *value* to the nearest grid interval if snapping is enabled."""
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
        track_y = _RULER_HEIGHT + self._track_index() * (_TRACK_HEIGHT + _TRACK_PADDING)
        # Zero-duration (point) clips get a minimum visual width, centered
        if w < _MIN_POINT_CLIP_WIDTH:
            x -= (_MIN_POINT_CLIP_WIDTH - w) / 2.0
            w = _MIN_POINT_CLIP_WIDTH
        new_rect = QtCore.QRectF(x, track_y, max(w, 1), _TRACK_HEIGHT)
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

    # -- painting -----------------------------------------------------------
    def paint(self, painter: QtGui.QPainter, option, widget=None):
        rect = self.rect()
        color = QtGui.QColor(self._data.color or "#5B8BD4")
        if self.isSelected():
            color = color.lighter(130)

        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, 4, 4)

        # Waveform overlay (if envelope data is present)
        waveform = self._data.data.get("waveform")
        if waveform and rect.width() > 4:
            self._paint_waveform(painter, rect, waveform, color)

        # Label
        if rect.width() > 30:
            painter.setPen(QtGui.QColor("#FFFFFF"))
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            text_rect = rect.adjusted(6, 0, -6, 0)
            painter.drawText(
                text_rect,
                QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                self._data.label,
            )

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
            self._drag_mode = self._hit_zone(event.pos())
            self._drag_origin_x = event.scenePos().x()
            self._drag_origin_start = self._data.start
            self._drag_origin_duration = self._data.duration
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
            self._drag_mode = None
            self.unsetCursor()
            widget = self._timeline.parent_sequencer
            if mode == "move":
                widget.clip_moved.emit(self._data.clip_id, self._data.start)
            else:
                widget.clip_resized.emit(
                    self._data.clip_id, self._data.start, self._data.duration
                )
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # -- utilities ----------------------------------------------------------
    def _hit_zone(self, pos) -> str:
        rect = self.rect()
        local_x = pos.x() - rect.x()
        if local_x <= _HANDLE_WIDTH and self._data.data.get(
            "resizable_left", True
        ):
            return "resize_left"
        elif local_x >= rect.width() - _HANDLE_WIDTH and self._data.data.get(
            "resizable_right", True
        ):
            return "resize_right"
        return "move"


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
class PlayheadItem(QtWidgets.QGraphicsLineItem):
    """A vertical line representing the current time / playhead."""

    def __init__(self, timeline: "TimelineView"):
        super().__init__()
        self._timeline = timeline
        self._time = 0.0
        self.setPen(QtGui.QPen(QtGui.QColor("#E8E84A"), 1.5))
        self.setZValue(20)
        # sync() is deferred until the scene/view wiring is complete

    @property
    def time(self) -> float:
        return self._time

    @time.setter
    def time(self, value: float):
        self._time = max(0.0, value)
        self.sync()

    def sync(self):
        x = self._timeline.time_to_x(self._time)
        scene_h = self._timeline._scene.height() if self._timeline._scene else 2000
        self.setLine(x, 0, x, scene_h)


# ---------------------------------------------------------------------------
#  MarkerItem
# ---------------------------------------------------------------------------
_MARKER_TRI_SIZE = 8  # size of the triangle pennant in pixels


class MarkerItem(QtWidgets.QGraphicsItem):
    """A named marker on the timeline: triangle at the ruler + dashed line."""

    def __init__(
        self, marker_data: MarkerData, timeline: "TimelineView"
    ):
        super().__init__()
        self._data = marker_data
        self._timeline = timeline
        self._drag_active = False
        self._drag_origin_x = 0.0
        self._drag_origin_time = 0.0
        self.setZValue(15)
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable)
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

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        color = QtGui.QColor(self._data.color)
        x = self._timeline.time_to_x(self._data.time)

        # Triangle at the ruler
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        tri = QtGui.QPolygonF(
            [
                QtCore.QPointF(x, _RULER_HEIGHT),
                QtCore.QPointF(x - _MARKER_TRI_SIZE / 2, _RULER_HEIGHT - _MARKER_TRI_SIZE),
                QtCore.QPointF(x + _MARKER_TRI_SIZE / 2, _RULER_HEIGHT - _MARKER_TRI_SIZE),
            ]
        )
        painter.setBrush(color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawPolygon(tri)

        # Dashed vertical line below ruler
        pen = QtGui.QPen(color, 1, QtCore.Qt.DashLine)
        painter.setPen(pen)
        scene_h = self._timeline._scene.height() if self._timeline._scene else 2000
        painter.drawLine(
            QtCore.QPointF(x, _RULER_HEIGHT),
            QtCore.QPointF(x, scene_h),
        )

        # Optional note label beside the triangle
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
        self.setCursor(QtCore.Qt.OpenHandCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    # -- drag (horizontal only) ---------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_active = True
            self._drag_origin_x = event.scenePos().x()
            self._drag_origin_time = self._data.time
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._drag_active:
            return super().mouseMoveEvent(event)
        tl = self._timeline
        dx_time = tl.x_to_time(event.scenePos().x()) - tl.x_to_time(
            self._drag_origin_x
        )
        new_time = max(0.0, self._drag_origin_time + dx_time)
        interval = tl.parent_sequencer.snap_interval
        if interval > 0:
            new_time = round(new_time / interval) * interval
        self._data.time = new_time
        self.sync()
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._drag_active:
            self._drag_active = False
            self.unsetCursor()
            widget = self._timeline.parent_sequencer
            widget.marker_moved.emit(self._data.marker_id, self._data.time)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # -- context menu -------------------------------------------------------

    def contextMenuEvent(self, event):
        widget = self._timeline.parent_sequencer
        menu = QtWidgets.QMenu()

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


# ---------------------------------------------------------------------------
#  TrackHeaderWidget
# ---------------------------------------------------------------------------
class TrackHeaderWidget(QtWidgets.QWidget):
    """Left-pane widget showing track labels, vertically synced to the timeline."""

    track_hide_requested = QtCore.Signal(list)  # [track_name, ...]
    track_show_requested = QtCore.Signal(str)  # track_name to un-hide
    track_selected = QtCore.Signal(list)  # [track_name, ...] clicked

    _STYLE_NORMAL = (
        "padding-left:6px; color:#CCCCCC; background:#333333; border-radius:3px;"
    )
    _STYLE_SELECTED = (
        "padding-left:6px; color:#FFFFFF; background:#505050; border-radius:3px;"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels: List[QtWidgets.QLabel] = []
        self._names: List[str] = []  # parallel to _labels
        self._selected: List[int] = []  # indices of selected labels
        self._hidden_track_names: List[str] = []  # set by SequencerWidget
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, _RULER_HEIGHT, 0, 0)
        self._layout.setSpacing(_TRACK_PADDING)
        self._layout.addStretch()

    def add_track_label(self, name: str):
        lbl = QtWidgets.QLabel(name)
        lbl.setFixedHeight(_TRACK_HEIGHT)
        lbl.setStyleSheet(self._STYLE_NORMAL)
        lbl.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        lbl.customContextMenuRequested.connect(
            lambda pos, w=lbl: self._show_label_menu(w, pos)
        )
        lbl.installEventFilter(self)
        idx = self._layout.count() - 1  # before the stretch
        self._layout.insertWidget(idx, lbl)
        self._labels.append(lbl)
        self._names.append(name)

    # -- selection ---------------------------------------------------------

    def eventFilter(self, obj, event):
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
            lbl.setStyleSheet(
                self._STYLE_SELECTED if i in self._selected else self._STYLE_NORMAL
            )

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

        # "Show Hidden" submenu — only when hidden tracks exist
        hidden = self._hidden_track_names
        if hidden:
            sub = menu.addMenu(f"Show Hidden ({len(hidden)})")
            for name in sorted(hidden):
                sub.addAction(name, lambda n=name: self.track_show_requested.emit(n))

        menu.exec_(widget.mapToGlobal(pos))

    def clear_tracks(self):
        for lbl in self._labels:
            lbl.removeEventFilter(self)
            self._layout.removeWidget(lbl)
            lbl.deleteLater()
        self._labels.clear()
        self._names.clear()
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
            t = self.x_to_time(scene_pos.x())
            self._scene.playhead.time = t
            self.parent_sequencer.playhead_moved.emit(t)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_active:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            hs = self.horizontalScrollBar()
            vs = self.verticalScrollBar()
            hs.setValue(hs.value() - delta.x())
            vs.setValue(vs.value() - delta.y())
            event.accept()
        elif self._ruler_drag:
            scene_pos = self.mapToScene(event.pos())
            t = self.x_to_time(scene_pos.x())
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
            super().mouseReleaseEvent(event)

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
        """Right-click on the timeline background to add a marker with a note."""
        # Only show on the background — not when clicking a clip or marker
        item = self.itemAt(event.pos())
        if isinstance(item, (ClipItem, MarkerItem)):
            super().contextMenuEvent(event)
            return

        scene_pos = self.mapToScene(event.pos())
        t = self.x_to_time(scene_pos.x())
        interval = self.parent_sequencer.snap_interval
        if interval > 0:
            t = round(t / interval) * interval

        menu = QtWidgets.QMenu(self)
        add_action = menu.addAction(f"Add Marker at {int(t)}\u2026")
        chosen = menu.exec_(event.globalPos())

        if chosen == add_action:
            note, ok = QtWidgets.QInputDialog.getText(
                self.parent_sequencer,
                "Marker Note",
                "Note:",
                QtWidgets.QLineEdit.Normal,
                "",
            )
            if ok:
                mid = self.parent_sequencer.add_marker(t, note=note)
                self.parent_sequencer.marker_added.emit(mid, t)

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
        self._sync_ruler_pos()
        self._scene.playhead.sync()
        self._update_scene_rect()
        self.viewport().update()

    def _update_scene_rect(self):
        """Ensure the scene is large enough to contain all clips and markers."""
        sq = self.parent_sequencer
        max_end = 100.0
        for cd in sq._clips.values():
            max_end = max(max_end, cd.end)
        for md in sq._markers.values():
            max_end = max(max_end, md.time)
        track_count = max(1, len(sq._tracks))
        w = self.time_to_x(max_end) + 200
        h = _RULER_HEIGHT + track_count * (_TRACK_HEIGHT + _TRACK_PADDING) + 40
        self._scene.setSceneRect(0, 0, w, h)

    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF):
        """Draw alternating track row backgrounds."""
        painter.fillRect(rect, QtGui.QColor("#1E1E1E"))
        sq = self.parent_sequencer
        for i in range(len(sq._tracks)):
            y = _RULER_HEIGHT + i * (_TRACK_HEIGHT + _TRACK_PADDING)
            bg = QtGui.QColor("#262626") if i % 2 == 0 else QtGui.QColor("#2A2A2A")
            painter.fillRect(
                QtCore.QRectF(rect.left(), y, rect.width(), _TRACK_HEIGHT), bg
            )


# ---------------------------------------------------------------------------
#  SequencerWidget  (the public API)
# ---------------------------------------------------------------------------
class SequencerWidget(QtWidgets.QSplitter, AttributesMixin):
    """A split-view NLE sequencer widget.

    Signals
    -------
    clip_moved(int, float)
        Emitted when a clip is repositioned.  Args: ``(clip_id, new_start)``.
    clip_resized(int, float, float)
        Emitted when a clip edge is dragged.  Args: ``(clip_id, new_start, new_duration)``.
    clip_selected(int)
        Emitted when a clip is clicked.  Args: ``(clip_id,)``.
    playhead_moved(float)
        Emitted when the playhead is repositioned.  Args: ``(time,)``.
    """

    clip_moved = QtCore.Signal(int, float)
    clip_resized = QtCore.Signal(int, float, float)
    clip_selected = QtCore.Signal(int)
    selection_changed = QtCore.Signal(list)
    playhead_moved = QtCore.Signal(float)
    track_hidden = QtCore.Signal(list)  # [track_name, ...] hidden via context menu
    track_shown = QtCore.Signal(str)  # track_name un-hidden via menu
    track_selected = QtCore.Signal(list)  # [track_name, ...] clicked in header
    undo_requested = QtCore.Signal()
    redo_requested = QtCore.Signal()
    marker_added = QtCore.Signal(int, float)  # (marker_id, time)
    marker_moved = QtCore.Signal(int, float)  # (marker_id, new_time)
    marker_changed = QtCore.Signal(int)  # (marker_id) after note/color edit
    marker_removed = QtCore.Signal(int)  # (marker_id)

    def __init__(self, parent=None, **kwargs):
        super().__init__(QtCore.Qt.Horizontal, parent)

        # -- state ----------------------------------------------------------
        self._tracks: List[TrackData] = []
        self._clips: Dict[int, ClipData] = {}
        self._clip_items: Dict[int, ClipItem] = {}
        self._next_track_id = 0
        self._next_clip_id = 0
        self._snap_interval: float = 0.0  # 0 = disabled
        self._undo_stack: List[Dict[int, tuple]] = []  # (start, duration) per clip_id
        self._redo_stack: List[Dict[int, tuple]] = []
        self._max_undo = 50
        self._markers: Dict[int, MarkerData] = {}
        self._marker_items: Dict[int, MarkerItem] = {}
        self._next_marker_id = 0

        # -- sub-widgets ----------------------------------------------------
        self._header = TrackHeaderWidget()
        self._header_scroll = QtWidgets.QScrollArea()
        self._header_scroll.setWidget(self._header)
        self._header_scroll.setWidgetResizable(True)
        self._header_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._header_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._header_scroll.setStyleSheet("background:#2B2B2B; border:none;")
        self._header_scroll.setFixedWidth(140)

        self._timeline = TimelineView(self)

        self.addWidget(self._header_scroll)
        self.addWidget(self._timeline)
        self.setSizes([140, 600])
        self.setHandleWidth(2)

        # -- sync vertical scroll -------------------------------------------
        self._timeline.verticalScrollBar().valueChanged.connect(
            self._header_scroll.verticalScrollBar().setValue
        )

        # -- forward track-hide/show/select from header ----------------------
        self._header.track_hide_requested.connect(self.track_hidden.emit)
        self._header.track_show_requested.connect(self.track_shown.emit)
        self._header.track_selected.connect(self.track_selected.emit)

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

    # -- public API ---------------------------------------------------------
    def add_track(self, name: str) -> int:
        """Add a new track row.  Returns the ``track_id``."""
        tid = self._next_track_id
        self._next_track_id += 1
        td = TrackData(track_id=tid, name=name)
        self._tracks.append(td)
        self._header.add_track_label(name)
        self._timeline._update_scene_rect()
        return tid

    def add_clip(
        self,
        track_id: int,
        start: float,
        duration: float,
        label: str = "",
        color: Optional[str] = None,
        **data,
    ) -> int:
        """Add a clip to an existing track.  Returns the ``clip_id``."""
        cid = self._next_clip_id
        self._next_clip_id += 1
        if color is None:
            color = _DEFAULT_CLIP_COLORS[cid % len(_DEFAULT_CLIP_COLORS)]
        cd = ClipData(
            clip_id=cid,
            track_id=track_id,
            start=start,
            duration=duration,
            label=label,
            color=color,
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
        for cid in list(td.clips):
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
        self._header.clear_tracks()
        self._next_track_id = 0
        self._next_clip_id = 0
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.clear_markers()
        self._timeline._refresh_all()

    # -- marker API ---------------------------------------------------------

    def add_marker(
        self,
        time: float,
        note: str = "",
        color: Optional[str] = None,
    ) -> int:
        """Add a marker at *time*. Returns the ``marker_id``."""
        mid = self._next_marker_id
        self._next_marker_id += 1
        md = MarkerData(
            marker_id=mid,
            time=time,
            note=note,
            color=color or "#E8A84A",
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
