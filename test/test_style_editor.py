# !/usr/bin/python
# coding=utf-8
"""Tests for StyleEditor theme-preset management and StyleSheet export/import."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from qtpy import QtWidgets
from conftest import QtBaseTestCase, setup_qt_application
from uitk.themes.style_sheet import StyleSheet
from uitk.widgets.colorSwatch import ColorSwatch
from uitk.widgets.editors.style_editor import (
    BASIC_TOKENS,
    BUILTIN_THEMES_DIR,
    LENGTH_TOKENS,
    StyleEditor,
)

app = setup_qt_application()

TEMP_ROOT = Path(__file__).parent / "temp_tests"


class _PresetRootSandboxCase(QtBaseTestCase):
    """Per-test preset root so ``.active`` / preset files never leak between
    tests (the conftest-level sandbox is process-wide, but the style editor
    persists an active-theme pointer at construction — sharing one root would
    make test outcomes order-dependent)."""

    def setUp(self):
        super().setUp()
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self._preset_root = Path(
            tempfile.mkdtemp(prefix="style_presets_", dir=TEMP_ROOT)
        )
        self._prev_root = os.environ.get("UITK_PRESETS_ROOT")
        os.environ["UITK_PRESETS_ROOT"] = str(self._preset_root)
        StyleSheet.reset_overrides()

    def tearDown(self):
        StyleSheet.reset_overrides()
        if self._prev_root is None:
            os.environ.pop("UITK_PRESETS_ROOT", None)
        else:
            os.environ["UITK_PRESETS_ROOT"] = self._prev_root
        shutil.rmtree(self._preset_root, ignore_errors=True)
        super().tearDown()


class TestStyleSheetExportImport(QtBaseTestCase):
    """Tests for StyleSheet.export_overrides / import_overrides / apply_theme."""

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

    # apply_theme -------------------------------------------------------

    def test_apply_theme_switches_registered_widgets(self):
        """apply_theme re-themes every widget registered with the system."""
        w = self.track_widget(QtWidgets.QWidget())
        StyleSheet().set(w, theme="light")
        StyleSheet.apply_theme("dark")
        self.assertEqual(StyleSheet._widget_configs[w]["theme"], "dark")

    def test_apply_theme_replaces_overrides(self):
        """The overrides arg REPLACES the theme's global override set."""
        StyleSheet.set_variable("TEXT_COLOR", "#111111", theme="dark")
        StyleSheet.apply_theme("dark", {"BUTTON_HOVER": "#abcdef"})

        self.assertEqual(
            StyleSheet.get_variable("BUTTON_HOVER", theme="dark"), "#abcdef"
        )
        # Pre-existing override was replaced away
        self.assertEqual(
            StyleSheet.get_variable("TEXT_COLOR", theme="dark"),
            StyleSheet.themes["dark"]["TEXT_COLOR"],
        )

    def test_apply_theme_empty_overrides_clears(self):
        """An empty overrides dict restores the pure base theme."""
        StyleSheet.set_variable("TEXT_COLOR", "#111111", theme="dark")
        StyleSheet.apply_theme("dark", {})
        self.assertEqual(
            StyleSheet.get_variable("TEXT_COLOR", theme="dark"),
            StyleSheet.themes["dark"]["TEXT_COLOR"],
        )

    def test_apply_theme_drops_unknown_and_derived_tokens(self):
        """Stale/derived keys in a preset never reach the override store."""
        StyleSheet.apply_theme(
            "dark",
            {
                "NOT_A_REAL_TOKEN": "#123",
                "BUTTON_HOVER_TINT": "#456",  # derived — auto-computed
                "BUTTON_HOVER": "#789",
            },
        )
        overrides = StyleSheet.export_overrides()["dark"]
        self.assertEqual(overrides, {"BUTTON_HOVER": "#789"})

    def test_apply_theme_unknown_theme_raises(self):
        with self.assertRaises(ValueError):
            StyleSheet.apply_theme("no_such_theme")

    # Theme definitions -------------------------------------------------

    def test_all_themes_share_the_same_token_set(self):
        """Every theme (incl. high-contrast) defines the identical tokens."""
        reference = set(StyleSheet.themes["light"])
        for name, theme in StyleSheet.themes.items():
            self.assertEqual(
                set(theme),
                reference,
                f"theme '{name}' token set drifted from 'light'",
            )

    def test_high_contrast_theme_exists(self):
        """The accessibility default ships as a base theme."""
        self.assertIn("high-contrast", StyleSheet.themes)


