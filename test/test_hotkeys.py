# !/usr/bin/python
# coding=utf-8
"""Unit tests for the Switchboard shortcut system.

Uses the real Switchboard with the examples module to test:
- Shortcut registration via @shortcut decorator
- Registry generation from connected slots
- User shortcut assignment and persistence
- HotkeyEditor UI functionality
"""
import unittest
from qtpy import QtWidgets, QtCore

# Base Test
from conftest import QtBaseTestCase

# Code to Test
from uitk.switchboard import Switchboard
from uitk.widgets.editors.hotkey_editor import HotkeyEditor
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


class TestHotkeyEditor(QtBaseTestCase):
    """Test the HotkeyEditor UI with real Switchboard."""

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
        from uitk.widgets.mixins.shortcuts import resolve_application_host

        maya = self.track_widget(QtWidgets.QWidget())
        maya.setObjectName("MayaWindow")
        maya.show()
        QtWidgets.QApplication.processEvents()

        hidden = self.track_widget(QtWidgets.QWidget())  # parentless, never shown
        host = resolve_application_host(hidden)
        self.assertIs(host, maya)
        self.assertTrue(host.isVisible())

    def test_falls_back_to_any_visible_top_level(self):
        from uitk.widgets.mixins.shortcuts import resolve_application_host

        visible = self.track_widget(QtWidgets.QWidget())
        visible.setObjectName("SomeStandaloneMainWindow")
        visible.show()
        QtWidgets.QApplication.processEvents()

        hidden = self.track_widget(QtWidgets.QWidget())
        host = resolve_application_host(hidden)
        self.assertTrue(host.isVisible(), "resolved host must be visible")
        self.assertIsNot(host, hidden)

    def test_never_returns_none(self):
        from uitk.widgets.mixins.shortcuts import resolve_application_host

        w = self.track_widget(QtWidgets.QWidget())
        self.assertIsNotNone(resolve_application_host(w))


class TestApplicationScopeOwner(QtBaseTestCase):
    """Regression: 'hotkey editor application scope does nothing'.

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
        from uitk.widgets.mixins.shortcuts import GlobalShortcut

        host = self.track_widget(QtWidgets.QWidget())
        host.show()
        sc = GlobalShortcut("Ctrl+Alt+Shift+F10", host)
        self.assertIn(sc, GlobalShortcut._instances)
        sc.dispose()
        self.assertNotIn(sc, GlobalShortcut._instances)

    def test_manager_remove_and_clear_dispose_global(self):
        from uitk.widgets.mixins.shortcuts import ShortcutManager, GlobalShortcut

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


if __name__ == "__main__":
    unittest.main()
