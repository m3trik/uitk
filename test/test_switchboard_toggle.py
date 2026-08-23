# !/usr/bin/python
# coding=utf-8
"""``SwitchboardUtilsMixin.toggle_multi`` (trigger mode) and ``enable_when``.

Pins the 2026-08-17 refactor: both share one widget value / signal table,
``toggle_multi`` applies the trigger's CURRENT state at wire time, and
``enable_when`` is the declarative "keep X enabled while Y says so" rule —
order-independent (a target registered later is picked up), multi-trigger,
invertible, idempotent, and re-appliable in bulk via ``refresh_dependencies``.

Run standalone: python -m test.test_switchboard_toggle
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets  # noqa: E402
from uitk.switchboard import Switchboard  # noqa: E402
from uitk.widgets.mainWindow import MainWindow  # noqa: E402


class _Base(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.sb = Switchboard(log_level="WARNING")
        self.central = QtWidgets.QWidget()
        self.layout = QtWidgets.QVBoxLayout(self.central)
        self.ui = MainWindow(
            "toggle_repro", self.sb, central_widget=self.central, log_level="WARNING"
        )
        self.track_widget(self.ui)

    def _add(self, cls, name, **kw):
        w = cls(self.central)
        w.setObjectName(name)
        for k, v in kw.items():
            getattr(w, k)(v)
        self.layout.addWidget(w)
        self.ui.register_widget(w)
        return w

    def _drain(self, pumps=5):
        for _ in range(pumps):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 12)


class TestToggleMultiTrigger(_Base):
    def test_applies_current_state_at_wire_time(self):
        """A trigger already in its 'on' state when wired must put its
        dependants in the matching state — no user click required."""
        chk = self._add(QtWidgets.QCheckBox, "chk_master", setChecked=True)
        spin = self._add(QtWidgets.QSpinBox, "s_dep")
        self.assertTrue(spin.isEnabled())
        self.sb.toggle_multi(
            self.ui,
            trigger="chk_master",
            on_True={"setDisabled": "s_dep"},
            on_False={"setEnabled": "s_dep"},
        )
        self.assertFalse(spin.isEnabled(), "initial apply missing")
        chk.setChecked(False)
        self.assertTrue(spin.isEnabled())

    def test_apply_now_false_keeps_legacy_connect_only(self):
        self._add(QtWidgets.QCheckBox, "chk_master", setChecked=True)
        spin = self._add(QtWidgets.QSpinBox, "s_dep")
        self.sb.toggle_multi(
            self.ui,
            trigger="chk_master",
            apply_now=False,
            on_True={"setDisabled": "s_dep"},
        )
        self.assertTrue(spin.isEnabled())

    def test_default_signal_follows_widget_type(self):
        """A combo trigger with no ``signal`` wires ``currentIndexChanged``
        (the old default was 'toggled', which a combo lacks)."""
        cmb = self._add(QtWidgets.QComboBox, "cmb_mode")
        cmb.addItems(["a", "b"])
        spin = self._add(QtWidgets.QSpinBox, "s_dep")
        self.sb.toggle_multi(
            self.ui,
            trigger="cmb_mode",
            on_0={"setEnabled": "s_dep"},
            on_1={"setDisabled": "s_dep"},
        )
        cmb.setCurrentIndex(1)
        self.assertFalse(spin.isEnabled())


class TestEnableWhen(_Base):
    def test_master_checkbox_truthiness_default(self):
        chk = self._add(QtWidgets.QCheckBox, "chk_master", setChecked=False)
        spin = self._add(QtWidgets.QSpinBox, "s_dep")
        self.sb.enable_when(self.ui, "s_dep", "chk_master")
        self.assertFalse(spin.isEnabled())
        chk.setChecked(True)
        self.assertTrue(spin.isEnabled())

    def test_combo_reads_current_data_and_callable_condition(self):
        cmb = self._add(QtWidgets.QComboBox, "cmb_fmt")
        cmb.addItem("FBX", "fbx")
        cmb.addItem("GLB", "glb")
        cmb.addItem("FBX + GLB", "fbx_glb")
        tex = self._add(QtWidgets.QComboBox, "cmb_tex")
        self.sb.enable_when(self.ui, "cmb_tex", "cmb_fmt", lambda fmt: fmt != "fbx")
        self.assertFalse(tex.isEnabled())
        cmb.setCurrentIndex(2)
        self.assertTrue(tex.isEnabled())
        cmb.setCurrentIndex(0)
        self.assertFalse(tex.isEnabled())

    def test_value_and_membership_conditions_and_invert(self):
        cmb = self._add(QtWidgets.QComboBox, "cmb_mode")
        cmb.addItems(["a", "b", "c"])  # no data -> index is the value
        one = self._add(QtWidgets.QSpinBox, "s_one")
        many = self._add(QtWidgets.QSpinBox, "s_many")
        other = self._add(QtWidgets.QSpinBox, "s_other")
        self.sb.enable_when(self.ui, "s_one", "cmb_mode", 1)
        self.sb.enable_when(self.ui, "s_many", "cmb_mode", {1, 2})
        self.sb.enable_when(self.ui, "s_other", "cmb_mode", {1, 2}, invert=True)
        self.assertEqual(
            (one.isEnabled(), many.isEnabled(), other.isEnabled()), (False, False, True)
        )
        cmb.setCurrentIndex(1)
        self.assertEqual(
            (one.isEnabled(), many.isEnabled(), other.isEnabled()), (True, True, False)
        )
        cmb.setCurrentIndex(2)
        self.assertEqual(
            (one.isEnabled(), many.isEnabled(), other.isEnabled()), (False, True, False)
        )

    def test_multiple_triggers_feed_the_condition_in_order(self):
        opt = self._add(QtWidgets.QCheckBox, "chk_opt", setChecked=False)
        tpl = self._add(QtWidgets.QComboBox, "cmb_tpl")
        tpl.addItem("As Authored", None)
        tpl.addItem("Unity", "unity")
        out = self._add(QtWidgets.QComboBox, "cmb_out")
        self.sb.enable_when(
            self.ui, "cmb_out", ["chk_opt", "cmb_tpl"], lambda o, t: bool(o) or bool(t)
        )
        self.assertFalse(out.isEnabled())
        opt.setChecked(True)
        self.assertTrue(out.isEnabled())
        opt.setChecked(False)
        self.assertFalse(out.isEnabled())
        tpl.setCurrentIndex(1)
        self.assertTrue(out.isEnabled())

    def test_membership_condition_tests_every_trigger(self):
        """A set/list condition over several triggers is ALL-of, not first-only.

        The membership branch was `lambda v, *rest: v in allowed`, so it read
        the first trigger and threw the rest away -- the target enabled on
        cmb_a alone while cmb_b said otherwise. All-of is the only reading that
        matches the `condition is True` branch (already all-of) and the
        docstring's "one value per trigger".
        """
        a = self._add(QtWidgets.QComboBox, "cmb_a")
        b = self._add(QtWidgets.QComboBox, "cmb_b")
        for cmb in (a, b):
            cmb.addItem("fbx", "fbx")
            cmb.addItem("glb", "glb")
        out = self._add(QtWidgets.QSpinBox, "s_out")
        self.sb.enable_when(self.ui, "s_out", ["cmb_a", "cmb_b"], {"fbx"})

        self.assertTrue(out.isEnabled(), "both triggers on fbx -> enabled")
        b.setCurrentIndex(1)  # cmb_b leaves the allowed set
        self.assertFalse(
            out.isEnabled(), "second trigger must be able to veto"
        )
        b.setCurrentIndex(0)
        self.assertTrue(out.isEnabled())
        a.setCurrentIndex(1)  # first trigger leaves it
        self.assertFalse(out.isEnabled())

    def test_equality_condition_tests_every_trigger(self):
        """Same defect, the plain-value branch (`v == condition`)."""
        a = self._add(QtWidgets.QComboBox, "cmb_ea")
        b = self._add(QtWidgets.QComboBox, "cmb_eb")
        for cmb in (a, b):
            cmb.addItems(["zero", "one"])
        out = self._add(QtWidgets.QSpinBox, "s_eq")
        self.sb.enable_when(self.ui, "s_eq", ["cmb_ea", "cmb_eb"], 1)

        a.setCurrentIndex(1)
        b.setCurrentIndex(1)
        self.assertTrue(out.isEnabled(), "both == 1 -> enabled")
        b.setCurrentIndex(0)
        self.assertFalse(out.isEnabled(), "second trigger must be able to veto")

    def test_single_trigger_membership_is_unchanged(self):
        """The counterweight: all-of must not disturb the 1-trigger case,
        which is every existing caller."""
        cmb = self._add(QtWidgets.QComboBox, "cmb_solo")
        cmb.addItem("fbx", "fbx")
        cmb.addItem("glb", "glb")
        out = self._add(QtWidgets.QSpinBox, "s_solo")
        self.sb.enable_when(self.ui, "s_solo", "cmb_solo", {"fbx"})
        self.assertTrue(out.isEnabled())
        cmb.setCurrentIndex(1)
        self.assertFalse(out.isEnabled())

    def test_a_conflicting_second_rule_is_reported_not_silently_dropped(self):
        """Re-wiring the same pair is a no-op by design (an `_init` that
        re-runs must not stack rules) -- but a rule with DIFFERENT semantics
        being dropped silently is a defect, not idempotency."""
        cmb = self._add(QtWidgets.QComboBox, "cmb_conf")
        cmb.addItems(["a", "b"])
        self._add(QtWidgets.QSpinBox, "s_conf")
        self.sb.enable_when(self.ui, "s_conf", "cmb_conf", 0)
        with self.assertLogs(self.sb.logger, level="WARNING") as caught:
            self.sb.enable_when(self.ui, "s_conf", "cmb_conf", 1)
        self.assertTrue(
            any("s_conf" in m for m in caught.output),
            f"the dropped rule must name the target: {caught.output}",
        )

    def test_the_same_rule_spelled_differently_is_not_reported(self):
        """The counterweight to the conflict report: `{1, 2}` and `[1, 2]` mean
        the same thing to the membership branch, so re-wiring one as the other
        is idempotency, not a conflict, and must stay silent."""
        cmb = self._add(QtWidgets.QComboBox, "cmb_same")
        cmb.addItems(["a", "b", "c"])
        self._add(QtWidgets.QSpinBox, "s_same")
        self.sb.enable_when(self.ui, "s_same", "cmb_same", {1, 2})
        with self.assertNoLogs(self.sb.logger, level="WARNING"):
            self.sb.enable_when(self.ui, "s_same", "cmb_same", [2, 1])

    def test_target_registered_later_is_picked_up(self):
        """Order-independence: the rule is declared before the target exists
        (a WidgetComboBox row / option-box item registers after the slot that
        declares the dependency); ``on_child_registered`` completes it."""
        chk = self._add(QtWidgets.QCheckBox, "chk_master", setChecked=False)
        self.sb.enable_when(self.ui, "s_late", "chk_master")
        spin = self._add(QtWidgets.QSpinBox, "s_late")
        self._drain()
        self.assertFalse(spin.isEnabled())
        chk.setChecked(True)
        self.assertTrue(spin.isEnabled())

    def test_trigger_registered_later_is_picked_up(self):
        spin = self._add(QtWidgets.QSpinBox, "s_dep")
        self.sb.enable_when(self.ui, "s_dep", "chk_late")
        chk = self._add(QtWidgets.QCheckBox, "chk_late", setChecked=False)
        self._drain()
        self.assertFalse(spin.isEnabled())
        chk.setChecked(True)
        self.assertTrue(spin.isEnabled())

    def test_same_rule_twice_is_a_noop_and_refresh_reapplies(self):
        chk = self._add(QtWidgets.QCheckBox, "chk_master", setChecked=True)
        spin = self._add(QtWidgets.QSpinBox, "s_dep")
        first = self.sb.enable_when(self.ui, "s_dep", "chk_master")
        second = self.sb.enable_when(self.ui, "s_dep", "chk_master")
        self.assertIs(first, second)
        # A change made with signals blocked (a preset load) is not announced…
        chk.blockSignals(True)
        chk.setChecked(False)
        chk.blockSignals(False)
        self.assertTrue(spin.isEnabled())
        # …until the bulk re-apply.
        self.sb.refresh_dependencies(self.ui)
        self.assertFalse(spin.isEnabled())

    def test_pattern_targets(self):
        chk = self._add(QtWidgets.QCheckBox, "chk_master", setChecked=False)
        spins = [self._add(QtWidgets.QSpinBox, f"s00{i}") for i in range(3)]
        self.sb.enable_when(self.ui, "s000-2", "chk_master")
        self.assertEqual([s.isEnabled() for s in spins], [False] * 3)
        chk.setChecked(True)
        self.assertEqual([s.isEnabled() for s in spins], [True] * 3)


class TestTextFrom(_Base):
    """``text_from`` — enable_when's text counterpart: a widget that names its own
    outcome instead of hiding it behind an option box."""

    def test_applies_at_wire_time_not_just_on_change(self):
        """The step hand-wiring forgets: a connection alone leaves the .ui's text
        standing until the user touches something, which is already wrong whenever a
        source starts non-default or was restored from session state."""
        spin = self._add(QtWidgets.QSpinBox, "s003")
        spin.setValue(30)
        btn = self._add(QtWidgets.QPushButton, "tb000")
        btn.setText("Crease")
        self.sb.text_from(self.ui, "tb000", "s003", "Crease {}".format)
        self.assertEqual(btn.text(), "Crease 30")
        spin.setValue(45)
        self.assertEqual(btn.text(), "Crease 45")

    def test_a_pattern_source_unpacks_and_feeds_one_value_per_widget(self):
        """Unlike enable_when's trigger, which resolves one ref to one widget."""
        boxes = [
            self._add(QtWidgets.QCheckBox, f"chk02{i}", setChecked=False)
            for i in (4, 5, 6)
        ]
        btn = self._add(QtWidgets.QPushButton, "tb003")
        self.sb.text_from(
            self.ui,
            "tb003",
            "chk024-26",
            lambda *on: "Constrain: ON" if any(on) else "Constrain: OFF",
        )
        self.assertEqual(btn.text(), "Constrain: OFF")
        boxes[1].setChecked(True)
        self.assertEqual(btn.text(), "Constrain: ON")
        boxes[1].setChecked(False)
        self.assertEqual(btn.text(), "Constrain: OFF")

    def test_several_sources_feed_the_formatter_in_declared_order(self):
        scope = self._add(QtWidgets.QComboBox, "cmb_scope")
        scope.addItem("Selected Only", "selected")
        scope.addItem("Entire Scene", "all")
        save = self._add(QtWidgets.QComboBox, "cmb_save")
        save.addItem("Alongside Scene File", "scene_dir")
        save.addItem("Prompt for File", "prompt")
        btn = self._add(QtWidgets.QPushButton, "tb003")
        self.sb.text_from(
            self.ui,
            "tb003",
            ["cmb_scope", "cmb_save"],
            lambda scope_, save_: f"{scope_}/{save_}",
        )
        self.assertEqual(btn.text(), "selected/scene_dir")
        scope.setCurrentIndex(1)
        self.assertEqual(btn.text(), "all/scene_dir")
        save.setCurrentIndex(1)
        self.assertEqual(btn.text(), "all/prompt")

    def test_a_per_source_reader_overrides_only_the_named_widget(self):
        """A combo whose items carry data reads as DATA by default; the label is
        what a self-describing button wants to say, so one source opts out."""
        scope = self._add(QtWidgets.QComboBox, "cmb_scope")
        scope.addItem("Selected Only", "selected")
        fmt = self._add(QtWidgets.QComboBox, "cmb_format")
        fmt.addItem("FBX", "fbx")
        fmt.addItem("GLB", "glb")
        btn = self._add(QtWidgets.QPushButton, "tb003")
        self.sb.text_from(
            self.ui,
            "tb003",
            ["cmb_scope", "cmb_format"],
            lambda scope_, fmt_: f"{scope_} {fmt_}",
            value={"cmb_format": lambda w: w.currentText()},
        )
        self.assertEqual(btn.text(), "selected FBX")
        fmt.setCurrentIndex(1)
        self.assertEqual(btn.text(), "selected GLB")

    def test_a_single_callable_reader_applies_to_every_source(self):
        one = self._add(QtWidgets.QComboBox, "cmb_a")
        one.addItem("Alpha", "a")
        two = self._add(QtWidgets.QComboBox, "cmb_b")
        two.addItem("Beta", "b")
        btn = self._add(QtWidgets.QPushButton, "tb000")
        self.sb.text_from(
            self.ui,
            "tb000",
            ["cmb_a", "cmb_b"],
            lambda a, b: f"{a}+{b}",
            value=lambda w: w.currentText(),
        )
        self.assertEqual(btn.text(), "Alpha+Beta")

    def test_a_source_registered_later_is_picked_up(self):
        btn = self._add(QtWidgets.QPushButton, "tb000")
        btn.setText("untouched")
        self.sb.text_from(self.ui, "tb000", "s_late", "Value {}".format)
        # An exact name that does not resolve yet holds the whole rule rather than
        # formatting a partial reading.
        self.assertEqual(btn.text(), "untouched")
        spin = self._add(QtWidgets.QSpinBox, "s_late")
        spin.setValue(7)
        self._drain()
        self.assertEqual(btn.text(), "Value 7")

    def test_a_target_registered_later_is_picked_up(self):
        spin = self._add(QtWidgets.QSpinBox, "s003")
        spin.setValue(3)
        self.sb.text_from(self.ui, "tb_late", "s003", "Crease {}".format)
        btn = self._add(QtWidgets.QPushButton, "tb_late")
        self._drain()
        self.assertEqual(btn.text(), "Crease 3")

    def test_same_rule_twice_is_a_noop_and_refresh_reapplies(self):
        spin = self._add(QtWidgets.QSpinBox, "s003")
        spin.setValue(1)
        btn = self._add(QtWidgets.QPushButton, "tb000")
        first = self.sb.text_from(self.ui, "tb000", "s003", "Crease {}".format)
        second = self.sb.text_from(self.ui, "tb000", "s003", "Crease {}".format)
        self.assertIs(first, second, "an _init that re-runs must not stack rules")
        # A change made with signals blocked (a preset load) is not announced…
        spin.blockSignals(True)
        spin.setValue(9)
        spin.blockSignals(False)
        self.assertEqual(btn.text(), "Crease 1")
        # …until the bulk re-apply, which must reach text rules too, not only
        # enable_when's (they live in separate registries).
        self.sb.refresh_dependencies(self.ui)
        self.assertEqual(btn.text(), "Crease 9")

    def test_refresh_dependencies_still_reaches_enable_when_rules(self):
        """The registry widening must not cost the original its bulk refresh."""
        chk = self._add(QtWidgets.QCheckBox, "chk_master", setChecked=True)
        spin = self._add(QtWidgets.QSpinBox, "s_dep")
        self.sb.enable_when(self.ui, "s_dep", "chk_master")
        self.sb.text_from(self.ui, "chk_master", "s_dep", "Master {}".format)
        chk.blockSignals(True)
        chk.setChecked(False)
        chk.blockSignals(False)
        self.sb.refresh_dependencies(self.ui)
        self.assertFalse(spin.isEnabled())

    def test_a_raising_formatter_leaves_the_text_alone(self):
        """A half-built source must not blank the label or take the panel down."""
        spin = self._add(QtWidgets.QSpinBox, "s003")
        btn = self._add(QtWidgets.QPushButton, "tb000")
        btn.setText("held")

        def boom(_value):
            raise ValueError("not ready")

        self.sb.text_from(self.ui, "tb000", "s003", boom)
        self.assertEqual(btn.text(), "held")
        spin.setValue(5)
        self.assertEqual(btn.text(), "held")

    def test_a_target_that_is_also_a_source_does_not_recurse(self):
        """``setText`` on a line edit emits ``textChanged``, which would re-enter
        apply forever. A hang is the one failure mode a UI helper must not have, so
        the write is fenced."""
        field = self._add(QtWidgets.QLineEdit, "txt000")
        field.setText("a")
        seen = []

        def shout(value):
            seen.append(value)
            return value.upper()

        self.sb.text_from(self.ui, "txt000", "txt000", shout)
        self.assertEqual(field.text(), "A")
        self.assertEqual(seen, ["a"], "the write-back must not re-enter the rule")

    def test_several_targets_share_one_derived_text(self):
        spin = self._add(QtWidgets.QSpinBox, "s003")
        spin.setValue(2)
        buttons = [self._add(QtWidgets.QPushButton, f"b00{i}") for i in range(3)]
        self.sb.text_from(self.ui, "b000-2", "s003", "Crease {}".format)
        self.assertEqual([b.text() for b in buttons], ["Crease 2"] * 3)


