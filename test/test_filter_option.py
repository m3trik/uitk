# !/usr/bin/python
# coding=utf-8
"""Unit tests for FilterOption + the option compatibility gate.

FilterOption is the all-in-one filter plugin (on/off toggle + text persistence
+ optional scope cycle) that replaced the standalone ``make_filter_lineedit``
factory. These tests verify the headless-observable behaviour: pattern building,
on/off gating, scope cycling/persistence, text persistence, and that the
option-box manager skips an incompatible (non-text) host.

Run standalone: python -m test.test_filter_option
"""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets

from uitk.widgets.optionBox.options.filter import FilterOption, to_patterns
from uitk.widgets.optionBox.options._options import BaseOption
from uitk.widgets.optionBox.utils import OptionBoxManager


class _DictSettings:
    """Minimal ``QSettings``-like store (value/setValue) for deterministic tests."""

    def __init__(self, initial=None):
        self._d = dict(initial or {})

    def value(self, key, default=None):
        return self._d.get(key, default)

    def setValue(self, key, value):
        self._d[key] = value


SCOPES = [
    {"key": "name", "icon": "filter"},
    {"key": "both", "icon": "filter"},
    {"key": "tags", "icon": "filter"},
]


class TestToPatterns(unittest.TestCase):
    """The shared comma/glob query convention."""

    def test_bare_terms_are_verbatim_strict(self):
        # Strict: a bare term is NOT wrapped — it matches exactly via fnmatch.
        self.assertEqual(to_patterns("foo"), ["foo"])
        self.assertEqual(to_patterns("foo, bar"), ["foo", "bar"])

    def test_globbed_terms_pass_through(self):
        self.assertEqual(to_patterns("foo*, ?bar, [ab]c"), ["foo*", "?bar", "[ab]c"])

    def test_blank_terms_dropped(self):
        self.assertEqual(to_patterns("  , foo ,  "), ["foo"])

    def test_negation_keeps_marker_remainder_verbatim(self):
        # "!drop" keeps the marker and the remainder verbatim (no wrapping).
        self.assertEqual(to_patterns("keep, !drop"), ["keep", "!drop"])
        self.assertEqual(to_patterns("*keep*, !*drop*"), ["*keep*", "!*drop*"])

    def test_negation_preserves_existing_globs(self):
        self.assertEqual(to_patterns("!*temp*"), ["!*temp*"])

    def test_bare_negation_marker_dropped(self):
        self.assertEqual(to_patterns("!, foo"), ["foo"])

    def test_negation_disabled_when_prefix_empty(self):
        # With no prefix, "!drop" is just a verbatim term (leading ! is literal).
        self.assertEqual(to_patterns("!drop", negate_prefix=""), ["!drop"])


class TestFilterOptionBehavior(QtBaseTestCase):
    """patterns()/is_on/scope/persistence on a real (text) wrapped widget."""

    def _make(self, *, settings=None, scopes=None, **kw):
        le = self.track_widget(QtWidgets.QLineEdit())
        opt = FilterOption(wrapped_widget=le, settings=settings, scopes=scopes, **kw)
        return le, opt

    # ── patterns + on/off gate ──────────────────────────────────────────

    def test_patterns_none_when_empty(self):
        _le, opt = self._make()
        self.assertIsNone(opt.patterns())

    def test_patterns_built_from_text(self):
        le, opt = self._make()
        le.setText("alpha, *beta*")
        # Strict: bare terms verbatim, wildcards explicit.
        self.assertEqual(opt.patterns(), ["alpha", "*beta*"])

    def test_patterns_none_when_filter_off(self):
        le, opt = self._make(initial_enabled=True)
        le.setText("alpha")
        opt.set_on(False)
        self.assertIsNone(opt.patterns(), "off filter must match everything (None)")
        opt.set_on(True)
        self.assertEqual(opt.patterns(), ["alpha"])

    def test_patterns_carry_inline_negation_end_to_end(self):
        # patterns() preserves the "!" marker verbatim; filter_list(negate_prefix
        # ="!") turns it into an exclusion — the full single-field flow. Strict:
        # the user supplies wildcards explicitly for substring matching.
        import pythontk as ptk

        from uitk.widgets.optionBox.options.filter import NEGATE_PREFIX

        le, opt = self._make()
        le.setText("*keep*, !*drop*")
        self.assertEqual(opt.patterns(), ["*keep*", "!*drop*"])
        items = ["keep_one", "keep_drop", "other"]
        result = ptk.filter_list(
            items, inc=opt.patterns(), ignore_case=True, negate_prefix=NEGATE_PREFIX
        )
        self.assertEqual(result, ["keep_one"])

    # ── text persistence ────────────────────────────────────────────────

    def test_text_persisted_on_edit(self):
        s = _DictSettings()
        le, _opt = self._make(settings=s, text_key="f.text", on_changed=lambda: None)
        le.setText("query")
        self.assertEqual(s.value("f.text"), "query")

    def test_text_restored_on_construct(self):
        s = _DictSettings({"f.text": "restored"})
        le, _opt = self._make(settings=s, text_key="f.text", on_changed=lambda: None)
        self.assertEqual(le.text(), "restored")

    def test_on_changed_fires_after_edit(self):
        calls = []
        le, _opt = self._make(on_changed=lambda: calls.append(1))
        le.setText("x")
        self.assertEqual(len(calls), 1)

    # ── on/off persistence (routed to the shared settings object) ───────

    def test_enabled_persisted(self):
        s = _DictSettings()
        _le, opt = self._make(settings=s, enabled_key="f.on", initial_enabled=True)
        opt.set_on(False)
        self.assertEqual(s.value("f.on"), False)

    def test_enabled_restored_overrides_initial(self):
        s = _DictSettings({"f.on": False})
        _le, opt = self._make(settings=s, enabled_key="f.on", initial_enabled=True)
        self.assertFalse(opt.is_on, "persisted off must override initial_enabled=True")

    def test_enabled_restored_from_stringified_bool(self):
        s = _DictSettings({"f.on": "false"})
        _le, opt = self._make(settings=s, enabled_key="f.on", initial_enabled=True)
        self.assertFalse(opt.is_on)

    # ── scope ───────────────────────────────────────────────────────────

    def test_no_scope_action_when_scopeless(self):
        _le, opt = self._make()
        self.assertIsNone(opt.scope_action)
        self.assertIsNone(opt.scope)

    def test_scope_defaults_then_set(self):
        s = _DictSettings()
        _le, opt = self._make(
            settings=s, scopes=SCOPES, scope_key="f.scope", default_scope="both"
        )
        self.assertIsNotNone(opt.scope_action)
        self.assertEqual(opt.scope, "both")
        opt.set_scope("tags")
        self.assertEqual(opt.scope, "tags")
        self.assertEqual(s.value("f.scope"), "tags")

    def test_scope_restored_from_settings(self):
        s = _DictSettings({"f.scope": "tags"})
        _le, opt = self._make(
            settings=s, scopes=SCOPES, scope_key="f.scope", default_scope="both"
        )
        self.assertEqual(opt.scope, "tags")

    def test_set_scope_rejects_unknown(self):
        _le, opt = self._make(scopes=SCOPES, scope_key="f.scope", default_scope="both")
        opt.set_scope("bogus")
        self.assertEqual(opt.scope, "both", "unknown scope is ignored")

    def test_set_scope_notify_fires_callback(self):
        seen = []
        _le, opt = self._make(
            scopes=SCOPES,
            scope_key="f.scope",
            default_scope="both",
            on_scope_changed=lambda k: seen.append(k),
        )
        opt.set_scope("name", notify=True)
        self.assertEqual(seen, ["name"])
        opt.set_scope("tags")  # notify defaults False
        self.assertEqual(seen, ["name"], "silent set must not fire on_scope_changed")


