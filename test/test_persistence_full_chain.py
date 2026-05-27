# !/usr/bin/python
# coding=utf-8
"""Regression coverage for widget-state persistence.

Locks down the chain that powers ``MainWindow.state.save`` /
``MainWindow.state.load`` end-to-end:

- dynamic widget add via ``widget.option_box.menu.add(...)``
- mutual-exclusion slot cascades (tentacle polygons pattern)
- simulated session restart (write, tear down, rebuild, restore)
- popup-reparenting Menu add timing
- ``refresh_on_show`` re-init that re-runs ``state.load`` on each show
- branched vs unbranched ``SettingsManager`` wiring
- ``StateManager.save`` syncs per-write — values land on disk without
  relying on host-app close events (see
  :class:`TestSaveSurvivesWithoutExplicitSync`)
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


_UI_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>{cls}</class>
 <widget class="QMainWindow" name="{name}">
  <widget class="QWidget" name="centralwidget">
   <layout class="QVBoxLayout" name="vlayout">
{items}
   </layout>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _make_ui(path, name, button_names):
    items = "\n".join(
        f"    <item><widget class=\"QPushButton\" name=\"{b}\"/></item>"
        for b in button_names
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(_UI_TEMPLATE.format(cls=name.capitalize(), name=name, items=items))


class _PersistBase(QtBaseTestCase):
    """Tmp UI dir + isolated QSettings + drain helper.

    Each test gets a fresh ``Switchboard``; clearing happens via a live
    ``SettingsManager`` instance to avoid the QSettings write-cache
    corruption that can occur when a transient cleared QSettings shares
    scope with a long-lived one.
    """

    TEST_ORG = "uitk_diag_test"
    TEST_APP = "main"

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        # Use the underlying QSettings directly so the clear is committed
        # to disk before any test code creates new QSettings instances.
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
            QtWidgets.QApplication.processEvents(
                QtCore.QEventLoop.AllEvents, 12
            )

    def _make_sb(self, ui_name, button_names, slot_class, use_branch=True):
        """Build a switchboard pointing at a synthetic UI + slot class.

        ``use_branch=True`` mirrors production wiring (``sb.settings``
        carries ``namespace='switchboard'``, each MainWindow gets
        ``sb.settings.branch(name)``).
        """
        ui_path = os.path.join(self.tmp.name, f"{ui_name}.ui")
        _make_ui(ui_path, ui_name, button_names)
        sb = Switchboard(
            ui_source=self.tmp.name,
            slot_source=slot_class,
            log_level="WARNING",
        )
        ui = getattr(sb.loaded_ui, ui_name)
        self.track_widget(ui)
        if use_branch:
            sb.settings = SettingsManager(
                org=self.TEST_ORG, app=self.TEST_APP, namespace="switchboard"
            )
            ui.settings = sb.settings.branch(ui.objectName())
        else:
            ui.settings = SettingsManager(
                org=self.TEST_ORG, app=self.TEST_APP
            )
        ui.state = StateManager(ui.settings)
        ui.register_children()
        self._drain(); self._drain()
        return sb, ui

    def _raw_keys(self):
        """All keys in the isolated test store (no namespace filter)."""
        return sorted(
            SettingsManager(org=self.TEST_ORG, app=self.TEST_APP).keys()
        )


# ===========================================================================
# Scenario 1: single option_box menu, single checkbox (baseline)
# ===========================================================================

class TestSingleOptionBoxCheckbox(_PersistBase):

    def test_toggle_persists_to_branched_namespace(self):
        class Repro:
            def __init__(s, switchboard, **_):
                s.sb = switchboard
                s.ui = switchboard.loaded_ui.repro

            def tb000_init(s, w):
                if not w.is_initialized:
                    w.option_box.menu.add(
                        "QCheckBox", setObjectName="chk_single"
                    )

        sb, ui = self._make_sb("repro", ["tb000"], Repro)
        ui.tb000.option_box.menu.chk_single.setChecked(True)
        self._drain()
        self.assertIn(
            "switchboard/repro/chk_single/toggled", self._raw_keys()
        )


# ===========================================================================
# Scenario 2: polygons-pattern (mutual-exclusion cascade)
# ===========================================================================

class TestPolygonsMutualExclusionCascade(_PersistBase):
    """Mimic polygons tb007_init: chk008/009/010 with mutual-exclusion
    via toggle_multi. The slot cascade fires programmatic setChecked
    calls during the user's toggle; verify the *user's intended final
    state* (not the intermediate cascade) is what persists."""

    def _build(self):
        class Repro:
            def __init__(s, switchboard, **_):
                s.sb = switchboard
                s.ui = switchboard.loaded_ui.repro

            def tb007_init(s, w):
                if not w.is_initialized:
                    w.option_box.menu.add(
                        "QCheckBox", setObjectName="chk008", setChecked=True
                    )
                    w.option_box.menu.add(
                        "QCheckBox", setObjectName="chk009", setChecked=True
                    )
                    w.option_box.menu.add(
                        "QCheckBox", setObjectName="chk010", setChecked=False
                    )

            def chk008(s, state, widget):
                if state:
                    s.sb.toggle_multi(widget.ui, setUnChecked="chk010")

            def chk009(s, state, widget):
                if state:
                    s.sb.toggle_multi(widget.ui, setUnChecked="chk010")

            def chk010(s, state, widget):
                if state:
                    s.sb.toggle_multi(widget.ui, setUnChecked="chk008,chk009")

        return self._make_sb("repro", ["tb007"], Repro)

    def test_toggling_chk010_persists_final_state(self):
        sb, ui = self._build()
        menu = ui.tb007.option_box.menu

        # User clicks chk010 → True. Slot un-checks chk008 and chk009.
        menu.chk010.setChecked(True)
        self._drain()

        keys = self._raw_keys()
        # All three should have keys after the cascade (each fired toggled).
        self.assertIn("switchboard/repro/chk008/toggled", keys)
        self.assertIn("switchboard/repro/chk009/toggled", keys)
        self.assertIn("switchboard/repro/chk010/toggled", keys)
        # And the persisted values reflect the final cascade state.
        sm = SettingsManager(org=self.TEST_ORG, app=self.TEST_APP)
        # SettingsManager.value() parses booleans coming back as JSON.
        self.assertEqual(
            sm.value("switchboard/repro/chk010/toggled"), True
        )
        # The cascade un-checked chk008/009 — those False values must
        # also have persisted (the production bug we're guarding against
        # is values being stuck at their .ui-file defaults).
        self.assertEqual(
            sm.value("switchboard/repro/chk008/toggled"), False
        )
        self.assertEqual(
            sm.value("switchboard/repro/chk009/toggled"), False
        )


# ===========================================================================
# Scenario 3: many widgets, only some toggled
# ===========================================================================

class TestManyWidgetsOnlySomeToggled(_PersistBase):
    """Toggle a subset of widgets across multiple option_box menus and
    verify only those — and the right ones — produce keys."""

    def test_only_toggled_widgets_persist(self):
        class Repro:
            def __init__(s, switchboard, **_):
                s.sb = switchboard
                s.ui = switchboard.loaded_ui.repro

            def tb000_init(s, w):
                if not w.is_initialized:
                    w.option_box.menu.add(
                        "QCheckBox", setObjectName="chk_a"
                    )

            def tb001_init(s, w):
                if not w.is_initialized:
                    w.option_box.menu.add(
                        "QCheckBox", setObjectName="chk_b"
                    )
                    w.option_box.menu.add(
                        "QSpinBox", setObjectName="s_b"
                    )

            def tb002_init(s, w):
                if not w.is_initialized:
                    cmb = w.option_box.menu.add(
                        "QComboBox", setObjectName="cmb_c"
                    )
                    cmb.addItems(["one", "two", "three"])

        sb, ui = self._make_sb(
            "repro", ["tb000", "tb001", "tb002"], Repro
        )

        # Toggle chk_a. Nothing else.
        ui.tb000.option_box.menu.chk_a.setChecked(True)
        self._drain()

        keys = self._raw_keys()
        self.assertIn("switchboard/repro/chk_a/toggled", keys)
        self.assertNotIn("switchboard/repro/chk_b/toggled", keys)
        self.assertNotIn("switchboard/repro/s_b/valueChanged", keys)

        # Now touch the other two.
        ui.tb001.option_box.menu.chk_b.setChecked(True)
        ui.tb001.option_box.menu.s_b.setValue(42)
        ui.tb002.option_box.menu.cmb_c.setCurrentIndex(2)
        self._drain()

        keys = self._raw_keys()
        self.assertIn("switchboard/repro/chk_b/toggled", keys)
        self.assertIn("switchboard/repro/s_b/valueChanged", keys)
        self.assertIn(
            "switchboard/repro/cmb_c/currentIndexChanged", keys
        )

        sm = SettingsManager(org=self.TEST_ORG, app=self.TEST_APP)
        self.assertEqual(sm.value("switchboard/repro/s_b/valueChanged"), 42)
        self.assertEqual(
            sm.value("switchboard/repro/cmb_c/currentIndexChanged"), 2
        )


# ===========================================================================
# Scenario 4: session-restart round-trip
# ===========================================================================

class TestSimulatedSessionRestart(_PersistBase):
    """Toggle, tear down, rebuild — values restore from QSettings."""

    def _build_session(self):
        class Repro:
            def __init__(s, switchboard, **_):
                s.sb = switchboard
                s.ui = switchboard.loaded_ui.repro

            def tb000_init(s, w):
                if not w.is_initialized:
                    w.option_box.menu.add(
                        "QCheckBox",
                        setObjectName="chk_persist",
                        setChecked=False,
                    )
                    w.option_box.menu.add(
                        "QSpinBox", setObjectName="s_persist"
                    )
                    # IMPORTANT: addItems BEFORE state.load runs, so the
                    # restored currentIndex is valid against the populated
                    # model. Tentacle slots that populate comboboxes from
                    # cmds.* should follow the same pattern.
                    cmb = w.option_box.menu.add(
                        "QComboBox", setObjectName="cmb_persist"
                    )
                    cmb.addItems(["x", "y", "z"])

        return self._make_sb("repro", ["tb000"], Repro)

    def test_all_three_widget_types_round_trip(self):
        # Session 1: write values.
        sb1, ui1 = self._build_session()
        menu = ui1.tb000.option_box.menu
        menu.chk_persist.setChecked(True)
        menu.s_persist.setValue(7)
        menu.cmb_persist.setCurrentIndex(2)
        self._drain()
        ui1.settings.sync()
        ui1.close()
        sb1.deleteLater()
        self._drain()

        # Session 2: rebuild from scratch, expect restoration.
        sb2, ui2 = self._build_session()
        menu2 = ui2.tb000.option_box.menu
        self.assertTrue(
            menu2.chk_persist.isChecked(),
            "checkbox not restored across simulated session restart",
        )
        self.assertEqual(
            menu2.s_persist.value(), 7,
            "spinbox value not restored across simulated session restart",
        )
        self.assertEqual(
            menu2.cmb_persist.currentIndex(), 2,
            "combobox index not restored across simulated session restart",
        )


# ===========================================================================
# Scenario 5: option_box menu shown (popup setup) BEFORE add()
# ===========================================================================

class TestMenuShownBeforeAddingWidgets(_PersistBase):
    """Menu does Qt.Tool|FramelessWindowHint reparenting on first show.
    Widgets added AFTER must still walk to the MainWindow correctly."""

    def test_add_after_show_still_persists(self):
        class Repro:
            def __init__(s, switchboard, **_):
                s.sb = switchboard
                s.ui = switchboard.loaded_ui.repro

            def tb000_init(s, w):
                # Don't add in init — we'll add after the menu has been shown.
                pass

        sb, ui = self._make_sb("repro", ["tb000"], Repro)
        menu = ui.tb000.option_box.menu
        menu.show()
        self._drain()
        menu.hide()
        self._drain()

        chk = menu.add("QCheckBox", setObjectName="chk_post_show")
        self._drain(); self._drain()

        self.assertIn(
            chk, ui.widgets,
            "chk added after menu show was not registered with MainWindow",
        )
        self.assertIs(
            getattr(chk, "ui", None), ui,
            "chk.ui not set to MainWindow after post-show add",
        )

        chk.setChecked(True)
        self._drain()
        self.assertIn(
            "switchboard/repro/chk_post_show/toggled", self._raw_keys(),
            "value did not persist for widget added after menu was shown",
        )


# ===========================================================================
# Scenario 6: refresh_on_show re-init does NOT overwrite saved value
# ===========================================================================

class TestReinitDoesNotResetSavedState(_PersistBase):
    """Re-running ``init_slot`` (the ``refresh_on_show`` pattern) calls
    state.load on each registered widget. The load path is wrapped in
    ``suppress_save()`` so the apply doesn't echo back as a save. If
    that suppression leaked, the saved value would either be lost on
    re-init OR get overwritten by the widget's default value."""

    def test_value_survives_repeated_init_slot(self):
        class Repro:
            def __init__(s, switchboard, **_):
                s.sb = switchboard
                s.ui = switchboard.loaded_ui.repro

            def tb000_init(s, w):
                if not w.is_initialized:
                    w.refresh_on_show = True
                    w.option_box.menu.add(
                        "QCheckBox", setObjectName="chk_refresh",
                        setChecked=False,
                    )

        sb, ui = self._make_sb("repro", ["tb000"], Repro)
        menu = ui.tb000.option_box.menu
        chk = menu.chk_refresh

        chk.setChecked(True)
        self._drain()

        sm = SettingsManager(org=self.TEST_ORG, app=self.TEST_APP)
        before = sm.value("switchboard/repro/chk_refresh/toggled")
        self.assertEqual(before, True)

        # Simulate refresh_on_show firing repeatedly. The state.load
        # path inside _perform_state_init will re-apply the stored value
        # under suppress_save() — verify NO spurious save fires and the
        # stored value remains True.
        for _ in range(5):
            ui.tb000.init_slot()
            self._drain()

        self.assertTrue(
            chk.isChecked(),
            "widget reverted to default after repeated init_slot",
        )
        after = sm.value("switchboard/repro/chk_refresh/toggled")
        self.assertEqual(
            after, True,
            "stored value changed during refresh re-inits — suppress_save leaked",
        )


