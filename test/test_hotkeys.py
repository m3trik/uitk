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
from uitk.widgets.hotkey_editor import HotkeyEditor
from uitk.widgets.mixins.shortcuts import Shortcut


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
            slot_source=self.example_module.ExampleSlots,
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
            slot_source=self.example_module.ExampleSlots,
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
            slot_source=self.example_module.ExampleSlots,
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


if __name__ == "__main__":
    unittest.main()
