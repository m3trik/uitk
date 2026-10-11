# !/usr/bin/python
# coding=utf-8
"""Tests for uitk._bootstrap (pre-QApplication setup, window-system capabilities)."""

import os
import sys
import unittest
from unittest.mock import patch

from conftest import BaseTestCase, setup_qt_application

setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402

import pythontk as ptk  # noqa: E402
from uitk._bootstrap import Bootstrap  # noqa: E402


class TestConfigurePlatform(BaseTestCase):
    """A standalone uitk app runs its Qt on X11 when a Wayland session offers
    it: native Wayland cannot place the marking menu or a popup at the cursor."""

    def _configure(self, env, platform="linux"):
        with (
            patch.object(
                QtWidgets.QApplication, "instance", new=staticmethod(lambda: None)
            ),
            patch.object(sys, "platform", platform),
            patch.dict(os.environ, env, clear=True),
        ):
            applied = Bootstrap.configure_platform()
            return applied, os.environ.get("QT_QPA_PLATFORM")

    def test_a_wayland_session_with_xwayland_runs_on_x11_first(self):
        env = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
        # X11 first; native Wayland if the xcb plug-in cannot load.
        self.assertEqual(self._configure(env), (True, "xcb;wayland"))

    def test_an_explicit_platform_always_wins(self):
        env = {
            "WAYLAND_DISPLAY": "wayland-0",
            "DISPLAY": ":0",
            "QT_QPA_PLATFORM": "wayland",
        }
        self.assertEqual(self._configure(env), (False, "wayland"))

    def test_nothing_changes_without_xwayland_or_off_linux(self):
        self.assertEqual(
            self._configure({"WAYLAND_DISPLAY": "wayland-0"}), (False, None)
        )
        self.assertEqual(self._configure({"DISPLAY": ":0"}), (False, None))
        env = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
        self.assertEqual(self._configure(env, platform="win32"), (False, None))

    def test_a_host_owned_application_is_left_alone(self):
        """Inside Maya/Blender the QApplication exists: too late, and not ours."""
        env = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(Bootstrap.configure_platform())
            self.assertIsNone(os.environ.get("QT_QPA_PLATFORM"))


class TestCapabilities(BaseTestCase):
    def test_only_native_wayland_forbids_client_placement(self):
        for name, expected in (
            ("wayland", False),
            ("wayland-egl", False),
            ("xcb", True),
            ("windows", True),
        ):
            with (
                self.subTest(platform=name),
                patch.object(
                    QtGui.QGuiApplication,
                    "platformName",
                    new=staticmethod(lambda n=name: n),
                ),
            ):
                self.assertIs(Bootstrap.positions_windows(), expected)

    def test_only_x11_without_a_compositor_drops_translucency(self):
        """Without a compositing manager an X11 translucent window paints
        black; an unknown answer (no X server to ask) keeps translucency."""
        cases = (
            ("xcb", False, False),
            ("xcb", True, True),
            ("xcb", None, True),
            ("windows", False, True),
        )
        for platform, compositor, expected in cases:
            with (
                self.subTest(platform=platform, compositor=compositor),
                patch.object(
                    QtGui.QGuiApplication,
                    "platformName",
                    new=staticmethod(lambda p=platform: p),
                ),
                patch.object(ptk.X11, "has_compositor", return_value=compositor),
            ):
                self.assertIs(Bootstrap.composites(), expected)


@unittest.skipUnless(
    QtGui.QGuiApplication.platformName() == "xcb" and ptk.X11.has_compositor() is False,
    "a real X server without a compositor (e.g. Xvfb)",
)
class TestOnX11WithoutCompositor(BaseTestCase):
    """End to end on the real thing: a bare X server paints a translucent
    window's clear pixels black."""

    def test_a_top_level_stays_opaque(self):
        window = QtWidgets.QWidget()
        self.addCleanup(window.deleteLater)
        self.assertFalse(Bootstrap.set_translucent(window))
        self.assertFalse(window.testAttribute(QtCore.Qt.WA_TranslucentBackground))

    def test_a_full_screen_overlay_gets_the_desktop_to_paint(self):
        window = QtWidgets.QWidget()
        self.addCleanup(window.deleteLater)
        backdrop = Bootstrap.screen_backdrop(window)
        self.assertIsNotNone(backdrop)
        self.assertFalse(backdrop.isNull())


