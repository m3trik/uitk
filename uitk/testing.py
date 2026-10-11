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

A host that goes on after the run — the user's own Maya, where mayatk's in-session harness runs a
suite — takes every guard for the run only: ``with TestSandbox.activated():`` puts them all back on
the way out, an exception included.

The Qt-free half — refusing real browser launches, routing the process temp dir into one throwaway
root — is :class:`pythontk.TestSandbox`, which this extends: ``activate()`` runs those guards first
(so the stores below nest inside that root) and then the two Qt-side redirects. Same name on
purpose: downstream suites call ONE sandbox and get every guard the stack has.
"""

import os
from contextlib import ExitStack, contextmanager

import pythontk as ptk


class _TestSandboxInternal:
    """Redirect mechanics behind :class:`TestSandbox`."""

    _qsettings_dir = None
    _presets_dir = None

    @staticmethod
    def _qsettings_snapshot():
        """What :meth:`TestSandbox.qsettings` changes, read before it does.

        Returns ``(cls, default_format, {scope: ini_dir})``: the class ``QtCore.QSettings``
        names, its default format and each scope's IniFormat directory. Qt has no getter for
        ``setPath``; a ``QSettings`` built for an org that does not exist names the file it
        would use, and reads and writes nothing.
        """
        from qtpy import QtCore

        real = QtCore.QSettings
        paths = {}
        for scope in (real.UserScope, real.SystemScope):
            probe = real(real.IniFormat, scope, "uitk_sandbox_probe", "path")
            paths[scope] = os.path.dirname(os.path.dirname(probe.fileName()))
        return real, real.defaultFormat(), paths

    @classmethod
    def _lift_qsettings(cls, snapshot):
        """Put back what :meth:`TestSandbox.qsettings` changed, as *snapshot* read it."""
        from qtpy import QtCore

        real, default_format, paths = snapshot
        QtCore.QSettings = real
        real.setDefaultFormat(default_format)
        for scope, path in paths.items():
            real.setPath(real.IniFormat, scope, path)
        cls._qsettings_dir = None

    @classmethod
    def _lift_presets(cls, previous):
        """Point the presets root back at *previous* (unset when ``None``)."""
        cls._restore_env(ptk.UserConfig.CONFIG_ROOT_ENV_VAR, previous)
        cls._presets_dir = None

    @staticmethod
    def _throwaway_dir(name):
        """A temp dir for the life of this process, swept later if the process never exits.

        ``ptk.TempArtifacts(policy="session")`` rather than ``tempfile.mkdtemp`` + an ``atexit``
        ``rmtree``, per the monorepo rule: test runs are hosted inside DCCs and are routinely
        *killed* rather than exited, and an exit hook cannot run then — the primitive's sweep
        of same-prefix leftovers reclaims those: at once when their owner has exited (a session
        tag names it), else by age.

        ``name`` goes in the PREFIX and the tag is left unique, not the other way round: a fixed
        tag is deterministic and self-overwriting, so two suites running at once (uitk's and
        tentacle's, routinely) would share one store and clobber each other's settings.
        """
        import pythontk as ptk

        return ptk.TempArtifacts(f"uitk_test_{name}", policy="session").dir_path()


class TestSandbox(_TestSandboxInternal, ptk.TestSandbox):
    """Point this process's user-state stores at throwaway temp dirs. Idempotent.

    Plus everything :class:`pythontk.TestSandbox` guards (no real browser, one throwaway temp
    root) — see :meth:`activate`.
    """

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
        sandbox = cls

        class _SandboxedQSettings(real):
            """Force the NativeFormat (registry-bound) overloads onto temp ini files.

            Only while a sandbox stands: once :meth:`activated` lifts it, this constructs as the
            real class does — a module that bound ``QSettings`` by name inside the block keeps
            this class, and must reach the real stores again, not an ini file at the real path.
            """

            def __init__(self, *args, **kwargs):
                if sandbox._qsettings_dir is None:
                    super().__init__(*args, **kwargs)
                elif (
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

        Presets live outside QSettings — JSON files under ``<user_config_root>/<pkg>/``
        (``%LOCALAPPDATA%/uitk`` by default) — so :meth:`qsettings` does not cover them.
        Merely constructing a preset-enabled editor touches that store (legacy migration, dir
        creation, first-run ``.active`` sidecar).
        """
        if cls._presets_dir is not None:
            return cls._presets_dir
        # The env var name comes from pythontk, which owns the presets root: uitk's
        # ``PresetManager.get_presets_root`` IS ``ptk.UserConfig.user_config_root``, so this one
        # redirect moves the GUI and the headless preset stores together.
        cls._presets_dir = cls._throwaway_dir("presets")
        # Through the shared ledger, so a detached app launched from here gets
        # the developer's root back (``ptk.TestSandbox.host_environ``).
        cls._redirect_env(ptk.UserConfig.CONFIG_ROOT_ENV_VAR, cls._presets_dir)
        return cls._presets_dir

    @classmethod
    def activate(cls):
        """Every guard; returns ``(qsettings_dir, presets_dir)``.

        pythontk's process-level guards first (browser refusal, the throwaway temp root — so the
        two stores below land inside it), then both Qt-side redirects. What a suite wants unless it
        has a reason to isolate only one. Safe to call more than once — a second call returns the
        dirs the first created rather than re-redirecting (which would strand state already written
        to the first pair).
        """
        super().activate()
        return cls.qsettings(), cls.presets()

    @classmethod
    @contextmanager
    def activated(cls):
        """Every guard for the ``with`` block only; yields ``(qsettings_dir, presets_dir)``.

        :meth:`activate` for a host that goes on after the run: mayatk's in-session harness runs
        a suite inside the user's own Maya, which :meth:`activate` would leave constructing its
        stores into temp files deleted when it exits. On the way out, an exception included, the
        ``QSettings`` class, its default format and ini paths and the presets root are put back,
        then pythontk's guards (:meth:`pythontk.TestSandbox.activated`). A guard standing on entry
        (an :meth:`activate` before the block) stays standing. A store built inside the block
        keeps its sandbox file: it was a test's.
        """
        with super().activated(), ExitStack() as lift:
            if cls._qsettings_dir is None:
                lift.callback(cls._lift_qsettings, cls._qsettings_snapshot())
            if cls._presets_dir is None:
                previous = os.environ.get(ptk.UserConfig.CONFIG_ROOT_ENV_VAR)
                lift.callback(cls._lift_presets, previous)
            yield cls.qsettings(), cls.presets()

    @classmethod
    def is_active(cls):
        """True once every guard is in place: pythontk's and the ``QSettings`` redirect.

        For a suite that wants to *assert* its own isolation rather than assume it — the failure
        mode being silent, a missing sandbox is otherwise indistinguishable from a working one
        until a developer's live settings are already gone.
        """
        if cls._qsettings_dir is None or not super().is_active():
            return False
        try:
            from qtpy import QtCore

            return QtCore.QSettings.__name__ == "_SandboxedQSettings"
        except Exception:
            return False
