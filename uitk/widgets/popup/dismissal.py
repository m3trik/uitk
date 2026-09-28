# !/usr/bin/python
# coding=utf-8
"""Event watchers that dismiss a popup: its host moved or hid, or the user left."""

from typing import Callable, List, Optional

from qtpy import QtCore, QtGui, QtWidgets

from uitk.managers.host_exit_guard import HostExitGuard


class AncestorDismissal(QtCore.QObject):
    """Dismiss a popup when the window hosting its anchor moves.

    Installs itself on the anchor and on every ancestor up to the top level. A
    ``Move`` of a WINDOW in that chain dismisses -- gated on ``isWindow()`` so a
    layout-driven move of an intermediate child widget does not. With
    ``on_hide`` a ``Hide`` of any widget in the chain dismisses too. Never
    consumes an event.

    Used by ``Menu.show_as_popup`` (gated on "visible and not pinned") and by
    the option-box value popups (which also close when an ancestor hides).
    """

    def __init__(
        self,
        anchor: QtWidgets.QWidget,
        dismiss: Callable[[], object],
        *,
        on_hide: bool = False,
        when: Optional[Callable[[], bool]] = None,
        parent: Optional[QtCore.QObject] = None,
    ):
        """Watch *anchor*'s ancestor chain.

        Parameters:
            anchor: The widget the popup is anchored to (it is watched too).
            dismiss: Called to dismiss the popup.
            on_hide: Also dismiss when any widget in the chain hides.
            when: Optional gate; the popup is dismissed only while it returns
                True (e.g. a pinned menu opts out).
            parent: The watcher's QObject owner, typically the popup, so the
                watcher dies with it.
        """
        super().__init__(parent)
        self._dismiss = dismiss
        self._on_hide = on_hide
        self._when = when
        self._watched: List[QtWidgets.QWidget] = []
        w = anchor
        while w is not None:
            try:
                w.installEventFilter(self)
                self._watched.append(w)
            except RuntimeError:
                pass  # widget already deleted (C++ side)
            w = w.parentWidget()

    def _armed(self) -> bool:
        return self._dismiss is not None and (self._when is None or self._when())

    def eventFilter(self, obj, event):
        event_type = event.type()
        # RuntimeError: the popup or the watched widget died mid-dispatch.
        # Swallowed, never raised: an exception escaping a shiboken virtual
        # override is a native fault, not a traceback.
        if event_type == QtCore.QEvent.Move:
            try:
                if self._armed() and obj.isWindow():
                    self._dismiss()
            except RuntimeError:
                pass
        elif event_type == QtCore.QEvent.Hide and self._on_hide:
            try:
                if self._armed():
                    self._dismiss()
            except RuntimeError:
                pass
        return False

    def detach(self) -> None:
        """Stop watching: remove the filter everywhere and drop the callback.

        Idempotent.
        """
        for w in self._watched:
            try:
                w.removeEventFilter(self)
            except RuntimeError:
                pass
        self._watched.clear()
        self._dismiss = None
        self._when = None


class OutsideClickDismissal(QtCore.QObject):
    """App-wide watcher: a press outside the popup, or Escape, dismisses it.

    :meth:`attach` it only while the popup session is open and :meth:`detach`
    it the moment the session ends, so its per-event cost exists only during
    an open popup. A dedicated QObject rather than the popup's own
    ``eventFilter``: installed app-wide, a filter receives the events of every
    widget in the application, and a widget's own item-hover branches would
    misfire on foreign widgets.

    Only Qt events are visible here -- a click on a DCC's native (non-Qt)
    surface never arrives. A consumer that needs that case watches its host
    window's ``WindowDeactivate`` as well (``ExpandableList`` click mode does).
    """

    def __init__(
        self,
        is_inside: Callable[[QtCore.QPoint], bool],
        dismiss: Callable[[], object],
    ):
        """Build a detached watcher.

        Parameters:
            is_inside: Given a global cursor position, whether it is over the
                popup (any part of it, e.g. a whole flyout chain).
            dismiss: Called to dismiss the popup; typically also detaches this
                watcher (ending the session).
        """
        # No QObject parent: the owner detaches it explicitly, and the popup
        # must stay free to be deleted mid-session without dragging the filter
        # down with it mid-dispatch.
        super().__init__()
        self._is_inside = is_inside
        self._dismiss = dismiss

    def attach(self) -> None:
        """Start watching every event in the application."""
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def detach(self) -> None:
        """Stop watching. Idempotent."""
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def eventFilter(self, obj, event):
        HostExitGuard.note(obj)  # an application filter: see its docstring
        event_type = event.type()
        if event_type == QtCore.QEvent.MouseButtonPress:
            # QCursor.pos() rather than the event's global position: dodges
            # the PySide2 globalPos() / PySide6 globalPosition() API split.
            try:
                if not self._is_inside(QtGui.QCursor.pos()):
                    # Dismiss, but do NOT consume: the outside press still
                    # lands on whatever the user pressed (standard menu
                    # dismissal semantics).
                    self._dismiss()
            except RuntimeError:
                # The popup's C++ side died (teardown mid-session): nothing
                # left to dismiss, so stop watching.
                self.detach()
            return False
        if event_type == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape:
            try:
                self._dismiss()
            except RuntimeError:
                self.detach()
            return True  # Escape is spent on dismissing the popup.
        return False
