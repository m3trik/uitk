# !/usr/bin/python
# coding=utf-8
"""Unit tests for the pure menu-resolution functions.

These tests don't touch Qt or the event loop — they verify the
state-to-menu mapping rules in isolation.
"""

import unittest
from unittest import mock

from uitk.widgets.marking_menu._resolver import (
    LEFT_BUTTON,
    RIGHT_BUTTON,
    MIDDLE_BUTTON,
    CTRL_MOD,
    MenuResolver,
)

build_state_key = MenuResolver.build_state_key
count_buttons = MenuResolver.count_buttons
parse_binding_keys = MenuResolver.parse_binding_keys
priority_button = MenuResolver.priority_button
resolve_target_menu = MenuResolver.resolve_target_menu


# Bindings shared across most tests, mirroring the TclMaya defaults.
DEFAULTS = {
    "Key_F12": "hud",
    "Key_F12|LeftButton": "cameras",
    "Key_F12|MiddleButton": "editors",
    "Key_F12|RightButton": "main",
    "Key_F12|LeftButton|RightButton": "maya",
}


class TestBuildStateKey(unittest.TestCase):
    def test_activation_only(self):
        self.assertEqual(build_state_key("Key_F12", 0, 0), "Key_F12")

    def test_button_appended_and_sorted(self):
        self.assertEqual(
            build_state_key("Key_F12", LEFT_BUTTON, 0), "Key_F12|LeftButton"
        )

    def test_chord_alphabetical(self):
        self.assertEqual(
            build_state_key("Key_F12", LEFT_BUTTON | RIGHT_BUTTON, 0),
            "Key_F12|LeftButton|RightButton",
        )

    def test_modifier(self):
        self.assertEqual(
            build_state_key("Key_F12", LEFT_BUTTON, CTRL_MOD),
            "ControlModifier|Key_F12|LeftButton",
        )


class TestPriorityAndCount(unittest.TestCase):
    def test_priority_picks_right_over_left(self):
        self.assertEqual(priority_button(LEFT_BUTTON | RIGHT_BUTTON), RIGHT_BUTTON)

    def test_priority_picks_middle_over_left(self):
        self.assertEqual(priority_button(LEFT_BUTTON | MIDDLE_BUTTON), MIDDLE_BUTTON)

    def test_priority_picks_right_over_middle(self):
        self.assertEqual(priority_button(MIDDLE_BUTTON | RIGHT_BUTTON), RIGHT_BUTTON)

    def test_priority_no_buttons(self):
        self.assertEqual(priority_button(0), 0)

    def test_count_buttons(self):
        self.assertEqual(count_buttons(0), 0)
        self.assertEqual(count_buttons(LEFT_BUTTON), 1)
        self.assertEqual(count_buttons(LEFT_BUTTON | RIGHT_BUTTON), 2)
        self.assertEqual(count_buttons(LEFT_BUTTON | RIGHT_BUTTON | MIDDLE_BUTTON), 3)


