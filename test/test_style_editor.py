# !/usr/bin/python
# coding=utf-8
"""Tests for StyleEditor preset management and StyleSheet export/import."""
import json
import shutil
import unittest
from pathlib import Path

from qtpy import QtWidgets, QtCore
from conftest import QtBaseTestCase, setup_qt_application
from uitk.widgets.mixins.style_sheet import StyleSheet
from uitk.widgets.style_editor import StyleEditor

app = setup_qt_application()


class TestStyleSheetExportImport(QtBaseTestCase):
    """Tests for StyleSheet.export_overrides / import_overrides."""

    def setUp(self):
        super().setUp()
        StyleSheet.reset_overrides()

    def tearDown(self):
        StyleSheet.reset_overrides()
        super().tearDown()

    def test_export_returns_deep_copy(self):
        """Exported dict should be a deep copy, not a reference."""
        StyleSheet.set_variable("BUTTON_HOVER", "#aabbcc", theme="light")
        exported = StyleSheet.export_overrides()

        # Mutate the copy — original should be unaffected
        exported["light"]["BUTTON_HOVER"] = "#000000"
        self.assertEqual(
            StyleSheet.get_variable("BUTTON_HOVER", theme="light"), "#aabbcc"
        )

    def test_export_contains_both_themes(self):
        """Exported dict should have keys for both light and dark."""
        StyleSheet.set_variable("TEXT_COLOR", "#111111", theme="light")
        StyleSheet.set_variable("TEXT_COLOR", "#222222", theme="dark")
        exported = StyleSheet.export_overrides()

        self.assertEqual(exported["light"]["TEXT_COLOR"], "#111111")
        self.assertEqual(exported["dark"]["TEXT_COLOR"], "#222222")

    def test_import_replaces_overrides(self):
        """import_overrides should fully replace existing overrides."""
        StyleSheet.set_variable("BUTTON_HOVER", "#aabbcc", theme="light")

        new_data = {"light": {"TEXT_COLOR": "#ff0000"}, "dark": {}}
        StyleSheet.import_overrides(new_data)

        # Old override should be gone
        self.assertNotEqual(
            StyleSheet.get_variable("BUTTON_HOVER", theme="light"), "#aabbcc"
        )
        # New override should be present
        self.assertEqual(
            StyleSheet.get_variable("TEXT_COLOR", theme="light"), "#ff0000"
        )

    def test_import_empty_clears_all(self):
        """Importing empty dict should clear all overrides."""
        StyleSheet.set_variable("BUTTON_HOVER", "#aabbcc", theme="light")
        StyleSheet.import_overrides({})

        # Should fall back to base theme value
        base_val = StyleSheet.themes["light"]["BUTTON_HOVER"]
        self.assertEqual(
            StyleSheet.get_variable("BUTTON_HOVER", theme="light"), base_val
        )

    def test_roundtrip_export_import(self):
        """export → import should reproduce the same override state."""
        StyleSheet.set_variable("PANEL_BACKGROUND", "#aaa", theme="light")
        StyleSheet.set_variable("PANEL_BACKGROUND", "#bbb", theme="dark")
        StyleSheet.set_variable("ICON_COLOR", "#ccc", theme="dark")

        snapshot = StyleSheet.export_overrides()
        StyleSheet.reset_overrides()

        # Verify overrides are cleared
        self.assertNotEqual(
            StyleSheet.get_variable("PANEL_BACKGROUND", theme="light"), "#aaa"
        )

        StyleSheet.import_overrides(snapshot)

        self.assertEqual(
            StyleSheet.get_variable("PANEL_BACKGROUND", theme="light"), "#aaa"
        )
        self.assertEqual(
            StyleSheet.get_variable("PANEL_BACKGROUND", theme="dark"), "#bbb"
        )
        self.assertEqual(StyleSheet.get_variable("ICON_COLOR", theme="dark"), "#ccc")


class TestStyleEditorPresets(QtBaseTestCase):
    """Tests for StyleEditor preset save/load/delete/rename."""

    _test_preset_dir: Path = None

    def setUp(self):
        super().setUp()
        StyleSheet.reset_overrides()
        self.editor = self.track_widget(StyleEditor())
        # Override preset_dir to a temporary location
        self._test_preset_dir = Path(__file__).parent / "temp_tests" / "style_presets"
        self._test_preset_dir.mkdir(parents=True, exist_ok=True)
        # Patch the property for testing
        StyleEditor.preset_dir = property(lambda self_: self._test_preset_dir)

    def tearDown(self):
        StyleSheet.reset_overrides()
        # Restore original property
        StyleEditor.preset_dir = StyleEditor.__dict__.get(
            "_original_preset_dir", StyleEditor.preset_dir
        )
        if self._test_preset_dir and self._test_preset_dir.exists():
            shutil.rmtree(self._test_preset_dir, ignore_errors=True)
        super().tearDown()

    def test_save_creates_json_file(self):
        """save_preset should write a JSON file in preset_dir."""
        StyleSheet.set_variable("BUTTON_HOVER", "#123456", theme="light")
        path = self.editor.save_preset("test_preset")
        self.assertTrue(path.exists())
        with open(path, "r") as f:
            data = json.load(f)
        self.assertIn("_meta", data)
        self.assertEqual(data["light"]["BUTTON_HOVER"], "#123456")

    def test_save_captures_both_themes(self):
        """Preset should contain overrides for all themes."""
        StyleSheet.set_variable("TEXT_COLOR", "#aaa", theme="light")
        StyleSheet.set_variable("TEXT_COLOR", "#bbb", theme="dark")
        path = self.editor.save_preset("both_themes")

        with open(path, "r") as f:
            data = json.load(f)
        data.pop("_meta", None)

        self.assertEqual(data["light"]["TEXT_COLOR"], "#aaa")
        self.assertEqual(data["dark"]["TEXT_COLOR"], "#bbb")

    def test_load_restores_overrides(self):
        """load_preset should bulk-apply overrides via import_overrides."""
        StyleSheet.set_variable("PANEL_BACKGROUND", "#abc", theme="light")
        self.editor.save_preset("restore_test")

        StyleSheet.reset_overrides()
        self.assertNotEqual(
            StyleSheet.get_variable("PANEL_BACKGROUND", theme="light"), "#abc"
        )

        result = self.editor.load_preset("restore_test")
        self.assertTrue(result)
        self.assertEqual(
            StyleSheet.get_variable("PANEL_BACKGROUND", theme="light"), "#abc"
        )

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

    def test_batch_load_single_reload(self):
        """Loading a preset should call import_overrides (one bulk update),
        not set_variable per-var.

        Bug prevention: Ensures batch-apply semantics to avoid N reloads.
        """
        StyleSheet.set_variable("BUTTON_HOVER", "#111", theme="light")
        StyleSheet.set_variable("TEXT_COLOR", "#222", theme="dark")
        self.editor.save_preset("batch_test")
        StyleSheet.reset_overrides()

        # Monkey-patch import_overrides to count calls
        import_calls = []
        original_import = StyleSheet.import_overrides

        @classmethod
        def counting_import(cls, data):
            import_calls.append(1)
            return original_import.__func__(cls, data)

        StyleSheet.import_overrides = counting_import
        try:
            self.editor.load_preset("batch_test")
            self.assertEqual(
                len(import_calls), 1, "import_overrides should be called exactly once"
            )
        finally:
            StyleSheet.import_overrides = original_import


if __name__ == "__main__":
    unittest.main()
