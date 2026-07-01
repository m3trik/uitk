# !/usr/bin/python
# coding=utf-8
"""Tests for ShortcutEditor preset management."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from qtpy import QtWidgets, QtCore
from conftest import QtBaseTestCase, setup_qt_application
from uitk.switchboard import Switchboard
from uitk.widgets.editors.shortcut_editor.registry_editor import ShortcutEditor
from uitk.widgets.editors.editor_panel import EditorPanel
from uitk.examples.example import ExampleSlots

app = setup_qt_application()


class TestShortcutEditorPresets(QtBaseTestCase):
    """Tests for ShortcutEditor preset save/load/delete/rename."""

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
        self.editor = ShortcutEditor(self.sb, parent=None)
        # Redirect storage to a unique temp dir through the real preset_dir
        # setter (which routes the underlying PresetManager), so save/load go
        # to the temp tree instead of the shared consolidated root.
        temp_root = Path(__file__).parent / "temp_tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        self._test_preset_dir = Path(
            tempfile.mkdtemp(prefix="shortcut_presets_", dir=temp_root)
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
        from uitk.widgets.editors.shortcut_editor.registry_editor import CollisionConflict

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
        from uitk.widgets.editors.shortcut_editor.registry_editor import CollisionConflict
        import uitk.widgets.editors.shortcut_editor.registry_editor as he

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
        from uitk.widgets.editors.shortcut_editor.registry_editor import CollisionConflict
        import uitk.widgets.editors.shortcut_editor.registry_editor as he

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
        path = self.editor.save_preset("test_shortcuts")
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

    def test_builtin_checker_flags_unloaded_overridden_ui(self):
        """An app-scoped binding persisted on an *unbuilt* UI still collides: it
        becomes a live QShortcut on load / next session, so the checker reads it
        from the no-build static registry instead of skipping unloaded UIs.

        This is the blind spot behind 'repeat-last works once then dies': its
        key was already owned, application-scoped, by an unbuilt UI's slot, so
        the two stacked into an ambiguous overload that fired neither — yet the
        editor never warned because it only inspected loaded UIs.
        """
        from unittest import mock

        ghost = "ghost_panel"
        static_entry = {
            "method": "b999",
            "name": "b999",
            "current": "Ctrl+Alt+8",
            "default": "",
            "current_scope": "application",
            "default_scope": "application",
            "doc": "",
        }
        with mock.patch.object(
            self.editor, "_registered_ui_names", return_value=[ghost]
        ), mock.patch.object(
            self.sb, "_ui_names_with_shortcut_overrides", return_value={ghost}
        ), mock.patch.object(
            self.sb, "get_static_shortcut_registry", return_value=[static_entry]
        ) as static_spy, mock.patch.object(
            self.sb, "get_ui", wraps=self.sb.get_ui
        ) as build_spy:
            # ``ghost_panel`` is never loaded, so loaded_ui.peek() returns None
            # for it naturally — the checker falls to the static-registry branch.
            conflicts = self.editor._builtin_internal_collision_checker(
                "Ctrl+Alt+8",
                "application",
                self.editor._COMMAND_UI,
                "repeat_last_command",
            )

        static_spy.assert_called_once_with(ghost)
        build_spy.assert_not_called()  # collision detection must never build a UI
        self.assertTrue(
            any(c.breaks_binding and ghost in c.description for c in conflicts),
            f"expected an overwritable conflict citing {ghost!r}, got {conflicts}",
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

        from uitk.widgets.editors.shortcut_editor.registry_editor import USER_SCOPES

        saw_bound, saw_unbound = False, False
        for row in range(self.editor.table.rowCount()):
            seq = self.editor.table.item(row, 1).text()
            scope = self.editor.scope_at(row)
            if not seq:
                saw_unbound = True
                self.assertFalse(
                    self.editor.scope_interactive(row),
                    "scope cell should be inert with no key",
                )
            elif scope in USER_SCOPES:
                saw_bound = True
                self.assertTrue(
                    self.editor.scope_interactive(row),
                    "scope cell should be interactive for a bound user-scoped row",
                )
        self.assertTrue(
            saw_bound or saw_unbound, "expected at least one scope button to check"
        )

    def test_scope_toggle_enabled_after_interactive_assign(self):
        """Assigning a key via the in-cell capture path must re-enable that
        row's scope toggle (a sequence now exists to scope). Exercises the
        delegate→``_apply_shortcut``→``populate`` rebuild, not just the static
        populate path, since the toggle is recreated per rebuild."""
        from unittest import mock
        from uitk.widgets.editors.shortcut_editor.registry_editor import USER_SCOPES

        for i in range(self.editor.cmb_ui.count()):
            if "example" in self.editor.cmb_ui.itemText(i).lower():
                self.editor.cmb_ui.setCurrentIndex(i)
                break
        self.editor.populate()

        # Find an unbound, user-scoped row (disabled toggle) to assign into.
        target = None
        for row in range(self.editor.table.rowCount()):
            if (
                not self.editor.table.item(row, 1).text()
                and self.editor.scope_at(row) in USER_SCOPES
            ):
                target = row
                break
        if target is None:
            self.skipTest("no unbound user-scoped example row")

        method = self.editor.table.item(target, 0).toolTip().replace("Method: ", "")
        with mock.patch.object(self.editor, "_resolve_collisions", return_value=True):
            self.editor._apply_shortcut(target, "Ctrl+Alt+7")

        # Row order is stable (sorted by method); locate the same method's row.
        for row in range(self.editor.table.rowCount()):
            if self.editor.table.item(row, 0).toolTip().replace(
                "Method: ", ""
            ) == method:
                self.assertEqual(self.editor.table.item(row, 1).text(), "Ctrl+Alt+7")
                self.assertTrue(
                    self.editor.scope_interactive(row),
                    "scope toggle must enable once a key is assigned",
                )
                return
        self.fail("assigned row not found after repopulate")

    def test_command_scope_shows_active_badge_after_assign(self):
        """A command's scope is fixed at Application (no window to scope to).
        Once a key is assigned, its scope cell is a non-interactive App badge
        shown in the *on* state — disabled but tinted/active, not a greyed
        'assign a shortcut first' toggle."""
        from unittest import mock

        idx = self.editor.cmb_ui.findText(self.editor._COMMANDS_LABEL)
        if idx < 0:
            self.skipTest("no commands registered")
        self.editor.cmb_ui.setCurrentIndex(idx)
        self.editor.populate()
        if self.editor.table.rowCount() == 0 or self.editor.table.columnSpan(0, 0) > 1:
            self.skipTest("no command rows")

        with mock.patch.object(self.editor, "_resolve_collisions", return_value=True):
            self.editor._apply_shortcut(0, "Ctrl+Alt+6")

        self.assertEqual(self.editor.table.item(0, 1).text(), "Ctrl+Alt+6")
        self.assertEqual(self.editor.scope_at(0), "application")
        # Fixed scope: non-interactive, but shown active ("on"), not greyed-off.
        self.assertFalse(
            self.editor.scope_interactive(0),
            "command scope is fixed, so non-interactive",
        )
        scope_item = self.editor.table.item(0, 2)
        self.assertIn("application-scoped", scope_item.toolTip().lower())
        self.assertNotIn("assign", scope_item.toolTip().lower())
        # Active badge tint: a translucent background brush behind the icon (not
        # a greyed-off control).
        self.assertGreater(
            scope_item.background().color().alpha(), 0, "active badge tint"
        )

    def test_binding_tooltip_is_formatted_rich_text(self):
        """The per-row tooltip is HTML: action name in bold, the bound key set
        off and colour-coded, inputs escaped, and an explicit 'Unassigned' when
        no key is bound."""
        from uitk.widgets.editors.shortcut_editor.registry_editor import _TT_KEY

        tip = ShortcutEditor._binding_tooltip("Save & Exit", "Saves the <file>.", "Ctrl+S")
        self.assertTrue(tip.lstrip().startswith("<"), "tooltip should be rich text")
        self.assertIn("<b>Save &amp; Exit</b>", tip, "name escaped + bold")
        self.assertIn("Saves the &lt;file&gt;.", tip, "description escaped")
        self.assertIn("Ctrl+S", tip)
        self.assertIn(_TT_KEY, tip, "bound key is colour-coded")
        self.assertIn("Shortcut", tip)

        unbound = ShortcutEditor._binding_tooltip("Nudge", "", "")
        self.assertIn("Unassigned", unbound)
        self.assertNotIn(_TT_KEY, unbound, "no key accent when unbound")

    # ------------------------------------------------------------------
    # Preset row placement (header ⋯-menu)
    # ------------------------------------------------------------------

    def test_preset_row_lives_in_header_menu(self):
        """The shortcut editor tucks its preset selector into the header ⋯-menu,
        not the body — the header gains a menu button and the combo stays
        reachable."""
        self.assertIn("menu", self.editor.header.buttons)
        self.assertIsNotNone(self.editor._cmb_preset)
        self.assertTrue(self.editor.header.menu.contains_items)

    # ------------------------------------------------------------------
    # UI listing & on-demand load
    # ------------------------------------------------------------------

    def test_combobox_lists_all_registered_uis(self):
        """The Target UI combobox should list every registered UI, loaded or not.

        Plus the two special "pseudo-UI" views at the top — "Assigned" (always,
        when there's anything to view) and "Commands" (the Switchboard's built-in
        nav commands are always registered).
        """
        filenames = self.sb.registry.ui_registry.get("filename") or []
        expected = {
            self.sb.convert_to_legal_name(name.rsplit(".", 1)[0]) for name in filenames
        }
        self.assertTrue(expected, "Test fixture should register at least one UI")
        expected.add(self.editor._COMMANDS_LABEL)
        expected.add(self.editor._ASSIGNED_LABEL)

        listed = {
            self.editor.cmb_ui.itemText(i) for i in range(self.editor.cmb_ui.count())
        }
        self.assertEqual(listed, expected)

    def test_populate_loads_unloaded_ui_on_selection(self):
        """Selecting an unloaded UI in the combobox should instantiate it on demand."""
        # The fixture's setUp loaded the example UI. Evict it from the
        # loaded_ui cache so we can prove that selecting it triggers a
        # fresh load, rather than just reading the cached value.
        # Specials sort to item 0, so target the example UI by name, not index.
        target_idx = next(
            i
            for i in range(self.editor.cmb_ui.count())
            if "example" in self.editor.cmb_ui.itemText(i).lower()
        )
        target_name = self.editor.cmb_ui.itemText(target_idx)
        self.assertTrue(target_name)

        del self.sb.loaded_ui[target_name]
        self.assertIsNone(
            self.sb.loaded_ui.peek(target_name),
            "Eviction should leave loaded_ui.peek returning None",
        )

        # Force a re-selection to fire currentTextChanged → populate().
        self.editor.cmb_ui.setCurrentIndex(-1)
        self.editor.cmb_ui.setCurrentIndex(target_idx)
        QtWidgets.QApplication.processEvents()

        self.assertIsNotNone(
            self.sb.loaded_ui.peek(target_name),
            "Selecting an unloaded UI should instantiate it",
        )
        first_cell = self.editor.table.item(0, 0)
        if first_cell is not None:
            self.assertNotIn("Could not load", first_cell.text())


class TestShortcutEditorFilter(QtBaseTestCase):
    """The filter LineEdit hides non-matching rows in place, the option-box
    toggle disables filtering, and the footer reflects the visible count."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module, slot_source=ExampleSlots
        )
        self.ui = self.sb.loaded_ui.example
        self.ui.show()
        QtWidgets.QApplication.processEvents()
        self.editor = ShortcutEditor(self.sb, parent=None)

    def tearDown(self):
        if getattr(self, "editor", None):
            # Don't let the 'show all' view mode persist into other tests via
            # the process-wide sandboxed QSettings.
            self.editor._settings.setValue("show_all", False)
            self.editor.close()
        if getattr(self, "ui", None):
            self.ui.close()
        super().tearDown()

    def _table_with_real_rows(self):
        t = self.editor.table
        if t.columnSpan(0, 0) > 1 or t.rowCount() == 0:
            self.skipTest("example UI has no real shortcut rows to filter")
        return t

    def _first_row_token(self, t):
        first = t.item(0, 0).text()
        return first.split()[0] if first.split() else first

    def test_matching_term_keeps_row_and_others_only_if_they_match(self):
        t = self._table_with_real_rows()
        token = self._first_row_token(t)
        # Strict matching → wrap in * for a substring search of the haystack.
        self.editor.le_filter.setText(f"*{token}*")
        QtWidgets.QApplication.processEvents()

        self.assertFalse(t.isRowHidden(0), "row matching the query stays visible")
        # Every *visible* row must contain the token (case-insensitive).
        for row in range(t.rowCount()):
            if not t.isRowHidden(row):
                self.assertIn(
                    token.lower(), self.editor._row_haystack(row).lower()
                )

    def test_no_match_hides_every_row(self):
        t = self._table_with_real_rows()
        self.editor.le_filter.setText("zzz_no_such_action_zzz")
        QtWidgets.QApplication.processEvents()
        self.assertTrue(
            all(t.isRowHidden(r) for r in range(t.rowCount())),
            "a query matching nothing hides every row",
        )

    def test_disabling_filter_reveals_all_even_with_text(self):
        t = self._table_with_real_rows()
        self.editor.le_filter.setText("zzz_no_such_action_zzz")
        QtWidgets.QApplication.processEvents()
        self.editor._filter.set_on(False)
        self.assertTrue(
            all(not t.isRowHidden(r) for r in range(t.rowCount())),
            "disabling the filter reveals every row regardless of text",
        )
        # Re-enabling restores the active query.
        self.editor._filter.set_on(True)
        self.assertTrue(
            all(t.isRowHidden(r) for r in range(t.rowCount())),
            "re-enabling re-applies the (still non-matching) query",
        )

    def test_filter_toggle_off_disables_field_but_keeps_button_live(self):
        """Toggling the filter off greys out the filter field (red icon ==
        disabled field) while the toggle button stays clickable to re-enable."""
        le = self.editor.le_filter
        toggle = self.editor._filter
        btn = toggle.widget
        self.assertTrue(le.isEnabled())

        toggle.set_on(False)  # user clicks the filter toggle off
        le.container._sync_option_buttons_enabled()
        self.assertFalse(le.isEnabled(), "filter off must grey out the field")
        self.assertTrue(
            btn.isEnabled(), "the filter toggle button must stay clickable"
        )

        toggle.set_on(True)
        self.assertTrue(le.isEnabled(), "re-enabling restores the field")

    def test_clearing_text_reveals_all(self):
        t = self._table_with_real_rows()
        self.editor.le_filter.setText("zzz_no_such_action_zzz")
        QtWidgets.QApplication.processEvents()
        self.editor.le_filter.setText("")
        QtWidgets.QApplication.processEvents()
        self.assertTrue(
            all(not t.isRowHidden(r) for r in range(t.rowCount())),
            "empty filter text shows every row",
        )

    def test_filter_persists_across_ui_repopulate(self):
        """A UI switch rebuilds the table; the active filter must re-apply so a
        non-matching query keeps the rebuilt rows hidden."""
        t = self._table_with_real_rows()
        self.editor.le_filter.setText("zzz_no_such_action_zzz")
        QtWidgets.QApplication.processEvents()
        self.editor.populate()  # simulate a rebuild
        self.assertTrue(
            all(t.isRowHidden(r) for r in range(t.rowCount())),
            "filter must survive a table rebuild",
        )

    def test_status_reports_partial_count(self):
        """``_compose_status`` appends a visible/total tail only when some rows
        are hidden, and shows the base status alone otherwise."""
        self.editor._base_status = "10 shortcuts"
        self.assertEqual(
            self.editor._compose_status(3, 10), "10 shortcuts — showing 3 of 10"
        )
        self.assertEqual(self.editor._compose_status(10, 10), "10 shortcuts")
        self.assertEqual(self.editor._compose_status(None, 10), "10 shortcuts")

    def test_show_all_filter_includes_ui_column(self):
        """In 'show all' mode the filter also matches the UI-name column."""
        self.editor._set_show_all(True)
        if self.editor.table.columnSpan(0, 0) > 1 or not self.editor.table.rowCount():
            self.skipTest("no real rows in all view")
        # The UI name ("example") is in column 5; filtering by it keeps rows.
        self.editor.le_filter.setText("*example*")
        QtWidgets.QApplication.processEvents()
        self.assertFalse(self.editor.table.isRowHidden(0))

    def test_empty_ui_clears_stale_filter_count(self):
        """Switching to a UI with no shortcuts must reset the footer — a prior
        ``showing X of N`` count must not linger over the 'No shortcuts' row."""
        from unittest import mock

        # Simulate a prior state where an active filter left a partial count.
        self.editor._base_status = "5 shortcuts"
        self.editor.footer.setStatusText("5 shortcuts — showing 2 of 5")

        with mock.patch.object(self.sb, "get_shortcut_registry", return_value=[]):
            self.editor.populate()

        self.assertEqual(self.editor._base_status, "0 shortcuts")
        self.assertNotIn("showing", self.editor._compose_status(None, 0))


