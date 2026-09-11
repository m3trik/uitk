# coding=utf-8
"""NLE-style timeline sequencer widget.

Public API for the sequencer package.  See root ``uitk.__init__`` for
top-level registration via ``DEFAULT_INCLUDE``.

>>> from uitk.widgets.sequencer import SequencerWidget
>>> w = SequencerWidget()

The re-exports resolve lazily (PEP 562 module ``__getattr__``, same shape
as :mod:`uitk.switchboard`). ``uitk/__init__.py`` bootstraps through
``pythontk``'s module resolver, whose ``pkgutil.walk_packages`` scan
imports every subpackage ``__init__`` -- so eager
``from uitk.widgets.sequencer._sequencer import ...`` here charged the
whole ~6k-line timeline tree (and the widgets it pulls) to every plain
``import uitk`` in the ecosystem, whether or not a sequencer was ever
shown. Names and import forms are unchanged; only the moment the
implementation module loads is.
"""

# Public name -> submodule it lives on, grouped by submodule so this block
# stays a 1:1 reading of the old import list.
_EXPORT_SOURCES = {
    "_data": (
        "ClipData",
        "TrackData",
        "MarkerData",
        "_TRACK_HEIGHT",
        "_SUB_ROW_HEIGHT",
        "_TRACK_PADDING",
        "_RULER_HEIGHT",
        "_SHOT_LANE_HEIGHT",
        "_HEADER_HEIGHT",
        "_HANDLE_WIDTH",
        "_MIN_CLIP_DURATION",
        "_MIN_POINT_CLIP_WIDTH",
        "SELECTED_ACCENT",
        "_COMMON_ATTRIBUTES",
        "_DISPLAY_COLORS",
        "_MENU_STYLESHEET",
        "_DEFAULT_ATTRIBUTE_COLORS",
        "MenuUtils",
        "CurveUtils",
        "HATCH_DENSE",
        "HATCH_MEDIUM",
        "HATCH_SPARSE",
        "PatternSpec",
        "PatternPainter",
        "PatternRegistry",
    ),
    "_drag_tooltip": ("FrameTooltip",),
    "_draggable": ("DraggableItemMixin", "ItemRetirement"),
    "_clip": ("ClipItem",),
    "_keyframe": ("KeyframeItem", "TangentHandleItem", "KeyScaleHandleItem"),
    "_overlays": (
        "_StaticRangeOverlay",
        "_GapOverlayItem",
        "_SnapGuideItem",
        "RangeHighlightItem",
    ),
    "_ruler": ("RulerItem",),
    "_playhead": ("PlayheadItem",),
    "_markers": ("MarkerItem",),
    "_timeline": (
        "_ElidingLabel",
        "TrackHeaderWidget",
        "TimelineScene",
        "TimelineView",
    ),
    "_sequencer": (
        "AttributeColorDialog",
        "SequencerWidget",
    ),
    "_scrub_player": ("ScrubPlayer",),
    "_transport_controls": (
        "TransportControls",
        "ScrubPlayerPlayController",
        "PlayController",
    ),
}

_LAZY = {
    name: module_suffix
    for module_suffix, names in _EXPORT_SOURCES.items()
    for name in names
}

__all__ = sorted(n for n in _LAZY if not n.startswith("_"))


def __getattr__(name):
    try:
        module_suffix = _LAZY[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    import importlib

    module = importlib.import_module(f"{__name__}.{module_suffix}")
    value = getattr(module, name)
    globals()[name] = value  # cache for subsequent accesses
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
