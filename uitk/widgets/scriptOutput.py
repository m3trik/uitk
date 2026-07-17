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

Coloring is layered, weakest signal first, so each layer overrides the one below:

1. :class:`ScriptHighlightRule` — regex over a single line. Matches words like
   ``Error`` / ``Warning`` / ``Result`` in the text, so the same rules color a Maya
   reporter dump and a Blender ``stdout`` redirect identically.
2. :class:`ScriptBlockRule` — regex over a multi-line *region*. Output that is
   structurally multi-line (a Python traceback) is one event, not N lines; a line
   rule reading ``  File "…", line 5560`` in isolation has nothing to match on.
3. **Log level** — when the host knows a chunk's origin (``logging`` record level),
   it passes it to :meth:`ScriptOutput.append_text` and the level wins over any word
   the text happens to contain. Authoritative where it's available; Maya mirrors a
   reporter and has none, which is why the word rules stay the base layer.
"""
import re
import logging
from typing import Callable, Dict, List, Optional, Tuple
from qtpy import QtWidgets, QtGui, QtCore
import pythontk as ptk

# What QTextCursor.insertText turns into a new paragraph — i.e. what actually splits a
# chunk into document blocks. Counting only "\n" undercounts a stream carrying bare
# carriage returns, which leaves the lines before one unstamped (see
# ScriptOutput._stamp_level). Order matters: "\r\n" must match before the single-char
# alternatives so it counts once, not twice.
PARAGRAPH_BREAK_RE = re.compile("\r\n|[\n\r\u2029]")

# The canonical palette — shared by the word rules, the block rules and the level map so
# an error reads the same whether it was identified by a word, a traceback header or a
# logging level.
COLOR_COMMENT = (90, 90, 90)
COLOR_WARNING = (205, 200, 120)
COLOR_ERROR = (165, 75, 75)
COLOR_RESULT = (115, 215, 150)
COLOR_INFO = (130, 220, 210)  # pastel teal


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


def _char_format(
    color: Tuple[int, int, int],
    bg_color: Optional[Tuple[int, int, int]] = None,
    bold: bool = False,
    italic: bool = False,
    font: Optional[QtGui.QFont] = None,
) -> QtGui.QTextCharFormat:
    """Build a monospace ``QTextCharFormat`` — the one construction shared by the line
    rules, the block rules and the level map, so all three stay visually consistent."""
    fmt = QtGui.QTextCharFormat()
    fmt.setForeground(QtGui.QColor(*color))
    if bg_color:
        fmt.setBackground(QtGui.QColor(*bg_color))
    rule_font = QtGui.QFont(font) if font is not None else _monospace_font()
    rule_font.setBold(bold)
    rule_font.setItalic(italic)
    fmt.setFont(rule_font)
    return fmt


class ScriptHighlightRule:
    """One regex → text-format rule for :class:`ScriptHighlighter`, scoped to a line."""

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
        self.format = _char_format(color, bg_color, bold, italic, font)


class ScriptBlockRule:
    """One format spanning a multi-line *region* — the altitude a line rule can't reach.

    A Python traceback is one event whose lines are individually unmatchable: the header
    names no error, the ``File "…", line N`` frames name no error, and only the last line
    carries the exception type. Matching per-line therefore colors either nothing or only
    the tail. This rule opens on ``start_pattern``, absorbs every following **indented**
    line (blank lines too, with ``allow_blank``), and closes on the first line that is
    neither — including that closing line when ``include_end``, since that is exactly
    where the exception type lives.

    Implemented over ``QSyntaxHighlighter``'s block-state channel, so the region survives
    streaming appends: each line only needs its predecessor's state, not a re-scan.

    Parameters:
        color: Foreground RGB for the whole region.
        start_pattern: Regex opening the region, tested per line. Searched, not
            anchored — anchor it with ``^`` (as the defaults do) unless a region really
            should open on a match anywhere in the line.
        include_end: Color the closing line too (default True).
        allow_blank: Treat blank lines as continuations rather than as the end
            (default False — a blank line closes the region).
    """

    def __init__(
        self,
        color: Tuple[int, int, int],
        start_pattern: str,
        bg_color: Optional[Tuple[int, int, int]] = None,
        bold: bool = False,
        italic: bool = False,
        font: Optional[QtGui.QFont] = None,
        include_end: bool = True,
        allow_blank: bool = False,
    ):
        self.pattern = QtCore.QRegularExpression(start_pattern)
        self.format = _char_format(color, bg_color, bold, italic, font)
        self.include_end = include_end
        self.allow_blank = allow_blank

    def starts(self, text: str) -> bool:
        """True when ``text`` opens a region."""
        return self.pattern.match(text).hasMatch()

    def continues(self, text: str) -> bool:
        """True when ``text`` belongs to an already-open region — i.e. it is indented
        (the traceback frame/source/caret lines), or blank when ``allow_blank``."""
        if not text.strip():
            return self.allow_blank
        return text[:1].isspace()


class ScriptHighlighter(QtGui.QSyntaxHighlighter):
    """Apply line rules, block rules and per-block log levels to a text document.

    Precedence is weakest → strongest: a line rule can be overridden by a block rule
    (structure beats a word), and both by a log level (the host's own classification
    beats any guess made from the text).
    """

    def __init__(
        self,
        doc: QtGui.QTextDocument,
        rules: Optional[List[ScriptHighlightRule]] = None,
        block_rules: Optional[List[ScriptBlockRule]] = None,
        level_formats: Optional[Dict[int, QtGui.QTextCharFormat]] = None,
    ):
        super().__init__(doc)
        self.rules = rules if rules is not None else default_rules()
        self.block_rules = block_rules if block_rules is not None else default_block_rules()
        self.level_formats = (
            level_formats if level_formats is not None else default_level_formats()
        )
        # The level being stamped onto a block right now — set only for the duration of
        # stamp_level's own rehighlightBlock call, never across an insert (see
        # stamp_level). Recorded as block user data on the way past, so it survives a
        # later rehighlight, when there is no stamp in flight.
        self.pending_level: Optional[int] = None

    def highlightBlock(self, text: str) -> None:
        for rule in self.rules:
            match_iter = rule.pattern.globalMatch(text)
            while match_iter.hasNext():
                match = match_iter.next()
                self.setFormat(
                    match.capturedStart(), match.capturedLength(), rule.format
                )

        self._highlight_region(text)

        fmt = self._level_format(self._block_level(text))
        if fmt is not None:
            self.setFormat(0, len(text), fmt)

    def stamp_level(self, block: QtGui.QTextBlock, level: int) -> None:
        """Record ``level`` on one ``block`` and recolor it.

        The level is stamped block by block, *after* an insert settles — never held
        across one. Enforcing a document's ``maximumBlockCount`` drops blocks off the
        front, and Qt reformats those inside the same ``insertText`` call, so ambient
        state spanning the insert also lands on the oldest surviving line and repaints
        the scrollback. Scoping it to a single explicit rehighlight is what keeps the
        level on the block it belongs to.
        """
        self.pending_level = level
        try:
            self.rehighlightBlock(block)
        finally:
            self.pending_level = None

    # -- internals -----------------------------------------------------------
    def _highlight_region(self, text: str) -> None:
        """Continue, close, or open a block region on this line, tracking it in the
        block state so the next line knows where it stands."""
        index = self.previousBlockState()
        open_rule = self.block_rules[index] if 0 <= index < len(self.block_rules) else None
        if open_rule is not None:
            if open_rule.continues(text):
                self.setFormat(0, len(text), open_rule.format)
                self.setCurrentBlockState(index)
                return
            if open_rule.include_end and text.strip():
                self.setFormat(0, len(text), open_rule.format)  # the exception line
            # Region closed. Fall through: this line may itself open the next one
            # (chained tracebacks put a new header right after the previous exception).
        for i, rule in enumerate(self.block_rules):
            if rule.starts(text):
                self.setFormat(0, len(text), rule.format)
                self.setCurrentBlockState(i)
                return
        self.setCurrentBlockState(-1)

    def _block_level(self, text: str) -> Optional[int]:
        """The log level of the current block: the level being stamped by
        :meth:`stamp_level` (recording it on the block), else whatever was recorded
        earlier.

        The ``text`` guard keeps a stamp off empty blocks. The caller already skips
        them, but ``rehighlightBlock`` cascades forward while block state keeps changing,
        and the block after a record is the trailing empty one a newline leaves behind —
        which belongs to whatever prints next, not to this record.
        """
        if self.pending_level is not None and text:
            self.setCurrentBlockUserData(_BlockLevel(self.pending_level))
            return self.pending_level
        data = self.currentBlockUserData()
        return data.level if isinstance(data, _BlockLevel) else None

    def _level_format(self, level: Optional[int]) -> Optional[QtGui.QTextCharFormat]:
        """The format for ``level``, resolved by threshold — the highest configured
        level at or below it — so custom/intermediate levels (e.g. 25) still land in the
        right bucket instead of falling through unformatted."""
        if level is None:
            return None
        fmt = None
        for threshold in sorted(self.level_formats):
            if level >= threshold:
                fmt = self.level_formats[threshold]
        return fmt


class _BlockLevel(QtGui.QTextBlockUserData):
    """Carries a document block's originating log level across rehighlights."""

    def __init__(self, level: int):
        super().__init__()
        self.level = level


