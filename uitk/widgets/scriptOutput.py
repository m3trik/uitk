# !/usr/bin/python
# coding=utf-8
"""Host-agnostic script-output console widget.

A read-only, monospace, syntax-highlighted text view for mirroring a DCC's
script/output log. Extracted from mayatk's ``ScriptConsole`` so every DCC
integration (Maya ``workspaceControl`` host, Blender owned-window host,
standalone) shares one widget and one look — the DCC-specific concerns
(*what clears the log*, *what extra context-menu actions exist*, *where the
text comes from*) are **injected** rather than baked in, so the widget itself
carries no ``maya.cmds`` / ``bpy`` dependency.

Coloring is done by a regex :class:`QSyntaxHighlighter` over whatever plain
text the host feeds in (a Maya reporter mirror, a redirected ``stdout`` stream,
a logging handler). Because it matches words like ``Error`` / ``Warning`` /
``Result`` in the text — not log-record levels — the same rules color a Maya
reporter dump and a Blender ``stdout`` redirect identically.
"""
from typing import Callable, List, Optional, Tuple
from qtpy import QtWidgets, QtGui, QtCore


def _monospace_font(point_size: int = 9) -> QtGui.QFont:
    """A monospace ``QFont`` that resolves across platforms (Consolas → Courier
    New → generic Monospace), so the console reads the same on Windows (Maya)
    and Linux (Blender)."""
    for family in ("Consolas", "Courier New", "Monospace"):
        font = QtGui.QFont(family, point_size)
        font.setStyleHint(QtGui.QFont.Monospace)
        if font.exactMatch() or family == "Monospace":
            return font
    fallback = QtGui.QFont()
    fallback.setPointSize(point_size)
    fallback.setStyleHint(QtGui.QFont.Monospace)
    return fallback


class ScriptHighlightRule:
    """One regex → text-format rule for :class:`ScriptHighlighter`."""

    def __init__(
        self,
        color: Tuple[int, int, int],
        pattern: str,
        bg_color: Optional[Tuple[int, int, int]] = None,
        bold: bool = False,
        italic: bool = False,
        font: Optional[QtGui.QFont] = None,
    ):
        self.pattern = QtCore.QRegularExpression(pattern)
        self.format = QtGui.QTextCharFormat()
        self.format.setForeground(QtGui.QColor(*color))
        if bg_color:
            self.format.setBackground(QtGui.QColor(*bg_color))
        rule_font = QtGui.QFont(font) if font is not None else _monospace_font()
        rule_font.setBold(bold)
        rule_font.setItalic(italic)
        self.format.setFont(rule_font)


class ScriptHighlighter(QtGui.QSyntaxHighlighter):
    """Apply a list of :class:`ScriptHighlightRule` to a text document."""

    def __init__(
        self,
        doc: QtGui.QTextDocument,
        rules: Optional[List[ScriptHighlightRule]] = None,
    ):
        super().__init__(doc)
        self.rules = rules if rules is not None else default_rules()

    def highlightBlock(self, text: str) -> None:
        for rule in self.rules:
            match_iter = rule.pattern.globalMatch(text)
            while match_iter.hasNext():
                match = match_iter.next()
                self.setFormat(
                    match.capturedStart(), match.capturedLength(), rule.format
                )


def default_rules() -> List[ScriptHighlightRule]:
    """The default log-coloring rules (Maya-parity palette).

    Kept as the canonical look so a Blender console is pixel-identical to the
    Maya one. Override by passing ``rules=`` to :class:`ScriptOutput`.
    """
    # The word rules are case-insensitive ((?i)) so they color Maya's capitalized
    # reporter text ("// Error:") AND Blender's uppercase logging levels ("ERROR:")
    # identically — no regression to the Maya look, strictly wider coverage.
    return [
        ScriptHighlightRule((90, 90, 90), r"(//|#).+"),  # comment
        ScriptHighlightRule((205, 200, 120), r"(?i).*\bWarning\b.*"),  # warning
        ScriptHighlightRule((165, 75, 75), r"(?i).*\bError\b.*"),  # error
        ScriptHighlightRule((115, 215, 150), r"(?i).*\bResult\b.*"),  # result
        ScriptHighlightRule((130, 220, 210), r"(?i).*\bInfo\b.*"),  # info (pastel teal)
    ]


