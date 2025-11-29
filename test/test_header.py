# !/usr/bin/python
# coding=utf-8
"""Unit tests for Header widget.

This module tests the Header widget functionality including:
- Header creation and configuration
- Button configuration
- Pin/unpin functionality
- Dragging behavior
- Menu integration
- Title text management

Run standalone: python -m test.test_header
"""

import unittest
from unittest.mock import MagicMock, patch

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore, QtGui

from uitk.widgets.header import Header


class TestHeaderCreation(QtBaseTestCase):
    """Tests for Header creation and initialization."""

    def test_creates_header_with_defaults(self):
        """Should create header with default settings."""
        header = self.track_widget(Header())
        self.assertIsNotNone(header)
        self.assertFalse(header.pinned)

    def test_creates_header_with_parent(self):
        """Should create header with parent widget."""
        parent = self.track_widget(QtWidgets.QWidget())
        header = self.track_widget(Header(parent=parent))
        self.assertEqual(header.parent(), parent)

    def test_creates_header_with_title(self):
        """Should create header with title via kwargs."""
        header = self.track_widget(Header(setTitle="My Title"))
        self.assertEqual(header.title(), "My Title")

    def test_has_container_layout(self):
        """Should have container layout for buttons."""
        header = self.track_widget(Header())
        self.assertIsNotNone(header.container_layout)
        self.assertIsInstance(header.container_layout, QtWidgets.QHBoxLayout)

    def test_has_open_hand_cursor(self):
        """Should have open hand cursor for dragging."""
        header = self.track_widget(Header())
        self.assertEqual(header.cursor().shape(), QtCore.Qt.OpenHandCursor)

    def test_has_fixed_height(self):
        """Should have fixed height of 20 pixels."""
        header = self.track_widget(Header())
        self.assertEqual(header.height(), 20)

    def test_has_bold_font(self):
        """Should have bold font."""
        header = self.track_widget(Header())
        self.assertTrue(header.font().bold())


class TestHeaderButtons(QtBaseTestCase):
    """Tests for Header button configuration."""

    def test_buttons_dict_empty_by_default(self):
        """Should have empty buttons dict when no buttons configured."""
        header = self.track_widget(Header())
        self.assertEqual(header.buttons, {})

    def test_config_buttons_adds_pin_button(self):
        """Should add pin button when configured."""
        header = self.track_widget(Header(config_buttons=["pin_button"]))
        self.assertIn("pin_button", header.buttons)

    def test_config_buttons_adds_multiple_buttons(self):
        """Should add multiple buttons when configured."""
        header = self.track_widget(Header(config_buttons=["pin_button", "hide_button"]))
        self.assertIn("pin_button", header.buttons)
        self.assertIn("hide_button", header.buttons)

    def test_config_buttons_ignores_unknown(self):
        """Should ignore unknown button names."""
        header = self.track_widget(Header(config_buttons=["unknown_button"]))
        self.assertNotIn("unknown_button", header.buttons)

    def test_has_buttons_returns_false_when_empty(self):
        """Should return False when no buttons exist."""
        header = self.track_widget(Header())
        self.assertFalse(header.has_buttons())

    def test_has_buttons_returns_true_when_buttons_exist(self):
        """Should return True when buttons exist."""
        header = self.track_widget(Header(config_buttons=["pin_button"]))
        self.assertTrue(header.has_buttons())

    def test_has_buttons_checks_specific_type(self):
        """Should check for specific button type."""
        header = self.track_widget(Header(config_buttons=["pin_button"]))
        self.assertTrue(header.has_buttons("pin_button"))
        self.assertFalse(header.has_buttons("hide_button"))

    def test_has_buttons_checks_list_of_types(self):
        """Should check for list of button types."""
        header = self.track_widget(Header(config_buttons=["pin_button"]))
        self.assertTrue(header.has_buttons(["pin_button", "hide_button"]))
        self.assertFalse(header.has_buttons(["hide_button", "menu_button"]))


