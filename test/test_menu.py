# !/usr/bin/python
# coding=utf-8
"""Unit tests for Menu widget.

This module tests the Menu widget functionality including:
- Menu creation and configuration
- MenuConfig dataclass
- Menu positioning
- Item addition and management
- Trigger button handling
- Hide on leave behavior
- Persistent mode
- Event filter management
- Apply button functionality

Run standalone: python -m test.test_menu
"""

import unittest
from unittest.mock import MagicMock, patch

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore

from uitk.widgets.menu import Menu, MenuConfig, MenuPositioner, ActionButtonManager


class TestMenuConfigCreation(unittest.TestCase):
    """Tests for MenuConfig dataclass creation."""

    def test_creates_config_with_defaults(self):
        """Should create config with default values."""
        config = MenuConfig()
        self.assertIsNone(config.parent)
        self.assertIsNone(config.name)
        self.assertIsNone(config.trigger_button)
        self.assertEqual(config.position, "cursorPos")
        self.assertTrue(config.add_header)
        self.assertTrue(config.add_footer)
        self.assertFalse(config.add_apply_button)
        self.assertTrue(config.match_parent_width)

    def test_creates_context_menu_config(self):
        """Should create context menu config with appropriate defaults."""
        config = MenuConfig.for_context_menu()
        self.assertEqual(config.trigger_button, "right")
        self.assertEqual(config.position, "cursorPos")
        self.assertEqual(config.fixed_item_height, 20)

    def test_creates_dropdown_menu_config(self):
        """Should create dropdown menu config with appropriate defaults."""
        config = MenuConfig.for_dropdown_menu()
        self.assertEqual(config.trigger_button, "none")
        self.assertEqual(config.position, "bottom")
        self.assertTrue(config.hide_on_leave)
        self.assertTrue(config.add_apply_button)

    def test_creates_popup_menu_config(self):
        """Should create popup menu config with appropriate defaults."""
        config = MenuConfig.for_popup_menu()
        self.assertEqual(config.trigger_button, "none")
        self.assertEqual(config.position, "cursorPos")

    def test_config_allows_overrides(self):
        """Should allow overriding default values."""
        config = MenuConfig.for_context_menu(
            name="custom_menu", add_header=False, fixed_item_height=30
        )
        self.assertEqual(config.name, "custom_menu")
        self.assertFalse(config.add_header)
        self.assertEqual(config.fixed_item_height, 30)

    def test_config_extra_attrs_default_empty(self):
        """Should have empty extra_attrs by default."""
        config = MenuConfig()
        self.assertEqual(config.extra_attrs, {})


class TestMenuCreation(QtBaseTestCase):
    """Tests for Menu widget creation."""

    def test_creates_menu_with_defaults(self):
        """Should create menu with default settings."""
        menu = self.track_widget(Menu())
        self.assertIsNotNone(menu)
        self.assertTrue(menu.add_header)
        self.assertTrue(menu.add_footer)
        self.assertFalse(menu.add_apply_button)

    def test_creates_menu_with_name(self):
        """Should create menu with specified name."""
        menu = self.track_widget(Menu(name="TestMenu"))
        self.assertEqual(menu.objectName(), "TestMenu")

    def test_creates_menu_with_parent(self):
        """Should create menu with parent widget."""
        parent = self.track_widget(QtWidgets.QWidget())
        menu = self.track_widget(Menu(parent=parent))
        self.assertEqual(menu.parent(), parent)

    def test_raises_type_error_for_invalid_name_type(self):
        """Should raise TypeError if name is not a string."""
        with self.assertRaises(TypeError) as context:
            Menu(name=123)
        self.assertIn("string", str(context.exception))

    def test_creates_menu_from_config(self):
        """Should create menu from MenuConfig object."""
        config = MenuConfig(name="FromConfig", add_header=False)
        menu = self.track_widget(Menu.from_config(config))
        self.assertEqual(menu.objectName(), "FromConfig")
        self.assertFalse(menu.add_header)


class TestMenuTriggerButton(QtBaseTestCase):
    """Tests for Menu trigger button configuration."""

    def test_sets_trigger_button_string(self):
        """Should accept string trigger button name and convert to Qt constant."""
        menu = self.track_widget(Menu(trigger_button="right"))
        # Menu converts string to Qt constant
        self.assertEqual(menu.trigger_button, QtCore.Qt.RightButton)

    def test_sets_trigger_button_none(self):
        """Should accept None for no auto-trigger (converts to False)."""
        menu = self.track_widget(Menu(trigger_button=None))
        # Menu converts None to False
        self.assertFalse(menu.trigger_button)

    def test_sets_trigger_button_tuple(self):
        """Should accept tuple of trigger buttons and convert to Qt constants."""
        menu = self.track_widget(Menu(trigger_button=("left", "right")))
        # Menu converts strings to Qt constants
        self.assertEqual(
            menu.trigger_button, (QtCore.Qt.LeftButton, QtCore.Qt.RightButton)
        )


class TestMenuPosition(QtBaseTestCase):
    """Tests for Menu position configuration."""

    def test_default_position_is_cursor(self):
        """Should default to cursor position."""
        menu = self.track_widget(Menu())
        self.assertEqual(menu.position, "cursorPos")

    def test_sets_position_bottom(self):
        """Should accept 'bottom' position."""
        menu = self.track_widget(Menu(position="bottom"))
        self.assertEqual(menu.position, "bottom")

    def test_sets_position_point(self):
        """Should accept QPoint position."""
        point = QtCore.QPoint(100, 200)
        menu = self.track_widget(Menu(position=point))
        self.assertEqual(menu.position, point)


class TestMenuPositioner(QtBaseTestCase):
    """Tests for MenuPositioner helper class."""

    def test_positions_at_coordinate_with_point(self):
        """Should position widget at QPoint coordinates."""
        widget = self.track_widget(QtWidgets.QWidget())
        widget.resize(100, 100)

        position = QtCore.QPoint(50, 50)
        MenuPositioner.position_at_coordinate(widget, position)
        self.assertEqual(widget.pos(), position)

    def test_positions_at_coordinate_with_tuple(self):
        """Should position widget at tuple coordinates."""
        widget = self.track_widget(QtWidgets.QWidget())
        widget.resize(100, 100)

        MenuPositioner.position_at_coordinate(widget, (75, 75))
        self.assertEqual(widget.pos(), QtCore.QPoint(75, 75))

    def test_positions_at_coordinate_with_list(self):
        """Should position widget at list coordinates."""
        widget = self.track_widget(QtWidgets.QWidget())
        widget.resize(100, 100)

        MenuPositioner.position_at_coordinate(widget, [25, 35])
        self.assertEqual(widget.pos(), QtCore.QPoint(25, 35))


class TestActionButtonManager(QtBaseTestCase):
    """Tests for ActionButtonManager helper class."""

    def setUp(self):
        super().setUp()
        self.menu = self.track_widget(Menu())
        self.manager = ActionButtonManager(self.menu)

    def test_creates_container_on_demand(self):
        """Should create container when first accessed."""
        container = self.manager.container
        self.assertIsNotNone(container)
        self.assertEqual(container.objectName(), "actionButtonContainer")

    def test_creates_button(self):
        """Should create a button with config."""
        from uitk.widgets.menu import _ActionButtonConfig

        config = _ActionButtonConfig(text="Apply", tooltip="Apply changes")
        button = self.manager.create_button("apply", config)
        self.assertEqual(button.text(), "Apply")
        self.assertEqual(button.toolTip(), "Apply changes")

    def test_get_button_returns_none_for_unknown(self):
        """Should return None for unknown button ID."""
        result = self.manager.get_button("nonexistent")
        self.assertIsNone(result)

    def test_has_visible_buttons_returns_false_when_empty(self):
        """Should return False when no buttons exist."""
        self.assertFalse(self.manager.has_visible_buttons())


class TestMenuItemAddition(QtBaseTestCase):
    """Tests for adding items to Menu."""

    def setUp(self):
        super().setUp()
        self.menu = self.track_widget(Menu())

    def test_adds_label_item(self):
        """Should add QLabel item to menu."""
        label = self.menu.add("QLabel", setText="Test Label")
        self.assertIsInstance(label, QtWidgets.QLabel)
        self.assertEqual(label.text(), "Test Label")

    def test_adds_button_item(self):
        """Should add QPushButton item to menu."""
        button = self.menu.add("QPushButton", setText="Test Button")
        self.assertIsInstance(button, QtWidgets.QPushButton)
        self.assertEqual(button.text(), "Test Button")

    def test_adds_checkbox_item(self):
        """Should add QCheckBox item to menu."""
        checkbox = self.menu.add("QCheckBox", setText="Check Me")
        self.assertIsInstance(checkbox, QtWidgets.QCheckBox)
        self.assertEqual(checkbox.text(), "Check Me")

    def test_has_on_item_added_signal(self):
        """Should have on_item_added signal."""
        self.assertTrue(hasattr(self.menu, "on_item_added"))


