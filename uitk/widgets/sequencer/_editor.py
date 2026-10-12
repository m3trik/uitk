# !/usr/bin/python
# coding=utf-8
"""Editors: what the sequencer's content area shows -- the seam a view plugs into.

:class:`~uitk.widgets.sequencer._sequencer.SequencerWidget` is the kernel:
the time axis, the ruler and shot lane, the playhead and markers, the
shortcut table and its legend.  An *editor* owns the content area below the
shot lane: its scene items (under one :attr:`SequencerEditor.content_root`,
so a single switch shows or hides them), the left pane's page, the content's
vertical extent and background, the mouse and keys it answers there, and the
verbs the window drives (frame, frame all...).

The kernel offers every content-area event to the ACTIVE editor first and
falls back to its own handling, which IS the track editor's behaviour -- so
:class:`TrackEditor` is today's rows unchanged, and another editor (the
graph editor, ``_graph_editor.py``) takes the area over by answering what it
changes.  Each hook's default here is "not handled".
"""

from typing import Callable, List, Optional, Tuple

from qtpy import QtCore, QtWidgets

#: ``(group, keys, what it does)`` -- a gesture legend row.
Gesture = Tuple[str, str, str]
#: ``(key sequence, action, description)`` -- a key an editor answers.
KeyBinding = Tuple[str, Callable[[], None], str]


class _ContentRoot(QtWidgets.QGraphicsObject):
    """An invisible parent for one editor's scene items.

    No contents and an empty bounding rect, so it is never hit, never
    painted and never in a marquee; hiding it hides every child at once.
    It sits at the scene origin with no transform, so a child's scene
    coordinates are unchanged by the parenting.
    """

    def __init__(self):
        super().__init__()
        self.setFlag(QtWidgets.QGraphicsItem.ItemHasNoContents, True)

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF()

    def paint(self, painter, option, widget=None) -> None:
        pass


class SequencerEditor(QtCore.QObject):
    """Base of the editors a :class:`SequencerWidget` hosts (module docstring).

    Parameters:
        sequencer: The hosting ``SequencerWidget`` (the kernel).
    """

    #: Registry name (``SequencerWidget.set_editor(name)``).
    name: str = ""
    #: Display name.
    label: str = ""
    #: The legend rows shown while this editor is active.
    gestures: Tuple[Gesture, ...] = ()

    def __init__(self, sequencer):
        super().__init__(sequencer)
        self.sequencer = sequencer
        self.content_root = _ContentRoot()
        self.content_root.setVisible(False)
        sequencer._timeline._scene.addItem(self.content_root)
        self._options: dict = {}

    # -- options: the header pane's Options combobox -------------------------------

    def add_option(
        self,
        key: str,
        label: str,
        getter,
        setter,
        tooltip: str = "",
        section: str = "",
    ) -> None:
        """Add a row to this editor's Options (the header pane's band).

        A checkbox reading ``getter()`` and writing ``setter(bool)`` -- the
        per-editor (per-plugin) settings, kept out of the way until asked
        for -- under its *section*'s title (none: above the titled ones).
        Adding *key* again replaces it, so a host re-init re-registers
        without duplicates.
        """
        self._options[key] = {
            "key": key,
            "label": label,
            "get": getter,
            "set": setter,
            "tooltip": tooltip,
            "section": section,
        }

    def options(self) -> List[dict]:
        """``[{"key", "label", "get", "set", "tooltip", "section"}, ...]`` in
        the order added."""
        return list(self._options.values())

    # -- lifecycle -------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self.sequencer.active_editor is self

    def activate(self) -> None:
        """Show this editor's items; the kernel then re-lays everything out."""
        self.content_root.setVisible(True)

    def deactivate(self) -> None:
        """Hide this editor's items (the kernel suppresses the selection
        signals the hiding raises)."""
        self.content_root.setVisible(False)

    def header_widget(self) -> Optional[QtWidgets.QWidget]:
        """The left pane's page while active; ``None`` keeps the track header."""
        return None

    def key_bindings(self) -> List[KeyBinding]:
        """Keys this editor answers before the kernel's shortcut table."""
        return []

    # -- the content area (events arrive in view coordinates) ------------------

    def mouse_press(self, event) -> bool:
        """A press in the content area; True takes the gesture (its moves and
        release come here too)."""
        return False

    def mouse_move(self, event) -> bool:
        """A move: a taken gesture's, or a hover in the content area."""
        return False

    def mouse_release(self, event) -> bool:
        return False

    def mouse_double_click(self, event) -> bool:
        return False

    def wheel(self, event) -> bool:
        return False

    def context_menu(self, event) -> bool:
        return False

    def gesture_group_at(self, viewport_pos) -> Optional[str]:
        """The legend group under the pointer, or ``None`` for the kernel's."""
        return None

    # -- layout ----------------------------------------------------------------

    def relayout(self) -> None:
        """Re-place this editor's items after a time-axis or size change."""

    def draw_background(self, painter, rect) -> bool:
        """Paint the content area's background; True replaces the track rows."""
        return False

    def content_height(self) -> Optional[float]:
        """The content's height in scene units, or ``None`` for the rows'."""
        return None

    def time_bounds(self) -> Optional[Tuple[float, float]]:
        """``(t0, t1)`` this editor's content spans beyond the kernel's own
        (clips, shots, markers), or ``None``: the timeline's scroll extent
        takes it in, so framing and panning reach it."""
        return None

    def key_times(self) -> Optional[List[float]]:
        """The sorted key times next / previous key steps through, or
        ``None`` for the kernel's own (the track rows' clips and keys)."""
        return None

    # -- verbs the window drives -----------------------------------------------

    def frame_values(self) -> None:
        """Fit the vertical axis to what the framed time range shows (the
        kernel has just framed time: a shot, the content, a range)."""


