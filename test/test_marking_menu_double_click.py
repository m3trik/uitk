# !/usr/bin/python
# coding=utf-8
"""Pins the marking-menu double-click gesture signals.

``mouseDoubleClickEvent`` re-emits a per-button ``*_double_click`` signal — the
public hook the docs advertise for "quick tool" gestures
(``mm.left_mouse_double_click.connect(self.quick_save)``) and the mechanism
tentacle's camera-view toggle rides (``Cameras`` → double-click inside the
marking menu toggles perspective ⇄ last orthographic view). It fires ONLY while
a stacked menu (a ``startmenu``/``submenu`` surface) is the active UI, so an
ordinary double-click on a standalone tool window is left alone.

This had no coverage, which is exactly how the camera-toggle wiring silently
rotted once — so pin both halves: emits while a menu surface is active, stays
silent otherwise.
"""
import unittest

from qtpy import QtCore, QtGui, QtWidgets

from conftest import QtBaseTestCase
from test_marking_menu_integration import (
    DriveableMarkingMenu,
    StubUi,
    DEFAULT_BINDINGS,
)


class MarkingMenuDoubleClickSignals(QtBaseTestCase):
    """The ``*_double_click`` signals fire on a double-click over a live menu
    surface, and only then."""

    def setUp(self):
        super().setUp()
        self._drain_qt_events()

        self.parent = QtWidgets.QWidget()
        self.parent.resize(400, 400)
        self.parent.show()
        self.track_widget(self.parent)

        self.mm = DriveableMarkingMenu(self.parent, dict(DEFAULT_BINDINGS))
        QtWidgets.QWidget.show(self.mm)
        self.track_widget(self.mm)

        # A stacked menu the user is inside (``cameras`` → tagged ``startmenu``),
        # made the active UI so the gesture's menu-surface gate is satisfied.
        self.menu_ui = StubUi("cameras", parent=self.mm)
        self.mm.sb.register_ui(self.menu_ui)
        self.track_widget(self.menu_ui)
        self.mm.sb.current_ui = self.menu_ui

    def _double_click(self, button, modifier=QtCore.Qt.NoModifier):
        ev = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonDblClick,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            button,
            button,
            modifier,
        )
        QtWidgets.QApplication.sendEvent(self.mm, ev)
        QtWidgets.QApplication.processEvents()

    def test_left_double_click_emits_over_menu_surface(self):
        """The signal tentacle's camera-view toggle connects to must fire."""
        fired = []
        self.mm.left_mouse_double_click.connect(lambda: fired.append(1))
        self._double_click(QtCore.Qt.LeftButton)
        self.assertEqual(fired, [1], "left_mouse_double_click did not emit")

    def test_ctrl_left_double_click_routes_to_ctrl_signal(self):
        """Ctrl+double-click is the distinct ``*_ctrl`` gesture, not the plain one."""
        plain, ctrl = [], []
        self.mm.left_mouse_double_click.connect(lambda: plain.append(1))
        self.mm.left_mouse_double_click_ctrl.connect(lambda: ctrl.append(1))
        self._double_click(QtCore.Qt.LeftButton, QtCore.Qt.ControlModifier)
        self.assertEqual((plain, ctrl), ([], [1]))

    def test_no_emit_when_active_ui_is_not_a_menu_surface(self):
        """A double-click while a standalone tool (no startmenu/submenu tag) is
        active must NOT fire the gesture — it belongs to the tool, not the menu."""
        standalone = StubUi("some_tool_panel", parent=self.mm)  # no menu tag
        self.mm.sb.register_ui(standalone)
        self.mm.sb.current_ui = standalone
        fired = []
        self.mm.left_mouse_double_click.connect(lambda: fired.append(1))
        self._double_click(QtCore.Qt.LeftButton)
        self.assertEqual(fired, [], "gesture fired while no menu surface was active")


if __name__ == "__main__":
    unittest.main()
