# !/usr/bin/python
# coding=utf-8
"""Tests for ExternalAppHub: a provider's external apps as a program of their own.

The provider is a real (temporary) source checkout -- a package with a
``__main__`` declaring ``HUB`` and a ``pyproject.toml`` declaring one in-process
app -- so discovery takes the same path a monorepo checkout on PYTHONPATH does.
Process-level setup (console, output streams, taskbar id) is patched out:
:mod:`test_bootstrap` covers it in child processes.
"""

import os
import shutil
import sys
import unittest
from unittest.mock import patch

from conftest import BaseTestCase, setup_qt_application

setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402

import pythontk as ptk  # noqa: E402
from uitk import ExternalAppHub  # noqa: E402
from uitk._bootstrap import Bootstrap  # noqa: E402
from uitk.handlers.external_app_handler import ExternalAppHandler  # noqa: E402

_FILES = {
    "hubpkg/__init__.py": '"""A provider package with a hub."""\n',
    "hubpkg/__main__.py": (
        "from uitk import ExternalAppHub\n"
        "HUB = ExternalAppHub('hubpkg', title='Hub Pkg', app_id='m3trik.hubpkg')\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(HUB.run())\n"
    ),
    "hubpkg/app.py": (
        "from qtpy import QtWidgets\n"
        "class FakeAppUI(QtWidgets.QMainWindow):\n"
        "    pass\n"
    ),
    "pyproject.toml": (
        "[project]\n"
        'name = "hubpkg"\n'
        '[project.entry-points."uitk.external_apps.in_process"]\n'
        'fake_app = "hubpkg.app:FakeAppUI"\n'
    ),
    "nohub/__init__.py": "",
    "nohub/__main__.py": "HUB = object()\n",
    # A ``python -m`` program that runs unguarded, as many do.
    "runpkg/__init__.py": "",
    "runpkg/__main__.py": (
        "import os\n"
        "open(os.path.join(os.path.dirname(__file__), 'ran'), 'w').close()\n"
        "raise SystemExit(2)\n"
    ),
}


class _HubCase(BaseTestCase):
    """A temporary provider checkout on ``sys.path`` for the whole class."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        here = os.path.dirname(os.path.abspath(__file__))
        cls.root = os.path.join(here, "temp_tests", f"hub provider {os.getpid()}")
        for relative, text in _FILES.items():
            path = os.path.join(cls.root, relative)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        sys.path.insert(0, cls.root)
        import hubpkg.__main__

        cls.hub = hubpkg.__main__.HUB
        # Kept apart from the attribute TestRun patches over.
        cls.real_switchboard = staticmethod(ExternalAppHub._switchboard)

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(cls.root)
        packages = ("hubpkg", "nohub", "runpkg")
        for name in [m for m in sys.modules if m.split(".")[0] in packages]:
            del sys.modules[name]
        shutil.rmtree(cls.root, ignore_errors=True)
        super().tearDownClass()

    def switchboard(self):
        """The hub's switchboard, with fake_app registered even where no TOML
        reader can read the checkout (Python < 3.11 without tomli)."""
        sb = self.real_switchboard(self.hub)
        handler = sb.handlers.external_app
        if not handler.is_registered("fake_app"):
            handler.register(
                "fake_app", module="hubpkg.app", entry="FakeAppUI", mode="in_process"
            )
        return sb

    def close_windows(self, *windows):
        for window in windows:
            self.addCleanup(window.deleteLater)
            self.addCleanup(window.hide)


class TestDeclaration(_HubCase):
    def test_a_provider_is_found_by_its_main(self):
        self.assertIs(ExternalAppHub.of("hubpkg"), self.hub)

    def test_no_hub_is_found_where_none_is_declared(self):
        self.assertIsNone(ExternalAppHub.of("nohub"))  # HUB is not a hub
        self.assertIsNone(ExternalAppHub.of("uitk"))  # no __main__
        self.assertIsNone(ExternalAppHub.of("no_such_package_anywhere"))

    def test_a_main_that_names_no_hub_is_never_run(self):
        """A browser asks for a hub on every external app's row menu, inside
        a host too: a provider whose ``__main__`` runs its program at import
        (unguarded, as many do) must not have it started by the lookup."""
        self.assertIsNone(ExternalAppHub.of("runpkg"))
        self.assertFalse(os.path.exists(os.path.join(self.root, "runpkg", "ran")))

    def test_defaults_are_derived_from_the_package(self):
        hub = ExternalAppHub("somepkg")
        self.assertEqual((hub.title, hub.app_id), ("somepkg", "uitk.somepkg"))
        root = str(ptk.UserConfig.user_config_root())
        self.assertEqual(hub.data_dir, os.path.join(root, "somepkg"))
        self.assertEqual(hub.log_file, os.path.join(root, "somepkg", "somepkg.log"))

    def test_the_command_line(self):
        args = self.hub._parse(["fake_app", "--shortcut", "start_menu"])
        self.assertEqual((args.app, args.shortcut), ("fake_app", "start_menu"))
        args = self.hub._parse([])
        self.assertEqual((args.app, args.shortcut), (None, None))


class TestOpen(_HubCase):
    @unittest.skipIf(
        ExternalAppHandler._toml_loader() is None, "no TOML reader for the checkout"
    )
    def test_a_source_checkout_lists_its_apps(self):
        """No installed metadata: the hub reads the provider's pyproject."""
        sb = self.hub._switchboard()
        self.assertTrue(sb.handlers.external_app.is_registered("fake_app"))

    def test_no_argument_opens_the_browser(self):
        browser = self.hub.open(self.switchboard())
        self.close_windows(browser)
        self.assertTrue(browser.isVisible())
        self.assertEqual(browser.windowTitle(), "Hub Pkg")
        self.assertIn("fake_app", list(browser._model._names))
        buttons = {
            w.objectName()
            for w in browser.header.menu.findChildren(QtWidgets.QPushButton)
        }
        self.assertTrue(
            {"btn_hub_shortcut_desktop", "btn_hub_shortcut_start_menu"} <= buttons
        )

    def test_an_app_name_opens_that_app_alone(self):
        window = self.hub.open(self.switchboard(), "fake_app")
        self.close_windows(window)
        self.assertEqual(type(window).__name__, "FakeAppUI")
        self.assertTrue(window.isVisible())


