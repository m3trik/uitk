#!/usr/bin/python
# coding=utf-8
"""Test script for PinValuesOption.

This script provides both interactive demo and unit tests for the PinValuesOption.
Run with --demo for interactive testing, or without arguments for unit tests.
"""

import sys
import unittest
from qtpy import QtWidgets, QtCore

# Ensure QApplication exists
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from uitk.widgets.optionBox import OptionBox
from uitk.widgets.optionBox.options.pin_values import PinValuesOption


class TestPinValuesOption(unittest.TestCase):
    def setUp(self):
        self.widget = QtWidgets.QLineEdit()
        self.pin_option = PinValuesOption(self.widget)
        self.option_box = OptionBox(options=[self.pin_option])
        self.container = self.option_box.wrap(self.widget)

    def tearDown(self):
        self.container.deleteLater()
        self.widget.deleteLater()

    def get_pin_button(self):
        """Helper to find the pin button in the container."""
        for child in self.container.findChildren(QtWidgets.QAbstractButton):
            if child.property("class") == "PinButton":
                return child
        return None

    def test_pin_creation(self):
        """Test that pin option can be created and added."""
        self.assertIsNotNone(self.container)
        pin_button = self.get_pin_button()
        self.assertIsNotNone(pin_button)

    def test_initial_state(self):
        """Test initial state - no pinned values."""
        self.assertFalse(self.pin_option.has_pinned_values)
        self.assertEqual(self.pin_option.pinned_values, [])

    def test_pin_value_programmatically(self):
        """Test pinning values programmatically."""
        self.widget.setText("Test Value 1")
        self.pin_option.add_pinned_value("Test Value 1")

        self.assertTrue(self.pin_option.has_pinned_values)
        self.assertIn("Test Value 1", self.pin_option.pinned_values)

    def test_multiple_pinned_values(self):
        """Test pinning multiple values."""
        self.pin_option.add_pinned_value("Value 1")
        self.pin_option.add_pinned_value("Value 2")
        self.pin_option.add_pinned_value("Value 3")

        self.assertEqual(len(self.pin_option.pinned_values), 3)

    def test_max_pinned_values(self):
        """Test that max pinned values is respected."""
        # Create option with small max
        pin_option = PinValuesOption(self.widget, max_pinned=3)

        pin_option.add_pinned_value("Value 1")
        pin_option.add_pinned_value("Value 2")
        pin_option.add_pinned_value("Value 3")
        pin_option.add_pinned_value("Value 4")

        self.assertEqual(len(pin_option.pinned_values), 3)
        # Most recent should be first
        self.assertEqual(pin_option.pinned_values[0], "Value 4")

    def test_clear_pinned_values(self):
        """Test clearing all pinned values."""
        self.pin_option.add_pinned_value("Value 1")
        self.pin_option.add_pinned_value("Value 2")

        self.pin_option.clear_pinned_values()

        self.assertFalse(self.pin_option.has_pinned_values)
        self.assertEqual(self.pin_option.pinned_values, [])

    def test_signals(self):
        """Test that signals are emitted correctly."""
        pinned_values = []
        restored_values = []

        self.pin_option.value_pinned.connect(
            lambda pinned, value: pinned_values.append((pinned, value))
        )
        self.pin_option.value_restored.connect(
            lambda value: restored_values.append(value)
        )

        # Pin a value
        self.pin_option.add_pinned_value("Test")
        self.assertEqual(len(pinned_values), 1)
        self.assertEqual(pinned_values[0], (True, "Test"))


def run_interactive_demo():
    """Run an interactive demo of the PinValuesOption."""
    # Create main window
    window = QtWidgets.QWidget()
    window.setWindowTitle("PinValuesOption Demo")
    window.resize(400, 300)
    layout = QtWidgets.QVBoxLayout(window)

    # Create a line edit with pin option
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

    # Add some instructions
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

    # Add a spinbox test
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


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_interactive_demo()
    else:
        unittest.main()
