# !/usr/bin/python
# coding=utf-8
"""Tests for PreviewController: a preview panel's widgets bound over a scene
session, driven through real (offscreen) Qt widgets and a recording fake
session. Each host's own session is tested in its own library's
``test_preview.py``.

Run standalone: python -m test.test_preview_controller
"""

import contextlib
import unittest

from qtpy import QtCore, QtWidgets

from conftest import QtBaseTestCase, setup_qt_application
from uitk.managers.preview_controller import PreviewController

app = setup_qt_application()


class FakeSession:
    """A :class:`PreviewSession` that records each call (``log``) over a
    selection the test sets; ``fail`` names a call that raises."""

    def __init__(self, operation=None):
        self.operation = operation
        self.log = []
        self.objects = ["a", "b"]
        self.fail = None

    def _call(self, name, *args):
        self.log.append((name,) + args if args else name)
        if self.fail == name:
            raise RuntimeError(f"{name} failed\nsecond line")

    def selection(self):
        self._call("selection")
        return list(self.objects)

    def begin(self, objects):
        self._call("begin", list(objects))

    def run(self):
        self._call("run")

    def rollback(self):
        self._call("rollback")

    def discard(self, reselect):
        self._call("discard", reselect)

    def commit(self):
        self._call("commit")

    def apply(self, objects):
        self._call("apply", list(objects))

    @contextlib.contextmanager
    def undo_step(self, name):
        self.log.append(("undo_step", name))
        try:
            yield
        finally:
            self.log.append("undo_step_end")

    @contextlib.contextmanager
    def unrecorded(self):
        self.log.append("unrecorded")
        try:
            yield
        finally:
            self.log.append("unrecorded_end")

    def select_result(self, checkbox, results, committed):
        self.log.append(("select_result", checkbox.isChecked(), results, committed))


class Operation:
    """A panel's operation: what the controller calls itself is the hook."""

    def __init__(self, log=None, prepare_fails=False):
        self.log = log
        self.prepare_fails = prepare_fails

    def perform_operation(self, objects, *args):  # the session's to call
        raise AssertionError("the controller never runs the operation itself")


class PreparingOperation(Operation):
    def prepare_operation(self, objects):
        self.log.append(("prepare", list(objects)))
        if self.prepare_fails:
            raise ValueError("precondition failed")


class PanelWindow(QtWidgets.QWidget):
    """A panel window with uitk ``MainWindow``'s show / hide signals."""

    on_show = QtCore.Signal()
    on_hide = QtCore.Signal()

    def showEvent(self, event):
        super().showEvent(event)
        self.on_show.emit()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.on_hide.emit()


