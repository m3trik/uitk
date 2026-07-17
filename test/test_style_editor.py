# !/usr/bin/python
# coding=utf-8
"""Tests for StyleEditor preset management and StyleSheet export/import."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from qtpy import QtWidgets, QtCore
from conftest import QtBaseTestCase, setup_qt_application
from uitk.themes.style_sheet import StyleSheet
from uitk.widgets.colorSwatch import ColorSwatch
from uitk.widgets.editors.style_editor import StyleEditor, BASIC_TOKENS, LENGTH_TOKENS
from uitk.widgets.editors.editor_panel import EditorPanel

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
        # Redirect storage to a unique temp dir through the real preset_dir
        # setter (which routes the underlying PresetManager), so save/load go
        # to the temp tree instead of the shared consolidated root.
        temp_root = Path(__file__).parent / "temp_tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        self._test_preset_dir = Path(
            tempfile.mkdtemp(prefix="style_presets_", dir=temp_root)
        )
        self.editor.preset_dir = self._test_preset_dir

    def tearDown(self):
        StyleSheet.reset_overrides()
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


class TestStyleEditorTheming(QtBaseTestCase):
    """Tests for the editor's self-styling + tier/length-token behaviors."""

    def setUp(self):
        super().setUp()
        StyleSheet.reset_overrides()
        self.editor = self.track_widget(StyleEditor())

    def tearDown(self):
        StyleSheet.reset_overrides()
        super().tearDown()

    # Self-styling ----------------------------------------------------

    def test_editor_registers_with_theme_system(self):
        """``__init__`` registers the editor in ``StyleSheet._widget_configs``."""
        self.assertIn(self.editor, StyleSheet._widget_configs)

    def test_initial_registered_theme_matches_combo(self):
        """Editor's registered theme matches the combobox's initial value."""
        self.assertEqual(
            StyleSheet._widget_configs[self.editor]["theme"],
            self.editor.cmb_theme.currentText(),
        )

    def test_theme_combo_change_rethemes_editor(self):
        """Changing the theme combo updates the editor's registered theme."""
        self.editor.cmb_theme.setCurrentText("dark")
        self.assertEqual(
            StyleSheet._widget_configs[self.editor]["theme"], "dark"
        )

    def test_theme_combo_change_rebuilds_table_with_new_swatches(self):
        """After switching themes, table cells are rebuilt for the new theme."""
        # Capture the light-theme swatch identity for WIDGET_BACKGROUND
        self.editor.cmb_tier.setCurrentText("All")
        light_swatch = self._cell_for("WIDGET_BACKGROUND").findChild(ColorSwatch)

        # Switching theme triggers ``populate()`` which clears rows and
        # builds new cell widgets. The swatch should be a different
        # instance (the table was rebuilt) and the underlying override
        # store should now resolve against the dark theme.
        self.editor.cmb_theme.setCurrentText("dark")
        dark_swatch = self._cell_for("WIDGET_BACKGROUND").findChild(ColorSwatch)
        self.assertIsNot(light_swatch, dark_swatch)
        # WIDGET_BACKGROUND is intentionally different per theme
        self.assertNotEqual(
            StyleSheet.get_variable("WIDGET_BACKGROUND", theme="light"),
            StyleSheet.get_variable("WIDGET_BACKGROUND", theme="dark"),
        )

    # Tier filter -----------------------------------------------------

    def test_basic_tier_filters_to_basic_tokens_only(self):
        """Basic tier shows exactly the tokens in ``BASIC_TOKENS``."""
        self.editor.cmb_tier.setCurrentText("Basic")
        self.assertEqual(self._visible_token_names(), BASIC_TOKENS)

    def test_all_tier_shows_every_token(self):
        """All tier shows every token defined in the current theme."""
        self.editor.cmb_tier.setCurrentText("All")
        self.assertEqual(
            self._visible_token_names(),
            set(StyleSheet.themes["light"].keys()),
        )

    def test_basic_tokens_all_exist_in_themes(self):
        """Every name in ``BASIC_TOKENS`` is a real token (no typos / drift)."""
        for theme_name, theme in StyleSheet.themes.items():
            unknown = BASIC_TOKENS - set(theme.keys())
            self.assertFalse(
                unknown,
                f"BASIC_TOKENS contains names not in theme '{theme_name}': {sorted(unknown)}",
            )

    def test_length_tokens_all_exist_in_themes(self):
        """Every name in ``LENGTH_TOKENS`` is a real token."""
        for theme_name, theme in StyleSheet.themes.items():
            unknown = set(LENGTH_TOKENS) - set(theme.keys())
            self.assertFalse(
                unknown,
                f"LENGTH_TOKENS contains names not in theme '{theme_name}': {sorted(unknown)}",
            )

    # Cell-widget kind --------------------------------------------------

    def test_length_token_renders_as_spinbox_with_px_suffix(self):
        """RADIUS row contains a ``QSpinBox`` with a ``px`` suffix."""
        self.editor.cmb_tier.setCurrentText("All")
        cell = self._cell_for("RADIUS")
        self.assertIsNotNone(cell)
        spin = cell.findChild(QtWidgets.QSpinBox)
        self.assertIsNotNone(spin)
        self.assertIn("px", spin.suffix())
        # Light theme default RADIUS is 4px; value mirrors the active theme.
        expected = int(StyleSheet.get_variable("RADIUS", theme="light").rstrip("px"))
        self.assertEqual(spin.value(), expected)

    def test_length_spinbox_caps_at_8(self):
        """RADIUS caps at 8 (Qt border-radius degrades above this on small widgets)."""
        self.editor.cmb_tier.setCurrentText("All")
        spin = self._cell_for("RADIUS").findChild(QtWidgets.QSpinBox)
        self.assertEqual(spin.maximum(), 8)
        self.assertEqual(spin.minimum(), 0)

    def test_combobox_item_height_renders_as_spinbox(self):
        """COMBOBOX_ITEM_HEIGHT is a length token: spinbox, not a swatch, with
        a ceiling tall enough for its 19px default."""
        self.editor.cmb_tier.setCurrentText("All")
        cell = self._cell_for("COMBOBOX_ITEM_HEIGHT")
        self.assertIsNotNone(cell)
        self.assertIsNone(cell.findChild(ColorSwatch))
        spin = cell.findChild(QtWidgets.QSpinBox)
        self.assertIsNotNone(spin)
        expected = int(
            StyleSheet.get_variable("COMBOBOX_ITEM_HEIGHT", theme="light").rstrip("px")
        )
        self.assertEqual(spin.value(), expected)
        self.assertGreaterEqual(spin.maximum(), expected)

    def test_color_token_renders_as_swatch(self):
        """BUTTON_HOVER row contains a ``ColorSwatch``."""
        self.editor.cmb_tier.setCurrentText("All")
        cell = self._cell_for("BUTTON_HOVER")
        self.assertIsNotNone(cell)
        self.assertIsNotNone(cell.findChild(ColorSwatch))

    def test_section_divider_spans_all_columns(self):
        """The divider between colors and lengths spans all 3 columns."""
        self.editor.cmb_tier.setCurrentText("All")
        for i in range(self.editor.table.rowCount()):
            if self.editor.table.columnSpan(i, 0) == 3:
                item = self.editor.table.item(i, 0)
                self.assertIsNotNone(item)
                self.assertIn("Size", item.text())
                return
        self.fail("no spanning section divider found")

    # Value-change handlers --------------------------------------------

    def test_length_change_writes_px_suffix_to_overrides(self):
        """Spinbox value change writes ``f'{N}px'`` to the override store."""
        self.editor.cmb_tier.setCurrentText("All")
        spin = self._cell_for("RADIUS").findChild(QtWidgets.QSpinBox)
        spin.setValue(7)
        self.assertEqual(StyleSheet.get_variable("RADIUS", theme="light"), "7px")

    def test_color_change_writes_hex_to_overrides(self):
        """Swatch color change writes the hex to the override store."""
        from qtpy import QtGui

        self.editor.cmb_tier.setCurrentText("All")
        swatch = self._cell_for("BUTTON_HOVER").findChild(ColorSwatch)
        swatch.color = QtGui.QColor("#abcdef")
        self.assertEqual(
            StyleSheet.get_variable("BUTTON_HOVER", theme="light"), "#abcdef"
        )

    # Helpers -----------------------------------------------------------

    def _visible_token_names(self):
        """Set of token names currently in the table, excluding divider rows."""
        out = set()
        for i in range(self.editor.table.rowCount()):
            item = self.editor.table.item(i, 0)
            if item is None or self.editor.table.columnSpan(i, 0) > 1:
                continue
            out.add(item.text())
        return out

    def _cell_for(self, name):
        """Cell widget in column 1 for the row whose column-0 text is ``name``."""
        for i in range(self.editor.table.rowCount()):
            item = self.editor.table.item(i, 0)
            if item and item.text() == name:
                return self.editor.table.cellWidget(i, 1)
        return None


if __name__ == "__main__":
    unittest.main()
