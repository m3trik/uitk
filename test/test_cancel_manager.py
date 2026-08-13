# !/usr/bin/python
# coding=utf-8
"""Tests for the cancellation stack: CancelManager/CancelProvider, the
ProgressBar's CancelScope binding, and the SlotWrapper's @Cancelable path.

Run standalone: python -m test.test_cancel_manager
"""

import unittest
from unittest.mock import MagicMock, patch

import pythontk as ptk
from qtpy import QtCore

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()


class RecordingProvider:
    """Stand-in host provider; records the bracket calls a DCC would make."""

    name = "recording"
    exclude_user_input = True
    escape_hold_seconds = 0.5

    def __init__(self, source=None):
        self.calls = []
        self.source = source
        self.pumped = 0

    def create_sources(self, scope, label=""):
        self.calls.append(("create_sources", label))
        return [self.source] if self.source else []

    def begin(self, scope, label="", rollback=False):
        self.calls.append(("begin", label, rollback))
        return "token"

    def tick(self, value=None, total=None, text=None):
        self.calls.append(("tick", value))

    def end(self, token, cancelled=False, rollback=False):
        self.calls.append(("end", token, cancelled, rollback))

    def pump(self):
        self.pumped += 1


class CancelStackTestCase(QtBaseTestCase):
    """Always restore the process-wide provider — it outlives a test."""

    def tearDown(self):
        from uitk.managers.cancel_manager import CancelManager

        CancelManager.reset()
        self.assertIsNone(ptk.CancelScope.current(), "ambient scope leaked")
        super().tearDown()

    def use_provider(self, provider):
        from uitk.managers.cancel_manager import CancelManager

        CancelManager._provider = provider  # bypass the isinstance gate
        return provider