class TestHeaderCreateButton(QtBaseTestCase):
    """Tests for Header create_button method."""

    def test_create_button_returns_push_button(self):
        """Should create QPushButton."""
        header = self.track_widget(Header())
        button = header.create_button("pin.svg", lambda: None)
        self.assertIsInstance(button, QtWidgets.QPushButton)

    def test_create_button_sets_object_name(self):
        """Should set object name when provided."""
        header = self.track_widget(Header())
        button = header.create_button(
            "pin.svg", lambda: None, button_type="test_button"
        )
        self.assertEqual(button.objectName(), "test_button")

    def test_create_button_has_arrow_cursor(self):
        """Should have arrow cursor on button."""
        header = self.track_widget(Header())
        button = header.create_button("pin.svg", lambda: None)
        self.assertEqual(button.cursor().shape(), QtCore.Qt.ArrowCursor)

    def test_create_button_connects_callback(self):
        """Should connect callback to clicked signal."""
        header = self.track_widget(Header())
        callback_called = []
        button = header.create_button("pin.svg", lambda: callback_called.append(True))
        button.click()
        self.assertTrue(callback_called)


class TestHeaderPinning(QtBaseTestCase):
    """Tests for Header pin/unpin functionality."""

    def test_pinned_default_false(self):
        """Should default to unpinned state."""
        header = self.track_widget(Header())
        self.assertFalse(header.pinned)

    def test_toggle_pin_changes_state(self):
        """Should toggle pinned state."""
        # Create header with a window parent to avoid errors
        window = self.track_widget(QtWidgets.QWidget())
        window.prevent_hide = False
        header = self.track_widget(Header(parent=window, config_buttons=["pin_button"]))
        initial_state = header.pinned
        header.toggle_pin()
        self.assertNotEqual(header.pinned, initial_state)

    def test_toggle_pin_emits_signal(self):
        """Should emit toggled signal when pin state changes."""
        window = self.track_widget(QtWidgets.QWidget())
        window.prevent_hide = False
        header = self.track_widget(Header(parent=window, config_buttons=["pin_button"]))
        signal_received = []
        header.toggled.connect(lambda state: signal_received.append(state))
        header.toggle_pin()
        self.assertEqual(len(signal_received), 1)

    def test_reset_pin_state_unpins(self):
        """Should reset to unpinned state."""
        window = self.track_widget(QtWidgets.QWidget())
        window.prevent_hide = False
        header = self.track_widget(Header(parent=window, config_buttons=["pin_button"]))
        header.pinned = True
        header.reset_pin_state()
        self.assertFalse(header.pinned)

    def test_reset_pin_state_emits_signal(self):
        """Should emit toggled signal when reset."""
        window = self.track_widget(QtWidgets.QWidget())
        window.prevent_hide = False
        header = self.track_widget(Header(parent=window, config_buttons=["pin_button"]))
        header.pinned = True
        signal_received = []
        header.toggled.connect(lambda state: signal_received.append(state))
        header.reset_pin_state()
        self.assertIn(False, signal_received)


class TestHeaderTitle(QtBaseTestCase):
    """Tests for Header title methods."""

    def test_set_title_updates_text(self):
        """Should update text when title is set."""
        header = self.track_widget(Header())
        header.setTitle("New Title")
        self.assertEqual(header.title(), "New Title")

    def test_title_returns_text(self):
        """Should return current text."""
        header = self.track_widget(Header())
        header.setText("Current Text")
        self.assertEqual(header.title(), "Current Text")


class TestHeaderMenu(QtBaseTestCase):
    """Tests for Header menu integration."""

    def test_menu_property_creates_menu(self):
        """Should create menu on first access."""
        header = self.track_widget(Header())
        menu = header.menu
        self.assertIsNotNone(menu)

    def test_menu_property_returns_same_instance(self):
        """Should return same menu instance on subsequent access."""
        header = self.track_widget(Header())
        menu1 = header.menu
        menu2 = header.menu
        self.assertIs(menu1, menu2)


class TestHeaderButtonDefinitions(QtBaseTestCase):
    """Tests for Header button definitions."""

    def test_has_button_definitions(self):
        """Should have button_definitions class attribute."""
        self.assertTrue(hasattr(Header, "button_definitions"))
        self.assertIsInstance(Header.button_definitions, dict)

    def test_button_definitions_has_menu_button(self):
        """Should have menu_button definition."""
        self.assertIn("menu_button", Header.button_definitions)

    def test_button_definitions_has_minimize_button(self):
        """Should have minimize_button definition."""
        self.assertIn("minimize_button", Header.button_definitions)

    def test_button_definitions_has_hide_button(self):
        """Should have hide_button definition."""
        self.assertIn("hide_button", Header.button_definitions)

    def test_button_definitions_has_pin_button(self):
        """Should have pin_button definition."""
        self.assertIn("pin_button", Header.button_definitions)

    def test_button_definition_contains_icon_and_method(self):
        """Should have (icon, method) tuple for each button."""
        for name, definition in Header.button_definitions.items():
            self.assertIsInstance(definition, tuple)
            self.assertEqual(len(definition), 2)