class PreviewControllerCase(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.window = PanelWindow()
        layout = QtWidgets.QVBoxLayout(self.window)
        self.chk = QtWidgets.QCheckBox("Preview", self.window)
        self.btn = QtWidgets.QPushButton("Create", self.window)
        self.btn.setEnabled(False)  # as the tools' .ui files ship it
        self.pick = QtWidgets.QCheckBox("Select Result", self.window)
        for widget in (self.chk, self.btn, self.pick):
            layout.addWidget(widget)
        self._widgets_to_cleanup.append(self.window)
        self.session = FakeSession()
        self.messages = []

    def tearDown(self):
        # Before the widgets go: a running preview discards over live ones.
        PreviewController.cleanup_all_instances()
        super().tearDown()

    def make(self, operation=None, **kwargs):
        kwargs.setdefault("message_func", self.messages.append)
        kwargs.setdefault("session", self.session)
        return PreviewController(
            operation or Operation(self.session.log), self.chk, self.btn, **kwargs
        )

    def calls(self):
        """The session's log without the selection reads."""
        return [c for c in self.session.log if c != "selection"]


class TestBinding(PreviewControllerCase):
    def test_the_checkbox_is_kept_out_of_restore_and_reset(self):
        self.make()
        self.assertIs(self.chk.exclude_from_reset, True)
        self.assertIs(self.chk.restore_state, False)

    def test_the_commit_button_is_live_from_the_start(self):
        self.make()
        self.assertTrue(self.btn.isEnabled())

    def test_require_preview_keeps_the_commit_button_dead_until_a_preview(self):
        preview = self.make(require_preview=True)
        self.assertFalse(self.btn.isEnabled())
        self.chk.click()
        self.assertTrue(self.btn.isEnabled())
        self.btn.click()
        self.assertFalse(self.btn.isEnabled())
        self.assertFalse(preview.is_enabled)

    def test_a_session_is_required(self):
        with self.assertRaises(TypeError):
            PreviewController(Operation(), self.chk, self.btn)

    def test_the_session_class_builds_one_per_preview(self):
        class Bound(PreviewController):
            SESSION_CLASS = FakeSession

        op = Operation()
        first = Bound(op, self.chk, self.btn)
        second = Bound(op, QtWidgets.QCheckBox(), QtWidgets.QPushButton())
        self.assertIsInstance(first.session, FakeSession)
        self.assertIs(first.session.operation, op)
        self.assertIsNot(first.session, second.session)

    def test_an_operation_and_both_widgets_are_required(self):
        with self.assertRaises(ValueError):
            PreviewController(object(), self.chk, self.btn, session=self.session)
        with self.assertRaises(ValueError):
            PreviewController(Operation(), None, self.btn, session=self.session)


class TestLifecycle(PreviewControllerCase):
    def test_checking_the_box_starts_a_pass_and_unchecking_discards_it(self):
        preview = self.make()
        self.chk.click()
        self.assertTrue(preview.is_enabled)
        self.assertEqual(self.calls(), [("begin", ["a", "b"]), "run"])
        self.chk.click()
        self.assertFalse(preview.is_enabled)
        self.assertEqual(
            self.calls()[2:],
            ["rollback", "unrecorded", "unrecorded_end", ("discard", True)],
        )

    def test_a_refresh_rolls_back_and_runs_again(self):
        preview = self.make()
        preview.refresh()
        self.assertEqual(self.calls(), [], "no preview running: nothing")
        self.chk.click()
        preview.refresh()
        self.assertEqual(self.calls()[-2:], ["rollback", "run"])

    def test_a_programmatic_enable_checks_the_box_without_a_second_pass(self):
        preview = self.make()
        heard = []
        self.chk.toggled.connect(heard.append)
        preview.enable()
        self.assertTrue(self.chk.isChecked())
        self.assertEqual(self.calls(), [("begin", ["a", "b"]), "run"])
        # The box's other listeners hear the change (a panel's own hooks).
        self.assertEqual(heard, [True])
        preview.enable()  # running: a no-op
        self.assertEqual(self.calls().count("run"), 1)

    def test_a_listener_refreshing_on_the_check_starts_no_second_pass(self):
        """Checking the box FOR the user reaches its other listeners; one that
        refreshes (a panel hook) must not run a pass ahead of the enable's."""
        preview = self.make()
        self.chk.toggled.connect(lambda on: on and preview.refresh())
        preview.enable()
        self.assertEqual(self.calls(), [("begin", ["a", "b"]), "run"])

    def test_an_empty_selection_refuses_the_preview(self):
        self.session.objects = []
        preview = self.make()
        self.chk.click()
        self.assertFalse(preview.is_enabled)
        self.assertFalse(self.chk.isChecked())
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.messages, ["No objects selected."])

    def test_validation_refuses_a_preview_and_a_commit(self):
        seen = []
        preview = self.make(validation_func=lambda objs: seen.append(objs) or False)
        self.chk.click()
        self.btn.click()
        self.assertFalse(preview.is_enabled)
        self.assertEqual(self.calls(), [])
        self.assertEqual(seen, [["a", "b"], ["a", "b"]])
        self.assertEqual(self.messages, ["Operation validation failed."] * 2)

    def test_a_failed_pass_is_reported_rolled_back_and_turned_off(self):
        restores, heard = [], []
        self.session.fail = "run"
        preview = self.make(restore_func=lambda: restores.append(1))
        self.chk.toggled.connect(heard.append)
        self.chk.click()
        self.assertFalse(preview.is_enabled)
        self.assertFalse(self.chk.isChecked())
        # A listener connected after the preview hears the box go off, nested
        # inside the user's own toggle (so before it): Qt's emission order.
        self.assertEqual(heard, [False, True], "the box's listeners hear it go off")
        self.assertEqual(
            self.calls(),
            [
                ("begin", ["a", "b"]),
                "run",
                "rollback",
                "unrecorded",
                "unrecorded_end",
                ("discard", True),
            ],
        )
        self.assertEqual(restores, [1])
        self.assertEqual(len(self.messages), 1)
        self.assertIn("run failed", self.messages[0])
        self.assertNotIn("second line", self.messages[0])

    def test_the_restore_hook_runs_unrecorded_on_a_discard_only(self):
        order = []
        session = self.session
        preview = self.make(
            restore_func=lambda: order.append(session.log[-1]),
            reselect_on_disable=False,
        )
        self.chk.click()
        self.btn.click()  # a commit never restores
        self.assertEqual(order, [])
        self.chk.click()
        self.chk.click()
        self.assertEqual(order, ["unrecorded"], "inside the unrecorded scope")
        self.assertEqual(self.calls()[-1], ("discard", False))
        preview.disable()  # already off: nothing to restore
        self.assertEqual(len(order), 1)

    def test_a_failed_prepare_aborts_the_enable(self):
        op = PreparingOperation(self.session.log, prepare_fails=True)
        preview = self.make(op)
        self.chk.click()
        self.assertFalse(preview.is_enabled)
        self.assertFalse(self.chk.isChecked())
        self.assertEqual(self.calls(), [("prepare", ["a", "b"])])
        self.assertIn("precondition failed", self.messages[-1])

    def test_prepare_runs_once_before_the_capture(self):
        op = PreparingOperation(self.session.log)
        preview = self.make(op)
        self.chk.click()
        preview.refresh()
        self.assertEqual(
            self.calls(),
            [("prepare", ["a", "b"]), ("begin", ["a", "b"]), "run", "rollback", "run"],
        )

    def test_a_curated_error_message_shows_whole(self):
        class Curated(Exception):
            user_message = "Select <b>two</b> loops."
            causes = ["one loop is closed"]
            title = "Bridge failed"

        text = PreviewController._format_op_error(Curated("raw"))
        self.assertIn("Bridge failed", text)
        self.assertIn("<b>two</b>", text)
        self.assertIn("one loop is closed", text)
        plain = PreviewController._format_op_error(RuntimeError("'<' broke\nmore"))
        self.assertIn("&lt;", plain)
        self.assertNotIn("more", plain)


