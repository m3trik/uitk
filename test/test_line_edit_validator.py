# !/usr/bin/python
# coding=utf-8
"""Tests for LineEdit.set_validator() and auto_record integration.

Verifies:
- set_validator() debounces textChanged and emits validated(ok, text).
- Visual feedback (actionState + tooltip) updates per validation state.
- empty_tooltip restores caller's default when text is cleared.
- validate_now() flushes pending debounce.
- RecentValuesOption(auto_record=True) records on editingFinished only,
  not on every keystroke, and skips invalid values.
"""

import os
import sys
import tempfile
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets

from uitk.widgets.lineEdit import LineEdit
from uitk.widgets.optionBox.options.recent_values import RecentValuesOption


def _pump(ms=50):
    """Run the Qt event loop for *ms* milliseconds."""
    deadline = QtCore.QElapsedTimer()
    deadline.start()
    while deadline.elapsed() < ms:
        QtWidgets.QApplication.processEvents(
            QtCore.QEventLoop.AllEvents, max(1, ms - deadline.elapsed())
        )


class TestValidatorBasics(QtBaseTestCase):
    def test_validator_emits_signal_on_valid(self):
        le = self.track_widget(LineEdit())
        captured = []
        le.validated.connect(lambda ok, t: captured.append((ok, t)))

        le.set_validator(lambda t: t == "yes", debounce_ms=0)
        le.setText("yes")

        self.assertTrue(captured)
        # Last result should be (True, "yes")
        self.assertEqual(captured[-1], (True, "yes"))
        self.assertTrue(le.is_valid)

    def test_validator_emits_signal_on_invalid(self):
        le = self.track_widget(LineEdit())
        captured = []
        le.validated.connect(lambda ok, t: captured.append((ok, t)))

        le.set_validator(lambda t: t == "yes", debounce_ms=0)
        le.setText("no")

        self.assertEqual(captured[-1], (False, "no"))
        self.assertFalse(le.is_valid)

    def test_validator_action_color_invalid(self):
        le = self.track_widget(LineEdit())
        le.set_validator(lambda t: False, debounce_ms=0)
        le.setText("anything")

        self.assertEqual(le.property("actionState"), "invalid")

    def test_validator_action_color_valid(self):
        le = self.track_widget(LineEdit())
        le.set_validator(lambda t: True, debounce_ms=0)
        le.setText("anything")

        self.assertEqual(le.property("actionState"), "reset")

    def test_empty_text_resets_state_with_default_tooltip(self):
        le = self.track_widget(LineEdit())
        le.setToolTip("Source directory")
        le.set_validator("dir", debounce_ms=0)
        le.setText("/definitely/not/a/real/path/xyz")
        self.assertEqual(le.property("actionState"), "invalid")

        le.setText("")
        self.assertIsNone(le.property("actionState"))
        self.assertEqual(le.toolTip(), "Source directory")

    def test_explicit_empty_tooltip(self):
        le = self.track_widget(LineEdit())
        le.set_validator(
            lambda t: True, debounce_ms=0, empty_tooltip="please enter a path"
        )
        # Empty by default
        self.assertEqual(le.toolTip(), "please enter a path")

    def test_preset_dir_validates_real_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            le = self.track_widget(LineEdit())
            captured = []
            le.validated.connect(lambda ok, t: captured.append(ok))
            le.set_validator("dir", debounce_ms=0)
            le.setText(tmp)

            self.assertTrue(captured[-1])
            self.assertTrue(le.is_valid)

    def test_clear_validator_disconnects_and_resets(self):
        le = self.track_widget(LineEdit())
        le.set_validator(lambda t: False, debounce_ms=0)
        le.setText("x")
        self.assertEqual(le.property("actionState"), "invalid")

        le.clear_validator()
        self.assertIsNone(le.property("actionState"))
        # Subsequent text changes should NOT re-validate
        le.setText("y")
        self.assertIsNone(le.is_valid)


class TestValidatorDebounce(QtBaseTestCase):
    def test_debounce_collapses_rapid_keystrokes(self):
        le = self.track_widget(LineEdit())
        count = []
        le.validated.connect(lambda ok, t: count.append(t))

        le.set_validator(lambda t: True, debounce_ms=50)
        # Clear initial-state emission
        count.clear()
        # Simulate rapid typing
        for ch in "abcde":
            le.setText(le.text() + ch)

        # Pre-pump, no validation should have fired
        self.assertEqual(count, [])

        _pump(120)

        # Debounce should have fired exactly once for the final text
        self.assertEqual(count, ["abcde"])

    def test_validate_now_flushes_debounce(self):
        le = self.track_widget(LineEdit())
        count = []
        le.validated.connect(lambda ok, t: count.append(t))

        le.set_validator(lambda t: True, debounce_ms=200)
        count.clear()
        le.setText("hello")
        self.assertEqual(count, [])

        le.validate_now()
        self.assertEqual(count, ["hello"])


class TestAutoRecord(QtBaseTestCase):
    def test_records_only_on_editing_finished(self):
        le = self.track_widget(LineEdit())
        opt = RecentValuesOption(wrapped_widget=le, auto_record=True)

        # Simulate typing each char — no record should happen
        for ch in "hello":
            le.setText(le.text() + ch)
        self.assertEqual(opt.recent_values, [])

        # Now commit
        le.editingFinished.emit()
        self.assertEqual(opt.recent_values, ["hello"])

    def test_skips_invalid_text(self):
        le = self.track_widget(LineEdit())
        opt = RecentValuesOption(wrapped_widget=le, auto_record=True)
        le.set_validator(lambda t: t == "ok", debounce_ms=0)

        le.setText("bad")
        le.editingFinished.emit()
        self.assertEqual(opt.recent_values, [])

        le.setText("ok")
        le.editingFinished.emit()
        self.assertEqual(opt.recent_values, ["ok"])

    def test_does_not_record_when_disabled(self):
        le = self.track_widget(LineEdit())
        opt = RecentValuesOption(wrapped_widget=le)  # auto_record default = False

        le.setText("hello")
        le.editingFinished.emit()
        self.assertEqual(opt.recent_values, [])

    def test_flushes_debounce_before_recording(self):
        """If user types and presses Enter before debounce fires, the validator
        must run first so is_valid reflects the current text."""
        le = self.track_widget(LineEdit())
        opt = RecentValuesOption(wrapped_widget=le, auto_record=True)
        le.set_validator(lambda t: t == "good", debounce_ms=500)

        # Type then commit immediately — debounce timer is still pending
        le.setText("good")
        le.editingFinished.emit()

        # auto_record should have called validate_now() and recorded
        self.assertEqual(opt.recent_values, ["good"])


if __name__ == "__main__":
    unittest.main()
