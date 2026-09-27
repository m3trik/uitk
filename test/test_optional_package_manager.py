# !/usr/bin/python
# coding=utf-8
"""Tests for uitk.managers.optional_package_manager."""

import sys
import unittest
from unittest.mock import MagicMock, patch

from conftest import BaseTestCase
from uitk.managers.optional_package_manager import OptionalPackageManager


class TestDefaultInstall(BaseTestCase):
    def _install(self, prefix, base_prefix):
        pm = MagicMock()
        with (
            patch.object(
                OptionalPackageManager, "pip_python", return_value=sys.executable
            ),
            patch("pythontk.PackageManager", return_value=pm) as pm_cls,
            patch.object(sys, "prefix", prefix),
            patch.object(sys, "base_prefix", base_prefix),
        ):
            OptionalPackageManager.default_install("somepkg")
        self.assertEqual(pm_cls.call_args.kwargs["python_path"], sys.executable)
        return pm.pip.call_args.args[0]

    def test_a_venv_interpreter_installs_into_the_venv(self):
        """pip refuses ``--user`` inside a venv ("user site-packages are not
        visible"), so every on-demand install from a venv-hosted app failed."""
        self.assertEqual(self._install("/work/venv", "/usr"), "install somepkg")

    def test_a_plain_interpreter_still_installs_per_user(self):
        self.assertEqual(self._install("/usr", "/usr"), "install --user somepkg")


if __name__ == "__main__":
    unittest.main()
