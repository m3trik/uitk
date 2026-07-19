# !/usr/bin/python
# coding=utf-8
"""Unit tests for the Switchboard shortcut system.

Uses the real Switchboard with the examples module to test:
- Shortcut registration via @shortcut decorator
- Registry generation from connected slots
- User shortcut assignment and persistence
- ShortcutEditor UI functionality
"""
import unittest
from qtpy import QtWidgets, QtCore, QtGui

# Base Test
from conftest import QtBaseTestCase

# Code to Test
from uitk.switchboard import Switchboard
from uitk.widgets.editors.shortcut_editor.registry_editor import ShortcutEditor
from uitk.switchboard import Shortcut
from uitk.examples.example import ExampleSlots


# -----------------------------------------------------------------------------
# Integration Tests - Using Real Switchboard
# -----------------------------------------------------------------------------


class TestShortcutRegistry(QtBaseTestCase):
    """Test shortcut registry generation using the real Switchboard."""

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

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_registry_returns_list(self):
        """Registry should return a list."""
        registry = self.sb.get_shortcut_registry(self.ui)
        self.assertIsInstance(registry, list)

    def test_registry_entries_have_required_fields(self):
        """Each registry entry should have the required fields."""
        registry = self.sb.get_shortcut_registry(self.ui)

        for entry in registry:
            self.assertIn("class", entry)
            self.assertIn("method", entry)
            self.assertIn("name", entry)
            self.assertIn("current", entry)
            self.assertIn("default", entry)
            self.assertIn("doc", entry)

    def test_registry_only_contains_connected_slots(self):
        """Registry should only contain slots that are connected to widgets."""
        registry = self.sb.get_shortcut_registry(self.ui)
        method_names = [r["method"] for r in registry]

        # Get the slots instance to check what methods exist
        slots = self.sb.get_slots_instance(self.ui)

        # Verify none of the excluded method types are present
        for name in method_names:
            # Should not be private
            self.assertFalse(
                name.startswith("_"), f"Private method in registry: {name}"
            )
            # Should not be init method
            self.assertFalse(name.endswith("_init"), f"Init method in registry: {name}")
            # Should not be state callback
            self.assertFalse(
                name.startswith("on_"), f"State callback in registry: {name}"
            )

    def test_registry_matches_connected_slots(self):
        """Registry methods should match widgets in connected_slots."""
        registry = self.sb.get_shortcut_registry(self.ui)
        method_names = set(r["method"] for r in registry)

        # Get connected slot widget names using .items() for NamespaceHandler
        connected = getattr(self.ui, "connected_slots", {})
        connected_widget_names = set()
        for widget, signals in connected.items():
            if widget == "default":
                continue
            if hasattr(widget, "objectName"):
                connected_widget_names.add(widget.objectName())

        # Every registry method should either be in connected_slots or have @shortcut
        slots = self.sb.get_slots_instance(self.ui)
        for name in method_names:
            method = getattr(slots, name, None)
            has_decorator = bool(getattr(method, "_shortcut_meta", {}).get("sequence"))
            in_connected = name in connected_widget_names
            self.assertTrue(
                has_decorator or in_connected,
                f"Method {name} not in connected_slots and has no @shortcut",
            )


class TestShortcutAssignment(QtBaseTestCase):
    """Test user shortcut assignment using the real Switchboard."""

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

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_set_user_shortcut_persists_to_settings(self):
        """set_user_shortcut should persist to settings."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")

        slot_name = registry[0]["method"]
        test_shortcut = "Ctrl+Alt+T"

        self.sb.set_user_shortcut(self.ui, slot_name, test_shortcut)

        # Verify settings were updated
        slots_cls = self.sb.get_slots_instance(self.ui).__class__.__name__
        key = f"shortcuts.{slots_cls}.{slot_name}"
        stored = self.ui.settings.value(key)
        self.assertEqual(stored, test_shortcut)

    def test_set_user_shortcut_creates_qshortcut(self):
        """set_user_shortcut should create a live QShortcut."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")

        slot_name = registry[0]["method"]
        test_shortcut = "Ctrl+Alt+X"

        self.sb.set_user_shortcut(self.ui, slot_name, test_shortcut)

        # Verify QShortcut was created
        slots = self.sb.get_slots_instance(self.ui)
        self.assertIn(slot_name, slots._connected_shortcuts)
        sc = slots._connected_shortcuts[slot_name]
        self.assertEqual(sc.key().toString(), "Ctrl+Alt+X")

    def test_registry_reflects_user_shortcut(self):
        """Registry should show user-assigned shortcut in 'current'."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")

        slot_name = registry[0]["method"]
        test_shortcut = "Alt+Shift+Z"

        self.sb.set_user_shortcut(self.ui, slot_name, test_shortcut)

        # Re-fetch registry
        new_registry = self.sb.get_shortcut_registry(self.ui)
        entry = next(r for r in new_registry if r["method"] == slot_name)

        self.assertEqual(entry["current"], test_shortcut)


class TestClearedShortcutBinding(QtBaseTestCase):
    """Clearing a binding that has a non-empty decorator default truly clears it.

    Regression: an empty-string override was read with ``if override:`` (falsy),
    so a cleared binding fell through to its decorator default — overwriting or
    clearing a shortcut left the old/default sequence showing in the editor and
    still live. A *present* empty override now means "no shortcut"; only a
    *missing* override reverts to the default.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        from uitk.switchboard import Shortcut

        class _DefaultShortcutSlots(ExampleSlots):
            @Shortcut("Ctrl+Alt+9")
            def probe_default_action(self):
                pass

        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=_DefaultShortcutSlots,
        )
        self.ui = self.sb.loaded_ui.example
        # The sandboxed QSettings store is session-scoped, so an override a
        # sibling test wrote for this (stable) class/key leaks in. Clear it so
        # every test starts from a clean "no override" baseline.
        self._key = "shortcuts._DefaultShortcutSlots.probe_default_action"
        if hasattr(self.ui, "settings"):
            self.ui.settings.clear(self._key)
        self.ui.show()
        QtWidgets.QApplication.processEvents()

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            if hasattr(self.ui, "settings"):
                self.ui.settings.clear(self._key)
            self.ui.close()
        super().tearDown()

    def _entry(self):
        reg = self.sb.get_shortcut_registry(self.ui)
        return next((r for r in reg if r["method"] == "probe_default_action"), None)

    def test_default_present_without_override(self):
        """No override → the decorator default is the current sequence."""
        entry = self._entry()
        self.assertIsNotNone(entry, "decorated method missing from registry")
        self.assertEqual(entry["default"], "Ctrl+Alt+9")
        self.assertEqual(entry["current"], "Ctrl+Alt+9")

    def test_clear_overrides_the_default(self):
        """Overwrite then clear → current is empty, NOT the default (the bug)."""
        self.sb.set_user_shortcut(self.ui, "probe_default_action", "Ctrl+Alt+8")
        self.assertEqual(self._entry()["current"], "Ctrl+Alt+8")
        self.sb.set_user_shortcut(self.ui, "probe_default_action", "")
        self.assertEqual(self._entry()["current"], "")

    def test_cleared_binding_creates_no_qshortcut(self):
        """A cleared binding tears down its live QShortcut and registers none."""
        self.sb.set_user_shortcut(self.ui, "probe_default_action", "")
        slots = self.sb.get_slots_instance(self.ui)
        self.assertNotIn(
            "probe_default_action", getattr(slots, "_connected_shortcuts", {})
        )


