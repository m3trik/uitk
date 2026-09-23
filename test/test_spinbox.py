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
from unittest.mock import MagicMock

from conftest import (
    QtBaseTestCase,
    QtWait,
    rendered_text_width,
    setup_qt_application,
)

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets


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
    """Tests for the symmetric modifier ladder.

    Ladder under test (Ctrl scales up, Alt scales down, stacking
    amplifies)::

        Ctrl          singleStep × 10
        Ctrl+Shift    singleStep × 100
        Alt           singleStep / 10          (fine)
        Ctrl+Alt      10 ** -decimals          (smallest)
    """

    def _make_spinbox(self, value=5, step=1, decimals=1):
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setDecimals(decimals)
        sb.setRange(-100, 100)
        sb.setSingleStep(step)
        sb.setValue(value)
        return sb

    def _make_wheel_event(self, delta=120, modifiers=None, axis="y"):
        """Create a mock wheel event with delta on the given axis.

        ``axis="x"`` puts the delta on ``angleDelta().x()`` with ``.y()`` at
        zero -- simulates the Alt-held axis transpose observed on some
        platforms / Qt6 builds.

        The position sits ON the value: the ladder is what these tests are
        about, and the position gate (TestSpinBoxWheelPositionGate) would
        otherwise decide their outcome for them.
        """

        event = MagicMock()
        event.position.return_value = QtCore.QPointF(6.0, 8.0)
        if axis == "x":
            event.angleDelta.return_value.x.return_value = delta
            event.angleDelta.return_value.y.return_value = 0
        else:
            event.angleDelta.return_value.x.return_value = 0
            event.angleDelta.return_value.y.return_value = delta
        event.modifiers.return_value = (
            modifiers if modifiers is not None else QtCore.Qt.NoModifier
        )
        return event

    # ---- Ctrl ladder ---------------------------------------------------

    def test_ctrl_wheel_up_steps_by_10x(self):

        sb = self._make_spinbox(value=5, step=1)
        event = self._make_wheel_event(delta=120, modifiers=QtCore.Qt.ControlModifier)
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 15.0, places=5)

    def test_ctrl_wheel_down_steps_by_10x(self):

        sb = self._make_spinbox(value=50, step=1)
        event = self._make_wheel_event(delta=-120, modifiers=QtCore.Qt.ControlModifier)
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 40.0, places=5)

    def test_ctrl_shift_wheel_steps_by_100x(self):

        sb = self._make_spinbox(value=5, step=1)
        sb.setRange(-1000, 1000)  # widen so 5 + 100 doesn't clamp
        event = self._make_wheel_event(
            delta=120,
            modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier,
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 105.0, places=5)

    # ---- Alt = singleStep / 10 (fine) ---------------------------------

    def test_alt_wheel_up_steps_by_singleStep_over_10(self):
        """Alt+wheel up: step the value by ``singleStep / 10``."""

        sb = self._make_spinbox(value=5, step=1, decimals=3)
        event = self._make_wheel_event(delta=120, modifiers=QtCore.Qt.AltModifier)
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.1, places=5)

    def test_alt_wheel_down_steps_by_singleStep_over_10(self):

        sb = self._make_spinbox(value=5, step=1, decimals=3)
        event = self._make_wheel_event(delta=-120, modifiers=QtCore.Qt.AltModifier)
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 4.9, places=5)

    def test_alt_wheel_does_not_mutate_single_step(self):
        """Alt+wheel must step the *value*, not the widget's ``singleStep``
        setting (the original pre-symmetric-ladder behaviour).
        """

        sb = self._make_spinbox(value=5, step=1, decimals=3)
        before_step = sb.singleStep()
        event = self._make_wheel_event(delta=120, modifiers=QtCore.Qt.AltModifier)
        sb.wheelEvent(event)
        self.assertEqual(sb.singleStep(), before_step)

    # ---- Ctrl+Alt = 10**-decimals (smallest) --------------------------

    def test_ctrl_alt_wheel_up_steps_by_smallest(self):
        """Ctrl+Alt+wheel up: step by ``10**-decimals`` (smallest)."""

        sb = self._make_spinbox(value=5, step=1, decimals=4)
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.0001, places=6)

    def test_ctrl_alt_wheel_down_steps_by_smallest(self):

        sb = self._make_spinbox(value=5, step=1, decimals=4)
        event = self._make_wheel_event(
            delta=-120, modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 4.9999, places=6)

    def test_alt_wheel_on_int_spinbox_is_no_op(self):
        """Alt+wheel on an int-precision spin-box (``decimals == 0``)
        does nothing: ``singleStep / 10 == 0.1`` is below the integer
        precision floor (``10**-0 == 1``). The mixin must detect this
        and skip ``setValue`` entirely -- otherwise the internal
        ``QDoubleSpinBox`` storage drifts to ``+0.1`` of the visible
        integer while the display stays put, and the HUD lies about a
        step happening.
        """

        sb = self._make_spinbox(value=5, step=1, decimals=0)
        # Drive the underlying QDoubleSpinBox directly so we can detect
        # any internal drift below the integer threshold.
        from qtpy.QtWidgets import QDoubleSpinBox

        QDoubleSpinBox.setValue(sb, 5.0)

        event = self._make_wheel_event(delta=120, modifiers=QtCore.Qt.AltModifier)
        sb.wheelEvent(event)

        self.assertEqual(sb.value(), 5)
        self.assertEqual(QDoubleSpinBox.value(sb), 5.0)

    def test_ctrl_alt_smaller_than_alt(self):
        """Ladder ordering invariant: ``Ctrl+Alt`` must produce a step
        strictly smaller than ``Alt`` alone. This is the contract the
        user expects -- adding ``Ctrl`` to ``Alt`` makes the gesture
        *finer*, not the same as ``Ctrl`` alone (the regression we
        rolled the snap-to-integer back to fix).
        """

        sb = self._make_spinbox(value=5, step=1, decimals=4)
        # Alt alone
        sb.setValue(5)
        event_alt = self._make_wheel_event(delta=120, modifiers=QtCore.Qt.AltModifier)
        sb.wheelEvent(event_alt)
        delta_alt = sb.value() - 5
        # Ctrl+Alt
        sb.setValue(5)
        event_ca = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event_ca)
        delta_ca = sb.value() - 5

        self.assertGreater(delta_alt, delta_ca)

    # ---- axis-swap fallback -------------------------------------------

    def test_alt_wheel_reads_x_axis_when_y_is_zero(self):
        """Alt+wheel on the transposed axis must still step the value
        (mirror of the Ctrl+Alt axis-swap test).
        """

        sb = self._make_spinbox(value=5, step=1, decimals=4)
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.AltModifier, axis="x"
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.1, places=5)

    def test_ctrl_alt_wheel_reads_x_axis_when_y_is_zero(self):
        """Alt-held wheel events arrive on .x() rather than .y() on some Qt
        builds / platforms (X11, certain Qt6 builds). The mixin must read
        whichever axis carries the delta or Ctrl+Alt silently no-ops --
        the regression we hit in real use even though the y-only test
        passed.
        """

        sb = self._make_spinbox(value=5, step=1, decimals=4)
        event = self._make_wheel_event(
            delta=120,
            modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier,
            axis="x",
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.0001, places=6)


