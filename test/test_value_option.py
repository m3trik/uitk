# !/usr/bin/python
# coding=utf-8
"""Unit tests for the ValueOption option-box plugin.

ValueOption adds a compact, editable numeric field beside a value widget that
stays in two-way live sync with it — the reusable "interactive value" the HDR
Manager's view slider needs. Verified against the real Slider + OptionBox wrap
(not a stub), so the lazy-wrap lifecycle and the field<->widget echo guard are
exercised end to end.

Run standalone: python -m test.test_value_option
"""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from uitk.widgets.slider import Slider
from uitk.widgets.optionBox.options.value import ValueOption


class TestValueOption(QtBaseTestCase):
    def _wrapped_slider(self, lo=0, hi=360, val=90, **add_kwargs):
        """A Slider wrapped with a ValueOption; returns (slider, option, field)."""
        sld = self.track_widget(Slider())
        sld.setRange(lo, hi)
        sld.setValue(val)
        sld.option_box.add_value(**add_kwargs)
        # Accessing .container forces the lazy wrap (create field + wire both ways).
        self.track_widget(sld.option_box.container)
        opt = sld.option_box.find_option(ValueOption)
        return sld, opt, opt.widget

    def test_field_mirrors_initial_value_and_range(self):
        sld, opt, field = self._wrapped_slider(lo=0, hi=360, val=90)
        self.assertEqual(field.value(), 90)
        self.assertEqual((field.minimum(), field.maximum()), (0, 360))

    def test_slider_drag_updates_field(self):
        sld, opt, field = self._wrapped_slider(val=90)
        sld.setValue(45)  # simulates a drag
        self.assertEqual(field.value(), 45)

    def test_field_edit_updates_slider_and_lets_it_emit(self):
        sld, opt, field = self._wrapped_slider(val=90)
        seen = []
        sld.valueChanged.connect(seen.append)  # a downstream slot
        field.setValue(200)  # simulates typing
        self.assertEqual(sld.value(), 200)
        # The wrapped widget must still emit so panel slots fire on a typed edit.
        self.assertIn(200, seen)

    def test_echo_does_not_loop(self):
        # A drag must not bounce back through the field and re-set the slider.
        sld, opt, field = self._wrapped_slider(val=90)
        calls = []
        sld.valueChanged.connect(calls.append)
        sld.setValue(123)
        self.assertEqual(calls, [123])  # exactly one, no echo storm
        self.assertEqual(field.value(), 123)

    def test_inherits_int_decimals_from_slider(self):
        # A QSlider is integer — the field must read back ints, not 90.000.
        sld, opt, field = self._wrapped_slider(val=90)
        self.assertEqual(field.decimals(), 0)
        self.assertIsInstance(field.value(), int)

    def test_opts_out_of_square_sizing(self):
        sld, opt, field = self._wrapped_slider()
        self.assertFalse(opt.square)
        # Square-forcing would setFixedSize(h, h) → max width == row height.
        # The opt-out must instead preserve the field's own (wider) width.
        self.assertEqual(field.minimumWidth(), 46)
        self.assertEqual(field.maximumWidth(), 46)

    def test_value_field_sits_left_of_icon_buttons(self):
        # The inline value must sort ahead of any icon-button option (it's first
        # in OptionBox._option_order), so it sits flush against the widget.
        from uitk.widgets.optionBox.options.toggle import ToggleOption

        sld = self.track_widget(Slider())
        sld.setRange(0, 360)
        sld.option_box.add_value()
        sld.option_box.add_toggle(icon="eye", initial=False, settings_key=False)
        self.track_widget(sld.option_box.container)

        layout = sld.option_box.container.layout()
        widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
        field = sld.option_box.find_option(ValueOption).widget
        button = sld.option_box.find_option(ToggleOption).widget
        self.assertLess(widgets.index(field), widgets.index(button))


if __name__ == "__main__":
    unittest.main(verbosity=2)
