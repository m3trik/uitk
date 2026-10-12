# !/usr/bin/python
# coding=utf-8
"""The graph editor: animation curves in value space, edited like Maya's.

A :class:`~uitk.widgets.sequencer._editor.SequencerEditor` that takes the
sequencer's content area over: the ruler, shot lane, playhead, markers and
transport stay the kernel's; below them the curves are drawn against a value
axis and edited in both directions.  The data is the host's, as plain
values -- :meth:`GraphEditor.set_outline` names the objects and their curves,
:meth:`GraphEditor.set_curve_provider` hands back ``pythontk.KeyCurve`` s --
and every edit leaves as a signal the host commits and answers with a
:meth:`GraphEditor.refresh`.  Until it does, the editor shows its own
prediction, so the widget also works on its own.

The grammar is the Graph Editor's: click / box selects (Shift toggles, Ctrl
removes, Ctrl+Shift adds); a LEFT drag on a key or a MIDDLE drag anywhere
moves the selection in time AND value (Shift locks the axis the drag starts
along; time snaps to the sequencer's snap interval, Ctrl to whole frames);
two or more selected keys sit in a scale frame -- drag an edge to scale time
or value about the opposite edge, a corner both (Alt: about the frame's
centre), the body to move; a tangent handle drags its tangent (Alt breaks
it, Shift gives every selected key the same vector); Alt+middle pans,
Alt+right zooms per axis, the wheel zooms (Ctrl: time only, Shift: value
only); A frames all, F the selected keys (none: the active shot), I keys
the displayed curves at the playhead, Delete removes the selected keys.

The collaborators live here until they earn files of their own (CODE_STANDARD
§3/§14): :class:`ValueAxis`, :class:`_GraphCanvas` (one item painting and
hit-testing every curve -- no item per key), :class:`_GraphPage` (the left
pane: a filter and the curve outline).
"""

import bisect
import dataclasses
import math
from typing import Dict, Iterable, List, Optional, Set, Tuple

from qtpy import QtCore, QtGui, QtWidgets

from uitk.widgets.sequencer._data import CurveUtils, MenuUtils
from uitk.widgets.sequencer._drag_tooltip import FrameTooltip
from uitk.widgets.sequencer._draggable import HeldGeometryMixin
from uitk.widgets.sequencer._editor import SequencerEditor

KeyRef = Tuple[str, float]  # (curve id, key time): stable across a refresh
_EPS = 1e-3

_ALT = QtCore.Qt.AltModifier
_CTRL = QtCore.Qt.ControlModifier
_SHIFT = QtCore.Qt.ShiftModifier


class ValueAxis:
    """Value <-> pixel row of the graph's content area.

    ``scale`` is pixels per value unit; ``top`` the value at the area's top
    edge.  Pan, zoom about a row, fit and the grid step all derive from those
    two numbers.
    """

    MIN_SCALE = 1e-6
    MAX_SCALE = 1e7

    def __init__(self, scale: float = 20.0, top: float = 10.0):
        self.scale = scale
        self.top = top

    def to_y(self, value: float, top_px: float) -> float:
        return top_px + (self.top - value) * self.scale

    def to_value(self, y: float, top_px: float) -> float:
        return self.top - (y - top_px) / self.scale

    def pan(self, dy_px: float) -> None:
        """Move the view *dy_px* pixels: the content follows the pointer."""
        self.top += dy_px / self.scale

    def zoom(self, factor: float, anchor_y: float, top_px: float) -> None:
        """Scale by *factor*, keeping the value under *anchor_y* in place."""
        anchor = self.to_value(anchor_y, top_px)
        self.scale = min(max(self.scale * factor, self.MIN_SCALE), self.MAX_SCALE)
        self.top = anchor + (anchor_y - top_px) / self.scale

    def fit(self, lo: float, hi: float, height_px: float, margin: float = 0.1) -> None:
        """Show ``[lo, hi]`` across *height_px*, *margin* (a fraction) each side."""
        span = hi - lo
        if span < 1e-9:  # a flat curve: a unit of room around it
            span = max(abs(lo) * 0.2, 1.0)
            lo, hi = lo - span / 2, hi + span / 2
        usable = max(height_px * (1.0 - 2.0 * margin), 1.0)
        self.scale = min(max(usable / span, self.MIN_SCALE), self.MAX_SCALE)
        self.top = hi + (height_px - usable) / 2.0 / self.scale

    def step(self, min_px: float = 36.0) -> float:
        """A 1-2-5 grid step at least *min_px* pixels apart."""
        raw = min_px / self.scale
        base = 10 ** math.floor(math.log10(raw))
        return next(m * base for m in (1, 2, 5, 10) if m * base >= raw)


