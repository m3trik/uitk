# !/usr/bin/python
# coding=utf-8
"""Standalone test for ActionOption multi-state cycling.

Verifies:
  - State 0 icon/tooltip applied on widget creation
  - Clicking cycles through states in order
  - Per-state callbacks fire correctly
  - Fallback to top-level callback when state has no callback
  - current_state property read/write
  - set_states() after construction re-applies state 0
  - Single-state (no cycling) still works unchanged

Run:  python -m pytest test/temp_tests/test_action_multistate.py -v
"""

import sys
import unittest
from pathlib import Path

# Ensure package root is importable
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qtpy import QtWidgets, QtCore

# QApplication must exist before widget imports
_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from uitk.widgets.optionBox.options.action import ActionOption
from uitk.widgets.optionBox.utils import OptionBoxManager


class TestActionMultiState(unittest.TestCase):
    """Exercise ActionOption multi-state cycling."""

    def _make_combo(self):
        """Helper: create a QComboBox with an OptionBoxManager attached."""
        combo = QtWidgets.QComboBox()
        combo.addItems(["A", "B", "C"])
        combo.option_box = OptionBoxManager(combo)
        return combo

    # ------------------------------------------------------------------
    # Core cycling
    # ------------------------------------------------------------------
    def test_states_cycle_on_click(self):
        """Each click advances state index and wraps around."""
        log = []
        opt = ActionOption(
            states=[
                {
                    "icon": "play",
                    "tooltip": "Play",
                    "callback": lambda: log.append("play"),
                },
                {
                    "icon": "pause",
                    "tooltip": "Pause",
                    "callback": lambda: log.append("pause"),
                },
                {
                    "icon": "stop",
                    "tooltip": "Stop",
                    "callback": lambda: log.append("stop"),
                },
            ]
        )
        btn = opt.widget  # force creation

        self.assertEqual(opt.current_state, 0)
        self.assertEqual(btn.toolTip(), "Play")

        opt._handle_action()  # simulate click
        self.assertEqual(log, ["play"])
        self.assertEqual(opt.current_state, 1)
        self.assertEqual(btn.toolTip(), "Pause")

        opt._handle_action()
        self.assertEqual(log, ["play", "pause"])
        self.assertEqual(opt.current_state, 2)
        self.assertEqual(btn.toolTip(), "Stop")

        opt._handle_action()  # wraps back to 0
        self.assertEqual(log, ["play", "pause", "stop"])
        self.assertEqual(opt.current_state, 0)
        self.assertEqual(btn.toolTip(), "Play")

    # ------------------------------------------------------------------
    # State 0 visuals applied at creation
    # ------------------------------------------------------------------
    def test_state_zero_applied_on_create(self):
        """Widget should show state 0's tooltip (not the default 'Options')."""
        opt = ActionOption(
            states=[
                {"icon": "check", "tooltip": "Accept"},
                {"icon": "close", "tooltip": "Reject"},
            ]
        )
        btn = opt.widget
        self.assertEqual(btn.toolTip(), "Accept")

    # ------------------------------------------------------------------
    # Per-state callback vs fallback
    # ------------------------------------------------------------------
    def test_fallback_to_toplevel_callback(self):
        """States without 'callback' key use the top-level handler."""
        log = []
        opt = ActionOption(
            callback=lambda: log.append("fallback"),
            states=[
                {"icon": "play", "tooltip": "State A"},
                {
                    "icon": "pause",
                    "tooltip": "State B",
                    "callback": lambda: log.append("per-state"),
                },
            ],
        )
        _ = opt.widget

        opt._handle_action()  # state 0 — no per-state cb → fallback
        self.assertEqual(log, ["fallback"])

        opt._handle_action()  # state 1 — has per-state cb
        self.assertEqual(log, ["fallback", "per-state"])

    # ------------------------------------------------------------------
    # current_state property setter
    # ------------------------------------------------------------------
    def test_current_state_setter_wraps(self):
        """Setting current_state wraps around the list length."""
        opt = ActionOption(
            states=[
                {"icon": "play", "tooltip": "A"},
                {"icon": "pause", "tooltip": "B"},
                {"icon": "stop", "tooltip": "C"},
            ]
        )
        _ = opt.widget
        opt.current_state = 5  # 5 % 3 == 2
        self.assertEqual(opt.current_state, 2)
        self.assertEqual(opt.widget.toolTip(), "C")

    # ------------------------------------------------------------------
    # set_states() post-init
    # ------------------------------------------------------------------
    def test_set_states_post_init_resets_to_zero(self):
        """Calling set_states after widget exists resets to state 0."""
        opt = ActionOption(icon="settings", tooltip="Old tooltip")
        btn = opt.widget
        self.assertEqual(btn.toolTip(), "Old tooltip")

        opt.set_states(
            [
                {"icon": "play", "tooltip": "New tooltip A"},
                {"icon": "pause", "tooltip": "New tooltip B"},
            ]
        )
        self.assertEqual(opt.current_state, 0)
        self.assertEqual(btn.toolTip(), "New tooltip A")

    # ------------------------------------------------------------------
    # Single-state (no cycling) backward compatibility
    # ------------------------------------------------------------------
    def test_single_state_no_cycling(self):
        """A single-element states list executes but doesn't cycle."""
        log = []
        opt = ActionOption(
            states=[
                {"icon": "play", "tooltip": "Only", "callback": lambda: log.append("x")}
            ]
        )
        _ = opt.widget
        opt._handle_action()
        opt._handle_action()
        self.assertEqual(log, ["x", "x"])
        self.assertEqual(opt.current_state, 0)  # never advances

    # ------------------------------------------------------------------
    # No states (original behavior)
    # ------------------------------------------------------------------
    def test_no_states_classic_behavior(self):
        """Without states, behavior is identical to pre-change."""
        log = []
        opt = ActionOption(
            callback=lambda: log.append("classic"), icon="settings", tooltip="Tip"
        )
        btn = opt.widget
        self.assertEqual(btn.toolTip(), "Tip")
        opt._handle_action()
        opt._handle_action()
        self.assertEqual(log, ["classic", "classic"])
        self.assertEqual(opt.current_state, 0)

    # ------------------------------------------------------------------
    # Fluent API via OptionBoxManager
    # ------------------------------------------------------------------
    def test_manager_set_action_with_states(self):
        """OptionBoxManager.set_action forwards states to ActionOption."""
        combo = self._make_combo()
        log = []
        combo.option_box.set_action(
            states=[
                {"icon": "play", "tooltip": "Go", "callback": lambda: log.append("go")},
                {
                    "icon": "stop",
                    "tooltip": "Halt",
                    "callback": lambda: log.append("halt"),
                },
            ]
        )
        # Verify pending options contain the ActionOption with states
        pending = combo.option_box._pending_options
        self.assertEqual(len(pending), 1)
        action_opt = pending[0]
        self.assertIsNotNone(action_opt._states)
        self.assertEqual(len(action_opt._states), 2)

    # ------------------------------------------------------------------
    # None handler is harmless
    # ------------------------------------------------------------------
    def test_no_callback_no_crash(self):
        """States without any callback and no top-level handler don't crash."""
        opt = ActionOption(
            states=[
                {"icon": "play", "tooltip": "A"},
                {"icon": "pause", "tooltip": "B"},
            ]
        )
        _ = opt.widget
        opt._handle_action()  # should not raise
        self.assertEqual(opt.current_state, 1)

    # ------------------------------------------------------------------
    # Persistence across sessions
    # ------------------------------------------------------------------
    def test_state_auto_persists_via_object_name(self):
        """State auto-persists when wrapped widget has an objectName.

        Bug: ActionOption multi-state buttons always reset to state 0 on
        session restart because current_state was never persisted.
        Root cause: option box buttons are ephemeral and never registered
        with MainWindow's StateManager, so they bypassed the standard
        auto-persistence that regular widgets get for free.
        Fixed: 2026-03-26
        """
        states = [
            {"icon": "play", "tooltip": "Play"},
            {"icon": "pause", "tooltip": "Pause"},
            {"icon": "stop", "tooltip": "Stop"},
        ]

        # Create a named widget — simulates a widget from a .ui file
        host = QtWidgets.QComboBox()
        host.setObjectName("_test_auto_persist_combo")

        # First instance: cycle to state 2
        opt1 = ActionOption(wrapped_widget=host, states=states)
        _ = opt1.widget
        opt1.current_state = 2
        self.assertEqual(opt1.current_state, 2)

        # Second instance with same wrapped widget — should restore state 2
        opt2 = ActionOption(wrapped_widget=host, states=states)
        btn2 = opt2.widget
        self.assertEqual(opt2.current_state, 2)
        self.assertEqual(btn2.toolTip(), "Stop")

        # Clean up
        opt2._settings.clear()

    def test_explicit_settings_key_overrides_auto(self):
        """An explicit settings_key takes precedence over objectName."""
        key = "_test_explicit_key"
        states = [
            {"icon": "play", "tooltip": "Play"},
            {"icon": "pause", "tooltip": "Pause"},
        ]
        host = QtWidgets.QComboBox()
        host.setObjectName("should_not_use_this_name")

        opt = ActionOption(wrapped_widget=host, states=states, settings_key=key)
        self.assertIsNotNone(opt._settings)
        self.assertEqual(opt._settings.namespace, key)
        opt._settings.clear()

    def test_no_object_name_no_persistence(self):
        """Without objectName or settings_key, state doesn't persist."""
        states = [
            {"icon": "play", "tooltip": "Play"},
            {"icon": "pause", "tooltip": "Pause"},
        ]
        # Widget with no objectName
        opt = ActionOption(states=states)
        _ = opt.widget
        self.assertIsNone(opt._settings)

    def test_settings_key_false_disables_persistence(self):
        """Passing settings_key=False disables auto-persistence."""
        states = [
            {"icon": "play", "tooltip": "Play"},
            {"icon": "pause", "tooltip": "Pause"},
        ]
        host = QtWidgets.QComboBox()
        host.setObjectName("_test_should_not_persist")

        opt = ActionOption(wrapped_widget=host, states=states, settings_key=False)
        self.assertIsNone(opt._settings)

    def test_manager_auto_persists_named_widget(self):
        """OptionBoxManager.set_action auto-persists for named widgets."""
        combo = QtWidgets.QComboBox()
        combo.setObjectName("_test_mgr_auto")
        combo.addItems(["A", "B", "C"])
        combo.option_box = OptionBoxManager(combo)
        combo.option_box.set_action(
            states=[
                {"icon": "play", "tooltip": "Play"},
                {"icon": "pause", "tooltip": "Pause"},
            ],
        )
        action_opts = [
            o for o in combo.option_box._pending_options if isinstance(o, ActionOption)
        ]
        self.assertEqual(len(action_opts), 1)
        self.assertIsNotNone(action_opts[0]._settings)
        action_opts[0]._settings.clear()


if __name__ == "__main__":
    unittest.main()
