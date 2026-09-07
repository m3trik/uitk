# !/usr/bin/python
# coding=utf-8
"""KeyframeItem — selectable, draggable keyframe dot on an attribute sub-row."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

from qtpy import QtWidgets, QtGui, QtCore

from uitk.widgets.sequencer._data import CurveUtils, MenuUtils
from uitk.widgets.sequencer._drag_tooltip import FrameTooltip
from uitk.widgets.sequencer._draggable import DraggableItemMixin

if TYPE_CHECKING:
    from uitk.widgets.sequencer._clip import ClipItem


class KeyframeItem(DraggableItemMixin, QtWidgets.QGraphicsEllipseItem):
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
        self._drag_tooltip = FrameTooltip()
        self._align_times = None  # alignment candidates, resolved on first move
        self._align_hit: bool = False  # drag currently sits on a key frame

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

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemSelectedHasChanged:
            # The tangent handles come and go with the selection: the CLIP
            # paints the handle lines (its rect already spans them; growing
            # the key's own rect on selection put it inside marquees it was
            # never under) and owns the grab points, so it is what resyncs
            # and repaints.
            self._parent_clip._sync_tangent_handles()
            self._parent_clip.update()
        return super().itemChange(change, value)

    # -- tangent handles ----------------------------------------------------

    def _key_index(self) -> int:
        """Position among the parent clip's keys (preview order), or -1."""
        for i, ki in enumerate(self._parent_clip._keyframe_items):
            if ki is self:
                return i
        return -1

    def _tangent_slots(self, index: Optional[int] = None) -> List[tuple]:
        """``[(side, segment index, control-point key), ...]`` for this key's
        IN and OUT handles that exist.

        Read from the parent clip's ``curve_preview``: the OUT handle is
        ``cp1`` of the segment this key opens, the IN handle ``cp2`` of the
        one it closes.  Nothing on a stepped or linear span (no control
        points there).  Nothing at all on a clip that refuses key edits
        (:attr:`ClipItem.keys_editable`) -- the one gate both the painted
        handle lines and the draggable grab points read.  *index* is this
        key's position among the clip's keys when the caller already knows
        it (the clip walks them in order); otherwise it is looked up, a
        linear scan.
        """
        if not self._parent_clip.keys_editable:
            return []
        segments = self._segments()
        idx = self._key_index() if index is None else index
        if idx < 0 or not segments:
            return []
        slots = []
        if 0 < idx <= len(segments) and segments[idx - 1].get("cp2") is not None:
            slots.append(("in", idx - 1, "cp2"))
        if idx < len(segments) and segments[idx].get("cp1") is not None:
            slots.append(("out", idx, "cp1"))
        return slots

    def _segments(self) -> list:
        preview = self._parent_clip._data.data.get("curve_preview") or {}
        return preview.get("segments") or []

    def is_broken(self, index: Optional[int] = None) -> bool:
        """True when this key's tangents are broken (IN and OUT independent).

        Read from the preview's optional ``broken`` list, one flag per key
        in ``keys`` order; a preview without it has no broken keys.  A
        broken key draws its handle lines dotted, as the Graph Editor does.
        """
        preview = self._parent_clip._data.data.get("curve_preview") or {}
        flags = preview.get("broken") or ()
        idx = self._key_index() if index is None else index
        return 0 <= idx < len(flags) and bool(flags[idx])

    def _tangent_handles(self, index: Optional[int] = None) -> List[QtCore.QPointF]:
        """Clip-local endpoints of this key's IN and OUT tangent handles.

        Hidden until the key is selected -- a sub-row is a strip a few pixels
        tall, and every key sprouting two lines would bury the curve -- and
        nothing mid-drag, when the preview is being re-timed live under the
        keys.  In the very coordinates the clip draws its curve with, so a
        handle lies ON the curve it shapes -- which is why the CLIP paints
        the handle lines (:meth:`ClipItem._paint_tangent_handles`); the grab
        points are :class:`TangentHandleItem` children of the clip.
        """
        clip = self._parent_clip
        if not self.isSelected() or clip._keys_dragging:
            return []
        segments = self._segments()
        return [
            self._clip_point(*segments[i][cp_key])
            for _side, i, cp_key in self._tangent_slots(index)
        ]

    def _clip_point(self, t: float, v: float) -> QtCore.QPointF:
        """Clip-local pixel position of curve point ``(t, v)``.

        The one mapping the key dot, its tangent handles and the clip's own
        curve preview share, so all three stay pixel-aligned.
        """
        clip = self._parent_clip
        rect = clip.rect()
        preview = clip._data.data.get("curve_preview", {})
        dur = clip._data.duration
        start = clip._data.start
        frac = (t - start) / dur if dur > 1e-6 else 0.5
        map_y, _is_flat = CurveUtils.make_value_mapper(
            rect.top(),
            rect.height(),
            preview.get("val_min", 0.0),
            preview.get("val_max", 1.0),
        )
        return QtCore.QPointF(rect.x() + frac * rect.width(), map_y(v))

    def _curve_coords(self, point: QtCore.QPointF) -> Tuple[float, float]:
        """The ``(t, v)`` a clip-local *point* stands for: :meth:`_clip_point`
        run backwards, for a handle dragged in pixels."""
        clip = self._parent_clip
        rect = clip.rect()
        preview = clip._data.data.get("curve_preview", {})
        dur = clip._data.duration
        frac = (point.x() - rect.x()) / rect.width() if rect.width() > 1e-6 else 0.0
        t = clip._data.start + frac * dur
        v = CurveUtils.unmap_value(
            rect.top(),
            rect.height(),
            preview.get("val_min", 0.0),
            preview.get("val_max", 1.0),
            point.y(),
        )
        return t, v

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

        if not self._parent_clip.keys_editable:
            # Selection only.  A locked or read-only row refuses clip drags
            # already (:meth:`ClipItem.mousePressEvent`); its keys drove
            # straight through, and the drag was committed to the host.
            super().mousePressEvent(event)
            return

        # Record the modifiers for the consumers' gates (mirrors the
        # clip/gap writers) — without this a key drag inherits whatever the
        # LAST clip/gap gesture left in the widget-level flags.
        self._parent_clip._timeline.parent_sequencer.record_press_modifiers(
            event.modifiers()
        )

        # Let Qt handle selection toggling (Shift/Ctrl modifiers).
        super().mousePressEvent(event)

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
        # Ctrl-click defers selection toggling to release, so the grabbed
        # key may not be in selectedItems() yet — without it the alignment
        # lead would be a key that never moves, its clip would escape the
        # exclusion set, and the emitted changes would omit the grabbed key.
        if not any(p is self for p, _ in self._drag_peers):
            self._drag_peers.append((self, self._time))

        # Mark all affected parent clips as having a key drag in progress.
        for peer, _ in self._drag_peers:
            peer._parent_clip._keys_dragging = True
            peer._parent_clip._sync_tangent_handles()

        # Alignment candidates are resolved lazily on the first real move:
        # the set can't change mid-gesture, but resolving it here would make
        # every plain key click walk each clip and key for nothing.
        self._align_times = None

        # No widget-level undo snapshot for key drags: the snapshot only
        # records clip bounds (not key times), so it could never restore
        # a key edit — capturing here just burned an undo step and wiped
        # the redo stack on every key click.  Key edits are undone
        # through the host app (keys_moved consumers → Maya undo).

        self._show_drag_tooltip(event.scenePos())
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

        # Alignment is measured on the grabbed key, then applied to the whole
        # selection as one delta — otherwise peers would drift apart.
        sq = self._parent_clip._timeline.parent_sequencer
        if self._align_times is None:
            moving = {p._parent_clip._data.clip_id for p, _ in self._drag_peers}
            self._align_times = sq.alignment_times(
                exclude_clip_ids=moving,
                # The dragged keys' origin frames alias into the top-level
                # segment bar's edges and sibling sub-row keys — without
                # this the drag magnets to where it started.
                exclude_times=[origin for _, origin in self._drag_peers],
            )
        lead_origin = next((o for p, o in self._drag_peers if p is self), self._time)
        hit = (
            sq.nearest_alignment(lead_origin + snapped_delta, self._align_times)
            if self._align_times
            else None
        )
        if hit is not None and sq.snap_to_keys:
            snapped_delta = hit - lead_origin
        self._align_hit = hit is not None
        sq.set_snap_guides([hit] if hit is not None else [])

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

        self._update_drag_tooltip(event.scenePos())
        event.accept()

    def _is_drag_active(self) -> bool:
        return self._dragging

    def _drag_sequencer(self):
        return self._parent_clip._timeline.parent_sequencer

    def _restore_drag_state(self) -> None:
        # Mirror the move-path order: capture the EXPANDED bounds and
        # call prepareGeometryChange BEFORE repositioning keys, so the
        # region where dragged-out keys/curves were painted is
        # invalidated too (repositioning first shrinks the rect and
        # leaves ghost pixels outside it).
        affected = {}
        for peer, _ in self._drag_peers:
            pid = id(peer._parent_clip)
            if pid not in affected:
                affected[pid] = peer._parent_clip
        expanded = {}
        for pid, clip in affected.items():
            scene = clip.scene()
            if scene:
                expanded[pid] = clip.mapToScene(clip.boundingRect()).boundingRect()
            clip.prepareGeometryChange()
        for peer, origin_time in self._drag_peers:
            peer._time = origin_time
            peer._reposition()
        for pid, clip in affected.items():
            clip._keys_dragging = False
            clip._sync_tangent_handles()
            scene = clip.scene()
            if scene:
                rect = clip.mapToScene(clip.boundingRect()).boundingRect()
                if pid in expanded:
                    rect = rect.united(expanded[pid])
                scene.invalidate(rect)
            else:
                clip.update()
        self._dragging = False
        self._drag_peers = []
        self._align_hit = False
        self._align_times = None
        self._parent_clip._timeline.parent_sequencer.clear_snap_guides()

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
                    clip._sync_tangent_handles()
                    affected.add(pid)

            # Group moved keys by parent clip so each clip gets its
            # own signal with only its own key changes.
            by_clip: dict = {}  # clip_id -> [(old_t, new_t), ...]
            for peer, origin_time in self._drag_peers:
                if abs(peer._time - origin_time) > 1e-6:
                    cid = peer._parent_clip._data.clip_id
                    by_clip.setdefault(cid, []).append((origin_time, peer._time))
            self._drag_peers = []

            self._hide_drag_tooltip()

            sq = self._parent_clip._timeline.parent_sequencer
            sq.clear_snap_guides()
            self._align_hit = False
            self._align_times = None

            if by_clip:
                # ONE gesture must reach the consumer as ONE payload: a
                # per-clip emit made each clip its own undo step, so a drag
                # over three attribute rows took three Ctrl+Z to reverse.
                if len(by_clip) > 1:
                    sq.keys_batch_moved.emit(list(by_clip.items()))
                else:
                    clip_id, changes = next(iter(by_clip.items()))
                    sq.keys_moved.emit(clip_id, changes)

            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # -- context menu -------------------------------------------------------

    def contextMenuEvent(self, event):
        """Right-click a key: the key menu, for the selected keys (this one
        included).

        A key outside the selection becomes the selection first -- the gesture
        every editor teaches -- so the menu never acts on keys the user cannot
        see highlighted.  The menu itself is the selection's, built by
        :meth:`SequencerWidget.show_key_menu` -- the same menu a right-click
        that lands beside a dot opens.
        """
        clip = self._parent_clip
        if not clip.keys_editable:
            event.ignore()
            return
        sq = clip._timeline.parent_sequencer
        if not self.isSelected():
            scene = self.scene()
            if scene is not None:
                scene.clearSelection()
            self.setSelected(True)
        if sq.show_key_menu(MenuUtils._menu_exec_pos(event)):
            event.accept()
        else:
            event.ignore()

    # -- drag tooltip -------------------------------------------------------

    def _drag_tooltip_color(self) -> str:
        """Readout colour — the guide colour while the drag is aligned."""
        sq = self._parent_clip._timeline.parent_sequencer
        if self._align_hit and sq.snap_guides_enabled:
            return sq.SNAP_GUIDE_COLOR
        return self._parent_clip._resolve_color().lighter(160).name()

    def _show_drag_tooltip(self, scene_pos):
        self._drag_tooltip.show(
            self.scene(),
            scene_pos,
            label=FrameTooltip.format_frame(self._time),
            color=self._drag_tooltip_color(),
        )

    def _update_drag_tooltip(self, scene_pos):
        self._drag_tooltip.update(
            scene_pos,
            label=FrameTooltip.format_frame(self._time),
            color=self._drag_tooltip_color(),
        )

    def _hide_drag_tooltip(self):
        self._drag_tooltip.hide()

    # -- positioning --------------------------------------------------------

    def _reposition(self):
        """Update scene position from current time/value using the parent
        clip's coordinate mapping (:meth:`_clip_point`)."""
        self.setPos(self._clip_point(self._time, self._value))