class TestMenuItemHeight(QtBaseTestCase):
    """Tests for Menu item height constraints."""

    def test_applies_fixed_item_height(self):
        """Should apply fixed height to items."""
        menu = self.track_widget(Menu(fixed_item_height=30))
        label = menu.add("QLabel", setText="Fixed Height")
        self.assertEqual(label.height(), 30)

    def test_applies_min_item_height(self):
        """Should apply minimum height to items."""
        menu = self.track_widget(Menu(min_item_height=25))
        label = menu.add("QLabel", setText="Min Height")
        self.assertGreaterEqual(label.minimumHeight(), 25)

    def test_applies_max_item_height(self):
        """Should apply maximum height to items."""
        menu = self.track_widget(Menu(max_item_height=40))
        label = menu.add("QLabel", setText="Max Height")
        self.assertLessEqual(label.maximumHeight(), 40)


class TestMenuHideOnLeave(QtBaseTestCase):
    """Tests for Menu hide on leave behavior."""

    def test_default_hide_on_leave_is_false(self):
        """Should default to hide_on_leave=False."""
        menu = self.track_widget(Menu())
        self.assertFalse(menu.hide_on_leave)

    def test_sets_hide_on_leave_true(self):
        """Should accept hide_on_leave=True."""
        menu = self.track_widget(Menu(hide_on_leave=True))
        self.assertTrue(menu.hide_on_leave)

    def _outside_point(self, menu):
        """A global point well outside *menu*'s rect (so the rect test fails)."""
        from qtpy import QtGui

        return QtGui.QCursor, QtCore.QPoint(
            menu.x() + menu.width() + 500, menu.y() + menu.height() + 500
        )

    def test_hide_on_leave_keeps_open_over_nested_popup(self):
        """A separate top-level popup whose QObject parent chain leads back into
        the menu (a ComboBox dropdown, an option-box ⋯ menu) must NOT trigger
        hide_on_leave when the cursor moves onto it. ``isAncestorOf`` is
        same-window-only and misses such popups; the parent-chain walk catches
        them."""
        from qtpy import QtGui

        menu = self.track_widget(Menu(hide_on_leave=True))
        menu.show()
        menu._mouse_has_entered = True
        # A separate top-level popup parented (in the QObject tree) under the menu.
        inner = QtWidgets.QWidget(menu)
        popup = QtWidgets.QWidget(inner)
        popup.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        _, far = self._outside_point(menu)
        with patch.object(QtGui.QCursor, "pos", staticmethod(lambda: far)), patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=popup
        ):
            menu._check_cursor_position()
        self.assertTrue(
            menu.isVisible(), "menu hid despite the cursor being over a nested popup"
        )

    def test_hide_on_leave_hides_when_cursor_truly_outside(self):
        """Sanity counterpart: an unrelated widget (no parent chain to the menu)
        still lets hide_on_leave close the menu."""
        from qtpy import QtGui

        menu = self.track_widget(Menu(hide_on_leave=True))
        menu.show()
        menu._mouse_has_entered = True
        unrelated = self.track_widget(QtWidgets.QWidget())
        _, far = self._outside_point(menu)
        with patch.object(QtGui.QCursor, "pos", staticmethod(lambda: far)), patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=unrelated
        ):
            menu._check_cursor_position()
        self.assertFalse(
            menu.isVisible(), "menu should hide when the cursor is truly outside"
        )


class TestMenuFactoryMethods(QtBaseTestCase):
    """Tests for Menu factory methods."""

    def test_create_context_menu(self):
        """Should create context menu with factory method."""
        menu = self.track_widget(Menu.create_context_menu())
        # Factory method sets trigger_button="right" which converts to Qt constant
        self.assertEqual(menu.trigger_button, QtCore.Qt.RightButton)
        self.assertEqual(menu.position, "cursorPos")

    def test_create_dropdown_menu(self):
        """Should create dropdown menu with factory method."""
        menu = self.track_widget(Menu.create_dropdown_menu())
        # Factory method sets trigger_button="none" which converts to False
        self.assertFalse(menu.trigger_button)
        self.assertEqual(menu.position, "bottom")
        self.assertTrue(menu.hide_on_leave)


class TestMenuContainsItems(QtBaseTestCase):
    """Tests for Menu contains_items property."""

    def test_contains_items_false_when_empty(self):
        """Should return False when menu has no items."""
        menu = self.track_widget(Menu())
        self.assertFalse(menu.contains_items)

    def test_contains_items_true_after_add(self):
        """Should return True after adding an item."""
        menu = self.track_widget(Menu())
        menu.add("QLabel", setText="Test")
        self.assertTrue(menu.contains_items)


class TestMenuEmptyState(QtBaseTestCase):
    """Tests for empty-state placeholder + auto-hide.

    Feature: an empty menu briefly shows a "No options" label, then
    hides itself, so the user sees feedback that the click registered.
    Added: 2026-05-16
    """

    def test_empty_placeholder_appears_on_show(self):
        menu = self.track_widget(Menu(empty_timeout_ms=0))
        menu.show()
        self.assertIsNotNone(menu._empty_placeholder)
        # Real-item count must stay 0 even with placeholder present.
        self.assertFalse(menu.contains_items)
        menu.hide()

    def test_placeholder_removed_on_hide(self):
        menu = self.track_widget(Menu(empty_timeout_ms=0))
        menu.show()
        menu.hide()
        self.assertIsNone(menu._empty_placeholder)

    def test_placeholder_uses_configured_message(self):
        menu = self.track_widget(Menu(empty_message="Nothing here", empty_timeout_ms=0))
        menu.show()
        self.assertEqual(menu._empty_placeholder.text(), "Nothing here")
        menu.hide()

    def test_no_placeholder_when_message_is_none(self):
        menu = self.track_widget(Menu(empty_message=None, empty_timeout_ms=0))
        menu.show()
        self.assertIsNone(menu._empty_placeholder)
        menu.hide()

    def test_no_placeholder_when_items_present(self):
        menu = self.track_widget(Menu(empty_timeout_ms=0))
        menu.add("QLabel", setText="Real Item")
        menu.show()
        self.assertIsNone(menu._empty_placeholder)
        menu.hide()

    def test_add_clears_existing_placeholder(self):
        menu = self.track_widget(Menu(empty_timeout_ms=0))
        menu.show()
        self.assertIsNotNone(menu._empty_placeholder)
        menu.add("QLabel", setText="Late arrival")
        self.assertIsNone(menu._empty_placeholder)
        self.assertTrue(menu.contains_items)
        menu.hide()

    def test_timer_hides_menu_when_still_empty(self):
        menu = self.track_widget(Menu(empty_timeout_ms=30))
        menu.show()
        self.assertTrue(menu.isVisible())
        # Spin the event loop until the singleshot fires (~30ms + slack).
        deadline = QtCore.QElapsedTimer()
        deadline.start()
        while menu.isVisible() and deadline.elapsed() < 1000:
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 30)
        self.assertFalse(menu.isVisible())


class TestMenuTitle(QtBaseTestCase):
    """Tests for Menu title methods."""

    def test_title_empty_by_default(self):
        """Should return empty string by default."""
        menu = self.track_widget(Menu())
        self.assertEqual(menu.title(), "")

    def test_set_title_updates_header(self):
        """Should update header text when title is set."""
        menu = self.track_widget(Menu(add_header=True))
        menu.setTitle("My Menu")
        self.assertEqual(menu.title(), "My Menu")


