#!/usr/bin/python
# coding=utf-8
"""Regression: the marking-menu overlay must follow the active monitor.

Bug: the overlay is a single frameless full-screen window and every menu is
positioned inside it via ``self.mapFromGlobal(...)``. ``showFullScreen()``
binds the window to whichever screen it currently occupies — set once at
construction to the parent (Maya) window's screen. After dragging Maya to a
second monitor, the overlay stayed pinned to the original screen, so a menu
anchored on the new monitor mapped to local coordinates outside the overlay's
bounds and silently never appeared. User report: "shows once, then on
subsequent show attempts fails without error … when dragging the maya app to
a second monitor it won't show on that window."

Fix: ``MarkingMenu._ensure_fullscreen_on_active_screen`` relocates the overlay
to the screen under the cursor before the menu is positioned. Crucially it is
a strict no-op on single-monitor / indeterminate setups (no screen mismatch
detectable), so it cannot perturb the existing single-screen behaviour.
"""
import unittest
from unittest import mock

from qtpy import QtCore, QtWidgets

from conftest import QtBaseTestCase
from uitk.widgets.marking_menu._marking_menu import MarkingMenu


class _FakeScreen:
    """Minimal stand-in for ``QScreen`` — only ``geometry``/``availableGeometry``."""

    def __init__(self, rect):
        self._rect = rect

    def geometry(self):
        return self._rect

    def availableGeometry(self):
        return self._rect


class _MMBare(MarkingMenu):
    """Bypass ``MarkingMenu.__init__`` — exercise only the method under test."""

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent=parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.resize(800, 600)


class TestMarkingMenuMultiScreen(QtBaseTestCase):
    """Covers the overlay-follows-the-active-monitor fix."""

    def setUp(self):
        super().setUp()
        self.mm = _MMBare()
        self.track_widget(self.mm)

    def test_relocates_overlay_to_anchor_screen(self):
        """Anchor on a different monitor → overlay is moved + re-full-screened
        on that monitor (otherwise the menu lands off the pinned overlay). The
        target screen is resolved from the anchor — the same point the menu is
        positioned against — not the cursor, so the two always agree."""
        screen1 = _FakeScreen(QtCore.QRect(0, 0, 1920, 1080))
        screen2 = _FakeScreen(QtCore.QRect(1920, 0, 1920, 1080))
        anchor = QtCore.QPoint(2880, 540)  # center of monitor 2

        handle = mock.Mock()
        handle.screen.return_value = screen1  # overlay currently on monitor 1

        with mock.patch.object(
            QtWidgets.QApplication, "screenAt", return_value=screen2
        ) as screen_at, mock.patch.object(
            self.mm, "windowHandle", return_value=handle
        ), mock.patch.object(
            self.mm, "setGeometry"
        ) as set_geom, mock.patch.object(
            self.mm, "showFullScreen"
        ) as show_fs:
            self.mm._ensure_fullscreen_on_active_screen(anchor)

        screen_at.assert_called_once_with(anchor)  # anchor drives screen choice
        handle.setScreen.assert_called_once_with(screen2)
        set_geom.assert_called_once_with(screen2.geometry())
        show_fs.assert_called_once()

    def test_no_relocation_when_already_on_active_screen(self):
        """Cursor on the overlay's current monitor → no move, no re-show."""
        screen1 = _FakeScreen(QtCore.QRect(0, 0, 1920, 1080))
        handle = mock.Mock()
        handle.screen.return_value = screen1

        with mock.patch.object(
            QtWidgets.QApplication, "screenAt", return_value=screen1
        ), mock.patch.object(
            self.mm, "windowHandle", return_value=handle
        ), mock.patch.object(
            self.mm, "isHidden", return_value=False
        ), mock.patch.object(
            self.mm, "setGeometry"
        ) as set_geom, mock.patch.object(
            self.mm, "showFullScreen"
        ) as show_fs:
            self.mm._ensure_fullscreen_on_active_screen()

        handle.setScreen.assert_not_called()
        set_geom.assert_not_called()
        show_fs.assert_not_called()

    def test_indeterminate_screen_falls_back_to_show_if_hidden(self):
        """No window handle (can't confirm a mismatch) → behave exactly like
        the original ``if self.isHidden(): self.showFullScreen()``: no
        geometry move, only a show when hidden."""
        screen2 = _FakeScreen(QtCore.QRect(1920, 0, 1920, 1080))

        with mock.patch.object(
            QtWidgets.QApplication, "screenAt", return_value=screen2
        ), mock.patch.object(
            self.mm, "windowHandle", return_value=None
        ), mock.patch.object(
            self.mm, "isHidden", return_value=True
        ), mock.patch.object(
            self.mm, "setGeometry"
        ) as set_geom, mock.patch.object(
            self.mm, "showFullScreen"
        ) as show_fs:
            self.mm._ensure_fullscreen_on_active_screen()

        set_geom.assert_not_called()
        show_fs.assert_called_once()


if __name__ == "__main__":
    unittest.main()