# =============================================================================
# Wheel Position Gate Tests
# =============================================================================


class TestSpinBoxWheelPositionGate(QtBaseTestCase):
    """The wheel steps only where it lands on (or near) the drawn value.

    A field stretched by its layout is mostly empty space, and a wheel out
    there belongs to whatever scrolls behind the box -- the panel it sits in
    -- not to a value the cursor was only passing over. Only where there IS
    something to scroll: in a panel that cannot, the box keeps the wheel.
    """

    VALUE = 5
    WIDTH = 400
    #: Well right of the number (which draws in the first ~15 px) and well
    #: left of the step arrows: field, and nothing else.
    EMPTY_FIELD_X = 200

    def _make_spinbox(self, width=None, scrollable=True):
        """A SpinBox *width* px wide in a panel that can scroll -- the case
        the gate exists for -- or, with *scrollable* False, in one that
        cannot."""
        from uitk.widgets.spinBox import SpinBox

        sb = SpinBox()
        sb.setRange(-100, 100)
        sb.setSingleStep(1)
        sb.setValue(self.VALUE)
        sb.setFixedWidth(width or self.WIDTH)
        if scrollable:
            host = self.track_widget(QtWidgets.QScrollArea())
            inner = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(inner)
            layout.addWidget(sb)
            for _ in range(40):  # rows enough to give the area a range
                layout.addWidget(QtWidgets.QLabel("row"))
            host.setWidget(inner)
            host.setWidgetResizable(True)
            host.resize((width or self.WIDTH) + 40, 120)
        else:
            host = self.track_widget(QtWidgets.QWidget())
            QtWidgets.QVBoxLayout(host).addWidget(sb)
        host.show()
        QtWait.pump()
        return sb

    def _wheel_at(self, widget, x, modifiers=QtCore.Qt.NoModifier, delta=120):
        """A real ``QWheelEvent`` *x* px across *widget* (local coords).

        Real rather than mocked: the gate reads ``event.position()``, so a
        mock would only be testing the mock's idea of where the cursor was.
        """
        local = QtCore.QPointF(x, widget.height() / 2)
        return QtGui.QWheelEvent(
            local,
            QtCore.QPointF(widget.mapToGlobal(local.toPoint())),
            QtCore.QPoint(0, 0),
            QtCore.QPoint(0, delta),
            QtCore.Qt.NoButton,
            modifiers,
            QtCore.Qt.NoScrollPhase,
            False,
        )

    def test_wheel_on_the_value_steps(self):
        sb = self._make_spinbox()
        event = self._wheel_at(sb, 8)

        sb.wheelEvent(event)

        self.assertEqual(sb.value(), self.VALUE + 1)
        self.assertTrue(event.isAccepted())

    def test_wheel_out_on_the_empty_field_is_left_for_the_parent(self):
        """Unaccepted is the whole contract: Qt walks an ignored wheel up the
        parent chain, which is how the panel behind the box gets to scroll."""
        sb = self._make_spinbox()
        event = self._wheel_at(sb, self.EMPTY_FIELD_X)

        sb.wheelEvent(event)

        self.assertEqual(sb.value(), self.VALUE)
        self.assertFalse(event.isAccepted())

    def test_modifier_wheel_out_on_the_empty_field_is_left_too(self):
        """One rule for every wheel: position decides whether there is a step
        at all, the modifier ladder only picks its size."""
        sb = self._make_spinbox()
        event = self._wheel_at(sb, self.EMPTY_FIELD_X, QtCore.Qt.ControlModifier)

        sb.wheelEvent(event)

        self.assertEqual(sb.value(), self.VALUE)
        self.assertFalse(event.isAccepted())

    def test_wheel_over_the_step_arrows_steps(self):
        """The arrows are a value affordance however far they sit from the
        number, so the zone covers the box's chrome as well."""
        sb = self._make_spinbox()
        editor = sb.lineEdit()
        if editor.x() + editor.width() >= sb.width():
            self.skipTest("this style leaves the box no chrome to aim at")
        event = self._wheel_at(sb, sb.width() - 2)

        sb.wheelEvent(event)

        self.assertEqual(sb.value(), self.VALUE + 1)

    def test_a_box_with_no_room_beside_its_value_takes_every_wheel(self):
        """70 px is what the ecosystem's panels actually author for a spin box
        (32 explicit ones across mayatk / tentacle / blendertk; the rest are
        sized by their layout). A box that size has no field to aim at beside
        its value, so it reads as one target and keeps every wheel -- without
        that, half of every standard panel field would have gone deaf while
        only the stretched ones were meant to change.

        The house width is swept rather than sampled: "takes every wheel" is
        the claim, and a single x would pass on whichever rule happened to
        answer. The second half then pins ``_AIMABLE_FIELD_PX`` on its own, at
        a width where the margin does not reach and with the aim point kept
        clear of the chrome escape hatch at the far edge -- otherwise the case
        could quietly stop testing the threshold and still pass. The wide box
        is its control: it proves that x really is past the value's margin.
        """
        house = self._make_spinbox(width=70)
        for x in range(0, house.width(), 5):
            house.setValue(self.VALUE)
            house.wheelEvent(self._wheel_at(house, x))
            self.assertEqual(house.value(), self.VALUE + 1, f"deaf at x={x}")

        boxed = self._make_spinbox(width=110)
        editor = boxed.lineEdit()
        # Three-quarters across the editor: clear of the value's margin on
        # one side and of the step arrows on the other, so only the threshold
        # can answer.
        x = editor.x() + (editor.width() * 3) // 4

        wide = self._make_spinbox()
        control = self._wheel_at(wide, x)
        wide.wheelEvent(control)
        self.assertFalse(control.isAccepted(), "fixture x is not past the value")

        event = self._wheel_at(boxed, x)
        boxed.wheelEvent(event)

        self.assertEqual(boxed.value(), self.VALUE + 1)

    def test_the_zone_follows_the_prefix_tab_column(self):
        """A tab-separated prefix puts the value at a tab STOP, tens of px
        right of the label's own advance. Measured with QFontMetrics instead,
        the zone would sit over the label and miss the number entirely."""
        sb = self._make_spinbox()
        sb.setPrefix("Bias:")
        QtWait.pump()

        on_label = self._wheel_at(sb, 20)
        sb.wheelEvent(on_label)
        self.assertEqual(sb.value(), self.VALUE, "the label is not the value")

        on_value = self._wheel_at(sb, 88)
        sb.wheelEvent(on_value)
        self.assertEqual(sb.value(), self.VALUE + 1)

    def test_with_nothing_to_scroll_the_box_keeps_every_wheel(self):
        """Most panels have no scroll area: a wheel left for the parent there
        went nowhere, and most of a stretched field went dead -- 55 of 75
        sampled x positions on a 298 px box did nothing at all."""
        sb = self._make_spinbox(scrollable=False)
        for x in range(0, sb.width(), 10):
            sb.setValue(self.VALUE)
            event = self._wheel_at(sb, x)
            sb.wheelEvent(event)
            self.assertEqual(sb.value(), self.VALUE + 1, f"dead at x={x}")

    def test_a_right_aligned_value_is_gated_from_its_own_side(self):
        """The field's room was measured to the RIGHT of the value only, so a
        right-aligned value -- its empty field on the left -- was never gated."""
        sb = self._make_spinbox()
        sb.setAlignment(QtCore.Qt.AlignRight)
        QtWait.pump()
        start, end, chrome, field = sb._value_span()

        far = self._wheel_at(sb, field + 20)
        sb.wheelEvent(far)
        self.assertEqual(sb.value(), self.VALUE)
        self.assertFalse(far.isAccepted())

        near = self._wheel_at(sb, (start + end) / 2)
        sb.wheelEvent(near)
        self.assertEqual(sb.value(), self.VALUE + 1)

    def test_widening_the_margin_does_not_turn_the_gate_off(self):
        """The threshold is px of field beside the value, and the margin is
        the slack around it -- a wider margin asks for an easier target. It
        was measured PAST the margin, so ``wheel_margin=100`` on a 150 px box
        switched the gate off entirely."""
        sb = self._make_spinbox(width=150)
        sb.wheel_margin = 100
        start, end, chrome, field = sb._value_span()
        x = end + sb.wheel_margin + 8
        if x >= chrome:
            self.skipTest("this style leaves no field past the widened zone")

        event = self._wheel_at(sb, x)
        sb.wheelEvent(event)

        self.assertEqual(sb.value(), self.VALUE)
        self.assertFalse(event.isAccepted())

    def test_a_read_only_box_takes_no_modified_step(self):
        """Qt's own wheel never steps a read-only box; the modifier ladder
        wrote the value around that rule (Ctrl+wheel went 5 -> 15)."""
        sb = self._make_spinbox(scrollable=False)
        sb.setReadOnly(True)
        for modifiers in (
            QtCore.Qt.NoModifier,
            QtCore.Qt.ControlModifier,
            QtCore.Qt.AltModifier | QtCore.Qt.ControlModifier,
        ):
            event = self._wheel_at(sb, 8, modifiers)
            sb.wheelEvent(event)
            self.assertEqual(sb.value(), self.VALUE, modifiers)

    def test_wheel_margin_none_steps_anywhere_on_the_box(self):
        """Opt-out, through the declarative path a dict-built panel uses --
        and through the constructor, which is the same path and is what the
        docs promise."""
        from uitk.widgets.spinBox import SpinBox

        self.assertIsNone(self.track_widget(SpinBox(wheel_margin=None)).wheel_margin)

        sb = self._make_spinbox()
        sb.set_attributes(wheel_margin=None)
        self.assertIsNone(sb.wheel_margin)

        event = self._wheel_at(sb, self.EMPTY_FIELD_X)
        sb.wheelEvent(event)

        self.assertEqual(sb.value(), self.VALUE + 1)
        self.assertTrue(event.isAccepted())

    def test_a_wider_margin_widens_the_zone(self):
        sb = self._make_spinbox()
        sb.wheel_margin = 300

        event = self._wheel_at(sb, self.EMPTY_FIELD_X)
        sb.wheelEvent(event)

        self.assertEqual(sb.value(), self.VALUE + 1)

    def test_the_box_never_swallows_what_the_panel_should_get(self):
        """The handover itself is Qt's: an unaccepted wheel walks up the
        parent chain to whatever scrolls (``QWidget::wheelEvent`` -- "it is
        very important that you ignore() the event if you do not handle it,
        so that the widget's parent can interpret it").

        That walk cannot be driven from in-process: it runs for SPONTANEOUS
        events, the ones the window system delivers. Measured under the
        offscreen QPA, a wheel pushed through ``QApplication.sendEvent`` --
        at the box, or at its window -- never reaches the scroll area, and a
        plain ``QLabel`` in the same fixture behaves identically (the same
        event sent straight at the viewport does scroll it). So this pins the
        half that is this widget's to keep: parked over the empty field, in a
        panel that has somewhere to scroll, the box takes nothing.
        """
        from uitk.widgets.spinBox import SpinBox

        area = self.track_widget(QtWidgets.QScrollArea())
        inner = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(inner)
        sb = SpinBox()
        sb.setRange(-100, 100)
        sb.setSingleStep(1)
        sb.setValue(self.VALUE)
        layout.addWidget(sb)
        for _ in range(40):  # enough rows to give the area something to scroll
            layout.addWidget(QtWidgets.QLabel("row"))
        area.setWidget(inner)
        area.setWidgetResizable(True)
        area.resize(self.WIDTH + 20, 120)
        area.show()
        QtWait.pump()
        self.assertGreater(
            area.verticalScrollBar().maximum(), 0, "fixture never became scrollable"
        )

        event = self._wheel_at(sb, self.EMPTY_FIELD_X, delta=-120)
        sb.wheelEvent(event)

        self.assertEqual(sb.value(), self.VALUE)
        self.assertFalse(event.isAccepted())


