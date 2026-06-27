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
        """Wire a real ``ComboBox`` to ``self.mgr`` and return it.

        Adds a user preset ("custom") alongside the shipped built-in
        ("studio") so both tiers are present in the combo.
        """
        from uitk.widgets.comboBox import ComboBox

        self.mgr.save("custom")  # a user preset to contrast with the built-in
        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        self.mgr.wire_combo(combo)
        return combo

    @staticmethod
    def _menu_labels(combo):
        """Labels the ⋯-menu provider yields for the current selection.

        Built-ins yield only ``Open Folder`` (they can't be renamed/deleted);
        user presets yield ``Rename / Open Folder / Delete``.
        """
        from uitk.widgets.optionBox.options.option_menu import ContextMenuOption

        opt = combo.option_box.find_option(ContextMenuOption)
        return [label for label, _ in opt._menu_provider(combo)]

    @staticmethod
    def _menu_callback(combo, label):
        """The ⋯-menu callback bound to *label* for the current selection."""
        from uitk.widgets.optionBox.options.option_menu import ContextMenuOption

        opt = combo.option_box.find_option(ContextMenuOption)
        for lbl, cb in opt._menu_provider(combo):
            if lbl == label:
                return cb
        raise AssertionError(f"no menu item {label!r}")

    def test_wire_combo_does_not_build_menu_eagerly(self):
        # Init-perf regression: wiring a preset combo must not build the ⋯
        # menu's dropdown Menu (applying its QSS/chrome) at wrap time -- it is
        # only needed when the user opens it. Building it eagerly was a
        # measurable chunk of the redesign's added init cost under a heavy DCC
        # stylesheet.
        from uitk.widgets.optionBox.options.option_menu import ContextMenuOption

        combo = self._wire_combo()
        opt = combo.option_box.find_option(ContextMenuOption)
        self.assertIsNone(opt._menu, "the ⋯ menu was built eagerly during wire_combo")

    def test_wire_combo_menu_rows_are_clickable_and_fire(self):
        # Real-dispatch regression (not the provider-closure proxy the other
        # menu tests use): the rendered ⋯-menu rows must be clickable buttons
        # that actually run their action. Before the fix they were inert
        # QLabels (no hover, no clicked signal, callback stored as dead data),
        # so clicking Delete did nothing in the live UI.
        from uitk.widgets.optionBox.options.option_menu import ContextMenuOption

        combo = self._wire_combo()
        combo.setCurrentIndex(combo.findText("custom"))  # a deletable user preset

        opt = combo.option_box.find_option(ContextMenuOption)
        opt._show_menu()  # populate + show the real menu
        rows = opt.menu.get_items()

        self.assertTrue(rows, "menu rendered no rows")
        self.assertTrue(
            all(hasattr(r, "clicked") for r in rows),
            "⋯-menu rows are inert (not clickable buttons)",
        )
        self.assertIn("custom", self.mgr.list())
        delete_row = next(r for r in rows if r.text() == "Delete")
        delete_row.click()
        self.assertNotIn(
            "custom", self.mgr.list(), "clicking Delete did not remove the preset"
        )

    def test_wire_combo_italicises_builtins(self):
        combo = self._wire_combo()
        model = combo.model()
        items = {
            model.item(i).text(): model.item(i) for i in range(model.rowCount())
        }
        # Built-in shown italic; user preset is not. Text stays the raw name in
        # both cases so load/rename/delete still resolve.
        self.assertTrue(items["studio"].font().italic(), "built-in not italicised")
        self.assertFalse(items["custom"].font().italic(), "user preset wrongly italicised")
        # Marking must be font-only — no item icons (they shifted the collapsed
        # display's text and pushed the dropdown arrow into the name).
        self.assertTrue(items["studio"].icon().isNull(), "built-in should carry no icon")
        self.assertTrue(items["custom"].icon().isNull(), "user preset should carry no icon")

    def test_wire_combo_shadowed_builtin_is_not_italicised(self):
        # A user preset that shadows a built-in of the same name is editable, so
        # it must NOT be marked read-only (italic). The batched built-in
        # detection must honour the shadow (in built-in AND in user => user),
        # matching source() semantics.
        from uitk.widgets.comboBox import ComboBox

        self.mgr.save("studio")  # user preset shadowing the built-in "studio"
        self.assertEqual(self.mgr.source("studio"), "user", "precondition: shadowed")
        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        self.mgr.wire_combo(combo)
        model = combo.model()
        item = next(
            model.item(i)
            for i in range(model.rowCount())
            if model.item(i).text() == "studio"
        )
        self.assertFalse(
            item.font().italic(),
            "a user preset shadowing a built-in must not be italicised",
        )

    def test_wire_combo_menu_hides_rename_delete_for_builtin(self):
        combo = self._wire_combo()

        combo.setCurrentIndex(combo.findText("studio"))  # built-in
        # A read-only built-in can't be renamed/deleted -> only Open is offered.
        self.assertEqual(self._menu_labels(combo), ["Open Folder"])

        combo.setCurrentIndex(combo.findText("custom"))  # user
        self.assertEqual(
            self._menu_labels(combo), ["Rename", "Open Folder", "Delete"]
        )

    @staticmethod
    def _toolbar_buttons(combo):
        """The option-box toolbar buttons wrapping *combo*, in layout order.

        Index 0 of the container layout is the combo; 1.. are the option
        widgets (Refresh, Save, ⋯-menu).
        """
        container = combo.option_box.container
        layout = container.layout()
        return [layout.itemAt(i).widget() for i in range(1, layout.count())]

    def test_wire_combo_toolbar_is_refresh_save_menu(self):
        combo = self._wire_combo()
        btns = self._toolbar_buttons(combo)
        self.assertEqual(len(btns), 3, "toolbar = [refresh][save][menu]")
        tips = [b.toolTip() for b in btns]
        self.assertTrue(tips[0].startswith("Rescan"), f"button0 not Refresh: {tips[0]!r}")
        self.assertTrue(tips[1].startswith("Save"), f"button1 not Save: {tips[1]!r}")
        self.assertIn("rename", tips[2].lower(), f"button2 not the menu: {tips[2]!r}")
        # All icon-only -> no visible text.
        self.assertTrue(all(b.text() == "" for b in btns), "buttons must be icon-only")

    def test_unbounded_combo_height_is_clamped(self):
        # Regression: a preset combo dropped into a *stretchy* container (a
        # menu's "Menu Actions" group via add_presets) has no vertical limit and
        # balloons — the option-box icon buttons are sized to the combo height,
        # so they became huge squares and squeezed the dropdown to nothing.
        # wire_combo pins an unbounded combo to its natural row height.
        from uitk.widgets.comboBox import ComboBox

        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        self.assertGreaterEqual(combo.maximumHeight(), 16777215, "combo starts unbounded")
        self.mgr.wire_combo(combo)
        self.assertLess(combo.maximumHeight(), 16777215, "height left unbounded")
        self.assertEqual(
            combo.maximumHeight(), combo.minimumHeight(), "height not pinned"
        )

    def test_explicit_combo_height_is_preserved(self):
        # An in-panel caller that sets its own row height (e.g. 19px) must keep
        # it — the clamp only applies to unbounded combos.
        from uitk.widgets.comboBox import ComboBox

        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        combo.setMaximumHeight(19)
        self.mgr.wire_combo(combo)
        self.assertEqual(combo.maximumHeight(), 19, "explicit max height clobbered")

    def test_menu_is_cursor_centred_without_chrome(self):
        # The ⋯ menu (Rename / Open / Delete) is a plain action list: centred on
        # the cursor, no header / footer / apply-defaults chrome.
        from uitk.widgets.optionBox.options.option_menu import ContextMenuOption

        combo = self._wire_combo()
        opt = combo.option_box.find_option(ContextMenuOption)
        menu = opt.menu
        self.assertEqual(menu.position, "cursorPos", "menu not cursor-centred")
        self.assertFalse(menu.add_header, "menu should have no header")
        self.assertFalse(getattr(menu, "add_footer", False), "menu should have no footer")
        self.assertFalse(menu.add_apply_button, "menu should have no apply button")
        self.assertFalse(menu.add_defaults_button, "menu should have no defaults button")

    def _refresh_button(self, combo):
        return self._toolbar_buttons(combo)[0]

    def _save_button(self, combo):
        return self._toolbar_buttons(combo)[1]

    @staticmethod
    def _pick(combo, name):
        """Simulate a user picking *name* from the dropdown (fires load).

        Selection-load is wired to ``activated`` (user-only), so a plain
        ``setCurrentIndex`` would not load — emit ``activated`` to mimic a pick.
        """
        idx = combo.findText(name)
        combo.setCurrentIndex(idx)
        combo.activated[int].emit(idx)

    @staticmethod
    def _inline_commit(combo, text):
        """Type *text* into the editable combo and commit (as Enter would)."""
        combo.lineEdit().setText(text)
        combo.setEditable(False)  # emits on_editing_finished -> commit

    def test_wire_combo_refresh_reloads_current_preset(self):
        # Refresh re-applies the active preset's stored values to the widgets.
        from uitk.widgets.comboBox import ComboBox

        self.chk.setChecked(True)
        self.spn.setValue(42)
        self.mgr.save("custom")  # captures chk=True, spn=42

        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        self.mgr.wire_combo(combo)
        self._pick(combo, "custom")  # user pick loads -> spn 42
        self.assertEqual(self.spn.value(), 42)

        self.spn.setValue(7)  # user edits away from the preset
        self._refresh_button(combo).click()
        self.assertEqual(self.spn.value(), 42, "Refresh must reload the selected preset")

    def test_refresh_picks_up_preset_added_to_dir_by_hand(self):
        # A preset file dropped into the dir outside the UI must show up in the
        # combo after Refresh (not only on the next wire).
        from uitk.widgets.comboBox import ComboBox

        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        self.mgr.wire_combo(combo)  # combo: ["studio"] (built-in only)
        self.assertEqual(combo.findText("manual"), -1)

        # Simulate the user copying a preset file into the dir by hand.
        (self.user / "manual.json").write_text(
            json.dumps({"_meta": {"version": 1}, "chk_a": True, "spn_b": 9}),
            encoding="utf-8",
        )
        self._refresh_button(combo).click()
        self.assertGreaterEqual(
            combo.findText("manual"), 0,
            "Refresh must re-scan the dir for hand-added presets",
        )

    def test_refresh_drops_preset_removed_from_dir_by_hand(self):
        # A user preset deleted from the dir outside the UI must drop out of the
        # combo after Refresh, with no error even when it was the active preset.
        from uitk.widgets.comboBox import ComboBox

        self.mgr.save("custom")  # a user preset on disk
        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        self.mgr.wire_combo(combo)
        self._pick(combo, "custom")  # active -> custom
        self.assertGreaterEqual(combo.findText("custom"), 0)

        (self.user / "custom.json").unlink()  # user deletes the file by hand
        self._refresh_button(combo).click()
        self.assertEqual(
            combo.findText("custom"), -1,
            "Refresh must drop presets removed from the dir",
        )

    def test_wire_combo_inline_save_creates_user_preset(self):
        combo = self._wire_combo()
        self.spn.setValue(9)
        self._save_button(combo).click()  # enter inline edit
        self.assertTrue(combo.isEditable(), "Save enters inline edit mode")
        self._inline_commit(combo, "fresh")
        self.assertEqual(self.mgr.source("fresh"), "user", "inline Save wrote a user preset")
        self.assertEqual(self.mgr.active_preset, "fresh")
        self.assertEqual(combo.currentText(), "fresh")
        self.assertFalse(self.mgr.is_modified(), "marker clean right after save")

    def test_wire_combo_inline_rename_moves_user_preset(self):
        combo = self._wire_combo()  # has user "custom" + builtin "studio"
        self._pick(combo, "custom")
        rename_cb = self._menu_callback(combo, "Rename")
        rename_cb()  # begin inline rename, seeded with "custom"
        self.assertTrue(combo.isEditable())
        self.assertEqual(combo.lineEdit().text(), "custom")
        self._inline_commit(combo, "renamed")
        self.assertTrue(self.mgr.exists("renamed"))
        self.assertFalse(self.mgr.exists("custom"))
        self.assertEqual(combo.currentText(), "renamed")

    def test_inline_save_cancelled_by_focus_out_does_not_overwrite(self):
        """Backstop for the accidental-overwrite report: an inline Save edit that
        ends via focus-out (what an involuntary popup hide does to the field)
        must NOT commit — the active preset's file is left untouched even though
        the field was pre-filled with that preset's own name.

        Pairs with ``Menu`` hide-on-leave's focus guard (which keeps the popup
        open mid-edit in the first place): the guard prevents the hide, this
        proves the commit path stays inert if a hide happens anyway."""
        from qtpy import QtGui, QtCore

        combo = self._wire_combo()  # user "custom" + builtin "studio"
        self.spn.setValue(5)
        self.mgr.save("custom")  # custom.json now holds spn_b == 5
        self._pick(combo, "custom")  # active -> custom

        self._save_button(combo).click()  # inline Save, seeded with "custom"
        self.assertTrue(combo.isEditable())
        self.assertEqual(combo.lineEdit().text(), "custom")

        self.spn.setValue(99)  # a value a stray commit would clobber "custom" with
        # Simulate the popup hiding and stealing focus from the line edit.
        combo.focusOutEvent(QtGui.QFocusEvent(QtCore.QEvent.FocusOut))

        self.assertFalse(combo.isEditable(), "focus-out should exit edit mode")
        stored = json.loads((self.user / "custom.json").read_text(encoding="utf-8"))
        self.assertEqual(
            stored.get("spn_b"), 5,
            "focus-out cancel overwrote the active preset with the in-progress value",
        )

    # ------------------------------------------------------------------
    # active-preset memory + modified ("dirty") marker
    # ------------------------------------------------------------------
    def test_active_preset_persists_across_managers(self):
        # Loading records the active preset in the .active sidecar; a fresh
        # manager over the same dirs reads it back (cross-session restore).
        self.mgr.load("studio")
        self.assertEqual(self.mgr.active_preset, "studio")
        mgr2 = PresetManager.from_widgets(
            preset_dir=str(self.user),
            widgets=[self.chk, self.spn],
            builtin_dir=str(self.builtin),
        )
        self.assertEqual(mgr2.active_preset, "studio")

    def test_wire_combo_restores_selection_without_applying_values(self):
        # The crux of idea 1: restoring the *selection* must NOT re-apply the
        # preset values (widgets restore themselves from session state).
        from uitk.widgets.comboBox import ComboBox

        self.mgr.load("studio")  # active -> studio; chk True, spn 5
        self.chk.setChecked(False)
        self.spn.setValue(0)  # stand-in for separately-restored session values

        mgr2 = PresetManager.from_widgets(
            preset_dir=str(self.user),
            widgets=[self.chk, self.spn],
            builtin_dir=str(self.builtin),
        )
        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        mgr2.wire_combo(combo)

        self.assertEqual(combo.currentText(), "studio")  # selection restored
        self.assertFalse(self.chk.isChecked())  # values untouched
        self.assertEqual(self.spn.value(), 0)
        # The restored values diverge from the preset -> dirty marker shows.
        self.assertTrue(mgr2.is_modified())
        self.assertEqual(combo.current_text_suffix, " *")

    def test_modified_marker_set_on_edit_and_cleared_on_refresh(self):
        from uitk.widgets.comboBox import ComboBox

        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        self.mgr.wire_combo(combo)
        self._pick(combo, "studio")  # load -> spn 5
        self.assertFalse(self.mgr.is_modified())
        self.assertEqual(combo.current_text_suffix, "")

        self.spn.setValue(7)  # edit -> change signal auto-updates the marker
        self.assertTrue(self.mgr.is_modified())
        self.assertEqual(combo.current_text_suffix, " *")

        self._refresh_button(combo).click()  # revert
        self.assertEqual(self.spn.value(), 5)
        self.assertFalse(self.mgr.is_modified())
        self.assertEqual(combo.current_text_suffix, "")

    def test_modified_marker_cleared_on_save_over_active(self):
        from uitk.widgets.comboBox import ComboBox

        self.mgr.save("draft")  # a user preset to make active
        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        self.mgr.wire_combo(combo)
        self._pick(combo, "draft")
        self.spn.setValue(13)
        self.assertTrue(self.mgr.is_modified())
        # Saving over the active preset bakes the edit -> marker clears.
        self.mgr.save("draft")
        self.assertFalse(self.mgr.is_modified())
        self.assertEqual(combo.current_text_suffix, "")

    def test_refresh_reloads_active_even_when_index_is_minus_one(self):
        # Regression for the live "Refresh does nothing" bug: after a session
        # restore the combo index can be -1 while the active preset is known.
        # The old index-based Refresh no-oped; it must key off active_preset.
        from uitk.widgets.comboBox import ComboBox

        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        self.mgr.wire_combo(combo)
        self._pick(combo, "studio")  # active -> studio
        self.spn.setValue(7)
        combo.blockSignals(True)
        combo.setCurrentIndex(-1)  # simulate post-restore / no visible selection
        combo.blockSignals(False)
        self.assertEqual(combo.currentIndex(), -1)

        self._refresh_button(combo).click()
        self.assertEqual(self.spn.value(), 5)  # restored despite index -1

    def test_wire_combo_placeholder_when_no_active(self):
        from uitk.widgets.comboBox import ComboBox

        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        self.mgr.wire_combo(combo)  # nothing loaded -> no active preset
        self.assertEqual(combo.currentIndex(), -1)
        self.assertEqual(combo.placeholderText(), "Presets…")

    def test_delete_active_clears_pointer_and_marker(self):
        from uitk.widgets.comboBox import ComboBox

        self.mgr.save("draft")
        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        self.mgr.wire_combo(combo)
        self._pick(combo, "draft")
        self.assertEqual(self.mgr.active_preset, "draft")
        self._menu_callback(combo, "Delete")()
        self.assertIsNone(self.mgr.active_preset)
        self.assertEqual(combo.current_text_suffix, "")
        self.assertEqual(combo.currentIndex(), -1)


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

    # ------------------------------------------------------------------
    # active-preset + modified marker (semantic mode)
    # ------------------------------------------------------------------
    def _shared_state_mgr(self):
        """A manager whose applier drives the same dict the provider reads.

        Mirrors a real panel: applying a preset updates the param widgets that
        ``value_provider`` then reports, so ``is_modified`` is meaningful.
        """
        state = dict(self.live)

        def applier(data):
            for k, v in data.items():
                if k in state:
                    state[k] = v
            return len(data)

        mgr = PresetManager(
            preset_dir=str(self.user),
            builtin_dir=str(self.builtin),
            value_provider=lambda: dict(state),
            value_applier=applier,
        )
        return mgr, state

    @staticmethod
    def _refresh_button(combo):
        """The Refresh button (first option-box toolbar button)."""
        layout = combo.option_box.container.layout()
        return layout.itemAt(1).widget()

    def test_semantic_active_persists_across_managers(self):
        mgr, state = self._shared_state_mgr()
        mgr.load("specular")
        self.assertEqual(mgr.active_preset, "specular")
        mgr2 = PresetManager(
            preset_dir=str(self.user),
            builtin_dir=str(self.builtin),
            value_provider=lambda: dict(state),
            value_applier=lambda d: len(d),
        )
        self.assertEqual(mgr2.active_preset, "specular")

    def test_semantic_is_modified_tracks_edits(self):
        mgr, state = self._shared_state_mgr()
        mgr.load("specular")  # state -> align 2, depth moderate
        self.assertFalse(mgr.is_modified())
        state["align_downscale"] = 9  # edit away from the preset
        self.assertTrue(mgr.is_modified())
        # Saving over the active preset rebaselines -> clean again.
        mgr.save("specular")
        self.assertFalse(mgr.is_modified())

    def test_semantic_refresh_discards_edits_even_when_index_minus_one(self):
        from uitk.widgets.comboBox import ComboBox

        mgr, state = self._shared_state_mgr()
        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        mgr.wire_combo(combo)
        idx = combo.findText("specular")
        combo.setCurrentIndex(idx)
        combo.activated[int].emit(idx)  # user pick loads
        state["align_downscale"] = 9
        combo.blockSignals(True)
        combo.setCurrentIndex(-1)
        combo.blockSignals(False)
        self._refresh_button(combo).click()
        self.assertEqual(state["align_downscale"], 2)  # restored from preset

    # ------------------------------------------------------------------
    # modified_value_provider: cheaper capture for the dirty-check only
    # ------------------------------------------------------------------
    def test_modified_value_provider_used_only_for_dirty_check(self):
        """``is_modified`` uses the cheaper ``modified_value_provider``; ``save``
        still uses the full ``value_provider``. This is the seam that lets the
        hotkey editor test 'modified' against only the loaded UIs yet save a
        complete snapshot of every UI.
        """
        full_calls, cheap_calls = [], []
        state = {"align_downscale": 2, "depth_filter": "moderate"}

        def full_provider():
            full_calls.append(1)
            return dict(state)

        def cheap_provider():
            cheap_calls.append(1)
            return {"align_downscale": state["align_downscale"]}  # subset

        mgr = PresetManager(
            preset_dir=str(self.user),
            builtin_dir=str(self.builtin),
            value_provider=full_provider,
            value_applier=lambda d: len(d),
            modified_value_provider=cheap_provider,
        )
        mgr.load("specular")  # baseline = {align_downscale: 2, depth_filter: moderate}
        full_calls.clear()
        cheap_calls.clear()

        # Dirty-check goes through the cheap provider only.
        self.assertFalse(mgr.is_modified())
        self.assertEqual(cheap_calls, [1])
        self.assertEqual(full_calls, [], "is_modified must not call the full provider")

        # An edit visible to the cheap subset flips the marker (still no full call).
        state["align_downscale"] = 9
        full_calls.clear()
        cheap_calls.clear()
        self.assertTrue(mgr.is_modified())
        self.assertEqual(full_calls, [])

        # Save captures via the FULL provider (complete snapshot).
        full_calls.clear()
        mgr.save("specular")
        self.assertTrue(full_calls, "save must capture via the full value_provider")

    def test_is_modified_falls_back_to_value_provider(self):
        """With no ``modified_value_provider``, ``is_modified`` uses ``value_provider``."""
        calls = []
        state = {"align_downscale": 2, "depth_filter": "moderate"}
        mgr = PresetManager(
            preset_dir=str(self.user),
            builtin_dir=str(self.builtin),
            value_provider=lambda: (calls.append(1), dict(state))[1],
            value_applier=lambda d: len(d),
        )
        mgr.load("specular")
        calls.clear()
        mgr.is_modified()
        self.assertEqual(calls, [1], "is_modified falls back to value_provider")


