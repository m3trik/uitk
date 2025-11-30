# !/usr/bin/python
# coding=utf-8
"""Unit tests for FileManager.

This module tests the FileManager functionality including:
- Container creation and management
- File discovery and filtering
- Duplicate handling
- Path resolution
- Edge cases and error handling

Run standalone: python -m test.test_file_manager
"""

import unittest
from collections import namedtuple
from pathlib import Path

from conftest import BaseTestCase, UITK_DIR, EXAMPLES_DIR, WIDGETS_DIR

from uitk.file_manager import FileManager
from pythontk.core_utils.namedtuple_container import NamedTupleContainer


class TestFileManagerContainerCreation(BaseTestCase):
    """Tests for FileManager container creation."""

    def setUp(self):
        super().setUp()
        self.file_manager = FileManager()

    def test_create_container_with_ui_files(self):
        """Should create a container for .ui files."""
        container = self.file_manager.create(
            "ui_registry",
            str(EXAMPLES_DIR),
            inc_files="*.ui",
        )
        self.assertIsInstance(container, NamedTupleContainer)

    def test_create_container_with_python_files(self):
        """Should create a container for Python files with custom fields."""
        container = self.file_manager.create(
            "widget_files",
            str(WIDGETS_DIR),
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )
        self.assertIsInstance(container, NamedTupleContainer)

    def test_create_container_with_base_dir(self):
        """Should resolve paths using base_dir parameter."""
        container = self.file_manager.create(
            "relative_path_test",
            str(WIDGETS_DIR),
            inc_files="*.py",
            base_dir=0,
        )
        self.assertIsInstance(container, NamedTupleContainer)

    def test_create_container_makes_attribute(self):
        """Created container should be accessible as attribute."""
        self.file_manager.create(
            "test_registry",
            str(EXAMPLES_DIR),
            inc_files="*.ui",
        )
        self.assertTrue(hasattr(self.file_manager, "test_registry"))

    def test_create_multiple_containers(self):
        """Should support creating multiple containers."""
        self.file_manager.create("registry1", str(EXAMPLES_DIR), inc_files="*.ui")
        self.file_manager.create("registry2", str(WIDGETS_DIR), inc_files="*.py")
        self.assertTrue(hasattr(self.file_manager, "registry1"))
        self.assertTrue(hasattr(self.file_manager, "registry2"))


class TestFileManagerContainerExtension(BaseTestCase):
    """Tests for extending FileManager containers."""

    def setUp(self):
        super().setUp()
        self.file_manager = FileManager()

    def test_extend_container(self):
        """Should extend an existing container with additional files."""
        self.file_manager.create(
            "widget_files",
            str(WIDGETS_DIR),
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )
        # Should not raise an exception
        self.file_manager.widget_files.extend(str(WIDGETS_DIR))

    def test_extend_container_with_base_dir(self):
        """Should extend container using base_dir for path resolution."""
        self.file_manager.create(
            "widget_files",
            str(WIDGETS_DIR),
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )
        self.file_manager.widget_files.extend(str(WIDGETS_DIR), base_dir=0)

    def test_extend_disallows_duplicates(self):
        """Should not add duplicate entries when allow_duplicates=False."""
        container = self.file_manager.create(
            "widget_files",
            str(WIDGETS_DIR),
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )
        initial_length = len(container.named_tuples)

        container.extend(str(WIDGETS_DIR), allow_duplicates=False)

        self.assertEqual(len(container.named_tuples), initial_length)

    def test_extend_allows_duplicates_when_enabled(self):
        """Should add duplicate entries when allow_duplicates=True."""
        container = self.file_manager.create(
            "widget_files",
            str(WIDGETS_DIR),
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )
        initial_length = len(container.named_tuples)

        container.extend(str(WIDGETS_DIR), allow_duplicates=True)

        self.assertGreater(len(container.named_tuples), initial_length)