class TestUndecoratedSlotShortcutPersistence(QtBaseTestCase):
    """Regression: an editor-assigned shortcut on an UNDECORATED slot was dead
    next session until the user reassigned it.

    ``register_slots_shortcuts`` (which re-creates a UI's shortcuts every time
    the UI is built) bailed at ``if not default_sequence: continue`` for every
    slot lacking a ``@Shortcut`` default — *before* reading the persisted user
    override. So a shortcut bound via the editor to a plain widget slot (the
    common case) was silently dropped on the next session's rebuild. The
    override is now read before that bail; only a slot with neither a default
    nor an override is skipped.
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
        self.ui = self.sb.loaded_ui.example
        self.ui.show()
        QtWidgets.QApplication.processEvents()
        # cmb_options is a real ExampleSlots slot with NO @Shortcut decorator.
        self.method = "cmb_options"
        self.key = f"shortcuts.ExampleSlots.{self.method}"
        # Sandboxed QSettings is process-scoped; clear any leaked override so
        # every run starts from a clean "no binding" baseline.
        if hasattr(self.ui, "settings"):
            self.ui.settings.clear(self.key)
            self.ui.settings.clear(self.key + ".scope")

    def tearDown(self):
        if getattr(self, "ui", None):
            if hasattr(self.ui, "settings"):
                self.ui.settings.clear(self.key)
                self.ui.settings.clear(self.key + ".scope")
            self.ui.close()
        super().tearDown()

    def test_method_ships_undecorated(self):
        # Guard: the regression only exists for a slot with no decorator default.
        entry = next(
            e
            for e in self.sb.get_shortcut_registry(self.ui)
            if e["method"] == self.method
        )
        self.assertFalse(entry["default"], "test slot must ship without a default")

    def test_persisted_override_recreated_on_rebuild(self):
        slots = self.sb.get_slots_instance(self.ui)
        # No decorator default -> nothing bound for it after the initial build.
        self.assertNotIn(self.method, getattr(slots, "_connected_shortcuts", {}))

        # A previous session persisted an application-scoped binding via the editor.
        self.ui.settings.setValue(self.key, "Ctrl+Alt+J")
        self.ui.settings.setValue(self.key + ".scope", "application")

        # The per-session rebuild step must now re-create it from settings
        # (previously it bailed before reading the override).
        self.sb.register_slots_shortcuts(self.ui, slots)

        sc = slots._connected_shortcuts.get(self.method)
        self.assertIsNotNone(
            sc, "undecorated slot's persisted shortcut was not re-created"
        )
        self.assertEqual(sc.key().toString(), "Ctrl+Alt+J")
        self.assertEqual(sc.context(), QtCore.Qt.ApplicationShortcut)

    def test_unbound_undecorated_slot_still_skipped(self):
        # No default AND no override -> nothing to bind (must not create a
        # shortcut for every plain method just because the bail moved).
        slots = self.sb.get_slots_instance(self.ui)
        self.sb.register_slots_shortcuts(self.ui, slots)
        self.assertNotIn(self.method, getattr(slots, "_connected_shortcuts", {}))


class TestDeferredAppScopedSlotShortcuts(QtBaseTestCase):
    """Cold-start standins for application-scoped slot shortcuts.

    An app-scoped shortcut bound to a slot is normally created by
    ``register_slots_shortcuts`` when its UI builds — but tool UIs are lazy, so
    on a fresh session (before the tool is opened) the binding had no live
    shortcut and the shortcut was dead though the editor still listed it. The
    switchboard now scans persisted app-scoped overrides at the first
    ``on_ui_loaded`` and owns a host-window standin per binding that
    builds-then-invokes on press, disposed the moment the real UI builds.
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
        self.ui = self.sb.loaded_ui.example
        self.ui.show()
        QtWidgets.QApplication.processEvents()

    def tearDown(self):
        if getattr(self, "ui", None):
            self.ui.close()
        super().tearDown()

    def test_ui_names_with_shortcut_overrides_parses_keys(self):
        keys = [
            "paneA/shortcuts.FooSlots.do_x",
            "paneA/shortcuts.FooSlots.do_x.scope",
            "paneB/some_widget/clicked",  # a state key, not a shortcut
        ]
        for k in keys:
            self.sb.settings.setValue(k, "x")
        try:
            names = self.sb._ui_names_with_shortcut_overrides()
            self.assertIn("paneA", names)
            self.assertNotIn("paneB", names)
        finally:
            for k in keys:
                self.sb.settings.clear(k)

    def test_ui_names_strip_host_suffix_from_branch(self):
        # Cold-start Maya: an app-scoped override persisted under the
        # host-namespaced branch ('mirror_maya', via _host_namespaced_branch)
        # must surface as the REAL UI name ('mirror') so downstream
        # get_static_shortcut_registry / loaded_ui.peek can resolve its slots.
        # Passing the raw branch name resolves no slot class -> dead shortcut.
        original = self.sb.context_tags
        self.sb.context_tags = {"maya"}
        self.assertEqual(self.sb._host_suffix(), "_maya")  # guard the premise
        keys = [
            "mirror_maya/shortcuts_maya.MirrorSlots.do_mirror",
            "mirror_maya/shortcuts_maya.MirrorSlots.do_mirror.scope",
            # migrated-user plain twin under the un-suffixed branch: must
            # dedupe to the same 'mirror', not add a separate entry.
            "mirror/shortcuts_maya.MirrorSlots.do_mirror",
            # another host's overrides must be ignored by a Maya scan.
            "other_blender/shortcuts_blender.OtherSlots.act",
        ]
        for k in keys:
            self.sb.settings.setValue(k, "x")
        try:
            names = self.sb._ui_names_with_shortcut_overrides()
            self.assertIn("mirror", names)  # suffix stripped -> real UI name
            self.assertNotIn("mirror_maya", names)  # NOT the raw branch
            self.assertNotIn("other_blender", names)  # other host ignored
        finally:
            for k in keys:
                self.sb.settings.clear(k)
            self.sb.context_tags = original

    def test_scan_creates_standin_only_for_app_scoped_unbound_unbuilt(self):
        from unittest import mock

        self.sb._deferred_slots_scanned = False
        self.sb._deferred_slot_shortcuts.clear()
        entries = [
            {"method": "act_app", "current": "Ctrl+Alt+0", "current_scope": "application"},
            {"method": "act_win", "current": "Ctrl+Alt+1", "current_scope": "window"},
            {"method": "act_empty", "current": "", "current_scope": "application"},
        ]
        with mock.patch.object(
            self.sb, "_ui_names_with_shortcut_overrides", return_value={"ghost_ui"}
        ), mock.patch.object(
            self.sb, "get_static_shortcut_registry", return_value=entries
        ):
            self.sb._bind_deferred_slot_shortcuts()

        keys = set(self.sb._deferred_slot_shortcuts)
        self.assertIn(("ghost_ui", "act_app"), keys)  # app-scoped -> standin
        self.assertNotIn(("ghost_ui", "act_win"), keys)  # window-scoped -> none
        self.assertNotIn(("ghost_ui", "act_empty"), keys)  # unbound -> none
        # cleanup the live standin we created
        self.sb._dispose_deferred_slot_shortcuts("ghost_ui")

    def test_scan_skips_already_built_ui(self):
        from unittest import mock

        self.sb._deferred_slots_scanned = False
        self.sb._deferred_slot_shortcuts.clear()
        # 'example' IS loaded (setUp), so it must be skipped — its real
        # shortcuts own the keys; a standin would be ambiguous.
        with mock.patch.object(
            self.sb, "_ui_names_with_shortcut_overrides", return_value={"example"}
        ), mock.patch.object(
            self.sb, "get_static_shortcut_registry"
        ) as static:
            self.sb._bind_deferred_slot_shortcuts()
        static.assert_not_called()
        self.assertEqual(self.sb._deferred_slot_shortcuts, {})

    def test_register_slots_shortcuts_disposes_standins_for_built_ui(self):
        from uitk.managers.shortcut_manager import GlobalShortcut

        host = self.track_widget(QtWidgets.QWidget())
        host.show()
        QtWidgets.QApplication.processEvents()
        gs = GlobalShortcut(
            QtGui.QKeySequence("Ctrl+Alt+9"),
            host,
            context=QtCore.Qt.ApplicationShortcut,
        )
        self.sb._deferred_slot_shortcuts[("example", "cmb_options")] = gs

        # Building/registering the example UI must dispose its standin.
        slots = self.sb.get_slots_instance(self.ui)
        self.sb.register_slots_shortcuts(self.ui, slots)

        self.assertNotIn(("example", "cmb_options"), self.sb._deferred_slot_shortcuts)
        self.assertNotIn(gs, GlobalShortcut._instances)  # truly disposed

    def test_deferred_callback_builds_and_invokes_with_widget_injection(self):
        from unittest import mock

        fired = []

        class _Inst:
            def act(self, widget=None):
                fired.append(widget)

        cb = self.sb._make_deferred_slot_callback("ghost_ui", "act")
        with mock.patch.object(
            self.sb, "get_ui", return_value=object()
        ), mock.patch.object(self.sb, "get_slots_instance", return_value=_Inst()):
            cb()
        self.assertEqual(fired, [None])  # widget injected as None on a bare trigger


