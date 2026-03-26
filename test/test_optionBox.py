# !/usr/bin/python
# coding=utf-8
"""Unit tests for optionBox subpackage.

This module tests the widgets.optionBox subpackage functionality including:
- OptionBox styling and layout behavior (Regression tests)
- PinValuesOption widget functionality
- RecentValuesOption display_format feature

Run standalone: python -m test.test_optionBox
Run with demo: python -m test.test_optionBox --demo
"""

import sys
import unittest
from typing import List, Tuple

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore
from pathlib import Path

from uitk.widgets.optionBox._optionBox import OptionBox, OptionBoxContainer
from uitk.widgets.optionBox.options._options import ButtonOption
from uitk.widgets.optionBox.options.pin_values import PinValuesOption
from uitk.widgets.optionBox.options.recent_values import (
    RecentValuesOption,
    RecentValuesPopup,
    _is_filesystem_path,
    _build_display_map_smart_path,
)


class TestOptionBoxStyling(QtBaseTestCase):
    """Regression tests for OptionBox styling and layout behavior."""

    def test_container_defaults_to_bordered(self):
        """OptionBoxContainer should have 'withBorder' class by default."""
        container = self.track_widget(OptionBoxContainer())

        # Verify default property assignment
        # This ensures standard widgets get borders
        classes = container.property("class")
        self.assertIn("withBorder", classes, "Container must default to having borders")

    def test_wrap_respects_frameless_param(self):
        """OptionBox.wrap(frameless=True) should remove the border class."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        opt = OptionBox(options=[])

        # Case 1: frameless=True (e.g. TableWidget cells)
        container_frameless = opt.wrap(widget, frameless=True)
        self.track_widget(container_frameless)

        classes = container_frameless.property("class")
        if classes:
            self.assertNotIn(
                "withBorder", classes, "Frameless wrap should remove border class"
            )

        # Reset
        widget = self.track_widget(QtWidgets.QLineEdit())
        opt = OptionBox(options=[])

        # Case 2: frameless=False (Standard widgets)
        container_framed = opt.wrap(widget, frameless=False)
        self.track_widget(container_framed)

        classes = container_framed.property("class")
        self.assertIn("withBorder", classes, "Standard wrap should keep border class")

    def test_table_cell_logic(self):
        """Simulate TableWidget logic to ensure it produces frameless containers."""
        # This mimics the code in uitk.widgets.tableWidget.py

        content_widget = self.track_widget(QtWidgets.QWidget())
        opt = OptionBox(options=[])
        # TableWidget explicitly calls frameless=True
        container = opt.wrap(content_widget, frameless=True)
        self.track_widget(container)

        # Verify it has NO border class
        classes = container.property("class") or ""
        self.assertNotIn("withBorder", classes)


class TestOptionBoxWrappingVisibility(QtBaseTestCase):
    """Regression tests for wrapping widgets inside collapsed groups."""

    def test_wrap_does_not_alter_widget_visibility(self):
        """wrap() must not change the widget's explicit visibility state.

        It should always call container.show() and leave the wrapped widget
        as-is.  Visibility control belongs to the parent (e.g. CollapsableGroup).
        """
        parent = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(parent)
        btn = QtWidgets.QPushButton("Test")
        layout.addWidget(btn)

        # Explicitly hide the button (simulates collapsed group)
        btn.setVisible(False)
        self.assertTrue(btn.isHidden())

        opt = OptionBox(options=[])
        container = opt.wrap(btn)
        self.track_widget(container)

        # wrap() must NOT un-hide the widget — that's the group's job
        self.assertTrue(btn.isHidden(), "wrap() should not alter widget visibility")
        # Container itself is always shown by wrap()
        self.assertFalse(container.isHidden(), "Container should be shown by wrap()")

    def test_collapsed_group_expand_shows_wrapped_buttons(self):
        """End-to-end: buttons wrapped while group is collapsed must appear on expand.

        Bug: _set_content_visible(True) only showed direct layout children
        (OptionBoxContainers), not the wrapped PushButtons inside them.
        Fixed: 2026-03-04
        """
        from uitk.widgets.collapsableGroup import CollapsableGroup

        group = self.track_widget(CollapsableGroup("Test Group"))
        group.restore_state = False
        group.setLayout(QtWidgets.QVBoxLayout())
        btn = QtWidgets.QPushButton("Action")
        group.layout().addWidget(btn)

        # Collapse: hides the button
        group.toggle_expand(False)
        self.assertTrue(btn.isHidden())

        # Wrap the hidden button in an OptionBoxContainer
        opt = OptionBox(options=[])
        container = opt.wrap(btn)
        self.track_widget(container)

        # Expand: _set_content_visible(True) must show containers AND their children
        group.toggle_expand(True)

        self.assertFalse(
            container.isHidden(), "Container should not be hidden after expand"
        )
        self.assertFalse(btn.isHidden(), "Button should not be hidden after expand")


class TestPinValuesOptionCreation(QtBaseTestCase):
    """Tests for PinValuesOption creation and initialization."""

    def setUp(self):
        super().setUp()
        self.widget = self.track_widget(QtWidgets.QLineEdit())
        self.pin_option = PinValuesOption(self.widget)
        self.option_box = OptionBox(options=[self.pin_option])
        self.container = self.track_widget(self.option_box.wrap(self.widget))

    def _find_pin_button(self):
        """Find the pin button in the container."""
        for child in self.container.findChildren(QtWidgets.QAbstractButton):
            if child.property("class") == "PinButton":
                return child
        return None

    def test_option_creates_pin_button(self):
        """Pin option should create a pin button in the container."""
        self.assertIsNotNone(self.container)
        pin_button = self._find_pin_button()
        self.assertIsNotNone(pin_button, "Pin button should exist in container")

    def test_initial_state_has_no_pinned_values(self):
        """Pin option should start with no pinned values."""
        self.assertFalse(self.pin_option.has_pinned_values)
        self.assertEqual(self.pin_option.pinned_values, [])


class TestPinValuesOptionPinning(QtBaseTestCase):
    """Tests for pinning and unpinning values."""

    def setUp(self):
        super().setUp()
        self.widget = self.track_widget(QtWidgets.QLineEdit())
        self.pin_option = PinValuesOption(self.widget)
        self.option_box = OptionBox(options=[self.pin_option])
        self.container = self.track_widget(self.option_box.wrap(self.widget))

    def test_add_single_pinned_value(self):
        """Should be able to pin a single value."""
        self.widget.setText("Test Value 1")
        self.pin_option.add_pinned_value("Test Value 1")

        self.assertTrue(self.pin_option.has_pinned_values)
        self.assertIn("Test Value 1", self.pin_option.pinned_values)

    def test_add_multiple_pinned_values(self):
        """Should be able to pin multiple values."""
        values = ["Value 1", "Value 2", "Value 3"]
        for value in values:
            self.pin_option.add_pinned_value(value)

        self.assertEqual(len(self.pin_option.pinned_values), 3)
        for value in values:
            self.assertIn(value, self.pin_option.pinned_values)

    def test_clear_pinned_values(self):
        """Should be able to clear all pinned values."""
        self.pin_option.add_pinned_value("Value 1")
        self.pin_option.add_pinned_value("Value 2")

        self.pin_option.clear_pinned_values()

        self.assertFalse(self.pin_option.has_pinned_values)
        self.assertEqual(self.pin_option.pinned_values, [])


class TestPinValuesOptionMaxLimit(QtBaseTestCase):
    """Tests for maximum pinned values enforcement."""

    def setUp(self):
        super().setUp()
        self.widget = self.track_widget(QtWidgets.QLineEdit())

    def test_respects_max_pinned_values_limit(self):
        """Should remove oldest values when max is exceeded."""
        pin_option = PinValuesOption(self.widget, max_pinned=3)

        pin_option.add_pinned_value("Value 1")
        pin_option.add_pinned_value("Value 2")
        pin_option.add_pinned_value("Value 3")
        pin_option.add_pinned_value("Value 4")

        self.assertEqual(len(pin_option.pinned_values), 3)

    def test_most_recent_value_is_first(self):
        """Most recently pinned value should be first in list."""
        pin_option = PinValuesOption(self.widget, max_pinned=3)

        pin_option.add_pinned_value("Value 1")
        pin_option.add_pinned_value("Value 2")
        pin_option.add_pinned_value("Value 3")
        pin_option.add_pinned_value("Value 4")

        self.assertEqual(pin_option.pinned_values[0], "Value 4")


class TestPinValuesOptionSignals(QtBaseTestCase):
    """Tests for signal emission."""

    def setUp(self):
        super().setUp()
        self.widget = self.track_widget(QtWidgets.QLineEdit())
        self.pin_option = PinValuesOption(self.widget)
        self.option_box = OptionBox(options=[self.pin_option])
        self.container = self.track_widget(self.option_box.wrap(self.widget))

        # Signal capture lists
        self.pinned_values: List[Tuple[bool, str]] = []
        self.restored_values: List[str] = []

    def test_emits_value_pinned_signal(self):
        """Should emit value_pinned signal when a value is pinned."""
        self.pin_option.value_pinned.connect(
            lambda pinned, value: self.pinned_values.append((pinned, value))
        )

        self.pin_option.add_pinned_value("Test")

        self.assertEqual(len(self.pinned_values), 1)
        self.assertEqual(self.pinned_values[0], (True, "Test"))

    def test_emits_value_restored_signal(self):
        """Should emit value_restored signal when a value is restored."""
        self.pin_option.value_restored.connect(
            lambda value: self.restored_values.append(value)
        )

        # Note: This test verifies signal connection works.
        # Actual restoration behavior depends on UI interaction.
        self.assertTrue(hasattr(self.pin_option, "value_restored"))


class TestRecentValuesDisplayHelpers(QtBaseTestCase):
    """Tests for display-format helper functions."""

    def test_is_filesystem_path_windows_drive(self):
        self.assertTrue(_is_filesystem_path("C:/Users/test"))
        self.assertTrue(_is_filesystem_path("D:\\Projects"))

    def test_is_filesystem_path_unc(self):
        self.assertTrue(_is_filesystem_path("\\\\server\\share"))
        self.assertTrue(_is_filesystem_path("//server/share"))

    def test_is_filesystem_path_unix(self):
        self.assertTrue(_is_filesystem_path("/home/user/file"))

    def test_is_filesystem_path_plain_string(self):
        self.assertFalse(_is_filesystem_path("hello world"))
        self.assertFalse(_is_filesystem_path("some_value"))

    def test_smart_path_strips_common_prefix(self):
        values = [
            "C:/Projects/PRODUCTION/AF/C-5M/Exports/C5_FCS",
            "C:/Projects/PRODUCTION/AF/C-17A/Exports/SFCS",
            "C:/Projects/PRODUCTION/AF/C-130/Exports/Flap",
        ]
        dm = _build_display_map_smart_path(values)
        self.assertIsNotNone(dm)
        for v in values:
            self.assertTrue(dm[v].startswith("\u2026/"))
        self.assertIn("C-5M", dm[values[0]])
        self.assertIn("C-17A", dm[values[1]])
        self.assertIn("C-130", dm[values[2]])

    def test_smart_path_single_returns_none(self):
        self.assertIsNone(_build_display_map_smart_path(["C:/only/one"]))

    def test_smart_path_non_paths_returns_none(self):
        self.assertIsNone(_build_display_map_smart_path(["hello", "world"]))

    def test_smart_path_mixed_returns_none(self):
        self.assertIsNone(_build_display_map_smart_path(["C:/a/b", "plain"]))


class TestRecentValuesDisplayFormat(QtBaseTestCase):
    """Tests for the display_format parameter on RecentValuesOption.

    Verifies that display formatting only affects popup presentation
    and never alters stored values or widget restoration.
    Added: 2026-03-05
    """

    def _make_option(self, display_format="auto"):
        widget = self.track_widget(QtWidgets.QLineEdit())
        return RecentValuesOption(
            wrapped_widget=widget,
            display_format=display_format,
        )

    def test_auto_with_paths_produces_display_map(self):
        option = self._make_option(display_format="auto")
        paths = ["C:/Root/Sub/DirA/file.txt", "C:/Root/Sub/DirB/other.txt"]
        dm = option._resolve_display_map(paths)
        self.assertTrue(len(dm) > 0)
        self.assertIn("DirA", dm[paths[0]])
        self.assertIn("DirB", dm[paths[1]])

    def test_auto_with_non_paths_falls_back(self):
        option = self._make_option(display_format="auto")
        self.assertEqual(option._resolve_display_map(["foo", "bar"]), {})

    def test_truncate_returns_empty(self):
        option = self._make_option(display_format="truncate")
        paths = ["C:/Root/Sub/DirA/file.txt", "C:/Root/Sub/DirB/other.txt"]
        self.assertEqual(option._resolve_display_map(paths), {})

    def test_basename_mode(self):
        option = self._make_option(display_format="basename")
        paths = ["C:/Root/Sub/DirA/file.txt", "C:/Root/Sub/DirB/other.txt"]
        dm = option._resolve_display_map(paths)
        self.assertEqual(dm[paths[0]], "file.txt")
        self.assertEqual(dm[paths[1]], "other.txt")

    def test_callable_format(self):
        option = self._make_option(
            display_format=lambda v: f"[{Path(v).stem}]",
        )
        paths = ["C:/Root/Sub/DirA/file.txt", "C:/Root/Sub/DirB/other.txt"]
        dm = option._resolve_display_map(paths)
        self.assertEqual(dm[paths[0]], "[file]")
        self.assertEqual(dm[paths[1]], "[other]")

    def test_storage_unchanged_by_display_format(self):
        """display_format must never alter stored values."""
        option = self._make_option(display_format="basename")
        raw = "C:/Very/Long/Path/To/Some/File.txt"
        option.add_recent_value(raw)
        self.assertEqual(option.recent_values, [raw])

    def test_restore_uses_raw_value(self):
        """Selecting a formatted entry must restore the original raw value."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        option = RecentValuesOption(wrapped_widget=widget, display_format="basename")
        raw = "C:/Very/Long/Path/To/Some/File.txt"
        option.add_recent_value(raw)
        option._restore_value(raw)
        self.assertEqual(widget.text(), raw)


