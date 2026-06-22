# !/usr/bin/python
# coding=utf-8
"""Deterministic reproduction of the Blender "leaf click is dead" report.

Symptom (live, Blender only): clicking a leaf button in the marking menu or a
submenu — e.g. ``normals`` ▸ *Average* / *Set To Face* — intermittently does
nothing; the slot is never called and the user has to click again (up to four
times). Reproduced + diagnosed live in
``tentacle/test/blender/normals_multiclick_check.py`` (real Blender, the real
buttons): with the grab held by the MENU, the named leaves fired **0/3**; with
the fix, **3/3**.

The precondition the simpler harnesses miss: the MarkingMenu is **holding the
mouse grab**. That happens whenever ``normals`` is reached through a *chord*
(hold the key + a mouse button → main/edit → Normals), which grabs the mouse via
``_transfer_mouse_control``. With the grab on the menu, a leaf's left **press**
is delivered to ``MarkingMenu`` instead of the button, and ``_sync_menu_to_state``
re-resolves ``buttons=LeftButton`` (key held) as the ``Key_F12|LeftButton``
**chord** — navigating the whole menu to ``cameras`` before the leaf can fire.
The click is "dead". (Live, the activation poller's 0.02s ``MouseTracking.track()``
periodically migrates the grab to the button under the cursor, which lets a click
through — so whether a given click works is a *race*, hence "up to four clicks".)

This is host-independent logic in the shared ``MarkingMenu`` (uitk), so the
*grab-held* state reproduces deterministically here with the same
``DriveableMarkingMenu`` harness the input-sequence tests use (the press is sent
straight to the menu, modelling the grab routing) — no flaky real Blender needed.
``test_genuine_chord_still_navigates`` is the control: the same press, but with
nothing clickable under the cursor, is a real chord and *must* still navigate (so
the fix must not break chords).
"""
import unittest
from unittest import mock

from qtpy import QtCore, QtGui, QtWidgets

from conftest import QtBaseTestCase
from test_marking_menu_integration import (
    DriveableMarkingMenu,
    StubUi,
    DEFAULT_BINDINGS,
)