class TestShortcutEditor(QtBaseTestCase):
    """Test the ShortcutEditor UI with real Switchboard."""

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

    def tearDown(self):
        if hasattr(self, "editor") and self.editor:
            self.editor.close()
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_combobox_populates_from_registry(self):
        """ComboBox should list UIs from the registry."""
        count = self.editor.cmb_ui.count()
        self.assertGreater(count, 0, "No UIs found in combobox")

    def test_table_populates_for_loaded_ui(self):
        """Table should show shortcuts for a loaded UI."""
        # Find and select Example in combo
        for i in range(self.editor.cmb_ui.count()):
            if "example" in self.editor.cmb_ui.itemText(i).lower():
                self.editor.cmb_ui.setCurrentIndex(i)
                break

        self.editor.populate()

        # Should have rows if there are connected slots
        registry = self.sb.get_shortcut_registry(self.ui)
        expected_rows = len(registry)
        actual_rows = self.editor.table.rowCount()

        # Either matches registry count or shows "no shortcuts" message
        self.assertTrue(
            actual_rows == expected_rows or actual_rows == 1,
            f"Expected {expected_rows} rows, got {actual_rows}",
        )


class TestShortcutScope(QtBaseTestCase):
    """Test scope persistence and live-rebind behaviour."""

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

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_registry_includes_scope_fields(self):
        """Each registry entry should expose current_scope and default_scope."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")
        for entry in registry:
            self.assertIn("current_scope", entry)
            self.assertIn("default_scope", entry)
            self.assertIn(
                entry["current_scope"],
                {"widget", "widget_children", "window", "application"},
            )

    def test_set_user_shortcut_persists_scope(self):
        """set_user_shortcut(..., scope=...) should write the scope settings key."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")

        slot_name = registry[0]["method"]
        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+T", "application")

        cls_name = self.sb.get_slots_instance(self.ui).__class__.__name__
        scope_key = f"shortcuts.{cls_name}.{slot_name}.scope"
        self.assertEqual(self.ui.settings.value(scope_key), "application")

    def test_set_user_shortcut_live_updates_context(self):
        """set_user_shortcut should update the live QShortcut's context."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")

        slot_name = registry[0]["method"]
        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+T", "application")

        slots = self.sb.get_slots_instance(self.ui)
        sc = slots._connected_shortcuts.get(slot_name)
        self.assertIsNotNone(sc)
        self.assertEqual(sc.context(), QtCore.Qt.ApplicationShortcut)

    def test_registry_reflects_scope_override(self):
        """Registry's current_scope should reflect a persisted override."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")

        slot_name = registry[0]["method"]
        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+T", "application")

        new_registry = self.sb.get_shortcut_registry(self.ui)
        entry = next(r for r in new_registry if r["method"] == slot_name)
        self.assertEqual(entry["current_scope"], "application")

    def test_omitting_scope_preserves_existing_override(self):
        """Calling set_user_shortcut without scope should not clobber a saved override."""
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")

        slot_name = registry[0]["method"]
        # First set scope=application
        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+T", "application")
        # Then update only the sequence
        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+Y")

        cls_name = self.sb.get_slots_instance(self.ui).__class__.__name__
        scope_key = f"shortcuts.{cls_name}.{slot_name}.scope"
        self.assertEqual(self.ui.settings.value(scope_key), "application")

        slots = self.sb.get_slots_instance(self.ui)
        sc = slots._connected_shortcuts.get(slot_name)
        self.assertEqual(sc.context(), QtCore.Qt.ApplicationShortcut)


