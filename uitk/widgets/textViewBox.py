# !/usr/bin/python
# coding=utf-8
"""Scrollable rich-text viewer window.

Read-only counterpart to :class:`MessageBox` for content too long for
a passive popup — reports, multi-line formatted output, log dumps.
Built on :class:`WindowPanel`, so it ships with the standard uitk
chrome (themed Header / body / Footer with size grip) and integrates
with the switchboard's footer busy indicator and progress feedback.

Non-modal by design: the viewer coexists with the host application so
the user can keep working while reading. Buttons are wired to
``close()`` for the standard Accept / Reject / Destructive roles;
Apply / Reset / Help leave the window open and surface the clicked
name via :attr:`clicked_button`.
"""
from qtpy import QtCore, QtGui, QtWidgets

from uitk.widgets.windowPanel import WindowPanel
from uitk.widgets._html_style import format_rich_text, resolve_background


class _ViewerTextEdit(QtWidgets.QTextBrowser):
    """Read-only browser that survives host-app shortcut interception.

    QTextBrowser (not plain QTextEdit) so callers get ``setOpenExternalLinks``
    out of the box — clickable ``file://`` paths in our HTML reports route
    through ``QDesktopServices`` instead of QTextBrowser's internal
    document loader, which can't render binary textures.

    Hosts like Maya install application-level ``ShortcutOverride`` handlers
    that swallow ``Ctrl+C`` before the widget can run its built-in copy
    action — leaving the user with only the context-menu Copy. Mirroring
    the pattern from :class:`mayatk.env_utils.script_output.ScriptOutput`,
    we accept the ``ShortcutOverride`` event ourselves whenever a selection
    exists, which tells Qt to dispatch the subsequent KeyPress to *us*
    rather than treating it as a host shortcut.
    """

    def event(self, event: QtCore.QEvent):
        if event.type() == QtCore.QEvent.ShortcutOverride and isinstance(
            event, QtGui.QKeyEvent
        ):
            if event.matches(QtGui.QKeySequence.Copy) and self.textCursor().hasSelection():
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.matches(QtGui.QKeySequence.Copy):
            if self.textCursor().hasSelection():
                self.copy()
                event.accept()
                return
        super().keyPressEvent(event)