class TestShortcutEditorAllView(QtBaseTestCase):
    """The 'show all' toggle lists every UI's slots at once, reveals the UI
    column, disables the combobox, keys each row to its own UI, and only
    instantiates a UI when one of its bindings is edited."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module, slot_source=ExampleSlots
        )
        self.ui = self.sb.loaded_ui.example
        self.ui.show()
        QtWidgets.QApplication.processEvents()
        self.editor = ShortcutEditor(self.sb, parent=None)
        self.editor._set_show_all(False)  # normalize (settings persist in-process)

    def tearDown(self):
        if getattr(self, "editor", None):
            # Don't let the 'show all' view mode persist into other tests via
            # the process-wide sandboxed QSettings.
            self.editor._settings.setValue("show_all", False)
            self.editor.close()
        if getattr(self, "ui", None):
            self.ui.close()
        super().tearDown()

    def _has_real_rows(self):
        t = self.editor.table
        return t.columnSpan(0, 0) == 1 and t.rowCount() > 0

    def test_toggle_reveals_ui_column_and_disables_combo(self):
        self.assertTrue(self.editor.table.isColumnHidden(5))
        self.assertTrue(self.editor.cmb_ui.isEnabled())

        self.editor._set_show_all(True)
        self.assertFalse(self.editor.table.isColumnHidden(5))
        self.assertFalse(
            self.editor.cmb_ui.isEnabled(), "combo is disabled while showing all"
        )
        if self._has_real_rows():
            self.assertEqual(self.editor.table.item(0, 5).text(), "example")

    def test_toggling_back_re_enables_combo_and_hides_column(self):
        self.editor._set_show_all(True)
        self.editor._set_show_all(False)
        self.assertTrue(self.editor.cmb_ui.isEnabled())
        self.assertTrue(self.editor.table.isColumnHidden(5))

    def test_apply_shortcut_resolves_row_ui_not_combobox(self):
        """Regression: the in-cell edit must resolve the UI from the row, not
        the combobox (which is wrong/disabled in 'show all' mode)."""
        from unittest import mock

        self.editor.populate()
        if not self._has_real_rows():
            self.skipTest("no real rows to edit")

        # Tag row 0 with a sentinel UI distinct from the combobox selection.
        self.editor.table.item(0, 0).setData(QtCore.Qt.UserRole, "sentinel_ui")
        captured = {}

        def fake_get_ui(x):
            captured["name"] = x
            return self.ui  # any live UI so the commit can proceed

        with mock.patch.object(self.sb, "get_ui", side_effect=fake_get_ui), mock.patch.object(
            self.editor, "_resolve_collisions", return_value=True
        ), mock.patch.object(self.sb, "set_user_shortcut"):
            self.editor._apply_shortcut(0, "Ctrl+Alt+8")

        self.assertEqual(
            captured.get("name"),
            "sentinel_ui",
            "edit must resolve the row's UI (UserRole), not the combobox text",
        )

    def test_all_view_lists_unloaded_ui_without_building_it(self):
        """Listing all UIs uses the static (no-build) path for unloaded UIs."""
        from unittest import mock

        del self.sb.loaded_ui["example"]  # make it unloaded
        with mock.patch.object(
            self.sb, "get_ui", wraps=self.sb.get_ui
        ) as get_ui_spy, mock.patch.object(
            self.sb,
            "get_static_shortcut_registry",
            wraps=self.sb.get_static_shortcut_registry,
        ) as static_spy:
            self.editor._set_show_all(True)

        get_ui_spy.assert_not_called()
        static_spy.assert_called()
        self.assertIsNone(
            self.sb.loaded_ui.peek("example"),
            "listing all UIs must not instantiate an unloaded one",
        )

    def test_apply_shortcut_handles_unloadable_ui_gracefully(self):
        """A statically-listed row whose UI fails to build on edit must not
        crash (get_ui -> None) — it reports and no-ops instead."""
        from unittest import mock

        self.editor.populate()
        if not self._has_real_rows():
            self.skipTest("no real rows to edit")
        self.editor.table.item(0, 0).setData(QtCore.Qt.UserRole, "broken_ui")

        with mock.patch.object(self.sb, "get_ui", return_value=None), mock.patch.object(
            self.sb, "set_user_shortcut"
        ) as setsc:
            self.editor._apply_shortcut(0, "Ctrl+Alt+9")  # must not raise

        setsc.assert_not_called()

    def test_editing_in_all_view_instantiates_only_that_ui(self):
        """Answers the design question: editing a row in 'show all' builds just
        that row's UI (lazy), never the whole set."""
        from unittest import mock

        del self.sb.loaded_ui["example"]
        self.editor._set_show_all(True)
        if not self._has_real_rows():
            self.skipTest("static registry produced no rows")
        self.assertIsNone(self.sb.loaded_ui.peek("example"))

        with mock.patch.object(self.editor, "_resolve_collisions", return_value=True):
            self.editor._apply_shortcut(0, "Ctrl+Alt+8")

        self.assertIsNotNone(
            self.sb.loaded_ui.peek("example"),
            "editing a row must instantiate that row's UI on demand",
        )