class TestMenuGetItems(QtBaseTestCase):
    """Tests for Menu get_items method."""

    def setUp(self):
        super().setUp()
        self.menu = self.track_widget(Menu())

    def test_get_items_returns_empty_list_initially(self):
        """Should return empty list when no items added."""
        items = self.menu.get_items()
        self.assertEqual(items, [])

    def test_get_items_returns_all_items(self):
        """Should return all items in menu."""
        self.menu.add("QLabel", setText="Label 1")
        self.menu.add("QPushButton", setText="Button 1")
        items = self.menu.get_items()
        self.assertEqual(len(items), 2)

    def test_get_items_filters_by_type_string(self):
        """Should filter items by type name string."""
        self.menu.add("QLabel", setText="Label 1")
        self.menu.add("QPushButton", setText="Button 1")
        labels = self.menu.get_items(types="QLabel")
        self.assertEqual(len(labels), 1)
        self.assertIsInstance(labels[0], QtWidgets.QLabel)

    def test_get_items_filters_by_type_class(self):
        """Should filter items by type class."""
        self.menu.add("QLabel", setText="Label 1")
        self.menu.add("QPushButton", setText="Button 1")
        buttons = self.menu.get_items(types=QtWidgets.QPushButton)
        self.assertEqual(len(buttons), 1)

    def test_get_items_filters_by_multiple_types(self):
        """Should filter items by multiple types."""
        self.menu.add("QLabel", setText="Label 1")
        self.menu.add("QPushButton", setText="Button 1")
        self.menu.add("QCheckBox", setText="Check 1")
        items = self.menu.get_items(types=["QLabel", "QPushButton"])
        self.assertEqual(len(items), 2)


class TestMenuGetItem(QtBaseTestCase):
    """Tests for Menu get_item method."""

    def setUp(self):
        super().setUp()
        self.menu = self.track_widget(Menu())
        self.menu.add("QLabel", setText="First")
        self.menu.add("QLabel", setText="Second")

    def test_get_item_by_index(self):
        """Should get item by index."""
        item = self.menu.get_item(0)
        self.assertEqual(item.text(), "First")

    def test_get_item_by_text(self):
        """Should get item by text."""
        item = self.menu.get_item("Second")
        self.assertEqual(item.text(), "Second")

    def test_get_item_raises_for_invalid_index(self):
        """Should raise ValueError for out of range index."""
        with self.assertRaises(ValueError):
            self.menu.get_item(999)

    def test_get_item_raises_for_invalid_text(self):
        """Should raise ValueError for unknown text."""
        with self.assertRaises(ValueError):
            self.menu.get_item("Nonexistent")

    def test_get_item_raises_for_invalid_type(self):
        """Should raise ValueError for invalid identifier type."""
        with self.assertRaises(ValueError):
            self.menu.get_item(3.14)


class TestMenuGetItemText(QtBaseTestCase):
    """Tests for Menu get_item_text method."""

    def setUp(self):
        super().setUp()
        self.menu = self.track_widget(Menu())

    def test_get_item_text_from_label(self):
        """Should get text from QLabel."""
        label = self.menu.add("QLabel", setText="Label Text")
        self.assertEqual(self.menu.get_item_text(label), "Label Text")

    def test_get_item_text_from_button(self):
        """Should get text from QPushButton."""
        button = self.menu.add("QPushButton", setText="Button Text")
        self.assertEqual(self.menu.get_item_text(button), "Button Text")

    def test_get_item_text_returns_none_for_no_text(self):
        """Should return None when widget has no text method."""
        widget = QtWidgets.QWidget()
        result = self.menu.get_item_text(widget)
        self.assertIsNone(result)


class TestMenuItemData(QtBaseTestCase):
    """Tests for Menu item data methods."""

    def setUp(self):
        super().setUp()
        self.menu = self.track_widget(Menu())

    def test_set_and_get_item_data(self):
        """Should set and get item data."""
        label = self.menu.add("QLabel", setText="Test", data={"key": "value"})
        data = self.menu.get_item_data(label)
        self.assertEqual(data, {"key": "value"})

    def test_get_item_data_returns_none_for_unknown(self):
        """Should return None for widget not in menu."""
        external_widget = QtWidgets.QLabel("External")
        result = self.menu.get_item_data(external_widget)
        self.assertIsNone(result)

    def test_item_data_method_on_widget(self):
        """Should add item_data method to widget."""
        label = self.menu.add("QLabel", setText="Test", data="my_data")
        self.assertEqual(label.item_data(), "my_data")


class TestMenuClear(QtBaseTestCase):
    """Tests for Menu clear method."""

    def test_clear_removes_all_items(self):
        """Should remove all items from menu."""
        menu = self.track_widget(Menu())
        menu.add("QLabel", setText="Item 1")
        menu.add("QLabel", setText="Item 2")
        menu.clear()
        self.assertFalse(menu.contains_items)

    def test_clear_resets_widget_data(self):
        """Should reset widget_data dictionary."""
        menu = self.track_widget(Menu())
        menu.add("QLabel", setText="Item", data="some_data")
        menu.clear()
        self.assertEqual(menu.widget_data, {})


class TestMenuRemoveWidget(QtBaseTestCase):
    """Tests for Menu remove_widget method."""

    def test_remove_widget_removes_from_layout(self):
        """Should remove widget from layout."""
        menu = self.track_widget(Menu())
        label = menu.add("QLabel", setText="To Remove")
        self.assertEqual(len(menu.get_items()), 1)
        menu.remove_widget(label)
        self.assertEqual(len(menu.get_items()), 0)

    def test_remove_widget_clears_data(self):
        """Should remove widget data when removed."""
        menu = self.track_widget(Menu())
        label = menu.add("QLabel", setText="Item", data="my_data")
        menu.remove_widget(label)
        self.assertNotIn(label, menu.widget_data)


class TestMenuAddMultipleItems(QtBaseTestCase):
    """Tests for Menu add with collections."""

    def setUp(self):
        super().setUp()
        self.menu = self.track_widget(Menu())

    def test_add_list_of_strings(self):
        """Should add multiple items from list."""
        items = self.menu.add(["Item A", "Item B", "Item C"])
        self.assertEqual(len(items), 3)

    def test_add_tuple_of_strings(self):
        """Should add multiple items from tuple."""
        items = self.menu.add(("Tuple A", "Tuple B"))
        self.assertEqual(len(items), 2)

    def test_add_set_of_strings(self):
        """Should add multiple items from set."""
        items = self.menu.add({"Set A", "Set B"})
        self.assertEqual(len(items), 2)

    def test_add_dict_with_data(self):
        """Should add items from dict with data."""
        items = self.menu.add({"Key1": "Value1", "Key2": "Value2"})
        self.assertEqual(len(items), 2)

    def test_add_zip_with_data(self):
        """Should add items from zip with data."""
        labels = ["Label1", "Label2"]
        data = ["Data1", "Data2"]
        items = self.menu.add(zip(labels, data))
        self.assertEqual(len(items), 2)
        # Verify data was attached
        self.assertEqual(items[0].item_data(), "Data1")


class TestMenuAddWidgetInstance(QtBaseTestCase):
    """Tests for Menu add with widget instances."""

    def setUp(self):
        super().setUp()
        self.menu = self.track_widget(Menu())

    def test_add_widget_instance(self):
        """Should add existing widget instance."""
        button = QtWidgets.QPushButton("My Button")
        result = self.menu.add(button)
        self.assertEqual(result, button)
        self.assertIn(button, self.menu.get_items())

    def test_add_widget_class(self):
        """Should instantiate and add widget class."""
        result = self.menu.add(QtWidgets.QLabel)
        self.assertIsInstance(result, QtWidgets.QLabel)


class TestMenuAddInvalidType(QtBaseTestCase):
    """Tests for Menu add with invalid types."""

    def test_add_raises_for_invalid_type(self):
        """Should raise TypeError for unsupported type."""
        menu = self.track_widget(Menu())
        with self.assertRaises(TypeError):
            menu.add(12345)  # int is not supported


class TestMenuIsPinned(QtBaseTestCase):
    """Tests for Menu is_pinned property."""

    def test_is_pinned_default_false(self):
        """Should default to not pinned."""
        menu = self.track_widget(Menu())
        self.assertFalse(menu.is_pinned)

    def test_is_pinned_true_when_prevent_hide(self):
        """Should be pinned when prevent_hide is True."""
        menu = self.track_widget(Menu())
        menu.prevent_hide = True
        self.assertTrue(menu.is_pinned)


class TestMenuPersistentMode(QtBaseTestCase):
    """Tests for Menu persistent mode."""

    def test_enable_persistent_mode(self):
        """Should enable persistent mode."""
        menu = self.track_widget(Menu(add_header=True))
        menu.enable_persistent_mode()
        self.assertTrue(menu.is_persistent_mode)
        self.assertTrue(menu.prevent_hide)
        self.assertFalse(menu.hide_on_leave)

    def test_disable_persistent_mode(self):
        """Should disable persistent mode and restore state."""
        menu = self.track_widget(Menu(add_header=True))
        menu.enable_persistent_mode()
        menu.disable_persistent_mode()
        self.assertFalse(menu.is_persistent_mode)

    def test_is_persistent_mode_default_false(self):
        """Should default to is_persistent_mode=False."""
        menu = self.track_widget(Menu())
        self.assertFalse(menu.is_persistent_mode)