class TestRun(_HubCase):
    """``run`` as a program: open, then quit once nothing shows."""

    def setUp(self):
        super().setUp()
        self.app_ids = []
        for name, value in (
            ("detach_console", False),
            ("capture_output", None),
            ("report_uncaught", None),
        ):
            patcher = patch.object(Bootstrap, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(
            Bootstrap, "set_app_id", side_effect=lambda i: self.app_ids.append(i)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(
            ExternalAppHub, "_switchboard", new=lambda hub: self.switchboard()
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        # A run that never quits fails the test instead of hanging the suite.
        self.guard = QtCore.QTimer()
        self.guard.setSingleShot(True)
        self.guard.timeout.connect(lambda: QtWidgets.QApplication.exit(9))
        self.addCleanup(self.guard.stop)

    def _hide_everything_soon(self):
        def hide():
            for widget in QtWidgets.QApplication.topLevelWidgets():
                if widget.isVisible() and widget.windowType() == QtCore.Qt.Window:
                    widget.hide()

        QtCore.QTimer.singleShot(200, hide)
        self.guard.start(10000)

    def test_one_app_runs_until_it_is_hidden(self):
        self._hide_everything_soon()
        self.assertEqual(self.hub.run(["fake_app"]), 0)
        self.assertEqual(self.app_ids, ["m3trik.hubpkg.fake_app"])

    def test_the_browser_runs_until_it_is_hidden(self):
        self._hide_everything_soon()
        self.assertEqual(self.hub.run([]), 0)
        self.assertEqual(self.app_ids, ["m3trik.hubpkg"])

    def test_an_unknown_app_is_reported_and_fails_the_run(self):
        reported = []
        with patch.object(sys, "excepthook", lambda *exc: reported.append(exc[1])):
            self.assertEqual(self.hub.run(["no_such_app"]), 1)
        self.assertEqual(len(reported), 1)
        self.assertIn("no_such_app", str(reported[0]))

    def test_a_subprocess_app_leaves_nothing_to_run_here(self):
        """Launching it returns its process, not a window: the run ends
        rather than spinning an event loop with nothing on screen."""
        with patch.object(
            ExternalAppHandler, "launch", new=lambda handler, name, **kw: object()
        ):
            self.assertEqual(self.hub.run(["fake_app"]), 0)

    def test_shortcut_writes_one_and_exits(self):
        with patch.object(
            ExternalAppHub, "create_shortcut", autospec=True, return_value="X.lnk"
        ) as create:
            self.assertEqual(self.hub.run(["fake_app", "--shortcut", "desktop"]), 0)
        create.assert_called_once_with(self.hub, "desktop", app="fake_app")

    def test_a_shortcut_to_an_unknown_app_is_refused(self):
        """A typo would otherwise leave a launcher that opens nothing."""
        reported = []
        hook = patch.object(sys, "excepthook", lambda *exc: reported.append(exc[1]))
        with patch.object(ExternalAppHub, "create_shortcut", autospec=True) as create:
            with hook:
                args = ["no_such_app", "--shortcut", "desktop"]
                self.assertEqual(self.hub.run(args), 1)
        create.assert_not_called()
        self.assertEqual(len(reported), 1)
        self.assertIn("no_such_app", str(reported[0]))


class TestCreateShortcut(_HubCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(ExternalAppHub, "_import_problem", return_value=None)
        self.import_problem = patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_apps_launcher_runs_the_package_with_its_name(self):
        with patch.object(
            ptk.AppLauncher, "create_shortcut", return_value="Hub Pkg Fake App.lnk"
        ) as create:
            path = self.hub.create_shortcut("desktop", app="fake_app", python="py.exe")
        self.assertEqual(path, "Hub Pkg Fake App.lnk")
        (name, target, args), kwargs = create.call_args
        # Named after the hub too: "Fake App" alone could replace another
        # program's shortcut.
        self.assertEqual((name, target), ("Hub Pkg Fake App", "py.exe"))
        self.assertEqual(args, ["-m", "hubpkg", "fake_app"])
        self.assertEqual(kwargs["location"], "desktop")
        self.assertEqual(kwargs["app_id"], "m3trik.hubpkg.fake_app")
        self.import_problem.assert_called_once_with("py.exe")

    def test_the_hubs_launcher_runs_the_package_alone(self):
        with patch.object(ptk.AppLauncher, "create_shortcut") as create:
            self.hub.create_shortcut("start_menu", python="py.exe")
        (name, _target, args), kwargs = create.call_args
        self.assertEqual((name, args), ("Hub Pkg", ["-m", "hubpkg"]))
        self.assertEqual(kwargs["app_id"], "m3trik.hubpkg")

    def test_a_package_that_does_not_import_is_refused(self):
        self.import_problem.return_value = "ModuleNotFoundError: No module named 'x'"
        with patch.object(ptk.AppLauncher, "create_shortcut") as create:
            with self.assertRaises(RuntimeError) as raised:
                self.hub.create_shortcut("desktop", python="py.exe")
        create.assert_not_called()
        self.assertIn("No module named 'x'", str(raised.exception))
        self.assertIn("pip", str(raised.exception))

    def test_a_missing_icon_leaves_the_targets_own(self):
        hub = ExternalAppHub("hubpkg", icon=os.path.join(self.root, "missing.svg"))
        self.assertIsNone(hub._shortcut_icon())

    @unittest.skipUnless(sys.platform == "win32", "a .lnk shows an .ico")
    def test_the_icon_is_rendered_to_an_ico_once(self):
        icon = self.hub._shortcut_icon()
        self.assertTrue(icon.endswith(".ico"))
        self.assertTrue(icon.startswith(self.hub.data_dir))
        self.assertEqual(QtGui.QImage(icon).size(), QtCore.QSize(256, 256))
        stamp = os.path.getmtime(icon)
        self.assertEqual(self.hub._shortcut_icon(), icon)
        self.assertEqual(os.path.getmtime(icon), stamp)

    def test_the_browsers_buttons_write_the_hubs_launcher(self):
        browser = self.hub.open(self.switchboard())
        self.close_windows(browser)
        button = browser.header.menu.findChild(
            QtWidgets.QPushButton, "btn_hub_shortcut_desktop"
        )
        with patch.object(
            ExternalAppHub, "create_shortcut", autospec=True, return_value="Hub.lnk"
        ) as create:
            button.click()
        create.assert_called_once_with(self.hub, "desktop")
        self.assertIn("Hub.lnk", browser.footer.statusText())


class TestImportCheck(_HubCase):
    """The check is real: a package only this process's ``sys.path`` holds (as
    a DCC's startup script would put it) does not import from the desktop."""

    def test_a_package_only_on_this_processes_path_does_not_import(self):
        problem = self.hub._import_problem(sys.executable)
        self.assertIsNotNone(problem)
        self.assertIn("hubpkg", problem)


if __name__ == "__main__":
    unittest.main()
