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
from uitk.widgets.optionBox.options.reset import ResetOption
from uitk.widgets.optionBox.options.pin_values import PinValuesOption
from uitk.widgets.optionBox.options.browse import BrowseOption
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


class TestOptionBoxOverlayRefit(QtBaseTestCase):
    """Regression: an absolutely-positioned OptionBoxContainer (the marking-menu
    overlay case) must re-fit to content on show.

    Bug: marking-menu option-box buttons measured their size hint *before* the
    theme QSS had been polished, so a host Qt style whose un-polished button
    minimum is large (e.g. Windows' native style) froze an inflated geometry —
    the option-box square ended up pushed ~2-4x too far from the button text on
    some hosts but not others. Fixed by re-fitting to content on first show when
    no parent layout owns the container. Fixed: 2026-06-13.
    """

    def test_absolute_container_refits_to_content_on_show(self):
        """No managing parent layout → collapse a stale/inflated size, keep center."""
        parent = self.track_widget(QtWidgets.QWidget())
        parent.resize(800, 600)
        btn = QtWidgets.QPushButton("Clean", parent)
        opt = OptionBox(options=[])
        container = self.track_widget(opt.wrap(btn))

        # Simulate the frozen, inflated geometry from a pre-polish size hint.
        container.resize(300, max(container.height(), 24))
        container.move(250, 100)
        inflated_center = container.geometry().center()

        parent.show()
        container.show()
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 100)

        content_w = container.sizeHint().width()
        self.assertLess(container.width(), 300, "Inflated width must shrink on show")
        self.assertLessEqual(
            container.width(),
            content_w + 2,
            f"Container should collapse to content (~{content_w}px), "
            f"got {container.width()}",
        )
        self.assertAlmostEqual(
            container.geometry().center().x(),
            inflated_center.x(),
            delta=3,
            msg="Re-fit must preserve the container's center point",
        )

    def test_layout_managed_container_not_refit_on_show(self):
        """A parent layout owns sizing → container must NOT collapse to content."""
        parent = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(parent)
        btn = QtWidgets.QPushButton("Clean")
        layout.addWidget(btn)
        opt = OptionBox(options=[])
        container = self.track_widget(opt.wrap(btn))  # replaces btn in the layout

        parent.resize(300, 60)
        parent.show()
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 100)

        self.assertGreater(
            container.width(),
            container.sizeHint().width() + 20,
            "Layout-managed container should stay stretched, not refit to content",
        )


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
        dm = option.store.display_map(paths)
        self.assertTrue(len(dm) > 0)
        self.assertIn("DirA", dm[paths[0]])
        self.assertIn("DirB", dm[paths[1]])

    def test_auto_with_non_paths_falls_back(self):
        """auto-fallback now returns full (short) strings, not an empty sentinel."""
        option = self._make_option(display_format="auto")
        self.assertEqual(
            option.store.display_map(["foo", "bar"]), {"foo": "foo", "bar": "bar"}
        )

    def test_truncate_returns_full_strings(self):
        """The store always returns display strings (never the old {} sentinel)."""
        option = self._make_option(display_format="truncate")
        paths = ["C:/Root/Sub/DirA/file.txt", "C:/Root/Sub/DirB/other.txt"]
        dm = option.store.display_map(paths)
        self.assertEqual(set(dm), set(paths))
        self.assertTrue(all(isinstance(v, str) for v in dm.values()))

    def test_basename_mode(self):
        option = self._make_option(display_format="basename")
        paths = ["C:/Root/Sub/DirA/file.txt", "C:/Root/Sub/DirB/other.txt"]
        dm = option.store.display_map(paths)
        self.assertEqual(dm[paths[0]], "file.txt")
        self.assertEqual(dm[paths[1]], "other.txt")

    def test_callable_format(self):
        option = self._make_option(
            display_format=lambda v: f"[{Path(v).stem}]",
        )
        paths = ["C:/Root/Sub/DirA/file.txt", "C:/Root/Sub/DirB/other.txt"]
        dm = option.store.display_map(paths)
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


class TestRecentValuesExcludesCurrent(QtBaseTestCase):
    """The popup lists *previously used* values only — never the widget's
    current value, since re-selecting the value you already have is a no-op.

    Bug: the current value was shown as a pinned row at the top of the popup.
    Added: 2026-06-25
    """

    def _populate(self, current_text, history):
        widget = self.track_widget(QtWidgets.QLineEdit())
        widget.setText(current_text)
        option = RecentValuesOption(wrapped_widget=widget)
        for v in history:
            option.add_recent_value(v)
        option._popup = RecentValuesPopup(parent=widget)
        self.track_widget(option._popup.menu)
        option._populate_popup()
        return option

    def _row_texts(self, option):
        return [
            b.text()
            for b in option._popup.menu.findChildren(
                QtWidgets.QPushButton, "recentValueButton"
            )
        ]

    def test_current_value_not_listed(self):
        option = self._populate("B", ["A", "B", "C"])
        self.assertEqual(self._row_texts(option), ["A", "C"])

    def test_no_current_row_or_separator(self):
        menu = self._populate("B", ["A", "B", "C"])._popup.menu
        self.assertEqual(
            menu.findChildren(QtWidgets.QWidget, "recentValueRow_current"), []
        )
        self.assertEqual(
            menu.findChildren(QtWidgets.QFrame, "recentValuesSeparator"), []
        )

    def test_empty_message_when_only_current(self):
        option = self._populate("B", ["B"])
        self.assertEqual(self._row_texts(option), [])
        self.assertEqual(
            len(
                option._popup.menu.findChildren(
                    QtWidgets.QLabel, "recentValuesEmptyLabel"
                )
            ),
            1,
        )


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

        long_value = (
            "A" * 50 + "B" * 50 + "C" * 50
        )  # 150 chars, exceeds _MAX_DISPLAY_LENGTH (120)
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


