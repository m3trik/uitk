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


if __name__ == "__main__":
    unittest.main(verbosity=2)