class TestCommit(PreviewControllerCase):
    def test_a_previewed_commit_is_one_undo_step_with_its_finalize_step(self):
        log = self.session.log
        preview = self.make(
            finalize_func=lambda: log.append("finalize"),
            undo_message="Bridge",
            select_result_checkbox=self.pick,
            result_provider=lambda: "result",
        )
        self.chk.click()
        del log[:]
        self.btn.click()
        self.assertFalse(preview.is_enabled)
        self.assertFalse(self.chk.isChecked())
        self.assertEqual(
            log,
            [
                ("undo_step", "Bridge"),
                "commit",
                "finalize",
                ("select_result", False, "result", True),
                "undo_step_end",
            ],
        )

    def test_a_commit_with_no_preview_runs_once_on_the_selection(self):
        op = PreparingOperation(self.session.log)
        preview = self.make(op)
        self.btn.click()
        self.assertFalse(preview.is_enabled)
        self.assertEqual(
            self.calls(),
            [
                ("undo_step", "PreparingOperation"),
                ("prepare", ["a", "b"]),
                ("apply", ["a", "b"]),
                "undo_step_end",
            ],
        )

    def test_a_refused_prepare_commits_nothing(self):
        finals = []
        op = PreparingOperation(self.session.log, prepare_fails=True)
        self.make(op, finalize_func=lambda: finals.append(1))
        self.btn.click()
        self.assertNotIn("apply", [c[0] for c in self.calls() if isinstance(c, tuple)])
        self.assertEqual(finals, [])
        self.assertEqual(self.calls()[-1], "undo_step_end")

    def test_a_refused_commit_cancels_its_undo_step(self):
        """A host whose step needs dropping when nothing changed (no empty
        undo step) yields a handle; the controller cancels it on a refusal."""
        cancelled = []

        class Handle:
            def cancel(self):
                cancelled.append(True)

        @contextlib.contextmanager
        def undo_step(name):
            yield Handle()

        self.session.undo_step = undo_step
        self.make(PreparingOperation(self.session.log, prepare_fails=True))
        self.btn.click()
        self.assertEqual(cancelled, [True])
        button = QtWidgets.QPushButton("Create", self.window)
        PreviewController(
            PreparingOperation(self.session.log),
            QtWidgets.QCheckBox(self.window),
            button,
            message_func=self.messages.append,
            session=self.session,
        )
        button.click()  # a commit that ran keeps its step
        self.assertEqual(cancelled, [True])

    def test_a_failed_previewed_commit_ends_as_a_discard(self):
        """The commit rolled the preview back before it failed: the session's
        discard runs (a host reasserts what its rollback dropped)."""
        self.session.fail = "commit"
        self.make()
        self.chk.click()
        self.btn.click()
        self.assertEqual(self.calls()[-2:], ["undo_step_end", ("discard", True)])

    def test_require_preview_refuses_a_blind_commit(self):
        preview = self.make(require_preview=True)
        preview.finalize_changes()
        self.assertEqual(self.calls(), [])

    def test_a_failed_commit_is_reported_and_leaves_the_preview_off(self):
        self.session.fail = "commit"
        finals = []
        preview = self.make(finalize_func=lambda: finals.append(1))
        self.chk.click()
        self.btn.click()  # must not raise out of the click
        self.assertFalse(preview.is_enabled)
        self.assertFalse(self.chk.isChecked())
        self.assertEqual(finals, [])
        self.assertIn("undo_step_end", self.calls())
        self.assertIn("commit failed", self.messages[-1])

    def test_a_raising_finalize_step_is_logged_not_raised(self):
        def boom():
            raise RuntimeError("finalize broke")

        preview = self.make(finalize_func=boom)
        with self.assertLogs(preview.logger, level="ERROR"):
            self.btn.click()
        self.assertEqual(self.calls()[-1], "undo_step_end")
        self.assertEqual(self.messages, [])