class MarkingMenuLeafClickWhileGrabHeld(QtBaseTestCase):
    """A leaf click while the MENU holds the mouse grab (a chord reach) must execute
    the leaf, not re-resolve the press as the ``F12|LeftButton`` chord and navigate
    away."""

    def setUp(self):
        super().setUp()
        self._drain_qt_events()

        self.parent = QtWidgets.QWidget()
        self.parent.resize(400, 400)
        self.parent.show()
        self.track_widget(self.parent)

        self.mm = DriveableMarkingMenu(self.parent, dict(DEFAULT_BINDINGS))
        # Blender's TclBlender constructs with suppress_default_on_reentry=True.
        self.mm._suppress_default_on_reentry = True
        QtWidgets.QWidget.show(self.mm)
        self.track_widget(self.mm)

        # A submenu the user has navigated into (e.g. normals#submenu), tagged so
        # the menu's startmenu/submenu gates treat it as a live menu surface.
        self.submenu = StubUi("normals#submenu", parent=self.mm)
        self.submenu._tags = {"submenu"}
        self.submenu.tags = ["submenu"]
        self.mm.sb.register_ui(self.submenu)
        self.track_widget(self.submenu)

        # A real leaf button on that submenu, wired the way Switchboard wires a
        # slot button (``ui`` + ``base_name``), with a recorder on its slot.
        self.leaf = QtWidgets.QPushButton("Average Normals", self.submenu)
        self.leaf.setObjectName("tb004")
        self.leaf.ui = self.submenu
        self.leaf.base_name = lambda: "tb"
        self.fired = []
        self.leaf.clicked.connect(lambda *a: self.fired.append("tb004"))
        self.track_widget(self.leaf)

        # Put the user inside the submenu with the activation key held and the MENU
        # holding the grab — the live state after reaching normals through a chord
        # (_transfer_mouse_control grabbed the mouse). Sending the press straight to
        # self.mm below models the grab routing the leaf press to the menu.
        self.mm._activation_key_held = True
        self.mm._non_default_shown = True
        self.mm.sb.current_ui = self.submenu
        self.mm._current_widget = self.submenu
        try:
            self.mm.grabMouse()  # may no-op under offscreen QPA; the routing below models it
        except Exception:
            pass

    def _press(self, button, buttons_after):
        ev = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            button,
            buttons_after,
            QtCore.Qt.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(self.mm, ev)
        QtWidgets.QApplication.processEvents()

    def _release(self, button, buttons_after):
        ev = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            button,
            buttons_after,
            QtCore.Qt.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(self.mm, ev)
        QtWidgets.QApplication.processEvents()

    def test_leaf_click_while_grab_armed_must_not_navigate_away(self):
        """Cursor over the leaf, grab armed, activation held → a left press must
        keep the submenu visible so the leaf can fire.

        Regressed when mousePressEvent re-resolved the on-leaf press as the
        F12|LeftButton chord and jumped to 'cameras' — the dead click. Fixed by
        _is_menu_item_press classifying the press as a click, not a chord.
        """
        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=self.leaf
        ):
            self._press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)

        current = self.mm.sb.current_ui
        self.assertEqual(
            current.objectName(),
            "normals#submenu",
            "leaf-click press was re-resolved as the F12|LeftButton chord and "
            f"navigated to '{current.objectName()}' — the leaf can never fire "
            "(the live 'dead click').",
        )

    def test_leaf_slot_runs_on_click_while_grab_armed(self):
        """End to end — the user's literal symptom: the leaf's slot must be
        called. A full press+release over the leaf, grab armed, runs the leaf's
        ``clicked`` exactly once.

        Regressed when the press jumped the menu to 'cameras', so at release the
        leaf was no longer a descendant of the current_ui and the dispatcher
        skipped it (``self.fired`` stayed empty).
        """
        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=self.leaf
        ):
            self._press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
            self._release(QtCore.Qt.NoButton, QtCore.Qt.NoButton)

        self.assertEqual(
            self.fired,
            ["tb004"],
            "the leaf slot was never called — the click is dead "
            f"(current_ui is now '{self.mm.sb.current_ui.objectName()}').",
        )

    def test_release_dispatch_uses_event_position_not_drifted_cursor(self):
        """Under a pumped host loop (Blender) the cursor can move between the
        physical release and when the handler runs. The dispatch must resolve the
        leaf at the *release event* position, not the live (drifted) cursor — else
        the click is silently dropped (the intermittent dead click).

        Here the event lands on the leaf (10,10) but the live cursor has drifted
        to (900,900) over nothing. The leaf must still fire.
        """
        def _at(pt):
            return self.leaf if (pt.x(), pt.y()) == (10, 10) else None

        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", side_effect=_at
        ), mock.patch.object(
            QtGui.QCursor, "pos", return_value=QtCore.QPoint(900, 900)
        ):
            self._press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
            self._release(QtCore.Qt.NoButton, QtCore.Qt.NoButton)

        self.assertEqual(
            self.fired,
            ["tb004"],
            "release was resolved at the drifted cursor, not the event position "
            "— the click was dropped.",
        )

    def test_genuine_chord_still_navigates(self):
        """CONTROL: the same left press, but with nothing clickable under the
        cursor, is a real F12+LMB chord and MUST still navigate to 'cameras'.

        PASSES today and must keep passing after the fix — the fix differentiates
        an on-leaf click from a chord, it does not disable chords.

        "Nothing clickable under the cursor" must mock BOTH hit-tests empty:
        ``widgetAt`` (OS) AND ``childAt`` (the geometric fallback _owned_item_at
        adds). With only widgetAt mocked, childAt would geometrically find the
        leaf (it sits at the press point) and (correctly) read the press as a
        click — so an empty-space chord must null both.
        """
        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=None
        ), mock.patch.object(self.submenu, "childAt", return_value=None):
            self._press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)

        self.assertEqual(self.mm.sb.current_ui.objectName(), "cameras")
        self.assertEqual(self.fired, [], "no leaf was under the cursor")

    def test_right_press_over_leaf_is_a_chord_not_a_click(self):
        """A Middle/Right press is a chord selector, never an item click — even with
        the cursor over a leaf and the menu holding the grab. Guards the LeftButton
        discriminator in _is_menu_item_press (a leaf is only ever left-clicked); a
        Right press must resolve the F12|Right chord ('main'), not fire the leaf.
        """
        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=self.leaf
        ):
            self._press(QtCore.Qt.RightButton, QtCore.Qt.RightButton)

        self.assertEqual(
            self.mm.sb.current_ui.objectName(),
            "main",
            "a Right press over a leaf must resolve as the F12|Right chord, not a click",
        )
        self.assertEqual(self.fired, [], "the leaf must not fire on a non-Left press")


