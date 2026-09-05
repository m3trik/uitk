# !/usr/bin/python
# coding=utf-8
"""Timeline view, scene, and track-header widgets."""

from __future__ import annotations

from typing import Dict, List, TYPE_CHECKING

from qtpy import QtWidgets, QtGui, QtCore

if TYPE_CHECKING:
    from uitk.widgets.sequencer._sequencer import SequencerWidget

from uitk.widgets.sequencer._data import (
    _TRACK_HEIGHT,
    _TRACK_PADDING,
    _RULER_HEIGHT,
    _HEADER_HEIGHT,
    MenuUtils,
    CurveUtils,
    PatternRegistry,
)
from uitk.widgets.sequencer._clip import ClipItem
from uitk.widgets.sequencer._overlays import (
    _SnapGuideItem,
    _StaticRangeOverlay,
    _GapOverlayItem,
    RangeHighlightItem,
)
from uitk.widgets.sequencer._ruler import RulerItem
from uitk.widgets.sequencer._playhead import PlayheadItem
from uitk.managers.cursor_manager import CursorManager
from uitk.widgets.sequencer._markers import MarkerItem


# Marquee modifiers, as plain ints.  Qt6 hands back an enum from these while
# a stored modifier snapshot is an int, so the comparison needs the value --
# resolved once at import because the marquee re-reads them on EVERY
# mouse-move of a drag.
_ALT_MOD, _CTRL_MOD, _SHIFT_MOD = (
    int(getattr(m, "value", m))
    for m in (
        QtCore.Qt.AltModifier,
        QtCore.Qt.ControlModifier,
        QtCore.Qt.ShiftModifier,
    )
)

