import unittest
from unittest.mock import MagicMock
import inspect
from uitk.switchboard import Switchboard


class TestSwitchboard(unittest.TestCase):
    def setUp(self):
        self.switchboard = Switchboard()
        self.mock_widget = MagicMock()

    def test_slot_wrapper_without_widget(self):
        def my_slot(a, b):
            return a + b

        wrapped_slot = self.switchboard._create_slot_wrapper(my_slot, self.mock_widget)
        result = wrapped_slot(1, 2)
        self.assertEqual(result, 3)

    def test_slot_wrapper_with_widget(self):
        def my_slot(a, b, widget=None):
            return a + b + (widget.value if widget else 0)

        self.mock_widget.value = 10
        wrapped_slot = self.switchboard._create_slot_wrapper(my_slot, self.mock_widget)
        result = wrapped_slot(1, 2)
        self.assertEqual(result, 13)

    def test_slot_wrapper_with_kwargs(self):
        def my_slot(a, b, **kwargs):
            return a + b + kwargs.get("extra", 0)

        wrapped_slot = self.switchboard._create_slot_wrapper(my_slot, self.mock_widget)
        result = wrapped_slot(1, 2, extra=3)
        self.assertEqual(result, 6)

    def test_slot_wrapper_with_unexpected_widget(self):
        def my_slot(a, b):
            return a + b

        wrapped_slot = self.switchboard._create_slot_wrapper(my_slot, self.mock_widget)

        try:
            result = wrapped_slot(1, 2, widget=self.mock_widget)
            self.assertEqual(result, 3)
        except TypeError:
            self.fail("Unexpected TypeError raised")

    def test_slot_history_is_updated(self):
        def my_slot(a, b):
            return a + b

        wrapped_slot = self.switchboard._create_slot_wrapper(my_slot, self.mock_widget)
        wrapped_slot(1, 2)

        self.assertTrue(
            self.switchboard.slot_history
        )  # Assumes slot_history() adds to an internal list or similar


if __name__ == "__main__":
    unittest.main()
