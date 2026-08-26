# !/usr/bin/python
# coding=utf-8
"""Unit tests for the AffixOption option-box plugin.

AffixOption adds a compact tri-state icon button beside a text field — click
cycles the affix mode (Auto → Suffix → Prefix) — the single reusable home for
the affix-picker pattern the DCC toolkits (mayatk / blendertk ``mat_utils``)
used to each duplicate. These tests verify the headless-observable behaviour:
default seeding, mode read-back, the click cycle, per-state icon swap,
``resolve`` delegation to ``pythontk.StrUtils.split_affix``, the on-change
callback firing only on a real change (not the initial seed), the fluent
manager surface (``set_affix`` / ``affix_mode`` / ``resolve_affix``), the
compatibility gate (non-text host skipped), and standard square button sizing.

Run standalone: python -m test.test_affix_option
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from uitk.widgets.lineEdit import LineEdit
from uitk.widgets.slider import Slider
from uitk.widgets.optionBox.options.affix import (
    AffixMode,
    AffixOption,
    BUILTIN_AFFIX_MODES,
)
from uitk.widgets.optionBox.options.clear import ClearOption


def _icon_name(widget):
    """The IconManager-registered icon name currently on *widget*."""
    from uitk.managers.icon_manager import IconManager

    info = IconManager.registered_info(widget)
    return info.get("name") if info else None


class TestAffixOptionState(QtBaseTestCase):
    """mode / set_mode / cycle / resolve on a real (text) wrapped widget."""

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
        self.assertEqual(_icon_name(opt.widget), "arrow_left")

    def test_unknown_default_falls_back_to_auto(self):
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
        # Building the picker must seed the updated mode's glyph.
        self.assertEqual(_icon_name(opt.widget), "arrow_left")
        self.assertEqual(opt.mode, "prefix")

    def test_click_cycles_modes(self):
        # Auto → Suffix → Prefix → Auto, with the glyph tracking each state.
        _le, opt = self._make()
        button = opt.widget
        self.assertEqual(opt.mode, "auto")
        button.click()
        self.assertEqual(opt.mode, "suffix")
        self.assertEqual(_icon_name(button), "arrow_right")
        button.click()
        self.assertEqual(opt.mode, "prefix")
        self.assertEqual(_icon_name(button), "arrow_left")
        button.click()
        self.assertEqual(opt.mode, "auto")
        self.assertEqual(_icon_name(button), "asterisk")

    def test_tooltip_names_current_mode(self):
        _le, opt = self._make(default="suffix")
        self.assertIn("Suffix", opt.widget.toolTip())
        opt.widget.click()  # → prefix
        self.assertIn("Prefix", opt.widget.toolTip())

    def test_static_tooltip_override(self):
        _le, opt = self._make(tooltip="Custom guide.")
        self.assertEqual(opt.widget.toolTip(), "Custom guide.")
        opt.widget.click()  # a cycle must not clobber the override
        self.assertEqual(opt.widget.toolTip(), "Custom guide.")

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

    def test_on_change_fires_on_change_not_seed(self):
        seen = []
        _le, opt = self._make(default="prefix", on_change=seen.append)
        # Building/seeding the widget must NOT fire on_change.
        button = opt.widget
        self.assertEqual(seen, [])
        button.click()  # user cycles prefix → auto
        self.assertEqual(seen, ["auto"])
        opt.set_mode("auto")  # same mode → no re-fire
        self.assertEqual(seen, ["auto"])
        opt.set_mode("suffix")  # programmatic change on the built button fires
        self.assertEqual(seen, ["auto", "suffix"])

    def test_square_button_sizing(self):
        # A standard option-box icon button: no square opt-out, so the
        # container gives it the same h x h footprint as every other option.
        _le, opt = self._make()
        self.assertTrue(getattr(opt, "square", True))

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
        from uitk.widgets.optionBox.utils import OptionBoxManager

        OptionBoxManager.patch_common_widgets()
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

    def test_clear_sits_left_of_affix(self):
        """The clear button leads the affix picker (and every other button)."""
        le = self.track_widget(LineEdit())
        le.option_box.clear_option = True
        le.option_box.set_affix()
        self.track_widget(le.option_box.container)

        layout = le.option_box.container.layout()
        widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
        clear = le.option_box.find_option(ClearOption).widget
        picker = le.option_box.find_option(AffixOption).widget
        self.assertLess(widgets.index(clear), widgets.index(picker))


class TestAffixOptionPersistence(QtBaseTestCase):
    """The selected mode survives a session (regression: it never persisted).

    AffixOption was a plain ButtonOption, so the picker reset to the caller's
    ``default`` on every launch while the field's TEXT was restored by
    StateManager — the spelling came back applied to the wrong side.
    """

    def _fresh(self, key, **kw):
        """A new option over a new field — stands in for a new session."""
        le = self.track_widget(LineEdit())
        le.setObjectName("txt_affix_persist")
        return AffixOption(wrapped_widget=le, settings_key=key, **kw)

    def _clear(self, option):
        if getattr(option, "_settings", None):
            option._settings.clear()
            option._settings.sync()

    def test_mode_round_trips_across_sessions(self):
        key = "test_affix_round_trip"
        first = self._fresh(key, default="auto")
        first.set_mode("prefix")

        second = self._fresh(key, default="auto")
        self.assertEqual(
            second.mode, "prefix", "persisted mode must override the caller's default"
        )
        self.assertEqual(_icon_name(second.widget), "arrow_left")
        self._clear(second)

    def test_click_cycle_persists(self):
        """The user-facing path (clicking the button), not just set_mode."""
        key = "test_affix_cycle_persist"
        first = self._fresh(key, default="auto")
        first.widget.click()  # auto -> suffix

        second = self._fresh(key, default="auto")
        self.assertEqual(second.mode, "suffix")
        self._clear(second)

    def test_restore_silently_does_not_fire_on_change(self):
        """Restoring is not a user action — on_change must stay quiet."""
        key = "test_affix_quiet_restore"
        first = self._fresh(key, default="auto")
        first.set_mode("suffix")

        seen = []
        second = self._fresh(key, default="auto", on_change=seen.append)
        second.widget  # force the build; a restore must not fire through it
        self.assertEqual(second.mode, "suffix")
        self.assertEqual(seen, [], "restoring a persisted mode is not a change")
        self._clear(second)

    def test_settings_key_false_disables_persistence(self):
        le = self.track_widget(LineEdit())
        le.setObjectName("txt_affix_optout")
        option = AffixOption(wrapped_widget=le, settings_key=False)
        option.set_mode("prefix")
        self.assertIsNone(option._settings)

        again = AffixOption(wrapped_widget=self.track_widget(LineEdit()))
        again.wrapped_widget.setObjectName("txt_affix_optout")
        self.assertEqual(again.mode, "auto")

    def test_unnamed_widget_persists_nothing(self):
        """No objectName to auto-derive from ⇒ no QSettings namespace."""
        option = AffixOption(wrapped_widget=self.track_widget(LineEdit()))
        self.assertIsNone(option._settings)

    def test_restore_default_returns_to_constructed_mode(self):
        """A sibling ResetOption must be able to reach a persisted mode."""
        key = "test_affix_restore_default"
        option = self._fresh(key, default="suffix")
        option.set_mode("prefix")
        option.restore_default()
        self.assertEqual(option.mode, "suffix")

        after = self._fresh(key, default="auto")
        self.assertEqual(after.mode, "suffix", "the reset must persist too")
        self._clear(after)

    def test_manager_forwards_settings_key(self):
        key = "test_affix_manager_key"
        le = self.track_widget(LineEdit())
        le.setObjectName("txt_affix_mgr")
        le.option_box.set_affix(default="auto", settings_key=key)
        le.option_box.find_option(AffixOption).set_mode("prefix")

        le2 = self.track_widget(LineEdit())
        le2.setObjectName("txt_affix_mgr")
        le2.option_box.set_affix(default="auto", settings_key=key)
        option = le2.option_box.find_option(AffixOption)
        self.assertEqual(le2.option_box.affix_mode, "prefix")
        self._clear(option)


class TestAffixOptionModeSet(QtBaseTestCase):
    """The cycle is configurable — three built-ins are a DEFAULT, not the API.

    Most fields want the three manual states; some want two; some want a custom
    state of their own. None of that may require editing the plugin.
    """

    def _make(self, **kw):
        le = self.track_widget(LineEdit())
        kw.setdefault("settings_key", False)
        return le, AffixOption(wrapped_widget=le, **kw)

    def test_defaults_to_the_three_builtins(self):
        _le, opt = self._make()
        self.assertEqual(opt.modes, ["auto", "suffix", "prefix"])

    def test_two_state_picker(self):
        _le, opt = self._make(modes=("suffix", "prefix"), default="suffix")
        self.assertEqual(opt.modes, ["suffix", "prefix"])
        opt.widget.click()
        self.assertEqual(opt.mode, "prefix")
        opt.widget.click()
        self.assertEqual(opt.mode, "suffix", "a two-state cycle wraps at two")

    def test_custom_mode_instance(self):
        custom = AffixMode(
            key="shout",
            label="Shout",
            icon="asterisk",
            resolver=lambda text, _default: ("", text.upper()),
        )
        le, opt = self._make(modes=("auto", custom), default="shout")
        le.setText("_mat")
        self.assertEqual(opt.modes, ["auto", "shout"])
        self.assertEqual(opt.resolve(), ("", "_MAT"))

    def test_unknown_mode_is_skipped_not_raised(self):
        _le, opt = self._make(modes=("suffix", "bogus"))
        self.assertEqual(opt.modes, ["suffix"])

    def test_all_bogus_falls_back_to_builtins(self):
        """A picker with no usable state would be worse than the default."""
        _le, opt = self._make(modes=("nope", "nah"))
        self.assertEqual(opt.modes, ["auto", "suffix", "prefix"])

    def test_duplicates_collapse_preserving_order(self):
        _le, opt = self._make(modes=("prefix", "auto", "prefix"))
        self.assertEqual(opt.modes, ["prefix", "auto"])

    def test_unknown_default_falls_back_to_first_available(self):
        _le, opt = self._make(modes=("suffix", "prefix"), default="auto")
        self.assertEqual(opt.mode, "suffix")

    def test_mode_spec_exposes_the_builtin(self):
        _le, opt = self._make()
        self.assertIs(opt.mode_spec("suffix"), BUILTIN_AFFIX_MODES["suffix"])

    def test_tooltip_names_the_configured_cycle(self):
        _le, opt = self._make(modes=("suffix", "prefix"), default="suffix")
        tip = opt.widget.toolTip()
        self.assertIn("Suffix -> Prefix", tip)
        self.assertNotIn("Auto", tip)


class TestAffixConventionMode(QtBaseTestCase):
    """The fourth state: a CUSTOM mode bound to the shared naming convention.

    It fills the field from ``pythontk.NamingConvention`` and makes it
    read-only — the widget stays ENABLED, so the value is still visible and the
    slot still reads it.
    """

    def setUp(self):
        super().setUp()
        import pythontk as ptk

        self.NC = ptk.NamingConvention
        self.NC.reload()

    def _make(self, *, convention_key="material", **kw):
        le = self.track_widget(LineEdit())
        kw.setdefault("settings_key", False)
        opt = AffixOption(wrapped_widget=le, convention_key=convention_key, **kw)
        opt.widget  # build, so setup_widget applies field effects
        return le, opt

    def test_convention_key_appends_a_fourth_state(self):
        _le, opt = self._make()
        self.assertEqual(opt.modes, ["auto", "suffix", "prefix", "convention"])

    def test_not_present_without_an_opt_in(self):
        """Most fields want three states — the fourth must never appear unasked."""
        le = self.track_widget(LineEdit())
        opt = AffixOption(wrapped_widget=le, settings_key=False)
        self.assertNotIn("convention", opt.modes)

    def test_selecting_it_fills_the_field_from_the_ssot(self):
        le, opt = self._make()
        le.setText("_MyOwn")
        opt.set_mode("convention")
        self.assertEqual(le.text(), self.NC.affix("material"))

    def test_field_is_read_only_but_still_enabled(self):
        le, opt = self._make()
        opt.set_mode("convention")
        self.assertTrue(le.isReadOnly(), "typing must be refused")
        self.assertTrue(le.isEnabled(), "but the value must still read")
        self.assertTrue(le.text(), "and still be visible")

    def test_leaving_the_mode_restores_the_users_text(self):
        le, opt = self._make()
        le.setText("_MyOwn")
        opt.set_mode("convention")
        opt.set_mode("auto")
        self.assertEqual(le.text(), "_MyOwn")
        self.assertFalse(le.isReadOnly())

    def test_resolve_answers_from_the_convention(self):
        le, opt = self._make()
        opt.set_mode("convention")
        self.assertEqual(opt.resolve(), self.NC.affix_parts("material"))

    def test_resolve_ignores_a_field_written_over_behind_our_back(self):
        """StateManager restores text after build; the SSoT must still win."""
        le, opt = self._make()
        opt.set_mode("convention")
        le.setText("_CLOBBERED")  # e.g. a session-state restore
        self.assertEqual(opt.resolve(), self.NC.affix_parts("material"))

    def test_refresh_repulls_after_the_convention_changes(self):
        le, opt = self._make()
        opt.set_mode("convention")
        try:
            self.NC.set("material", "MTL_")
            opt.refresh()
            self.assertEqual(le.text(), "MTL_")
            self.assertEqual(opt.resolve(), ("MTL_", ""))
        finally:
            self.NC.reset("material")

    def test_convention_mode_honours_the_conventions_own_placement(self):
        """A convention spelled as a prefix must land as a prefix."""
        _le, opt = self._make(convention_key="mesh")
        opt.set_mode("convention")
        try:
            self.NC.set("mesh", "GEO_")
            opt.refresh()
            self.assertEqual(opt.resolve(), ("GEO_", ""))
        finally:
            self.NC.reset("mesh")

    def test_modes_explicit_overrides_convention_key(self):
        le = self.track_widget(LineEdit())
        opt = AffixOption(
            wrapped_widget=le,
            modes=("auto", "suffix"),
            convention_key="material",
            settings_key=False,
        )
        self.assertEqual(opt.modes, ["auto", "suffix"])

    def test_showing_the_box_repulls_the_convention(self):
        """The clobber path: StateManager restores a field's saved text AFTER
        the option applied the convention at wrap time, so the picker would say
        Scene beside stale text. Showing the box re-pulls."""
        le = self.track_widget(LineEdit())
        le.setObjectName("txt_affix_show")
        le.option_box.set_affix(convention_key="material", settings_key=False)
        option = le.option_box.find_option(AffixOption)
        option.set_mode("convention")
        container = self.track_widget(le.option_box.container)

        le.setText("_CLOBBERED")  # e.g. a session-state restore landing late
        # The container is already visible from the wrap, so hide first —
        # otherwise show() is a no-op and no QShowEvent is delivered. In a real
        # panel the equivalent event is the owning window becoming visible,
        # which every un-hidden child receives.
        container.hide()
        container.show()
        self.assertEqual(le.text(), self.NC.affix("material"))

    def test_unknown_convention_key_is_skipped_not_dead_locked(self):
        """Regression: a typo produced a state that emptied the field, locked
        it read-only, and applied nothing — with no visible cause. A picker
        missing its fourth state is diagnosable; a dead field is not."""
        le = self.track_widget(LineEdit())
        le.setText("_MyOwn")
        option = AffixOption(
            wrapped_widget=le, convention_key="materal", settings_key=False
        )
        option.widget  # build
        self.assertNotIn("convention", option.modes)
        self.assertEqual(le.text(), "_MyOwn", "the user's text must survive")
        self.assertFalse(le.isReadOnly(), "the field must stay typeable")

    def test_manager_forwards_convention_key(self):
        le = self.track_widget(LineEdit())
        le.option_box.set_affix(convention_key="material", settings_key=False)
        opt = le.option_box.find_option(AffixOption)
        self.assertIn("convention", opt.modes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
