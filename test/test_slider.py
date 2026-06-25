# !/usr/bin/python
# coding=utf-8
"""Unit tests for the Slider widget.

Slider is QSlider + uitk's MenuMixin / OptionBoxMixin / AttributesMixin — the
reusable slider the other uitk input widgets (ComboBox / SpinBox) imply but
that didn't exist until the HDR Manager's view control needed one.

Run standalone: python -m test.test_slider
"""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtCore

from uitk.widgets.slider import Slider


class TestSlider(QtBaseTestCase):
    def test_is_horizontal_qslider(self):
        s = self.track_widget(Slider())
        self.assertIsInstance(s, QtWidgets.QSlider)
        self.assertEqual(s.orientation(), QtCore.Qt.Horizontal)

    def test_exposes_option_box(self):
        # The whole reason the widget exists: it must carry an option box.
        s = self.track_widget(Slider())
        self.assertIsNotNone(s.option_box)

    def test_class_property_drives_qss(self):
        s = self.track_widget(Slider())
        self.assertEqual(s.property("class"), "Slider")

    def test_kwargs_configure_via_attributes_mixin(self):
        s = self.track_widget(Slider(setMinimum=0, setMaximum=360))
        self.assertEqual(s.minimum(), 0)
        self.assertEqual(s.maximum(), 360)


if __name__ == "__main__":
    unittest.main(verbosity=2)
