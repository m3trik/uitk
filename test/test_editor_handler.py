# !/usr/bin/python
# coding=utf-8
"""Tests for ``EditorHandler`` — the bundled editors as launcher rows.

Covers:
- Every ``sb.editors`` window is a row (kind ``editor``); the UI Browser
  lists itself
- ``handlers={"editor": None}`` opts a Switchboard out
- launch / close / is_visible / focus, and row refresh when an editor hides
  by any path
- ``launch_code``: the browser's snippet carries the registry, and opens the
  browser -- listing the registry -- in a fresh interpreter
"""

import os
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

import pythontk as ptk
from qtpy import QtWidgets
from uitk.handlers.editor_handler import EditorHandler
from uitk.switchboard import Switchboard


def _write_ui(path, name):
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n'
            f" <class>{name.capitalize()}</class>\n"
            f' <widget class="QMainWindow" name="{name}"/>\n</ui>\n'
        )


class _Base(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = ptk.TempArtifacts("uitk_test_editor_handler", policy="scoped")
        self.dir = self.tmp.dir_path()
        _write_ui(os.path.join(self.dir, "alpha.ui"), "alpha")
        self.sb = Switchboard(ui_source=self.dir, log_level="WARNING")
        self.handler = self.sb.handlers.editor

    def tearDown(self):
        for name in self.sb.editors.names():
            editor = self.sb.editors.peek(name)
            if editor is not None:
                editor.hide()
                editor.deleteLater()
        self.sb.deleteLater()
        QtWidgets.QApplication.processEvents()
        self.tmp.cleanup()
        super().tearDown()


class EditorRows(_Base):
    def test_every_bundled_editor_is_a_row(self):
        self.assertIsInstance(self.handler, EditorHandler)
        rows = [e for e in self.sb.iter_handler_entries() if e.kind == "editor"]
        self.assertEqual(sorted(e.name for e in rows), sorted(self.sb.editors.names()))
        for entry in rows:
            self.assertIs(entry.handler, self.handler)
            self.assertFalse(entry.editable_tags)

    def test_the_ui_browser_lists_itself(self):
        browser = self.sb.editors.get("browser")
        self.assertIn("browser", browser._model._names)
        self.assertIn("alpha", browser._model._names)

    def test_a_registered_ui_keeps_a_name_an_editor_also_has(self):
        """A host UI named like a bundled editor (``presets.ui``) keeps its row;
        the editor's row steps aside, and the others stay.

        Regression: the editor rows were listed unconditionally, and the
        browser keeps ONE row per name -- the last, which is the editor's (its
        handler registers after the UI handler) -- so the host's own
        ``presets`` UI vanished from the launcher.
        """
        path = os.path.join(self.dir, "presets.ui")
        _write_ui(path, "presets")
        self.sb.register(ui_location=path)
        rows = [e for e in self.sb.iter_handler_entries() if e.name == "presets"]
        self.assertEqual([e.kind for e in rows], ["ui_file"])
        editor_rows = {
            e.name for e in self.sb.iter_handler_entries() if e.kind == "editor"
        }
        self.assertEqual(editor_rows, set(self.sb.editors.names()) - {"presets"})

    def test_a_switchboard_can_opt_out(self):
        sb = Switchboard(ui_source=self.dir, handlers={"editor": None})
        try:
            self.assertIsNone(getattr(sb.handlers, "editor", None))
            kinds = {e.kind for e in sb.iter_handler_entries()}
            self.assertEqual(kinds, {"ui_file"})
        finally:
            sb.deleteLater()


class EditorLifecycle(_Base):
    def test_launch_close_and_visibility(self):
        self.assertFalse(self.handler.is_visible("style"))
        editor = self.handler.launch("style")
        self.assertIs(editor, self.sb.editors.peek("style"))
        self.assertTrue(self.handler.is_visible("style"))
        self.handler.close("style")
        self.assertFalse(self.handler.is_visible("style"))

    def test_row_refreshes_when_an_editor_hides_by_any_path(self):
        """Wired at build, so a window opened outside the handler (a slot's
        ``sb.editors.show``) still refreshes its row."""
        editor = self.sb.editors.show("style")
        seen = []
        self.sb.on_handler_entry_changed.connect(
            lambda handler, name: seen.append((handler, name))
        )
        editor.hide()
        QtWidgets.QApplication.processEvents()
        self.assertIn(("editor", "style"), seen)

    def test_a_hide_is_relayed_after_it_returns_never_inside_it(self):
        """Qt sends a window its Hide from inside ``~QWidget`` too. Relayed
        synchronously, the browser's own model then emitted ``dataChanged``
        into its own view mid-destruction: a standalone launch died with an
        access violation at exit in about one run in eight. The relay waits
        for the next event-loop turn, and still arrives when the window is
        deleted right after hiding."""
        import shiboken6

        editor = self.sb.editors.show("style")
        QtWidgets.QApplication.processEvents()
        seen = []
        self.sb.on_handler_entry_changed.connect(
            lambda handler, name: seen.append((handler, name))
        )
        editor.hide()
        self.assertEqual(seen, [], "the Hide was relayed inside hide() itself")
        QtWidgets.QApplication.processEvents()
        self.assertIn(("editor", "style"), seen)

        seen.clear()
        editor.show()
        QtWidgets.QApplication.processEvents()
        seen.clear()
        shiboken6.delete(editor)  # ~QWidget sends the Hide
        self.assertEqual(seen, [], "the destructor's Hide was relayed synchronously")
        QtWidgets.QApplication.processEvents()
        self.assertIn(("editor", "style"), seen)

    def test_focus_and_close_never_build_an_editor(self):
        self.handler.focus("presets")
        self.handler.close("presets")
        self.assertIsNone(self.sb.editors.peek("presets"))
        self.assertFalse(self.handler.is_visible("presets"))


class EditorLaunchCode(_Base):
    def test_the_browsers_snippet_carries_the_registry(self):
        code = self.handler.launch_code("browser")
        compile(code, "<launch_code>", "exec")
        self.assertIn("sb.register(", code)
        ui_dir = os.path.abspath(self.dir)
        if os.sep == "\\":
            ui_dir = ui_dir.replace("\\", "/")
        self.assertIn(f"ui_location={ui_dir!r},", code)
        self.assertIn("handler.sb.editors.show('browser')", code)

    def test_an_editor_with_its_own_store_needs_no_sources(self):
        code = self.handler.launch_code("style")
        self.assertNotIn(".register(", code)
        self.assertIn("handler.sb.editors.show('style')", code)

    def test_unknown_editor_has_no_code(self):
        self.assertIsNone(self.handler.launch_code("nope"))

    def test_fresh_interpreter_opens_the_browser_over_the_registry(self):
        """The shelf-button case: a new session gets a browser that lists the
        same UIs -- and itself."""
        from conftest import run_launch_snippet

        probe = (
            "[ns['handler'].sb.editors.peek('browser').isVisible(), "
            "sorted(ns['handler'].sb.editors.peek('browser')._model._names), "
            "len(exec_calls)]"
        )
        visible, names, loops = run_launch_snippet(
            self.handler.launch_code("browser"), probe
        )
        self.assertTrue(visible)
        self.assertIn("alpha", names)
        self.assertIn("browser", names)
        self.assertEqual(loops, 1)


if __name__ == "__main__":
    unittest.main()
