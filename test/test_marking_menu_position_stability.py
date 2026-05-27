#!/usr/bin/python
# coding=utf-8
"""Regression: marking menu must stay anchored to its gesture start position
across chord transitions, even with cursor jitter.

Bug: each chord transition (e.g. F12 → F12+LMB → F12) re-ran
``start_gesture(cursor)`` and ``setCurrentWidget`` cursor-centered, so any
hand jitter between presses migrated the menu pixel-by-pixel in a
consistent direction. User report: "the ui steadily shifts to the left
or right a small amount each time."

Fix: ``start_gesture`` only runs on the first show of an activation
cycle (when the overlay path is empty). Subsequent startmenu shows
anchor at the existing ``start_pos`` instead of the current cursor.
"""
import unittest

from qtpy import QtCore, QtGui, QtWidgets

from conftest import QtBaseTestCase
from uitk.widgets.marking_menu._marking_menu import MarkingMenu


class _Path:
    """Minimal stand-in for ``overlay.path`` — only the bits MarkingMenu reads."""

    def __init__(self):
        self._entries = []

    @property
    def is_empty(self):
        return len(self._entries) == 0

    @property
    def start_pos(self):
        return self._entries[0][2] if self._entries else None

    def reset(self):
        self._entries = [(None, None, QtGui.QCursor.pos())]

    def clear(self):
        self._entries = []

    def add(self, ui, widget):
        if widget and widget.isVisible():
            self._entries.append(
                (widget, widget.mapToGlobal(widget.rect().center()), QtGui.QCursor.pos())
            )


class _Overlay:
    def __init__(self):
        self.path = _Path()

    def start_gesture(self, global_pos):
        # Mirror real Overlay.start_gesture: reset path which captures
        # the current cursor position as start_pos.
        self.path.reset()

    def clone_widgets_along_path(self, *_a, **_kw):
        pass


class _MouseTracking:
    def update_child_widgets(self):
        pass


class _StubStyle:
    def set(self, **_kw):
        pass


