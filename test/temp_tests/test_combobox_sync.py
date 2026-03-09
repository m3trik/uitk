# !/usr/bin/python
# coding=utf-8
"""Diagnostic test: Does ComboBox index sync work end-to-end?

1. Creates two UIs with matching ComboBox widgets.
2. Simulates index change on one.
3. Checks if the other updates.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import unittest
from collections import namedtuple
from qtpy import QtWidgets, QtCore
from uitk import Switchboard


def _make_app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


class TestComboBoxSync(unittest.TestCase):
    """Test ComboBox index sync between related UIs."""

    @classmethod
    def setUpClass(cls):
        cls.app = _make_app()

    def _build_pair(self, name_a, name_b):
        """Build two MainWindows with a shared ComboBox and CheckBox,
        register them as loaded UIs inside a single Switchboard, and
        return (sb, win_a, win_b, cmb_a, cmb_b, chk_a, chk_b).
        """
        sb = Switchboard(ui_source=[])

        # -- build a minimal ui_registry entry for both names ---------
        Entry = namedtuple("Entry", ["dir", "filename", "filepath", "tags"])
        e_a = Entry(dir="", filename=name_a, filepath=f"{name_a}.ui", tags=())
        e_b = Entry(dir="", filename=name_b, filepath=f"{name_b}.ui", tags=())
        sb.registry.ui_registry.named_tuples.extend([e_a, e_b])

        # -- create the MainWindows -----------------------------------
        from uitk.widgets.mainWindow import MainWindow

        win_a = MainWindow(name_a, sb)
        win_b = MainWindow(name_b, sb)

        # Store in loaded_ui namespace (raw name, matching add_ui behavior)
        sb.loaded_ui[name_a] = win_a
        sb.loaded_ui[name_b] = win_b

        # -- Combobox (basic QComboBox -- no header) ------------------
        cmb_a = QtWidgets.QComboBox(win_a)
        cmb_a.setObjectName("cmb_test")
        cmb_a.addItems(["Alpha", "Beta", "Gamma"])
        win_a.register_widget(cmb_a)

        cmb_b = QtWidgets.QComboBox(win_b)
        cmb_b.setObjectName("cmb_test")
        cmb_b.addItems(["Alpha", "Beta", "Gamma"])
        win_b.register_widget(cmb_b)

        # -- Checkbox -------------------------------------------------
        chk_a = QtWidgets.QCheckBox(win_a)
        chk_a.setObjectName("chk_test")
        win_a.register_widget(chk_a)

        chk_b = QtWidgets.QCheckBox(win_b)
        chk_b.setObjectName("chk_test")
        win_b.register_widget(chk_b)

        return sb, win_a, win_b, cmb_a, cmb_b, chk_a, chk_b

    # ------------------------------------------------------------------
    #  simple parent / child   (e.g. polygons  <->  polygons#submenu)
    # ------------------------------------------------------------------
    def test_checkbox_sync_simple(self):
        """Checkbox sync should work for parent/child naming."""
        sb, _, _, _, _, chk_a, chk_b = self._build_pair("testui", "testui#sub")
        self.assertFalse(chk_b.isChecked())
        chk_a.setChecked(True)  # fires toggled → sync
        self.assertTrue(chk_b.isChecked(), "Checkbox did NOT sync (simple)")

    def test_combobox_sync_simple(self):
        """ComboBox index sync should work for parent/child naming."""
        sb, _, _, cmb_a, cmb_b, _, _ = self._build_pair("testui", "testui#sub")
        self.assertEqual(cmb_b.currentIndex(), 0)
        cmb_a.setCurrentIndex(2)  # fires currentIndexChanged → sync
        self.assertEqual(
            cmb_b.currentIndex(), 2, "ComboBox did NOT sync index (simple)"
        )

    # ------------------------------------------------------------------
    #  divergent paths  (e.g. main#startmenu  <->  main#lower#submenu)
    # ------------------------------------------------------------------
    def test_checkbox_sync_divergent(self):
        """Checkbox sync should work for divergent tag paths."""
        sb, _, _, _, _, chk_a, chk_b = self._build_pair(
            "main#startmenu", "main#lower#submenu"
        )
        self.assertFalse(chk_b.isChecked())
        chk_a.setChecked(True)
        self.assertTrue(chk_b.isChecked(), "Checkbox did NOT sync (divergent)")

    def test_combobox_sync_divergent(self):
        """ComboBox index sync should work for divergent tag paths."""
        sb, _, _, cmb_a, cmb_b, _, _ = self._build_pair(
            "main#startmenu", "main#lower#submenu"
        )
        self.assertEqual(cmb_b.currentIndex(), 0)
        cmb_a.setCurrentIndex(2)
        self.assertEqual(
            cmb_b.currentIndex(), 2, "ComboBox did NOT sync index (divergent)"
        )

    # ------------------------------------------------------------------
    #  custom uitk ComboBox (with check_index / header logic)
    # ------------------------------------------------------------------
    def test_uitk_combobox_sync(self):
        """Sync with the uitk ComboBox class (no header)."""
        from uitk.widgets.comboBox import ComboBox

        sb = Switchboard(ui_source=[])
        Entry = namedtuple("Entry", ["dir", "filename", "filepath", "tags"])
        sb.registry.ui_registry.named_tuples.extend([
            Entry("", "ctest", "ctest.ui", ()),
            Entry("", "ctest#sub", "ctest#sub.ui", ()),
        ])

        from uitk.widgets.mainWindow import MainWindow

        win_a = MainWindow("ctest", sb)
        win_b = MainWindow("ctest#sub", sb)
        sb.loaded_ui["ctest"] = win_a
        sb.loaded_ui["ctest#sub"] = win_b

        cmb_a = ComboBox(win_a)
        cmb_a.setObjectName("cmb_test")
        cmb_a.add(["Alpha", "Beta", "Gamma"])
        win_a.register_widget(cmb_a)

        cmb_b = ComboBox(win_b)
        cmb_b.setObjectName("cmb_test")
        cmb_b.add(["Alpha", "Beta", "Gamma"])
        win_b.register_widget(cmb_b)

        # Verify initial state
        print(f"\n[uitk ComboBox] Initial: a={cmb_a.currentIndex()}, b={cmb_b.currentIndex()}")
        print(f"  a.has_header={cmb_a.has_header}, b.has_header={cmb_b.has_header}")
        print(f"  a.derived_type={cmb_a.derived_type}, b.derived_type={cmb_b.derived_type}")
        print(f"  a.default_signals()={cmb_a.default_signals()}, b.default_signals()={cmb_b.default_signals()}")

        # Test sync
        cmb_a.setCurrentIndex(2)
        print(f"[uitk ComboBox] After set a=2: a={cmb_a.currentIndex()}, b={cmb_b.currentIndex()}")
        self.assertEqual(
            cmb_b.currentIndex(), 2, "uitk ComboBox did NOT sync index"
        )

    def test_uitk_combobox_with_header_sync(self):
        """Sync with uitk ComboBox that has a header."""
        from uitk.widgets.comboBox import ComboBox

        sb = Switchboard(ui_source=[])
        Entry = namedtuple("Entry", ["dir", "filename", "filepath", "tags"])
        sb.registry.ui_registry.named_tuples.extend([
            Entry("", "htest", "htest.ui", ()),
            Entry("", "htest#sub", "htest#sub.ui", ()),
        ])

        from uitk.widgets.mainWindow import MainWindow

        win_a = MainWindow("htest", sb)
        win_b = MainWindow("htest#sub", sb)
        sb.loaded_ui["htest"] = win_a
        sb.loaded_ui["htest#sub"] = win_b

        cmb_a = ComboBox(win_a)
        cmb_a.setObjectName("cmb_test")
        cmb_a.add(["Alpha", "Beta", "Gamma"], header="Pick One")
        win_a.register_widget(cmb_a)

        cmb_b = ComboBox(win_b)
        cmb_b.setObjectName("cmb_test")
        cmb_b.add(["Alpha", "Beta", "Gamma"], header="Pick One")
        win_b.register_widget(cmb_b)

        print(f"\n[header ComboBox] Initial: a={cmb_a.currentIndex()}, b={cmb_b.currentIndex()}")
        print(f"  a.has_header={cmb_a.has_header}, b.has_header={cmb_b.has_header}")
        print(f"  a.count={cmb_a.count()}, b.count={cmb_b.count()}")

        # For header combobox, selecting an item momentarily sets the index
        # then check_index resets to -1. Let's test the signal flow:
        received_values = []
        def on_changed(widget, value):
            received_values.append((widget.objectName(), value))

        win_a.on_child_changed.connect(on_changed)

        cmb_a.setCurrentIndex(2)  # This fires currentIndexChanged(2); check_index resets to -1

        print(f"[header ComboBox] After set a=2: a={cmb_a.currentIndex()}, b={cmb_b.currentIndex()}")
        print(f"  received_values={received_values}")

    # ------------------------------------------------------------------
    #  Debug: trace the full signal pathway for standard QComboBox
    # ------------------------------------------------------------------
    def test_signal_trace(self):
        """Trace every step of the sync pipeline for QComboBox."""
        sb, win_a, win_b, cmb_a, cmb_b, _, _ = self._build_pair(
            "trace", "trace#sub"
        )
        print(f"\n--- SIGNAL TRACE ---")
        print(f"  cmb_a.derived_type = {cmb_a.derived_type}")
        print(f"  cmb_a.default_signals() = {cmb_a.default_signals()}")
        print(f"  cmb_a.objectName() = {cmb_a.objectName()}")
        print(f"  cmb_b.objectName() = {cmb_b.objectName()}")

        # Check relatives
        relatives = sb.get_ui_relatives(win_a, upstream=True, downstream=True)
        print(f"  get_ui_relatives(win_a) = {relatives}")
        print(f"  relative objectNames = {[r.objectName() for r in relatives]}")

        for relative in relatives:
            rw = sb.get_widget(cmb_a.objectName(), relative)
            print(f"  get_widget('{cmb_a.objectName()}', '{relative.objectName()}') = {rw}")
            if rw:
                print(f"    rw is cmb_b: {rw is cmb_b}")
                print(f"    rw.derived_type = {rw.derived_type}")

        # Now test the actual sync
        print(f"  BEFORE: cmb_a.index={cmb_a.currentIndex()}, cmb_b.index={cmb_b.currentIndex()}")
        cmb_a.setCurrentIndex(2)
        print(f"  AFTER:  cmb_a.index={cmb_a.currentIndex()}, cmb_b.index={cmb_b.currentIndex()}")

        self.assertEqual(cmb_b.currentIndex(), 2, "ComboBox sync FAILED in trace")


if __name__ == "__main__":
    unittest.main(verbosity=2)