class TestResolveApplicationHost(QtBaseTestCase):
    """Unit tests for resolve_application_host.

    Application-scoped shortcuts must be owned by an always-visible window;
    Qt disables a shortcut whose owner widget is hidden, regardless of scope.
    """

    def test_prefers_named_dcc_host(self):
        from uitk.managers.shortcut_manager import resolve_application_host

        maya = self.track_widget(QtWidgets.QWidget())
        maya.setObjectName("MayaWindow")
        maya.show()
        QtWidgets.QApplication.processEvents()

        hidden = self.track_widget(QtWidgets.QWidget())  # parentless, never shown
        host = resolve_application_host(hidden)
        self.assertIs(host, maya)
        self.assertTrue(host.isVisible())

    def test_falls_back_to_any_visible_top_level(self):
        from uitk.managers.shortcut_manager import resolve_application_host

        visible = self.track_widget(QtWidgets.QWidget())
        visible.setObjectName("SomeStandaloneMainWindow")
        visible.show()
        QtWidgets.QApplication.processEvents()

        hidden = self.track_widget(QtWidgets.QWidget())
        host = resolve_application_host(hidden)
        self.assertTrue(host.isVisible(), "resolved host must be visible")
        self.assertIsNot(host, hidden)

    def test_never_returns_none(self):
        from uitk.managers.shortcut_manager import resolve_application_host

        w = self.track_widget(QtWidgets.QWidget())
        self.assertIsNotNone(resolve_application_host(w))


class TestApplicationScopeOwner(QtBaseTestCase):
    """Regression: 'shortcut editor application scope does nothing'.

    An application-scoped shortcut must be owned by a *visible* host window,
    not the slot UI — which is hidden whenever the tool isn't open, exactly
    when application scope is meant to fire. A QShortcut whose owner widget is
    hidden is inert even at Qt.ApplicationShortcut scope.
    """

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
        self.ui = self.sb.loaded_ui.example  # built but not shown (hidden)
        QtWidgets.QApplication.processEvents()

    def tearDown(self):
        if getattr(self, "ui", None):
            self.ui.close()
        super().tearDown()

    def _first_slot(self):
        registry = self.sb.get_shortcut_registry(self.ui)
        if not registry:
            self.skipTest("No slots available in example")
        return registry[0]["method"]

    def test_application_scope_owner_is_visible_when_ui_hidden(self):
        slot_name = self._first_slot()
        self.ui.hide()
        host = self.track_widget(QtWidgets.QWidget())
        host.setObjectName("MayaWindow")
        host.show()
        QtWidgets.QApplication.processEvents()

        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+G", "application")

        slots = self.sb.get_slots_instance(self.ui)
        sc = slots._connected_shortcuts.get(slot_name)
        self.assertIsNotNone(sc)
        self.assertEqual(sc.context(), QtCore.Qt.ApplicationShortcut)
        owner = sc.parent()
        self.assertIsNotNone(owner)
        self.assertTrue(
            owner.isVisible(), "application-scope shortcut owner must be visible"
        )
        self.assertIsNot(owner, self.ui, "must not be owned by the hidden slot UI")
        self.assertIs(owner, host)

    def test_window_scope_owner_is_the_ui(self):
        slot_name = self._first_slot()
        self.ui.show()
        QtWidgets.QApplication.processEvents()

        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+H", "window")

        slots = self.sb.get_slots_instance(self.ui)
        sc = slots._connected_shortcuts.get(slot_name)
        self.assertEqual(sc.context(), QtCore.Qt.WindowShortcut)
        self.assertIs(sc.parent(), self.ui)

    def test_toggle_window_to_application_reowns_to_visible_host(self):
        slot_name = self._first_slot()
        self.ui.show()
        QtWidgets.QApplication.processEvents()

        # Start window-scoped: owned by the slot UI.
        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+J", "window")
        slots = self.sb.get_slots_instance(self.ui)
        self.assertIs(slots._connected_shortcuts[slot_name].parent(), self.ui)

        # Hide the UI and flip to application scope: must be re-owned by a
        # visible host so the binding survives the UI being closed.
        self.ui.hide()
        host = self.track_widget(QtWidgets.QWidget())
        host.setObjectName("MayaWindow")
        host.show()
        QtWidgets.QApplication.processEvents()

        self.sb.set_user_shortcut(self.ui, slot_name, "Ctrl+Alt+J", "application")
        sc = slots._connected_shortcuts[slot_name]
        self.assertEqual(sc.context(), QtCore.Qt.ApplicationShortcut)
        self.assertIs(sc.parent(), host)
        self.assertTrue(sc.parent().isVisible())