def default_rules() -> List[ScriptHighlightRule]:
    """The default single-line log-coloring rules (Maya-parity palette).

    Kept as the canonical look so a Blender console is pixel-identical to the
    Maya one. Override by passing ``rules=`` to :class:`ScriptOutput`.
    """
    # The word rules are case-insensitive ((?i)) so they color Maya's capitalized
    # reporter text ("// Error:") AND Blender's uppercase logging levels ("ERROR:")
    # identically — no regression to the Maya look, strictly wider coverage.
    #
    # \b\w*Error\b (not \bError\b) also catches the exception CLASS names Python
    # actually raises — AttributeError, ValueError, RuntimeError. A bare \bError\b
    # requires a word boundary before "Error", and "AttributeError" has none, so the
    # line naming the exception was the one line a traceback never got colored on.
    # The trailing \b still keeps it tight: "ErrorLogs" stays unmatched.
    return [
        ScriptHighlightRule(COLOR_COMMENT, r"(//|#).+"),  # comment
        ScriptHighlightRule(COLOR_WARNING, r"(?i).*\b\w*Warning\b.*"),  # warning
        ScriptHighlightRule(COLOR_ERROR, r"(?i).*\b\w*Error\b.*"),  # error
        ScriptHighlightRule(COLOR_RESULT, r"(?i).*\bResult\b.*"),  # result
        ScriptHighlightRule(COLOR_INFO, r"(?i).*\bInfo\b.*"),  # info
    ]


