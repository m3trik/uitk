# !/usr/bin/python
# coding=utf-8
"""Shared drag infrastructure for sequencer graphics items.

Provides:
- :func:`snap_time` — unified time-snap helper (Ctrl = per-frame).
- :class:`DraggableItemMixin` — template for ``cancel_drag()`` support.
"""
from __future__ import annotations

from qtpy import QtWidgets, QtCore


def snap_time(value: float, timeline) -> float:
    """Snap *value* to the timeline's grid, or to 1 when Ctrl is held."""
    modifiers = QtWidgets.QApplication.keyboardModifiers()
    if modifiers & QtCore.Qt.ControlModifier:
        return round(value)
    interval = timeline.parent_sequencer.snap_interval
    if interval > 0:
        return round(value / interval) * interval
    return value


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

    def _is_drag_active(self) -> bool:
        raise NotImplementedError

    def _restore_drag_state(self) -> None:
        raise NotImplementedError

    def cancel_drag(self) -> bool:
        if not self._is_drag_active():
            return False
        self._restore_drag_state()
        tip = getattr(self, "_drag_tooltip", None)
        if tip is not None:
            tip.hide()
        self.update()
        return True
