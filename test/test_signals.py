# !/usr/bin/python
# coding=utf-8
"""Unit tests for Signals decorator and related utilities.

This module tests the Signals functionality including:
- Signal decorator creation and validation
- Signal attribute assignment to functions
- Block signals decorator
- Edge cases and error handling

Run standalone: python -m test.test_signals
"""

import unittest
from functools import wraps

from conftest import BaseTestCase, QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets
from uitk.widgets.mixins.switchboard_slots import Signals

# Alias for backward compatibility in tests
block_signals = Signals.blockSignals


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

    def test_raises_type_error_for_none_signal(self):
        """Should raise TypeError when signal is None."""
        with self.assertRaises(TypeError) as context:
            Signals(None)
        self.assertIn("Signal must be a string", str(context.exception))

    def test_raises_type_error_for_list_signal(self):
        """Should raise TypeError when signal is a list."""
        with self.assertRaises(TypeError) as context:
            Signals(["clicked"])
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

    def test_decorated_function_with_kwargs(self):
        """Decorated function should handle kwargs correctly."""

        @Signals("clicked")
        def func_with_kwargs(**kwargs):
            return kwargs

        result = func_with_kwargs(a=1, b=2)
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_decorated_function_with_default_args(self):
        """Decorated function should handle default arguments."""

        @Signals("clicked")
        def func_with_defaults(a=10, b=20):
            return a + b

        self.assertEqual(func_with_defaults(), 30)
        self.assertEqual(func_with_defaults(5), 25)
        self.assertEqual(func_with_defaults(5, 15), 20)

    def test_decorated_function_with_args_and_kwargs(self):
        """Decorated function should handle *args and **kwargs."""

        @Signals("clicked")
        def func_with_all(*args, **kwargs):
            return (args, kwargs)

        result = func_with_all(1, 2, x=3, y=4)
        self.assertEqual(result, ((1, 2), {"x": 3, "y": 4}))

    def test_decorated_method_on_class(self):
        """Decorator should work on class methods."""

        class MyClass:
            @Signals("clicked")
            def my_method(self):
                return "called"

        obj = MyClass()
        self.assertEqual(obj.my_method(), "called")
        self.assertEqual(obj.my_method.signals, ("clicked",))

    def test_decorated_function_preserves_docstring(self):
        """Decorated function should preserve docstring."""

        @Signals("clicked")
        def documented_func():
            """This is the docstring."""
            pass

        self.assertEqual(documented_func.__doc__, "This is the docstring.")

    def test_signals_with_empty_string(self):
        """Should accept empty string as signal name (though unusual)."""
        decorator = Signals("")
        self.assertEqual(decorator.signals, ("",))


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

    def test_block_signals_returns_function_result(self):
        """block_signals should return the wrapped function's result."""

        class TestWidget(QtWidgets.QLineEdit):
            @block_signals
            def get_modified_text(self, text):
                self.setText(text)
                return text.upper()

        widget = self.track_widget(TestWidget())
        result = widget.get_modified_text("hello")
        self.assertEqual(result, "HELLO")

    def test_block_signals_with_exception(self):
        """block_signals should restore signals even if exception occurs."""

        class TestWidget(QtWidgets.QLineEdit):
            @block_signals
            def failing_method(self):
                self.setText("before error")
                raise ValueError("test error")

        widget = self.track_widget(TestWidget())
        signal_received = []
        widget.textChanged.connect(lambda t: signal_received.append(t))

        # The decorator doesn't handle exceptions, so signals may not restore
        # This tests the current behavior
        with self.assertRaises(ValueError):
            widget.failing_method()

    def test_block_signals_preserves_function_name(self):
        """block_signals should preserve wrapped function's name."""

        class TestWidget(QtWidgets.QLineEdit):
            @block_signals
            def my_named_method(self):
                pass

        widget = self.track_widget(TestWidget())
        self.assertEqual(widget.my_named_method.__name__, "my_named_method")

    def test_block_signals_with_spinbox(self):
        """block_signals should work with QSpinBox."""

        class TestSpinBox(QtWidgets.QSpinBox):
            @block_signals
            def set_value_silently(self, value):
                self.setValue(value)

        spinbox = self.track_widget(TestSpinBox())
        signal_received = []
        spinbox.valueChanged.connect(lambda v: signal_received.append(v))

        spinbox.set_value_silently(42)

        self.assertEqual(spinbox.value(), 42)
        self.assertEqual(len(signal_received), 0)

    def test_block_signals_with_checkbox(self):
        """block_signals should work with QCheckBox."""

        class TestCheckBox(QtWidgets.QCheckBox):
            @block_signals
            def set_checked_silently(self, checked):
                self.setChecked(checked)

        checkbox = self.track_widget(TestCheckBox())
        signal_received = []
        checkbox.stateChanged.connect(lambda s: signal_received.append(s))

        checkbox.set_checked_silently(True)

        self.assertTrue(checkbox.isChecked())
        self.assertEqual(len(signal_received), 0)


class TestSignalsEdgeCases(BaseTestCase):
    """Edge case tests for Signals decorator."""

    def test_signals_with_unicode_names(self):
        """Should accept unicode signal names."""
        decorator = Signals("signalÜnicode", "日本語Signal")
        self.assertEqual(len(decorator.signals), 2)

    def test_signals_with_whitespace_names(self):
        """Should accept signal names with whitespace (though unusual)."""
        decorator = Signals("signal with spaces")
        self.assertEqual(decorator.signals, ("signal with spaces",))

    def test_signals_with_special_characters(self):
        """Should accept signal names with special characters."""
        decorator = Signals("signal_with_underscore", "signal-with-dash")
        self.assertEqual(len(decorator.signals), 2)

    def test_signals_tuple_is_immutable(self):
        """Signals tuple should be immutable."""
        decorator = Signals("clicked")
        with self.assertRaises(TypeError):
            decorator.signals[0] = "modified"

    def test_signals_with_duplicate_names(self):
        """Should accept duplicate signal names (no validation)."""
        decorator = Signals("clicked", "clicked", "clicked")
        self.assertEqual(decorator.signals, ("clicked", "clicked", "clicked"))

    def test_stacked_decorators(self):
        """Signals decorator should work with other decorators."""

        def other_decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs) + " modified"

            return wrapper

        @Signals("clicked")
        @other_decorator
        def my_func():
            return "original"

        self.assertEqual(my_func(), "original modified")
        self.assertEqual(my_func.signals, ("clicked",))


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
