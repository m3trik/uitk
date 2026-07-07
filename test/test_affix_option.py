# !/usr/bin/python
# coding=utf-8
"""Unit tests for the AffixOption option-box plugin.

AffixOption adds a compact, inline "Auto / Suffix / Prefix" mode picker beside a
text field — the single reusable home for the affix-picker pattern the DCC
toolkits (mayatk / blendertk ``mat_utils``) used to each duplicate. These tests
verify the headless-observable behaviour: default seeding, mode read-back,
``resolve`` delegation to ``pythontk.StrUtils.split_affix``, the on-change
callback firing only on a user change (not the initial seed), the fluent manager
surface (``set_affix`` / ``affix_mode`` / ``resolve_affix``), the compatibility
gate (non-text host skipped), and inline (non-square) sizing/ordering.

Run standalone: python -m test.test_affix_option
"""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from uitk.widgets.lineEdit import LineEdit
from uitk.widgets.slider import Slider
from uitk.widgets.optionBox.options.affix import AffixOption


class TestAffixOptionState(QtBaseTestCase):
    """mode / set_mode / resolve on a real (text) wrapped widget."""

    def _make(self, *, text="", **kw):
        le = self.track_widget(LineEdit())
        le.setText(text)
        opt = AffixOption(wrapped_widget=le, **kw)
        return le, opt

    def test_default_mode_auto(self):
        _le, opt = self._make()
        self.assertEqual(opt.mode, "auto")

    def test_default_mode_prefix_seeded(self):
        _le, opt = self._make(default="prefix")
        self.assertEqual(opt.mode, "prefix")
        self.assertEqual(opt.widget.currentIndex(), 2)

    def test_unknown_default_falls_back_to_first_value(self):
        _le, opt = self._make(default="bogus")
        self.assertEqual(opt.mode, "auto")

    def test_set_mode(self):
        _le, opt = self._make()
        opt.set_mode("suffix")
        self.assertEqual(opt.mode, "suffix")
        opt.set_mode("nope")  # unknown → no-op
        self.assertEqual(opt.mode, "suffix")

    def test_mode_read_does_not_build_widget(self):
        # A property getter must not have side effects — reading the mode before
        # the picker is shown reports the seeded default without constructing it.
        _le, opt = self._make(default="suffix")
        self.assertEqual(opt.mode, "suffix")
        self.assertIsNone(opt._widget)

    def test_set_mode_before_build_seeds_on_show(self):
        _le, opt = self._make(default="auto")
        opt.set_mode("prefix")  # widget not built yet
        self.assertIsNone(opt._widget)
        self.assertEqual(opt.mode, "prefix")
        # Building the picker must seed to the updated mode.
        self.assertEqual(opt.widget.currentIndex(), 2)
        self.assertEqual(opt.mode, "prefix")

    def test_resolve_auto_reads_widget_text(self):
        le, opt = self._make(text="_MAT")  # leading '_' → suffix
        self.assertEqual(opt.resolve(), ("", "_MAT"))
        le.setText("MAT_")  # trailing '_' → prefix
        self.assertEqual(opt.resolve(), ("MAT_", ""))

    def test_resolve_explicit_text_and_default_fallback(self):
        _le, opt = self._make()  # auto
        # Ambiguous text (no boundary delimiter) → falls to *default*.
        self.assertEqual(opt.resolve("brick", default="suffix"), ("", "brick"))
        self.assertEqual(opt.resolve("brick", default="prefix"), ("brick", ""))

    def test_resolve_honors_forced_mode(self):
        le, opt = self._make(default="suffix", text="XYZ")
        self.assertEqual(opt.resolve(), ("", "XYZ"))
        opt.set_mode("prefix")
        self.assertEqual(opt.resolve(), ("XYZ", ""))

    def test_on_change_fires_on_user_change_not_seed(self):
        seen = []
        _le, opt = self._make(default="prefix", on_change=seen.append)
        # Building/seeding the widget must NOT fire on_change.
        combo = opt.widget
        self.assertEqual(seen, [])
        combo.setCurrentIndex(1)  # simulates the user picking "Suffix"
        self.assertEqual(seen, ["suffix"])

    def test_opts_out_of_square_sizing(self):
        _le, opt = self._make()
        self.assertFalse(opt.square)

    def test_is_compatible(self):
        le = self.track_widget(LineEdit())
        self.assertTrue(AffixOption.is_compatible(le))
        sld = self.track_widget(Slider())  # numeric, no text()
        self.assertFalse(AffixOption.is_compatible(sld))
        self.assertFalse(AffixOption.is_compatible(None))


