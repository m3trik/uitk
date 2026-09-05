# !/usr/bin/python
# coding=utf-8
"""Unit tests for ``uitk.managers.cursor_manager``.

The override-cursor suites (stack primitives, ``OverrideCursorGuard``, the
modal suspension) moved here from ``test_switchboard.py`` when the cursor
policy moved out of the switchboard; the dialog-level tests that exercise
them through ``Switchboard`` stayed there.

Run standalone: python -m test.test_cursor_manager
"""

import gc
import unittest
import weakref

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore, QtGui

from uitk.managers.cursor_manager import (
    CursorManager,
    OverrideCursorGuard,
    _ModalSuspendFilter,
)


def _shapes():
    """The whole override stack, top-first, left exactly as it was."""
    qapp = QtWidgets.QApplication.instance()
    saved = CursorManager.pop_stack(qapp)
    for cursor in reversed(saved):
        qapp.setOverrideCursor(cursor)
    return [c.shape() for c in saved]


class _CursorStackTestCase(QtBaseTestCase):
    """Every override-stack test starts and ends with an empty stack."""

    def setUp(self):
        super().setUp()
        CursorManager.drain()
        self.app = QtWidgets.QApplication.instance()

    def tearDown(self):
        CursorManager.drain()
        super().tearDown()


# =============================================================================
# Stack primitives
# =============================================================================
class TestStackPrimitives(_CursorStackTestCase):
    """``pop_stack`` / ``push_stack`` / ``suspend`` / ``drain`` / ``release``."""

    def test_pop_returns_top_first_and_push_restores_the_order(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.BusyCursor))
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        saved = CursorManager.pop_stack(self.app)
        self.assertEqual(
            [c.shape() for c in saved], [QtCore.Qt.WaitCursor, QtCore.Qt.BusyCursor]
        )
        self.assertIsNone(self.app.overrideCursor())
        CursorManager.push_stack(saved, self.app)
        self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor, QtCore.Qt.BusyCursor])

    def test_suspend_is_a_noop_without_an_active_override(self):
        with CursorManager.suspend():
            self.assertIsNone(self.app.overrideCursor())
        self.assertIsNone(self.app.overrideCursor())

    def test_suspend_clears_for_the_block_and_restores_after(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        with CursorManager.suspend():
            self.assertIsNone(
                self.app.overrideCursor(), "busy cursor not suspended for the dialog"
            )
        self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor])

    def test_suspend_restores_the_full_stack_in_order(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.BusyCursor))
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        with CursorManager.suspend():
            self.assertIsNone(self.app.overrideCursor())
        self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor, QtCore.Qt.BusyCursor])

    def test_suspend_restores_even_on_exception(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        with self.assertRaises(ValueError):
            with CursorManager.suspend():
                raise ValueError("boom")
        self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor])

    def test_drain_clears_the_whole_stack_and_is_idempotent(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.BusyCursor))
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        CursorManager.drain()
        self.assertIsNone(self.app.overrideCursor(), "override stack not drained")
        CursorManager.drain()
        self.assertIsNone(self.app.overrideCursor())

    def test_release_pops_its_own_shape_when_on_top(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self.assertTrue(CursorManager.release(QtCore.Qt.WaitCursor, self.app))
        self.assertIsNone(self.app.overrideCursor())

    def test_release_removes_a_buried_entry_without_popping_the_stranger(self):
        """The defect in the raw pair: ``restoreOverrideCursor`` pops the top."""
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))  # stranger
        self.assertTrue(CursorManager.release(QtCore.Qt.WaitCursor, self.app))
        self.assertEqual(
            _shapes(),
            [QtCore.Qt.CrossCursor],
            "release must take OUR entry, not whatever sits on top",
        )

    def test_release_removes_exactly_one_entry_of_the_shape(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))
        CursorManager.release(QtCore.Qt.WaitCursor, self.app)
        self.assertEqual(_shapes(), [QtCore.Qt.CrossCursor, QtCore.Qt.WaitCursor])

    def test_release_reports_false_and_changes_nothing_when_none_left(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))
        self.assertFalse(CursorManager.release(QtCore.Qt.WaitCursor, self.app))
        self.assertEqual(_shapes(), [QtCore.Qt.CrossCursor])
        CursorManager.drain()
        self.assertFalse(CursorManager.release(QtCore.Qt.WaitCursor, self.app))


