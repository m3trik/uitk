# !/usr/bin/python
# coding=utf-8
import unittest
import os
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

from conftest import QtBaseTestCase
from uitk.switchboard import Switchboard
from uitk.file_manager import FileManager


class TestSwitchboardSources(QtBaseTestCase):
    """Tests for Switchboard source input handling."""

    def setUp(self):
        super().setUp()
        self.mock_app = MagicMock()
        self.mock_app.instance.return_value = self.mock_app

        # Create dummy file structure for testing
        self.test_dir = os.path.join(os.path.dirname(__file__), "temp_source_tests")
        os.makedirs(self.test_dir, exist_ok=True)

        # Create dummy UI file
        with open(os.path.join(self.test_dir, "test.ui"), "w") as f:
            f.write("<?xml version='1.0'?><ui version='4.0'></ui>")

        # Create dummy Python file
        with open(os.path.join(self.test_dir, "test_slots.py"), "w") as f:
            f.write("class TestSlots: pass")

    def tearDown(self):
        import shutil
        import gc

        # Force garbage collection to release file handles
        gc.collect()

        # Retry cleanup
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except OSError:
                # Simple retry logic or ignore if really stuck (OS timing)
                try:
                    import time

                    time.sleep(0.1)
                    shutil.rmtree(self.test_dir)
                except OSError:
                    pass  # We tried our best, temporary files might persist manually cleanup later

        super().tearDown()

    def test_single_string_path(self):
        """Test sources as single string paths."""
        sb = Switchboard(
            ui_source=self.test_dir,
            slot_source=self.test_dir,
            base_dir=None,  # Absolute paths used
        )

        self.assertTrue(len(sb.registry.containers) > 0)
        # Check if UI registry found the test.ui
        ui_files = [f.filename for f in sb.registry.ui_registry]
        self.assertIn("test", ui_files)

        # Check if Slots registry found test_slots.py class
        slot_classes = [c.classname for c in sb.registry.slot_registry]
        self.assertIn("TestSlots", slot_classes)

    def test_list_of_paths(self):
        """Test sources as list of paths."""
        sb = Switchboard(
            ui_source=[self.test_dir, self.test_dir],  # Duplicate just to test list
            base_dir=None,
        )
        self.assertTrue(len(sb.registry.ui_registry) >= 1)

    def test_tuple_of_paths(self):
        """Test sources as tuple of paths."""
        sb = Switchboard(ui_source=(self.test_dir,), base_dir=None)
        # Should contain 'test'
        self.assertEqual(sb.registry.ui_registry[0].filename, "test")

    def test_module_object(self):
        """Test sources as module objects."""
        # Create a dummy module
        mod = ModuleType("dummy_module")
        mod.__file__ = os.path.join(self.test_dir, "__init__.py")
        sys.modules["dummy_module"] = mod

        try:
            sb = Switchboard(ui_source=mod, base_dir=None)
            # Since mod.__file__ points to test_dir, it should scan test_dir
            self.assertEqual(sb.registry.ui_registry[0].filename, "test")
        finally:
            del sys.modules["dummy_module"]

    def test_list_of_mixed_types(self):
        """Test sources as list of mixed types (str and module)."""
        mod = ModuleType("dummy_module")
        mod.__file__ = os.path.join(self.test_dir, "__init__.py")

        sb = Switchboard(ui_source=[self.test_dir, mod], base_dir=None)
        # It should process both. Since they point to same dir, we might get dupes
        # FileContainer logic might handle duplicates if configured,
        # but here we just check it doesn't crash
        self.assertTrue(len(sb.registry.ui_registry) >= 1)

    def test_none_sources(self):
        """Test None for sources."""
        sb = Switchboard(ui_source=None)
        self.assertEqual(len(sb.registry.ui_registry), 0)

    def test_base_dir_resolution(self):
        """Test relative path resolution using base_dir."""
        # Relative path
        rel_path = "temp_source_tests"
        base = os.path.dirname(__file__)

        sb = Switchboard(ui_source=rel_path, base_dir=base)
        self.assertEqual(sb.registry.ui_registry[0].filename, "test")

    def test_modify_registry_post_init(self):
        """Test modifying sources after initialization."""
        sb = Switchboard(ui_source=None)

        # Verify empty
        self.assertEqual(len(sb.registry.ui_registry), 0)

        # Test the register method
        sb.register(ui_location=self.test_dir)

        # Verify updated
        self.assertTrue(
            len(sb.registry.ui_registry) > 0, "UI registry should not be empty"
        )
        self.assertIn("test", [f.filename for f in sb.registry.ui_registry])

    def test_register_icons(self):
        """Test registering icon locations."""
        sb = Switchboard(ui_source=None)

        # Create dummy icon
        with open(os.path.join(self.test_dir, "test_icon.png"), "w") as f:
            f.write("dummy")

        sb.register(icon_location=self.test_dir)

        # Verify
        self.assertTrue(len(sb.registry.icon_registry) > 0)
        filenames = [icon.filename for icon in sb.registry.icon_registry]
        self.assertIn("test_icon", filenames)


if __name__ == "__main__":
    unittest.main()
