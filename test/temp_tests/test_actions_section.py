# !/usr/bin/python
# coding=utf-8
"""Tests for WidgetComboBox persistent actions namespace and PresetManager on_change.

Validates that:
- Actions appear below a separator at the bottom of the dropdown.
- Actions survive add(clear=True) calls.
- Action rows are not selectable.
- actions.clear() removes the section.
- Batch add via dict and list-of-tuples works.
- actions.remove() works by label.
- PresetManager on_change callbacks fire on save/delete/rename.
"""
import sys
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

PACKAGE_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from conftest import QtBaseTestCase
from qtpy import QtWidgets, QtCore

from uitk.widgets.widgetComboBox import WidgetComboBox
from uitk.widgets.mixins.preset_manager import PresetManager
from uitk.widgets.mixins.state_manager import StateManager


# =========================================================================
# WidgetComboBox actions namespace
# =========================================================================
class TestActionsNamespace(QtBaseTestCase):
    """Test the actions namespace on WidgetComboBox."""

    def setUp(self):
        super().setUp()
        self.combo = WidgetComboBox()
        self.track_widget(self.combo)
        self.cb_a = MagicMock()
        self.cb_b = MagicMock()

    # ------------------------------------------------------------------
    # add — single form
    # ------------------------------------------------------------------
    def test_add_single_creates_separator_and_container(self):
        """actions.add('Label', cb) adds separator + container row."""
        self.combo.add(["Item 1", "Item 2", "Item 3"])
        self.combo.actions.add("Action A", self.cb_a)

        # 3 data + 1 separator + 1 container = 5 rows
        self.assertEqual(self.combo._model.rowCount(), 5)
        self.assertEqual(self.combo._action_row_count, 2)

    def test_add_single_returns_qaction(self):
        """add() returns the created QAction."""
        action = self.combo.actions.add("A", self.cb_a)
        self.assertIsInstance(action, QtWidgets.QAction)
        self.assertEqual(action.text(), "A")

    def test_add_multiple_singles(self):
        """Multiple add() calls accumulate actions in container."""
        self.combo.add(["X"])
        self.combo.actions.add("A", self.cb_a)
        self.combo.actions.add("B", self.cb_b)
        # 1 data + sep + 1 container = 3
        self.assertEqual(self.combo._model.rowCount(), 3)
        self.assertEqual(self.combo._action_row_count, 2)

    # ------------------------------------------------------------------
    # add — dict form
    # ------------------------------------------------------------------
    def test_add_dict_batch(self):
        """actions.add({...}) adds all entries at once."""
        self.combo.add(["X"])
        self.combo.actions.add({"A": self.cb_a, "B": self.cb_b})
        # 1 data + sep + 1 container = 3
        self.assertEqual(self.combo._model.rowCount(), 3)

    def test_add_dict_returns_list(self):
        """Batch add returns a list of QActions."""
        result = self.combo.actions.add({"A": self.cb_a, "B": self.cb_b})
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    # ------------------------------------------------------------------
    # add — list-of-tuples form
    # ------------------------------------------------------------------
    def test_add_list_of_tuples(self):
        """actions.add([('Label', cb), ...]) works."""
        self.combo.add(["X"])
        self.combo.actions.add([("A", self.cb_a), ("B", self.cb_b)])
        # 1 data + sep + 1 container = 3
        self.assertEqual(self.combo._model.rowCount(), 3)

    # ------------------------------------------------------------------
    # Survive add(clear=True)
    # ------------------------------------------------------------------
    def test_actions_survive_add_clear(self):
        """Actions persist through add(clear=True) calls."""
        self.combo.add(["A", "B"])
        self.combo.actions.add("Act", self.cb_a)
        self.assertEqual(self.combo._model.rowCount(), 4)  # 2 + sep + container

        self.combo.add(["X", "Y", "Z"], clear=True)
        # 3 data + sep + container = 5
        self.assertEqual(self.combo._model.rowCount(), 5)
        self.assertEqual(self.combo._action_row_count, 2)

    def test_actions_survive_multiple_add_clear_cycles(self):
        """Actions persist across multiple add(clear=True) cycles."""
        self.combo.actions.add({"A": self.cb_a, "B": self.cb_b})

        for n in range(1, 4):
            items = [f"item_{i}" for i in range(n)]
            self.combo.add(items, clear=True)
            expected = n + 2  # n items + sep + 1 container
            self.assertEqual(
                self.combo._model.rowCount(),
                expected,
                f"Failed on cycle with {n} items",
            )

    # ------------------------------------------------------------------
    # Selectability
    # ------------------------------------------------------------------
    def test_action_rows_not_selectable(self):
        """Action container row should not be selectable."""
        self.combo.add(["A"])
        self.combo.actions.add("Act", self.cb_a)

        data_item = self.combo._model.item(0)
        container_item = self.combo._model.item(2)  # 0=data, 1=sep, 2=container

        self.assertTrue(bool(data_item.flags() & QtCore.Qt.ItemIsSelectable))
        self.assertFalse(bool(container_item.flags() & QtCore.Qt.ItemIsSelectable))

    # ------------------------------------------------------------------
    # Action triggering
    # ------------------------------------------------------------------
    def test_action_trigger_fires_callback(self):
        """Clicking an action button inside the container fires the callback."""
        self.combo.add(["A"])
        self.combo.actions.add("Act", self.cb_a)

        # The container is the widget item on the last row.
        container_row = self.combo._model.rowCount() - 1
        container = self.combo._widget_items.get(container_row)
        self.assertIsNotNone(container)

        btns = container.findChildren(QtWidgets.QPushButton)
        self.assertEqual(len(btns), 1)
        btns[0].click()
        self.cb_a.assert_called_once()

    # ------------------------------------------------------------------
    # remove
    # ------------------------------------------------------------------
    def test_remove_by_label(self):
        """actions.remove('Label') removes the matching action."""
        self.combo.add(["X"])
        self.combo.actions.add("A", self.cb_a)
        self.combo.actions.add("B", self.cb_b)
        self.assertEqual(len(self.combo.actions), 2)

        removed = self.combo.actions.remove("A")
        self.assertTrue(removed)
        self.assertEqual(len(self.combo.actions), 1)
        self.assertNotIn("A", self.combo.actions)
        self.assertIn("B", self.combo.actions)

    def test_remove_nonexistent_returns_false(self):
        """actions.remove() returns False when label not found."""
        self.assertFalse(self.combo.actions.remove("ghost"))

    # ------------------------------------------------------------------
    # clear
    # ------------------------------------------------------------------
    def test_clear_removes_section(self):
        """actions.clear() removes all action rows."""
        self.combo.add(["A", "B"])
        self.combo.actions.add({"X": self.cb_a, "Y": self.cb_b})
        self.assertEqual(self.combo._model.rowCount(), 4)  # 2 + sep + container

        self.combo.actions.clear()
        self.assertEqual(self.combo._model.rowCount(), 2)
        self.assertEqual(self.combo._action_row_count, 0)
        self.assertEqual(len(self.combo.actions), 0)

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------
    def test_len(self):
        self.assertEqual(len(self.combo.actions), 0)
        self.combo.actions.add("A", self.cb_a)
        self.assertEqual(len(self.combo.actions), 1)

    def test_bool(self):
        self.assertFalse(self.combo.actions)
        self.combo.actions.add("A", self.cb_a)
        self.assertTrue(self.combo.actions)

    def test_contains(self):
        self.combo.actions.add("A", self.cb_a)
        self.assertIn("A", self.combo.actions)
        self.assertNotIn("B", self.combo.actions)

    # ------------------------------------------------------------------
    # No actions — no section
    # ------------------------------------------------------------------
    def test_no_actions_no_section(self):
        """When no actions are set, add() does not append a section."""
        self.combo.add(["A", "B", "C"])
        self.assertEqual(self.combo._model.rowCount(), 3)
        self.assertEqual(self.combo._action_row_count, 0)