if __name__ == "__main__":
    unittest.main()


class TestShortcutEditorGeometryPersistence(QtBaseTestCase):
    """The editor must remember a user-adjusted window size across sessions.

    The editor is a plain WindowPanel (not a MainWindow), so it never had
    geometry persistence: a hand-resized window reopened at the constructor's
    600x600 default every session. WindowPanel now offers opt-in persistence
    and the editor opts in, keyed per launch variant.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module, slot_source=ExampleSlots
        )
        # A loaded UI so populate() has real rows (mirrors the other suites).
        self.ui = self.sb.loaded_ui.example
        self.ui.show()
        QtWidgets.QApplication.processEvents()
        self._editors = []

    def tearDown(self):
        # Close first (closeEvent saves geometry), THEN clear — so nothing leaks
        # through the process-wide sandboxed QSettings into another test.
        for editor in self._editors:
            try:
                editor.close()
                for variant in ("main", "commands"):
                    editor._settings.clear(f"window_geometry.{variant}")
            except RuntimeError:  # already destroyed
                pass
        if getattr(self, "ui", None):
            self.ui.close()
        super().tearDown()

    def _make_editor(self, **kwargs):
        editor = self.track_widget(ShortcutEditor(self.sb, parent=None, **kwargs))
        self._editors.append(editor)
        return editor

    def test_editor_opts_into_geometry_persistence(self):
        """The editor wires WindowPanel geometry persistence to its own settings
        branch, under a focus-keyed key."""
        editor = self._make_editor()
        self.assertIs(editor._geometry_settings, editor._settings)
        self.assertEqual(editor._geometry_key, "window_geometry.main")

        focused = self._make_editor(focus="commands")
        self.assertEqual(focused._geometry_key, "window_geometry.commands")

    def test_size_persists_across_sessions(self):
        """A resized editor reopens at that size, not the 600x600 default."""
        # --- Session 1: show, resize, hide (saves geometry) ---
        e1 = self._make_editor()
        e1.clear_saved_geometry()
        e1.show()
        QtWidgets.QApplication.processEvents()
        e1.resize(480, 420)
        QtWidgets.QApplication.processEvents()
        e1.hide()  # triggers save_window_geometry
        QtWidgets.QApplication.processEvents()

        # --- Session 2: a fresh editor restores the saved size ---
        e2 = self._make_editor()
        e2.show()
        QtWidgets.QApplication.processEvents()
        self.assertEqual((e2.width(), e2.height()), (480, 420))

    def test_restored_size_is_authoritative_over_fit(self):
        """A restored (tall) size survives the on-show content fit.

        Re-fitting a restored window to the small example table's content is
        exactly what discarded a hand-expanded height every session.
        """
        e1 = self._make_editor()
        e1.clear_saved_geometry()
        e1.show()
        QtWidgets.QApplication.processEvents()
        e1.resize(520, 560)
        QtWidgets.QApplication.processEvents()
        e1.hide()
        QtWidgets.QApplication.processEvents()

        e2 = self._make_editor()
        e2.show()
        # Drain the deferred _fit_to_content tick; it must be skipped on a
        # restored window.
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.processEvents()
        self.assertEqual((e2.width(), e2.height()), (520, 560))

    def test_focus_variants_keep_separate_sizes(self):
        """The full editor and the focused 'commands' panel share a settings
        branch but must not clobber each other's remembered size."""
        full = self._make_editor()
        full.clear_saved_geometry()
        full.show()
        QtWidgets.QApplication.processEvents()
        full.resize(500, 500)
        QtWidgets.QApplication.processEvents()
        full.hide()
        QtWidgets.QApplication.processEvents()

        commands = self._make_editor(focus="commands")
        commands.clear_saved_geometry()
        commands.show()
        QtWidgets.QApplication.processEvents()
        commands.resize(360, 300)
        QtWidgets.QApplication.processEvents()
        commands.hide()
        QtWidgets.QApplication.processEvents()

        # Reopen the full editor: it restores ITS size, not the commands panel's.
        full2 = self._make_editor()
        full2.show()
        QtWidgets.QApplication.processEvents()
        self.assertEqual((full2.width(), full2.height()), (500, 500))

    def test_first_show_without_saved_geometry_fits_to_content(self):
        """With nothing to restore, first show still fits to content — the
        restore skip must not disable content-fitting outright."""
        e = self._make_editor()
        e.clear_saved_geometry()  # ensure a first-ever show (nothing restored)
        e.resize(600, 900)  # oversize before show; the fit should trim height
        e.show()
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.processEvents()  # let deferred _fit_to_content run
        self.assertLess(
            e.height(), 900, "first show with no saved size must fit to content"
        )