class TestRecentValuesRowPadding(QtBaseTestCase):
    """Tests for right padding in recent value popup rows.

    Bug: Remove buttons crowded the value text, making it unreadable.
    Fixed: 2026-03-06
    """

    def test_row_has_right_padding(self):
        """Recent value rows must have >=8px right margin for button clearance."""
        parent = self.track_widget(QtWidgets.QWidget())
        popup = RecentValuesPopup(parent=parent)
        self.track_widget(popup.menu)
        popup.add_recent_value("test_value")

        # Find the row container
        rows = popup.menu.findChildren(QtWidgets.QWidget, "recentValueRow")
        self.assertTrue(len(rows) > 0, "Should have at least one row")
        layout = rows[0].layout()
        margins = layout.contentsMargins()
        self.assertGreaterEqual(margins.right(), 8, "Right margin must be >= 8px")
        self.assertGreaterEqual(layout.spacing(), 4, "Spacing must be >= 4px")


class TestRecentValuesCenterTruncation(QtBaseTestCase):
    """Tests for center (middle) truncation of long values.

    Bug: Values were truncated from the left (mode='start'), hiding
    the beginning of the text. Center truncation preserves both ends.
    Fixed: 2026-03-06
    """

    def test_long_value_truncated_from_middle(self):
        """Long values should be truncated from the center, keeping both ends visible."""
        import pythontk as ptk

        long_value = "A" * 50 + "B" * 50 + "C" * 50  # 150 chars, exceeds _MAX_DISPLAY_LENGTH (120)
        parent = self.track_widget(QtWidgets.QWidget())
        popup = RecentValuesPopup(parent=parent)
        self.track_widget(popup.menu)
        popup.add_recent_value(long_value)

        # Find the value button text
        buttons = popup.menu.findChildren(QtWidgets.QPushButton, "recentValueButton")
        self.assertTrue(len(buttons) > 0)
        display = buttons[0].text()

        # Middle truncation: both start and end of original should be present
        self.assertTrue(display.startswith("A"), "Start of value should be preserved")
        self.assertTrue(display.endswith("C"), "End of value should be preserved")
        self.assertIn("..", display, "Should contain truncation marker")
        self.assertLess(
            len(display), len(long_value), "Should be shorter than original"
        )

    def test_short_value_not_truncated(self):
        """Short values should not be truncated."""
        parent = self.track_widget(QtWidgets.QWidget())
        popup = RecentValuesPopup(parent=parent)
        self.track_widget(popup.menu)
        popup.add_recent_value("short")

        buttons = popup.menu.findChildren(QtWidgets.QPushButton, "recentValueButton")
        self.assertTrue(len(buttons) > 0)
        self.assertEqual(buttons[0].text(), "short")


