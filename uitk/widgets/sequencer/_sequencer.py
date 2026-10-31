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

import dataclasses
from contextlib import contextmanager
from typing import Any, Dict, List, Mapping, Optional, Tuple

from qtpy import QtWidgets, QtGui, QtCore
from uitk.themes.style_sheet import StyleSheet

from uitk.widgets.editors.color_mapping_editor import (
    ColorMappingEditor,
    ColorMappingDialog,
)
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter
from uitk.widgets.widgetComboBox import WidgetComboBox
from uitk.managers.settings_manager import SettingsManager
from uitk.managers.shortcut_manager import ShortcutManager

from uitk.widgets.sequencer._data import (
    ClipData,
    TrackData,
    MarkerData,
    RowMetrics,
    _RULER_HEIGHT,
    DISPLAY_COLORS,
    SELECTED_ACCENT,
)
from uitk.widgets.sequencer._editor import (
    SequencerEditor,
    TrackEditor,
    _EditorRegistry,
)
from uitk.widgets.sequencer._layer import SequencerLayer, _LayerRegistry
from uitk.widgets.sequencer._overlays import RangeHighlightItem, _Ranges, _Snapping
from uitk.widgets.sequencer._markers import _MarkerSet
from uitk.widgets.sequencer._draggable import ItemRetirement
from uitk.widgets.sequencer._timeline import (
    TrackHeaderWidget,
    TimelineView,
    _SHIFT_MOD,
)
from uitk.widgets.sequencer._rows import _TrackRows
from uitk.widgets.sequencer._selection import _KeyScaleBox, _Selection
from uitk.widgets.sequencer._shortcuts import _KeyRouting, _ShortcutLegend
from uitk.widgets.sequencer._navigation import _Navigation


# ---------------------------------------------------------------------------
#  AttributeColorDialog
# ---------------------------------------------------------------------------
class AttributeColorDialog(ColorMappingDialog):
    """Dialog for configuring attribute-type color mappings.

    Extends :class:`ColorMappingDialog` with sequencer-specific sections
    (Common / Scene / Display) and dynamic *active_attrs* discovery.  The
    attribute vocabulary is the host's: uitk supplies only its own display rows
    (:data:`DISPLAY_COLORS`), so a DCC passes its channel names and colours in.

    Parameters:
        defaults (Mapping[str, object]): Factory-default ``{attr_name: color}``
            for the host's attributes; a value is anything whose ``str()`` is a
            colour (``"#E06666"``, a ``pythontk.Color``), so
            ``ptk.Palette.channels()`` passes as is.
        common_attrs (list): Attribute names always displayed regardless of
            scene content.
        active_attrs (list, optional): Additional attribute names currently
            keyed in the scene (:meth:`SequencerWidget.clip_attributes`).
        settings (SettingsManager, optional): Persistence; defaults to the
            sequencer's own namespace, the one :meth:`load_color_map` reads.
        parent (QWidget, optional): Parent widget.
    """

    _SETTINGS_NS = "sequencer/attribute_colors"

    def __init__(
        self,
        defaults: Optional[Mapping[str, object]] = None,
        common_attrs: Optional[List[str]] = None,
        active_attrs: Optional[List[str]] = None,
        settings: Optional["SettingsManager"] = None,
        parent=None,
    ):
        # A fresh dict — fallback colors for scene-attr extras are written into
        # it below, and mutating a caller-supplied mapping would pollute
        # shared/persistent defaults.
        defs = self._with_display_colors(defaults)
        common = list(common_attrs or [])
        active = active_attrs or []

        # Build sections
        all_known = set(common) | set(DISPLAY_COLORS)
        extra = sorted(set(active) - all_known)
        sections = [("Common", common)] if common else []
        if extra:
            sections.append(("Scene Attributes", extra))
            for attr in extra:
                if attr not in defs:
                    defs[attr] = ColorMappingEditor._FALLBACK_COLOR
        sections.append(("Display", list(DISPLAY_COLORS)))

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
    def _with_display_colors(
        defaults: Optional[Mapping[str, object]],
    ) -> Dict[str, str]:
        """``DISPLAY_COLORS`` overlaid with the host's *defaults*, as hex strings."""
        merged = dict(DISPLAY_COLORS)
        merged.update({name: str(color) for name, color in (defaults or {}).items()})
        return merged

    @staticmethod
    def load_color_map(
        defaults: Optional[Mapping[str, object]] = None,
    ) -> Dict[str, str]:
        """The persisted attribute color map, without opening a dialog.

        Parameters:
            defaults (Mapping[str, object]): The host's factory colours, as
                :class:`AttributeColorDialog` takes them; the user's saved
                choices win over them.

        Returns:
            dict: ``{attr_name: hex}`` -- display rows, *defaults*, then saves.
        """
        sm = SettingsManager(namespace=AttributeColorDialog._SETTINGS_NS)
        result = AttributeColorDialog._with_display_colors(defaults)
        for key in sm.keys():
            val = sm.value(key)
            if val:
                result[key] = val
        return result


# ---------------------------------------------------------------------------
#  SequencerWidget  (the public API)
# ---------------------------------------------------------------------------


class _OptionsCombo(WidgetComboBox):
    """The Options band's combobox: the rows are read from the active editor
    as it opens (:meth:`_OptionsBand.rebuild`), so they say the options'
    values now -- a graph's context menu sets the same ones."""

    def __init__(self, band: "_OptionsBand"):
        super().__init__(band)
        self._band = band

    def showPopup(self) -> None:
        self._band.rebuild()
        super().showPopup()