class TextViewBox(WindowPanel):
    """Read-only rich-text viewer with optional standard buttons.

    Parameters mirror :class:`MessageBox` where they overlap so callers
    can swap between the two helpers without rewriting branch logic.

    Parameters
    ----------
    parent : QWidget, optional
        Anchor widget. The window reparents to ``parent.window()``.
    title : str
        Window title — shown in the header bar.
    align : str
        Default alignment when the supplied HTML lacks an ``align=``
        attribute. Default ``"left"``.
    monospace : bool
        Use a monospace body font (log / command output). Default
        ``False``.
    word_wrap : bool
        Wrap long lines. Set ``False`` for tabular content. Default
        ``True``.
    """

    # Case-insensitive map from MessageBox-style button names to
    # ``(label, role, canonical_name)`` for :class:`QDialogButtonBox`.
    # Keys are lowercase so lookup is ``name.lower()``; the canonical
    # name (mixed case) is what callers see returned from
    # :attr:`clicked_button`.
    BUTTONS = {
        "ok": ("OK", QtWidgets.QDialogButtonBox.AcceptRole, "Ok"),
        "open": ("Open", QtWidgets.QDialogButtonBox.AcceptRole, "Open"),
        "save": ("Save", QtWidgets.QDialogButtonBox.AcceptRole, "Save"),
        "saveall": ("Save All", QtWidgets.QDialogButtonBox.AcceptRole, "SaveAll"),
        "retry": ("Retry", QtWidgets.QDialogButtonBox.AcceptRole, "Retry"),
        "apply": ("Apply", QtWidgets.QDialogButtonBox.ApplyRole, "Apply"),
        "reset": ("Reset", QtWidgets.QDialogButtonBox.ResetRole, "Reset"),
        "restoredefaults": (
            "Restore Defaults",
            QtWidgets.QDialogButtonBox.ResetRole,
            "RestoreDefaults",
        ),
        "help": ("Help", QtWidgets.QDialogButtonBox.HelpRole, "Help"),
        "yes": ("Yes", QtWidgets.QDialogButtonBox.YesRole, "Yes"),
        "yestoall": ("Yes to All", QtWidgets.QDialogButtonBox.YesRole, "YesToAll"),
        "no": ("No", QtWidgets.QDialogButtonBox.NoRole, "No"),
        "notoall": ("No to All", QtWidgets.QDialogButtonBox.NoRole, "NoToAll"),
        "cancel": ("Cancel", QtWidgets.QDialogButtonBox.RejectRole, "Cancel"),
        "close": ("Close", QtWidgets.QDialogButtonBox.RejectRole, "Close"),
        "abort": ("Abort", QtWidgets.QDialogButtonBox.RejectRole, "Abort"),
        "ignore": ("Ignore", QtWidgets.QDialogButtonBox.RejectRole, "Ignore"),
        "discard": ("Discard", QtWidgets.QDialogButtonBox.DestructiveRole, "Discard"),
    }

    def __init__(
        self,
        parent=None,
        title: str = "",
        align: str = "left",
        monospace: bool = False,
        word_wrap: bool = True,
    ):
        super().__init__(title=title, parent=parent)
        self.align = align
        self._result_name = None

        # Body: read-only QTextBrowser fills the body.
        self.text_edit = _ViewerTextEdit(self)
        self.text_edit.setReadOnly(True)
        # Force selectable + link-accessible so Ctrl+C has something to
        # copy and ``file://`` paths in HTML are clickable / focusable
        # via keyboard. Read-only QTextEdit/QTextBrowser defaults to
        # ``NoTextInteraction`` under some styles in Maya.
        self.text_edit.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse
            | QtCore.Qt.TextSelectableByKeyboard
            | QtCore.Qt.LinksAccessibleByMouse
            | QtCore.Qt.LinksAccessibleByKeyboard
        )
        # Disable QTextBrowser's internal navigation entirely — when no
        # ``source`` document is set, QTextBrowser may try to load the
        # clicked URL as the new document and clobber the report. Route
        # link clicks through ``QDesktopServices`` explicitly so the
        # host OS picks the right handler (image viewer for textures,
        # Explorer for folders, etc.).
        self.text_edit.setOpenLinks(False)
        self.text_edit.setOpenExternalLinks(False)
        self.text_edit.anchorClicked.connect(self._on_anchor_clicked)
        if monospace:
            self.text_edit.setFont(self._monospace_font())
        if not word_wrap:
            self.text_edit.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        self.body_layout.addWidget(self.text_edit, 1)

        # Buttons live in the footer (right side) so the body is reserved
        # for the content. ``background=True`` gives the button bar a
        # normal styled background instead of footer-transparent, so the
        # buttons read as real UI affordances rather than ghosted onto
        # the footer.
        self.button_box = QtWidgets.QDialogButtonBox()
        self.button_box.setVisible(False)
        self.footer.add_widget(self.button_box, side="right", background=True)

        self.setProperty("class", self.__class__.__name__)

    def _fit_to_content(self):
        """Skip the table-aware sizing in the base class.

        ``WindowPanel._fit_to_content`` measures a contained QTableWidget.
        Viewers are TextEdit-driven and have no table to measure — the
        caller sets the size explicitly via ``resize(w, h)`` before
        showing, so ``adjustSize()`` here would clamp it down to the
        text's minimumSizeHint. Just keep whatever the caller asked
        for.
        """
        return

    @staticmethod
    def _monospace_font() -> QtGui.QFont:
        for family in ("Consolas", "Courier New", "Monospace"):
            font = QtGui.QFont(family)
            font.setStyleHint(QtGui.QFont.Monospace)
            if font.exactMatch() or family == "Monospace":
                return font
        fallback = QtGui.QFont()
        fallback.setStyleHint(QtGui.QFont.Monospace)
        return fallback

    def _on_anchor_clicked(self, url: QtCore.QUrl) -> None:
        """Open clicked anchors via the host OS shell.

        Routed through ``QDesktopServices`` so ``file://`` URLs hit
        Explorer / Finder / xdg-open with the system's default handler
        and the viewer's document stays intact.
        """
        if not url.isEmpty():
            QtGui.QDesktopServices.openUrl(url)

    def setStandardButtons(self, *buttons) -> None:
        """Configure the visible buttons by name.

        Accepts the same name strings as :class:`MessageBox`
        (``"Ok"``, ``"Cancel"``, ``"Yes"``, ``"No"``, ...). The chosen
        name is exposed via :attr:`clicked_button` so callers can branch
        on the same strings used today with ``message_box``.

        Calling with no arguments hides the button bar entirely (useful
        for passive viewers dismissed via the window chrome).
        """
        self.button_box.clear()
        if not buttons:
            self.button_box.setVisible(False)
            return

        self.button_box.setVisible(True)
        for name in buttons:
            if not isinstance(name, str):
                continue
            spec = self.BUTTONS.get(name.lower())
            if spec is None:
                continue
            text, role, canonical = spec
            btn = self.button_box.addButton(text, role)
            # Footer buttons render with light padding at default size,
            # which makes short labels like "OK" disappear into the
            # status row. Widen each button to ~3× its natural width so
            # the controls read as deliberate affordances.
            btn.setMinimumWidth(max(btn.sizeHint().width() * 3, 90))
            btn.clicked.connect(
                lambda _=False, n=canonical: self._on_button_clicked(n)
            )

    def setText(
        self,
        string: str,
        fontColor: str = "white",
        background=False,
        fontSize=None,
    ) -> None:
        """Set the body text, replacing any existing content.

        Parameters mirror :meth:`MessageBox.setText`. ``fontSize``
        defaults to ``None`` (use the widget's native size) since long
        viewer content does not benefit from MessageBox's larger
        default.
        """
        s = format_rich_text(
            string, align=self.align, font_color=fontColor, font_size=fontSize
        )
        self.text_edit.setHtml(s)

        bg_css = resolve_background(background)
        if bg_css:
            self.text_edit.setStyleSheet(
                f"QTextEdit {{ background-color: {bg_css}; }}"
            )
        else:
            self.text_edit.setStyleSheet("")

    def append_text(
        self,
        string: str,
        fontColor: str = "white",
        fontSize=None,
    ) -> None:
        """Append a paragraph without clearing existing content."""
        s = format_rich_text(
            string, align=self.align, font_color=fontColor, font_size=fontSize
        )
        self.text_edit.append(s)
        bar = self.text_edit.verticalScrollBar()
        if bar:
            bar.setValue(bar.maximum())

    def clear_text(self) -> None:
        self.text_edit.clear()

    @property
    def clicked_button(self):
        """Canonical name of the last clicked button, or ``None``.

        Read-only. Callers can connect to a button signal directly if
        they need realtime handling; this attribute is the
        click-and-look-after pattern for slot handlers.
        """
        return self._result_name

    def _on_button_clicked(self, name: str) -> None:
        self._result_name = name
        spec = self.BUTTONS.get(name.lower())
        if spec is None:
            return
        _, role, _canonical = spec
        # Accept / Reject / Destructive roles close the window. Apply /
        # Reset / Help leave it open; callers can read clicked_button
        # if they need to react.
        if role in (
            QtWidgets.QDialogButtonBox.AcceptRole,
            QtWidgets.QDialogButtonBox.YesRole,
            QtWidgets.QDialogButtonBox.RejectRole,
            QtWidgets.QDialogButtonBox.NoRole,
            QtWidgets.QDialogButtonBox.DestructiveRole,
        ):
            self.close()


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = TextViewBox(title="Result Viewer")
    w.resize(720, 480)
    w.setText(
        "<h2>Build Report</h2>"
        "<p>Result: success</p>"
        "<p>Warning: 3 files skipped</p>"
        "<pre>foo.py        OK\nbar.py        OK\nbaz.py        SKIP</pre>"
    )
    w.setStandardButtons("Ok", "Cancel")
    w.show()
    sys.exit(app.exec_())
