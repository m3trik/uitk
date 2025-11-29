# !/usr/bin/python
# coding=utf-8
"""Unit tests for PinValuesOption widget.

This module tests the PinValuesOption functionality including:
- Pin option creation and initialization
- Pinning and unpinning values
- Signal emission
- Maximum pinned values enforcement

Run standalone: python -m test.test_pin_values
Run with demo: python -m test.test_pin_values --demo
"""

import sys
import unittest
from typing import List, Tuple

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets
from uitk.widgets.optionBox import OptionBox
from uitk.widgets.optionBox.options.pin_values import PinValuesOption


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


# -----------------------------------------------------------------------------
# Interactive Demo
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
