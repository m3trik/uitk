# !/usr/bin/python
# coding=utf-8
"""Unit tests for the widget-free RecentValuesStore model.

RecentValuesStore is the shared source-of-truth for "recent values" history.
It owns the list, persistence, dedup/normalize, validity filtering, display
formatting and a change-observer hook — so an option-box popup, an
ExpandableList sublist, or any other presenter can render the same data.

These tests are Qt-light: the store only touches ``QSettings`` (QtCore) for
persistence, never widgets, so no QApplication is required.

Run standalone: python test/test_recent_values_store.py
"""
import os
import tempfile
import unittest

import conftest  # noqa: F401 — inserts the package root on sys.path

from qtpy import QtCore
from uitk.widgets.mixins.settings_manager import SettingsManager
from uitk.widgets.mixins.recent_values_store import (
    RecentValuesStore,
    RecentValueEntry,
    normalize_value,
    _is_filesystem_path,
    _build_display_map_smart_path,
)


def _ini_settings():
    """Return an isolated SettingsManager backed by a temp INI file.

    Keeps persistence tests off the real registry/config root.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".ini", delete=False)
    tmp.close()
    qs = QtCore.QSettings(tmp.name, QtCore.QSettings.IniFormat)
    return SettingsManager(qsettings=qs, namespace="test_recent"), tmp.name


class TestModelBasics(unittest.TestCase):
    def test_record_front_inserts_and_dedups(self):
        s = RecentValuesStore()
        s.record("a")
        s.record("b")
        s.record("a")  # moves to front, no duplicate
        self.assertEqual(s.values, ["a", "b"])

    def test_record_trims_to_max_recent(self):
        s = RecentValuesStore(max_recent=2)
        s.record("a")
        s.record("b")
        s.record("c")
        self.assertEqual(s.values, ["c", "b"])

    def test_record_ignores_empty(self):
        s = RecentValuesStore()
        s.record("")
        s.record("   ")
        s.record(None)
        self.assertEqual(s.values, [])

    def test_add_seeds_without_reordering(self):
        s = RecentValuesStore()
        s.add("a")
        s.add("b")
        s.add("a")  # already present — no-op
        self.assertEqual(s.values, ["a", "b"])

    def test_remove(self):
        s = RecentValuesStore()
        s.record("a")
        s.record("b")
        s.remove("a")
        self.assertEqual(s.values, ["b"])

    def test_clear(self):
        s = RecentValuesStore()
        s.record("a")
        s.clear()
        self.assertEqual(s.values, [])

    def test_add_into_full_store_drops_oldest_not_newest(self):
        # The list is most-recent-first. Seeding an entry into a full store
        # must drop the OLDEST (tail), never the user's most recent entries
        # (head). Prior code sliced [-max:], discarding the most recent.
        s = RecentValuesStore(max_recent=3)
        s.record("a")
        s.record("b")
        s.record("c")  # -> ["c", "b", "a"] (c most recent)
        self.assertEqual(s.values, ["c", "b", "a"])

        s.add("seed")  # store already full; seed is a lower-priority append
        # The most recent user entries survive; the seeded (oldest) value is
        # dropped rather than "c".
        self.assertEqual(s.values, ["c", "b", "a"])
        self.assertIn("c", s.values)

    def test_add_respects_max_recent_from_empty(self):
        s = RecentValuesStore(max_recent=2)
        s.add("a")
        s.add("b")
        s.add("c")  # over capacity: newest seed is trimmed (tail/oldest)
        self.assertEqual(s.values, ["a", "b"])


class TestNormalize(unittest.TestCase):
    def test_path_dedup_is_case_and_sep_insensitive(self):
        s = RecentValuesStore()
        s.record("C:/Dir/Proj")
        s.record("c:\\dir\\proj")  # same path, different sep/case
        self.assertEqual(len(s.values), 1)

    def test_normalize_value_strips_and_lowers_paths(self):
        self.assertEqual(normalize_value("  C:/Dir  "), normalize_value("c:\\dir"))
        # Non-path strings are only stripped, not lowercased.
        self.assertEqual(normalize_value("  Hello "), "Hello")


class TestValidator(unittest.TestCase):
    def test_valid_values_filters(self):
        s = RecentValuesStore(validator=lambda v: v != "bad")
        s.record("bad")
        s.record("good")
        self.assertEqual(s.values, ["good", "bad"])  # raw list keeps both
        self.assertEqual(s.valid_values(), ["good"])  # filtered view drops bad

    def test_prune_invalid_removes_and_returns(self):
        s = RecentValuesStore(validator=lambda v: v != "bad")
        s.record("bad")
        s.record("good")
        removed = s.prune_invalid()
        self.assertEqual(removed, ["bad"])
        self.assertEqual(s.values, ["good"])

    def test_no_validator_means_all_valid(self):
        s = RecentValuesStore()
        s.record("a")
        self.assertEqual(s.valid_values(), ["a"])
        self.assertEqual(s.prune_invalid(), [])


class TestDisplayMap(unittest.TestCase):
    def test_basename(self):
        s = RecentValuesStore(display_format="basename")
        dm = s.display_map(["C:/a/b/proj1", "C:/x/proj2"])
        self.assertEqual(dm["C:/a/b/proj1"], "proj1")
        self.assertEqual(dm["C:/x/proj2"], "proj2")

    def test_callable(self):
        s = RecentValuesStore(display_format=lambda v: f"<{v}>")
        dm = s.display_map(["a"])
        self.assertEqual(dm["a"], "<a>")

    def test_auto_strips_common_prefix(self):
        s = RecentValuesStore(display_format="auto")
        vals = ["C:/proj/scenes/a", "C:/proj/scenes/b"]
        dm = s.display_map(vals)
        # Common prefix removed, leaf retained.
        self.assertTrue(dm[vals[0]].endswith("a"))
        self.assertTrue(dm[vals[1]].endswith("b"))
        self.assertNotIn("C:/proj/scenes", dm[vals[0]])

    def test_truncate_fallback_returns_strings(self):
        s = RecentValuesStore(display_format="truncate")
        long = "x" * 400
        dm = s.display_map([long])
        self.assertIsInstance(dm[long], str)
        self.assertLess(len(dm[long]), len(long))

    def test_display_map_defaults_to_current_values(self):
        s = RecentValuesStore(display_format="basename")
        s.record("C:/a/proj1")
        dm = s.display_map()
        self.assertEqual(dm["C:/a/proj1"], "proj1")


class TestObserver(unittest.TestCase):
    def test_subscribe_fires_on_mutation(self):
        s = RecentValuesStore()
        calls = []
        s.subscribe(lambda: calls.append(1))
        s.record("a")
        s.record("b")
        s.remove("a")
        s.clear()  # "b" still present, so this is a real mutation
        self.assertEqual(len(calls), 4)

    def test_noop_mutation_does_not_notify(self):
        s = RecentValuesStore()
        calls = []
        s.subscribe(lambda: calls.append(1))
        s.remove("absent")  # nothing to remove
        s.clear()  # already empty
        self.assertEqual(calls, [])

    def test_subscriber_exception_does_not_break_notify(self):
        s = RecentValuesStore()
        s.subscribe(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        ok = []
        s.subscribe(lambda: ok.append(1))
        s.record("a")  # must not raise
        self.assertEqual(ok, [1])


class TestPersistence(unittest.TestCase):
    def test_values_survive_a_new_store_on_same_settings(self):
        sm, path = _ini_settings()
        try:
            s1 = RecentValuesStore(settings=sm)
            s1.record("a")
            s1.record("b")
            # New store on the same backing settings reloads the history.
            s2 = RecentValuesStore(settings=sm)
            self.assertEqual(s2.values, ["b", "a"])
        finally:
            os.unlink(path)

    def test_no_settings_means_in_memory_only(self):
        s = RecentValuesStore()
        s.record("a")
        # No persistence configured — nothing to assert beyond no crash.
        self.assertEqual(s.values, ["a"])


class TestRecentValueEntry(unittest.TestCase):
    """Entries carry a separate display string while deduping by their data."""

    def test_entry_dedups_against_plain_value_by_data(self):
        s = RecentValuesStore()
        s.record("C:/a/Rock_Normal.png")
        s.record(RecentValueEntry("C:/a/Rock_Normal.png", display="Rock"))
        # Same data (case/sep-insensitive) → one entry, the latest wins.
        self.assertEqual(len(s.values), 1)
        self.assertIsInstance(s.values[0], RecentValueEntry)

    def test_record_ignores_entry_with_empty_data(self):
        s = RecentValuesStore()
        s.record(RecentValueEntry("   ", display="x"))
        s.record(RecentValueEntry(None, display="y"))
        self.assertEqual(s.values, [])

    def test_display_map_prefers_entry_display(self):
        s = RecentValuesStore(display_format="basename")
        entry = RecentValueEntry("C:/a/b/Rock_Normal.png", display="Rock set")
        plain = "C:/x/proj1"
        dm = s.display_map([entry, plain])
        self.assertEqual(dm[entry], "Rock set")  # explicit display wins
        self.assertEqual(dm[plain], "proj1")  # plain still formatted

    def test_entry_survives_persistence_round_trip(self):
        sm, path = _ini_settings()
        try:
            s1 = RecentValuesStore(settings=sm)
            s1.record(RecentValueEntry("C:/a/Rock_Normal.png", display="Rock"))
            s2 = RecentValuesStore(settings=sm)
            self.assertEqual(len(s2.values), 1)
            restored = s2.values[0]
            self.assertIsInstance(restored, RecentValueEntry)
            self.assertEqual(restored.display, "Rock")
            self.assertEqual(restored.data, "C:/a/Rock_Normal.png")
        finally:
            os.unlink(path)


class TestHelpersStillImportable(unittest.TestCase):
    """recent_values.py re-exports these; pin the canonical home."""

    def test_is_filesystem_path(self):
        self.assertTrue(_is_filesystem_path("C:/x"))
        self.assertTrue(_is_filesystem_path("/home/x"))
        self.assertFalse(_is_filesystem_path("plain"))

    def test_build_display_map_smart_path_needs_two_paths(self):
        self.assertIsNone(_build_display_map_smart_path(["only-one"]))


if __name__ == "__main__":
    unittest.main()