def _run_child(
    code, env=None, creationflags=0, startupinfo=None, timeout=120, python=None
):
    """Run *code* in a fresh interpreter importing this tree's packages.

    The process-level helpers below change the process they run in (its
    console, its output streams, its taskbar identity), so they are exercised
    in a child, never in the test runner.
    """
    import subprocess

    child_env = dict(os.environ, **(env or {}))
    child_env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    child_env["QT_QPA_PLATFORM"] = "offscreen"
    return subprocess.run(
        [python or sys.executable, "-c", code],
        capture_output=startupinfo is None,
        text=True,
        env=child_env,
        timeout=timeout,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )


class _TempDirCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        import shutil

        here = os.path.dirname(os.path.abspath(__file__))
        self.dir = os.path.join(here, "temp_tests", f"bootstrap {os.getpid()}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)


class TestCaptureOutput(_TempDirCase):
    """Under ``pythonw`` (a gui-script, a desktop shortcut) ``sys.stdout`` and
    ``sys.stderr`` are None and every traceback vanishes; ``capture_output``
    gives them a log. Measured before it existed: pythontk's LoggingMixin
    handlers had captured ``stream=None`` and stayed silent for good."""

    def test_a_streamless_process_writes_everything_to_the_log(self):
        log = os.path.join(self.dir, "app.log")
        with open(log, "w", encoding="utf-8") as handle:
            handle.write("the previous run\n")
        code = "\n".join(
            [
                "import os, sys",
                "sys.stdout = sys.stderr = None  # what pythonw hands a process",
                "from uitk._bootstrap import Bootstrap",
                "log = os.environ['LOG_UNDER_TEST']",
                "assert Bootstrap.capture_output(log) == log",
                "print('a printed line')",
                "import pythontk as ptk",
                "class Reporter(ptk.LoggingMixin):",
                "    pass",
                "Reporter().logger.error('a logged line')",
                "raise RuntimeError('an uncaught Caf\\u00e9 \\u2605 error')",
            ]
        )
        result = _run_child(code, env={"LOG_UNDER_TEST": log})
        self.assertNotEqual(result.returncode, 0)  # the raise still fails the run
        with open(log, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("a printed line", text)
        self.assertIn("a logged line", text)
        self.assertIn("RuntimeError: an uncaught Caf\u00e9 \u2605 error", text)
        with open(log + ".1", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "the previous run\n")

    def test_an_unwritable_log_leaves_the_program_running(self):
        """Its folder cannot be made (a file is in the way): no log, no crash
        -- under pythonw a crash here would end the program unseen."""
        blocker = os.path.join(self.dir, "a file")
        open(blocker, "w").close()
        code = "\n".join(
            [
                "import os, sys",
                "sys.stdout = sys.stderr = None",
                "from uitk._bootstrap import Bootstrap",
                "log = os.path.join(os.environ['BLOCKER'], 'sub', 'app.log')",
                "assert Bootstrap.capture_output(log) is None",
                "assert sys.stdout is None and sys.stderr is None",
                "open(os.environ['BLOCKER'] + '.ran', 'w').close()",
            ]
        )
        result = _run_child(code, env={"BLOCKER": blocker})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.exists(blocker + ".ran"))

    def test_live_streams_are_left_alone(self):
        stdout, stderr = sys.stdout, sys.stderr
        log = os.path.join(self.dir, "unused.log")
        self.assertIsNone(Bootstrap.capture_output(log))
        self.assertIs(sys.stdout, stdout)
        self.assertIs(sys.stderr, stderr)
        self.assertFalse(os.path.exists(log))


@unittest.skipUnless(sys.platform == "win32", "a console window is a Windows thing")
class TestDetachConsole(_TempDirCase):
    """A desktop shortcut into a console Python (``mayapy``, Blender's
    ``python.exe``) opens a console beside the GUI; the process closes it when
    the console is its alone, and never a console a terminal shares."""

    def _in_own_console(self, code):
        """Run *code* in a child with a console of its own (hidden, so no
        window flashes); return what it wrote to the result file."""
        import json
        import subprocess

        result_file = os.path.join(self.dir, "result.json")
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0  # SW_HIDE
        # The real interpreter, not a venv's python.exe: that is a redirector
        # running the base python.exe as a second client of its console, so
        # neither process owns it alone (a shortcut into a venv targets its
        # pythonw.exe, which opens no console at all).
        _run_child(
            code,
            env={"RESULT_UNDER_TEST": result_file},
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            startupinfo=info,
            python=getattr(sys, "_base_executable", None) or sys.executable,
        )
        with open(result_file, encoding="utf-8") as handle:
            return json.load(handle)

    def test_a_console_of_its_own_is_closed(self):
        detached, console_left = self._in_own_console(
            "\n".join(
                [
                    "import ctypes, json, os",
                    "from uitk._bootstrap import Bootstrap",
                    "detached = Bootstrap.detach_console()",
                    "left = bool(ctypes.windll.kernel32.GetConsoleWindow())",
                    "with open(os.environ['RESULT_UNDER_TEST'], 'w') as f:",
                    "    json.dump([detached, left], f)",
                ]
            )
        )
        self.assertTrue(detached)
        self.assertFalse(console_left)

    def test_a_shared_console_is_left_alone(self):
        """A second process on the console stands in for the terminal."""
        detached, console_left = self._in_own_console(
            "\n".join(
                [
                    "import ctypes, json, os, subprocess, sys, time",
                    "peer = subprocess.Popen([sys.executable, '-c', "
                    "'import time; time.sleep(60)'])",
                    "time.sleep(1)",
                    "from uitk._bootstrap import Bootstrap",
                    "detached = Bootstrap.detach_console()",
                    "left = bool(ctypes.windll.kernel32.GetConsoleWindow())",
                    "peer.kill()",
                    "with open(os.environ['RESULT_UNDER_TEST'], 'w') as f:",
                    "    json.dump([detached, left], f)",
                ]
            )
        )
        self.assertFalse(detached)
        self.assertTrue(console_left)


class TestDetachConsoleOffWindows(BaseTestCase):
    def test_off_windows_there_is_nothing_to_detach(self):
        with patch.object(sys, "platform", "linux"):
            self.assertFalse(Bootstrap.detach_console())


class TestReportUncaught(BaseTestCase):
    """Started from the desktop, a traceback lands in a log nobody reads; the
    hook shows it, once per distinct error, after the previous hook ran."""

    def setUp(self):
        super().setUp()
        saved = sys.excepthook
        self.addCleanup(setattr, sys, "excepthook", saved)
        self.previous = []
        sys.excepthook = lambda *exc: self.previous.append(exc[1])
        self.shown = []

        def show(box):
            self.shown.append((box.windowTitle(), box.text(), box.informativeText()))
            return 0

        patcher = patch.object(QtWidgets.QMessageBox, "exec_", new=show)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_each_distinct_error_is_shown_once(self):
        Bootstrap.report_uncaught("My Tools", log_file="C:/logs/tools.log")
        boom, key = ValueError("boom"), KeyError("k")
        for exc in (boom, boom, key):
            sys.excepthook(type(exc), exc, None)
        self.assertEqual(self.previous, [boom, boom, key])  # always written
        self.assertEqual(
            [text for _title, text, _info in self.shown],
            ["ValueError: boom", "KeyError: 'k'"],
        )
        title, _text, info = self.shown[0]
        self.assertEqual(title, "My Tools")
        self.assertIn("C:/logs/tools.log", info)

    def test_installing_twice_keeps_one_hook(self):
        Bootstrap.report_uncaught("My Tools")
        Bootstrap.report_uncaught("My Tools")
        error = ValueError("once")
        sys.excepthook(ValueError, error, None)
        self.assertEqual(self.previous, [error])
        self.assertEqual(len(self.shown), 1)

    def test_a_worker_threads_error_shows_no_box(self):
        import threading

        Bootstrap.report_uncaught("My Tools")
        error = ValueError("off the GUI thread")
        worker = threading.Thread(
            target=lambda: sys.excepthook(ValueError, error, None)
        )
        worker.start()
        worker.join()
        self.assertEqual(self.previous, [error])
        self.assertEqual(self.shown, [])


class TestSetAppId(BaseTestCase):
    @unittest.skipUnless(sys.platform == "win32", "an AppUserModelID is Windows'")
    def test_the_process_takes_the_id(self):
        code = "\n".join(
            [
                "import ctypes",
                "from uitk._bootstrap import Bootstrap",
                "ok = Bootstrap.set_app_id('m3trik.uitk.test')",
                "out = ctypes.c_wchar_p()",
                "ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID("
                "ctypes.byref(out))",
                "print(ok, out.value)",
            ]
        )
        result = _run_child(code)
        self.assertEqual(result.stdout.strip(), "True m3trik.uitk.test", result.stderr)

    def test_off_windows_there_is_no_id(self):
        with patch.object(sys, "platform", "linux"):
            self.assertFalse(Bootstrap.set_app_id("m3trik.uitk.test"))


if __name__ == "__main__":
    unittest.main()
