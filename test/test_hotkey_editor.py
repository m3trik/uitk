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

    def test_dirty_check_peeks_not_builds(self):
        """``export_shortcuts(loaded_only=True)`` reads already-loaded UIs via
        ``peek`` and never calls ``get_ui`` — so the preset dirty-check cannot
        build every registered UI (the cause of the slow editor launch).
        """
        from unittest import mock

        with mock.patch.object(self.sb, "get_ui", wraps=self.sb.get_ui) as spy:
            data = self.editor.export_shortcuts(loaded_only=True)
        spy.assert_not_called()
        self.assertIsInstance(data, dict)

    def test_modified_provider_wired_to_cheap_export(self):
        """The editor wires ``PresetManager.modified_value_provider`` to the
        cheap (``loaded_only``) export, so computing the modified marker on open
        never builds every UI.
        """
        from unittest import mock

        mgr = self.editor._preset_mgr
        self.assertIsNotNone(mgr.modified_value_provider)
        with mock.patch.object(self.sb, "get_ui", wraps=self.sb.get_ui) as spy:
            mgr.modified_value_provider()
        spy.assert_not_called()

    def test_collision_checker_peeks_not_builds(self):
        """The internal collision checker reads only already-loaded UIs (peek),
        never ``get_ui`` — assigning a shortcut must not build every registered
        UI (the cause of the assign slowness/crash and native-menu MEL errors).
        """
        from unittest import mock

        with mock.patch.object(self.sb, "get_ui", wraps=self.sb.get_ui) as spy:
            self.editor._builtin_internal_collision_checker(
                "Ctrl+Alt+9", "window", "example", "nope"
            )
        spy.assert_not_called()

    def test_scope_toggle_is_modeless(self):
        """Toggling a binding's scope applies immediately and never pops the
        conflict modal — even when a checker reports a conflict (the modal is
        reserved for binding a key).
        """
        from unittest import mock
        from uitk.widgets.editors.hotkey_editor import CollisionConflict

        for i in range(self.editor.cmb_ui.count()):
            if "example" in self.editor.cmb_ui.itemText(i).lower():
                self.editor.cmb_ui.setCurrentIndex(i)
                break
        self.editor.populate()
        if self.editor.table.rowCount() == 0:
            self.skipTest("no example slots in table")

        # Give row 0 a sequence (in the table) so the toggle runs a conflict check.
        self.editor.table.item(0, 1).setText("Ctrl+Alt+5")
        method = self.editor.table.item(0, 0).toolTip().replace("Method: ", "")
        self.editor.add_collision_checker(
            lambda *a, **k: [CollisionConflict("uitk", "dup", breaks_binding=True)]
        )
        with mock.patch.object(self.editor, "_prompt_conflicts") as prompt, mock.patch.object(
            self.sb, "set_user_shortcut"
        ) as setsc:
            self.editor._on_scope_toggle(self.ui, method, "window")
        prompt.assert_not_called()  # modeless — no modal on a scope flip
        setsc.assert_called_once()  # but the toggle was applied

    def test_conflict_dialog_offers_maya_clear_when_editable(self):
        """A Maya conflict carrying a clear_action gets an 'Assign & free Maya
        binding' button; clicking it runs the Maya clear and proceeds.
        """
        from unittest import mock
        from uitk.widgets.editors.hotkey_editor import CollisionConflict
        import uitk.widgets.editors.hotkey_editor as he

        cleared = []
        conf = CollisionConflict(
            "maya", "Maya 'cut'", breaks_binding=False,
            clear_action=lambda: cleared.append("maya"),
        )
        buttons = {}
        box = mock.MagicMock()
        box.addButton.side_effect = lambda *a, **k: buttons.setdefault(a[0], mock.Mock())
        box.clickedButton.side_effect = lambda: buttons.get("Assign && free Maya binding")
        MB = mock.MagicMock(return_value=box)
        MB.Cancel, MB.Warning, MB.AcceptRole = "CANCEL", "WARN", "ACCEPT"
        with mock.patch.object(he.QtWidgets, "QMessageBox", MB):
            proceed = self.editor._prompt_conflicts("Ctrl+S", "window", [conf])
        self.assertTrue(proceed)
        self.assertEqual(cleared, ["maya"])
        self.assertIn("Assign && free Maya binding", buttons)

    def test_conflict_dialog_disables_maya_clear_when_locked(self):
        """A Maya conflict with no clear_action (locked set) shows the option
        disabled rather than absent, and clears nothing on 'Assign anyway'.
        """
        from unittest import mock
        from uitk.widgets.editors.hotkey_editor import CollisionConflict
        import uitk.widgets.editors.hotkey_editor as he

        conf = CollisionConflict("maya", "Maya 'cut' (locked)", breaks_binding=False)
        buttons = {}
        box = mock.MagicMock()
        box.addButton.side_effect = lambda *a, **k: buttons.setdefault(a[0], mock.Mock())
        box.clickedButton.side_effect = lambda: buttons.get("Assign anyway")
        MB = mock.MagicMock(return_value=box)
        MB.Cancel, MB.Warning, MB.AcceptRole = "CANCEL", "WARN", "ACCEPT"
        with mock.patch.object(he.QtWidgets, "QMessageBox", MB):
            proceed = self.editor._prompt_conflicts("Ctrl+S", "window", [conf])
        self.assertTrue(proceed)
        locked = buttons.get("Free Maya binding (set locked)")
        self.assertIsNotNone(locked, "locked Maya button should be present")
        locked.setEnabled.assert_called_with(False)

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

    def test_builtin_checker_offers_overwrite_for_app_vs_window(self):
        """An Application binding collides with a Window binding on the same key,
        and the conflict is overwritable (breaks_binding + clear_action).

        'Safe unless application wide': once either side is app-scoped the key
        genuinely conflicts, so the user must be offered the overwrite path —
        not just a soft 'may fire alongside' note.
        """
        registry = self.sb.get_shortcut_registry(self.ui)
        if len(registry) < 2:
            self.skipTest("Need at least two slots to test internal collision")

        first = registry[0]["method"]
        second = registry[1]["method"]
        ui_name = self.editor.cmb_ui.currentText() or ""

        # First slot grabs Ctrl+Alt+W at *application* scope.
        self.sb.set_user_shortcut(self.ui, first, "Ctrl+Alt+W", "application")

        # Assigning the same key to the second slot at *window* scope collides.
        conflicts = self.editor._builtin_internal_collision_checker(
            "Ctrl+Alt+W", "window", ui_name, second
        )
        self.assertTrue(conflicts, "app-vs-window same key must collide")
        self.assertTrue(all(c.breaks_binding for c in conflicts))
        self.assertTrue(all(c.clear_action for c in conflicts))

    def test_builtin_checker_allows_window_dupes_across_uis(self):
        """Two Window-scoped bindings on the same key in *different* UIs are
        safe — different windows are independent focus targets, so no conflict
        is reported (the scope rule that keeps reuse possible)."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")
        first = registry[0]["method"]
        self.sb.set_user_shortcut(self.ui, first, "Ctrl+Alt+Q", "window")

        # Probe as if assigning the same Window key in a *different* UI.
        conflicts = self.editor._builtin_internal_collision_checker(
            "Ctrl+Alt+Q", "window", "some_other_ui", "other_method"
        )
        self.assertEqual(
            conflicts, [], "window dupes across different UIs are safe"
        )

    def test_scope_button_disabled_without_sequence(self):
        """Scope toggles are disabled on rows with no bound key, enabled on rows
        that have one — scope is only meaningful once a sequence exists."""
        for i in range(self.editor.cmb_ui.count()):
            if "example" in self.editor.cmb_ui.itemText(i).lower():
                self.editor.cmb_ui.setCurrentIndex(i)
                break
        self.editor.populate()
        if self.editor.table.rowCount() == 0:
            self.skipTest("no example slots in table")

        from uitk.widgets.editors.hotkey_editor import USER_SCOPES

        saw_bound, saw_unbound = False, False
        for row in range(self.editor.table.rowCount()):
            seq = self.editor.table.item(row, 1).text()
            btn = self.editor.table.cellWidget(row, 2)
            scope = btn.property("scope_name")
            if not seq:
                saw_unbound = True
                self.assertFalse(
                    btn.isEnabled(), "scope button should be disabled with no key"
                )
            elif scope in USER_SCOPES:
                saw_bound = True
                self.assertTrue(
                    btn.isEnabled(),
                    "scope button should be enabled for a bound user-scoped row",
                )
        self.assertTrue(
            saw_bound or saw_unbound, "expected at least one scope button to check"
        )

    # ------------------------------------------------------------------
    # Preset row placement (header ⋯-menu)
    # ------------------------------------------------------------------

    def test_preset_row_lives_in_header_menu(self):
        """The hotkey editor tucks its preset selector into the header ⋯-menu,
        not the body — the header gains a menu button and the combo stays
        reachable."""
        self.assertIn("menu", self.editor.header.buttons)
        self.assertIsNotNone(self.editor._cmb_preset)
        self.assertTrue(self.editor.header.menu.contains_items)

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