class TestCaptureScope(BaseTestCase):
    """Per-instance capture ``scope`` + ``include`` / ``exclude`` filtering.

    Drives the standalone value path (the fake window has no ``state``) so the
    scope-selection and name-filter logic is exercised without a real
    ``StateManager`` / registered widgets. End-to-end StateManager integration
    for the real scene_exporter window is covered by a live-Maya probe.
    """

    class _FakeWindow:
        """Stands in for a uitk ``MainWindow``.

        Exposes ``widgets`` (the registered set) and ``state`` (``None`` here, so
        the standalone value path is exercised). ``state`` being present is what
        marks it as a window-parent to ``PresetManager._resolve_window``.
        """

        def __init__(self, widgets):
            self.widgets = set(widgets)
            self.state = None

        def objectName(self):  # liveness probe in PresetManager._resolve_window
            return "FakeWindow"

    class _FakeMenu:
        """Stands in for a uitk ``Menu``: ``get_items`` + ``owner_window``."""

        def __init__(self, items, window):
            self._items = list(items)
            self._window = window

        def get_items(self):
            return list(self._items)

        def owner_window(self):
            return self._window

    def setUp(self):
        super().setUp()
        from qtpy import QtWidgets

        self._tmp = Path(tempfile.mkdtemp(prefix="presets_scope_"))

        def _mk(cls, name, restore=True, **attrs):
            w = cls()
            w.setObjectName(name)
            w.restore_state = restore
            self.addCleanup(w.deleteLater)
            for k, v in attrs.items():
                getattr(w, k)(v)
            return w

        # Menu-hosted widgets (registered in the window's set in production).
        self.menu_chk = _mk(QtWidgets.QCheckBox, "menu_chk")
        # Panel widgets — what a menu-scoped preset misses today.
        self.panel_chk = _mk(QtWidgets.QCheckBox, "panel_chk")
        self.panel_txt = _mk(QtWidgets.QLineEdit, "panel_txt")
        self.path_txt = _mk(QtWidgets.QLineEdit, "path_txt")  # to be excluded
        # A non-restorable widget must never be captured in window scope.
        self.transient = _mk(QtWidgets.QCheckBox, "transient", restore=False)

        self.window = self._FakeWindow(
            [self.menu_chk, self.panel_chk, self.panel_txt, self.path_txt, self.transient]
        )
        self.menu = self._FakeMenu([self.menu_chk], self.window)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def _mgr(self, scope="auto"):
        mgr = PresetManager(parent=self.menu, preset_dir=str(self._tmp / "u"))
        mgr.scope = scope
        return mgr

    @staticmethod
    def _names(widgets):
        return {w.objectName() for w in widgets}

    def test_auto_scope_is_menu_only_for_a_menu_parent(self):
        # Regression guard: existing add_presets callers (reference_manager,
        # color_manager) stay menu-scoped under the default.
        mgr = self._mgr("auto")
        self.assertEqual(self._names(mgr._get_widgets()), {"menu_chk"})

    def test_window_scope_captures_panel_and_menu_widgets(self):
        mgr = self._mgr("window")
        # Whole window minus the non-restorable transient.
        self.assertEqual(
            self._names(mgr._get_widgets()),
            {"menu_chk", "panel_chk", "panel_txt", "path_txt"},
        )

    def test_menu_scope_is_explicitly_menu_only(self):
        mgr = self._mgr("menu")
        self.assertEqual(self._names(mgr._get_widgets()), {"menu_chk"})

    def test_exclude_drops_named_widget(self):
        mgr = self._mgr("window")
        mgr.exclude("path_txt")
        self.assertNotIn("path_txt", self._names(mgr._get_widgets()))
        self.assertIn("panel_chk", self._names(mgr._get_widgets()))

    def test_exclude_accepts_widget_instances(self):
        mgr = self._mgr("window")
        mgr.exclude(self.path_txt)
        self.assertNotIn("path_txt", self._names(mgr._get_widgets()))

    def test_include_is_an_allowlist(self):
        mgr = self._mgr("window")
        mgr.include("panel_chk")
        self.assertEqual(self._names(mgr._get_widgets()), {"panel_chk"})

    def test_window_scope_round_trip_restores_panel_widgets(self):
        mgr = self._mgr("window")
        mgr.exclude("path_txt")
        self.panel_chk.setChecked(True)
        self.panel_txt.setText("hello")
        self.path_txt.setText("C:/machine/specific")
        mgr.save("tmpl")

        # Mutate everything, then load the template back.
        self.panel_chk.setChecked(False)
        self.panel_txt.setText("")
        self.path_txt.setText("C:/other")
        mgr.load("tmpl")

        self.assertTrue(self.panel_chk.isChecked())          # restored
        self.assertEqual(self.panel_txt.text(), "hello")     # restored
        self.assertEqual(self.path_txt.text(), "C:/other")   # excluded, untouched

    def test_value_filter_only_applies_to_explicit_window_scope(self):
        # Back-compat guard: the legacy auto/MainWindow path
        # (``PresetManager(parent=window)`` — MainWindow.presets, curtain) must
        # keep its restore_state-only set; only explicit "window" scope drops
        # non-value widgets. Else those tools' saved presets silently change.
        from qtpy import QtWidgets

        btn = QtWidgets.QPushButton()
        btn.setObjectName("btn_action")
        btn.restore_state = True
        self.addCleanup(btn.deleteLater)
        win = self._FakeWindow([self.panel_chk, btn])
        mgr = PresetManager(parent=win, preset_dir=str(self._tmp / "u2"))

        # auto + window parent -> MainWindow mode, NO value-type filter.
        self.assertEqual(mgr.scope, "auto")
        self.assertIn("btn_action", self._names(mgr._get_widgets()))

        # explicit window scope -> value-type filter drops the button.
        mgr.scope = "window"
        names = self._names(mgr._get_widgets())
        self.assertNotIn("btn_action", names)
        self.assertIn("panel_chk", names)

    def test_invalid_scope_rejected(self):
        mgr = self._mgr("auto")
        with self.assertRaises(ValueError):
            mgr.scope = "everything"


