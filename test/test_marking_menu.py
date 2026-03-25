# !/usr/bin/python
# coding=utf-8
"""Tests for MarkingMenu show/hide behaviour when standalone windows are opened."""
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from qtpy import QtWidgets, QtCore

from conftest import QtBaseTestCase


class MarkingMenuStub(QtWidgets.QStackedWidget):
    """Minimal stub that replicates the MarkingMenu methods under test.

    We re-implement just enough of:
      _show_window, _transition_to_state, _build_lookup_key,
      _on_activation_press, _on_activation_release, hide

    to verify the guards added for the standalone-window reshow bug.
    """

    key_show_release = QtCore.Signal()

    def __init__(self, parent=None, bindings=None):
        super().__init__(parent)
        self._activation_key_held = False
        self._activation_key_str = "Key_F12"
        self._standalone_suppress = False
        self._bindings = bindings or {"Key_F12": "startmenu"}
        self._chord_buttons_at_press = 0
        self._cancel_chord_timer_called = False
        self._hidden = False  # Track explicit hide() calls

    # ------------------------------------------------------------------
    # Real methods (copied from _marking_menu.py with minimal stubs)
    # ------------------------------------------------------------------

    def _build_lookup_key(self, buttons=None, modifiers=None, key=None):
        parts = []
        if self._activation_key_held and self._activation_key_str:
            parts.append(self._activation_key_str)
        if buttons:
            buttons_int = int(buttons)
            if buttons_int & int(QtCore.Qt.LeftButton):
                parts.append("LeftButton")
        return "|".join(sorted(parts)) if parts else ""

    def _transition_to_state(self, buttons, modifiers=None):
        if self.isHidden():
            return
        lookup = self._build_lookup_key(buttons=buttons, modifiers=modifiers)
        next_ui = self._bindings.get(lookup)
        if next_ui:
            self._show_marking_menu(next_ui)

    def _show_marking_menu(self, widget_or_name, **kwargs):
        """Record that the marking menu was reshown."""
        if self.isHidden():
            self.show()
        self._last_shown_ui = widget_or_name

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

    def _cancel_chord_timer(self):
        self._cancel_chord_timer_called = True


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
        """_show_window must clear _activation_key_held so _build_lookup_key
        won't include Key_F12 in subsequent lookups."""
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

    # ----- _transition_to_state guards -----

    def test_transition_blocked_when_hidden(self):
        """_transition_to_state must be a no-op when the MarkingMenu is hidden.

        Bug: releasing all mouse buttons while F12 is held after _show_window
        built lookup 'Key_F12' -> 'startmenu' and reshowed the overlay.
        """
        self.mm._activation_key_held = True
        self.mm.show()
        self.mm._show_window(QtWidgets.QWidget())
        # Now hidden, activation_key_held is False. Simulate fallthrough:
        self.mm._activation_key_held = True  # hypothetical stale state
        self.mm._transition_to_state(QtCore.Qt.NoButton)
        # Should NOT have called _show_marking_menu
        self.assertTrue(self.mm.isHidden())

    def test_transition_still_works_when_visible(self):
        """Normal transition (menu visible) should proceed."""
        self.mm._activation_key_held = True
        self.mm.show()
        self.mm._last_shown_ui = None
        self.mm._transition_to_state(QtCore.Qt.NoButton)
        self.assertEqual(self.mm._last_shown_ui, "startmenu")

    # ----- _on_activation_press / _on_activation_release guards -----

    def test_activation_press_suppressed_after_standalone_window(self):
        """If a standalone window was opened during this key-hold cycle,
        a spurious re-press must NOT reactivate the marking menu.

        Bug: focus changes in Maya could cause a spurious KeyRelease then
        KeyPress, firing _on_activation_press a second time.
        """
        self.mm._activation_key_held = True
        self.mm.show()
        self.mm._show_window(QtWidgets.QWidget())
        self.assertTrue(self.mm._standalone_suppress)
        # Simulate spurious re-press
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

        # Genuine release
        self.mm._on_activation_release()
        self.assertFalse(self.mm._standalone_suppress)

        # Genuine re-press
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

        # After standalone window open
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