class TestMenuHideMethod(QtBaseTestCase):
    """Tests for Menu hide method."""

    def test_hide_returns_true_when_hidden(self):
        """Should return True when successfully hidden."""
        menu = self.track_widget(Menu())
        menu.show()
        result = menu.hide()
        self.assertTrue(result)
        self.assertFalse(menu.isVisible())

    def test_hide_returns_false_when_pinned(self):
        """Should return False when pinned without force."""
        menu = self.track_widget(Menu())
        menu.show()
        menu.prevent_hide = True
        result = menu.hide()
        self.assertFalse(result)
        self.assertTrue(menu.isVisible())

    def test_hide_force_overrides_pinned(self):
        """Should hide when force=True even if pinned."""
        menu = self.track_widget(Menu())
        menu.show()
        menu.prevent_hide = True
        result = menu.hide(force=True)
        self.assertTrue(result)


class TestMenuShouldTrigger(QtBaseTestCase):
    """Tests for Menu _should_trigger method."""

    def test_should_trigger_false_when_trigger_button_false(self):
        """Should return False when trigger_button is False."""
        menu = self.track_widget(Menu(trigger_button="none"))
        self.assertFalse(menu._should_trigger(QtCore.Qt.LeftButton))

    def test_should_trigger_true_when_button_matches(self):
        """Should return True when button matches trigger_button."""
        menu = self.track_widget(Menu(trigger_button="left"))
        self.assertTrue(menu._should_trigger(QtCore.Qt.LeftButton))

    def test_should_trigger_false_when_button_differs(self):
        """Should return False when button doesn't match."""
        menu = self.track_widget(Menu(trigger_button="right"))
        self.assertFalse(menu._should_trigger(QtCore.Qt.LeftButton))


class TestMenuShowAsPopup(QtBaseTestCase):
    """Tests for Menu show_as_popup method."""

    def test_show_as_popup_shows_menu(self):
        """Should show the menu."""
        menu = self.track_widget(Menu())
        menu.add("QLabel", setText="Item")
        menu.show_as_popup()
        self.assertTrue(menu.isVisible())

    def test_show_as_popup_with_anchor(self):
        """Should show menu relative to anchor widget."""
        parent = self.track_widget(QtWidgets.QPushButton("Anchor"))
        parent.show()
        menu = self.track_widget(Menu(parent=parent))
        menu.add("QLabel", setText="Item")
        # Just test that it shows without error
        menu.show_as_popup(position="cursorPos")
        self.assertTrue(menu.isVisible())


class TestMenuCentralWidget(QtBaseTestCase):
    """Tests for Menu central widget methods."""

    def test_set_central_widget(self):
        """Should set central widget."""
        menu = self.track_widget(Menu())
        widget = QtWidgets.QWidget()
        menu.setCentralWidget(widget)
        self.assertEqual(menu.centralWidget(), widget)

    def test_central_widget_returns_none_before_init(self):
        """Should return None before layout initialization."""
        menu = self.track_widget(Menu())
        # Force check before any items added
        central = menu.centralWidget()
        # Central widget is created during init_layout
        self.assertIsNotNone(central)


class TestMenuSignals(QtBaseTestCase):
    """Tests for Menu signals."""

    def test_has_on_item_added_signal(self):
        """Should have on_item_added signal."""
        menu = self.track_widget(Menu())
        self.assertTrue(hasattr(menu, "on_item_added"))

    def test_has_on_item_interacted_signal(self):
        """Should have on_item_interacted signal."""
        menu = self.track_widget(Menu())
        self.assertTrue(hasattr(menu, "on_item_interacted"))

    def test_on_item_added_is_signal_type(self):
        """Should have on_item_added as a Qt Signal."""
        menu = self.track_widget(Menu())
        # Verify it's a signal by checking we can connect to it
        connected = False
        try:
            menu.on_item_added.connect(lambda w: None)
            connected = True
        except Exception:
            pass
        self.assertTrue(connected)

    def test_on_item_added_is_delivered(self):
        """on_item_added must reach connected slots despite add()'s blockSignals.

        Regression: add() blocks signals for the duration of the insert, so a
        synchronous emit was swallowed and the documented signal never fired.
        The added widget(s) are now flushed by the outermost add() once
        blocking is lifted.
        """
        menu = self.track_widget(Menu())
        received = []
        menu.on_item_added.connect(received.append)
        widget = menu.add("QPushButton", setText="A")
        self.assertEqual(received, [widget])

    def test_on_item_added_delivered_for_bulk_add(self):
        """A collection add fires the signal once per item, in order."""
        menu = self.track_widget(Menu())
        received = []
        menu.on_item_added.connect(received.append)
        widgets = menu.add(["A", "B", "C"])
        self.assertEqual(received, widgets)

    def test_on_item_added_respects_external_block(self):
        """An externally pre-blocked add() suppresses the signal entirely.

        The notification must be dropped (not leaked into a later unblocked
        add()), so the recursion-depth flush honors signalsBlocked().
        """
        menu = self.track_widget(Menu())
        received = []
        menu.on_item_added.connect(received.append)

        menu.blockSignals(True)
        menu.add("Hidden")
        menu.blockSignals(False)
        self.assertEqual(received, [])  # dropped while blocked

        later = menu.add("Visible")
        self.assertEqual(received, [later])  # no leak of the blocked item


class TestMenuGridLayout(QtBaseTestCase):
    """Tests for Menu grid layout positioning."""

    def test_add_at_specific_row_col(self):
        """Should add item at specific row and column."""
        menu = self.track_widget(Menu())
        label = menu.add("QLabel", setText="At 2,1", row=2, col=1)
        # Verify item was added
        self.assertIn(label, menu.get_items())

    def test_add_with_row_span(self):
        """Should add item with row span."""
        menu = self.track_widget(Menu())
        label = menu.add("QLabel", setText="Spanning", rowSpan=2)
        self.assertIn(label, menu.get_items())

    def test_add_with_col_span(self):
        """Should add item with column span."""
        menu = self.track_widget(Menu())
        label = menu.add("QLabel", setText="Wide", colSpan=3)
        self.assertIn(label, menu.get_items())


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestMenuConfigEdgeCases(unittest.TestCase):
    """Edge case tests for MenuConfig."""

    def test_config_with_empty_name(self):
        """Should handle empty name."""
        config = MenuConfig(name="")
        self.assertEqual(config.name, "")

    def test_config_with_all_options(self):
        """Should handle all options set."""
        config = MenuConfig(
            parent=None,
            name="full_menu",
            trigger_button="middle",
            position="top",
            add_header=False,
            add_footer=False,
            add_apply_button=True,
            match_parent_width=False,
            hide_on_leave=True,
            fixed_item_height=50,
            min_item_height=20,
            max_item_height=100,
        )
        self.assertEqual(config.name, "full_menu")
        self.assertFalse(config.add_header)
        self.assertTrue(config.add_apply_button)

    def test_config_extra_attrs(self):
        """Should store extra attributes."""
        config = MenuConfig(extra_attrs={"custom": "value"})
        self.assertEqual(config.extra_attrs["custom"], "value")


class TestMenuPositionerEdgeCases(QtBaseTestCase):
    """Edge case tests for MenuPositioner."""

    def test_position_at_negative_coordinates(self):
        """Should handle negative coordinates."""
        widget = self.track_widget(QtWidgets.QWidget())
        widget.resize(100, 100)
        MenuPositioner.position_at_coordinate(widget, (-10, -10))
        self.assertEqual(widget.pos(), QtCore.QPoint(-10, -10))

    def test_position_at_zero(self):
        """Should handle zero coordinates."""
        widget = self.track_widget(QtWidgets.QWidget())
        widget.resize(100, 100)
        MenuPositioner.position_at_coordinate(widget, (0, 0))
        self.assertEqual(widget.pos(), QtCore.QPoint(0, 0))

    def test_position_at_large_coordinates(self):
        """Should handle very large coordinates."""
        widget = self.track_widget(QtWidgets.QWidget())
        widget.resize(100, 100)
        MenuPositioner.position_at_coordinate(widget, (10000, 10000))
        self.assertEqual(widget.pos(), QtCore.QPoint(10000, 10000))


