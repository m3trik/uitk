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
        """An unrecognized name contributes nothing (NoButton)."""
        w = self._make()
        w.setStandardButtons("NotARealButton")
        self.assertEqual(w.standardButtons(), QtWidgets.QMessageBox.NoButton)

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

if __name__ == "__main__":
    unittest.main(verbosity=2)
