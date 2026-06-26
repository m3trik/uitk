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
from uitk.widgets.mixins.state_manager import StateManager

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
