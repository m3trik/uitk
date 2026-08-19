# !/usr/bin/python
# coding=utf-8
"""Tests for the Phase-5 visibility policies (BLENDER_PORT_PLAN §3 Phase 5):

1. ``requires`` tag — a widget carrying a ``requires`` Designer property is hidden at
   registration when the switchboard's ``context_tags`` shares no tag with it.
2. Nav auto-hide — a ``MenuButton`` whose ``target`` doesn't resolve against the UI
   registry hides itself.
3. Missing-slot policy hook — ``connect_slot``'s no-slot branch invokes the switchboard's
   ``on_missing_slot`` hook (production default: None/no-op; ``mark_missing_slot`` greys).
4. ``Switchboard.gate`` — the explicit, slot-called availability gate for a tool whose
   external app / plugin / optional package isn't installed, rendered per the persisted
   ``unmet_policy`` ("hide" / "disable" / "show").

All assertions are deterministic product state (``isHidden``/``isEnabled``/recorder lists) —
no OS-dependent visibility/focus outcomes (offscreen-QPA safe).

Run standalone: python -m test.test_visibility_policy
"""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets
from uitk.switchboard import Switchboard
from uitk.widgets.menuButton import MenuButton
from uitk.examples.example import ExampleSlots


class _PolicyTestBase(QtBaseTestCase):
    context_tags = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=ExampleSlots,
            context_tags=self.context_tags,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def register(self, widget, name):
        widget.setObjectName(name)
        self.ui.register_widget(widget)
        return widget


class TestRequiresTag(_PolicyTestBase):
    """`requires` Designer-property filtering against the switchboard's context_tags."""

    context_tags = {"maya"}

    def _button(self, name, requires):
        b = QtWidgets.QPushButton(self.ui)
        b.setProperty("requires", requires)
        return self.register(b, name)

    def test_unmatched_requires_hides(self):
        b = self._button("b900", "blender")
        self.assertTrue(b.isHidden())
        self.assertEqual(getattr(b, "hidden_by_policy", None), "requires")

    def test_matched_requires_stays_visible(self):
        b = self._button("b901", "maya")
        self.assertFalse(b.isHidden())

    def test_alternatives_match_any(self):
        b = self._button("b902", "maya|blender")
        self.assertFalse(b.isHidden())
        b2 = self._button("b903", "blender, max")
        self.assertTrue(b2.isHidden())

    def test_no_requires_property_untouched(self):
        b = QtWidgets.QPushButton(self.ui)
        self.register(b, "b904")
        self.assertFalse(b.isHidden())


class TestRequiresIgnoredWithoutContext(_PolicyTestBase):
    """Empty context_tags (standalone/dev) disables requires filtering entirely."""

    context_tags = None

    def test_requires_ignored(self):
        b = QtWidgets.QPushButton(self.ui)
        b.setProperty("requires", "maya")
        self.register(b, "b905")
        self.assertFalse(b.isHidden())