class TestAffixOptionManager(QtBaseTestCase):
    """The fluent OptionBoxManager surface: set_affix / affix_mode / resolve_affix."""

    def _wrapped(self, *, text="", **kw):
        le = self.track_widget(LineEdit())
        le.setText(text)
        le.option_box.set_affix(**kw)
        opt = le.option_box.find_option(AffixOption)
        return le, opt

    def test_set_affix_adds_option(self):
        _le, opt = self._wrapped(default="prefix")
        self.assertIsInstance(opt, AffixOption)
        self.assertEqual(opt.mode, "prefix")

    def test_affix_mode_property_delegates(self):
        le, _opt = self._wrapped(default="suffix")
        self.assertEqual(le.option_box.affix_mode, "suffix")

    def test_resolve_affix_delegates(self):
        le, _opt = self._wrapped(text="_MAT")  # auto
        self.assertEqual(le.option_box.resolve_affix(default="suffix"), ("", "_MAT"))

    def test_set_affix_on_plain_autopatched_qlineedit(self):
        # Slot .ui fields may be plain (autopatched) QLineEdits — they get the
        # .option_box manager but NOT the .options fluent wrapper. The manager
        # surface must work regardless (regression guard: callers use set_affix,
        # not .options.affix, precisely for this).
        from qtpy import QtWidgets
        from uitk.widgets.optionBox.utils import patch_common_widgets

        patch_common_widgets()
        le = self.track_widget(QtWidgets.QLineEdit())
        self.assertFalse(hasattr(le, "options"))  # no fluent wrapper on the bare class
        le.option_box.set_affix(default="prefix")
        le.setText("brick")
        self.assertEqual(le.option_box.affix_mode, "prefix")
        self.assertEqual(le.option_box.resolve_affix(), ("brick", ""))

    def test_fluent_options_affix(self):
        le = self.track_widget(LineEdit())
        le.options.affix(default="prefix")
        opt = le.option_box.find_option(AffixOption)
        self.assertIsInstance(opt, AffixOption)
        self.assertEqual(opt.mode, "prefix")

    def test_replace_keeps_single_option(self):
        le = self.track_widget(LineEdit())
        le.option_box.set_affix(default="auto")
        le.option_box.set_affix(default="prefix")  # replace=True default
        opts = [o for o in le.option_box._pending_options if isinstance(o, AffixOption)]
        # find_option returns the survivor; only one AffixOption should remain.
        self.assertEqual(len(opts), 1)
        self.assertEqual(le.option_box.affix_mode, "prefix")

    # ── no-option fallbacks (picker never added) ─────────────────────────

    def test_affix_mode_defaults_to_auto_without_option(self):
        le = self.track_widget(LineEdit())
        self.assertEqual(le.option_box.affix_mode, "auto")

    def test_resolve_affix_without_option_uses_auto(self):
        le = self.track_widget(LineEdit())
        le.setText("_MAT")
        self.assertEqual(le.option_box.resolve_affix(default="suffix"), ("", "_MAT"))

    # ── compatibility gate ───────────────────────────────────────────────

    def test_incompatible_host_skipped(self):
        sld = self.track_widget(Slider())  # numeric, no text()
        sld.option_box.set_affix()
        self.assertIsNone(sld.option_box.find_option(AffixOption))

    # ── ordering ─────────────────────────────────────────────────────────

    def test_affix_sits_left_of_icon_buttons(self):
        from uitk.widgets.optionBox.options.toggle import ToggleOption

        le = self.track_widget(LineEdit())
        le.option_box.set_affix()
        le.option_box.add_toggle(icon="eye", initial=False, settings_key=False)
        self.track_widget(le.option_box.container)

        layout = le.option_box.container.layout()
        widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
        picker = le.option_box.find_option(AffixOption).widget
        button = le.option_box.find_option(ToggleOption).widget
        self.assertLess(widgets.index(picker), widgets.index(button))


if __name__ == "__main__":
    unittest.main(verbosity=2)