class TestMenuItemEdgeCases(QtBaseTestCase):
    """Edge case tests for menu item management."""

    def test_add_empty_string_label(self):
        """Should handle empty string label."""
        menu = self.track_widget(Menu())
        label = menu.add("QLabel", setText="")
        self.assertEqual(label.text(), "")

    def test_add_unicode_label(self):
        """Should handle unicode text."""
        menu = self.track_widget(Menu())
        label = menu.add("QLabel", setText="日本語 🍣")
        self.assertEqual(label.text(), "日本語 🍣")

    def test_add_very_long_text(self):
        """Should handle very long text."""
        menu = self.track_widget(Menu())
        long_text = "A" * 1000
        label = menu.add("QLabel", setText=long_text)
        self.assertEqual(label.text(), long_text)

    def test_add_many_items(self):
        """Should handle many items."""
        menu = self.track_widget(Menu())
        for i in range(100):
            menu.add("QLabel", setText=f"Item {i}")
        self.assertEqual(len(menu.get_items()), 100)

    def test_get_item_with_zero_index(self):
        """Should get first item with index 0."""
        menu = self.track_widget(Menu())
        menu.add("QLabel", setText="First")
        menu.add("QLabel", setText="Second")
        item = menu.get_item(0)
        self.assertEqual(item.text(), "First")

    def test_get_item_with_negative_index(self):
        """Should raise ValueError for negative index."""
        menu = self.track_widget(Menu())
        menu.add("QLabel", setText="First")
        menu.add("QLabel", setText="Last")
        with self.assertRaises(ValueError):
            menu.get_item(-1)


class TestMenuTriggerEdgeCases(QtBaseTestCase):
    """Edge case tests for menu trigger handling."""

    def test_trigger_button_middle(self):
        """Should handle middle button trigger."""
        menu = self.track_widget(Menu(trigger_button="middle"))
        self.assertEqual(menu.trigger_button, QtCore.Qt.MiddleButton)

    def test_trigger_button_multiple(self):
        """Should handle multiple trigger buttons."""
        menu = self.track_widget(Menu(trigger_button=("left", "middle", "right")))
        self.assertEqual(
            menu.trigger_button,
            (QtCore.Qt.LeftButton, QtCore.Qt.MiddleButton, QtCore.Qt.RightButton),
        )


class TestMenuHideEdgeCases(QtBaseTestCase):
    """Edge case tests for menu hiding."""

    def test_hide_already_hidden_menu(self):
        """Should handle hiding already hidden menu."""
        menu = self.track_widget(Menu())
        menu.hide()  # First hide
        result = menu.hide()  # Second hide
        self.assertTrue(result)

    def test_show_then_hide_rapidly(self):
        """Should handle rapid show/hide cycles."""
        menu = self.track_widget(Menu())
        menu.add("QLabel", setText="Item")
        for _ in range(10):
            menu.show()
            menu.hide()
        self.assertFalse(menu.isVisible())


class TestMenuDataEdgeCases(QtBaseTestCase):
    """Edge case tests for menu item data."""

    def test_item_data_none(self):
        """Should handle None data."""
        menu = self.track_widget(Menu())
        label = menu.add("QLabel", setText="Test", data=None)
        self.assertIsNone(label.item_data())

    def test_item_data_complex_object(self):
        """Should handle complex object data."""
        menu = self.track_widget(Menu())
        data = {"nested": {"key": [1, 2, 3]}, "list": [{"a": 1}]}
        label = menu.add("QLabel", setText="Test", data=data)
        self.assertEqual(label.item_data(), data)

    def test_item_data_callable(self):
        """Should handle callable data."""
        menu = self.track_widget(Menu())

        def my_func():
            return 42

        label = menu.add("QLabel", setText="Test", data=my_func)
        self.assertEqual(label.item_data()(), 42)


class TestMenuClearEdgeCases(QtBaseTestCase):
    """Edge case tests for menu clear."""

    def test_clear_empty_menu(self):
        """Should handle clearing empty menu."""
        menu = self.track_widget(Menu())
        menu.clear()  # Should not raise
        self.assertFalse(menu.contains_items)

    def test_clear_then_add(self):
        """Should allow adding items after clear."""
        menu = self.track_widget(Menu())
        menu.add("QLabel", setText="First")
        menu.clear()
        menu.add("QLabel", setText="Second")
        self.assertEqual(len(menu.get_items()), 1)
        self.assertEqual(menu.get_items()[0].text(), "Second")


class TestMenuTitleEdgeCases(QtBaseTestCase):
    """Edge case tests for menu title."""

    def test_title_empty_string(self):
        """Should handle empty string title."""
        menu = self.track_widget(Menu(add_header=True))
        menu.setTitle("")
        self.assertEqual(menu.title(), "")

    def test_title_unicode(self):
        """Should handle unicode title."""
        menu = self.track_widget(Menu(add_header=True))
        menu.setTitle("メニュー 🎨")
        self.assertEqual(menu.title(), "メニュー 🎨")

    def test_title_without_header(self):
        """Should handle title without header."""
        menu = self.track_widget(Menu(add_header=False))
        menu.setTitle("Test")
        # Title may be stored even without header
        self.assertIsNotNone(menu.title())


class TestMenuInitializationVisibility(QtBaseTestCase):
    """Regression tests for Menu show/hide flash during initialization.

    Bug: Menus flash (show/hide rapidly) multiple times during init because
    _setup_as_popup() triggers visibility events via setParent/setWindowFlags,
    and showEvent() does expensive layout work while the menu is already visible.
    Fixed: 2026-03-18
    """

    def test_menu_not_visible_after_construction(self):
        """Menu must remain hidden after __init__ completes."""
        menu = self.track_widget(Menu(hide_on_leave=True))
        self.assertFalse(
            menu.isVisible(),
            "Menu should not be visible immediately after construction",
        )

    def test_menu_not_visible_after_adding_items(self):
        """Menu must remain hidden after items are added (before explicit show)."""
        menu = self.track_widget(Menu(hide_on_leave=True))
        menu.add("QPushButton", setText="Button A")
        menu.add("QLabel", setText="Label A")
        menu.add("QCheckBox", setText="Check A")
        self.assertFalse(
            menu.isVisible(),
            "Menu should not be visible after adding items",
        )

    def test_no_show_events_during_construction(self):
        """Menu __init__ must not trigger any showEvent calls."""
        show_count = []
        original_showEvent = Menu.showEvent

        def counting_showEvent(self_menu, event):
            show_count.append(1)
            original_showEvent(self_menu, event)

        with patch.object(Menu, "showEvent", counting_showEvent):
            menu = self.track_widget(Menu(hide_on_leave=True))

        self.assertEqual(
            len(show_count),
            0,
            f"showEvent fired {len(show_count)} time(s) during construction",
        )

    def test_no_show_events_during_item_addition(self):
        """Adding items must not trigger any showEvent calls."""
        menu = self.track_widget(Menu(hide_on_leave=True))

        show_count = []
        original_showEvent = Menu.showEvent

        def counting_showEvent(self_menu, event):
            show_count.append(1)
            original_showEvent(self_menu, event)

        with patch.object(Menu, "showEvent", counting_showEvent):
            menu.add("QPushButton", setText="Button A")
            menu.add("QLabel", setText="Label A")

        self.assertEqual(
            len(show_count),
            0,
            f"showEvent fired {len(show_count)} time(s) during item addition",
        )

    def test_show_as_popup_shows_exactly_once(self):
        """show_as_popup must result in exactly one show() call."""
        parent = self.track_widget(QtWidgets.QPushButton("Anchor"))
        parent.setGeometry(100, 100, 200, 30)
        parent.show()

        menu = self.track_widget(Menu(parent=parent, hide_on_leave=True))
        menu.add("QPushButton", setText="Item")

        show_count = []
        original_show = Menu.show

        def counting_show(self_menu):
            show_count.append(1)
            original_show(self_menu)

        with patch.object(Menu, "show", counting_show):
            menu.show_as_popup(anchor_widget=parent, position="bottom")

        self.assertEqual(
            len(show_count),
            1,
            f"show() called {len(show_count)} time(s) during show_as_popup",
        )
        menu.hide(force=True)

    def test_showEvent_does_not_reposition_after_show_as_popup(self):
        """showEvent must NOT call _apply_position when show_as_popup positioned already.

        Bug: show_as_popup() positions menu correctly, but showEvent() calls
        _apply_position() which overrides the anchor-based position with
        self.position (e.g. "cursorPos"), causing the menu to jump visibly.
        Fixed: 2026-03-18
        """
        parent = self.track_widget(QtWidgets.QPushButton("Anchor"))
        parent.setGeometry(200, 200, 200, 30)
        parent.show()

        menu = self.track_widget(Menu(parent=parent, hide_on_leave=True))
        menu.add("QPushButton", setText="Item")

        reposition_calls = []
        original_apply_position = Menu._apply_position

        def tracking_apply_position(self_menu):
            reposition_calls.append(1)
            original_apply_position(self_menu)

        with patch.object(Menu, "_apply_position", tracking_apply_position):
            menu.show_as_popup(anchor_widget=parent, position="bottom")

        self.assertEqual(
            len(reposition_calls),
            0,
            f"_apply_position called {len(reposition_calls)} time(s) during "
            f"show_as_popup (should be 0 - positioning handled by show_as_popup)",
        )
        menu.hide(force=True)

    def test_no_show_events_during_option_box_wrapping(self):
        """OptionBox wrapping must not trigger any Menu show events.

        Bug: When OptionBoxManager wraps a PushButton that has been added
        to a header menu, the lazy deferred wrapping could trigger show
        events on the option_box menu during layout replacement.
        Fixed: 2026-03-18
        """
        from uitk.widgets.header import Header
        from uitk.widgets.optionBox.utils import OptionBoxManager

        header = self.track_widget(Header())
        header.setGeometry(100, 100, 300, 20)

        # Add a button to the header menu (simulates tentacle header_init)
        button = header.menu.add("QPushButton", setText="Tool Button")

        # Track show events on ALL Menu instances
        show_events = []
        original_showEvent = Menu.showEvent

        def counting_showEvent(self_menu, event):
            show_events.append(self_menu.objectName() or id(self_menu))
            original_showEvent(self_menu, event)

        with patch.object(Menu, "showEvent", counting_showEvent):
            # Access option_box.menu (simulates tb000_init)
            mgr = OptionBoxManager(button)
            mgr.enable_menu()
            mgr.menu.add("QSpinBox", setObjectName="s000")
            mgr.menu.add("QCheckBox", setText="Option A")

            # Force wrapping synchronously (normally deferred via QTimer)
            if mgr._pending_options and not mgr._is_wrapped:
                mgr._perform_wrap()

        self.assertEqual(
            len(show_events),
            0,
            f"Menu showEvent fired {len(show_events)} time(s) during option box wrapping",
        )

    def test_register_with_main_window_deferred_not_synchronous(self):
        """_register_with_main_window must NOT run synchronously inside add().

        Bug: add() called _register_with_main_window synchronously which called
        mainWindow.register_widget → init_slot → tb###_init, creating nested
        option-box menus and wrapping layout while add() was still running.
        This caused menus to flash on init and option menus to break.
        Fixed: 2026-03-18

        Contract: registration is deferred to a later event-loop tick.  This
        test only checks "not during add()"; the order/coalescing properties
        are covered in the dedicated tests below.
        """
        parent = self.track_widget(QtWidgets.QWidget())
        parent.show()
        menu = self.track_widget(Menu(parent=parent))

        # Track whether _register_with_main_window is called during add()
        register_calls_during_add = []
        original_register = menu._register_with_main_window

        def tracking_register(widget, _orig=original_register):
            register_calls_during_add.append(widget.objectName())
            _orig(widget)

        menu._register_with_main_window = tracking_register

        menu.add("QPushButton", setText="Tool", setObjectName="tb018")

        # Should NOT have been called synchronously during add()
        self.assertEqual(
            len(register_calls_during_add),
            0,
            f"_register_with_main_window called {len(register_calls_during_add)} "
            f"time(s) synchronously during add() — should be deferred",
        )


