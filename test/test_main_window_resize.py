# !/usr/bin/python
# coding=utf-8
"""Regression tests for the MainWindow dynamic-resize API.

Covers:
- ``adjust_height_by`` applies a signed delta, preserves width, clamps to min.
- ``fit_height_to_content`` snaps to layout's natural content height.
- ``CollapsableGroup`` delegates its window resize through the central API
  (verified via a stubbed ``adjust_height_by`` recorder).
"""
import unittest

from qtpy import QtCore, QtWidgets

from conftest import QtBaseTestCase

from uitk.widgets.mainWindow import MainWindow
from uitk.widgets.collapsableGroup import CollapsableGroup


class _BareSwitchboard:
    """Minimal stand-in so MainWindow's __init__ can complete without uitk.Switchboard."""

    def convert_to_legal_name(self, name):
        return name

    def get_base_name(self, name):
        return name

    def has_tags(self, *_a, **_k):
        return False

    def get_slots_instance(self, *_a, **_k):
        return None

    def center_widget(self, *_a, **_k):
        return None


def _build_window(content_widget):
    """Construct a MainWindow with content_widget centered, return it."""
    win = MainWindow(
        name="test_resize_window",
        switchboard_instance=_BareSwitchboard(),
        central_widget=content_widget,
        restore_window_size=False,
        ensure_on_screen=False,
    )
    return win


class TestAdjustHeightBy(QtBaseTestCase):
    """Signed-delta resize."""

    def test_zero_delta_is_a_noop(self):
        central = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(central)
        win = self.track_widget(_build_window(central))
        win.resize(300, 400)
        win.adjust_height_by(0)
        self.assertEqual(win.height(), 400)
        self.assertEqual(win.width(), 300)

    def test_positive_delta_grows_window_preserving_width(self):
        central = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(central)
        win = self.track_widget(_build_window(central))
        win.resize(300, 400)
        win.adjust_height_by(50)
        self.assertEqual(win.height(), 450)
        self.assertEqual(win.width(), 300)

    def test_negative_delta_clamped_to_minimum_size_hint(self):
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        # Force a known minimum content size
        spacer = QtWidgets.QLabel("x" * 20)
        spacer.setMinimumHeight(120)
        layout.addWidget(spacer)
        win = self.track_widget(_build_window(central))
        win.show()
        win.resize(300, 400)
        QtWidgets.QApplication.processEvents()

        win.adjust_height_by(-1000)  # would go negative
        self.assertGreaterEqual(win.height(), win.minimumSizeHint().height())
        self.assertEqual(win.width(), 300)


class TestFitHeightToContent(QtBaseTestCase):
    """Snap-to-content resize."""

    def test_fit_collapses_to_minimum_size_hint(self):
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        label = QtWidgets.QLabel("hi")
        label.setFixedHeight(30)
        layout.addWidget(label)
        win = self.track_widget(_build_window(central))
        win.show()
        win.resize(400, 800)  # user-stretched
        QtWidgets.QApplication.processEvents()

        win.fit_height_to_content()
        # Width preserved; height snapped near the minimum hint.
        self.assertEqual(win.width(), 400)
        self.assertLess(win.height(), 800)
        self.assertGreaterEqual(win.height(), win.minimumSizeHint().height() - 1)


class TestCollapsableGroupDelegatesToMainWindow(QtBaseTestCase):
    """CollapsableGroup must hand the resize off to MainWindow.adjust_height_by."""

    def test_toggle_invokes_adjust_height_by(self):
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        group = CollapsableGroup("Test")
        group.restore_state = False
        group.setLayout(QtWidgets.QVBoxLayout())
        group.addWidget(QtWidgets.QLabel("inner"))
        group.addWidget(QtWidgets.QLabel("inner2"))
        layout.addWidget(group)
        win = self.track_widget(_build_window(central))
        win.show()
        QtWidgets.QApplication.processEvents()

        calls = []
        win.adjust_height_by = lambda d: calls.append(d)

        group.toggle_expand(False)  # collapse
        self.assertTrue(
            calls and calls[-1] < 0,
            f"Expected negative delta on collapse, got {calls!r}",
        )

        group.toggle_expand(True)  # expand
        self.assertTrue(
            calls and calls[-1] > 0,
            f"Expected positive delta on expand, got {calls!r}",
        )


if __name__ == "__main__":
    unittest.main()