# =============================================================================
# Prefix Tests
# =============================================================================


class TestAttributeWindowIntUsesUitkSpinBox(QtBaseTestCase):
    """AttributeWindow int rows should use the uitk SpinBox so modifier-driven
    wheel stepping works there too. Pinning this prevents a quiet revert to
    plain QSpinBox during future factory refactors.
    """

    def test_build_int_returns_uitk_spinbox(self):
        from uitk.bridge.spec import AttributeSpec, KindFactory
        from uitk.widgets.spinBox import SpinBox

        spec = AttributeSpec(key="count", kind="int", default=3)
        widget = self.track_widget(KindFactory.make_widget(spec))
        self.assertIsInstance(widget, SpinBox)
        # SpinBox returns int when decimals == 0
        self.assertEqual(widget.value(), 3)
        self.assertIsInstance(widget.value(), int)

    def test_build_int_wheel_modifiers_dispatch(self):
        """Ctrl+Alt+wheel on an AttributeWindow int row should step by
        ``10**-decimals == 1`` (the smallest representable int step).
        Smoke-tests that the SpinBox swap actually wires up the modifier
        dispatch on a real factory-built widget.
        """
        from unittest.mock import MagicMock
        from uitk.bridge.spec import AttributeSpec, KindFactory

        spec = AttributeSpec(
            key="count", kind="int", default=5, minimum=-100, maximum=100
        )
        widget = self.track_widget(KindFactory.make_widget(spec))
        widget.setSingleStep(1)

        event = MagicMock()
        event.angleDelta.return_value.x.return_value = 0
        event.angleDelta.return_value.y.return_value = 120
        event.modifiers.return_value = QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
        event.position.return_value = QtCore.QPointF(6.0, 8.0)  # on the value

        widget.wheelEvent(event)
        self.assertEqual(widget.value(), 6)