class TestGlobalShortcutDispose(QtBaseTestCase):
    """`GlobalShortcut.dispose()` must drop the static `_instances` ref.

    `__init__` registers each instance in the class-level `_instances` set;
    that strong ref kept disposed wrappers alive forever (`deleteLater` can't
    collect a still-referenced object), a slow leak across rebinds. `dispose`
    (and the ShortcutManager paths that call it) must clear the ref.
    """

    def test_dispose_removes_from_instances(self):
        from uitk.managers.shortcut_manager import GlobalShortcut

        host = self.track_widget(QtWidgets.QWidget())
        host.show()
        sc = GlobalShortcut("Ctrl+Alt+Shift+F10", host)
        self.assertIn(sc, GlobalShortcut._instances)
        sc.dispose()
        self.assertNotIn(sc, GlobalShortcut._instances)

    def test_manager_remove_and_clear_dispose_global(self):
        from uitk.managers.shortcut_manager import ShortcutManager, GlobalShortcut

        host = self.track_widget(QtWidgets.QWidget())
        host.show()
        mgr = ShortcutManager(host)

        gs = mgr.add_global_shortcut("Ctrl+Alt+Shift+F11")
        self.assertIn(gs, GlobalShortcut._instances)
        mgr.remove_shortcut("Ctrl+Alt+Shift+F11")
        self.assertNotIn(gs, GlobalShortcut._instances)

        gs2 = mgr.add_global_shortcut("Ctrl+Alt+Shift+F12")
        self.assertIn(gs2, GlobalShortcut._instances)
        mgr.clear_all()
        self.assertNotIn(gs2, GlobalShortcut._instances)

    def test_remove_shortcut_notifies_change_subscribers(self):
        """remove_shortcut must fire on_change (like add/rebind) so downstream
        caches (e.g. the sequencer's _shortcut_sequences) drop the removed key.

        Regression: a destroyed transport removed its Space/Alt+Space bindings
        but the sequencer never re-synced, leaving those keys swallowed-but-dead.
        """
        from uitk.managers.shortcut_manager import ShortcutManager

        host = self.track_widget(QtWidgets.QWidget())
        mgr = ShortcutManager(host)
        calls = []
        mgr.on_change(lambda: calls.append(True))

        mgr.add_shortcut("Space", lambda: None)
        self.assertEqual(len(calls), 1)  # add notified

        self.assertTrue(mgr.remove_shortcut("Space"))
        self.assertEqual(len(calls), 2)  # remove notified too

        # A no-op removal (key absent) must not notify.
        self.assertFalse(mgr.remove_shortcut("Space"))
        self.assertEqual(len(calls), 2)


class TestShortcutManagerOverwriteDispose(QtBaseTestCase):
    """Re-adding a binding on an already-registered key must dispose the old
    shortcut, not orphan it.

    Regression: ``add_shortcut`` / ``add_global_shortcut`` overwrote the
    ``self.shortcuts[key]`` entry without tearing down the previous shortcut.
    The old QShortcut stayed enabled + parented to the widget, so Qt logged an
    ambiguous-overload and fired NEITHER handler, and the orphaned object was
    unreachable from ``self.shortcuts`` (never cleared -> leak).
    """

    def test_add_shortcut_overwrite_disposes_previous(self):
        from uitk.managers.shortcut_manager import ShortcutManager

        host = self.track_widget(QtWidgets.QWidget())
        mgr = ShortcutManager(host)

        first = mgr.add_shortcut("Ctrl+G", lambda: None)
        second = mgr.add_shortcut("Ctrl+G", lambda: None)

        self.assertIsNot(first, second)
        # Old shortcut was disabled by _dispose (inert immediately) ...
        self.assertFalse(first.isEnabled())
        # ... and the registry now points only at the replacement.
        self.assertIs(mgr.shortcuts["Ctrl+G"]["shortcut"], second)

    def test_add_global_shortcut_overwrite_disposes_previous(self):
        from uitk.managers.shortcut_manager import ShortcutManager, GlobalShortcut

        host = self.track_widget(QtWidgets.QWidget())
        host.show()
        mgr = ShortcutManager(host)

        first = mgr.add_global_shortcut("Ctrl+Alt+Shift+F9")
        self.assertIn(first, GlobalShortcut._instances)

        second = mgr.add_global_shortcut("Ctrl+Alt+Shift+F9")
        # Overwrite disposes the old GlobalShortcut (drops the static _instances
        # ref + event filter) and keeps only the replacement registered.
        self.assertNotIn(first, GlobalShortcut._instances)
        self.assertIn(second, GlobalShortcut._instances)
        self.assertIs(mgr.shortcuts["Ctrl+Alt+Shift+F9"]["shortcut"], second)