class TestCancelManager(CancelStackTestCase):
    def test_default_provider_when_none_registered(self):
        from uitk.managers.cancel_manager import CancelManager, CancelProvider

        provider = CancelManager.provider()
        self.assertIsInstance(provider, CancelProvider)
        self.assertFalse(provider.exclude_user_input)

    def test_register_rejects_non_provider(self):
        from uitk.managers.cancel_manager import CancelManager

        with self.assertRaises(TypeError):
            CancelManager.register(object())

    def test_register_and_reset(self):
        from uitk.managers.cancel_manager import CancelManager, CancelProvider

        class HostProvider(CancelProvider):
            name = "host"

        CancelManager.register(HostProvider())
        self.assertEqual(CancelManager.provider().name, "host")
        CancelManager.reset()
        self.assertEqual(CancelManager.provider().name, "qt")

    def test_new_scope_wires_provider_sources(self):
        from uitk.managers.cancel_manager import CancelManager

        flag = {"v": False}
        self.use_provider(RecordingProvider(source=lambda: flag["v"]))

        scope = CancelManager.new_scope("job", poll_min_interval=0)
        self.assertTrue(scope.tick())
        flag["v"] = True
        self.assertFalse(scope.tick())

    def test_new_scope_survives_a_broken_provider(self):
        from uitk.managers.cancel_manager import CancelManager, CancelProvider

        class BrokenProvider(CancelProvider):
            def create_sources(self, scope, label=""):
                raise RuntimeError("host not ready")

        self.use_provider(BrokenProvider())
        scope = CancelManager.new_scope("job")
        self.assertFalse(scope.cancelled)
        scope.cancel("dialog")  # still cancellable by other means
        self.assertTrue(scope.cancelled)

    def test_bracket_stack_balances(self):
        from uitk.managers.cancel_manager import CancelProvider

        provider = CancelProvider()
        self.assertIsNone(provider.current_bracket)
        a = provider.open_bracket("a")
        b = provider.open_bracket("b")
        self.assertIs(provider.current_bracket, b)
        self.assertIs(provider.close_bracket(b), b)
        self.assertIs(provider.current_bracket, a)
        provider.close_bracket(a)
        self.assertIsNone(provider.current_bracket)

    def test_close_bracket_returns_none_for_junk_and_double_close(self):
        """Host teardown keys off this, so it must run exactly once."""
        from uitk.managers.cancel_manager import CancelProvider

        provider = CancelProvider()
        token = provider.open_bracket("a")
        self.assertIsNone(provider.close_bracket("never opened"))
        self.assertIsNone(provider.close_bracket(None))
        self.assertIs(provider.close_bracket(token), token)
        self.assertIsNone(provider.close_bracket(token), "double close must be None")

    def test_close_bracket_matches_by_identity_not_equality(self):
        """A dataclass-style bracket must not close its equal-valued sibling."""
        from uitk.managers.cancel_manager import CancelProvider

        class ValueBracket:
            def __init__(self, label):
                self.label = label

            def __eq__(self, other):
                return isinstance(other, ValueBracket) and other.label == self.label

            __hash__ = None  # like a mutable dataclass

        provider = CancelProvider()
        outer = provider.open_bracket(ValueBracket("same"))
        inner = provider.open_bracket(ValueBracket("same"))

        self.assertIs(provider.close_bracket(inner), inner)
        self.assertIs(provider.current_bracket, outer, "closed the wrong bracket")
        self.assertIs(provider.close_bracket(outer), outer)
        self.assertIsNone(provider.current_bracket)

    def test_install_registers_and_survives_failure(self):
        from uitk.managers.cancel_manager import CancelManager, CancelProvider

        class HostProvider(CancelProvider):
            name = "host"

        installed = HostProvider.install()
        self.assertIs(CancelManager.provider(), installed)

        class BrokenProvider(CancelProvider):
            def __init__(self):
                raise RuntimeError("host not ready")

        self.assertIsNone(BrokenProvider.install())

    def test_reports_attribute_to_the_concrete_providers_module(self):
        """A DCC twin's message must not be filed under uitk."""
        from uitk.managers.cancel_manager import CancelProvider

        Local = type("LocalProvider", (CancelProvider,), {})
        Local.__module__ = "somepkg.ui_utils.cancel_provider"
        with self.assertLogs("somepkg.ui_utils.cancel_provider", level="WARNING"):
            Local.report_warning("something")

    def test_default_provider_supplies_an_escape_source(self):
        """Esc must not depend on the event loop — that is when it is needed."""
        from uitk.managers.cancel_manager import CancelProvider

        sources = CancelProvider().create_sources(ptk.CancelScope("x"))
        self.assertEqual(len(sources), 1)

        with patch.object(ptk.ExecutionMonitor, "is_escape_pressed", return_value=True):
            with patch.object(
                ptk.ExecutionMonitor, "is_foreground_process", return_value=True
            ):
                probe = sources[0]
                self.assertFalse(probe(), "must require a sustained hold")
                probe._held_since -= CancelProvider.escape_hold_seconds + 1
                self.assertTrue(probe())