# =============================================================================
# busy() — the bounded scope
# =============================================================================
class TestBusyScope(_CursorStackTestCase):
    """``CursorManager.busy`` owns its entry: pushed on entry, removed on exit
    wherever it sits, yielding to a modal in between."""

    def test_pushes_for_the_block_and_removes_its_entry_after(self):
        with CursorManager.busy():
            self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor])
        self.assertIsNone(self.app.overrideCursor())

    def test_custom_shape(self):
        with CursorManager.busy(QtCore.Qt.BusyCursor):
            self.assertEqual(_shapes(), [QtCore.Qt.BusyCursor])
        self.assertIsNone(self.app.overrideCursor())

    def test_removes_its_own_entry_even_when_buried(self):
        """A stranger pushed on top of us survives our exit untouched."""
        with CursorManager.busy():
            self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))
        self.assertEqual(
            _shapes(),
            [QtCore.Qt.CrossCursor],
            "the scope popped the stranger's cursor instead of its own",
        )

    def test_nested_scopes_balance(self):
        with CursorManager.busy():
            with CursorManager.busy():
                self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor] * 2)
            self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor])
        self.assertIsNone(self.app.overrideCursor())

    def test_is_exception_safe(self):
        with self.assertRaises(ValueError):
            with CursorManager.busy():
                raise ValueError("boom")
        self.assertIsNone(self.app.overrideCursor())

    def test_a_drain_inside_the_scope_leaves_nothing_to_remove(self):
        """A non-modal viewer opened in the scope cancels the busy cursor; the
        scope's exit must then remove nothing — not a later stranger."""
        with CursorManager.busy():
            CursorManager.drain()
            self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))
        self.assertEqual(_shapes(), [QtCore.Qt.CrossCursor])

    def test_yields_to_a_modal_block_and_resumes_after(self):
        with CursorManager.busy():
            QtCore.QCoreApplication.sendEvent(
                self.app, QtCore.QEvent(QtCore.QEvent.WindowBlocked)
            )
            self.assertIsNone(
                self.app.overrideCursor(), "busy cursor not suspended for the modal"
            )
            QtCore.QCoreApplication.sendEvent(
                self.app, QtCore.QEvent(QtCore.QEvent.WindowUnblocked)
            )
            self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor])
        self.assertIsNone(self.app.overrideCursor())

    def test_modal_suspension_can_be_declined(self):
        with CursorManager.busy(suspend_for_modals=False):
            QtCore.QCoreApplication.sendEvent(
                self.app, QtCore.QEvent(QtCore.QEvent.WindowBlocked)
            )
            self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor])
            QtCore.QCoreApplication.sendEvent(
                self.app, QtCore.QEvent(QtCore.QEvent.WindowUnblocked)
            )
        self.assertIsNone(self.app.overrideCursor())


# =============================================================================
# Modal suspension filter
# =============================================================================
class TestModalSuspendFilter(_CursorStackTestCase):
    """The busy cursor must yield to a native modal dialog.

    Qt posts ``WindowBlocked`` / ``WindowUnblocked`` when a modal blocks /
    releases the app (native Maya ``cmds.fileDialog2``, OS pickers included);
    the filter suspends the override for that span so the dialog shows
    natural cursors, then restores it for the post-dialog work. Driven with
    synthetic events — real modal block/unblock is unreliable headless.
    """

    def setUp(self):
        super().setUp()
        self.filt = _ModalSuspendFilter(self.app)

    def _send(self, etype):
        self.filt.eventFilter(None, QtCore.QEvent(etype))

    def test_block_suspends_unblock_restores(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self._send(QtCore.QEvent.WindowBlocked)
        self.assertIsNone(
            self.app.overrideCursor(), "busy cursor not suspended for the modal"
        )
        self._send(QtCore.QEvent.WindowUnblocked)
        self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor])

    def test_nested_modals_only_outer_pair_toggles(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self._send(QtCore.QEvent.WindowBlocked)  # outer
        self._send(QtCore.QEvent.WindowBlocked)  # inner
        self.assertIsNone(self.app.overrideCursor())
        self._send(QtCore.QEvent.WindowUnblocked)  # inner closes — stay suspended
        self.assertIsNone(self.app.overrideCursor(), "inner unblock restored too early")
        self._send(QtCore.QEvent.WindowUnblocked)  # outer closes — restore
        self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor])

    def test_restores_full_stack_in_order(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.BusyCursor))
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self._send(QtCore.QEvent.WindowBlocked)
        self.assertIsNone(self.app.overrideCursor())
        self._send(QtCore.QEvent.WindowUnblocked)
        self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor, QtCore.Qt.BusyCursor])

    def test_eventfilter_never_consumes(self):
        for etype in (
            QtCore.QEvent.WindowBlocked,
            QtCore.QEvent.WindowUnblocked,
            QtCore.QEvent.Show,
        ):
            self.assertFalse(self.filt.eventFilter(None, QtCore.QEvent(etype)))

    def test_cleanup_rebalances_dangling_suspend(self):
        """If a block never gets its unblock, cleanup restores the stack."""
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self._send(QtCore.QEvent.WindowBlocked)
        self.assertIsNone(self.app.overrideCursor())
        self.filt.cleanup()
        self.assertEqual(_shapes(), [QtCore.Qt.WaitCursor])


