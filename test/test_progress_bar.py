# !/usr/bin/python
# coding=utf-8
"""Regression tests for the ProgressBar widget / ProgressTaskContext.

Run standalone: python -m test.test_progress_bar
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()


class TestProgressTaskShortcutTeardown(QtBaseTestCase):
    """The app-wide Esc GlobalShortcut enabled by start_task must always be
    torn down on task exit — including the exception path.

    Regression: __exit__ only disabled it via finish_task() on the clean path;
    on an exception (or with auto_hide off) the shortcut stayed enabled, so a
    later Esc-hold anywhere in the host app fired cancel() on a dead task.
    """

    def test_shortcut_disabled_when_task_body_raises(self):
        from uitk.widgets.progressBar import ProgressBar

        pb = self.track_widget(ProgressBar(auto_hide=False))

        with self.assertRaises(ValueError):
            with pb.task(total=10, text="work") as update:
                update(1)
                # While the task runs, the Esc shortcut is enabled.
                self.assertTrue(pb._cancel_shortcut._shortcut.isEnabled())
                raise ValueError("boom")

        # After the exception unwinds the context, it must be disabled.
        self.assertIsNotNone(pb._cancel_shortcut)
        self.assertFalse(pb._cancel_shortcut._shortcut.isEnabled())

    def test_shortcut_disabled_on_clean_exit(self):
        from uitk.widgets.progressBar import ProgressBar

        pb = self.track_widget(ProgressBar(auto_hide=False))
        with pb.task(total=5, text="work") as update:
            update(5)
        self.assertFalse(pb._cancel_shortcut._shortcut.isEnabled())


if __name__ == "__main__":
    unittest.main()
