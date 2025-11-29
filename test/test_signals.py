# !/usr/bin/python
# coding=utf-8
"""Unit tests for Signals decorator and related utilities.

This module tests the Signals functionality including:
- Signal decorator creation and validation
- Signal attribute assignment to functions
- Block signals decorator

Run standalone: python -m test.test_signals
"""

import unittest
from functools import wraps

from conftest import BaseTestCase, QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets
from uitk.signals import Signals, block_signals


class TestSignalsDecoratorCreation(BaseTestCase):
    """Tests for Signals decorator creation and validation."""

    def test_creates_decorator_with_single_signal(self):
        """Should create a decorator with a single signal name."""
        decorator = Signals("clicked")
        self.assertEqual(decorator.signals, ("clicked",))

    def test_creates_decorator_with_multiple_signals(self):
        """Should create a decorator with multiple signal names."""
        decorator = Signals("clicked", "pressed", "released")
        self.assertEqual(decorator.signals, ("clicked", "pressed", "released"))

    def test_raises_value_error_when_no_signals(self):
        """Should raise ValueError when no signals are provided."""
        with self.assertRaises(ValueError) as context:
            Signals()
        self.assertIn("At least one signal must be specified", str(context.exception))

    def test_raises_type_error_for_non_string_signal(self):
        """Should raise TypeError when signal is not a string."""
        with self.assertRaises(TypeError) as context:
            Signals(123)
        self.assertIn("Signal must be a string", str(context.exception))

    def test_raises_type_error_for_mixed_types(self):
        """Should raise TypeError when signals contain non-string values."""
        with self.assertRaises(TypeError) as context:
            Signals("clicked", 456, "released")
        self.assertIn("Signal must be a string", str(context.exception))


class TestSignalsDecoratorApplication(BaseTestCase):
    """Tests for applying the Signals decorator to functions."""

    def test_decorated_function_has_signals_attribute(self):
        """Decorated function should have signals attribute."""

        @Signals("clicked")
        def my_slot():
            pass

        self.assertTrue(hasattr(my_slot, "signals"))
        self.assertEqual(my_slot.signals, ("clicked",))

    def test_decorated_function_preserves_behavior(self):
        """Decorated function should preserve original behavior."""

        @Signals("clicked")
        def add_numbers(a, b):
            return a + b

        result = add_numbers(3, 5)
        self.assertEqual(result, 8)

    def test_decorated_function_preserves_name(self):
        """Decorated function should preserve function name."""

        @Signals("clicked")
        def my_custom_slot():
            pass

        self.assertEqual(my_custom_slot.__name__, "my_custom_slot")

    def test_multiple_signals_on_function(self):
        """Function should store multiple signals."""

        @Signals("textChanged", "returnPressed")
        def on_text_input():
            pass

        self.assertEqual(on_text_input.signals, ("textChanged", "returnPressed"))


class TestBlockSignalsDecorator(QtBaseTestCase):
    """Tests for the block_signals decorator."""

    def setUp(self):
        super().setUp()
        self.widget = self.track_widget(QtWidgets.QLineEdit())
        self.signal_received = False
        self.widget.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text):
        """Slot to track signal emission."""
        self.signal_received = True

    def test_block_signals_prevents_signal_emission(self):
        """block_signals decorator should prevent signals during method execution."""

        class TestWidget(QtWidgets.QLineEdit):
            @block_signals
            def set_text_silently(self, text):
                self.setText(text)

        widget = self.track_widget(TestWidget())
        signal_received = []
        widget.textChanged.connect(lambda t: signal_received.append(t))

        widget.set_text_silently("silent text")

        self.assertEqual(widget.text(), "silent text")
        self.assertEqual(len(signal_received), 0)

    def test_block_signals_restores_signals_after(self):
        """block_signals should restore signal emission after method completes."""

        class TestWidget(QtWidgets.QLineEdit):
            @block_signals
            def set_text_silently(self, text):
                self.setText(text)

        widget = self.track_widget(TestWidget())
        signal_received = []
        widget.textChanged.connect(lambda t: signal_received.append(t))

        widget.set_text_silently("silent")
        widget.setText("loud")

        self.assertEqual(len(signal_received), 1)
        self.assertEqual(signal_received[0], "loud")

    def test_block_signals_class_method_access(self):
        """blockSignals should be accessible as class method on Signals."""
        self.assertTrue(hasattr(Signals, "blockSignals"))
        self.assertTrue(callable(Signals.blockSignals))


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
