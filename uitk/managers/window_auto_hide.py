# !/usr/bin/python
# coding=utf-8
"""Hide a floating window once the cursor has visited it and left.

:class:`WindowAutoHide` gives any top-level window the behavior of a transient
tool popup: from each show, it polls the cursor, and once the cursor has been
inside the window and then leaves it, the window hides -- unless it is pinned
(``window.is_pinned``, the flag uitk's header pin button sets).  A window that
the cursor never entered stays up, so opening one from a hotkey away from the
cursor does not close it before the user reaches it.

The hide is flagged on the window as ``_auto_hiding`` for its duration, which
``MainWindow.hideEvent`` reads to skip re-raising the parent: an automatic hide
must not steal z-order from sibling tool windows.

Example
-------
>>> self._auto_hide = WindowAutoHide(self.ui)  # keep a reference
"""

from typing import Callable, Optional

from qtpy import QtCore, QtGui, QtWidgets


class WindowAutoHide(QtCore.QObject):
    """Hide *window* when the cursor leaves it after having entered it.

    Parameters:
        window: The top-level widget to manage. The helper parents itself to
            it, so it lives exactly as long as the window.
        interval: Cursor poll period in milliseconds.
        cursor_pos: ``() -> QPoint`` in global coordinates; default
            ``QCursor.pos``. Injectable for tests.
    """

    def __init__(
        self,
        window: QtWidgets.QWidget,
        interval: int = 100,
        cursor_pos: Optional[Callable[[], QtCore.QPoint]] = None,
    ):
        super().__init__(window)
        self.window = window
        self._cursor_pos = cursor_pos or QtGui.QCursor.pos
        #: Whether the cursor has been inside the window since it was shown.
        self.entered = False
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(interval)
        self.timer.timeout.connect(self.check)
        window.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        """Re-arm on every show: the cursor has not entered this showing yet."""
        if obj is self.window and event.type() == QtCore.QEvent.Show:
            self.entered = False
            self.timer.start()
        return False

    def cursor_inside(self) -> bool:
        """Whether the cursor is over the window, a widget it contains, or a
        popup it owns."""
        window = self.window
        pos = self._cursor_pos()
        if window.rect().contains(window.mapFromGlobal(pos)):
            return True
        # A popup or child window the window owns (a combo's list, an option
        # menu) sits outside its rect but is still "inside" for the user.
        # ``isAncestorOf`` stops at a window boundary -- such a popup is a
        # window of its own -- so walk the parent chain across them.
        widget = QtWidgets.QApplication.widgetAt(pos)
        while widget is not None:
            if widget is window:
                return True
            widget = widget.parentWidget()
        return False

    def check(self) -> None:
        """One poll: hide the window if the cursor has left it (and it is unpinned)."""
        window = self.window
        if not window.isVisible():
            self.timer.stop()
            return
        if getattr(window, "is_pinned", False):
            return
        if self.cursor_inside():
            self.entered = True
        elif self.entered:
            window._auto_hiding = True
            try:
                window.hide()
            finally:
                window._auto_hiding = False
            self.timer.stop()
