# !/usr/bin/python
# coding=utf-8
"""Unit tests for SpinBox widget.

This module tests SpinBox functionality including:
- Value behavior (int vs float based on decimals)
- Custom display value mapping
- Text/value conversion
- Input validation with custom strings
- Step-by grid snapping (min/max boundary recovery)
- Ctrl/Alt modifier step adjustments

Run standalone: python -m pytest test/test_spinbox.py -v
"""

import unittest
from unittest.mock import MagicMock, patch

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore, QtGui


# =============================================================================
# Value Behavior Tests
# =============================================================================


class TestSpinBoxValueBehavior(QtBaseTestCase):
    """Tests for SpinBox value type based on decimals setting."""

    def test_returns_int_when_decimals_zero(self):
        """Should return integer when decimals is 0 (default)."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setRange(-100, 100)
        sb.setValue(42)

        self.assertIsInstance(sb.value(), int)
        self.assertEqual(sb.value(), 42)

    def test_returns_float_when_decimals_positive(self):
        """Should return float when decimals > 0."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setDecimals(2)
        sb.setRange(-100, 100)
        sb.setValue(42.5)

        self.assertIsInstance(sb.value(), float)
        self.assertAlmostEqual(sb.value(), 42.5)

    def test_default_decimals_is_zero(self):
        """Should default to 0 decimals (integer behavior)."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        self.assertEqual(sb.decimals(), 0)

    def test_sets_class_property(self):
        """Should set class property to 'SpinBox'."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        self.assertEqual(sb.property("class"), "SpinBox")


# =============================================================================
# Custom Display Value Tests
# =============================================================================