class TestResolveTargetMenu(unittest.TestCase):
    def resolve(self, **state):
        state.setdefault("activation_held", True)
        state.setdefault("activation_key_str", "Key_F12")
        state.setdefault("buttons", 0)
        state.setdefault("modifiers", 0)
        state.setdefault("bindings", DEFAULTS)
        return resolve_target_menu(**state)

    # --- Activation gating ---

    def test_returns_none_when_activation_not_held(self):
        self.assertIsNone(self.resolve(activation_held=False))

    def test_returns_none_when_activation_key_unknown(self):
        self.assertIsNone(self.resolve(activation_key_str=None))

    # --- Default & single-button cases ---

    def test_no_buttons_returns_default(self):
        self.assertEqual(self.resolve(), "hud")

    def test_left_button(self):
        self.assertEqual(self.resolve(buttons=LEFT_BUTTON), "cameras")

    def test_right_button(self):
        self.assertEqual(self.resolve(buttons=RIGHT_BUTTON), "main")

    def test_middle_button(self):
        self.assertEqual(self.resolve(buttons=MIDDLE_BUTTON), "editors")

    # --- Chord cases ---

    def test_chord_left_right_explicit_binding(self):
        """L+R has its own binding -> use it."""
        self.assertEqual(self.resolve(buttons=LEFT_BUTTON | RIGHT_BUTTON), "maya")

    def test_chord_with_no_explicit_binding_falls_back_to_priority(self):
        """L+M has no binding; priority is M -> use editors."""
        self.assertEqual(self.resolve(buttons=LEFT_BUTTON | MIDDLE_BUTTON), "editors")

    def test_chord_three_buttons_falls_back_to_priority(self):
        """L+M+R has no binding; priority is R -> use main (since chord 'maya'
        only matches L+R exactly)."""
        bindings = {**DEFAULTS}
        del bindings["Key_F12|LeftButton|RightButton"]
        self.assertEqual(
            self.resolve(
                buttons=LEFT_BUTTON | MIDDLE_BUTTON | RIGHT_BUTTON,
                bindings=bindings,
            ),
            "main",
        )

    # --- Modifier fallbacks ---

    def test_modifier_strips_when_no_specific_binding(self):
        """Ctrl+L has no binding; strip Ctrl -> cameras."""
        self.assertEqual(
            self.resolve(buttons=LEFT_BUTTON, modifiers=CTRL_MOD), "cameras"
        )

    def test_modifier_specific_binding_wins(self):
        bindings = {**DEFAULTS, "ControlModifier|Key_F12|LeftButton": "ctrl_cams"}
        self.assertEqual(
            self.resolve(buttons=LEFT_BUTTON, modifiers=CTRL_MOD, bindings=bindings),
            "ctrl_cams",
        )

    def test_modifier_only_default(self):
        """Holding F12+Ctrl with no buttons -> default (no Ctrl-specific binding)."""
        self.assertEqual(self.resolve(modifiers=CTRL_MOD), "hud")

    # --- Empty / missing bindings ---

    def test_empty_bindings_returns_none(self):
        self.assertIsNone(self.resolve(bindings={}))

    def test_only_default_bound(self):
        bindings = {"Key_F12": "hud"}
        self.assertEqual(self.resolve(buttons=LEFT_BUTTON, bindings=bindings), "hud")


class TestParseBindingKeys(unittest.TestCase):
    def test_extracts_activation_key(self):
        norm, act = parse_binding_keys({"Key_F12|LeftButton": "x"})
        self.assertEqual(act, "Key_F12")
        self.assertEqual(norm, {"Key_F12|LeftButton": "x"})

    def test_normalizes_part_order(self):
        norm, _ = parse_binding_keys({"LeftButton|Key_F12": "x"})
        self.assertEqual(norm, {"Key_F12|LeftButton": "x"})

    def test_bare_key_name_auto_prefixed(self):
        norm, act = parse_binding_keys({"F12": "x", "F12|LeftButton": "y"})
        self.assertEqual(act, "Key_F12")
        self.assertIn("Key_F12", norm)
        self.assertIn("Key_F12|LeftButton", norm)

    def test_skips_non_string_keys(self):
        norm, _ = parse_binding_keys({"Key_F12": "x", 42: "y"})
        self.assertEqual(norm, {"Key_F12": "x"})