class GraphEditor(SequencerEditor):
    """Curves in value space over the sequencer's time axis (module docstring).

    Signals carry edits in curve units; ``curve_id`` is the host's own name
    for a curve (a node, a data path) and key times are the times BEFORE
    the edit:

    * ``keys_edited([(curve_id, [(time, dt, dv), ...]), ...])`` -- a move
      or a scale.
    * ``tangents_edited([(curve_id, [(time, side, dt, dv, broken), ...]), ...])``
      -- the handle VECTOR from its key, per edited side.
    * ``keys_deleted([(curve_id, [time, ...]), ...])``.
    * ``keys_inserted([(curve_id, time), ...])`` -- keep the curve's shape.
    * ``tangent_type_requested(type_id, [(curve_id, [time, ...]), ...])``.
    * ``tangents_broken(broken, [(curve_id, [time, ...]), ...])``.
    * ``weighted_requested(weighted, [curve_id, ...])``.
    * ``infinity_requested(side, mode, [curve_id, ...])`` -- side ``"pre"``
      or ``"post"``; mode a ``pythontk.KeyCurve`` infinity mode.
    * ``key_selection_changed([(curve_id, [time, ...]), ...])``.
    """

    name = "graph"
    label = "Graph"
    gestures = (
        (
            "Keys",
            "Click / Drag box",
            "Select (Shift toggle, Ctrl remove, Ctrl+Shift add)",
        ),
        ("Keys", "Drag a key / Middle-drag", "Move in time and value"),
        ("Keys", "Shift+Drag", "Move along the axis the drag starts on"),
        ("Keys", "Ctrl+Drag", "Snap time to whole frames"),
        ("Keys", "Drag the frame's edge", "Scale time or value about the far edge"),
        ("Keys", "Drag a corner", "Scale both (Alt: about the centre)"),
        ("Keys", "Double-click a curve", "Insert a key there"),
        ("Tangents", "Drag a handle", "Reshape (a unified key's other side follows)"),
        ("Tangents", "Alt+Drag", "Break the tangent"),
        ("Tangents", "Shift+Drag", "Give every selected key this tangent"),
        ("View", "Alt+Middle-drag", "Pan"),
        ("View", "Alt+Right-drag", "Zoom each axis (Shift: one)"),
        ("View", "Wheel", "Zoom (Ctrl: time only, Shift: value only)"),
        ("View", "A / F", "Frame all / the selection, else the shot"),
        ("View", "I / Delete", "Key the curves at the playhead / delete keys"),
    )

    keys_edited = QtCore.Signal(list)
    tangents_edited = QtCore.Signal(list)
    keys_deleted = QtCore.Signal(list)
    keys_inserted = QtCore.Signal(list)
    tangent_type_requested = QtCore.Signal(str, list)
    tangents_broken = QtCore.Signal(bool, list)
    weighted_requested = QtCore.Signal(bool, list)
    infinity_requested = QtCore.Signal(str, str, list)
    key_selection_changed = QtCore.Signal(list)
    #: ``(menu, [(curve_id, [time, ...]), ...])`` as the right-click menu
    #: builds: the host adds its rows for the key selection (the track
    #: editor's ``key_menu_requested``, curve-keyed).
    key_menu_requested = QtCore.Signal(object, list)
    #: Live Update, mid-drag: ``[(curve_id, KeyCurve), ...]`` -- the curves as
    #: the drag shapes them, for a host to show in its scene before release.
    curves_previewed = QtCore.Signal(list)
    #: A live drag ended with no edit (Escape, or released where it began).
    preview_cancelled = QtCore.Signal()

    #: Pixels within which a key, handle or curve is hit.
    HIT_PX = 6.0
    #: Screen length of an unweighted tangent handle (only its angle is data).
    HANDLE_PX = 40.0
    #: Movement before a press becomes a drag.
    DRAG_PX = 4

    #: ``pythontk.KeyCurve`` infinity modes, in menu order, with labels.
    INFINITY_MODES = (
        ("constant", "Constant"),
        ("linear", "Linear"),
        ("cycle", "Cycle"),
        ("cycle_offset", "Cycle with Offset"),
        ("oscillate", "Oscillate"),
    )

    def __init__(self, sequencer):
        super().__init__(sequencer)
        self.axis = ValueAxis()
        self._outline: List[dict] = []
        self._provider = None
        self._curves: Dict[str, object] = {}  # curve id -> KeyCurve (host truth)
        self._preview: Dict[str, object] = {}  # curve id -> KeyCurve mid-drag
        self._colors: Dict[str, QtGui.QColor] = {}
        self._shown: List[str] = []  # displayed curve ids, outline order
        self._sel: Set[KeyRef] = set()
        #: Mid-drag, the dragged keys at their PREVIEW times (drawn selected).
        self._preview_sel: Set[KeyRef] = set()
        self._tangent_types: List[Tuple[str, str]] = []
        self._normalized = False
        self._show_infinity = True
        self._auto_load = True
        self._live = False
        self._live_sent = False
        self._dim_outside = True
        self._focus_range: Optional[Tuple[float, float]] = None
        self._readout = FrameTooltip()
        #: Whether the host's curves have a weighted / non-weighted mode (Maya
        #: does; a Blender handle always carries its length): off drops the
        #: menu's weighting rows.
        self.offers_weighting = True
        self._drag: Optional[dict] = None
        #: A context-menu event belongs to the right-button drag that began
        #: (Alt+right zoom): Windows sends it on the release, after the drag.
        self._menu_spent = False
        #: ``id(curve) -> [curve, times, normalization]`` (:meth:`_times`).
        self._memo: Dict[int, list] = {}
        self._framed_once = False
        # Owned, so a switch's pending first framing dies with the editor.
        self._first_frame_timer = QtCore.QTimer(self)
        self._first_frame_timer.setSingleShot(True)
        self._first_frame_timer.timeout.connect(self._first_frame)
        self._canvas = _GraphCanvas(self)
        self._canvas.setParentItem(self.content_root)
        for section, key, label, attr, tip in (
            (
                "Display",
                "normalize",
                "Normalize",
                "normalized",
                "Each curve drawn in [-1, 1]",
            ),
            (
                "Display",
                "infinity",
                "Show Infinity",
                "show_infinity",
                "The curves past their ends, dashed",
            ),
            (
                "Display",
                "dim",
                "Dim Outside Shots",
                "dim_outside",
                "Veil the time outside the shots on screen (the scope)",
            ),
            (
                "Behavior",
                "auto_load",
                "Auto Load Selected",
                "auto_load",
                "Show the selected objects' curves (off: the display stays pinned)",
            ),
            (
                "Behavior",
                "live",
                "Live Update",
                "live",
                "Show a drag in the scene as it happens, before the release commits it",
            ),
        ):
            self.add_option(
                key,
                label,
                lambda a=attr: getattr(self, a),
                lambda on, a=attr: setattr(self, a, on),
                tip,
                section=section,
            )
        sequencer.add_flat_spans_option(self)
        self._page = _GraphPage(self)

    # -- the editor seam --------------------------------------------------------

    def header_widget(self):
        return self._page

    def activate(self) -> None:
        super().activate()
        # The value axis replaces the rows: no vertical scroll left over.
        self.sequencer._timeline.verticalScrollBar().setValue(0)
        if not self._framed_once and self._shown:
            self._first_frame_timer.start(0)

    def deactivate(self) -> None:
        self.cancel_drag()  # a drag the graph no longer shows must not linger
        super().deactivate()

    def _first_frame(self) -> None:
        # The active shot, as F frames it: never every key of the scene.  Once
        # only: a later switch back keeps whatever the user framed since.
        if self.is_active and not self._framed_once:
            self._framed_once = True
            self.frame_selection()

    def key_bindings(self):
        return [
            ("A", self.frame_all, "Frame all curves"),
            ("F", self.frame_selection, "Frame the selected keys, else the shot"),
            ("Delete", self.delete_selection, "Delete the selected keys"),
            ("I", self.insert_keys_at_playhead, "Key the curves at the playhead"),
            ("Ctrl+A", self.select_all, "Select every key"),
            ("Escape", self.cancel_drag, "Cancel the drag"),
        ]

    def content_height(self) -> float:
        view = self.sequencer._timeline
        return max(view.viewport().height() - self.sequencer._content_top, 1.0)

    def relayout(self) -> None:
        self._canvas.sync()

    def draw_background(self, painter, rect) -> bool:
        # The canvas paints the whole content area opaque: the track rows
        # (and their full-range curves) under it would be drawn for nothing.
        return True

    def time_bounds(self) -> Optional[Tuple[float, float]]:
        """The displayed curves' key extent: the timeline scrolls to it."""
        spans = [
            (curve.keys[0].time, curve.keys[-1].time)
            for curve in map(self._curves.get, self._shown)
            if curve is not None and len(curve)
        ]
        if not spans:
            return None
        return min(a for a, _b in spans), max(b for _a, b in spans)

    def key_times(self) -> List[float]:
        """The displayed curves' keys (claimed samples aside): what the
        transport's next / previous key steps through here."""
        return sorted({k.time for _cid, k in self._shown_keys()})

    def _shown_keys(self, hidden: bool = False):
        """``(curve_id, key)`` for the displayed curves' keys -- the claimed
        samples (hidden keys) too only with *hidden*."""
        for cid in self._shown:
            curve = self._curves.get(cid)
            for k in curve.keys if curve is not None else ():
                if hidden or not k.hidden:
                    yield cid, k

    def frame_values(self) -> None:
        """Fit the value axis to what the framed time range shows."""
        t0, t1 = self._visible_time_range()
        self._fit_values(self._value_range(self._shown, t0, t1))

    # -- data in (plain values) -------------------------------------------------

    def set_outline(self, entries: List[dict]) -> None:
        """The objects and their curves, for the left pane and the display.

        Parameters:
            entries: ``[{"id", "label", "children": [{"curve_id", "label",
                "color"}, ...]}, ...]`` -- one per object, in display order.
        """
        self._outline = list(entries or ())
        for entry in self._outline:
            for child in entry.get("children", ()):
                if child.get("color"):
                    # Parsed here: a colour Qt can't take raises at this call,
                    # not later inside a paint (where it would fault).
                    self._colors[child["curve_id"]] = QtGui.QColor(child["color"])
        self._page.rebuild()
        self._update_shown()

    def set_curve_provider(self, provider) -> None:
        """``callable(curve_ids) -> [pythontk.KeyCurve, ...]`` -- the host's reader."""
        self._provider = provider
        self.refresh()

    def set_tangent_types(self, types: Iterable[Tuple[str, str]]) -> None:
        """The host's tangent types as ``[(type_id, label), ...]`` (menu order)."""
        self._tangent_types = list(types)

    def refresh(self, curve_ids: Optional[Iterable[str]] = None) -> None:
        """Re-read curves from the provider (every shown one, or *curve_ids*)."""
        ids = list(self._shown) if curve_ids is None else list(curve_ids)
        self._memo.clear()  # a host may hand back the same object, changed
        if curve_ids is None:
            self._curves = {k: v for k, v in self._curves.items() if k in self._shown}
        if self._provider is not None and ids:
            got = set()
            for curve in self._provider(ids) or ():
                self._curves[curve.curve_id] = curve
                if curve.color and curve.curve_id not in self._colors:
                    self._colors[curve.curve_id] = QtGui.QColor(curve.color)
                got.add(curve.curve_id)
            for cid in set(ids) - got:  # the host no longer has it
                self._curves.pop(cid, None)
        self._preview.clear()
        self._prune_selection()
        self._repaint()

    def invalidate(self, curve_ids: Iterable[str]) -> None:
        """Curves the host changed: the shown ones re-read now, the rest
        dropped from the cache (read again when next shown)."""
        ids = set(curve_ids)
        shown = [cid for cid in self._shown if cid in ids]
        for cid in ids.difference(shown):
            self._curves.pop(cid, None)
        if shown:
            self.refresh(shown)

    # -- reading ----------------------------------------------------------------

    @property
    def normalized(self) -> bool:
        """Each curve drawn in [-1, 1] (edits still land in its own units)."""
        return self._normalized

    @normalized.setter
    def normalized(self, on: bool) -> None:
        self._normalized = bool(on)
        self.frame_values()  # the values' scale changed; the time framed stays

    @property
    def show_infinity(self) -> bool:
        """The curves drawn dashed past their first and last keys."""
        return self._show_infinity

    @show_infinity.setter
    def show_infinity(self, on: bool) -> None:
        self._show_infinity = bool(on)
        self._repaint()

    @property
    def auto_load(self) -> bool:
        """Follow the host's object selection (Maya's Auto Load Selected
        Objects); off pins the display.  The host reads it before
        :meth:`focus_objects`."""
        return self._auto_load

    @auto_load.setter
    def auto_load(self, on: bool) -> None:
        self._auto_load = bool(on)

    @property
    def live(self) -> bool:
        """Raise :attr:`curves_previewed` while a drag shapes the curves, so
        the host shows it in its scene before the release commits it."""
        return self._live

    @live.setter
    def live(self, on: bool) -> None:
        self._live = bool(on)

    @property
    def dim_outside(self) -> bool:
        """Veil the time outside :attr:`focus_range` (the shots on screen)."""
        return self._dim_outside

    @dim_outside.setter
    def dim_outside(self, on: bool) -> None:
        self._dim_outside = bool(on)
        self._repaint()

    @property
    def focus_range(self) -> Optional[Tuple[float, float]]:
        """``(t0, t1)`` the host is working in -- the shots its scope shows --
        or None; what lies outside is veiled while :attr:`dim_outside`."""
        return self._focus_range

    @focus_range.setter
    def focus_range(self, span) -> None:
        self._focus_range = None if span is None else (float(span[0]), float(span[1]))
        self._repaint()

    def displayed_curve_ids(self) -> List[str]:
        return list(self._shown)

    def curve(self, curve_id: str):
        """The curve as drawn: the drag's preview, else the host's."""
        return self._preview.get(curve_id) or self._curves.get(curve_id)

    def _drawn_selection(self) -> Dict[str, List[float]]:
        """``{curve_id: [time, ...]}`` of the keys drawn selected (mid-drag:
        where the preview put them)."""
        previewed = set(self._preview) if self._preview_sel else set()
        by: Dict[str, List[float]] = {}
        for cid, t in self._sel:
            if cid not in previewed:
                by.setdefault(cid, []).append(t)
        for cid, t in self._preview_sel or ():
            if cid in previewed:
                by.setdefault(cid, []).append(t)
        return by

    def selected_keys(self) -> List[Tuple[str, List[float]]]:
        """``[(curve_id, [time, ...]), ...]`` in display order."""
        by: Dict[str, List[float]] = {}
        for cid, t in sorted(self._sel):
            by.setdefault(cid, []).append(t)
        return [(cid, by[cid]) for cid in self._shown if cid in by]

    def select_keys(self, refs: Iterable[KeyRef], mode: str = "replace") -> None:
        """Select keys by ``(curve_id, time)``; *mode* replace / add / remove / toggle."""
        refs = {(cid, float(t)) for cid, t in refs}
        if mode == "replace":
            self._sel = refs
        elif mode == "add":
            self._sel |= refs
        elif mode == "remove":
            self._sel -= refs
        else:
            self._sel ^= refs
        self._prune_selection()
        self._selection_changed()

    def focus_objects(self, object_ids: Iterable[str]) -> bool:
        """Show the curves of *object_ids* (their outline rows selected).

        What a host calls to follow its own selection, as Maya's Graph Editor
        loads the selected objects.  Ids not in the outline are ignored;
        returns False (the display unchanged) when none is.  When the curves
        on display already belong to exactly those objects the display is
        kept: a curve isolated within them stays isolated (a key click
        re-announces its object's selection).
        """
        owners = {
            child["curve_id"]: entry["id"]
            for entry in self._outline
            for child in entry.get("children", ())
        }
        listed = set(object_ids) & set(owners.values())
        if not listed:
            return False
        if {owners.get(cid) for cid in self._shown} == listed:
            return True
        return self._page.select_objects(listed)

    def select_all(self) -> None:
        """Select every key of the displayed curves."""
        self.select_keys((cid, k.time) for cid, k in self._shown_keys())

    # -- verbs ------------------------------------------------------------------

    def frame_all(self) -> None:
        """Frame every displayed curve's keys, in time and value."""
        self._framed_once = True
        times = [k.time for _cid, k in self._shown_keys(hidden=True)]
        if not times:
            return
        lo, hi = min(times), max(times)
        self.sequencer.frame_time_range(lo, hi, fit_values=False)
        self._fit_values(self._value_range(self._shown, lo, hi))

    def frame_selection(self) -> None:
        """Frame the selected keys; with none, the active shot -- its time,
        and the values the curves take there (``SequencerWidget.frame_shot``,
        what F does in the track view) -- or, with no shot, every curve
        (:meth:`frame_all`)."""
        if not self._sel:
            self._framed_once = True
            if not self.sequencer.frame_shot():
                self.frame_all()
            return
        times = [t for _cid, t in self._sel]
        values = [
            self._display_value(cid, k.value)
            for cid, t in self._sel
            for k in [self._key(cid, t)]
            if k is not None
        ]
        self.sequencer.frame_time_range(min(times), max(times), fit_values=False)
        if values:
            self._fit_values((min(values), max(values)))

    def delete_selection(self) -> None:
        """Delete the selected keys (:attr:`keys_deleted`), shown at once."""
        groups = self.selected_keys()
        if not groups:
            return
        for cid, times in groups:
            c = self._curves.get(cid)
            if c is not None:
                gone = {self._index(c, t) for t in times}
                keys = [k for i, k in enumerate(c.keys) if i not in gone]
                self._curves[cid] = dataclasses.replace(c, keys=keys)
        self._sel.clear()
        self._selection_changed()
        self.keys_deleted.emit(groups)

    def insert_keys_at_playhead(self) -> None:
        """Key the selection's curves (every displayed one when none) at the
        playhead, keeping each curve's shape."""
        t = float(self.sequencer._timeline._scene.playhead.time)
        ids = [cid for cid in self._target_curves() if cid in self._curves]
        if ids:
            self.keys_inserted.emit([(cid, t) for cid in ids])

    def cancel_drag(self) -> bool:
        if self._drag is None:
            return False
        self._drag = None
        self._preview.clear()
        self._preview_sel = set()
        self._readout.hide()
        self._end_live(committed=False)
        self._repaint()
        return True

    def _emit_live(self) -> None:
        """Live Update: hand the host the curves as the drag now shapes them."""
        if self._live and self._preview:
            self._live_sent = True
            self.curves_previewed.emit(list(self._preview.items()))

    def _end_live(self, committed: bool) -> None:
        """A live drag is over: the commit takes it from here, or the host
        puts its scene back (:attr:`preview_cancelled`)."""
        if self._live_sent and not committed:
            self.preview_cancelled.emit()
        self._live_sent = False

    def request_tangent_type(self, type_id: str) -> None:
        groups = self.selected_keys()
        if groups:
            self.tangent_type_requested.emit(type_id, groups)

    def request_broken(self, broken: bool) -> None:
        groups = self.selected_keys()
        if groups:
            self.tangents_broken.emit(bool(broken), groups)

    def _target_curves(self) -> List[str]:
        """The selection's curves, else every displayed one."""
        return sorted({cid for cid, _t in self._sel}) or list(self._shown)

    def request_weighted(self, weighted: bool) -> None:
        ids = self._target_curves()
        if ids:
            self.weighted_requested.emit(bool(weighted), ids)

    def request_infinity(self, side: str, mode: str) -> None:
        ids = self._target_curves()
        if ids:
            self.infinity_requested.emit(side, mode, ids)

    # -- the content area's mouse (view coordinates) -----------------------------

    def mouse_press(self, event) -> bool:
        pos = self.sequencer._timeline.mapToScene(event.pos())
        button, mods = event.button(), event.modifiers()
        drag = self._drag
        if drag is not None:
            if event.buttons() & drag["button"]:
                return True  # another button mid-drag: the drag goes on
            self.cancel_drag()  # its release went elsewhere (a popup took it)
        self._menu_spent = False
        if button == QtCore.Qt.RightButton:
            if mods & _ALT:
                self._drag = self._start("zoom", event, pos)
                self._menu_spent = True
                return True
            return False  # the context menu
        if button == QtCore.Qt.MiddleButton:
            if mods & _ALT:
                self._drag = self._start("pan", event, pos)
            elif self._sel:
                self._drag = self._start("move", event, pos, anchor=self._anchor_key())
            return True
        if button != QtCore.Qt.LeftButton:
            return False
        if mods & _CTRL and mods & _ALT:
            self._drag = self._start("boxzoom", event, pos)  # Maya's region zoom
            return True
        handle = self._handle_at(pos)
        if handle is not None:
            self._drag = self._start("tangent", event, pos, handle=handle)
            return True
        ref = self._key_at(pos)
        if ref is not None:
            was_selected = ref in self._sel
            if mods & _CTRL and mods & _SHIFT:
                self.select_keys([ref], "add")
            elif mods & (_SHIFT | _CTRL) and was_selected:
                pass  # a click toggles / removes on release; a drag moves it
            elif mods & _SHIFT:
                self.select_keys([ref], "add")
            elif mods & _CTRL:
                return True  # removing an unselected key: nothing to do
            elif not was_selected:
                self.select_keys([ref], "replace")
            if ref in self._sel:
                self._drag = self._start(
                    "move",
                    event,
                    pos,
                    anchor=ref,
                    clicked=ref,
                    was_selected=was_selected,
                )
            return True
        zone = self._box_zone_at(pos)
        if zone == "body" and mods & (_SHIFT | _CTRL):
            zone = None  # a selection box may start inside the frame
        if zone == "body":
            self._drag = self._start("move", event, pos, anchor=self._anchor_key())
            return True
        if zone is not None:
            self._drag = self._start("scale", event, pos, zone=zone)
            return True
        # A box starts anywhere -- on a curve too; a CLICK on one selects
        # its keys (on release, so a drag from it still boxes).
        self._drag = self._start("marquee", event, pos, curve=self._curve_at(pos))
        return True

    def mouse_move(self, event) -> bool:
        drag = self._drag
        view = self.sequencer._timeline
        pos = view.mapToScene(event.pos())
        if drag is None:
            self._sync_cursor(pos)
            return False  # a hover: the kernel keeps its own bookkeeping too
        if not event.buttons() & drag["button"]:
            # Its release went elsewhere (a popup took the grab): a hover must
            # not go on moving keys.
            self.cancel_drag()
            return True
        if not drag["live"]:
            if (event.pos() - drag["press_px"]).manhattanLength() < self.DRAG_PX:
                return True
            drag["live"] = True
        kind = drag["kind"]
        if kind == "pan":
            delta = event.pos() - drag["last_px"]
            drag["last_px"] = event.pos()
            dx, dy = delta.x(), delta.y()
            if drag["mods"] & _SHIFT:  # Alt+Shift+MMB: Maya's one-axis track
                moved = event.pos() - drag["press_px"]
                if drag["axis"] is None and moved.manhattanLength() > self.DRAG_PX:
                    drag["axis"] = "t" if abs(moved.x()) >= abs(moved.y()) else "v"
                if drag["axis"] != "t":
                    dx = 0
                if drag["axis"] != "v":
                    dy = 0
            bar = view.horizontalScrollBar()
            bar.setValue(bar.value() - dx)
            self.axis.pan(dy)
        elif kind == "zoom":
            self._drag_zoom(event, drag)
        elif kind in ("marquee", "boxzoom"):
            drag["current"] = pos
        elif kind == "move":
            self._drag_move(event, pos, drag)
        elif kind == "scale":
            self._drag_scale(event, pos, drag)
        elif kind == "tangent":
            self._drag_tangent(event, pos, drag)
        if kind in ("move", "scale", "tangent"):
            self._show_readout(drag, pos)
            self._emit_live()
        self._repaint()
        return True

    def _show_readout(self, drag, pos) -> None:
        """The drag's frame / value / scale beside the cursor, as the track
        rows' drags show theirs (``FrameTooltip``)."""
        label = drag.get("readout")
        if not label:
            return
        if self._readout.is_visible():
            self._readout.update(pos, label=label)
        else:
            self._readout.show(self.sequencer._timeline._scene, pos, label=label)

    def mouse_release(self, event) -> bool:
        if self._drag is not None and event.button() != self._drag["button"]:
            return True  # another button's release: the drag goes on
        drag, self._drag = self._drag, None
        self._preview_sel = set()
        self._readout.hide()
        if drag is None:
            return True
        kind = drag["kind"]
        mods = event.modifiers()
        if kind == "marquee":
            if drag["live"]:
                self._finish_marquee(drag, mods)
            elif drag.get("curve") is not None:
                self._click_curve(drag["curve"][0], drag["mods"])
            elif not mods & (_SHIFT | _CTRL):
                self.select_keys([], "replace")
        elif kind == "move" and not drag["live"] and drag.get("clicked"):
            # A click -- no drag -- on a key: what the modifiers say.
            ref, press = drag["clicked"], drag["mods"]
            if not press & (_SHIFT | _CTRL | _ALT):
                self.select_keys([ref], "replace")  # that key alone
            elif drag.get("was_selected") and not (press & _SHIFT and press & _CTRL):
                self.select_keys([ref], "toggle" if press & _SHIFT else "remove")
        elif kind in ("move", "scale"):
            self._preview.clear()
            self._end_live(committed=bool(drag.get("edits")))
            if drag.get("edits"):
                self._emit_moves(drag["edits"])
        elif kind == "tangent" and drag["live"]:
            self._preview.clear()
            self._end_live(committed=bool(drag.get("rows")))
            if drag.get("rows"):
                self._emit_tangents(drag["rows"])
        elif kind == "boxzoom" and drag["live"]:
            self._zoom_to_box(drag["press"], drag["current"])
        self._repaint()
        return True

    def _zoom_to_box(self, a, b) -> None:
        """Frame the time x value region between scene points *a* and *b* --
        dragged right to left, zoom OUT by the box's share of the view
        (Maya's region zoom both ways)."""
        top = self.sequencer._content_top
        t0, t1 = sorted((self._x_to_t(a.x()), self._x_to_t(b.x())))
        v0, v1 = sorted(
            (self.axis.to_value(a.y(), top), self.axis.to_value(b.y(), top))
        )
        if t1 - t0 <= 1e-9 or v1 - v0 <= 1e-12:
            return
        if b.x() >= a.x():
            self.sequencer.frame_time_range(t0, t1, fit_values=False)
            self._fit_values((v0, v1))
            return
        vt0, vt1 = self._visible_time_range()
        area = self.content_height()
        vv_hi = self.axis.to_value(top, top)
        vv_lo = self.axis.to_value(top + area, top)
        kt = (t1 - t0) / max(vt1 - vt0, 1e-9)  # the box's share of the view
        kv = (v1 - v0) / max(vv_hi - vv_lo, 1e-12)
        ct, cv = (t0 + t1) / 2.0, (v0 + v1) / 2.0
        half_t = (vt1 - vt0) / max(kt, 1e-3) / 2.0
        half_v = (vv_hi - vv_lo) / max(kv, 1e-3) / 2.0
        self.sequencer.frame_time_range(ct - half_t, ct + half_t, fit_values=False)
        self._fit_values((cv - half_v, cv + half_v))

    def _curve_refs(self, cid: str) -> List[KeyRef]:
        """Every drawn key of curve *cid* (its claimed samples aside)."""
        curve = self._curves.get(cid)
        return [(cid, k.time) for k in curve.keys if not k.hidden] if curve else []

    def select_curve_keys(self, curve_ids: Iterable[str]) -> None:
        """Select every drawn key of *curve_ids*, the rest deselected -- a
        click on a curve, for several (the outline menu's Select Keys)."""
        self.select_keys([ref for cid in curve_ids for ref in self._curve_refs(cid)])

    def _click_curve(self, cid: str, mods) -> None:
        """A click on a curve between its keys: Maya's curve selection --
        every (drawn) key of it, under the key click's modifiers (Shift
        toggles the curve, Ctrl removes it, Ctrl+Shift adds it)."""
        refs = self._curve_refs(cid)
        if mods & _CTRL and mods & _SHIFT:
            mode = "add"
        elif mods & _CTRL:
            mode = "remove"
        elif mods & _SHIFT:
            mode = "remove" if refs and set(refs) <= self._sel else "add"
        else:
            mode = "replace"
        self.select_keys(refs, mode)

    def mouse_double_click(self, event) -> bool:
        pos = self.sequencer._timeline.mapToScene(event.pos())
        if event.button() != QtCore.Qt.LeftButton or self._key_at(pos) is not None:
            return True
        hit = self._curve_at(pos)
        if hit is not None:
            self.keys_inserted.emit([hit])
        return True

    def wheel(self, event) -> bool:
        view = self.sequencer._timeline
        steps = event.angleDelta().y() / 120.0
        if not steps:
            return True
        factor = 1.15**steps
        mods = event.modifiers()
        pos = (
            event.position()
            if hasattr(event, "position")
            else QtCore.QPointF(event.pos())
        )
        if not mods & _SHIFT:
            view.zoom_at(factor, pos.x())
        if not mods & _CTRL:
            anchor = view.mapToScene(pos.toPoint()).y()
            self.axis.zoom(factor, anchor, self.sequencer._content_top)
            self._repaint()
        return True

    def context_menu(self, event) -> bool:
        if self._drag is not None or self._menu_spent:
            # Over a running drag (a press-trigger platform's right press), or
            # the release-triggered menu of an Alt+right zoom just ended.
            self._menu_spent = False
            return True
        self.build_context_menu().exec_(event.globalPos())
        return True

    def build_context_menu(self) -> QtWidgets.QMenu:
        """The right-click menu: tangents, weighting, infinity, keys, view."""
        menu = MenuUtils._styled_menu()
        has_sel = bool(self._sel)
        if self._tangent_types:
            sub = menu.addMenu("Tangents")
            sub.setEnabled(has_sel)
            for type_id, label in self._tangent_types:
                sub.addAction(label, lambda t=type_id: self.request_tangent_type(t))
        for title, broken in (("Break Tangents", True), ("Unify Tangents", False)):
            act = menu.addAction(title, lambda b=broken: self.request_broken(b))
            act.setEnabled(has_sel)
        if self.offers_weighting:
            menu.addSeparator()
            menu.addAction("Weighted Tangents", lambda: self.request_weighted(True))
            menu.addAction(
                "Non-Weighted Tangents", lambda: self.request_weighted(False)
            )
        menu.addSeparator()
        for side, title in (("pre", "Pre Infinity"), ("post", "Post Infinity")):
            sub = menu.addMenu(title)
            for mode, label in self.INFINITY_MODES:
                sub.addAction(label, lambda s=side, m=mode: self.request_infinity(s, m))
        menu.addSeparator()
        act = menu.addAction("Delete Keys", self.delete_selection)
        act.setEnabled(has_sel)
        menu.addAction("Key at Playhead", self.insert_keys_at_playhead)
        # The host's rows for the selection, above the view rows.
        self.key_menu_requested.emit(menu, self.selected_keys())
        menu.addSeparator()
        menu.addAction("Frame Shot", self.sequencer.frame_shot)
        menu.addAction("Frame Selection", self.frame_selection).setEnabled(has_sel)
        menu.addAction("Frame All", self.frame_all)
        for row in self.options():  # the Options menu's rows, one source
            act = menu.addAction(row["label"])
            act.setCheckable(True)
            act.setChecked(bool(row["get"]()))
            act.toggled.connect(lambda on, r=row: r["set"](on))
        return menu

    def gesture_group_at(self, viewport_pos) -> Optional[str]:
        pos = self.sequencer._timeline.mapToScene(viewport_pos)
        if self._handle_at(pos) is not None:
            return "Tangents"
        if self._key_at(pos) is not None or self._box_zone_at(pos) is not None:
            return "Keys"
        return "View"

    # -- drags ------------------------------------------------------------------

    def _start(self, kind: str, event, pos, **extra) -> dict:
        drag = {
            "kind": kind,
            "button": event.button(),  # only its release ends the drag
            "press_px": event.pos(),
            "last_px": event.pos(),
            "press": pos,
            "current": pos,
            "mods": event.modifiers(),
            "live": kind in ("pan", "zoom"),
            "axis": None,
            "edits": [],
        }
        drag.update(extra)
        if kind in ("move", "scale"):
            drag["origin"] = {
                ref: (k.time, self._display_value(ref[0], k.value))
                for ref in self._sel
                for k in [self._key(*ref)]
                if k is not None
            }
        if kind == "scale":
            drag["box"] = self._selection_box_units()
        return drag

    def _drag_zoom(self, event, drag) -> None:
        delta = event.pos() - drag["last_px"]
        drag["last_px"] = event.pos()
        dx, dy = delta.x(), delta.y()
        if drag["mods"] & _SHIFT:
            if drag["axis"] is None and (abs(dx) + abs(dy)) > 2:
                drag["axis"] = "t" if abs(dx) >= abs(dy) else "v"
            if drag["axis"] == "t":
                dy = 0
            elif drag["axis"] == "v":
                dx = 0
        if dx:
            self.sequencer._timeline.zoom_at(math.exp(dx * 0.01), drag["press_px"].x())
        if dy:
            self.axis.zoom(
                math.exp(-dy * 0.01), drag["press"].y(), self.sequencer._content_top
            )

    def _axis_lock(
        self, drag, dx_px: float, dy_px: float, mods=None
    ) -> Tuple[bool, bool]:
        """``(time moves, value moves)`` for a drag that may be axis-locked.

        Shift held at the press or at any point since locks the drag to the
        axis its motion from the press runs along most.
        """
        if mods is not None and mods & _SHIFT:
            drag["locking"] = True
        if not (drag["mods"] & _SHIFT or drag.get("locking")):
            return True, True
        if drag["axis"] is None and (abs(dx_px) + abs(dy_px)) > self.DRAG_PX:
            drag["axis"] = "t" if abs(dx_px) >= abs(dy_px) else "v"
        return drag["axis"] != "v", drag["axis"] != "t"

    def _snap_dt(self, t0: float, dt: float, mods) -> float:
        """*dt* moved so a key at *t0* lands on the snap grid."""
        interval = 1.0 if mods & _CTRL else float(self.sequencer.snap_interval or 0)
        if interval <= 0:
            return dt
        return round((t0 + dt) / interval) * interval - t0

    def _drag_move(self, event, pos, drag) -> None:
        dx_px = pos.x() - drag["press"].x()
        dy_px = pos.y() - drag["press"].y()
        move_t, move_v = self._axis_lock(drag, dx_px, dy_px, event.modifiers())
        dt = dx_px / self.sequencer._timeline.pixels_per_unit if move_t else 0.0
        dv = -dy_px / self.axis.scale if move_v else 0.0
        anchor = drag.get("anchor")
        if move_t and anchor in drag["origin"]:
            dt = self._snap_dt(drag["origin"][anchor][0], dt, event.modifiers())
        self._set_preview(drag, lambda t, v: (t + dt, v + dv))
        if anchor in drag["origin"]:
            t0, v0d = drag["origin"][anchor]
            value = self._real_value(anchor[0], v0d + dv)
            parts = []
            if move_t:
                parts.append(FrameTooltip.format_frame(t0 + dt))
            if move_v:
                parts.append(f"{value:.4g}")
            drag["readout"] = "  ".join(parts)

    def _drag_scale(self, event, pos, drag) -> None:
        box = drag["box"]
        if box is None:
            return
        t_lo, t_hi, v_lo, v_hi = box
        zone = drag["zone"]
        center = bool(event.modifiers() & _ALT)
        top = self.sequencer._content_top
        t = self._x_to_t(pos.x())
        v = self.axis.to_value(pos.y(), top)
        press = drag["press"]
        press_t = self._x_to_t(press.x())
        press_v = self.axis.to_value(press.y(), top)

        def factor(lo, hi, now, grabbed, high_side):
            if center:
                pivot = (lo + hi) / 2.0
                edge = hi if high_side else lo
            else:
                pivot, edge = (lo, hi) if high_side else (hi, lo)
            # Measured from where the edge was GRABBED -- a band padded past
            # the keys -- so the press itself scales nothing.
            span = grabbed - pivot
            if span * (edge - pivot) <= 0 or abs(span) < 1e-9:
                span = edge - pivot  # grabbed across the pivot (a tiny frame)
            if abs(span) < 1e-9:
                return pivot, 1.0
            return pivot, (now - pivot) / span

        st, pt, sv, pv = 1.0, t_lo, 1.0, v_lo
        if "l" in zone or "r" in zone:
            pt, st = factor(t_lo, t_hi, t, press_t, "r" in zone)
        if "t" in zone or "b" in zone:
            pv, sv = factor(v_lo, v_hi, v, press_v, "t" in zone)
        st = max(st, 1e-3)  # never folds the keys over each other in time
        self._set_preview(
            drag, lambda kt, kv: (pt + (kt - pt) * st, pv + (kv - pv) * sv)
        )
        parts = []
        if "l" in zone or "r" in zone:
            parts.append(f"Scale {st:.2f}x")
        if "t" in zone or "b" in zone:
            parts.append(f"Value {sv:.2f}x")
        drag["readout"] = "  ".join(parts)

    def _set_preview(self, drag, place) -> None:
        """Move every dragged key to ``place(t, display value)`` in the preview."""
        by_curve: Dict[str, Dict[int, Tuple[float, float]]] = {}
        edits: Dict[str, List[Tuple[float, float, float]]] = {}
        for ref, (t0, v0d) in drag["origin"].items():
            cid = ref[0]
            curve = self._curves.get(cid)
            idx = self._index(curve, ref[1]) if curve is not None else -1
            if idx < 0:
                continue
            nt, nvd = place(t0, v0d)
            nv = self._real_value(cid, nvd)
            by_curve.setdefault(cid, {})[idx] = (nt, nv)
        self._preview = {}
        self._preview_sel = set()
        for cid, placed in by_curve.items():
            curve = self._curves[cid]
            new = self._placed(curve, placed)
            self._preview[cid] = new
            # ``_placed`` keeps the key order, so an index still names its key.
            for i in placed:
                self._preview_sel.add((cid, new.keys[i].time))
                old = curve.keys[i]
                dt = new.keys[i].time - old.time
                dv = new.keys[i].value - old.value
                # Only what moved: a drag brought back to where it began is
                # no edit (and a live one is cancelled, not committed).
                if abs(dt) > 1e-9 or abs(dv) > 1e-12:
                    edits.setdefault(cid, []).append((old.time, dt, dv))
        drag["edits"] = list(edits.items())

    @staticmethod
    def _placed(curve, placed: Dict[int, Tuple[float, float]]):
        """A copy of *curve* with keys at new ``(time, value)``, the order kept.

        A move or a scale maps the moved keys monotonically, so they keep
        their order among themselves; where the edit would bring two keys
        within ``_EPS`` (a moved key onto one that stays, or a scale folding
        two together) its time change is cut back by ONE fraction for every
        key -- the block stops whole, its spacing kept, as
        ``KeyCurve.with_keys_moved`` clamps a move.  Values move in full.
        """
        times = curve.times()
        new = list(times)
        for i, (t, _v) in placed.items():
            new[i] = t
        share = 1.0
        for i in range(len(times) - 1):
            was, now = times[i + 1] - times[i], new[i + 1] - new[i]
            if now < _EPS < was and now < was:
                share = min(share, (was - _EPS) / (was - now))
        # New key objects for the moved keys only: a deep copy of the whole
        # curve on every mouse move cost a select-all drag over a bake seconds.
        keys = list(curve.keys)
        for i, (t, v) in placed.items():
            keys[i] = dataclasses.replace(
                keys[i], time=times[i] + share * (t - times[i]), value=v
            )
        return dataclasses.replace(curve, keys=keys)

    def _drag_tangent(self, event, pos, drag) -> None:
        cid, idx, side = drag["handle"]
        curve = self._curves.get(cid)
        if curve is None:
            return
        key = curve.keys[idx]
        vec = self._handle_vector(cid, curve, key, side, pos)
        mods = event.modifiers()
        breaking = bool(mods & _ALT)
        targets = [(cid, idx)]
        if mods & _SHIFT:  # every selected key takes this exact vector
            targets += [
                (c, self._index(self._curves[c], t))
                for c, t in sorted(self._sel)
                if c in self._curves and (c, t) != (cid, key.time)
            ]
        edits: Dict[str, list] = {}
        rows: Dict[str, list] = {}
        for c, i in targets:
            if i < 0:
                continue
            edits.setdefault(c, []).append((i, side, vec, breaking))
            t = self._curves[c].keys[i].time
            rows.setdefault(c, []).append((t, side, vec[0], vec[1], breaking))
        self._preview = {
            c: self._with_handles(self._curves[c], items) for c, items in edits.items()
        }
        drag["rows"] = list(rows.items())

    @staticmethod
    def _with_handles(curve, edits):
        """A copy of *curve* with handles set -- *edits* ``[(index, side,
        vector, breaking), ...]`` -- each as ``KeyCurve.with_handle`` sets it
        (an unbroken key's other side swings along; *breaking* breaks it).

        One copy for the lot: ``with_handle`` copies the whole curve per call,
        and a Shift drag over a bake's selection is thousands of handles per
        mouse move.  Each key goes through ``with_handle`` alone, on a curve of
        that one key (the rule reads the key and the curve's weighting only).
        """
        out = curve.copy()
        for i, side, vec, breaking in edits:
            key = out.keys[i]
            unify = not (breaking or key.broken)
            alone = dataclasses.replace(curve, keys=[key])
            key = alone.with_handle(0, side, vec, unify=unify).keys[0]
            if breaking:
                key.broken = True
            out.keys[i] = key
        return out

    def _handle_vector(self, cid, curve, key, side, pos) -> Tuple[float, float]:
        """The handle vector (curve units) the pointer at *pos* asks for."""
        t = self._x_to_t(pos.x())
        vd = self.axis.to_value(pos.y(), self.sequencer._content_top)
        dt = t - key.time
        dv = self._real_value(cid, vd) - key.value
        dt = max(dt, 1e-6) if side == "out" else min(dt, -1e-6)
        if curve.weighted:
            return dt, dv
        slope = dv / dt  # an unweighted curve stores the angle alone
        return (1.0, slope) if side == "out" else (-1.0, -slope)

    def _finish_marquee(self, drag, mods) -> None:
        rect = QtCore.QRectF(drag["press"], drag["current"]).normalized()
        hits = {
            (cid, k.time)
            for cid, k in self._shown_keys()
            if rect.contains(self._key_point(cid, k))
        }
        if mods & _CTRL and mods & _SHIFT:
            self.select_keys(hits, "add")
        elif mods & _SHIFT:
            self.select_keys(hits, "toggle")
        elif mods & _CTRL:
            self.select_keys(hits, "remove")
        else:
            self.select_keys(hits, "replace")

    # -- edits out --------------------------------------------------------------

    def _emit_moves(self, edits) -> None:
        """Publish a move/scale and show it until the host's refresh."""
        for cid, rows in edits:
            curve = self._curves.get(cid)
            if curve is None:
                continue
            placed = {}
            for t, dt, dv in rows:
                i = self._index(curve, t)
                if i >= 0:
                    placed[i] = (t + dt, curve.keys[i].value + dv)
            new = self._placed(curve, placed)
            self._curves[cid] = new
            # Remapped in one pass: key by key, a key moved onto the next
            # one's old time was dropped with it.
            remap = {(cid, curve.keys[i].time): (cid, new.keys[i].time) for i in placed}
            kept = {remap[ref] for ref in remap if ref in self._sel}
            self._sel = (self._sel - remap.keys()) | kept
        self.keys_edited.emit([(cid, list(rows)) for cid, rows in edits])
        self._selection_changed()

    def _emit_tangents(self, rows) -> None:
        for cid, items in rows:
            curve = self._curves.get(cid)
            if curve is None:
                continue
            handles = []
            for t, side, dt, dv, breaking in items:
                i = self._index(curve, t)
                if i >= 0:
                    handles.append((i, side, (dt, dv), breaking))
            self._curves[cid] = self._with_handles(curve, handles)
        self.tangents_edited.emit([(cid, list(items)) for cid, items in rows])
        self._repaint()

    # -- geometry ---------------------------------------------------------------

    def _x_to_t(self, x: float) -> float:
        return self.sequencer._timeline.x_to_time(x)

    def _memo_of(self, curve) -> list:
        """``[curve, times, normalization]`` for *curve*, its time list read
        once per curve OBJECT.  Every change makes a new one (an edit or a
        preview returns a copy; :meth:`refresh` clears the lot), so an object
        names one state: a per-key lookup is a bisect, not a rebuilt list --
        a select-all over a bake was O(keys^2) per move."""
        entry = self._memo.get(id(curve))
        if entry is None or entry[0] is not curve:
            if len(self._memo) > 256:  # previews come and go every move
                self._memo.clear()
            entry = self._memo[id(curve)] = [curve, curve.times(), None]
        return entry

    def _index(self, curve, t: float) -> int:
        """``curve.index_at(t)`` over the memoized times (:meth:`_memo_of`)."""
        times = self._memo_of(curve)[1]
        i = bisect.bisect_left(times, t - _EPS)
        return i if i < len(times) and abs(times[i] - t) <= _EPS else -1

    def _norm(self, cid: str) -> Tuple[float, float]:
        if not self._normalized:
            return 0.0, 1.0
        curve = self._curves.get(cid)
        if curve is None or not len(curve):
            return 0.0, 1.0
        entry = self._memo_of(curve)
        if entry[2] is None:  # an O(keys) measure, once per curve state
            entry[2] = curve.normalization()
        return entry[2]

    def _display_value(self, cid: str, value: float) -> float:
        off, sc = self._norm(cid)
        return (value - off) * sc

    def _real_value(self, cid: str, display: float) -> float:
        off, sc = self._norm(cid)
        return display / sc + off

    def _point(self, cid: str, t: float, v: float) -> QtCore.QPointF:
        return QtCore.QPointF(
            self.sequencer._timeline.time_to_x(t),
            self.axis.to_y(self._display_value(cid, v), self.sequencer._content_top),
        )

    def _key_point(self, cid: str, key) -> QtCore.QPointF:
        return self._point(cid, key.time, key.value)

    def _key(self, cid: str, t: float):
        curve = self._curves.get(cid)
        if curve is None:
            return None
        i = self._index(curve, t)
        return curve.keys[i] if i >= 0 else None

    def _handle_point(self, cid: str, curve, key, side: str) -> QtCore.QPointF:
        """Where a key's handle is drawn: a weighted handle at its control
        point, an unweighted one at a fixed screen length along its angle."""
        vec = key.out_handle if side == "out" else key.in_handle
        if curve.weighted:
            return self._point(cid, key.time + vec[0], key.value + vec[1])
        root = self._key_point(cid, key)
        _off, sc = self._norm(cid)
        dx = vec[0] * self.sequencer._timeline.pixels_per_unit
        dy = -vec[1] * sc * self.axis.scale
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return root
        return QtCore.QPointF(
            root.x() + dx / length * self.HANDLE_PX,
            root.y() + dy / length * self.HANDLE_PX,
        )

    def _visible_time_range(self) -> Tuple[float, float]:
        view = self.sequencer._timeline
        rect = view.mapToScene(view.viewport().rect()).boundingRect()
        return self._x_to_t(rect.left()), self._x_to_t(rect.right())

    def _value_range(self, ids, t0: float, t1: float) -> Optional[Tuple[float, float]]:
        lo = hi = None
        for cid in ids:
            curve = self._curves.get(cid)
            if curve is None or not len(curve):
                continue
            a, b = curve.value_bounds(t0, t1)
            a, b = self._display_value(cid, a), self._display_value(cid, b)
            lo = a if lo is None else min(lo, a)
            hi = b if hi is None else max(hi, b)
        return None if lo is None else (lo, hi)

    def _fit_values(self, value_range) -> None:
        if value_range is None:
            return
        self.axis.fit(value_range[0], value_range[1], self.content_height())
        self._repaint()

    def _selection_box_units(self) -> Optional[Tuple[float, float, float, float]]:
        """``(t_lo, t_hi, v_lo, v_hi)`` of the selection, display values."""
        pts = [
            (k.time, self._display_value(cid, k.value))
            for cid, t in self._sel
            for k in [self._key(cid, t)]
            if k is not None
        ]
        if len(pts) < 2:
            return None
        ts = [p[0] for p in pts]
        vs = [p[1] for p in pts]
        return min(ts), max(ts), min(vs), max(vs)

    def selection_frame(self) -> Optional[QtCore.QRectF]:
        """The scale frame around two or more selected keys (scene coords);
        hidden while another drag runs."""
        if self._drag is not None and self._drag["kind"] not in ("scale",):
            return None
        box = self._selection_box_units()
        if box is None:
            return None
        t_lo, t_hi, v_lo, v_hi = box
        top = self.sequencer._content_top
        view = self.sequencer._timeline
        rect = QtCore.QRectF(
            QtCore.QPointF(view.time_to_x(t_lo), self.axis.to_y(v_hi, top)),
            QtCore.QPointF(view.time_to_x(t_hi), self.axis.to_y(v_lo, top)),
        ).normalized()
        pad = self.HIT_PX
        return rect.adjusted(-pad, -pad, pad, pad)

    # -- hit tests --------------------------------------------------------------

    def _key_at(self, pos) -> Optional[KeyRef]:
        best, best_d = None, self.HIT_PX
        # Only the keys within the hit distance in time: a bisect window, not
        # a scan of every key (it runs on every press, and on hover).
        lo_t = self._x_to_t(pos.x() - self.HIT_PX)
        hi_t = self._x_to_t(pos.x() + self.HIT_PX)
        for cid in self._shown:
            curve = self._curves.get(cid)
            if curve is None:
                continue
            times = self._memo_of(curve)[1]
            a = bisect.bisect_left(times, lo_t)
            b = bisect.bisect_right(times, hi_t)
            for k in curve.keys[a:b]:
                if k.hidden:
                    continue
                p = self._key_point(cid, k)
                d = max(abs(p.x() - pos.x()), abs(p.y() - pos.y()))
                if d <= best_d:
                    best, best_d = (cid, k.time), d
        return best

    def _handle_at(self, pos) -> Optional[Tuple[str, int, str]]:
        if len(self._sel) > _GraphCanvas.HANDLE_CAP:
            return None  # not drawn (_GraphCanvas._paint_selected), not grabbed
        for cid, t in sorted(self._sel):
            curve = self._curves.get(cid)
            i = self._index(curve, t) if curve is not None else -1
            if i < 0:
                continue
            key = curve.keys[i]
            for side in ("in", "out"):
                p = self._handle_point(cid, curve, key, side)
                if math.hypot(p.x() - pos.x(), p.y() - pos.y()) <= self.HIT_PX:
                    return cid, i, side
        return None

    def _box_zone_at(self, pos) -> Optional[str]:
        frame = self.selection_frame()
        if frame is None or not frame.adjusted(-2, -2, 2, 2).contains(pos):
            return None
        e = self.HIT_PX
        vertical = (
            "t"
            if abs(pos.y() - frame.top()) <= e
            else "b"
            if abs(pos.y() - frame.bottom()) <= e
            else ""
        )
        horizontal = (
            "l"
            if abs(pos.x() - frame.left()) <= e
            else "r"
            if abs(pos.x() - frame.right()) <= e
            else ""
        )
        return (vertical + horizontal) or "body"

    def _curve_at(self, pos) -> Optional[Tuple[str, float]]:
        t = self._x_to_t(pos.x())
        for cid in reversed(self._shown):
            curve = self._curves.get(cid)
            if curve is None or not len(curve):
                continue
            p = self._point(cid, t, curve.evaluate(t))
            if abs(p.y() - pos.y()) <= self.HIT_PX:
                return cid, t
        return None

    def _anchor_key(self) -> Optional[KeyRef]:
        return min(self._sel) if self._sel else None

    # -- bookkeeping ------------------------------------------------------------

    def _update_shown(self) -> None:
        # Once each: a curve listed under two objects is still one curve.
        self._shown = list(dict.fromkeys(self._page.displayed_curve_ids()))
        missing = [cid for cid in self._shown if cid not in self._curves]
        if missing and self._provider is not None:
            for curve in self._provider(missing) or ():
                self._curves[curve.curve_id] = curve
        had = len(self._sel)
        self._prune_selection()
        if len(self._sel) != had:  # keys of curves no longer shown left it
            self._selection_changed()
        else:
            self._repaint()

    def _prune_selection(self) -> None:
        keep = set()
        for cid, t in self._sel:
            if cid not in self._shown:
                continue
            k = self._key(cid, t)
            if k is not None and not k.hidden:
                keep.add((cid, k.time))
        self._sel = keep

    def _selection_changed(self) -> None:
        self._repaint()
        self.key_selection_changed.emit(self.selected_keys())

    #: The scale frame's zones and the cursor each shows.
    _ZONE_CURSORS = {
        "l": QtCore.Qt.SizeHorCursor,
        "r": QtCore.Qt.SizeHorCursor,
        "t": QtCore.Qt.SizeVerCursor,
        "b": QtCore.Qt.SizeVerCursor,
        "tl": QtCore.Qt.SizeFDiagCursor,
        "br": QtCore.Qt.SizeFDiagCursor,
        "tr": QtCore.Qt.SizeBDiagCursor,
        "bl": QtCore.Qt.SizeBDiagCursor,
    }

    def _sync_cursor(self, pos) -> None:
        zone = self._box_zone_at(pos) if self._handle_at(pos) is None else None
        vp = self.sequencer._timeline.viewport()
        if zone in self._ZONE_CURSORS:
            vp.setCursor(self._ZONE_CURSORS[zone])
        else:
            vp.unsetCursor()

    def _repaint(self) -> None:
        self._canvas.update()


