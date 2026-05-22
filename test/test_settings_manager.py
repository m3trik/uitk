# !/usr/bin/python
# coding=utf-8
"""Tests for SettingsManager defaults and legacy registry migration.

Touches the real registry — but only under test-prefixed orgs
(``test_uitk_*``) so it can't disturb real user data. Every test cleans
up its own keys in tearDown via ``QSettings.clear()``.
"""

import unittest
from typing import List, Tuple

from qtpy import QtCore

from conftest import BaseTestCase, setup_qt_application

app = setup_qt_application()

import uitk.widgets.mixins.settings_manager as sm  # noqa: E402
from uitk.widgets.mixins.settings_manager import (  # noqa: E402
    DEFAULT_APP_NAME,
    DEFAULT_ORG_NAME,
    SettingsManager,
)


def _wipe(org: str, app: str) -> None:
    """Best-effort wipe of a (org, app) QSettings location."""
    qs = QtCore.QSettings(org, app)
    qs.clear()
    qs.sync()


class TestSettingsManagerDefaults(BaseTestCase):
    """``SettingsManager`` with no args lands at the consolidated location."""

    def setUp(self):
        super().setUp()
        # Reset the process-cache so each test exercises the migration check.
        sm._MIGRATED_REGISTRY_PAIRS.clear()
        _wipe(DEFAULT_ORG_NAME, DEFAULT_APP_NAME)

    def tearDown(self):
        _wipe(DEFAULT_ORG_NAME, DEFAULT_APP_NAME)
        super().tearDown()

    def test_no_arg_construction_uses_uitk_shared(self):
        mgr = SettingsManager()
        self.assertEqual(mgr.settings.organizationName(), DEFAULT_ORG_NAME)
        self.assertEqual(mgr.settings.applicationName(), DEFAULT_APP_NAME)

    def test_namespace_only_construction_uses_default_org_app(self):
        mgr = SettingsManager(namespace="some_feature")
        self.assertEqual(mgr.settings.organizationName(), DEFAULT_ORG_NAME)
        self.assertEqual(mgr.settings.applicationName(), DEFAULT_APP_NAME)
        self.assertEqual(mgr.namespace, "some_feature")


