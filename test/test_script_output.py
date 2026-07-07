# !/usr/bin/python
# coding=utf-8
"""Unit tests for the shared ScriptOutput console widget.

Run standalone: python -m test.test_script_output
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtGui  # noqa: E402
from uitk.widgets.scriptOutput import ScriptOutput  # noqa: E402


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

    def test_default_rules_present(self):
        w = self.track_widget(ScriptOutput())
        self.assertEqual(len(w.highlighter.rules), 5)

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
        added = []

        def hook(menu):
            added.append(menu)
            menu.addAction("Echo All Commands")

        w = self.track_widget(ScriptOutput(context_menu_hook=hook))
        menu = QtWidgets.QMenu()
        w.context_menu_hook(menu)  # the hook portion of _context_menu (exec_ would block)
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


if __name__ == "__main__":
    unittest.main()