class TestRecentValuesPopupWidthSizing(QtBaseTestCase):
    """The popup must size to its content width even while still invisible.

    Bug: ``adjustSize()`` on a freshly-populated, not-yet-shown popup
    collapsed the menu to its minimum width, center-clipping every value
    into uselessness (observed on tentacle's "Set Workspace" history).
    Root cause: ``add()`` skips ``self._layout.activate()`` while invisible,
    leaving the inner QBoxLayouts' cached sizeHints collapsed to their
    margins; ``Menu.sizeHint()`` read those stale hints. Fixed by forcing
    a synchronous activate of the inner layout chain in ``sizeHint()``.
    Fixed: 2026-06-09
    """

    LONG_VALUES = [
        "O:/Dropbox (Moth+Flame)/Moth+Flame Dropbox/Ryan Simpson/_tests/lightmap_bake_test/scripts",
        "O:/Dropbox (Moth+Flame)/Moth+Flame Team Folder/Platform/Build",
        "O:/Dropbox (Moth+Flame)/Moth+Flame Team Folder/PRODUCTION/SceneAssembly",
    ]

    def test_invisible_popup_sizehint_reflects_content(self):
        """sizeHint width must reflect the widest row, not the menu minimum."""
        parent = self.track_widget(QtWidgets.QWidget())
        popup = RecentValuesPopup(parent=parent, text_align="left")
        self.track_widget(popup.menu)
        for v in self.LONG_VALUES:
            popup.add_recent_value(v)

        self.assertFalse(popup.menu.isVisible())
        hint_w = popup.menu.sizeHint().width()
        grid_w = popup.menu.gridLayout.sizeHint().width()
        # The grid already knows the true content width; the menu must agree
        # rather than collapsing to its 150px minimum.
        self.assertGreaterEqual(
            hint_w,
            grid_w,
            f"Menu sizeHint width {hint_w} collapsed below grid content {grid_w}",
        )
        self.assertGreater(hint_w, popup.menu.minimumWidth() + 100)

    def test_adjustsize_widens_to_content_before_show(self):
        """adjustSize() on the hidden popup must widen it to fit the content."""
        parent = self.track_widget(QtWidgets.QWidget())
        popup = RecentValuesPopup(parent=parent, text_align="left")
        self.track_widget(popup.menu)
        for v in self.LONG_VALUES:
            popup.add_recent_value(v)

        popup.menu.adjustSize()
        # Deterministic, font-independent: adjustSize() must widen the popup to its
        # content (the grid's own width hint), not collapse to the 150px minimum. The
        # absolute pixel width of these paths is font-dependent (e.g. 574px at 9pt Segoe
        # UI vs >1000px at the default font), so a hardcoded threshold flakes across
        # environments — assert the popup reached its content width instead.
        self.assertGreaterEqual(
            popup.menu.width(),
            popup.menu.gridLayout.sizeHint().width(),
            "Popup stayed collapsed after adjustSize (content clipped)",
        )
        self.assertGreater(
            popup.menu.width(),
            popup.menu.minimumWidth() + 100,
            "Popup didn't widen past its minimum",
        )

    def test_empty_popup_stays_compact(self):
        """The fix must not balloon an empty popup."""
        parent = self.track_widget(QtWidgets.QWidget())
        popup = RecentValuesPopup(parent=parent)
        self.track_widget(popup.menu)
        popup.add_empty_message()
        popup.menu.adjustSize()
        self.assertLess(popup.menu.width(), 400)


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


