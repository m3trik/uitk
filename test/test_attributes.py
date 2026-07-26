# !/usr/bin/python
# coding=utf-8
"""Regression tests for AttributesMixin custom-attribute handling.

Covers ``set_attributes(widget, setCheckState=<int>)``: the documented int
mapping (0/1/2 -> Qt.CheckState) was unreachable because the dispatcher called
the native ``setCheckState`` method directly with the raw int, which raises an
uncaught TypeError under PySide6 (a Qt.CheckState is expected).

Run standalone: python test/test_attributes.py
"""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets  # noqa: E402
from uitk.widgets.mixins.attributes import AttributesMixin  # noqa: E402


class TestSetCheckStateInt(QtBaseTestCase):
    """``setCheckState=<int>`` must map to Qt.CheckState for plain Qt widgets."""

    def setUp(self):
        super().setUp()
        self.mixin = AttributesMixin()
        self.cb = self.track_widget(QtWidgets.QCheckBox())
        self.cb.setTristate(True)

    def test_int_checked(self):
        self.mixin.set_attributes(self.cb, setCheckState=2)
        self.assertEqual(self.cb.checkState(), QtCore.Qt.CheckState.Checked)
        self.assertTrue(self.cb.isChecked())

    def test_int_unchecked(self):
        self.cb.setChecked(True)
        self.mixin.set_attributes(self.cb, setCheckState=0)
        self.assertEqual(self.cb.checkState(), QtCore.Qt.CheckState.Unchecked)

    def test_int_partially_checked(self):
        self.mixin.set_attributes(self.cb, setCheckState=1)
        self.assertEqual(self.cb.checkState(), QtCore.Qt.CheckState.PartiallyChecked)

    def test_enum_value_passes_through(self):
        # An already-Qt.CheckState value must still work (not KeyError).
        self.mixin.set_attributes(
            self.cb, setCheckState=QtCore.Qt.CheckState.Checked
        )
        self.assertEqual(self.cb.checkState(), QtCore.Qt.CheckState.Checked)


class TestSetLimitsStep(QtBaseTestCase):
    """``set_limits`` must never apply a zero/negative step.

    A zero singleStep freezes the spinbox entirely: Qt's default wheel
    stepping and every WheelStepMixin modifier branch scale off singleStep,
    and set_limits also hides the up/down buttons (NoButtons). Regression:
    the tentacle select-similar tolerance spinbox was stuck at 0.000.
    """

    def setUp(self):
        super().setUp()
        self.mixin = AttributesMixin()
        self.sb = self.track_widget(QtWidgets.QDoubleSpinBox())

    def test_zero_step_falls_back(self):
        self.mixin.set_attributes(self.sb, set_limits=[0, 9999, 0.0, 3])
        self.assertGreater(self.sb.singleStep(), 0)
        self.assertEqual(self.sb.minimum(), 0)
        self.assertEqual(self.sb.maximum(), 9999)
        self.assertEqual(self.sb.decimals(), 3)

    def test_negative_step_falls_back(self):
        self.mixin.set_attributes(self.sb, set_limits=[0, 10, -0.5])
        self.assertGreater(self.sb.singleStep(), 0)

    def test_valid_step_preserved(self):
        self.mixin.set_attributes(self.sb, set_limits=[0, 9999, 0.1, 3])
        self.assertAlmostEqual(self.sb.singleStep(), 0.1)


if __name__ == "__main__":
    unittest.main()
