# !/usr/bin/python
# coding=utf-8
"""Tests for HotkeyEditor preset management."""
import json
import shutil
import unittest
from pathlib import Path

from qtpy import QtWidgets, QtCore
from conftest import QtBaseTestCase, setup_qt_application
from uitk.switchboard import Switchboard
from uitk.widgets.hotkey_editor import HotkeyEditor
from uitk.examples.example import ExampleSlots

app = setup_qt_application()


class TestHotkeyEditorPresets(QtBaseTestCase):
    """Tests for HotkeyEditor preset save/load/delete/rename."""

    _test_preset_dir: Path = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example
        self.ui.show()
        QtWidgets.QApplication.processEvents()
        self.editor = HotkeyEditor(self.sb, parent=None)
        # Override preset_dir to a temp location
        self._test_preset_dir = Path(__file__).parent / "temp_tests" / "hotkey_presets"
        self._test_preset_dir.mkdir(parents=True, exist_ok=True)
        # Patch preset_dir property for testing
        HotkeyEditor.preset_dir = property(lambda self_: self._test_preset_dir)

    def tearDown(self):
        if hasattr(self, "editor") and self.editor:
            self.editor.close()
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        if self._test_preset_dir and self._test_preset_dir.exists():
            shutil.rmtree(self._test_preset_dir, ignore_errors=True)
        super().tearDown()

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def test_export_returns_dict(self):
        """export_shortcuts should return a dict keyed by UI name."""
        data = self.editor.export_shortcuts()
        self.assertIsInstance(data, dict)

    def test_export_captures_loaded_uis(self):
        """export_shortcuts should include entries for loaded UIs with slots."""
        data = self.editor.export_shortcuts()
        # The example UI has connected slots, so it should appear
        has_entries = any(
            "example" in key.lower() for key in data.keys()
        )
        registry = self.sb.get_shortcut_registry(self.ui)
        if registry:
            self.assertTrue(has_entries, "Expected example UI in export data")

    def test_import_applies_shortcuts(self):
        """import_shortcuts should call set_user_shortcut for each entry."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")

        slot_name = registry[0]["method"]
        ui_name = None

        # Find the UI name used in export
        data = self.editor.export_shortcuts()
        for name in data:
            if "example" in name.lower():
                ui_name = name
                break

        if not ui_name:
            self.skipTest("Example UI not found in export")

        # Build a preset dict with a custom shortcut
        preset_data = {ui_name: {slot_name: "Ctrl+Alt+P"}}
        applied = self.editor.import_shortcuts(preset_data)
        self.assertGreaterEqual(applied, 1)

        # Verify the shortcut was applied
        new_registry = self.sb.get_shortcut_registry(self.ui)
        entry = next((r for r in new_registry if r["method"] == slot_name), None)
        if entry:
            self.assertEqual(entry["current"], "Ctrl+Alt+P")

    # ------------------------------------------------------------------
    # Save / Load / Delete / Rename
    # ------------------------------------------------------------------

    def test_save_creates_json_file(self):
        """save_preset should write a JSON file in preset_dir."""
        path = self.editor.save_preset("test_hotkeys")
        self.assertTrue(path.exists())
        with open(path, "r") as f:
            data = json.load(f)
        self.assertIn("_meta", data)

    def test_load_restores_shortcuts(self):
        """load_preset should apply saved shortcuts."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")

        slot_name = registry[0]["method"]

        # Set a custom shortcut and save
        data = self.editor.export_shortcuts()
        ui_name = None
        for name in data:
            if "example" in name.lower():
                ui_name = name
                break
        if not ui_name:
            self.skipTest("Example UI not found in export")

        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+L")
        self.editor.save_preset("load_test")

        # Change the shortcut to something else
        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+M")

        # Load should restore the saved value
        result = self.editor.load_preset("load_test")
        self.assertTrue(result)

        new_registry = self.sb.get_shortcut_registry(self.ui)
        entry = next((r for r in new_registry if r["method"] == slot_name), None)
        if entry:
            self.assertEqual(entry["current"], "Ctrl+Alt+L")

    def test_load_nonexistent_returns_false(self):
        """load_preset should return False for a missing file."""
        self.assertFalse(self.editor.load_preset("does_not_exist"))

    def test_delete_removes_file(self):
        """delete_preset should remove the JSON file."""
        self.editor.save_preset("to_delete")
        self.assertIn("to_delete", self.editor._list_presets())
        self.assertTrue(self.editor.delete_preset("to_delete"))
        self.assertNotIn("to_delete", self.editor._list_presets())

    def test_rename_updates_filename(self):
        """rename_preset should rename the file on disk."""
        self.editor.save_preset("old_name")
        self.assertTrue(self.editor.rename_preset("old_name", "new_name"))
        self.assertNotIn("old_name", self.editor._list_presets())
        self.assertIn("new_name", self.editor._list_presets())

    def test_rename_fails_if_target_exists(self):
        """rename_preset should fail when target name already exists."""
        self.editor.save_preset("name_a")
        self.editor.save_preset("name_b")
        self.assertFalse(self.editor.rename_preset("name_a", "name_b"))

    def test_list_returns_sorted_names(self):
        """_list_presets should return alphabetically sorted stems."""
        self.editor.save_preset("zebra")
        self.editor.save_preset("alpha")
        names = self.editor._list_presets()
        self.assertEqual(names, ["alpha", "zebra"])


if __name__ == "__main__":
    unittest.main()