def default_block_rules() -> List[ScriptBlockRule]:
    """The default multi-line region rules — Python tracebacks, header to exception.

    Both chaining connectors are start patterns of their own: a chained traceback prints
    ``… another exception occurred:`` outside any indented region, so without them the
    connector line would read as plain text between two colored regions.
    """
    return [
        ScriptBlockRule(
            COLOR_ERROR,
            r"^\s*(Traceback \(most recent call last\):"
            r"|During handling of the above exception, another exception occurred:"
            r"|The above exception was the direct cause of the following exception:)",
        ),
    ]


def default_level_formats() -> Dict[int, QtGui.QTextCharFormat]:
    """The default ``logging`` level → format map (same palette as the word rules).

    Resolved by threshold, so ``CRITICAL`` picks up its own bold-red entry while any
    custom level in between falls to the bucket below it. ``NOTSET`` (0) maps to nothing
    — an unclassified record is left to the word/block rules rather than mis-colored.
    """
    return {
        logging.DEBUG: _char_format(COLOR_COMMENT),
        logging.INFO: _char_format(COLOR_INFO),
        logging.WARNING: _char_format(COLOR_WARNING),
        logging.ERROR: _char_format(COLOR_ERROR),
        logging.CRITICAL: _char_format(COLOR_ERROR, bold=True),
    }


