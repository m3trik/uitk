import unittest
from uitk.switchboard import Switchboard


class TestSwitchboard(unittest.TestCase):
    def setUp(self):
        from uitk import example

        self.sb = Switchboard(ui_location=example, slot_location=example.example_slots)
        self.ui = self.sb.example

    def test_slot_wrapper_variants(self):
        test_cases = [
            {"widget_obj": self.ui.button_a, "args": [], "expected": None},
            {"widget_obj": self.ui.button_b, "args": [], "expected": None},
            {"widget_obj": self.ui.spinbox, "args": [5], "expected": None},
            {"widget_obj": self.ui.checkbox, "args": [True], "expected": None},
        ]

        for case in test_cases:
            with self.subTest(case=case):
                result = case["widget_obj"].call_slot(*case["args"])
                self.assertEqual(result, case["expected"])


if __name__ == "__main__":
    unittest.main()