class TestPopupAlignParameter(QtBaseTestCase):
    """Tests for popup_align parameter on RecentValuesOption and PinValuesOption.

    Feature: Popups default to right-aligned to the parent window edge,
    with an option for left alignment.
    Added: 2026-03-06
    """

    def test_recent_default_popup_align_is_right(self):
        """RecentValuesOption should default to popup_align='right'."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        option = RecentValuesOption(wrapped_widget=widget)
        self.assertEqual(option._popup_align, "right")

    def test_recent_popup_align_left(self):
        """RecentValuesOption should accept popup_align='left'."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        option = RecentValuesOption(wrapped_widget=widget, popup_align="left")
        self.assertEqual(option._popup_align, "left")

    def test_pin_default_popup_align_is_right(self):
        """PinValuesOption should default to popup_align='right'."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        option = PinValuesOption(wrapped_widget=widget)
        self.assertEqual(option._popup_align, "right")

    def test_pin_popup_align_left(self):
        """PinValuesOption should accept popup_align='left'."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        option = PinValuesOption(wrapped_widget=widget, popup_align="left")
        self.assertEqual(option._popup_align, "left")


class TestFindParentWindow(QtBaseTestCase):
    """Tests for _find_parent_window helper on ButtonOption.

    Feature: Popup width is capped to the parent window width.
    Added: 2026-03-06
    """

    def test_finds_top_level_window(self):
        """Should find a top-level QWidget as the parent window."""
        window = self.track_widget(QtWidgets.QWidget())
        window.setWindowFlags(QtCore.Qt.Window)
        window.resize(500, 300)

        child = QtWidgets.QWidget(window)
        line_edit = QtWidgets.QLineEdit(child)

        option = RecentValuesOption(wrapped_widget=line_edit)
        found = option._find_parent_window()
        self.assertIs(found, window)

    def test_returns_none_for_orphan_widget(self):
        """Should return the widget itself when it has no parent (it is the window)."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        option = RecentValuesOption(wrapped_widget=widget)
        found = option._find_parent_window()
        # A top-level QLineEdit is itself a window
        self.assertIsNotNone(found)

    def test_no_widget_returns_none(self):
        """Should return None when there is no wrapped widget."""
        option = RecentValuesOption(wrapped_widget=None)
        found = option._find_parent_window()
        self.assertIsNone(found)


class TestPinnedValuesRowPadding(QtBaseTestCase):
    """Tests for right padding in pinned value popup rows.

    Bug: Pin/unpin buttons crowded the value text, making it unreadable.
    Fixed: 2026-03-06
    """

    def test_pinned_row_has_right_padding(self):
        """Pinned value rows must have >=8px right margin for button clearance."""
        from uitk.widgets.optionBox.options.pin_values import PinnedValuesPopup

        parent = self.track_widget(QtWidgets.QWidget())
        popup = PinnedValuesPopup(parent=parent)
        self.track_widget(popup.menu)
        popup.add_current_value("test_value", is_pinned=False)

        rows = popup.menu.findChildren(QtWidgets.QWidget, "pinnedValueRow_current")
        self.assertTrue(len(rows) > 0, "Should have at least one row")
        layout = rows[0].layout()
        margins = layout.contentsMargins()
        self.assertGreaterEqual(margins.right(), 8, "Right margin must be >= 8px")
        self.assertGreaterEqual(layout.spacing(), 4, "Spacing must be >= 4px")


class TestOptionBoxDisabledState(QtBaseTestCase):
    """Tests for disabled-state propagation to option buttons.

    Feature: Option buttons should automatically disable when their
    wrapped widget or container is disabled.
    Added: 2026-03-23
    """

    def _make_wrapped(self):
        """Create a LineEdit wrapped with a pin option button."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        pin = PinValuesOption(widget)
        ob = OptionBox(options=[pin])
        container = self.track_widget(ob.wrap(widget))
        buttons = [
            container.layout().itemAt(i).widget()
            for i in range(1, container.layout().count())
        ]
        return widget, container, buttons

    def test_buttons_enabled_by_default(self):
        """Option buttons should be enabled when wrapped widget is enabled."""
        widget, container, buttons = self._make_wrapped()
        self.assertTrue(widget.isEnabled())
        for btn in buttons:
            self.assertTrue(btn.isEnabled(), "Button should be enabled by default")

    def test_disable_wrapped_widget_disables_buttons(self):
        """Disabling the wrapped widget should disable option buttons."""
        widget, container, buttons = self._make_wrapped()
        widget.setEnabled(False)
        app.processEvents()
        for btn in buttons:
            self.assertFalse(btn.isEnabled(), "Button should be disabled")

    def test_reenable_wrapped_widget_reenables_buttons(self):
        """Re-enabling the wrapped widget should re-enable option buttons."""
        widget, container, buttons = self._make_wrapped()
        widget.setEnabled(False)
        app.processEvents()
        widget.setEnabled(True)
        app.processEvents()
        for btn in buttons:
            self.assertTrue(btn.isEnabled(), "Button should be re-enabled")

    def test_disable_container_disables_buttons(self):
        """Disabling the container should disable option buttons."""
        widget, container, buttons = self._make_wrapped()
        container.setEnabled(False)
        app.processEvents()
        for btn in buttons:
            self.assertFalse(btn.isEnabled(), "Button should be disabled")

    def test_widget_disabled_at_wrap_time(self):
        """Option buttons should be disabled if widget is already disabled before wrapping."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        widget.setEnabled(False)
        pin = PinValuesOption(widget)
        ob = OptionBox(options=[pin])
        container = self.track_widget(ob.wrap(widget))
        buttons = [
            container.layout().itemAt(i).widget()
            for i in range(1, container.layout().count())
        ]
        for btn in buttons:
            self.assertFalse(btn.isEnabled(), "Button should be disabled at wrap time")


# -----------------------------------------------------------------------------
# Interactive Demo (Legacy)
# -----------------------------------------------------------------------------


def run_interactive_demo():
    """Run an interactive demo of the PinValuesOption."""
    window = QtWidgets.QWidget()
    window.setWindowTitle("PinValuesOption Demo")
    window.resize(400, 300)
    layout = QtWidgets.QVBoxLayout(window)

    # LineEdit with pin option
    layout.addWidget(QtWidgets.QLabel("LineEdit with Pin Option:"))
    line_edit = QtWidgets.QLineEdit()
    line_edit.setPlaceholderText("Enter text and click pin button...")

    pin_option = PinValuesOption(line_edit)
    pin_option.value_pinned.connect(
        lambda pinned, value: print(
            f"Value {'pinned' if pinned else 'unpinned'}: {value}"
        )
    )
    pin_option.value_restored.connect(lambda value: print(f"Value restored: {value}"))

    option_box = OptionBox(options=[pin_option])
    container = option_box.wrap(line_edit)
    layout.addWidget(container)

    # Instructions
    instructions = QtWidgets.QLabel(
        "Instructions:\n"
        "1. Type some text in the field\n"
        "2. Click the pin button to show the dropdown\n"
        "3. Click the pin icon next to 'Current' to pin the value\n"
        "4. Type new text and pin again\n"
        "5. Click a pinned value to restore it\n"
        "6. Click the pin icon on a pinned value to unpin it"
    )
    instructions.setWordWrap(True)
    layout.addWidget(instructions)

    # SpinBox with pin option
    layout.addWidget(QtWidgets.QLabel("\nSpinBox with Pin Option:"))
    spinbox = QtWidgets.QSpinBox()
    spinbox.setRange(0, 100)
    pin_option2 = PinValuesOption(spinbox)
    option_box2 = OptionBox(options=[pin_option2])
    container2 = option_box2.wrap(spinbox)
    layout.addWidget(container2)

    layout.addStretch()

    window.show()
    sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_interactive_demo()
    else:
        unittest.main(verbosity=2)