class TestCompatibilityGate(QtBaseTestCase):
    """is_compatible() + the OptionBoxManager.add_option skip-with-warning gate."""

    def test_base_option_compatible_with_anything(self):
        self.assertTrue(BaseOption.is_compatible(QtWidgets.QLineEdit()))
        self.assertTrue(BaseOption.is_compatible(None))

    def test_filter_option_requires_text_widget(self):
        self.assertTrue(FilterOption.is_compatible(QtWidgets.QLineEdit()))
        # QPushButton has text/setText but no textChanged signal → incompatible.
        self.assertFalse(FilterOption.is_compatible(QtWidgets.QPushButton()))
        self.assertFalse(FilterOption.is_compatible(None))

    def test_manager_skips_incompatible_option(self):
        button = self.track_widget(QtWidgets.QPushButton())
        mgr = OptionBoxManager(button)
        opt = FilterOption(wrapped_widget=button)
        mgr.add_option(opt)
        self.assertIsNone(
            mgr.find_option(FilterOption),
            "FilterOption must be skipped on a non-text host",
        )

    def test_manager_keeps_compatible_option(self):
        le = self.track_widget(QtWidgets.QLineEdit())
        mgr = OptionBoxManager(le)
        opt = FilterOption(wrapped_widget=le)
        mgr.add_option(opt)
        self.assertIs(mgr.find_option(FilterOption), opt)


class TestSetFilterManager(QtBaseTestCase):
    """The fluent OptionBoxManager.set_filter entry point + scope-button gating."""

    def test_set_filter_adds_filter_and_scope(self):
        from uitk.widgets.optionBox.options.action import ActionOption

        le = self.track_widget(QtWidgets.QLineEdit())
        mgr = OptionBoxManager(le)
        mgr.set_filter(
            settings=_DictSettings(),
            text_key="t",
            on_changed=lambda: None,
            scopes=SCOPES,
            scope_key="s",
            default_scope="both",
        )
        filt = mgr.find_option(FilterOption)
        self.assertIsNotNone(filt)
        # The scope cycle is a sibling ActionOption added beside the filter.
        self.assertIs(mgr.find_option(ActionOption), filt.scope_action)

    def test_set_filter_skips_scope_on_incompatible_host(self):
        from uitk.widgets.optionBox.options.action import ActionOption

        button = self.track_widget(QtWidgets.QPushButton())
        mgr = OptionBoxManager(button)
        mgr.set_filter(
            settings=_DictSettings(),
            text_key="t",
            on_changed=lambda: None,
            scopes=SCOPES,
            scope_key="s",
            default_scope="both",
        )
        self.assertIsNone(mgr.find_option(FilterOption))
        self.assertIsNone(
            mgr.find_option(ActionOption),
            "no orphan scope button without its filter on a non-text host",
        )

    def test_set_filter_scopeless_adds_only_filter(self):
        from uitk.widgets.optionBox.options.action import ActionOption

        le = self.track_widget(QtWidgets.QLineEdit())
        mgr = OptionBoxManager(le)
        mgr.set_filter(settings=_DictSettings(), text_key="t", on_changed=lambda: None)
        self.assertIsNotNone(mgr.find_option(FilterOption))
        self.assertIsNone(mgr.find_option(ActionOption))


if __name__ == "__main__":
    unittest.main()