class TestNavAutoHide(_PolicyTestBase):
    """MenuButton auto-hide when its target doesn't resolve in the UI registry."""

    def test_unresolved_target_hides(self):
        b = MenuButton(self.ui, target="no_such_menu#submenu")
        self.register(b, "b906")
        self.assertTrue(b.isHidden())
        self.assertEqual(getattr(b, "hidden_by_policy", None), "nav-unresolved")

    def test_resolved_target_stays_visible(self):
        self.assertTrue(self.sb.is_registered_ui("example"))
        b = MenuButton(self.ui, target="example")
        self.register(b, "b907")
        self.assertFalse(b.isHidden())

    def test_empty_target_untouched(self):
        b = MenuButton(self.ui)  # may be wired at runtime — never auto-hidden
        self.register(b, "b908")
        self.assertFalse(b.isHidden())

    def test_bare_target_resolves_via_submenu_stays_visible(self):
        """Regression: a bare base-name ``target`` (the marking-menu convention)
        navigates on hover to ``"<target>#submenu"``. The auto-hide must resolve
        the same way — the bare name is never itself a registered filename, so an
        exact-match check wrongly hid every submenu launcher (whole maya menu went
        blank). Here ``"render"`` -> registered ``"render#submenu"`` -> stay visible.
        """
        self.sb.is_registered_ui = lambda name: name == "render#submenu"
        self.assertFalse(self.sb.is_registered_ui("render"))  # bare name is not a filename
        b = MenuButton(self.ui, target="render")
        self.register(b, "b913")
        self.assertFalse(b.isHidden())

    def test_filter_tagged_target_resolves(self):
        """A button carrying ``filterTags`` navigates to ``"<target>#<tags>#submenu"``."""
        self.sb.is_registered_ui = lambda name: name == "polygons#face#submenu"
        b = MenuButton(self.ui, target="polygons", filterTags="face")
        self.register(b, "b914")
        self.assertFalse(b.isHidden())

    def test_bare_target_without_submenu_still_hides(self):
        """No matching direct/submenu/filter-tagged UI -> the launcher is dead -> hidden."""
        self.sb.is_registered_ui = lambda name: False
        b = MenuButton(self.ui, target="unported")
        self.register(b, "b915")
        self.assertTrue(b.isHidden())
        self.assertEqual(getattr(b, "hidden_by_policy", None), "nav-unresolved")


class TestMissingSlotHook(_PolicyTestBase):
    """connect_slot's no-slot branch routes through the on_missing_slot policy hook."""

    def test_default_is_silent_noop(self):
        self.assertIsNone(self.sb.on_missing_slot)
        b = QtWidgets.QPushButton(self.ui)
        self.register(b, "b909")  # no slot in ExampleSlots
        self.assertTrue(b.isEnabled())

    def test_hook_invoked_for_unwired_widget(self):
        seen = []
        self.sb.on_missing_slot = seen.append
        b = QtWidgets.QPushButton(self.ui)
        self.register(b, "b910")
        self.assertIn(b, seen)

    def test_hook_skips_nav_menubutton(self):
        seen = []
        self.sb.on_missing_slot = seen.append
        b = MenuButton(self.ui, target="example")
        self.register(b, "b911")
        self.assertNotIn(b, seen)

    def test_mark_missing_slot_greys_widget(self):
        self.sb.on_missing_slot = self.sb.mark_missing_slot
        b = QtWidgets.QPushButton(self.ui)
        self.register(b, "b912")
        self.assertFalse(b.isEnabled())
        self.assertIn("b912", b.toolTip())


class TestUnmetPolicy(_PolicyTestBase):
    """``Switchboard.unmet_policy`` — the persisted hide/disable/show preference."""

    def setUp(self):
        super().setUp()
        self.sb.unmet_policy = Switchboard.UNMET_POLICY_DEFAULT

    def test_default_is_hide(self):
        self.assertEqual(Switchboard.UNMET_POLICY_DEFAULT, "hide")
        self.assertEqual(self.sb.unmet_policy, "hide")

    def test_round_trips_valid_values(self):
        for mode in Switchboard.UNMET_POLICIES:
            self.sb.unmet_policy = mode
            self.assertEqual(self.sb.unmet_policy, mode)

    def test_invalid_value_falls_back_to_default(self):
        self.sb.unmet_policy = "nonsense"
        self.assertEqual(self.sb.unmet_policy, Switchboard.UNMET_POLICY_DEFAULT)

    def test_policy_is_shared_across_switchboards(self):
        """It is a user preference, not per-instance state -- a second Switchboard
        in the same process (a dev reload) must read the same value."""
        self.sb.unmet_policy = "disable"
        other = Switchboard(ui_source=self.example_module, slot_source=ExampleSlots)
        try:
            self.assertEqual(other.unmet_policy, "disable")
        finally:
            self.sb.unmet_policy = Switchboard.UNMET_POLICY_DEFAULT


