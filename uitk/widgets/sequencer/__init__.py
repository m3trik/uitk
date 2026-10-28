# coding=utf-8
"""NLE-style timeline sequencer widget.

Public API for the sequencer package.  See root ``uitk.__init__`` for
top-level registration via ``DEFAULT_INCLUDE``.

>>> from uitk.widgets.sequencer import SequencerWidget
>>> w = SequencerWidget()

The re-exports resolve lazily (``pythontk``'s ``lazy_exports``, the one
subpackage idiom -- CODE_STANDARD section 4). ``uitk/__init__.py`` bootstraps through
``pythontk``'s module resolver, whose ``pkgutil.walk_packages`` scan
imports every subpackage ``__init__`` -- so eager
``from uitk.widgets.sequencer._sequencer import ...`` here charged the
whole ~6k-line timeline tree (and the widgets it pulls) to every plain
``import uitk`` in the ecosystem, whether or not a sequencer was ever
shown. Names and import forms are unchanged; only the moment the
implementation module loads is.
"""

from pythontk.core_utils.module_resolver import lazy_exports

# Public name -> submodule it lives on.  The ``_``-prefixed layout constants
# and item classes are this package's own internals, listed for its tests.
lazy_exports(
    globals(),
    {
        "_data": (
            "ClipData",
            "TrackData",
            "MarkerData",
            "RowMetrics",
            "_TRACK_HEIGHT",
            "_SUB_ROW_HEIGHT",
            "_TRACK_PADDING",
            "_RULER_HEIGHT",
            "_HANDLE_WIDTH",
            "_MIN_CLIP_DURATION",
            "_MIN_POINT_CLIP_WIDTH",
            "SELECTED_ACCENT",
            "DISPLAY_COLORS",
            "_MENU_STYLESHEET",
            "MenuUtils",
            "CurveUtils",
            "HATCH_DENSE",
            "HATCH_MEDIUM",
            "HATCH_SPARSE",
            "PatternSpec",
            "PatternPainter",
            "PatternRegistry",
        ),
        "_drag_tooltip": "FrameTooltip",
        "_draggable": ("DraggableItemMixin", "ItemRetirement"),
        # The content-area seam: a host subclasses SequencerEditor for
        # ``SequencerWidget.register_editor``.
        "_editor": ("SequencerEditor", "TrackEditor"),
        # The timeline seam: a host's layer (a lane, its items) for
        # ``SequencerWidget.add_layer`` -- the protocol it is read through.
        "_layer": "SequencerLayer",
        "_graph_editor": "GraphEditor",
        "_clip": "ClipItem",
        "_keyframe": ("KeyframeItem", "TangentHandleItem", "KeyScaleBoxItem"),
        "_overlays": (
            "_StaticRangeOverlay",
            "_SnapGuideItem",
            "RangeHighlightItem",
        ),
        "_ruler": "RulerItem",
        "_playhead": "PlayheadItem",
        "_markers": "MarkerItem",
        "_timeline": (
            "_ElidingLabel",
            "TrackHeaderWidget",
            "TimelineScene",
            "TimelineView",
        ),
        "_sequencer": ("AttributeColorDialog", "SequencerWidget"),
        "_scrub_player": "ScrubPlayer",
        "_transport_controls": (
            "TransportControls",
            "ScrubPlayerPlayController",
            "PlayController",
        ),
    },
)