class TestNamedTupleContainerQuery(BaseTestCase):
    """Tests for NamedTupleContainer query functionality."""

    def setUp(self):
        super().setUp()
        File = namedtuple("File", ["filename", "filepath"])
        self.named_tuples = [
            File("file1.txt", "/path1"),
            File("file2.txt", "/path2"),
            File("file3.txt", "/path3"),
        ]
        self.container = NamedTupleContainer(
            named_tuples=self.named_tuples,
            fields=["filename", "filepath"],
        )

    def test_get_returns_matching_field(self):
        """Should return the requested field for matching criteria."""
        result = self.container.get(return_field="filename", filepath="/path1")
        self.assertEqual(result, "file1.txt")

    def test_get_returns_empty_for_no_match(self):
        """Should return empty list when no match is found."""
        result = self.container.get(return_field="filename", filepath="/nonexistent")
        self.assertEqual(result, [])

    def test_get_returns_all_when_no_filter(self):
        """Should return all items when no filter criteria provided."""
        result = self.container.get(return_field="filename")
        self.assertEqual(len(result), 3)

    def test_get_with_multiple_matches(self):
        """Should return first matching item when return_field and conditions specified."""
        File = namedtuple("File", ["filename", "filepath", "extension"])
        tuples = [
            File("file1.txt", "/path1", ".txt"),
            File("file2.txt", "/path2", ".txt"),
            File("file3.py", "/path3", ".py"),
        ]
        container = NamedTupleContainer(
            named_tuples=tuples,
            fields=["filename", "filepath", "extension"],
        )
        # When both conditions and return_field are specified, get() returns first match
        result = container.get(return_field="filename", extension=".txt")
        self.assertEqual(result, "file1.txt")

    def test_get_all_matches_without_return_field(self):
        """Should return all matching tuples when only conditions specified."""
        File = namedtuple("File", ["filename", "filepath", "extension"])
        tuples = [
            File("file1.txt", "/path1", ".txt"),
            File("file2.txt", "/path2", ".txt"),
            File("file3.py", "/path3", ".py"),
        ]
        container = NamedTupleContainer(
            named_tuples=tuples,
            fields=["filename", "filepath", "extension"],
        )
        # When only conditions specified (no return_field), returns all matching tuples
        result = container.get(extension=".txt")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].filename, "file1.txt")
        self.assertEqual(result[1].filename, "file2.txt")


class TestNamedTupleContainerModification(BaseTestCase):
    """Tests for NamedTupleContainer modification functionality."""

    def setUp(self):
        super().setUp()
        File = namedtuple("File", ["filename", "filepath"])
        self.named_tuples = [File("file1.txt", "/path1")]
        self.container = NamedTupleContainer(
            named_tuples=self.named_tuples,
            fields=["filename", "filepath"],
        )

    def test_modify_updates_field_value(self):
        """Should modify a field value in an existing tuple."""
        modified_tuple = self.container.modify(0, filename="new_file.txt")
        self.assertEqual(modified_tuple.filename, "new_file.txt")

    def test_modify_preserves_other_fields(self):
        """Should preserve unmodified fields."""
        modified_tuple = self.container.modify(0, filename="new_file.txt")
        self.assertEqual(modified_tuple.filepath, "/path1")

    def test_modify_multiple_fields(self):
        """Should modify multiple fields at once."""
        modified_tuple = self.container.modify(
            0, filename="new_file.txt", filepath="/new_path"
        )
        self.assertEqual(modified_tuple.filename, "new_file.txt")
        self.assertEqual(modified_tuple.filepath, "/new_path")

    def test_modify_updates_container(self):
        """Should update the tuple in the container."""
        self.container.modify(0, filename="updated.txt")
        self.assertEqual(self.container.named_tuples[0].filename, "updated.txt")