class TestReconcileBindings(unittest.TestCase):
    """Forward-merge of new default bindings into a persisted set.

    Regression: a user whose stored bindings predate a newly-shipped chord
    (e.g. ``F12+L+R`` → ``maya#startmenu``) kept a frozen set and never received
    it — the chord fell through to the RightButton-only sibling (``main#startmenu``).
    """

    @staticmethod
    def _reconcile(defaults, stored):
        from uitk.widgets.marking_menu._marking_menu import MarkingMenu

        return MarkingMenu._reconcile_bindings(defaults, stored)

    def test_first_run_seeds_defaults(self):
        defaults = {"Key_F12": "hud", "Key_F12|LeftButton": "cameras"}
        self.assertEqual(self._reconcile(defaults, None), defaults)

    def test_adds_new_default_key_to_stale_stored(self):
        defaults = {"Key_F12": "hud", "Key_F12|LeftButton|RightButton": "maya"}
        stored = {"Key_F12": "hud"}  # older set, missing the L+R chord
        merged = self._reconcile(defaults, stored)
        self.assertEqual(
            merged, {"Key_F12": "hud", "Key_F12|LeftButton|RightButton": "maya"}
        )

    def test_user_customization_wins_on_overlap(self):
        defaults = {"Key_F12": "hud", "Key_F12|RightButton": "main"}
        stored = {"Key_F12": "my_custom_menu"}  # user rebound the default key
        merged = self._reconcile(defaults, stored)
        self.assertEqual(merged["Key_F12"], "my_custom_menu")  # preserved
        self.assertEqual(merged["Key_F12|RightButton"], "main")  # new default added

    def test_no_write_when_already_current(self):
        defaults = {"Key_F12": "hud"}
        stored = {"Key_F12": "hud", "Key_F12|LeftButton": "user_extra"}
        # stored already covers every default key → nothing to persist
        self.assertIsNone(self._reconcile(defaults, stored))

    def test_empty_defaults_no_write(self):
        self.assertIsNone(self._reconcile({}, None))

    def test_corrupt_stored_reseeds_without_crashing(self):
        # A non-dict from corrupt/legacy QSettings must not be spread into a
        # dict literal (would raise at construction) — re-seed defaults instead.
        defaults = {"Key_F12": "hud"}
        for bad in (["not", "a", "dict"], "string", 42):
            self.assertEqual(self._reconcile(defaults, bad), defaults)

    # --- activation-key eviction ------------------------------------------------------------
    # A menu has exactly ONE activation key, but the resolver elects it by taking the first
    # ``Key_*`` while walking this dict. Merging without eviction let several accumulate and the
    # winner became an insertion-order accident from an earlier session.

    def _activation(self, bindings):
        from uitk.widgets.marking_menu._resolver import MenuResolver

        return MenuResolver.parse_binding_keys(bindings)[1]

    def test_stale_activation_key_is_evicted(self):
        defaults = {"Key_F12": "hud", "Key_F12|RightButton": "main"}
        stored = {"Key_Z": "hud", "Key_Z|RightButton": "main"}  # an earlier key_show
        merged = self._reconcile(defaults, stored)
        self.assertNotIn("Key_Z", merged)
        self.assertEqual(self._activation(merged), "Key_F12")

    def test_requested_key_wins_even_when_already_stored(self):
        """The reported break: a store led by a stale key that ``key_show`` could not dislodge.

        Every requested binding was already present with identical values, so the old merge
        equalled the stored dict and returned None — nothing was rewritten, and the stale leader
        kept winning every launch. Reproduces a real store, which had accumulated four keys.
        """
        defaults = {f"Key_F12{sfx}": t for sfx, t in (("", "hud"), ("|RightButton", "main"))}
        stored = {}
        for key in ("Key_F11", "Key_Z", "Key_F12", "Key_F10"):  # F12 present, but not first
            stored[key] = "hud"
            stored[f"{key}|RightButton"] = "main"
        self.assertEqual(self._activation(stored), "Key_F11")  # what the user was stuck on

        merged = self._reconcile(defaults, stored)
        self.assertIsNotNone(merged, "an eviction must be persisted, not skipped as 'current'")
        self.assertEqual(self._activation(merged), "Key_F12")
        self.assertEqual(sorted({k.split("|")[0] for k in merged}), ["Key_F12"])

    def test_stale_key_in_bare_form_is_also_evicted(self):
        """Eviction must use the resolver's election rule, not a local re-implementation.

        ``parse_binding_keys`` auto-prefixes bare parts, so ``"F11|LeftButton"`` elects
        ``Key_F11``. A hand-rolled "first part starting with Key_" check reports None for it and
        keeps it — leaving behind exactly the kind of entry that can still win the election.
        """
        defaults = {"Key_F12": "hud"}
        stored = {"F11": "hud", "F11|LeftButton": "cameras", "Key_F12": "hud"}
        merged = self._reconcile(defaults, stored)
        self.assertNotIn("F11", merged)
        self.assertNotIn("F11|LeftButton", merged)
        self.assertEqual(self._activation(merged), "Key_F12")

    def test_customizations_on_the_requested_key_survive_eviction(self):
        defaults = {"Key_F12": "hud", "Key_F12|RightButton": "main"}
        stored = {"Key_F12": "my_custom_menu", "Key_Z": "hud"}
        merged = self._reconcile(defaults, stored)
        self.assertEqual(merged["Key_F12"], "my_custom_menu")  # user's edit kept
        self.assertNotIn("Key_Z", merged)  # stale key dropped


