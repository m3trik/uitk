# !/usr/bin/python
# coding=utf-8
"""Regression: both-buttons-held drag-over-item RELEASE must register a click + hide.

Symptom (live): holding **both** mouse buttons (the ``F12|LeftButton|RightButton``
chord), dragging the cursor onto a menu item and releasing did nothing — the click
was dead — whereas releasing a *single* button over the same item works. This
regressed when the old ``_chord_release_timer`` machinery (which dispatched the
held item's action once all buttons were released) was replaced by the
``_sync_menu_to_state`` model: ``child_mouseButtonReleaseEvent`` was reduced to a
no-op pass-through.

The precondition the menu-level harness misses: during a drag the mouse grab
migrates from the MarkingMenu to the child button under the cursor
(``MouseTracking._handle_mouse_grab`` captures QPushButtons). The grabbed button
never got a *press* (the chord press went to the overlay), so it is not ``down``
and Qt emits no native click; the release is delivered to the child's event
filter (``child_mouseButtonReleaseEvent``), NOT to ``MarkingMenu.mouseReleaseEvent``.
So the deterministic reproduction drives ``child_mouseButtonReleaseEvent`` directly
with the child under the mouse — modelling the grab routing — exactly as the
sibling ``test_marking_menu_leaf_click`` models the menu-grab routing.
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


class MarkingMenuChordReleaseDispatch(QtBaseTestCase):
    """A release delivered to a *grabbed child* (the live drag state) must fire
    the item and hide the menu — single button or the both-button chord."""

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

        # The L+R chord menu ("maya"), tagged startmenu, is the live surface.
        self.menu = self.mm.sb.get_ui("maya")

        # A real leaf item on that menu, wired the way Switchboard wires a slot
        # button (``ui`` + ``base_name``), with a recorder on its slot.
        self.leaf = QtWidgets.QPushButton("Do Thing", self.menu)
        self.leaf.setObjectName("tb000")
        self.leaf.ui = self.menu
        self.leaf.base_name = lambda: "tb"
        self.fired = []
        self.leaf.clicked.connect(lambda *a: self.fired.append("tb000"))
        self.track_widget(self.leaf)

        # Put the user inside the chord menu with the key held — the live state
        # after the both-button chord opened "maya" and the grab migrated to the
        # leaf during the drag.
        self.mm._activation_key_held = True
        self.mm._non_default_shown = True
        self.mm.sb.current_ui = self.menu
        self.mm._current_widget = self.menu
        self.menu.show()

    def _release_on_child(
        self, w, button, buttons_after, under_mouse=True, widget_at="__w__", global_pos=(10, 10)
    ):
        """Deliver a release to ``w`` the way the grab routing does.

        ``widget_at`` is what ``QApplication.widgetAt(event position)`` resolves to
        — the dispatch target, mirroring ``mouseReleaseEvent`` (defaults to ``w``).
        ``under_mouse`` only matters for the not-an-owned-item forward path, and
        ``global_pos`` is the release event position (offscreen QPA can't place a
        real cursor, so the target is resolved through the mocked ``widgetAt``)."""
        w.underMouse = lambda: under_mouse
        target = w if widget_at == "__w__" else widget_at
        gp = QtCore.QPointF(*global_pos)
        ev = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(10, 10),
            gp,
            button,
            buttons_after,
            QtCore.Qt.NoModifier,
        )
        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=target
        ):
            consumed = self.mm.child_mouseButtonReleaseEvent(w, ev)
        QtWidgets.QApplication.processEvents()
        return consumed

    def _release_on_menu(self, button, buttons_after, widget_at):
        """Deliver a release to the MENU (mouseReleaseEvent) — the Maya grab path.

        ``widget_at`` is the value (or side_effect callable) ``QApplication.widgetAt``
        resolves to for this release."""
        ev = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            button,
            buttons_after,
            QtCore.Qt.NoModifier,
        )
        kw = (
            {"side_effect": widget_at}
            if callable(widget_at)
            else {"return_value": widget_at}
        )
        with mock.patch.object(QtWidgets.QApplication, "widgetAt", **kw):
            self.mm.mouseReleaseEvent(ev)
        QtWidgets.QApplication.processEvents()

    def _wait(self, ms: int):
        """Spin a REAL event loop for *ms* so the single-shot chord-release timer
        can actually fire — the timing fidelity the instant-fire tests lacked."""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        loop.exec_()
        QtWidgets.QApplication.processEvents()

    def test_both_button_chord_final_release_fires_and_hides(self):
        """Hold L+R, drag onto the leaf, release the last button (all up):
        the leaf's slot must run exactly once and the menu must hide.

        Before the fix this returned without firing — the dead click."""
        consumed = self._release_on_child(
            self.leaf, QtCore.Qt.RightButton, QtCore.Qt.NoButton
        )
        self.assertTrue(consumed, "the grabbed-child release was not consumed")
        self.assertEqual(
            self.fired,
            ["tb000"],
            "both-buttons-held drag-release did not register a click (dead click)",
        )
        self.assertIsNone(
            self.mm._current_widget, "the marking menu did not hide after the click"
        )

    def test_single_button_release_over_grabbed_leaf_fires(self):
        """The single-button drag-release (grab migrated to the leaf) must also
        fire — the fix makes both paths reliable, not just the chord."""
        consumed = self._release_on_child(
            self.leaf, QtCore.Qt.LeftButton, QtCore.Qt.NoButton
        )
        self.assertTrue(consumed)
        self.assertEqual(self.fired, ["tb000"])
        self.assertIsNone(self.mm._current_widget)

    def test_both_button_partial_release_over_item_fires_immediately(self):
        """THE regression. The real both-buttons gesture: the two buttons lift a
        few ms apart, so the release arrives as two events. A release OVER AN OWNED
        ITEM fires the click IMMEDIATELY on the FIRST (partial) release — exactly
        as the proven v1.0.66 path did, with NO wait for the other held button —
        and the menu hides. The trailing release of the pair lands on the now-
        hidden menu and is swallowed by the single-shot latch (no double fire).

        The regression deferred this owned-item release through the tolerance
        window first, so the timer navigated the menu to the remaining-button menu
        (the "stays open and shifts") and the click under the cursor was lost."""
        # First (partial) release — R up, L still held — over the item: FIRES NOW.
        consumed1 = self._release_on_child(
            self.leaf, QtCore.Qt.RightButton, QtCore.Qt.LeftButton
        )
        self.assertTrue(consumed1, "the partial release over the item must be consumed")
        self.assertEqual(
            self.fired,
            ["tb000"],
            "an owned-item release must fire IMMEDIATELY on the first release "
            "(it must NOT be deferred — that was the dead-click regression)",
        )
        self.assertIsNone(
            self.mm._current_widget, "the click must hide the menu"
        )

        # Trailing (all-up) release — swallowed by the latch, no second fire.
        consumed2 = self._release_on_child(
            self.leaf, QtCore.Qt.LeftButton, QtCore.Qt.NoButton
        )
        self.assertTrue(consumed2, "the trailing release must be consumed (swallowed)")
        self.assertEqual(
            self.fired, ["tb000"], "the trailing release must NOT fire a second action"
        )

    def test_navigation_partial_release_is_deferred_not_navigated(self):
        """A partial chord release over EMPTY overlay (no owned item under it) is
        the NAVIGATION case — and only there does the tolerance defer. It must NOT
        immediately navigate to the remaining-button menu (that flickers the menu
        before the imminent both-buttons release lands)."""
        consumed = self._release_on_child(
            self.leaf,
            QtCore.Qt.RightButton,
            QtCore.Qt.LeftButton,
            widget_at=None,  # nothing owned under the release → navigation case
        )
        self.assertTrue(consumed, "the partial release must be consumed (deferred)")
        self.assertEqual(self.fired, [], "a deferred partial release must not fire")
        self.assertIs(
            self.mm._current_widget,
            self.menu,
            "the menu must stay on the chord menu (deferred), not shift/navigate",
        )

    def test_menu_grab_navigation_partial_release_is_deferred(self):
        """The menu-grab path (mouseReleaseEvent) defers a partial NAVIGATION
        release (over empty overlay) exactly like the child-grab path — same
        gesture, same result regardless of which object holds the grab."""
        self._release_on_menu(
            QtCore.Qt.RightButton, QtCore.Qt.LeftButton, widget_at=None
        )
        self.assertEqual(self.fired, [], "menu-grab partial release must not fire")
        self.assertEqual(
            self.mm.sb.current_ui.objectName(),
            "maya",
            "deferred partial release must stay on the chord menu (no shift)",
        )

    def test_menu_grab_partial_release_over_item_fires_immediately(self):
        """The menu-grab path (Maya: the menu holds the grab) fires an owned-item
        release IMMEDIATELY on the first (partial) release — the user's exact
        scenario (release both buttons over the 'key' MenuButton). The click must
        register without waiting for the other button or the tolerance timer."""
        self._release_on_menu(
            QtCore.Qt.RightButton, QtCore.Qt.LeftButton, widget_at=self.leaf
        )
        self.assertEqual(
            self.fired,
            ["tb000"],
            "menu-grab owned-item release must fire on the first (partial) release",
        )
        self.assertIsNone(
            self.mm._current_widget, "the click must hide the menu, not shift it"
        )

    def test_owned_item_fires_at_event_position_even_when_cursor_drifted(self):
        """Under a pumped host loop the cursor can drift off the item between the
        physical release and this handler. Dispatch must resolve the item at the
        RELEASE EVENT position (not the live cursor / underMouse), so the click
        still fires AND _handle_widget_action receives the event position — the
        same drift-immunity mouseReleaseEvent has.

        The event lands on the leaf (10,10) while the live cursor has drifted to
        (900,900) over nothing and underMouse() reads False.
        """
        captured = {}
        orig = self.mm._handle_widget_action

        def spy(widget, global_pos=None):
            captured["pos"] = global_pos
            return orig(widget, global_pos)

        self.mm._handle_widget_action = spy
        with mock.patch.object(
            QtGui.QCursor, "pos", return_value=QtCore.QPoint(900, 900)
        ):
            consumed = self._release_on_child(
                self.leaf,
                QtCore.Qt.LeftButton,
                QtCore.Qt.NoButton,
                under_mouse=False,
                global_pos=(10, 10),
            )
        self.assertTrue(consumed, "drifted-cursor release dropped the click")
        self.assertEqual(self.fired, ["tb000"])
        self.assertEqual(
            captured.get("pos"),
            QtCore.QPoint(10, 10),
            "dispatch used the drifted live cursor, not the release event position",
        )

    def test_unowned_release_with_cursor_off_is_forwarded(self):
        """When the release is not over an owned menu item and the cursor has
        moved off the grabbed child, the event is forwarded to the child's own
        handler (the original delegate behavior) — no menu dispatch."""
        forwarded = []
        self.leaf.mouseReleaseEvent = lambda e: forwarded.append(e)
        consumed = self._release_on_child(
            self.leaf,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoButton,
            under_mouse=False,
            widget_at=None,  # nothing owned under the release position
        )
        self.assertFalse(consumed)
        self.assertEqual(len(forwarded), 1, "release was not forwarded to the child")
        self.assertEqual(self.fired, [])

    def test_release_over_unowned_widget_does_not_fire(self):
        """A grabbed child that is not part of the current menu must not be
        dispatched as a menu item."""
        stray = QtWidgets.QPushButton("stray")  # no .ui, not owned by the menu
        self.track_widget(stray)
        stray_fired = []
        stray.clicked.connect(lambda *a: stray_fired.append(1))
        consumed = self._release_on_child(
            stray, QtCore.Qt.LeftButton, QtCore.Qt.NoButton
        )
        self.assertFalse(consumed)
        self.assertEqual(stray_fired, [])

    def test_chord_release_dispatches_once_on_nav_button(self):
        """A chord release over a NAV button (the 'key' case: dispatch navigates
        to a submenu and does NOT hide the menu) dispatches EXACTLY ONCE — on the
        FIRST (partial) release — and the single-shot latch swallows the trailing
        release so it cannot re-navigate the submenu the first release opened."""
        calls = []

        # A nav-style action: dispatches (returns True) but does NOT hide.
        def nav_action(widget, global_pos=None):
            calls.append(widget)
            return True

        self.mm._handle_widget_action = nav_action

        # First (partial) release over the nav item → dispatch immediately.
        self._release_on_child(self.leaf, QtCore.Qt.RightButton, QtCore.Qt.LeftButton)
        self.assertEqual(len(calls), 1, "the nav item must dispatch on the first release")

        # Trailing release → swallowed by the latch (no second navigate).
        c2 = self._release_on_child(
            self.leaf, QtCore.Qt.LeftButton, QtCore.Qt.NoButton
        )
        self.assertTrue(c2, "the trailing release must be consumed")
        self.assertEqual(
            len(calls), 1, "the chord release must dispatch exactly one action"
        )

    def test_maya_final_release_recovers_item_at_live_cursor(self):
        """Regression (Maya, both-button release): the menu 'stays open and
        shifts' while the MenuButton under the cursor fails to register a click.

        Cause: a Maya chord release's ``event.globalPos()`` can resolve to the
        menu BACKGROUND instead of the item the pointer is over, so the dispatch
        was lost and the release fell through to ``_sync_menu_to_state`` (the
        shift). On the FINAL all-up release, the live-cursor fallback (the position
        v1.0.66 used before the hit-test moved to ``event.globalPos()``) must
        recover the item and fire it instead of re-syncing the menu.
        """
        probes = {"n": 0}

        def widget_at(*_a, **_k):
            probes["n"] += 1
            # 1st probe = event.globalPos() -> menu background (current_ui,
            # excluded); 2nd probe = live cursor -> the item the pointer is over.
            return self.menu if probes["n"] == 1 else self.leaf

        # Final all-up release (buttons==0): the dispatch path that must recover.
        self._release_on_menu(
            QtCore.Qt.LeftButton, QtCore.Qt.NoButton, widget_at=widget_at
        )
        self.assertEqual(
            self.fired,
            ["tb000"],
            "the item under the live cursor must fire (it was lost when the event "
            "position resolved to the menu background and the menu re-synced)",
        )
        self.assertIsNone(
            self.mm._current_widget,
            "the click must hide the menu, not leave it open + shifted",
        )

    def test_real_timing_both_released_within_tolerance_no_switch(self):
        """END-TO-END with REAL timing (a real event loop, not instant fire — the
        fidelity the earlier tests lacked), NAVIGATION case (release over empty
        overlay): release one button, wait LESS than the tolerance, then release
        the other → the menu must NOT flicker through the remaining-button
        ('cameras') menu. This is the imperfect both-buttons release the tolerance
        exists to absorb."""
        # Partial release over empty — deferred; no switch during the window.
        self._release_on_menu(
            QtCore.Qt.RightButton, QtCore.Qt.LeftButton, widget_at=None
        )
        self._wait(int(self.mm.CHORD_RELEASE_TOLERANCE_MS * 0.4))
        self.assertEqual(
            self.mm.sb.current_ui.objectName(),
            "maya",
            "menu must not switch to the one-button menu inside the window",
        )
        # Final all-up release within the tolerance → settles to the base (F12)
        # menu; crucially it never flickered to the one-button 'cameras' menu.
        self._release_on_menu(
            QtCore.Qt.LeftButton, QtCore.Qt.NoButton, widget_at=None
        )
        self.assertNotEqual(
            self.mm.sb.current_ui.objectName(),
            "cameras",
            "a both-buttons release within tolerance must not flicker through the "
            "one-button (cameras) menu",
        )

    def test_real_timing_held_past_tolerance_navigates(self):
        """END-TO-END with REAL timing: release one button and HOLD the other past
        the tolerance → the menu SWITCHES to the remaining-button menu (intentional
        chord switch), NOT a select. The tolerance is what distinguishes this from
        an imperfect both-buttons release."""
        # Partial release over empty (no owned item) — deferred.
        self._release_on_menu(
            QtCore.Qt.RightButton, QtCore.Qt.LeftButton, widget_at=None
        )
        self.assertEqual(
            self.mm.sb.current_ui.objectName(),
            "maya",
            "deferred — must not switch before the tolerance expires",
        )
        # Hold past the tolerance → the timer fires → switch to the L menu.
        self._wait(int(self.mm.CHORD_RELEASE_TOLERANCE_MS * 1.8))
        self.assertEqual(
            self.mm.sb.current_ui.objectName(),
            "cameras",
            "holding L past the tolerance must switch to the L (cameras) menu",
        )

    def test_press_rearms_dispatch_latch(self):
        """The single-shot latch is per-gesture: a fresh mouse press re-arms it so
        the NEXT click dispatches. (It must NOT re-arm on a mid-gesture submenu
        show, or the trailing release would slip through — hence press, not show.)
        """
        self.mm._action_dispatched = True
        press = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=None
        ):
            self.mm.mousePressEvent(press)
        self.assertFalse(
            self.mm._action_dispatched, "a new press must re-arm the dispatch latch"
        )

    def test_release_resolves_via_childAt_when_widgetAt_misses(self):
        """THE live root cause. ``QApplication.widgetAt`` returns None over the
        marking menu's translucent (``WA_TranslucentBackground``) overlay even
        when the cursor is squarely over a button — so the release hit-test missed
        and the gesture navigated away instead of clicking. The geometric
        ``current_ui.childAt`` fallback resolves the item widgetAt couldn't.

        Confirmed live in Maya: at a cursor inside a button's rect, widgetAt
        returned None while childAt returned the button.
        """
        # widgetAt misses (None — the translucent-overlay behavior); childAt finds
        # the owned leaf by geometry.
        with mock.patch.object(self.menu, "childAt", return_value=self.leaf):
            self._release_on_menu(
                QtCore.Qt.LeftButton, QtCore.Qt.NoButton, widget_at=None
            )
        self.assertEqual(
            self.fired,
            ["tb000"],
            "the childAt geometric fallback must dispatch the item widgetAt missed",
        )
        self.assertIsNone(
            self.mm._current_widget, "the recovered click must hide the menu"
        )

    def test_press_classified_as_item_via_childAt_when_widgetAt_misses(self):
        """``_is_menu_item_press`` must use the SAME geometric fallback: a lone
        press over a menu item whose widgetAt misses (translucent overlay) must
        still be recognized as a click — otherwise it is mis-resolved as a chord
        and ``_sync_menu_to_state`` navigates away (the playback-press symptom in
        the live repro)."""
        press = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=None
        ), mock.patch.object(self.menu, "childAt", return_value=self.leaf):
            result = self.mm._is_menu_item_press(press)
        self.assertTrue(
            result,
            "a press over an item must classify as a click via childAt when "
            "widgetAt misses over the translucent overlay",
        )

    def test_owned_item_at_prefers_widgetat_then_falls_back_to_childat(self):
        """``_owned_item_at`` returns the owned item from widgetAt when it hits
        (preserving logical-descendant resolution), and from childAt only when
        widgetAt misses."""
        pos = QtCore.QPoint(10, 10)
        # widgetAt hits → used directly, childAt not consulted.
        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=self.leaf
        ), mock.patch.object(self.menu, "childAt", return_value=None) as ca:
            self.assertIs(self.mm._owned_item_at(pos, self.menu), self.leaf)
            ca.assert_not_called()
        # widgetAt misses → childAt fallback.
        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=None
        ), mock.patch.object(self.menu, "childAt", return_value=self.leaf):
            self.assertIs(self.mm._owned_item_at(pos, self.menu), self.leaf)
        # neither finds an owned item → None.
        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=None
        ), mock.patch.object(self.menu, "childAt", return_value=None):
            self.assertIsNone(self.mm._owned_item_at(pos, self.menu))

    def test_activation_release_cancels_pending_chord_timer(self):
        """If the activation key is released while a partial chord release is still
        deferred, the pending decision must be dropped — a stray timeout must not
        fire a menu switch after the gesture has ended."""
        # Defer a partial NAVIGATION release (over empty) → the tolerance timer
        # is armed (an over-item partial would fire immediately instead).
        self._release_on_menu(
            QtCore.Qt.RightButton, QtCore.Qt.LeftButton, widget_at=None
        )
        self.assertTrue(
            self.mm._chord_release_timer is not None
            and self.mm._chord_release_timer.isActive(),
            "a partial release must arm the tolerance timer",
        )
        self.assertNotEqual(self.mm._chord_pending_buttons, 0)

        # Activation key released — the gesture is over.
        self.mm._on_activation_release()
        QtWidgets.QApplication.processEvents()
        self.assertFalse(
            self.mm._chord_release_timer.isActive(),
            "the tolerance timer must be cancelled on activation release",
        )
        self.assertEqual(
            self.mm._chord_pending_buttons,
            0,
            "the pending chord-release decision must be cleared",
        )


class MarkingMenuHideRelinquishesControl(QtBaseTestCase):
    """``hide()`` must end the gesture and fully release mouse control.

    Regression: a window launched from a leaf goes through ``hide()`` then the
    leaf's slot — NOT ``_show_window`` — so ``_activation_key_held`` (cleared only
    on the physical key release and in ``_show_window``) stayed set when the
    key-release was missed (focus jumps to the launched window). The hidden menu's
    re-grab guards (``mousePressEvent`` / ``_do_pending_hide``) then kept/re-took
    the mouse grab and the launched window was input-dead until the user tapped
    the activation key again — which ran this same cleanup via
    ``_on_activation_release``. ``hide()`` also released a grab only when
    ``mouseGrabber() is self``, missing a grab ``MouseTracking`` migrated onto a
    leaf button.
    """

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

    def test_hide_ends_gesture_and_releases_self_grab(self):
        # The live state after a chord launch with the key still held.
        self.mm._activation_key_held = True
        spy = mock.MagicMock()
        self.mm.releaseMouse = spy
        try:
            with mock.patch.object(
                QtWidgets.QWidget, "mouseGrabber", return_value=self.mm
            ):
                self.mm.hide()
        finally:
            del self.mm.releaseMouse
        self.assertFalse(
            self.mm._activation_key_held,
            "hide() must end the gesture so the re-grab guards can't re-acquire "
            "the mouse once the menu is hidden",
        )
        # hide() releases, and the hideEvent safety net releases again (idempotent
        # in reality — the first release clears the grabber — but our static
        # mouseGrabber mock keeps reporting self, so just assert it was released).
        self.assertTrue(spy.called, "hide() must release the menu's own grab")

    def test_hideevent_safety_net_ends_gesture(self):
        # A hide that bypasses hide() (parent hide / setVisible(False)) still
        # delivers a hideEvent; the safety net must END THE GESTURE, not only
        # release the grab — otherwise the flag stays set and a re-grab guard can
        # re-acquire the mouse on a later stray press.
        self.mm._activation_key_held = True
        self.mm.hideEvent(QtGui.QHideEvent())
        self.assertFalse(
            self.mm._activation_key_held,
            "hideEvent must clear _activation_key_held, not just release the grab",
        )

    def test_release_input_grab_releases_a_child_button_grab(self):
        # MouseTracking migrates the grab onto the leaf under the cursor; that
        # child is a descendant of the menu, so the release must reach it.
        child = QtWidgets.QPushButton(self.mm)
        self.track_widget(child)
        spy = mock.MagicMock()
        child.releaseMouse = spy
        try:
            with mock.patch.object(
                QtWidgets.QWidget, "mouseGrabber", return_value=child
            ):
                self.mm._release_input_grab()
        finally:
            del child.releaseMouse
        spy.assert_called_once()

    def test_release_input_grab_ignores_an_unrelated_grabber(self):
        other = QtWidgets.QWidget()
        self.track_widget(other)
        spy = mock.MagicMock()
        other.releaseMouse = spy
        try:
            with mock.patch.object(
                QtWidgets.QWidget, "mouseGrabber", return_value=other
            ):
                self.mm._release_input_grab()
        finally:
            del other.releaseMouse
        spy.assert_not_called()

    def test_release_input_grab_handles_no_grabber(self):
        with mock.patch.object(
            QtWidgets.QWidget, "mouseGrabber", return_value=None
        ):
            self.mm._release_input_grab()  # must not raise


class MarkingMenuIgnoresPopupMenuChildren(QtBaseTestCase):
    """A control shown inside an interactive ``Menu`` popup (an option-box
    dropdown) must NOT be driven by the gesture child-handlers.

    Live root cause (verified by instrumenting a real Maya): the option box
    displays real start/submenu slot widgets inside a popup ``Menu``, so they
    carry this menu's ``child_event_filter``. Routing their release through
    ``_handle_menu_item_release`` swallowed it — ``_action_dispatched`` is left
    stuck ``True`` by the launching click (a popup press never resets it), so the
    latch returned ``True`` (consumed) and the checkbox never toggled / the
    combobox never selected. (Re-opening the marking menu ran ``_on_activation_press``
    which cleared the latch — the user's "fix".) The gate skips such popup-``Menu``
    children so their release reaches their own handler. Distinct from
    ExpandableList sublist ToolTips, which are gesture surfaces (not ``Menu``).
    """

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
        # A live start/submenu so the owned-item dispatch path would otherwise
        # engage on the release.
        self.mm.sb.current_ui = self.mm.sb.get_ui("maya")

    def _popup_with_checkbox(self, name):
        from uitk.widgets.menu import Menu

        popup = self.track_widget(Menu(name=name, parent=self.parent))
        popup.add("QCheckBox", setText="cb")
        popup._setup_as_popup()  # Qt.Tool window, like the real option-box menu
        return popup, popup.findChild(QtWidgets.QCheckBox)

    def _release(self, w):
        ev = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(5, 5),
            QtCore.QPointF(5, 5),
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoButton,
            QtCore.Qt.NoModifier,
        )
        return self.mm.child_mouseButtonReleaseEvent(w, ev)

    def test_release_on_popup_menu_child_not_swallowed_by_stuck_latch(self):
        _popup, cb = self._popup_with_checkbox("opt_menu")
        # The stuck-latch state left by the launching click.
        self.mm._action_dispatched = True

        # Force the owned-item resolution so that WITHOUT the gate the release
        # would reach _handle_menu_item_release, whose stuck _action_dispatched
        # latch returns True (swallow). The gate must short-circuit before that.
        with mock.patch.object(
            self.mm, "_resolve_release_target", return_value=(cb, QtCore.QPoint(5, 5))
        ):
            consumed = self._release(cb)

        self.assertFalse(
            consumed,
            "a popup-Menu child's release must propagate to the widget, not be "
            "swallowed by the stale _action_dispatched latch",
        )

    def test_is_popup_menu_child_only_true_inside_a_menu_window(self):
        _popup, cb_in_menu = self._popup_with_checkbox("opt_menu2")
        cb_on_mm = self.track_widget(QtWidgets.QCheckBox(self.mm))

        self.assertTrue(
            self.mm._is_popup_menu_child(cb_in_menu),
            "a control whose top-level window is a Menu is a popup child",
        )
        self.assertFalse(
            self.mm._is_popup_menu_child(cb_on_mm),
            "a control on the marking menu itself is a real gesture item",
        )


if __name__ == "__main__":
    unittest.main()
