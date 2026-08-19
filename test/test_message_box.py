# !/usr/bin/python
# coding=utf-8
"""Unit tests for the MessageBox widget.

Covers two regressions:

1. ``setStandardButtons`` used ``str.capitalize()`` to "normalize" the button
   name before the mapping lookup. ``capitalize()`` lowercases every character
   after the first, so multi-word Qt StandardButton names — "RestoreDefaults",
   "YesToAll", "SaveAll", "NoToAll" — became "Restoredefaults" / "Yestoall" /
   ... which are absent from ``buttonMapping`` and silently resolved to
   ``NoButton``. The lookup is now case-insensitive against the real names.

2. ``move_`` ignored a QPoint location (despite the class docstring promising
   QPoint support) and always positioned relative to ``screens()[0]`` (the
   primary monitor). It now honors a passed QPoint and otherwise anchors to the
   screen under the cursor.

Run standalone: python -m test.test_message_box
"""

import unittest
from unittest.mock import patch

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore

from uitk.widgets.messageBox import MessageBox


def _has_button(flags, button) -> bool:
    """True if *button* bit is set in the StandardButtons *flags* (binding-safe)."""
    return bool(int(flags) & int(button))


class TestMessageBoxStandardButtons(QtBaseTestCase):
    """setStandardButtons must resolve multi-word names, case-insensitively."""

    def _make(self):
        # theme=None skips StyleSheet registration — keeps the test light and
        # independent of the theme engine.
        return self.track_widget(MessageBox(theme=None))

    def test_multiword_restore_defaults_resolves(self):
        """'RestoreDefaults' must set the RestoreDefaults bit (was dropped)."""
        w = self._make()
        w.setStandardButtons("RestoreDefaults")
        self.assertTrue(
            _has_button(w.standardButtons(), QtWidgets.QMessageBox.RestoreDefaults)
        )

    def test_multiword_yes_to_all_resolves(self):
        """'YesToAll' must set the YesToAll bit (was dropped by capitalize())."""
        w = self._make()
        w.setStandardButtons("YesToAll")
        self.assertTrue(
            _has_button(w.standardButtons(), QtWidgets.QMessageBox.YesToAll)
        )

    def test_multiword_save_all_resolves(self):
        w = self._make()
        w.setStandardButtons("SaveAll")
        self.assertTrue(
            _has_button(w.standardButtons(), QtWidgets.QMessageBox.SaveAll)
        )

    def test_single_word_still_resolves(self):
        """A simple name like 'Ok' must still work."""
        w = self._make()
        w.setStandardButtons("Ok")
        self.assertTrue(_has_button(w.standardButtons(), QtWidgets.QMessageBox.Ok))

    def test_lowercase_input_resolves(self):
        """Lookup is case-insensitive: 'restoredefaults' resolves too."""
        w = self._make()
        w.setStandardButtons("restoredefaults")
        self.assertTrue(
            _has_button(w.standardButtons(), QtWidgets.QMessageBox.RestoreDefaults)
        )

    def test_multiple_multiword_buttons_combine(self):
        """Several names OR together into one StandardButtons flag."""
        w = self._make()
        w.setStandardButtons("YesToAll", "NoToAll")
        flags = w.standardButtons()
        self.assertTrue(_has_button(flags, QtWidgets.QMessageBox.YesToAll))
        self.assertTrue(_has_button(flags, QtWidgets.QMessageBox.NoToAll))

    def test_unknown_name_resolves_to_no_button(self):
        """An unrecognized name contributes nothing (NoButton) — but loudly.

        The drop used to be silent, which cosmetically broke callers: a
        confirmation asking for ("Fix", "Cancel") rendered a Cancel-only box
        with no affirmative action (live-caught in the tentacle scene panel).
        The console warning is the tell that turns that into a 5-second fix.
        """
        import contextlib
        import io

        w = self._make()
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            w.setStandardButtons("NotARealButton")
        self.assertEqual(w.standardButtons(), QtWidgets.QMessageBox.NoButton)
        self.assertIn("NotARealButton", captured.getvalue())
        self.assertIn("Valid:", captured.getvalue())

    def test_accepts_enum_value(self):
        """A real StandardButton enum still passes through."""
        w = self._make()
        w.setStandardButtons(QtWidgets.QMessageBox.Ok)
        self.assertTrue(_has_button(w.standardButtons(), QtWidgets.QMessageBox.Ok))


