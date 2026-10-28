# !/usr/bin/python
# coding=utf-8
"""Data models and shared constants for the sequencer widget."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from qtpy import QtWidgets, QtGui, QtCore
from uitk.themes.style_sheet import StyleSheet


# ---------------------------------------------------------------------------
#  Background-pattern spacing tiers + declarative spec
# ---------------------------------------------------------------------------
# Defined early so data records (ClipData, TrackData) can carry a PatternSpec
# as a field. Registry, brush builder, and paint helper live further down.
HATCH_DENSE = 6
HATCH_MEDIUM = 8
HATCH_SPARSE = 12


@dataclass(frozen=True)
class PatternSpec:
    """Declarative, hashable description of a tiled background pattern."""

    style: str  # "diagonal" | "crosshatch" | "vstripes" | "hstripes" | "dots" | "grid" | custom
    color: str = "#000000"
    alpha: int = 255
    spacing: int = HATCH_MEDIUM
    line_width: float = 1.0

    def brush(self) -> QtGui.QBrush:
        c = QtGui.QColor(self.color)
        c.setAlpha(self.alpha)
        return PatternRegistry.pattern_brush(
            self.style, c, self.spacing, self.line_width
        )


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
    locked: bool = False
    sub_row: str = ""  # empty = main track row, non-empty = expanded sub-row name
    data: Dict[str, Any] = field(default_factory=dict)
    pattern: Optional[PatternSpec] = None

    @property
    def end(self) -> float:
        return self.start + self.duration

    def key_hidden(self, index: int) -> bool:
        """Whether the curve preview's key *index* is drawn without a dot.

        A host marks a key ``hidden`` (``curve_preview["hidden"]``, one bool
        per key) when it shapes the curve but is not a key the user works
        with -- its own bookkeeping samples.  Such a key has no dot, is not
        selectable, and is neither a navigation stop nor a snap target.
        """
        hidden = (self.data.get("curve_preview") or {}).get("hidden") or ()
        return index < len(hidden) and bool(hidden[index])

    def shown_key_times(self) -> List[float]:
        """The curve preview's key times that are drawn as dots."""
        keys = (self.data.get("curve_preview") or {}).get("keys") or ()
        return [
            float(entry[0] if isinstance(entry, (list, tuple)) else entry)
            for i, entry in enumerate(keys)
            if not self.key_hidden(i)
        ]


@dataclass
class TrackData:
    """Lightweight data record for a track row."""

    track_id: int
    name: str
    color: Optional[str] = None
    text_color: Optional[str] = None
    clips: List[int] = field(default_factory=list)
    pattern: Optional[PatternSpec] = None
    # Header-label presentation, stored so label rebuilds (e.g. after
    # remove_track) re-apply the full style instead of degrading every
    # remaining track to a plain label.
    icon: Any = None
    dimmed: bool = False
    italic: bool = False


@dataclass
class MarkerData:
    """Lightweight data record for a timeline marker."""

    marker_id: int
    time: float
    note: str = ""
    color: str = "#E8A84A"
    draggable: bool = True
    style: str = "triangle"  # triangle | diamond | line | bracket
    line_style: str = "dashed"  # dashed | solid | dotted | none
    opacity: float = 1.0
    #: The consumer's own payload (who placed the marker, what it marks),
    #: carried untouched through every edit the widget makes.
    data: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
_TRACK_HEIGHT = 28
_SUB_ROW_HEIGHT = 22  # default height for expanded attribute sub-rows
_TRACK_PADDING = 2
#: The frame ruler: numbers and key ticks all the way down, every row of it
#: the scrub.  A layer's lane is a strip of its own below it
#: (``SequencerWidget.add_layer``) -- sharing the ruler's band put a lane's
#: grabs where the scrub belongs.
_RULER_HEIGHT = 24
_HANDLE_WIDTH = 5  # pixels from edge that activates resize cursor
_MIN_CLIP_DURATION = 1.0
_MIN_POINT_CLIP_WIDTH = 4  # minimum pixel width for zero-duration clips