class InputHandoffDiagnostics(QtBaseTestCase):
    """The input-handoff diagnostics (``enable_input_logging``) must default OFF
    and never run their state capture on the hot event path unless explicitly
    enabled.

    Enabling that capture unconditionally — it calls ``QApplication.widgetAt()``
    inside ``mousePressEvent`` — segfaulted offscreen QPA on every press. The gate
    is a dedicated flag, NOT the log level: the class logger sits at NOTSET, so
    ``isEnabledFor(DEBUG)`` is True even when nothing is emitted.
    """

    def setUp(self):
        super().setUp()
        self._drain_qt_events()
        self.parent = QtWidgets.QWidget()
        self.parent.resize(200, 200)
        self.parent.show()
        self.track_widget(self.parent)
        self.mm = DriveableMarkingMenu(self.parent, dict(DEFAULT_BINDINGS))
        QtWidgets.QWidget.show(self.mm)
        self.track_widget(self.mm)

    def test_diagnostics_off_by_default(self):
        self.assertFalse(self.mm._input_logging_on)
        self.assertFalse(self.mm.mouse_tracking._input_logging_on)

    def test_press_does_not_capture_state_while_off(self):
        """Regression guard: with diagnostics off, a press must NOT invoke the
        (Qt-hit-test-touching) state capture — that eager call crashed offscreen."""
        with mock.patch.object(
            DriveableMarkingMenu, "_input_state", autospec=True
        ) as spy:
            ev = QtGui.QMouseEvent(
                QtCore.QEvent.MouseButtonPress,
                QtCore.QPointF(10, 10),
                QtCore.QPointF(10, 10),
                QtCore.Qt.LeftButton,
                QtCore.Qt.LeftButton,
                QtCore.Qt.NoModifier,
            )
            try:
                self.mm.mousePressEvent(ev)  # press internals are not under test
            except Exception:
                pass
        spy.assert_not_called()

    def test_enable_disable_toggles_both_flags(self):
        """enable/disable flips the gate on BOTH the menu and its MouseTracking
        (separate class loggers). Logging I/O is mocked so the test neither writes
        a file nor mutates the shared class-logger level."""
        mt_cls = type(self.mm.mouse_tracking)
        with mock.patch.object(
            DriveableMarkingMenu, "set_log_file"
        ), mock.patch.object(
            DriveableMarkingMenu, "set_log_level"
        ), mock.patch.object(
            mt_cls, "set_log_file"
        ), mock.patch.object(
            mt_cls, "set_log_level"
        ):
            returned = self.mm.enable_input_logging("ignored.log")
            self.assertEqual(returned, "ignored.log")
            self.assertTrue(self.mm._input_logging_on)
            self.assertTrue(self.mm.mouse_tracking._input_logging_on)

            self.mm.disable_input_logging()
            self.assertFalse(self.mm._input_logging_on)
            self.assertFalse(self.mm.mouse_tracking._input_logging_on)


if __name__ == "__main__":
    unittest.main()
