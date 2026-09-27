# !/usr/bin/python
# coding=utf-8
"""Preset-root migrations: pull presets saved under older layouts into the current root.

One part of :class:`~uitk.managers.preset_manager.PresetManager`, which
inherits it and runs it from ``preset_dir`` the first time a directory is
used. Two kinds live here:

* **Legacy layouts** (scheduled for removal, see the banner below): the
  pre-consolidation per-package folders (:data:`_LEGACY_PRESET_PATHS`, copied
  in once per package key and marked by a ``.migrated`` sentinel), and the old
  Qt-derived roots (``<AppConfigLocation>/...``, ``<GenericConfigLocation>/<pkg>``)
  drained once per process by :meth:`_PresetRootMigration._maybe_clear_legacy_qt_roots`.
* **Renamed preset domains** (:data:`_RENAMED_PRESET_DOMAINS`): a same-root
  rename of a preset folder, carried across on first use.

The current root is pythontk's (``ptk.UserConfig.user_config_root``); the Qt
location readers here exist only to FIND the old layouts, which Qt created.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from qtpy import QtCore
import pythontk as ptk

_log = logging.getLogger("uitk.managers.preset_manager")


class _PresetRootMigration:
    """One-shot moves of preset data from older layouts into the current root."""

    #: Set once the legacy Qt-root drain has run in this process (see
    #: :meth:`_maybe_clear_legacy_qt_roots`). Class state, flipped on this class
    #: only, so it is one flag per process however many managers exist.
    _qt_roots_cleared: bool = False

    @staticmethod
    def _presets_root() -> Path:
        """The current presets root -- pythontk's, the single owner."""
        return ptk.UserConfig.user_config_root()

    @staticmethod
    def _same_dir(a: Path, b: Path) -> bool:
        """True when *a* and *b* name the same directory (case/separators/links)."""
        try:
            return a.resolve() == b.resolve()
        except OSError:
            return os.path.normcase(os.path.abspath(a)) == os.path.normcase(
                os.path.abspath(b)
            )

    @staticmethod
    def QStandardPaths_writableLocation() -> str:
        """Return Qt's per-application writable config directory.

        On Windows this is ``<LOCALAPPDATA>/<exeName>`` (e.g.
        ``C:/Users/<u>/AppData/Local/python``) when no organisation/application
        name has been set on ``QCoreApplication`` — the ``<exeName>`` segment
        is Qt auto-naming from the executable, *not* a pre-existing dir.

        Used only for *finding legacy* preset data written under previous
        layouts; the current root is pythontk's (:meth:`_presets_root`).
        """
        return QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.AppConfigLocation
        )

    @staticmethod
    def QStandardPaths_genericConfigLocation() -> str:
        """Return Qt's host-independent writable config directory.

        On Windows this is ``<LOCALAPPDATA>`` directly (no executable-name
        segment); on macOS ``~/Library/Preferences``; on Linux ``~/.config``.
        Same path regardless of which host process (standalone Python, Maya,
        Painter, ...) is running. The pre-wrap layout C lived directly under it
        (see :meth:`_legacy_qt_root_candidates`); the current root is pythontk's
        (:meth:`_presets_root`), which resolves the same folder from the
        environment instead of Qt's known-folder API.
        """
        return QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.GenericConfigLocation
        )

    @staticmethod
    def _resolve_legacy_template(template: str) -> Path:
        """Expand ``{APPCONFIG}``, environment variables, and ``~`` in *template*."""
        if "{APPCONFIG}" in template:
            template = template.replace(
                "{APPCONFIG}", _PresetRootMigration.QStandardPaths_writableLocation()
            )
        return Path(ptk.UserConfig.expand(template))

    @staticmethod
    def _migration_sentinel_path(key: str) -> Path:
        """Path to the per-package sentinel marking a completed migration.

        The sentinel lives *inside* the migrated package dir itself (as a
        dotfile that ``glob('*.json')`` ignores) so it travels with its
        data — if the user wipes the package dir, the sentinel goes too
        and the next access re-migrates from legacy, which is normally
        what they want.
        """
        return (
            _PresetRootMigration._presets_root().joinpath(*key.split("/"))
            / _MIGRATION_SENTINEL_NAME
        )

    @staticmethod
    def _has_migrated(key: str) -> bool:
        return _PresetRootMigration._migration_sentinel_path(key).exists()

    @staticmethod
    def _mark_migrated(key: str) -> None:
        p = _PresetRootMigration._migration_sentinel_path(key)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch(exist_ok=True)
        except OSError as e:
            _log.warning("preset migration: could not mark %s migrated: %s", key, e)

    @staticmethod
    def _merge_move(src: Path, dst: Path) -> None:
        """Move *src* tree into *dst*, never overwriting existing destination files.

        Unlike ``shutil.move`` (which fails or overwrites on collisions), this
        walks the source tree and moves each file into place only if the
        corresponding destination doesn't exist. Empty source dirs are removed
        as the walk unwinds so a fully-merged subtree leaves nothing behind.
        Collisions silently keep the destination version — the assumption is
        that whatever the live code wrote is the user's intent.
        """
        if not dst.exists():
            try:
                shutil.move(str(src), str(dst))
            except (OSError, shutil.Error) as e:
                _log.warning("preset merge: could not move %s -> %s: %s", src, dst, e)
            return
        if src.is_file():
            # Collision at a leaf file. Keep the destination (whatever the
            # live code wrote is the user's intent) and leave the source in
            # place as evidence — a user investigating "missing preset"
            # symptoms can find it via the debug log and the on-disk copy.
            _log.debug("preset merge: collision at %s, kept destination", dst)
            return
        for item in list(src.iterdir()):
            _PresetRootMigration._merge_move(item, dst / item.name)
        try:
            src.rmdir()
        except OSError:
            pass

    @staticmethod
    def _legacy_qt_root_candidates() -> List[Path]:
        """Old preset root locations to drain into the current root.

        Three prior layouts existed:

        A. ``<AppConfigLocation>/m3trik/presets/<pkg>/...`` — an interim
           revision wrapped every relative preset in an unsolicited
           ``m3trik/presets`` segment.
        B. ``<AppConfigLocation>/<pkg>/...`` — used Qt's
           ``AppConfigLocation`` directly. That path embeds the host
           application name (``python/`` standalone, ``maya/`` from Maya,
           etc.), making presets invisible across hosts.
        C. ``<GenericConfigLocation>/<pkg>/...`` — used the host-independent
           config dir but as a bare root, so the ecosystem's packages were
           siblings of unrelated apps (pip, npm, Microsoft, ...). The
           current layout wraps everything in a single ``uitk/`` folder.

        Order matters: deepest layouts first so their contents don't get
        re-processed by outer passes. Pulled out as a function so tests can
        monkey-patch it to point at tmp dirs (essential — without the patch
        the cleanup would touch the real developer machine's data). The drain
        calls it through THIS class, so patch it here
        (``_PresetRootMigration._legacy_qt_root_candidates``), not on
        ``PresetManager``, which only inherits it.

        Returns ``[]`` when the root came from ``$UITK_PRESETS_ROOT``, or when the
        environment moved pythontk's root off Qt's known folder (a process
        started with a redirected ``%LOCALAPPDATA%`` / ``$XDG_CONFIG_HOME``:
        the same "use exactly this location" as the override). These are
        absolute *real* machine paths, and the drain
        (:func:`_maybe_clear_legacy_qt_roots`) hoists them with :func:`_merge_move`
        — a **move**, not a copy. ``<generic>/uitk`` IS the live store and ``uitk``
        IS one of the ``known_pkgs``, so against an overridden root the drain
        relocates the user's entire store into that root. For a power user pointing
        the override at a network share that is merely surprising; for a *test* —
        which redirects the root to a tmp dir and ``rmtree``s it in teardown — it is
        fatal, and it has already destroyed a real preset store once (mayatk's
        ``test_macro_editor_window`` sets the env var without patching this
        function, unlike ``TestLegacyMigration``). An explicit override means "use
        exactly this location", never "hoover the machine into it", so there is
        nothing legitimate to drain. The guard lives *here*, inside the seam tests
        already replace, so a test that patches this function keeps its behaviour
        while every test that merely sets the env var is protected by default.
        """
        if os.environ.get(ptk.UserConfig.CONFIG_ROOT_ENV_VAR):
            return []
        appconfig = Path(_PresetRootMigration.QStandardPaths_writableLocation())
        generic = Path(_PresetRootMigration.QStandardPaths_genericConfigLocation())
        # The root is pythontk's (``UserConfig.user_config_root``), resolved from
        # the environment; these candidates are Qt's known folders. When the two
        # disagree (a process started with a redirected %LOCALAPPDATA% /
        # $XDG_CONFIG_HOME) the environment has redirected the root, and
        # ``<generic>/uitk`` -- the REAL live store -- would be hoisted into it:
        # the same store-destroying move the override guard above prevents.
        if not _PresetRootMigration._same_dir(
            _PresetRootMigration._presets_root(), generic / _ECOSYSTEM_WRAPPER_NAME
        ):
            return []
        return [appconfig / "m3trik" / "presets", appconfig, generic]

    @staticmethod
    def _dir_has_preset_data(directory: Path) -> bool:
        """True when *directory* holds at least one preset file (``*.json``).

        Distinguishes a *husk* — an empty shell a prior wrap left behind,
        holding only a ``.migrated`` sentinel (the merge keeps the destination
        on a sentinel collision, so the source dir survives) — from genuine
        pre-wrap state that still carries presets to relocate. A husk must not
        count as pre-wrap evidence, or it re-triggers the wrap on every launch
        and keeps reburying correctly-placed packages (the "saved preset gone
        next session" bug).
        """
        try:
            return any(directory.rglob("*.json"))
        except OSError:
            return False

    @staticmethod
    def _looks_like_ecosystem_wrapper(uitk_dir: Path) -> bool:
        """True when *uitk_dir* is already in the wrapper layout.

        Pre-wrap evidence is **only** one of uitk's OWN state dirs
        (:data:`_UITK_OWN_PRE_WRAP_DIRS`) sitting at the root, carrying data.
        Anything else — ``mayatk/``, ``blendertk/``, ``shots/``, a package added
        next year — is a correctly-placed sibling, never pre-wrap state.

        This is an **allowlist of uitk's own dirs**, not a denylist of
        ``known_pkgs``. It used to be the latter, and *that was a data-corrupting
        bug*: ``known_pkgs`` is derived from :data:`_LEGACY_PRESET_PATHS`, a table
        frozen around the packages that existed when the legacy layouts died
        (``uitk`` / ``mayatk`` / ``extapps``). Every package added afterwards —
        ``blendertk``, ``shots`` — was therefore "non-known", so its live state read
        as pre-wrap and got buried in ``<generic>/uitk/uitk/<pkg>/`` on the next
        launch. Worse, the move is a :func:`_merge_move`, which keeps the
        destination on a collision and leaves the source behind, so a store could be
        *split across both levels* — the observed failure was blendertk's
        ``macro_manager`` with ``.active`` relocated but ``m3trik.json`` stranded at
        the source, leaving ``PresetStore.active`` reading ``None`` and every macro
        hotkey silently unbound.

        Empty dirs — and data-less *husks* (only a ``.migrated`` sentinel,
        no ``*.json``) — count as "already wrapped": there is nothing to
        move, and treating them as pre-wrap would re-fire the wrap forever,
        burying any package freshly re-created at the root in between.
        """
        if not uitk_dir.is_dir():
            return False
        try:
            child_dirs = [p for p in uitk_dir.iterdir() if p.is_dir()]
        except OSError:
            return False
        if not child_dirs:
            return True
        for child in child_dirs:
            if child.name not in _UITK_OWN_PRE_WRAP_DIRS:
                continue  # another package's state — correctly placed, never move it
            if not _PresetRootMigration._dir_has_preset_data(child):
                continue  # husk left by a prior wrap — not real pre-wrap state
            return False
        return True

    @staticmethod
    def _wrap_pre_wrap_uitk_state(uitk_dir: Path) -> None:
        """Restructure ``<generic>/uitk/`` from pre-wrap to wrapper layout.

        Before this code: ``<generic>/uitk/`` held uitk-package state
        directly (``style_presets/``, ``hotkey_presets/``, ...). The
        current layout uses ``<generic>/uitk/`` as the *ecosystem wrapper*
        with uitk's own state nested at ``<generic>/uitk/uitk/``. This
        function detects the pre-wrap state and moves the existing contents
        one level deeper, in place, without a sibling temp dir.

        Robust to a previously-interrupted wrap: the detector treats any
        *data-bearing* non-known-pkg / non-dotfile child as evidence of
        pre-wrap state, so a partial wrap (inner ``uitk/`` already created,
        some siblings not yet moved) gets finished on the next call.

        Only uitk's own pre-wrap dirs move down. A known-package sibling
        (``mayatk/``, ``extapps/``, and the inner ``uitk/`` itself) already
        lives at the correct level, so it is left in place — relocating it
        would bury presets saved under it where the live load path can't
        find them (the "saved preset gone next session" bug).

        Interim migration-state artifacts (``.migrated``, ``.migration/``)
        that survive from older revisions of this module are dropped
        rather than carried into the new layout.

        No-op if *uitk_dir* doesn't exist or is already in the wrapper
        layout.
        """
        if not uitk_dir.exists() or not uitk_dir.is_dir():
            return
        if _PresetRootMigration._looks_like_ecosystem_wrapper(uitk_dir):
            return

        # Snapshot children BEFORE creating the target so the target itself
        # (created below) doesn't appear in our iteration.
        try:
            children = list(uitk_dir.iterdir())
        except OSError as e:
            _log.warning("preset wrap: could not iterate %s: %s", uitk_dir, e)
            return

        target = uitk_dir / _ECOSYSTEM_WRAPPER_NAME
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            _log.warning("preset wrap: could not create %s: %s", target, e)
            return

        for child in children:
            # Drop interim migration-state artifacts; they're dead state
            # from older revisions and shouldn't be preserved.
            if child.name in _INTERIM_STATE_ARTIFACTS:
                try:
                    if child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        shutil.rmtree(child)
                except OSError as e:
                    _log.warning("preset wrap: could not remove %s: %s", child, e)
                continue
            # Only uitk's OWN pre-wrap state moves down. Every other sibling —
            # mayatk/, blendertk/, extapps/, shots/, the inner uitk/ itself, and any
            # package added later — already lives at the right level; relocating it
            # buries presets where the live load path will never find them (and
            # _merge_move's keep-the-destination rule can strand half a store at each
            # level). This was previously `child.name in known_pkgs`, a denylist that
            # silently swallowed every package younger than _LEGACY_PRESET_PATHS.
            # Files never move: on Linux this folder is also QSettings' INI home
            # (org "uitk": shared.conf, GlobalStyle.conf, ...), and burying those
            # reset every setting.
            if not child.is_dir() or child.name not in _UITK_OWN_PRE_WRAP_DIRS:
                continue
            # The inner target itself shows up in the snapshot only if it
            # pre-existed; skip it so we don't try to move it into itself.
            if child.resolve() == target.resolve():
                continue
            dest = target / child.name
            if dest.exists():
                _PresetRootMigration._merge_move(child, dest)
            else:
                try:
                    shutil.move(str(child), str(dest))
                    _log.debug("preset wrap: moved %s -> %s", child, dest)
                except (OSError, shutil.Error) as e:
                    _log.warning(
                        "preset wrap: could not move %s -> %s: %s", child, dest, e
                    )

    @staticmethod
    def _maybe_clear_legacy_qt_roots() -> None:
        """Hoist preset data from older root layouts to the current root.

        Runs two passes:

        1. **Pre-wrap detection.** If the new root (``<generic>/uitk/``)
           already exists but holds *uitk-package* state directly (the
           pre-wrap layout where ``<generic>/uitk/style_presets/`` lived
           at the root level), restructure it in place into the wrapper
           layout (``<generic>/uitk/uitk/style_presets/``). See
           :func:`_wrap_pre_wrap_uitk_state`.

        2. **Candidate drain.** Iterates :func:`_legacy_qt_root_candidates`
           in nesting order and, for each candidate, hoists only the
           *known package* subdirs (uitk / mayatk / extapps — derived from
           ``_LEGACY_PRESET_PATHS`` keys) into the new root. Other contents
           — pip's cache, other Python tools' configs, unrelated apps'
           data — are left strictly alone.

        Before each drain, interim migration-state artifacts
        (``.migrated``, ``.migration/``) are deleted so they don't leak up.
        Empty ``m3trik`` shells are removed afterward; bare
        AppConfigLocation / GenericConfigLocation dirs are never removed
        since they usually hold other apps' data.

        Guarded by a process-global flag so subsequent ``preset_dir``
        accesses are zero-cost.
        """
        # Set on the owning class, never through ``cls``/a subclass: the drain
        # runs once per PROCESS, whichever class reached it first.
        if _PresetRootMigration._qt_roots_cleared:
            return
        _PresetRootMigration._qt_roots_cleared = True

        new_root = _PresetRootMigration._presets_root()
        known_pkgs = {key.split("/")[0] for key in _LEGACY_PRESET_PATHS}

        # Pass 1: handle the pre-wrap collision at the new root itself.
        _PresetRootMigration._wrap_pre_wrap_uitk_state(new_root)

        # Pass 2: drain candidates.
        candidates = _PresetRootMigration._legacy_qt_root_candidates()
        for old_root in candidates:
            # Skip when old_root *is* the new root — pass 1 already handled it.
            try:
                if old_root.resolve() == new_root.resolve():
                    continue
            except OSError:
                continue
            if not old_root.exists() or not old_root.is_dir():
                continue

            # Drop interim migration-state artifacts so they don't litter
            # the new root.
            for artifact in _INTERIM_STATE_ARTIFACTS:
                artifact_path = old_root / artifact
                try:
                    if artifact_path.is_file():
                        artifact_path.unlink()
                    elif artifact_path.is_dir():
                        shutil.rmtree(artifact_path)
                except OSError as e:
                    _log.warning(
                        "preset cleanup: could not remove %s: %s", artifact_path, e
                    )

            # Hoist only known package subdirs. If a candidate *contains*
            # the new root (e.g. old_root == <generic>, new_root ==
            # <generic>/uitk), the uitk subdir IS the new root — pass 1
            # already handled it, so skip that single pkg here.
            for pkg in known_pkgs:
                src = old_root / pkg
                if not src.exists() or not src.is_dir():
                    continue
                try:
                    if src.resolve() == new_root.resolve():
                        continue  # pass 1 territory
                except OSError:
                    continue
                dst = new_root / pkg
                _log.debug("preset cleanup: hoisting %s -> %s", src, dst)
                _PresetRootMigration._merge_move(src, dst)

        # Clean up the m3trik shell if it's now empty. Identified by the path
        # shape ``.../m3trik/presets`` so the cleanup works whether candidates
        # come from the real QStandardPaths or a test monkey-patch. The bare
        # AppConfigLocation / GenericConfigLocation candidates are never
        # removed — they hold unrelated apps' data.
        for cand in candidates:
            if cand.name == "presets" and cand.parent.name == "m3trik":
                for p in (cand, cand.parent):
                    try:
                        p.rmdir()
                    except OSError:
                        pass

    @staticmethod
    def _maybe_migrate_legacy(new_dir: Path) -> None:
        """Copy a legacy preset tree into the consolidated root once.

        Finds the longest prefix of *new_dir*'s relative path that maps to a
        known legacy location in :data:`_LEGACY_PRESET_PATHS`. When such a
        package boundary is found and the migration sentinel does not yet
        exist, copies the *entire* legacy tree (every subdir, every preset)
        so sibling subdirs not yet requested are present too — this matters
        for bridges that switch active template at runtime.

        Existing files at the destination are never overwritten; if the user
        already has presets in the new location, the legacy contents merge
        in beside them. Marks the package migrated either way so subsequent
        accesses are no-ops. Best-effort: I/O failures swallow rather than
        propagate to keep preset loading robust at runtime.
        """
        _PresetRootMigration._maybe_clear_legacy_qt_roots()
        presets_root = _PresetRootMigration._presets_root()
        try:
            rel = new_dir.relative_to(presets_root)
        except ValueError:
            return  # absolute path outside the consolidated root

        matched_key: Optional[str] = None
        for length in range(len(rel.parts), 0, -1):
            candidate = "/".join(rel.parts[:length])
            if candidate in _LEGACY_PRESET_PATHS:
                matched_key = candidate
                break
        if matched_key is None or _PresetRootMigration._has_migrated(matched_key):
            return

        # Migrate the whole package, not the requested leaf — sibling subdirs
        # (e.g. other bridge templates) would otherwise be silently orphaned
        # once the package is marked migrated.
        legacy_pkg_root = _PresetRootMigration._resolve_legacy_template(
            _LEGACY_PRESET_PATHS[matched_key]
        )
        new_pkg_root = presets_root.joinpath(*matched_key.split("/"))

        if legacy_pkg_root.exists() and legacy_pkg_root.is_dir():
            try:
                new_pkg_root.mkdir(parents=True, exist_ok=True)
                for item in legacy_pkg_root.iterdir():
                    _PresetRootMigration._merge_move(item, new_pkg_root / item.name)
                # Drop the legacy package root if empty after the merge.
                # Non-empty means collisions left files in place (forensic
                # preservation — see _merge_move docs); leaving the dir
                # gives the user something to inspect.
                try:
                    legacy_pkg_root.rmdir()
                except OSError:
                    pass
            except OSError as e:
                # see docstring: best-effort. Logged so users can opt into
                # diagnostics; default is silent.
                _log.warning(
                    "preset migration: %s from %s failed: %s",
                    matched_key,
                    legacy_pkg_root,
                    e,
                )

        _PresetRootMigration._mark_migrated(matched_key)

    @staticmethod
    def _maybe_migrate_renamed_domain(new_dir: Path) -> None:
        """Move presets from a renamed sibling domain into *new_dir*, once.

        Looks up *new_dir*'s leaf name in :data:`_RENAMED_PRESET_DOMAINS`; when it
        was renamed from a prior leaf, a same-parent dir under that prior name is
        merged in via :func:`_merge_move` (which never overwrites an existing
        destination file, so a post-rename edit always wins). Interim migration
        artifacts are dropped rather than carried. Best-effort: I/O failures are
        swallowed so preset loading stays robust.
        """
        old_name = _RENAMED_PRESET_DOMAINS.get(new_dir.name)
        if not old_name:
            return
        old_dir = new_dir.with_name(old_name)
        if old_dir == new_dir or not old_dir.is_dir():
            return
        try:
            new_dir.mkdir(parents=True, exist_ok=True)
            for item in list(old_dir.iterdir()):
                if item.name in _INTERIM_STATE_ARTIFACTS:
                    try:
                        item.unlink()
                    except OSError:
                        pass
                    continue
                _PresetRootMigration._merge_move(item, new_dir / item.name)
            try:
                old_dir.rmdir()  # removed only if fully carried (no collisions left)
            except OSError:
                pass
        except OSError as e:
            _log.warning(
                "preset domain rename %s -> %s failed: %s", old_name, new_dir.name, e
            )