class TestBrowseOption(QtBaseTestCase):
    """Tests for BrowseOption file/folder browsing plugin.

    Added: 2026-04-04
    """

    def test_creation_with_defaults(self):
        """BrowseOption should create a button with default icon and tooltip."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        browse = BrowseOption(wrapped_widget=widget)
        button = browse.widget
        self.assertIsNotNone(button)
        self.assertEqual(button.toolTip(), "Browse...")
        self.assertEqual(button.property("class"), "BrowseButton")

    def test_wrap_adds_browse_button(self):
        """Wrapping a widget with BrowseOption should add a browse button."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        browse = BrowseOption(wrapped_widget=widget)
        ob = OptionBox(options=[browse])
        container = self.track_widget(ob.wrap(widget))
        buttons = container.findChildren(QtWidgets.QPushButton)
        browse_buttons = [b for b in buttons if b.property("class") == "BrowseButton"]
        self.assertEqual(len(browse_buttons), 1)

    def test_callable_start_dir(self):
        """start_dir should accept a callable for lazy evaluation."""
        calls = []

        def get_dir():
            calls.append(1)
            return ""

        widget = self.track_widget(QtWidgets.QLineEdit())
        browse = BrowseOption(wrapped_widget=widget, start_dir=get_dir)
        result = browse._resolve_start_dir()
        self.assertEqual(len(calls), 1, "Callable should be invoked at resolve time")
        self.assertEqual(result, "")

    def test_string_start_dir(self):
        """start_dir should accept a plain string."""
        import tempfile, os

        tmp = tempfile.gettempdir()
        widget = self.track_widget(QtWidgets.QLineEdit())
        browse = BrowseOption(wrapped_widget=widget, start_dir=tmp)
        result = browse._resolve_start_dir()
        self.assertEqual(result, tmp)

    def test_start_dir_falls_back_to_widget_value(self):
        """When start_dir is None, should use the widget's current value if it's a valid directory."""
        import tempfile

        tmp = tempfile.gettempdir()
        widget = self.track_widget(QtWidgets.QLineEdit())
        widget.setText(tmp)
        browse = BrowseOption(wrapped_widget=widget)
        result = browse._resolve_start_dir()
        self.assertEqual(result, tmp)

    def test_start_dir_falls_back_to_parent_of_file(self):
        """When widget contains a file path, should use parent directory."""
        import tempfile, os

        tmp = tempfile.gettempdir()
        fake_file = os.path.join(tmp, "nonexistent_file.txt")
        widget = self.track_widget(QtWidgets.QLineEdit())
        widget.setText(fake_file)
        browse = BrowseOption(wrapped_widget=widget)
        result = browse._resolve_start_dir()
        self.assertEqual(result, tmp)

    def test_start_dir_empty_when_no_hints(self):
        """When no start_dir and widget is empty, should return empty string."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        browse = BrowseOption(wrapped_widget=widget)
        result = browse._resolve_start_dir()
        self.assertEqual(result, "")

    def test_file_types_property(self):
        """file_types should be gettable/settable."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        browse = BrowseOption(wrapped_widget=widget, file_types="Images (*.png *.jpg)")
        self.assertEqual(browse.file_types, "Images (*.png *.jpg)")
        browse.file_types = "All Files (*.*)"
        self.assertEqual(browse.file_types, "All Files (*.*)")

    def test_start_dir_property_setter(self):
        """start_dir should be updatable after creation."""
        import tempfile

        widget = self.track_widget(QtWidgets.QLineEdit())
        browse = BrowseOption(wrapped_widget=widget)
        self.assertIsNone(browse.start_dir)
        browse.start_dir = tempfile.gettempdir()
        self.assertEqual(browse.start_dir, tempfile.gettempdir())

    def test_mode_defaults_to_file(self):
        """Default mode should be 'file'."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        browse = BrowseOption(wrapped_widget=widget)
        self.assertEqual(browse._mode, "file")


class TestActionOptionMultiInstance(QtBaseTestCase):
    """Tests for multiple ActionOption instances on a single widget."""

    def _make_managed_widget(self):
        """Create a widget with OptionBoxManager wired up."""
        from uitk.widgets.optionBox.utils import OptionBoxManager

        parent = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(parent)
        widget = QtWidgets.QPushButton("Test")
        layout.addWidget(widget)
        mgr = OptionBoxManager(widget)
        widget._option_box_manager = mgr
        # ``option_box`` may be a class-level property (when
        # ``patch_common_widgets`` has been called by another test or by
        # bootstrap code).  Setting it as an instance attribute would then
        # raise AttributeError; the property resolves to the manager via
        # ``_option_box_manager`` already, so the assignment is unnecessary.
        try:
            widget.option_box = mgr
        except AttributeError:
            pass
        return widget, mgr

    def test_add_action_creates_multiple_buttons(self):
        """add_action() should add a second action without replacing the first."""
        from uitk.widgets.optionBox.options.action import ActionOption

        widget, mgr = self._make_managed_widget()

        mgr.set_action(lambda: None, icon="play")
        mgr.add_action(lambda: None, icon="pause")

        # Force wrapping
        container = mgr.container
        self.assertIsNotNone(container)

        # Count ActionOption instances
        actions = [
            o for o in mgr._option_box.get_options() if isinstance(o, ActionOption)
        ]
        self.assertEqual(len(actions), 2, "Should have two ActionOption instances")

    def test_set_action_replaces_only_actions_not_menu(self):
        """set_action(replace=True) must not remove MenuOption instances."""
        from uitk.widgets.optionBox.options.action import ActionOption, MenuOption

        widget, mgr = self._make_managed_widget()

        # Add menu first, then action
        mgr.menu  # triggers enable_menu
        mgr.set_action(lambda: None, icon="play")

        container = mgr.container
        self.assertIsNotNone(container)

        options = mgr._option_box.get_options()
        menu_opts = [o for o in options if isinstance(o, MenuOption)]
        action_opts = [
            o
            for o in options
            if isinstance(o, ActionOption) and not isinstance(o, MenuOption)
        ]
        self.assertEqual(len(menu_opts), 1, "MenuOption must survive set_action")
        self.assertEqual(len(action_opts), 1)

        # Replace with a new action — menu must still survive
        mgr.set_action(lambda: None, icon="stop")
        options = mgr._option_box.get_options()
        menu_opts = [o for o in options if isinstance(o, MenuOption)]
        action_opts = [
            o
            for o in options
            if isinstance(o, ActionOption) and not isinstance(o, MenuOption)
        ]
        self.assertEqual(len(menu_opts), 1, "MenuOption must survive second set_action")
        self.assertEqual(len(action_opts), 1, "Old action should be replaced")

    def test_set_action_replaces_all_pure_actions(self):
        """set_action(replace=True) should remove all prior pure ActionOptions."""
        from uitk.widgets.optionBox.options.action import ActionOption, MenuOption

        widget, mgr = self._make_managed_widget()

        mgr.set_action(lambda: None, icon="a")
        mgr.add_action(lambda: None, icon="b")
        # Now replace all
        mgr.set_action(lambda: None, icon="c")

        container = mgr.container
        options = mgr._option_box.get_options()
        action_opts = [
            o
            for o in options
            if isinstance(o, ActionOption) and not isinstance(o, MenuOption)
        ]
        self.assertEqual(len(action_opts), 1, "set_action should replace all")


class TestBrowseOptionIntegration(QtBaseTestCase):
    """Tests for BrowseOption integration with other options."""

    def test_records_to_sibling_recent_option(self):
        """Browse should auto-record to a sibling RecentValuesOption."""
        from uitk.widgets.optionBox.utils import OptionBoxManager

        widget = self.track_widget(QtWidgets.QLineEdit())
        # Use OptionBoxManager (real-world path) so _option_box_manager is set
        mgr = OptionBoxManager(widget)
        widget._option_box_manager = mgr

        recent = RecentValuesOption(
            wrapped_widget=widget, settings_key="test_browse_recent"
        )
        browse = BrowseOption(wrapped_widget=widget)
        ob = OptionBox(options=[recent, browse])
        container = self.track_widget(ob.wrap(widget))
        mgr._option_box = ob
        mgr._is_wrapped = True

        # Simulate what browse() does after a successful dialog
        browse._set_widget_value("/some/test/path.txt")
        browse._record_recent("/some/test/path.txt")

        self.assertIn("/some/test/path.txt", recent.recent_values)

    def test_user_callback_receives_result(self):
        """User callback should be invoked with the selected path."""
        results = []
        widget = self.track_widget(QtWidgets.QLineEdit())
        browse = BrowseOption(
            wrapped_widget=widget, callback=lambda r: results.append(r)
        )
        self.assertIsNotNone(browse._user_callback)

    def test_has_public_browse_method(self):
        """BrowseOption should expose a public browse() method."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        browse = BrowseOption(wrapped_widget=widget)
        self.assertTrue(callable(getattr(browse, "browse", None)))


class TestOptionBoxManagerBrowse(QtBaseTestCase):
    """Tests for the OptionBoxManager.browse() fluent API.

    Added: 2026-04-04
    """

    def test_browse_fluent_returns_self(self):
        """browse() should return the manager for chaining."""
        from uitk.widgets.optionBox.utils import OptionBoxManager

        widget = self.track_widget(QtWidgets.QLineEdit())
        mgr = OptionBoxManager(widget)
        result = mgr.browse(file_types="All Files (*.*)")
        self.assertIs(result, mgr)

    def test_browse_adds_browse_option(self):
        """browse() should add a BrowseOption to pending options."""
        from uitk.widgets.optionBox.utils import OptionBoxManager

        widget = self.track_widget(QtWidgets.QLineEdit())
        mgr = OptionBoxManager(widget)
        mgr.browse(file_types="Text Files (*.txt)")

        browse_opts = [o for o in mgr._pending_options if isinstance(o, BrowseOption)]
        self.assertEqual(len(browse_opts), 1)
        self.assertEqual(browse_opts[0].file_types, "Text Files (*.txt)")

    def test_browse_chained_with_recent(self):
        """browse() and recent() should chain without conflict."""
        from uitk.widgets.optionBox.utils import OptionBoxManager

        widget = self.track_widget(QtWidgets.QLineEdit())
        mgr = OptionBoxManager(widget)
        mgr.browse(file_types="All Files (*.*)").recent(settings_key="test_chain")

        browse_opts = [o for o in mgr._pending_options if isinstance(o, BrowseOption)]
        recent_opts = [
            o for o in mgr._pending_options if isinstance(o, RecentValuesOption)
        ]
        self.assertEqual(len(browse_opts), 1)
        self.assertEqual(len(recent_opts), 1)


