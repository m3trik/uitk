# !/usr/bin/python
# coding=utf-8
"""Unit tests for the shared ScriptOutput console widget.

Run standalone: python -m test.test_script_output
"""

import logging
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets, QtGui, QtTest  # noqa: E402
from uitk.widgets.scriptOutput import (  # noqa: E402
    ScriptOutput,
    COLOR_COMMENT,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_INFO,
)

# The traceback that motivated block formatting, exactly as it arrives in Blender: the
# capture tees stderr and delegates isatty() to Blender's system console, so CPython
# colors its own traceback and the escapes ride along into the widget.
BLENDER_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File \x1b[35m"space_view3d.py"\x1b[0m, line \x1b[35m5560\x1b[0m, '
    "in \x1b[35mdraw\x1b[0m\n"
    "    arm = \x1b[1;31medit_object.data\x1b[0m\n"
    "          \x1b[1;31m^^^^^^^^^^^^^^^^\x1b[0m\n"
    "\x1b[1;35mAttributeError\x1b[0m: \x1b[35m'NoneType' object has no attribute "
    "'data'\x1b[0m\n"
)


def _enter_event():
    """A real hover event, valid on both bindings.

    Qt6 types ``enterEvent`` as taking a ``QEnterEvent`` (a bare ``QEvent(Enter)`` is a
    TypeError there); Qt5 types it as ``QEvent``, which ``QEnterEvent`` satisfies by
    inheritance. Constructing the concrete event is therefore the one form that works
    under PySide2 and PySide6 alike.
    """
    pos = QtCore.QPointF(1, 1)
    return QtGui.QEnterEvent(pos, pos, pos)


def _key_click(widget, key, modifier):
    """``QTest.keyClick`` with *modifier*, then put the global modifier state back.

    ``QGuiApplication.keyboardModifiers()`` is a **cache of the last processed key
    event**, and QTest's key events go through the same platform path that maintains it —
    so a Ctrl+C here leaves every later test in the process believing Ctrl is still held.
    That is not hypothetical: uitk's own sequencer reads ``keyboardModifiers()`` to decide
    snapping (``sequencer/_draggable.py::snap_time`` rounds to 1 when Ctrl is down), so an
    unreleased Ctrl silently broke ``test_sequencer`` — but only in a full-suite run, never
    when that file ran alone. Releasing Ctrl explicitly keeps the leak contained here.
    """
    QtTest.QTest.keyClick(widget, key, modifier)
    # Release the key(s) matching the modifier actually passed — releasing a
    # hardcoded Ctrl would leak Shift/Alt if a future test used those.
    for mod, mod_key in (
        (QtCore.Qt.ControlModifier, QtCore.Qt.Key_Control),
        (QtCore.Qt.ShiftModifier, QtCore.Qt.Key_Shift),
        (QtCore.Qt.AltModifier, QtCore.Qt.Key_Alt),
    ):
        if modifier & mod:
            QtTest.QTest.keyRelease(widget, mod_key, QtCore.Qt.NoModifier)


class TestScriptOutput(QtBaseTestCase):
    """The host-agnostic console widget extracted from mayatk's ScriptConsole.

    Injectable clear/menu collaborators keep it free of maya.cmds/bpy so mayatk
    (workspaceControl) and blendertk (area-shadow skin) share one widget + one look.
    Added: 2026-07-04
    """

    def _line_colors(self, widget, lineno):
        """Set of (r,g,b) foreground colors applied to a document line by the highlighter."""
        widget.highlighter.rehighlight()
        QtWidgets.QApplication.processEvents()
        block = widget.document().findBlockByLineNumber(lineno)
        return {
            (fr.format.foreground().color().red(),
             fr.format.foreground().color().green(),
             fr.format.foreground().color().blue())
            for fr in block.layout().formats()
        }

    def _line_color(self, widget, lineno):
        """The single foreground color of a line, asserting the line is uniformly
        colored — what "the whole region is red" actually means."""
        colors = self._line_colors(widget, lineno)
        self.assertEqual(
            len(colors), 1, f"line {lineno} is not uniformly colored: {colors}"
        )
        return colors.pop()

    def test_default_rules_present(self):
        w = self.track_widget(ScriptOutput())
        self.assertEqual(len(w.highlighter.rules), 5)
        self.assertEqual(len(w.highlighter.block_rules), 1)  # traceback

    # -- exception class names (the line rules' blind spot) -------------------
    def test_exception_class_names_color_as_errors(self):
        """Regression: \\bError\\b never matched AttributeError.

        A word boundary needs a word/non-word transition and "AttributeError" has none
        before "Error", so the one line of a traceback that names the exception went
        uncolored — the exact symptom that surfaced this.
        """
        w = self.track_widget(ScriptOutput())
        for name in ("AttributeError", "ValueError", "RuntimeError", "TypeError"):
            with self.subTest(name=name):
                w.setPlainText(f"{name}: boom\n")
                self.assertIn(COLOR_ERROR, self._line_colors(w, 0))

    def test_exception_class_warnings_color_as_warnings(self):
        w = self.track_widget(ScriptOutput())
        w.setPlainText("DeprecationWarning: old api\n")
        self.assertIn(COLOR_WARNING, self._line_colors(w, 0))

    def test_error_word_still_requires_a_trailing_boundary(self):
        """The widened rule must not start painting every path with Error in it."""
        w = self.track_widget(ScriptOutput())
        w.setPlainText("wrote C:/ErrorLogs/run.txt\n")
        self.assertNotIn(COLOR_ERROR, self._line_colors(w, 0))

    # -- block regions --------------------------------------------------------
    def test_traceback_colors_as_one_region(self):
        """Header, indented frames, caret line AND the exception line — all one event."""
        w = self.track_widget(ScriptOutput())
        w.append_text(BLENDER_TRACEBACK)
        for lineno in range(5):
            with self.subTest(line=w.document().findBlockByLineNumber(lineno).text()):
                self.assertEqual(self._line_color(w, lineno), COLOR_ERROR)

    def test_block_region_closes_after_the_exception_line(self):
        """The region must not bleed into whatever prints next."""
        w = self.track_widget(ScriptOutput())
        w.append_text(BLENDER_TRACEBACK)
        w.append_text("business as usual\n")
        plain = w.document().blockCount() - 2  # the appended line
        self.assertEqual(
            w.document().findBlockByLineNumber(plain).text(), "business as usual"
        )
        self.assertNotIn(COLOR_ERROR, self._line_colors(w, plain))

    def test_indented_lines_outside_a_region_are_not_colored(self):
        """Indentation alone means nothing — only indentation under an open header."""
        w = self.track_widget(ScriptOutput())
        w.append_text("    just indented output\n")
        self.assertNotIn(COLOR_ERROR, self._line_colors(w, 0))

    def test_chained_traceback_colors_the_connector_line(self):
        """The connector prints outside any indented region; it opens a region itself."""
        w = self.track_widget(ScriptOutput())
        w.append_text(
            "Traceback (most recent call last):\n"
            '  File "a.py", line 1, in f\n'
            "ValueError: first\n"
            "\n"
            "During handling of the above exception, another exception occurred:\n"
            "\n"
            "Traceback (most recent call last):\n"
            '  File "b.py", line 2, in g\n'
            "AttributeError: second\n"
        )
        for lineno in (0, 1, 2, 4, 6, 7, 8):
            with self.subTest(line=w.document().findBlockByLineNumber(lineno).text()):
                self.assertEqual(self._line_color(w, lineno), COLOR_ERROR)

    def test_block_region_survives_chunked_streaming(self):
        """Real output arrives a write at a time, not as one string."""
        w = self.track_widget(ScriptOutput())
        for line in BLENDER_TRACEBACK.splitlines(keepends=True):
            w.append_text(line)
        for lineno in range(5):
            self.assertEqual(self._line_color(w, lineno), COLOR_ERROR)

    # -- ANSI ------------------------------------------------------------------
    def test_ansi_escapes_are_stripped(self):
        """QTextEdit renders VT100 as literal garbage; the text must arrive clean."""
        w = self.track_widget(ScriptOutput())
        w.append_text(BLENDER_TRACEBACK)
        text = w.toPlainText()
        self.assertNotIn("\x1b", text)
        self.assertNotIn("[35m", text)
        self.assertIn('  File "space_view3d.py", line 5560, in draw', text)
        self.assertIn("AttributeError: 'NoneType' object has no attribute 'data'", text)

    def test_ansi_only_chunk_appends_nothing(self):
        w = self.track_widget(ScriptOutput())
        w.append_text("\x1b[0m")
        self.assertEqual(w.toPlainText(), "")

    # -- log level (the host's own classification) ------------------------------
    def test_level_beats_the_words_in_the_text(self):
        """A DEBUG record mentioning "error" is not an error — the level is authoritative."""
        w = self.track_widget(ScriptOutput())
        w.append_text("checking for error conditions\n", level=logging.DEBUG)
        self.assertEqual(self._line_color(w, 0), COLOR_COMMENT)

    def test_level_colors_by_record_not_text(self):
        w = self.track_widget(ScriptOutput())
        for level, color in (
            (logging.DEBUG, COLOR_COMMENT),
            (logging.INFO, COLOR_INFO),
            (logging.WARNING, COLOR_WARNING),
            (logging.ERROR, COLOR_ERROR),
            (logging.CRITICAL, COLOR_ERROR),
        ):
            with self.subTest(level=logging.getLevelName(level)):
                w.clear()
                w.append_text("plain message\n", level=level)
                self.assertEqual(self._line_color(w, 0), color)

    def test_custom_level_resolves_to_the_bucket_below(self):
        """Level 25 (between INFO and WARNING) must land on INFO, not fall through."""
        w = self.track_widget(ScriptOutput())
        w.append_text("custom level\n", level=25)
        self.assertEqual(self._line_color(w, 0), COLOR_INFO)

    def test_level_survives_rehighlight(self):
        """Recorded on the block, so a rehighlight (theme/rule change) can't lose it."""
        w = self.track_widget(ScriptOutput())
        w.append_text("checking for error conditions\n", level=logging.DEBUG)
        w.highlighter.rehighlight()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self._line_color(w, 0), COLOR_COMMENT)

    def test_level_does_not_leak_to_later_appends(self):
        """pending_level is per-insert; a levelless write must fall back to the rules."""
        w = self.track_widget(ScriptOutput())
        w.append_text("first\n", level=logging.ERROR)
        w.append_text("second\n")
        self.assertEqual(self._line_color(w, 0), COLOR_ERROR)
        self.assertNotIn(COLOR_ERROR, self._line_colors(w, 1))

    def test_level_does_not_leak_to_blocks_trimmed_by_max_blocks(self):
        """A levelled append that trips the block cap must not repaint the scrollback.

        Enforcing `maximumBlockCount` drops blocks off the *front*, which Qt signals as
        its own contentsChange and reformats inside the same insertText call. Ambient
        state held for the duration of the insert lands on those blocks too — so the
        oldest surviving line turned red on every levelled write past the cap.
        """
        w = self.track_widget(ScriptOutput(max_blocks=6))
        for i in range(6):
            w.append_text(f"plain line {i}\n")  # no level: must stay uncolored
        w.append_text("boom\n", level=logging.ERROR)
        for lineno in range(4):
            text = w.document().findBlockByLineNumber(lineno).text()
            with self.subTest(line=text):
                self.assertTrue(text.startswith("plain line"), text)
                self.assertNotIn(COLOR_ERROR, self._line_colors(w, lineno))

    def test_levelled_multiline_chunk_tags_every_line_it_wrote(self):
        """One record can span lines (a formatted traceback); all of them are the record."""
        w = self.track_widget(ScriptOutput())
        w.append_text("line a\nline b\nline c\n", level=logging.ERROR)
        for lineno in range(3):
            self.assertEqual(self._line_color(w, lineno), COLOR_ERROR)

    def test_levelled_chunk_split_by_carriage_returns(self):
        """Qt splits blocks on \\r and \\r\\n too, not just \\n.

        Counting only "\\n" undercounts the blocks a chunk wrote, so everything before a
        bare carriage return went unstamped — a levelled record came out half-colored.
        """
        w = self.track_widget(ScriptOutput())
        w.append_text("first\rsecond\r\nthird\n", level=logging.ERROR)
        for lineno in range(3):
            with self.subTest(line=w.document().findBlockByLineNumber(lineno).text()):
                self.assertEqual(self._line_color(w, lineno), COLOR_ERROR)

    def test_levelled_chunk_larger_than_max_blocks(self):
        """A record longer than the cap: the cap eats its own head mid-insert, so the
        first-block arithmetic must clamp rather than address a negative block."""
        w = self.track_widget(ScriptOutput(max_blocks=4))
        w.append_text("".join(f"rec {i}\n" for i in range(10)), level=logging.ERROR)
        for lineno in range(w.document().blockCount()):
            if w.document().findBlockByLineNumber(lineno).text():
                self.assertEqual(self._line_color(w, lineno), COLOR_ERROR)

    def test_levelless_append_keeps_the_maya_look(self):
        """No regression: Maya passes no level, so the word rules stay in charge."""
        w = self.track_widget(ScriptOutput())
        w.append_text("// Error: something failed //\n")
        self.assertIn(COLOR_ERROR, self._line_colors(w, 0))

    def test_error_and_warning_lines_colored(self):
        w = self.track_widget(ScriptOutput())
        w.setPlainText("Warning: x\nError: boom\n")
        self.assertIn((205, 200, 120), self._line_colors(w, 0))  # warning
        self.assertIn((165, 75, 75), self._line_colors(w, 1))    # error

    def test_highlight_is_case_insensitive(self):
        """Blender's uppercase logging levels must color like Maya's capitalized text."""
        w = self.track_widget(ScriptOutput())
        w.setPlainText("ERROR: boom\n")
        self.assertIn((165, 75, 75), self._line_colors(w, 0))

    def test_clear_callback_controls_clearing(self):
        hits = []
        w = self.track_widget(ScriptOutput(clear_callback=lambda: hits.append(1)))
        w.setPlainText("keep me")
        w._do_clear()
        self.assertEqual(hits, [1])
        self.assertEqual(w.toPlainText(), "keep me")  # callback owns the clear

    def test_default_clear_empties_widget(self):
        w = self.track_widget(ScriptOutput())
        w.setPlainText("bye")
        w._do_clear()
        self.assertEqual(w.toPlainText(), "")

    def test_context_menu_hook_invoked(self):
        """A host (Maya's Echo toggle) appends to the real menu, after the built-ins."""
        added = []

        def hook(menu):
            added.append(menu)
            menu.addAction("Echo All Commands")

        w = self.track_widget(ScriptOutput(context_menu_hook=hook))
        menu = w.build_context_menu()  # the real menu (exec_ would block)
        self.assertEqual(len(added), 1)
        self.assertTrue(any(a.text() == "Echo All Commands" for a in menu.actions()))

    def test_no_clear_on_hide(self):
        """Regression vs uitk.TextEdit (which wipes its document on hide)."""
        w = self.track_widget(ScriptOutput())
        w.setPlainText("persist across hide")
        w.show(); QtWidgets.QApplication.processEvents()
        w.hide(); QtWidgets.QApplication.processEvents()
        w.show(); QtWidgets.QApplication.processEvents()
        self.assertEqual(w.toPlainText(), "persist across hide")

    def test_copy_joins_with_newlines(self):
        w = self.track_widget(ScriptOutput())
        w.setPlainText("line1\nline2")
        w.selectAll()
        w._handle_copy_shortcut()
        self.assertEqual(QtWidgets.QApplication.clipboard().text(), "line1\nline2")

    def test_append_text_preserves_stream_newlines(self):
        w = self.track_widget(ScriptOutput())
        w.append_text("a\n")
        w.append_text("b\n")
        self.assertEqual(w.toPlainText(), "a\nb\n")

    def test_append_text_preserves_user_selection(self):
        """Streaming output must not collapse a selection the user is making to copy."""
        w = self.track_widget(ScriptOutput())
        w.setPlainText("hello world")
        cursor = w.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(5, QtGui.QTextCursor.KeepAnchor)
        w.setTextCursor(cursor)
        self.assertEqual(w.textCursor().selectedText(), "hello")
        w.append_text("\nstreamed output\n")
        self.assertEqual(w.textCursor().selectedText(), "hello")  # selection survives

    def test_max_blocks_caps_growth(self):
        """A streaming console must not grow the document unbounded."""
        w = self.track_widget(ScriptOutput(max_blocks=10))
        for i in range(60):
            w.append_text(f"line {i}\n")
        self.assertLessEqual(w.document().blockCount(), 10)

    def test_app_wide_copy_scopes_the_shortcut(self):
        """False → widget-scoped (won't hijack Ctrl+C app-wide); True → application-scoped."""
        import qtpy.QtCore as QtCore
        w_local = self.track_widget(ScriptOutput(app_wide_copy=False))
        self.assertEqual(w_local._copy_shortcut.context(),
                         QtCore.Qt.WidgetWithChildrenShortcut)
        w_global = self.track_widget(ScriptOutput(app_wide_copy=True))
        self.assertEqual(w_global._copy_shortcut.context(), QtCore.Qt.ApplicationShortcut)

    # -- hover-to-focus (what makes the shortcuts reachable at all) -----------
    def _hover(self, widget):
        """Deliver a real QEvent.Enter, recording setFocus calls.

        Records rather than reading ``hasFocus()``: whether a synthetic Enter on an
        offscreen-QPA widget produces real platform focus is exactly the kind of
        environment-dependent state that flakes (see test_focus_on_hover_takes_real_focus
        for the shown-widget check). What this pins is our own decision — did the widget
        ask for focus, and with which reason.
        """
        calls = []
        widget.setFocus = lambda *a: calls.append(a[0] if a else None)  # noqa: E731
        widget.enterEvent(_enter_event())
        return calls

    def test_focus_on_hover_default_on(self):
        """Hovering must focus, else Ctrl+C/Ctrl+A never reach the console (the DCC eats them)."""
        w = self.track_widget(ScriptOutput())
        self.assertTrue(w.focus_on_hover)  # on by default for both hosts
        self.assertEqual(self._hover(w), [QtCore.Qt.MouseFocusReason])

    def test_focus_on_hover_can_be_disabled(self):
        w = self.track_widget(ScriptOutput(focus_on_hover=False))
        self.assertEqual(self._hover(w), [])

    def test_focus_on_hover_takes_real_focus(self):
        """End-to-end on a shown widget: hover → the widget really holds focus."""
        w = self.track_widget(ScriptOutput())
        w.show()
        w.activateWindow()
        QtWidgets.QApplication.processEvents()
        w.clearFocus()
        self.assertFalse(w.hasFocus())
        w.enterEvent(_enter_event())
        QtWidgets.QApplication.processEvents()
        self.assertTrue(w.hasFocus())

    def test_hover_focus_makes_ctrl_c_copy_without_clicking(self):
        """The user-facing behavior: hover + Ctrl+C copies, no click-to-focus first."""
        w = self.track_widget(ScriptOutput(app_wide_copy=False))
        w.setPlainText("copy me")
        w.show()
        w.activateWindow()
        QtWidgets.QApplication.processEvents()
        w.clearFocus()
        w.selectAll()
        QtWidgets.QApplication.clipboard().clear()
        w.enterEvent(_enter_event())  # hover, never a click
        QtWidgets.QApplication.processEvents()
        _key_click(w, QtCore.Qt.Key_C, QtCore.Qt.ControlModifier)
        self.assertEqual(QtWidgets.QApplication.clipboard().text(), "copy me")

    def test_modifier_state_is_not_leaked_to_other_tests(self):
        """Guard for the helper above — a stuck Ctrl silently broke test_sequencer's
        snapping (it reads keyboardModifiers()) in full-suite runs only."""
        w = self.track_widget(ScriptOutput())
        w.setPlainText("x")
        w.show()
        QtWidgets.QApplication.processEvents()
        _key_click(w, QtCore.Qt.Key_C, QtCore.Qt.ControlModifier)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(
            QtWidgets.QApplication.keyboardModifiers(), QtCore.Qt.NoModifier
        )

    # -- context menu ---------------------------------------------------------
    def _menu_for(self, widget):
        """The REAL menu (``build_context_menu``), minus the blocking exec_."""
        return widget.build_context_menu()

    def test_context_menu_advertises_shortcuts(self):
        """The shortcut hints are how a hover-focus binding is discoverable at all."""
        w = self.track_widget(ScriptOutput())
        actions = {a.text(): a for a in self._menu_for(w).actions()}
        self.assertEqual(
            actions["Copy"].shortcut(), QtGui.QKeySequence(QtGui.QKeySequence.Copy)
        )
        self.assertEqual(
            actions["Select All"].shortcut(),
            QtGui.QKeySequence(QtGui.QKeySequence.SelectAll),
        )

    def test_context_menu_copy_disabled_without_selection(self):
        w = self.track_widget(ScriptOutput())
        w.setPlainText("text")
        self.assertFalse({a.text(): a for a in self._menu_for(w).actions()}["Copy"].isEnabled())
        w.selectAll()
        self.assertTrue({a.text(): a for a in self._menu_for(w).actions()}["Copy"].isEnabled())

    def test_read_only_mirror_offers_no_paste(self):
        """Deliberate: this mirrors the host's output (reporter / stdout tee) — there is
        nothing to paste into, same as Maya's own Script Editor output pane."""
        w = self.track_widget(ScriptOutput())
        self.assertTrue(w.isReadOnly())
        texts = [a.text() for a in self._menu_for(w).actions()]
        self.assertNotIn("Paste", texts)

    def test_select_all_shortcut_works_in_read_only(self):
        """Ctrl+A must reach QTextEdit's own handling — keyPressEvent only claims Copy."""
        w = self.track_widget(ScriptOutput())
        w.setPlainText("line1\nline2")
        w.show()
        w.activateWindow()
        QtWidgets.QApplication.processEvents()
        w.enterEvent(_enter_event())
        _key_click(w, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        self.assertEqual(
            w.textCursor().selectedText().replace(" ", "\n"), "line1\nline2"
        )


if __name__ == "__main__":
    unittest.main()
