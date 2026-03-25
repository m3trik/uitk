# coding=utf-8
"""NLE-style timeline sequencer widget.

Public API for the sequencer package.  See root ``uitk.__init__`` for
top-level registration via ``DEFAULT_INCLUDE``.

>>> from uitk.widgets.sequencer import SequencerWidget
>>> w = SequencerWidget()
"""
from uitk.widgets.sequencer._data import (  # noqa: F401
    ClipData,
    TrackData,
    MarkerData,
    _TRACK_HEIGHT,
    _SUB_ROW_HEIGHT,
    _TRACK_PADDING,
    _RULER_HEIGHT,
    _SHOT_LANE_HEIGHT,
    _HANDLE_WIDTH,
    _MIN_CLIP_DURATION,
    _MIN_POINT_CLIP_WIDTH,
    _DEFAULT_CLIP_COLORS,
    _COMMON_ATTRIBUTES,
    _DISPLAY_COLORS,
    _MENU_STYLESHEET,
    _DEFAULT_ATTRIBUTE_COLORS,
    _styled_menu,
    _menu_exec_pos,
)
from uitk.widgets.sequencer._clip import ClipItem  # noqa: F401
from uitk.widgets.sequencer._overlays import (  # noqa: F401
    _StaticRangeOverlay,
    _GapOverlayItem,
    RangeHighlightItem,
)
from uitk.widgets.sequencer._ruler import ShotLaneItem, RulerItem  # noqa: F401
from uitk.widgets.sequencer._playhead import PlayheadItem  # noqa: F401
from uitk.widgets.sequencer._markers import MarkerItem  # noqa: F401
from uitk.widgets.sequencer._timeline import (  # noqa: F401
    _ElidingLabel,
    TrackHeaderWidget,
    TimelineScene,
    TimelineView,
)
from uitk.widgets.sequencer._sequencer import (  # noqa: F401
    AttributeColorDialog,
    SequencerWidget,
)
