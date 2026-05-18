# !/usr/bin/python
# coding=utf-8
"""Unit tests for DoubleSpinBox widget.

DoubleSpinBox is the float-input widget used by the AttributeWindow factory
(see uitk.widgets.attributeWindow._factory._build_float). It has the same
modifier-driven step semantics as SpinBox.

Run standalone: python -m pytest test/test_double_spin_box.py -v
"""

import unittest
from unittest.mock import MagicMock

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore


class TestDoubleSpinBoxModifierSteps(QtBaseTestCase):
    """Tests for Alt / Ctrl / Ctrl+Alt step behavior."""

    def _make_spinbox(self, value=5.0, step=1.0, decimals=4):
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        sb = self.track_widget(DoubleSpinBox())
        sb.setDecimals(decimals)
        sb.setRange(-100, 100)
        sb.setSingleStep(step)
        sb.setValue(value)
        return sb

    def _make_wheel_event(self, delta=120, modifiers=None):
        event = MagicMock()
        event.angleDelta.return_value.y.return_value = delta
        event.modifiers.return_value = (
            modifiers if modifiers is not None else QtCore.Qt.NoModifier
        )
        return event

    def test_ctrl_wheel_up_steps_by_10x(self):
        """Ctrl alone should move the value by 10x the singleStep."""
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

    def test_ctrl_alt_wheel_up_moves_lowest_decimal(self):
        """Ctrl+Alt should move the value by the lowest decimal place.

        Regression: equality compare between event.modifiers() and
        ``Qt.ControlModifier | Qt.AltModifier`` fails under PySide6's flag
        enum, so Ctrl+Alt scrolls did nothing.
        """
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
        )

        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.0001, places=6)

    def test_ctrl_alt_wheel_down_moves_lowest_decimal(self):
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=-120, modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
        )

        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 4.9999, places=6)

    def test_alt_only_wheel_adjusts_step_not_value(self):
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=3)
        before = sb.value()
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.AltModifier
        )

        sb.wheelEvent(event)
        self.assertEqual(sb.value(), before)
        self.assertNotEqual(sb.singleStep(), 1.0)


class TestDoubleSpinBoxPrefix(QtBaseTestCase):
    def test_prefix_adds_tab(self):
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        sb = self.track_widget(DoubleSpinBox())
        sb.setPrefix("Value:")
        self.assertEqual(sb.prefix(), "Value:\t")


if __name__ == "__main__":
    unittest.main()
