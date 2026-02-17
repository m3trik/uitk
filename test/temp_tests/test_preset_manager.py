# !/usr/bin/python
# coding=utf-8
"""Tests for PresetManager and StateManager.suppress_save.

Validates the full preset lifecycle: save, load, list, delete, rename,
and the interaction with StateManager's suppress_save mechanism.
"""
import sys
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Ensure package root is importable
PACKAGE_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from conftest import QtBaseTestCase, setup_qt_application
from qtpy import QtWidgets, QtCore

from uitk.widgets.mixins.state_manager import StateManager
from uitk.widgets.mixins.settings_manager import SettingsManager
from uitk.widgets.mixins.preset_manager import PresetManager


class TestSuppressSave(QtBaseTestCase):
    """Test StateManager.suppress_save context manager."""

    def setUp(self):
        super().setUp()
        self.qsettings = QtCore.QSettings()
        self.state = StateManager(self.qsettings)

    def test_suppress_save_flag_lifecycle(self):
        """Verify _save_suppressed is False by default, True inside context."""
        self.assertFalse(self.state._save_suppressed)

        with self.state.suppress_save():
            self.assertTrue(self.state._save_suppressed)

        self.assertFalse(self.state._save_suppressed)

    def test_suppress_save_restores_on_exception(self):
        """Verify flag is restored even if an exception occurs."""
        try:
            with self.state.suppress_save():
                raise ValueError("test error")
        except ValueError:
            pass

        self.assertFalse(self.state._save_suppressed)

    def test_save_skipped_when_suppressed(self):
        """Verify QSettings.setValue is not called while suppressed."""
        # Create a real widget to test with
        widget = QtWidgets.QCheckBox("test")
        widget.setObjectName("test_suppress_checkbox")
        widget.restore_state = True
        widget.derived_type = "QCheckBox"
        widget.default_signals = lambda: "toggled"
        self.track_widget(widget)

        with self.state.suppress_save():
            self.state.save(widget, True)

        # The key should NOT be in QSettings
        key = self.state._get_state_key(widget)
        self.assertIsNone(self.qsettings.value(key))