# Wrapper folder under the per-user config dir (``<generic>/uitk``). Also the
# name of uitk's OWN folder inside it (``<generic>/uitk/uitk``) that the pre-wrap
# layout is moved down into -- see ``_wrap_pre_wrap_uitk_state``.
_ECOSYSTEM_WRAPPER_NAME = "uitk"


# =============================================================================
# DEPRECATED MIGRATION LOGIC — scheduled for removal
# =============================================================================
#
# Everything in this module except the renamed-domain pass
# (``_RENAMED_PRESET_DOMAINS`` / ``_maybe_migrate_renamed_domain``) and the
# small shared helpers (``_presets_root``, ``_same_dir``) exists solely to
# migrate users coming from older preset-path layouts. It is *not* part of the
# current design and should be deleted once no users remain on the old layouts.
# The mayatk / extapps rows of ``_LEGACY_PRESET_PATHS`` go first, on 2026-11-19
# (``.claude/FUTURE.md``).
#
# Removal candidates (delete together — they form one self-contained block):
#
#   - ``_MIGRATION_SENTINEL_NAME``
#   - ``_LEGACY_PRESET_PATHS``
#   - ``_resolve_legacy_template``
#   - ``_migration_sentinel_path``
#   - ``_has_migrated``
#   - ``_mark_migrated``
#   - ``_merge_move`` (unless the renamed-domain pass still needs it)
#   - ``_PresetRootMigration._qt_roots_cleared``
#   - ``QStandardPaths_writableLocation`` / ``QStandardPaths_genericConfigLocation``
#     (and their module aliases in ``preset_manager``)
#   - ``_INTERIM_STATE_ARTIFACTS``
#   - ``_legacy_qt_root_candidates``
#   - ``_looks_like_ecosystem_wrapper``
#   - ``_wrap_pre_wrap_uitk_state``
#   - ``_maybe_clear_legacy_qt_roots``
#   - ``_maybe_migrate_legacy``
#   - The ``_maybe_migrate_legacy(self._preset_dir)`` call inside the
#     ``PresetManager.preset_dir`` property
#   - Test class ``TestLegacyMigration`` in ``test/test_preset_manager.py``
#
# Removal criteria (any one is sufficient):
#
#   1. No legacy preset data exists at the candidate roots on any
#      machine that runs this code — confirmed by inspection.
#   2. The deprecation review date below has passed AND the
#      ``.migrated`` sentinel files have been present in user dirs
#      long enough that any first-launch on legacy data has run.
#
# Suggested review date: **2027-05-21** (one year out from the
# introduction of GenericConfigLocation as the root). Reviewing earlier
# is fine if you're confident in (1). Reviewing later is fine too —
# the migration code is small, idempotent, and gated by a per-process
# flag so its runtime cost is negligible.
#
# =============================================================================