class TestProgressBarScope(CancelStackTestCase):
    def _bar(self):
        from uitk.widgets.progressBar import ProgressBar

        return self.track_widget(ProgressBar(auto_hide=False))

    def test_start_task_creates_a_scope(self):
        pb = self._bar()
        self.assertIsNone(pb.scope)
        pb.start_task(total=5, text="work")
        self.assertIsInstance(pb.scope, ptk.CancelScope)
        self.assertFalse(pb.is_cancelled)

    def test_start_task_adopts_the_ambient_scope(self):
        """The slot's scope and the bar's must be one object, not two."""
        pb = self._bar()
        outer = ptk.CancelScope("slot")
        with outer.activate():
            pb.start_task(total=5, text="work")
            self.assertIs(pb.scope, outer)

    def test_update_returns_false_after_scope_cancel(self):
        pb = self._bar()
        outer = ptk.CancelScope("slot")
        with outer.activate():
            pb.start_task(total=5, text="work")
            self.assertTrue(pb.update_progress(1))
            outer.cancel("dialog")
            self.assertFalse(pb.update_progress(2))
            self.assertTrue(pb.is_cancelled)

    def test_bar_cancel_flags_the_shared_scope(self):
        """Esc over the bar must stop the slot, not just the bar."""
        pb = self._bar()
        outer = ptk.CancelScope("slot")
        with outer.activate():
            pb.start_task(total=5, text="work")
            pb.cancel("escape-hold")
            self.assertTrue(outer.cancelled)
            self.assertEqual(outer.reason, "escape-hold")

    def test_cancel_before_any_task_is_not_dropped(self):
        pb = self._bar()
        pb.cancel()
        self.assertTrue(pb.is_cancelled)

    def test_start_task_resets_previous_cancellation(self):
        pb = self._bar()
        pb.start_task(total=5, text="a")
        pb.cancel()
        self.assertTrue(pb.is_cancelled)
        pb.start_task(total=5, text="b")
        self.assertFalse(pb.is_cancelled)

    def test_show_event_does_not_clear_cancellation(self):
        pb = self._bar()
        pb.start_task(total=5, text="work")
        pb.cancel()
        pb.show()
        self.assertTrue(pb.is_cancelled)

    def test_update_uses_provider_pump(self):
        provider = self.use_provider(RecordingProvider())
        pb = self._bar()
        pb.start_task(total=5, text="work")
        pb.update_progress(1)
        self.assertEqual(provider.pumped, 1)
        self.assertIn(("tick", 1), provider.calls)

    def test_pump_excludes_user_input_for_dcc_providers(self):
        """Dispatching queued input mid-slot would nest a second slot into
        half-mutated scene state."""
        from uitk.managers.cancel_manager import CancelProvider

        class DccProvider(CancelProvider):
            exclude_user_input = True

        app_instance = MagicMock()
        with patch(
            "uitk.managers.cancel_manager.QtWidgets.QApplication.instance",
            return_value=app_instance,
        ):
            DccProvider().pump()
            app_instance.processEvents.assert_called_once_with(
                QtCore.QEventLoop.ExcludeUserInputEvents
            )

            app_instance.reset_mock()
            CancelProvider().pump()
            app_instance.processEvents.assert_called_once_with()

    def test_host_label_mirrors_when_the_bar_shows_no_text(self):
        """The footer keeps the label off the bar; the host must still get it."""
        provider = self.use_provider(RecordingProvider())
        provider.tick = lambda value=None, total=None, text=None: provider.calls.append(
            ("tick", value, text)
        )
        pb = self._bar()
        pb.start_task(total=5, text="", host_label="Scanning scene")
        pb.update_progress(1)
        self.assertIn(("tick", 1, "Scanning scene"), provider.calls)

    def test_footer_passes_its_label_to_the_host(self):
        from uitk.widgets.footer import Footer

        provider = self.use_provider(RecordingProvider())
        provider.tick = lambda value=None, total=None, text=None: provider.calls.append(
            ("tick", value, text)
        )
        footer = self.track_widget(Footer())
        with footer.progress(total=3, text="Copying") as update:
            update(1)
        self.assertIn(("tick", 1, "Copying"), provider.calls)

    def test_footer_per_tick_text_reaches_the_host(self):
        """Host progress UI must not be stuck on the label the task started
        with — it is the only place a marking-menu slot's progress is visible
        once its window has closed."""
        from uitk.widgets.footer import Footer

        provider = self.use_provider(RecordingProvider())
        provider.tick = lambda value=None, total=None, text=None: provider.calls.append(
            ("tick", value, text)
        )
        footer = self.track_widget(Footer())
        with footer.progress(total=3, text="Copying") as update:
            update(1, "Copying a.fbx")
            update(2, "Copying b.fbx")
        self.assertIn(("tick", 1, "Copying a.fbx"), provider.calls)
        self.assertIn(("tick", 2, "Copying b.fbx"), provider.calls)

    def test_step_forwards_cancellation(self):
        pb = self._bar()
        pb.start_task(total=10, text="work")
        self.assertTrue(pb.step(0, 10))
        pb.cancel()
        self.assertFalse(pb.step(1, 10))