class TestStyleEditorPresets(_PresetRootSandboxCase):
    """Tests for StyleEditor preset save/load/delete/rename (semantic mode)."""

    BUILTINS = ("dark", "high-contrast", "light")

    def setUp(self):
        super().setUp()
        self.editor = self.track_widget(StyleEditor())

    def test_builtin_themes_are_listed(self):
        """The base themes appear in the preset list as built-ins."""
        names = self.editor._list_presets()
        for builtin in self.BUILTINS:
            self.assertIn(builtin, names)

    def test_builtin_theme_presets_match_engine_themes(self):
        """Shipped preset files stay in lockstep with StyleSheet.themes."""
        stems = sorted(p.stem for p in BUILTIN_THEMES_DIR.glob("*.json"))
        self.assertEqual(stems, sorted(StyleSheet.themes))
        for path in BUILTIN_THEMES_DIR.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data.get("theme"), path.stem)
            self.assertEqual(data.get("overrides"), {})

    def test_save_creates_json_file(self):
        """save_preset should write a JSON file in the new theme format."""
        StyleSheet.set_variable("BUTTON_HOVER", "#123456", theme=self.editor.theme)
        path = self.editor.save_preset("test_preset")
        self.assertTrue(path.exists())
        with open(path, "r") as f:
            data = json.load(f)
        self.assertIn("_meta", data)
        self.assertEqual(data["theme"], self.editor.theme)
        self.assertEqual(data["overrides"]["BUTTON_HOVER"], "#123456")

    def test_save_captures_current_theme_only(self):
        """A preset is one base theme + its overrides — not other themes'."""
        other = "light" if self.editor.theme != "light" else "dark"
        StyleSheet.set_variable("TEXT_COLOR", "#aaa", theme=self.editor.theme)
        StyleSheet.set_variable("TEXT_COLOR", "#bbb", theme=other)
        path = self.editor.save_preset("one_theme")

        with open(path, "r") as f:
            data = json.load(f)

        self.assertEqual(data["overrides"]["TEXT_COLOR"], "#aaa")
        self.assertNotIn(other, data)

    def test_load_restores_theme_and_overrides(self):
        """load_preset should re-apply the stored base theme + overrides."""
        theme = self.editor.theme
        StyleSheet.set_variable("PANEL_BACKGROUND", "#abc", theme=theme)
        self.editor.save_preset("restore_test")

        StyleSheet.reset_overrides()
        self.assertNotEqual(
            StyleSheet.get_variable("PANEL_BACKGROUND", theme=theme), "#abc"
        )

        result = self.editor.load_preset("restore_test")
        self.assertTrue(result)
        self.assertEqual(self.editor.theme, theme)
        self.assertEqual(
            StyleSheet.get_variable("PANEL_BACKGROUND", theme=theme), "#abc"
        )

    def test_load_builtin_switches_theme(self):
        """Loading a built-in theme preset switches the editor's base theme
        globally and clears that theme's overrides."""
        StyleSheet.set_variable("TEXT_COLOR", "#123", theme="light")
        self.editor.load_preset("light")
        self.assertEqual(self.editor.theme, "light")
        # Built-in = pure base theme: its overrides were replaced with {}
        self.assertEqual(
            StyleSheet.get_variable("TEXT_COLOR", theme="light"),
            StyleSheet.themes["light"]["TEXT_COLOR"],
        )
        # The editor itself re-themed
        self.assertEqual(StyleSheet._widget_configs[self.editor]["theme"], "light")

    def test_load_legacy_format_still_applies(self):
        """Old presets ({theme: {var: value}} dumps) import via overrides."""
        legacy = {
            "_meta": {"version": 1},
            "light": {"TEXT_COLOR": "#fedcba"},
            "dark": {},
        }
        path = self.editor.preset_dir / "legacy.json"
        path.write_text(json.dumps(legacy), encoding="utf-8")

        theme_before = self.editor.theme
        self.assertTrue(self.editor.load_preset("legacy"))
        self.assertEqual(
            StyleSheet.get_variable("TEXT_COLOR", theme="light"), "#fedcba"
        )
        # Legacy payloads carry no base theme — the current one is kept.
        self.assertEqual(self.editor.theme, theme_before)

    def test_load_nonexistent_returns_false(self):
        """load_preset should return False for a missing file."""
        self.assertFalse(self.editor.load_preset("does_not_exist"))

    def test_delete_removes_file(self):
        """delete_preset should remove the JSON file."""
        self.editor.save_preset("to_delete")
        self.assertIn("to_delete", self.editor._list_presets())

        self.assertTrue(self.editor.delete_preset("to_delete"))
        self.assertNotIn("to_delete", self.editor._list_presets())

    def test_delete_builtin_refused(self):
        """Built-in theme presets are read-only."""
        self.assertFalse(self.editor.delete_preset("light"))
        self.assertIn("light", self.editor._list_presets())

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
        """_list_presets returns sorted names (user saves + built-ins)."""
        self.editor.save_preset("zebra")
        self.editor.save_preset("alpha")
        names = self.editor._list_presets()
        self.assertEqual(names, sorted(names))
        for expected in ("alpha", "zebra") + self.BUILTINS:
            self.assertIn(expected, names)

    def test_batch_load_single_reload(self):
        """Loading a preset applies in ONE bulk reload pass, not per-var."""
        theme = self.editor.theme
        StyleSheet.set_variable("BUTTON_HOVER", "#111", theme=theme)
        StyleSheet.set_variable("TEXT_COLOR", "#222", theme=theme)
        self.editor.save_preset("batch_test")
        StyleSheet.reset_overrides()

        reload_calls = []
        original_reload = StyleSheet.reload

        @classmethod
        def counting_reload(cls, widget=None):
            reload_calls.append(widget)
            return original_reload.__func__(cls, widget)

        StyleSheet.reload = counting_reload
        try:
            self.editor.load_preset("batch_test")
            self.assertEqual(
                len(reload_calls), 1, "load should trigger exactly one reload pass"
            )
        finally:
            StyleSheet.reload = original_reload

    def test_edits_flag_active_preset_modified(self):
        """A table edit dirties the active preset; saving cleans it."""
        mgr = self.editor._preset_mgr
        self.editor.load_preset("dark")
        self.assertFalse(mgr.refresh_modified_state())

        StyleSheet.set_variable("BUTTON_HOVER", "#445566", theme="dark")
        self.assertTrue(mgr.refresh_modified_state())

        self.editor.save_preset("dark")  # user save shadows the built-in
        self.assertFalse(mgr.refresh_modified_state())