_MIGRATION_SENTINEL_NAME = ".migrated"


# Map: new relative path under the consolidated root → legacy absolute path
# template. ``{APPCONFIG}`` is substituted with QStandardPaths.AppConfigLocation
# at resolution time so the table itself stays declarative.
#
# Each entry represents a *package boundary*: when a request resolves to a
# path under one of these keys (e.g. ``mayatk/substance_bridge/<template>``),
# the *entire* legacy tree for that key is copied so sibling subdirs (other
# bridge templates) come along for the ride — not just the requested leaf.
_LEGACY_PRESET_PATHS: Dict[str, str] = {
    "mayatk/substance_bridge": "~/.mayatk/presets/substance_bridge",
    "mayatk/marmoset_bridge": "~/.mayatk/presets/marmoset_bridge",
    "mayatk/rizom_bridge": "~/.mayatk/presets/rizom_bridge",
    "mayatk/scene_exporter": "~/.mayatk/presets/scene_exporter",
    "mayatk/reference_manager": "~/.mayatk/presets/reference_manager",
    "mayatk/color_manager": "~/.mayatk/presets/color_manager",
    "mayatk/shot_manifest_colors": "~/.mayatk/presets/shot_manifest_colors",
    "extapps/texture_maps/packer": "~/.pythontk/presets/map_packer",
    "uitk/style_presets": "{APPCONFIG}/uitk/style_presets",
    "uitk/shortcut_presets": "{APPCONFIG}/uitk/hotkey_presets",
    "uitk/switchboard_browser/presets": "{APPCONFIG}/uitk/switchboard_browser/presets",
}