class TangentHandleItem(QtWidgets.QGraphicsEllipseItem):
    """The grab point of a selected key's IN or OUT tangent handle.

    A child of the key's clip, like the key dot, positioned on the control
    point the clip's ``curve_preview`` carries for that side (see
    :meth:`KeyframeItem._tangent_slots`).  Dragging it rewrites that control
    point IN PLACE, so the clip's curve and the handle line follow the mouse
    live, and the release reports the gesture once as
    :attr:`SequencerWidget.key_tangent_dragged` -- the handle vector in
    curve units (frames, value), which is what a host turns into a tangent
    angle and weight (Maya) or a handle position (Blender).  The OUT handle
    stays after its key and the IN handle before it: a handle dragged past
    its key is a tangent no curve can carry.

    Never selectable, so a marquee ignores it; a right-click on it is the
    key's own menu.
    """

    _RADIUS = 2.5

    def __init__(self, key: KeyframeItem, side: str, seg_index: int, cp_key: str):
        r = self._RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r, key._parent_clip)
        self._key = key
        self._side = side
        self._seg_index = seg_index
        self._cp_key = cp_key
        self._dragging = False
        self._origin: Optional[tuple] = None
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton | QtCore.Qt.RightButton)
        self.setZValue(key.zValue() + 1)
        self.setPen(QtCore.Qt.NoPen)
        self._reposition()

    # -- identity -----------------------------------------------------------

    @property
    def side(self) -> str:
        return self._side

    @property
    def key(self) -> KeyframeItem:
        return self._key

    def slot(self) -> tuple:
        """``(key, side, segment index, control-point key)`` -- what this
        handle stands for, compared by the clip on each resync."""
        return (self._key, self._side, self._seg_index, self._cp_key)

    def control_point(self) -> Optional[tuple]:
        segments = self._key._segments()
        if not 0 <= self._seg_index < len(segments):
            return None
        cp = segments[self._seg_index].get(self._cp_key)
        return None if cp is None else (float(cp[0]), float(cp[1]))

    def _set_control_point(self, t: float, v: float) -> None:
        self._key._segments()[self._seg_index][self._cp_key] = (t, v)

    def _reposition(self) -> None:
        cp = self.control_point()
        self.setVisible(cp is not None and self._key.isVisible())
        if cp is not None:
            self.setPos(self._key._clip_point(*cp))

    # -- painting -----------------------------------------------------------

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        color = QtGui.QColor(self._key._parent_clip._data.color or "#CCCCCC").lighter(
            150
        )
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(self.rect())

    def shape(self) -> QtGui.QPainterPath:
        p = QtGui.QPainterPath()
        hit_r = self._RADIUS + 2
        p.addEllipse(QtCore.QRectF(-hit_r, -hit_r, 2 * hit_r, 2 * hit_r))
        return p

    # -- hover --------------------------------------------------------------

    def hoverEnterEvent(self, event):
        self.setCursor(QtCore.Qt.SizeAllCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    # -- drag ---------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        self._origin = self.control_point()
        self._dragging = self._origin is not None
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        clip = self._key._parent_clip
        t, v = self._key._curve_coords(clip.mapFromScene(event.scenePos()))
        # The handle never crosses its key: the tangent it stands for has
        # a direction, and a zero or reversed time step is not one.
        eps = 1e-3
        if self._side == "out":
            t = max(t, self._key._time + eps)
        else:
            t = min(t, self._key._time - eps)
        self._set_control_point(t, v)
        self.setPos(self._key._clip_point(t, v))
        clip.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton or not self._dragging:
            event.ignore()
            return
        self._dragging = False
        cp, origin = self.control_point(), self._origin
        self._origin = None
        event.accept()
        if cp is None or origin is None:
            return
        if abs(cp[0] - origin[0]) < 1e-9 and abs(cp[1] - origin[1]) < 1e-9:
            return
        sq = self._key._parent_clip._timeline.parent_sequencer
        sq.key_tangent_dragged.emit(
            self._key._parent_clip._data.clip_id,
            self._key._time,
            self._side,
            cp[0] - self._key._time,
            cp[1] - self._key._value,
        )

    def contextMenuEvent(self, event):
        # The handle belongs to its key; so does the menu.
        self._key.contextMenuEvent(event)