class TestSpinBoxCustomDisplay(QtBaseTestCase):
    """Tests for custom value-to-display-text mapping."""

    def test_set_custom_display_with_dict(self):
        """Should accept dict mapping values to display strings."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setDecimals(1)
        sb.setRange(-1, 100)
        sb.setCustomDisplayValues({-1: "Auto", 0: "Off"})

        self.assertIn(-1.0, sb._custom_display_map)
        self.assertEqual(sb._custom_display_map[-1.0], "Auto")
        self.assertEqual(sb._custom_display_map[0.0], "Off")

    def test_set_custom_display_with_two_args(self):
        """Should accept (value, label) pair."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setDecimals(1)
        sb.setRange(-1, 100)
        sb.setCustomDisplayValues(-1, "Auto")

        self.assertEqual(sb._custom_display_map[-1.0], "Auto")

    def test_text_from_value_uses_custom_map(self):
        """Should display custom text for mapped values."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setDecimals(1)
        sb.setRange(-1, 100)
        sb.setCustomDisplayValues({-1: "Auto"})

        self.assertEqual(sb.textFromValue(-1), "Auto")

    def test_text_from_value_formats_normal_values(self):
        """Should use ':g' formatting for non-mapped values."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setDecimals(2)
        sb.setRange(-100, 100)

        self.assertEqual(sb.textFromValue(42.0), "42")
        self.assertEqual(sb.textFromValue(3.14), "3.14")

    def test_value_from_text_uses_custom_map(self):
        """Should resolve custom display text back to value."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setDecimals(1)
        sb.setRange(-1, 100)
        sb.setCustomDisplayValues({-1: "Auto"})

        self.assertAlmostEqual(sb.valueFromText("Auto"), -1.0)


# =============================================================================
# Validation Tests
# =============================================================================


class TestSpinBoxValidation(QtBaseTestCase):
    """Tests for input validation with custom display strings."""

    def test_validates_custom_string_as_acceptable(self):
        """Full custom display string should be Acceptable."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setDecimals(1)
        sb.setRange(-1, 100)
        sb.setCustomDisplayValues({-1: "Auto"})

        state, _, _ = sb.validate("Auto", 4)
        self.assertEqual(state, QtGui.QValidator.Acceptable)

    def test_validates_partial_custom_string_as_intermediate(self):
        """Partial match of custom string should be Intermediate."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setDecimals(1)
        sb.setRange(-1, 100)
        sb.setCustomDisplayValues({-1: "Auto"})

        state, _, _ = sb.validate("Au", 2)
        self.assertEqual(state, QtGui.QValidator.Intermediate)


# =============================================================================
# stepBy Grid Snapping Tests
# =============================================================================


class TestSpinBoxStepByGridSnapping(QtBaseTestCase):
    """Tests for stepBy snapping to the step-size grid after min/max clamping.

    Bug: When a spinbox with step=1 and min=0.1 stepped down from 1 to the
    min (0.1), subsequent steps up produced 1.1, 2.1, 3.1 instead of 1, 2, 3.
    Fixed: 2026-03-25 — stepBy now snaps off-grid values to the nearest
    grid-aligned value in the stepping direction.
    """

    def _make_spinbox(self, value, step=1, min_val=0.1, max_val=100, decimals=1):
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setDecimals(decimals)
        sb.setRange(min_val, max_val)
        sb.setSingleStep(step)
        sb.setValue(value)
        return sb

    def test_step_down_to_min_then_up_snaps_to_grid(self):
        """Stepping up from off-grid min should snap to next grid value.

        Sequence: 5→4→3→2→1→0.1 (clamped), then up: 0.1→1→2→3
        NOT: 0.1→1.1→2.1→3.1
        """
        sb = self._make_spinbox(value=5, step=1, min_val=0.1)

        # Step down: 5→4→3→2→1
        for expected in [4, 3, 2, 1]:
            sb.stepBy(-1)
            self.assertAlmostEqual(sb.value(), expected, places=5)

        # Step down to min (clamped to 0.1)
        sb.stepBy(-1)
        self.assertAlmostEqual(sb.value(), 0.1, places=5)

        # Step back up: should snap to grid (1, 2, 3)
        sb.stepBy(1)
        self.assertAlmostEqual(
            sb.value(), 1.0, places=5, msg="First step up from 0.1 should snap to 1.0"
        )

        sb.stepBy(1)
        self.assertAlmostEqual(sb.value(), 2.0, places=5)

        sb.stepBy(1)
        self.assertAlmostEqual(sb.value(), 3.0, places=5)

    def test_step_up_to_max_then_down_snaps_to_grid(self):
        """Stepping down from off-grid max should snap to next grid value.

        With max=4.7, step=1: 1→2→3→4→4.7 (clamped), then down: 4.7→4→3→2
        """
        sb = self._make_spinbox(value=1, step=1, min_val=0, max_val=4.7)

        # Step up: 1→2→3→4
        for expected in [2, 3, 4]:
            sb.stepBy(1)
            self.assertAlmostEqual(sb.value(), expected, places=5)

        # Step up to max (clamped to 4.7)
        sb.stepBy(1)
        self.assertAlmostEqual(sb.value(), 4.7, places=5)

        # Step back down: should snap to 4, not 3.7
        sb.stepBy(-1)
        self.assertAlmostEqual(
            sb.value(),
            4.0,
            places=5,
            msg="First step down from 4.7 should snap to 4.0",
        )

        sb.stepBy(-1)
        self.assertAlmostEqual(sb.value(), 3.0, places=5)

    def test_on_grid_stepping_unchanged(self):
        """Normal on-grid stepping should work as before."""
        sb = self._make_spinbox(value=5, step=1, min_val=0, max_val=10)

        sb.stepBy(1)
        self.assertAlmostEqual(sb.value(), 6.0, places=5)

        sb.stepBy(-1)
        self.assertAlmostEqual(sb.value(), 5.0, places=5)

    def test_fractional_step_on_grid(self):
        """Fractional step sizes should also stay on grid."""
        sb = self._make_spinbox(value=1.0, step=0.5, min_val=0, max_val=10, decimals=2)

        sb.stepBy(1)
        self.assertAlmostEqual(sb.value(), 1.5, places=5)

        sb.stepBy(1)
        self.assertAlmostEqual(sb.value(), 2.0, places=5)

        sb.stepBy(-1)
        self.assertAlmostEqual(sb.value(), 1.5, places=5)

    def test_off_grid_manual_entry_snaps_on_step(self):
        """Manually entered off-grid values should snap on next step."""
        sb = self._make_spinbox(value=3.3, step=1, min_val=0, max_val=10)

        # Step up from 3.3 → should snap to 4.0
        sb.stepBy(1)
        self.assertAlmostEqual(
            sb.value(), 4.0, places=5, msg="Step up from 3.3 should snap to 4.0"
        )

        # Step down from 4.0 → 3.0 (on grid now)
        sb.stepBy(-1)
        self.assertAlmostEqual(sb.value(), 3.0, places=5)

    def test_off_grid_manual_entry_step_down_snaps(self):
        """Stepping down from a manually-entered off-grid value should snap."""
        sb = self._make_spinbox(value=3.3, step=1, min_val=0, max_val=10)

        # Step down from 3.3 → should snap to 3.0
        sb.stepBy(-1)
        self.assertAlmostEqual(
            sb.value(), 3.0, places=5, msg="Step down from 3.3 should snap to 3.0"
        )

    def test_value_at_min_step_down_stays_at_min(self):
        """Stepping down when already at min should not go below min."""
        sb = self._make_spinbox(value=0.1, step=1, min_val=0.1, max_val=10)

        sb.stepBy(-1)
        self.assertAlmostEqual(
            sb.value(), 0.1, places=5, msg="Should stay at min when stepping down"
        )

    def test_value_at_max_step_up_stays_at_max(self):
        """Stepping up when already at max should not go above max."""
        sb = self._make_spinbox(value=100, step=1, min_val=0, max_val=100)

        sb.stepBy(1)
        self.assertAlmostEqual(
            sb.value(), 100.0, places=5, msg="Should stay at max when stepping up"
        )

    def test_multiple_steps_at_once(self):
        """stepBy with steps > 1 should work correctly."""
        sb = self._make_spinbox(value=2, step=1, min_val=0, max_val=10)

        sb.stepBy(3)
        self.assertAlmostEqual(sb.value(), 5.0, places=5)

        sb.stepBy(-2)
        self.assertAlmostEqual(sb.value(), 3.0, places=5)

    def test_multiple_steps_from_off_grid(self):
        """Multiple steps from off-grid value should snap and apply remaining."""
        sb = self._make_spinbox(value=0.1, step=1, min_val=0.1, max_val=10)

        # stepBy(3) from 0.1 → ceil(0.1)=1, (1 + 3 - 1) * 1 = 3.0
        sb.stepBy(3)
        self.assertAlmostEqual(sb.value(), 3.0, places=5)


# =============================================================================
# Large/Small Step Modifier Tests
# =============================================================================


class TestSpinBoxModifierSteps(QtBaseTestCase):
    """Tests for Ctrl and Ctrl+Alt step multipliers."""

    def _make_spinbox(self, value=5, step=1, decimals=1):
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setDecimals(decimals)
        sb.setRange(-100, 100)
        sb.setSingleStep(step)
        sb.setValue(value)
        return sb

    def _make_wheel_event(self, delta=120):
        """Create a mock wheel event with the given delta."""
        event = MagicMock()
        event.delta.return_value = delta
        return event

    def test_ctrl_wheel_up_steps_by_10x(self):
        """Ctrl+wheel up should increase by 10x the single step."""
        sb = self._make_spinbox(value=5, step=1)
        event = self._make_wheel_event(delta=120)

        sb.increaseValueWithLargeStep(event)
        self.assertAlmostEqual(sb.value(), 15.0, places=5)

    def test_ctrl_wheel_down_steps_by_10x(self):
        """Ctrl+wheel down should decrease by 10x the single step."""
        sb = self._make_spinbox(value=50, step=1)
        event = self._make_wheel_event(delta=-120)

        sb.increaseValueWithLargeStep(event)
        self.assertAlmostEqual(sb.value(), 40.0, places=5)

    def test_ctrl_alt_wheel_up_steps_by_tenth(self):
        """Ctrl+Alt+wheel up should increase by 1/10th the single step."""
        sb = self._make_spinbox(value=5, step=1)
        event = self._make_wheel_event(delta=120)

        sb.decreaseValueWithSmallStep(event)
        self.assertAlmostEqual(sb.value(), 5.1, places=5)

    def test_ctrl_alt_wheel_down_steps_by_tenth(self):
        """Ctrl+Alt+wheel down should decrease by 1/10th the single step."""
        sb = self._make_spinbox(value=5, step=1)
        event = self._make_wheel_event(delta=-120)

        sb.decreaseValueWithSmallStep(event)
        self.assertAlmostEqual(sb.value(), 4.9, places=5)


# =============================================================================
# Prefix Tests
# =============================================================================


class TestSpinBoxPrefix(QtBaseTestCase):
    """Tests for prefix formatting."""

    def test_prefix_adds_tab(self):
        """setPrefix should append a tab character after the prefix text."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setPrefix("Value:")
        self.assertEqual(sb.prefix(), "Value:\t")


if __name__ == "__main__":
    unittest.main()