class TrackEditor(SequencerEditor):
    """The track rows: clips, expanded attribute rows, keys and shot overlays.

    The kernel's own content handling is this editor's behaviour; what lives
    here is what makes the rows one editor among others -- their content root
    and their legend.
    """

    name = "tracks"
    label = "Tracks"
    #: The mouse grammar, as the consumers implement it and the shortcut overlay
    #: shows it: ``(group, keys, what it does)``.  A shot's own bound (its edges,
    #: the ruler band's edges) never moves the shot's keys: a plain drag moves
    #: the bound and the neighbouring shots ripple with their keys to keep the
    #: gaps; Ctrl moves the bound and nothing else (the shot grows into the gap
    #: over the keys there, or shrinks and leaves keys for the next shot); Shift
    #: retimes the keys into the new span.  The ruler band's body moves the shot.
    #: A gap's edge belongs to the shot beyond it: a plain drag slides that shot.
    #: A tangent handle reads the same three modifiers on the key selection it is
    #: part of (:class:`~uitk.widgets.sequencer._keyframe.TangentHandleItem`).
    gestures = (
        ("Shot bounds", "Drag", "Move the bound; neighbours ripple (keys stay)"),
        ("Shot bounds", "Ctrl+Drag", "Move the bound only; a neighbour's gives way"),
        ("Shot bounds", "Shift+Drag", "Retime keys into the new span"),
        ("Shot bounds", "Alt+Drag", "Resize about the shot's centre"),
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
        ("Tangents", "Drag a handle", "Reshape every selected key's tangent"),
        ("Tangents", "Ctrl+Drag", "Reshape the grabbed key only"),
        ("Tangents", "Shift+Drag", "Give every selected key this exact tangent"),
        ("Tangents", "Alt+Drag", "Break the tangent (dotted while held)"),
        ("Timeline", "Drag", "Marquee select (Space moves it)"),
        ("Timeline", "Ctrl+Shift+Click", "Switch to the shot under the cursor"),
        ("Timeline", "Wheel / Middle-drag", "Zoom / pan"),
    )

    def __init__(self, sequencer):
        super().__init__(sequencer)
        sequencer.add_flat_spans_option(self)  # the clips' and rows' curves