_INTERIM_STATE_ARTIFACTS = (".migrated", ".migration")

# uitk's OWN state dirs, as they sat at ``<generic>/uitk/`` in the pre-wrap
# layout. These are the ONLY children the wrap may relocate down into
# ``<generic>/uitk/uitk/`` — see _looks_like_ecosystem_wrapper for why this is an
# allowlist rather than "everything not in known_pkgs" (that denylist buried every
# package younger than _LEGACY_PRESET_PATHS: blendertk, shots).
# ``hotkey_presets`` is the pre-rename name of ``shortcut_presets`` and is listed
# so a store that never launched post-rename still wraps correctly.
_UITK_OWN_PRE_WRAP_DIRS = frozenset(
    {"style_presets", "shortcut_presets", "hotkey_presets", "switchboard_browser"}
)


# Intra-root preset-domain renames: { new_leaf_dir: prior_leaf_dir } under the
# same parent. When the new domain dir is first ensured, presets saved under the
# prior name (same parent) are carried across so *renaming* a preset domain keeps
# the user's snapshots. Distinct from _LEGACY_PRESET_PATHS (which pulls from
# external pre-consolidation roots); this is a same-root rename.
_RENAMED_PRESET_DOMAINS: Dict[str, str] = {
    # 2026-06: the global key-binding editor's domain was renamed from
    # "hotkey_presets" to "shortcut_presets" (hotkey -> shortcut terminology).
    "shortcut_presets": "hotkey_presets",
}