class ScriptOutput(QtWidgets.QTextEdit):
    """Read-only, syntax-highlighted console view — host-agnostic.

    Injectable collaborators (DIP — no ``maya.cmds`` / ``bpy`` here):

    Parameters:
        parent: Qt parent.
        rules: Highlight rules; defaults to :func:`default_rules` (Maya palette).
        clear_callback: Called by the context-menu **Clear** action. Defaults to
            clearing just this widget; a DCC host passes a callback that also
            clears the underlying reporter/log.
        context_menu_hook: ``callable(menu)`` invoked while building the context
            menu, so a host can append DCC-specific actions (e.g. Maya's
            "Echo All Commands" toggle) without subclassing.
        app_wide_copy: When True (Maya), capture Ctrl+C **application-wide** — an
            ``ApplicationShortcut`` plus an app-level event filter — so a selection
            copies even when the host intercepts the shortcut or the widget lacks
            focus. When False (Blender / standalone, where the widget receives its
            own key events), scope copy to this widget so it never hijacks Ctrl+C
            from other widgets in the same QApplication while the console holds a
            stale selection.
        max_blocks: If set, cap the document at this many blocks (oldest trimmed) —
            terminal-style scrollback so a long streaming session can't grow the
            document unbounded. ``None`` (default) = unbounded (Maya mirrors a
            host-capped reporter, so it needs no cap).
        point_size: Monospace font size.
    """

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        *,
        rules: Optional[List[ScriptHighlightRule]] = None,
        clear_callback: Optional[Callable[[], None]] = None,
        context_menu_hook: Optional[Callable[[QtWidgets.QMenu], None]] = None,
        app_wide_copy: bool = True,
        max_blocks: Optional[int] = None,
        point_size: int = 9,
    ):
        super().__init__(parent)
        self.setProperty("class", self.__class__.__name__)  # QSS theming hook
        self.clear_callback = clear_callback
        self.context_menu_hook = context_menu_hook

        self.setReadOnly(True)
        self.setFont(_monospace_font(point_size))
        if max_blocks:
            self.document().setMaximumBlockCount(int(max_blocks))

        # Ctrl+C copy. app_wide_copy=True (Maya) reaches over host shortcut interception
        # via an ApplicationShortcut + app event filter; False scopes it to this widget so
        # it can't hijack Ctrl+C elsewhere in the app when the console holds a selection.
        self._copy_shortcut = QtGui.QShortcut(QtGui.QKeySequence.Copy, self)
        self._copy_shortcut.setContext(
            QtCore.Qt.ApplicationShortcut if app_wide_copy
            else QtCore.Qt.WidgetWithChildrenShortcut
        )
        self._copy_shortcut.activated.connect(self._handle_copy_shortcut)
        if app_wide_copy:
            app = QtWidgets.QApplication.instance()
            if app:
                app.installEventFilter(self)

        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse | QtCore.Qt.TextSelectableByKeyboard
        )
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

        self.highlighter = ScriptHighlighter(self.document(), rules)

    # -- public API (snake_case wrappers) ------------------------------------
    def set_clear_callback(self, callback: Optional[Callable[[], None]]) -> None:
        """Set the callback the **Clear** context-menu action invokes."""
        self.clear_callback = callback

    def set_context_menu_hook(
        self, hook: Optional[Callable[[QtWidgets.QMenu], None]]
    ) -> None:
        """Set a ``callable(menu)`` hook that appends host-specific actions."""
        self.context_menu_hook = hook

    def set_rules(self, rules: List[ScriptHighlightRule]) -> None:
        """Replace the highlight rules and re-highlight the document."""
        self.highlighter.rules = rules
        self.highlighter.rehighlight()

    def append_text(self, text: str) -> None:
        """Append raw ``text`` at the end without disturbing the user's selection/caret.

        Inserts through a **detached** cursor (not ``self.textCursor()``), so a live
        selection — e.g. the user is mid-drag selecting output to copy — survives a
        streaming write instead of being collapsed to the end every tick. Auto-scrolls
        only when the view is already at the bottom (terminal behavior: don't yank the
        user back down while they've scrolled up to read). Preserves the stream's own
        newlines (``insertText``, not ``append`` which injects a paragraph per call);
        the highlighter recolors each block.
        """
        scrollbar = self.verticalScrollBar()
        at_bottom = scrollbar is None or scrollbar.value() >= scrollbar.maximum() - 4
        cursor = QtGui.QTextCursor(self.document())
        cursor.movePosition(QtGui.QTextCursor.End)
        cursor.insertText(text)
        if at_bottom and scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())

    # -- Qt overrides (camelCase) --------------------------------------------
    def keyPressEvent(self, event: QtGui.QKeyEvent):
        """Ensure copy works reliably in the output widget."""
        if event.matches(QtGui.QKeySequence.Copy):
            self._handle_copy_shortcut()
            event.accept()
            return
        super().keyPressEvent(event)

    def event(self, event: QtCore.QEvent):
        """Intercept ShortcutOverride so the host doesn't steal Ctrl+C."""
        if event.type() == QtCore.QEvent.ShortcutOverride:
            if isinstance(event, QtGui.QKeyEvent) and event.matches(
                QtGui.QKeySequence.Copy
            ):
                if self.textCursor().hasSelection():
                    event.accept()
                    return True
        return super().event(event)

    def eventFilter(self, obj, event: QtCore.QEvent):
        if event.type() in (QtCore.QEvent.KeyPress, QtCore.QEvent.ShortcutOverride):
            if isinstance(event, QtGui.QKeyEvent) and event.matches(
                QtGui.QKeySequence.Copy
            ):
                if self.textCursor().hasSelection():
                    self._handle_copy_shortcut()
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    # -- internals -----------------------------------------------------------
    def _handle_copy_shortcut(self):
        if self.textCursor().hasSelection():
            cursor = self.textCursor()
            text = cursor.selectedText().replace("\u2029", "\n")
            QtWidgets.QApplication.clipboard().setText(text)

    def _do_clear(self):
        """Run the injected clear callback, falling back to clearing the widget."""
        if self.clear_callback is not None:
            self.clear_callback()
        else:
            self.clear()

    def _context_menu(self, pos: QtCore.QPoint):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Clear", self._do_clear)
        menu.addAction("Copy", self.copy)  # Qt's built-in copy
        if self.context_menu_hook is not None:
            self.context_menu_hook(menu)
        menu.exec_(self.mapToGlobal(pos))


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    w = ScriptOutput()
    w.setWindowTitle("ScriptOutput Example")
    w.resize(600, 300)
    w.setPlainText(
        "// comment line\n"
        "Warning: something looks off\n"
        "Error: it broke\n"
        "# Result: 42\n"
        "Info: all good\n"
    )
    w.show()
    sys.exit(app.exec_())
