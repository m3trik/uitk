# !/usr/bin/python
# coding=utf-8
"""Tests for PresetManager root resolution and legacy migration.

Covers the regression scenarios that motivated the consolidation:

* root resolution (default vs ``M3TRIK_PRESETS_ROOT`` env override),
* relative-vs-absolute path handling in ``_resolve_preset_dir``,
* legacy migration copying the **entire** legacy package on first
  access — important for bridges whose presets live in per-template
  subdirs — not just the leaf the user happened to request,
* migration idempotency via the per-key sentinel,
* respect for pre-existing files at the new location.
"""

import os
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from conftest import BaseTestCase, setup_qt_application

# QApplication needed because preset_manager imports from qtpy at module load.
app = setup_qt_application()

import uitk.widgets.mixins.preset_manager as pm  # noqa: E402
from uitk.widgets.mixins.preset_manager import (  # noqa: E402
    PresetManager,
    PRESETS_ROOT_ENV_VAR,
    get_presets_root,
)


class TestPresetsRootResolution(BaseTestCase):
    """``get_presets_root`` and ``_resolve_preset_dir`` semantics."""

    def setUp(self):
        super().setUp()
        self._tmp = Path(tempfile.mkdtemp(prefix="presets_root_"))
        self._prior_env = os.environ.pop(PRESETS_ROOT_ENV_VAR, None)
        # Reset the process-global guard so unrelated tests can't disable
        # legacy-cleanup behavior by running first.
        pm._LEGACY_QT_ROOTS_CLEARED = False

    def tearDown(self):
        if self._prior_env is None:
            os.environ.pop(PRESETS_ROOT_ENV_VAR, None)
        else:
            os.environ[PRESETS_ROOT_ENV_VAR] = self._prior_env
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def test_env_var_override_redirects_root(self):
        os.environ[PRESETS_ROOT_ENV_VAR] = str(self._tmp / "custom")
        self.assertEqual(get_presets_root(), self._tmp / "custom")

    def test_root_is_always_absolute(self):
        # Relative override values must still produce an absolute path so
        # callers can rely on ``relative_to`` and ``mkdir`` semantics.
        os.environ[PRESETS_ROOT_ENV_VAR] = "relative/subdir"
        root = get_presets_root()
        self.assertTrue(root.is_absolute(), f"root is relative: {root}")

    def test_relative_preset_dir_resolves_under_root(self):
        os.environ[PRESETS_ROOT_ENV_VAR] = str(self._tmp / "root")
        mgr = PresetManager(preset_dir="mayatk/color_manager")
        resolved = mgr._resolve_preset_dir("mayatk/color_manager")
        self.assertEqual(resolved, self._tmp / "root" / "mayatk" / "color_manager")

    def test_absolute_preset_dir_passed_through(self):
        os.environ[PRESETS_ROOT_ENV_VAR] = str(self._tmp / "root")
        abs_path = (self._tmp / "elsewhere").resolve()
        mgr = PresetManager(preset_dir=str(abs_path))
        self.assertEqual(mgr._resolve_preset_dir(str(abs_path)), abs_path)


