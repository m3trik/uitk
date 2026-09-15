# !/usr/bin/python
# coding=utf-8
"""Tests for ``ResetGesture`` — the Restore Defaults click grammar."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets

from uitk.managers.reset_gesture import ResetGesture

Qt = QtCore.Qt


class _SavingState:
    """Records what the gesture asked of a full StateManager."""

    def __init__(self, saved=False):
        self.calls = []
        self.saved = saved

    def reset_all(self, block_signals=False, widgets=None, factory=False):
        self.calls.append(("factory" if factory else "reset", widgets))

    def save_defaults(self, widgets=None):
        self.calls.append(("save", widgets))
        self.saved = True
        return 1

    def clear_saved_defaults(self, widgets=None):
        return 0

    def has_saved_defaults(self, widgets=None):
        return self.saved


class _ResetOnlyState:
    """A stand-in that can reset but not save (e.g. an editor's shim)."""

    def __init__(self):
        self.calls = []

    def reset_all(self, block_signals=False, widgets=None):
        self.calls.append(("reset", widgets))


class TestActionFor(unittest.TestCase):
    def test_plain_click_resets(self):
        self.assertEqual(ResetGesture.action_for(Qt.NoModifier), ResetGesture.RESET)

    def test_shift_saves(self):
        self.assertEqual(ResetGesture.action_for(Qt.ShiftModifier), ResetGesture.SAVE)

    def test_ctrl_shift_is_factory_even_when_ctrl_bypasses(self):
        action = ResetGesture.action_for(
            Qt.ControlModifier | Qt.ShiftModifier,
            bypass_modifier=Qt.AltModifier | Qt.ControlModifier,
        )
        self.assertEqual(action, ResetGesture.FACTORY)

    def test_bypass_only_for_a_control_that_has_one(self):
        self.assertEqual(ResetGesture.action_for(Qt.AltModifier), ResetGesture.RESET)
        self.assertEqual(
            ResetGesture.action_for(Qt.AltModifier, bypass_modifier=Qt.AltModifier),
            ResetGesture.BYPASS,
        )

    def test_modifier_keys_names_the_set_flags(self):
        keys = ResetGesture.modifier_keys(Qt.AltModifier | Qt.ControlModifier)
        self.assertEqual(keys, ["Ctrl", "Alt"])


class TestTooltip(unittest.TestCase):
    def test_teaches_every_modifier(self):
        tip = ResetGesture.tooltip()
        for text in ("Shift", "Ctrl", "factory defaults", "current values"):
            self.assertIn(text, tip)

    def test_says_whether_saved_defaults_are_in_use(self):
        self.assertIn("saved defaults are in use", ResetGesture.tooltip(saved=True))
        self.assertIn("factory values", ResetGesture.tooltip(saved=False))
        self.assertNotIn(
            "factory values", ResetGesture.tooltip(), "unknown: no stale note"
        )

    def test_bypass_row_only_when_documented(self):
        self.assertNotIn("bypass", ResetGesture.tooltip())
        self.assertIn("bypass", ResetGesture.tooltip(bypass=["Alt", "Ctrl"]))

    def test_no_saving_rows_for_a_state_that_cannot_save(self):
        tip = ResetGesture.tooltip(saving=False)
        self.assertNotIn("Shift", tip)
        self.assertIn("Reset to the defaults", tip)


class TestAttachedButton(QtBaseTestCase):
    def _make(self, state, held=Qt.NoModifier):
        button = self.track_widget(QtWidgets.QPushButton("Restore Defaults"))
        self.held = held
        gesture = ResetGesture(
            button, state, widgets=lambda: ["w"], modifiers=lambda: self.held
        )
        return button, gesture

    def _hover(self, button):
        point = QtCore.QPointF(1, 1)
        QtWidgets.QApplication.sendEvent(button, QtGui.QEnterEvent(point, point, point))

    def test_plain_click_resets_the_scope(self):
        state = _SavingState()
        button, _ = self._make(state)
        button.click()
        self.assertEqual(state.calls, [("reset", ["w"])])

    def test_shift_click_saves_the_current_values(self):
        state = _SavingState()
        button, _ = self._make(state, Qt.ShiftModifier)
        button.click()
        self.assertEqual(state.calls, [("save", ["w"])])

    def test_ctrl_shift_click_restores_factory(self):
        state = _SavingState()
        button, _ = self._make(state, Qt.ControlModifier | Qt.ShiftModifier)
        button.click()
        self.assertEqual(state.calls, [("factory", ["w"])])

    def test_the_button_tooltip_teaches_the_modifiers(self):
        button, _ = self._make(_SavingState())
        self.assertIn("Shift", button.toolTip())

    def test_hover_refreshes_the_saved_note(self):
        state = _SavingState()
        button, _ = self._make(state)
        self.assertIn("factory values", button.toolTip())
        state.saved = True
        help_event = QtGui.QHelpEvent(
            QtCore.QEvent.ToolTip, QtCore.QPoint(1, 1), QtCore.QPoint(1, 1)
        )
        QtWidgets.QApplication.sendEvent(button, help_event)
        self.assertIn("saved defaults are in use", button.toolTip())

    def test_held_modifier_previews_the_action_on_the_button(self):
        button, gesture = self._make(_SavingState(), Qt.ShiftModifier)
        self._hover(button)
        self.assertEqual(button.text(), "Save as Defaults")
        self.held = Qt.ControlModifier | Qt.ShiftModifier
        gesture._poll.timeout.emit()
        self.assertEqual(button.text(), "Factory Reset")
        self._hover(button)  # a second Enter with no Leave (a host grab ate it)
        self.held = Qt.NoModifier
        gesture._poll.timeout.emit()
        self.assertEqual(button.text(), "Restore Defaults", "the preview never sticks")
        QtWidgets.QApplication.sendEvent(button, QtCore.QEvent(QtCore.QEvent.Leave))
        self.assertEqual(button.text(), "Restore Defaults")
        self.assertFalse(gesture._poll.isActive(), "polling stops on leave")

    def test_click_flashes_the_result_then_restores_the_label(self):
        button, gesture = self._make(_SavingState(), Qt.ShiftModifier)
        button.click()
        self.assertEqual(button.text(), ResetGesture.RESULTS[ResetGesture.SAVE])
        gesture._flash_timer.timeout.emit()
        self.assertEqual(button.text(), "Restore Defaults")

    def test_a_state_that_cannot_save_resets_and_offers_no_preview(self):
        state = _ResetOnlyState()
        button, _ = self._make(state, Qt.ShiftModifier)
        self.assertNotIn("Shift", button.toolTip())
        self._hover(button)
        self.assertEqual(button.text(), "Restore Defaults")
        button.click()
        self.assertEqual(state.calls, [("reset", ["w"])])

    def test_on_performed_receives_the_action(self):
        seen = []
        button = self.track_widget(QtWidgets.QPushButton("Restore Defaults"))
        ResetGesture(
            button,
            _SavingState(),
            on_performed=seen.append,
            modifiers=lambda: Qt.ShiftModifier,
        )
        button.click()
        self.assertEqual(seen, [ResetGesture.SAVE])


if __name__ == "__main__":
    unittest.main(verbosity=2)