class TestFooterCancelSurvivesTheSignal(CancelStackTestCase):
    """A footer-hosted bar must not erase the cancel it just reported."""

    def test_cancelling_a_footer_bar_keeps_update_returning_false(self):
        """Regression: ``cancelled`` was wired to the finish handler.

        ``Footer._on_progress_finished`` calls ``reset()``, which drops the
        bar's scope reference -- so ``cancel()`` emitted the signal that
        immediately erased its own effect. ``is_cancelled`` went back to False
        and ``update()`` kept answering True, meaning Esc silently did nothing
        and the loop ran to completion. The cancelled task is still running
        when this fires; ``start_task`` is the reset point, not the signal.
        """
        from uitk.widgets.footer import Footer

        footer = self.track_widget(Footer())
        update = footer.start_progress(total=10, text="Working")

        self.assertTrue(update(1))
        footer.progress_bar.cancel("test")

        self.assertTrue(footer.progress_bar.is_cancelled, "cancel was erased")
        self.assertFalse(update(2), "the loop was never told to stop")


class TestSlotWrapperCancelable(CancelStackTestCase):
    """The dispatcher path: scope activation, transaction, rollback, reporting."""

    def _wrapper(self, slot):
        from uitk.switchboard.slots import SlotWrapper

        widget = self.track_widget(__import__("qtpy").QtWidgets.QWidget())
        widget.setObjectName("b000")
        sb = MagicMock()
        sb.logger = MagicMock()
        sb.active_ui = None
        sb._current_ui = None
        sb._suppress_slot_capture = True
        return SlotWrapper(slot, widget, sb), sb

    def test_plain_slot_runs_without_a_scope(self):
        def slot():
            self.assertIsNone(ptk.CancelScope.current())
            return "ran"

        wrapper, _ = self._wrapper(slot)
        self.assertEqual(wrapper(), "ran")

    def test_cancelable_slot_activates_a_scope(self):
        from uitk.switchboard.slots import Cancelable

        seen = {}

        @Cancelable(60)
        def slot():
            seen["scope"] = ptk.CancelScope.current()
            return "ran"

        wrapper, _ = self._wrapper(slot)
        self.assertEqual(wrapper(), "ran")
        self.assertIsInstance(seen["scope"], ptk.CancelScope)
        self.assertIsNone(ptk.CancelScope.current(), "scope must not leak")

    def test_a_checkpointless_slot_is_not_rolled_back(self):
        """Requested != consumed: undoing a COMPLETED run is the worst outcome.

        ``ExecutionMonitor``'s Esc detector sets the flag from its background
        thread with no cooperation from the slot. A slot that is one monolithic
        host call reaches no checkpoint, so it runs to completion with the flag
        set behind it -- and the dispatcher, reading ``scope.cancelled``, then
        reported it cancelled and handed ``rollback=True`` a finished run to
        undo. The user loses work they never asked to abandon, which is far
        worse than the cancel simply not landing.
        """
        from uitk.switchboard.slots import Cancelable

        provider = self.use_provider(RecordingProvider())

        @Cancelable(60, rollback=True)
        def slot():
            # Cancel is requested, but nothing ever polls it.
            ptk.CancelScope.current().cancel("esc")
            return "completed anyway"

        wrapper, sb = self._wrapper(slot)
        self.assertEqual(wrapper(), "completed anyway")
        ends = [c for c in provider.calls if c[0] == "end"]
        self.assertTrue(ends, "the bracket was never closed")
        self.assertTrue(
            all(not c[2] for c in ends),
            f"a completed run was reported cancelled: {ends}",
        )
        # ...but the user is still told why their Esc did nothing. Silence here
        # would recreate the exact complaint this mechanism answers.
        said = " ".join(str(c) for c in sb.logger.warning.call_args_list)
        self.assertIn("could not be cancelled", said)
        self.assertIn("ran to completion", said)

    def test_a_slot_that_raised_is_not_reported_as_completed(self):
        """A pending cancel must not turn a crash into "it finished".

        Same shape as the checkpoint-less case -- flag set, nothing consumed --
        but the slot died rather than finishing, and telling the user it "ran
        to completion" sends them looking for changes that were never made.
        """
        from uitk.switchboard.slots import Cancelable

        self.use_provider(RecordingProvider())

        @Cancelable(60)
        def slot():
            ptk.CancelScope.current().cancel("esc")
            raise ValueError("boom")

        wrapper, sb = self._wrapper(slot)
        with self.assertRaises(ValueError):
            wrapper()
        said = " ".join(str(c) for c in sb.logger.warning.call_args_list)
        self.assertNotIn("ran to completion", said)

    def test_a_consumed_cancel_is_rolled_back(self):
        """The other side of the same line: a slot that DID stop must roll back."""
        from uitk.switchboard.slots import Cancelable

        provider = self.use_provider(RecordingProvider())

        @Cancelable(60, rollback=True)
        def slot():
            scope = ptk.CancelScope.current()
            scope.cancel("esc")
            if not scope.tick():  # the checkpoint consumes it
                return "stopped early"
            return "ran on"

        wrapper, _ = self._wrapper(slot)
        self.assertEqual(wrapper(), "stopped early")
        ends = [c for c in provider.calls if c[0] == "end"]
        self.assertTrue(
            any(c[2] for c in ends),
            f"a genuinely cancelled run was not reported: {ends}",
        )

    def test_provider_bracket_opens_and_closes(self):
        from uitk.switchboard.slots import Cancelable

        provider = self.use_provider(RecordingProvider())

        @Cancelable(60)
        def slot():
            return "ran"

        wrapper, _ = self._wrapper(slot)
        wrapper()
        kinds = [c[0] for c in provider.calls]
        self.assertEqual(kinds[0], "create_sources")
        self.assertIn(("begin", "Slot 'slot' on 'b000'", False), provider.calls)
        end = [c for c in provider.calls if c[0] == "end"][0]
        self.assertEqual(end, ("end", "token", False, False))

    def test_rollback_request_reaches_begin(self):
        """The host has to start recording before the work runs, not after."""
        from uitk.switchboard.slots import Cancelable

        provider = self.use_provider(RecordingProvider())

        @Cancelable(60, message="Bake", rollback=True)
        def slot():
            return "ran"

        wrapper, _ = self._wrapper(slot)
        wrapper()
        self.assertIn(("begin", "Bake", True), provider.calls)

    def test_bool_style_cancel_is_reported_and_rolled_back(self):
        """A slot that breaks out of its loop must still trigger rollback.

        The ``tick()`` is load-bearing, not decoration: breaking out of a loop
        *means* a checkpoint reported the stop, and that report is the only
        evidence the dispatcher has that the slot abandoned its work. Without
        it this slot is byte-for-byte indistinguishable from one that ignored
        the flag and ran to completion -- see
        ``test_a_checkpointless_slot_is_not_rolled_back`` for why that case
        must NOT be rolled back.
        """
        from uitk.switchboard.slots import Cancelable

        provider = self.use_provider(RecordingProvider())

        @Cancelable(60, rollback=True)
        def slot():
            scope = ptk.CancelScope.current()
            scope.cancel("escape-hold")
            if not scope.tick():  # the loop's own checkpoint says stop
                return "partial"
            return "ran on"

        wrapper, sb = self._wrapper(slot)
        self.assertEqual(wrapper(), "partial")
        end = [c for c in provider.calls if c[0] == "end"][0]
        self.assertEqual(end, ("end", "token", True, True))
        sb.logger.warning.assert_called()

    def test_exception_style_cancel_is_swallowed_at_the_boundary(self):
        from uitk.switchboard.slots import Cancelable

        provider = self.use_provider(RecordingProvider())

        @Cancelable(60, rollback=True)
        def slot():
            ptk.CancelScope.current().cancel("dialog")
            ptk.CancelScope.check()  # raises OperationCancelled
            return "never"

        wrapper, sb = self._wrapper(slot)
        self.assertIsNone(wrapper())
        end = [c for c in provider.calls if c[0] == "end"][0]
        self.assertEqual(end, ("end", "token", True, True))

    def test_rollback_is_opt_in(self):
        from uitk.switchboard.slots import Cancelable

        provider = self.use_provider(RecordingProvider())

        @Cancelable(60)
        def slot():
            ptk.CancelScope.current().cancel("esc")
            return None

        wrapper, _ = self._wrapper(slot)
        wrapper()
        end = [c for c in provider.calls if c[0] == "end"][0]
        self.assertEqual(end[3], False, "rollback must not default on")

    def test_rollback_on_a_host_that_cannot_undo_is_reported(self):
        """Silently not rolling back would let a slot ship partial work."""
        from uitk.switchboard.slots import Cancelable

        self.use_provider(RecordingProvider())  # supports_rollback absent -> False

        @Cancelable(60, message="Bake", rollback=True)
        def slot():
            return "ran"

        wrapper, sb = self._wrapper(slot)
        wrapper()
        warnings = " ".join(str(c) for c in sb.logger.warning.call_args_list)
        self.assertIn("cannot undo", warnings)

    def test_no_rollback_warning_when_host_supports_it(self):
        from uitk.managers.cancel_manager import CancelProvider
        from uitk.switchboard.slots import Cancelable

        class UndoableProvider(CancelProvider):
            name = "undoable"
            supports_rollback = True

        self.use_provider(UndoableProvider())

        @Cancelable(60, rollback=True)
        def slot():
            return "ran"

        wrapper, sb = self._wrapper(slot)
        wrapper()
        warnings = " ".join(str(c) for c in sb.logger.warning.call_args_list)
        self.assertNotIn("cannot undo", warnings)

    def test_slot_exception_still_closes_the_bracket(self):
        from uitk.switchboard.slots import Cancelable

        provider = self.use_provider(RecordingProvider())

        @Cancelable(60)
        def slot():
            raise ValueError("boom")

        wrapper, _ = self._wrapper(slot)
        with self.assertRaises(ValueError):
            wrapper()
        end = [c for c in provider.calls if c[0] == "end"][0]
        self.assertEqual(end[2], False)

    def test_broken_provider_does_not_break_dispatch(self):
        from uitk.managers.cancel_manager import CancelProvider
        from uitk.switchboard.slots import Cancelable

        class BrokenProvider(CancelProvider):
            def begin(self, scope, label="", rollback=False):
                raise RuntimeError("no host")

            def end(self, token, cancelled=False, rollback=False):
                raise RuntimeError("no host")

        self.use_provider(BrokenProvider())

        @Cancelable(60)
        def slot():
            return "ran"

        wrapper, _ = self._wrapper(slot)
        self.assertEqual(wrapper(), "ran")

    def test_cancelable_meta_carries_rollback(self):
        from uitk.switchboard.slots import Cancelable

        @Cancelable(30, message="Bake", rollback=True)
        def slot():
            pass

        self.assertEqual(
            slot._cancelable_meta,
            {"timeout": 30.0, "message": "Bake", "rollback": True},
        )

    def test_cancelable_rejects_bad_timeout(self):
        from uitk.switchboard.slots import Cancelable

        for bad in (0, -1, "60", None):
            with self.assertRaises(ValueError):
                Cancelable(bad)


class TestThreadSafeLogProxy(CancelStackTestCase):
    def test_forwards_records_on_the_calling_thread(self):
        from uitk.switchboard.slots import _ThreadSafeLogProxy

        logger = MagicMock()
        proxy = _ThreadSafeLogProxy(logger)
        proxy.warning("slow")
        logger.warning.assert_called_once_with("slow")

    def test_broken_logger_is_swallowed(self):
        from uitk.switchboard.slots import _ThreadSafeLogProxy

        logger = MagicMock()
        logger.warning.side_effect = RuntimeError("sink died")
        _ThreadSafeLogProxy(logger).warning("slow")  # must not raise


if __name__ == "__main__":
    unittest.main()