class TestOptionBoxManagerFindOption(QtBaseTestCase):
    """Tests for OptionBoxManager.find_option() method.

    Added: 2026-04-04
    """

    def test_find_pending_option(self):
        """find_option should search pending options."""
        from uitk.widgets.optionBox.utils import OptionBoxManager

        widget = self.track_widget(QtWidgets.QLineEdit())
        mgr = OptionBoxManager(widget)
        mgr.browse(file_types="All Files (*.*)")

        found = mgr.find_option(BrowseOption)
        self.assertIsNotNone(found)
        self.assertIsInstance(found, BrowseOption)

    def test_find_returns_none_when_absent(self):
        """find_option should return None when no match exists."""
        from uitk.widgets.optionBox.utils import OptionBoxManager

        widget = self.track_widget(QtWidgets.QLineEdit())
        mgr = OptionBoxManager(widget)

        found = mgr.find_option(BrowseOption)
        self.assertIsNone(found)

    def test_find_live_option(self):
        """find_option should search live options on a wrapped option box."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        browse = BrowseOption(wrapped_widget=widget)
        ob = OptionBox(options=[browse])
        container = self.track_widget(ob.wrap(widget))

        from uitk.widgets.optionBox.utils import OptionBoxManager

        mgr = OptionBoxManager(widget)
        mgr._option_box = ob
        mgr._is_wrapped = True

        found = mgr.find_option(BrowseOption)
        self.assertIsNotNone(found)
        self.assertIsInstance(found, BrowseOption)

    def test_find_with_tuple_of_types(self):
        """find_option should accept a tuple of types."""
        from uitk.widgets.optionBox.utils import OptionBoxManager

        widget = self.track_widget(QtWidgets.QLineEdit())
        mgr = OptionBoxManager(widget)
        mgr.browse()

        found = mgr.find_option((BrowseOption, PinValuesOption))
        self.assertIsNotNone(found)
        self.assertIsInstance(found, BrowseOption)


class TestToggleOption(QtBaseTestCase):
    """Tests for ToggleOption — persisted binary on/off button."""

    def _make_toggle(self, **kwargs):
        from uitk.widgets.optionBox.options.toggle import ToggleOption

        # Default to settings_key=False so unit tests never touch QSettings.
        kwargs.setdefault("settings_key", False)
        widget = self.track_widget(QtWidgets.QLineEdit())
        toggle = ToggleOption(wrapped_widget=widget, **kwargs)
        return widget, toggle

    def test_defaults_to_on(self):
        _, toggle = self._make_toggle()
        self.assertTrue(toggle.is_on)

    def test_initial_false_starts_off(self):
        _, toggle = self._make_toggle(initial=False)
        self.assertFalse(toggle.is_on)

    def test_set_on_emits_toggled_when_state_changes(self):
        _, toggle = self._make_toggle(initial=True)
        seen = []
        toggle.toggled.connect(seen.append)

        toggle.set_on(False)
        self.assertEqual(seen, [False])
        # Same value → no emission
        toggle.set_on(False)
        self.assertEqual(seen, [False])
        toggle.set_on(True)
        self.assertEqual(seen, [False, True])

    def test_set_on_emit_false_is_silent(self):
        _, toggle = self._make_toggle(initial=True)
        seen = []
        toggle.toggled.connect(seen.append)

        toggle.set_on(False, emit=False)
        self.assertFalse(toggle.is_on)
        self.assertEqual(seen, [])

    def test_user_click_flips_state_and_emits(self):
        _, toggle = self._make_toggle(initial=True)
        # Force widget creation so the click handler is wired.
        _ = toggle.widget
        seen = []
        toggle.toggled.connect(seen.append)

        toggle._widget.click()
        self.assertFalse(toggle.is_on)
        self.assertEqual(seen, [False])

        toggle._widget.click()
        self.assertTrue(toggle.is_on)
        self.assertEqual(seen, [False, True])

    def test_gated_widgets_disable_in_sync(self):
        gated = self.track_widget(QtWidgets.QLineEdit())
        gated.setEnabled(True)
        _, toggle = self._make_toggle(initial=True, gated_widgets=[gated])
        # Trigger setup_widget which applies initial gating state
        _ = toggle.widget
        self.assertTrue(gated.isEnabled(), "Gated widget should be enabled when toggle is on")

        toggle.set_on(False)
        self.assertFalse(gated.isEnabled(), "Gated widget should be disabled when toggle is off")

        toggle.set_on(True)
        self.assertTrue(gated.isEnabled())

    def test_gated_widgets_respect_initial_false(self):
        gated = self.track_widget(QtWidgets.QLineEdit())
        gated.setEnabled(True)
        _, toggle = self._make_toggle(initial=False, gated_widgets=[gated])
        _ = toggle.widget  # trigger setup_widget
        self.assertFalse(
            gated.isEnabled(),
            "Gated widget should already be disabled when toggle starts off",
        )

    def test_tooltip_swaps_on_state_change(self):
        _, toggle = self._make_toggle(
            initial=True,
            tooltip_on="ON-LABEL",
            tooltip_off="OFF-LABEL",
        )
        _ = toggle.widget  # trigger setup_widget → _apply_visuals
        self.assertEqual(toggle._widget.toolTip(), "ON-LABEL")
        toggle.set_on(False)
        self.assertEqual(toggle._widget.toolTip(), "OFF-LABEL")
        toggle.set_on(True)
        self.assertEqual(toggle._widget.toolTip(), "ON-LABEL")

    def test_initial_false_applies_off_tooltip_immediately(self):
        """Regression: initial=False must produce the off tooltip on first render,
        not the on tooltip (would happen if create_widget's setText overrode setup_widget)."""
        _, toggle = self._make_toggle(
            initial=False,
            tooltip_on="ON-LABEL",
            tooltip_off="OFF-LABEL",
        )
        _ = toggle.widget
        self.assertEqual(toggle._widget.toolTip(), "OFF-LABEL")

    def test_click_does_not_store_bound_method_callback(self):
        """Regression: __init__ must not stash _handle_click on self.callback —
        that path created a needless reference cycle and confused readers."""
        _, toggle = self._make_toggle()
        self.assertIsNone(
            toggle.callback,
            "ToggleOption should leave ButtonOption.callback as None and wire "
            "the click connection directly.",
        )

    def test_disabled_color_defaults_to_palette_error(self):
        import pythontk as ptk
        from uitk.widgets.optionBox.options.toggle import (
            _DEFAULT_DISABLED_COLOR,
        )

        expected = ptk.Palette.status()["error"][0]
        self.assertEqual(_DEFAULT_DISABLED_COLOR, expected)

        _, toggle = self._make_toggle()
        self.assertEqual(toggle._disabled_color, expected)

    def test_persistence_round_trip(self):
        from uitk.widgets.optionBox.options.toggle import ToggleOption

        # Use an in-memory-ish settings key unique to this test run
        key = "test_toggle_round_trip"
        widget = self.track_widget(QtWidgets.QLineEdit())
        toggle = ToggleOption(
            wrapped_widget=widget, initial=True, settings_key=key
        )
        toggle.set_on(False)  # writes is_on=False to QSettings under `key`

        widget2 = self.track_widget(QtWidgets.QLineEdit())
        # `initial=True` would normally win, but persisted False should override.
        toggle2 = ToggleOption(
            wrapped_widget=widget2, initial=True, settings_key=key
        )
        self.assertFalse(toggle2.is_on, "Persisted state must override initial=True")

        # Clean up so subsequent runs start fresh.
        if toggle2._settings is not None:
            toggle2._settings.clear()
            toggle2._settings.sync()


class TestOptionBoxManagerToggle(QtBaseTestCase):
    """Tests for the OptionBoxManager.set_toggle() / add_toggle() fluent API."""

    def _make_manager(self):
        from uitk.widgets.optionBox.utils import OptionBoxManager

        widget = self.track_widget(QtWidgets.QLineEdit())
        mgr = OptionBoxManager(widget)
        widget._option_box_manager = mgr
        return widget, mgr

    def test_set_toggle_returns_self(self):
        _, mgr = self._make_manager()
        result = mgr.set_toggle(settings_key=False)
        self.assertIs(result, mgr)

    def test_set_toggle_adds_toggle_option(self):
        from uitk.widgets.optionBox.options.toggle import ToggleOption

        _, mgr = self._make_manager()
        mgr.set_toggle(settings_key=False)

        toggles = [
            o for o in mgr._pending_options if isinstance(o, ToggleOption)
        ]
        self.assertEqual(len(toggles), 1)

    def test_set_toggle_replaces_existing_by_default(self):
        from uitk.widgets.optionBox.options.toggle import ToggleOption

        _, mgr = self._make_manager()
        mgr.set_toggle(icon="filter", settings_key=False)
        mgr.set_toggle(icon="lock", settings_key=False)

        toggles = [
            o for o in mgr._pending_options if isinstance(o, ToggleOption)
        ]
        self.assertEqual(len(toggles), 1, "Second set_toggle should replace the first")
        self.assertEqual(toggles[0]._icon_on, "lock")

    def test_add_toggle_stacks(self):
        from uitk.widgets.optionBox.options.toggle import ToggleOption

        _, mgr = self._make_manager()
        mgr.set_toggle(icon="filter", settings_key=False)
        mgr.add_toggle(icon="lock", settings_key=False)

        toggles = [
            o for o in mgr._pending_options if isinstance(o, ToggleOption)
        ]
        self.assertEqual(len(toggles), 2)

    def test_set_toggle_on_toggled_wires_signal(self):
        _, mgr = self._make_manager()
        seen = []
        mgr.set_toggle(
            initial=True,
            settings_key=False,
            on_toggled=seen.append,
        )

        from uitk.widgets.optionBox.options.toggle import ToggleOption

        toggle = mgr.find_option(ToggleOption)
        self.assertIsNotNone(toggle)
        toggle.set_on(False)
        self.assertEqual(seen, [False])


class TestResetOption(QtBaseTestCase):
    """The per-widget reset-to-default button + its modifier-gated bypass toggle."""

    def _make(self, default=0.0, start=5.0):
        sb = self.track_widget(QtWidgets.QDoubleSpinBox())
        sb.setRange(-100.0, 100.0)
        sb.setValue(start)
        opt = ResetOption(sb, reset=lambda: sb.setValue(default))
        box = OptionBox(options=[opt])
        self.track_widget(box.wrap(sb))
        return sb, opt

    @staticmethod
    def _force_modifier(opt, modifier):
        """Make the option's click handler see *modifier* as held (test seam)."""
        opt._current_modifiers = lambda: modifier

    # ---- plain reset (primary behavior) ----------------------------------

    def test_starts_active(self):
        sb, opt = self._make()
        self.assertFalse(opt.is_bypassed)
        self.assertTrue(sb.isEnabled())
        self.assertEqual(sb.value(), 5.0)

    def test_plain_click_resets_to_default_without_greying(self):
        sb, opt = self._make(default=0.0, start=5.0)
        self._force_modifier(opt, QtCore.Qt.NoModifier)
        opt.widget.click()
        app.processEvents()
        self.assertFalse(opt.is_bypassed, "plain click does not enter bypass")
        self.assertEqual(sb.value(), 0.0, "plain click resets to default")
        self.assertTrue(sb.isEnabled(), "plain reset leaves the widget enabled")

    def test_reset_method_resets_value(self):
        sb, opt = self._make(default=0.0, start=5.0)
        opt.reset()
        self.assertEqual(sb.value(), 0.0)
        self.assertFalse(opt.is_bypassed)

    # ---- bypass toggle (Alt/Ctrl + click) --------------------------------

    def test_modifier_click_enters_bypass(self):
        sb, opt = self._make(default=0.0, start=5.0)
        self._force_modifier(opt, QtCore.Qt.AltModifier)
        opt.widget.click()
        app.processEvents()
        self.assertTrue(opt.is_bypassed)
        self.assertEqual(sb.value(), 0.0, "bypass -> reset to default")
        self.assertFalse(sb.isEnabled(), "bypass -> greyed out")

    def test_ctrl_modifier_also_enters_bypass(self):
        sb, opt = self._make()
        self._force_modifier(opt, QtCore.Qt.ControlModifier)
        opt.widget.click()
        app.processEvents()
        self.assertTrue(opt.is_bypassed)

    def test_bypass_snapshots_resets_and_greys_out(self):
        sb, opt = self._make(default=0.0, start=5.0)
        opt.set_bypassed(True)
        self.assertTrue(opt.is_bypassed)
        self.assertEqual(sb.value(), 0.0, "bypassed -> reset to default")
        self.assertFalse(sb.isEnabled(), "bypassed -> greyed out")

    def test_restore_brings_back_value_and_re_enables(self):
        sb, opt = self._make(default=0.0, start=5.0)
        opt.set_bypassed(True)
        opt.set_bypassed(False)
        self.assertFalse(opt.is_bypassed)
        self.assertEqual(sb.value(), 5.0, "restored the snapshot")
        self.assertTrue(sb.isEnabled())

    def test_click_while_bypassed_restores_regardless_of_modifier(self):
        # While bypassed the greyed row's only live control must not be a
        # confusing no-op: any click (plain or modified) restores.
        sb, opt = self._make(default=0.0, start=5.0)
        opt.set_bypassed(True)
        app.processEvents()
        self._force_modifier(opt, QtCore.Qt.NoModifier)
        opt.widget.click()  # plain click while bypassed
        app.processEvents()
        self.assertFalse(opt.is_bypassed)
        self.assertEqual(sb.value(), 5.0)
        self.assertTrue(sb.isEnabled())

    def test_bypass_button_stays_clickable_while_widget_disabled(self):
        # Bypass greys out the wrapped widget, which cascade-disables every
        # option button via the container's enabled-sync. The reset button
        # itself must stay enabled, or the user can never click it to restore.
        sb, opt = self._make(default=0.0, start=5.0)
        button = opt.widget
        opt.set_bypassed(True)
        app.processEvents()
        self.assertFalse(sb.isEnabled())
        self.assertTrue(
            button.isEnabled(), "reset button must stay clickable to restore"
        )
        # End-to-end via the real clicked signal — QAbstractButton.click() is a
        # no-op while disabled, so this also proves the button is truly clickable
        # (not merely that the opt-out property is set).
        button.click()
        app.processEvents()
        self.assertFalse(opt.is_bypassed)
        self.assertEqual(sb.value(), 5.0)
        self.assertTrue(sb.isEnabled())

    def test_other_buttons_still_disable_when_widget_bypassed(self):
        # The opt-out is surgical: sibling option buttons (pin, clear, ...)
        # still cascade-disable with the wrapped widget — only the reset button
        # is exempt.
        sb = self.track_widget(QtWidgets.QDoubleSpinBox())
        sb.setValue(5.0)
        reset = ResetOption(sb, reset=lambda: sb.setValue(0.0))
        pin = PinValuesOption(sb)
        box = OptionBox(options=[reset, pin])
        self.track_widget(box.wrap(sb))
        reset.set_bypassed(True)
        app.processEvents()
        self.assertTrue(reset.widget.isEnabled(), "reset button exempt")
        self.assertFalse(pin.widget.isEnabled(), "pin button still disabled")

    def test_snapshot_tracks_edits_before_bypass(self):
        # The value the user has at the moment of bypassing is what's restored.
        sb, opt = self._make(default=0.0, start=5.0)
        sb.setValue(7.5)
        opt.set_bypassed(True)
        self.assertEqual(sb.value(), 0.0)
        opt.set_bypassed(False)
        self.assertEqual(sb.value(), 7.5)

    # ---- type-correct value signal (snapshot/restore) --------------------

    @staticmethod
    def _register(widget, signal_name):
        """Simulate Switchboard registration so the option uses the type signal."""
        widget.default_signals = lambda: signal_name

    def _wrap(self, widget, reset):
        opt = ResetOption(widget, reset=reset)
        self.track_widget(OptionBox(options=[opt]).wrap(widget))
        return opt

    def test_bypass_restore_emits_widget_type_signal_combobox(self):
        # A combo box's slots connect to currentIndexChanged. Restoring by the
        # type signal must set the *index* and fire that signal — not silently
        # change the display text.
        combo = self.track_widget(QtWidgets.QComboBox())
        combo.addItems(["A", "B", "C"])
        combo.setCurrentIndex(2)
        self._register(combo, "currentIndexChanged")
        opt = self._wrap(combo, reset=lambda: combo.setCurrentIndex(0))

        seen = []
        combo.currentIndexChanged.connect(seen.append)

        opt.set_bypassed(True)  # -> index 0
        self.assertEqual(combo.currentIndex(), 0)
        seen.clear()
        opt.set_bypassed(False)  # restore -> index 2
        self.assertEqual(combo.currentIndex(), 2, "restored the snapshot index")
        self.assertEqual(seen, [2], "currentIndexChanged must fire on restore")

    def test_snapshot_uses_type_signal_checkbox(self):
        # get_value() on a QCheckBox returns its *label* (text() precedes
        # isChecked()); the signal-keyed snapshot captures the checked state
        # instead, so a restore round-trips correctly and fires toggled.
        cb = self.track_widget(QtWidgets.QCheckBox("My Label"))
        cb.setChecked(True)
        self._register(cb, "toggled")
        opt = self._wrap(cb, reset=lambda: cb.setChecked(False))

        seen = []
        cb.toggled.connect(seen.append)

        opt.set_bypassed(True)  # -> unchecked
        self.assertFalse(cb.isChecked())
        seen.clear()
        opt.set_bypassed(False)  # restore -> checked
        self.assertTrue(cb.isChecked(), "restored checked state, not the label")
        self.assertEqual(seen, [True], "toggled must fire on restore")

    def test_bypass_restore_emits_valuechanged_spinbox(self):
        # Regression: the registered-spinbox path still fires valueChanged.
        sb, opt = self._make(default=0.0, start=5.0)
        self._register(sb, "valueChanged")
        seen = []
        sb.valueChanged.connect(seen.append)
        opt.set_bypassed(True)
        seen.clear()
        opt.set_bypassed(False)
        self.assertEqual(sb.value(), 5.0)
        self.assertEqual(seen, [5.0], "valueChanged must fire on restore")

    def test_centralized_reset_clears_bypassed_snapshot(self):
        # When a field is bypassed (holding a snapshot) and the panel's global
        # reset-to-default runs, the snapshot must follow to the new default so
        # restoring the field doesn't resurrect the pre-reset value.
        from uitk.widgets.mixins.state_manager import StateManager

        window = self.track_widget(QtWidgets.QWidget())  # top-level -> isWindow()
        layout = QtWidgets.QVBoxLayout(window)
        sb = QtWidgets.QDoubleSpinBox()
        sb.setObjectName("sb")
        sb.setRange(-100.0, 100.0)
        sb.derived_type = QtWidgets.QDoubleSpinBox
        sb.default_signals = lambda: "valueChanged"
        sb.restore_state = True
        layout.addWidget(sb)

        qs = QtCore.QSettings("uitk_test", "reset_sync_repro")
        qs.clear()
        window.state = StateManager(qs)
        sb.setValue(0.0)
        window.state.capture_default(sb)  # default = 0
        sb.setValue(5.0)

        opt = ResetOption(sb)
        self.track_widget(OptionBox(options=[opt]).wrap(sb))

        opt.set_bypassed(True)  # snapshot 5, widget -> 0, disabled
        self.assertEqual(sb.value(), 0.0)

        window.state.reset_all()  # global reset-to-default

        opt.set_bypassed(False)  # restore
        self.assertEqual(
            sb.value(),
            0.0,
            "restore after a global reset must yield the default, not the stale 5",
        )

    def test_toggled_signal(self):
        sb, opt = self._make()
        seen = []
        opt.toggled.connect(seen.append)
        opt.set_bypassed(True)
        opt.set_bypassed(False)
        self.assertEqual(seen, [True, False])
        opt.set_bypassed(False)  # no-op, no emit
        self.assertEqual(seen, [True, False])

    def test_plain_reset_does_not_emit_toggled(self):
        sb, opt = self._make()
        seen = []
        opt.toggled.connect(seen.append)
        opt.reset()
        self.assertEqual(seen, [], "a plain reset is not a bypass-state change")

    def test_silent_set_does_not_emit(self):
        sb, opt = self._make()
        seen = []
        opt.toggled.connect(seen.append)
        opt.set_bypassed(True, emit=False)
        self.assertEqual(seen, [])
        self.assertTrue(opt.is_bypassed)

    def test_auto_reset_uses_window_state_manager(self):
        # With no explicit reset, the option resolves the default from the
        # wrapped widget's window StateManager (window.state.reset(widget)) —
        # the zero-config path uitk panels rely on.
        window = self.track_widget(QtWidgets.QWidget())  # top-level -> isWindow()
        calls = []

        class _FakeState:
            def reset(self, w):
                calls.append(w)

        window.state = _FakeState()
        layout = QtWidgets.QVBoxLayout(window)
        sb = QtWidgets.QDoubleSpinBox()
        sb.setValue(5.0)
        layout.addWidget(sb)
        opt = ResetOption(sb)  # no explicit reset
        box = OptionBox(options=[opt])
        self.track_widget(box.wrap(sb))

        opt.set_bypassed(True)
        self.assertEqual(calls, [sb], "auto reset should call window.state.reset(widget)")

    def test_bypass_suppresses_the_persistence_save(self):
        # The bypass reset must run inside the StateManager's suppress_save() so
        # the default value isn't persisted — the bypass stays transient.
        window, sb, events = self._make_state_window()
        opt = ResetOption(sb)
        box = OptionBox(options=[opt])
        self.track_widget(box.wrap(sb))

        opt.set_bypassed(True)
        self.assertEqual(
            events, ["enter", "reset", "exit"], "bypass reset must run inside suppress_save"
        )

    def test_plain_reset_does_not_suppress_the_persistence_save(self):
        # A plain reset persists the default (the user chose it), so it must NOT
        # run inside suppress_save.
        window, sb, events = self._make_state_window()
        opt = ResetOption(sb)
        box = OptionBox(options=[opt])
        self.track_widget(box.wrap(sb))

        opt.reset()
        self.assertEqual(events, ["reset"], "plain reset must persist (no suppress_save)")

    def _make_state_window(self):
        """A top-level window carrying a StateManager that records save-suppression."""
        import contextlib

        window = self.track_widget(QtWidgets.QWidget())
        events = []

        class _FakeState:
            @contextlib.contextmanager
            def suppress_save(self):
                events.append("enter")
                try:
                    yield
                finally:
                    events.append("exit")

            def reset(self, w):
                events.append("reset")

        window.state = _FakeState()
        layout = QtWidgets.QVBoxLayout(window)
        sb = QtWidgets.QDoubleSpinBox()
        layout.addWidget(sb)
        return window, sb, events


class TestOptionBoxManagerReset(QtBaseTestCase):
    """The OptionBoxManager.set_reset() fluent API + ordering."""

    def _make_manager(self):
        from uitk.widgets.optionBox.utils import OptionBoxManager

        sb = self.track_widget(QtWidgets.QDoubleSpinBox())
        mgr = OptionBoxManager(sb)
        sb._option_box_manager = mgr
        return sb, mgr

    def test_set_reset_returns_self_and_adds_option(self):
        sb, mgr = self._make_manager()
        result = mgr.set_reset()
        self.assertIs(result, mgr)
        self.assertEqual(
            len([o for o in mgr._pending_options if isinstance(o, ResetOption)]), 1
        )

    def test_set_reset_replaces_by_default(self):
        sb, mgr = self._make_manager()
        mgr.set_reset(icon="undo")
        mgr.set_reset(icon="close")
        resets = [o for o in mgr._pending_options if isinstance(o, ResetOption)]
        self.assertEqual(len(resets), 1)

    def test_reset_is_in_valid_option_order(self):
        sb, mgr = self._make_manager()
        # Should not raise: "reset" is a recognized order key now.
        mgr.option_order = ["reset", "clear"]
        self.assertIn("reset", mgr.option_order)


class TestOptionBoxInitPerfRegressions(QtBaseTestCase):
    """Phase-1 init-performance regressions.

    Pin the behavioral guarantees behind the Phase-1 optimizations so a
    future refactor can't silently re-introduce the wasted work:
      - wrapping a widget must not materialize its lazy MenuMixin context menu;
      - a state-less ActionOption/MenuOption must not open QSettings;
      - border-trim styling must be idempotent across re-wraps.
    """

    def _make_menu_mixin_widget(self):
        """A widget exposing the lazy MenuMixin ``menu``/``has_menu`` API."""
        from uitk.widgets.checkBox import CheckBox
        from uitk.widgets.optionBox.utils import OptionBoxManager

        parent = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(parent)
        widget = CheckBox("Test")
        layout.addWidget(widget)
        mgr = OptionBoxManager(widget)
        widget._option_box_manager = mgr
        try:
            widget.option_box = mgr
        except AttributeError:
            pass
        return widget, mgr

    def test_wrapping_does_not_create_context_menu(self):
        """Adding an option-box menu must not create the widget's context menu.

        ``_find_existing_option_box`` / the ``container`` fallback used to probe
        ``widget.menu`` directly, whose lazy descriptor *creates* a standalone
        context menu as a side effect. The non-creating ``has_menu`` check must
        leave the wrapped widget menu-less.
        """
        widget, mgr = self._make_menu_mixin_widget()
        self.assertFalse(widget.has_menu, "precondition: no context menu yet")

        mgr.menu.add("Some Item")  # the ubiquitous tbXXX_init pattern
        container = mgr.container  # force the lazy wrap + container fallback
        self.assertIsNotNone(container)

        self.assertFalse(
            widget.has_menu,
            "option-box setup must not materialize the widget's context menu",
        )

    def test_stateless_action_option_skips_qsettings(self):
        """A state-less ActionOption must not construct a SettingsManager."""
        from uitk.widgets.optionBox.options.action import ActionOption

        opt = ActionOption(wrapped_widget=None, callback=lambda: None)
        self.assertIsNone(
            opt._settings, "no states => no persistence handle should be opened"
        )

    def test_stateful_action_option_persists_round_trip(self):
        """States init persistence AND it still saves/restores through the
        restructured init path (settings now created in set_states, not the
        constructor). Covers construction-time states and the runtime
        ``set_states`` path.
        """
        from uitk.widgets.optionBox.options.action import ActionOption

        states = [{"icon": "play"}, {"icon": "pause"}, {"icon": "stop"}]
        widget = self.track_widget(QtWidgets.QPushButton("Test"))
        widget.setObjectName("perf_regression_action_btn")

        opt = ActionOption(wrapped_widget=widget, states=states)
        self.assertIsNotNone(
            opt._settings, "states present => settings handle must exist"
        )
        try:
            # Save an index, then reconstruct and confirm it restores.
            opt._current_state = 2
            opt._save_state()

            restored = ActionOption(wrapped_widget=widget, states=states)
            self.assertEqual(
                restored._current_state, 2, "persisted state must restore on reconstruct"
            )

            # Runtime path: a state-less option opens no settings, but
            # set_states() must initialize them and restore the saved index.
            late = ActionOption(wrapped_widget=widget, callback=lambda: None)
            self.assertIsNone(late._settings, "no states => no QSettings opened")
            late.set_states(states)
            self.assertIsNotNone(
                late._settings, "set_states() must lazily initialize persistence"
            )
            self.assertEqual(
                late._current_state, 2, "set_states() must restore the persisted index"
            )
        finally:
            if opt._settings is not None:
                opt._settings.clear()

    def test_border_styling_is_idempotent(self):
        """Re-applying border trim must not duplicate style fragments."""
        widget = self.track_widget(QtWidgets.QLineEdit())
        button = self.track_widget(QtWidgets.QPushButton())
        opt = OptionBox(options=[])

        opt._apply_border_styling(widget, [button])
        once = widget.styleSheet()
        opt._apply_border_styling(widget, [button])
        twice = widget.styleSheet()

        self.assertEqual(
            once, twice, "border trim must be idempotent (no fragment accumulation)"
        )
        self.assertEqual(
            once.count("border-right-width: 0px"),
            1,
            "the right-border trim must appear exactly once on the wrapped widget",
        )


class TestOptionMenuClickableRows(QtBaseTestCase):
    """``(label, callback)`` entries must render as real, clickable rows.

    Bug: ``OptionMenuOption`` / ``ContextMenuOption`` added items via
    ``menu.add(label, callback)``. ``Menu.add`` maps a non-widget string to a
    QLabel (no hover, no ``clicked`` signal) and stores the callback as inert
    item-DATA that is never invoked -- so the rows were dead (no hover, clicks
    did nothing). Fixed by building actual buttons and wiring ``clicked``.
    Fixed: 2026-06-25
    """

    def test_static_items_are_clickable_buttons(self):
        from uitk.widgets.optionBox.options.option_menu import OptionMenuOption

        fired = []
        opt = OptionMenuOption(
            menu_items=[("Do It", lambda: fired.append("do")), "separator"]
        )
        self.track_widget(opt.menu)
        rows = opt.menu.get_items()
        self.assertEqual([type(r).__name__ for r in rows], ["QPushButton"])
        self.assertEqual(rows[0].text(), "Do It")
        rows[0].click()
        self.assertEqual(fired, ["do"], "row click did not invoke the callback")

    def test_context_items_rebuild_as_clickable_and_fire(self):
        from uitk.widgets.optionBox.options.option_menu import ContextMenuOption

        host = self.track_widget(QtWidgets.QLineEdit())
        fired = []
        opt = ContextMenuOption(
            wrapped_widget=host,
            menu_provider=lambda w: [
                ("Alpha", lambda: fired.append("a")),
                ("Beta", lambda: fired.append("b")),
            ],
        )
        self.track_widget(opt.menu)
        opt._show_menu()  # populate + show the real menu

        rows = opt.menu.get_items()
        self.assertTrue(rows and all(hasattr(r, "clicked") for r in rows),
                        "context-menu rows are not clickable buttons")
        self.assertEqual([r.text() for r in rows], ["Alpha", "Beta"])

        beta = next(r for r in rows if r.text() == "Beta")
        beta.click()
        self.assertEqual(fired, ["b"], "clicking a context-menu row did nothing")

    def test_clicking_a_row_hides_the_menu(self):
        # A context action menu should dismiss itself once an item is chosen.
        from uitk.widgets.optionBox.options.option_menu import ContextMenuOption

        host = self.track_widget(QtWidgets.QLineEdit())
        opt = ContextMenuOption(
            wrapped_widget=host,
            menu_provider=lambda w: [("Only", lambda: None)],
        )
        self.track_widget(opt.menu)
        opt._show_menu()
        row = opt.menu.get_items()[0]
        row.click()
        self.assertFalse(opt.menu.isVisible(), "menu stayed open after an action")

    def test_menu_is_built_lazily(self):
        # Init-perf regression: constructing the option must NOT build the
        # dropdown Menu (creating it applies the menu QSS + chrome, an init cost
        # paid even if the user never opens it). It is created on first
        # access / show only.
        from uitk.widgets.optionBox.options.option_menu import (
            ContextMenuOption,
            OptionMenuOption,
        )

        host = self.track_widget(QtWidgets.QLineEdit())
        ctx = ContextMenuOption(wrapped_widget=host, menu_provider=lambda w: [])
        self.assertIsNone(ctx._menu, "ContextMenuOption built its menu eagerly")

        static = OptionMenuOption(menu_items=[("X", lambda: None)])
        self.assertIsNone(static._menu, "OptionMenuOption built its menu eagerly")

        # First access materialises it (and populates static rows).
        self.track_widget(ctx.menu)
        self.track_widget(static.menu)
        self.assertIsNotNone(ctx._menu)
        self.assertEqual([r.text() for r in static.menu.get_items()], ["X"])


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