class _GraphCanvas(HeldGeometryMixin, QtWidgets.QGraphicsObject):
    """Paints the graph editor's grid, curves, keys, handles and frames.

    One item for everything: hit-testing is the editor's arithmetic, so a
    thousand-key bake costs a thousand rectangles in one paint, not a
    thousand scene items.  It spans the scene's width over the content area
    and holds that geometry between syncs (``HeldGeometryMixin``).
    """

    KEY_PX = 5.0
    #: Repeats of a cycling curve drawn per side, at most.
    MAX_CYCLES = 400
    BG = QtGui.QColor("#2B2B2B")
    GRID = QtGui.QColor("#353535")
    GRID_ZERO = QtGui.QColor("#4E4E4E")
    LABEL = QtGui.QColor("#8A8A8A")
    KEY = QtGui.QColor("#D6D6D6")
    #: Over the time outside the shots on screen (``GraphEditor.dim_outside``).
    VEIL = QtGui.QColor(43, 43, 43, 150)
    KEY_SELECTED = QtGui.QColor("#FFD84A")
    KEY_BREAKDOWN = QtGui.QColor("#5FD35F")
    HANDLE = QtGui.QColor("#C88A44")
    FRAME = QtGui.QColor(255, 255, 255, 120)

    def __init__(self, editor: GraphEditor):
        super().__init__()
        self._editor = editor
        self.setFlag(QtWidgets.QGraphicsItem.ItemUsesExtendedStyleOption, True)
        #: ``id(curve) -> (curve, path, risers, flats, keys, breakdowns)`` (:meth:`_build`).
        self._built: Dict[int, tuple] = {}

    def _layout_geometry(self) -> QtCore.QRectF:
        sq = self._editor.sequencer
        scene_rect = sq._timeline._scene.sceneRect()
        return QtCore.QRectF(
            scene_rect.left(),
            sq._content_top,
            scene_rect.width(),
            self._editor.content_height(),
        )

    def boundingRect(self) -> QtCore.QRectF:
        return self._geometry()

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        ed = self._editor
        view = ed.sequencer._timeline
        area = self._geometry()
        exposed = option.exposedRect.intersected(area) if option is not None else area
        painter.save()
        painter.setClipRect(area)
        painter.fillRect(exposed, self.BG)
        self._paint_grid(painter, exposed)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        t0 = view.x_to_time(exposed.left())
        t1 = view.x_to_time(exposed.right())
        drawn, built = [], {}
        for cid in ed._shown:
            curve = ed.curve(cid)
            if curve is None or not len(curve):
                continue
            geo = self._built.get(id(curve))
            if geo is None or geo[0] is not curve:
                geo = self._build(curve)
            built[id(curve)] = geo
            drawn.append((cid, curve, geo, self._curve_transform(cid)))
        self._built = built  # a curve no longer drawn lets its geometry go
        for cid, curve, geo, xform in drawn:
            self._paint_curve(painter, cid, curve, geo, xform, t0, t1)
        # Unsmoothed: a 5 px dot reads the same, and a bake is 130k of them.
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        for _cid, _curve, geo, xform in drawn:
            self._paint_keys(painter, geo, xform)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self._paint_veil(painter, exposed)
        self._paint_selected(painter, drawn, t0, t1)
        self._paint_frame(painter)
        drag = ed._drag
        if drag is not None and drag["kind"] == "marquee" and drag["live"]:
            rect = QtCore.QRectF(drag["press"], drag["current"]).normalized()
            painter.setPen(QtGui.QPen(QtGui.QColor(51, 153, 255, 160), 1))
            painter.setBrush(QtGui.QColor(51, 153, 255, 40))
            painter.drawRect(rect)
        elif drag is not None and drag["kind"] == "boxzoom" and drag["live"]:
            rect = QtCore.QRectF(drag["press"], drag["current"]).normalized()
            painter.setPen(QtGui.QPen(self.FRAME, 1, QtCore.Qt.DashLine))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(rect)
        painter.restore()

    def _paint_grid(self, painter, exposed) -> None:
        ed = self._editor
        sq = ed.sequencer
        view = sq._timeline
        top = sq._content_top
        area = self._geometry()
        # Frame columns at a step at least 40 px apart (1, 2, 5, 10, 20...).
        ppu = view.pixels_per_unit
        frames, mults = 1.0, (2.0, 2.5, 2.0)
        i = 0
        while frames * ppu < 40.0:
            frames *= mults[i % 3]
            i += 1
        f = math.floor(view.x_to_time(exposed.left()) / frames) * frames
        painter.setPen(self.GRID)
        while view.time_to_x(f) <= exposed.right():
            x = view.time_to_x(f)
            painter.drawLine(
                QtCore.QPointF(x, exposed.top()), QtCore.QPointF(x, exposed.bottom())
            )
            f += frames
        # Value rows, labelled along the viewport's left edge.
        step = ed.axis.step()
        v_hi = ed.axis.to_value(area.top(), top)
        v_lo = ed.axis.to_value(area.bottom(), top)
        v = math.floor(v_lo / step) * step
        left = view.mapToScene(0, 0).x()
        font = QtGui.QFont(painter.font())
        font.setPointSize(7)
        painter.setFont(font)
        while v <= v_hi + step:
            y = ed.axis.to_y(v, top)
            zero = abs(v) < step * 1e-6
            painter.setPen(self.GRID_ZERO if zero else self.GRID)
            painter.drawLine(
                QtCore.QPointF(exposed.left(), y), QtCore.QPointF(exposed.right(), y)
            )
            painter.setPen(self.LABEL)
            painter.drawText(
                QtCore.QPointF(left + 3, y - 2), f"{0.0 if zero else v:.6g}"
            )
            v += step

    def _map_y(self, cid):
        ed = self._editor
        top = ed.sequencer._content_top

        def map_y(v):
            return ed.axis.to_y(ed._display_value(cid, v), top)

        return map_y

    @staticmethod
    def _visible_span(curve, t0: float, t1: float) -> Tuple[int, int]:
        """Key indices ``(lo, hi)`` whose spans reach into ``[t0, t1]``: one
        key past each edge, so the edge spans draw whole."""
        times = curve.times()
        lo = max(bisect.bisect_left(times, t0) - 1, 0)
        hi = min(bisect.bisect_right(times, t1), len(times) - 1)
        return lo, hi

    # -- curve geometry: built once per curve object, drawn through a transform --

    @staticmethod
    def _paths(segments) -> Tuple[QtGui.QPainterPath, ...]:
        """``(path, risers, flats)`` of *segments* in curve units: the
        curve, its stepped spans' vertical jumps (drawn dotted) and its flat
        spans (``SequencerWidget.mark_flat_spans``) apart."""
        risers, flats = QtGui.QPainterPath(), QtGui.QPainterPath()
        path = CurveUtils.build_curve_path(segments, float, float, risers, flats)
        return path, risers, flats

    @classmethod
    def _build(cls, curve) -> tuple:
        """``(curve, path, risers, flats, keys, breakdowns)``: *curve*'s
        whole path, its step risers and flat spans (:meth:`_paths`) and its
        drawn keys as point lists, in curve units (frame, value).

        Built once per curve object -- a re-read or a drag preview is a new
        one -- and drawn through :meth:`_curve_transform`, so a repaint costs
        Qt's C++ per key rather than Python's: a production bake (165 curves,
        132,819 keys) took 2.1 s a paint built per key per paint.
        """
        path, risers, flats = cls._paths(curve.segments())
        keys = [k for k in curve.keys if not k.hidden]
        return (
            curve,
            path,
            risers,
            flats,
            QtGui.QPolygonF(
                [QtCore.QPointF(k.time, k.value) for k in keys if not k.breakdown]
            ),
            QtGui.QPolygonF(
                [QtCore.QPointF(k.time, k.value) for k in keys if k.breakdown]
            ),
        )

    def _curve_transform(self, cid: str) -> QtGui.QTransform:
        """Curve units -> scene.  Time and value (normalized or not) both map
        affinely, so two samples fix it."""
        view = self._editor.sequencer._timeline
        map_y = self._map_y(cid)
        x0, y0 = view.time_to_x(0.0), map_y(0.0)
        return QtGui.QTransform(
            view.time_to_x(1.0) - x0, 0.0, 0.0, map_y(1.0) - y0, x0, y0
        )

    @staticmethod
    def _pen(color, width: float, style=QtCore.Qt.SolidLine) -> QtGui.QPen:
        """A pen *width* pixels wide whatever the transform (cosmetic)."""
        pen = QtGui.QPen(color, width, style)
        pen.setCosmetic(True)
        return pen

    #: Below this share of a curve's spans on screen, the visible spans are
    #: built afresh instead of the whole cached path being stroked.
    CULL_SHARE = 0.25

    #: A stepped span's vertical jump: dotted (on, off, in pixels), as Maya's
    #: Graph Editor draws it -- finer than the infinity's dashes.
    RISER_DASHES = (2.0, 3.0)

    def _paint_curve(self, painter, cid, curve, geo, xform, t0, t1) -> None:
        ed = self._editor
        color = QtGui.QColor(ed._colors.get(cid, "#CCCCCC"))
        lo, hi = self._visible_span(curve, t0, t1)
        if hi - lo < len(curve) * self.CULL_SHARE:
            # Zoomed in on a long bake: stroke the few spans on screen.
            path, risers, flats = self._paths(curve.segments(lo, hi))
        else:
            path, risers, flats = geo[1:4]
        painter.save()
        painter.setTransform(xform, True)
        painter.setBrush(QtCore.Qt.NoBrush)
        CurveUtils.stroke_curve(
            painter,
            self._pen(color, 1.4),
            path,
            flats,
            mark=ed.sequencer.mark_flat_spans,
        )
        if not risers.isEmpty():
            pen = self._pen(color, 1.0)
            pen.setDashPattern(list(self.RISER_DASHES))
            painter.setPen(pen)
            painter.drawPath(risers)
        if ed._show_infinity:
            painter.setPen(self._pen(color, 1.0, QtCore.Qt.DashLine))
            self._paint_infinity(painter, curve, geo[1:4], t0, t1)
        painter.restore()

    def _paint_infinity(self, painter, curve, paths, t0, t1) -> None:
        """The curve past its ends, dashed (the painter in curve units).

        Constant and linear infinity are straight lines; a cycling side is the
        curve's own *paths* (path, step risers, flats) repeated -- shifted a
        period per repeat, raised by
        the end-to-end change each repeat (with offset), mirrored every other
        repeat (oscillate) -- never re-evaluated point by point.
        """
        first, last = curve.keys[0], curve.keys[-1]
        period = last.time - first.time
        for pre in (True, False):
            if (pre and t0 >= first.time) or (not pre and t1 <= last.time):
                continue
            mode = curve.pre_infinity if pre else curve.post_infinity
            if mode in ("constant", "linear") or period <= 0:
                a, b = (t0, first.time) if pre else (last.time, t1)
                painter.drawLine(
                    QtCore.QPointF(a, curve.evaluate(a)),
                    QtCore.QPointF(b, curve.evaluate(b)),
                )
                continue
            rise = last.value - first.value  # per repeat
            # From the repeat at the exposed edge nearest the curve: counted
            # from the curve, the cap left a view far out with no cycle drawn
            # and stroked every repeat between.
            if pre:
                k = min(-1, math.floor((t1 - first.time) / period))
            else:
                k = max(1, math.floor((t0 - first.time) / period))
            for _ in range(self.MAX_CYCLES):
                lo = first.time + k * period
                if (pre and lo + period < t0) or (not pre and lo > t1):
                    break
                xform = QtGui.QTransform()
                lift = rise * k if mode == "cycle_offset" else 0.0
                xform.translate(k * period, lift)
                if mode == "oscillate" and k % 2:
                    xform.translate(first.time + last.time, 0)
                    xform.scale(-1, 1)
                painter.save()
                painter.setTransform(xform, True)
                for path in paths:
                    painter.drawPath(path)
                painter.restore()
                k += -1 if pre else 1

    @classmethod
    def _dot_pen(cls, color, width: float) -> QtGui.QPen:
        """A cosmetic round-capped pen: a point drawn with it is a solid dot."""
        pen = cls._pen(color, width)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        return pen

    def _paint_keys(self, painter, geo, xform) -> None:
        """A curve's keys as solid dots -- one point draw each for the plain
        and the breakdown keys (the selected ones go over, in yellow)."""
        keys, breakdowns = geo[4:]
        painter.save()
        painter.setTransform(xform, True)
        for points, color in ((keys, self.KEY), (breakdowns, self.KEY_BREAKDOWN)):
            if not points.isEmpty():
                painter.setPen(self._dot_pen(color, self.KEY_PX))
                painter.drawPoints(points)
        painter.restore()

    def _paint_veil(self, painter, exposed) -> None:
        """Veil the time outside ``focus_range`` (``dim_outside``)."""
        ed = self._editor
        span = ed.focus_range
        if not ed.dim_outside or span is None:
            return
        view = ed.sequencer._timeline
        x0, x1 = view.time_to_x(span[0]), view.time_to_x(span[1])
        for left, right in ((exposed.left(), x0), (x1, exposed.right())):
            if right > left:
                painter.fillRect(
                    QtCore.QRectF(left, exposed.top(), right - left, exposed.height()),
                    self.VEIL,
                )

    #: Past this many selected keys their tangent handles are not drawn: a
    #: select-all over a bake is thousands of handles, read as noise.
    HANDLE_CAP = 2000

    def _paint_selected(self, painter, drawn, t0, t1) -> None:
        """The selected keys over the rest, with their tangent handles while
        the selection is small enough for them to read."""
        ed = self._editor
        selection = ed._drawn_selection()
        if not selection:
            return
        handles = sum(len(times) for times in selection.values()) <= self.HANDLE_CAP
        half = self.KEY_PX / 2.0
        for cid, curve, _geo, xform in drawn:
            times = selection.get(cid)
            if not times:
                continue
            found = (ed._index(curve, t) for t in times)
            keys = [curve.keys[i] for i in found if i >= 0]
            keys = [k for k in keys if not k.hidden]
            if not handles:
                points = QtGui.QPolygonF(
                    [
                        QtCore.QPointF(k.time, k.value)
                        for k in keys
                        if t0 <= k.time <= t1
                    ]
                )
                painter.save()
                painter.setTransform(xform, True)
                painter.setPen(self._dot_pen(self.KEY_SELECTED, self.KEY_PX + 1.0))
                painter.drawPoints(points)
                painter.restore()
                continue
            for k in keys:
                p = ed._key_point(cid, k)
                for side in ("in", "out"):
                    hp = ed._handle_point(cid, curve, k, side)
                    pen = QtGui.QPen(self.HANDLE, 1)
                    if k.broken:
                        pen.setStyle(QtCore.Qt.DotLine)
                    painter.setPen(pen)
                    painter.drawLine(p, hp)
                    painter.setBrush(self.HANDLE)
                    painter.drawEllipse(hp, 2.5, 2.5)
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(self.KEY_SELECTED)
                painter.drawEllipse(p, half + 0.5, half + 0.5)

    def _paint_frame(self, painter) -> None:
        frame = self._editor.selection_frame()
        if frame is None:
            return
        painter.setPen(QtGui.QPen(self.FRAME, 1, QtCore.Qt.DashLine))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(frame)
        painter.setBrush(self.FRAME)
        painter.setPen(QtCore.Qt.NoPen)
        for p in (
            frame.topLeft(),
            frame.topRight(),
            frame.bottomLeft(),
            frame.bottomRight(),
        ):
            painter.drawRect(QtCore.QRectF(p.x() - 3, p.y() - 3, 6, 6))