class TestRegistryMigration(BaseTestCase):
    """Drain legacy QSettings (org, app) pairs into the consolidated layout."""

    TEST_NEW_ORG = "test_uitk_new"
    TEST_LEGACY_ORG_A = "test_uitk_legacy_widgets"
    TEST_LEGACY_ORG_B = "test_uitk_legacy_mixins"
    TEST_APP = "test_widget"
    TEST_SHARED_APP = "test_shared"
    TEST_LEGACY_DEFAULT_APP = "test_legacy_default_app"

    _saved_pairs_fn = None

    def setUp(self):
        super().setUp()
        # Override the legacy-pair function so production data is never touched.
        self._saved_pairs_fn = sm._legacy_qsettings_pairs_for

        def fake_pairs(new_org: str, new_app: str) -> List[Tuple[str, str]]:
            if new_org != self.TEST_NEW_ORG:
                return []
            pairs = [(self.TEST_LEGACY_ORG_A, new_app)]
            if new_app == self.TEST_SHARED_APP:
                pairs.append((self.TEST_LEGACY_ORG_B, self.TEST_LEGACY_DEFAULT_APP))
            return pairs

        sm._legacy_qsettings_pairs_for = fake_pairs

        # Reset process-cache so each test triggers the migration check.
        sm._MIGRATED_REGISTRY_PAIRS.clear()

        # Wipe both legacy and new test locations.
        for org, app in [
            (self.TEST_NEW_ORG, self.TEST_APP),
            (self.TEST_NEW_ORG, self.TEST_SHARED_APP),
            (self.TEST_LEGACY_ORG_A, self.TEST_APP),
            (self.TEST_LEGACY_ORG_A, self.TEST_SHARED_APP),
            (self.TEST_LEGACY_ORG_B, self.TEST_LEGACY_DEFAULT_APP),
        ]:
            _wipe(org, app)

    def tearDown(self):
        sm._legacy_qsettings_pairs_for = self._saved_pairs_fn
        for org, app in [
            (self.TEST_NEW_ORG, self.TEST_APP),
            (self.TEST_NEW_ORG, self.TEST_SHARED_APP),
            (self.TEST_LEGACY_ORG_A, self.TEST_APP),
            (self.TEST_LEGACY_ORG_A, self.TEST_SHARED_APP),
            (self.TEST_LEGACY_ORG_B, self.TEST_LEGACY_DEFAULT_APP),
        ]:
            _wipe(org, app)
        super().tearDown()

    def test_legacy_widgets_keys_migrated(self):
        """Keys at the old ``uitk.widgets/<app>`` land at ``uitk/<app>``."""
        legacy = QtCore.QSettings(self.TEST_LEGACY_ORG_A, self.TEST_APP)
        legacy.setValue("color", "#abc")
        legacy.setValue("size/w", 100)
        legacy.sync()

        mgr = SettingsManager(org=self.TEST_NEW_ORG, app=self.TEST_APP)

        self.assertEqual(mgr.settings.value("color"), "#abc")
        self.assertEqual(int(mgr.settings.value("size/w")), 100)

    def test_legacy_source_drained_after_migration(self):
        """Successful migration empties the legacy location (move-semantics)."""
        legacy = QtCore.QSettings(self.TEST_LEGACY_ORG_A, self.TEST_APP)
        legacy.setValue("foo", "bar")
        legacy.sync()

        _ = SettingsManager(org=self.TEST_NEW_ORG, app=self.TEST_APP)

        legacy_after = QtCore.QSettings(self.TEST_LEGACY_ORG_A, self.TEST_APP)
        self.assertIsNone(legacy_after.value("foo"),
                          "legacy source preserved instead of drained")

    def test_live_data_wins_on_collision(self):
        """If the new location already has a key, the legacy value doesn't overwrite."""
        new = QtCore.QSettings(self.TEST_NEW_ORG, self.TEST_APP)
        new.setValue("color", "live")
        new.sync()

        legacy = QtCore.QSettings(self.TEST_LEGACY_ORG_A, self.TEST_APP)
        legacy.setValue("color", "stale")
        legacy.setValue("other", "from-legacy")
        legacy.sync()

        mgr = SettingsManager(org=self.TEST_NEW_ORG, app=self.TEST_APP)

        # Collision: live wins.
        self.assertEqual(mgr.settings.value("color"), "live")
        # Non-colliding key: migrated through.
        self.assertEqual(mgr.settings.value("other"), "from-legacy")

    def test_idempotent_within_process(self):
        """A second construction in the same process doesn't re-migrate."""
        legacy = QtCore.QSettings(self.TEST_LEGACY_ORG_A, self.TEST_APP)
        legacy.setValue("k", "v1")
        legacy.sync()

        _ = SettingsManager(org=self.TEST_NEW_ORG, app=self.TEST_APP)

        # Repopulate the legacy location with a different value.
        legacy.setValue("k", "v2")
        legacy.sync()

        # Second construction: the process-cache should make the migration
        # a no-op so the second legacy value does NOT get pulled in.
        mgr2 = SettingsManager(org=self.TEST_NEW_ORG, app=self.TEST_APP)
        self.assertEqual(mgr2.settings.value("k"), "v1",
                         "second construction re-ran migration despite cache")

    def test_idempotent_across_processes_via_marker(self):
        """The on-disk marker prevents re-migration after the process-cache resets."""
        legacy = QtCore.QSettings(self.TEST_LEGACY_ORG_A, self.TEST_APP)
        legacy.setValue("k", "first-value")
        legacy.sync()

        _ = SettingsManager(org=self.TEST_NEW_ORG, app=self.TEST_APP)

        # Simulate a "new process": clear the in-memory cache and put a
        # stale value back at the legacy location.
        sm._MIGRATED_REGISTRY_PAIRS.clear()
        legacy.setValue("k", "second-value")
        legacy.sync()

        mgr2 = SettingsManager(org=self.TEST_NEW_ORG, app=self.TEST_APP)
        self.assertEqual(mgr2.settings.value("k"), "first-value",
                         "on-disk marker did not prevent re-migration")

    def test_shared_app_drains_both_legacy_orgs(self):
        """The default-app bucket pulls from both ``uitk.widgets`` and ``uitk.widgets.mixins``."""
        a = QtCore.QSettings(self.TEST_LEGACY_ORG_A, self.TEST_SHARED_APP)
        a.setValue("from_widgets", 1)
        a.sync()
        b = QtCore.QSettings(self.TEST_LEGACY_ORG_B, self.TEST_LEGACY_DEFAULT_APP)
        b.setValue("from_mixins", 2)
        b.sync()

        mgr = SettingsManager(org=self.TEST_NEW_ORG, app=self.TEST_SHARED_APP)

        self.assertEqual(int(mgr.settings.value("from_widgets")), 1)
        self.assertEqual(int(mgr.settings.value("from_mixins")), 2)

    def test_non_default_org_skips_migration(self):
        """Explicit non-default org means the caller takes responsibility — no auto-drain."""
        # Plant data at a "would-be legacy" location.
        legacy = QtCore.QSettings(self.TEST_LEGACY_ORG_A, self.TEST_APP)
        legacy.setValue("k", "stale")
        legacy.sync()

        # Construct with an org that is NOT the default — migration should skip.
        mgr = SettingsManager(org="some_other_org", app=self.TEST_APP)
        self.assertIsNone(mgr.settings.value("k"),
                          "migration ran for a non-default org")
        # Cleanup
        _wipe("some_other_org", self.TEST_APP)

    def test_internal_migration_marker_hidden_from_keys(self):
        """The migration marker doesn't appear in ``SettingsManager.keys()``.

        Hides bookkeeping from any caller iterating its own settings.
        Also defends against a user passing ``namespace="Meta"`` (or any
        future namespace that might collide with the marker's path
        prefix) and seeing a phantom entry.
        """
        # Plant a single legacy key so migration runs and writes the marker.
        legacy = QtCore.QSettings(self.TEST_LEGACY_ORG_A, self.TEST_APP)
        legacy.setValue("user_key", "real-data")
        legacy.sync()

        mgr = SettingsManager(org=self.TEST_NEW_ORG, app=self.TEST_APP)

        keys = mgr.keys()
        # User-authored data is visible.
        self.assertIn("user_key", keys)
        # Marker is NOT visible — even though raw allKeys() includes it.
        self.assertNotIn(sm._REGISTRY_MIGRATED_KEY, keys,
                         "migration marker leaked into keys() output")
        # Raw QSettings.allKeys still includes the marker (it's stored;
        # we just filter it at the SettingsManager layer).
        self.assertIn(sm._REGISTRY_MIGRATED_KEY, mgr.settings.allKeys())


if __name__ == "__main__":
    unittest.main()
