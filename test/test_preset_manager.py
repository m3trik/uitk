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

    def setUp(self):
        super().setUp()
        self._tmp = Path(tempfile.mkdtemp(prefix="presets_migrate_"))
        self._new_root = self._tmp / "new"
        self._legacy_root = self._tmp / "legacy"

        # Redirect the consolidated root.
        self._prior_env = os.environ.pop(PRESETS_ROOT_ENV_VAR, None)
        os.environ[PRESETS_ROOT_ENV_VAR] = str(self._new_root)

        # Inject a test entry into the legacy table.
        self.SAVED_LEGACY_PATHS = dict(pm._LEGACY_PRESET_PATHS)
        pm._LEGACY_PRESET_PATHS[self.TEST_KEY] = str(self._legacy_root)

    def tearDown(self):
        # Restore the legacy table and env var.
        pm._LEGACY_PRESET_PATHS.clear()
        pm._LEGACY_PRESET_PATHS.update(self.SAVED_LEGACY_PATHS)
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

    def test_flat_package_migration_copies_files(self):
        self._write_legacy("red.json", {"_meta": {"version": 1}, "r": 255})

        mgr = PresetManager(preset_dir=self.TEST_KEY)
        resolved = mgr.preset_dir

        self.assertTrue((resolved / "red.json").exists())
        with open(resolved / "red.json", "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["r"], 255)

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


if __name__ == "__main__":
    unittest.main()
