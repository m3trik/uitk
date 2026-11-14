#!/usr/bin/python
# coding=utf-8
"""``WidgetSpec``: what a widget built from a setter-kwargs spec reads at rest,
with no widget built and no Qt binding imported -- how a headless caller runs
with a fresh panel's values (Unity Scripts' Send to Unity runs the Scene
Exporter with them)."""

import subprocess
import sys
import unittest
from pathlib import Path

from uitk.managers.widget_spec import WidgetSpec


class TestWidgetSpec(unittest.TestCase):
    def test_each_widget_kind_reads_its_default(self):
        self.assertEqual(WidgetSpec.default({"widget_type": "QCheckBox", "setChecked": True}), (True, True))
        self.assertEqual(WidgetSpec.default({"widget_type": "QCheckBox", "setText": "Label"}), (True, False))
        combo = {"widget_type": "ComboBox", "add": {"Off": None, "Scene": "scene"}, "setCurrentIndex": 1}
        self.assertEqual(WidgetSpec.default(combo), (True, "scene"))
        built = {"widget_type": "ComboBox", "add": lambda: ["a", "b"]}
        self.assertEqual(WidgetSpec.default(built), (True, "a"), "a list's labels are its data")
        self.assertEqual(WidgetSpec.default({"widget_type": "ComboBox"}), (False, None), "no items, no value")
        self.assertEqual(WidgetSpec.default({"widget_type": "SpinBox", "setValue": 0.5}), (True, 0.5))
        self.assertEqual(WidgetSpec.default({"widget_type": "QLineEdit"}), (True, ""))

    def test_a_table_reads_by_the_key_its_caller_names(self):
        table = {
            "export_data": {"widget_type": "QCheckBox", "setChecked": True},
            "floor": {"widget_type": "SpinBox", "object_name": "floor_depth", "setValue": 2},
            "empty": {"widget_type": "ComboBox"},
        }
        values = WidgetSpec.defaults(table, lambda name, spec: spec.get("object_name") or name)
        self.assertEqual(values, {"export_data": True, "floor_depth": 2})

    def test_it_imports_no_qt(self):
        root = Path(__file__).resolve().parents[1]
        code = "import sys; from uitk import WidgetSpec; WidgetSpec.default({}); print('qtpy' in sys.modules)"
        out = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.stdout.strip(), "False", out.stderr)


if __name__ == "__main__":
    unittest.main()