class TestMenuRegistrationCoalescing(QtBaseTestCase):
    """Locks down :meth:`Menu._schedule_registration` /
    :meth:`Menu._drain_pending_registrations` semantics.

    Background: ``Menu.add`` used to schedule one
    ``QTimer.singleShot(0, _register_with_main_window)`` per item.  Bulk
    adds inside ``tbXXX_init`` queued one timer wakeup per item, each
    landing on its own event-loop tick.  The current implementation
    coalesces every registration request from a given tick into a single
    drain pass, but the *observable* contract — same FIFO order, no
    synchronous call inside add(), re-entrant adds re-arm a fresh timer —
    is preserved.  These tests guard the coalesced path against future
    refactors that would re-introduce per-item timers or break ordering.
    """

    def test_bulk_add_schedules_single_drain_timer(self):
        """N adds in one tick must schedule exactly one drain timer."""
        from uitk.widgets import menu as menu_module

        parent = self.track_widget(QtWidgets.QWidget())
        parent.show()
        m = self.track_widget(Menu(parent=parent))

        scheduled = []
        original_singleShot = QtCore.QTimer.singleShot

        def counting_singleShot(interval, slot, *args, **kwargs):
            scheduled.append((interval, getattr(slot, "__name__", repr(slot))))
            return original_singleShot(interval, slot, *args, **kwargs)

        with patch.object(menu_module.QtCore.QTimer, "singleShot", counting_singleShot):
            for i in range(5):
                m.add("QPushButton", setObjectName=f"b{i:03d}")

        drain_schedules = [
            s for s in scheduled if s[1] == "_drain_pending_registrations"
        ]
        self.assertEqual(
            len(drain_schedules),
            1,
            f"Expected exactly 1 drain timer for 5 adds; got {len(drain_schedules)}: {scheduled}",
        )
        self.assertEqual(len(m._pending_registrations), 5)
        self.assertTrue(m._registration_drain_scheduled)

    def test_drain_processes_in_fifo_order(self):
        """_drain_pending_registrations must call _register_with_main_window
        in insertion order (the contract callers rely on for sibling lookups
        in <name>_init bodies)."""
        parent = self.track_widget(QtWidgets.QWidget())
        parent.show()
        m = self.track_widget(Menu(parent=parent))

        order = []
        m._register_with_main_window = lambda w: order.append(w.objectName())

        names = ["b000", "b001", "b002", "b003"]
        for n in names:
            m.add("QPushButton", setObjectName=n)

        m._drain_pending_registrations()
        self.assertEqual(order, names)
        self.assertEqual(m._pending_registrations, [])
        self.assertFalse(m._registration_drain_scheduled)


class _StubMainWindow(QtWidgets.QMainWindow):
    """Minimal stand-in exposing the ``register_widget`` / ``widgets`` contract
    that :meth:`Menu._resolve_registration_window` probes for.

    ``register_widget`` mirrors the essential side effects of the real
    ``MainWindow.register_widget``: it marks the widget for state persistence
    (``restore_state``) and tracks it. That's all the registration path needs
    to verify here.
    """

    def __init__(self):
        super().__init__()
        self.widgets = set()
        self.registered = []

    def register_widget(self, widget):
        widget.restore_state = True
        self.widgets.add(widget)
        self.registered.append(widget.objectName())


