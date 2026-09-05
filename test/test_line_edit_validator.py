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
import tempfile
import threading
import unittest
from unittest.mock import patch

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets

from uitk.widgets.lineEdit import LineEdit
from uitk.widgets.optionBox.options.recent_values import (
    RecentValuesOption,
    RecentValueEntry,
)


def _pump(ms=50):
    """Run the Qt event loop for *ms* milliseconds."""
    deadline = QtCore.QElapsedTimer()
    deadline.start()
    while deadline.elapsed() < ms:
        QtWidgets.QApplication.processEvents(
            QtCore.QEventLoop.AllEvents, max(1, ms - deadline.elapsed())
        )


def _settle(le, ms=1000):
    """Pump until a deferred check has answered (the ``info`` state clears)."""
    deadline = QtCore.QElapsedTimer()
    deadline.start()
    while le.property("actionState") == "info" and deadline.elapsed() < ms:
        _pump(20)


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


class TestValidatorDeferred(QtBaseTestCase):
    """The deferred stage: a slow check off the Qt thread whose answer lands
    on the field only while it still describes the current text."""

    def _field(self, answer):
        le = self.track_widget(LineEdit())
        le.set_validator(
            lambda t: bool(t),
            deferred=answer,
            invalid_tooltip="bad",
            pending_tooltip="checking",
            debounce_ms=0,
        )
        return le

    def test_pending_then_failure_colors_invalid_with_message(self):
        le = self._field(lambda t: (False, f"{t} unreachable"))
        le.setText("http://x")
        self.assertEqual(le.property("actionState"), "info")
        self.assertEqual(le.toolTip(), "checking")
        _settle(le)
        self.assertEqual(le.property("actionState"), "invalid")
        self.assertEqual(le.toolTip(), "http://x unreachable")
        self.assertFalse(le.is_valid)

    def test_success_resets_and_emits_validated_twice(self):
        le = self._field(lambda t: True)
        captured = []
        le.validated.connect(lambda ok, t: captured.append(ok))
        le.setText("http://x")
        _settle(le)
        self.assertNotIn(le.property("actionState"), ("info", "invalid"))
        self.assertEqual(captured, [True, True])
        self.assertTrue(le.is_valid)

    def test_stale_answer_for_replaced_text_is_dropped(self):
        gate = threading.Event()

        def answer(t):
            if t == "http://first":
                gate.wait(2)
                return (False, "late")
            return True

        le = self._field(answer)
        le.setText("http://first")
        le.setText("http://second")
        _settle(le)
        gate.set()
        _pump(150)
        self.assertNotIn(le.property("actionState"), ("info", "invalid"))
        self.assertNotEqual(le.toolTip(), "late")
        self.assertTrue(le.is_valid)

    def test_validate_now_without_deferred_settles_sync_only(self):
        le = self._field(lambda t: (False, "no"))
        le.setText("http://x")
        le.validate_now(run_deferred=False)
        self.assertNotIn(le.property("actionState"), ("info", "invalid"))
        _pump(150)  # the retired probe's answer must not land
        self.assertNotIn(le.property("actionState"), ("info", "invalid"))
        self.assertTrue(le.is_valid)

    def test_exception_in_deferred_reads_as_invalid_with_default_tooltip(self):
        def boom(_t):
            raise RuntimeError("x")

        le = self._field(boom)
        le.setText("http://x")
        _settle(le)
        self.assertEqual(le.property("actionState"), "invalid")
        self.assertEqual(le.toolTip(), "bad")

    def test_clear_validator_retires_in_flight_check(self):
        gate = threading.Event()

        def slow(_t):
            gate.wait(2)
            return (False, "late")

        le = self._field(slow)
        le.setText("http://x")
        le.clear_validator()
        gate.set()
        _pump(150)
        self.assertNotIn(le.property("actionState"), ("info", "invalid"))


class TestValidatorUrlPresets(QtBaseTestCase):
    """``"url"`` / ``"file_or_url"``: shape synchronously, reachability through
    the auto-installed deferred probe, the reason wrapped by a callable tooltip."""

    _URL = "https://x.test/a.csv"

    def test_file_or_url_accepts_an_existing_file_without_probing(self):
        le = self.track_widget(LineEdit())
        with patch("pythontk.RemoteFile.probe", side_effect=AssertionError("probed")):
            le.set_validator("file_or_url", debounce_ms=0)
            le.setText(__file__)
            _pump(50)
        self.assertNotIn(le.property("actionState"), ("info", "invalid"))
        self.assertTrue(le.is_valid)

    def test_file_or_url_rejects_a_missing_file_synchronously(self):
        le = self.track_widget(LineEdit())
        le.set_validator("file_or_url", invalid_tooltip="nope", debounce_ms=0)
        le.setText("X:/no/such.csv")
        self.assertEqual(le.property("actionState"), "invalid")
        self.assertEqual(le.toolTip(), "nope")

    def test_url_preset_probes_and_wraps_the_reason(self):
        le = self.track_widget(LineEdit())
        le.set_validator("url", invalid_tooltip=lambda m: f"[{m}]", debounce_ms=0)
        with patch("pythontk.RemoteFile.probe", return_value="Can't fetch: 404"):
            le.setText(self._URL)
            self.assertEqual(le.property("actionState"), "info")
            _settle(le)
        self.assertEqual(le.property("actionState"), "invalid")
        self.assertEqual(le.toolTip(), "[Can't fetch: 404]")
        self.assertFalse(le.is_valid)

    def test_url_preset_reachable_resets(self):
        le = self.track_widget(LineEdit())
        le.set_validator("url", debounce_ms=0)
        with patch("pythontk.RemoteFile.probe", return_value=None):
            le.setText(self._URL)
            _settle(le)
        self.assertNotIn(le.property("actionState"), ("info", "invalid"))
        self.assertTrue(le.is_valid)

    def test_callable_invalid_tooltip_gets_none_on_sync_failure(self):
        le = self.track_widget(LineEdit())
        le.set_validator(
            "url", invalid_tooltip=lambda m: "sync" if m is None else m, debounce_ms=0
        )
        le.setText("not a url")
        self.assertEqual(le.property("actionState"), "invalid")
        self.assertEqual(le.toolTip(), "sync")

    def test_explicit_deferred_overrides_the_preset_probe(self):
        le = self.track_widget(LineEdit())
        le.set_validator("url", deferred=lambda t: (False, "custom"), debounce_ms=0)
        with patch("pythontk.RemoteFile.probe", side_effect=AssertionError("probed")):
            le.setText(self._URL)
            _settle(le)
        self.assertEqual(le.toolTip(), "custom")


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