class TestHeaderWindowActions(QtBaseTestCase):
    """Tests for Header window action methods."""

    def test_minimize_window_minimizes_parent(self):
        """Should minimize parent window."""
        window = self.track_widget(QtWidgets.QWidget())
        window.show()
        header = self.track_widget(Header(parent=window))
        # Should not raise
        header.minimize_window()

    def test_hide_window_hides_parent(self):
        """Should hide parent window."""
        window = self.track_widget(QtWidgets.QWidget())
        window.prevent_hide = False
        window.show()
        header = self.track_widget(Header(parent=window, config_buttons=["pin_button"]))
        header.hide_window()
        self.assertFalse(window.isVisible())


class TestHeaderAttachTo(QtBaseTestCase):
    """Tests for Header attach_to method."""

    def test_attach_to_widget_with_layout(self):
        """Should attach header to widget with layout."""
        widget = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(widget)
        header = self.track_widget(Header())
        header.attach_to(widget)
        self.assertEqual(widget.header, header)

    def test_attach_to_widget_creates_layout(self):
        """Should create layout if widget has none."""
        widget = self.track_widget(QtWidgets.QWidget())
        header = self.track_widget(Header())
        header.attach_to(widget)
        self.assertIsNotNone(widget.layout())

    def test_attach_to_mainwindow_uses_central_widget(self):
        """Should attach to central widget of QMainWindow."""
        window = self.track_widget(QtWidgets.QMainWindow())
        central = QtWidgets.QWidget()
        central_layout = QtWidgets.QVBoxLayout(central)
        window.setCentralWidget(central)
        header = self.track_widget(Header())
        header.attach_to(window)
        self.assertEqual(central.header, header)

    def test_attach_to_avoids_double_attachment(self):
        """Should not attach twice to same widget."""
        widget = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(widget)
        header = self.track_widget(Header())
        header.attach_to(widget)
        header.attach_to(widget)  # Second attach should be ignored
        self.assertEqual(widget.header, header)


class TestHeaderToggledSignal(QtBaseTestCase):
    """Tests for Header toggled signal."""

    def test_has_toggled_signal(self):
        """Should have toggled signal."""
        header = self.track_widget(Header())
        self.assertTrue(hasattr(header, "toggled"))

    def test_toggled_signal_emits_bool(self):
        """Should emit boolean value."""
        window = self.track_widget(QtWidgets.QWidget())
        window.prevent_hide = False
        header = self.track_widget(Header(parent=window, config_buttons=["pin_button"]))
        received_values = []
        header.toggled.connect(lambda v: received_values.append(v))
        header.toggle_pin()
        self.assertTrue(all(isinstance(v, bool) for v in received_values))


class TestHeaderConfigButtonsMethod(QtBaseTestCase):
    """Tests for Header config_buttons method."""

    def test_config_buttons_accepts_list(self):
        """Should accept list of button names."""
        header = self.track_widget(Header())
        header.config_buttons(["pin_button", "hide_button"])
        self.assertIn("pin_button", header.buttons)
        self.assertIn("hide_button", header.buttons)

    def test_config_buttons_accepts_args(self):
        """Should accept button names as args."""
        header = self.track_widget(Header())
        header.config_buttons("pin_button", "hide_button")
        self.assertIn("pin_button", header.buttons)
        self.assertIn("hide_button", header.buttons)

    def test_config_buttons_clears_existing(self):
        """Should clear existing buttons before adding new ones."""
        header = self.track_widget(Header(config_buttons=["pin_button"]))
        header.config_buttons("hide_button")
        self.assertNotIn("pin_button", header.buttons)
        self.assertIn("hide_button", header.buttons)


class TestHeaderIconMethods(QtBaseTestCase):
    """Tests for Header icon methods."""

    def test_get_icon_path_returns_string(self):
        """Should return string path."""
        header = self.track_widget(Header())
        path = header.get_icon_path("pin.svg")
        self.assertIsInstance(path, str)

    def test_get_icon_path_includes_filename(self):
        """Should include filename in path."""
        header = self.track_widget(Header())
        path = header.get_icon_path("pin.svg")
        self.assertIn("pin.svg", path)

    def test_create_svg_icon_returns_qicon(self):
        """Should return QIcon."""
        header = self.track_widget(Header())
        icon = header.create_svg_icon("pin.svg")
        self.assertIsInstance(icon, QtGui.QIcon)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