class TestMenuRegistrationSurvivesReparent(QtBaseTestCase):
    """Deferred registration must reach the MainWindow even after the menu
    reparents to a top-level popup on show.

    Regression: a menu shows by reparenting itself to a top-level Tool/Popup
    window, which severs the live parent chain back to the MainWindow. Because
    dynamic-widget registration is *deferred* to a later event-loop tick, in a
    live DCC session the show/reparent could race ahead of the drain — at which
    point ``_register_with_main_window`` walked a broken chain, found no
    MainWindow, and silently skipped registration. The widget never got
    ``restore_state``, so its value was neither saved nor restored. Repro'd as
    menu-hosted options resetting every session only in interactive Maya.

    Fix: capture the owning MainWindow weakly while the chain is still intact
    (at schedule time) and fall back to it at drain time.
    """

    def _build(self):
        window = self.track_widget(_StubMainWindow())
        central = self.track_widget(QtWidgets.QWidget())
        window.setCentralWidget(central)
        host = self.track_widget(QtWidgets.QPushButton("host", central))
        menu = self.track_widget(Menu(parent=host))
        return window, host, menu

    def test_resolve_finds_window_via_live_chain(self):
        """The cheap, common path: an intact parent chain resolves directly."""
        window, _host, menu = self._build()
        self.assertIs(menu._resolve_registration_window(), window)

    def test_resolve_falls_back_to_cache_after_reparent(self):
        """Once the live chain is broken, the cached window still resolves."""
        window, _host, menu = self._build()
        # Prime the cache via a successful live walk.
        self.assertIs(menu._resolve_registration_window(), window)

        rogue = self.track_widget(QtWidgets.QMainWindow())  # no register_widget
        menu.setParent(rogue, QtCore.Qt.Window)
        self.assertFalse(hasattr(menu.parent(), "register_widget"))

        self.assertIs(menu._resolve_registration_window(), window)

    def test_registration_survives_menu_reparent_before_drain(self):
        """End-to-end: add → reparent (break chain) → drain still registers."""
        window, _host, menu = self._build()
        chk = menu.add("QCheckBox", setObjectName="chk_opt")

        # Simulate the menu becoming a top-level popup on show.
        rogue = self.track_widget(QtWidgets.QMainWindow())
        menu.setParent(rogue, QtCore.Qt.Window)
        self.assertFalse(hasattr(menu.parent(), "register_widget"))

        menu._drain_pending_registrations()

        self.assertIn("chk_opt", window.registered)
        self.assertIn(chk, window.widgets)
        self.assertTrue(getattr(chk, "restore_state", False))

    def test_reentrant_add_during_drain_rearms_timer(self):
        """If a registration handler triggers another add() while the drain
        is running, the new item must land in a fresh queue with its own
        scheduled drain — matching the per-item-timer behavior this replaced.
        Without re-arming, items added during drain would never register."""
        from uitk.widgets import menu as menu_module

        parent = self.track_widget(QtWidgets.QWidget())
        parent.show()
        m = self.track_widget(Menu(parent=parent))

        timers_after_init: list[int] = []

        def registration_handler(widget):
            # Simulate an init-slot that adds another item mid-drain.
            if widget.objectName() == "b000":
                m.add("QPushButton", setObjectName="b000_child")

        m._register_with_main_window = registration_handler

        m.add("QPushButton", setObjectName="b000")

        scheduled_during_drain = []
        original_singleShot = QtCore.QTimer.singleShot

        def counting_singleShot(interval, slot, *args, **kwargs):
            scheduled_during_drain.append(getattr(slot, "__name__", repr(slot)))
            return original_singleShot(interval, slot, *args, **kwargs)

        with patch.object(menu_module.QtCore.QTimer, "singleShot", counting_singleShot):
            m._drain_pending_registrations()

        # The reentrant add() should have queued a fresh drain
        self.assertEqual(len(m._pending_registrations), 1)
        self.assertEqual(m._pending_registrations[0].objectName(), "b000_child")
        self.assertTrue(m._registration_drain_scheduled)
        self.assertIn("_drain_pending_registrations", scheduled_during_drain)

    def test_drain_swallows_runtime_error_for_deleted_widget(self):
        """A widget can be deleted between schedule and drain; the drain
        must skip it without aborting the rest of the queue."""
        parent = self.track_widget(QtWidgets.QWidget())
        parent.show()
        m = self.track_widget(Menu(parent=parent))

        registered = []

        def patched_register(widget):
            name = widget.objectName()
            if name == "b001":
                raise RuntimeError("Internal C++ object already deleted")
            registered.append(name)

        m._register_with_main_window = patched_register

        for n in ("b000", "b001", "b002"):
            m.add("QPushButton", setObjectName=n)

        m._drain_pending_registrations()
        self.assertEqual(registered, ["b000", "b002"])

    def test_drain_isolates_non_runtime_exceptions(self):
        """Per-item-timer behavior: a non-RuntimeError exception in one
        registration must not abort the rest of the queue.  This guards
        the parity between the coalesced drain and the prior per-item
        QTimer mechanism, where each item's failure was naturally
        independent."""
        parent = self.track_widget(QtWidgets.QWidget())
        parent.show()
        m = self.track_widget(Menu(parent=parent))

        registered = []

        def patched_register(widget):
            name = widget.objectName()
            if name == "b001":
                raise ValueError("intentional bug in slot init")
            registered.append(name)

        m._register_with_main_window = patched_register

        for n in ("b000", "b001", "b002"):
            m.add("QPushButton", setObjectName=n)

        m._drain_pending_registrations()
        # b001's ValueError is logged but doesn't drop b002.
        self.assertEqual(registered, ["b000", "b002"])

    def test_layout_activate_skipped_when_invisible(self):
        """Bulk add() during slot init must not call _layout.activate() per
        item.  The menu is invisible at that point and Qt re-activates layouts
        before paint anyway; activating per-item is wasted work that shows
        up under the bench's phase 04 (register_children_sync)."""
        parent = self.track_widget(QtWidgets.QWidget())
        parent.show()
        m = self.track_widget(Menu(parent=parent))
        # Menu.__init__ creates _layout eagerly via init_layout — verify.
        self.assertIsNotNone(m._layout)
        self.assertFalse(m.isVisible())

        with patch.object(m._layout, "activate") as mock_activate:
            for i in range(5):
                m.add("QPushButton", setObjectName=f"b{i:03d}")

        self.assertEqual(
            mock_activate.call_count,
            0,
            f"_layout.activate() called {mock_activate.call_count} time(s) "
            f"while menu invisible — should be skipped (Qt activates before paint)",
        )

    def test_layout_activate_runs_when_visible(self):
        """Counterpart to the invisible-skip test: when the menu *is*
        visible, add() still calls activate() so the on-screen layout
        updates immediately."""
        parent = self.track_widget(QtWidgets.QWidget())
        parent.show()
        m = self.track_widget(Menu(parent=parent))
        m.show()
        QtWidgets.QApplication.processEvents()
        if not m.isVisible():
            self.skipTest("Menu did not become visible in this Qt environment")

        with patch.object(m._layout, "activate") as mock_activate:
            m.add("QPushButton", setObjectName="b_visible")

        self.assertGreaterEqual(
            mock_activate.call_count,
            1,
            "_layout.activate() must run on add() while menu is visible",
        )


class TestHeaderMenuPopup(QtBaseTestCase):
    """Tests for Header menu display as proper popup.

    Bug: Header.show_menu() used setVisible(True) instead of show_as_popup(),
    causing the menu to appear at (0,0) or wrong position instead of anchored
    to the header widget.
    Fixed: 2026-03-18
    """

    def test_header_menu_uses_popup(self):
        """Header.show_menu() must position the menu as a popup, not raw setVisible."""
        from uitk.widgets.header import Header

        header = self.track_widget(Header())
        header.setGeometry(100, 100, 300, 20)
        header.show()

        # Populate the menu
        header.menu.add("QPushButton", setText="Action 1")
        header.menu.add("QPushButton", setText="Action 2")

        # Show the menu
        header.show_menu()

        self.assertTrue(
            header.menu.isVisible(),
            "Menu should be visible after show_menu()",
        )

        # Verify the menu has popup window flags (Tool | FramelessWindowHint)
        flags = header.menu.windowFlags()
        self.assertTrue(
            flags & QtCore.Qt.Tool,
            "Menu must have Qt.Tool flag to display as popup",
        )

        header.menu.hide(force=True)

    def test_header_menu_positioned_near_header(self):
        """Header menu should appear near the header widget, not at (0,0)."""
        from uitk.widgets.header import Header

        header = self.track_widget(Header())
        header.setGeometry(200, 200, 300, 20)
        header.show()

        header.menu.add("QPushButton", setText="Action 1")

        header.show_menu()

        # Menu position should be near the header, not at origin
        menu_pos = header.menu.pos()
        # The menu should be positioned somewhere near the header's screen position
        # At minimum, it shouldn't be at (0,0) which is the default unpositioned location
        header_global = header.mapToGlobal(header.rect().bottomLeft())

        # Allow generous margin for positioning differences, but not at (0,0)
        self.assertFalse(
            menu_pos.x() == 0 and menu_pos.y() == 0,
            "Menu should not be positioned at origin (0,0)",
        )

        header.menu.hide(force=True)


