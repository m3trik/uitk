# !/usr/bin/python
# coding=utf-8
"""Tests for :mod:`uitk.testing`: :meth:`TestSandbox.activated`, the reversible form.

:meth:`TestSandbox.activate` redirects the ``QSettings`` class, its default
format and ini paths and the presets root for the rest of the process. That
suits a test process, not a host that goes on after the run: mayatk's
in-session harness runs a suite inside the user's own Maya, which would then
keep its settings in a temp file deleted when it exits. ``activated()`` takes
every one of those down again on the way out.

Each case runs in a fresh interpreter: this one is sandboxed by the conftest,
and a block entered under standing guards leaves them standing. The probes
only construct a ``QSettings`` and ask its file name and format, which reads
and writes no store.
"""

import json
import subprocess
import sys

from conftest import PACKAGE_ROOT, BaseTestCase

#: Run in the child first: everything the sandbox changes, captured to compare.
PRELUDE = """
import json, os, sys
sys.path[:0] = [{pythontk!r}, {uitk!r}]
from qtpy import QtCore
import pythontk as ptk
from uitk.testing import TestSandbox


def ini_path(scope):
    probe = QtCore.QSettings(QtCore.QSettings.IniFormat, scope, "uitk_probe", "x")
    return probe.fileName()


def snapshot():
    return [
        QtCore.QSettings,
        QtCore.QSettings.defaultFormat(),
        ini_path(QtCore.QSettings.UserScope),
        ini_path(QtCore.QSettings.SystemScope),
        os.environ.get(ptk.UserConfig.CONFIG_ROOT_ENV_VAR),
        ptk.TestSandbox.is_active(),
    ]


def under(path, root):
    return os.path.normcase(os.path.abspath(path)).startswith(
        os.path.normcase(os.path.abspath(root))
    )


before = snapshot()
report = {{}}
"""


class TestActivated(BaseTestCase):
    """Every guard ``activated()`` puts up comes down on the way out."""

    def _child(self, body):
        """Run *body* after :data:`PRELUDE` in a fresh interpreter; return the
        ``report`` dict it prints as its last line."""
        mono = PACKAGE_ROOT.parent
        code = PRELUDE.format(pythontk=str(mono / "pythontk"), uitk=str(PACKAGE_ROOT))
        proc = subprocess.run(
            [sys.executable, "-c", code + body],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout.splitlines()[-1])

    def test_every_guard_comes_off_on_exit(self):
        report = self._child(
            """
with TestSandbox.activated() as (qsettings_dir, presets_dir):
    store = QtCore.QSettings("uitk", "shared")
    report["redirected"] = store.format() == QtCore.QSettings.IniFormat and under(
        store.fileName(), qsettings_dir
    )
    report["presets"] = under(str(ptk.UserConfig.user_config_root()), presets_dir)
    report["active"] = TestSandbox.is_active()
    bound = QtCore.QSettings  # a module that bound the class by name
report["restored"] = snapshot() == before
report["inactive"] = not TestSandbox.is_active()
report["bound_class_is_real_again"] = (
    bound("uitk", "shared").format() == QtCore.QSettings("uitk", "shared").format()
)
report["dirs_gone"] = not (os.path.exists(qsettings_dir) or os.path.exists(presets_dir))
print(json.dumps(report))
"""
        )
        self.assertEqual(
            report,
            dict.fromkeys(
                ("redirected", "presets", "active", "restored", "inactive")
                + ("bound_class_is_real_again", "dirs_gone"),
                True,
            ),
        )

    def test_every_guard_comes_off_when_the_block_raises(self):
        report = self._child(
            """
try:
    with TestSandbox.activated():
        store = QtCore.QSettings("uitk", "shared")
        report["redirected"] = store.format() == QtCore.QSettings.IniFormat
        raise ValueError("a failing run")
except ValueError:
    report["raised"] = True
report["restored"] = snapshot() == before
report["inactive"] = not TestSandbox.is_active()
print(json.dumps(report))
"""
        )
        self.assertEqual(
            report,
            dict.fromkeys(("redirected", "raised", "restored", "inactive"), True),
        )

    def test_guards_standing_on_entry_stay_standing(self):
        """A block inside an ``activate()``'d process (a runner's child that
        imports a conftest) neither re-redirects nor takes anything down."""
        report = self._child(
            """
dirs = TestSandbox.activate()
standing = snapshot()
with TestSandbox.activated() as inner:
    report["same_dirs"] = inner == dirs
report["kept"] = snapshot() == standing
report["active"] = TestSandbox.is_active()
report["dirs_kept"] = all(os.path.isdir(d) for d in dirs)
print(json.dumps(report))
"""
        )
        self.assertEqual(
            report, dict.fromkeys(("same_dirs", "kept", "active", "dirs_kept"), True)
        )

    def test_a_detached_app_gets_the_developers_presets_root(self):
        """``ptk.TestSandbox.host_environ`` -- what ``AppLauncher.launch``
        hands a detached app -- puts the presets root back too: an app that
        outlives the run must not keep a throwaway store as its own."""
        report = self._child(
            """
name = ptk.UserConfig.CONFIG_ROOT_ENV_VAR
host = os.environ.get(name)
with TestSandbox.activated() as (_qsettings_dir, presets_dir):
    report["redirected"] = os.environ.get(name) == presets_dir
    report["host_root"] = TestSandbox.host_environ().get(name) == host
    with TestSandbox.user_config():  # the same variable, redirected again
        pass
    report["nested_kept"] = (
        os.environ.get(name) == presets_dir
        and TestSandbox.host_environ().get(name) == host
    )
report["cleared"] = TestSandbox.host_environ() is None
print(json.dumps(report))
"""
        )
        self.assertEqual(
            report,
            dict.fromkeys(("redirected", "host_root", "nested_kept", "cleared"), True),
        )
