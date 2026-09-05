# !/usr/bin/python
# coding=utf-8
"""Shared drag infrastructure for sequencer graphics items.

Provides:
- :meth:`DraggableItemMixin.snap_time` — unified time-snap helper (Ctrl = per-frame).
- :meth:`ItemRetirement.retire` — remove a scene item without destroying it mid-event.
- :class:`DraggableItemMixin` — template for ``cancel_drag()`` support.
"""

from __future__ import annotations

from qtpy import QtWidgets, QtCore


class ItemRetirement:
    """Deferred destruction for scene items removed mid-event.

    A class rather than two module functions over two module globals: the
    parked-item list and the drain flag ARE this behaviour's state, and the
    ecosystem keeps implementation on a class namespace rather than flat in a
    module (root ``CLAUDE.md``, "Encapsulate").  The state stays class-level,
    not per-instance -- see :attr:`_retired`.
    """

    #: Items removed from a scene but not yet destroyed.  CLASS-level (not
    #: per-widget) so the drain survives the widget itself being torn down.
    _retired: list = []
    #: Whether a drain is already queued, so N retirements cost one timer.
    _drain_scheduled: bool = False

    @classmethod
    def retire(cls, item) -> None:
        """Take *item* out of its scene, destroying it one event-loop pass later.

        Removing a QGraphicsItem drops the scene's ownership, so releasing the
        last Python reference destroys the C++ object then and there.  That is
        fatal when the removal happens INSIDE that item's own event handler —
        a consumer rebuilding the widget from ``mouseReleaseEvent``, or from a
        context-menu action while ``contextMenuEvent`` is still on the stack.
        Qt goes on to touch the item after the handler returns (mouse-grabber
        release, hover recalculation, the handler's own trailing statements),
        and the freed object takes the host application down with it.

        Parking the reference until the next event-loop pass lets Qt finish
        with the item first.  The item is already out of the scene, so it
        neither paints nor receives events in the meantime.
        """
        if item is None:
            return
        scene = item.scene()
        if scene is not None:
            scene.removeItem(item)
        if QtWidgets.QApplication.instance() is None:
            return  # no event loop to come back on, and no dispatch to survive
        cls._retired.append(item)
        if not cls._drain_scheduled:
            cls._drain_scheduled = True
            QtCore.QTimer.singleShot(0, cls._drain)

    @classmethod
    def _drain(cls) -> None:
        # A QMenu popup spins a nested event loop that services timers, so this
        # drain can fire while an item's contextMenuEvent is still on the C++
        # stack — releasing a parked parent there would destroy its children
        # mid-event, the exact crash class this module exists to prevent.  Defer
        # until no popup is live.  (Deliberately NOT deferred on modal dialogs:
        # a sequencer hosted inside one would then never drain at all.)
        if QtWidgets.QApplication.activePopupWidget() is not None:
            QtCore.QTimer.singleShot(50, cls._drain)
            return
        cls._drain_scheduled = False
        cls._retired.clear()


class DraggableItemMixin:
    """Standard Escape-to-cancel support for QGraphicsItems.

    Subclasses override :meth:`_is_drag_active` and :meth:`_restore_drag_state`.
    Items that push an undo snapshot do so lazily on the first real
    mouse move and record it in the instance flag ``_undo_captured`` —
    ``_cancel_active_drag`` pops the snapshot only when that flag is
    set (a press-without-move never captures, so a plain click can't
    burn an undo step or wipe the redo stack).
    """

    _undo_captured: bool = False
    #: Screen position of the press, for :meth:`_past_drag_threshold`.
    _press_screen_pos = None
    #: Whether the press has become a drag (grab cursor + frame label shown).
    _grab_armed: bool = False

    def _past_drag_threshold(self, event) -> bool:
        """True once the pointer has travelled far enough to mean a drag.

        Qt's own ``startDragDistance``, measured in SCREEN pixels rather than
        scene units: a scene-space threshold would be a different physical
        distance at every zoom level, so the same flick of the wrist would
        start a drag zoomed out and not zoomed in.

        Every handle in the package answers the same question — "is this a
        click or a drag yet?" — and answers it to decide the same three
        things: the grab cursor, the floating frame tooltip, and the undo
        snapshot.  ``_press_screen_pos`` unset means the press was not
        recorded, in which case there is nothing to measure from and the
        gesture is treated as a drag (the pre-threshold behaviour).
        """
        origin = self._press_screen_pos
        if origin is None:
            return True
        delta = event.screenPos() - origin
        return delta.manhattanLength() >= QtWidgets.QApplication.startDragDistance()

    @staticmethod
    def snap_time(value: float, timeline) -> float:
        """Snap *value* to the timeline's grid, or to 1 when Ctrl is held."""
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & QtCore.Qt.ControlModifier:
            return round(value)
        interval = timeline.parent_sequencer.snap_interval
        if interval > 0:
            return round(value / interval) * interval
        return value

    def _is_drag_active(self) -> bool:
        raise NotImplementedError

    def _restore_drag_state(self) -> None:
        raise NotImplementedError

    def _drag_sequencer(self):
        """Host SequencerWidget — override where the timeline lives elsewhere."""
        tl = getattr(self, "_timeline", None)
        return tl.parent_sequencer if tl is not None else None

    def sceneEvent(self, event):
        """Cancel the drag when the mouse grab is stolen mid-gesture.

        A popup or a grab handoff (routine in this codebase's marking-menu
        environment) takes the grab without ever delivering a release, so
        the drag state — guides, tooltip, the lazily-captured undo
        snapshot — would persist until the next gesture.  Qt delivers
        ``UngrabMouse`` in both cases, and also after a normal release,
        where the drag state is already cleared and this no-ops.
        """
        if event.type() == QtCore.QEvent.UngrabMouse and self._is_drag_active():
            captured = self._undo_captured
            if self.cancel_drag() and captured:
                # The snapshot recorded a gesture that never committed —
                # leaving it would burn an undo step (mirrors
                # SequencerWidget._cancel_active_drag).
                self._undo_captured = False
                sq = self._drag_sequencer()
                if sq is not None and sq._undo_stack:
                    sq._undo_stack.pop()
        return super().sceneEvent(event)

    def cancel_drag(self) -> bool:
        if not self._is_drag_active():
            return False
        self._restore_drag_state()
        tip = getattr(self, "_drag_tooltip", None)
        if tip is not None:
            tip.hide()
        self.update()
        return True
