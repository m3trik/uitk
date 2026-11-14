# !/usr/bin/python
# coding=utf-8
"""Tests for uitk.managers.background_task: work off the UI thread, its outcome read back on it."""

import threading
import unittest

from qtpy import QtCore, QtWidgets

from conftest import QtBaseTestCase, QtWait, setup_qt_application
from uitk.managers.background_task import BackgroundTask

app = setup_qt_application()


class TestBackgroundTask(QtBaseTestCase):
    def test_what_the_work_returns_reaches_the_ui_thread(self):
        release = threading.Event()
        task = BackgroundTask(lambda: (release.wait(5), threading.current_thread().name)[1], "bg-test")
        self.assertFalse(task.done)  # the caller was not kept waiting
        seen = []
        parent = self.track_widget(QtWidgets.QWidget())
        task.when_done(parent, lambda: seen.append((task.result(), threading.current_thread())))
        release.set()
        QtWait.until(lambda: seen, "the callback never ran", timeout_ms=5000)
        (worker_name, called_on), = seen
        self.assertEqual(worker_name, "bg-test")
        self.assertIs(called_on, threading.main_thread())

    def test_a_result_someone_waits_for_is_looked_for_sooner(self):
        task = BackgroundTask(lambda: 7, "bg-quick")
        task.wait(5)
        parent = self.track_widget(QtWidgets.QWidget())
        seen = []
        task.when_done(parent, lambda: seen.append(task.result()), poll_ms=10)
        timers = parent.findChildren(QtCore.QTimer)
        self.assertEqual([t.interval() for t in timers], [10])
        QtWait.until(lambda: seen, "the callback never ran", timeout_ms=2000)
        self.assertEqual(seen, [7])

    def test_what_the_work_raises_is_raised_where_its_result_is_read(self):
        def fail():
            raise RuntimeError("the service did not start")

        task = BackgroundTask(fail, "bg-fail")
        task.wait(5)
        self.assertTrue(task.done)
        with self.assertRaises(RuntimeError) as ctx:
            task.result()
        self.assertIn("did not start", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