class TestShortcutManagerRegistry(QtBaseTestCase):
    """``ShortcutManager.get_registry`` emits the shared editor entry shape so
    the one unified ShortcutEditor can render a manager's bindings."""

    def _mgr(self):
        from uitk.managers.shortcut_manager import ShortcutManager

        host = self.track_widget(QtWidgets.QWidget())
        return ShortcutManager(host)

    def test_registry_entry_shape(self):
        mgr = self._mgr()
        mgr.add_shortcut("Ctrl+G", lambda: None, "Do G")
        entry = {e["method"]: e for e in mgr.get_registry()}["Ctrl+G"]
        # Same keys the editor's _build_row consumes.
        for field in (
            "method", "name", "current", "default",
            "current_scope", "default_scope", "doc", "hidden", "editable",
        ):
            self.assertIn(field, entry)
        self.assertEqual(entry["name"], "Do G")
        self.assertEqual(entry["current"], "Ctrl+G")
        self.assertTrue(entry["editable"])
        self.assertFalse(entry["hidden"])

    def test_info_entry_is_non_editable(self):
        mgr = self._mgr()
        mgr.add_info_entry("Ctrl+Shift+LMB", "Switch to shot at cursor")
        entry = {e["method"]: e for e in mgr.get_registry()}["Ctrl+Shift+LMB"]
        self.assertFalse(entry["editable"])  # read_only -> locked
        self.assertEqual(entry["name"], "Switch to shot at cursor")

    def test_hidden_flag_propagates(self):
        mgr = self._mgr()
        mgr.add_shortcut("Ctrl+H", lambda: None, "Hidden one", hidden=True)
        entry = {e["method"]: e for e in mgr.get_registry()}["Ctrl+H"]
        self.assertTrue(entry["hidden"])

    def test_scope_reflects_context(self):
        mgr = self._mgr()
        mgr.add_shortcut(
            "Ctrl+W", lambda: None, "Win", QtCore.Qt.WindowShortcut
        )
        entry = {e["method"]: e for e in mgr.get_registry()}["Ctrl+W"]
        self.assertEqual(entry["current_scope"], "window")


class TestShortcutManagerEditorIntegration(QtBaseTestCase):
    """``ShortcutManager.show_editor`` opens the ONE unified ShortcutEditor (via
    ManagerSwitchboardFacade), not a bespoke dialog — the DRY merge."""

    def _editor_for(self, *binds, infos=()):
        from uitk.managers.shortcut_manager import ShortcutManager

        host = self.track_widget(QtWidgets.QWidget())
        mgr = ShortcutManager(host)
        for b in binds:
            mgr.add_shortcut(*b)
        for label, desc in infos:
            mgr.add_info_entry(label, desc)
        mgr.show_editor(title="Sequencer Shortcuts")
        ed = mgr._editor
        self.track_widget(ed)
        ed._set_show_hidden(False)  # deterministic regardless of persisted pref
        return mgr, ed

    def _rows(self, ed):
        return [
            ed.table.item(r, 0).text()
            for r in range(ed.table.rowCount())
            if ed.table.item(r, 0) and ed.table.columnSpan(r, 0) == 1
        ]

    def test_opens_unified_editor_in_manager_mode(self):
        from uitk.widgets.editors.shortcut_editor.registry_editor import ShortcutEditor

        _mgr, ed = self._editor_for(("Ctrl+G", lambda: None, "Do G"))
        self.assertIsInstance(ed, ShortcutEditor)
        self.assertTrue(ed._manager_mode)
        # Manager mode has no preset row and no Assigned/Commands pseudo-views.
        self.assertIsNone(getattr(ed, "_preset_mgr", None))
        self.assertEqual(
            [ed.cmb_ui.itemText(i) for i in range(ed.cmb_ui.count())],
            ["Sequencer Shortcuts"],
        )
        self.assertIn("Do G", self._rows(ed))

    def test_hidden_binding_obeys_show_hidden_toggle(self):
        _mgr, ed = self._editor_for(
            ("Ctrl+G", lambda: None, "Visible"),
            ("Ctrl+H", lambda: None, "Hidden", QtCore.Qt.WidgetShortcut, True),
        )
        self.assertNotIn("Hidden", self._rows(ed))
        ed._set_show_hidden(True)
        self.assertIn("Hidden", self._rows(ed))

    def test_rebind_routes_through_manager(self):
        mgr, ed = self._editor_for(("Ctrl+G", lambda: None, "Do G"))
        ed._apply_shortcut(0, "Ctrl+J")
        self.assertIn("Ctrl+J", mgr.shortcuts)
        self.assertNotIn("Ctrl+G", mgr.shortcuts)

    def test_clearing_is_not_destructive(self):
        # A manager binding has no "listed but unbound" state, so clearing must
        # not delete it (and its action) outright — empty input is ignored.
        mgr, ed = self._editor_for(("Ctrl+G", lambda: None, "Do G"))
        ed._apply_shortcut(0, "")
        self.assertIn("Ctrl+G", mgr.shortcuts)

    def test_reset_column_precedes_description(self):
        _mgr, ed = self._editor_for(("Ctrl+G", lambda: None, "Do G"))
        headers = [
            ed.table.horizontalHeaderItem(c).text()
            for c in range(ed.table.columnCount())
        ]
        # Scope + Reset are icon-only columns with blank headers; the assertion
        # of interest is the order — Reset precedes Description (a prior regression
        # swapped them).
        self.assertEqual(
            headers, ["Action", "Shortcut", "", "", "Description", "UI"]
        )
        self.assertLess(ed.COL_RESET, ed.COL_DESCRIPTION)

    def test_manager_view_hides_description_column(self):
        _mgr, ed = self._editor_for(("Ctrl+G", lambda: None, "Do G"))
        self.assertTrue(ed.table.isColumnHidden(ed.COL_DESCRIPTION))

    def test_manager_view_hides_scope_column(self):
        # A manager binding's scope is fixed by its owner widget (not per-row
        # editable), so the focused view hides the Scope column entirely rather
        # than showing inert toggles.
        _mgr, ed = self._editor_for(("Ctrl+G", lambda: None, "Do G"))
        self.assertTrue(ed.table.isColumnHidden(ed.COL_SCOPE))

    def test_set_columns_hidden_api_round_trips(self):
        # Use a column visible by default in manager mode (Scope is hidden there)
        # so the hide→show round-trip exercises both directions meaningfully.
        _mgr, ed = self._editor_for(("Ctrl+G", lambda: None, "Do G"))
        self.assertFalse(ed.table.isColumnHidden(ed.COL_SHORTCUT))
        ed.set_columns_hidden(ed.COL_SHORTCUT)
        self.assertTrue(ed.table.isColumnHidden(ed.COL_SHORTCUT))
        ed.set_columns_hidden(ed.COL_SHORTCUT, hidden=False)
        self.assertFalse(ed.table.isColumnHidden(ed.COL_SHORTCUT))

    def test_manager_header_menu_has_view_section_only(self):
        from uitk.widgets.separator import Separator

        _mgr, ed = self._editor_for(("Ctrl+G", lambda: None, "Do G"))
        titles = [
            s.title for s in ed.header.menu.findChildren(Separator) if s.title
        ]
        self.assertEqual(titles, ["View"])  # no Presets section in manager mode
        self.assertEqual(
            ed._show_hidden_checkbox.maximumHeight(), ed.HEADER_WIDGET_HEIGHT
        )

    def test_show_hidden_lives_in_header_menu(self):
        _mgr, ed = self._editor_for(("Ctrl+G", lambda: None, "Do G"))
        # The checkbox exists and drives _set_show_hidden (not on the filter row).
        self.assertTrue(hasattr(ed, "_show_hidden_checkbox"))
        ed._show_hidden_checkbox.setChecked(True)
        self.assertTrue(ed._show_hidden)
        ed._show_hidden_checkbox.setChecked(False)
        self.assertFalse(ed._show_hidden)

    def test_description_not_duplicated_into_doc_column(self):
        _mgr, ed = self._editor_for(("Ctrl+G", lambda: None, "Do G"))
        for r in range(ed.table.rowCount()):
            it = ed.table.item(r, 0)
            if it and it.text() == "Do G":
                desc = ed.table.item(r, ed.COL_DESCRIPTION)
                self.assertEqual(desc.text(), "")  # Description col is empty
                break
        else:
            self.fail("row not found")

    def test_info_entry_locked_normal_binding_rebindable_scope_fixed(self):
        _mgr, ed = self._editor_for(
            ("Ctrl+G", lambda: None, "Do G"),
            infos=(("Ctrl+Shift+LMB", "Switch to shot"),),
        )
        by_name = {}
        for r in range(ed.table.rowCount()):
            it = ed.table.item(r, 0)
            if it and ed.table.columnSpan(r, 0) == 1:
                by_name[it.text()] = r
        # Info row: not rebindable, scope locked.
        ir = by_name["Switch to shot"]
        self.assertFalse(
            bool(ed.table.item(ir, 1).flags() & QtCore.Qt.ItemIsEditable)
        )
        self.assertFalse(ed.scope_interactive(ir))
        # Normal row: rebindable, but scope is owner-fixed (locked).
        nr = by_name["Do G"]
        self.assertTrue(
            bool(ed.table.item(nr, 1).flags() & QtCore.Qt.ItemIsEditable)
        )
        self.assertFalse(ed.scope_interactive(nr))


