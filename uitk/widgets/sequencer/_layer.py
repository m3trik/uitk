# !/usr/bin/python
# coding=utf-8
"""Layers: a host's vocabulary on the timeline -- the seam a domain plugs into.

:class:`~uitk.widgets.sequencer._sequencer.SequencerWidget` knows tracks,
clips, keys, markers, ranges and the ruler, and names no domain.  What a host
draws over them in its own terms -- tentacle's Shot Sequencer: a lane of shots
under the ruler and the gaps between them -- is a *layer*, added with
:meth:`SequencerWidget.add_layer`.  A layer may own a lane, a strip of
:attr:`SequencerLayer.lane_height` pixels under the ruler (lanes stack in the
order their layers were added, and the content area clears them all), and
scene items it puts under the track rows (``SequencerWidget.add_track_item``,
built from the same parts as the widget's own: ``HeldGeometryMixin``,
``DraggableItemMixin``, ``FrameTooltip``).

The widget offers a layer, in the order layers were added:

- every press on the timeline after the active editor's and the middle-button
  pan (:meth:`~SequencerLayer.mouse_press`); one it takes sends the gesture's
  moves and release to it, as an editor's does;
- each hover, after the active editor's;
- the legend group under the pointer, before the widget's own;
- the data the widget describes itself with, to edit: the legend rows, the
  timeline menu's entries, and the zone a right-click reports;
- the range highlight's edge presses its own items lie under, the scroll
  extent, a re-layout, and a clear.

Every hook is optional -- a layer leaves out what it does not do, and a
missing hook is the default its docstring names -- and a layer need not
subclass :class:`SequencerLayer`: it is the protocol, for reading and type
checking.  With no layer added the widget is the plain timeline: the ruler
alone above the rows.
"""

from typing import TYPE_CHECKING, Dict, List, Optional, Protocol, Sequence, Tuple

from qtpy import QtCore, QtGui

if TYPE_CHECKING:
    from uitk.widgets.sequencer._sequencer import SequencerWidget

#: ``(group, keys, what it does)`` -- a legend row (``SequencerEditor.gestures``).
Gesture = Tuple[str, str, str]


class SequencerLayer(Protocol):
    """What :meth:`SequencerWidget.add_layer` reads off a layer (module docstring)."""

    #: Registry name (:meth:`SequencerWidget.layer`), and the zone a press or
    #: right-click on its lane reports (``TimelineView.hit_zone``,
    #: ``zone_context_menu_requested``).  The one required attribute.
    name: str
    #: The lane's height under the ruler, in pixels; 0 (or absent): no lane.
    #: Read when the layer is added.
    lane_height: int

    def paint_lane(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        """Paint the lane into *rect*: its strip, in scene coordinates, as wide
        as the visible span.  The painter's state is restored afterwards."""

    def mouse_press(self, event) -> bool:
        """A press on the timeline (view coordinates); True takes the gesture:
        its moves and release come here, and the widget does nothing else
        with them.  Default: False."""

    def mouse_move(self, event) -> bool:
        """A taken gesture's move, or a hover (after the active editor's);
        True on a hover ends it there.  Default: False."""

    def mouse_release(self, event) -> bool:
        """A taken gesture's release; True: handled, False lets the widget
        handle it as its own.  Default: False."""

    def gesture_group_at(self, viewport_pos) -> Optional[str]:
        """The legend group under the pointer, or ``None`` for the widget's."""

    def claims_press(self, scene_pos) -> bool:
        """Whether a press at *scene_pos* on the range highlight's edge belongs
        to an item of this layer drawn there instead.  Default: False."""

    def legend(self, editor: str, rows: Tuple[Gesture, ...]) -> Sequence[Gesture]:
        """The legend rows to show while the *editor* named is active, given
        the editor's (as the layers before this one edited them).  Default:
        *rows*."""

    def context_entries(
        self, time: float, entries: List[Optional[dict]]
    ) -> List[Optional[dict]]:
        """The timeline menu's entries at *time*, given the widget's
        (``TimelineView.default_context_entries``: dicts with a ``key``,
        ``None`` a separator).  Default: *entries*."""

    def menu_zone(self, zone: str, time: float) -> str:
        """The zone a right-click at *time* reports, given the strip it landed
        in (``"ruler"``, a lane's name, ``"tracks"``).  Default: *zone*."""

    def time_bounds(self) -> Optional[Tuple[float, float]]:
        """``(t0, t1)`` of what this layer draws, so the scroll extent reaches
        it (``SequencerWidget.refresh_extent`` after it changes); ``None``:
        nothing."""

    def relayout(self) -> None:
        """Re-place this layer's items: the zoom, the rows or the viewport
        changed."""

    def clear(self) -> None:
        """Drop what this layer shows: the widget was cleared
        (``clear``, ``clear_decorations``), or another layer took its name."""


class _LayerRegistry:
    """The layers (the protocol above) in the order they were added, the lanes
    they stack under the ruler, and the header's height -- the ruler and
    every lane -- that the content starts below, *ruler_height* the
    ruler's own."""

    def __init__(self, sequencer: "SequencerWidget", ruler_height: float):
        self._sequencer = sequencer
        self.ruler_height = float(ruler_height)
        #: name -> layer (:meth:`SequencerWidget.add_layer`), in the order
        #: they were added.
        self.layers: Dict[str, SequencerLayer] = {}
        #: ``[(layer, lane height), ...]`` top to bottom under the ruler, and
        #: the y the content starts at below them: read on every paint and
        #: press, so kept rather than derived.
        self.lane_stack: List[Tuple[SequencerLayer, int]] = []
        self.header_height: float = self.ruler_height

    def add(self, layer: SequencerLayer) -> None:
        previous = self.layers.get(layer.name)
        if previous is not None and previous is not layer:
            clear = getattr(previous, "clear", None)
            if clear is not None:
                clear()
        self.layers[layer.name] = layer  # a taken name keeps its place
        self.restack()

    def restack(self) -> None:
        """Re-stack the lanes and re-lay the header, the content and the
        legend out after a layer came or went."""
        sq = self._sequencer
        heights = (
            (layer, int(getattr(layer, "lane_height", 0) or 0))
            for layer in self.layers.values()
        )
        self.lane_stack = [(layer, h) for layer, h in heights if h > 0]
        self.header_height = self.ruler_height + sum(h for _lyr, h in self.lane_stack)
        top = int(self.header_height)
        sq._header.set_top_margin(top)
        sq._timeline._scene.ruler.set_height(self.header_height)
        sq._options_band.sync_geometry()
        sq._apply_legend()
        sq._timeline._refresh_all()

    def clear(self) -> None:
        """Each layer drops what it shows (:meth:`SequencerWidget.clear`,
        :meth:`SequencerWidget.clear_decorations`)."""
        for layer in self.layers.values():
            clear = getattr(layer, "clear", None)
            if clear is not None:
                clear()

    def relayout(self) -> None:
        """Each layer re-places its items (the rows changed)."""
        for layer in self.layers.values():
            relayout = getattr(layer, "relayout", None)
            if relayout is not None:
                relayout()

    def claims_press(self, scene_pos) -> bool:
        for layer in self.layers.values():
            claims = getattr(layer, "claims_press", None)
            if claims is not None and claims(scene_pos):
                return True
        return False
