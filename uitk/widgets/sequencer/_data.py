# !/usr/bin/python
# coding=utf-8
"""Data models and shared constants for the sequencer widget."""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from qtpy import QtWidgets, QtGui, QtCore


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
        return pattern_brush(self.style, c, self.spacing, self.line_width)


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


@dataclass
class TrackData:
    """Lightweight data record for a track row."""

    track_id: int
    name: str
    color: Optional[str] = None
    text_color: Optional[str] = None
    clips: List[int] = field(default_factory=list)
    pattern: Optional[PatternSpec] = None


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


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
_TRACK_HEIGHT = 28
_SUB_ROW_HEIGHT = 22  # default height for expanded attribute sub-rows
_TRACK_PADDING = 2
_RULER_HEIGHT = 24
_SHOT_LANE_HEIGHT = 12  # height of the always-visible shot block lane
_HANDLE_WIDTH = 5  # pixels from edge that activates resize cursor
_MIN_CLIP_DURATION = 1.0
_MIN_POINT_CLIP_WIDTH = 4  # minimum pixel width for zero-duration clips
_DEFAULT_CLIP_COLORS = [
    "#5B8BD4",
    "#6EBF6E",
    "#D4A65B",
    "#C45C5C",
    "#8E6FBF",
    "#5BBFB4",
    "#BF6E8E",
    "#8EB05B",
]

# Attribute color configuration
_COMMON_ATTRIBUTES = [
    "translateX",
    "translateY",
    "translateZ",
    "rotateX",
    "rotateY",
    "rotateZ",
    "scaleX",
    "scaleY",
    "scaleZ",
    "visibility",
]

_DISPLAY_COLORS = [
    "consolidated",
]

_MENU_STYLESHEET = (
    "QMenu { background:#333; color:#CCC; }" "QMenu::item:selected { background:#555; }"
)


def _styled_menu(parent=None) -> QtWidgets.QMenu:
    """Create a QMenu with the sequencer's standard dark stylesheet."""
    menu = QtWidgets.QMenu(parent)
    menu.setStyleSheet(_MENU_STYLESHEET)
    return menu


def _menu_exec_pos(event) -> QtCore.QPoint:
    """Return a screen position suitable for ``QMenu.exec_``."""
    if hasattr(event, "screenPos"):
        return event.screenPos()
    return QtGui.QCursor.pos()


_DEFAULT_ATTRIBUTE_COLORS = {
    "translateX": "#E06666",
    "translateY": "#6AA84F",
    "translateZ": "#6FA8DC",
    "rotateX": "#CC4125",
    "rotateY": "#38761D",
    "rotateZ": "#3D85C6",
    "scaleX": "#F6B26B",
    "scaleY": "#93C47D",
    "scaleZ": "#76A5AF",
    "visibility": "#FFD966",
    "consolidated": "#FFFFFF",
}


# ---------------------------------------------------------------------------
#  Background fill patterns — registry + cached brushes
# ---------------------------------------------------------------------------
# Spacing tiers (HATCH_DENSE / MEDIUM / SPARSE) live near the top of the file
# so PatternSpec can reference them as defaults.

# A pattern painter draws one tile of side ``size`` onto the given QPainter.
PatternPainter = Callable[[QtGui.QPainter, int, QtGui.QColor, float], None]

_pattern_painters: Dict[str, PatternPainter] = {}


def register_pattern(name: str, painter: PatternPainter) -> None:
    """Register (or override) a tile-painter for :func:`pattern_brush`."""
    _pattern_painters[name] = painter


def _paint_diagonal(p, size, color, lw):
    p.setPen(QtGui.QPen(color, lw))
    p.drawLine(0, size, size, 0)


def _paint_crosshatch(p, size, color, lw):
    pen = QtGui.QPen(color, lw)
    p.setPen(pen)
    p.drawLine(0, size, size, 0)
    p.drawLine(0, 0, size, size)


def _paint_vstripes(p, size, color, lw):
    p.setPen(QtGui.QPen(color, lw))
    p.drawLine(0, 0, 0, size)


def _paint_hstripes(p, size, color, lw):
    p.setPen(QtGui.QPen(color, lw))
    p.drawLine(0, 0, size, 0)


def _paint_dots(p, size, color, lw):
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(color)
    radius = max(0.5, lw)
    c = size / 2.0
    p.drawEllipse(QtCore.QPointF(c, c), radius, radius)


def _paint_grid(p, size, color, lw):
    p.setPen(QtGui.QPen(color, lw))
    p.drawLine(0, 0, size, 0)
    p.drawLine(0, 0, 0, size)


for _name, _fn in (
    ("diagonal", _paint_diagonal),
    ("crosshatch", _paint_crosshatch),
    ("vstripes", _paint_vstripes),
    ("hstripes", _paint_hstripes),
    ("dots", _paint_dots),
    ("grid", _paint_grid),
):
    register_pattern(_name, _fn)


_pattern_cache: Dict[tuple, QtGui.QBrush] = {}
_PATTERN_CACHE_MAX = 128


def pattern_brush(
    style: str,
    color: QtGui.QColor,
    spacing: int = HATCH_MEDIUM,
    line_width: float = 1.0,
) -> QtGui.QBrush:
    """Return a cached tiled brush for the registered ``style`` (``line_width`` doubles as dot radius for ``"dots"``)."""
    key = (style, color.rgba(), spacing, line_width)
    brush = _pattern_cache.get(key)
    if brush is not None:
        return brush
    painter_fn = _pattern_painters.get(style)
    if painter_fn is None:
        raise KeyError(
            f"Unknown pattern style {style!r}. "
            f"Registered: {sorted(_pattern_painters)}"
        )
    tile = QtGui.QPixmap(spacing, spacing)
    tile.fill(QtCore.Qt.transparent)
    tp = QtGui.QPainter(tile)
    try:
        painter_fn(tp, spacing, color, line_width)
    finally:
        tp.end()
    brush = QtGui.QBrush(tile)
    if len(_pattern_cache) >= _PATTERN_CACHE_MAX:
        _pattern_cache.pop(next(iter(_pattern_cache)))
    _pattern_cache[key] = brush
    return brush


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