class _GraphPage(QtWidgets.QWidget):
    """The left pane while the graph editor shows: a filter and the curve
    outline (objects > curves; the selected rows are what is drawn, every
    row when none is), under the pane's Options band -- nothing else, so the
    pane narrows as far as the user likes.  A row's right-click menu is the
    track labels' (:meth:`build_menu`)."""

    def __init__(self, editor: GraphEditor):
        super().__init__()
        self._editor = editor
        self._building = False
        #: Curve ids out of the outline and the display (Hide Curve), kept
        #: across outline rebuilds until Show Hidden Curves brings them back.
        self._hidden: Set[str] = set()
        self.setMinimumWidth(0)
        layout = QtWidgets.QVBoxLayout(self)
        # Below the Options band (level with the ruler and the shot lane).
        layout.setContentsMargins(2, int(editor.sequencer._content_top) + 1, 2, 2)
        layout.setSpacing(2)

        self.filter_field = QtWidgets.QLineEdit()
        self.filter_field.setMinimumWidth(0)
        self.filter_field.setPlaceholderText("Filter curves")
        self.filter_field.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_field)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setMinimumWidth(0)
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_menu)
        layout.addWidget(self.tree, 1)

    # -- outline -----------------------------------------------------------------

    @staticmethod
    def _row_key(item) -> tuple:
        """``("obj", id)`` / ``("curve", id)`` (Qt hands the tuple back as a list)."""
        return tuple(item.data(0, QtCore.Qt.UserRole) or ())

    def _rows(self):
        """``(object row, [curve rows])`` for every object, in order."""
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            yield top, [top.child(j) for j in range(top.childCount())]

    def rebuild(self) -> None:
        selected = {self._row_key(it) for it in self.tree.selectedItems()}
        collapsed = {
            self._row_key(top) for top, _rows in self._rows() if not top.isExpanded()
        }
        self._building = True
        try:
            self.tree.clear()
            for entry in self._editor._outline:
                top = QtWidgets.QTreeWidgetItem([entry.get("label") or entry["id"]])
                key = ("obj", entry["id"])
                top.setData(0, QtCore.Qt.UserRole, key)
                font = top.font(0)
                font.setBold(True)
                top.setFont(0, font)
                self.tree.addTopLevelItem(top)
                for child in entry.get("children", ()):
                    cid = child["curve_id"]
                    row = QtWidgets.QTreeWidgetItem([child.get("label") or cid])
                    row.setData(0, QtCore.Qt.UserRole, ("curve", cid))
                    pix = QtGui.QPixmap(10, 10)
                    pix.fill(QtGui.QColor(child.get("color") or "#CCCCCC"))
                    row.setIcon(0, QtGui.QIcon(pix))
                    top.addChild(row)
                    row.setSelected(("curve", cid) in selected)
                top.setSelected(key in selected)
                top.setExpanded(key not in collapsed)
            self._apply_filter(self.filter_field.text())
        finally:
            self._building = False

    def displayed_curve_ids(self) -> List[str]:
        """Curves of the selected rows (an object row: all its curves); every
        visible curve when nothing is selected."""
        chosen, visible = [], []
        for top, rows in self._rows():
            for row in rows:
                if row.isHidden():
                    continue
                cid = self._row_key(row)[1]
                visible.append(cid)
                if top.isSelected() or row.isSelected():
                    chosen.append(cid)
        return chosen or visible

    def _select_rows(self, items) -> None:
        """Select exactly *items* (outline rows), the display following once."""
        self._building = True
        try:
            self.tree.clearSelection()
            for item in items:
                item.setSelected(True)
        finally:
            self._building = False
        self._editor._update_shown()

    def select_objects(self, object_ids: Iterable[str]) -> bool:
        """Select the object rows of *object_ids*; False when none is listed."""
        wanted = {("obj", oid) for oid in object_ids}
        tops = [top for top, _rows in self._rows() if self._row_key(top) in wanted]
        if tops:
            self._select_rows(tops)
        return bool(tops)

    def select_curves(self, curve_ids: Iterable[str]) -> None:
        """Select the outline rows of *curve_ids* (what the display then shows)."""
        wanted = set(curve_ids)
        self._select_rows(
            row
            for _top, rows in self._rows()
            for row in rows
            if self._row_key(row)[1] in wanted
        )

    def hide_curves(self, curve_ids: Iterable[str]) -> None:
        """Put *curve_ids* out of the outline and the display (their rows
        deselected: shown again, they do not isolate themselves)."""
        ids = set(curve_ids)
        self._hidden |= ids
        self._building = True
        try:
            for _top, rows in self._rows():
                for row in rows:
                    if self._row_key(row)[1] in ids:
                        row.setSelected(False)
        finally:
            self._building = False
        self._apply_filter(self.filter_field.text())

    def show_curves(self, curve_ids: Iterable[str]) -> None:
        """Bring hidden *curve_ids* back into the outline and the display."""
        self._hidden -= set(curve_ids)
        self._apply_filter(self.filter_field.text())

    def hidden_curves(self) -> List[Tuple[str, str]]:
        """``[(curve_id, label), ...]`` of the outline's hidden curves, in
        outline order; the label names the object too."""
        out = []
        for entry in self._editor._outline:
            owner = entry.get("label") or entry["id"]
            for child in entry.get("children", ()):
                cid = child["curve_id"]
                if cid in self._hidden:
                    out.append((cid, f"{child.get('label') or cid} ({owner})"))
        return out

    # -- context menu ------------------------------------------------------------

    def _show_menu(self, pos) -> None:
        menu = self.build_menu(self.tree.itemAt(pos))
        try:  # parented for its style, so released: one QMenu per click
            if not menu.isEmpty():
                menu.exec_(self.tree.viewport().mapToGlobal(pos))
        finally:
            menu.deleteLater()

    def build_menu(self, item=None) -> QtWidgets.QMenu:
        """The right-click menu for outline row *item* (None: the empty pane).

        The row joins the selection as a track label's right-click does --
        an unselected row alone, a selected one keeping the rest -- and the
        menu acts on the selected rows of its kind.  Both kinds select their
        curves' keys.  An object row's menu is then the track labels' own
        (:meth:`TrackHeaderWidget.add_track_actions`, the objects named by
        their outline ``id``); a curve row's hides curves, with the host's
        track rows (``track_menu_requested``) for the curves' objects.
        """
        menu = MenuUtils._styled_menu(self)
        header = self._editor.sequencer._header
        if item is None:
            self._add_show_hidden(menu)
            header.add_track_actions(menu, [])
            return menu
        if not item.isSelected():
            self._select_rows([item])
        kind = self._row_key(item)[0]
        rows = [
            it
            for it in self.tree.selectedItems()
            if not it.isHidden() and self._row_key(it)[0] == kind
        ]
        if kind == "obj":
            ids = [self._row_key(top)[1] for top in rows]
            curves = [
                self._row_key(top.child(j))[1]
                for top in rows
                for j in range(top.childCount())
                if not top.child(j).isHidden()
            ]
        else:
            curves = [self._row_key(row)[1] for row in rows]
            ids = list(dict.fromkeys(self._row_key(row.parent())[1] for row in rows))
        menu.addAction("Select Keys", lambda: self._editor.select_curve_keys(curves))
        menu.addSeparator()
        if kind == "obj":
            header.add_track_actions(menu, ids)
            return menu
        n = len(curves)
        menu.addAction(
            f"Hide {n} Curves" if n > 1 else "Hide Curve",
            lambda: self.hide_curves(curves),
        )
        header.track_menu_requested.emit(menu, ids)
        self._add_show_hidden(menu)
        return menu

    def _add_show_hidden(self, menu) -> None:
        """A Show Hidden Curves submenu, while any of the outline's are."""
        hidden = self.hidden_curves()
        if not hidden:
            return
        sub = menu.addMenu(f"Show Hidden Curves ({len(hidden)})")
        ids = [cid for cid, _label in hidden]
        sub.addAction("Show All", lambda: self.show_curves(ids))
        sub.addSeparator()
        for cid, label in hidden:
            sub.addAction(label, lambda c=cid: self.show_curves([c]))

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        for top, rows in self._rows():
            any_shown = False
            for row in rows:
                show = self._row_key(row)[1] not in self._hidden and (
                    not text
                    or text in row.text(0).lower()
                    or text in top.text(0).lower()
                )
                row.setHidden(not show)
                any_shown = any_shown or show
            top.setHidden(not any_shown)
        if not self._building:
            self._editor._update_shown()

    def _on_tree_selection(self) -> None:
        if not self._building:
            self._editor._update_shown()