class TestPresetManager(QtBaseTestCase):
    """Test PresetManager save/load/list/delete/rename lifecycle."""

    def setUp(self):
        super().setUp()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="uitk_preset_test_"))
        self.qsettings = QtCore.QSettings()
        self.state = StateManager(self.qsettings)

        # Create a mock parent that mimics MainWindow's widget registry
        self.parent_widget = QtWidgets.QWidget()
        self.parent_widget.setObjectName("TestWindow")
        self.parent_widget.widgets = set()
        self.track_widget(self.parent_widget)

        self.preset_mgr = PresetManager(
            self.parent_widget, self.state, preset_dir=self.tmpdir
        )

        # Create test widgets
        self.chk = self._make_checkbox("myCheckBox", checked=True)
        self.spin = self._make_spinbox("mySpinBox", value=42)
        self.line = self._make_lineedit("myLineEdit", text="hello")

    def tearDown(self):
        super().tearDown()
        if self.tmpdir.exists():
            shutil.rmtree(self.tmpdir)

    def _make_checkbox(self, name, checked=False):
        w = QtWidgets.QCheckBox("test", self.parent_widget)
        w.setObjectName(name)
        w.setChecked(checked)
        w.restore_state = True
        w.derived_type = "QCheckBox"
        w.default_signals = lambda: "toggled"
        self.parent_widget.widgets.add(w)
        self.track_widget(w)
        return w

    def _make_spinbox(self, name, value=0):
        w = QtWidgets.QSpinBox(self.parent_widget)
        w.setObjectName(name)
        w.setRange(0, 100)
        w.setValue(value)
        w.restore_state = True
        w.derived_type = "QSpinBox"
        w.default_signals = lambda: "valueChanged"
        self.parent_widget.widgets.add(w)
        self.track_widget(w)
        return w

    def _make_lineedit(self, name, text=""):
        w = QtWidgets.QLineEdit(self.parent_widget)
        w.setObjectName(name)
        w.setText(text)
        w.restore_state = True
        w.derived_type = "QLineEdit"
        w.default_signals = lambda: "textChanged"
        self.parent_widget.widgets.add(w)
        self.track_widget(w)
        return w

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def test_save_creates_json_file(self):
        """Verify save creates a valid JSON file in the preset directory."""
        path = self.preset_mgr.save("my_preset")
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".json")

        with open(path, "r") as f:
            data = json.load(f)

        self.assertIn("_meta", data)
        self.assertEqual(data["_meta"]["version"], 1)
        self.assertEqual(data["myCheckBox"], True)
        self.assertEqual(data["mySpinBox"], 42)
        self.assertEqual(data["myLineEdit"], "hello")

    def test_save_excludes_non_restorable_widgets(self):
        """Widgets with restore_state=False should not appear in presets."""
        excluded = self._make_checkbox("excludedBox", checked=True)
        excluded.restore_state = False

        path = self.preset_mgr.save("filtered_preset")
        with open(path, "r") as f:
            data = json.load(f)

        self.assertNotIn("excludedBox", data)

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def test_load_restores_values(self):
        """Verify load applies saved values back to widgets."""
        self.preset_mgr.save("restore_test")

        # Change all values
        self.chk.setChecked(False)
        self.spin.setValue(0)
        self.line.setText("changed")

        count = self.preset_mgr.load("restore_test")

        self.assertEqual(count, 3)
        self.assertTrue(self.chk.isChecked())
        self.assertEqual(self.spin.value(), 42)
        self.assertEqual(self.line.text(), "hello")

    def test_load_nonexistent_returns_zero(self):
        """Loading a preset that doesn't exist should return 0."""
        count = self.preset_mgr.load("does_not_exist")
        self.assertEqual(count, 0)

    def test_load_ignores_unknown_keys(self):
        """Keys in the preset that have no matching widget are skipped."""
        # Manually write a preset with an extra key
        path = self.tmpdir / "extra_keys.json"
        with open(path, "w") as f:
            json.dump(
                {"_meta": {"version": 1}, "myCheckBox": False, "phantomWidget": 99}, f
            )

        count = self.preset_mgr.load("extra_keys")
        self.assertEqual(count, 1)  # Only myCheckBox matched
        self.assertFalse(self.chk.isChecked())

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------

    def test_save_with_scope(self):
        """Verify scope limits which widgets are captured."""
        container = QtWidgets.QGroupBox("group", self.parent_widget)
        container.setObjectName("testGroup")
        self.track_widget(container)

        # Move only the checkbox into the container
        scoped_chk = self._make_checkbox("scopedCheck", checked=True)
        scoped_chk.setParent(container)

        path = self.preset_mgr.save("scoped", scope=container)
        with open(path, "r") as f:
            data = json.load(f)

        self.assertIn("scopedCheck", data)
        # Other widgets should NOT be in the scoped preset
        self.assertNotIn("mySpinBox", data)
        self.assertNotIn("myLineEdit", data)

    # ------------------------------------------------------------------
    # List / Delete / Rename / Exists
    # ------------------------------------------------------------------

    def test_list_returns_sorted_names(self):
        """Verify list returns all preset names, sorted."""
        self.preset_mgr.save("zebra")
        self.preset_mgr.save("alpha")
        self.preset_mgr.save("middle")

        names = self.preset_mgr.list()
        self.assertEqual(names, ["alpha", "middle", "zebra"])

    def test_delete_removes_file(self):
        """Verify delete removes the preset file."""
        self.preset_mgr.save("to_delete")
        self.assertTrue(self.preset_mgr.exists("to_delete"))

        result = self.preset_mgr.delete("to_delete")
        self.assertTrue(result)
        self.assertFalse(self.preset_mgr.exists("to_delete"))

    def test_delete_nonexistent_returns_false(self):
        """Deleting a preset that doesn't exist returns False."""
        self.assertFalse(self.preset_mgr.delete("ghost"))

    def test_rename(self):
        """Verify rename changes the file name."""
        self.preset_mgr.save("old_name")
        result = self.preset_mgr.rename("old_name", "new_name")

        self.assertTrue(result)
        self.assertFalse(self.preset_mgr.exists("old_name"))
        self.assertTrue(self.preset_mgr.exists("new_name"))

    def test_rename_to_existing_fails(self):
        """Cannot rename to an already existing preset name."""
        self.preset_mgr.save("first")
        self.preset_mgr.save("second")

        result = self.preset_mgr.rename("first", "second")
        self.assertFalse(result)

    def test_exists(self):
        """Verify exists returns correct bool."""
        self.assertFalse(self.preset_mgr.exists("nope"))
        self.preset_mgr.save("yep")
        self.assertTrue(self.preset_mgr.exists("yep"))

    # ------------------------------------------------------------------
    # Name sanitization
    # ------------------------------------------------------------------

    def test_name_sanitization(self):
        """Verify dangerous characters in preset names are sanitized."""
        path = self.preset_mgr.save("my/preset\\name:bad")
        self.assertTrue(path.exists())
        # Should not contain path separators in the filename
        self.assertNotIn("/", path.stem)
        self.assertNotIn("\\", path.stem)


if __name__ == "__main__":
    import unittest

    unittest.main()
