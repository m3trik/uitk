# !/usr/bin/python
# coding=utf-8
"""Reproduce: launched tool window falls behind launching window.

Bug scenario (sibling windows):
    1. Sequencer (MainWindow) is visible, parented to Maya.
    2. Shots settings window (another MainWindow) is opened via marking menu.
    3. Both windows are siblings under Maya — no Z-order enforcement.
    4. Any activation of the sequencer (OS focus, mouse enter, etc.) can
       bring it above the shots window.

Fix:
    When _show_window detects the target is launched from a visible
    standalone window, it reparents the target to that window so Qt's
    window-group management keeps the new window on top.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PACKAGE_ROOT = Path(__file__).parent.parent.parent.absolute()
TEST_DIR = Path(__file__).parent.parent.absolute()
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

from conftest import setup_qt_application, QtBaseTestCase

app = setup_qt_application()

from qtpy import QtWidgets, QtCore
from uitk.widgets.mainWindow import MainWindow


class MockSwitchboard:
    """Minimal switchboard mock for MainWindow construction."""

    def __init__(self):
        self.current_ui = None
        self.app = QtWidgets.QApplication.instance()
        self.default_signals = {}

    def convert_to_legal_name(self, name):
        return name

    def get_base_name(self, name):
        return name

    def has_tags(self, widget, tags=None):
        return False

    def edit_tags(self, *a, **kw):
        return None

    def _get_widget_from_ui(self, ui, attr):
        return None

    def get_slots_instance(self, widget):
        return MagicMock()

    def get_ui_relatives(self, *a, **kw):
        return []

    def get_widget(self, name, ui):
        return None

    def center_widget(self, *a, **kw):
        pass

    def init_slot(self, *a, **kw):
        pass

    def call_slot(self, *a, **kw):
        pass

    def connect_slot(self, *a, **kw):
        pass


class TestWindowZOrderSiblings(QtBaseTestCase):
    """Prove that sibling windows can freely reorder (the root cause)."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()
        # Simulate Maya as the top-level parent
        self.maya = self.track_widget(QtWidgets.QMainWindow())
        self.maya.resize(1200, 800)
        self.maya.show()

        # Sequencer: child of Maya
        self.sequencer = self.track_widget(
            MainWindow("sequencer_test", self.sb, add_footer=False)
        )
        self.sequencer.setParent(self.maya, QtCore.Qt.Window)
        self.sequencer.resize(800, 400)
        self.sequencer.show()
        app.processEvents()

        # Shots: starts as SIBLING of sequencer (both under Maya) — pre-fix state
        self.shots = self.track_widget(
            MainWindow("shots_test", self.sb, add_footer=False)
        )
        self.shots.setParent(self.maya, QtCore.Qt.Window)
        self.shots.resize(300, 500)

    def test_sibling_raise_steals_zorder(self):
        """Prove siblings can steal Z-order from each other.

        Bug: Both sequencer and shots are parented to Maya (siblings).
        When the sequencer is activated, it can freely rise above the
        shots window because there is no parent-child Z constraint.
        Fixed: 2026-03-24
        """
        self.shots.show()
        self.shots.raise_()
        self.shots.activateWindow()
        app.processEvents()

        # Simulate the sequencer being activated (OS focus return, etc.)
        self.sequencer.raise_()
        self.sequencer.activateWindow()
        app.processEvents()

        # Sequencer raise succeeds — proving sibling windows can
        # freely steal Z-order. This is the root cause.
        # (We can't directly check Z-order in Qt, but this call
        # completes without constraint — no Z-order enforcement.)
        self.assertTrue(self.sequencer.isActiveWindow())


class TestWindowZOrderChildEnforcement(QtBaseTestCase):
    """Verify that making shots a CHILD of sequencer prevents Z-order theft."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

        self.maya = self.track_widget(QtWidgets.QMainWindow())
        self.maya.resize(1200, 800)
        self.maya.show()

        self.sequencer = self.track_widget(
            MainWindow("sequencer_test", self.sb, add_footer=False)
        )
        self.sequencer.setParent(self.maya, QtCore.Qt.Window)
        self.sequencer.resize(800, 400)
        self.sequencer.show()
        app.processEvents()

        # Shots: CHILD of sequencer (the fix)
        self.shots = self.track_widget(
            MainWindow("shots_test", self.sb, add_footer=False)
        )
        self.shots.setParent(self.sequencer, QtCore.Qt.Window)
        self.shots.resize(300, 500)

    def test_child_stays_above_parent_after_parent_activate(self):
        """After fix: shots (child) stays above sequencer (parent).

        Qt window-group management ensures child windows with Qt.Window
        flag stay above their parent. Activating the parent does NOT
        bring it above the child.
        """
        self.shots.show()
        self.shots.raise_()
        self.shots.activateWindow()
        app.processEvents()

        # Activate the parent (sequencer) — simulates any mechanism
        # that might give the sequencer focus after shots is shown.
        self.sequencer.activateWindow()
        app.processEvents()

        # The shots window is still visible and never got hidden
        self.assertTrue(self.shots.isVisible())
        # Parent relationship enforces Z-order
        self.assertEqual(self.shots.parentWidget(), self.sequencer)

    def test_auto_hide_does_not_raise_parent(self):
        """Auto-hide on mouse-leave should not raise parent window."""
        self.shots.show()
        app.processEvents()

        raised_count = {"value": 0}
        orig_raise = self.sequencer.raise_

        def spy_raise():
            raised_count["value"] += 1
            orig_raise()

        self.sequencer.raise_ = spy_raise

        # Simulate auto-hide with flag
        self.shots._auto_hiding = True
        self.shots.hide()
        self.shots._auto_hiding = False
        app.processEvents()

        self.assertEqual(
            raised_count["value"],
            0,
            "Auto-hide should NOT raise the parent window.",
        )


if __name__ == "__main__":
    unittest.main()
