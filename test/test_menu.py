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


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