class TestMessageBoxMove(QtBaseTestCase):
    """move_ must honor a QPoint and use the relevant (not primary) screen."""

    def _make(self):
        return self.track_widget(MessageBox(theme=None))

    def test_move_honors_qpoint(self):
        """A QPoint location must be applied verbatim (was ignored)."""
        w = self._make()
        target = QtCore.QPoint(321, 654)
        with patch.object(w, "move") as mock_move:
            w.move_(target)
        mock_move.assert_called_once_with(target)

    def test_move_string_anchors_to_screen_geometry(self):
        """A string location positions relative to the resolved screen's
        geometry (offset by its left/top), not a bare width/2 origin."""
        w = self._make()
        # Resolve the same screen move_ does so the expected value matches.
        from qtpy import QtGui

        screen = (
            QtWidgets.QApplication.screenAt(QtGui.QCursor.pos())
            or QtWidgets.QApplication.primaryScreen()
        )
        rect = screen.geometry()
        offset_x = w.sizeHint().width() / 2
        offset_y = w.sizeHint().height() / 2
        expected = QtCore.QPoint(
            rect.left() + offset_x, rect.top() + offset_y
        )
        with patch.object(w, "move") as mock_move:
            w.move_("topLeft")
        mock_move.assert_called_once()
        got = mock_move.call_args[0][0]
        self.assertEqual(got, expected)

    def test_move_unrecognized_location_does_not_raise(self):
        """An unknown string falls through to the centered default."""
        w = self._make()
        with patch.object(w, "move") as mock_move:
            w.move_("nonsense")
        mock_move.assert_called_once()
        self.assertIsInstance(mock_move.call_args[0][0], QtCore.QPoint)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

class TestMessageBoxPromptFlags(QtBaseTestCase):
    """A buttoned, exec_()d box must be answerable.

    ``__init__`` applied one flag set to both of the widgets this class is:
    the passive toast (must never steal focus) and the interactive prompt
    (useless unless it can take focus). ``exec_()`` makes the box app-modal,
    so the toast flags produced a dialog that HALTED the host DCC while
    refusing every keypress meant to answer it -- and ``autoClose`` skips
    buttoned boxes, so nothing else dismissed it either.

    Asserted through ``as_prompt`` rather than ``exec_`` on purpose: exec_
    enters a modal event loop, and a test that spins one to read a window
    flag hangs the suite exactly the way the bug hangs Blender.
    """

    def test_toast_refuses_focus_by_default(self):
        """The passive path is unchanged -- a toast must not steal focus."""
        box = MessageBox()
        self.assertTrue(
            bool(box.windowFlags() & QtCore.Qt.WindowDoesNotAcceptFocus),
            "a passive toast must keep WindowDoesNotAcceptFocus",
        )
        self.assertEqual(box.windowModality(), QtCore.Qt.NonModal)

    def test_prompt_can_take_focus(self):
        """The regression: an answerable dialog cannot refuse the keyboard."""
        box = MessageBox()
        box.setStandardButtons("Yes", "No")
        box.as_prompt()
        self.assertFalse(
            bool(box.windowFlags() & QtCore.Qt.WindowDoesNotAcceptFocus),
            "an exec_()d prompt blocks the host, so refusing focus makes it "
            "unanswerable -- there is no other way to dismiss it",
        )

    def test_prompt_is_findable_over_the_host(self):
        """Qt.Tool need not appear in the task bar or above the host window."""
        box = MessageBox()
        box.as_prompt()
        # Qt.Tool is a COMPOSITE (Popup|Dialog), so `flags & Qt.Tool` is truthy
        # for any plain QDialog. The window TYPE is the only honest test.
        self.assertNotEqual(
            box.windowFlags() & QtCore.Qt.WindowType_Mask,
            QtCore.Qt.Tool,
            "a modal prompt must be findable -- a Tool window blocking the "
            "session that the user cannot locate is the same hang",
        )

    def test_prompt_modality_matches_what_exec_actually_does(self):
        """exec_() is app-modal; NonModal was a standing contradiction."""
        box = MessageBox()
        box.as_prompt()
        self.assertEqual(box.windowModality(), QtCore.Qt.ApplicationModal)

    def test_prompt_keeps_the_styled_look(self):
        """The fix is scoped to answerability, not appearance.

        Frameless + always-on-top are the styling and neither blocks an
        answer, so they stay -- pinned so a later "make it a real dialog"
        sweep is a deliberate choice rather than a silent restyle.
        """
        box = MessageBox()
        box.as_prompt()
        flags = box.windowFlags()
        self.assertTrue(bool(flags & QtCore.Qt.FramelessWindowHint))
        self.assertTrue(bool(flags & QtCore.Qt.WindowStaysOnTopHint))

    def test_as_prompt_is_idempotent(self):
        """exec_() calls it every time; a re-shown box must not drift."""
        box = MessageBox()
        first = box.as_prompt().windowFlags()
        self.assertEqual(box.as_prompt().windowFlags(), first)

    def test_parented_prompt_is_a_top_level_dialog_not_a_child_widget(self):
        """A hints-only flag set silently demotes a PARENTED box to Qt.Widget.

        Qt derives the window type from the flags; with no type bit and a
        parent it resolves to Qt.Widget, i.e. an embedded child rather than a
        window -- which would be worse than the bug being fixed, since the
        production path (``sb.message_box`` -> ``MessageBox(self.parent())``)
        ALWAYS passes a parent. Asserted parented on purpose: unparented, the
        same flags resolve to Qt.Window and the defect is invisible.
        """
        host = QtWidgets.QWidget()
        box = MessageBox(host)
        box.as_prompt()
        self.assertEqual(
            box.windowFlags() & QtCore.Qt.WindowType_Mask,
            QtCore.Qt.Dialog,
            "a parented prompt must stay a top-level Dialog",
        )
        self.assertTrue(box.isWindow(), "the prompt must be a window")

if __name__ == "__main__":
    unittest.main(verbosity=2)
