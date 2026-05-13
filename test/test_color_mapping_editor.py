"""Unit tests for ColorMappingEditor and ColorMappingDialog.

Covers the preset round-trip and the default-shape persistence rule for
``apply_color_map``.

Run standalone: python test/test_color_mapping_editor.py
"""

import json
import tempfile
import unittest
from pathlib import Path

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore  # noqa: E402

from uitk.widgets.editors.color_mapping_editor import (  # noqa: E402
    ColorMappingDialog,
    ColorMappingEditor,
)
from uitk.widgets.mixins.settings_manager import SettingsManager  # noqa: E402


PAIR_DEFAULTS = {
    "info": ("#88B8D0", "#28323D"),
    "warn": ("#D4B878", "#3D3528"),
    "error": ("#D4908F", "#3D2828"),
}


def _make_settings(unique_suffix: str) -> SettingsManager:
    mgr = SettingsManager(namespace=f"uitk_test/color_mapping/{unique_suffix}")
    # Wipe any leftover keys from prior runs
    for key in PAIR_DEFAULTS:
        mgr.clear(f"{key}/fg")
        mgr.clear(f"{key}/bg")
        mgr.clear(key)
    return mgr


class TestApplyColorMapShape(QtBaseTestCase):
    """``apply_color_map`` must persist in the shape ``_current_color`` reads."""

    def test_pair_value_round_trips_through_settings(self):
        settings = _make_settings("pair_round_trip")
        editor = self.track_widget(
            ColorMappingEditor(defaults=PAIR_DEFAULTS, settings=settings)
        )
        app.processEvents()

        editor.apply_color_map({"warn": ["#00FF00", "#003300"]})

        # The /fg and /bg keys must be populated so a fresh editor reading
        # from the same settings sees the override.
        self.assertEqual(settings.value("warn/fg"), "#00FF00")
        self.assertEqual(settings.value("warn/bg"), "#003300")

        # color_map() exposes the resolved override, not the default
        self.assertEqual(editor.color_map()["warn"], ("#00FF00", "#003300"))

    def test_scalar_value_on_pair_entry_broadcasts_to_both_slots(self):
        """A single hex applied to a pair-default key must fan out to fg+bg."""
        settings = _make_settings("scalar_on_pair")
        editor = self.track_widget(
            ColorMappingEditor(defaults=PAIR_DEFAULTS, settings=settings)
        )
        app.processEvents()

        editor.apply_color_map({"warn": "#ABCDEF"})

        self.assertEqual(settings.value("warn/fg"), "#ABCDEF")
        self.assertEqual(settings.value("warn/bg"), "#ABCDEF")
        self.assertEqual(editor.color_map()["warn"], ("#ABCDEF", "#ABCDEF"))

    def test_pair_value_on_scalar_entry_collapses_to_fg(self):
        """A pair applied to a single-default key must collapse to ``key`` slot."""
        scalar_defaults = {"accent": "#5B8BD4"}
        settings = _make_settings("pair_on_scalar")
        editor = self.track_widget(
            ColorMappingEditor(defaults=scalar_defaults, settings=settings)
        )
        app.processEvents()

        editor.apply_color_map({"accent": ["#112233", "#445566"]})

        # _current_color for a scalar default reads the flat key, not /fg.
        self.assertEqual(settings.value("accent"), "#112233")
        self.assertEqual(editor.color_map()["accent"], "#112233")

    def test_unknown_keys_silently_skipped(self):
        settings = _make_settings("unknown_keys")
        editor = self.track_widget(
            ColorMappingEditor(defaults=PAIR_DEFAULTS, settings=settings)
        )
        app.processEvents()

        editor.apply_color_map({"nonexistent": "#000000"})

        self.assertIsNone(settings.value("nonexistent"))
        self.assertIsNone(settings.value("nonexistent/fg"))


class TestColorMappingDialogPresets(QtBaseTestCase):
    """End-to-end preset round-trip via the dialog."""

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.preset_dir = Path(self._tmp.name) / "presets"

    def tearDown(self):
        self._tmp.cleanup()
        super().tearDown()

    def test_default_preset_auto_written_on_first_use(self):
        settings = _make_settings("dlg_default_preset")
        dlg = self.track_widget(
            ColorMappingDialog(
                defaults=PAIR_DEFAULTS,
                settings=settings,
                preset_dir=self.preset_dir,
            )
        )
        app.processEvents()
        app.processEvents()

        default_path = self.preset_dir / "default.json"
        self.assertTrue(default_path.exists())
        data = json.loads(default_path.read_text())
        # Stored colors should match the defaults exactly (lists from JSON)
        stored = data["_meta"]["colors"]
        self.assertEqual(set(stored), set(PAIR_DEFAULTS))
        for k, (fg, bg) in PAIR_DEFAULTS.items():
            self.assertEqual(stored[k], [fg, bg])
        dlg.close()

    def test_default_preset_not_overwritten_if_present(self):
        # Pre-write a tampered "default" preset to verify the dialog doesn't
        # clobber a user's customised default on subsequent opens.
        self.preset_dir.mkdir(parents=True, exist_ok=True)
        tampered = {"_meta": {"version": 1, "colors": {"info": ["#000000", "#FFFFFF"]}}}
        (self.preset_dir / "default.json").write_text(json.dumps(tampered))

        settings = _make_settings("dlg_preserve_default")
        dlg = self.track_widget(
            ColorMappingDialog(
                defaults=PAIR_DEFAULTS,
                settings=settings,
                preset_dir=self.preset_dir,
            )
        )
        app.processEvents()

        data = json.loads((self.preset_dir / "default.json").read_text())
        self.assertEqual(data["_meta"]["colors"]["info"], ["#000000", "#FFFFFF"])
        dlg.close()

    def test_load_preset_applies_colors_and_settings(self):
        settings = _make_settings("dlg_load_preset")
        dlg = self.track_widget(
            ColorMappingDialog(
                defaults=PAIR_DEFAULTS,
                settings=settings,
                preset_dir=self.preset_dir,
            )
        )
        app.processEvents()

        # Mutate then save a "custom" preset
        dlg._editor.apply_color_map({"warn": ("#00FF00", "#003300")})
        dlg._preset_manager.save("custom")

        # Apply something else, then load "default" to revert
        dlg._editor.apply_color_map({"warn": ("#FF0000", "#330000")})
        dlg._preset_manager.load("default")

        self.assertEqual(dlg._editor.color_map()["warn"], ("#D4B878", "#3D3528"))
        # Settings must reflect the loaded preset so reopening the dialog
        # restores the same state.
        self.assertEqual(settings.value("warn/fg"), "#D4B878")
        self.assertEqual(settings.value("warn/bg"), "#3D3528")
        dlg.close()


if __name__ == "__main__":
    unittest.main()
