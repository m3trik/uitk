# !/usr/bin/python
# coding=utf-8
"""KeyframeItem — selectable, draggable keyframe dot on an attribute sub-row."""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Tuple

from qtpy import QtWidgets, QtGui, QtCore

if TYPE_CHECKING:
    from uitk.widgets.sequencer._clip import ClipItem


class KeyframeItem(QtWidgets.QGraphicsEllipseItem):
    """An interactive keyframe indicator inside a sub-row :class:`ClipItem`.

    Each instance represents a single keyframe at a specific time and value.
    Keys are children of a :class:`ClipItem` but render un-clipped so they
    are not cropped at clip edges.

    Parameters
    ----------
    time : float
        Absolute time of the keyframe.
    value : float
        Absolute value of the keyframe.
    is_stepped : bool
        If *True* draw a square; otherwise draw a circle.
    parent_clip : ClipItem
        The owning clip item (set as QGraphicsItem parent).
    """

    _DOT_RADIUS = 3.5

    def __init__(
        self,
        time: float,
        value: float,
        is_stepped: bool,
        parent_clip: "ClipItem",
    ):
        r = self._DOT_RADIUS
        # EllipseItem rect is in local coords, centered at (0, 0).
        super().__init__(-r, -r, 2 * r, 2 * r, parent_clip)
        self._time = time
        self._value = value
        self._is_stepped = is_stepped
        self._parent_clip = parent_clip

        # Drag state
        self._dragging = False
        self._drag_origin_scene_x = 0.0
        self._drag_peers: List[Tuple["KeyframeItem", float]] = []

        self.setAcceptHoverEvents(True)
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemIgnoresParentOpacity
        )
        # Render on top of the parent clip's curve path.
        self.setZValue(1)

    # -- public accessors ---------------------------------------------------

    @property
    def time(self) -> float:
        return self._time

    @property
    def value(self) -> float:
        return self._value

    # -- painting -----------------------------------------------------------

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        clip = self._parent_clip
        color = clip._resolve_color()
        fg = clip._foreground_for(color)

        key_color = QtGui.QColor(color)
        if self.isSelected():
            key_color = key_color.lighter(150)

        painter.setBrush(key_color)
        painter.setPen(QtGui.QPen(fg, 0.6))

        r = self._DOT_RADIUS
        if self._is_stepped:
            painter.drawRect(QtCore.QRectF(-r, -r, 2 * r, 2 * r))
        else:
            painter.drawEllipse(QtCore.QRectF(-r, -r, 2 * r, 2 * r))

    def boundingRect(self) -> QtCore.QRectF:
        r = self._DOT_RADIUS + 1  # slight padding for anti-aliased pen
        return QtCore.QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self) -> QtGui.QPainterPath:
        """Larger hit area for easier clicking."""
        p = QtGui.QPainterPath()
        hit_r = self._DOT_RADIUS + 2
        p.addEllipse(QtCore.QRectF(-hit_r, -hit_r, 2 * hit_r, 2 * hit_r))
        return p

    # -- hover --------------------------------------------------------------

    def hoverEnterEvent(self, event):
        self.setCursor(QtCore.Qt.SizeHorCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    # -- drag interaction ---------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            super().mousePressEvent(event)
            return

        # Let Qt handle selection toggling (Shift/Ctrl modifiers).
        super().mousePressEvent(event)

        # Re-select the parent clip so the controller's clip context
        # isn't lost when Qt's default handler deselects other items.
        if not self._parent_clip.isSelected():
            self._parent_clip.setSelected(True)

        self._dragging = True
        self._drag_origin_scene_x = event.scenePos().x()

        # Snapshot origin times for all selected KeyframeItems
        # (including self) for coordinated multi-key dragging.
        self._drag_peers = []
        scene = self.scene()
        if scene:
            for item in scene.selectedItems():
                if isinstance(item, KeyframeItem):
                    self._drag_peers.append((item, item._time))

        # Mark all affected parent clips as having a key drag in progress.
        for peer, _ in self._drag_peers:
            peer._parent_clip._keys_dragging = True

        # Capture undo snapshot on the sequencer.
        sq = self._parent_clip._timeline.parent_sequencer
        sq._capture_undo()

        event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return

        tl = self._parent_clip._timeline
        dx_time = tl.x_to_time(event.scenePos().x()) - tl.x_to_time(
            self._drag_origin_scene_x
        )

        # Snap the delta so all peers shift by the same snapped amount.
        snapped_delta = self._parent_clip._snap(dx_time)

        # Collect unique parent clips and notify them that their
        # bounding rect will change before we move any keys.
        affected: dict = {}  # id -> ClipItem
        for peer, _ in self._drag_peers:
            pid = id(peer._parent_clip)
            if pid not in affected:
                affected[pid] = peer._parent_clip
        for clip in affected.values():
            clip.prepareGeometryChange()

        for peer, origin_time in self._drag_peers:
            new_time = max(0.0, origin_time + snapped_delta)
            peer._time = new_time
            peer._reposition()

        # Invalidate each clip's scene region so the graphics view
        # fully repaints background, curve, and key dots.
        for clip in affected.values():
            scene = clip.scene()
            if scene:
                scene.invalidate(clip.mapToScene(clip.boundingRect()).boundingRect())
            else:
                clip.update()

        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._dragging:
            self._dragging = False

            # Clear drag flag on all affected parent clips and
            # notify them their bounding rect will shrink back.
            affected = set()
            for peer, _ in self._drag_peers:
                clip = peer._parent_clip
                pid = id(clip)
                if pid not in affected:
                    clip.prepareGeometryChange()
                    clip._keys_dragging = False
                    affected.add(pid)

            # Group moved keys by parent clip so each clip gets its
            # own signal with only its own key changes.
            by_clip: dict = {}  # clip_id -> [(old_t, new_t), ...]
            for peer, origin_time in self._drag_peers:
                if abs(peer._time - origin_time) > 1e-6:
                    cid = peer._parent_clip._data.clip_id
                    by_clip.setdefault(cid, []).append((origin_time, peer._time))
            self._drag_peers = []

            if by_clip:
                sq = self._parent_clip._timeline.parent_sequencer
                for clip_id, changes in by_clip.items():
                    sq.keys_moved.emit(clip_id, changes)

            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # -- positioning --------------------------------------------------------

    def _reposition(self):
        """Update scene position from current time/value using the parent
        clip's coordinate mapping."""
        clip = self._parent_clip
        rect = clip.rect()
        preview = clip._data.data.get("curve_preview", {})
        val_min = preview.get("val_min", 0.0)
        val_max = preview.get("val_max", 1.0)
        val_range = val_max - val_min
        if val_range < 1e-9:
            val_range = 1.0

        dur = clip._data.duration
        start = clip._data.start

        # X mapping (time -> pixel)
        if dur > 1e-6:
            frac = (self._time - start) / dur
        else:
            frac = 0.5
        sx = rect.x() + frac * rect.width()

        # Y mapping (value -> pixel)
        pad = rect.height() * 0.15
        y_top = rect.top() + pad
        y_bot = rect.bottom() - pad
        is_flat = (val_max - val_min) < 1e-9
        if is_flat:
            sy = y_top + (y_bot - y_top) * 0.5
        else:
            vfrac = (self._value - val_min) / val_range
            sy = y_bot - vfrac * (y_bot - y_top)

        self.setPos(sx, sy)
