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
        self.assertTrue(_has_button(w.standardButtons(), QtWidgets.QMessageBox.SaveAll))

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

    def test_a_name_qt_has_no_button_for_becomes_a_labelled_button(self):
        """A confirmation asking for ("Fix", "Cancel") used to render a
        Cancel-only box -- the unknown name was dropped (live-caught in the
        tentacle scene panel), later with a console warning. Any other name
        is now a button wearing that label, beside the standard ones, so a
        prompt can say what each answer DOES ("Override All").
        Changed: 2026-10-04
        """
        w = self._make()
        w.setStandardButtons("Override All", "Override", "Cancel")
        self.assertTrue(_has_button(w.standardButtons(), QtWidgets.QMessageBox.Cancel))
        labels = [b.text().replace("&", "") for b in w.buttons()]
        self.assertIn("Override All", labels)
        self.assertIn("Override", labels)
        # Re-setting replaces them rather than piling up a second pair.
        w.setStandardButtons("Fix", "Cancel")
        labels = sorted(b.text().replace("&", "") for b in w.buttons())
        self.assertEqual(labels, ["Cancel", "Fix"])

    def test_a_labelled_button_answers_with_its_label(self):
        """``exec_`` answers with the clicked button's name: Qt's own name for
        a standard button, the label for any other. Driven by a click queued
        into the modal loop, so the test never blocks on it."""
        w = self._make()
        w.setStandardButtons("Override All", "Override", "Cancel")
        target = next(b for b in w.buttons() if b.text() == "Override")
        QtCore.QTimer.singleShot(0, target.click)
        self.assertEqual(w.exec_(), "Override")
        cancel = w.button(QtWidgets.QMessageBox.Cancel)
        QtCore.QTimer.singleShot(0, cancel.click)
        self.assertEqual(w.exec_(), "Cancel")

    def test_the_default_button_is_chosen_by_name(self):
        """Enter answers the default -- for a prompt that can override a
        safety check that must be the safe answer, not whichever button Qt
        found first."""
        w = self._make()
        w.setStandardButtons("Override All", "Override", "Cancel")
        w.set_default_button("Cancel")
        self.assertIs(w.defaultButton(), w.button(QtWidgets.QMessageBox.Cancel))
        w.set_default_button("Override")
        self.assertEqual(w.defaultButton().text(), "Override")
        with self.assertRaises(ValueError):
            w.set_default_button("Nope")

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
        expected = QtCore.QPoint(rect.left() + offset_x, rect.top() + offset_y)
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


class TestMessageBoxLinks(QtBaseTestCase):
    """An address in a dialog is a link its label opens -- where to install a
    missing tool, above all, which was text to copy by hand."""

    def test_an_address_in_the_text_opens_in_the_browser(self):
        url = "https://example.test/install"
        box = self.track_widget(MessageBox(theme=None))
        box.setText(f"Install it from {url}.")
        label = box.findChild(QtWidgets.QLabel, "qt_msgbox_label")
        self.assertIn(f'<a href="{url}">{url}</a>.', label.text())
        self.assertTrue(label.openExternalLinks())
        self.assertTrue(label.textInteractionFlags() & QtCore.Qt.LinksAccessibleByMouse)


class TestMessageBoxAutoTimeout(QtBaseTestCase):
    """``timeout="auto"`` keeps a toast up long enough to read its text, and
    never longer than a few seconds -- the full text is in the log anyway."""

    def _make(self, **kwargs):
        return self.track_widget(MessageBox(theme=None, **kwargs))

    def test_longer_text_stays_up_longer(self):
        short = MessageBox.reading_time("Done.")
        longer = MessageBox.reading_time("Exported 12 objects to the scene folder.")
        self.assertLess(short, longer)

    def test_reading_time_is_clamped_to_a_few_seconds(self):
        low, high = MessageBox.AUTO_TIMEOUT_RANGE
        self.assertLessEqual(high, 5.0, "a toast must leave within a few seconds")
        self.assertEqual(MessageBox.reading_time(""), low)
        self.assertEqual(MessageBox.reading_time("word " * 500), high)

    def test_reading_time_counts_the_visible_text_not_the_markup(self):
        self.assertEqual(
            MessageBox.reading_time("<font color='red'><b>Done.</b></font>"),
            MessageBox.reading_time("Done."),
        )

    def test_auto_starts_the_timer_for_the_reading_time(self):
        box = self._make(timeout="auto")
        box.setText("Exported 12 objects to the scene folder.")
        box.show()
        self.assertTrue(box.menu_timer.isActive())
        expected = MessageBox.reading_time(box.text())
        self.assertEqual(box.menu_timer.interval(), round(expected * 1000))

    def test_new_text_on_a_showing_toast_is_timed_afresh(self):
        """``sb.message_box`` reuses one passive box; ``show()`` on a visible
        widget sends no showEvent, so a second message inherited what was left
        of the first one's time."""
        box = self._make(timeout="auto")
        box.setText("Done.")
        box.show()
        box.setText("A much longer message that needs more time to read. " * 2)
        self.assertEqual(
            box.menu_timer.interval(),
            round(MessageBox.reading_time(box.text()) * 1000),
        )

    def test_new_text_on_a_showing_toast_is_placed_afresh(self):
        """The same missing showEvent skipped ``move_``: a longer second
        message grew rightward from where the first was centred."""
        box = self._make(timeout="auto")
        box.setText("Done.")
        box.show()
        box.setText("A much longer message that needs more time to read. " * 2)
        with patch.object(box, "move") as mock_move:
            box.move_(box.location)
        self.assertEqual(box.pos(), mock_move.call_args[0][0])

    def test_a_box_with_buttons_never_closes_itself(self):
        """Buttons that are ALL labelled are no standard button, and the
        auto-close took that for a toast: ``sb.message_box`` times every box
        ``"auto"``, so the WebXR panel's ("Open Page", "Not Now") offer closed
        itself after a few seconds and answered None.
        Fixed: 2026-10-04
        """
        box = self._make(timeout="auto")
        box.setStandardButtons("Open Page", "Not Now")
        box.setText("Open the preview page?")
        box.show()
        self.assertFalse(box.menu_timer.isActive(), "a prompt waits for its answer")
        box.autoClose()  # what the timer would call
        self.assertTrue(box.isVisible())

    def test_a_toast_still_closes_itself(self):
        box = self._make(timeout="auto")
        box.setText("Done.")
        box.show()
        self.assertTrue(box.menu_timer.isActive())
        box.autoClose()
        self.assertFalse(box.isVisible())

    def test_zero_timeout_never_auto_closes(self):
        """0 meant "no timeout" to ``__init__`` but was assigned verbatim by
        ``sb.message_box``, so the timer started at 0 ms and closed the box
        on the next event-loop turn."""
        box = self._make()
        box.timeout = 0
        box.setText("Stays until dismissed.")
        box.show()
        self.assertIsNone(box.timeout)
        self.assertFalse(box.menu_timer.isActive())

    def test_an_unknown_timeout_word_is_rejected(self):
        box = self._make()
        with self.assertRaises(ValueError):
            box.timeout = "soon"


if __name__ == "__main__":
    unittest.main(verbosity=2)