# ===========================================================================
# Scenario 7: branched vs unbranched
# ===========================================================================

class TestBranchedVsUnbranched(_PersistBase):

    def _toggle(self, use_branch):
        class Repro:
            def __init__(s, switchboard, **_):
                s.sb = switchboard
                s.ui = switchboard.loaded_ui.repro

            def tb000_init(s, w):
                if not w.is_initialized:
                    w.option_box.menu.add(
                        "QCheckBox", setObjectName="chk_x"
                    )

        sb, ui = self._make_sb("repro", ["tb000"], Repro, use_branch=use_branch)
        ui.tb000.option_box.menu.chk_x.setChecked(True)
        self._drain()
        return self._raw_keys()

    def test_branched_writes_to_namespaced_key(self):
        keys = self._toggle(use_branch=True)
        self.assertIn("switchboard/repro/chk_x/toggled", keys)

    def test_unbranched_writes_to_bare_key(self):
        keys = self._toggle(use_branch=False)
        self.assertIn("chk_x/toggled", keys)


# ===========================================================================
# Scenario 8: per-save sync makes value visible without explicit sync()
# ===========================================================================

class TestSaveSurvivesWithoutExplicitSync(_PersistBase):
    """Regression for the production scenario: host app exits without
    firing ``MainWindow.closeEvent`` (so the existing
    ``on_close -> settings.sync`` wire never runs).

    Contract: ``StateManager.save()`` itself syncs per-write, so a
    fresh ``QSettings`` instance can see the value without anyone
    calling ``settings.sync()`` between the write and the read.
    """

    def test_value_visible_to_fresh_qsettings_without_explicit_sync(self):
        class Repro:
            def __init__(s, switchboard, **_):
                s.sb = switchboard
                s.ui = switchboard.loaded_ui.repro

            def tb000_init(s, w):
                if not w.is_initialized:
                    w.option_box.menu.add(
                        "QCheckBox", setObjectName="chk_no_sync",
                        setChecked=False,
                    )

        sb, ui = self._make_sb("repro", ["tb000"], Repro)
        ui.tb000.option_box.menu.chk_no_sync.setChecked(True)
        self._drain()

        # NO explicit sync. Brand-new QSettings instance.
        fresh = QtCore.QSettings(self.TEST_ORG, self.TEST_APP)
        keys = fresh.allKeys()
        self.assertIn(
            "switchboard/repro/chk_no_sync/toggled", keys,
            "save() did not sync to disk; the production class of bug where "
            "Maya exits without close events would lose this write",
        )


# ===========================================================================
# Scenario 9: button with both *_init and action method
# ===========================================================================

class TestSlotMethodAndInitCoexist(_PersistBase):
    """Tentacle convention: ``tb000_init`` builds structure, ``tb000``
    runs an action. Toggling a widget under tb000's option_box must NOT
    trigger the action method (it should only trigger the widget's own
    slot)."""

    def test_toggle_does_not_fire_button_action(self):
        action_calls = []

        class Repro:
            def __init__(s, switchboard, **_):
                s.sb = switchboard
                s.ui = switchboard.loaded_ui.repro

            def tb000_init(s, w):
                if not w.is_initialized:
                    w.option_box.menu.add(
                        "QCheckBox", setObjectName="chk_under_button"
                    )

            def tb000(s, widget):
                action_calls.append(True)

        sb, ui = self._make_sb("repro", ["tb000"], Repro)
        ui.tb000.option_box.menu.chk_under_button.setChecked(True)
        self._drain()

        self.assertIn(
            "switchboard/repro/chk_under_button/toggled", self._raw_keys()
        )
        self.assertEqual(
            action_calls, [],
            "toggling a child widget incorrectly fired the parent button's action",
        )


if __name__ == "__main__":
    unittest.main()
