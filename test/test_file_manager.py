# !/usr/bin/python
# coding=utf-8
"""Unit tests for FileManager.

This module tests the FileManager functionality including:
- Container creation and management
- File discovery and filtering
- Duplicate handling
- Path resolution

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


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