# =============================================================================
# OverrideCursorGuard
# =============================================================================
class TestOverrideCursorGuard(_CursorStackTestCase):
    """An interaction-scoped override cursor must never outlive the interaction.

    Bug: the marking menu's gesture ``CrossCursor`` was a balanced
    setOverrideCursor/restoreOverrideCursor pair driven by the overlay's
    mouse-release and hide events. Whenever neither arrived — the release
    landed on a child holding the mouse grab, the window was destroyed
    instead of hidden, a modal suspension snapshot re-pushed the stack after
    the owner had let go — the cross cursor was stranded over the whole
    application. ``OverrideCursorGuard`` replaces the bookkeeping with an
    enforced invariant. Fixed: 2026-08-06
    """

    # A shape nothing else in the process pushes — the guard's exclusivity
    # contract, honored by the test itself.
    SHAPE = QtCore.Qt.WhatsThisCursor

    def setUp(self):
        super().setUp()
        self.live = True
        self.guard = OverrideCursorGuard(
            self.SHAPE, is_live=lambda: self.live, interval_ms=10
        )

    def tearDown(self):
        self.guard.clear()
        super().tearDown()

    def test_apply_and_clear_are_idempotent(self):
        self.guard.apply()
        self.guard.apply()
        self.assertEqual(_shapes(), [self.SHAPE], "double apply stacked twice")
        self.guard.clear()
        self.guard.clear()
        self.assertIsNone(self.app.overrideCursor())

    def test_watchdog_clears_when_predicate_dies(self):
        """The core guarantee: no event has to arrive for the cursor to go."""
        self.guard.apply()
        self.live = False
        self.guard._on_tick()
        self.assertIsNone(self.app.overrideCursor(), "watchdog left the override")
        self.assertFalse(self.guard.holding)

    def test_watchdog_keeps_cursor_while_live(self):
        self.guard.apply()
        self.guard._on_tick()
        self.assertEqual(_shapes(), [self.SHAPE], "watchdog fired too eagerly")

    def test_raising_predicate_counts_as_dead(self):
        """A deleted C++ owner raises RuntimeError — release, never strand."""

        def boom():
            raise RuntimeError("wrapped C/C++ object has been deleted")

        self.guard._is_live = boom
        self.guard.apply()
        self.guard._on_tick()
        self.assertIsNone(self.app.overrideCursor())

    def test_clear_removes_a_buried_entry_without_popping_the_stranger(self):
        """A slot's busy cursor pushed on top must survive our release."""
        self.guard.apply()
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self.guard.clear()
        self.assertEqual(
            _shapes(),
            [QtCore.Qt.WaitCursor],
            "clear must remove OUR entry, not whatever sits on top",
        )

    def test_apply_reconciles_a_leaked_entry(self):
        """A cursor stranded by an earlier interaction is dropped, not stacked."""
        self.app.setOverrideCursor(QtGui.QCursor(self.SHAPE))  # the leak
        self.guard.apply()
        self.assertEqual(_shapes(), [self.SHAPE])
        self.guard.clear()
        self.assertIsNone(self.app.overrideCursor(), "leaked entry survived")

    def test_suspension_does_not_resurrect_a_released_cursor(self):
        """The modal-dialog snapshot/restore path (the re-push leak).

        A slot opens a modal dialog while the gesture cursor is up: the whole
        stack is popped for the dialog's lifetime. The gesture ends *during*
        that dialog, so by the time the stack is restored the guard has
        released — its entry must not come back, since nothing would ever pop
        it again.
        """
        self.guard.apply()
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))

        saved = CursorManager.pop_stack(self.app)
        self.guard.clear()  # gesture ends while the stack is suspended
        CursorManager.push_stack(saved, self.app)

        self.assertEqual(
            _shapes(),
            [QtCore.Qt.WaitCursor],
            "the released gesture cursor was resurrected by the restore",
        )

    def test_suspension_restores_a_still_held_cursor(self):
        """The same path with the gesture still live must be untouched."""
        self.guard.apply()
        saved = CursorManager.pop_stack(self.app)
        self.assertIsNone(self.app.overrideCursor())
        CursorManager.push_stack(saved, self.app)
        self.assertEqual(_shapes(), [self.SHAPE])

    def test_drain_drops_ownership_so_apply_re_asserts(self):
        """A drain takes our entry too — the guard must not keep claiming it.

        Left claiming, ``apply`` short-circuits and the rest of the
        interaction runs with no cursor at all.
        """
        self.guard.apply()
        CursorManager.drain()  # e.g. a slot opening a non-modal viewer
        self.assertFalse(self.guard.holding, "guard still claims a drained entry")

        self.guard.apply()
        self.assertEqual(_shapes(), [self.SHAPE], "cursor never came back")

    def test_unclaimed_shapes_are_never_filtered(self):
        """reconcile/restore only ever touch shapes a guard claims."""
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.BusyCursor))
        OverrideCursorGuard.reconcile()
        self.assertEqual(_shapes(), [QtCore.Qt.BusyCursor])

    def test_busy_scope_survives_a_guard_pushed_on_top(self):
        """The two owned forms compose: each removes only its own entry."""
        with CursorManager.busy():
            self.guard.apply()
            self.assertEqual(_shapes(), [self.SHAPE, QtCore.Qt.WaitCursor])
        self.assertEqual(_shapes(), [self.SHAPE], "busy exit took the guard's")
        self.guard.clear()
        self.assertIsNone(self.app.overrideCursor())


