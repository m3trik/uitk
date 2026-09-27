# !/usr/bin/python
# coding=utf-8
"""Tests for uitk._bootstrap (pre-QApplication setup, window-system capabilities)."""

import os
import sys
import unittest
from unittest.mock import patch

from conftest import BaseTestCase, setup_qt_application

setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402

import pythontk as ptk  # noqa: E402
from uitk._bootstrap import Bootstrap  # noqa: E402


class TestConfigurePlatform(BaseTestCase):
    """A standalone uitk app runs its Qt on X11 when a Wayland session offers
    it: native Wayland cannot place the marking menu or a popup at the cursor."""

    def _configure(self, env, platform="linux"):
        with (
            patch.object(
                QtWidgets.QApplication, "instance", new=staticmethod(lambda: None)
            ),
            patch.object(sys, "platform", platform),
            patch.dict(os.environ, env, clear=True),
        ):
            applied = Bootstrap.configure_platform()
            return applied, os.environ.get("QT_QPA_PLATFORM")

    def test_a_wayland_session_with_xwayland_runs_on_x11_first(self):
        env = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
        # X11 first; native Wayland if the xcb plug-in cannot load.
        self.assertEqual(self._configure(env), (True, "xcb;wayland"))

    def test_an_explicit_platform_always_wins(self):
        env = {
            "WAYLAND_DISPLAY": "wayland-0",
            "DISPLAY": ":0",
            "QT_QPA_PLATFORM": "wayland",
        }
        self.assertEqual(self._configure(env), (False, "wayland"))

    def test_nothing_changes_without_xwayland_or_off_linux(self):
        self.assertEqual(
            self._configure({"WAYLAND_DISPLAY": "wayland-0"}), (False, None)
        )
        self.assertEqual(self._configure({"DISPLAY": ":0"}), (False, None))
        env = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
        self.assertEqual(self._configure(env, platform="win32"), (False, None))

    def test_a_host_owned_application_is_left_alone(self):
        """Inside Maya/Blender the QApplication exists: too late, and not ours."""
        env = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(Bootstrap.configure_platform())
            self.assertIsNone(os.environ.get("QT_QPA_PLATFORM"))


class TestCapabilities(BaseTestCase):
    def test_only_native_wayland_forbids_client_placement(self):
        for name, expected in (
            ("wayland", False),
            ("wayland-egl", False),
            ("xcb", True),
            ("windows", True),
        ):
            with (
                self.subTest(platform=name),
                patch.object(
                    QtGui.QGuiApplication,
                    "platformName",
                    new=staticmethod(lambda n=name: n),
                ),
            ):
                self.assertIs(Bootstrap.positions_windows(), expected)

    def test_only_x11_without_a_compositor_drops_translucency(self):
        """Without a compositing manager an X11 translucent window paints
        black; an unknown answer (no X server to ask) keeps translucency."""
        cases = (
            ("xcb", False, False),
            ("xcb", True, True),
            ("xcb", None, True),
            ("windows", False, True),
        )
        for platform, compositor, expected in cases:
            with (
                self.subTest(platform=platform, compositor=compositor),
                patch.object(
                    QtGui.QGuiApplication,
                    "platformName",
                    new=staticmethod(lambda p=platform: p),
                ),
                patch.object(ptk.X11, "has_compositor", return_value=compositor),
            ):
                self.assertIs(Bootstrap.composites(), expected)


@unittest.skipUnless(
    QtGui.QGuiApplication.platformName() == "xcb" and ptk.X11.has_compositor() is False,
    "a real X server without a compositor (e.g. Xvfb)",
)
class TestOnX11WithoutCompositor(BaseTestCase):
    """End to end on the real thing: a bare X server paints a translucent
    window's clear pixels black."""

    def test_a_top_level_stays_opaque(self):
        window = QtWidgets.QWidget()
        self.addCleanup(window.deleteLater)
        self.assertFalse(Bootstrap.set_translucent(window))
        self.assertFalse(window.testAttribute(QtCore.Qt.WA_TranslucentBackground))

    def test_a_full_screen_overlay_gets_the_desktop_to_paint(self):
        window = QtWidgets.QWidget()
        self.addCleanup(window.deleteLater)
        backdrop = Bootstrap.screen_backdrop(window)
        self.assertIsNotNone(backdrop)
        self.assertFalse(backdrop.isNull())


if __name__ == "__main__":
    unittest.main()
