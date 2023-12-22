import unittest

# from PySide2 import QtWidgets
from uitk.switchboard import Switchboard


class TestSwitchboard(unittest.TestCase):
    def setUp(self):
        from uitk import example

        self.sb = Switchboard(ui_location=example, slot_location=example.example_slots)
        self.ui = self.sb.example

    def test_slot_wrapper_variants(self):
        def test_wrapper(fn):
            def wrapper(*args, **kwargs):
                if args and hasattr(args[0], "__class__"):
                    self = args[0]
                    fn(self, *args[1:], **kwargs)
                else:
                    fn(*args, **kwargs)

            return wrapper

        actual_button_a_method = self.ui.button_a.get_slot()
        wrapped_button_a = test_wrapper(actual_button_a_method)

        test_cases = [
            {
                "widget_obj": self.ui.button_a,
                "method": "call_slot",
                "args": [],
                "self_obj": self.ui.button_a,
                "expected": None,
            },
            {
                "widget_obj": wrapped_button_a,
                "method": None,
                "args": [],
                "self_obj": self.ui.button_a,
                "expected": None,
            },
            {
                "widget_obj": self.ui.button_b,
                "method": "call_slot",
                "args": [],
                "self_obj": self.ui.button_b,
                "expected": None,
            },
            {
                "widget_obj": self.ui.spinbox,
                "method": "call_slot",
                "args": [5],
                "self_obj": self.ui.spinbox,
                "expected": None,
            },
            {
                "widget_obj": self.ui.checkbox,
                "method": "call_slot",
                "args": [True],
                "self_obj": self.ui.checkbox,
                "expected": None,
            },
            # Simulate textChanged signal with text
            {
                "widget_obj": self.ui.textedit,
                "method": "call_slot",
                "args": ["sample text"],
                "self_obj": self.ui.textedit,
                "expected": None,
            },
            # Simulate returnPressed signal with no additional text
            {
                "widget_obj": self.ui.textedit,
                "method": "call_slot",
                "args": [],
                "self_obj": self.ui.textedit,
                "expected": None,
            },
        ]

        for case in test_cases:
            with self.subTest(case=case):
                if case["method"]:
                    result = getattr(case["widget_obj"], case["method"])(*case["args"])
                else:
                    result = case["widget_obj"](case["self_obj"], *case["args"])

                self.assertEqual(result, case["expected"])

    def test_store_and_restore_widget_state(self):
        test_cases = [
            {
                "widget_name": "spinbox",
                "setter": lambda w, v: w.setValue(v),
                "getter": lambda w: w.value(),
                "initial_value": 5,
                "new_value": 10,
            },
            {
                "widget_name": "checkbox",
                "setter": lambda w, v: w.setChecked(v),
                "getter": lambda w: w.isChecked(),
                "initial_value": True,
                "new_value": False,
            },
            {
                "widget_name": "button_a",
                "setter": lambda w, v: w.setText(v),
                "getter": lambda w: w.text(),
                "initial_value": "Text A",
                "new_value": "New Text",
            },
        ]

        for case in test_cases:
            with self.subTest(case=case):
                widget_name = case["widget_name"]
                widget = getattr(self.ui, widget_name)
                setter = case["setter"]
                getter = case["getter"]
                initial_value = case["initial_value"]
                new_value = case["new_value"]

                # Set initial state, change it, and close the UI
                setter(widget, initial_value)
                setter(widget, new_value)
                self.ui.close()

                # Re-open the UI and verify the state is as expected
                self.ui = self.sb.example
                widget = getattr(self.ui, widget_name)
                self.assertEqual(getter(widget), new_value)

                # Cleanup: Close the UI to restore the original state
                self.ui.close()


if __name__ == "__main__":
    unittest.main()
