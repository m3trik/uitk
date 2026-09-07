# !/usr/bin/python
# coding=utf-8
"""A corner legend of a widget's mouse gestures and keyboard shortcuts.

The reminder Substance Painter keeps in its viewport corner: what a drag does
under each modifier, and the keys that matter, read off a
:class:`~uitk.managers.shortcut_manager.ShortcutManager` so the legend can
never drift from what the widget actually binds. Built through
:meth:`ShortcutManager.overlay`; the host tells it which gesture group the
pointer is over (:meth:`ShortcutOverlay.set_context`) and that group is
brightened while the rest dim.
"""

from html import escape
from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets


class ShortcutOverlay(QtWidgets.QWidget):
    """Translucent, mouse-transparent legend anchored to a corner of *host*.

    One gesture group is shown at a time -- the group under the pointer,
    or the first registered until the pointer lands on one -- under a line
    naming every group, so the legend stays a few rows tall wherever it is
    read.  A last line lists the first *max_keys* keyboard bindings.

    Parameters:
        manager: The :class:`ShortcutManager` whose gestures and shortcuts
            are shown; the legend re-renders on every change it publishes.
        host: The widget to anchor to -- a scroll area anchors inside its
            viewport so the legend never sits on a scrollbar.
        anchor: ``"bottom-right"`` (default), ``"bottom-left"``,
            ``"top-right"`` or ``"top-left"``.
        max_keys: How many keyboard bindings to list under the gestures
            (the first registered ones; ``0`` lists none).
    """

    # Not a Designer widget-box entry: a manager builds this
    # (:meth:`ShortcutManager.overlay`), it anchors itself to a host it is
    # given, and it cannot exist without that manager -- so the bare
    # ``cls(parent)`` Designer makes has nothing to render.
    designer_spec = {"visible": False}

    MARGIN = 8
    #: Widest the legend grows before its rows wrap: a corner card, not a bar.
    MAX_WIDTH = 380
    #: Card fill and hairline, both translucent: the timeline reads through.
    BACKGROUND = (18, 18, 18, 160)
    BORDER = (255, 255, 255, 40)
    #: Key text, description text, the other groups' names, the shown group.
    _COLORS = {"head": "#e8e8e8", "row": "#c8c8c8", "dim": "#8a8a8a", "hot": "#ffffff"}

    def __init__(
        self,
        manager,
        host: QtWidgets.QWidget,
        anchor: str = "bottom-right",
        max_keys: int = 4,
    ):
        super().__init__(host)
        self._manager = manager
        self._host = host
        self._anchor = anchor
        self._max_keys = max(0, int(max_keys))
        self._context: Optional[str] = None
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self._label = QtWidgets.QLabel(self)
        self._label.setTextFormat(QtCore.Qt.RichText)
        self._label.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        font = self._label.font()
        font.setPointSize(8)
        self._label.setFont(font)
        self._label.setWordWrap(True)
        # uitk's theme gives every QLabel an opaque background and a border --
        # a solid slab over the card's own translucent fill, and a second
        # rounded outline inside it.  Opt this one out of both.
        self._label.setStyleSheet(
            "background: transparent; border: none; padding: 0px;"
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.addWidget(self._label)
        viewport = getattr(host, "viewport", None)
        (viewport() if callable(viewport) else host).installEventFilter(self)
        manager.on_change(self.refresh)
        self.refresh()
        self.hide()

    def _fit(self) -> None:
        """Size to the text, no wider than :attr:`MAX_WIDTH`, wrapping below it.

        ``adjustSize`` reads the unwrapped hint -- a keys line is a single
        very long row -- so the width is capped first and the height taken
        for THAT width.
        """
        m = self.layout().contentsMargins()
        width = min(
            self._label.sizeHint().width(), self.MAX_WIDTH - m.left() - m.right()
        )
        height = self._label.heightForWidth(width)
        if height <= 0:
            height = self._label.sizeHint().height()
        self.resize(width + m.left() + m.right(), height + m.top() + m.bottom())

    # -- state ---------------------------------------------------------------

    @property
    def context(self) -> Optional[str]:
        """The gesture group the pointer is over, or ``None`` (first group shown)."""
        return self._context

    @property
    def shown_group(self) -> Optional[str]:
        """The group whose rows are on screen right now."""
        groups = list(self._manager.gestures)
        if not groups:
            return None
        return self._context if self._context in groups else groups[0]

    def set_context(self, group: Optional[str]) -> None:
        """Brighten *group* (a gesture group name) and dim the others."""
        if group == self._context:
            return
        self._context = group
        self.refresh()

    def refresh(self) -> None:
        """Re-render from the manager and re-anchor."""
        self._label.setText(self._html())
        self._fit()
        self._reanchor()

    # -- rendering -----------------------------------------------------------

    def _html(self) -> str:
        """The legend as rich text.

        Every registered string is ESCAPED on the way in: a group name, a key
        and a description are plain text a caller writes for a human ("Clips &
        keys", "drag < 3 px"), and pasting one into markup would either mangle
        it or swallow the rest of the row.
        """
        c = self._COLORS
        shown = self.shown_group
        tabs = " &nbsp;&middot;&nbsp; ".join(
            f'<span style="color:{c["hot"]}"><b>{escape(name)}</b></span>'
            if name == shown
            else f'<span style="color:{c["dim"]}">{escape(name)}</span>'
            for name in self._manager.gestures
        )
        parts = ['<table cellspacing="0" cellpadding="1">']
        if tabs:
            parts.append(
                f'<tr><td colspan="2" style="padding-bottom:3px">{tabs}</td></tr>'
            )
        for keys_text, description in self._manager.gestures.get(shown, ()):
            parts.append(
                f'<tr><td style="color:{c["head"]}; padding-right:10px">'
                f"<b>{escape(keys_text)}</b></td>"
                f'<td style="color:{c["row"]}">{escape(description)}</td></tr>'
            )
        keys = [
            (k, v.get("description") or "")
            for k, v in self._manager.shortcuts.items()
            if not v.get("read_only")
        ][: self._max_keys]
        for i, (key, description) in enumerate(keys):
            pad = "padding-top:4px; " if i == 0 else ""
            parts.append(
                f'<tr><td style="{pad}color:{c["dim"]}; padding-right:10px">'
                f"<b>{escape(key)}</b></td>"
                f'<td style="{pad}color:{c["dim"]}">{escape(description)}</td></tr>'
            )
        parts.append("</table>")
        return "".join(parts)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtGui.QPen(QtGui.QColor(*self.BORDER), 1))
        painter.setBrush(QtGui.QColor(*self.BACKGROUND))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 5, 5)

    # -- anchoring -----------------------------------------------------------

    def _host_rect(self) -> QtCore.QRect:
        viewport = getattr(self._host, "viewport", None)
        if callable(viewport):
            return viewport().geometry()
        return self._host.rect()

    def _reanchor(self) -> None:
        r = self._host_rect()
        m = self.MARGIN
        # ``QRect.right()`` is inclusive: the far edge is ``left + width``.
        x = (
            r.left() + m
            if "left" in self._anchor
            else r.left() + r.width() - self.width() - m
        )
        y = (
            r.top() + m
            if "top" in self._anchor
            else r.top() + r.height() - self.height() - m
        )
        self.move(max(r.left(), x), max(r.top(), y))
        self.raise_()

    def eventFilter(self, obj, event):
        # The viewport's Resize, not the scroll area's: the area's own event
        # reaches a filter BEFORE it lays its viewport out, so anchoring on
        # it read the old size.
        if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show):
            self._reanchor()
        return False