class TestLegacyMigration(BaseTestCase):
    """End-to-end migration scenarios using an injected test key."""

    TEST_KEY = "uitk_test_pkg/sample_dir"
    SAVED_LEGACY_PATHS = None
    _saved_root_candidates = None

    def setUp(self):
        super().setUp()
        self._tmp = Path(tempfile.mkdtemp(prefix="presets_migrate_"))
        self._new_root = self._tmp / "new"
        self._legacy_root = self._tmp / "legacy"
        # Fake AppConfigLocation + GenericConfigLocation under the tmp
        # dir so the legacy-root cleanup can drain them without ever
        # touching the developer's real config dirs.
        self._fake_appconfig = self._tmp / "fake_appconfig"
        self._fake_generic = self._tmp / "fake_generic"
        self._fake_appconfig.mkdir(parents=True, exist_ok=True)
        self._fake_generic.mkdir(parents=True, exist_ok=True)

        # Redirect the consolidated root.
        self._prior_env = os.environ.pop(PRESETS_ROOT_ENV_VAR, None)
        os.environ[PRESETS_ROOT_ENV_VAR] = str(self._new_root)

        # Inject a test entry into the legacy table.
        self.SAVED_LEGACY_PATHS = dict(pm._LEGACY_PRESET_PATHS)
        pm._LEGACY_PRESET_PATHS[self.TEST_KEY] = str(self._legacy_root)

        # Redirect the legacy Qt-root candidates to point at the fake
        # config dirs. Essential — without this, the cleanup would see
        # (and potentially modify) the developer's real config dirs.
        self._saved_root_candidates = pm._legacy_qt_root_candidates
        pm._legacy_qt_root_candidates = lambda: [
            self._fake_appconfig / "m3trik" / "presets",
            self._fake_appconfig,
            self._fake_generic,
        ]

        # Reset the process-global cleanup guard so each test exercises
        # the cleanup branch when applicable.
        pm._LEGACY_QT_ROOTS_CLEARED = False

    def tearDown(self):
        # Restore the legacy table and env var.
        pm._LEGACY_PRESET_PATHS.clear()
        pm._LEGACY_PRESET_PATHS.update(self.SAVED_LEGACY_PATHS)
        if self._saved_root_candidates is not None:
            pm._legacy_qt_root_candidates = self._saved_root_candidates
        if self._prior_env is None:
            os.environ.pop(PRESETS_ROOT_ENV_VAR, None)
        else:
            os.environ[PRESETS_ROOT_ENV_VAR] = self._prior_env
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def _write_legacy(self, relpath: str, payload: dict) -> Path:
        """Plant a fake legacy preset file and return its path."""
        full = self._legacy_root / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(json.dumps(payload), encoding="utf-8")
        return full

    def test_flat_package_migration_moves_files(self):
        """Legacy data appears at the new location after migration."""
        self._write_legacy("red.json", {"_meta": {"version": 1}, "r": 255})

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        resolved = mgr.preset_dir

        self.assertTrue((resolved / "red.json").exists())
        with open(resolved / "red.json", "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["r"], 255)

    def test_per_package_migration_removes_legacy_source(self):
        """Successful migration removes the legacy source — not copy+leave.

        Locks in that ``_maybe_migrate_legacy`` uses move-semantics so
        users don't end up with two copies of every preset (one live,
        one stale in the old tilde path) after migration.
        """
        self._write_legacy("blue.json", {"b": 1})
        self._write_legacy("green.json", {"g": 1})

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        resolved = mgr.preset_dir

        # New location has both files.
        self.assertTrue((resolved / "blue.json").exists())
        self.assertTrue((resolved / "green.json").exists())
        # Legacy source is fully drained — no files left and the dir
        # itself rmdir'd.
        self.assertFalse((self._legacy_root / "blue.json").exists(),
                         "legacy source preserved instead of moved")
        self.assertFalse((self._legacy_root / "green.json").exists())
        self.assertFalse(self._legacy_root.exists(),
                         "empty legacy root not cleaned up")

    def test_whole_package_migrated_when_leaf_requested(self):
        """The bug fix: requesting one bridge template must bring siblings along."""
        self._write_legacy("default/foo.json", {"k": "default-foo"})
        self._write_legacy("hardsurface/bar.json", {"k": "hardsurface-bar"})

        # Request only the `default` template.
        leaf_path = f"{self.TEST_KEY}/default"
        mgr = PresetManager(preset_dir=leaf_path)
        _ = mgr.preset_dir  # trigger migration

        # Both templates should now be present under the new root.
        new_pkg = self._new_root.joinpath(*self.TEST_KEY.split("/"))
        self.assertTrue((new_pkg / "default" / "foo.json").exists())
        self.assertTrue((new_pkg / "hardsurface" / "bar.json").exists())

    def test_migration_is_idempotent(self):
        self._write_legacy("alpha.json", {"v": 1})

        mgr1 = PresetManager(preset_dir=self.TEST_KEY)
        first_dir = mgr1.preset_dir

        # Manually edit the migrated file to detect any re-copy.
        (first_dir / "alpha.json").write_text(json.dumps({"v": 2}), encoding="utf-8")

        mgr2 = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr2.preset_dir

        with open(first_dir / "alpha.json", "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["v"], 2, "migration re-copied over user edits")

    def test_existing_files_not_overwritten(self):
        self._write_legacy("a.json", {"src": "legacy"})

        # Pre-create new dir with a clashing name + content.
        new_pkg = self._new_root.joinpath(*self.TEST_KEY.split("/"))
        new_pkg.mkdir(parents=True, exist_ok=True)
        (new_pkg / "a.json").write_text(json.dumps({"src": "user"}), encoding="utf-8")

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        with open(new_pkg / "a.json", "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["src"], "user",
                             "migration overwrote a user-authored file")

    def test_no_legacy_still_marks_migrated(self):
        # Legacy root does not exist. Migration should be a no-op but still
        # write the sentinel so subsequent accesses don't keep retrying.
        self.assertFalse(self._legacy_root.exists())

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        sentinel = pm._migration_sentinel_path(self.TEST_KEY)
        self.assertTrue(sentinel.exists(),
                        "sentinel not written when legacy was absent")

    def test_m3trik_wrapper_data_hoisted_up(self):
        """Data stranded in the interim ``<appconfig>/m3trik/presets/`` wrapper is rescued."""
        stranded_pkg = (
            self._fake_appconfig / "m3trik" / "presets" / "mayatk" / "color_manager"
        )
        stranded_pkg.mkdir(parents=True)
        (stranded_pkg / "red.json").write_text(json.dumps({"r": 255}), encoding="utf-8")

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        hoisted = self._new_root / "mayatk" / "color_manager" / "red.json"
        self.assertTrue(hoisted.exists(),
                        f"m3trik-wrapped data not hoisted to {hoisted}")
        # The empty m3trik shell should be removed.
        self.assertFalse((self._fake_appconfig / "m3trik").exists(),
                         "empty m3trik subtree was not cleaned up")

    def test_appconfig_wrapper_data_hoisted_up(self):
        """Data at ``<appconfig>/<pkg>/`` (the Qt python/ wrapper layout) is rescued.

        This is the layout users are on right now: their presets live at
        ``<LOCALAPPDATA>/python/mayatk/...`` because Qt's AppConfigLocation
        adds an exe-name segment. After switching to GenericConfigLocation
        we need to hoist them up one level.
        """
        stranded_pkg = self._fake_appconfig / "mayatk" / "substance_bridge"
        stranded_pkg.mkdir(parents=True)
        (stranded_pkg / "matte.json").write_text(json.dumps({"r": 0.7}),
                                                 encoding="utf-8")

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        hoisted = self._new_root / "mayatk" / "substance_bridge" / "matte.json"
        self.assertTrue(hoisted.exists(),
                        f"appconfig-wrapped data not hoisted to {hoisted}")
        # The fake appconfig itself is NOT removed — it may hold other apps' data.
        self.assertTrue(self._fake_appconfig.exists())
        # The hoisted package dir under fake appconfig should be empty / gone.
        self.assertFalse(stranded_pkg.exists(),
                         "source package dir not consumed by the move")

    def test_appconfig_wrapper_leaves_unrelated_dirs_alone(self):
        """Non-uitk subdirs under AppConfigLocation are not touched."""
        # Plant a non-uitk dir (e.g., a fake "pip" cache) — cleanup must not
        # touch it.
        unrelated = self._fake_appconfig / "pip" / "cache"
        unrelated.mkdir(parents=True)
        (unrelated / "wheel.bin").write_text("binary-blob", encoding="utf-8")

        # Plant uitk data alongside.
        uitk_pkg = self._fake_appconfig / "mayatk" / "color_manager"
        uitk_pkg.mkdir(parents=True)
        (uitk_pkg / "red.json").write_text(json.dumps({"r": 1}), encoding="utf-8")

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        # Unrelated content untouched.
        self.assertTrue((unrelated / "wheel.bin").exists(),
                        "cleanup disturbed unrelated AppConfigLocation content")
        # uitk content hoisted.
        self.assertTrue((self._new_root / "mayatk" / "color_manager" / "red.json").exists())

    def test_legacy_cleanup_does_not_overwrite_user_data(self):
        """Live data wins on collision; the stranded copy stays on disk."""
        stranded_dir = (
            self._fake_appconfig / "m3trik" / "presets" / "mayatk" / "color_manager"
        )
        stranded_dir.mkdir(parents=True)
        stranded_file = stranded_dir / "shared.json"
        stranded_file.write_text(json.dumps({"src": "stranded"}), encoding="utf-8")

        live_dir = self._new_root / "mayatk" / "color_manager"
        live_dir.mkdir(parents=True)
        (live_dir / "shared.json").write_text(json.dumps({"src": "live"}),
                                              encoding="utf-8")

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        with open(live_dir / "shared.json", "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["src"], "live",
                             "legacy cleanup overwrote a live file")
        # Collision leaves stranded data on disk for forensics; future
        # changes that delete it would silently destroy user-visible work.
        self.assertTrue(stranded_file.exists(),
                        "stranded data was deleted instead of preserved")

    def test_legacy_cleanup_recursive_merge(self):
        """Deep collisions don't orphan data — recursion merges at every level."""
        live_inner = self._new_root / "uitk" / "switchboard_browser" / "presets"
        live_inner.mkdir(parents=True)
        (live_inner / "keep.json").write_text(json.dumps({"src": "live"}),
                                              encoding="utf-8")

        # Stranded data four levels deep under the m3trik wrapper.
        stranded_inner = (
            self._fake_appconfig / "m3trik" / "presets"
            / "uitk" / "switchboard_browser" / "presets"
        )
        stranded_inner.mkdir(parents=True)
        (stranded_inner / "rescue.json").write_text(json.dumps({"src": "stranded"}),
                                                    encoding="utf-8")

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        self.assertTrue((live_inner / "keep.json").exists())
        self.assertTrue((live_inner / "rescue.json").exists(),
                        "recursive merge failed to rescue deeply-nested data")
        self.assertFalse((self._fake_appconfig / "m3trik").exists(),
                         "m3trik subtree not collapsed after recursive merge")

    def test_generic_era_data_hoisted_to_wrapper(self):
        """Data at ``<generic>/<pkg>/`` (bare generic-config era) is wrapped up."""
        # User had data sitting as siblings of unrelated apps at the
        # bare GenericConfigLocation level — needs to move into the new
        # ecosystem wrapper.
        stranded_pkg = self._fake_generic / "mayatk" / "color_manager"
        stranded_pkg.mkdir(parents=True)
        (stranded_pkg / "red.json").write_text(json.dumps({"r": 255}),
                                               encoding="utf-8")

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        hoisted = self._new_root / "mayatk" / "color_manager" / "red.json"
        self.assertTrue(hoisted.exists(),
                        f"generic-era data not hoisted to {hoisted}")
        # Source consumed by the move.
        self.assertFalse(stranded_pkg.exists())

    def test_pre_wrap_uitk_state_restructured_in_place(self):
        """Pre-wrap ``<new_root>/style_presets/`` becomes ``<new_root>/uitk/style_presets/``.

        Before the ecosystem-wrapper layout, ``<generic>/uitk/`` held
        uitk-package state directly. With the wrapper, ``<generic>/uitk/``
        IS the ecosystem root and uitk's own state nests inside as
        ``<generic>/uitk/uitk/``. This test verifies the in-place
        restructure happens when pre-wrap data is detected at the new
        root itself.
        """
        # Plant pre-wrap state at the new root — folders named like
        # uitk-package dirs (not known-package names).
        (self._new_root / "style_presets").mkdir(parents=True)
        (self._new_root / "style_presets" / "dark.json").write_text(
            json.dumps({"bg": "#000"}), encoding="utf-8"
        )
        (self._new_root / "hotkey_presets").mkdir()
        (self._new_root / "hotkey_presets" / "vim.json").write_text(
            json.dumps({"esc": "Esc"}), encoding="utf-8"
        )

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        # Both pre-wrap dirs should now live under the inner uitk/ wrapper.
        self.assertTrue(
            (self._new_root / "uitk" / "style_presets" / "dark.json").exists(),
            "pre-wrap style_presets not nested into uitk/uitk/")
        self.assertTrue(
            (self._new_root / "uitk" / "hotkey_presets" / "vim.json").exists(),
            "pre-wrap hotkey_presets not nested into uitk/uitk/")
        # Old locations are gone.
        self.assertFalse((self._new_root / "style_presets").exists())
        self.assertFalse((self._new_root / "hotkey_presets").exists())

    def test_husk_dirs_do_not_rebury_known_packages(self):
        """Regression: leftover husk dirs must not re-bury a placed package.

        Field repro — a freshly-saved ``mayatk/curtain`` preset vanished the
        next session. Cause: a prior wrap left behind *husk* dirs at the
        wrapper root (``style_presets/`` etc. holding only a ``.migrated``
        sentinel, no preset data). Those non-known-package names made the
        wrapper-detector return False every launch, so the wrap fired and
        relocated the *entire* correctly-placed ``mayatk/`` tree into
        ``<root>/uitk/mayatk/`` — where the live load path never looks. The
        preset wasn't deleted, just buried.

        Two invariants pin the fix: (1) data-less husks are not treated as
        pre-wrap evidence, and (2) a known-package sibling is never moved
        into the inner wrapper even if the wrap does run.
        """
        # Correct wrapper layout: inner uitk/ (uitk's own state) + a known-
        # package sibling holding a real user preset (the curtain save).
        (self._new_root / "uitk" / "style_presets").mkdir(parents=True)
        (self._new_root / "uitk" / "style_presets" / "dark.json").write_text(
            "{}", encoding="utf-8"
        )
        curtain = self._new_root / "mayatk" / "curtain"
        curtain.mkdir(parents=True)
        (curtain / "MyCurtain.json").write_text(
            json.dumps({"_meta": {"version": 1}, "s000": 29.0}), encoding="utf-8"
        )
        # Leftover husks at the root: interim sentinel only, no preset data.
        for husk in ("style_presets", "hotkey_presets", "switchboard_browser"):
            (self._new_root / husk).mkdir()
            (self._new_root / husk / ".migrated").write_text("", encoding="utf-8")

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir  # trigger migration

        # The user's preset must remain at its live location...
        self.assertTrue(
            (self._new_root / "mayatk" / "curtain" / "MyCurtain.json").exists(),
            "known-package preset reburied by a husk-triggered re-wrap",
        )
        # ...and must NOT have been relocated under the inner uitk/ wrapper.
        self.assertFalse(
            (self._new_root / "uitk" / "mayatk" / "curtain" / "MyCurtain.json").exists(),
            "mayatk tree buried under <root>/uitk/mayatk/",
        )

    def test_wrap_leaves_known_package_sibling_at_root(self):
        """When the wrap DOES fire, a known-package sibling stays put.

        Companion to ``test_husk_dirs_do_not_rebury_known_packages``: that one
        keeps the wrap from firing at all (husks ignored); this one forces a
        genuine fire — real pre-wrap uitk state (``style_presets/`` *with*
        data) coexisting with a freshly-placed ``mayatk/`` package — and pins
        the second half of the fix: only uitk's own pre-wrap dirs move into
        the inner wrapper; the known-package sibling is never relocated. Fails
        before the ``known_pkgs`` skip in ``_wrap_pre_wrap_uitk_state`` (mayatk
        gets dragged down into ``<root>/uitk/mayatk/``).
        """
        # Genuine pre-wrap uitk state carrying real presets -> wrap must fire.
        (self._new_root / "style_presets").mkdir(parents=True)
        (self._new_root / "style_presets" / "dark.json").write_text(
            json.dumps({"bg": "#000"}), encoding="utf-8"
        )
        # A placed known-package sibling with a user preset.
        curtain = self._new_root / "mayatk" / "curtain"
        curtain.mkdir(parents=True)
        (curtain / "keep.json").write_text(
            json.dumps({"_meta": {"version": 1}, "s000": 1.0}), encoding="utf-8"
        )

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir  # trigger migration

        # The wrap ran: uitk's own pre-wrap state nested under the inner uitk/.
        self.assertTrue(
            (self._new_root / "uitk" / "style_presets" / "dark.json").exists(),
            "pre-wrap uitk state was not nested (wrap didn't fire)",
        )
        self.assertFalse((self._new_root / "style_presets").exists())
        # ...but the known-package sibling stayed at the root, untouched.
        self.assertTrue(
            (self._new_root / "mayatk" / "curtain" / "keep.json").exists(),
            "known-package sibling dragged into the inner wrapper by the wrap",
        )
        self.assertFalse(
            (self._new_root / "uitk" / "mayatk").exists(),
            "mayatk relocated under <root>/uitk/ instead of staying at root",
        )

    def test_pre_wrap_skipped_when_already_wrapped(self):
        """If the new root already has the wrapper layout, no in-place re-wrap."""
        # New-style wrapper layout: known-package subdirs present.
        (self._new_root / "uitk" / "style_presets").mkdir(parents=True)
        (self._new_root / "uitk" / "style_presets" / "x.json").write_text(
            "{}", encoding="utf-8"
        )
        (self._new_root / "mayatk").mkdir()  # known-pkg marker

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        # The wrap must NOT have nested everything one more level deep.
        self.assertTrue((self._new_root / "uitk" / "style_presets" / "x.json").exists())
        self.assertFalse((self._new_root / "uitk" / "uitk").exists(),
                         "wrap ran on an already-wrapped layout")

    def test_pre_wrap_resumes_partial_wrap(self):
        """A prior wrap that was killed mid-move is resumed on the next access.

        Without this, the strict-detector behavior, the inner ``uitk/`` subdir
        would be the only known-pkg child and a lenient detector would
        treat the dir as already-wrapped, leaving the stray sibling
        orphaned forever.
        """
        # Simulate a partial wrap: inner uitk/ already created with one
        # subdir moved in, but another sibling (style_presets) was never
        # processed before the prior run died.
        (self._new_root / "uitk" / "hotkey_presets").mkdir(parents=True)
        (self._new_root / "uitk" / "hotkey_presets" / "moved.json").write_text(
            "{}", encoding="utf-8"
        )
        (self._new_root / "style_presets").mkdir()
        (self._new_root / "style_presets" / "stuck.json").write_text(
            "{}", encoding="utf-8"
        )

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        # Previously-moved file still in place; orphaned sibling resumed.
        self.assertTrue((self._new_root / "uitk" / "hotkey_presets" / "moved.json").exists())
        self.assertTrue(
            (self._new_root / "uitk" / "style_presets" / "stuck.json").exists(),
            "partial-wrap recovery did not pick up the orphaned sibling")
        self.assertFalse((self._new_root / "style_presets").exists(),
                         "orphaned sibling still at root after recovery")

    def test_pre_wrap_drops_interim_artifacts(self):
        """``.migrated`` / ``.migration/`` at root level don't get wrapped into uitk/."""
        # Plant a real pre-wrap dir + dead-state artifacts at the same level.
        (self._new_root / "style_presets").mkdir(parents=True)
        (self._new_root / "style_presets" / "x.json").write_text(
            "{}", encoding="utf-8"
        )
        (self._new_root / ".migrated").write_text("[]", encoding="utf-8")
        (self._new_root / ".migration").mkdir()
        (self._new_root / ".migration" / "ghost").touch()

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        self.assertTrue((self._new_root / "uitk" / "style_presets" / "x.json").exists())
        # Dead-state artifacts dropped, not preserved inside the wrapper.
        self.assertFalse((self._new_root / "uitk" / ".migrated").exists(),
                         ".migrated artifact carried into wrapper")
        self.assertFalse((self._new_root / "uitk" / ".migration").exists(),
                         ".migration artifact carried into wrapper")
        # And not at the root level either.
        self.assertFalse((self._new_root / ".migrated").exists())
        self.assertFalse((self._new_root / ".migration").exists())

    def test_pre_wrap_and_candidate_drain_combined(self):
        """Pass 1 (wrap) and Pass 2 (drain) cooperate in the same migration.

        Realistic scenario: user has BOTH pre-wrap uitk-pkg state at the
        new root AND legacy data at an old AppConfigLocation candidate.
        Both end up correctly placed in a single first-access cycle.
        """
        # Pre-wrap state at <new_root>/style_presets/ (handled by pass 1).
        (self._new_root / "style_presets").mkdir(parents=True)
        (self._new_root / "style_presets" / "wrap.json").write_text(
            json.dumps({"src": "prewrap"}), encoding="utf-8"
        )
        # Legacy data at <fake_appconfig>/mayatk/ (handled by pass 2).
        (self._fake_appconfig / "mayatk" / "color_manager").mkdir(parents=True)
        (self._fake_appconfig / "mayatk" / "color_manager" / "hoist.json").write_text(
            json.dumps({"src": "appconfig"}), encoding="utf-8"
        )

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        # Pass 1 result: uitk-pkg state nested.
        self.assertTrue(
            (self._new_root / "uitk" / "style_presets" / "wrap.json").exists(),
            "pass 1 (wrap) did not run in combined scenario")
        # Pass 2 result: mayatk hoisted into the wrapper sibling.
        self.assertTrue(
            (self._new_root / "mayatk" / "color_manager" / "hoist.json").exists(),
            "pass 2 (candidate drain) did not run in combined scenario")

    def test_legacy_cleanup_drops_interim_state_artifacts(self):
        """Interim ``.migrated`` / ``.migration`` files don't leak up."""
        wrapper = self._fake_appconfig / "m3trik" / "presets"
        wrapper.mkdir(parents=True)
        (wrapper / ".migrated").write_text("[]", encoding="utf-8")
        (wrapper / ".migration").mkdir()
        (wrapper / ".migration" / "uitk__style_presets").touch()
        (wrapper / "mayatk").mkdir()
        (wrapper / "mayatk" / "x.json").write_text("{}", encoding="utf-8")

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        _ = mgr.preset_dir

        self.assertTrue((self._new_root / "mayatk" / "x.json").exists())
        self.assertFalse((self._new_root / ".migrated").exists(),
                         "interim .migrated file leaked to root")
        self.assertFalse((self._new_root / ".migration").exists(),
                         "interim .migration dir leaked to root")


class TestBuiltinTier(BaseTestCase):
    """Built-in (shipped) presets layered under user presets via PresetStore.

    Uses standalone (``from_widgets``) mode with real Qt widgets so no
    MainWindow / StateManager is needed.
    """

    def setUp(self):
        super().setUp()
        from qtpy import QtWidgets

        self._tmp = Path(tempfile.mkdtemp(prefix="presets_builtin_"))
        self.builtin = self._tmp / "builtin"
        self.user = self._tmp / "user"
        self.builtin.mkdir()
        # A shipped built-in preset (objectName -> value, like save() writes).
        (self.builtin / "studio.json").write_text(
            json.dumps({"_meta": {"version": 1}, "chk_a": True, "spn_b": 5}),
            encoding="utf-8",
        )
        self.chk = QtWidgets.QCheckBox()
        self.chk.setObjectName("chk_a")
        self.spn = QtWidgets.QSpinBox()
        self.spn.setObjectName("spn_b")
        self.spn.setMaximum(100)
        self.mgr = PresetManager.from_widgets(
            preset_dir=str(self.user),
            widgets=[self.chk, self.spn],
            builtin_dir=str(self.builtin),
        )

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def test_builtin_listed_and_sourced(self):
        self.assertEqual(self.mgr.list(), ["studio"])
        self.assertEqual(self.mgr.source("studio"), "builtin")
        self.assertTrue(self.mgr.exists("studio"))

    def test_builtin_loads_into_widgets(self):
        self.assertEqual(self.mgr.load("studio"), 2)
        self.assertTrue(self.chk.isChecked())
        self.assertEqual(self.spn.value(), 5)

    def test_save_creates_user_preset_alongside_builtin(self):
        self.chk.setChecked(True)
        self.mgr.save("custom")
        self.assertEqual(self.mgr.list(), ["custom", "studio"])
        self.assertEqual(self.mgr.source("custom"), "user")
        self.assertEqual(self.mgr.source("studio"), "builtin")

    def test_user_preset_shadows_builtin_of_same_name(self):
        self.spn.setValue(42)
        self.mgr.save("studio")  # same name as the built-in
        self.assertEqual(self.mgr.source("studio"), "user")  # now user-sourced
        self.assertEqual(self.mgr.list().count("studio"), 1)  # still listed once
        self.spn.setValue(0)
        self.mgr.load("studio")
        self.assertEqual(self.spn.value(), 42)  # user copy won

    def test_builtin_is_read_only(self):
        # Can't delete or rename a name that exists only as a built-in.
        self.assertFalse(self.mgr.delete("studio"))
        self.assertFalse(self.mgr.rename("studio", "studio2"))
        self.assertTrue(self.mgr.exists("studio"))  # survives
        # Deleting the user shadow falls back to the built-in.
        self.mgr.save("studio")
        self.assertTrue(self.mgr.delete("studio"))
        self.assertEqual(self.mgr.source("studio"), "builtin")

    # ------------------------------------------------------------------
    # wire_combo: built-in handling in the GUI selector
    # ------------------------------------------------------------------
    def _wire_combo(self):
        """Wire a real WidgetComboBox to ``self.mgr`` and return it.

        Adds a user preset ("custom") alongside the shipped built-in
        ("studio") so both tiers are present in the combo.
        """
        from uitk.widgets.widgetComboBox import WidgetComboBox

        self.mgr.save("custom")  # a user preset to contrast with the built-in
        combo = WidgetComboBox()
        self.addCleanup(combo.deleteLater)
        self.mgr.wire_combo(combo)
        return combo

    @staticmethod
    def _action_state(combo, label):
        """Enabled state of the actions-section button named *label*.

        Matches on accessibleName since the preset combo uses icon-only buttons
        (no visible text).
        """
        last = combo._model.rowCount() - 1
        inner = combo._row_containers.get(last).property("_embedded_widget")
        lay = inner.layout()
        for i in range(lay.count()):
            btn = lay.itemAt(i).widget()
            if btn.accessibleName() == label:
                return btn.isEnabled()
        raise AssertionError(f"no action button {label!r}")

    def test_wire_combo_italicises_builtins(self):
        combo = self._wire_combo()
        items = {
            combo._model.item(i).text(): combo._model.item(i)
            for i in range(combo._model.rowCount() - combo._action_row_count)
        }
        # Built-in shown italic; user preset is not. Text stays the raw name in
        # both cases so load/rename/delete still resolve.
        self.assertTrue(items["studio"].font().italic(), "built-in not italicised")
        self.assertFalse(items["custom"].font().italic(), "user preset wrongly italicised")
        # Marking must be font-only — no item icons (they shifted the collapsed
        # display's text and pushed the dropdown arrow into the name).
        self.assertTrue(items["studio"].icon().isNull(), "built-in should carry no icon")
        self.assertTrue(items["custom"].icon().isNull(), "user preset should carry no icon")

    def test_wire_combo_disables_rename_delete_for_builtin(self):
        combo = self._wire_combo()

        combo.setCurrentIndex(combo.findText("studio"))  # built-in
        self.assertFalse(self._action_state(combo, "Rename"))
        self.assertFalse(self._action_state(combo, "Delete"))
        self.assertTrue(self._action_state(combo, "Save"))  # override allowed
        self.assertTrue(self._action_state(combo, "Open"))

        combo.setCurrentIndex(combo.findText("custom"))  # user
        self.assertTrue(self._action_state(combo, "Rename"))
        self.assertTrue(self._action_state(combo, "Delete"))

    @staticmethod
    def _action_buttons(combo):
        last = combo._model.rowCount() - 1
        inner = combo._row_containers.get(last).property("_embedded_widget")
        lay = inner.layout()
        return [lay.itemAt(i).widget() for i in range(lay.count())]

    def test_wire_combo_actions_are_icon_only_single_row_with_refresh(self):
        combo = self._wire_combo()
        btns = self._action_buttons(combo)
        names = [b.accessibleName() for b in btns]
        self.assertEqual(names, ["Rename", "Refresh", "Delete", "Open", "Save"])
        # icon-only -> no visible text; single row -> no separator row.
        self.assertTrue(all(b.text() == "" for b in btns), "buttons must be icon-only")
        self.assertEqual(combo._action_row_count, 1, "separator removed -> one action row")

    def test_wire_combo_refresh_reloads_current_preset(self):
        # Refresh re-applies the selected preset's stored values to the widgets.
        from uitk.widgets.widgetComboBox import WidgetComboBox

        self.chk.setChecked(True)
        self.spn.setValue(42)
        self.mgr.save("custom")  # captures chk=True, spn=42

        combo = WidgetComboBox()
        self.addCleanup(combo.deleteLater)
        self.mgr.wire_combo(combo)
        combo.setCurrentIndex(combo.findText("custom"))  # loads -> spn 42
        self.assertEqual(self.spn.value(), 42)

        self.spn.setValue(7)  # user edits away from the preset
        for b in self._action_buttons(combo):
            if b.accessibleName() == "Refresh":
                b.click()
                break
        self.assertEqual(self.spn.value(), 42, "Refresh must reload the selected preset")


class TestSemanticPresetMode(BaseTestCase):
    """``value_provider`` / ``value_applier`` mode: presets keyed by semantic
    name (not widget ``objectName``), shared with a headless CLI's PresetStore.

    No Qt widgets involved -- the callbacks own the (de)serialization, so the
    same JSON a CLI runner reads round-trips through the GUI manager.
    """

    def setUp(self):
        super().setUp()
        self._tmp = Path(tempfile.mkdtemp(prefix="presets_semantic_"))
        self.builtin = self._tmp / "builtin"
        self.user = self._tmp / "user"
        self.builtin.mkdir()
        # A shipped built-in run-template (semantic keys, like the CLI writes).
        (self.builtin / "specular.json").write_text(
            json.dumps({"_meta": {"version": 1},
                        "align_downscale": 2, "depth_filter": "moderate"}),
            encoding="utf-8",
        )
        # Stand-in for a panel's live param values + an applied-into sink.
        self.live = {"align_downscale": 1, "depth_filter": "mild",
                     "face_count": "high"}
        self.applied: dict = {}

        def applier(data):
            self.applied = dict(data)
            return len(data)

        self.mgr = PresetManager(
            preset_dir=str(self.user),
            builtin_dir=str(self.builtin),
            value_provider=lambda: dict(self.live),
            value_applier=applier,
        )

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def test_builtin_loads_via_applier_without_meta(self):
        n = self.mgr.load("specular")
        self.assertEqual(n, 2)
        # The applier sees the semantic payload, with `_meta` already stripped.
        self.assertEqual(self.applied, {"align_downscale": 2,
                                        "depth_filter": "moderate"})
        self.assertNotIn("_meta", self.applied)

    def test_save_writes_provider_payload_to_user_tier(self):
        path = self.mgr.save("custom")
        self.assertEqual(self.mgr.source("custom"), "user")
        on_disk = json.loads(Path(path).read_text(encoding="utf-8"))
        # Provider keys persisted; `_meta` added by the manager.
        self.assertEqual(on_disk["align_downscale"], 1)
        self.assertEqual(on_disk["depth_filter"], "mild")
        self.assertEqual(on_disk["face_count"], "high")
        self.assertIn("_meta", on_disk)

    def test_round_trip_save_then_load(self):
        self.mgr.save("custom")
        # Change live values; loading the saved preset must drive the applier
        # back to the captured snapshot.
        self.live.update(align_downscale=8, depth_filter="aggressive")
        self.mgr.load("custom")
        self.assertEqual(self.applied["align_downscale"], 1)
        self.assertEqual(self.applied["depth_filter"], "mild")
        self.assertEqual(self.applied["face_count"], "high")

    def test_user_preset_shadows_builtin_semantic(self):
        self.live = {"align_downscale": 4}
        self.mgr.save("specular")  # same name as the built-in
        self.assertEqual(self.mgr.source("specular"), "user")
        self.mgr.load("specular")
        self.assertEqual(self.applied, {"align_downscale": 4})  # user copy won

    def test_combo_lists_both_tiers(self):
        # wire_combo / list() are tier-aware and unchanged by semantic mode.
        self.live = {"align_downscale": 4}
        self.mgr.save("custom")
        self.assertEqual(self.mgr.list(), ["custom", "specular"])


if __name__ == "__main__":
    unittest.main()
