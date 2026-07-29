# !/usr/bin/python
# coding=utf-8
"""Keep an editing chord with the widget the user is actually typing in.

Qt asks the focus widget first: before resolving ``Ctrl+C`` to a shortcut it
sends the widget a :attr:`QEvent.ShortcutOverride`, and accepting that cancels
the lookup so the plain ``KeyPress`` arrives instead. ``QLineEdit`` and an
editable ``QTextEdit`` already answer yes for the whole editing family
(read-only-aware: a read-only field claims Copy/SelectAll but leaves
Cut/Paste/Undo alone), so they need nothing from this module.

**Read-only text views do.** A read-only ``QTextEdit`` / ``QTextBrowser`` claims
*nothing* — not even Copy — so any app-wide binding outranks it and the user is
left with the context menu. :class:`ShortcutGuardMixin` restores the claim.

The corollary, learned the hard way (see ``ScriptOutput``'s ``app_wide_copy``):
**never reach for an application-level event filter to win a chord.** A filter on
the ``QApplication`` sees key presses before their target widget and so bypasses
this protocol entirely, outranking every focused field in the process — a stale
selection in an output pane once hijacked Ctrl+C application-wide that way. A
``QShortcut`` at ``ApplicationShortcut`` scope gives the same reach *through*
the protocol, letting the focus widget keep what is rightfully its own.
"""
from qtpy import QtCore, QtGui


class ShortcutGuardMixin:
    """Mixin: claim the standard editing shortcuts for the focused widget.

    Inherit **before** the Qt base class so :meth:`event` wins the MRO::

        class _ViewerTextEdit(ShortcutGuardMixin, QtWidgets.QTextBrowser):

    :attr:`guarded_shortcuts` and :attr:`mutating_shortcuts` are class
    attributes, so a widget can narrow or extend the claimed set without
    reimplementing the dispatch.

    Sequences that write to the widget are not claimed on a read-only field
    (detected via ``isReadOnly``): the widget would ignore them anyway, and
    swallowing the override would leave the chord dead instead of falling
    through to whatever else is bound to it.
    """

    guarded_shortcuts = (
        QtGui.QKeySequence.Copy,
        QtGui.QKeySequence.Cut,
        QtGui.QKeySequence.Paste,
        QtGui.QKeySequence.Undo,
        QtGui.QKeySequence.Redo,
        QtGui.QKeySequence.SelectAll,
    )

    mutating_shortcuts = frozenset(
        {
            QtGui.QKeySequence.Cut,
            QtGui.QKeySequence.Paste,
            QtGui.QKeySequence.Undo,
            QtGui.QKeySequence.Redo,
        }
    )

    def event(self, event: QtCore.QEvent):
        if event.type() == QtCore.QEvent.ShortcutOverride and isinstance(
            event, QtGui.QKeyEvent
        ):
            if self.claims_shortcut(event):
                event.accept()
                return True
        return super().event(event)

    def claims_shortcut(self, event: QtGui.QKeyEvent) -> bool:
        """Whether *event* is an editing chord this widget should handle itself."""
        for sequence in self.guarded_shortcuts:
            # ``matches`` returns a plain bool on some bindings and a
            # ``SequenceMatch`` enum on others — truthiness is the portable read.
            # Every guarded sequence is a single chord, so the enum's truthy-but-
            # partial value can't occur here.
            if not event.matches(sequence):
                continue
            return not (sequence in self.mutating_shortcuts and self.is_read_only())
        return False

    def is_read_only(self) -> bool:
        """``isReadOnly`` when the base class provides it, else False."""
        getter = getattr(self, "isReadOnly", None)
        return bool(getter()) if callable(getter) else False