class TestNamedTupleContainerDuplicates(BaseTestCase):
    """Tests for duplicate handling in NamedTupleContainer."""

    def setUp(self):
        super().setUp()
        self.File = namedtuple("File", ["filename", "filepath"])
        self.container = NamedTupleContainer(
            named_tuples=[],
            fields=["filename", "filepath"],
        )

    def test_allows_duplicates_when_enabled(self):
        """Should allow duplicate entries when allow_duplicates=True."""
        existing = [self.File("file1.txt", "/path/to/file1.txt")]
        new = [
            self.File("file1.txt", "/path/to/file1.txt"),
            self.File("file2.txt", "/path/to/file2.txt"),
        ]
        combined = self.container._handle_duplicates(
            existing, new, allow_duplicates=True
        )
        self.assertEqual(len(combined), 3)

    def test_rejects_duplicates_when_disabled(self):
        """Should reject duplicate entries when allow_duplicates=False."""
        existing = [self.File("file1.txt", "/path/to/file1.txt")]
        new = [
            self.File("file1.txt", "/path/to/file1.txt"),
            self.File("file2.txt", "/path/to/file2.txt"),
        ]
        combined = self.container._handle_duplicates(
            existing, new, allow_duplicates=False
        )
        self.assertEqual(len(combined), 2)

    def test_empty_existing_list(self):
        """Should handle empty existing list."""
        existing = []
        new = [self.File("file1.txt", "/path1")]
        combined = self.container._handle_duplicates(
            existing, new, allow_duplicates=False
        )
        self.assertEqual(len(combined), 1)

    def test_empty_new_list(self):
        """Should handle empty new list."""
        existing = [self.File("file1.txt", "/path1")]
        new = []
        combined = self.container._handle_duplicates(
            existing, new, allow_duplicates=False
        )
        self.assertEqual(len(combined), 1)


class TestFileManagerLocationCheck(BaseTestCase):
    """Tests for FileManager location checking."""

    def setUp(self):
        super().setUp()
        self.file_manager = FileManager()
        self.file_manager.create(
            "ui_registry",
            str(EXAMPLES_DIR),
            inc_files="*.ui",
        )

    def test_contains_existing_location(self):
        """Should return True for a location that exists in the container."""
        # Use forward slashes for cross-platform compatibility
        contained_location = str(EXAMPLES_DIR / "example.ui")
        self.assertTrue(
            self.file_manager.contains_location(contained_location, "ui_registry")
        )

    def test_does_not_contain_nonexistent_location(self):
        """Should return False for a location that doesn't exist."""
        not_contained_location = str(EXAMPLES_DIR / "non_existent_file.ui")
        self.assertFalse(
            self.file_manager.contains_location(not_contained_location, "ui_registry")
        )

    def test_contains_location_case_sensitivity(self):
        """Should handle case sensitivity appropriately."""
        # This test verifies the behavior exists, actual result depends on OS
        contained_location = str(EXAMPLES_DIR / "example.ui")
        result = self.file_manager.contains_location(contained_location, "ui_registry")
        self.assertIsInstance(result, bool)


class TestNamedTupleContainerIteration(BaseTestCase):
    """Tests for NamedTupleContainer iteration."""

    def setUp(self):
        super().setUp()
        File = namedtuple("File", ["filename", "filepath"])
        self.named_tuples = [
            File("file1.txt", "/path1"),
            File("file2.txt", "/path2"),
        ]
        self.container = NamedTupleContainer(
            named_tuples=self.named_tuples,
            fields=["filename", "filepath"],
        )

    def test_iteration_returns_tuples(self):
        """Should be iterable and return tuples."""
        items = list(self.container)
        self.assertEqual(len(items), 2)

    def test_length(self):
        """Should support len()."""
        self.assertEqual(len(self.container), 2)


class TestNamedTupleContainerEdgeCases(BaseTestCase):
    """Edge case tests for NamedTupleContainer."""

    def test_empty_container(self):
        """Should handle empty container."""
        container = NamedTupleContainer(named_tuples=[], fields=["name"])
        self.assertEqual(len(container), 0)
        result = container.get(return_field="name")
        self.assertEqual(result, [])

    def test_container_with_none_values(self):
        """Should handle tuples with None values."""
        Item = namedtuple("Item", ["name", "value"])
        tuples = [Item("item1", None), Item("item2", "value2")]
        container = NamedTupleContainer(named_tuples=tuples, fields=["name", "value"])
        result = container.get(return_field="name", value=None)
        self.assertEqual(result, "item1")

    def test_single_field_container(self):
        """Should work with single field."""
        Item = namedtuple("Item", ["name"])
        tuples = [Item("item1"), Item("item2")]
        container = NamedTupleContainer(named_tuples=tuples, fields=["name"])
        self.assertEqual(len(container), 2)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