class _OptionsBand(QtWidgets.QWidget):
    """The header pane's top strip, level with the ruler and the lanes under it.

    Pinned like them -- the rows scroll under it -- and holding one combobox
    the pane's full width: the active editor's Options
    (:meth:`SequencerEditor.options`), a checkbox each under its section's
    title, collapsed until asked for, so a view's settings never cost the
    pane's room.
    """

    def __init__(self, sequencer, host: QtWidgets.QWidget):
        super().__init__(host)
        self._sequencer = sequencer
        self.setObjectName("sequencerOptionsBand")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet("#sequencerOptionsBand { background: #2B2B2B; }")
        layout = QtWidgets.QHBoxLayout(self)
        # The combobox IS the band: edge to edge, no arrow (2026-10-12).
        layout.setContentsMargins(0, 0, 0, 0)
        self.combo = _OptionsCombo(self)
        self.combo.setToolTip("This view's options")
        self.combo.item_spacing = 0  # the checkbox rows sit flush
        self.combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        layout.addWidget(self.combo)
        self.rebuild()
        host.installEventFilter(self)
        # A page switch raises the new page over every sibling, this strip
        # included: raise it back, or an editor switch buries the button.
        host.currentChanged.connect(lambda _index: self.sync_geometry())
        self.sync_geometry()

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show):
            self.sync_geometry()
        return False

    def sync_geometry(self) -> None:
        host = self.parentWidget()
        self.setGeometry(0, 0, host.width(), int(self._sequencer._content_top))
        self.raise_()

    def rebuild(self) -> None:
        """The combobox's rows from the active editor's options: a checkbox
        each, reading its value now, grouped under their sections' titles in
        the order the sections were first added (unsectioned rows first)."""
        from uitk.widgets.separator import Separator

        rows = self._sequencer.active_editor.options()
        order = {"": 0}  # a section's rank: first added first, unsectioned top
        for row in rows:
            order.setdefault(row["section"], len(order))
        rows = sorted(rows, key=lambda r: order[r["section"]])
        widgets, section = [], ""
        for row in rows:
            if row["section"] != section:
                section = row["section"]
                widgets.append(Separator(title=section))
            box = QtWidgets.QCheckBox(row["label"])
            box.setChecked(bool(row["get"]()))
            box.setToolTip(row["tooltip"])
            box.toggled.connect(lambda on, r=row: r["set"](on))
            widgets.append(box)
        if not widgets:
            note = QtWidgets.QLabel("No options for this view")
            note.setEnabled(False)
            widgets.append(note)
        self.combo.add(widgets, header="Options:")
        model = self.combo.model()
        for i in range(model.rowCount()):  # a click acts on its widget, never picks
            model.item(i).setFlags(QtCore.Qt.ItemIsEnabled)

    def rows(self) -> List[QtWidgets.QWidget]:
        """The combobox's row widgets, top to bottom."""
        return [self.combo.widgetAt(i) for i in range(self.combo.count())]


# ---------------------------------------------------------------------------
#  SequencerWidget's parts: each owns its state and holds the widget, calling
#  its public methods through it (an override of one reaches every caller).
#  The larger ones live in modules of their own (``_rows.py``,
#  ``_selection.py``, ``_shortcuts.py``, ``_navigation.py``) or beside the
#  items they own (``_markers.py``, ``_overlays.py``, ``_layer.py``,
#  ``_editor.py``).
# ---------------------------------------------------------------------------


class _UndoStack:
    """The clip-position undo the widget falls back on when no host rebuilds
    it from :attr:`SequencerWidget.undo_requested`: ``{clip_id: (start,
    duration)}`` snapshots, the newest last, :attr:`max_undo` deep."""

    def __init__(self, sequencer: "SequencerWidget"):
        self._sequencer = sequencer
        self.undo_stack: List[Dict[int, tuple]] = []  # (start, duration) per clip_id
        self.redo_stack: List[Dict[int, tuple]] = []
        self.max_undo = 50

    def snapshot(self) -> Dict[int, tuple]:
        clips = self._sequencer._clips
        return {cid: (cd.start, cd.duration) for cid, cd in clips.items()}

    def capture(self) -> None:
        self.undo_stack.append(self._sequencer._snapshot())
        if len(self.undo_stack) > self.max_undo:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def restore(self, snapshot: Dict[int, tuple]) -> None:
        """Apply a saved snapshot to all clips."""
        clips = self._sequencer._clips
        for cid, (start, dur) in snapshot.items():
            cd = clips.get(cid)
            if cd is not None:
                cd.start = start
                cd.duration = dur
        self._sequencer._timeline._refresh_all()

    def undo(self) -> None:
        sq = self._sequencer
        sq.undo_requested.emit()
        if not self.undo_stack:
            return
        self.redo_stack.append(sq._snapshot())
        self.restore(self.undo_stack.pop())

    def redo(self) -> None:
        sq = self._sequencer
        sq.redo_requested.emit()
        if not self.redo_stack:
            return
        self.undo_stack.append(sq._snapshot())
        self.restore(self.redo_stack.pop())

    def drop_last(self) -> None:
        """Forget the newest step: the one a cancelled drag captured."""
        if self.undo_stack:
            self.undo_stack.pop()

    def clear(self) -> None:
        self.undo_stack.clear()
        self.redo_stack.clear()


class _AudioScrub:
    """The audio scrub: the bound source's player (a ``ScrubPlayer``, built
    on first use) and the frame rate a playhead move becomes a grain at."""

    def __init__(self, sequencer: "SequencerWidget"):
        self._sequencer = sequencer
        self.player = None  # type: Optional[ScrubPlayer]
        self.fps: float = 24.0

    def set_source(self, path: str, fps: float) -> bool:
        from uitk.widgets.sequencer._scrub_player import ScrubPlayer

        if self.player is None:
            self.player = ScrubPlayer(self._sequencer)
        self.fps = float(fps) if fps and fps > 0 else 24.0
        return self.player.set_source(path)

    def clear_source(self) -> None:
        if self.player is not None:
            self.player.clear_source()

    def on_playhead_moved(self, time: float) -> None:
        if self.player is None:
            return
        self.player.play_at_frame(time, self.fps)


