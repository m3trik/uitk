# !/usr/bin/python
# coding=utf-8
"""Regression coverage for the 2026-06-16 persistence hardening pass.

Three intermittent "values reset to defaults a few sessions later" bugs:

1. **Cross-surface divergence** — the same control is stored under a
   separate per-surface namespace (``<panel>`` vs ``<panel>#submenu`` vs
   ``<panel>#startmenu``).  A change made while a sibling surface was not
   loaded never reached that sibling's store, so reopening it later
   restored a stale/default value.  ``sync_widget_values`` must now
   persist into *every* related surface's store, loaded or not.

2. **Deferred-init default clobber** — the immediate ``init_slot`` path
   blocks signals around slot-init + restore, but the deferred batch path
   did not, so a stateful widget initialized through the deferred path
   (``addItems``/``setChecked`` in its ``*_init``) saved its post-init
   default *before* restore ran, wiping the persisted value.

3. **Combobox index transients** — restoring / repopulating a combobox
   briefly reports ``currentIndex == -1`` (or an out-of-range stored
   index against a not-yet-populated model); persisting that transient
   wiped a valid stored index.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets

from uitk.switchboard import Switchboard
from uitk.widgets.mixins.settings_manager import SettingsManager
from uitk.widgets.mixins.state_manager import StateManager
from uitk.widgets.optionBox.utils import patch_common_widgets

patch_common_widgets()


_UI_HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>{cls}</class>
 <widget class="QMainWindow" name="{name}">
  <widget class="QWidget" name="{central}">
   <layout class="QVBoxLayout" name="vlayout">
{items}
   </layout>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _item(cls, name):
    return f'    <item><widget class="{cls}" name="{name}"/></item>'


def _write_ui(path, name, items, central="centralwidget"):
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            _UI_HEAD.format(
                cls=name.replace("#", "_").capitalize(),
                name=name,
                central=central,
                items="\n".join(items),
            )
        )


class _Base(QtBaseTestCase):
    TEST_ORG = "uitk_hardening_test"
    TEST_APP = "main"

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        sm = SettingsManager(org=self.TEST_ORG, app=self.TEST_APP)
        sm.settings.clear()
        sm.settings.sync()

    def tearDown(self):
        sm = SettingsManager(org=self.TEST_ORG, app=self.TEST_APP)
        sm.settings.clear()
        sm.settings.sync()
        self.tmp.cleanup()
        super().tearDown()

    def _drain(self, pumps=10):
        for _ in range(pumps):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 12)

    def _raw(self, key):
        return SettingsManager(org=self.TEST_ORG, app=self.TEST_APP).value(key)

    def _new_sb(self, slot_class):
        sb = Switchboard(
            ui_source=self.tmp.name, slot_source=slot_class, log_level="WARNING"
        )
        sb.settings = SettingsManager(
            org=self.TEST_ORG, app=self.TEST_APP, namespace="switchboard"
        )
        return sb

    def _load(self, sb, ui_name, register=True):
        ui = getattr(sb.loaded_ui, ui_name)
        self.track_widget(ui)
        ui.settings = sb.settings.branch(ui.objectName())
        ui.state = StateManager(ui.settings)
        if register:
            ui.register_children()
            self._drain()
        return ui


# ===========================================================================
# 1. Cross-surface divergence
# ===========================================================================

class TestCrossSurfaceSync(_Base):
    """A change in the panel must persist into a sibling surface's store
    even when that surface was never opened this session."""

    def _build(self):
        items = [_item("QCheckBox", "chk_x")]
        _write_ui(os.path.join(self.tmp.name, "repro.ui"), "repro", items)
        _write_ui(
            os.path.join(self.tmp.name, "repro#submenu.ui"), "repro#submenu", items
        )

        class Repro:
            def __init__(s, switchboard, **_):
                s.sb = switchboard

        return Repro

    def test_change_in_panel_reaches_unloaded_submenu_store(self):
        slot = self._build()
        sb = self._new_sb(slot)
        panel = self._load(sb, "repro")  # submenu intentionally NOT loaded

        panel.chk_x.setChecked(True)
        self._drain()

        # Panel's own store.
        self.assertEqual(
            self._raw("switchboard/repro/chk_x/toggled"), True
        )
        # The sibling surface's store must have been written too, despite
        # never being shown/registered this session.
        self.assertEqual(
            self._raw("switchboard/repro#submenu/chk_x/toggled"),
            True,
            "value did not propagate to the unloaded sibling surface's store "
            "(cross-surface divergence regression)",
        )

    def test_submenu_restores_value_set_from_panel(self):
        slot = self._build()
        sb = self._new_sb(slot)
        panel = self._load(sb, "repro")
        panel.chk_x.setChecked(True)
        self._drain()

        # Now open the submenu surface for the first time.
        submenu = self._load(sb, "repro#submenu")
        self.assertTrue(
            submenu.chk_x.isChecked(),
            "sibling surface did not restore the value set from the panel",
        )


# ===========================================================================
# 2. Deferred-init batch runs under save-suppression
# ===========================================================================

class TestDeferredBatchSuppressesSaves(_Base):
    """The deferred-widget batch (slots.py ``_process_deferred_widgets``)
    must run under ``state.suppress_save`` so a widget's ``*_init`` value
    mutations can't be persisted *before* restore — mirroring the
    signal-blocked immediate path.  Asserted at the batch boundary because
    a stateful widget only reaches the deferred path via re-entrant
    slot-instance creation, which is impractical to drive end-to-end."""

    def test_process_deferred_widgets_suppresses_saves(self):
        items = [_item("QPushButton", "tb000")]
        _write_ui(os.path.join(self.tmp.name, "drepro.ui"), "drepro", items)

        class DRepro:
            def __init__(s, switchboard, **_):
                s.sb = switchboard

        sb = self._new_sb(DRepro)
        ui = self._load(sb, "drepro")

        seen = {}
        orig = sb._perform_slot_init

        def spy(u, w):
            # Record the suppression depth at the moment a deferred widget's
            # slot init runs — this is where init-time signals would fire.
            seen.setdefault("depth", []).append(u.state._save_suppressed)
            return orig(u, w)

        sb._perform_slot_init = spy
        try:
            sb._process_deferred_widgets(ui, [ui.tb000])
        finally:
            sb._perform_slot_init = orig

        self.assertTrue(seen.get("depth"), "deferred batch never ran slot init")
        self.assertTrue(
            all(d > 0 for d in seen["depth"]),
            "saves were NOT suppressed during the deferred init batch "
            f"(suppression depths seen: {seen['depth']})",
        )


# ===========================================================================
# 3. Combobox index transients
# ===========================================================================

class TestComboIndexTransients(QtBaseTestCase):
    """StateManager must not persist a -1 (no-selection) transient, and
    must not lose a stored index by applying an out-of-range value."""

    def _state(self):
        qs = QtCore.QSettings("uitk_hardening_test", "combo_guard")
        qs.clear()
        return StateManager(qs)

    def _combo(self, items, current):
        cmb = self.track_widget(QtWidgets.QComboBox())
        cmb.setObjectName("cmb_guard")
        cmb.addItems(items)
        cmb.setCurrentIndex(current)
        cmb.derived_type = QtWidgets.QComboBox
        cmb.default_signals = lambda: "currentIndexChanged"
        cmb.restore_state = True
        return cmb

    def test_save_skips_no_selection_transient(self):
        state = self._state()
        cmb = self._combo(["a", "b", "c"], 2)
        state.save(cmb, 2)
        # Model momentarily cleared → currentIndex == -1.
        state.save(cmb, -1)
        self.assertEqual(
            state.qsettings.value("cmb_guard/currentIndexChanged"),
            2,
            "a -1 (no-selection) transient clobbered the stored index",
        )

    def test_apply_ignores_out_of_range_index(self):
        state = self._state()
        cmb = self._combo(["a", "b", "c"], 1)
        # Stored index 10 applied against a 3-item model must not lose the
        # current selection (and the disk value is preserved for a later,
        # fully-populated restore).
        state.apply(cmb, 10)
        self.assertEqual(
            cmb.currentIndex(), 1, "out-of-range apply disturbed the combobox"
        )


if __name__ == "__main__":
    unittest.main()
