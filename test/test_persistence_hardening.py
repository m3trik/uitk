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
from uitk.widgets.mainWindow import MainWindow
from uitk.widgets.comboBox import ComboBox
from uitk.managers.settings_manager import SettingsManager
from uitk.managers.state_manager import StateManager
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


# ===========================================================================
# 4. Combobox populate-time clobber (Qt-native addItems/clear)
# ===========================================================================

class TestComboPopulateClobber(QtBaseTestCase):
    """A uitk ``ComboBox`` populated via the Qt-native API after registration
    must not persist the populate-time ``currentIndexChanged`` over the user's
    stored selection.

    Repro of the "combobox doesn't restore across sessions" bug: the map-packer
    populates its channel combos in the slot-class ``__init__`` — *outside*
    ``init_slot``'s signal-blocked wrap — so on reopen ``addItems`` fired
    ``currentIndexChanged(0)``, the switchboard saved ``0``, and restore then
    read back the clobbered ``0``.  ``ComboBox`` now blocks its own signals
    across structural mutations (matching ``add()``'s ``@Signals.blockSignals``),
    so populating is inert with respect to state.
    """

    ORG = "uitk_combo_clobber_test"
    KEY = "cmb_chan/currentIndexChanged"
    ITEMS = ["None", "Metallic", "Roughness"]

    def _settings(self):
        sm = SettingsManager(org=self.ORG, app="main")
        sm.settings.clear()
        sm.settings.sync()
        return sm

    def tearDown(self):
        sm = SettingsManager(org=self.ORG, app="main")
        sm.settings.clear()
        sm.settings.sync()
        super().tearDown()

    def _registered_combo(self, sm, name="cmb_chan"):
        """A fresh window + registered ComboBox sharing ``sm`` (one 'session')."""
        sb = Switchboard()
        win = self.track_widget(
            MainWindow(
                name, sb, settings=sm, central_widget=QtWidgets.QWidget()
            )
        )
        c = ComboBox()
        c.setObjectName("cmb_chan")
        c.setParent(win.centralWidget())
        win.register_widget(c)  # wires on_child_changed -> save; restore_state -> True
        return win, c

    def test_populate_writes_no_state(self):
        """addItems on a registered, restore_state combo persists nothing."""
        sm = self._settings()
        win, c = self._registered_combo(sm, "ui_a")
        c.addItems(self.ITEMS)
        self.assertIsNone(
            sm.value(self.KEY),
            "populating the combo persisted a transient index (clobber risk)",
        )

    def test_additem_loop_writes_no_state(self):
        """A singular-``addItem`` populate loop is also inert.

        Distinct from ``addItems``: the first ``addItem`` moves the index
        ``-1 -> 0`` and fires ``currentIndexChanged`` just the same. This is the
        dominant population idiom in the consumer slots (``for text, data: cmb.
        addItem(...)``), so its override needs its own guard — without it a future
        "the singular override is redundant" cleanup would silently reopen the
        clobber at those call sites.
        """
        sm = self._settings()
        win, c = self._registered_combo(sm, "ui_a")
        for text in self.ITEMS:
            c.addItem(text)
        self.assertIsNone(
            sm.value(self.KEY),
            "a singular addItem() loop persisted a transient index (clobber risk)",
        )

    def test_reopen_restores_user_selection(self):
        """Cross-session round-trip: a saved selection survives repopulation."""
        sm = self._settings()

        # --- session 1: open, restore, user picks "Metallic" (index 1) ---
        win1, c1 = self._registered_combo(sm, "ui_a")
        c1.addItems(self.ITEMS)
        win1.state.capture_default(c1)
        c1.perform_restore_state()
        c1.setCurrentIndex(1)
        win1.state.save(c1)
        self.assertEqual(sm.value(self.KEY), 1, "user selection failed to save")
        win1.close()

        # --- session 2: reopen; repopulation must not clobber the stored 1 ---
        win2, c2 = self._registered_combo(sm, "ui_b")
        c2.addItems(self.ITEMS)  # the bug trigger
        self.assertEqual(
            sm.value(self.KEY),
            1,
            "repopulating the combo on reopen clobbered the stored selection",
        )
        win2.state.capture_default(c2)
        c2.perform_restore_state()
        self.assertEqual(
            c2.currentIndex(),
            1,
            "combo did not restore the user's selection across sessions",
        )


# ===========================================================================
# 5. Plain-QLineEdit persistence round-trip (coverage gap)
# ===========================================================================

