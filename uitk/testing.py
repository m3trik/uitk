# !/usr/bin/python
# coding=utf-8
"""Test isolation for every suite in the ecosystem — keep test runs off live user state.

uitk's *production* state lives in the real per-user stores: ``QSettings`` (``HKCU\\Software\\uitk``
on Windows, ``~/.config/uitk`` elsewhere) and the consolidated preset root. Constructing almost any
uitk-backed object touches them — a ``MarkingMenu`` persists its bindings on construction, a
preset-enabled editor writes an ``.active`` sidecar on first run — so an unisolated suite silently
reads, rewrites and sometimes wipes the developer's live marking-menu bindings, widget state and
themes. The symptom is never a test failure: it is "my hotkey keeps resetting itself" hours later,
in a different app, with nothing to grep for.

This lives in the shipped package rather than in one repo's ``conftest.py`` because the stores are
**process-wide and shared across the whole ecosystem** — uitk, tentacle, mayatk and blendertk all
write the same ``(org, app)`` — so every downstream suite needs the identical redirect, and a second
copy is a copy that drifts. Downstream use is one line::

    from uitk.testing import TestSandbox
    TestSandbox.activate()

Call it **before the first ``QSettings`` is constructed** — at import time of a conftest or a test
runner, not from a fixture — since the redirect works by replacing the ``QSettings`` class.
"""
import os


class _TestSandboxInternal:
    """Redirect mechanics behind :class:`TestSandbox`."""

    _qsettings_dir = None
    _presets_dir = None

    @staticmethod
    def _throwaway_dir(name):
        """A temp dir for the life of this process, swept later if the process never exits.

        ``ptk.TempArtifacts(policy="session")`` rather than ``tempfile.mkdtemp`` + an ``atexit``
        ``rmtree``, per the monorepo rule: test runs are hosted inside DCCs and are routinely
        *killed* rather than exited, and an exit hook cannot run then — only the primitive's
        age-gated sweep of same-prefix leftovers ever reclaims those.

        ``name`` goes in the PREFIX and the tag is left unique, not the other way round: a fixed
        tag is deterministic and self-overwriting, so two suites running at once (uitk's and
        tentacle's, routinely) would share one store and clobber each other's settings.
        """
        import pythontk as ptk

        return ptk.TempArtifacts(f"uitk_test_{name}", policy="session").dir_path()


class TestSandbox(_TestSandboxInternal):
    """Point this process's user-state stores at throwaway temp dirs. Idempotent."""

    @classmethod
    def qsettings(cls):
        """Redirect every ``QSettings`` store to temp ini files; returns the temp dir.

        The catch on Windows: ``QSettings(org, app)`` and ``QSettings(scope, org, app)`` *always*
        use ``NativeFormat`` (the registry). They ignore ``setDefaultFormat`` (which governs only
        the no-arg / parent-only constructors), and ``setPath`` is a documented no-op for
        ``NativeFormat``. The only reliable redirect is to rewrite those two registry-bound
        overloads to the explicit ``IniFormat`` constructor — done by swapping ``QtCore.QSettings``
        for a thin subclass; ``setPath`` then steers the resulting ini files into the temp dir.

        Pass-through is deliberate for every other overload (explicit-format,
        ``QSettings(path, IniFormat)``, no-arg): those never touch the shared native store.
        Subclassing rather than a factory function preserves ``QSettings.IniFormat`` enum access
        and ``isinstance(x, QSettings)``.
        """
        if cls._qsettings_dir is not None:
            return cls._qsettings_dir

        from qtpy import QtCore

        tmp = cls._throwaway_dir("qsettings")
        real = QtCore.QSettings
        ini, user = real.IniFormat, real.UserScope

        for scope in (real.UserScope, real.SystemScope):
            real.setPath(ini, scope, tmp)
        # Load-bearing for the no-arg / QObject-parent constructors the subclass forwards verbatim.
        real.setDefaultFormat(ini)

        class _SandboxedQSettings(real):
            """Force the NativeFormat (registry-bound) overloads onto temp ini files."""

            def __init__(self, *args, **kwargs):
                if (
                    len(args) >= 2
                    and isinstance(args[0], str)
                    and isinstance(args[1], str)
                ):
                    # (org, app[, parent]) -> (Ini, UserScope, org, app[, parent])
                    super().__init__(ini, user, *args, **kwargs)
                elif (
                    len(args) >= 3
                    and isinstance(args[1], str)
                    and isinstance(args[2], str)
                ):
                    # (scope, org, app[, parent]) -> (Ini, scope, org, app[, parent])
                    super().__init__(ini, *args, **kwargs)
                else:
                    super().__init__(*args, **kwargs)

        QtCore.QSettings = _SandboxedQSettings
        cls._qsettings_dir = tmp
        return tmp

    @classmethod
    def presets(cls):
        """Redirect the consolidated preset root; returns the temp dir.

        Presets live outside QSettings — JSON files under ``<GenericConfigLocation>/uitk/<pkg>/`` —
        so :meth:`qsettings` does not cover them. Merely constructing a preset-enabled editor
        touches that store (legacy migration, dir creation, first-run ``.active`` sidecar).
        """
        if cls._presets_dir is not None:
            return cls._presets_dir
        # The env var name comes from pythontk rather than a literal: ``user_config`` and uitk's
        # ``preset_manager`` already agree on it by NAME only, so a third hardcoded copy is a third
        # thing to miss if it ever moves.
        from pythontk.core_utils.user_config import CONFIG_ROOT_ENV_VAR

        cls._presets_dir = cls._throwaway_dir("presets")
        os.environ[CONFIG_ROOT_ENV_VAR] = cls._presets_dir
        return cls._presets_dir

    @classmethod
    def activate(cls):
        """Redirect both stores; returns ``(qsettings_dir, presets_dir)``.

        What a suite wants unless it has a reason to isolate only one. Safe to call more than once
        — a second call returns the dirs the first created rather than re-redirecting (which would
        strand state already written to the first pair).
        """
        return cls.qsettings(), cls.presets()

    @classmethod
    def is_active(cls):
        """True once :meth:`qsettings` has redirected the store.

        For a suite that wants to *assert* its own isolation rather than assume it — the failure
        mode being silent, a missing sandbox is otherwise indistinguishable from a working one
        until a developer's live settings are already gone.
        """
        if cls._qsettings_dir is None:
            return False
        try:
            from qtpy import QtCore

            return QtCore.QSettings.__name__ == "_SandboxedQSettings"
        except Exception:
            return False
