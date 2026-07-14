# !/usr/bin/python
# coding=utf-8
"""Smoke tests for the uitk package export surface.

Every symbol registered in ``uitk.DEFAULT_INCLUDE`` must resolve through the
lazy package ``__getattr__``. A stale entry (a module that no longer exists, a
class that was renamed/removed) resolves to AttributeError only on first touch,
so it ships silently and pollutes the auto-generated API registry.

Run standalone: python -m test.test_package_exports
"""

import unittest

from conftest import setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

import uitk


class TestDefaultIncludeResolves(unittest.TestCase):
    """Every DEFAULT_INCLUDE symbol must be resolvable from the uitk root."""

    def test_every_registered_symbol_resolves(self):
        failures = []
        for module_path, symbols in uitk.DEFAULT_INCLUDE.items():
            names = [symbols] if isinstance(symbols, str) else list(symbols)
            for name in names:
                try:
                    resolved = getattr(uitk, name)
                except Exception as e:  # AttributeError (or wrapped ImportError)
                    failures.append(f"{name} ({module_path}): {type(e).__name__}: {e}")
                    continue
                if resolved is None:
                    failures.append(f"{name} ({module_path}): resolved to None")

        self.assertEqual(
            failures,
            [],
            "Unresolvable DEFAULT_INCLUDE exports:\n  " + "\n  ".join(failures),
        )


if __name__ == "__main__":
    unittest.main()
