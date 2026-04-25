# !/usr/bin/python
# coding=utf-8
"""Tests for MarkingMenu show/hide behaviour when standalone windows are opened."""
import unittest
from qtpy import QtWidgets, QtCore

from conftest import QtBaseTestCase
from uitk.widgets.marking_menu._resolver import resolve_target_menu


class MarkingMenuStub(QtWidgets.QStackedWidget):
    """Minimal stub that replicates the MarkingMenu methods under test.

    Re-implements just enough of ``_show_window``, ``_sync_menu_to_state``,
    ``_on_activation_press``, ``_on_activation_release`` and ``hide`` to
    verify the standalone-window reshow guards without booting Switchboard.
    """

    key_show_release = QtCore.Signal()

    def __init__(self, parent=None, bindings=None):
        super().__init__(parent)
        self._activation_key_held = False
        self._activation_key_str = "Key_F12"
        self._standalone_suppress = False
        self._bindings = bindings or {"Key_F12": "startmenu"}
        self._suppress_default_on_reentry = False
        self._non_default_shown = False
        self._current_widget = None
        self._last_shown_ui = None

    def _sync_menu_to_state(self, *, buttons=0, modifiers=0, extra_key=None):
        if self.isHidden():
            return
        target = resolve_target_menu(
            activation_held=self._activation_key_held,
            activation_key_str=self._activation_key_str,
            buttons=int(buttons) if buttons else 0,
            modifiers=int(modifiers) if modifiers else 0,
            bindings=self._bindings,
            extra_key=extra_key,
        )
        if target:
            self._last_shown_ui = target

    def _show_window(self, widget, pos=None, force=False, **kwargs):
        if widget.parent() is self:
            widget.setParent(self.parent(), QtCore.Qt.Window)
        self._activation_key_held = False
        self._standalone_suppress = True
        self.hide()
        return widget

    def _on_activation_press(self):
        if self._standalone_suppress:
            return
        self._activation_key_held = True

    def _on_activation_release(self):
        self._activation_key_held = False
        self._standalone_suppress = False
        self.key_show_release.emit()
        self.hide()


class TestStandaloneWindowSuppression(QtBaseTestCase):
    """Verify the marking menu doesn't reshow after opening a standalone window."""

    def setUp(self):
        super().setUp()
        self.parent = QtWidgets.QWidget()
        self.track_widget(self.parent)
        self.mm = MarkingMenuStub(self.parent, bindings={"Key_F12": "startmenu"})
        self.track_widget(self.mm)

    # ----- _show_window guards -----

    def test_show_window_clears_activation_key_held(self):
        """_show_window must clear _activation_key_held so subsequent state
        syncs won't resolve any activation-keyed binding."""
        self.mm._activation_key_held = True
        child = QtWidgets.QWidget()
        self.track_widget(child)
        self.mm._show_window(child)
        self.assertFalse(self.mm._activation_key_held)

    def test_show_window_sets_standalone_suppress(self):
        """_show_window must set the suppression flag."""
        child = QtWidgets.QWidget()
        self.track_widget(child)
        self.mm._show_window(child)
        self.assertTrue(self.mm._standalone_suppress)

    def test_show_window_hides_marking_menu(self):
        """_show_window must hide the MarkingMenu."""
        self.mm.show()
        child = QtWidgets.QWidget()
        self.track_widget(child)
        self.mm._show_window(child)
        self.assertTrue(self.mm.isHidden())

    def test_show_window_reparents_child_widgets(self):
        """If the standalone window is a child of the MarkingMenu, it must be
        reparented before hiding so it isn't hidden alongside the overlay."""
        child = QtWidgets.QWidget(self.mm)
        self.track_widget(child)
        self.assertIs(child.parent(), self.mm)
        self.mm._show_window(child)
        self.assertIsNot(child.parent(), self.mm)

    def test_show_window_does_not_auto_pin(self):
        """Standalone windows must NOT be auto-pinned on open.

        Windows should hide when the activation key is released (unless
        the user has explicitly pinned or minimized them).
        Updated: 2025-07-17
        """
        child = QtWidgets.QMainWindow()
        child._pinned = False
        child.set_pinned = lambda v: setattr(child, "_pinned", v)
        self.track_widget(child)
        self.mm._show_window(child)
        self.assertFalse(child._pinned)

    # ----- _sync_menu_to_state guards -----

    def test_sync_menu_to_state_blocked_when_hidden(self):
        """_sync_menu_to_state must be a no-op when the MarkingMenu is hidden.

        Bug: releasing all mouse buttons while F12 is held after _show_window
        reshowed the overlay via a stale state lookup.
        """
        self.mm._activation_key_held = True
        self.mm.show()
        self.mm._show_window(QtWidgets.QWidget())
        # Now hidden, activation_key_held is False. Simulate a stale fallthrough:
        self.mm._activation_key_held = True
        self.mm._last_shown_ui = None
        self.mm._sync_menu_to_state(buttons=0, modifiers=0)
        self.assertIsNone(self.mm._last_shown_ui)
        self.assertTrue(self.mm.isHidden())

    def test_sync_menu_to_state_still_works_when_visible(self):
        """Normal sync (menu visible) should resolve and record the target."""
        self.mm._activation_key_held = True
        self.mm.show()
        self.mm._last_shown_ui = None
        self.mm._sync_menu_to_state(buttons=0, modifiers=0)
        self.assertEqual(self.mm._last_shown_ui, "startmenu")

    # ----- _on_activation_press / _on_activation_release guards -----

    def test_activation_press_suppressed_after_standalone_window(self):
        """If a standalone window was opened during this key-hold cycle,
        a spurious re-press must NOT reactivate the marking menu."""
        self.mm._activation_key_held = True
        self.mm.show()
        self.mm._show_window(QtWidgets.QWidget())
        self.assertTrue(self.mm._standalone_suppress)
        self.mm._on_activation_press()
        self.assertFalse(self.mm._activation_key_held)

    def test_suppression_cleared_on_real_release(self):
        """After the user actually releases the key, the suppression flag
        must clear so the next key press works normally."""
        self.mm._standalone_suppress = True
        self.mm._on_activation_release()
        self.assertFalse(self.mm._standalone_suppress)

    def test_full_cycle_reshow_after_release_and_repress(self):
        """After a standalone window is opened, releasing and re-pressing the
        key should show the marking menu normally."""
        self.mm._activation_key_held = True
        self.mm.show()
        self.mm._show_window(QtWidgets.QWidget())

        self.mm._on_activation_release()
        self.assertFalse(self.mm._standalone_suppress)

        self.mm._on_activation_press()
        self.assertTrue(self.mm._activation_key_held)

    def test_key_show_release_always_emitted(self):
        """key_show_release is always emitted on activation release, even
        after a standalone window open. This allows request_hide to close
        unpinned standalone windows when the key is released.
        Updated: 2025-07-17
        """
        received = []
        self.mm.key_show_release.connect(lambda: received.append(True))

        self.mm._standalone_suppress = True
        self.mm._on_activation_release()
        self.assertEqual(received, [True], "key_show_release should always fire")

    def test_key_show_release_emitted_on_normal_release(self):
        """key_show_release must still fire on a normal (non-standalone)
        activation release."""
        received = []
        self.mm.key_show_release.connect(lambda: received.append(True))

        self.mm._standalone_suppress = False
        self.mm._on_activation_release()
        self.assertEqual(received, [True])


if __name__ == "__main__":
    unittest.main()
