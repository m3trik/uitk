# !/usr/bin/python
# coding=utf-8
"""What is selected on a :class:`~uitk.widgets.sequencer._sequencer.SequencerWidget`'s
timeline and the key edits made on it -- the key menu, Delete, the Shift scale
box: parts the widget holds and publishes (``_sequencer.py``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from qtpy import QtWidgets

from uitk.widgets.sequencer._clip import ClipItem
from uitk.widgets.sequencer._data import MenuUtils
from uitk.widgets.sequencer._draggable import ItemRetirement
from uitk.widgets.sequencer._timeline import _SHIFT_MOD

if TYPE_CHECKING:
    from uitk.widgets.sequencer._sequencer import SequencerWidget


class _Selection:
    """What is selected on the timeline, as the widget reports it -- the
    clips, and the keys grouped by clip -- the key edits made on it (the
    key menu, Delete), and the guard that keeps a programmatic rebuild from
    reading as the user deselecting."""

    def __init__(self, sequencer: "SequencerWidget"):
        self._sequencer = sequencer
        # >0 while the widget is being rebuilt programmatically: the scene's
        # selectionChanged fires as items are torn down, and forwarding that
        # empty selection makes consumers clear the host app's own selection
        # on every refresh (see on_scene_selection).
        self.suppressed: int = 0

    def clips(self) -> List[int]:
        try:
            items = self._sequencer._timeline._scene.selectedItems()
        except RuntimeError:
            return []
        return [item.clip_data.clip_id for item in items if isinstance(item, ClipItem)]

    def keys(self) -> List[dict]:
        from uitk.widgets.sequencer._keyframe import KeyframeItem

        try:
            items = self._sequencer._timeline._scene.selectedItems()
        except RuntimeError:
            return []
        by_clip: dict = {}
        for item in items:
            if isinstance(item, KeyframeItem):
                cid = item._parent_clip._data.clip_id
                by_clip.setdefault(cid, {"clip_id": cid, "times": []})
                by_clip[cid]["times"].append(item._time)
        return list(by_clip.values())

    def select_keys(self, wanted: List[dict], replace: bool) -> int:
        sq = self._sequencer
        scene = sq._timeline._scene
        selectable = QtWidgets.QGraphicsItem.ItemIsSelectable
        n = 0
        sq._selection_suppressed += 1
        try:
            if replace:
                scene.clearSelection()
            for item in sq._clip_items.values():
                bag = item._data.data
                for want in wanted:
                    match = want.get("data") or {}
                    if any(bag.get(k) != v for k, v in match.items()):
                        continue
                    times = want.get("times") or []
                    for ki in item._keyframe_items:
                        if not (ki.flags() & selectable):
                            continue
                        if any(abs(ki._time - t) <= 1e-6 for t in times):
                            ki.setSelected(True)
                            n += 1
        finally:
            sq._selection_suppressed -= 1
        sq._on_scene_selection()
        return n

    def on_scene_selection(self) -> None:
        """The scene's selection changed: report it, unless a rebuild is
        running."""
        sq = self._sequencer
        if sq._selection_suppressed:
            # Programmatic rebuild, not a user gesture.  Forwarding it would
            # make consumers mirror an empty selection into the host app --
            # the "I can't keep anything selected" symptom when something
            # refreshes the panel repeatedly.
            return
        sel = sq.selected_clips()
        sq.selection_changed.emit(sel)
        # Backwards-compat: also emit clip_selected for the first item
        if sel:
            sq.clip_selected.emit(sel[0])

        # Emit key-level selection info for graph-editor sync.
        sq.key_selection_changed.emit(sq.selected_keys())
        # The Shift scale box brackets the SELECTION, so it follows it.
        sq.refresh_key_scale_box()

    def show_key_menu(self, global_pos) -> bool:
        sq = self._sequencer
        groups = self.editable_key_groups()
        if not groups:
            return False
        menu = MenuUtils.styled_menu()
        sq.key_menu_requested.emit(menu, groups)
        if not menu.actions():
            return False
        menu.exec_(global_pos)
        return True

    def editable_key_groups(self) -> List[dict]:
        """:meth:`SequencerWidget.selected_keys` minus the clips that refuse
        key edits.

        What the key menu offers and what Delete acts on: both are built
        from the SELECTION, which a marquee can sweep across a locked or
        read-only row (:attr:`ClipItem.keys_editable`) that must not be
        written to.
        """
        sq = self._sequencer
        groups = []
        for group in sq.selected_keys():
            item = sq._clip_items.get(group["clip_id"])
            if item is None or item.keys_editable:
                groups.append(group)
        return groups

    def delete_selected_keys(self) -> None:
        sq = self._sequencer
        groups = self.editable_key_groups()
        if not groups:
            return

        sq._capture_undo()
        for group in groups:
            sq.keys_deleted.emit(group["clip_id"], group["times"])


class _KeyScaleBox:
    """The Shift scale box around a key selection (``KeyScaleBoxItem``, the
    one gesture that changes a selection's length): up while Shift is held
    over keys a scale means something for, and out of a tangent drag's way."""

    def __init__(self, sequencer: "SequencerWidget"):
        self._sequencer = sequencer
        # Shift + a key selection raises a scale box around it; see
        # ``refresh``.
        self.box = None
        # A tangent handle is being dragged: the Shift scale box answers the
        # same Shift that drag reads, and must stay out of its way.
        self.tangent_drag_active: bool = False

    def scalable_keys(self) -> list:
        from uitk.widgets.sequencer._keyframe import KeyframeItem

        try:
            items = self._sequencer._timeline._scene.selectedItems()
        except RuntimeError:
            return []
        return [
            item
            for item in items
            if isinstance(item, KeyframeItem) and item._parent_clip.keys_editable
        ]

    @staticmethod
    def span(keys) -> Optional[tuple]:
        """``(lo, hi, top, bottom)`` the scale box should bracket, or None.

        None whenever a scale is meaningless -- fewer than two keys, or every
        key on one frame, where no ratio exists to scale by.
        """
        times = [k._time for k in keys]
        if len(keys) < 2 or (max(times) - min(times)) < 1e-6:
            return None
        tops, bottoms = [], []
        for k in keys:
            rect = k._parent_clip.rect()
            tops.append(rect.top())
            bottoms.append(rect.bottom())
        return min(times), max(times), min(tops), max(bottoms)

    def refresh(self) -> None:
        from uitk.widgets.sequencer._keyframe import KeyScaleBoxItem

        sq = self._sequencer
        box = self.box
        if box is not None and box._is_drag_active():
            return
        span = None
        if sq.modifiers_held & _SHIFT_MOD and not self.tangent_drag_active:
            span = self.span(sq._scalable_keys())
        if span is None:
            sq.clear_key_scale_box()
            return
        if box is None:
            box = self.box = KeyScaleBoxItem(sq)
            sq.add_track_item(box)
        box.set_span(*span)

    def clear(self) -> None:
        box = self.box
        if box is None:
            return
        box.cancel_drag()
        ItemRetirement.retire(box)
        self.box = None
