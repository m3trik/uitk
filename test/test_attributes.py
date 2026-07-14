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


if __name__ == "__main__":
    unittest.main()
