# !/usr/bin/python
# coding=utf-8
"""Unit tests for ``uitk.bridge.attribute_spec`` -- the Qt-free spec half.

A bridge registry (``PARAMS = {key: AttributeSpec(...)}``) is declared at
module import, including in processes with no Qt binding (a headless engine, a
test of a registry's contents). The spec must therefore import -- through every
public path -- without one; only :class:`~uitk.bridge.spec.KindFactory` builds
widgets.
"""

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class TestAttributeSpecWithoutQt(unittest.TestCase):
    def _run_without_qt(self, body: str) -> subprocess.CompletedProcess:
        """Run *body* in a fresh interpreter where every Qt binding is blocked."""
        script = textwrap.dedent(
            """
            import sys
            for name in ("qtpy", "PySide6", "PySide2", "PyQt5", "PyQt6"):
                sys.modules[name] = None
            sys.path.insert(0, {root!r})
            """
        ).format(root=str(PACKAGE_ROOT)) + textwrap.dedent(body)
        return subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=120
        )

    def test_every_public_path_resolves_without_a_binding(self):
        result = self._run_without_qt(
            """
            import uitk
            from uitk.bridge import AttributeSpec
            from uitk.bridge.attribute_spec import AttributeSpec as Direct
            assert AttributeSpec is Direct is uitk.AttributeSpec
            spec = AttributeSpec(key="SIZE", kind="choice", default=1024,
                                 choices=[("1K", 1024), ("2K", 2048)])
            assert spec.display_label == "SIZE"
            assert "uitk.bridge.spec" not in sys.modules
            print("OK")
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)


class TestInferKind(unittest.TestCase):
    def test_bool_before_int(self):
        from uitk.bridge.attribute_spec import AttributeSpec

        self.assertEqual(AttributeSpec.infer_kind(True), "bool")
        self.assertEqual(AttributeSpec.infer_kind(3), "int")
        self.assertEqual(AttributeSpec.infer_kind(1.5), "float")
        self.assertEqual(AttributeSpec.infer_kind("a"), "str")
        self.assertEqual(AttributeSpec.infer_kind([1, 2]), "str")

    def test_from_value_uses_the_inferred_kind(self):
        from uitk.bridge.attribute_spec import AttributeSpec

        spec = AttributeSpec.from_value("flag", False)
        self.assertEqual((spec.kind, spec.default, spec.label), ("bool", False, "flag"))

    def test_kind_factory_agrees(self):
        """``KindFactory.infer_kind`` is the same rule, not a second copy."""
        from uitk.bridge.attribute_spec import AttributeSpec
        from uitk.bridge.spec import KindFactory

        for value in (True, 0, 0.0, "", None, (1,)):
            self.assertEqual(
                KindFactory.infer_kind(value), AttributeSpec.infer_kind(value)
            )

    def test_empty_key_is_refused(self):
        from uitk.bridge.attribute_spec import AttributeSpec

        with self.assertRaises(ValueError):
            AttributeSpec(key="")


if __name__ == "__main__":
    unittest.main()
