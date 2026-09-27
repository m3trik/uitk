# !/usr/bin/python
# coding=utf-8
"""Unit tests for WindowAutoHide (hide a window once the cursor has left it).

The cursor is injected, so every case runs offscreen: a window the cursor never
entered stays up, one it entered and left hides (flagged ``_auto_hiding`` while
it does), a pinned one never hides, and each show re-arms the poll.

Run standalone: python -m test.test_window_auto_hide
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets

from uitk import WindowAutoHide


class _Window(QtWidgets.QWidget):
    """Records the ``_auto_hiding`` flag each hide saw."""

    def __init__(self):
        super().__init__()
        self.hide_flags = []

    def hideEvent(self, event):
        self.hide_flags.append(getattr(self, "_auto_hiding", None))
        super().hideEvent(event)


class TestWindowAutoHide(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.win = self.track_widget(_Window())
        self.win.setGeometry(100, 100, 200, 150)
        self.cursor = QtCore.QPoint(0, 0)
        self.auto = WindowAutoHide(self.win, cursor_pos=lambda: self.cursor)
        self.win.show()
        self.inside = self.win.mapToGlobal(QtCore.QPoint(50, 50))
        self.outside = self.win.mapToGlobal(QtCore.QPoint(1000, 1000))

    def test_show_arms_the_poll(self):
        self.assertTrue(self.auto.timer.isActive())
        self.assertFalse(self.auto.entered)

    def test_never_entered_stays_up(self):
        self.cursor = self.outside
        self.auto.check()
        self.assertTrue(self.win.isVisible())

    def test_entered_then_left_hides_flagged(self):
        self.cursor = self.inside
        self.auto.check()
        self.assertTrue(self.auto.entered)
        self.assertTrue(self.win.isVisible())
        self.cursor = self.outside
        self.auto.check()
        self.assertFalse(self.win.isVisible())
        self.assertEqual(self.win.hide_flags, [True], "the hide is flagged automatic")
        self.assertFalse(self.win._auto_hiding, "and the flag is cleared after")
        self.assertFalse(self.auto.timer.isActive())

    def test_pinned_never_hides(self):
        self.win.is_pinned = True
        self.cursor = self.inside
        self.auto.check()
        self.cursor = self.outside
        self.auto.check()
        self.assertTrue(self.win.isVisible())

    def test_each_show_re_arms(self):
        self.cursor = self.inside
        self.auto.check()
        self.cursor = self.outside
        self.auto.check()
        self.win.show()
        self.assertTrue(self.auto.timer.isActive())
        self.assertFalse(self.auto.entered, "a new showing starts un-entered")

    def test_a_popup_the_window_owns_counts_as_inside(self):
        """A popup the window owns (a uitk ``Menu``, an option-box popup, a
        combo's list) sits outside its rect but is still "inside" for the user.

        Regression: ``isAncestorOf`` stops at window boundaries, so the cursor
        on the window's own Tool popup read as outside, and the Shots panel hid
        while the user was in its menu.
        """
        popup = QtWidgets.QWidget(
            self.win, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
        )
        popup.setGeometry(400, 400, 120, 120)
        row = QtWidgets.QPushButton("row", popup)
        row.setGeometry(0, 0, 120, 120)
        popup.show()
        QtWidgets.QApplication.processEvents()
        self.cursor = self.inside
        self.auto.check()
        self.cursor = row.mapToGlobal(QtCore.QPoint(60, 60))
        self.assertIs(QtWidgets.QApplication.widgetAt(self.cursor), row)
        self.assertTrue(self.auto.cursor_inside())
        self.auto.check()
        self.assertTrue(self.win.isVisible(), "hid while the cursor was on its popup")

    def test_an_unrelated_window_is_outside(self):
        """The walk stops at the managed window: another top-level is outside."""
        other = self.track_widget(QtWidgets.QWidget())
        other.setGeometry(600, 600, 100, 100)
        other.show()
        QtWidgets.QApplication.processEvents()
        self.cursor = self.inside
        self.auto.check()
        self.cursor = other.mapToGlobal(QtCore.QPoint(50, 50))
        self.assertFalse(self.auto.cursor_inside())
        self.auto.check()
        self.assertFalse(self.win.isVisible())

    def test_a_hidden_window_stops_polling(self):
        self.win.hide()
        self.auto.check()
        self.assertFalse(self.auto.timer.isActive())

    def test_lives_with_the_window(self):
        self.assertIs(self.auto.parent(), self.win)


if __name__ == "__main__":
    unittest.main()