@dataclass(frozen=True)
class RowMetrics:
    """How tall the track rows are and how their keys are drawn: one density.

    The one source every row reader shares -- the scene's row layout
    (``SequencerWidget._iter_rows``) and the header's labels
    (``TrackHeaderWidget.apply_metrics``) -- so the two cannot drift.

    ``key_style`` is ``"curve"`` (a sub-row draws its keys at their values on
    a mini normalised curve, with tangent handles) or ``"flat"`` (keys sit on
    the row's centre line, dope-sheet style, no curve and no handles; an
    object row draws its ``summary_times`` as ticks).
    """

    track_height: int = _TRACK_HEIGHT
    sub_row_height: int = _SUB_ROW_HEIGHT
    padding: int = _TRACK_PADDING
    key_style: str = "curve"

    #: The ``key_style`` values a preset may name.
    KEY_STYLES = ("curve", "flat")

    def __post_init__(self):
        if self.key_style not in self.KEY_STYLES:
            raise ValueError(
                f"key_style must be one of {self.KEY_STYLES}, got {self.key_style!r}"
            )

    @property
    def flat_keys(self) -> bool:
        """True when keys are drawn on the row's centre line."""
        return self.key_style == "flat"

    @classmethod
    def preset(cls, name: str) -> "RowMetrics":
        """The named density: ``"standard"`` (today's rows) or ``"compact"``.

        Raises:
            KeyError: *name* is not a preset.
        """
        return _ROW_METRICS_PRESETS[name]

    @classmethod
    def preset_names(cls) -> tuple:
        """The preset names, in display order."""
        return tuple(_ROW_METRICS_PRESETS)


_ROW_METRICS_PRESETS: Dict[str, RowMetrics] = {
    "standard": RowMetrics(),
    "compact": RowMetrics(
        track_height=16, sub_row_height=14, padding=1, key_style="flat"
    ),
}

#: The one accent every "this is selected" cue is drawn in -- a lane's
#: selected band (``SequencerWidget.SELECTED_ACCENT``, for a layer), the range
#: highlight over the tracks, and a selected clip's outline.  Kept here rather
#: than in any one painter so they agree: separate blues would read as
#: unrelated decorations.
SELECTED_ACCENT = "#5A8CDC"

#: The colours of the widget's own display rows -- the only attribute colours
#: uitk knows.  A host's channel vocabulary (``translateX``...) and its colours
#: are the host's to inject (:attr:`SequencerWidget.attribute_colors`,
#: ``AttributeColorDialog(defaults=..., common_attrs=...)``): uitk carries no
#: application vocabulary.
DISPLAY_COLORS: Dict[str, str] = {"consolidated": "#FFFFFF"}

_MENU_STYLESHEET = (
    "QMenu { background:#333; color:#CCC; }QMenu::item:selected { background:#555; }"
)


class MenuUtils:
    """Construction/placement helpers for the sequencer's context menus --
    its own items' and a layer's (``SequencerWidget.add_layer``), so every
    menu on the timeline reads alike."""

    @staticmethod
    def styled_menu(parent=None) -> QtWidgets.QMenu:
        """Create a QMenu with the sequencer's standard dark stylesheet."""
        menu = QtWidgets.QMenu(parent)
        # Pinned first: a sheet of its own would otherwise draw its check
        # marks and submenu arrows in the host's style.
        StyleSheet.pin_base_style(menu)
        menu.setStyleSheet(_MENU_STYLESHEET)
        StyleSheet.cast_shadow(menu)
        return menu

    @staticmethod
    def menu_exec_pos(event) -> QtCore.QPoint:
        """Return a screen position suitable for ``QMenu.exec_``."""
        if hasattr(event, "screenPos"):
            return event.screenPos()
        return QtGui.QCursor.pos()


