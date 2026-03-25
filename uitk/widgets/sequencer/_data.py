# !/usr/bin/python
# coding=utf-8
"""Data models and shared constants for the sequencer widget."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qtpy import QtWidgets, QtGui, QtCore


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