class TestSelectResult(PreviewControllerCase):
    def test_each_pass_applies_it_and_a_toggle_applies_it_live(self):
        results = ["r1"]
        self.make(select_result_checkbox=self.pick, result_provider=lambda: results)
        self.chk.click()
        self.assertEqual(self.calls()[-1], ("select_result", False, ["r1"], False))
        runs = self.calls().count("run")
        self.pick.click()
        self.assertEqual(self.calls()[-1], ("select_result", True, ["r1"], False))
        self.assertEqual(self.calls().count("run"), runs, "a toggle never re-runs")

    def test_unconfigured_it_does_nothing(self):
        self.make(select_result_checkbox=self.pick)
        self.chk.click()
        self.pick.click()
        self.assertNotIn(
            "select_result", [c[0] for c in self.calls() if isinstance(c, tuple)]
        )

    def test_a_raising_provider_is_logged_not_raised(self):
        def boom():
            raise RuntimeError("provider broke")

        preview = self.make(select_result_checkbox=self.pick, result_provider=boom)
        with self.assertLogs(preview.logger, level="ERROR"):
            self.chk.click()
        self.assertTrue(preview.is_enabled)


class TestWindowHooks(PreviewControllerCase):
    def test_enable_on_show_previews_each_time_the_window_shows(self):
        preview = self.make(enable_on_show=True)
        self.window.show()
        app.processEvents()
        self.assertTrue(preview.is_enabled)
        self.assertTrue(self.chk.isChecked())
        self.window.hide()
        app.processEvents()
        self.assertFalse(preview.is_enabled, "a hide discards by default")
        self.window.show()
        app.processEvents()
        self.assertTrue(preview.is_enabled)
        self.assertEqual(self.calls().count("run"), 2)

    def test_a_show_previews_nothing_by_default(self):
        preview = self.make()
        self.window.show()
        app.processEvents()
        self.assertFalse(preview.is_enabled)

    def test_disable_on_hide_false_keeps_the_preview(self):
        preview = self.make(disable_on_hide=False)
        self.window.show()
        app.processEvents()
        self.chk.click()
        self.window.hide()
        app.processEvents()
        self.assertTrue(preview.is_enabled)


class TestInstances(PreviewControllerCase):
    def test_cleanup_all_instances_discards_every_running_preview(self):
        preview = self.make()
        self.chk.click()
        self.assertIn(preview, PreviewController._instances)
        PreviewController.cleanup_all_instances()
        self.assertFalse(preview.is_enabled)
        self.assertNotIn(preview, PreviewController._instances)
        self.assertEqual(self.calls()[-1], ("discard", True))


if __name__ == "__main__":
    unittest.main()