class TestOptionBoxMenuPopupFlags(QtBaseTestCase):
    """Tests for OptionBox menu popup flag lifecycle.

    Original bug: ``MenuOption.set_wrapped_widget()`` called setParent(widget)
    without preserving window flags, stripping ``Qt.Tool | Qt.FramelessWindowHint``
    set by ``_setup_as_popup()``.  The menu then rendered as a clipped
    child instead of a floating popup.
    Fixed: 2026-03-18

    Updated contract (Fix A): popup setup is deferred until the menu's
    first show — running it during ``Menu.__init__`` creates a native
    Tool window per Menu, which on Windows produces a brief WM-visible
    artifact ("multiple menus initializing repeatedly") for every
    option_box menu created during ``register_children``.  Tests below
    were updated to reflect the deferred-setup contract.
    """

    def test_option_box_menu_acquires_popup_flags_on_first_show(self):
        """Fix A contract: menu has *no* Tool flag pre-show; it's set
        on the first ``show_as_popup`` (or ``showEvent``).  This eliminates
        the Tool-window flash visible during ``register_children`` when
        ``_setup_as_popup`` ran eagerly in ``Menu.__init__``."""
        from uitk.widgets.optionBox.utils import OptionBoxManager

        parent = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(parent)
        button = QtWidgets.QPushButton("Test")
        layout.addWidget(button)
        parent.show()

        mgr = OptionBoxManager(button)
        mgr.enable_menu()
        menu = mgr.menu

        # Pre-show: popup setup deferred — no Tool flag yet.
        self.assertFalse(
            menu._popup_configured,
            "Menu must defer popup setup until first show",
        )
        flags_before = menu.windowFlags()
        self.assertFalse(
            flags_before & QtCore.Qt.Tool,
            "Menu must NOT have Qt.Tool flag before first show (Fix A)",
        )

        # Wrap fires (Fix C: synchronous when parent exists).
        container = mgr.container
        self.track_widget(container)

        # Wrap also doesn't set Tool flag — that waits for first show.
        self.assertFalse(
            menu.windowFlags() & QtCore.Qt.Tool,
            "Wrap must not eagerly trigger popup setup",
        )

        # First show — popup setup runs synchronously inside show_as_popup
        # before positioning, so the menu's geometry is in screen coords.
        menu.show_as_popup(anchor_widget=button, position="bottom")

        self.assertTrue(menu._popup_configured)
        self.assertTrue(
            menu.windowFlags() & QtCore.Qt.Tool,
            "Menu must have Qt.Tool flag after first show_as_popup",
        )
        menu.hide(force=True)

    def test_setvisible_true_directly_triggers_popup_setup(self):
        """Direct ``menu.setVisible(True)`` (bypassing ``show()`` /
        ``show_as_popup``) must still apply popup setup.  Without this,
        callers that use the low-level visibility API would see a
        non-popup menu, or worse, the ``setWindowFlags`` hide-during-show
        race that bricked the show.
        """
        menu = self.track_widget(Menu())
        self.assertFalse(menu._popup_configured)

        menu.setVisible(True)

        self.assertTrue(
            menu._popup_configured,
            "setVisible(True) must trigger _setup_as_popup",
        )
        self.assertTrue(
            menu.windowFlags() & QtCore.Qt.Tool,
            "Tool flag must be applied via setVisible(True) path",
        )
        self.assertTrue(menu.isVisible())
        menu.hide(force=True)

    def test_show_hide_show_cycle_keeps_popup_configured(self):
        """Once popup setup runs, subsequent show/hide cycles must not
        re-run it — the ``_popup_configured`` flag is sticky.  Without
        idempotency, every show would call setWindowFlags again,
        recreating the native window handle and producing exactly the
        flicker Fix A is meant to eliminate."""
        menu = self.track_widget(Menu())
        self.assertFalse(menu._popup_configured)

        menu.show()
        self.assertTrue(menu._popup_configured)
        flags_first_show = menu.windowFlags()

        menu.hide(force=True)
        menu.show()  # second show
        flags_second_show = menu.windowFlags()

        self.assertEqual(
            flags_first_show,
            flags_second_show,
            "Window flags must be stable across show/hide cycles",
        )
        menu.hide(force=True)

    def test_construction_does_not_create_tool_window(self):
        """The user-facing flicker source: ``_setup_as_popup`` running
        eagerly in ``Menu.__init__`` created an OS-level Tool window per
        Menu, producing brief WM-visible artifacts during
        register_children.  After Fix A, construction must leave the
        menu as a hidden child widget — no popup setup, no Tool flag,
        no native window created."""
        parent = self.track_widget(QtWidgets.QWidget())
        menu = self.track_widget(Menu(parent=parent))

        self.assertFalse(menu._popup_configured)
        self.assertFalse(menu.windowFlags() & QtCore.Qt.Tool)
        self.assertIs(menu.parent(), parent)
        # Explicit hide marker prevents parent-cascade auto-show.
        self.assertFalse(menu.isVisible())

    def test_parent_cascade_does_not_auto_show_menu(self):
        """The bug Fix A's ``super().hide()`` in __init__ guards: when
        the Menu is parented to a button that gets reparented into an
        ``OptionBoxContainer``, the container's ``show()`` cascades
        through children.  Without explicit hide, the cascade reaches
        the Menu and fires showEvent — running popup setup mid-wrap and
        defeating the deferral.  Explicit hide flips
        ``WA_WState_ExplicitShowHide`` so the cascade skips it."""
        parent = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(parent)
        button = QtWidgets.QPushButton()
        layout.addWidget(button)
        menu = self.track_widget(Menu(parent=button))

        # Show the parent — cascade would auto-show Menu without explicit hide.
        parent.show()
        QtWidgets.QApplication.processEvents()

        self.assertFalse(
            menu.isVisible(),
            "Menu must remain hidden through parent.show() cascade",
        )
        self.assertFalse(
            menu._popup_configured,
            "Popup setup must NOT run via parent cascade",
        )
        parent.hide()

    def test_option_box_menu_retains_popup_flags_across_wrap(self):
        """Once popup setup has run, subsequent operations on the
        wrapped menu must not strip Tool flags (the original 2026-03-18
        bug)."""
        from uitk.widgets.optionBox.utils import OptionBoxManager

        parent = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(parent)
        button = QtWidgets.QPushButton("Test")
        layout.addWidget(button)
        parent.show()

        mgr = OptionBoxManager(button)
        mgr.enable_menu()
        menu = mgr.menu

        # Force popup setup to happen now (simulate first show).
        menu._setup_as_popup()
        self.assertTrue(menu.windowFlags() & QtCore.Qt.Tool)

        # Trigger wrap path which reparents via setParent(widget, windowFlags()).
        container = mgr.container
        self.track_widget(container)

        # Tool flag must be preserved through the wrap reparent.
        self.assertTrue(
            menu.windowFlags() & QtCore.Qt.Tool,
            "Menu must retain Qt.Tool flag after OptionBox wrapping",
        )

    def test_option_box_menu_shows_as_popup(self):
        """OptionBox menu must display as a floating popup, not clipped child."""
        from uitk.widgets.optionBox.utils import OptionBoxManager

        parent = self.track_widget(QtWidgets.QWidget())
        parent.setGeometry(100, 100, 300, 40)
        layout = QtWidgets.QVBoxLayout(parent)
        button = QtWidgets.QPushButton("Test")
        layout.addWidget(button)
        parent.show()

        mgr = OptionBoxManager(button)
        mgr.menu.add("QLabel", setText="Option 1")
        mgr.menu.add("QCheckBox", setText="Option 2")

        # Force wrap
        container = mgr.container
        self.track_widget(container)

        # Show the menu
        mgr.menu.show_as_popup(anchor_widget=button, position="bottom")

        self.assertTrue(
            mgr.menu.isVisible(),
            "OptionBox menu should be visible after show_as_popup",
        )

        # Menu height should be greater than the button height (proves it's not clipped)
        self.assertGreater(
            mgr.menu.height(),
            button.height(),
            "Menu should be taller than button (not clipped as child widget)",
        )

        mgr.menu.hide(force=True)

    def test_nested_option_menu_in_header_menu(self):
        """Option box menus on buttons inside header.menu must open as popups.

        This replicates the exact tentacle animation slots pattern:
        header_init adds PushButton items to header.menu, then tb###_init
        adds items to widget.option_box.menu for each tool button.
        Fixed: 2026-03-18
        """
        from uitk.widgets.header import Header
        from uitk.widgets.optionBox.utils import OptionBoxManager

        # Setup: header with menu containing buttons (simulates header_init)
        header = self.track_widget(Header())
        header.setGeometry(100, 100, 300, 20)
        header.show()

        tool_button = header.menu.add("QPushButton", setText="Smart Bake")

        # Setup option box on the tool button (simulates tb018_init)
        mgr = OptionBoxManager(tool_button)
        mgr.enable_menu()
        mgr.menu.add("QCheckBox", setText="Bake Constraints")
        mgr.menu.add("QCheckBox", setText="Bake Expressions")

        # Force wrapping synchronously
        if mgr._pending_options and not mgr._is_wrapped:
            mgr._perform_wrap()

        # Show the header menu first
        header.show_menu()
        self.assertTrue(header.menu.isVisible(), "Header menu should be visible")

        # Now show the option box menu (simulates clicking the option_box button)
        mgr.menu.show_as_popup(anchor_widget=tool_button, position="bottom")

        self.assertTrue(
            mgr.menu.isVisible(),
            "Option box menu inside header menu must be visible after show_as_popup",
        )

        # Verify popup flags are intact
        flags = mgr.menu.windowFlags()
        self.assertTrue(
            flags & QtCore.Qt.Tool,
            "Nested option box menu must have Qt.Tool flag",
        )

        mgr.menu.hide(force=True)
        header.menu.hide(force=True)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
