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


class TestRequirementRanges(BaseTestCase):
    """A full specifier set is a superset of the ``>=`` floor these read
    before: one ``ptk.PackageRequirement``, the reader the external-app
    handler checks a provider's range with."""

    def setUp(self):
        import pythontk as ptk

        super().setUp()
        self.ptk = ptk
        self.addCleanup(setattr, ptk, "__version__", ptk.__version__)

    def test_split_reads_the_name_and_inclusive_floor_of_a_range(self):
        split = OptionalPackageManager.split_requirement
        self.assertEqual(split("extapps>=0.8.0,<0.9"), ("extapps", (0, 8, 0)))
        self.assertEqual(split("extapps <0.9, >= 0.8.1"), ("extapps", (0, 8, 1)))
        self.assertEqual(split("extapps~=0.8.2"), ("extapps", (0, 8, 2)))
        self.assertEqual(split("extapps<0.9"), ("extapps", None))
        # A spec the reader does not parse still yields its name, never raises.
        self.assertEqual(split("extapps @ https://example.com/e.whl")[0], "extapps")

    def test_available_honours_a_cap_and_pre_release_order(self):
        available = OptionalPackageManager.available
        self.ptk.__version__ = "0.8.5"
        self.assertTrue(available("pythontk>=0.8.0,<0.9"))
        self.ptk.__version__ = "0.9.0"
        self.assertFalse(available("pythontk>=0.8.0,<0.9"))
        # A release candidate is not yet the release a floor names.
        self.ptk.__version__ = "0.8.0rc1"
        self.assertFalse(available("pythontk>=0.8.0"))

    def test_ensure_offers_an_update_naming_the_installed_version(self):
        prompts = []

        def prompt(message, *buttons):
            prompts.append(message)
            return "Yes"

        installed = []
        mgr = OptionalPackageManager(prompt=prompt, installer=installed.append)
        self.ptk.__version__ = "0.9.1"  # above the cap: an update, then a restart
        self.assertFalse(mgr.ensure("pythontk>=0.8.0,<0.9"))
        self.assertEqual(installed, ["pythontk>=0.8.0,<0.9"])
        self.assertIn("update", prompts[0].lower())
        self.assertIn("0.9.1", prompts[0])
        # The prompt is HTML: the cap's "<" arrives escaped, not as a tag.
        self.assertIn("&lt;0.9", prompts[0])
        self.assertIn("restart", prompts[1].lower())


if __name__ == "__main__":
    unittest.main()