# =============================================================================
# push / pop — gesture cursors on widgets and graphics items
# =============================================================================
class TestGestureCursors(QtBaseTestCase):
    """``pop`` restores exactly what was there: an explicit cursor, or none.

    ``target.cursor()`` reports the inherited arrow for a target with no
    cursor of its own, so a restore built on it pins an explicit arrow on a
    widget that used to inherit (the table scrub's former restore).

    The targets are CHILD widgets, as every real call site's are (a header in
    a window, a table in a panel): only a child can inherit a cursor. Qt leaves
    ``WA_SetCursor`` set on a top-level window after ``unsetCursor()`` — the
    window has nothing to inherit from, so the distinction is moot there and
    the effective cursor is what matters (see the last test).
    """

    def _child(self):
        parent = self.track_widget(QtWidgets.QWidget())
        return QtWidgets.QWidget(parent)

    def test_pop_returns_an_inheriting_widget_to_inheriting(self):
        w = self._child()
        self.assertFalse(CursorManager.has_explicit_cursor(w))

        CursorManager.push(w, QtCore.Qt.SizeHorCursor)
        self.assertEqual(w.cursor().shape(), QtCore.Qt.SizeHorCursor)
        self.assertTrue(CursorManager.has_explicit_cursor(w))

        self.assertTrue(CursorManager.pop(w))
        self.assertFalse(
            CursorManager.has_explicit_cursor(w),
            "a widget that inherited its cursor must inherit it again",
        )

    def test_pop_restores_an_explicit_cursor(self):
        w = self._child()
        w.setCursor(QtCore.Qt.OpenHandCursor)

        CursorManager.push(w, QtCore.Qt.ClosedHandCursor)
        self.assertEqual(w.cursor().shape(), QtCore.Qt.ClosedHandCursor)

        CursorManager.pop(w)
        self.assertEqual(w.cursor().shape(), QtCore.Qt.OpenHandCursor)
        self.assertTrue(CursorManager.has_explicit_cursor(w))

    def test_pushes_nest(self):
        w = self._child()
        w.setCursor(QtCore.Qt.OpenHandCursor)
        CursorManager.push(w, QtCore.Qt.ClosedHandCursor)
        CursorManager.push(w, QtCore.Qt.ForbiddenCursor)
        self.assertEqual(w.cursor().shape(), QtCore.Qt.ForbiddenCursor)
        CursorManager.pop(w)
        self.assertEqual(w.cursor().shape(), QtCore.Qt.ClosedHandCursor)
        CursorManager.pop(w)
        self.assertEqual(w.cursor().shape(), QtCore.Qt.OpenHandCursor)

    def test_in_gesture_changes_do_not_disturb_the_restore(self):
        """Variations during the gesture are plain setCursor calls."""
        w = self._child()
        CursorManager.push(w, QtCore.Qt.ClosedHandCursor)
        w.setCursor(QtCore.Qt.ForbiddenCursor)  # pointer left the window
        w.setCursor(QtCore.Qt.ClosedHandCursor)  # and came back
        CursorManager.pop(w)
        self.assertFalse(CursorManager.has_explicit_cursor(w))

    def test_pop_without_a_push_is_a_reported_noop(self):
        w = self._child()
        w.setCursor(QtCore.Qt.OpenHandCursor)
        self.assertFalse(CursorManager.pop(w))
        self.assertEqual(w.cursor().shape(), QtCore.Qt.OpenHandCursor)

    def test_accepts_a_qcursor_as_the_shape(self):
        w = self._child()
        CursorManager.push(w, QtGui.QCursor(QtCore.Qt.SizeAllCursor))
        self.assertEqual(w.cursor().shape(), QtCore.Qt.SizeAllCursor)
        CursorManager.pop(w)

    def test_top_level_window_returns_to_the_arrow(self):
        """A window cannot inherit; pop leaves it on the default arrow."""
        window = self.track_widget(QtWidgets.QWidget())
        CursorManager.push(window, QtCore.Qt.SizeAllCursor)
        self.assertEqual(window.cursor().shape(), QtCore.Qt.SizeAllCursor)
        CursorManager.pop(window)
        self.assertEqual(window.cursor().shape(), QtCore.Qt.ArrowCursor)

    def test_graphics_item_round_trip(self):
        """The same pair works on a QGraphicsItem (``hasCursor``)."""
        scene = QtWidgets.QGraphicsScene()
        item = scene.addRect(0, 0, 10, 10)
        self.assertFalse(item.hasCursor())

        CursorManager.push(item, QtCore.Qt.ClosedHandCursor)
        self.assertTrue(item.hasCursor())
        self.assertEqual(item.cursor().shape(), QtCore.Qt.ClosedHandCursor)
        self.assertTrue(CursorManager.pop(item))
        self.assertFalse(item.hasCursor(), "an item without a cursor gets none back")

        item.setCursor(QtCore.Qt.OpenHandCursor)  # the hover affordance
        CursorManager.push(item, QtCore.Qt.ClosedHandCursor)
        CursorManager.pop(item)
        self.assertEqual(item.cursor().shape(), QtCore.Qt.OpenHandCursor)
        scene.clear()

    def test_bookkeeping_does_not_keep_the_target_alive(self):
        w = QtWidgets.QWidget()
        ref = weakref.ref(w)
        CursorManager.push(w, QtCore.Qt.SizeHorCursor)
        del w
        gc.collect()
        self.assertIsNone(ref(), "a pushed target must not be pinned by the manager")


