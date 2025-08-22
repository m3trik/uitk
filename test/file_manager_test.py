import unittest
from collections import namedtuple
from uitk.file_manager import FileManager
from pythontk.core_utils.namedtuple_container import NamedTupleContainer


class TestFileManager(unittest.TestCase):
    def setUp(self):
        self.file_manager = FileManager()

    def test_create_container_with_files(self):
        container = self.file_manager.create(
            "ui_registry", "o:/Cloud/Code/_scripts/uitk/uitk/examples", inc_files="*.ui"
        )
        self.assertIsInstance(container, NamedTupleContainer)

    def test_create_container_with_classes(self):
        container = self.file_manager.create(
            "widget_files",
            "o:/Cloud/Code/_scripts/uitk/uitk/widgets",
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )
        self.assertIsInstance(container, NamedTupleContainer)

    def test_extend_container(self):
        self.file_manager.create(
            "widget_files",
            "o:/Cloud/Code/_scripts/uitk/uitk/widgets",
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )
        self.file_manager.widget_files.extend(
            "o:/Cloud/Code/_scripts/uitk/uitk/widgets"
        )

    def test_base_dir_resolution(self):
        # Use base_dir=0 to resolve the relative path based on the current test file's directory
        container = self.file_manager.create(
            "relative_path_test",
            "o:/Cloud/Code/_scripts/uitk/uitk/widgets",
            inc_files="*.py",
            base_dir=0,
        )
        self.assertIsInstance(container, NamedTupleContainer)

    def test_extend_container_with_base_dir(self):
        self.file_manager.create(
            "widget_files",
            "o:/Cloud/Code/_scripts/uitk/uitk/widgets",
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )
        self.file_manager.widget_files.extend(
            "o:/Cloud/Code/_scripts/uitk/uitk/widgets", base_dir=0
        )
        # Add assertions to check the extended content

    def test_container_query(self):
        named_tuples = [
            namedtuple("File", ["filename", "filepath"])("file1.txt", "/path1"),
            namedtuple("File", ["filename", "filepath"])("file2.txt", "/path2"),
        ]
        container = NamedTupleContainer(
            named_tuples=named_tuples, fields=["filename", "filepath"]
        )
        result = container.get(return_field="filename", filepath="/path1")
        self.assertEqual(result, "file1.txt")

    def test_container_modification(self):
        named_tuples = [
            namedtuple("File", ["filename", "filepath"])("file1.txt", "/path1")
        ]
        container = NamedTupleContainer(
            named_tuples=named_tuples, fields=["filename", "filepath"]
        )
        modified_tuple = container.modify(0, filename="new_file.txt")
        self.assertEqual(modified_tuple.filename, "new_file.txt")

    def test_allow_duplicates(self):
        TupleClass = namedtuple("File", ["filename", "filepath"])
        container = NamedTupleContainer(
            named_tuples=[], fields=["filename", "filepath"]
        )
        existing = [TupleClass("file1.txt", "/path/to/file1.txt")]
        new = [
            TupleClass("file1.txt", "/path/to/file1.txt"),
            TupleClass("file2.txt", "/path/to/file2.txt"),
        ]
        combined = container._handle_duplicates(existing, new, allow_duplicates=True)
        self.assertEqual(len(combined), 3)  # Duplicates are allowed, so length is 3

    def test_disallow_duplicates(self):
        TupleClass = namedtuple("File", ["filename", "filepath"])
        container = NamedTupleContainer(
            named_tuples=[], fields=["filename", "filepath"]
        )
        existing = [TupleClass("file1.txt", "/path/to/file1.txt")]
        new = [
            TupleClass("file1.txt", "/path/to/file1.txt"),
            TupleClass("file2.txt", "/path/to/file2.txt"),
        ]
        combined = container._handle_duplicates(existing, new, allow_duplicates=False)
        self.assertEqual(len(combined), 2)  # Duplicates are not allowed, so length is 2

    def test_extend_container_disallow_duplicates(self):
        # Create the initial container
        container = self.file_manager.create(
            "widget_files",
            "o:/Cloud/Code/_scripts/uitk/uitk/widgets",
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )
        # Record the length of the named tuples before extension
        initial_length = len(container.named_tuples)

        # Extend the container with the same path, disallowing duplicates
        container.extend(
            "o:/Cloud/Code/_scripts/uitk/uitk/widgets", allow_duplicates=False
        )

        # Check that the length of the named tuples is the same as before extension
        self.assertEqual(len(container.named_tuples), initial_length)

    def test_contains_location(self):
        # Create a container with specific files
        self.file_manager.create("ui_registry", "../uitk/examples", inc_files="*.ui")

        # Test with a location that is known to be in the container
        contained_location = "../uitk/examples/example.ui"
        self.assertTrue(
            self.file_manager.contains_location(contained_location, "ui_registry")
        )

        # Test with a location that is known not to be in the container
        not_contained_location = "../uitk/examples/non_existent_file.ui"
        self.assertFalse(
            self.file_manager.contains_location(not_contained_location, "ui_registry")
        )


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
