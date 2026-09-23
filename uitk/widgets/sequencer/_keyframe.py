# !/usr/bin/python
# coding=utf-8
"""The interactive items of an expanded attribute sub-row.

``KeyframeItem`` is the key dot itself, ``TangentHandleItem`` the grab point
of one of its tangents, and ``KeyScaleBoxItem`` the box Shift raises around a
key selection to retime it as a whole.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

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
        # Set for the length of a breaking tangent drag (see
        # ``TangentHandleItem.BREAK_MODIFIER``), so the handle lines go
        # dotted under the cursor instead of only after the host writes it.
        self._break_pending: bool = False

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

    def _preview(self) -> dict:
        """The parent clip's ``curve_preview``, or an empty dict.

        The one reader: the key dot, its handles and the clip's own curve
        all shape themselves from this mapping, and a second spelling of
        the lookup is a second place for them to disagree.
        """
        return self._parent_clip._data.data.get("curve_preview") or {}

    def _segments(self) -> list:
        return self._preview().get("segments") or []

    def weighted_handles(self) -> bool:
        """Whether a handle's LENGTH carries meaning on this curve.

        ``True`` (the default a preview without the key gets) means a handle
        is where the curve says it is, and moving one keeps its distance
        from the key -- Blender's handles, Maya's weighted tangents.  When
        the host reports ``False`` the curve stores an ANGLE only: the
        handle's time offset is fixed (a third of its span) and its value
        follows the slope, so a partner swung about the key keeps its TIME
        offset instead (:meth:`TangentHandleItem._swing_partner`).
        """
        return bool(self._preview().get("weighted", True))

    def is_broken(self, index: Optional[int] = None) -> bool:
        """True when this key's tangents are broken (IN and OUT independent).

        Read from the preview's optional ``broken`` list, one flag per key
        in ``keys`` order; a preview without it has no broken keys.  A
        broken key draws its handle lines dotted, as the Graph Editor does.
        True as well while a breaking tangent drag is carrying this key --
        the line goes dotted with the gesture, not a rebuild later.
        """
        if self._break_pending:
            return True
        flags = self._preview().get("broken") or ()
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
        preview = self._preview()
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
        preview = self._preview()
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
    :attr:`SequencerWidget.keys_tangent_dragged` -- one handle VECTOR per
    key in curve units (frames, value), which is what a host turns into a
    tangent angle and weight (Maya) or a handle position (Blender).  The OUT
    handle stays after its key and the IN handle before it: a handle dragged
    past its key is a tangent no curve can carry.

    An UNBROKEN key is one straight line through the dot, so the side the
    user is not holding swings with the side they are -- reversed, its own
    length kept -- live, under the cursor.  Without it every drag looked
    like it was breaking the tangent and only the release revealed that
    both sides had moved.  A broken key (dotted lines), or one this drag is
    breaking, keeps its other side exactly where it is: moving the sides
    independently is what broken MEANS.  The swing is a preview of what the
    host writes on release, not something reported on its own -- Maya swings
    a unified key's other side itself, Blender re-aims an aligned handle.

    A drag carries the whole key SELECTION: every other selected key's
    handle on the same side moves with the grabbed one, the way a key drag
    moves every selected dot.  The modifiers are the sequencer's own
    grammar, read on the tangent instead of the clip -- Ctrl means "only
    this one, nothing else moves", Shift "apply it across the selection",
    Alt "the other mode":

    * ``Ctrl``  -- ISOLATE: reshape only the grabbed key and leave the rest
      of the selection where it was;
    * ``Shift`` -- MATCH: give every selected key this EXACT vector (one
      angle, one weight) instead of the same nudge it started from;
    * ``Alt``   -- BREAK the tangent, so the dragged side no longer swings
      its partner.  The handle lines go dotted while it is held.

    They compose: ``Ctrl+Alt`` breaks just the grabbed key, ``Shift+Alt``
    puts the whole selection on one broken tangent.  ``Ctrl`` outranks
    ``Shift`` -- with one key in the gesture, "the same nudge" and "the same
    vector" are the same drag.  All three are read on every MOVE, so what
    the release commits is what the curve under the cursor already shows;
    a chord pressed after the last move, with nothing left to redraw, is
    not part of the gesture.

    Never selectable, so a marquee ignores it; a right-click on it is the
    key's own menu.
    """

    _RADIUS = 2.5

    #: The drag grammar, as class attributes so a host can re-point one
    #: without reaching into the event handlers.
    ISOLATE_MODIFIER = QtCore.Qt.ControlModifier
    MATCH_MODIFIER = QtCore.Qt.ShiftModifier
    BREAK_MODIFIER = QtCore.Qt.AltModifier

    #: How far, in frames, a handle is held off its own key.
    _MIN_SPAN = 1e-3

    def __init__(self, key: KeyframeItem, side: str, seg_index: int, cp_key: str):
        r = self._RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r, key._parent_clip)
        self._key = key
        self._side = side
        self._seg_index = seg_index
        self._cp_key = cp_key
        self._dragging = False
        self._drag_owner = None  # the handle whose drag is carrying this one
        self._origin: Optional[tuple] = None
        # The handles this drag carries, with the control point each
        # started from -- resolved on press (see ``_collect_peers``).
        self._peers: List[Tuple["TangentHandleItem", tuple]] = []
        # ``id(key) -> (opposite-side handle, the point it started from)``
        # for every key this drag moves -- the sides it has to keep in line.
        self._partners: Dict[int, Tuple["TangentHandleItem", tuple]] = {}
        self._mods = QtCore.Qt.NoModifier  # chord of the last move
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

    @property
    def drag_participant(self) -> bool:
        """True while this handle is being dragged, or carried by one that
        is.  The clip reads it before rebuilding its key items: a resync
        mid-gesture retires the very handles the drag is holding.

        Being carried is ASKED of the owner rather than remembered as a flag
        of its own.  A gesture whose own handle is retired under it -- a host
        rebuild landing mid-drag -- never reaches its release, and a flag
        would leave every peer marked for the rest of the session, with their
        clips refusing to rebuild ever again.
        """
        if self._dragging:
            return True
        owner = self._drag_owner
        return owner is not None and owner._dragging and owner.scene() is not None

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

    def _clamp_time(self, t: float, key_time: float) -> float:
        """*t* pushed back to this handle's own side of its key.

        The handle never crosses it: the tangent it stands for has a
        direction, and a zero or reversed time step is not one.
        """
        if self._side == "out":
            return max(t, key_time + self._MIN_SPAN)
        return min(t, key_time - self._MIN_SPAN)

    def _place(self, t: float, v: float) -> "ClipItem":
        """Write the control point and move the grab point onto it.

        Returns the clip that now has to repaint -- the handle LINE and the
        curve are painted by the clip, not by the grab point.
        """
        t = self._clamp_time(t, self._key._time)
        self._set_control_point(t, v)
        self.setPos(self._key._clip_point(t, v))
        return self._key._parent_clip

    def _collect_gesture(self) -> tuple:
        """``(peers, partners)`` -- every handle this drag moves, with the
        control point each starts from.

        *peers* are the same-side handles of the OTHER selected keys, in
        selection order; *partners* map a key id to its OPPOSITE-side
        handle, for the grabbed key and every peer, since an unbroken key's
        two sides are one line.

        Resolved once, on press, in ONE walk: the selection cannot change
        under a drag, and re-reading it on every move would cost a scene
        query per pixel on a long selection.  Read from the clips' own
        handle items rather than rebuilt from the preview, so a key with
        nothing on the dragged side -- a linear or stepped span, a clip
        that refuses key edits and grows no handles at all -- brings
        neither a peer nor a partner, which is right: a side that does not
        move has nothing to keep in line with.
        """
        scene = self.scene()
        if scene is None:
            return [], {}
        keys = [self._key]
        keys += [
            i
            for i in scene.selectedItems()
            if isinstance(i, KeyframeItem) and i is not self._key
        ]
        handles, seen = {}, set()
        for key in keys:
            clip = key._parent_clip
            if id(clip) in seen:
                continue
            seen.add(id(clip))
            for handle in clip._tangent_handle_items:
                handles[(id(handle._key), handle.side)] = handle
        other = "in" if self._side == "out" else "out"
        peers, partners = [], {}
        for key in keys:
            handle = self if key is self._key else handles.get((id(key), self._side))
            cp = None if handle is None else handle.control_point()
            if cp is None:
                continue
            if handle is not self:
                peers.append((handle, cp))
            partner = handles.get((id(key), other))
            partner_cp = None if partner is None else partner.control_point()
            if partner_cp is not None:
                partners[id(key)] = (partner, partner_cp)
        return peers, partners

    def _swing_partner(self, key: KeyframeItem, cp: tuple, started: tuple, dirty: dict):
        """Keep *key*'s other side in line with the one being dragged.

        The partner is reversed along the new tangent, keeping whichever of
        its measurements the curve actually stores
        (:meth:`KeyframeItem.weighted_handles`): its LENGTH on a weighted
        curve -- Blender re-aims an aligned handle exactly so, and Maya's
        unified key takes one angle for both sides while each keeps its
        weight -- or its TIME offset on an unweighted one, where the host
        will re-lay it a fixed third of its span out and only the slope is
        the drag's to set.  Guessing one rule for both put the partner where
        the rebuild would not, and the release snapped it.

        It goes back untouched when the key is broken (or this drag is
        breaking it), and when the dragged side has not actually left
        *started*, which is what Ctrl's restore needs: a key whose sides were
        never collinear to begin with must not drift every time the peers
        snap back.
        """
        entry = self._partners.get(id(key))
        if entry is None:
            return
        partner, cp0 = entry
        if partner.scene() is None:
            return
        moved = abs(cp[0] - started[0]) > 1e-9 or abs(cp[1] - started[1]) > 1e-9
        if not moved or key.is_broken():
            clip = partner._place(*cp0)
        else:
            dt, dv = cp[0] - key._time, cp[1] - key._value
            # Where the partner starts, as an offset from its key: signed,
            # so it already names the side the partner belongs on.
            back_t, back_v = cp0[0] - key._time, cp0[1] - key._value
            if key.weighted_handles():
                reach = math.hypot(dt, dv)
                length = math.hypot(back_t, back_v)
                if reach < 1e-12 or length < 1e-12:
                    return
                off_t, off_v = -dt / reach * length, -dv / reach * length
            elif abs(dt) < 1e-12:
                return
            else:
                off_t, off_v = back_t, back_t * (dv / dt)
            clip = partner._place(key._time + off_t, key._value + off_v)
        dirty[id(clip)] = clip

    def _sync_break_pending(self, on: bool, isolate: bool) -> None:
        """Flag the keys this drag is breaking, so their handle lines go
        dotted under the cursor (:meth:`KeyframeItem.is_broken`) instead of
        only once the host has written the tangent and rebuilt."""
        self._key._break_pending = on
        for peer, _cp in self._peers:
            peer._key._break_pending = on and not isolate

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        self._origin = self.control_point()
        self._dragging = self._origin is not None
        self._mods = event.modifiers()
        if self._dragging:
            sq = self._key._parent_clip._timeline.parent_sequencer
            # Mirrors the key dot: a gesture must never inherit the chord
            # the LAST one banked.
            sq.record_press_modifiers(event.modifiers())
            # The Shift scale box answers the same Shift this drag reads,
            # so it has no business rising over a tangent gesture.
            sq._tangent_drag_active = True
            sq.clear_key_scale_box()
            self._peers, self._partners = self._collect_gesture()
            for peer, _cp in self._peers:
                peer._drag_owner = self
            for partner, _cp in self._partners.values():
                partner._drag_owner = self
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        self._mods = event.modifiers()
        isolate = bool(self._mods & self.ISOLATE_MODIFIER)
        match = bool(self._mods & self.MATCH_MODIFIER) and not isolate
        # Flagged BEFORE anything moves: each swing asks its key whether it
        # is broken, and a breaking drag is what makes it so.
        self._sync_break_pending(bool(self._mods & self.BREAK_MODIFIER), isolate)
        key = self._key
        clip = key._parent_clip
        t, v = key._curve_coords(clip.mapFromScene(event.scenePos()))
        self._place(t, v)
        dirty = {id(clip): clip}
        cp = self.control_point()
        self._swing_partner(key, cp, self._origin, dirty)
        vector = (cp[0] - key._time, cp[1] - key._value)
        step = (cp[0] - self._origin[0], cp[1] - self._origin[1])
        for peer, cp0 in self._peers:
            if peer.scene() is None:
                continue  # retired under the drag by a host rebuild
            peer_key = peer._key
            if isolate:
                # Ctrl is live, not a release-time gate: the peers go back
                # to where they were, so the curve shows what will commit.
                target = cp0
            elif match:
                target = (peer_key._time + vector[0], peer_key._value + vector[1])
            else:
                target = (cp0[0] + step[0], cp0[1] + step[1])
            peer_clip = peer._place(*target)
            dirty[id(peer_clip)] = peer_clip
            self._swing_partner(peer_key, peer.control_point(), cp0, dirty)
        for item in dirty.values():
            item.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton or not self._dragging:
            event.ignore()
            return
        self._dragging = False
        self._sync_break_pending(False, False)
        peers, self._peers = self._peers, []
        partners, self._partners = self._partners, {}
        for handle, _cp in list(peers) + list(partners.values()):
            handle._drag_owner = None
        origin, self._origin = self._origin, None
        mods, self._mods = self._mods, QtCore.Qt.NoModifier
        sq = self._key._parent_clip._timeline.parent_sequencer
        sq._tangent_drag_active = False
        # Shift means the scale box again the moment the gesture ends.
        sq.refresh_key_scale_box()
        event.accept()
        if origin is None:
            return
        broken = bool(mods & self.BREAK_MODIFIER)
        isolate = bool(mods & self.ISOLATE_MODIFIER)
        groups: dict = {}  # clip_id -> [(time, dt, dv), ...]
        for handle, started in [(self, origin)] + ([] if isolate else peers):
            if handle.scene() is None:
                continue
            cp = handle.control_point()
            if cp is None:
                continue
            if abs(cp[0] - started[0]) < 1e-9 and abs(cp[1] - started[1]) < 1e-9:
                continue  # never moved, or clamped back onto where it was
            key = handle._key
            groups.setdefault(key._parent_clip._data.clip_id, []).append(
                (key._time, cp[0] - key._time, cp[1] - key._value)
            )
        if not groups:
            return
        sq.keys_tangent_dragged.emit(list(groups.items()), self._side, broken)

    def contextMenuEvent(self, event):
        # The handle belongs to its key; so does the menu.
        self._key.contextMenuEvent(event)