class TestRegistryFacadeEditor(QtBaseTestCase):
    """``RegistrySwitchboardFacade`` renders any grouped binding store in the
    ONE unified ShortcutEditor — groups become the target combobox, edits and
    clears route to the provider, and an opt-in preset row fronts the
    provider's own store (the Macro Manager pattern)."""

    def setUp(self):
        super().setUp()
        import uuid

        self._ns = f"test_registry_facade_{uuid.uuid4().hex[:8]}"
        # Provider state: {group: {method: (label, sequence)}} + applied calls.
        self.store = {
            "Display": {"m_grid": ["Grid", "Ctrl+G"]},
            "Edit": {"m_group": ["Group", ""]},
        }
        self.applied = []

    def _entries(self, group):
        return [
            {
                "method": method,
                "name": label,
                "doc": f"{label} doc",
                "current": seq,
                "default": "",
                "current_scope": "application",
                "default_scope": "application",
                "scope_editable": False,
            }
            for method, (label, seq) in self.store.get(group, {}).items()
        ]

    def _apply(self, group, method, sequence, _scope=None):
        self.applied.append((group, method, sequence))
        if method in self.store.get(group, {}):
            self.store[group][method][1] = sequence

    def _facade(self, **kwargs):
        from uitk.widgets.editors.shortcut_editor import RegistrySwitchboardFacade

        kwargs.setdefault("groups", lambda: sorted(self.store))
        kwargs.setdefault("get_entries", self._entries)
        kwargs.setdefault("apply_binding", self._apply)
        kwargs.setdefault("settings_namespace", self._ns)
        return RegistrySwitchboardFacade(**kwargs)

    def _editor(self, facade):
        ed = ShortcutEditor(facade)
        self.track_widget(ed)
        ed._set_show_hidden(False)
        return ed

    def _rows(self, ed):
        return [
            ed.table.item(r, 0).text()
            for r in range(ed.table.rowCount())
            if ed.table.item(r, 0) and ed.table.columnSpan(r, 0) == 1
        ]

    def test_groups_become_target_combo(self):
        ed = self._editor(self._facade())
        self.assertTrue(ed._manager_mode)
        self.assertEqual(
            [ed.cmb_ui.itemText(i) for i in range(ed.cmb_ui.count())],
            ["Display", "Edit"],  # no Assigned/Commands pseudo-views
        )
        self.assertEqual(self._rows(ed), ["Grid"])  # first group's rows
        ed.cmb_ui.setCurrentIndex(1)
        self.assertEqual(self._rows(ed), ["Group"])

    def test_show_all_flattens_groups_and_relabels_ui_column(self):
        ed = self._editor(
            self._facade(
                editor_title="Macro Manager",
                ui_column_label="Category",
                default_show_all=True,
            )
        )
        # Fresh settings namespace → the facade's show-all default applies.
        self.assertTrue(ed._show_all)
        self.assertEqual(sorted(self._rows(ed)), ["Grid", "Group"])
        self.assertFalse(ed.table.isColumnHidden(ed.COL_UI))
        self.assertEqual(
            ed.table.horizontalHeaderItem(ed.COL_UI).text(), "Category"
        )
        # The group name renders in the (re-labeled) UI column.
        col_ui = [
            ed.table.item(r, ed.COL_UI).text()
            for r in range(ed.table.rowCount())
        ]
        self.assertEqual(sorted(col_ui), ["Display", "Edit"])
        # The header label elides at narrow widths; the OS window title
        # carries the full facade branding.
        self.assertEqual(ed.windowTitle(), "Macro Manager")

    def test_edit_and_clear_route_to_provider_with_group(self):
        ed = self._editor(self._facade(default_show_all=True))
        rows = {
            ed.table.item(r, 0).text(): r for r in range(ed.table.rowCount())
        }
        ed._apply_shortcut(rows["Group"], "Ctrl+J")  # assign
        self.assertIn(("Edit", "m_group", "Ctrl+J"), self.applied)
        rows = {
            ed.table.item(r, 0).text(): r for r in range(ed.table.rowCount())
        }
        ed._apply_shortcut(rows["Grid"], "")  # clear passes through verbatim
        self.assertIn(("Display", "m_grid", ""), self.applied)

    def test_group_names_with_dots_are_not_truncated(self):
        """Facade group names pass through verbatim. Regression: the editor's
        UI-name gather stripped everything after the last '.' (filename-
        extension logic), truncating a dotted group — e.g. Maya's hierarchical
        runTimeCommand categories ("Custom Scripts.Foo") — into an empty view.
        """
        self.store["Custom Scripts.Foo"] = {"m_dot": ["Dotty", ""]}
        ed = self._editor(self._facade())
        combo = [ed.cmb_ui.itemText(i) for i in range(ed.cmb_ui.count())]
        self.assertIn("Custom Scripts.Foo", combo)
        ed.cmb_ui.setCurrentIndex(combo.index("Custom Scripts.Foo"))
        self.assertEqual(self._rows(ed), ["Dotty"])

    def test_builtin_collision_checker_spans_groups(self):
        # Two application-scoped bindings on the same key collide across
        # groups — the facade's synthetic UIs must not hide that.
        ed = self._editor(self._facade())
        conflicts = ed._builtin_internal_collision_checker(
            "Ctrl+G", "application", "Edit", "m_group"
        )
        self.assertEqual(len(conflicts), 1)
        self.assertIn("m_grid", conflicts[0].description)

    def test_preset_config_builds_row_over_provider_store(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            old_root = os.environ.get("UITK_PRESETS_ROOT")
            os.environ["UITK_PRESETS_ROOT"] = tmp
            try:
                exported, imported = [], []

                def provider():
                    exported.append(True)
                    return {"m_grid": {"key": "ctl+g"}}

                def applier(data):
                    imported.append(data)
                    return len(data)

                ed = self._editor(
                    self._facade(
                        preset_config={
                            "dir_name": "macro_manager",
                            "package": "testpkg",
                            "value_provider": provider,
                            "value_applier": applier,
                        }
                    )
                )
                # Facade mode + preset_config → the preset row exists and
                # fronts the provider's store (not export_shortcuts).
                self.assertIsNotNone(ed._preset_mgr)
                self.assertIn(
                    os.path.join("testpkg", "macro_manager"),
                    str(ed.preset_dir),
                )
                ed.save_preset("unit")
                self.assertTrue(exported)
                self.assertTrue(ed.load_preset("unit"))
                self.assertEqual(imported[-1], {"m_grid": {"key": "ctl+g"}})
            finally:
                if old_root is None:
                    os.environ.pop("UITK_PRESETS_ROOT", None)
                else:
                    os.environ["UITK_PRESETS_ROOT"] = old_root


class TestStaticShortcutRegistry(QtBaseTestCase):
    """``get_static_shortcut_registry`` lists a UI's slots WITHOUT building it,
    matching the live registry's methods/defaults and reading the same
    persisted overrides."""

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

    def tearDown(self):
        if getattr(self, "ui", None):
            self.ui.close()
        super().tearDown()

    def test_static_matches_live_methods_and_defaults(self):
        live = {e["method"]: e for e in self.sb.get_shortcut_registry(self.ui)}
        static = {
            e["method"]: e for e in self.sb.get_static_shortcut_registry("example")
        }
        if not live:
            self.skipTest("example UI exposes no shortcut slots")

        # Static may legitimately miss slots bound to widgets created in code
        # (the documented fidelity caveat), so it must be a subset — never
        # inventing slots the live tree doesn't have.
        self.assertTrue(
            set(static) <= set(live),
            f"static listed slots absent from live: {set(static) - set(live)}",
        )
        # @shortcut-decorated methods come from the class, so they must always
        # appear statically.
        decorated = {m for m, e in live.items() if e["default"]}
        self.assertTrue(
            decorated <= set(static),
            f"static dropped decorated slots: {decorated - set(static)}",
        )
        for method in static:
            for field in ("class", "name", "default", "default_scope", "doc"):
                self.assertEqual(
                    static[method][field],
                    live[method][field],
                    f"static/live mismatch for {method!r} field {field!r}",
                )

    def test_static_registry_does_not_instantiate(self):
        from unittest import mock

        # Evict the example UI so a static read can't lean on the loaded copy.
        del self.sb.loaded_ui["example"]
        with mock.patch.object(self.sb, "get_ui", wraps=self.sb.get_ui) as spy:
            static = self.sb.get_static_shortcut_registry("example")
        spy.assert_not_called()
        self.assertIsInstance(static, list)
        self.assertIsNone(
            self.sb.loaded_ui.peek("example"),
            "a static read must not instantiate the UI",
        )

    def test_static_reads_persisted_override(self):
        """An override persisted by the live UI must be read by the static path,
        proving both use the same per-UI QSettings namespace."""
        live = self.sb.get_shortcut_registry(self.ui)
        if not live:
            self.skipTest("example UI exposes no shortcut slots")
        method = live[0]["method"]

        self.sb.set_user_shortcut(self.ui, method, "Ctrl+Alt+7", "application")
        if hasattr(self.ui.settings, "sync"):
            self.ui.settings.sync()

        static = {
            e["method"]: e for e in self.sb.get_static_shortcut_registry("example")
        }
        self.assertEqual(static[method]["current"], "Ctrl+Alt+7")
        self.assertEqual(static[method]["current_scope"], "application")

    def test_unknown_ui_returns_empty(self):
        self.assertEqual(
            self.sb.get_static_shortcut_registry("no_such_ui_xyz"), []
        )


if __name__ == "__main__":
    unittest.main()