# ---------------------------------------------------------------------------
#  Curve rendering — shared value→pixel mapping + segment path builder
# ---------------------------------------------------------------------------
class CurveUtils:
    """Shared value→pixel mapping + curve-segment path builder.

    Key dots, clip curve previews, and background curves must agree
    pixel-for-pixel; these are the single implementations both sides share.
    """

    @staticmethod
    def make_value_mapper(
        rect_top: float, rect_height: float, val_min: float, val_max: float
    ):
        """Return ``(map_y, is_flat)`` — the canonical value→pixel mapping.

        Key dots (KeyframeItem), clip curve previews, and background curves
        must agree pixel-for-pixel: same 15% vertical pad, inverted Y (high
        values → top), and flat curves centered in the row.  This is the
        single implementation; per-site copies drifted (a floored range let
        flat background curves paint at the row bottom while their key dots
        centered).
        """
        y_bot, y_span, val_range, is_flat = CurveUtils._value_axis(
            rect_top, rect_height, val_min, val_max
        )

        def map_y(v: float) -> float:
            if is_flat:
                return y_bot - y_span * 0.5
            frac = (v - val_min) / val_range
            return y_bot - frac * y_span

        return map_y, is_flat

    @staticmethod
    def _value_axis(
        rect_top: float, rect_height: float, val_min: float, val_max: float
    ):
        """``(y_bot, y_span, val_range, is_flat)`` behind the value mapping."""
        pad = rect_height * 0.15
        y_top = rect_top + pad
        y_bot = rect_top + rect_height - pad
        val_range = val_max - val_min
        return y_bot, y_bot - y_top, val_range, val_range < 1e-9

    @staticmethod
    def unmap_value(
        rect_top: float, rect_height: float, val_min: float, val_max: float, y: float
    ) -> float:
        """The value a pixel row *y* stands for -- :meth:`make_value_mapper`
        run backwards, for a handle dragged in pixels that has to land in
        curve units.  A flat range has no value axis to read, so its one
        value comes back."""
        y_bot, y_span, val_range, is_flat = CurveUtils._value_axis(
            rect_top, rect_height, val_min, val_max
        )
        if is_flat or y_span < 1e-9:
            return val_min
        return val_min + (y_bot - y) / y_span * val_range

    #: Values this close are one level (curve units) -- a span that stays
    #: within it of its start is flat (:meth:`segment_is_flat`); the
    #: tolerance the hosts split hold spans out at (mayatk / blendertk
    #: ``SegmentKeys.collect_segments(static_tolerance=)``), so a span the
    #: track view shows as a hold clip never draws as moving.
    FLAT_TOLERANCE = 1e-4
    #: A flat span's stroke, against a moving one's (:meth:`flat_pen`).
    FLAT_DASHES = (4.0, 3.0)

    @staticmethod
    def segment_is_flat(seg: dict, tolerance: float = FLAT_TOLERANCE) -> bool:
        """Whether span *seg* holds one value end to end, within *tolerance*.

        A step span always does (its jump is a riser, not the span); any
        other must end where it starts, with its control points or samples
        level too -- equal ends with tilted handles overshoot, and move.

        Parameters:
            seg: A :meth:`build_curve_path` segment.
            tolerance: Curve units within which two values are one.
        """
        samples = seg.get("samples")
        out_type = seg.get("out_type", "spline")
        if out_type in ("step", "stepnext") and not samples:
            return True
        v0 = seg["v0"]
        if abs(seg["v1"] - v0) > tolerance:  # most spans: no list built
            return False
        if samples:
            inner = (v for _t, v in samples)
        elif out_type == "linear":
            return True
        else:
            inner = (cp[1] for cp in (seg.get("cp1"), seg.get("cp2")) if cp)
        return all(abs(v - v0) <= tolerance for v in inner)

    @staticmethod
    def flat_pen(pen: QtGui.QPen) -> QtGui.QPen:
        """*pen* as a flat span draws: dashed (:attr:`FLAT_DASHES`), so a
        span that only nearly holds -- solid -- reads apart from one that
        does, at any zoom."""
        out = QtGui.QPen(pen)
        out.setDashPattern(list(CurveUtils.FLAT_DASHES))
        return out

    @staticmethod
    def stroke_curve(painter, pen, path, flats=None, mark: bool = True) -> None:
        """Stroke a :meth:`build_curve_path` *path* with *pen*, and its
        *flats* with :meth:`flat_pen` -- or with *pen*, unmarked -- the one
        way every view draws a curve's flat spans."""
        painter.setPen(pen)
        painter.drawPath(path)
        if flats is not None and not flats.isEmpty():
            painter.setPen(CurveUtils.flat_pen(pen) if mark else pen)
            painter.drawPath(flats)

    @staticmethod
    def build_curve_path(
        segments, map_x, map_y, risers=None, flats=None
    ) -> QtGui.QPainterPath:
        """Build a QPainterPath from curve *segments*.

        One implementation of the out-type switch (``step`` /
        ``stepnext`` / ``linear`` / cubic-Bézier via ``cp1``/``cp2``) shared
        by the clip curve preview, the background curve painter and the
        graph editor, so a tangent-rendering change can't silently diverge
        between them.

        A segment may also carry ``samples`` -- ``[(t, v), ...]`` strictly
        between its endpoints -- for a span neither a line nor one cubic can
        draw (Blender's eased interpolations: SINE, BACK, BOUNCE, ...); it is
        drawn through them, whatever its ``out_type`` says.

        *risers*, a ``QPainterPath``, takes each step span's vertical jump
        instead of the returned path (which moves across it), for a painter
        that draws the jump apart -- the graph editor dots it, as Maya's
        Graph Editor does.  Without it the jump is part of the path.

        *flats*, a ``QPainterPath``, likewise takes every flat span
        (:meth:`segment_is_flat`; a run of them as one line) for a painter
        that marks them (:meth:`flat_pen`): a step's jump stays a jump.
        """
        path = QtGui.QPainterPath()
        if not segments:
            return path
        # A segment that does not carry its own endpoints cannot be drawn, and
        # RAISING over it is not an option: this runs inside
        # ``QGraphicsItem.paint``, where a Python exception leaves the painter
        # half-built and Qt goes on to fault the host process.  Measured
        # 2026-09-11: one segment missing ``t0`` took an offscreen render down
        # with an access violation, not a traceback -- which is the whole
        # distance between a missing curve and a lost Maya session.  Draw the
        # segments that are well formed and skip the rest.
        segments = [
            seg for seg in segments if all(k in seg for k in ("t0", "v0", "t1", "v1"))
        ]
        if not segments:
            return path
        first_seg = segments[0]
        path.moveTo(map_x(first_seg["t0"]), map_y(first_seg["v0"]))
        for seg in segments:
            x1 = map_x(seg["t1"])
            y1 = map_y(seg["v1"])
            ot = seg.get("out_type", "spline")
            cp1 = seg.get("cp1")
            cp2 = seg.get("cp2")
            samples = seg.get("samples")
            flat = flats is not None and CurveUtils.segment_is_flat(seg)
            if flat or ot in ("step", "stepnext"):  # the start, only when used
                x0, y0 = map_x(seg["t0"]), map_y(seg["v0"])
            # The span's body: the path, or -- flat -- *flats*, continuing
            # its run there (one line, so a dash pattern flows through).
            body = path
            if flat:
                body = flats
                start = QtCore.QPointF(x0, y1 if ot == "stepnext" else y0)
                if flats.elementCount() == 0 or flats.currentPosition() != start:
                    flats.moveTo(start)
            if samples:
                for t, v in samples:
                    body.lineTo(map_x(t), map_y(v))
                body.lineTo(x1, y1)
            elif ot == "step":
                # Hold value, then jump at next key
                body.lineTo(x1, y0)
                if body is flats:
                    path.moveTo(x1, y0)
                CurveUtils._jump(path, risers, x1, y0, y1)
                continue  # the path is at the span's end
            elif ot == "stepnext":
                # Jump to next value immediately, then hold
                CurveUtils._jump(path, risers, x0, y0, y1)
                body.lineTo(x1, y1)
            elif ot == "linear" or cp1 is None or cp2 is None:
                body.lineTo(x1, y1)
            else:
                body.cubicTo(
                    map_x(cp1[0]),
                    map_y(cp1[1]),
                    map_x(cp2[0]),
                    map_y(cp2[1]),
                    x1,
                    y1,
                )
            if body is flats:
                path.moveTo(x1, y1)
        return path

    @staticmethod
    def _jump(path, risers, x: float, y_from: float, y_to: float) -> None:
        """A step's vertical at *x*, *y_from* to *y_to*: onto *risers* (the
        path moving across it) when given, else the path's own line.  A jump
        of no height stays on the path: drawn apart it is a stray dot."""
        if risers is None or y_from == y_to:
            path.lineTo(x, y_to)
            return
        risers.moveTo(x, y_from)
        risers.lineTo(x, y_to)
        path.moveTo(x, y_to)


