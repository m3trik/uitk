# !/usr/bin/python
# coding=utf-8
"""Promoting a plain child widget to a frameless top-level popup window."""

from typing import Callable, Optional

from qtpy import QtCore, QtWidgets

from uitk._bootstrap import Bootstrap
from uitk.themes.style_sheet import StyleSheet


class PopupWindow:
    """The window a popup floats in.

    A popup starts life as an ordinary child widget -- built, populated and
    styled inside its host -- and becomes a top-level window only on its first
    open, while still hidden: a flag change hides a widget, which is a no-op
    then, and no OS-level window exists before one is needed (no WM-visible
    flash at construction). ``Menu`` and ``ExpandableList`` flyouts both
    promote this way; what differs between them is data (the flags, the
    translucency, who owns a parentless popup), so it is passed in.
    """

    @staticmethod
    def promote(
        widget: QtWidgets.QWidget,
        flags: QtCore.Qt.WindowFlags,
        *,
        parent_fallback: Optional[Callable[[], Optional[QtWidgets.QWidget]]] = None,
        translucent: bool = False,
    ) -> Optional[QtWidgets.QWidget]:
        """Make *widget* a top-level window with *flags*, keeping its owner.

        One ``setParent(parent, flags)`` call: ``setWindowFlags`` alone
        recreates the native handle and a ``setParent`` after it would
        recreate it again. The attributes are set AFTER the reparent so they
        survive that recreation.

        Parameters:
            widget: The widget to promote (still hidden).
            flags: The full window flags -- a window TYPE plus hints (e.g.
                ``Qt.Tool | Qt.FramelessWindowHint``). A hints-only set would
                demote a parented widget to an embedded child.
            parent_fallback: Called only when *widget* has no parent; returns
                the window that should own the popup (``None`` leaves it
                parentless). ``Menu`` passes :meth:`active_window`. A fallback
                that raises leaves the popup parentless.
            translucent: Also set ``WA_TranslucentBackground`` (through
                ``Bootstrap.set_translucent``, which leaves it off where the
                desktop cannot composite). For a popup whose ground is a
                translucent window background; an opaque surface must NOT set
                it, or the backing store clears to transparent wherever the
                fill does not reach. A translucent popup also blurs what is
                behind it when its owner's theme has ``WINDOW_BLUR`` on.

        Returns:
            QtWidgets.QWidget or None: The popup's owner after the promotion.
        """
        parent = widget.parentWidget()
        if parent is not None:
            widget.setParent(parent, flags)
        elif parent_fallback is not None:
            try:
                parent = parent_fallback()
                if parent is not None and parent is not widget:
                    widget.setParent(parent, flags)
                else:
                    parent = None
                    widget.setWindowFlags(flags)
            except Exception:
                parent = None
                widget.setWindowFlags(flags)
        else:
            widget.setWindowFlags(flags)

        if translucent:
            Bootstrap.set_translucent(widget)
            # Frosted like the window it pops from: the owner's WINDOW_BLUR,
            # re-read at each show so a theme change reaches it.
            Bootstrap.set_blur(widget, StyleSheet.window_blur)
        widget.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        return parent

    @staticmethod
    def active_window() -> Optional[QtWidgets.QWidget]:
        """The application's active window: the owner for a parentless popup.

        Returns:
            QtWidgets.QWidget or None: None with no active window (or no app).
        """
        app = QtWidgets.QApplication.instance()
        return app.activeWindow() if app else None
