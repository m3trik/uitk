# !/usr/bin/python
# coding=utf-8
"""Unit tests for DoubleSpinBox widget.

DoubleSpinBox is the float-input widget used by the AttributeWindow factory
(see uitk.widgets.attributeWindow._factory._build_float). It has the same
modifier-driven step semantics as SpinBox.

Modifier ladder under test (symmetric: Ctrl scales up, Alt scales down,
stacking amplifies):

    Ctrl          singleStep × 10
    Ctrl+Shift    singleStep × 100
    Alt           singleStep / 10
    Ctrl+Alt      10 ** -decimals          (smallest)

Run standalone: python -m pytest test/test_double_spin_box.py -v
"""

import unittest
from unittest.mock import MagicMock

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore


class TestDoubleSpinBoxModifierSteps(QtBaseTestCase):
    """Tests for the symmetric modifier ladder on DoubleSpinBox."""

    def _make_spinbox(self, value=5.0, step=1.0, decimals=4):
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        sb = self.track_widget(DoubleSpinBox())
        sb.setDecimals(decimals)
        sb.setRange(-100, 100)
        sb.setSingleStep(step)
        sb.setValue(value)
        return sb

    def _make_wheel_event(self, delta=120, modifiers=None, axis="y"):
        event = MagicMock()
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
        sb = self._make_spinbox(value=5.0, step=1.0)
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.ControlModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 15.0, places=5)

    def test_ctrl_wheel_down_steps_by_10x(self):
        sb = self._make_spinbox(value=50.0, step=1.0)
        event = self._make_wheel_event(
            delta=-120, modifiers=QtCore.Qt.ControlModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 40.0, places=5)

    def test_ctrl_shift_wheel_steps_by_100x(self):
        sb = self._make_spinbox(value=5.0, step=1.0)
        sb.setRange(-1000, 1000)  # widen so 5 + 100 doesn't clamp
        event = self._make_wheel_event(
            delta=120,
            modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier,
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 105.0, places=5)

    # ---- Alt = singleStep / 10 (fine) ---------------------------------

    def test_alt_wheel_up_steps_by_singleStep_over_10(self):
        """Alt+wheel up should step by ``singleStep / 10``."""
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.1, places=6)

    def test_alt_wheel_down_steps_by_singleStep_over_10(self):
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=-120, modifiers=QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 4.9, places=6)

    def test_alt_wheel_does_not_mutate_single_step(self):
        """Alt+wheel must step the *value*, not the widget's ``singleStep``
        setting (the original pre-symmetric-ladder behaviour).
        """
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=3)
        before_step = sb.singleStep()
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event)
        self.assertEqual(sb.singleStep(), before_step)

    # ---- Ctrl+Alt = 10**-decimals (smallest) --------------------------

    def test_ctrl_alt_wheel_up_steps_by_smallest(self):
        """Ctrl+Alt+wheel up: step by ``10**-decimals`` (smallest)."""
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.0001, places=6)

    def test_ctrl_alt_wheel_down_steps_by_smallest(self):
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=-120, modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 4.9999, places=6)

    def test_ctrl_alt_smaller_than_alt(self):
        """Ladder ordering invariant: ``Ctrl+Alt`` must produce a step
        strictly smaller than ``Alt`` alone for any float spin-box where
        ``singleStep / 10`` exceeds ``10**-decimals``. This is what the
        user actually observes -- adding ``Ctrl`` to ``Alt`` makes the
        gesture *finer*, not the same.
        """
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        # Alt alone
        sb.setValue(5.0)
        event_alt = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event_alt)
        delta_alt = sb.value() - 5.0
        # Ctrl+Alt
        sb.setValue(5.0)
        event_ca = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event_ca)
        delta_ca = sb.value() - 5.0

        self.assertGreater(delta_alt, delta_ca)

    # ---- axis-swap fallback -------------------------------------------

    def test_alt_wheel_reads_x_axis_when_y_is_zero(self):
        """Real-world regression: Alt-held wheel events on some platforms /
        Qt6 builds put the delta on ``angleDelta().x()`` instead of
        ``.y()``. The y-only check that previously gated direction would
        always read 0 and silently no-op.
        """
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.AltModifier, axis="x"
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.1, places=6)

    def test_ctrl_alt_wheel_reads_x_axis_when_y_is_zero(self):
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=120,
            modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier,
            axis="x",
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.0001, places=6)


class TestDoubleSpinBoxPrefix(QtBaseTestCase):
    def test_prefix_adds_tab(self):
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        sb = self.track_widget(DoubleSpinBox())
        sb.setPrefix("Value:")
        self.assertEqual(sb.prefix(), "Value:\t")


class TestDoubleSpinBoxTextColor(QtBaseTestCase):
    """SpinBoxTextColorMixin.set_text_color — tints the value text (e.g. X/Y/Z)."""

    def _make(self):
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        return self.track_widget(DoubleSpinBox())

    def test_default_is_unset(self):
        sb = self._make()
        self.assertIsNone(sb.text_color())
        self.assertEqual(sb.styleSheet(), "")

    def test_set_text_color_applies_to_spinbox(self):
        sb = self._make()
        sb.set_text_color("#ff5555")
        self.assertEqual(sb.text_color(), "#ff5555")
        # Applied on the spin box itself — under the theme the QAbstractSpinBox
        # color governs the displayed value, so a line-edit color is overridden.
        self.assertIn("color: #ff5555;", sb.styleSheet())

    def test_clear_with_none_resets_to_theme(self):
        sb = self._make()
        sb.set_text_color("#ff5555")
        sb.set_text_color(None)
        self.assertIsNone(sb.text_color())
        self.assertEqual(sb.styleSheet(), "")

    def test_empty_string_clears(self):
        sb = self._make()
        sb.set_text_color("#ff5555")
        sb.set_text_color("")  # falsy -> treated as clear
        self.assertIsNone(sb.text_color())
        self.assertEqual(sb.styleSheet(), "")

    def test_color_merges_with_existing_inline_style(self):
        # set_text_color must not clobber other inline styling (e.g. option-box
        # border tweaks); changing/clearing the color leaves the rest intact.
        sb = self._make()
        sb.setStyleSheet("border-right-width: 0px;")
        sb.set_text_color("#ff5555")
        self.assertIn("border-right-width: 0px;", sb.styleSheet())
        self.assertIn("color: #ff5555;", sb.styleSheet())
        sb.set_text_color("#00b000")  # change color
        self.assertIn("border-right-width: 0px;", sb.styleSheet())
        self.assertNotIn("#ff5555", sb.styleSheet())
        sb.set_text_color(None)  # clear color
        self.assertEqual(sb.styleSheet().strip(), "border-right-width: 0px;")


if __name__ == "__main__":
    unittest.main()