# ---------------------------------------------------------------------------
#  Background fill patterns — registry + cached brushes
# ---------------------------------------------------------------------------
# Spacing tiers (HATCH_DENSE / MEDIUM / SPARSE) live near the top of the file
# so PatternSpec can reference them as defaults.

# A pattern painter draws one tile of side ``size`` onto the given QPainter.
PatternPainter = Callable[[QtGui.QPainter, int, QtGui.QColor, float], None]

_PATTERN_CACHE_MAX = 128


class PatternRegistry:
    """Registry of tile-painters + cached tiled brushes for background fills."""

    #: The spacing tiers, by name, for a caller outside the package (a layer's
    #: items): :meth:`pattern_brush`'s *spacing*.
    HATCH_DENSE = HATCH_DENSE
    HATCH_MEDIUM = HATCH_MEDIUM
    HATCH_SPARSE = HATCH_SPARSE

    # Registered tile-painters, keyed by style name.
    _pattern_painters: Dict[str, PatternPainter] = {}
    # Brush cache — keyed by (style, color, spacing, width) only, so an
    # override purge (see register_pattern) drops stale tiles for known combos.
    _pattern_cache: Dict[tuple, QtGui.QBrush] = {}

    @staticmethod
    def register_pattern(name: str, painter: PatternPainter) -> None:
        """Register (or override) a tile-painter for :meth:`pattern_brush`."""
        PatternRegistry._pattern_painters[name] = painter
        # Drop cached brushes rendered by the previous painter — the cache
        # is keyed by (style, color, spacing, width) only, so an override
        # would otherwise keep serving stale tiles for known arg combos.
        for key in [k for k in PatternRegistry._pattern_cache if k[0] == name]:
            del PatternRegistry._pattern_cache[key]

    @staticmethod
    def _paint_diagonal(p, size, color, lw):
        p.setPen(QtGui.QPen(color, lw))
        p.drawLine(0, size, size, 0)

    @staticmethod
    def _paint_crosshatch(p, size, color, lw):
        pen = QtGui.QPen(color, lw)
        p.setPen(pen)
        p.drawLine(0, size, size, 0)
        p.drawLine(0, 0, size, size)

    @staticmethod
    def _paint_vstripes(p, size, color, lw):
        p.setPen(QtGui.QPen(color, lw))
        p.drawLine(0, 0, 0, size)

    @staticmethod
    def _paint_hstripes(p, size, color, lw):
        p.setPen(QtGui.QPen(color, lw))
        p.drawLine(0, 0, size, 0)

    @staticmethod
    def _paint_dots(p, size, color, lw):
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        radius = max(0.5, lw)
        c = size / 2.0
        p.drawEllipse(QtCore.QPointF(c, c), radius, radius)

    @staticmethod
    def _paint_grid(p, size, color, lw):
        p.setPen(QtGui.QPen(color, lw))
        p.drawLine(0, 0, size, 0)
        p.drawLine(0, 0, 0, size)

    @staticmethod
    def pattern_brush(
        style: str,
        color: QtGui.QColor,
        spacing: int = HATCH_MEDIUM,
        line_width: float = 1.0,
    ) -> QtGui.QBrush:
        """Return a cached tiled brush for the registered ``style`` (``line_width`` doubles as dot radius for ``"dots"``)."""
        key = (style, color.rgba(), spacing, line_width)
        brush = PatternRegistry._pattern_cache.get(key)
        if brush is not None:
            return brush
        painter_fn = PatternRegistry._pattern_painters.get(style)
        if painter_fn is None:
            raise KeyError(
                f"Unknown pattern style {style!r}. "
                f"Registered: {sorted(PatternRegistry._pattern_painters)}"
            )
        tile = QtGui.QPixmap(spacing, spacing)
        tile.fill(QtCore.Qt.transparent)
        tp = QtGui.QPainter(tile)
        try:
            painter_fn(tp, spacing, color, line_width)
        finally:
            tp.end()
        brush = QtGui.QBrush(tile)
        if len(PatternRegistry._pattern_cache) >= _PATTERN_CACHE_MAX:
            PatternRegistry._pattern_cache.pop(
                next(iter(PatternRegistry._pattern_cache))
            )
        PatternRegistry._pattern_cache[key] = brush
        return brush

    @staticmethod
    def paint_pattern(
        painter: QtGui.QPainter,
        rect: QtCore.QRectF,
        spec: PatternSpec,
    ) -> None:
        """Fill ``rect`` with ``spec``; tile is anchored to ``rect.topLeft()``."""
        prev_origin = painter.brushOrigin()
        painter.setBrushOrigin(rect.topLeft().toPoint())
        try:
            painter.fillRect(rect, spec.brush())
        finally:
            painter.setBrushOrigin(prev_origin)


# Register the built-in tile-painters into the registry.
for _name, _fn in (
    ("diagonal", PatternRegistry._paint_diagonal),
    ("crosshatch", PatternRegistry._paint_crosshatch),
    ("vstripes", PatternRegistry._paint_vstripes),
    ("hstripes", PatternRegistry._paint_hstripes),
    ("dots", PatternRegistry._paint_dots),
    ("grid", PatternRegistry._paint_grid),
):
    PatternRegistry.register_pattern(_name, _fn)