class TestGate(_PolicyTestBase):
    """``sb.gate(widget, available, reason)`` — explicit availability gating."""

    def setUp(self):
        super().setUp()
        self.sb.unmet_policy = Switchboard.UNMET_POLICY_DEFAULT

    def tearDown(self):
        self.sb.unmet_policy = Switchboard.UNMET_POLICY_DEFAULT
        super().tearDown()

    def _button(self, name):
        b = QtWidgets.QPushButton(self.ui)
        return self.register(b, name)

    # -- available: always a full restore, whatever the policy ----------------
    def test_available_widget_untouched(self):
        b = self._button("g900")
        self.assertTrue(self.sb.gate(b, True))
        self.assertFalse(b.isHidden())
        self.assertTrue(b.isEnabled())
        self.assertIsNone(getattr(b, "hidden_by_policy", None))

    def test_available_restores_a_previously_gated_widget(self):
        """A re-fired ``*_init`` after the app was installed must undo the gate."""
        b = self._button("g901")
        self.sb.unmet_policy = "disable"
        self.sb.gate(b, False, "Toolbag executable not found.")
        self.assertFalse(b.isEnabled())
        self.assertTrue(self.sb.gate(b, True))
        self.assertTrue(b.isEnabled())
        self.assertFalse(b.isHidden())
        self.assertEqual(b.toolTip(), "")

    def test_available_restore_preserves_a_real_tooltip(self):
        """Restoring must not eat a tooltip the widget legitimately owns."""
        b = self._button("g902")
        b.setToolTip("Send the selection to Toolbag.")
        self.sb.unmet_policy = "disable"
        self.sb.gate(b, False, "Toolbag executable not found.")
        self.sb.gate(b, True)
        self.assertEqual(b.toolTip(), "Send the selection to Toolbag.")

    # -- unavailable: per policy ---------------------------------------------
    def test_hide_policy_hides(self):
        b = self._button("g903")
        self.sb.unmet_policy = "hide"
        self.assertFalse(self.sb.gate(b, False, "RizomUV executable not found."))
        self.assertTrue(b.isHidden())
        self.assertEqual(b.hidden_by_policy, "unmet")

    def test_disable_policy_greys_and_explains(self):
        b = self._button("g904")
        self.sb.unmet_policy = "disable"
        self.assertFalse(self.sb.gate(b, False, "RizomUV executable not found."))
        self.assertFalse(b.isHidden())
        self.assertFalse(b.isEnabled())
        self.assertIn("RizomUV executable not found.", b.toolTip())
        self.assertEqual(b.hidden_by_policy, "unmet")

    def test_show_policy_leaves_widget_usable(self):
        """Dev/passthrough: left exactly as found -- visible, enabled, tooltip kept.

        ``show`` is a pure passthrough, so the reason is deliberately NOT
        surfaced here: only ``disable`` appends it (widgets.py's ``gate``
        docstring says so, and the tooltip is the disabled state's whole point).
        Pinned because nothing else catches the tooltip half drifting.
        """
        b = self._button("g905")
        b.setToolTip("Send the selection to Unity.")
        self.sb.unmet_policy = "show"
        self.assertFalse(self.sb.gate(b, False, "Unity executable not found."))
        self.assertFalse(b.isHidden())
        self.assertTrue(b.isEnabled())
        self.assertEqual(b.toolTip(), "Send the selection to Unity.")

    def test_reason_is_optional(self):
        b = self._button("g906")
        self.sb.unmet_policy = "disable"
        self.sb.gate(b, False)
        self.assertFalse(b.isEnabled())
        self.assertTrue(b.toolTip())  # a generic explanation, not empty

    # -- idempotency / re-entry ----------------------------------------------
    def test_repeated_gating_does_not_stack_tooltips(self):
        """``*_init`` re-fires on every show; the tooltip must not grow."""
        b = self._button("g907")
        b.setToolTip("Round-trip through RizomUV.")
        self.sb.unmet_policy = "disable"
        self.sb.gate(b, False, "RizomUV executable not found.")
        first = b.toolTip()
        self.sb.gate(b, False, "RizomUV executable not found.")
        self.assertEqual(b.toolTip(), first)

    def test_policy_change_applies_on_next_gate_call(self):
        """No widget registry needed -- the next ``*_init`` re-gates."""
        b = self._button("g908")
        self.sb.unmet_policy = "hide"
        self.sb.gate(b, False, "gone")
        self.assertTrue(b.isHidden())
        self.sb.unmet_policy = "disable"
        self.sb.gate(b, False, "gone")
        self.assertFalse(b.isHidden())
        self.assertFalse(b.isEnabled())

    def test_every_policy_transition_fully_respecifies_presentation(self):
        """Switching policy between two gate calls must leave NO stale state.

        Regression: the first cut only un-hid in the ``disable`` branch, so
        ``hide`` -> ``show`` left the widget invisible; and ``disable`` -> ``hide``
        left the appended reason on the tooltip.
        """
        b = self._button("g909")
        b.setToolTip("Base tip.")
        expected = {
            "hide": (True, True, "Base tip."),
            "disable": (False, False, None),
            "show": (False, True, "Base tip."),
        }
        for first in Switchboard.UNMET_POLICIES:
            for second in Switchboard.UNMET_POLICIES:
                with self.subTest(first=first, second=second):
                    self.sb.unmet_policy = first
                    self.sb.gate(b, False, "Reason here.")
                    self.sb.unmet_policy = second
                    self.sb.gate(b, False, "Reason here.")
                    hidden, enabled, tip = expected[second]
                    self.assertEqual(b.isHidden(), hidden)
                    self.assertEqual(b.isEnabled(), enabled)
                    if tip is None:
                        self.assertIn("Reason here.", b.toolTip())
                        self.assertIn("Base tip.", b.toolTip())
                    else:
                        self.assertEqual(b.toolTip(), tip)

    def test_restore_after_any_policy_returns_baseline(self):
        """Whatever policy gated it, ``gate(..., True)`` restores the baseline."""
        for policy in Switchboard.UNMET_POLICIES:
            with self.subTest(policy=policy):
                b = self._button(f"g91{Switchboard.UNMET_POLICIES.index(policy)}")
                b.setToolTip("Original.")
                self.sb.unmet_policy = policy
                self.sb.gate(b, False, "Missing.")
                self.sb.gate(b, True)
                self.assertFalse(b.isHidden())
                self.assertTrue(b.isEnabled())
                self.assertEqual(b.toolTip(), "Original.")
                self.assertIsNone(getattr(b, "hidden_by_policy", None))

    def test_gate_does_not_clobber_a_requires_hidden_widget(self):
        """``gate(..., True)`` must leave a widget hidden by a DIFFERENT policy alone."""
        b = QtWidgets.QPushButton(self.ui)
        b.setProperty("requires", "blender")
        self.register(b, "g920")  # context_tags is None here -> not hidden
        b.setVisible(False)
        b.hidden_by_policy = "requires"
        self.sb.gate(b, True)
        self.assertTrue(b.isHidden())
        self.assertEqual(b.hidden_by_policy, "requires")

    def test_unavailable_gate_does_not_override_a_requires_hide(self):
        """A widget hidden by ``requires`` must STAY hidden when a gate runs on it.

        ``register_widget`` applies ``apply_visibility_policy`` and THEN calls
        ``init_slot``, so a widget hidden for the wrong DCC reaches its panel's
        ``*_init`` and gets gated too. Under ``disable`` the gate's
        ``setVisible(policy != "hide")`` would show a widget this host must never
        show -- the two policies are not equal partners: ``requires`` is a hard
        context exclusion, the gate is a soft "app missing" presentation.
        """
        b = QtWidgets.QPushButton(self.ui)
        self.register(b, "g930")
        b.setVisible(False)
        b.hidden_by_policy = "requires"
        for policy in Switchboard.UNMET_POLICIES:
            with self.subTest(policy=policy):
                self.sb.unmet_policy = policy
                self.sb.gate(b, False, "Toolbag not found.")
                self.assertTrue(b.isHidden(), "requires-hide must win over the gate")
                self.assertEqual(b.hidden_by_policy, "requires")

    def test_unavailable_gate_does_not_override_nav_autohide(self):
        """Same for a MenuButton the nav policy already hid."""
        b = MenuButton(self.ui, target="no_such_menu#submenu")
        self.register(b, "g931")
        self.assertTrue(b.isHidden())
        self.sb.unmet_policy = "disable"
        self.sb.gate(b, False, "Unity not found.")
        self.assertTrue(b.isHidden())
        self.assertEqual(b.hidden_by_policy, "nav-unresolved")

    def test_gate_tolerates_none_widget(self):
        """A slot gating an optional widget must not need a None guard."""
        self.assertFalse(self.sb.gate(None, False, "nope"))
        self.assertTrue(self.sb.gate(None, True))
        self.assertTrue(self.sb.gate(None, lambda: True))

    # -- restore is from the STASH, not to a hardcoded 'on' -------------------
    def test_restore_returns_a_pre_hidden_widget_to_hidden(self):
        """A widget hidden before it was ever gated must not be un-hidden by one.

        The stash used to hold the tooltip alone, so ``_ungate`` assumed
        visibility and enabled-ness were both on and wrote True to each -- the
        app appearing then REVEALED a widget its panel had deliberately hidden.
        """
        b = self._button("g920")
        b.setVisible(False)
        b.setEnabled(False)
        self.sb.unmet_policy = "disable"
        self.sb.gate(b, False, "not installed")
        # ...and the gate must not have revealed it in the first place: a gate
        # may only ever take presentation away.
        self.assertFalse(b.isVisibleTo(self.ui))
        self.sb.gate(b, True)  # the app showed up
        self.assertFalse(b.isVisibleTo(self.ui))
        self.assertFalse(b.isEnabled())

    def test_restore_returns_a_normal_widget_to_visible(self):
        """The ordinary case still restores to on -- the stash records that too."""
        b = self._button("g921")
        self.sb.unmet_policy = "hide"
        self.sb.gate(b, False, "not installed")
        self.assertFalse(b.isVisibleTo(self.ui))
        self.sb.gate(b, True)
        self.assertTrue(b.isVisibleTo(self.ui))
        self.assertTrue(b.isEnabled())

    # -- recheck_gates: the on-demand twin of the *_init re-fire --------------
    def test_recheck_applies_a_policy_change_to_an_open_panel(self):
        b = self._button("g922")
        self.sb.unmet_policy = "hide"
        self.sb.gate(b, False, "not installed")
        self.assertFalse(b.isVisibleTo(self.ui))
        self.sb.unmet_policy = "disable"
        self.assertTrue(self.sb.recheck_gates() >= 1)
        self.assertTrue(b.isVisibleTo(self.ui))
        self.assertFalse(b.isEnabled())

    def test_recheck_re_evaluates_a_callable_gate(self):
        """The mid-session install: the answer changes, nothing rebuilds the panel."""
        installed = {"yes": False}
        b = self._button("g923")
        self.sb.unmet_policy = "hide"
        self.sb.gate(b, lambda: installed["yes"], "not installed")
        self.assertFalse(b.isVisibleTo(self.ui))
        installed["yes"] = True
        self.sb.recheck_gates()
        self.assertTrue(b.isVisibleTo(self.ui))
        self.assertTrue(b.isEnabled())

    def test_recheck_cannot_re_evaluate_a_bool_gate(self):
        """A bool records an ANSWER, not a question -- documented, so pinned."""
        b = self._button("g924")
        self.sb.unmet_policy = "hide"
        self.sb.gate(b, False, "not installed")
        self.sb.recheck_gates()
        self.assertFalse(b.isVisibleTo(self.ui))

    def test_registry_does_not_grow_on_repeated_gating(self):
        """``*_init`` re-fires on every panel show; the registry must not accrete."""
        b = self._button("g925")
        for _ in range(5):
            self.sb.gate(b, False, "not installed")
        entries = [e for e in self.sb._gate_registry if e[0]() is b]
        self.assertEqual(len(entries), 1)


if __name__ == "__main__":
    unittest.main()
