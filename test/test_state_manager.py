# !/usr/bin/python
# coding=utf-8
"""Regression coverage for ``StateManager`` combo persistence modes.

Locks down ``widget.restore_by`` (``"index"`` default / ``"text"`` / ``"data"``):
the fix for a combo whose item list is rebuilt at runtime (e.g. the scene
exporter's FBX-preset combo, populated from a directory scan each show). With
the default index-based persistence a selection saved one session lands on the
wrong item -- or, when the list is now shorter, falls out of range and resets
the combo to item 0 ("resets to None") -- the next session. Persisting by the
item *text* / *data* survives the list reordering, growing, and shrinking.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets

from uitk.widgets.comboBox import ComboBox
from uitk.managers.state_manager import StateManager

# Item dicts standing in for a directory scan of ``*.fbxexportpreset`` files.
LIST_ORIG = {"None": None, "presetA": "/a.fbxexportpreset", "presetB": "/b.fbxexportpreset"}
LIST_REORDERED = {"None": None, "presetB": "/b.fbxexportpreset", "presetA": "/a.fbxexportpreset"}
LIST_SHRUNK = {"None": None, "presetB": "/b.fbxexportpreset"}  # presetA deleted


class _ComboPersistBase(QtBaseTestCase):
    """A real ``ComboBox`` + ``StateManager`` over a throwaway ini store."""

    def setUp(self):
        super().setUp()
        self._dir = tempfile.TemporaryDirectory()
        ini = os.path.join(self._dir.name, "state.ini")
        self.store = QtCore.QSettings(ini, QtCore.QSettings.IniFormat)
        self.sm = StateManager(self.store)

    def tearDown(self):
        self._dir.cleanup()
        super().tearDown()

    def make_combo(self, items, restore_by=None):
        """Build a state-managed combo with the attrs register_widget sets."""
        c = self.track_widget(ComboBox())
        c.setObjectName("cmb000")
        c.restore_state = True
        c.derived_type = QtWidgets.QComboBox  # truthy -> StateManager signal path
        c.default_signals = lambda: "currentIndexChanged"
        if restore_by is not None:
            c.restore_by = restore_by
        c.add(items, clear=True)
        return c


class TestIndexModeIsTheDefault(_ComboPersistBase):
    """Default (no ``restore_by``) keeps the historical index-based behavior."""

    def test_same_list_restores(self):
        c1 = self.make_combo(LIST_ORIG)
        c1.setCurrentIndex(2)
        self.sm.save(c1)
        self.assertEqual(self.store.value("cmb000/currentIndexChanged"), 2)

        c2 = self.make_combo(LIST_ORIG)
        self.sm.load(c2)
        self.assertEqual(c2.currentText(), "presetB")

    def test_shrunk_list_is_the_bug_index_mode_cannot_survive(self):
        # Documents *why* the feature exists: index mode resets to item 0 when
        # the saved index is out of range against a now-shorter list.
        c1 = self.make_combo(LIST_ORIG)
        c1.setCurrentIndex(2)
        self.sm.save(c1)

        c2 = self.make_combo(LIST_SHRUNK)
        self.sm.load(c2)
        self.assertEqual(c2.currentText(), "None")  # NOT presetB


class TestTextMode(_ComboPersistBase):
    """``restore_by='text'`` persists the selection by item text."""

    def test_stores_text_not_index(self):
        c1 = self.make_combo(LIST_ORIG, restore_by="text")
        c1.setCurrentIndex(2)
        self.sm.save(c1)
        self.assertEqual(self.store.value("cmb000/currentIndexChanged"), "presetB")

    def test_survives_reordered_list(self):
        c1 = self.make_combo(LIST_ORIG, restore_by="text")
        c1.setCurrentIndex(2)
        self.sm.save(c1)

        c2 = self.make_combo(LIST_REORDERED, restore_by="text")
        self.sm.load(c2)
        self.assertEqual(c2.currentText(), "presetB")

    def test_survives_shrunk_list(self):
        c1 = self.make_combo(LIST_ORIG, restore_by="text")
        c1.setCurrentIndex(2)
        self.sm.save(c1)

        c2 = self.make_combo(LIST_SHRUNK, restore_by="text")
        self.sm.load(c2)
        self.assertEqual(c2.currentText(), "presetB")

    def test_save_ignores_index_delivered_by_change_signal(self):
        # MainWindow's change wire calls ``state.save(widget, <index>)`` because
        # currentIndexChanged carries the index; text mode must re-derive.
        c1 = self.make_combo(LIST_ORIG, restore_by="text")
        c1.setCurrentIndex(1)
        self.sm.save(c1, value=1)  # the index the signal would pass
        self.assertEqual(self.store.value("cmb000/currentIndexChanged"), "presetA")

    def test_missing_value_keeps_current_selection(self):
        # A saved preset that no longer exists must not force the combo to item 0.
        c1 = self.make_combo(LIST_ORIG, restore_by="text")
        c1.setCurrentIndex(1)  # presetA
        self.sm.save(c1)

        c2 = self.make_combo(LIST_SHRUNK, restore_by="text")  # presetA gone
        c2.setCurrentIndex(1)  # presetB currently
        self.sm.load(c2)
        self.assertEqual(c2.currentText(), "presetB")  # unchanged, not "None"

    def test_apply_none_does_not_select_the_None_item(self):
        # ``None`` is "no stored selection" -- it must NOT be coerced to
        # findText("None") and pick an item literally named "None".
        c = self.make_combo(LIST_ORIG, restore_by="text")
        c.setCurrentIndex(1)  # presetA
        self.sm.apply(c, None)
        self.assertEqual(c.currentText(), "presetA")  # unchanged, not "None"

    def test_transient_empty_does_not_overwrite_stored_value(self):
        # A repopulate that briefly empties the combo must not wipe the saved
        # preset (the identity-mode analog of the index -1 no-selection guard).
        c1 = self.make_combo(LIST_ORIG, restore_by="text")
        c1.setCurrentIndex(2)
        self.sm.save(c1)
        self.assertEqual(self.store.value("cmb000/currentIndexChanged"), "presetB")

        empty = self.make_combo({}, restore_by="text")  # no items -> currentText() == ""
        self.sm.save(empty)
        self.assertEqual(self.store.value("cmb000/currentIndexChanged"), "presetB")

    def test_numeric_looking_name_stays_a_string(self):
        items = {"None": None, "123": "/123.fbxexportpreset"}
        c1 = self.make_combo(items, restore_by="text")
        c1.setCurrentIndex(1)
        self.sm.save(c1)

        c2 = self.make_combo(items, restore_by="text")
        self.sm.load(c2)
        self.assertEqual(c2.currentText(), "123")


class TestTextWidgetStringRoundTrip(_ComboPersistBase):
    """A text widget's JSON-parseable string must survive save -> load.

    ``load`` JSON-decodes stored strings (that is how bools / numbers come
    back from backends that stringify them), so a line edit holding
    ``"1.10"`` restored as ``"1.1"`` and ``"123"`` as ``"123"``-the-int the
    next session. The store side must quote such ambiguous strings so the
    decode restores them verbatim.
    """

    def make_lineedit(self, name="le000"):
        le = self.track_widget(QtWidgets.QLineEdit())
        le.setObjectName(name)
        le.restore_state = True
        le.derived_type = QtWidgets.QLineEdit
        le.default_signals = lambda: "textChanged"
        return le

    def test_numeric_looking_text_round_trips(self):
        for text in ("1.10", "123", "true", "None"):
            le1 = self.make_lineedit()
            le1.setText(text)
            self.sm.save(le1)

            le2 = self.make_lineedit()
            self.sm.load(le2)
            self.assertEqual(
                le2.text(), text,
                f"line-edit text {text!r} was mangled across save/load",
            )

    def test_plain_text_stored_unquoted(self):
        # Non-ambiguous strings keep their raw on-disk form (readability +
        # legacy-reader compatibility).
        le = self.make_lineedit()
        le.setText("C:/proj/sourceimages")
        self.sm.save(le)
        self.assertEqual(
            self.store.value("le000/textChanged"), "C:/proj/sourceimages"
        )


class TestSettingsManagerBackedStore(QtBaseTestCase):
    """StateManager against a ``SettingsManager`` store — the MainWindow mode.

    ``clear()`` / ``clear_custom()`` call ``store.remove(key)``; because
    ``SettingsManager.__getattr__`` manufactures a ``SettingItem`` proxy for
    any unknown attribute, the missing ``remove`` surfaced as a ``TypeError``
    at clear time instead of an ``AttributeError`` at review time.
    """

    ORG = "test_uitk_state_clear"
    APP = "test_app"

    def setUp(self):
        super().setUp()
        from uitk.managers.settings_manager import SettingsManager

        self.settings = SettingsManager(org=self.ORG, app=self.APP)
        self.settings.settings.clear()
        self.settings.settings.sync()
        self.sm = StateManager(self.settings)

    def tearDown(self):
        self.settings.settings.clear()
        self.settings.settings.sync()
        super().tearDown()

    def make_lineedit(self, name="le000"):
        le = self.track_widget(QtWidgets.QLineEdit())
        le.setObjectName(name)
        le.restore_state = True
        le.derived_type = QtWidgets.QLineEdit
        le.default_signals = lambda: "textChanged"
        return le

    def test_clear_removes_stored_state(self):
        le = self.make_lineedit()
        le.setText("hello")
        self.sm.save(le)
        self.assertEqual(self.settings.value("le000/textChanged"), "hello")

        self.sm.clear(le)  # raised TypeError before SettingsManager.remove()
        self.assertIsNone(self.settings.value("le000/textChanged"))

    def test_custom_keys_round_trip_and_clear(self):
        self.sm.save_custom("splitter", [100, 250])
        self.assertEqual(self.sm.load_custom("splitter"), [100, 250])

        # Ambiguous string: must come back as the same string, not a float
        # (the double-decode through SettingsManager mangled it before).
        self.sm.save_custom("version", "1.10")
        self.assertEqual(self.sm.load_custom("version"), "1.10")

        self.sm.clear_custom("splitter")
        self.assertIsNone(self.sm.load_custom("splitter"))

        # The caller's default must come back verbatim, not JSON-decoded.
        self.assertEqual(self.sm.load_custom("missing", "1.10"), "1.10")

    def test_text_state_round_trips_via_settings_manager(self):
        le1 = self.make_lineedit()
        le1.setText("1.10")
        self.sm.save(le1)

        le2 = self.make_lineedit()
        self.sm.load(le2)
        self.assertEqual(le2.text(), "1.10")


class TestDataMode(_ComboPersistBase):
    """``restore_by='data'`` persists the selection by item data."""

    def test_survives_reorder_by_data(self):
        c1 = self.make_combo(LIST_ORIG, restore_by="data")
        c1.setCurrentIndex(2)
        self.sm.save(c1)
        self.assertEqual(
            self.store.value("cmb000/currentIndexChanged"), "/b.fbxexportpreset"
        )

        c2 = self.make_combo(LIST_REORDERED, restore_by="data")
        self.sm.load(c2)
        self.assertEqual(c2.currentText(), "presetB")


if __name__ == "__main__":
    unittest.main()
