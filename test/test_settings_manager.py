# !/usr/bin/python
# coding=utf-8
"""Tests for SettingsManager defaults and legacy registry migration.

Storage is sandboxed to a throwaway temp dir by the suite-wide conftest
fixture (``_sandbox_qsettings``), so these tests cannot disturb the
developer's real settings even when they construct ``SettingsManager()`` at
the production ``(uitk, shared)`` location. As defense in depth the
migration tests also pin ``_legacy_qsettings_pairs_for`` to test-prefixed
orgs (``test_uitk_*``) and clean up their own keys in tearDown.
"""

import unittest
from typing import List, Tuple

from qtpy import QtCore

from conftest import BaseTestCase, setup_qt_application

app = setup_qt_application()

import uitk.managers.settings_manager as sm  # noqa: E402
from uitk.managers.settings_manager import (  # noqa: E402
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
    """``SettingsManager`` with no args lands at the consolidated location.

    These assertions only inspect ``organizationName()`` /
    ``applicationName()`` / ``namespace`` — they never read or write a
    setting — so they need no clean store and MUST NOT clear the real
    ``(uitk, shared)`` location, which holds the developer's live
    marking-menu bindings, widget state, and theme. (A prior version wiped
    it in setUp *and* tearDown, silently resetting real settings to defaults
    on every suite run.) Construction is additionally kept from draining any
    legacy data by pinning ``_legacy_qsettings_pairs_for`` to no-op.
    """

    _saved_pairs_fn = None

    def setUp(self):
        super().setUp()
        # Never let construction migrate/drain real legacy registry data.
        self._saved_pairs_fn = sm._legacy_qsettings_pairs_for
        sm._legacy_qsettings_pairs_for = lambda new_org, new_app: []
        # Reset the process-cache so each test exercises the migration check.
        sm._MIGRATED_REGISTRY_PAIRS.clear()

    def tearDown(self):
        sm._legacy_qsettings_pairs_for = self._saved_pairs_fn
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


class TestSettingsManagerRemove(BaseTestCase):
    """``SettingsManager.remove()`` — namespace-aware single-key removal.

    ``StateManager`` calls ``store.remove(key)`` on its backing store.
    ``QSettings`` has it; ``SettingsManager`` historically didn't — and
    because ``__getattr__`` manufactures a ``SettingItem`` proxy for any
    unknown name, ``StateManager.clear()`` / ``clear_custom()`` failed with
    a cryptic ``TypeError`` in MainWindow mode (where the store IS a
    ``SettingsManager``) instead of removing the key.
    """

    ORG = "test_uitk_remove"
    APP = "test_app"

    def setUp(self):
        super().setUp()
        _wipe(self.ORG, self.APP)

    def tearDown(self):
        _wipe(self.ORG, self.APP)
        super().tearDown()

    def test_remove_deletes_key(self):
        mgr = SettingsManager(org=self.ORG, app=self.APP)
        mgr.setValue("k", 1)
        mgr.remove("k")
        self.assertIsNone(mgr.value("k"))
        self.assertNotIn("k", mgr.keys())

    def test_remove_is_namespace_aware(self):
        root = SettingsManager(org=self.ORG, app=self.APP)
        ns = root.branch("ns")
        ns.setValue("k", 1)
        root.setValue("k", 2)  # same leaf name outside the namespace
        ns.remove("k")
        self.assertIsNone(ns.value("k"))
        self.assertEqual(root.value("k"), 2)

    def test_remove_missing_key_is_noop(self):
        mgr = SettingsManager(org=self.ORG, app=self.APP)
        mgr.remove("never_set")  # must not raise


class TestStringValueRoundTrip(BaseTestCase):
    """Strings that *parse* as JSON must still round-trip as strings.

    ``value()`` JSON-decodes every string — that is what restores bools /
    ints / floats from QSettings backends that stringify them (registry,
    ini) — so a stored *string* ``"1.10"`` came back as the float ``1.1``,
    ``"123"`` as an int, and ``"true"`` as a bool: a line edit holding a
    version string was silently rewritten between sessions. ``setValue``
    must quote exactly the ambiguous strings so the decode restores them
    verbatim, while plain strings stay unquoted (human-readable) on disk.
    """

    ORG = "test_uitk_roundtrip"
    APP = "test_app"

    def setUp(self):
        super().setUp()
        _wipe(self.ORG, self.APP)

    def tearDown(self):
        _wipe(self.ORG, self.APP)
        super().tearDown()

    def _mgr(self):
        return SettingsManager(org=self.ORG, app=self.APP)

    def test_ambiguous_strings_round_trip_as_strings(self):
        mgr = self._mgr()
        for s in ("1.10", "123", "true", "false", "null", "None", "1e5"):
            mgr.setValue("k", s)
            self.assertEqual(
                mgr.value("k"), s,
                f"string {s!r} did not round-trip verbatim",
            )

    def test_plain_strings_stored_unquoted(self):
        # The on-disk form of a non-ambiguous string stays the raw string —
        # human-readable in the registry / ini, and unchanged for any legacy
        # reader of the same key.
        mgr = self._mgr()
        mgr.setValue("p", "C:/proj/sourceimages")
        self.assertEqual(mgr.settings.value("p"), "C:/proj/sourceimages")
        self.assertEqual(mgr.value("p"), "C:/proj/sourceimages")

    def test_native_types_round_trip(self):
        mgr = self._mgr()
        cases = {
            "b": True,
            "i": 42,
            "f": 2.5,
            "l": [1, "two", 3.0],
            "d": {"a": 1, "b": [2, 3]},
        }
        for key, val in cases.items():
            mgr.setValue(key, val)
            self.assertEqual(mgr.value(key), val)

    def test_tuple_round_trips_as_list(self):
        # Tuples were previously passed raw to QSettings (platform-dependent
        # QVariant round-trip); they now share the JSON path (list parity).
        mgr = self._mgr()
        mgr.setValue("t", (1, 2, 3))
        self.assertEqual(mgr.value("t"), [1, 2, 3])

    def test_default_returned_verbatim_when_key_missing(self):
        # The decode belongs to STORED values only. value() used to run the
        # caller's default through json.loads too, so value("k", "1.10")
        # returned 1.1 with nothing stored at all.
        mgr = self._mgr()
        self.assertEqual(mgr.value("missing", "1.10"), "1.10")
        self.assertEqual(mgr.value("missing", "None"), "None")
        self.assertEqual(mgr.value("missing", [1, 2]), [1, 2])

    def test_legacy_raw_scalar_strings_still_decode(self):
        # Data written by older code (or by QSettings' own bool/number
        # stringification) is stored unquoted; it must keep decoding to the
        # native type.
        mgr = self._mgr()
        mgr.settings.setValue("flag", "true")  # planted raw, bypassing setValue
        self.assertIs(mgr.value("flag"), True)
        mgr.settings.setValue("count", "5")
        self.assertEqual(mgr.value("count"), 5)

    def test_direct_attribute_assignment_is_rejected(self):
        # The class docstring previously advertised ``settings.key = value`` as
        # a working "legacy attribute style", but __setattr__ deliberately
        # rejects it. The supported write API is ``settings.key.set(value)``.
        mgr = self._mgr()
        with self.assertRaises(AttributeError):
            mgr.my_key = "boom"
        mgr.my_key.set("ok")
        self.assertEqual(mgr.my_key.get(), "ok")
        self.assertEqual(mgr.value("my_key"), "ok")


if __name__ == "__main__":
    unittest.main()