class TestStyleEditorTheming(_PresetRootSandboxCase):
    """Tests for the editor's self-styling + tier/length-token behaviors."""

    def setUp(self):
        super().setUp()
        self.editor = self.track_widget(StyleEditor())

    # Self-styling ----------------------------------------------------

    def test_editor_registers_with_theme_system(self):
        """``__init__`` registers the editor in ``StyleSheet._widget_configs``."""
        self.assertIn(self.editor, StyleSheet._widget_configs)

    def test_initial_registered_theme_matches_editor_theme(self):
        """Editor's registered theme matches its current-theme property."""
        self.assertEqual(
            StyleSheet._widget_configs[self.editor]["theme"],
            self.editor.theme,
        )

    def test_default_theme_is_dark(self):
        """With no persisted active preset, the editor edits 'dark'."""
        self.assertEqual(self.editor.theme, "dark")

    def test_default_activates_matching_builtin(self):
        """A virgin session activates the built-in matching the default theme
        so the combo reads 'Theme:  dark' instead of the placeholder."""
        self.assertEqual(self.editor._preset_mgr.active_preset, "dark")

    def test_no_separate_theme_combo(self):
        """The theme combobox is gone — the preset combo IS the selector."""
        self.assertFalse(hasattr(self.editor, "cmb_theme"))
        self.assertEqual(self.editor._cmb_preset.current_text_prefix, "Theme:  ")

    def test_theme_survives_editor_restart(self):
        """The active theme (via the active preset) persists to a new editor."""
        self.editor.load_preset("high-contrast")
        second = self.track_widget(StyleEditor())
        self.assertEqual(second.theme, "high-contrast")

    def test_loading_theme_preset_rebuilds_table_with_new_swatches(self):
        """After switching themes, table cells are rebuilt for the new theme."""
        self.editor.set_tier("All")
        dark_swatch = self._cell_for("WIDGET_BACKGROUND").findChild(ColorSwatch)

        self.editor.load_preset("light")
        light_swatch = self._cell_for("WIDGET_BACKGROUND").findChild(ColorSwatch)
        self.assertIsNot(dark_swatch, light_swatch)
        self.assertEqual(
            StyleSheet._widget_configs[self.editor]["theme"], "light"
        )
        # WIDGET_BACKGROUND is intentionally different per theme
        self.assertNotEqual(
            StyleSheet.get_variable("WIDGET_BACKGROUND", theme="light"),
            StyleSheet.get_variable("WIDGET_BACKGROUND", theme="dark"),
        )

    # Tier filter -----------------------------------------------------

    def test_tier_combo_lives_in_header_menu(self):
        """The Basic/All filter is a header ⋯-menu option, not a body row."""
        self.assertIn("menu", self.editor.header.buttons)
        self.assertIn(self.editor.cmb_tier, self.editor.header.menu.get_items())

    def test_basic_tier_filters_to_basic_tokens_only(self):
        """Basic tier shows exactly the tokens in ``BASIC_TOKENS``."""
        self.editor.set_tier("Basic")
        self.assertEqual(self._visible_token_names(), BASIC_TOKENS)

    def test_all_tier_shows_every_token(self):
        """All tier shows every token defined in the current theme."""
        self.editor.set_tier("All")
        self.assertEqual(
            self._visible_token_names(),
            set(StyleSheet.themes[self.editor.theme].keys()),
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
        self.editor.set_tier("All")
        cell = self._cell_for("RADIUS")
        self.assertIsNotNone(cell)
        spin = cell.findChild(QtWidgets.QSpinBox)
        self.assertIsNotNone(spin)
        self.assertIn("px", spin.suffix())
        # Value mirrors the editor's current (active) theme.
        expected = int(
            StyleSheet.get_variable("RADIUS", theme=self.editor.theme).rstrip("px")
        )
        self.assertEqual(spin.value(), expected)

    def test_length_spinbox_caps_at_8(self):
        """RADIUS caps at 8 (Qt border-radius degrades above this on small widgets)."""
        self.editor.set_tier("All")
        spin = self._cell_for("RADIUS").findChild(QtWidgets.QSpinBox)
        self.assertEqual(spin.maximum(), 8)
        self.assertEqual(spin.minimum(), 0)

    def test_combobox_item_height_renders_as_spinbox(self):
        """COMBOBOX_ITEM_HEIGHT is a length token: spinbox, not a swatch, with
        a ceiling tall enough for its default."""
        self.editor.set_tier("All")
        cell = self._cell_for("COMBOBOX_ITEM_HEIGHT")
        self.assertIsNotNone(cell)
        self.assertIsNone(cell.findChild(ColorSwatch))
        spin = cell.findChild(QtWidgets.QSpinBox)
        self.assertIsNotNone(spin)
        expected = int(
            StyleSheet.get_variable(
                "COMBOBOX_ITEM_HEIGHT", theme=self.editor.theme
            ).rstrip("px")
        )
        self.assertEqual(spin.value(), expected)
        self.assertGreaterEqual(spin.maximum(), expected)

    def test_color_token_renders_as_swatch(self):
        """BUTTON_HOVER row contains a ``ColorSwatch``."""
        self.editor.set_tier("All")
        cell = self._cell_for("BUTTON_HOVER")
        self.assertIsNotNone(cell)
        self.assertIsNotNone(cell.findChild(ColorSwatch))

    def test_section_divider_spans_all_columns(self):
        """The divider between colors and lengths spans all 3 columns."""
        self.editor.set_tier("All")
        for i in range(self.editor.table.rowCount()):
            if self.editor.table.columnSpan(i, 0) == 3:
                item = self.editor.table.item(i, 0)
                self.assertIsNotNone(item)
                self.assertIn("Size", item.text())
                return
        self.fail("no spanning section divider found")

    # Cell geometry ------------------------------------------------------

    def test_value_cells_not_clipped_by_row(self):
        """No swatch / spinbox extends past its table row (the cropped-swatch
        bug: QSS item padding shrank the cell-widget rect below the editors'
        fixed height, clipping their bottom edge)."""
        self.editor.set_tier("All")
        self.editor.show()
        QtWidgets.QApplication.processEvents()

        table = self.editor.table
        vp = table.viewport()
        checked = 0
        for row in range(table.rowCount()):
            cell = table.cellWidget(row, 1)
            if cell is None:
                continue
            child = cell.findChild(ColorSwatch) or cell.findChild(QtWidgets.QSpinBox)
            if child is None:
                continue
            name = table.item(row, 0).text()
            top = child.mapTo(vp, child.rect().topLeft()).y()
            bottom = child.mapTo(vp, child.rect().bottomLeft()).y()
            row_top = table.rowViewportPosition(row)
            row_bottom = row_top + table.rowHeight(row) - 1
            self.assertGreaterEqual(
                top, row_top, f"{name}: editor starts above its row"
            )
            self.assertLessEqual(
                bottom, row_bottom, f"{name}: editor clipped at row bottom"
            )
            checked += 1
        self.assertGreater(checked, 0)

    # Value-change handlers --------------------------------------------

    def test_length_change_writes_px_suffix_to_overrides(self):
        """Spinbox value change writes ``f'{N}px'`` to the override store."""
        self.editor.set_tier("All")
        spin = self._cell_for("RADIUS").findChild(QtWidgets.QSpinBox)
        spin.setValue(7)
        self.assertEqual(
            StyleSheet.get_variable("RADIUS", theme=self.editor.theme), "7px"
        )

    def test_color_change_writes_hex_to_overrides(self):
        """Swatch color change writes the hex to the override store."""
        from qtpy import QtGui

        self.editor.set_tier("All")
        swatch = self._cell_for("BUTTON_HOVER").findChild(ColorSwatch)
        swatch.color = QtGui.QColor("#abcdef")
        self.assertEqual(
            StyleSheet.get_variable("BUTTON_HOVER", theme=self.editor.theme),
            "#abcdef",
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
