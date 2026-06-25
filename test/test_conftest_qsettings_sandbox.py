# !/usr/bin/python
# coding=utf-8
"""Meta-test for the conftest QSettings sandbox (``_sandbox_qsettings``).

The sandbox is what keeps the whole suite off the developer's real settings
store. It guards two regressions that already bit once:

* an *inert* sandbox — the first attempt used only ``setDefaultFormat`` /
  ``setPath``, which are a no-op for the ``QSettings(org, app)`` overload on
  Windows (that overload always uses NativeFormat / the registry); and
* the original field bug — a test cleared the live ``(uitk, shared)`` store and
  silently reset the user's marking-menu bindings, widget state, and theme.

If any of these fail, the suite can reach the real registry again.
"""
import os
import unittest

from conftest import BaseTestCase, setup_qt_application, QSETTINGS_SANDBOX_DIR

app = setup_qt_application()

from qtpy import QtCore  # noqa: E402
from uitk.widgets.mixins.settings_manager import (  # noqa: E402
    DEFAULT_APP_NAME,
    DEFAULT_ORG_NAME,
    SettingsManager,
)


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


class TestQSettingsSandbox(BaseTestCase):
    """Every registry-bound QSettings overload must land in the temp sandbox."""

    SANDBOX = _norm(QSETTINGS_SANDBOX_DIR)

    def _assert_sandboxed(self, qs):
        self.assertEqual(qs.format(), QtCore.QSettings.IniFormat)
        self.assertTrue(
            _norm(qs.fileName()).startswith(self.SANDBOX),
            f"{qs.fileName()!r} escaped sandbox {QSETTINGS_SANDBOX_DIR!r}",
        )

    def test_org_app_overload_redirected(self):
        # The production overload + production names — must NOT hit the registry.
        self._assert_sandboxed(QtCore.QSettings(DEFAULT_ORG_NAME, DEFAULT_APP_NAME))

    def test_org_app_parent_overload_redirected(self):
        # (org, app, parent) is registry-bound too; a future test passing a
        # parent must not slip past the guard.
        self._assert_sandboxed(
            QtCore.QSettings(DEFAULT_ORG_NAME, DEFAULT_APP_NAME, app)
        )

    def test_scope_org_app_overload_redirected(self):
        self._assert_sandboxed(
            QtCore.QSettings(
                QtCore.QSettings.UserScope, DEFAULT_ORG_NAME, DEFAULT_APP_NAME
            )
        )

    def test_isinstance_and_enum_preserved(self):
        # Subclassing (not a factory fn) must keep these working for callers.
        qs = QtCore.QSettings(DEFAULT_ORG_NAME, DEFAULT_APP_NAME)
        self.assertIsInstance(qs, QtCore.QSettings)
        self.assertIsNotNone(QtCore.QSettings.IniFormat)

    def test_explicit_ini_path_passthrough(self):
        # (fileName, format) keeps its explicit path — it is NOT rewritten to
        # the org/app layout (which would clobber a test's own temp file).
        target = os.path.join(QSETTINGS_SANDBOX_DIR, "explicit_probe.ini")
        qs = QtCore.QSettings(target, QtCore.QSettings.IniFormat)
        self.assertEqual(os.path.basename(qs.fileName()), "explicit_probe.ini")

    def test_settings_manager_production_path_sandboxed(self):
        # The real production wiring (Switchboard uses namespace="switchboard")
        # — the end-to-end proof that production code can't reach the registry.
        sm = SettingsManager(namespace="switchboard")
        self._assert_sandboxed(sm.settings)


if __name__ == "__main__":
    unittest.main()