class TestLineEditValueData(QtBaseTestCase):
    """The display/data split: set_value() shows a friendly string while
    value()/data() carry the real payload."""

    def test_set_value_with_display_splits_text_and_value(self):
        le = self.track_widget(LineEdit())
        le.set_value("C:/a/Rock_Normal.png", display="Rock")
        self.assertEqual(le.text(), "Rock")  # friendly display
        self.assertEqual(le.value(), "C:/a/Rock_Normal.png")  # real payload
        self.assertEqual(le.data(), "C:/a/Rock_Normal.png")

    def test_set_value_without_display_behaves_like_set_text(self):
        le = self.track_widget(LineEdit())
        le.set_value("plain")
        self.assertEqual(le.text(), "plain")
        self.assertEqual(le.value(), "plain")
        self.assertIsNone(le.data())  # no hidden payload

    def test_value_falls_back_to_text_when_no_payload(self):
        le = self.track_widget(LineEdit())
        le.setText("typed")
        self.assertEqual(le.value(), "typed")
        self.assertIsNone(le.data())

    def test_manual_edit_invalidates_payload(self):
        le = self.track_widget(LineEdit())
        le.set_value("DATA", display="disp")
        self.assertEqual(le.data(), "DATA")
        # A user keystroke emits textEdited (programmatic setText does not).
        le.textEdited.emit("disp typed")
        self.assertIsNone(le.data())
        self.assertEqual(le.value(), le.text())

    def test_clear_value_drops_payload_keeps_text(self):
        le = self.track_widget(LineEdit())
        le.set_value("DATA", display="disp")
        le.clear_value()
        self.assertIsNone(le.data())
        self.assertEqual(le.text(), "disp")

    def test_validator_runs_against_payload_not_display(self):
        le = self.track_widget(LineEdit())
        seen = []
        le.validated.connect(lambda ok, v: seen.append((ok, v)))
        le.set_validator(lambda v: v == "REAL", debounce_ms=0)
        le.set_value("REAL", display="friendly")
        # Validation sees the payload, not the on-screen "friendly" text.
        self.assertTrue(le.is_valid)
        self.assertEqual(seen[-1], (True, "REAL"))


class TestDataAwareRecentValues(QtBaseTestCase):
    """RecentValuesOption records and restores both the display and the data
    when the wrapped widget carries a payload."""

    @property
    def _joined(self):
        return os.pathsep.join(["C:/a/Rock_BaseColor.png", "C:/a/Rock_Normal.png"])

    def test_record_captures_entry_with_display_and_data(self):
        le = self.track_widget(LineEdit())
        opt = RecentValuesOption(wrapped_widget=le)
        le.set_value(self._joined, display="Rock")
        opt.record()

        vals = opt.recent_values
        self.assertEqual(len(vals), 1)
        entry = vals[0]
        self.assertIsInstance(entry, RecentValueEntry)
        self.assertEqual(entry.display, "Rock")
        self.assertEqual(entry.data, self._joined)

    def test_restore_entry_sets_value_and_display(self):
        le = self.track_widget(LineEdit())
        opt = RecentValuesOption(wrapped_widget=le)
        entry = RecentValueEntry(self._joined, display="Rock")

        opt._restore_value(entry)
        self.assertEqual(le.text(), "Rock")  # friendly label restored
        self.assertEqual(le.value(), self._joined)  # real paths restored
        self.assertEqual(le.data(), self._joined)

    def test_plain_text_records_without_entry(self):
        le = self.track_widget(LineEdit())
        opt = RecentValuesOption(wrapped_widget=le)
        le.setText("C:/just/a/dir")
        opt.record()
        self.assertEqual(opt.recent_values, ["C:/just/a/dir"])

    def test_entry_dedups_against_plain_value_by_data(self):
        le = self.track_widget(LineEdit())
        opt = RecentValuesOption(wrapped_widget=le)
        opt.record(self._joined)  # plain
        le.set_value(self._joined, display="Rock")
        opt.record()  # entry with same data → moves to front, no dup
        self.assertEqual(len(opt.recent_values), 1)


if __name__ == "__main__":
    unittest.main()
