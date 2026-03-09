# !/usr/bin/python
# coding=utf-8
"""Tests for RecentValuesOption display_format feature.

Validates that the smart path formatting, built-in enums, and callable
overrides produce the correct display strings without altering stored data.
"""

import sys
import unittest
from pathlib import Path

# Add package root and test directory to path
PACKAGE_ROOT = Path(__file__).parent.parent.parent.absolute()
TEST_DIR = Path(__file__).parent.parent.absolute()
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets
from uitk.widgets.optionBox.options.recent_values import (
    RecentValuesOption,
    _is_filesystem_path,
    _build_display_map_smart_path,
)


class TestIsFilesystemPath(unittest.TestCase):
    """Tests for the _is_filesystem_path helper."""

    def test_windows_drive(self):
        self.assertTrue(_is_filesystem_path("C:/Users/test"))
        self.assertTrue(_is_filesystem_path("D:\\Projects"))

    def test_unc_path(self):
        self.assertTrue(_is_filesystem_path("\\\\server\\share"))
        self.assertTrue(_is_filesystem_path("//server/share"))

    def test_unix_absolute(self):
        self.assertTrue(_is_filesystem_path("/home/user/file"))

    def test_plain_string(self):
        self.assertFalse(_is_filesystem_path("hello world"))
        self.assertFalse(_is_filesystem_path("some_value"))

    def test_url_like(self):
        # URLs don't start with / or have drive letters
        self.assertFalse(_is_filesystem_path("http://example.com"))


class TestBuildDisplayMapSmartPath(unittest.TestCase):
    """Tests for the _build_display_map_smart_path helper."""

    def test_strips_common_prefix(self):
        values = [
            "C:/Projects/PRODUCTION/AF/C-5M/Exports/C5_FCS",
            "C:/Projects/PRODUCTION/AF/C-17A/Exports/SFCS",
            "C:/Projects/PRODUCTION/AF/C-130/Exports/Flap",
        ]
        dm = _build_display_map_smart_path(values)
        self.assertIsNotNone(dm)
        # All should start with the ellipsis prefix
        for v in values:
            self.assertTrue(
                dm[v].startswith("\u2026/"), f"Expected \u2026/ prefix: {dm[v]}"
            )
        # The differentiating tail should be present
        self.assertIn("C-5M", dm[values[0]])
        self.assertIn("C-17A", dm[values[1]])
        self.assertIn("C-130", dm[values[2]])

    def test_single_path_returns_none(self):
        dm = _build_display_map_smart_path(["C:/only/one/path"])
        self.assertIsNone(dm)

    def test_non_paths_returns_none(self):
        dm = _build_display_map_smart_path(["hello", "world"])
        self.assertIsNone(dm)

    def test_mixed_paths_and_non_paths_returns_none(self):
        dm = _build_display_map_smart_path(["C:/some/path", "not a path"])
        self.assertIsNone(dm)


class TestRecentValuesDisplayFormat(QtBaseTestCase):
    """Tests for the display_format parameter on RecentValuesOption."""

    def _make_option(self, display_format="auto"):
        widget = self.track_widget(QtWidgets.QLineEdit())
        option = RecentValuesOption(
            wrapped_widget=widget,
            display_format=display_format,
        )
        return option

    def test_auto_with_paths_produces_display_map(self):
        option = self._make_option(display_format="auto")
        paths = [
            "C:/Root/Sub/DirA/file.txt",
            "C:/Root/Sub/DirB/other.txt",
        ]
        dm = option._resolve_display_map(paths)
        # Auto should engage smart path logic
        self.assertTrue(len(dm) > 0, "Auto should produce a display map for paths")
        self.assertIn("DirA", dm[paths[0]])
        self.assertIn("DirB", dm[paths[1]])

    def test_auto_with_non_paths_falls_back(self):
        option = self._make_option(display_format="auto")
        dm = option._resolve_display_map(["foo", "bar"])
        # Should fall back to empty dict (default truncation)
        self.assertEqual(dm, {})

    def test_truncate_always_returns_empty(self):
        option = self._make_option(display_format="truncate")
        paths = [
            "C:/Root/Sub/DirA/file.txt",
            "C:/Root/Sub/DirB/other.txt",
        ]
        dm = option._resolve_display_map(paths)
        self.assertEqual(dm, {}, "truncate mode should return empty (use default)")

    def test_basename_mode(self):
        option = self._make_option(display_format="basename")
        paths = [
            "C:/Root/Sub/DirA/file.txt",
            "C:/Root/Sub/DirB/other.txt",
        ]
        dm = option._resolve_display_map(paths)
        self.assertEqual(dm[paths[0]], "file.txt")
        self.assertEqual(dm[paths[1]], "other.txt")

    def test_callable_format(self):
        option = self._make_option(
            display_format=lambda v: f"[{Path(v).stem}]",
        )
        paths = [
            "C:/Root/Sub/DirA/file.txt",
            "C:/Root/Sub/DirB/other.txt",
        ]
        dm = option._resolve_display_map(paths)
        self.assertEqual(dm[paths[0]], "[file]")
        self.assertEqual(dm[paths[1]], "[other]")

    def test_storage_unchanged_by_display_format(self):
        """display_format must never alter the values stored in the list."""
        option = self._make_option(display_format="basename")
        raw_path = "C:/Very/Long/Path/To/Some/File.txt"
        option.add_recent_value(raw_path)
        self.assertEqual(option.recent_values, [raw_path])

    def test_restore_uses_raw_value(self):
        """Selecting a formatted entry must restore the original raw value."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        option = RecentValuesOption(
            wrapped_widget=widget,
            display_format="basename",
        )
        raw_path = "C:/Very/Long/Path/To/Some/File.txt"
        option.add_recent_value(raw_path)
        # Simulate restore
        option._restore_value(raw_path)
        self.assertEqual(widget.text(), raw_path)


if __name__ == "__main__":
    unittest.main()