# =============================================================================
# heal_hover
# =============================================================================
class TestHealHover(QtBaseTestCase):
    """A hover move over a widget Qt says is not under the mouse re-runs the
    enter dispatch; a consistent state, a held button or a live grab do not."""

    def _shown(self):
        window = self.track_widget(QtWidgets.QWidget())
        window.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        layout = QtWidgets.QVBoxLayout(window)
        child = QtWidgets.QLabel("hover me", parent=window)
        child.setCursor(QtCore.Qt.OpenHandCursor)
        layout.addWidget(child)
        window.show()
        QtWidgets.QApplication.processEvents()
        return window, child

    def test_heals_a_widget_qt_thinks_is_not_under_the_mouse(self):
        window, child = self._shown()
        self.assertFalse(child.underMouse())  # never entered — the stale shape
        pos = child.mapToGlobal(child.rect().center())
        self.assertTrue(CursorManager.heal_hover(child, pos))
        self.assertTrue(child.underMouse(), "the re-dispatched Enter never landed")
        self.assertTrue(window.underMouse(), "Enter must run up the chain too")

    def test_consistent_state_is_left_alone(self):
        window, child = self._shown()
        pos = child.mapToGlobal(child.rect().center())
        CursorManager.heal_hover(child, pos)
        self.assertFalse(CursorManager.heal_hover(child, pos))

    def test_live_mouse_grab_is_qts_intent_not_a_fault(self):
        window, child = self._shown()
        grabber = self.track_widget(QtWidgets.QWidget())
        grabber.grabMouse()
        try:
            pos = child.mapToGlobal(child.rect().center())
            self.assertFalse(CursorManager.heal_hover(child, pos))
            self.assertFalse(child.underMouse())
        finally:
            grabber.releaseMouse()

    def test_unshown_widget_is_a_noop(self):
        w = self.track_widget(QtWidgets.QWidget())
        self.assertFalse(CursorManager.heal_hover(w, QtCore.QPoint(0, 0)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