class ScriptOutput(QtWidgets.QTextEdit):
    """Read-only, syntax-highlighted console view — host-agnostic.

    Injectable collaborators (DIP — no ``maya.cmds`` / ``bpy`` here):

    Parameters:
        parent: Qt parent.
        rules: Single-line highlight rules; defaults to :func:`default_rules` (Maya
            palette).
        block_rules: Multi-line region rules; defaults to :func:`default_block_rules`
            (Python tracebacks).
        level_formats: ``logging`` level → format map applied to chunks whose level the
            host passes to :meth:`append_text`; defaults to
            :func:`default_level_formats`.
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
        focus_on_hover: Take keyboard focus when the mouse enters (default True), so
            the console's shortcuts — Ctrl+C copy, Ctrl+A select-all, and PgUp/PgDn/
            Home/End/arrow scrollback navigation — work on hover without clicking in
            first. Both hosts need it and neither can rely on the DCC handing keys
            over by itself: Maya routes hotkeys through its own app shortcuts, and in
            Blender the console is a child of the GHOST window, so the host would
            otherwise swallow every keystroke. It also matches Blender's own
            focus-follows-mouse paradigm (hover an area → that area takes the keys).
            A host embedding this in a foreign (non-Qt) window is responsible for the
            **OS**-level focus hand-off — Qt focus alone doesn't redirect native key
            messages (see ``blendertk.ui_utils.qt_dock.QtDock``).
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
        block_rules: Optional[List[ScriptBlockRule]] = None,
        level_formats: Optional[Dict[int, QtGui.QTextCharFormat]] = None,
        clear_callback: Optional[Callable[[], None]] = None,
        context_menu_hook: Optional[Callable[[QtWidgets.QMenu], None]] = None,
        app_wide_copy: bool = True,
        max_blocks: Optional[int] = None,
        point_size: int = 9,
        focus_on_hover: bool = True,
    ):
        super().__init__(parent)
        self.setProperty("class", self.__class__.__name__)  # QSS theming hook
        self.clear_callback = clear_callback
        self.context_menu_hook = context_menu_hook
        self.focus_on_hover = focus_on_hover

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

        self.highlighter = ScriptHighlighter(
            self.document(), rules, block_rules, level_formats
        )

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
        """Replace the single-line highlight rules and re-highlight the document."""
        self.highlighter.rules = rules
        self.highlighter.rehighlight()

    def set_block_rules(self, block_rules: List[ScriptBlockRule]) -> None:
        """Replace the multi-line region rules and re-highlight the document."""
        self.highlighter.block_rules = block_rules
        self.highlighter.rehighlight()

    def append_text(self, text: str, level: Optional[int] = None) -> None:
        """Append raw ``text`` at the end without disturbing the user's selection/caret.

        Inserts through a **detached** cursor (not ``self.textCursor()``), so a live
        selection — e.g. the user is mid-drag selecting output to copy — survives a
        streaming write instead of being collapsed to the end every tick. Auto-scrolls
        only when the view is already at the bottom (terminal behavior: don't yank the
        user back down while they've scrolled up to read). Preserves the stream's own
        newlines (``insertText``, not ``append`` which injects a paragraph per call);
        the highlighter recolors each block.

        ANSI escapes are stripped on the way in. A console that tees a TTY stream
        receives them whether it wants them or not (CPython emits colored tracebacks
        when ``stderr.isatty()``), and this view doesn't interpret VT100 — unstripped,
        they render as literal ``[35m`` garbage. Color here comes from the rules, so the
        look stays identical to Maya's, which mirrors a reporter and has no escapes.

        Parameters:
            text: The raw chunk to append.
            level: The ``logging`` level this chunk came from, when the host knows it.
                Takes precedence over the word/block rules for the lines it creates —
                so a DEBUG record that merely mentions "error" stays grey. ``None``
                (Maya's reporter mirror, plain ``stdout``) leaves the rules in charge.
        """
        text = ptk.strip_ansi(text)
        if not text:  # a chunk that was nothing but escapes
            return
        scrollbar = self.verticalScrollBar()
        at_bottom = scrollbar is None or scrollbar.value() >= scrollbar.maximum() - 4
        cursor = QtGui.QTextCursor(self.document())
        cursor.movePosition(QtGui.QTextCursor.End)
        cursor.insertText(text)
        if level is not None:
            breaks = len(PARAGRAPH_BREAK_RE.findall(text))
            self._stamp_level(cursor.blockNumber(), breaks, level)
        if at_bottom and scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())

    def _stamp_level(self, last_block: int, breaks: int, level: int) -> None:
        """Stamp ``level`` onto the blocks the just-inserted chunk wrote.

        Deliberately after the insert, never across it — see
        :meth:`ScriptHighlighter.stamp_level`. ``last_block`` is the cursor's block and
        ``breaks`` the chunk's paragraph-break count (:data:`PARAGRAPH_BREAK_RE` — Qt
        splits on more than ``\\n``), which together bound what it wrote; the lower bound
        is clamped because a chunk longer than ``max_blocks`` has its own head trimmed
        away mid-insert.
        """
        doc = self.document()
        for number in range(max(0, last_block - breaks), last_block + 1):
            block = doc.findBlockByNumber(number)
            # Skip the trailing empty block a newline-terminated chunk leaves behind:
            # it belongs to whatever prints next, not to this record.
            if block.isValid() and block.text():
                self.highlighter.stamp_level(block, level)

    # -- Qt overrides (camelCase) --------------------------------------------
    def enterEvent(self, event: QtCore.QEvent):
        """Focus on hover (see ``focus_on_hover``) so the console's shortcuts reach it
        without clicking in first.

        ``MouseFocusReason`` — not the default ``OtherFocusReason`` — so widgets that
        react to *why* focus moved read this correctly as a pointer-driven focus (e.g.
        uitk's ``hide_on_leave`` autofocus demotion). Qt only sends ``Enter`` when the
        cursor crosses into the widget's own geometry; moving onto a child (viewport,
        scrollbar) does not re-fire it, so this is once per hover, not per mouse-move.
        """
        super().enterEvent(event)
        if self.focus_on_hover:
            self.setFocus(QtCore.Qt.MouseFocusReason)

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

    def build_context_menu(self) -> QtWidgets.QMenu:
        """The context menu, built but not shown (``_context_menu`` execs it).

        Separate from the exec so it can be asserted on without a blocking modal — and
        so a host can reuse the exact menu elsewhere (a header button, say).

        The Copy / Select All rows carry their key sequences purely as **hints** — a
        transient menu's actions aren't live shortcuts; the real bindings are the
        ``_copy_shortcut`` above and QTextEdit's own read-only key handling. Showing
        them here is what makes the hover-focus shortcuts discoverable at all. Copy is
        disabled without a selection rather than silently copying nothing, and routes
        through ``_handle_copy_shortcut`` (not Qt's ``copy``) so the menu and Ctrl+C put
        identical plain text on the clipboard.

        No Paste/Cut row, by design: this is a read-only mirror of the host's output
        (Maya's reporter / a stdout tee), so there is nothing to paste into — same as
        Maya's own Script Editor output pane.
        """
        menu = QtWidgets.QMenu(self)
        menu.addAction("Clear", self._do_clear)
        copy_action = menu.addAction("Copy", self._handle_copy_shortcut)
        copy_action.setShortcut(QtGui.QKeySequence.Copy)
        copy_action.setEnabled(self.textCursor().hasSelection())
        select_all_action = menu.addAction("Select All", self.selectAll)
        select_all_action.setShortcut(QtGui.QKeySequence.SelectAll)
        if self.context_menu_hook is not None:
            self.context_menu_hook(menu)
        return menu

    def _context_menu(self, pos: QtCore.QPoint):
        self.build_context_menu().exec_(self.mapToGlobal(pos))


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    w = ScriptOutput()
    w.setWindowTitle("ScriptOutput Example")
    w.resize(700, 400)
    w.append_text(
        "// comment line\n"
        "Warning: something looks off\n"
        "Error: it broke\n"
        "# Result: 42\n"
        "Info: all good\n"
    )
    # A traceback: colored as one region, header through exception line — and arriving
    # with the ANSI escapes CPython emits to a TTY, which must not reach the view.
    w.append_text(
        "Traceback (most recent call last):\n"
        '  File \x1b[35m"space_view3d.py"\x1b[0m, line \x1b[35m5560\x1b[0m, in \x1b[35mdraw\x1b[0m\n'
        "    arm = \x1b[1;31medit_object.data\x1b[0m\n"
        "          \x1b[1;31m^^^^^^^^^^^^^^^^\x1b[0m\n"
        "\x1b[1;35mAttributeError\x1b[0m: \x1b[35m'NoneType' object has no attribute 'data'\x1b[0m\n"
    )
    # Level beats the words: grey despite saying "error", red despite saying nothing.
    w.append_text("DEBUG: checking for error conditions\n", level=logging.DEBUG)
    w.append_text("something went wrong\n", level=logging.ERROR)
    w.show()
    sys.exit(app.exec_())