class TestSpinBoxPrefix(QtBaseTestCase):
    """Tests for prefix formatting."""

    def test_prefix_adds_tab(self):
        """setPrefix should append a tab character after the prefix text."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setPrefix("Value:")
        self.assertEqual(sb.prefix(), "Value:\t")

    def test_prefix_is_idempotent(self):
        """A ``.ui`` round-trip replays the stored, already-tab-suffixed string
        through setPrefix — the label must not grow a tab stop each time."""
        from uitk.widgets.spinBox import SpinBox

        sb = self.track_widget(SpinBox())
        sb.setPrefix("Value:")
        sb.setPrefix(sb.prefix())
        self.assertEqual(sb.prefix(), "Value:\t")
        self.assertEqual(sb.prefix_label(), "Value:")

    def test_narrow_field_keeps_the_value_visible(self):
        """PrefixColumnMixin reaches SpinBox too (its own MRO). See
        test_double_spin_box.TestPrefixColumn for the full contract."""
        from qtpy import QtWidgets
        from uitk.widgets.spinBox import SpinBox

        # Hosted, and started wide: a top-level widget's resize is negotiated
        # with the platform window, which offscreen honors only sometimes — a
        # silently clamped one leaves the assertion measuring nothing.
        host = self.track_widget(QtWidgets.QWidget())
        host.resize(600, 80)
        sb = SpinBox(host)
        sb.setDecimals(3)
        sb.setRange(0.0, 1.0)
        sb.setPrefix("Value:")
        sb.setValue(0.5)
        sb.resize(500, sb.sizeHint().height())
        host.show()
        app.processEvents()

        compact = sb.fontMetrics().horizontalAdvance("Value: 0.5")
        chrome = sb.width() - sb.lineEdit().width()
        sb.setFixedWidth(int(chrome + compact + 6))
        app.processEvents()
        self.assertEqual(sb.lineEdit().width(), compact + 6)  # the resize landed

        rendered = rendered_text_width(sb.lineEdit().text(), sb.font())
        self.assertLessEqual(rendered, sb.lineEdit().width())


class TestSpinBoxTextColor(QtBaseTestCase):
    """SpinBoxTextColorMixin.set_text_color is shared with DoubleSpinBox."""

    def _make(self):
        from uitk.widgets.spinBox import SpinBox

        return self.track_widget(SpinBox())

    def test_set_and_clear_text_color(self):
        sb = self._make()
        self.assertIsNone(sb.text_color())
        sb.set_text_color("#55aaff")
        self.assertEqual(sb.text_color(), "#55aaff")
        self.assertIn("color: #55aaff;", sb.styleSheet())
        sb.set_text_color(None)
        self.assertIsNone(sb.text_color())
        self.assertEqual(sb.styleSheet(), "")


if __name__ == "__main__":
    unittest.main()
