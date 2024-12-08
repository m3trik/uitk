import unittest

# from qtpy import QtWidgets
from uitk.switchboard import Switchboard


class TestSwitchboard(unittest.TestCase):
    def setUp(self):
        from uitk import example

        self.sb = Switchboard(ui_source=example, slot_source=example.example_slots)
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


class TestCreateButtonGroups(unittest.TestCase):
    def setUp(self):
        from uitk import example

        self.sb = Switchboard(ui_source=example, slot_source=example.example_slots)
        self.ui = self.sb.example

        self.chk000 = self.ui.button_b.menu.add(
            "QCheckBox", setObjectName="chk000", setText="Option A", setChecked=True
        )
        self.chk001 = self.ui.button_b.menu.add(
            "QCheckBox", setObjectName="chk001", setText="Option B"
        )
        self.chk002 = self.ui.button_b.menu.add(
            "QCheckBox", setObjectName="chk002", setText="Option C"
        )

    def test_create_button_groups_allow_deselect(self):
        # Test allow_deselect functionality
        self.sb.create_button_groups(
            self.ui.button_b.menu,
            "chk000-2",
            allow_deselect=True,
            allow_multiple=False,
        )

        self.chk000.setChecked(True)
        self.assertTrue(self.chk000.isChecked())

        # Click the same button again to deselect
        self.chk000.click()
        self.assertFalse(self.chk000.isChecked(), "Button should be deselected")

    def test_create_button_groups_allow_multiple(self):
        # Test allow_multiple functionality
        self.sb.create_button_groups(
            self.ui.button_b.menu,
            "chk000-2",
            allow_deselect=False,
            allow_multiple=True,
        )

        self.chk000.setChecked(True)
        self.chk001.setChecked(True)

        self.assertTrue(self.chk000.isChecked())
        self.assertTrue(self.chk001.isChecked())
        self.assertFalse(self.chk002.isChecked())

    def test_create_button_groups_exclusive(self):
        # Test exclusive group (neither allow_deselect nor allow_multiple)
        self.sb.create_button_groups(
            self.ui.button_b.menu,
            "chk000-2",
            allow_deselect=False,
            allow_multiple=False,
        )

        self.chk000.setChecked(True)
        self.chk001.setChecked(True)

        self.assertFalse(self.chk000.isChecked(), "Button 1 should be unchecked")
        self.assertTrue(self.chk001.isChecked())


if __name__ == "__main__":
    unittest.main()