class KeyScaleBoxItem(DraggableItemMixin, QtWidgets.QGraphicsRectItem):
    """The scale box Shift raises around a key selection.

    An outline bracketing every selected key, with a marker at each corner so
    the extent reads at a glance and one drag handle at the middle of each
    vertical edge.  Dragging a handle retimes the whole selection about the
    other edge -- the way the Graph Editor's scale manipulator does.  A key
    drag translates a selection rigidly; this is the gesture that changes its
    LENGTH, which no amount of dragging dots can do.

    Only the two middle handles are draggable.  The corners are markers, and
    the box has no vertical axis to drag: each sub-row maps values with its
    OWN ``val_min``/``val_max`` and the rows are different attributes in
    different units, so one box spanning several of them has no single
    vertical quantity to scale.  :meth:`shape` is therefore just the two
    grips, and a press anywhere else inside the box falls through to the key
    dots and the marquee underneath.

    Modifiers during the drag:

    * **Ctrl** -- snap the dragged edge to whole frames (the package-wide
      idiom, inherited from :meth:`DraggableItemMixin.snap_time`);
    * **Alt** -- pivot at the PLAYHEAD instead of the far edge, so the
      selection scales around where the user is parked.  Both edges of the
      box then move.

    It appears only while Shift is held (:meth:`SequencerWidget.
    refresh_key_scale_box`), so nothing is added to the timeline for a user
    who is not asking for it, and it is never selectable -- a marquee sweeps
    past it to the dots underneath.

    The release reports the gesture through the key-drag signals
    (``keys_moved`` / ``keys_batch_moved``), so a consumer that already
    commits a key drag as one undoable step commits a scale the same way,
    with no second code path.
    """

    #: Narrowest the selection may be scaled to, in frames.  A scale of 0 is
    #: reachable in one flick past the pivot, and it stacks every selected key
    #: on one frame -- which the consumer then merges, losing them with no
    #: gesture to undo it back.  The floor makes an overshoot a very short
    #: selection instead of a destroyed one.
    _MIN_SPAN = 1.0
    _GRIP_W = 5.0  # drawn width of a middle handle
    _GRIP_PAD = 5.0  # extra hit width either side of one
    _CORNER = 3.0  # half-size of a corner marker
    _MIN_GRIP_H = 8.0
    _MAX_GRIP_H = 24.0

    def __init__(self, sequencer):
        super().__init__()
        self._sq = sequencer
        self._lo = 0.0
        self._hi = 0.0
        self._top = 0.0
        self._bottom = 0.0
        self._dragging = False
        self._side = ""  # "left" / "right" while a drag is live
        self._pivot = 0.0
        self._origin_lo = 0.0
        self._origin_hi = 0.0
        self._min_scale = 0.0
        self._max_scale = float("inf")
        self._keys: List[Tuple["KeyframeItem", float]] = []
        self._drag_tooltip = FrameTooltip()
        self.setZValue(6)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
        self.setPen(QtCore.Qt.NoPen)
        self.setBrush(QtCore.Qt.NoBrush)

    # -- geometry -----------------------------------------------------------
    @property
    def lo(self) -> float:
        """Frame of the box's left edge."""
        return self._lo

    @property
    def hi(self) -> float:
        """Frame of the box's right edge."""
        return self._hi

    @property
    def side(self) -> str:
        """Which handle is being dragged, or ``""`` when none is."""
        return self._side

    def set_span(self, lo: float, hi: float, top: float, bottom: float) -> None:
        """Place the box around a selection spanning *lo*-*hi* over those rows."""
        self._lo, self._hi = float(lo), float(hi)
        self._top, self._bottom = float(top), float(bottom)
        self._resync()

    def _resync(self) -> None:
        # No prepareGeometryChange here: boundingRect is derived from rect(),
        # and setRect issues one itself.
        tl = self._sq._timeline
        x0, x1 = tl.time_to_x(self._lo), tl.time_to_x(self._hi)
        self.setRect(
            QtCore.QRectF(x0, self._top, max(x1 - x0, 0.0), self._bottom - self._top)
        )

    def _grip_rect(self, side: str) -> QtCore.QRectF:
        """The drawn bar of one middle handle, in scene coordinates."""
        r = self.rect()
        h = min(max(r.height() * 0.5, self._MIN_GRIP_H), self._MAX_GRIP_H)
        h = min(h, r.height())
        x = r.left() if side == "left" else r.right()
        return QtCore.QRectF(
            x - self._GRIP_W / 2.0, r.center().y() - h / 2.0, self._GRIP_W, h
        )

    def _hit_side(self, pos: QtCore.QPointF) -> str:
        """Which handle *pos* lands on, or ``""``."""
        for side in ("left", "right"):
            if (
                self._grip_rect(side)
                .adjusted(-self._GRIP_PAD, 0, self._GRIP_PAD, 0)
                .contains(pos)
            ):
                return side
        return ""

    def shape(self) -> QtGui.QPainterPath:
        """Only the two grips.  The box's interior belongs to what is under it."""
        path = QtGui.QPainterPath()
        for side in ("left", "right"):
            path.addRect(
                self._grip_rect(side).adjusted(-self._GRIP_PAD, 0, self._GRIP_PAD, 0)
            )
        return path

    def boundingRect(self) -> QtCore.QRectF:
        pad = self._GRIP_PAD + self._GRIP_W
        return self.rect().adjusted(-pad, -pad, pad, pad)

    # -- painting -----------------------------------------------------------
    def paint(self, painter: QtGui.QPainter, option, widget=None):
        r = self.rect()
        if r.width() <= 0 and r.height() <= 0:
            return
        color = QtGui.QColor(self._sq.SNAP_GUIDE_COLOR)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        outline = QtGui.QColor(color)
        outline.setAlpha(150)
        painter.setPen(QtGui.QPen(outline, 1.0))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(r)

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(color)
        c = self._CORNER
        for x in (r.left(), r.right()):
            for y in (r.top(), r.bottom()):
                painter.drawRect(QtCore.QRectF(x - c, y - c, 2 * c, 2 * c))
        for side in ("left", "right"):
            painter.drawRect(self._grip_rect(side))

    # -- hover --------------------------------------------------------------
    def hoverEnterEvent(self, event):
        # Only the grips are in :meth:`shape`, so a hover here is always over
        # one of them -- same enter/leave pair the key dot and the tangent
        # handle use.
        self.setCursor(QtCore.Qt.SizeHorCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    # -- drag ---------------------------------------------------------------
    def _playhead_time(self) -> float:
        return float(self._sq._timeline._scene.playhead.time)

    def mousePressEvent(self, event):
        side = self._hit_side(event.pos())
        keys = self._sq._scalable_keys()
        times = [k._time for k in keys]
        if not side or len(keys) < 2 or (max(times) - min(times)) < 1e-6:
            event.ignore()
            return
        self._side = side
        self._origin_lo, self._origin_hi = min(times), max(times)
        span = self._origin_hi - self._origin_lo
        self._min_scale = min(1.0, self._MIN_SPAN / span)
        # Alt pivots at the playhead, so BOTH edges travel; otherwise the far
        # edge is the fixed point and only the grabbed one moves.
        if event.modifiers() & QtCore.Qt.AltModifier:
            self._pivot = self._playhead_time()
        else:
            self._pivot = self._origin_hi if side == "left" else self._origin_lo
        if abs(self._origin_edge() - self._pivot) < 1e-9:
            # Nothing to measure a ratio against.  Clear the side too: a
            # refused press must leave no trace of a gesture that never began.
            self._side = ""
            event.ignore()
            return
        # Ceiling so the EARLIEST key cannot be pushed through frame 0.  Per-key
        # clamping would answer the same question by collapsing whatever
        # crossed onto frame 0 -- deforming the selection and stacking keys the
        # consumer then merges -- which is exactly what the clip-group scale
        # clamps its ratio to avoid (``ClipItem._arm_group_scale``).  A
        # selection already reaching before frame 0 gets no ceiling; it is
        # there, and measuring one from it would pin the scale at its floor.
        self._max_scale = float("inf")
        if 0.0 <= self._origin_lo < self._pivot:
            self._max_scale = max(
                self._min_scale, self._pivot / (self._pivot - self._origin_lo)
            )
        self._keys = [(k, k._time) for k in keys]
        self._dragging = True
        for clip in self._affected_clips():
            clip._keys_dragging = True
            clip._sync_tangent_handles()
        self._drag_tooltip.show(
            self.scene(),
            event.scenePos(),
            label=FrameTooltip.format_frame(self._origin_edge()),
            color=self._sq.SNAP_GUIDE_COLOR,
        )
        event.accept()

    def _origin_edge(self) -> float:
        return self._origin_lo if self._side == "left" else self._origin_hi

    def _affected_clips(self) -> list:
        seen: dict = {}
        for key, _origin in self._keys:
            seen.setdefault(id(key._parent_clip), key._parent_clip)
        return list(seen.values())

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        tl = self._sq._timeline
        new_edge = self.snap_time(tl.x_to_time(event.scenePos().x()), tl)
        denom = self._origin_edge() - self._pivot
        if abs(denom) < 1e-9:
            event.accept()
            return
        scale = min(
            max((new_edge - self._pivot) / denom, self._min_scale), self._max_scale
        )
        clips = self._affected_clips()
        for clip in clips:
            clip.prepareGeometryChange()
        for key, origin in self._keys:
            # No per-key floor: the RATIO is already clamped so the earliest
            # key cannot cross frame 0 (see the press).  Clamping here as well
            # would flatten a selection that legitimately reaches back before
            # 0 -- a shot padded at the head -- onto frame 0 instead.
            key._time = self._pivot + (origin - self._pivot) * scale
            key._reposition()
        self._lo = self._pivot + (self._origin_lo - self._pivot) * scale
        self._hi = self._pivot + (self._origin_hi - self._pivot) * scale
        self._resync()
        for clip in clips:
            scene = clip.scene()
            if scene:
                scene.invalidate(clip.mapToScene(clip.boundingRect()).boundingRect())
            else:
                clip.update()
        self._drag_tooltip.update(
            event.scenePos(),
            label=FrameTooltip.format_frame(
                self._lo if self._side == "left" else self._hi
            ),
        )
        event.accept()

    def mouseReleaseEvent(self, event):
        if not self._dragging:
            event.ignore()
            return
        self._dragging = False
        self._side = ""
        self._drag_tooltip.hide()
        for clip in self._affected_clips():
            clip.prepareGeometryChange()
            clip._keys_dragging = False
            clip._sync_tangent_handles()
        # Order the landings so a consumer committing them one at a time never
        # writes a key onto a frame another key has not left yet: a shrink
        # lands nearest the pivot first, a stretch farthest first (the rule
        # ``ClipItem._collision_free_order`` applies to a clip group, for the
        # same reason).
        moved = [
            (key, origin)
            for key, origin in self._keys
            if abs(key._time - origin) > 1e-6
        ]
        growing = any(
            abs(k._time - self._pivot) > abs(o - self._pivot) for k, o in moved
        )
        moved.sort(key=lambda pair: abs(pair[1] - self._pivot), reverse=growing)
        by_clip: dict = {}
        for key, origin in moved:
            cid = key._parent_clip._data.clip_id
            by_clip.setdefault(cid, []).append((origin, key._time))
        self._keys = []
        event.accept()
        if not by_clip:
            return
        sq = self._sq
        if len(by_clip) > 1:
            sq.keys_batch_moved.emit(list(by_clip.items()))
        else:
            clip_id, changes = next(iter(by_clip.items()))
            sq.keys_moved.emit(clip_id, changes)

    # -- cancellation -------------------------------------------------------
    def _is_drag_active(self) -> bool:
        return self._dragging

    def _drag_sequencer(self):
        """The mixin looks for a ``_timeline``; this item holds the widget."""
        return self._sq

    def _restore_drag_state(self) -> None:
        """Put every key back where the press found it.

        Reached by Escape (``SequencerWidget._cancel_active_drag``) and by the
        mixin's ``UngrabMouse`` handling -- a popup or a grab handoff takes the
        mouse without ever delivering a release, and the box would otherwise
        stay mid-drag, with ``refresh_key_scale_box`` refusing to touch one
        that is, for the rest of the session.
        """
        for key, origin in self._keys:
            key._time = origin
            key._reposition()
        for clip in self._affected_clips():
            clip._keys_dragging = False
            clip._sync_tangent_handles()
            clip.update()
        self._dragging = False
        self._side = ""
        self._keys = []
        self._lo, self._hi = self._origin_lo, self._origin_hi
        self._resync()