class _HeaderPane:
    """The left pane's behaviour: its width -- snapped closed below a
    threshold, remembered across sessions -- and the background menu that
    brings hidden tracks back."""

    def __init__(self, sequencer: "SequencerWidget"):
        self._sequencer = sequencer
        # Snap-close: collapse the header pane when dragged below threshold
        self.snap_width = 140  # default / open width
        self.snap_threshold = 60  # collapse if narrower
        self.settings: Optional[SettingsManager] = None  # built by restore()
        self.hidden_tracks: List[str] = []

    def restore(self) -> None:
        """Open the pane at the width the user left it at."""
        # Persistent layout settings
        self.settings = SettingsManager(namespace="sequencer/layout")
        saved_width = self.settings.value("header_width")
        if saved_width is not None:
            try:
                self.snap_width = int(saved_width)
            except (ValueError, TypeError):
                pass
        self._sequencer.setSizes([self.snap_width, 600])

    def set_hidden_tracks(self, names: List[str]) -> None:
        self.hidden_tracks = list(names)
        self._sequencer._header._hidden_track_names = list(names)

    def show_hidden_menu(self, pos) -> None:
        """Right-click on header background → menu with consumer actions
        and hidden-track entries."""
        sq = self._sequencer
        # Parented to the header for positioning, so it must be
        # explicitly released — otherwise every right-click leaks one
        # QMenu child for the life of the panel.
        menu = QtWidgets.QMenu(sq._header)
        StyleSheet.cast_shadow(menu)
        try:
            # Let consumers add their own actions first
            sq.header_menu_requested.emit(menu)
            if self.hidden_tracks:
                if not menu.isEmpty():
                    menu.addSeparator()
                for name in sorted(self.hidden_tracks):
                    menu.addAction(
                        f"Show: {name}", lambda n=name: sq.track_shown.emit(n)
                    )
            if menu.isEmpty():
                return
            menu.exec_(sq._header.mapToGlobal(pos))
        finally:
            menu.deleteLater()

    def on_splitter_moved(self, pos: int, index: int) -> None:
        """Snap-close the header pane when dragged below threshold."""
        sq = self._sequencer
        if index != 1:  # only respond to the first handle
            return
        if pos < self.snap_threshold:
            sq.setSizes([0, sq.width()])
        elif pos > 0 and sq.sizes()[0] == 0:
            # Re-opening from collapsed: restore default width
            sq.setSizes([self.snap_width, sq.width() - self.snap_width])
        else:
            # Remember the user-chosen width.  No sync() here — splitter
            # drags emit per-mouse-move and each sync() is a disk flush;
            # QSettings flushes automatically on destruction.
            self.snap_width = pos
            self.settings.setValue("header_width", pos)


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
    #: [(track_name, sub_name), ...] — sub-rows of an expanded track clicked.
    #: A track label means the whole object; a sub-row means one channel of
    #: it, so the two are separate signals rather than one with a flag.
    sub_track_selected = QtCore.Signal(list)
    track_menu_requested = QtCore.Signal(object, list)  # (QMenu, [track_name, ...])
    undo_requested = QtCore.Signal()
    redo_requested = QtCore.Signal()
    track_expanded = QtCore.Signal(int)  # (track_id) after expansion complete
    track_collapsed = QtCore.Signal(int)  # (track_id) after collapse complete
    marker_added = QtCore.Signal(int, float)  # (marker_id, time)
    marker_moved = QtCore.Signal(int, float)  # (marker_id, new_time)
    marker_changed = QtCore.Signal(int)  # (marker_id) after note/color edit
    marker_removed = QtCore.Signal(int)  # (marker_id)
    app_event = QtCore.Signal(str, object)  # (event_name, payload) generic bridge
    range_highlight_changed = QtCore.Signal(
        float, float
    )  # (start, end) after move/resize
    clip_menu_requested = QtCore.Signal(
        object, int
    )  # (QMenu, clip_id) — add actions before exec
    #: (zone, time, global_pos): ``"ruler"``, ``"tracks"``, or a lane's layer
    #: name (a layer may refine it: ``SequencerLayer.menu_zone``).
    zone_context_menu_requested = QtCore.Signal(str, float, QtCore.QPoint)
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
    )  # [{clip_id, times}, ...] -- ``selected_keys()``
    # Right-click on a key: the selected keys (the clicked one included),
    # minus rows that refuse key edits (``ClipItem.keys_editable``), grouped
    # by clip exactly as ``key_selection_changed`` reports them, so a
    # consumer resolves both payloads with one routine.  Emitted before
    # ``exec_`` -- add actions; the widget adds none of its own (Delete is
    # the shortcut, see ``show_key_menu``).
    key_menu_requested = QtCore.Signal(object, list)  # (QMenu, [{clip_id, times}])
    # A tangent handle was dragged: every key the gesture carried, grouped
    # by clip -- [(clip_id, [(time, dt, dv), ...]), ...], the handle VECTOR
    # from each key in curve units (frames along, value up) -- which side
    # ("in" / "out") it belongs to, and whether the drag asked to BREAK the
    # tangent (Alt).  A drag carries the whole key selection unless Ctrl
    # isolates it; Shift makes every key take the grabbed key's exact
    # vector instead of the same nudge.  One emit per gesture, on release;
    # the preview's control points already show the new shape, and the
    # consumer rebuilds from the scene after writing the tangents.
    keys_tangent_dragged = QtCore.Signal(list, str, bool)
    #: The content area now shows the editor of this name (``set_editor``).
    editor_changed = QtCore.Signal(str)
    #: A host finished rebuilding the content: the outermost
    #: :meth:`bulk_updates` block exited.  What an editor drawing the same
    #: data its own way (a graph editor) refreshes from.
    content_rebuilt = QtCore.Signal()

    #: The accent every "this is selected" cue is drawn in: a layer draws its
    #: own (a lane's selected band) in it, so the timeline's agree.
    SELECTED_ACCENT = SELECTED_ACCENT

    def __init__(self, parent=None, **kwargs):
        super().__init__(QtCore.Qt.Horizontal, parent)

        # -- parts: built first, so no event reaches a half-built widget -----
        self._rows = _TrackRows(self)
        self._undo = _UndoStack(self)
        self._snapping = _Snapping(self)
        self._marker_set = _MarkerSet(self)
        self._ranges = _Ranges(self)
        self._audio = _AudioScrub(self)
        self._header_pane = _HeaderPane(self)
        self._layer_registry = _LayerRegistry(self, _RULER_HEIGHT)
        self._shortcut_legend = _ShortcutLegend(self)
        self._key_routing = _KeyRouting(self)
        self._editor_registry = _EditorRegistry(self)
        self._selection = _Selection(self)
        self._scale_box = _KeyScaleBox(self)
        self._navigation = _Navigation(self)

        # -- state ----------------------------------------------------------
        self._attribute_colors: Dict[str, str] = dict(DISPLAY_COLORS)
        self._bulk_depth: int = 0  # >0 inside bulk_updates() — defer scene-rect
        self._shift_at_press: bool = False  # Shift held when last drag started
        self._mark_flat_spans: bool = True  # see mark_flat_spans
        # The chord held over the timeline, as a plain int: the Shift scale
        # box and the legend's "On Modifier" mode are both answers to it
        # (:meth:`set_modifiers_held`).
        self._modifiers_held: int = 0
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
        # Clip labels / marker notes are graphics-item tooltips over its viewport.
        TooltipPresenter.manage(self._timeline)

        # -- editors: what the content area shows (``_editor.py``) ------------
        self.register_editor(TrackEditor.name, TrackEditor)
        self.register_editor("graph", _EditorRegistry.graph_editor_factory)
        self.editor(TrackEditor.name).activate()

        # The left pane is a stack: the track header, or the active editor's
        # own page (a graph editor's curve list).
        self._header_stack = QtWidgets.QStackedWidget()
        self._header_stack.setMinimumWidth(0)
        self._header_stack.addWidget(self._header_scroll)
        #: Pinned over the pane's top strip, level with the ruler and its
        #: lanes: the active editor's Options menu.
        self._options_band = _OptionsBand(self, self._header_stack)

        self.addWidget(self._header_stack)
        self.addWidget(self._timeline)
        self.setHandleWidth(2)
        self.setCollapsible(0, True)
        self.setCollapsible(1, False)

        # The header pane's width: snap-closed, remembered (_HeaderPane).
        self._header_pane.restore()
        self.splitterMoved.connect(self._header_pane.on_splitter_moved)

        # -- sync vertical scroll -------------------------------------------
        self._timeline.verticalScrollBar().valueChanged.connect(
            self._header_scroll.verticalScrollBar().setValue
        )

        # -- forward track-hide/show/delete/select from header ---------------
        self._header.track_hide_requested.connect(self.track_hidden.emit)
        self._header.track_show_requested.connect(self.track_shown.emit)
        self._header.track_delete_requested.connect(self.track_deleted.emit)
        self._header.track_selected.connect(self.track_selected.emit)
        self._header.sub_track_selected.connect(self.sub_track_selected.emit)
        self._header.track_menu_requested.connect(self.track_menu_requested.emit)
        self._header.track_expand_requested.connect(self._rows.on_header_expand)

        # -- right-click on header background: show hidden tracks -----------
        self._header.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._header.customContextMenuRequested.connect(
            self._header_pane.show_hidden_menu
        )

        # -- selection forwarding -------------------------------------------
        self._timeline._scene.selectionChanged.connect(self._on_scene_selection)

        # -- keyboard shortcuts via ShortcutManager -------------------------
        self._key_routing.install_shortcuts()
        self._apply_legend()
        self._ctrl_at_press = False
        # Keep the ShortcutOverride sequences in sync with the manager
        self._shortcut_mgr.on_change(self._sync_shortcut_sequences)
        self._sync_shortcut_sequences()

        # -- audio scrub player (lazy) --------------------------------------
        self.playhead_moved.connect(self._audio.on_playhead_moved)

        # -- first-show framing ---------------------------------------------
        #: Frame the active shot the first time the panel is shown.  Opening
        #: onto frame 0 of a several-thousand-frame scene means every session
        #: starts by hunting for the shot being worked on.
        self.frame_on_first_show = True
        # Armed only now: an event arriving mid-construction would reach a
        # half-built widget, and nothing can be framed before there is a
        # timeline to frame it in.
        self._navigation.pending_first_frame = True

        # -- apply kwargs via AttributesMixin --------------------------------
        if kwargs:
            self.set_attributes(self, **kwargs)

    # -- shortcut sequence sync --------------------------------------------

    def _sync_shortcut_sequences(self) -> None:
        """Rebuild the ShortcutOverride key list: the active editor's keys
        (:meth:`SequencerEditor.key_bindings`), then the manager's."""
        return self._key_routing.sync_sequences()

    # -- consume assigned shortcuts so they don't leak to the host app --------

    @property
    def window_shortcuts(self) -> bool:
        """When ``True``, sequencer shortcuts are active whenever the
        top-level window has focus, not just when the sequencer widget
        itself is focused."""
        return self._key_routing.window_shortcuts

    @window_shortcuts.setter
    def window_shortcuts(self, enabled: bool) -> None:
        self._key_routing.set_window_shortcuts(enabled)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._key_routing.on_show()
        self._navigation.frame_first_show()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        # A show can arrive before the final geometry does, and framing
        # against a viewport a few pixels wide sets a zoom the user then has
        # to undo -- the resize that settles the geometry is the retry.
        self._navigation.frame_first_show()

    def _match_shortcut(self, event):
        """Return ``(sequence, entry_or_None)`` when a key event matches a
        registered shortcut, else ``None``.

        The single implementation of the modifiers → QKeySequence →
        ExactMatch → manager-lookup rule shared by every intercept path
        (widget ``event``/``keyPressEvent``, the window ``eventFilter``,
        and the timeline view's handlers) so matching semantics can't
        drift between copies.
        """
        return self._key_routing.match(event)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Intercept ShortcutOverride on the window when window_shortcuts is on.

        Accepting a ``ShortcutOverride`` prevents Qt from firing the
        matching ``QShortcut``, so the action must be dispatched here.
        The subsequent ``KeyPress`` is consumed to stop the host app
        (e.g. Maya) from also processing the key.
        """
        if self._key_routing.filter_window_event(event):
            return True
        return super().eventFilter(obj, event)

    def event(self, event: QtCore.QEvent) -> bool:
        # The type comes first: an event that arrives before the parts
        # exist (QSplitter's own construction) never reaches them.
        if event.type() == QtCore.QEvent.ShortcutOverride:
            if self._key_routing.shortcut_override(event):
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        """Dispatch registered shortcuts when focus is on a non-timeline child."""
        if not self._key_routing.key_press(event):
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
        return self._rows.add_track(name, icon, dimmed, italic, color, text_color)

    def _sync_row_bound_items(self) -> None:
        """Re-derive the overlays whose height follows the track rows.

        They hold their geometry until told (``HeldGeometryMixin``), and a
        new row is a layout change no ``_refresh_all`` follows.  A handful of
        items, so cheap inside a bulk rebuild too.
        """
        for item in (
            self._ranges.highlight,
            self._snapping.guide,
            *self._ranges.overlays,
        ):
            if item is not None:
                item.sync()
        self._layer_registry.relayout()

    def refresh_extent(self) -> None:
        """Recompute the scrollable extent unless a bulk rebuild is running.

        Anything that changes HOW FAR the timeline reaches -- a clip, a
        marker, a range overlay, what a layer draws -- has to go through
        here, or the new span is drawn but cannot be scrolled to.
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
                self.content_rebuilt.emit()

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
        return self._rows.add_clip(
            track_id, start, duration, label, color, sub_row, locked, data
        )

    def remove_clip(self, clip_id: int):
        """Remove a clip by id."""
        return self._rows.remove_clip(clip_id)

    def set_clip_label(self, clip_id: int, label: str):
        """Set the display label for a clip."""
        return self._rows.set_clip_label(clip_id, label)

    def set_clip_locked(self, clip_id: int, locked: bool):
        """Lock or unlock a clip, preventing drag/resize/rename/selection."""
        return self._rows.set_clip_locked(clip_id, locked)

    def remove_track(self, track_id: int):
        """Remove a track and all its clips."""
        return self._rows.remove_track(track_id)

    def get_clip(self, clip_id: int) -> Optional[ClipData]:
        """Return the data for a clip, or None."""
        return self._rows.clips.get(clip_id)

    def get_track(self, track_id: int) -> Optional[TrackData]:
        """Return the data for a track, or None."""
        return self._rows.get_track(track_id)

    def tracks(self) -> List[TrackData]:
        """Return a list of all track data."""
        return list(self._rows.tracks)

    @property
    def shortcut_manager(self) -> ShortcutManager:
        """The sequencer's shortcut table: a host adds or re-points a key
        (``add_shortcut``) or opens the editor (``show_editor``) through it."""
        return self._key_routing.manager

    def context_entries(self, t: float) -> list:
        """The timeline's own right-click entries at time *t*, as data
        (:meth:`TimelineView.default_context_entries`): what a host folds into
        a menu it builds itself."""
        return self._timeline.default_context_entries(t)

    def refresh(self) -> None:
        """Re-lay every item out against the current zoom, rows and editor."""
        self._timeline._refresh_all()

    def viewport_state(self) -> dict:
        """The view to put back after a rebuild.

        ``{"zoom": pixels per frame, "h_scroll": scrollbar value,
        "expanded": [track NAME, ...]}`` -- names, since a rebuild hands out
        fresh track ids (:meth:`restore_viewport_state` re-applies the first
        two; the host re-expands by name once its rows exist).
        """
        return self._navigation.viewport_state()

    def restore_viewport_state(self, state: dict) -> None:
        """Re-apply a :meth:`viewport_state`'s zoom and horizontal scroll."""
        return self._navigation.restore_viewport_state(state)

    def clips(self, track_id: Optional[int] = None) -> List[ClipData]:
        """Return clip data, optionally filtered by track."""
        return self._rows.clips_on(track_id)

    def clip_attributes(self) -> List[str]:
        """The attribute names the clips key (their ``attributes`` data), sorted
        -- the *active_attrs* an :class:`AttributeColorDialog` offers beyond the
        host's common set."""
        return self._rows.clip_attributes()

    def swap_clips(self, clip_id_a: int, clip_id_b: int) -> None:
        """Swap the timeline positions of two clips and emit ``clips_reordered``.

        Each clip adopts the other's ``start``, preserving its own
        duration.  The gap between them is maintained: the shorter clip
        gains trailing space, shifted so the layout stays contiguous.

        This is a visual-only operation; the controller should listen
        to ``clips_reordered`` to perform the actual keyframe swap in
        the backend.
        """
        return self._rows.swap_clips(clip_id_a, clip_id_b)

    def set_playhead(self, time: float):
        """Move the playhead to a specific time."""
        return self._navigation.set_playhead(time)

    # -- audio scrub --------------------------------------------------------

    def set_audio_source(self, path: str, fps: float = 24.0) -> bool:
        """Bind an audio file (typically a composite WAV) for scrub playback.

        Once set, user-driven playhead motion automatically emits short
        audio grains.  External ``set_playhead`` calls do not trigger
        audio (no signal emission), so Maya time-sync won't stutter.
        """
        return self._audio.set_source(path, fps)

    def clear_audio_source(self) -> None:
        """Drop the bound audio source and stop any in-flight scrub."""
        return self._audio.clear_source()

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
            self._rows.clear()
            self._undo.clear()
            self.clear_markers()
            if not keep_range_highlight:
                self.clear_range_highlight()
            self.clear_range_overlays()
            self._layer_registry.clear()
            self.clear_snap_guides()
            self.clear_key_scale_box()
        finally:
            self._selection_suppressed -= 1
        self._timeline._refresh_all()

    def clear_decorations(self, *, keep_range_highlight: bool = False):
        """Remove markers, overlays and what each layer shows, without touching
        tracks or clips.

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
            self._layer_registry.clear()
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
        data: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Add a marker at *time*. Returns the ``marker_id``.

        *data* is the consumer's payload (``MarkerData.data``): the widget
        never reads it, and keeps it through every edit.
        """
        return self._marker_set.add(
            time, note, color, draggable, style, line_style, opacity, data
        )

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
        return self._marker_set.remove(marker_id)

    def get_marker(self, marker_id: int) -> Optional[MarkerData]:
        """Return marker data, or None."""
        return self._marker_set.markers.get(marker_id)

    def markers(self) -> List[MarkerData]:
        """Return all markers."""
        return list(self._marker_set.markers.values())

    def clear_markers(self):
        """Remove all markers."""
        return self._marker_set.clear()

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
        return self._ranges.set_highlight(start, end, color, alpha)

    def clear_range_highlight(self):
        """Remove the range highlight from the timeline."""
        return self._ranges.clear_highlight()

    def add_range_overlay(
        self,
        start: float,
        end: float,
        color: str = "#888888",
        alpha: int = 15,
    ):
        """Add a non-interactive range overlay (e.g. a host's inactive ranges)."""
        return self._ranges.add_overlay(start, end, color, alpha)

    def clear_range_overlays(self):
        """Remove all non-interactive range overlays."""
        return self._ranges.clear_overlays()

    # -- the header and the content area ------------------------------------

    @property
    def _content_top(self) -> float:
        """Y coordinate where track rows begin -- below the ruler AND its lanes."""
        return self._layer_registry.header_height

    def content_span(self) -> Tuple[float, float]:
        """``(top, height)`` of the content area an overlay spans in scene
        units: from below the header (the ruler and every lane), every row
        and at least the visible area under the header."""
        return self._rows.content_span()

    @property
    def timeline(self) -> TimelineView:
        """The timeline view: time <-> x (``time_to_x``, ``x_to_time``,
        ``pixels_per_unit``), the strip a point is in (``hit_zone``), and the
        Qt view a layer maps and hit-tests with."""
        return self._timeline

    @property
    def range_highlight_item(self) -> Optional[RangeHighlightItem]:
        """The range highlight's scene item (:meth:`set_range_highlight`), or
        ``None``: what a lane drives the highlight's grabs through
        (``RangeHighlightItem.zone_at`` / ``begin_edge_drag``)."""
        return self._ranges.highlight

    # -- layers: a host's vocabulary on the timeline (``_layer.py``) ---------

    def add_layer(self, layer: SequencerLayer) -> None:
        """Plug *layer* into the timeline (``SequencerLayer``, ``_layer.py``).

        Its lane (``lane_height`` > 0) stacks under the ruler and the lanes
        added before it; the content area moves down to clear it, and the
        legend takes the layer's edits.  Adding a layer under a name already
        taken replaces that one in its place: its ``clear()`` runs first, so
        a host's re-init re-registers without leaving the old one's items
        behind.
        """
        return self._layer_registry.add(layer)

    def layer(self, name: str) -> SequencerLayer:
        """The layer added under *name*.

        Raises:
            KeyError: No layer is added under *name*.
        """
        return self._layer_registry.layers[name]

    def add_track_item(self, item: QtWidgets.QGraphicsItem) -> None:
        """Put a scene item under the track editor's content root: it hides
        while another editor shows, as the rows do (a layer's items too)."""
        item.setParentItem(self.editor(TrackEditor.name).content_root)

    def remove_track_item(self, item: QtWidgets.QGraphicsItem) -> None:
        """Take *item* out of the scene, safely from inside its own event
        handler (destroyed one event-loop pass later: ``ItemRetirement``)."""
        ItemRetirement.retire(item)

    def _layer_claims_press(self, scene_pos) -> bool:
        """Whether a layer keeps a press at *scene_pos* from the range
        highlight's edge for an item of its own drawn there."""
        return self._layer_registry.claims_press(scene_pos)

    def _apply_legend(self, editor: Optional[SequencerEditor] = None) -> None:
        """Register *editor*'s legend (the active one's) in place of the
        rows registered now."""
        return self._shortcut_legend.apply(editor)

    def range_highlight(self) -> Optional[tuple]:
        """Return ``(start, end)`` of the active highlight, or ``None``."""
        return self._ranges.highlight_span()

    def set_hidden_tracks(self, names: List[str]):
        """Store a list of hidden track names for the 'show hidden' menu."""
        return self._header_pane.set_hidden_tracks(names)

    def set_active_range(self, start: float, end: float):
        """Set the active time range, painted as a column tint."""
        return self._ranges.set_active(start, end)

    def clear_active_range(self):
        """Remove the active range's column tint."""
        return self._ranges.clear_active()

    # -- playhead navigation -----------------------------------------------
    def _move_playhead(self, time: float):
        """Set the playhead to *time* and emit ``playhead_moved``."""
        return self._navigation.move_playhead(time)

    def step_forward(self):
        """Advance the playhead by one step (snap_interval or 1 frame)."""
        return self._navigation.step_forward()

    def step_backward(self):
        """Move the playhead back by one step (snap_interval or 1 frame)."""
        return self._navigation.step_backward()

    def _key_times(self) -> list:
        """Return sorted unique visible key times.

        Includes clip boundaries for all clips and individual keyframe
        times from expanded sub-row clips -- or the active editor's own
        keys (:meth:`SequencerEditor.key_times`: the graph's curves).
        """
        return self._navigation.key_times()

    def go_to_next_key(self):
        """Jump the playhead to the next clip boundary."""
        return self._navigation.go_to_next_key()

    def go_to_prev_key(self):
        """Jump the playhead to the previous clip boundary."""
        return self._navigation.go_to_prev_key()

    def go_to_start(self):
        """Jump the playhead to frame 0."""
        return self._move_playhead(0.0)

    def go_to_end(self):
        """Jump the playhead to the end of the last clip."""
        return self._navigation.go_to_end()

    def add_marker_at_playhead(self):
        """Add a marker at the current playhead position."""
        return self._marker_set.add_at_playhead()

    def frame_shot(self) -> bool:
        """Zoom and scroll the timeline to frame the active shot range.

        Checks range highlight first, then active range (column tint),
        then falls back to framing all clips.

        Returns:
            Whether anything was framed: ``False`` with no shot and no clip.
        """
        return self._navigation.frame_shot()

    def frame_time_range(self, t_min: float, t_max: float, fit_values: bool = True):
        """Zoom and scroll so ``[t_min, t_max]`` fills the timeline's width.

        Parameters:
            t_min, t_max: The frames to show (a span under one frame shows one).
            fit_values: Let the active editor fit its vertical axis to what the
                range shows (:meth:`SequencerEditor.frame_values`) -- a graph
                editor's value axis; the track rows have none.
        """
        return self._navigation.frame_time_range(t_min, t_max, fit_values)

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
        if captured_undo:
            self._undo.drop_last()
        return cancelled

    # -- undo / redo -------------------------------------------------------
    def _snapshot(self) -> Dict[int, tuple]:
        """Return a snapshot of all clip positions: ``{clip_id: (start, duration)}``."""
        return self._undo.snapshot()

    def _capture_undo(self):
        """Push current clip positions onto the undo stack."""
        return self._undo.capture()

    def undo(self):
        """Revert to the previous clip state.

        Emits :signal:`undo_requested` first.  When a controller handles
        that signal and rebuilds the widget (calling :meth:`clear`), the
        internal stack is wiped and the fallback below becomes a no-op.
        """
        return self._undo.undo()

    def redo(self):
        """Re-apply a previously undone change.

        See :meth:`undo` for signal/fallback semantics.
        """
        return self._undo.redo()

    # -- snapping -----------------------------------------------------------
    @property
    def snap_interval(self) -> float:
        """Time-snap interval.  0 disables snapping."""
        return self._snapping.interval

    @snap_interval.setter
    def snap_interval(self, value: float):
        self._snapping.interval = max(0.0, value)

    # -- key alignment (guides + optional snap) ------------------------------
    @property
    def snap_guides_enabled(self) -> bool:
        """Draw a guide (and tint the drag readout) when a drag lands on a
        frame that already carries a key -- visual only."""
        return self._snapping.guides_enabled

    @snap_guides_enabled.setter
    def snap_guides_enabled(self, value: bool):
        self._snapping.set_guides_enabled(value)

    @property
    def snap_to_keys(self) -> bool:
        """Also pull a drag onto a nearby key frame, not just highlight it.

        Off by default: the guides answer "am I aligned?" without taking
        control of the drag away from the user.
        """
        return self._snapping.to_keys

    @snap_to_keys.setter
    def snap_to_keys(self, value: bool):
        self._snapping.to_keys = bool(value)

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
        return self._snapping.alignment_times(
            exclude_clip_ids, exclude_times, exclude_spans
        )

    def nearest_alignment(
        self, time: float, candidates, tolerance: Optional[float] = None
    ) -> Optional[float]:
        """Return the entry of *candidates* within *tolerance* of *time*.

        *tolerance* defaults to the pixel capture radius converted to
        frames at the current zoom, so the affordance keeps the same
        on-screen feel however far the user has zoomed in or out.
        """
        return self._snapping.nearest_alignment(time, candidates, tolerance)

    def set_snap_guides(self, times) -> None:
        """Show vertical alignment guides at *times* (empty hides them).

        The item is kept and emptied rather than destroyed: this runs on
        every mouse-move of a drag, and churning a QGraphicsItem per pixel
        of travel is pure waste.  ``clear_snap_guides`` frees it.
        """
        return self._snapping.set_guides(times)

    def clear_snap_guides(self) -> None:
        """Remove the alignment guides."""
        return self._snapping.clear_guides()

    # -- overlay visibility -------------------------------------------------
    @property
    def show_range_overlays(self) -> bool:
        return self._ranges.show_overlays

    @show_range_overlays.setter
    def show_range_overlays(self, value: bool):
        self._ranges.set_show_overlays(value)

    @property
    def show_range_highlight(self) -> bool:
        return self._ranges.show_highlight

    @show_range_highlight.setter
    def show_range_highlight(self, value: bool):
        self._ranges.set_show_highlight(value)

    @property
    def mark_flat_spans(self) -> bool:
        """Draw a curve's flat spans apart (``CurveUtils.flat_pen``), so one
        that only nearly holds reads as moving: every view's curves -- the
        clips', the rows' background and the graph's.  One setting, offered
        in each of those editors' Display options."""
        return self._mark_flat_spans

    @mark_flat_spans.setter
    def mark_flat_spans(self, value: bool) -> None:
        self._mark_flat_spans = bool(value)
        self._timeline._scene.update()  # clips, rows and canvas alike

    def add_flat_spans_option(self, editor: SequencerEditor) -> None:
        """Offer :attr:`mark_flat_spans` in *editor*'s Display options (an
        editor whose curves honour it)."""
        editor.add_option(
            "flat_spans",
            "Mark Flat Spans",
            lambda: self.mark_flat_spans,
            lambda on: setattr(self, "mark_flat_spans", on),
            "Dash the spans that hold one value: a nearly flat one stays solid",
            section="Display",
        )

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

        The consumers' "bound only" gate: a range's bound handle grabbed
        with Ctrl moves the bound and leaves the keys where they are.
        """
        return self._ctrl_at_press

    @ctrl_held_at_press.setter
    def ctrl_held_at_press(self, value: bool) -> None:
        self._ctrl_at_press = bool(value)

    def record_press_modifiers(self, modifiers) -> None:
        """Bank the modifiers a press carried, for the consumers' gates.

        Every press site calls this -- clips, keys, the range highlight, a
        layer's items and lanes -- so a gesture never inherits what the LAST
        one left behind.
        """
        self._shift_at_press = bool(modifiers & QtCore.Qt.ShiftModifier)
        self._ctrl_at_press = bool(modifiers & QtCore.Qt.ControlModifier)

    # -- shortcut overlay ---------------------------------------------------

    @property
    def shortcut_overlay(self):
        """The corner legend (:class:`ShortcutOverlay`), or ``None`` until
        it has been shown once."""
        return self._shortcut_legend.overlay

    @property
    def shortcut_overlay_visible(self) -> bool:
        """Show a legend of the drag grammar and keys in the timeline's corner.

        The reminder Substance Painter keeps in its viewport: the gesture
        group under the pointer is brightened as the mouse moves.  Built on
        first show from the shortcut manager's gestures and bindings.
        """
        return self._shortcut_legend.visible()

    @shortcut_overlay_visible.setter
    def shortcut_overlay_visible(self, value: bool) -> None:
        self.shortcut_overlay_mode = "on" if value else "off"

    #: What the corner legend does: never, always, or only while one of the
    #: modifiers it explains is held.
    SHORTCUT_OVERLAY_MODES = ("off", "on", "modifier")

    @property
    def shortcut_overlay_mode(self) -> str:
        """When to show the legend: ``"off"``, ``"on"``, or ``"modifier"``.

        ``"modifier"`` keeps it out of the way until the user reaches for
        one of the keys it explains -- Ctrl, Shift or Alt -- and takes it
        away again on release, so the legend answers the question at the
        moment it is asked instead of sitting in the corner all session.
        Assigning a bool is the two-state face of the same setting.
        """
        return self._shortcut_legend.mode

    @shortcut_overlay_mode.setter
    def shortcut_overlay_mode(self, value) -> None:
        self._shortcut_legend.set_mode(value)

    @property
    def shortcut_overlay_tracking(self) -> bool:
        """Whether the group under the pointer is worth resolving: the legend
        is up, or one modifier away from being.

        The gesture context is a mouse-MOVE answer and the legend can rise
        between two of them, so "On Modifier" keeps tracking while hidden --
        otherwise it would open on whatever page the pointer was over when
        it was last visible.
        """
        return self._shortcut_legend.tracking()

    def _set_gesture_context(self, group: Optional[str]) -> None:
        """Brighten *group* on the legend, and remember it for one that has
        yet to rise."""
        return self._shortcut_legend.set_gesture_context(group)

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

    # -- row density --------------------------------------------------------
    @property
    def row_metrics(self) -> RowMetrics:
        """Row sizes and key style: a :class:`RowMetrics` (a density preset).

        ``RowMetrics.preset("standard")`` is today's rows; ``"compact"``
        narrows every row and draws keys flat.  Setting it re-lays the scene
        rows and the header labels out together, so the two stay level.
        """
        return self._rows.metrics

    @row_metrics.setter
    def row_metrics(self, metrics: RowMetrics) -> None:
        self._rows.set_metrics(metrics)

    # -- editors: the content area's views (``_editor.py``) -----------------
    def register_editor(self, name: str, factory) -> None:
        """Offer an editor under *name*, built the first time it is asked for.

        Parameters:
            name: Registry name (:meth:`set_editor`).
            factory: A :class:`SequencerEditor` subclass, or any
                ``callable(sequencer) -> SequencerEditor``.

        Raises:
            ValueError: An editor of that name is already built.
        """
        return self._editor_registry.register(name, factory)

    def editor(self, name: str) -> SequencerEditor:
        """The editor registered under *name*, built on first use.

        Raises:
            KeyError: No editor is registered under *name*.
        """
        return self._editor_registry.get(name)

    def editor_names(self) -> List[str]:
        """The registered editors' names (``"tracks"``, ``"graph"``...)."""
        return list(self._editor_registry.editors)

    @property
    def active_editor(self) -> SequencerEditor:
        """The editor the content area shows."""
        return self.editor(self._editor_registry.active_name)

    def set_editor(self, name: str) -> None:
        """Show the editor registered under *name* in the content area.

        The ruler and its lanes, playhead, markers and every shortcut stay; the
        previous editor's items hide (their selection is not reported as a
        user's deselection), the left pane shows the new editor's page, the
        legend its gestures, and its keys answer before the shortcut table.

        Raises:
            KeyError: No editor is registered under *name*.
        """
        return self._editor_registry.show(name)

    # -- sub-row expansion --------------------------------------------------
    @property
    def sub_row_height(self) -> int:
        """Pixel height of expanded attribute sub-rows (default half track height)."""
        return self._rows.metrics.sub_row_height

    @sub_row_height.setter
    def sub_row_height(self, value: int):
        self.row_metrics = dataclasses.replace(
            self.row_metrics, sub_row_height=max(8, value)
        )

    @property
    def sub_row_provider(self):
        """Callable providing sub-row data for track expansion.

        Signature: ``(track_id, track_name) -> [(sub_name, [(start, dur, label, color), ...]), ...]``

        When set, double-clicking (or toggling) a track header calls this
        function, creates the sub-rows and their clips automatically, and
        emits ``track_expanded``.  Set to ``None`` to disable expansion.
        """
        return self._rows.sub_row_provider

    @sub_row_provider.setter
    def sub_row_provider(self, fn):
        self._rows.sub_row_provider = fn

    def expand_track(self, track_id: int, sub_row_data=None):
        """Expand *track_id* to show sub-rows beneath it.

        Parameters
        ----------
        sub_row_data : list, optional
            ``[(sub_name, [(start, dur, label, color), ...]), ...]``.
            If omitted, the ``sub_row_provider`` callback is used.
            If neither is available, does nothing.
        """
        return self._rows.expand(track_id, sub_row_data)

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
        return self._rows.set_bg_curve_preview(track_id, sub_row, preview, color)

    def collapse_track(self, track_id: int):
        """Collapse a previously expanded track, removing its sub-row clips."""
        return self._rows.collapse(track_id)

    def is_track_expanded(self, track_id: int) -> bool:
        """Return True if the track is currently expanded."""
        return track_id in self._rows.expanded

    def toggle_track_expanded(self, track_id: int):
        """Toggle expansion state.  Uses ``sub_row_provider`` when expanding."""
        return self._rows.toggle(track_id)

    def _iter_rows(self):
        """Yield ``(track, sub_name_or_None, y, height)`` for every visual row.

        Single source of the row-layout accumulation (track height +
        padding + per-sub-row height + padding) — ``_row_position``,
        ``_total_row_height``, and ``_visual_rows`` are all expressed
        through it so the metrics can't silently diverge.
        """
        return self._rows.iter_rows()

    def _row_position(self, track_id: int, sub_row: str = "") -> tuple:
        """Return ``(y, height)`` for a given track and optional sub-row."""
        return self._rows.row_position(track_id, sub_row)

    def _total_row_height(self) -> float:
        """Total pixel height of all tracks including expanded sub-rows."""
        return self._rows.total_height()

    def _visual_rows(self) -> List[tuple]:
        """Return ``[(y, height, is_sub_row, track_id), ...]`` for background painting."""
        return self._rows.visual_rows()

    # -- selection ----------------------------------------------------------
    def selected_clips(self) -> List[int]:
        """Return clip IDs for all currently selected clips."""
        return self._selection.clips()

    def selected_keys(self) -> List[dict]:
        """Selected keyframe dots grouped by clip: ``[{clip_id, times}, ...]``.

        The payload of :attr:`key_selection_changed`, :attr:`key_menu_requested`
        and the Delete shortcut alike, so every consumer resolves a key
        selection through one routine.
        """
        return self._selection.keys()

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
        return self._selection.select_keys(wanted, replace)

    # -- internal -----------------------------------------------------------
    def _on_scene_selection(self):
        return self._selection.on_scene_selection()

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
        return self._selection.show_key_menu(global_pos)

    # -- key scale handles --------------------------------------------------
    def _scalable_keys(self) -> list:
        """Selected key dots that a scale may retime.

        The selection minus the dots on a clip that refuses key edits
        (:attr:`ClipItem.keys_editable`) -- the same gate the key menu and
        Delete take, for the same reason: a marquee can sweep a locked or
        read-only row, and an edit from here would be written straight into
        the host.
        """
        return self._scale_box.scalable_keys()

    def refresh_key_scale_box(self) -> None:
        """Show or hide the Shift scale box around the current key selection.

        Held Shift plus a key selection is the request; anything else --
        Shift let go, the selection gone or collapsed onto one frame, a
        scale already in flight, a tangent drag reading that same Shift as
        its own -- takes the box away again.  Called from the timeline's key
        handling and from every key-selection change, so the box tracks both
        halves of the condition.
        """
        return self._scale_box.refresh()

    def clear_key_scale_box(self) -> None:
        """Remove the scale box, cancelling a drag it still owns.

        Cheap when there is nothing up: this runs from ``_refresh_all``, on
        every zoom, scroll and rebuild.
        """
        return self._scale_box.clear()

    def set_shift_held(self, held: bool) -> None:
        """Record whether Shift is down -- the one-key face of
        :meth:`set_modifiers_held`, for callers that track only the modifier
        the scale box answers to."""
        mods = self._modifiers_held
        self.set_modifiers_held(mods | _SHIFT_MOD if held else mods & ~_SHIFT_MOD)

    @property
    def modifiers_held(self) -> int:
        """The chord currently held over the timeline, as a plain int."""
        return self._modifiers_held

    def set_modifiers_held(self, modifiers) -> None:
        """Record the chord held over the timeline; takes a Qt flag or an int.

        The view has to tell the widget rather than the widget asking: Qt
        delivers no KeyPress for a modifier already down when the pointer
        arrives, and no KeyRelease once focus has gone.  Two things read it
        -- the Shift scale box, and the corner legend in its "On Modifier"
        mode -- so both are re-evaluated here.
        """
        value = int(getattr(modifiers, "value", modifiers))
        if value == self._modifiers_held:
            return
        self._modifiers_held = value
        self.refresh_key_scale_box()
        self._shortcut_legend.refresh()

    def _delete_selected_keys(self):
        """Delete all selected :class:`KeyframeItem` instances.

        Groups deletions by parent clip and emits one
        :attr:`keys_deleted` signal per clip -- for the clips that accept
        key edits; a locked or read-only row keeps its keys.
        """
        return self._selection.delete_selected_keys()

    # -- private names other code reads, forwarded to the part that owns them --
    # (the timeline and its items, tentacle's layer, the hosts' tests)
    _tracks = property(lambda self: self._rows.tracks)
    _clips = property(lambda self: self._rows.clips)
    _clip_items = property(lambda self: self._rows.items)
    _expanded_tracks = property(lambda self: self._rows.expanded)
    _bg_curve_previews = property(lambda self: self._rows.bg_curve_previews)
    _undo_stack = property(lambda self: self._undo.undo_stack)
    _redo_stack = property(lambda self: self._undo.redo_stack)
    _snap_interval = property(lambda self: self._snapping.interval)
    _snap_guide = property(lambda self: self._snapping.guide)
    _markers = property(lambda self: self._marker_set.markers)
    _marker_items = property(lambda self: self._marker_set.items)
    _range_highlight = property(lambda self: self._ranges.highlight)
    _range_overlays = property(lambda self: self._ranges.overlays)
    _active_range = property(lambda self: self._ranges.active)
    _active_range_color = property(lambda self: self._ranges.active_color)
    _scrub_player = property(lambda self: self._audio.player)
    _audio_fps = property(lambda self: self._audio.fps)
    _hidden_tracks = property(lambda self: self._header_pane.hidden_tracks)
    _layers = property(lambda self: self._layer_registry.layers)
    _lane_stack = property(lambda self: self._layer_registry.lane_stack)
    _legend = property(lambda self: self._shortcut_legend.rows)
    _gesture_context = property(lambda self: self._shortcut_legend.gesture_context)
    _shortcut_mgr = property(lambda self: self._key_routing.manager)
    _editors = property(lambda self: self._editor_registry.editors)
    # Raised and lowered around a rebuild, by the widget's items too.
    _selection_suppressed = property(
        lambda self: self._selection.suppressed,
        lambda self, depth: setattr(self._selection, "suppressed", depth),
    )
    _key_scale_box = property(lambda self: self._scale_box.box)
    # Raised for a tangent handle's drag (``TangentHandleItem``).
    _tangent_drag_active = property(
        lambda self: self._scale_box.tangent_drag_active,
        lambda self, on: setattr(self._scale_box, "tangent_drag_active", on),
    )
    # Written by the editor switch, read by the key matching.
    _editor_keys = property(
        lambda self: self._key_routing.editor_keys,
        lambda self, keys: setattr(self._key_routing, "editor_keys", keys),
    )