class TestLineEditPersistence(QtBaseTestCase):
    """A registered *plain* (unpromoted) ``QLineEdit`` saves on ``textChanged``
    and restores its value across sessions — the line-edit analogue of the combo
    coverage above. Closes a coverage gap (text widgets had no persistence test).
    """

    ORG = "uitk_lineedit_persist_test"
    KEY = "le_path/textChanged"

    def _settings(self):
        sm = SettingsManager(org=self.ORG, app="main")
        sm.settings.clear()
        sm.settings.sync()
        return sm

    def tearDown(self):
        sm = SettingsManager(org=self.ORG, app="main")
        sm.settings.clear()
        sm.settings.sync()
        super().tearDown()

    def _registered_lineedit(self, sm, win_name):
        """A fresh window + registered *plain* QLineEdit sharing ``sm``."""
        sb = Switchboard()
        win = self.track_widget(
            MainWindow(
                win_name, sb, settings=sm, central_widget=QtWidgets.QWidget()
            )
        )
        le = QtWidgets.QLineEdit()
        le.setObjectName("le_path")
        le.setParent(win.centralWidget())
        win.register_widget(le)  # wires textChanged -> save; restore_state -> True
        return win, le

    def _pump(self):
        for _ in range(10):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 12)

    def test_user_text_round_trips_across_sessions(self):
        """A value typed after restore survives a reopen."""
        sm = self._settings()
        win1, le1 = self._registered_lineedit(sm, "ui_a")
        win1.state.capture_default(le1)
        le1.perform_restore_state()
        le1.setText("C:/proj/sourceimages")  # user edit (post-restore)
        self._pump()
        self.assertEqual(sm.value(self.KEY), "C:/proj/sourceimages")
        win1.close()

        win2, le2 = self._registered_lineedit(sm, "ui_b")
        win2.state.capture_default(le2)
        le2.perform_restore_state()
        self.assertEqual(
            le2.text(),
            "C:/proj/sourceimages",
            "lineedit did not restore the user's value across sessions",
        )

    def test_numeric_looking_text_round_trips(self):
        """A version-like string ("1.10") must not be mangled to a float."""
        sm = self._settings()
        win1, le1 = self._registered_lineedit(sm, "ui_a")
        win1.state.capture_default(le1)
        le1.perform_restore_state()
        le1.setText("1.10")
        self._pump()
        self.assertEqual(sm.value(self.KEY), "1.10")
        win1.close()

        win2, le2 = self._registered_lineedit(sm, "ui_b")
        win2.state.capture_default(le2)
        le2.perform_restore_state()
        self.assertEqual(
            le2.text(), "1.10",
            "numeric-looking text was JSON-mangled across sessions",
        )

    def test_empty_user_text_round_trips(self):
        """An intentionally-cleared field restores as empty (not the .ui default)."""
        sm = self._settings()
        win1, le1 = self._registered_lineedit(sm, "ui_a")
        le1.setText("seed")  # a .ui-style default present at registration
        win1.register_widget(le1)
        win1.state.capture_default(le1)
        le1.perform_restore_state()
        le1.setText("")  # user clears it (post-restore edit)
        self._pump()
        self.assertEqual(sm.value(self.KEY), "")
        win1.close()

        win2, le2 = self._registered_lineedit(sm, "ui_b")
        win2.state.capture_default(le2)
        le2.perform_restore_state()
        self.assertEqual(le2.text(), "", "cleared field did not restore as empty")


class TestTextEditPersistence(QtBaseTestCase):
    """A registered ``QTextEdit`` persists and restores across sessions.

    ``QTextEdit.textChanged`` emits NO payload, so the change relay emitted
    ``None`` and ``sync_widget_values`` dropped it before deriving the real
    value — combined with the ``textChanged`` getter not knowing
    ``toPlainText()``, QTextEdit state never persisted at all. The relay must
    derive the live value from the widget when the signal carries none.
    """

    ORG = "uitk_textedit_persist_test"
    KEY = "te_notes/textChanged"

    def _settings(self):
        sm = SettingsManager(org=self.ORG, app="main")
        sm.settings.clear()
        sm.settings.sync()
        return sm

    def tearDown(self):
        sm = SettingsManager(org=self.ORG, app="main")
        sm.settings.clear()
        sm.settings.sync()
        super().tearDown()

    def _registered_textedit(self, sm, win_name):
        sb = Switchboard()
        win = self.track_widget(
            MainWindow(
                win_name, sb, settings=sm, central_widget=QtWidgets.QWidget()
            )
        )
        te = QtWidgets.QTextEdit()
        te.setObjectName("te_notes")
        te.setParent(win.centralWidget())
        win.register_widget(te)
        return win, te

    def _pump(self):
        for _ in range(10):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 12)

    def test_text_round_trips_across_sessions(self):
        sm = self._settings()
        win1, te1 = self._registered_textedit(sm, "ui_a")
        win1.state.capture_default(te1)
        te1.perform_restore_state()
        te1.setPlainText("session notes")  # user edit (post-restore)
        self._pump()
        self.assertEqual(
            sm.value(self.KEY), "session notes",
            "QTextEdit change never reached the store (no-arg signal dropped)",
        )
        win1.close()

        win2, te2 = self._registered_textedit(sm, "ui_b")
        win2.state.capture_default(te2)
        te2.perform_restore_state()
        self.assertEqual(
            te2.toPlainText(), "session notes",
            "QTextEdit did not restore its value across sessions",
        )


if __name__ == "__main__":
    unittest.main()
