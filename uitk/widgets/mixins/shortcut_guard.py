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
*nothing* — not even Copy — so any app-wide binding outranks it: the chord is
consumed elsewhere and the user is left with the context menu. Live-Maya
measured, with uitk's own console holding the app-scope Copy shortcut: Ctrl+C in
a focused ``QTextBrowser`` copied **nothing at all** (the console had no
selection, so it consumed the key and no-op'd) or the *console's* text (when it
did). Both flavours of that bug are what this module exists to prevent.

Two ways in, same policy:

* :class:`ShortcutGuardMixin` — inherit it, for widgets uitk defines.
* :class:`ShortcutGuardFilter` — install it, for widgets uitk does not define,
  such as a ``QTextBrowser`` declared in a ``.ui`` file. ``MainWindow``
  registration installs one on every text view it registers, so panel authors
  get the guard without promoting anything.

The corollary, learned the hard way (see ``ScriptOutput``'s ``app_wide_copy``):
**never reach for an application-level event filter to win a chord.** A filter on
the ``QApplication`` sees key presses before their target widget and so bypasses
this protocol entirely, outranking every focused field in the process — a stale
selection in an output pane once hijacked Ctrl+C application-wide that way. A
``QShortcut`` at ``ApplicationShortcut`` scope gives the same reach *through*
the protocol, letting the focus widget keep what is rightfully its own. Keep such
a shortcut **disabled unless it has something to copy**, or it silently eats the
chord from every widget that declines the override.
"""
from qtpy import QtCore, QtGui


class ShortcutGuardMixin:
    """Mixin: claim the standard editing shortcuts for the focused widget.

    Inherit **before** the Qt base class so :meth:`event` wins the MRO::

        class _ViewerTextEdit(ShortcutGuardMixin, QtWidgets.QTextBrowser):

    :attr:`guarded_shortcuts` and :attr:`mutating_shortcuts` are class
    attributes, so a widget can narrow or extend the claimed set without
    reimplementing the dispatch.

    Two sequences are deliberately *not* claimed:

    * anything that writes to the widget, on a read-only field (detected via
      ``isReadOnly``) — the widget would ignore it anyway, and swallowing the
      override would leave the chord dead rather than falling through;
    * ``Copy`` with nothing selected — there is nothing to put on the clipboard,
      so the chord belongs to whatever else wants it (an app-wide copy, say).
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

    # Sequences that need something selected to mean anything.
    selection_shortcuts = frozenset({QtGui.QKeySequence.Copy, QtGui.QKeySequence.Cut})

    @classmethod
    def claim_override(cls, widget, event: QtCore.QEvent) -> bool:
        """Accept *event* on *widget*'s behalf when it's a chord *widget* should own.

        Returns True when the event was claimed (the caller is done with it), so the
        two entry points share one implementation of *both* halves — which events are
        even candidates, and whether this widget wants them.
        """
        if event.type() != QtCore.QEvent.ShortcutOverride or not isinstance(
            event, QtGui.QKeyEvent
        ):
            return False
        if not cls.claims(widget, event):
            return False
        event.accept()
        return True

    @classmethod
    def claims(cls, widget, event: QtGui.QKeyEvent) -> bool:
        """Whether *widget* should handle *event*'s chord itself.

        The single source of the policy, shared by :class:`ShortcutGuardMixin`
        (inheritance) and :class:`ShortcutGuardFilter` (installation), so the two
        entry points can't drift.
        """
        for sequence in cls.guarded_shortcuts:
            # ``matches`` returns a plain bool on some bindings and a
            # ``SequenceMatch`` enum on others — truthiness is the portable read.
            # Every guarded sequence is a single chord, so the enum's truthy-but-
            # partial value can't occur here.
            if not event.matches(sequence):
                continue
            if sequence in cls.mutating_shortcuts and cls.is_read_only(widget):
                return False
            if sequence in cls.selection_shortcuts and not cls.has_selection(widget):
                return False
            return True
        return False

    @staticmethod
    def is_read_only(widget) -> bool:
        """``widget.isReadOnly()`` when it has one, else False."""
        getter = getattr(widget, "isReadOnly", None)
        return bool(getter()) if callable(getter) else False

    @staticmethod
    def has_selection(widget) -> bool:
        """Whether *widget* holds a text selection.

        Covers both Qt text families — ``hasSelectedText`` (QLineEdit) and
        ``textCursor().hasSelection()`` (QTextEdit/QTextBrowser/QPlainTextEdit).
        A widget with neither is assumed to have something worth copying, so an
        unrecognised widget is never silently denied its own chord.
        """
        has_selected_text = getattr(widget, "hasSelectedText", None)
        if callable(has_selected_text):
            return bool(has_selected_text())
        text_cursor = getattr(widget, "textCursor", None)
        if callable(text_cursor):
            return bool(text_cursor().hasSelection())
        return True

    def event(self, event: QtCore.QEvent):
        # Called through the instance, so ``cls`` is this widget's own class and a
        # subclass that narrowed ``guarded_shortcuts`` is honoured.
        if self.claim_override(self, event):
            return True
        return super().event(event)

    def claims_shortcut(self, event: QtGui.QKeyEvent) -> bool:
        """Whether *event* is an editing chord this widget should handle itself."""
        return self.claims(self, event)


class ShortcutGuardFilter(QtCore.QObject):
    """Event-filter form of :class:`ShortcutGuardMixin`, for widgets uitk can't subclass.

    A ``QTextBrowser`` declared in a ``.ui`` file is a plain Qt widget, so the
    mixin can't reach it — but a filter installed on the instance sees the
    ``ShortcutOverride`` before the widget's own ``event`` and can accept it on
    the widget's behalf. One instance serves any number of widgets: the policy is
    read from ``obj`` per event, so read-only and selection state stay live even
    if the panel toggles them later.

    When ``obj`` *is* a :class:`ShortcutGuardMixin` (a uitk ``TextEdit`` registered on
    a window gets both forms), the widget's own class supplies the policy — the filter
    runs before the widget's ``event``, so reading the base policy here would quietly
    override a subclass that narrowed :attr:`ShortcutGuardMixin.guarded_shortcuts`.
    """

    def eventFilter(self, obj, event: QtCore.QEvent) -> bool:
        policy = type(obj) if isinstance(obj, ShortcutGuardMixin) else ShortcutGuardMixin
        try:
            if policy.claim_override(obj, event):
                return True
        except RuntimeError:  # C++ side already deleted
            pass
        return super().eventFilter(obj, event)
