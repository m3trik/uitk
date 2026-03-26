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
from typing import Dict, List, Optional

from qtpy import QtWidgets, QtGui, QtCore

from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.settings_manager import SettingsManager
from uitk.widgets.mixins.shortcuts import ShortcutManager

from uitk.widgets.sequencer._data import (
    ClipData,
    TrackData,
    MarkerData,
    _TRACK_HEIGHT,
    _SUB_ROW_HEIGHT,
    _TRACK_PADDING,
    _RULER_HEIGHT,
    _DEFAULT_ATTRIBUTE_COLORS,
    _COMMON_ATTRIBUTES,
    _DISPLAY_COLORS,
)
from uitk.widgets.sequencer._clip import ClipItem
from uitk.widgets.sequencer._overlays import (
    _StaticRangeOverlay,
    _GapOverlayItem,
    RangeHighlightItem,
)
from uitk.widgets.sequencer._markers import MarkerItem
from uitk.widgets.sequencer._timeline import TrackHeaderWidget, TimelineView


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
        all_known = set(self._common) | set(_DISPLAY_COLORS)
        extra = sorted(set(self._active) - all_known)
        if extra:
            sep = QtWidgets.QLabel("Scene Attributes")
            sep.setStyleSheet("color:#999; font-size:10px; font-weight:bold;")
            self._grid.addWidget(sep, row, 0, 1, 2)
            row += 1
            for attr in extra:
                row = self._add_color_row(attr, row)

        # Display colors (non-attribute entries like 'consolidated')
        display_header = QtWidgets.QLabel("Display")
        display_header.setStyleSheet("color:#999; font-size:10px; font-weight:bold;")
        self._grid.addWidget(display_header, row, 0, 1, 2)
        row += 1
        for attr in _DISPLAY_COLORS:
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
        """Return the full attribute â†’ hex-color mapping."""
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
    track_deleted = QtCore.Signal(list)  # [track_name, ...] deleted via context menu
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
    gap_left_resized = QtCore.Signal(
        float, float
    )  # (original_prev_shot_end, new_prev_shot_end)
    gap_moved = QtCore.Signal(
        float, float, float, float
    )  # (old_start, old_end, new_start, new_end)
    gap_lock_changed = QtCore.Signal(float, float, bool)  # (gap_start, gap_end, locked)
    gap_lock_all_requested = QtCore.Signal()
    gap_unlock_all_requested = QtCore.Signal()
    clip_menu_requested = QtCore.Signal(
        object, int
    )  # (QMenu, clip_id) â€” add actions before exec
    gap_menu_requested = QtCore.Signal(
        object, float, float
    )  # (QMenu, gap_start, gap_end) â€” add actions before exec
    shot_block_clicked = QtCore.Signal(str)  # (shot_name) from shot lane
    shot_lane_double_clicked = QtCore.Signal(float)  # (time) edit shot at time
    zone_context_menu_requested = QtCore.Signal(
        str, float, QtCore.QPoint
    )  # (zone, time, global_pos)

    def __init__(self, parent=None, **kwargs):
        super().__init__(QtCore.Qt.Horizontal, parent)

        # -- state ----------------------------------------------------------
        self._tracks: List[TrackData] = []
        self._clips: Dict[int, ClipData] = {}
        self._clip_items: Dict[int, ClipItem] = {}
        self._next_track_id = 0
        self._next_clip_id = 0
        self._snap_interval: float = 1.0  # 1 = per-frame snap (default)
        self._undo_stack: List[Dict[int, tuple]] = []  # (start, duration) per clip_id
        self._redo_stack: List[Dict[int, tuple]] = []
        self._max_undo = 50
        self._markers: Dict[int, MarkerData] = {}
        self._marker_items: Dict[int, MarkerItem] = {}
        self._next_marker_id = 0
        self._attribute_colors: Dict[str, str] = dict(_DEFAULT_ATTRIBUTE_COLORS)
        self._expanded_tracks: Dict[int, List[str]] = {}  # track_id â†’ sub-row names
        self._sub_row_height: int = _SUB_ROW_HEIGHT
        self._sub_row_provider = None  # callable(track_id, track_name) â†’ [(sub_name, [(start,dur,label,color), ...]), ...]
        self._range_highlight: Optional[RangeHighlightItem] = None
        self._range_overlays: List[QtWidgets.QGraphicsItem] = []
        self._gap_overlays: List[QtWidgets.QGraphicsItem] = []
        self._shift_at_press: bool = False  # Shift held when last drag started
        self._show_range_overlays: bool = True  # toggle for shot range overlays
        self._show_gap_overlays: bool = True  # toggle for gap overlays
        self._show_range_highlight: bool = True  # toggle for active shot highlight
        self._window_shortcuts: bool = False  # shortcuts active at window level
        self._window_filter_installed: bool = False
        self._active_range: Optional[tuple] = None  # (start, end) in frames
        self._active_range_color = QtGui.QColor(
            90, 140, 220, 25
        )  # semi-transparent blue

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
        self.setHandleWidth(2)
        self.setCollapsible(0, True)
        self.setCollapsible(1, False)

        # Snap-close: collapse the header pane when dragged below threshold
        self._header_snap_width = 140  # default / open width
        self._header_snap_threshold = 60  # collapse if narrower

        # Persistent layout settings
        self._layout_settings = SettingsManager(namespace="sequencer/layout")
        saved_width = self._layout_settings.value("header_width")
        if saved_width is not None:
            try:
                self._header_snap_width = int(saved_width)
            except (ValueError, TypeError):
                pass
        self.setSizes([self._header_snap_width, 600])

        self.splitterMoved.connect(self._on_splitter_moved)

        # -- sync vertical scroll -------------------------------------------
        self._timeline.verticalScrollBar().valueChanged.connect(
            self._header_scroll.verticalScrollBar().setValue
        )

        # -- forward track-hide/show/delete/select from header ---------------
        self._header.track_hide_requested.connect(self.track_hidden.emit)
        self._header.track_show_requested.connect(self.track_shown.emit)
        self._header.track_delete_requested.connect(self.track_deleted.emit)
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
            ("Left", self.go_to_prev_key, "Jump to previous key"),
            ("Right", self.go_to_next_key, "Jump to next key"),
            ("Shift+Left", self.step_backward, "Step playhead backward"),
            ("Shift+Right", self.step_forward, "Step playhead forward"),
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

    @property
    def window_shortcuts(self) -> bool:
        """When ``True``, sequencer shortcuts are active whenever the
        top-level window has focus, not just when the sequencer widget
        itself is focused."""
        return self._window_shortcuts

    @window_shortcuts.setter
    def window_shortcuts(self, enabled: bool) -> None:
        if enabled == self._window_shortcuts:
            return
        self._window_shortcuts = enabled
        ctx = (
            QtCore.Qt.WindowShortcut
            if enabled
            else QtCore.Qt.WidgetWithChildrenShortcut
        )
        for entry in self._shortcut_mgr.shortcuts.values():
            entry["shortcut"].setContext(ctx)
        # Defer event filter install until the widget is shown (parented),
        # since self.window() may not return the actual top-level yet.
        if not enabled:
            self._uninstall_window_filter()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self._window_shortcuts and not self._window_filter_installed:
            self._install_window_filter()

    def _install_window_filter(self) -> None:
        win = self.window()
        if win is not None and not self._window_filter_installed:
            win.installEventFilter(self)
            self._window_filter_installed = True

    def _uninstall_window_filter(self) -> None:
        win = self.window()
        if win is not None and self._window_filter_installed:
            win.removeEventFilter(self)
            self._window_filter_installed = False

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Intercept ShortcutOverride on the window when window_shortcuts is on."""
        if (
            self._window_shortcuts
            and event.type() == QtCore.QEvent.ShortcutOverride
        ):
            # Don't intercept keystrokes while a text-editing widget has focus
            focused = QtWidgets.QApplication.focusWidget()
            if isinstance(
                focused, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)
            ):
                return super().eventFilter(obj, event)
            mods = event.modifiers()
            mod_int = mods.value if hasattr(mods, "value") else int(mods)
            key = QtGui.QKeySequence(event.key() | mod_int)
            for seq in self._timeline._shortcut_sequences:
                if key.matches(seq) == QtGui.QKeySequence.ExactMatch:
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

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

    def keyPressEvent(self, event):
        """Dispatch registered shortcuts when focus is on a non-timeline child."""
        mods = event.modifiers()
        mod_int = mods.value if hasattr(mods, "value") else int(mods)
        key_seq = QtGui.QKeySequence(event.key() | mod_int)
        for seq in self._timeline._shortcut_sequences:
            if key_seq.matches(seq) == QtGui.QKeySequence.ExactMatch:
                entry = self._shortcut_mgr.shortcuts.get(seq.toString())
                if entry:
                    entry["action"]()
                event.accept()
                return
        super().keyPressEvent(event)

    # -- public API ---------------------------------------------------------
    def add_track(
        self,
        name: str,
        icon=None,
        dimmed: bool = False,
        italic: bool = False,
        color: Optional[str] = None,
        text_color: Optional[str] = None,
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
        color : str, optional
            Hex background tint for the track header (e.g. status severity).
        text_color : str, optional
            Hex foreground colour for the track header text.
        """
        tid = self._next_track_id
        self._next_track_id += 1
        td = TrackData(track_id=tid, name=name, color=color, text_color=text_color)
        self._tracks.append(td)
        self._header.add_track_label(
            name, icon=icon, dimmed=dimmed, italic=italic,
            color=color, text_color=text_color,
        )
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

        self._capture_undo()

        a.start = new_a_start
        b.start = new_b_start

        # Refresh visual items
        for cid in (a.clip_id, b.clip_id):
            item = self._clip_items.get(cid)
            if item:
                item._sync_geometry()
                item.update()

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
        self.clear_shot_blocks()
        self._timeline._refresh_all()

    def clear_decorations(self):
        """Remove markers, overlays, and shot lane without touching tracks or clips."""
        self.clear_markers()
        self.clear_range_highlight()
        self.clear_range_overlays()
        self.clear_gap_overlays()
        self.clear_shot_blocks()

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
        locked: bool = False,
    ):
        """Add a diagonal-hatch overlay for a gap between shots."""
        item = _GapOverlayItem(self._timeline, start, end, color, alpha, locked=locked)
        item.setVisible(self._show_gap_overlays)
        self._timeline._scene.addItem(item)
        self._gap_overlays.append(item)

    def clear_gap_overlays(self):
        """Remove all gap overlays."""
        for item in self._gap_overlays:
            if item.scene():
                item.scene().removeItem(item)
        self._gap_overlays.clear()

    def set_all_gap_overlays_locked(self, locked: bool):
        """Set the locked state on every gap overlay."""
        for item in self._gap_overlays:
            item._locked = locked
            item._update_tooltip()
            item.update()

    # -- shot lane API ------------------------------------------------------

    @property
    def _content_top(self) -> float:
        """Y coordinate where track rows begin (below ruler)."""
        return _RULER_HEIGHT

    def set_shot_blocks(self, blocks: list) -> None:
        """Show coloured shot-block indicators on the ruler.

        Parameters
        ----------
        blocks : list of dict
            Each dict has ``name``, ``start``, ``end``, and ``active`` keys.
        """
        self._timeline._scene.ruler.set_shot_blocks(blocks)

    def clear_shot_blocks(self) -> None:
        """Remove all shot-block indicators from the ruler."""
        self._timeline._scene.ruler.clear_shot_blocks()

    def range_highlight(self) -> Optional[tuple]:
        """Return ``(start, end)`` of the active highlight, or ``None``."""
        if self._range_highlight is None:
            return None
        return (self._range_highlight.start, self._range_highlight.end)

    def set_hidden_tracks(self, names: List[str]):
        """Store a list of hidden track names for the 'show hidden' menu."""
        self._hidden_tracks = list(names)
        self._header._hidden_track_names = list(names)

    def set_active_range(self, start: float, end: float):
        """Set the active-shot time range painted as a column tint."""
        self._active_range = (start, end)
        self._timeline.viewport().update()

    def clear_active_range(self):
        """Remove the active-shot column tint."""
        self._active_range = None
        self._timeline.viewport().update()

    def _show_hidden_menu(self, pos):
        """Right-click on header background â†’ menu listing hidden tracks."""
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

    def _key_times(self) -> list:
        """Return sorted unique visible key times.

        Includes clip boundaries for all clips and individual keyframe
        times from expanded sub-row clips.
        """
        times: set = set()
        for cd in self._clips.values():
            times.add(cd.start)
            if cd.duration > 0:
                times.add(cd.end)
            # Include keyframe times from expanded sub-row clips
            if cd.sub_row and cd.track_id in self._expanded_tracks:
                kf = cd.data.get("keyframe_times")
                if kf:
                    for entry in kf:
                        times.add(
                            entry[0] if isinstance(entry, (list, tuple)) else entry
                        )
        return sorted(times)

    def go_to_next_key(self):
        """Jump the playhead to the next clip boundary."""
        current = self._timeline._scene.playhead.time
        for t in self._key_times():
            if t > current + 0.01:
                self._move_playhead(t)
                return

    def go_to_prev_key(self):
        """Jump the playhead to the previous clip boundary."""
        current = self._timeline._scene.playhead.time
        for t in reversed(self._key_times()):
            if t < current - 0.01:
                self._move_playhead(t)
                return

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

        Checks range highlight first, then active range (column tint),
        then falls back to framing all clips.
        """
        rh = self.range_highlight()
        if rh is not None:
            t_min, t_max = rh
        elif self._active_range is not None:
            t_min, t_max = self._active_range
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
                # Single-key (zero-duration) sub-row clips can move but
                # not resize since there is no duration to adjust.
                is_point = dur < 1e-6
                if is_point:
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
        y = self._content_top
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
        y = self._content_top
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
        else:
            # Remember the user-chosen width
            self._header_snap_width = pos
            self._layout_settings.setValue("header_width", pos)
            self._layout_settings.sync()