class _StubUi(QtWidgets.QMainWindow):
    """Real QWidget so geometry calls work; carries the marking-menu tags."""

    def __init__(self, name, tags, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.resize(600, 600)
        self._tags = set(tags)
        self.is_initialized = True
        self.header = None
        self.widgets = []
        self.style = _StubStyle()
        self.ensure_on_screen = False
        self.restore_window_size = False

        class _Settings:
            def clear(self, *_a, **_kw):
                pass

        self.settings = _Settings()

    def has_tags(self, tags):
        if isinstance(tags, str):
            tags = [tags]
        return any(t in self._tags for t in tags)


class _StubSb:
    def __init__(self):
        self._uis = {}
        self._current = None

    def register(self, ui):
        self._uis[ui.objectName()] = ui

    def get_ui(self, name):
        return self._uis.get(name) if name else self._current

    @property
    def current_ui(self):
        return self._current

    @current_ui.setter
    def current_ui(self, ui):
        self._current = ui

    @property
    def active_ui(self):
        return self._current

    def get_widget(self, name, ui):
        return None

    def ui_history(self, *_a, **_kw):
        return []


class _MM(MarkingMenu):
    """Bypass MarkingMenu.__init__ — exercise the exact methods under test."""

    def __init__(self, parent):
        QtWidgets.QWidget.__init__(self, parent=parent)
        import logging

        self.logger = logging.getLogger("PositionStabilityTest")
        self.logger.setLevel(logging.WARNING)

        self.sb = _StubSb()
        self.overlay = _Overlay()
        self.mouse_tracking = _MouseTracking()

        self._current_widget = None
        self._pending_hide_widget = None
        self._activation_key_held = False
        self._activation_key_str = "Key_F12"
        self._suppress_default_on_reentry = False
        self._non_default_shown = False
        self._standalone_suppress = False
        self._bindings = {"Key_F12": "hud"}
        self._windows_to_restore = set()
        self._transitioning_to_window = False

        # Frameless overlay so geometry queries return sane values.
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.resize(1920, 1080)
        QtWidgets.QWidget.show(self)


class TestMarkingMenuPositionStability(QtBaseTestCase):
    """Bug-for-bug regression covering [user report] "ui steadily shifts" on
    repeated chord transitions while holding F12."""

    _drain_qt_events_in_teardown = False

    def setUp(self):
        super().setUp()
        self.parent = QtWidgets.QWidget()
        self.parent.resize(400, 400)
        self.parent.show()
        self.track_widget(self.parent)

        self.mm = _MM(self.parent)
        self.track_widget(self.mm)

        self.hud = _StubUi("hud", ["startmenu"], parent=self.mm)
        self.cameras = _StubUi("cameras", ["startmenu"], parent=self.mm)
        self.main = _StubUi("main", ["startmenu"], parent=self.mm)
        self.mm.sb.register(self.hud)
        self.mm.sb.register(self.cameras)
        self.mm.sb.register(self.main)
        QtWidgets.QApplication.processEvents()

    def _initial_activation(self, cursor):
        """Simulate F12 press: cursor at given global position, show hud."""
        QtGui.QCursor.setPos(cursor)
        QtWidgets.QApplication.processEvents()
        self.mm._activation_key_held = True
        self.mm._show_marking_menu(self.hud)
        QtWidgets.QApplication.processEvents()

    def _chord_show(self, ui_name, cursor):
        """Simulate chord transition: move cursor (jitter) then show menu."""
        QtGui.QCursor.setPos(cursor)
        QtWidgets.QApplication.processEvents()
        ui = self.mm.sb.get_ui(ui_name)
        self.mm._show_marking_menu(ui)
        QtWidgets.QApplication.processEvents()

    def test_initial_show_anchors_at_cursor(self):
        """First activation must anchor at the cursor (sets start_pos)."""
        anchor = QtCore.QPoint(900, 500)
        self._initial_activation(anchor)

        expected_pos = self.mm.mapFromGlobal(anchor) - self.hud.rect().center()
        self.assertEqual(self.hud.pos(), expected_pos)
        self.assertFalse(self.mm.overlay.path.is_empty)

    def test_chord_transition_anchors_at_start_pos_not_cursor(self):
        """LMB press during gesture must position cameras at start_pos."""
        anchor = QtCore.QPoint(900, 500)
        self._initial_activation(anchor)

        # Simulate cursor jitter on LMB press.
        jittered = anchor + QtCore.QPoint(3, -2)
        self._chord_show("cameras", jittered)

        # cameras must be at start_pos (= anchor), NOT at jittered cursor.
        expected_pos = self.mm.mapFromGlobal(anchor) - self.cameras.rect().center()
        self.assertEqual(
            self.cameras.pos(),
            expected_pos,
            "chord transition must ignore cursor jitter — anchor at gesture start",
        )

    def test_no_drift_over_many_chord_transitions(self):
        """Bouncing between two startmenus must never shift their position
        even with consistent cursor drift on each press."""
        anchor = QtCore.QPoint(900, 500)
        self._initial_activation(anchor)

        positions_main = []
        positions_cameras = []

        # Simulate user's hand drifting 1px right + 1px down per press.
        for i in range(20):
            drift = QtCore.QPoint(i, i // 2)
            self._chord_show("main", anchor + drift)
            positions_main.append(self.main.pos())
            self._chord_show("cameras", anchor + drift)
            positions_cameras.append(self.cameras.pos())

        # All 20 iterations must produce identical positions.
        self.assertEqual(
            len(set((p.x(), p.y()) for p in positions_main)),
            1,
            f"main drifted across iterations: {positions_main[:5]} … {positions_main[-3:]}",
        )
        self.assertEqual(
            len(set((p.x(), p.y()) for p in positions_cameras)),
            1,
            f"cameras drifted across iterations: "
            f"{positions_cameras[:5]} … {positions_cameras[-3:]}",
        )

    def test_path_clear_starts_fresh_gesture(self):
        """If the path was cleared (e.g. menu hidden), the next show must
        start a new gesture at the new cursor (not the stale start_pos)."""
        first = QtCore.QPoint(900, 500)
        self._initial_activation(first)
        first_start = self.mm.overlay.path.start_pos

        # Simulate menu hide → path cleared, then a new activation.
        self.mm.overlay.path.clear()
        second = QtCore.QPoint(600, 700)
        self._initial_activation(second)

        self.assertNotEqual(first_start, self.mm.overlay.path.start_pos)
        self.assertEqual(self.mm.overlay.path.start_pos, second)


if __name__ == "__main__":
    unittest.main()