#: Held at press, these keep the existing selection instead of replacing it.
_MARQUEE_KEEP_MODS = _ALT_MOD | _CTRL_MOD | _SHIFT_MOD


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
    track_delete_requested = QtCore.Signal(list)  # [track_name, ...] to delete
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
        self._colors: List = []  # parallel: bg hex or None
        self._text_colors: List = []  # parallel: fg hex or None
        self._selected: List[int] = []  # indices of selected labels
        self._hidden_track_names: List[str] = []  # set by SequencerWidget
        self._sub_labels: Dict[int, List[QtWidgets.QLabel]] = {}  # idx → sub-row labels
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, _HEADER_HEIGHT, 0, 0)
        self._layout.setSpacing(_TRACK_PADDING)
        self._layout.addStretch()

    def set_top_margin(self, margin: int) -> None:
        m = self._layout.contentsMargins()
        self._layout.setContentsMargins(m.left(), margin, m.right(), m.bottom())

    def add_track_label(
        self,
        name: str,
        icon=None,
        dimmed: bool = False,
        italic: bool = False,
        color: str = None,
        text_color: str = None,
    ):
        if color and not dimmed:
            tc = text_color or "#CCCCCC"
            base_style = (
                f"padding-left:6px; color:{tc}; background:{color}; border-radius:3px;"
            )
        elif dimmed:
            base_style = self._STYLE_DIMMED
        else:
            base_style = self._STYLE_NORMAL
        if italic:
            base_style += " font-style:italic;"

        # Build the display widget (plain label, or icon+text container),
        # then run ONE shared wiring/bookkeeping tail — the two paths
        # previously duplicated the context-menu/event-filter/layout/
        # parallel-list block, and the icon branch built-and-abandoned a
        # plain QLabel on every call.
        if icon is not None and not icon.isNull():
            px = icon.pixmap(16, 16)
            if px.width() > 16 or px.height() > 16:
                px = px.scaled(
                    16, 16, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
                )
            widget = QtWidgets.QWidget()
            widget.setFixedHeight(_TRACK_HEIGHT)
            widget.setStyleSheet(base_style)
            h = QtWidgets.QHBoxLayout(widget)
            h.setContentsMargins(4, 0, 2, 0)
            h.setSpacing(4)
            ico_lbl = QtWidgets.QLabel()
            ico_lbl.setPixmap(px)
            ico_lbl.setFixedSize(22, _TRACK_HEIGHT)
            ico_lbl.setAlignment(QtCore.Qt.AlignCenter)
            ico_lbl.setStyleSheet("background:transparent; border:none; padding:0;")
            txt_color = (
                text_color
                if (text_color and not dimmed)
                else ("#777777" if dimmed else "#CCCCCC")
            )
            if italic and not text_color:
                txt_color = "#999977" if not dimmed else "#777766"
            txt_lbl = _ElidingLabel(name)
            txt_lbl.setStyleSheet(
                f"padding:0; color:{txt_color}; background:transparent; border:none;"
                + (" font-style:italic;" if italic else "")
            )
            h.addWidget(ico_lbl)
            h.addWidget(txt_lbl, 1)  # stretch so text fills available space
        else:
            widget = QtWidgets.QLabel(name)
            widget.setFixedHeight(_TRACK_HEIGHT)
            widget.setStyleSheet(base_style)

        widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(
            lambda pos, w=widget: self._show_label_menu(w, pos)
        )
        widget.installEventFilter(self)
        idx = self._layout.count() - 1  # before the stretch
        self._layout.insertWidget(idx, widget)
        self._labels.append(widget)
        self._names.append(name)
        self._dimmed.append(dimmed)
        self._colors.append(color)
        self._text_colors.append(text_color)

    # -- sub-row expansion -------------------------------------------------

    @staticmethod
    def _label_text_widget(lbl) -> QtWidgets.QLabel:
        if isinstance(lbl, QtWidgets.QLabel):
            return lbl
        for child in lbl.findChildren(QtWidgets.QLabel):
            if child.pixmap() is None or child.pixmap().isNull():
                return child
        return lbl

    def set_track_expanded(self, track_idx: int, sub_names: List[str], sub_height: int):
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
            btn = event.button()
            idx = self._labels.index(obj)

            if btn == QtCore.Qt.RightButton:
                # Preserve multi-selection on right-click (matching
                # standard OS behaviour):  only switch when the
                # right-clicked track is not already selected.
                if idx not in self._selected:
                    self._selected = [idx]
                    self._refresh_styles()
                    self.track_selected.emit(self.selected_names())
                return False  # let Qt deliver the ContextMenu event

            if btn == QtCore.Qt.LeftButton:
                mods = event.modifiers()
                ctrl = mods & QtCore.Qt.ControlModifier
                shift = mods & QtCore.Qt.ShiftModifier
                if shift and self._selected:
                    anchor = self._selected[-1]
                    lo, hi = sorted((anchor, idx))
                    self._selected = list(range(lo, hi + 1))
                elif ctrl:
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
        return [self._names[i] for i in self._selected if i < len(self._names)]

    def _refresh_styles(self):
        for i, lbl in enumerate(self._labels):
            if i in self._selected:
                style = self._STYLE_SELECTED
            elif i < len(self._dimmed) and self._dimmed[i]:
                style = self._STYLE_DIMMED
            elif i < len(self._colors) and self._colors[i]:
                tc = (
                    self._text_colors[i]
                    if i < len(self._text_colors) and self._text_colors[i]
                    else "#CCCCCC"
                )
                style = f"padding-left:6px; color:{tc}; background:{self._colors[i]}; border-radius:3px;"
            else:
                style = self._STYLE_NORMAL
            lbl.setStyleSheet(style)

    # -- context menu ------------------------------------------------------

    def _show_label_menu(self, widget, pos):
        # Selection is already adjusted by eventFilter (right-click path).
        names = self.selected_names()
        count = len(names)
        menu = MenuUtils._styled_menu(self)
        hide_label = f"Hide {count} Tracks" if count > 1 else "Hide Track"
        menu.addAction(hide_label, lambda: self.track_hide_requested.emit(names))
        del_label = f"Delete {count} Tracks" if count > 1 else "Delete Track"
        menu.addAction(del_label, lambda: self.track_delete_requested.emit(names))

        # Let consumers add custom actions
        self.track_menu_requested.emit(menu, names)

        # "Show Hidden" submenu
        hidden = self._hidden_track_names
        if hidden:
            sub = menu.addMenu(f"Show Hidden ({len(hidden)})")
            for name in sorted(hidden):
                sub.addAction(name, lambda n=name: self.track_show_requested.emit(n))

        menu.exec_(widget.mapToGlobal(pos))

    def clear_tracks(self):
        for idx in list(self._sub_labels):
            self.set_track_collapsed(idx)
        for lbl in self._labels:
            lbl.removeEventFilter(self)
            self._layout.removeWidget(lbl)
            lbl.deleteLater()
        self._labels.clear()
        self._names.clear()
        self._dimmed.clear()
        self._colors.clear()
        self._text_colors.clear()
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
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.SmartViewportUpdate)
        self.setStyleSheet("background:#1E1E1E; border:none;")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._pan_active = False
        self._pan_start = QtCore.QPoint()
        self._ruler_drag = False
        #: The range highlight, while one of its bounds is being dragged
        #: from the ruler's shot lane (the item is not the mouse grabber
        #: there, so the view forwards the drag to it).
        self._range_edge_drag = None
        self._shortcut_sequences: List[QtGui.QKeySequence] = []
        # Custom marquee state
        self._marquee_active = False
        self._marquee_anchor = QtCore.QPoint()  # viewport coords
        self._marquee_current = QtCore.QPoint()
        self._marquee_pre_selection: set = set()  # item ids before drag
        self._marquee_modifier = 0  # modifier held at press time
        self._space_held = False
        self._space_last_pos = QtCore.QPoint()
        # Now that the scene/view wiring is complete, sync deferred items
        self._scene.playhead.sync()
        # Keep ruler pinned to the viewport top during vertical scroll
        self.verticalScrollBar().valueChanged.connect(self._sync_ruler_pos)

    # -- event override: consume shortcut keys so they don't leak to host --
    def event(self, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.ShortcutOverride:
            if self.parent_sequencer._match_shortcut(event) is not None:
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        # Spacebar during marquee: start repositioning the selection area
        if event.key() == QtCore.Qt.Key_Space and self._marquee_active:
            self._space_held = True
            self._space_last_pos = self._marquee_current
            event.accept()
            return

        match = self.parent_sequencer._match_shortcut(event)
        if match is not None:
            _seq, entry = match
            if entry and entry.get("action"):
                entry["action"]()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == QtCore.Qt.Key_Space and self._marquee_active:
            self._space_held = False
            event.accept()
            return
        super().keyReleaseEvent(event)

    def enterEvent(self, event):
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
        # Overlay boundingRects depend on viewport height — refresh so
        # the scene index tracks the new geometry, or clicks/repaints in
        # a newly exposed strip miss the gap/range overlays until the
        # next zoom or clip edit.
        self._refresh_all()

    # -- zoom ---------------------------------------------------------------
    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        old_ppu = self._pixels_per_unit

        view_x = event.position().x() if hasattr(event, "position") else event.pos().x()
        scene_x_before = self.mapToScene(int(view_x), 0).x()
        time_under_cursor = scene_x_before / old_ppu if old_ppu else 0.0

        self._pixels_per_unit = max(0.01, min(100.0, old_ppu * factor))
        self._refresh_all()

        scene_x_after = time_under_cursor * self._pixels_per_unit
        self.horizontalScrollBar().setValue(int(scene_x_after - view_x))
        event.accept()

    # -- shot-bound handles on the ruler ------------------------------------

    def _sync_shot_bound_cursor(self, viewport_pos) -> bool:
        """Show the resize cursor over a shot bound on the shot lane.

        The affordance the item's own hover gives below the header; up here
        the ruler item is topmost, so the cursor is the view's to set.
        """
        zone = self._shot_band_zone(viewport_pos)
        if zone in ("left", "right"):
            self.viewport().setCursor(QtCore.Qt.SplitHCursor)
        elif zone == "move":
            self.viewport().setCursor(QtCore.Qt.OpenHandCursor)
        elif self.viewport().cursor().shape() in (
            QtCore.Qt.SplitHCursor,
            QtCore.Qt.OpenHandCursor,
        ):
            self.viewport().unsetCursor()
        return bool(zone)

    def _in_shot_lane(self, viewport_y: float) -> bool:
        """True for the strip below the ruler where shot blocks are drawn.

        Asks :meth:`_hit_zone` rather than re-deriving the band: the cursor
        sync runs off this on every move while the press routes off the zone,
        and two spellings of the same span disagree at its edge -- a resize
        cursor over a pixel that presses as "tracks".
        """
        return self._hit_zone(viewport_y) == "shot_lane"

    def _shot_bound_handle(self, viewport_pos, scene_x: float):
        """The range highlight, if *viewport_pos* is on one of its grabs.

        Returns the item with its drag already begun, or ``None`` -- in
        which case the ruler keeps its scrub.
        """
        zone = self._shot_band_zone(viewport_pos)
        if not zone:
            return None
        sq = self.parent_sequencer
        sq.shift_held_at_press = bool(
            QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ShiftModifier
        )
        sq._range_highlight.begin_edge_drag(zone, scene_x)
        return sq._range_highlight

    def _shot_band_zone(self, viewport_pos) -> str:
        """Which of the highlight's grabs *viewport_pos* is over, or ``""``.

        The one answer both the cursor and the press ask for; asking twice
        let them disagree, which is a wrong cursor sitting over a live
        handle.  The band offers all three: the two bounds, and the body --
        the ONE place the whole shot can be dragged, since the item's own
        body passes presses through so the marquee keeps working inside the
        shot (see ``RangeHighlightItem.mousePressEvent``).
        """
        hl = self.parent_sequencer._range_highlight
        if hl is None or not hl.isVisible():
            return ""
        if not self._in_shot_lane(viewport_pos.y()):
            return ""
        return hl.zone_at(self.mapToScene(viewport_pos).x())

    # -- zone detection -----------------------------------------------------

    def _hit_zone(self, viewport_y: float) -> str:
        if viewport_y < _RULER_HEIGHT:
            return "ruler"
        if viewport_y < _HEADER_HEIGHT:
            return "shot_lane"
        return "tracks"

    # -- marquee helpers ----------------------------------------------------

    def _restore_selection(self, ids: set) -> None:
        """Re-select exactly the items whose ``id`` is in *ids*.

        Undoes the clear that forwarding an unaccepted press to the scene
        performs, so a modifier drag starts from the selection the user
        actually had.  Kept id-based to match the marquee's own snapshot --
        the items themselves are not hashable-stable across a rebuild.

        Batched like :meth:`_sync_marquee_selection`, and for the same
        reason: ``setSelected`` emits ``selectionChanged`` per item, and the
        consumers do real work (per-curve host-app selection) on each one.
        """
        changed = False
        self._scene.blockSignals(True)
        try:
            for item in self._scene.items():
                if id(item) in ids and not item.isSelected():
                    item.setSelected(True)
                    changed = True
        finally:
            self._scene.blockSignals(False)
        if changed:
            self._scene.selectionChanged.emit()

    def _marquee_rect(self) -> QtCore.QRect:
        """Return the current marquee rectangle in viewport coords."""
        return QtCore.QRect(self._marquee_anchor, self._marquee_current).normalized()

    def _items_in_marquee(self) -> set:
        """Return the set of selectable items inside the current marquee."""
        rect = self._marquee_rect()
        scene_rect = QtCore.QRectF(
            self.mapToScene(rect.topLeft()),
            self.mapToScene(rect.bottomRight()),
        )
        items = set()
        for item in self._scene.items(scene_rect, QtCore.Qt.IntersectsItemShape):
            if item.flags() & QtWidgets.QGraphicsItem.ItemIsSelectable:
                items.add(item)
        return items

    def _sync_marquee_selection(self):
        """Update scene selection to reflect the current marquee state."""
        in_band = self._items_in_marquee()
        mods = self._marquee_modifier
        pre = self._marquee_pre_selection

        # One predicate, then one loop.  The three modes differ only in how
        # they combine "was selected before the drag" with "is in the band",
        # so they are three expressions, not three passes over the scene.
        if mods & (_ALT_MOD | _CTRL_MOD):
            # Alt (or Ctrl) REMOVES: keep the pre-selection, minus the band.
            def should(item):
                return id(item) in pre and item not in in_band

        elif mods & _SHIFT_MOD:
            # Shift ADDS: the pre-selection plus the band -- the whole point
            # of holding it, so it never narrows what was already picked.
            def should(item):
                return id(item) in pre or item in in_band

        else:
            # No modifier: exact replacement.
            def should(item):
                return item in in_band

        # Block selectionChanged until we're done batching
        changed = False
        self._scene.blockSignals(True)
        try:
            for item in self._scene.items():
                if not (item.flags() & QtWidgets.QGraphicsItem.ItemIsSelectable):
                    continue
                want = should(item)
                if item.isSelected() != want:
                    item.setSelected(want)
                    changed = True
        finally:
            self._scene.blockSignals(False)
        # Emit once, and only when something actually flipped — this
        # runs on EVERY marquee mouse-move, and consumers do real work
        # (e.g. per-curve host-app selection) on each emission.
        if changed:
            self._scene.selectionChanged.emit()

    def _finish_marquee(self):
        """Clean up marquee state and trigger a final viewport repaint."""
        self._marquee_active = False
        self._space_held = False
        self.viewport().update()

    # -- clicking / dragging ------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self._pan_active = True
            self._pan_start = event.pos()
            CursorManager.push(self, QtCore.Qt.SizeAllCursor)
            event.accept()
            return

        # Ctrl+Shift+Click: request shot switch at clicked time
        mods = event.modifiers()
        if (
            event.button() == QtCore.Qt.LeftButton
            and mods & QtCore.Qt.ControlModifier
            and mods & QtCore.Qt.ShiftModifier
        ):
            scene_pos = self.mapToScene(event.pos())
            t = self.x_to_time(scene_pos.x())
            self.parent_sequencer.shot_switch_requested.emit(t)
            event.accept()
            return

        zone = self._hit_zone(event.pos().y())
        if event.button() == QtCore.Qt.LeftButton and zone in ("ruler", "shot_lane"):
            item = self.itemAt(event.pos())
            if isinstance(item, MarkerItem):
                super().mousePressEvent(event)
                return
            scene_pos = self.mapToScene(event.pos())
            # A shot bound is DRAWN on the shot lane, so it is grabbed
            # there too -- and only there; the ruler proper scrubs, every row
            # of it.  Driven directly rather than by extending the highlight's
            # hit area up here: a view-dependent boundingRect re-enters the
            # scene index on scroll and dies natively.
            hl = self._shot_bound_handle(event.pos(), scene_pos.x())
            if hl is not None:
                self._range_edge_drag = hl
                event.accept()
                return
            self._ruler_drag = True
            self.parent_sequencer._move_playhead(round(self.x_to_time(scene_pos.x())))
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton:
            # Check if click landed on a selectable item
            item = self.itemAt(event.pos())
            if item is not None and (
                item.flags() & QtWidgets.QGraphicsItem.ItemIsSelectable
            ):
                # Direct item click — let Qt handle it (drag, selection toggle)
                super().mousePressEvent(event)
            else:
                # Snapshot the selection BEFORE anything is forwarded to Qt.
                # Forwarding a press the scene does not accept clears the
                # selection -- except under Ctrl, which is Qt's own extend
                # modifier -- so a snapshot taken afterwards came back empty
                # and left an Alt-marquee with nothing to subtract from.
                pre_selection = {id(it) for it in self._scene.selectedItems()}
                mods_int = int(getattr(mods, "value", mods))
                # Forward to scene so non-selectable interactive overlays
                # (gap, range-highlight) can accept edge drags.
                if item is not None:
                    super().mousePressEvent(event)
                    if self._scene.mouseGrabberItem() is not None:
                        return  # overlay started a drag — done
                # Empty space (or overlay rejected) — start custom marquee
                self._marquee_active = True
                self._marquee_anchor = event.pos()
                self._marquee_current = event.pos()
                self._marquee_modifier = mods_int
                self._space_held = False
                self._marquee_pre_selection = pre_selection
                # Alt/Ctrl/Shift all build on what is already selected, so
                # clearing here would leave the subtract nothing to subtract
                # from and the add nothing to add to.  A plain drag replaces,
                # so it clears -- and so does the forwarded press above, which
                # is why the restore below runs for the modifier cases.
                if not (mods_int & _MARQUEE_KEEP_MODS):
                    self._scene.clearSelection()
                elif pre_selection and not self._scene.selectedItems():
                    # Exactly what Qt's clear leaves behind -- it empties the
                    # selection outright, so "had one, has none" identifies
                    # it without walking the scene to compare sets.
                    self._restore_selection(pre_selection)
                event.accept()
        elif event.button() == QtCore.Qt.RightButton:
            # Preserve multi-selection on right-click: if the item under
            # the cursor is already selected, keep the whole selection so
            # the context menu can operate on all selected items.
            # If it's unselected, switch to it (standard OS behaviour).
            item = self.itemAt(event.pos())
            if isinstance(item, ClipItem):
                if not item.isSelected():
                    self._scene.clearSelection()
                    item.setSelected(True)
                event.accept()
            else:
                super().mousePressEvent(event)
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
            if hs.value() >= hs.maximum() - 10:
                self._update_scene_rect()
            event.accept()
        elif self._range_edge_drag is not None:
            self._range_edge_drag.update_edge_drag(self.mapToScene(event.pos()).x())
            event.accept()
        elif self._ruler_drag:
            scene_pos = self.mapToScene(event.pos())
            self.parent_sequencer._move_playhead(round(self.x_to_time(scene_pos.x())))
            event.accept()
        elif self._marquee_active:
            if self._space_held:
                # Reposition: shift the anchor by the mouse delta
                delta = event.pos() - self._space_last_pos
                self._marquee_anchor += delta
                self._marquee_current += delta
                self._space_last_pos = event.pos()
            else:
                self._marquee_current = event.pos()
            self._sync_marquee_selection()
            self.viewport().update()
            event.accept()
        else:
            self._sync_shot_bound_cursor(event.pos())
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self._pan_active = False
            CursorManager.pop(self)
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton and self._range_edge_drag:
            self._range_edge_drag.finish_edge_drag()
            self._range_edge_drag = None
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton and self._ruler_drag:
            self._ruler_drag = False
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton and self._marquee_active:
            self._finish_marquee()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _playhead_hit(self, viewport_pos) -> bool:
        """True when *viewport_pos* lands on the playhead's badge/line band.

        The badge is the grab target the eye sees, so its width is the hit
        width — a bare line would be a 1px target.
        """
        ph = self._scene.playhead
        x = self.mapFromScene(QtCore.QPointF(ph._badge_hit_x(), 0)).x()
        return abs(viewport_pos.x() - x) <= ph._badge_hit_half_width()

    def _prompt_playhead_time(self) -> None:
        """Ask for a frame and put the playhead on it.

        The scrub gesture answers "roughly there"; typing answers "exactly
        this frame", which is what the badge shows and what a double-click on
        it should let you set.
        """
        ph = self._scene.playhead
        value, ok = QtWidgets.QInputDialog.getDouble(
            self.parent_sequencer,
            "Go to Frame",
            "Frame:",
            float(ph.time),
            -1e6,
            1e6,
            2,
        )
        if not ok:
            return
        # ``_move_playhead`` is the widget's set-and-emit for a USER-initiated
        # move (the transport buttons and shot navigation all go through it),
        # and it emits the playhead's stored time rather than the raw input --
        # so a hand-rolled pair here would be a fourth copy and could report a
        # value the setter had normalised away.
        self.parent_sequencer._move_playhead(float(value))

    def mouseDoubleClickEvent(self, event):
        zone = self._hit_zone(event.pos().y())
        if event.button() == QtCore.Qt.LeftButton and zone in ("ruler", "shot_lane"):
            item = self.itemAt(event.pos())
            if isinstance(item, MarkerItem):
                super().mouseDoubleClickEvent(event)
                return
            if self._playhead_hit(event.pos()):
                # Double-clicking the playhead means "set the frame", not
                # "drop a marker on top of it".
                self._prompt_playhead_time()
                event.accept()
                return
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

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._marquee_active:
            rect = self._marquee_rect()
            if not rect.isNull():
                painter = QtGui.QPainter(self.viewport())
                color = QtGui.QColor(51, 153, 255, 40)
                painter.fillRect(rect, color)
                pen = QtGui.QPen(QtGui.QColor(51, 153, 255, 160), 1)
                pen.setStyle(QtCore.Qt.DashLine)
                painter.setPen(pen)
                painter.drawRect(rect.adjusted(0, 0, -1, -1))
                painter.end()

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if isinstance(item, (ClipItem, MarkerItem, _GapOverlayItem)):
            super().contextMenuEvent(event)
            return

        sq = self.parent_sequencer
        scene_pos = self.mapToScene(event.pos())
        t = self.x_to_time(scene_pos.x())
        interval = sq.snap_interval
        if interval > 0:
            t = round(t / interval) * interval

        zone = self._hit_zone(event.pos().y())
        # Refine: a click at a time some shot covers is the shot lane,
        # whatever the height — a shot owns its whole timeline COLUMN, not
        # just the band drawn in the lane, so "right-click the shot" has to
        # mean the same thing over the tracks as over the band.  Consumers
        # present a shot-specific menu there and fold the timeline's own
        # actions into it (see :meth:`add_default_context_actions`).
        # Hit-test with the UNSNAPPED click time: `t` was snapped above,
        # which near a block edge can land the test on the wrong side of the
        # boundary.  (Press/double-click keep plain "ruler" semantics: scrub
        # and add-marker.)
        raw_t = self.x_to_time(scene_pos.x())
        if self._scene.ruler.shot_block_at(raw_t) is not None:
            zone = "shot_lane"

        if sq.zone_menu_enabled:
            sq.zone_context_menu_requested.emit(zone, t, event.globalPos())
            event.accept()
            return

        self._show_default_context_menu(sq, t, event.globalPos())

    def add_default_context_actions(self, menu, t: float):
        """Append the timeline's own actions to *menu*; return their handler.

        The marker and display-toggle entries the widget owns.  Split out of
        :meth:`_show_default_context_menu` so a consumer building a richer
        menu -- a shot menu, say -- can FOLD these into it rather than
        leaving the user to hunt for a second menu somewhere else to reach
        them.

        Returns a callable: pass it whatever ``menu.exec_`` returned; it
        performs the action and answers whether it owned it, so the consumer
        can fall through to its own entries::

            handled = widget._timeline.add_default_context_actions(menu, t)
            chosen = menu.exec_(pos)
            if handled(chosen):
                return
        """
        sq = self.parent_sequencer
        if not menu.isEmpty():
            menu.addSeparator()
        add_action = menu.addAction(f"Add Marker at {int(t)}\u2026")
        menu.addSeparator()

        toggles = {}
        for key, label, current in (
            ("range_overlays", "Show Shot Ranges", sq.show_range_overlays),
            ("range_highlight", "Show Active Range", sq.show_range_highlight),
            ("gap_overlays", "Show Gap Overlays", sq.show_gap_overlays),
        ):
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(current)
            toggles[key] = act

        def _handle(chosen) -> bool:
            if chosen is None:
                return False
            if chosen is add_action:
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
                return True
            for key, act in toggles.items():
                if chosen is act:
                    setattr(sq, f"show_{key}", act.isChecked())
                    return True
            return False

        return _handle

    def _show_default_context_menu(self, sq, t, global_pos):
        menu = MenuUtils._styled_menu(self)
        handled = self.add_default_context_actions(menu, t)
        handled(menu.exec_(global_pos))

    # -- ruler pinning ------------------------------------------------------
    def _sync_ruler_pos(self):
        try:
            top = self.mapToScene(0, 0).y()
            self._scene.ruler.setPos(0, top)
            self._scene.ruler.update()
            # The playhead badge and marker head glyphs draw at
            # ruler-relative y — pin them to the viewport top too, or
            # vertical scrolling leaves them stranded at scene-top
            # behind the pinned ruler (and marker hit-shapes become
            # unreachable until scrolled back).
            self._scene.playhead.setPos(0, top)
            for item in self.parent_sequencer._marker_items.values():
                item.setPos(0, top)
        except RuntimeError:
            pass  # C++ object already deleted during teardown

    # -- internal refresh ---------------------------------------------------
    def _refresh_all(self):
        for item in self._scene.items():
            if isinstance(item, ClipItem):
                item._sync_geometry()
            elif isinstance(item, MarkerItem):
                item.sync()
            elif isinstance(item, RangeHighlightItem):
                item.sync()
            elif isinstance(
                item, (_StaticRangeOverlay, _GapOverlayItem, _SnapGuideItem)
            ):
                item.prepareGeometryChange()
                item.update()
        self._sync_ruler_pos()
        self._scene.playhead.sync()
        self._update_scene_rect()
        self.viewport().update()

    def content_time_bounds(self) -> tuple:
        """``(min_time, max_time)`` spanned by everything the scene draws.

        Every decoration counts, not just the clips: shot bands, range
        overlays and gaps are the things a shot edit moves, and a shot that
        no longer encloses any clip still has to be reachable.

        Frame 0 is not the floor.  Padding a shot's head or rippling one
        upstream legitimately puts content before it, and a view that
        started at the origin left that content unreachable.
        """
        sq = self.parent_sequencer
        lo = hi = None

        def _span(a, b):
            nonlocal lo, hi
            if b < a:
                # Consumer-supplied spans (shot blocks especially) are not
                # validated anywhere; an inverted one would pull the bounds
                # INWARD and hide the very content it describes.
                a, b = b, a
            lo = a if lo is None else min(lo, a)
            hi = b if hi is None else max(hi, b)

        for cd in sq._clips.values():
            _span(cd.start, cd.end)
        for md in sq._markers.values():
            _span(md.time, md.time)
        if sq._range_highlight is not None:
            _span(sq._range_highlight.start, sq._range_highlight.end)
        for overlays in (sq._gap_overlays, sq._range_overlays):
            for ov in overlays:
                _span(ov._start, ov._end)
        for blk in self._scene.ruler._shot_blocks:
            _span(blk["start"], blk["end"])
        if sq._active_range is not None:
            _span(*sq._active_range)
        if lo is None:
            return 0.0, 0.0
        return lo, hi

    def _update_scene_rect(self):
        sq = self.parent_sequencer
        min_start, max_end = self.content_time_bounds()
        # The origin always stays in view: an all-positive timeline keeps the
        # exact scene rect it had before content below 0 was representable.
        min_start = min(min_start, 0.0)
        max_end = max(max_end, 100.0)
        vp_w = self.viewport().width()
        left = self.time_to_x(min_start)
        if left < 0:
            left -= vp_w  # the same page of slack the tail already gets
        right = self.time_to_x(max_end) + vp_w
        # Never shrink out from under the current viewport mid-scroll.  The
        # padding above is deliberately measured from CONTENT, not from where
        # the view happens to sit: adding a page to the viewport edge on every
        # rebuild grows the scene without bound while parked at either end.
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        left = min(left, visible.left())
        right = max(right, visible.right())
        row_h = max(sq._total_row_height(), self.viewport().height() - sq._content_top)
        h = sq._content_top + row_h
        self._scene.setSceneRect(left, 0, right - left, h)
        # Keep the ruler's boundingRect as wide as the scene so its ticks/
        # labels/background keep painting in a newly-widened region at high
        # zoom / far scroll (a fixed cap stopped them past width/ppu), and as
        # far left so they keep painting before frame 0.
        self._scene.ruler.set_content_left(left)
        self._scene.ruler.set_content_width(right - left)
        # Key ticks ride the same "content changed" pulse as the extent --
        # they are derived from the clips, so anything that moves one moves
        # the other.  ``alignment_times`` is the existing every-clip-and-key
        # scan (the drag-alignment candidates), not a second one.
        self._scene.ruler.set_key_ticks(sq.alignment_times())
        hbar = self.horizontalScrollBar()
        hbar_h = hbar.height() if hbar.isVisible() else 0
        sq._header.setMinimumHeight(int(h + hbar_h))

    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF):
        painter.fillRect(rect, QtGui.QColor("#1E1E1E"))
        sq = self.parent_sequencer
        _BG_MAIN = (QtGui.QColor("#262626"), QtGui.QColor("#2A2A2A"))
        _BG_SUB = (QtGui.QColor("#222222"), QtGui.QColor("#252525"))
        _CENTER_LINE = QtGui.QColor("#3A3A3A")
        for i, (y, h, is_sub, track_id) in enumerate(sq._visual_rows()):
            palette = _BG_SUB if is_sub else _BG_MAIN
            bg = palette[i % 2]
            row_rect = QtCore.QRectF(rect.left(), y, rect.width(), h)
            painter.fillRect(row_rect, bg)
            if not is_sub:
                td = sq.get_track(track_id)
                if td is not None and td.pattern is not None:
                    PatternRegistry.paint_pattern(painter, row_rect, td.pattern)
            if is_sub:
                cy = y + h / 2.0
                painter.setPen(QtGui.QPen(_CENTER_LINE, 1))
                painter.drawLine(
                    QtCore.QPointF(rect.left(), cy),
                    QtCore.QPointF(rect.right(), cy),
                )
                painter.setPen(QtCore.Qt.NoPen)

        # --- full-range background curves for expanded sub-rows ---
        # Exclude each visible clip rect so curves don't overlap clip-level
        # curve previews.  The mask follows clips in real-time during drag.
        bg_previews = getattr(sq, "_bg_curve_previews", {})
        if bg_previews:
            painter.save()
            clip_items = getattr(sq, "_clip_items", {})
            if clip_items:
                full = QtGui.QRegion(rect.toAlignedRect())
                exclude = QtGui.QRegion()
                for item in clip_items.values():
                    if item.isVisible():
                        sr = item.mapToScene(item.boundingRect()).boundingRect()
                        cr = sr.toAlignedRect()
                        if not cr.isEmpty():
                            exclude += QtGui.QRegion(cr)
                if not exclude.isEmpty():
                    painter.setClipRegion(full.subtracted(exclude))
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            for (track_id, sub_row), entry in bg_previews.items():
                preview = entry["preview"]
                segs = preview.get("segments", [])
                if not segs:
                    continue
                row_y, row_h = sq._row_position(track_id, sub_row)
                map_y, _is_flat = CurveUtils.make_value_mapper(
                    row_y,
                    row_h,
                    preview.get("val_min", 0.0),
                    preview.get("val_max", 1.0),
                )
                path = CurveUtils.build_curve_path(segs, self.time_to_x, map_y)
                c = QtGui.QColor(entry.get("color", "#CCCCCC"))
                c.setAlpha(180)
                painter.setPen(QtGui.QPen(c, 1.2))
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawPath(path)
            painter.restore()

        ar = sq._active_range
        if ar is not None:
            x0 = self.time_to_x(ar[0])
            x1 = self.time_to_x(ar[1])
            top = sq._content_top
            h = max(sq._total_row_height(), self.viewport().height() - top)
            painter.fillRect(QtCore.QRectF(x0, top, x1 - x0, h), sq._active_range_color)