class TestTextFromOnAnOptionBoxMenu(_Base):
    """The shape every real caller uses: the ``ui`` is an option box's ``menu``.

    Worth its own case because a Menu is not a MainWindow — it exposes its items as
    attributes (so the names resolve) but has no ``on_child_registered``, so the
    late-registration hook is skipped. That is correct here: an ``_init`` slot adds
    every option before it wires the rule, so there is nothing left to arrive.
    """

    def _button(self, name="tb003"):
        from uitk.widgets.pushButton import PushButton

        btn = PushButton()
        btn.setObjectName(name)
        btn.setText("placeholder")
        self.track_widget(btn)
        return btn

    def test_the_export_button_shape_reads_data_and_label_from_one_menu(self):
        btn = self._button()
        menu = btn.option_box.menu
        scope = menu.add("QComboBox", setObjectName="cmb_scope")
        scope.addItem("Selected Only", "selected")
        scope.addItem("Entire Scene", "all")
        fmt = menu.add("QComboBox", setObjectName="cmb_format")
        fmt.addItem("FBX", "fbx")
        fmt.addItem("GLB", "glb")

        self.sb.text_from(
            menu,
            btn,
            ["cmb_scope", "cmb_format"],
            lambda scope_, fmt_: f"Export {scope_} {fmt_}",
            value={"cmb_format": lambda w: w.currentText()},
        )
        # Scope by DATA (the default reader), format by LABEL (the override).
        self.assertEqual(btn.text(), "Export selected FBX")
        scope.setCurrentIndex(1)
        self.assertEqual(btn.text(), "Export all FBX")
        fmt.setCurrentIndex(1)
        self.assertEqual(btn.text(), "Export all GLB")

    def test_the_constrain_button_shape_unpacks_a_checkbox_pattern(self):
        btn = self._button("tb003")
        menu = btn.option_box.menu
        for name in ("chk024", "chk025", "chk026"):
            menu.add("QCheckBox", setObjectName=name, setText=name)

        self.sb.text_from(
            menu,
            btn,
            "chk024-26",
            lambda *on: "Constrain: ON" if any(on) else "Constrain: OFF",
        )
        self.assertEqual(btn.text(), "Constrain: OFF")
        menu.chk025.setChecked(True)
        self.assertEqual(btn.text(), "Constrain: ON")
        menu.chk025.setChecked(False)
        self.assertEqual(btn.text(), "Constrain: OFF")

    def test_a_rule_that_can_never_fire_says_so(self):
        """The whole reason this class of bug survived: nothing announced it.

        Against a Menu there is no ``on_child_registered``, so resolving nothing at
        wire time is not "waiting" — the names are on another container and the rule
        is dead. Both rules report it, at WARNING, which is the level the suites and
        the app actually run at.
        """
        btn = self._button()
        btn.option_box.menu.add("QCheckBox", setObjectName="chk024", setText="A")

        for wire in (
            lambda: self.sb.text_from(btn.menu, btn, "chk024-26", str),
            lambda: self.sb.text_from(btn.menu, btn, "chk024", str),
            lambda: self.sb.enable_when(btn.menu, "chk024", "chk025"),
        ):
            with self.subTest(wire=wire):
                with self.assertLogs(self.sb.logger, level="WARNING") as caught:
                    wire()
                self.assertTrue(
                    any("can never fire" in line for line in caught.output),
                    caught.output,
                )

    def test_a_rule_wired_to_the_right_menu_stays_quiet(self):
        btn = self._button()
        menu = btn.option_box.menu
        for name in ("chk024", "chk025", "chk026"):
            menu.add("QCheckBox", setObjectName=name, setText=name)
        with self.assertNoLogs(self.sb.logger, level="WARNING"):
            self.sb.text_from(menu, btn, "chk024-26", lambda *on: str(any(on)))
            self.sb.enable_when(menu, "chk025", "chk024")

    def test_holding_for_a_late_registration_is_not_reported_as_dead(self):
        """A MainWindow CAN deliver later, so an unresolved name there is patience,
        not a mistake — the warning must not fire on the order-independent path."""
        with self.assertNoLogs(self.sb.logger, level="WARNING"):
            self.sb.text_from(self.ui, "tb_late", "s_late", "Value {}".format)
            self.sb.enable_when(self.ui, "s_dep_late", "chk_late")
        btn = self._add(QtWidgets.QPushButton, "tb_late")
        spin = self._add(QtWidgets.QSpinBox, "s_late")
        spin.setValue(4)
        self._drain()
        self.assertEqual(btn.text(), "Value 4")

    def test_the_option_box_menu_is_not_the_widgets_context_menu(self):
        """The trap the rule's explicit ``ui`` argument closes: uitk's option box
        deliberately does not reuse ``MenuMixin``'s context menu, so a name pattern
        aimed at ``widget.menu`` resolves to nothing — and iterating nothing connects
        nothing, with no exception and no warning."""
        btn = self._button()
        btn.option_box.menu.add("QCheckBox", setObjectName="chk024", setText="A")
        self.assertIsNot(btn.menu, btn.option_box.menu)
        self.assertIsNotNone(getattr(btn.option_box.menu, "chk024", None))
        self.assertIsNone(getattr(btn.menu, "chk024", None))
        self.assertEqual(
            self.sb.get_widgets_by_string_pattern(btn.menu, "chk024-26"), []
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
