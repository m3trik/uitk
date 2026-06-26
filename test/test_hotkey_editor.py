# !/usr/bin/python
# coding=utf-8
"""Tests for HotkeyEditor preset management."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from qtpy import QtWidgets, QtCore
from conftest import QtBaseTestCase, setup_qt_application
from uitk.switchboard import Switchboard
from uitk.widgets.editors.hotkey_editor import HotkeyEditor
from uitk.widgets.editors.editor_panel import EditorPanel
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
        # Redirect storage to a unique temp dir through the real preset_dir
        # setter (which routes the underlying PresetManager), so save/load go
        # to the temp tree instead of the shared consolidated root.
        temp_root = Path(__file__).parent / "temp_tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        self._test_preset_dir = Path(
            tempfile.mkdtemp(prefix="hotkey_presets_", dir=temp_root)
        )
        self.editor.preset_dir = self._test_preset_dir

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
        has_entries = any("example" in key.lower() for key in data.keys())
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

    # ------------------------------------------------------------------
    # Preset format: scope round-trip + back-compat
    # ------------------------------------------------------------------

    def test_export_includes_scope(self):
        """Exported bindings should be {seq, scope} dicts."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")

        slot_name = registry[0]["method"]
        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+E", "application")

        data = self.editor.export_shortcuts()
        ui_name = next((n for n in data if "example" in n.lower()), None)
        self.assertIsNotNone(ui_name)

        binding = data[ui_name][slot_name]
        self.assertIsInstance(binding, dict)
        self.assertEqual(binding["seq"], "Ctrl+Alt+E")
        self.assertEqual(binding["scope"], "application")

    def test_import_legacy_string_format(self):
        """Legacy presets where values are bare strings should still import."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")

        slot_name = registry[0]["method"]
        ui_name = next(
            (n for n in self.editor.export_shortcuts() if "example" in n.lower()),
            None,
        )
        self.assertIsNotNone(ui_name)

        # Old-shape preset: value is the sequence string directly
        legacy = {ui_name: {slot_name: "Ctrl+Alt+L"}}
        self.editor.import_shortcuts(legacy)

        new_registry = self.sb.get_shortcut_registry(self.ui)
        entry = next((r for r in new_registry if r["method"] == slot_name), None)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["current"], "Ctrl+Alt+L")

    def test_import_new_format_round_trip(self):
        """Exported preset should re-import and restore both seq and scope."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")

        slot_name = registry[0]["method"]
        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+R", "application")
        snapshot = self.editor.export_shortcuts()

        # Knock the binding back to something else
        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+Z", "window")

        self.editor.import_shortcuts(snapshot)

        new_registry = self.sb.get_shortcut_registry(self.ui)
        entry = next((r for r in new_registry if r["method"] == slot_name), None)
        self.assertEqual(entry["current"], "Ctrl+Alt+R")
        self.assertEqual(entry["current_scope"], "application")

    # ------------------------------------------------------------------
    # Collision checker hook
    # ------------------------------------------------------------------

    def test_collision_checker_receives_assignment_args(self):
        """Custom checkers should be called with (sequence, scope, ui_name, method)."""
        captured = {}

        def fake_checker(sequence, scope, ui_name, method_name):
            captured["sequence"] = sequence
            captured["scope"] = scope
            captured["ui_name"] = ui_name
            captured["method_name"] = method_name
            return []

        self.editor.add_collision_checker(fake_checker)

        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")
        slot_name = registry[0]["method"]
        ui_name = next(
            (n for n in self.editor.export_shortcuts() if "example" in n.lower()),
            None,
        )

        proceed = self.editor._resolve_collisions(
            self.ui, slot_name, "Ctrl+Alt+K", "application"
        )
        self.assertTrue(proceed)
        self.assertEqual(captured["sequence"], "Ctrl+Alt+K")
        self.assertEqual(captured["scope"], "application")
        self.assertEqual(captured["method_name"], slot_name)
        # ui_name comes from the combobox; just assert it was passed as a string
        self.assertIsInstance(captured["ui_name"], str)

    def test_builtin_checker_flags_application_duplicate(self):
        """Two Application bindings on the same key should be a breaks_binding conflict."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if len(registry) < 2:
            self.skipTest("Need at least two slots to test internal collision")

        first = registry[0]["method"]
        second = registry[1]["method"]

        # Bind the first slot to Ctrl+Alt+D / application
        self.sb.set_user_shortcut(self.ui, first, "Ctrl+Alt+D", "application")

        # Now ask the checker about assigning the same key to the second slot
        conflicts = self.editor._builtin_internal_collision_checker(
            "Ctrl+Alt+D",
            "application",
            self.editor.cmb_ui.currentText() or "",
            second,
        )

        self.assertTrue(any(c.breaks_binding for c in conflicts))
        breaking = next(c for c in conflicts if c.breaks_binding)
        self.assertIsNotNone(breaking.clear_action)

    # ------------------------------------------------------------------
    # UI listing & on-demand load
    # ------------------------------------------------------------------

    def test_combobox_lists_all_registered_uis(self):
        """The Target UI combobox should list every registered UI, loaded or not."""
        filenames = self.sb.registry.ui_registry.get("filename") or []
        expected = {
            self.sb.convert_to_legal_name(name.rsplit(".", 1)[0]) for name in filenames
        }
        self.assertTrue(expected, "Test fixture should register at least one UI")

        listed = {
            self.editor.cmb_ui.itemText(i) for i in range(self.editor.cmb_ui.count())
        }
        self.assertEqual(listed, expected)

    def test_populate_loads_unloaded_ui_on_selection(self):
        """Selecting an unloaded UI in the combobox should instantiate it on demand."""
        # The fixture's setUp loaded the example UI. Evict it from the
        # loaded_ui cache so we can prove that selecting it triggers a
        # fresh load, rather than just reading the cached value.
        target_name = self.editor.cmb_ui.itemText(0)
        self.assertTrue(target_name)

        del self.sb.loaded_ui[target_name]
        self.assertIsNone(
            self.sb.loaded_ui.peek(target_name),
            "Eviction should leave loaded_ui.peek returning None",
        )

        # Force a re-selection to fire currentTextChanged → populate().
        self.editor.cmb_ui.setCurrentIndex(-1)
        self.editor.cmb_ui.setCurrentIndex(0)
        QtWidgets.QApplication.processEvents()

        self.assertIsNotNone(
            self.sb.loaded_ui.peek(target_name),
            "Selecting an unloaded UI should instantiate it",
        )
        first_cell = self.editor.table.item(0, 0)
        if first_cell is not None:
            self.assertNotIn("Could not load", first_cell.text())


if __name__ == "__main__":
    unittest.main()
