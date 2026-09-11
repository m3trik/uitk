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

from contextlib import contextmanager
from typing import Dict, List, Optional

from qtpy import QtWidgets, QtGui, QtCore

from uitk.widgets.editors.color_mapping_editor import (
    ColorMappingEditor,
    ColorMappingDialog,
)
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.managers.settings_manager import SettingsManager
from uitk.managers.shortcut_manager import ShortcutManager

from uitk.widgets.sequencer._data import (
    ClipData,
    MenuUtils,
    TrackData,
    MarkerData,
    _TRACK_HEIGHT,
    _SUB_ROW_HEIGHT,
    _TRACK_PADDING,
    _HEADER_HEIGHT,
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
from uitk.widgets.sequencer._draggable import ItemRetirement
from uitk.widgets.sequencer._timeline import TrackHeaderWidget, TimelineView


#: Pixels of margin :meth:`SequencerWidget.frame_shot` leaves on each side.
_FRAME_PADDING = 40
#: A viewport narrower than this is not laid out yet -- framing into it sets a
#: zoom the user then has to undo, so the first-show framing waits for a resize.
_MIN_FRAME_VIEWPORT_WIDTH = _FRAME_PADDING * 3


# ---------------------------------------------------------------------------
#  AttributeColorDialog
# ---------------------------------------------------------------------------
class AttributeColorDialog(ColorMappingDialog):
    """Dialog for configuring attribute-type color mappings.

    Extends :class:`ColorMappingDialog` with sequencer-specific sections
    (Common / Scene / Display) and dynamic *active_attrs* discovery.

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

    _SETTINGS_NS = "sequencer/attribute_colors"

    def __init__(
        self,
        defaults: Optional[Dict[str, str]] = None,
        common_attrs: Optional[List[str]] = None,
        active_attrs: Optional[List[str]] = None,
        settings: Optional["SettingsManager"] = None,
        parent=None,
    ):
        # Copy — fallback colors for scene-attr extras are written into
        # this dict below, and mutating a caller-supplied mapping would
        # pollute shared/persistent defaults.
        defs = dict(defaults) if defaults else dict(_DEFAULT_ATTRIBUTE_COLORS)
        common = common_attrs or list(_COMMON_ATTRIBUTES)
        active = active_attrs or []

        # Build sections
        all_known = set(common) | set(_DISPLAY_COLORS)
        extra = sorted(set(active) - all_known)
        sections = [("Common", common)]
        if extra:
            sections.append(("Scene Attributes", extra))
            for attr in extra:
                if attr not in defs:
                    defs[attr] = ColorMappingEditor._FALLBACK_COLOR
        sections.append(("Display", list(_DISPLAY_COLORS)))

        kw = {"settings": settings} if settings else {"settings_ns": self._SETTINGS_NS}
        super().__init__(
            defaults=defs,
            sections=sections,
            title="Attribute Colors",
            parent=parent,
            **kw,
        )

    # Backward-compatible proxies ----------------------------------------

    @property
    def _swatches(self):
        return self._editor._swatches

    def _current_color(self, attr):
        return self._editor._current_color(attr)

    def _restore_defaults(self):
        self._editor.restore_defaults()

    @staticmethod
    def load_color_map() -> Dict[str, str]:
        """Return the persisted attribute color map without opening a dialog."""
        sm = SettingsManager(namespace=AttributeColorDialog._SETTINGS_NS)
        result = dict(_DEFAULT_ATTRIBUTE_COLORS)
        for key in sm.keys():
            val = sm.value(key)
            if val:
                result[key] = val
        return result


# ---------------------------------------------------------------------------
#  SequencerWidget  (the public API)
# ---------------------------------------------------------------------------
#: The mouse grammar, as the consumers implement it and the shortcut overlay
#: shows it: ``(group, keys, what it does)``.  A shot's own bound (its edges,
#: the ruler band's edges) never moves the shot's keys: a plain drag moves
#: the bound and the neighbouring shots ripple with their keys to keep the
#: gaps; Ctrl moves the bound and nothing else (the shot grows into the gap
#: over the keys there, or shrinks and leaves keys for the next shot); Shift
#: retimes the keys into the new span.  The ruler band's body moves the shot.
#: A gap's edge belongs to the shot beyond it: a plain drag slides that shot.
_GESTURE_DEFS = (
    ("Shot bounds", "Drag", "Move the bound; neighbours ripple (keys stay)"),
    ("Shot bounds", "Ctrl+Drag", "Move the bound only; nothing else moves"),
    ("Shot bounds", "Shift+Drag", "Retime keys into the new span"),
    ("Shot bounds", "Drag band", "Move the shot (keys ride)"),
    ("Gaps", "Drag edge", "Slide the shot beyond it (gap changes)"),
    ("Gaps", "Ctrl+Drag edge", "Move that bound only (keys stay)"),
    ("Gaps", "Shift+Drag edge", "Retime that shot into the new span"),
    ("Gaps", "Drag body", "Slide the gap (active shot's edge follows)"),
    ("Gaps", "Right-click", "Lock / unlock the gap"),
    ("Clips & keys", "Drag", "Move keys (ripple)"),
    ("Clips & keys", "Drag edge", "Scale the clip's keys"),
    ("Clips & keys", "Drag edge (multi)", "Scale the whole selection as one"),
    ("Clips & keys", "Shift (keys selected)", "Scale box: drag an end to retime"),
    ("Clips & keys", "Alt+Drag a scale end", "Scale about the playhead instead"),
    ("Clips & keys", "Shift+Drag", "Cross shot bounds, bounds stay"),
    ("Clips & keys", "Ctrl", "Snap to whole frames"),
    ("Clips & keys", "Right-click", "Tangents, lock, Move to Shot"),
    ("Timeline", "Drag", "Marquee select (Space moves it)"),
    ("Timeline", "Ctrl+Shift+Click", "Switch to the shot under the cursor"),
    ("Timeline", "Wheel / Middle-drag", "Zoom / pan"),
)


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
    clips_batch_resized(list)
        Emitted when an edge drag scaled a SELECTION of clips as one unit.
        Args: ``[(clip_id, new_start, new_duration), ...]``.
    clip_selected(int)
        Emitted when a clip is clicked.  Args: ``(clip_id,)``.
    playhead_moved(float)
        Emitted when the playhead is repositioned.  Args: ``(time,)``.
    """

    clip_moved = QtCore.Signal(int, float)
    # [(clip_id, new_start), ...] -- ordered so a consumer can commit them one
    # at a time without a landing overrunning a clip that has not moved yet
    # (see ClipItem._collision_free_order); NOT the selection order.
    clips_batch_moved = QtCore.Signal(list)
    clips_reordered = QtCore.Signal(int, int)  # (clip_id_a, clip_id_b) swap request
    clip_resized = QtCore.Signal(int, float, float)
    # An edge drag with SEVERAL clips selected scales the whole selection as
    # one unit -- [(clip_id, start, duration), ...], ordered so a consumer
    # committing them one at a time never lands a clip on a span another has
    # not left yet (``ClipItem._collision_free_order``).  ``clip_resized``
    # still carries a lone clip's own resize.
    clips_batch_resized = QtCore.Signal(list)
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
    )  # (QMenu, clip_id) — add actions before exec
    gap_menu_requested = QtCore.Signal(
        object, float, float
    )  # (QMenu, gap_start, gap_end) — add actions before exec
    shot_switch_requested = QtCore.Signal(float)  # (time) Ctrl+Shift+Click
    zone_context_menu_requested = QtCore.Signal(
        str, float, QtCore.QPoint
    )  # (zone, time, global_pos)
    header_menu_requested = QtCore.Signal(
        object
    )  # (QMenu) right-click on header background
    keys_moved = QtCore.Signal(int, list)  # (clip_id, [(old_t, new_t), ...])
    # One drag that moved keys across SEVERAL clips arrives here as a single
    # payload -- [(clip_id, [(old_t, new_t), ...]), ...] -- so a consumer can
    # commit the whole gesture as one undoable operation.  ``keys_moved`` is
    # still emitted (alone) when the drag touched exactly one clip.
    keys_batch_moved = QtCore.Signal(list)
    keys_deleted = QtCore.Signal(int, list)  # (clip_id, [time, ...])
    key_selection_changed = QtCore.Signal(
        list
    )  # [{clip_id, obj, attr_name, times}, ...]
    # Right-click on a key: the selected keys (the clicked one included),
    # grouped by clip exactly as ``key_selection_changed`` reports them, so a
    # consumer resolves both payloads with one routine.  Emitted before
    # ``exec_`` -- add actions; the widget appends Delete after them.
    key_menu_requested = QtCore.Signal(object, list)  # (QMenu, [{clip_id, times}])
    # A tangent handle of a selected key was dragged: the key's clip and
    # time, which side ("in" / "out"), and the handle VECTOR from the key in
    # curve units -- frames along, value up.  One emit per gesture, on
    # release; the preview's control point already shows the new shape, and
    # the consumer rebuilds from the scene after writing the tangent.
    key_tangent_dragged = QtCore.Signal(int, float, str, float, float)

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
        self._expanded_tracks: Dict[int, List[str]] = {}  # track_id → sub-row names
        self._bulk_depth: int = 0  # >0 inside bulk_updates() — defer scene-rect
        self._sub_row_height: int = _SUB_ROW_HEIGHT
        self._sub_row_provider = None  # callable(track_id, track_name) → [(sub_name, [(start,dur,label,color), ...]), ...]
        self._range_highlight: Optional[RangeHighlightItem] = None
        self._range_overlays: List[QtWidgets.QGraphicsItem] = []
        self._gap_overlays: List[QtWidgets.QGraphicsItem] = []
        self._shift_at_press: bool = False  # Shift held when last drag started
        # >0 while the widget is being rebuilt programmatically: the scene's
        # selectionChanged fires as items are torn down, and forwarding that
        # empty selection makes consumers clear the host app's own selection
        # on every refresh (see _on_scene_selection).
        self._selection_suppressed: int = 0
        self._snap_guide = None  # _SnapGuideItem, created lazily
        self._snap_guides_enabled: bool = True  # draw alignment guides on drag
        self._snap_to_keys: bool = False  # also SNAP the drag to those frames
        self._align_capture_px: float = 6.0  # guide/snap capture radius, px
        self._show_range_overlays: bool = True  # toggle for shot range overlays
        self._show_gap_overlays: bool = True  # toggle for gap overlays
        self._show_range_highlight: bool = True  # toggle for active shot highlight
        self._bg_curve_previews: Dict[tuple, dict] = {}  # (track_id, sub_row) → preview
        # Shift + a key selection raises a scale box around it; see
        # ``refresh_key_scale_box``.
        self._key_scale_box = None
        self._shift_held: bool = False
        self._window_shortcuts: bool = False  # shortcuts active at window level
        # Top-level window the ShortcutOverride filter is installed on.
        # Tracked by identity (not a bool) so a reparent — e.g. Maya
        # dock/undock — moves the filter instead of leaving it dangling
        # on the old window.
        self._filtered_window = None
        # (key, modifiers) dispatched by eventFilter, awaiting its
        # follow-up KeyPress; 0 when nothing is pending.
        self._filter_pending_key = 0
        # (key, modifiers) dispatched by event() on a ShortcutOverride,
        # awaiting the KeyPress Qt delivers next so keyPressEvent consumes
        # it once instead of re-dispatching; 0 when nothing is pending.
        self._override_pending_key = 0
        self._active_range: Optional[tuple] = None  # (start, end) in frames
        self._active_range_color = QtGui.QColor(
            90, 140, 220, 25
        )  # semi-transparent blue
        # Route right-clicks through ``zone_context_menu_requested`` instead
        # of the built-in default menu.  ``None`` = unset → fall back to the
        # legacy ``_zone_menu_connected`` attribute (see ``zone_menu_enabled``).
        self._zone_menu_enabled: Optional[bool] = None

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
            ("Delete", self._delete_selected_keys, "Delete selected keyframes"),
            ("Escape", self._cancel_active_drag, "Cancel the active drag"),
        ]
        self._shortcut_mgr = ShortcutManager(self)
        _ctx = QtCore.Qt.WidgetWithChildrenShortcut
        self._shortcut_mgr.add_shortcuts_batch(
            [(k, fn, desc, _ctx) for k, fn, desc in _shortcut_defs]
        )
        for group, keys, description in _GESTURE_DEFS:
            self._shortcut_mgr.add_gesture(group, keys, description)
        self._shortcut_overlay = None  # built on first show (shortcut_overlay_visible)
        self._ctrl_at_press = False
        # Keep the ShortcutOverride sequences in sync with the manager
        self._shortcut_mgr.on_change(self._sync_shortcut_sequences)
        self._sync_shortcut_sequences()

        # -- audio scrub player (lazy) --------------------------------------
        self._scrub_player = None  # type: Optional[ScrubPlayer]
        self._audio_fps: float = 24.0
        self.playhead_moved.connect(self._on_playhead_moved_for_audio)

        # -- first-show framing ---------------------------------------------
        #: Frame the active shot the first time the panel is shown.  Opening
        #: onto frame 0 of a several-thousand-frame scene means every session
        #: starts by hunting for the shot being worked on.
        self.frame_on_first_show = True
        # Armed only now: an event arriving mid-construction would reach a
        # half-built widget, and nothing can be framed before there is a
        # timeline to frame it in.
        self._pending_first_frame = True

        # -- apply kwargs via AttributesMixin --------------------------------
        if kwargs:
            self.set_attributes(self, **kwargs)

    # -- shortcut sequence sync --------------------------------------------

    def _sync_shortcut_sequences(self) -> None:
        """Rebuild the ShortcutOverride key list from the manager."""
        self._timeline._shortcut_sequences = [
            QtGui.QKeySequence(k)
            for k, v in self._shortcut_mgr.shortcuts.items()
            if not v.get("read_only")
        ]

    # -- consume assigned shortcuts so they don't leak to the host app --------

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
            if entry["shortcut"] is not None:
                entry["shortcut"].setContext(ctx)
        if not enabled:
            self._uninstall_window_filter()
        elif self.isVisible():
            # Enabled at runtime on an already-visible widget — there
            # may be no further showEvent, so install immediately or
            # keys leak to the host until the panel is hidden/reshown.
            self._install_window_filter()
        # Otherwise defer to showEvent: self.window() may not return
        # the actual top-level until the widget is shown (parented).

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self._window_shortcuts:
            # Self-guards on same-window; after a reparent (Maya
            # dock/undock) this moves the filter to the new top-level.
            self._install_window_filter()
        self._frame_first_show()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        # A show can arrive before the final geometry does, and framing
        # against a viewport a few pixels wide sets a zoom the user then has
        # to undo -- the resize that settles the geometry is the retry.
        self._frame_first_show()

    def _frame_first_show(self) -> None:
        """Frame the active shot once, as soon as there is something to frame."""
        if not (self._pending_first_frame and self.frame_on_first_show):
            return
        if self._timeline.viewport().width() < _MIN_FRAME_VIEWPORT_WIDTH:
            return
        if (
            self.range_highlight() is None
            and self._active_range is None
            and not self._clips
        ):
            return  # nothing to frame yet; a later show/resize retries
        self._pending_first_frame = False
        self.frame_shot()

    def _install_window_filter(self) -> None:
        win = self.window()
        if win is None or win is self._filtered_window:
            return
        if self._filtered_window is not None:
            try:
                self._filtered_window.removeEventFilter(self)
            except RuntimeError:
                pass  # old top-level already destroyed
        win.installEventFilter(self)
        self._filtered_window = win

    def _uninstall_window_filter(self) -> None:
        if self._filtered_window is not None:
            try:
                self._filtered_window.removeEventFilter(self)
            except RuntimeError:
                pass  # top-level already destroyed
            self._filtered_window = None

    def _match_shortcut(self, event):
        """Return ``(sequence, entry_or_None)`` when a key event matches a
        registered shortcut, else ``None``.

        The single implementation of the modifiers → QKeySequence →
        ExactMatch → manager-lookup rule shared by every intercept path
        (widget ``event``/``keyPressEvent``, the window ``eventFilter``,
        and the timeline view's handlers) so matching semantics can't
        drift between copies.
        """
        mods = event.modifiers()
        mod_int = mods.value if hasattr(mods, "value") else int(mods)
        key = QtGui.QKeySequence(event.key() | mod_int)
        for seq in self._timeline._shortcut_sequences:
            if key.matches(seq) == QtGui.QKeySequence.ExactMatch:
                return seq, self._shortcut_mgr.shortcuts.get(seq.toString())
        return None

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Intercept ShortcutOverride on the window when window_shortcuts is on.

        Accepting a ``ShortcutOverride`` prevents Qt from firing the
        matching ``QShortcut``, so the action must be dispatched here.
        The subsequent ``KeyPress`` is consumed to stop the host app
        (e.g. Maya) from also processing the key.
        """
        if self._window_shortcuts:
            if event.type() == QtCore.QEvent.ShortcutOverride:
                # Don't intercept keystrokes while a text-editing widget has focus
                focused = QtWidgets.QApplication.focusWidget()
                if isinstance(
                    focused,
                    (
                        QtWidgets.QLineEdit,
                        QtWidgets.QTextEdit,
                        QtWidgets.QPlainTextEdit,
                    ),
                ):
                    return super().eventFilter(obj, event)
                match = self._match_shortcut(event)
                if match is not None:
                    event.accept()
                    # Dispatch the action directly — the QShortcut won't
                    # fire because we accepted the override.
                    _seq, entry = match
                    if entry and entry.get("action"):
                        entry["action"]()
                    mods = event.modifiers()
                    self._filter_pending_key = (
                        event.key(),
                        mods.value if hasattr(mods, "value") else int(mods),
                    )
                    return True
            elif event.type() == QtCore.QEvent.KeyPress and self._filter_pending_key:
                # Consume the KeyPress that Qt delivers after the accepted
                # ShortcutOverride so the host app doesn't also act on it.
                # A pending key that never arrived (the press was accepted
                # elsewhere) must not linger and eat a later press — clear
                # on ANY KeyPress, consume only an exact key+mods match.
                pending_key, pending_mods = self._filter_pending_key
                self._filter_pending_key = 0
                mods = event.modifiers()
                mod_int = mods.value if hasattr(mods, "value") else int(mods)
                if event.key() == pending_key and mod_int == pending_mods:
                    return True
        return super().eventFilter(obj, event)

    def event(self, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.ShortcutOverride:
            match = self._match_shortcut(event)
            if match is not None:
                event.accept()
                # Dispatch here instead of relying on the follow-up KeyPress
                # bubbling back to keyPressEvent: accepting the override
                # suppresses the QShortcut, and any intermediate focused
                # child (e.g. a clicked track label) can swallow the KeyPress
                # so it never reaches keyPressEvent — leaving the shortcut
                # dead.  _override_pending_key gates the follow-up press so
                # the action can't fire twice.
                _seq, entry = match
                if entry and entry.get("action"):
                    entry["action"]()
                mods = event.modifiers()
                self._override_pending_key = (
                    event.key(),
                    mods.value if hasattr(mods, "value") else int(mods),
                )
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        """Dispatch registered shortcuts when focus is on a non-timeline child."""
        # Consume (once) the KeyPress that follows an override we already
        # dispatched in event().  Clear on ANY press so a stale pending key
        # — whose press never arrived because a child ate it — can't eat a
        # later, unrelated press.
        pending = self._override_pending_key
        if pending:
            self._override_pending_key = 0
            mods = event.modifiers()
            mod_int = mods.value if hasattr(mods, "value") else int(mods)
            if event.key() == pending[0] and mod_int == pending[1]:
                event.accept()
                return
        match = self._match_shortcut(event)
        if match is not None:
            _seq, entry = match
            if entry and entry.get("action"):
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
        td = TrackData(
            track_id=tid,
            name=name,
            color=color,
            text_color=text_color,
            icon=icon,
            dimmed=dimmed,
            italic=italic,
        )
        self._tracks.append(td)
        self._header.add_track_label(
            name,
            icon=icon,
            dimmed=dimmed,
            italic=italic,
            color=color,
            text_color=text_color,
        )
        self._refresh_extent()
        return tid

    def _refresh_extent(self) -> None:
        """Recompute the scrollable extent unless a bulk rebuild is running.

        Anything that changes HOW FAR the timeline reaches -- a clip, a shot
        band, a range or gap overlay -- has to go through here, or the new
        span is drawn but cannot be scrolled to.
        """
        if not self._bulk_depth:
            self._timeline._update_scene_rect()

    @contextmanager
    def bulk_updates(self):
        """Suppress per-add scene-rect recomputation during a rebuild.

        ``_update_scene_rect`` walks every clip, marker, and gap overlay;
        calling it once per ``add_clip``/``add_track`` makes a full
        rebuild O(n²).  Wrap the rebuild in this context manager and one
        recompute runs on exit::

            with widget.bulk_updates():
                widget.clear()
                for ...: widget.add_clip(...)
        """
        self._bulk_depth += 1
        self._selection_suppressed += 1
        try:
            yield
        finally:
            self._bulk_depth -= 1
            self._selection_suppressed -= 1
            if self._bulk_depth == 0:
                self._timeline._update_scene_rect()

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
        self._refresh_extent()
        return cid

    def remove_clip(self, clip_id: int):
        """Remove a clip by id."""
        if clip_id not in self._clips:
            return
        cd = self._clips.pop(clip_id)
        ItemRetirement.retire(self._clip_items.pop(clip_id, None))
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
        """Lock or unlock a clip, preventing drag/resize/rename/selection."""
        cd = self._clips.get(clip_id)
        if cd is None:
            return
        cd.locked = locked
        item = self._clip_items.get(clip_id)
        if item:
            item.sync_selectable()
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
        # Drop this track's background curve previews (mirrors
        # collapse_track) — stale entries keyed to a recycled track_id
        # would paint another object's curve across the wrong row.
        stale_bg = [k for k in self._bg_curve_previews if k[0] == track_id]
        for k in stale_bg:
            del self._bg_curve_previews[k]
        # Rebuild header labels with their FULL stored presentation and
        # re-apply expansion for still-expanded tracks — a plain-name
        # rebuild dropped icons/colors and desynced every row below an
        # expanded track from its header.
        self._header.clear_tracks()
        for i, t in enumerate(self._tracks):
            self._header.add_track_label(
                t.name,
                icon=t.icon,
                dimmed=t.dimmed,
                italic=t.italic,
                color=t.color,
                text_color=t.text_color,
            )
            sub_names = self._expanded_tracks.get(t.track_id)
            if sub_names:
                self._header.set_track_expanded(i, sub_names, self._sub_row_height)
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

    # -- audio scrub --------------------------------------------------------

    def set_audio_source(self, path: str, fps: float = 24.0) -> bool:
        """Bind an audio file (typically a composite WAV) for scrub playback.

        Once set, user-driven playhead motion automatically emits short
        audio grains.  External ``set_playhead`` calls do not trigger
        audio (no signal emission), so Maya time-sync won't stutter.
        """
        from uitk.widgets.sequencer._scrub_player import ScrubPlayer

        if self._scrub_player is None:
            self._scrub_player = ScrubPlayer(self)
        self._audio_fps = float(fps) if fps and fps > 0 else 24.0
        return self._scrub_player.set_source(path)

    def clear_audio_source(self) -> None:
        """Drop the bound audio source and stop any in-flight scrub."""
        if self._scrub_player is not None:
            self._scrub_player.clear_source()

    def _on_playhead_moved_for_audio(self, time: float) -> None:
        if self._scrub_player is None:
            return
        self._scrub_player.play_at_frame(time, self._audio_fps)

    def clear(self, *, keep_range_highlight: bool = False):
        """Remove all tracks, clips, and markers.

        Parameters
        ----------
        keep_range_highlight : bool
            If True the interactive range-highlight overlay is preserved
            across the clear so that an in-progress drag is not
            interrupted by a content rebuild.
        """
        # Tearing items out of the scene fires selectionChanged for every
        # selectable item removed — clips, markers, the range highlight.  A
        # rebuild must not be reported to consumers as the user deselecting,
        # so the guard covers the whole teardown, not just the clip loop.
        self._selection_suppressed += 1
        try:
            for cid in list(self._clips):
                ItemRetirement.retire(self._clip_items.pop(cid, None))
            self._clips.clear()
            self._tracks.clear()
            self._expanded_tracks.clear()
            # Background curve previews are keyed by (track_id, sub_row);
            # with _next_track_id reset below, a stale entry would attach to
            # whatever track recycles that id and paint the wrong curve.
            self._bg_curve_previews.clear()
            self._header.clear_tracks()
            self._next_track_id = 0
            self._next_clip_id = 0
            self._undo_stack.clear()
            self._redo_stack.clear()
            self.clear_markers()
            if not keep_range_highlight:
                self.clear_range_highlight()
            self.clear_range_overlays()
            self.clear_gap_overlays()
            self.clear_shot_blocks()
            self.clear_snap_guides()
            self.clear_key_scale_box()
        finally:
            self._selection_suppressed -= 1
        self._timeline._refresh_all()

    def clear_decorations(self, *, keep_range_highlight: bool = False):
        """Remove markers, overlays, and shot lane without touching tracks or clips.

        Parameters
        ----------
        keep_range_highlight : bool
            If True the interactive range-highlight overlay is preserved.
        """
        # Markers and the range highlight are selectable; their teardown
        # fires selectionChanged and must not read as a user deselection
        # (same guard clear() carries, for the same reason).
        self._selection_suppressed += 1
        try:
            self.clear_markers()
            if not keep_range_highlight:
                self.clear_range_highlight()
            self.clear_range_overlays()
            self.clear_gap_overlays()
            self.clear_shot_blocks()
        finally:
            self._selection_suppressed -= 1

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
        # Pin the new marker to the current viewport top (matches the
        # ruler/playhead pinning applied on every vertical scroll).
        self._timeline._sync_ruler_pos()
        return mid

    def remove_marker(self, marker_id: int):
        """Remove a marker by id.

        Emits ``marker_removed`` only when a marker with that id actually
        existed — a no-op remove must not fire the signal (it drove a
        redundant store rebuild in consumers).

        Note: ``add_marker`` and ``clear_markers`` are deliberately
        signal-free populate primitives (mirroring ``set_playhead`` vs.
        ``_move_playhead``).  User-initiated additions emit ``marker_added``
        at their call sites; consumers that repopulate markers via
        ``add_marker`` in a rebuild loop rely on the silence.
        """
        existed = marker_id in self._markers
        self._markers.pop(marker_id, None)
        ItemRetirement.retire(self._marker_items.pop(marker_id, None))
        if existed:
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
            ItemRetirement.retire(self._marker_items.pop(mid, None))
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
        self._refresh_extent()

    def clear_range_highlight(self):
        """Remove the range highlight from the timeline."""
        if self._range_highlight is not None:
            ItemRetirement.retire(self._range_highlight)
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
        self._refresh_extent()

    def clear_range_overlays(self):
        """Remove all non-interactive range overlays."""
        for item in self._range_overlays:
            ItemRetirement.retire(item)
        self._range_overlays.clear()

    def add_gap_overlay(
        self,
        start: float,
        end: float,
        color: str = "#555555",
        alpha: int = 120,
        locked: bool = False,
        tail: bool = False,
        head: bool = False,
    ):
        """Add a diagonal-hatch overlay for a gap between shots.

        ``tail=True`` places a left-edge-only handle (pass ``start == end``
        at the last shot's end) so the final shot -- which has no following
        shot to form a gap with -- still gets a drag handle; ``head=True``
        is the right-edge-only twin at the first shot's start.  Both report
        through ``gap_left_resized`` / ``gap_resized`` like a gap edge; the
        consumer tells them apart by the shot having no neighbour there.
        """
        item = _GapOverlayItem(
            self._timeline,
            start,
            end,
            color,
            alpha,
            locked=locked,
            tail=tail,
            head=head,
        )
        item.setVisible(self._show_gap_overlays)
        self._timeline._scene.addItem(item)
        self._gap_overlays.append(item)
        self._refresh_extent()

    def clear_gap_overlays(self):
        """Remove all gap overlays."""
        for item in self._gap_overlays:
            ItemRetirement.retire(item)
        self._gap_overlays.clear()

    def set_all_gap_overlays_locked(self, locked: bool):
        """Set the locked state on every gap overlay.

        Head/tail handles are exempt: they are shot-bound handles, not gaps,
        and a locked one would leave the first/last shot with no way to
        resize.
        """
        for item in self._gap_overlays:
            if item._tail or item._head:
                continue
            item._locked = locked
            item._update_tooltip()
            item.update()

    # -- shot lane API ------------------------------------------------------

    @property
    def _content_top(self) -> float:
        """Y coordinate where track rows begin -- below the ruler AND the lane."""
        return _HEADER_HEIGHT

    def set_shot_blocks(self, blocks: list) -> None:
        """Show coloured shot-block indicators on the ruler.

        Parameters
        ----------
        blocks : list of dict
            Each dict has ``name``, ``start``, ``end``, and ``active`` keys.
            An optional ``id`` is carried through untouched, so a consumer can
            get its own identifier back from :meth:`selected_shot`.
        """
        self._timeline._scene.ruler.set_shot_blocks(blocks)
        self._refresh_extent()

    def selected_shot(self) -> Optional[dict]:
        """The shot block currently marked ``active``, or ``None``.

        The widget does not own shot selection -- the consumer does, and says
        so through :meth:`set_shot_blocks` -- but a shortcut or menu acting on
        "the selected shot" needs to read it back without the consumer keeping
        a parallel copy.
        """
        return self._timeline._scene.ruler.selected_block()

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
        self._refresh_extent()
        self._timeline.viewport().update()

    def clear_active_range(self):
        """Remove the active-shot column tint."""
        self._active_range = None
        self._timeline.viewport().update()

    def _show_hidden_menu(self, pos):
        """Right-click on header background → menu with consumer actions
        and hidden-track entries."""
        # Parented to the header for positioning, so it must be
        # explicitly released — otherwise every right-click leaks one
        # QMenu child for the life of the panel.
        menu = QtWidgets.QMenu(self._header)
        try:
            # Let consumers add their own actions first
            self.header_menu_requested.emit(menu)
            if self._hidden_tracks:
                if not menu.isEmpty():
                    menu.addSeparator()
                for name in sorted(self._hidden_tracks):
                    menu.addAction(
                        f"Show: {name}", lambda n=name: self.track_shown.emit(n)
                    )
            if menu.isEmpty():
                return
            menu.exec_(self._header.mapToGlobal(pos))
        finally:
            menu.deleteLater()

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
        # Floored at the timeline's own reach rather than 0 -- stepping back
        # into a shot that lives before the origin is legitimate.
        floor = min(0.0, self._timeline.content_time_bounds()[0])
        self._move_playhead(max(floor, self._timeline._scene.playhead.time - step))

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
            # Include keyframe times from expanded sub-row clips.  Keys
            # arrive either as legacy "keyframe_times" or inside a
            # "curve_preview" dict (the form real consumers supply) —
            # without the latter, next/prev-key navigation skips every
            # visible key dot and only lands on clip boundaries.
            if cd.sub_row and cd.track_id in self._expanded_tracks:
                kf = cd.data.get("keyframe_times")
                if not kf:
                    preview = cd.data.get("curve_preview") or {}
                    kf = preview.get("keys") or []
                for entry in kf:
                    times.add(entry[0] if isinstance(entry, (list, tuple)) else entry)
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
        padding = _FRAME_PADDING
        usable = max(vp_w - padding * 2, 1)
        self._timeline._pixels_per_unit = usable / span
        self._timeline._refresh_all()
        self._timeline.horizontalScrollBar().setValue(
            int(self._timeline.time_to_x(t_min) - padding)
        )

    # Keep legacy alias so external callers aren't broken
    frame_all = frame_shot

    # -- drag cancel -------------------------------------------------------
    def _cancel_active_drag(self) -> bool:
        """Abort any in-progress drag on the timeline.

        Iterates scene items, calls their ``cancel_drag`` method, and pops
        the pre-drag undo snapshot so Escape leaves no spurious undo step.
        Returns True if something was cancelled.
        """
        scene = self._timeline._scene
        if scene is None:
            return False
        cancelled = False
        captured_undo = False
        for item in scene.items():
            fn = getattr(item, "cancel_drag", None)
            if callable(fn) and fn():
                cancelled = True
                if getattr(item, "_undo_captured", False):
                    captured_undo = True
                    item._undo_captured = False
        if captured_undo and self._undo_stack:
            self._undo_stack.pop()
        return cancelled

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

    # -- key alignment (guides + optional snap) ------------------------------
    @property
    def snap_guides_enabled(self) -> bool:
        """Draw a guide (and tint the drag readout) when a drag lands on a
        frame that already carries a key -- visual only."""
        return self._snap_guides_enabled

    @snap_guides_enabled.setter
    def snap_guides_enabled(self, value: bool):
        self._snap_guides_enabled = bool(value)
        if not value:
            self.clear_snap_guides()

    @property
    def snap_to_keys(self) -> bool:
        """Also pull a drag onto a nearby key frame, not just highlight it.

        Off by default: the guides answer "am I aligned?" without taking
        control of the drag away from the user.
        """
        return self._snap_to_keys

    @snap_to_keys.setter
    def snap_to_keys(self, value: bool):
        self._snap_to_keys = bool(value)

    #: Guide colour — deliberately distinct from every clip/attribute colour.
    SNAP_GUIDE_COLOR = "#FFD24A"

    def alignment_times(
        self, exclude_clip_ids=(), exclude_times=(), exclude_spans=()
    ) -> List[float]:
        """Sorted, de-duplicated frames that a drag can align to.

        Every clip's start/end plus every visible keyframe dot, minus what
        the drag itself is moving.  Values are rounded to 3 decimals so
        float drift can't produce two entries one microframe apart.

        Parameters:
            exclude_clip_ids: Clips being dragged — skipped entirely.
            exclude_times: Absolute frames to drop (matched on the rounded
                grain).  Key drags pass their keys' origin frames, which
                alias into the merged segment bar's edges and sibling
                sub-row keys.
            exclude_spans: ``(track_id, start, end)`` pre-drag spans of the
                moving content — a candidate from any clip on that track
                falling inside the span is dropped, so a drag never aligns
                to a stale alias of the very content it is moving.  Clips
                and keys on the same track OUTSIDE the span stay valid
                (end-to-start butting against neighbours still works).
        """
        exclude = set(exclude_clip_ids)
        ex_times = {round(float(t), 3) for t in exclude_times}
        spans = [(tid, lo - 1e-3, hi + 1e-3) for tid, lo, hi in exclude_spans]

        def _dropped(track_id, t):
            if t in ex_times:
                return True
            return any(tid == track_id and lo <= t <= hi for tid, lo, hi in spans)

        times: set = set()
        for cd in self._clips.values():
            if cd.clip_id in exclude:
                continue
            for t in self._clip_candidate_times(cd):
                if not _dropped(cd.track_id, t):
                    times.add(t)
        return sorted(times)

    @staticmethod
    def _clip_candidate_times(cd):
        """Yield one clip's alignment candidates, rounded to the grain."""
        yield round(cd.start, 3)
        if cd.duration > 0:
            yield round(cd.end, 3)
        preview = cd.data.get("curve_preview") or {}
        for entry in preview.get("keys") or ():
            t = entry[0] if isinstance(entry, (list, tuple)) else entry
            yield round(float(t), 3)

    def nearest_alignment(
        self, time: float, candidates, tolerance: Optional[float] = None
    ) -> Optional[float]:
        """Return the entry of *candidates* within *tolerance* of *time*.

        *tolerance* defaults to the pixel capture radius converted to
        frames at the current zoom, so the affordance keeps the same
        on-screen feel however far the user has zoomed in or out.
        """
        if not candidates:
            return None
        if tolerance is None:
            ppu = self._timeline.pixels_per_unit or 1.0
            tolerance = self._align_capture_px / ppu
        best = None
        best_d = tolerance
        for t in candidates:
            d = abs(t - time)
            if d <= best_d:
                best, best_d = t, d
        return best

    def set_snap_guides(self, times) -> None:
        """Show vertical alignment guides at *times* (empty hides them).

        The item is kept and emptied rather than destroyed: this runs on
        every mouse-move of a drag, and churning a QGraphicsItem per pixel
        of travel is pure waste.  ``clear_snap_guides`` frees it.
        """
        if not self._snap_guides_enabled:
            return
        times = [float(t) for t in times]
        if not times:
            if self._snap_guide is not None:
                self._snap_guide.set_times([])
            return
        if self._snap_guide is None:
            from uitk.widgets.sequencer._overlays import _SnapGuideItem

            self._snap_guide = _SnapGuideItem(
                self._timeline, color=self.SNAP_GUIDE_COLOR
            )
            self._timeline._scene.addItem(self._snap_guide)
        self._snap_guide.set_times(times)

    def clear_snap_guides(self) -> None:
        """Remove the alignment guides."""
        if self._snap_guide is not None:
            ItemRetirement.retire(self._snap_guide)
            self._snap_guide = None

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

    @property
    def zone_menu_enabled(self) -> bool:
        """When ``True``, right-clicks emit :attr:`zone_context_menu_requested`
        (letting the consumer present a zone-specific menu) instead of the
        widget's built-in default context menu.

        Set this ``True`` after connecting a slot to
        ``zone_context_menu_requested``.  For backward compatibility the
        legacy private ``_zone_menu_connected`` attribute is still honoured
        as a fallback when this property has not been set explicitly.
        """
        if self._zone_menu_enabled is not None:
            return self._zone_menu_enabled
        return bool(getattr(self, "_zone_menu_connected", False))

    @zone_menu_enabled.setter
    def zone_menu_enabled(self, value: bool) -> None:
        self._zone_menu_enabled = bool(value)

    @property
    def shift_held_at_press(self) -> bool:
        """Whether Shift was held when the last drag interaction started."""
        return self._shift_at_press

    @shift_held_at_press.setter
    def shift_held_at_press(self, value: bool) -> None:
        self._shift_at_press = value

    @property
    def ctrl_held_at_press(self) -> bool:
        """Whether Ctrl was held when the last drag interaction started.

        The consumers' "bound only" gate: a shot-bound handle grabbed with
        Ctrl moves the bound and leaves the keys where they are.
        """
        return self._ctrl_at_press

    @ctrl_held_at_press.setter
    def ctrl_held_at_press(self, value: bool) -> None:
        self._ctrl_at_press = bool(value)

    def record_press_modifiers(self, modifiers) -> None:
        """Bank the modifiers a press carried, for the consumers' gates.

        Every press site calls this -- clips, keys, both overlays, the ruler
        band -- so a gesture never inherits what the LAST one left behind.
        """
        self._shift_at_press = bool(modifiers & QtCore.Qt.ShiftModifier)
        self._ctrl_at_press = bool(modifiers & QtCore.Qt.ControlModifier)

    # -- shortcut overlay ---------------------------------------------------

    @property
    def shortcut_overlay(self):
        """The corner legend (:class:`ShortcutOverlay`), or ``None`` until
        it has been shown once."""
        return self._shortcut_overlay

    @property
    def shortcut_overlay_visible(self) -> bool:
        """Show a legend of the drag grammar and keys in the timeline's corner.

        The reminder Substance Painter keeps in its viewport: the gesture
        group under the pointer is brightened as the mouse moves.  Built on
        first show from the shortcut manager's gestures and bindings.
        """
        return self._shortcut_overlay is not None and self._shortcut_overlay.isVisible()

    @shortcut_overlay_visible.setter
    def shortcut_overlay_visible(self, value: bool) -> None:
        if value and self._shortcut_overlay is None:
            self._shortcut_overlay = self._shortcut_mgr.overlay(self._timeline)
        if self._shortcut_overlay is not None:
            self._shortcut_overlay.setVisible(bool(value))
            if value:
                self._shortcut_overlay.refresh()

    def _set_gesture_context(self, group: Optional[str]) -> None:
        """Brighten *group* on the legend, if one is showing."""
        if self._shortcut_overlay is not None:
            self._shortcut_overlay.set_context(group)

    # -- attribute colors ---------------------------------------------------
    @property
    def attribute_colors(self) -> Dict[str, str]:
        """Mapping of attribute name to hex color string.

        The getter returns the *live* internal dict (it is read on the clip
        paint path via ``_resolve_color``, so no defensive copy is made).
        Mutating it in place therefore does **not** trigger a repaint --
        assign a whole new mapping through the setter, or call
        :meth:`set_attribute_color`, to have the change reflected on screen.
        """
        return self._attribute_colors

    @attribute_colors.setter
    def attribute_colors(self, value: Dict[str, str]):
        self._attribute_colors = dict(value)
        self._timeline._scene.update()

    def set_attribute_color(self, name: str, color: str) -> None:
        """Set a single attribute's color and repaint.

        Prefer this over mutating the :attr:`attribute_colors` mapping in
        place (e.g. ``seq.attribute_colors["translateX"] = "#FF0000"``):
        the property getter returns the live dict for paint-path
        efficiency, so an in-place assignment updates the backing store but
        does not trigger the scene repaint this method (and the property
        setter) perform.
        """
        self._attribute_colors[name] = color
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
                self.add_clip(
                    track_id,
                    start,
                    dur,
                    label=label,
                    color=color,
                    sub_row=sub_name,
                    **extra,
                )

        self._sync_track_selectability(track_id)
        idx = self._track_index(track_id)
        if idx is not None:
            self._header.set_track_expanded(idx, sub_names, self._sub_row_height)
        self._timeline._refresh_all()
        self.track_expanded.emit(track_id)

    def set_bg_curve_preview(
        self, track_id: int, sub_row: str, preview: dict, color: str = "#CCCCCC"
    ) -> None:
        """Set or clear a background curve preview for a sub-row.

        Parameters
        ----------
        preview : dict or None
            ``{keys, segments, val_min, val_max}`` from
            ``build_curve_preview``, or *None* to clear.
        color : str
            Hex color for the curve line.
        """
        key = (track_id, sub_row)
        if preview is None:
            self._bg_curve_previews.pop(key, None)
        else:
            self._bg_curve_previews[key] = {"preview": preview, "color": color}
        self._timeline.viewport().update()

    def collapse_track(self, track_id: int):
        """Collapse a previously expanded track, removing its sub-row clips."""
        if track_id not in self._expanded_tracks:
            return
        self._expanded_tracks.pop(track_id)
        # Remove background curve previews for this track
        stale_bg = [k for k in self._bg_curve_previews if k[0] == track_id]
        for k in stale_bg:
            del self._bg_curve_previews[k]
        # Remove sub-row clips
        to_remove = [
            cid
            for cid, cd in self._clips.items()
            if cd.track_id == track_id and cd.sub_row
        ]
        for cid in to_remove:
            self.remove_clip(cid)
        self._sync_track_selectability(track_id)
        idx = self._track_index(track_id)
        if idx is not None:
            self._header.set_track_collapsed(idx)
        self._timeline._refresh_all()
        self.track_collapsed.emit(track_id)

    def _sync_track_selectability(self, track_id: int) -> None:
        """Re-apply every main-row clip's selectable flag for *track_id*.

        A main-row clip on an expanded track is only a summary of the key
        dots below it (:meth:`ClipItem.is_selectable`), so expansion revokes
        its selection and collapse gives it back.  A selection actually
        dropped is reported once, as a real selection change: the consumer
        mirrors the widget's selection into its host app and would otherwise
        keep showing a bar the user can no longer pick.
        """
        dropped = False
        for cd in self._clips.values():
            if cd.track_id != track_id or cd.sub_row:
                continue
            item = self._clip_items.get(cd.clip_id)
            if item is None:
                continue
            was_selected = item.isSelected()
            self._selection_suppressed += 1
            try:
                item.sync_selectable()
            finally:
                self._selection_suppressed -= 1
            dropped = dropped or (was_selected and not item.isSelected())
        if dropped and not self._selection_suppressed:
            self._on_scene_selection()

    def is_track_expanded(self, track_id: int) -> bool:
        """Return True if the track is currently expanded."""
        return track_id in self._expanded_tracks

    def toggle_track_expanded(self, track_id: int):
        """Toggle expansion state.  Uses ``sub_row_provider`` when expanding."""
        if self.is_track_expanded(track_id):
            self.collapse_track(track_id)
        else:
            self.expand_track(track_id)

    def _iter_rows(self):
        """Yield ``(track, sub_name_or_None, y, height)`` for every visual row.

        Single source of the row-layout accumulation (track height +
        padding + per-sub-row height + padding) — ``_row_position``,
        ``_total_row_height``, and ``_visual_rows`` are all expressed
        through it so the metrics can't silently diverge.
        """
        y = self._content_top
        for td in self._tracks:
            yield td, None, y, _TRACK_HEIGHT
            y += _TRACK_HEIGHT + _TRACK_PADDING
            for sr in self._expanded_tracks.get(td.track_id, []):
                yield td, sr, y, self._sub_row_height
                y += self._sub_row_height + _TRACK_PADDING

    def _row_position(self, track_id: int, sub_row: str = "") -> tuple:
        """Return ``(y, height)`` for a given track and optional sub-row."""
        fallback = None
        for td, sr, y, h in self._iter_rows():
            if td.track_id != track_id:
                continue
            if not sub_row:
                if sr is None:
                    return y, h
            elif sr == sub_row:
                return y, h
            # Remember the last row of the matching track: a requested
            # sub-row that isn't expanded falls through to just after
            # the track's final row (legacy behavior).
            fallback = (y + h + _TRACK_PADDING, self._sub_row_height)
        if sub_row and fallback is not None:
            return fallback
        # Past the end — first free y after all rows.
        end_y = self._content_top
        for _td, _sr, y, h in self._iter_rows():
            end_y = y + h + _TRACK_PADDING
        return end_y, _TRACK_HEIGHT

    def _total_row_height(self) -> float:
        """Total pixel height of all tracks including expanded sub-rows."""
        h = 0.0
        for _td, _sr, _y, row_h in self._iter_rows():
            h += row_h + _TRACK_PADDING
        return h

    def _visual_rows(self) -> List[tuple]:
        """Return ``[(y, height, is_sub_row, track_id), ...]`` for background painting."""
        return [
            (y, h, sr is not None, td.track_id) for td, sr, y, h in self._iter_rows()
        ]

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

    def selected_keys(self) -> List[dict]:
        """Selected keyframe dots grouped by clip: ``[{clip_id, times}, ...]``.

        The payload of :attr:`key_selection_changed`, :attr:`key_menu_requested`
        and the Delete shortcut alike, so every consumer resolves a key
        selection through one routine.
        """
        from uitk.widgets.sequencer._keyframe import KeyframeItem

        try:
            items = self._timeline._scene.selectedItems()
        except RuntimeError:
            return []
        by_clip: dict = {}
        for item in items:
            if isinstance(item, KeyframeItem):
                cid = item._parent_clip._data.clip_id
                by_clip.setdefault(cid, {"clip_id": cid, "times": []})
                by_clip[cid]["times"].append(item._time)
        return list(by_clip.values())

    def select_keys(self, wanted: List[dict], replace: bool = True) -> int:
        """Select keyframe dots by clip data and time; returns how many matched.

        *wanted* is ``[{"data": {...}, "times": [...]}, ...]``: a key is
        selected when its clip's ``data`` bag carries every item of ``data``
        and its time is one of ``times`` (within 1e-6 -- the times come back
        from :meth:`selected_keys`, so they match exactly).  This is how
        a consumer keeps a key selection alive across its own rebuild, whose
        clip ids are fresh every time -- the ``data`` bag is the consumer's
        own vocabulary (``obj``/``attr_name``, say), so no id survives here.
        One ``key_selection_changed`` for the whole batch, not one per dot.
        """
        scene = self._timeline._scene
        selectable = QtWidgets.QGraphicsItem.ItemIsSelectable
        n = 0
        self._selection_suppressed += 1
        try:
            if replace:
                scene.clearSelection()
            for item in self._clip_items.values():
                bag = item._data.data
                for want in wanted:
                    match = want.get("data") or {}
                    if any(bag.get(k) != v for k, v in match.items()):
                        continue
                    times = want.get("times") or []
                    for ki in item._keyframe_items:
                        if not (ki.flags() & selectable):
                            continue
                        if any(abs(ki._time - t) <= 1e-6 for t in times):
                            ki.setSelected(True)
                            n += 1
        finally:
            self._selection_suppressed -= 1
        self._on_scene_selection()
        return n

    # -- internal -----------------------------------------------------------
    def _on_scene_selection(self):
        if self._selection_suppressed:
            # Programmatic rebuild, not a user gesture.  Forwarding it would
            # make consumers mirror an empty selection into the host app --
            # the "I can't keep anything selected" symptom when something
            # refreshes the panel repeatedly.
            return
        sel = self.selected_clips()
        self.selection_changed.emit(sel)
        # Backwards-compat: also emit clip_selected for the first item
        if sel:
            self.clip_selected.emit(sel[0])

        # Emit key-level selection info for graph-editor sync.
        self.key_selection_changed.emit(self.selected_keys())
        # The Shift scale box brackets the SELECTION, so it follows it.
        self.refresh_key_scale_box()

    def show_key_menu(self, global_pos) -> bool:
        """Open the key menu for the current key selection; ``False`` if empty.

        The menu belongs to the SELECTION, not to the dot under the cursor:
        a right-click anywhere over the tracks opens it while any key is
        selected (:meth:`TimelineView.contextMenuEvent`), so reaching a
        tangent type never means hitting a 7-pixel dot.  Everything in it --
        tangent types, move to shot -- is the consumer's, added through
        :attr:`key_menu_requested` before the menu opens; the widget adds
        nothing of its own, so a consumer that offers nothing gets no menu
        rather than an empty one.

        Deleting is deliberately NOT here: ``Delete`` is a registered
        shortcut (:meth:`_delete_selected_keys`, which a host may re-point)
        acting on this same selection, and a menu row duplicating a key
        every editor already binds is one more row between the user and the
        rows only this menu has.

        Parameters:
            global_pos (QPoint): Screen position to open the menu at.

        Returns:
            bool: True when a menu was shown.
        """
        groups = self._editable_key_groups()
        if not groups:
            return False
        menu = MenuUtils._styled_menu()
        self.key_menu_requested.emit(menu, groups)
        if not menu.actions():
            return False
        menu.exec_(global_pos)
        return True

    # -- key scale handles --------------------------------------------------
    def _scalable_keys(self) -> list:
        """Selected key dots that a scale may retime.

        The selection minus the dots on a clip that refuses key edits
        (:attr:`ClipItem.keys_editable`) -- the same gate the key menu and
        Delete take, for the same reason: a marquee can sweep a locked or
        read-only row, and an edit from here would be written straight into
        the host.
        """
        from uitk.widgets.sequencer._keyframe import KeyframeItem

        try:
            items = self._timeline._scene.selectedItems()
        except RuntimeError:
            return []
        return [
            item
            for item in items
            if isinstance(item, KeyframeItem) and item._parent_clip.keys_editable
        ]

    def _key_scale_span(self, keys) -> Optional[tuple]:
        """``(lo, hi, top, bottom)`` the scale box should bracket, or None.

        None whenever a scale is meaningless -- fewer than two keys, or every
        key on one frame, where no ratio exists to scale by.
        """
        times = [k._time for k in keys]
        if len(keys) < 2 or (max(times) - min(times)) < 1e-6:
            return None
        tops, bottoms = [], []
        for k in keys:
            rect = k._parent_clip.rect()
            tops.append(rect.top())
            bottoms.append(rect.bottom())
        return min(times), max(times), min(tops), max(bottoms)

    def refresh_key_scale_box(self) -> None:
        """Show or hide the Shift scale box around the current key selection.

        Held Shift plus a key selection is the request; anything else --
        Shift let go, the selection gone or collapsed onto one frame, a
        scale already in flight -- takes the box away again.  Called from
        the timeline's key handling and from every key-selection change, so
        the box tracks both halves of the condition.
        """
        from uitk.widgets.sequencer._keyframe import KeyScaleBoxItem

        box = self._key_scale_box
        if box is not None and box._is_drag_active():
            return
        span = None
        if self._shift_held:
            span = self._key_scale_span(self._scalable_keys())
        if span is None:
            self.clear_key_scale_box()
            return
        if box is None:
            box = self._key_scale_box = KeyScaleBoxItem(self)
            self._timeline._scene.addItem(box)
        box.set_span(*span)

    def clear_key_scale_box(self) -> None:
        """Remove the scale box, cancelling a drag it still owns.

        Cheap when there is nothing up: this runs from ``_refresh_all``, on
        every zoom, scroll and rebuild.
        """
        box = self._key_scale_box
        if box is None:
            return
        box.cancel_drag()
        ItemRetirement.retire(box)
        self._key_scale_box = None

    def set_shift_held(self, held: bool) -> None:
        """Record whether Shift is down and re-evaluate the scale box."""
        held = bool(held)
        if held == self._shift_held:
            return
        self._shift_held = held
        self.refresh_key_scale_box()

    def _editable_key_groups(self) -> List[dict]:
        """:meth:`selected_keys` minus the clips that refuse key edits.

        What the key menu offers and what Delete acts on: both are built
        from the SELECTION, which a marquee can sweep across a locked or
        read-only row (:attr:`ClipItem.keys_editable`) that must not be
        written to.
        """
        groups = []
        for group in self.selected_keys():
            item = self._clip_items.get(group["clip_id"])
            if item is None or item.keys_editable:
                groups.append(group)
        return groups

    def _delete_selected_keys(self):
        """Delete all selected :class:`KeyframeItem` instances.

        Groups deletions by parent clip and emits one
        :attr:`keys_deleted` signal per clip -- for the clips that accept
        key edits; a locked or read-only row keeps its keys.
        """
        groups = self._editable_key_groups()
        if not groups:
            return

        self._capture_undo()
        for group in groups:
            self.keys_deleted.emit(group["clip_id"], group["times"])

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
            # Remember the user-chosen width.  No sync() here — splitter
            # drags emit per-mouse-move and each sync() is a disk flush;
            # QSettings flushes automatically on destruction.
            self._header_snap_width = pos
            self._layout_settings.setValue("header_width", pos)
