# !/usr/bin/python
# coding=utf-8
"""Editors: what the sequencer's content area shows -- the seam a view plugs into.

:class:`~uitk.widgets.sequencer._sequencer.SequencerWidget` is the kernel:
the time axis, the ruler and the layers' lanes under it, the playhead and
markers, the shortcut table and its legend.  An *editor* owns the content
area below the header: its scene items (under one :attr:`SequencerEditor.content_root`,
so a single switch shows or hides them), the left pane's page, the content's
vertical extent and background, the mouse and keys it answers there, and the
verbs the window drives (frame, frame all...).

The kernel offers every content-area event to the ACTIVE editor first and
falls back to its own handling, which IS the track editor's behaviour -- so
:class:`TrackEditor` is today's rows unchanged, and another editor (the
graph editor, ``_graph_editor.py``) takes the area over by answering what it
changes.  Each hook's default here is "not handled".
"""

from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from qtpy import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from uitk.widgets.sequencer._sequencer import SequencerWidget

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
        (clips, markers, ranges, the layers'), or ``None``: the timeline's scroll extent
        takes it in, so framing and panning reach it."""
        return None

    def key_times(self) -> Optional[List[float]]:
        """The sorted key times next / previous key steps through, or
        ``None`` for the kernel's own (the track rows' clips and keys)."""
        return None

    # -- verbs the window drives -----------------------------------------------

    def frame_values(self) -> None:
        """Fit the vertical axis to what the framed time range shows (the
        kernel has just framed time: the active range, the content, a span)."""


class TrackEditor(SequencerEditor):
    """The track rows: clips, expanded attribute rows, keys and range overlays.

    The kernel's own content handling is this editor's behaviour; what lives
    here is what makes the rows one editor among others -- their content root
    and their legend.
    """

    name = "tracks"
    label = "Tracks"
    #: The mouse grammar, as the shortcut overlay shows it: ``(group, keys,
    #: what it does)``.  A host's layer edits it for its own gestures and
    #: wording (``SequencerLayer.legend``).  A tangent handle reads the same
    #: three modifiers on the key selection it is part of
    #: (:class:`~uitk.widgets.sequencer._keyframe.TangentHandleItem`).
    gestures = (
        ("Clips & keys", "Drag", "Move keys (ripple)"),
        ("Clips & keys", "Drag edge", "Scale the clip's keys"),
        ("Clips & keys", "Drag edge (multi)", "Scale the whole selection as one"),
        ("Clips & keys", "Shift (keys selected)", "Scale box: drag an end to retime"),
        ("Clips & keys", "Alt+Drag a scale end", "Scale about the playhead instead"),
        ("Clips & keys", "Ctrl", "Snap to whole frames"),
        ("Clips & keys", "Right-click", "Lock, rename"),
        ("Tangents", "Drag a handle", "Reshape every selected key's tangent"),
        ("Tangents", "Ctrl+Drag", "Reshape the grabbed key only"),
        ("Tangents", "Shift+Drag", "Give every selected key this exact tangent"),
        ("Tangents", "Alt+Drag", "Break the tangent (dotted while held)"),
        ("Timeline", "Drag", "Marquee select (Space moves it)"),
        ("Timeline", "Wheel / Middle-drag", "Zoom / pan"),
    )

    def __init__(self, sequencer):
        super().__init__(sequencer)
        sequencer.add_flat_spans_option(self)  # the clips' and rows' curves


class _EditorRegistry:
    """The editors the content area can show (the classes above): each built on
    first use from the factory registered for it, and the one shown now."""

    def __init__(self, sequencer: "SequencerWidget"):
        self._sequencer = sequencer
        #: name -> editor instance, or the factory that builds it on first use
        #: (the graph editor's module loads only when it is first shown).
        self.editors: Dict[str, object] = {}
        self.active_name = TrackEditor.name

    @staticmethod
    def graph_editor_factory(sequencer) -> SequencerEditor:
        """Build the graph editor; its module loads on first use only."""
        from uitk.widgets.sequencer._graph_editor import GraphEditor

        return GraphEditor(sequencer)

    def register(self, name: str, factory) -> None:
        if isinstance(self.editors.get(name), SequencerEditor):
            raise ValueError(f"The {name!r} editor is already built.")
        self.editors[name] = factory

    def get(self, name: str) -> SequencerEditor:
        sq = self._sequencer
        entry = self.editors[name]
        if not isinstance(entry, SequencerEditor):
            entry = self.editors[name] = entry(sq)
            # Its page is the pane's from the start: a page first parented
            # when the editor is shown was a top-level the editor's Python
            # side alone held, destroyed by whichever garbage collection
            # reached it after the sequencer was gone -- mid-way through
            # another widget's events.
            page = entry.header_widget()
            if page is not None and sq._header_stack.indexOf(page) < 0:
                sq._header_stack.addWidget(page)
        return entry

    def show(self, name: str) -> None:
        sq = self._sequencer
        if name == self.active_name:
            return
        new = sq.editor(name)
        old = sq.active_editor
        sq._selection_suppressed += 1
        try:
            old.deactivate()
            self.active_name = name
            new.activate()
            sq._apply_legend(new)
        finally:
            sq._selection_suppressed -= 1
        page = new.header_widget() or sq._header_scroll
        if sq._header_stack.indexOf(page) < 0:
            sq._header_stack.addWidget(page)
        sq._header_stack.setCurrentWidget(page)
        sq._editor_keys = {
            QtGui.QKeySequence(key).toString(): {"action": fn, "description": desc}
            for key, fn, desc in new.key_bindings()
        }
        sq._sync_shortcut_sequences()
        sq._timeline._refresh_all()
        sq.editor_changed.emit(name)