class TestLoadPersistsSessionState(BaseTestCase):
    """MainWindow (``StateManager``) path: loading a preset persists the applied
    values to QSettings so the active preset survives to the next session.

    Regression for "the template is active in the combo but its widget values
    aren't restored next session": the bulk apply was fully suppressed, so the
    loaded preset never became session state and the next session restored the
    stale *pre-load* values while the active-name sidecar still pointed at the
    template. Previously this state path was only exercised by a live-Maya probe.
    """

    def setUp(self):
        super().setUp()
        from qtpy import QtCore
        from uitk.widgets.mixins.state_manager import StateManager

        self._tmp = Path(tempfile.mkdtemp(prefix="preset_session_"))
        self.user = self._tmp / "user"
        self.user.mkdir(parents=True)
        (self.user / "unity_basic.json").write_text(
            json.dumps({"_meta": {"version": 1}, "chk_a": True, "spn_b": 5}),
            encoding="utf-8",
        )
        self.store = QtCore.QSettings(
            str(self._tmp / "state.ini"), QtCore.QSettings.IniFormat
        )
        self.sm = StateManager(self.store)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def _make_widgets(self):
        from qtpy import QtWidgets

        chk = QtWidgets.QCheckBox()
        chk.setObjectName("chk_a")
        chk.restore_state = True
        chk.derived_type = QtWidgets.QCheckBox
        chk.default_signals = lambda: "toggled"
        spn = QtWidgets.QSpinBox()
        spn.setObjectName("spn_b")
        spn.setMaximum(100)
        spn.restore_state = True
        spn.derived_type = QtWidgets.QSpinBox
        spn.default_signals = lambda: "valueChanged"
        self.addCleanup(chk.deleteLater)
        self.addCleanup(spn.deleteLater)
        return chk, spn

    def _mgr(self, widgets):
        mgr = PresetManager(preset_dir=str(self.user), widgets=widgets)
        mgr.state = self.sm  # MainWindow mode
        return mgr

    def _seed_manual_state(self, chk, spn):
        chk.setChecked(False)
        spn.setValue(0)
        self.sm.save(chk)
        self.sm.save(spn)

    def test_load_writes_applied_values_to_qsettings(self):
        chk, spn = self._make_widgets()
        mgr = self._mgr([chk, spn])
        self._seed_manual_state(chk, spn)  # store holds the stale 0
        mgr.load("unity_basic")
        # The applied value is now the persisted session state, not the stale 0.
        self.assertEqual(int(self.store.value("spn_b/valueChanged")), 5)

    def test_active_template_restores_in_next_session(self):
        chk, spn = self._make_widgets()
        mgr = self._mgr([chk, spn])
        self._seed_manual_state(chk, spn)
        mgr.load("unity_basic")
        self.store.sync()

        # Next session: fresh widgets restore from QSettings; name from sidecar.
        chk2, spn2 = self._make_widgets()
        self.sm.load(chk2)
        self.sm.load(spn2)
        mgr2 = self._mgr([chk2, spn2])
        self.assertEqual(mgr2.active_preset, "unity_basic")
        self.assertTrue(chk2.isChecked())
        self.assertEqual(spn2.value(), 5)

    def test_manual_edit_after_load_coexists_with_template(self):
        chk, spn = self._make_widgets()
        mgr = self._mgr([chk, spn])
        self._seed_manual_state(chk, spn)
        mgr.load("unity_basic")  # chk True, spn 5
        spn.setValue(9)
        self.sm.save(spn)  # the change signal does this in production
        self.store.sync()

        chk2, spn2 = self._make_widgets()
        self.sm.load(chk2)
        self.sm.load(spn2)
        self.assertTrue(chk2.isChecked())  # template value survived
        self.assertEqual(spn2.value(), 9)  # manual edit survived

    def test_window_scope_adopts_state_and_persists(self):
        """The actual scene_exporter path (not a proxy): a *menu-parented*,
        ``scope="window"`` manager adopts the window's ``StateManager`` during
        ``_get_widgets`` and persists the loaded preset to it."""

        class _Win:
            def __init__(self, widgets, state):
                self.widgets = set(widgets)
                self.state = state

            def objectName(self):
                return "scene_exporter"

        class _Menu:
            def __init__(self, window):
                self._window = window

            def get_items(self):
                return []

            def owner_window(self):
                return self._window

        chk, spn = self._make_widgets()
        win = _Win([chk, spn], self.sm)
        mgr = PresetManager(parent=_Menu(win), preset_dir=str(self.user))
        mgr.scope = "window"
        self.assertIsNone(mgr.state)  # not adopted until a scope resolve

        self._seed_manual_state(chk, spn)  # stale 0 in the store
        mgr.load("unity_basic")

        self.assertIs(mgr.state, self.sm)  # adopted via window scope
        self.assertEqual(int(self.store.value("spn_b/valueChanged")), 5)  # persisted


if __name__ == "__main__":
    unittest.main()