# =========================================================================
# PresetManager on_change callbacks
# =========================================================================
class TestPresetManagerOnChange(QtBaseTestCase):
    """Test PresetManager on_change callback system."""

    def setUp(self):
        super().setUp()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="uitk_preset_cb_"))
        self.qsettings = QtCore.QSettings()
        self.state = StateManager(self.qsettings)

        self.parent_widget = QtWidgets.QWidget()
        self.parent_widget.setObjectName("CallbackTestWindow")
        self.parent_widget.widgets = set()
        self.track_widget(self.parent_widget)

        # Add a simple widget so presets have something to capture
        chk = QtWidgets.QCheckBox("test", self.parent_widget)
        chk.setObjectName("testCheck")
        chk.setChecked(True)
        chk.restore_state = True
        chk.derived_type = "QCheckBox"
        chk.default_signals = lambda: "toggled"
        self.parent_widget.widgets.add(chk)
        self.track_widget(chk)

        self.mgr = PresetManager(self.parent_widget, self.state, preset_dir=self.tmpdir)
        self.callback = MagicMock()
        self.mgr.on_change(self.callback)

    def tearDown(self):
        super().tearDown()
        if self.tmpdir.exists():
            shutil.rmtree(self.tmpdir)

    def test_save_fires_callback(self):
        """on_change callback fires after save()."""
        self.mgr.save("test_preset")
        self.callback.assert_called_once()

    def test_delete_fires_callback(self):
        """on_change callback fires after delete()."""
        self.mgr.save("to_delete")
        self.callback.reset_mock()

        self.mgr.delete("to_delete")
        self.callback.assert_called_once()

    def test_delete_nonexistent_does_not_fire(self):
        """on_change callback does NOT fire if delete() finds no file."""
        self.mgr.delete("ghost")
        self.callback.assert_not_called()

    def test_rename_fires_callback(self):
        """on_change callback fires after rename()."""
        self.mgr.save("old")
        self.callback.reset_mock()

        self.mgr.rename("old", "new")
        self.callback.assert_called_once()

    def test_rename_failure_does_not_fire(self):
        """on_change callback does NOT fire if rename() fails."""
        self.mgr.rename("nonexistent", "new")
        # Only the save() call should have fired the callback
        self.callback.assert_not_called()

    def test_multiple_callbacks(self):
        """Multiple registered callbacks all fire."""
        cb2 = MagicMock()
        self.mgr.on_change(cb2)

        self.mgr.save("multi")
        self.callback.assert_called_once()
        cb2.assert_called_once()

    def test_callback_exception_does_not_propagate(self):
        """A failing callback does not prevent other callbacks from running."""
        bad_cb = MagicMock(side_effect=RuntimeError("boom"))
        good_cb = MagicMock()
        self.mgr.on_change(bad_cb)
        self.mgr.on_change(good_cb)
        self.callback.reset_mock()

        self.mgr.save("resilient")
        # All three callbacks were invoked (self.callback, bad_cb, good_cb)
        self.callback.assert_called_once()
        bad_cb.assert_called_once()
        good_cb.assert_called_once()


if __name__ == "__main__":
    import unittest

    unittest.main()
