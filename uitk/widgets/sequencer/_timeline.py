# !/usr/bin/python
# coding=utf-8
"""Timeline view, scene, and track-header widgets."""
from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

from qtpy import QtWidgets, QtGui, QtCore

if TYPE_CHECKING:
    from uitk.widgets.sequencer._sequencer import SequencerWidget

from uitk.widgets.sequencer._data import (
    _TRACK_HEIGHT,
    _TRACK_PADDING,
    _RULER_HEIGHT,
    _SHOT_LANE_HEIGHT,
    _styled_menu,
)
from uitk.widgets.sequencer._clip import ClipItem
from uitk.widgets.sequencer._overlays import (
    _StaticRangeOverlay,
    _GapOverlayItem,
    RangeHighlightItem,
)
from uitk.widgets.sequencer._ruler import ShotLaneItem, RulerItem
from uitk.widgets.sequencer._playhead import PlayheadItem
from uitk.widgets.sequencer._markers import MarkerItem


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
        self._layout.setContentsMargins(0, _RULER_HEIGHT, 0, 0)
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
            self._colors.append(color)
            self._text_colors.append(text_color)
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
            idx = self._labels.index(obj)
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
        idx = self._labels.index(widget)
        if idx not in self._selected:
            self._selected = [idx]
            self._refresh_styles()
        names = self.selected_names()
        count = len(names)
        menu = _styled_menu(self)
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
            mods = event.modifiers()
            mod_int = mods.value if hasattr(mods, "value") else int(mods)
            key = QtGui.QKeySequence(event.key() | mod_int)
            for seq in self._shortcut_sequences:
                if key.matches(seq) == QtGui.QKeySequence.ExactMatch:
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

    # -- zone detection -----------------------------------------------------

    def _hit_zone(self, viewport_y: float) -> str:
        if viewport_y < _RULER_HEIGHT:
            return "ruler"
        return "tracks"

    # -- marquee helpers ----------------------------------------------------

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

        _ctrl = QtCore.Qt.ControlModifier
        _ctrl_v = _ctrl.value if hasattr(_ctrl, "value") else int(_ctrl)
        _shift = QtCore.Qt.ShiftModifier
        _shift_v = _shift.value if hasattr(_shift, "value") else int(_shift)

        # Block selectionChanged until we're done batching
        self._scene.blockSignals(True)
        try:
            if mods & _ctrl_v:
                # Ctrl: subtract items inside marquee from the pre-selection
                for item in self._scene.items():
                    if not (item.flags() & QtWidgets.QGraphicsItem.ItemIsSelectable):
                        continue
                    should = id(item) in self._marquee_pre_selection and item not in in_band
                    if item.isSelected() != should:
                        item.setSelected(should)
            elif mods & _shift_v:
                # Shift: add to pre-selection
                for item in self._scene.items():
                    if not (item.flags() & QtWidgets.QGraphicsItem.ItemIsSelectable):
                        continue
                    should = id(item) in self._marquee_pre_selection or item in in_band
                    if item.isSelected() != should:
                        item.setSelected(should)
            else:
                # No modifier: exact replacement
                for item in self._scene.items():
                    if not (item.flags() & QtWidgets.QGraphicsItem.ItemIsSelectable):
                        continue
                    should = item in in_band
                    if item.isSelected() != should:
                        item.setSelected(should)
        finally:
            self._scene.blockSignals(False)
        # Emit once
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
            self.setCursor(QtCore.Qt.ClosedHandCursor)
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
        if event.button() == QtCore.Qt.LeftButton and zone == "ruler":
            item = self.itemAt(event.pos())
            if isinstance(item, MarkerItem):
                super().mousePressEvent(event)
                return
            self._ruler_drag = True
            scene_pos = self.mapToScene(event.pos())
            t = round(self.x_to_time(scene_pos.x()))
            self._scene.playhead.time = t
            self.parent_sequencer.playhead_moved.emit(t)
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
                # Empty space — start custom marquee
                self._marquee_active = True
                self._marquee_anchor = event.pos()
                self._marquee_current = event.pos()
                self._marquee_modifier = mods.value if hasattr(mods, "value") else int(mods)
                self._space_held = False
                # Snapshot current selection (by id) for additive/subtractive modes
                self._marquee_pre_selection = {
                    id(it)
                    for it in self._scene.selectedItems()
                }
                # If no modifier, clear selection immediately
                if not (mods & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier)):
                    self._scene.clearSelection()
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
            if hs.value() >= hs.maximum() - 10:
                self._update_scene_rect()
            event.accept()
        elif self._ruler_drag:
            scene_pos = self.mapToScene(event.pos())
            t = round(self.x_to_time(scene_pos.x()))
            self._scene.playhead.time = t
            self.parent_sequencer.playhead_moved.emit(t)
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
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self._pan_active = False
            self.unsetCursor()
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton and self._ruler_drag:
            self._ruler_drag = False
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton and self._marquee_active:
            self._finish_marquee()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        zone = self._hit_zone(event.pos().y())
        if event.button() == QtCore.Qt.LeftButton and zone == "ruler":
            item = self.itemAt(event.pos())
            if isinstance(item, MarkerItem):
                super().mouseDoubleClickEvent(event)
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

        if getattr(sq, "_zone_menu_connected", False):
            sq.zone_context_menu_requested.emit(zone, t, event.globalPos())
            event.accept()
            return

        self._show_default_context_menu(sq, t, event.globalPos())

    def _show_default_context_menu(self, sq, t, global_pos):
        menu = _styled_menu(self)
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

        chosen = menu.exec_(global_pos)

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
        try:
            top = self.mapToScene(0, 0).y()
            self._scene.ruler.setPos(0, top)
            self._scene.ruler.update()
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
            elif isinstance(item, (_StaticRangeOverlay, _GapOverlayItem)):
                item.prepareGeometryChange()
                item.update()
            elif isinstance(item, ShotLaneItem):
                item.prepareGeometryChange()
                item.update()
        self._sync_ruler_pos()
        self._scene.playhead.sync()
        self._update_scene_rect()
        self.viewport().update()

    def _update_scene_rect(self):
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
        visible_right = self.x_to_time(
            self.horizontalScrollBar().value() + self.viewport().width()
        )
        max_end = max(max_end, visible_right)
        w = self.time_to_x(max_end) + self.viewport().width()
        row_h = max(sq._total_row_height(), self.viewport().height() - sq._content_top)
        h = sq._content_top + row_h
        self._scene.setSceneRect(0, 0, w, h)
        hbar = self.horizontalScrollBar()
        hbar_h = hbar.height() if hbar.isVisible() else 0
        sq._header.setMinimumHeight(int(h + hbar_h))

    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF):
        painter.fillRect(rect, QtGui.QColor("#1E1E1E"))
        sq = self.parent_sequencer
        _BG_MAIN = (QtGui.QColor("#262626"), QtGui.QColor("#2A2A2A"))
        _BG_SUB = (QtGui.QColor("#222222"), QtGui.QColor("#252525"))
        _CENTER_LINE = QtGui.QColor("#3A3A3A")
        for i, (y, h, is_sub) in enumerate(sq._visual_rows()):
            palette = _BG_SUB if is_sub else _BG_MAIN
            bg = palette[i % 2]
            painter.fillRect(QtCore.QRectF(rect.left(), y, rect.width(), h), bg)
            if is_sub:
                cy = y + h / 2.0
                painter.setPen(QtGui.QPen(_CENTER_LINE, 1))
                painter.drawLine(
                    QtCore.QPointF(rect.left(), cy),
                    QtCore.QPointF(rect.right(), cy),
                )
                painter.setPen(QtCore.Qt.NoPen)

        ar = sq._active_range
        if ar is not None:
            x0 = self.time_to_x(ar[0])
            x1 = self.time_to_x(ar[1])
            top = sq._content_top
            h = max(sq._total_row_height(), self.viewport().height() - top)
            painter.fillRect(QtCore.QRectF(x0, top, x1 - x0, h), sq._active_range_color)
