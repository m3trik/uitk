# !/usr/bin/python
# coding=utf-8
"""Tests for ``SwitchboardEditorsMixin`` — the ``sb.editors`` registry.

Covers:
- Editor name registry (``style``, ``shortcut``, ``browser``)
- Lazy instantiation + caching
- Auto-recovery when the underlying Qt object is destroyed
- ``show()`` shows + raises the cached editor
- Property accessors (``sb.editors.style`` etc.)
- Unknown editor names raise ``KeyError``
- Parent resolution: handlers.marking_menu first, then sb.parent()
"""

import os
import tempfile
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets
from uitk.switchboard import Switchboard
from uitk.switchboard.editors import _EditorRegistry


def _write_ui(path, name):
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>{name.capitalize()}</class>
 <widget class="QMainWindow" name="{name}"/>
</ui>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class _Base(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        _write_ui(os.path.join(self.tmp.name, "alpha.ui"), "alpha")
        self.sb = Switchboard(ui_source=self.tmp.name, log_level="WARNING")

    def tearDown(self):
        # Clean up any cached editors before tearing down the switchboard
        if hasattr(self.sb, "_editors_registry"):
            for inst in self.sb._editors_registry._cache.values():
                try:
                    inst.deleteLater()
                except RuntimeError:
                    pass
        self.tmp.cleanup()
        super().tearDown()


class EditorsProperty(_Base):
    def test_editors_property_lazy_and_cached(self):
        # First access creates the registry; second returns the same one.
        self.assertFalse(hasattr(self.sb, "_editors_registry"))
        registry_a = self.sb.editors
        self.assertIs(registry_a, self.sb.editors)
        self.assertIsInstance(registry_a, _EditorRegistry)

    def test_known_editor_names(self):
        names = set(self.sb.editors.names())
        self.assertEqual(names, {"style", "shortcut", "global_shortcuts", "browser"})


class EditorsGet(_Base):
    def test_get_browser_returns_switchboard_browser(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowser

        editor = self.sb.editors.get("browser")
        self.assertIsInstance(editor, SwitchboardBrowser)
        # The browser was given our switchboard, not a fresh one
        self.assertIs(editor.sb, self.sb)

    def test_get_shortcut_passes_switchboard(self):
        from uitk.widgets.editors.shortcut_editor.registry_editor import ShortcutEditor

        editor = self.sb.editors.get("shortcut")
        self.assertIsInstance(editor, ShortcutEditor)
        self.assertIsNone(editor._focus)  # full editor, not focused

    def test_get_global_shortcuts_is_focused_commands_editor(self):
        # Same ShortcutEditor class, built with the focused-commands flag and
        # cached separately from the full "shortcut" editor.
        from uitk.widgets.editors.shortcut_editor.registry_editor import ShortcutEditor

        editor = self.sb.editors.get("global_shortcuts")
        self.assertIsInstance(editor, ShortcutEditor)
        self.assertEqual(editor._focus, "commands")
        self.assertIsNot(editor, self.sb.editors.get("shortcut"))

    def test_global_shortcuts_combo_stripped_to_commands(self):
        # Focused mode strips the UI combo to the single locked ⌘ Commands entry
        # (no other UIs, no show-all toggle overlay to orphan) rather than hiding
        # the combo.
        editor = self.sb.editors.get("global_shortcuts")
        editor.refresh_ui_list()
        self.assertEqual(editor.cmb_ui.count(), 1)
        self.assertEqual(editor.cmb_ui.itemText(0), editor._COMMANDS_LABEL)

    def test_global_shortcuts_hides_scope_description_ui_columns(self):
        # The focused launcher drops Scope, Description, and UI — leaving just
        # Action + Shortcut (+ Reset). refresh_ui_list runs the Commands populate,
        # which must NOT re-reveal the UI column in focused mode.
        editor = self.sb.editors.get("global_shortcuts")
        editor.refresh_ui_list()
        for col in (editor.COL_SCOPE, editor.COL_DESCRIPTION, editor.COL_UI):
            self.assertTrue(editor.table.isColumnHidden(col), col)
        for col in (editor.COL_ACTION, editor.COL_SHORTCUT):
            self.assertFalse(editor.table.isColumnHidden(col), col)

    def test_get_style_no_switchboard_arg(self):
        # StyleEditor's constructor doesn't accept a switchboard, so the
        # registry must call it without one.
        from uitk.widgets.editors.style_editor import StyleEditor

        editor = self.sb.editors.get("style")
        self.assertIsInstance(editor, StyleEditor)

    def test_get_caches_instance(self):
        # Subsequent calls return the same object (no re-instantiation)
        a = self.sb.editors.get("browser")
        b = self.sb.editors.get("browser")
        self.assertIs(a, b)

    def test_get_unknown_raises(self):
        with self.assertRaises(KeyError) as ctx:
            self.sb.editors.get("nonexistent")
        # The error message should list available editor names so the
        # caller can self-correct.
        msg = str(ctx.exception)
        self.assertIn("style", msg)
        self.assertIn("shortcut", msg)
        self.assertIn("browser", msg)


class EditorsAutoRecovery(_Base):
    def test_rebuilds_after_qt_object_destroyed(self):
        # Get a browser, force-delete its underlying Qt object, get again
        first = self.sb.editors.get("browser")
        first.deleteLater()
        # Process events so deletion completes
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.processEvents()
        # Probe — accessing should now build a fresh instance, not raise
        second = self.sb.editors.get("browser")
        self.assertIsNotNone(second)
        # And the fresh instance must be alive
        self.assertEqual(second.objectName(), second.objectName())

    def test_is_alive_handles_attribute_error(self):
        # Some shiboken builds raise AttributeError instead of RuntimeError
        # for partially-disposed wrappers — the shared liveness probe (used by
        # the editor cache) must treat that as "dead" rather than propagate.
        class _BadlyDisposed:
            def objectName(self):
                raise AttributeError("simulated wrapper disposal")

        self.assertFalse(self.sb._widget_is_alive(_BadlyDisposed()))


class EditorsShortcuts(_Base):
    def test_property_style(self):
        from uitk.widgets.editors.style_editor import StyleEditor

        self.assertIsInstance(self.sb.editors.style, StyleEditor)

    def test_property_shortcut(self):
        from uitk.widgets.editors.shortcut_editor.registry_editor import ShortcutEditor

        self.assertIsInstance(self.sb.editors.shortcut, ShortcutEditor)

    def test_property_browser(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowser

        self.assertIsInstance(self.sb.editors.browser, SwitchboardBrowser)


class EditorsShow(_Base):
    def test_show_returns_visible_editor(self):
        editor = self.sb.editors.show("browser")
        self.assertTrue(editor.isVisible())
        editor.hide()

    def test_show_caches_same_instance(self):
        a = self.sb.editors.show("browser")
        a.hide()
        b = self.sb.editors.show("browser")
        self.assertIs(a, b)
        b.hide()


class UiHandlerEditorsDelegate(_Base):
    """Verify the ``UiHandler.editors`` delegate.

    Lets shelf scripts launch a bundled editor in one line — equivalent
    to ``handler.sb.editors`` but reads more naturally and avoids the
    caller having to know about ``.sb``.
    """

    def test_editors_delegates_to_switchboard(self):
        from unittest import mock
        from uitk.handlers.ui_handler import UiHandler

        handler = UiHandler(switchboard=self.sb)
        # Patch the property to a sentinel so we verify the delegate
        # threads through *this* sb's editors property, independent of
        # any caching state lingering from other tests.
        sentinel = object()
        with mock.patch.object(
            type(self.sb),
            "editors",
            new_callable=mock.PropertyMock,
            return_value=sentinel,
        ):
            self.assertIs(handler.editors, sentinel)

    def test_editors_show_via_handler(self):
        from uitk.handlers.ui_handler import UiHandler

        handler = UiHandler(switchboard=self.sb)
        editor = handler.editors.show("browser")
        try:
            self.assertTrue(editor.isVisible())
        finally:
            editor.hide()


class PopupContextRecovery(_Base):
    """Verify the popup-context recovery behind every uitk window's ``present``.

    The bug guarded against: ``QMenu`` action slots fire while the menu
    is still the active popup. After the slot returns, the menu's own
    ``hideEvent`` runs and explicitly raises whatever window was active
    before the menu opened — which buries our just-shown editor. So
    ``WindowPanel.present`` checks :meth:`WindowPanel.is_in_popup_context`
    and schedules a deferred re-raise on the next event-loop tick; the
    registry's ``show`` delegates to it, as do the editor's non-Switchboard
    owners (``ShortcutManager``, the DCC macro managers), which each used to
    hand-roll a show+raise without this recovery.
    """

    def _panel(self):
        from uitk.widgets.windowPanel import WindowPanel

        panel = WindowPanel()
        self.addCleanup(panel.deleteLater)
        return panel

    def test_no_popup_context_when_no_active_popup(self):
        self.assertFalse(self._panel().is_in_popup_context())

    def test_popup_context_true_when_other_popup_active(self):
        from unittest.mock import patch

        panel = self._panel()
        sentinel = QtWidgets.QWidget()
        self.addCleanup(sentinel.deleteLater)
        with patch(
            "qtpy.QtWidgets.QApplication.activePopupWidget", return_value=sentinel
        ):
            self.assertTrue(panel.is_in_popup_context())

    def test_popup_context_false_when_the_window_is_the_popup(self):
        # If the window itself is the active popup (e.g. a modal it spawned),
        # we don't want to defer a self-raise — there's nothing to lose focus to.
        from unittest.mock import patch

        panel = self._panel()
        with patch("qtpy.QtWidgets.QApplication.activePopupWidget", return_value=panel):
            self.assertFalse(panel.is_in_popup_context())

    def _present(self, panel, popup=None):
        """``panel.present()`` with every deferred callback run inline, returning
        the raise/activate call log.

        Asserting on the *effect* rather than on how many callbacks got
        scheduled: ``show()`` itself schedules incidental ``singleShot`` work
        (``_fit_to_content``), so a count is noise — the question is whether the
        window gets raised a second time after the menu closes.
        """
        from unittest.mock import patch
        from qtpy import QtCore

        calls = []
        panel.raise_ = lambda: calls.append("raise")
        panel.activateWindow = lambda: calls.append("activate")
        popup_patch = patch(
            "qtpy.QtWidgets.QApplication.activePopupWidget", return_value=popup
        )
        with (
            popup_patch,
            patch.object(
                QtCore.QTimer, "singleShot", staticmethod(lambda _ms, cb: cb())
            ),
        ):
            self.assertIs(panel.present(), panel, "present returns the window")
        return calls

    def test_present_re_raises_after_the_popup_closes(self):
        """The synchronous raise happens first (callers/tests see it visible
        immediately); the deferred one runs once the menu has closed."""
        panel = self._panel()
        sentinel = QtWidgets.QWidget()
        self.addCleanup(sentinel.deleteLater)
        calls = self._present(panel, popup=sentinel)
        self.assertTrue(panel.isVisible())
        self.assertEqual(calls, ["raise", "activate", "raise", "activate"])

    def test_present_raises_once_without_a_popup(self):
        panel = self._panel()
        self.assertEqual(self._present(panel), ["raise", "activate"])

    def test_present_can_show_without_raising(self):
        panel = self._panel()
        calls = []
        panel.raise_ = lambda: calls.append("raise")
        panel.present(raise_window=False)
        self.assertTrue(panel.isVisible())
        self.assertEqual(calls, [])

    def test_registry_show_delegates_to_present(self):
        """The registry must not re-derive the presentation — a second copy is
        how the other three owners drifted."""
        from unittest.mock import patch

        sb = self.sb
        editor = sb.editors.get("style")
        with patch.object(type(editor), "present", return_value=editor) as present:
            self.assertIs(sb.editors.show("style"), editor)
        present.assert_called_once_with(raise_window=True)


class ParentResolution(_Base):
    def test_falls_back_to_sb_parent_when_no_marking_menu(self):
        # Switchboard with no handlers.marking_menu should still build editors
        host = QtWidgets.QWidget()
        host.setObjectName("test_host")
        try:
            self.sb.setParent(host)
            # Must not raise
            editor = self.sb.editors.get("browser")
            self.assertIsNotNone(editor)
        finally:
            host.deleteLater()


if __name__ == "__main__":
    unittest.main()