class TestBindingStoreKey(unittest.TestCase):
    """Per-host namespacing of the persisted-bindings QSettings key.

    Regression: the QSettings backend is shared by (org, app), so Maya and
    Blender wrote the same ``marking_menu_bindings`` and the F12+L+R chord
    (maya#startmenu vs blender#startmenu) collided — fixing Maya pointed
    Blender's chord at a UI it doesn't have.
    """

    @staticmethod
    def _key(context_tags):
        from uitk.widgets.marking_menu._marking_menu import MarkingMenu

        return MarkingMenu._binding_store_key(context_tags)

    def test_maya_and_blender_keys_differ(self):
        self.assertEqual(self._key({"maya"}), "marking_menu_bindings_maya")
        self.assertEqual(self._key({"blender"}), "marking_menu_bindings_blender")
        self.assertNotEqual(self._key({"maya"}), self._key({"blender"}))

    def test_standalone_keeps_legacy_unsuffixed_key(self):
        self.assertEqual(self._key(None), "marking_menu_bindings")
        self.assertEqual(self._key(set()), "marking_menu_bindings")

    def test_multi_tag_is_deterministic(self):
        # sorted → stable regardless of set iteration order
        self.assertEqual(self._key({"b", "a"}), "marking_menu_bindings_a_b")


class _FakeItem:
    """Stand-in for a ``SettingsManager.SettingItem`` — only ``get`` is exercised."""

    def __init__(self, value):
        self._value = value

    def get(self, default=None):
        return default if self._value is None else self._value


class _FakeSettings:
    """Stand-in for ``SettingsManager``: attribute access yields a stored value by key."""

    def __init__(self, values):
        self._values = values

    def branch(self, _name):
        return self

    def __getattr__(self, name):  # only reached for keys not in __dict__
        return _FakeItem(self._values.get(name))


class TestStoredActivationKey(unittest.TestCase):
    """Reading the key the USER chose, BEFORE a menu exists.

    Written only by ``set_activation_key`` (a real rebind: shortcut editor, Preferences
    panel, adopted DCC keymap edit) — never by construction seeding — so presence is
    provenance. A host launches on this when present; otherwise its own ``key_show``
    default applies, which is also how a changed shipped default reaches exactly the
    installs whose user never rebound. The store is faked so the test never touches a
    real QSettings backend.
    """

    @staticmethod
    def _stored_key(values, context_tags=None):
        from uitk.widgets.marking_menu import _marking_menu as module

        with mock.patch.object(
            module, "SettingsManager", lambda **kw: _FakeSettings(values)
        ):
            return module.MarkingMenu.stored_activation_key(context_tags)

    def test_reads_the_user_chosen_key(self):
        values = {"marking_menu_user_activation_key_maya": "Key_F11"}
        self.assertEqual(self._stored_key(values, {"maya"}), "Key_F11")

    def test_reads_the_hosts_own_namespace(self):
        """Maya's chosen key must not leak into Blender's launch (the shared-backend hazard)."""
        values = {"marking_menu_user_activation_key_maya": "Key_F11"}
        self.assertEqual(self._stored_key(values, {"maya"}), "Key_F11")
        self.assertIsNone(self._stored_key(values, {"blender"}))

    def test_seeded_chords_alone_are_not_a_user_choice(self):
        """The chord table is written by construction seeding every launch; only the
        set_activation_key sidecar is provenance. Treating seeded chords as a choice is
        what froze the shipped default forever for every existing install."""
        values = {
            "marking_menu_bindings_maya": {
                "Key_F11": "hud#startmenu",
                "Key_F11|LeftButton": "cameras#startmenu",
            }
        }
        self.assertIsNone(self._stored_key(values, {"maya"}))

    def test_nothing_stored_returns_none(self):
        self.assertIsNone(self._stored_key({}))

    def test_garbage_value_returns_none(self):
        """A corrupt/legacy value must read as "no choice", not crash a host's startup.
        The write path only stores normalized, validated Qt key names, so anything
        else — a bare un-prefixed key, or a ``Key_``-prefixed name QtCore.Qt doesn't
        have (which would leave the menu un-triggerable) — is garbage by definition."""
        for value in ({}, [], "F12", 0, "", "Key_NotARealKey"):
            with self.subTest(value=value):
                self.assertIsNone(
                    self._stored_key({"marking_menu_user_activation_key": value})
                )

    def test_an_unreadable_store_returns_none(self):
        from uitk.widgets.marking_menu import _marking_menu as module

        def _boom(**_kwargs):
            raise RuntimeError("no QSettings backend")

        with mock.patch.object(module, "SettingsManager", _boom):
            self.assertIsNone(module.MarkingMenu.stored_activation_key({"maya"}))


if __name__ == "__main__":
    unittest.main()
