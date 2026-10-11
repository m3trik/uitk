# !/usr/bin/python
# coding=utf-8
"""A provider's external apps as a program of their own: one app, or all of them.

:class:`ExternalAppHandler` launches external apps inside a host (Maya,
Blender, tentacle). :class:`ExternalAppHub` is that handler with no host. A
provider package declares one in its ``__main__`` and becomes a program::

    # mypkg/__main__.py
    from uitk import ExternalAppHub

    HUB = ExternalAppHub("mypkg", title="My Tools", icon=..., app_id="me.mytools")

    if __name__ == "__main__":
        raise SystemExit(HUB.run())

``python -m mypkg`` opens a browser listing every external app, and
``python -m mypkg compositor`` opens one. A ``[project.gui-scripts]`` entry
(``mypkg = "mypkg.__main__:HUB.run"``) gives it a console-free command, and
:meth:`ExternalAppHub.create_shortcut` a desktop or start-menu launcher. A
host's UI Browser offers the same launcher on each external app's row
(``ExternalAppHandler.create_shortcut``), so someone who only ever opens Maya
can still put an app on the desktop.
"""

import os
import sys
from pathlib import Path
from typing import Optional, Sequence

import pythontk as ptk
from qtpy import QtCore, QtWidgets


class _QuitWhenAllHidden(QtCore.QObject):
    """End the hub once none of its windows shows.

    uitk windows hide rather than close (their header's hide button), and Qt
    quits only when the last window CLOSES, so a hub whose last window was
    hidden would run on with nothing on screen. Watched: the windows handed to
    :meth:`watch` and every window the external-app handler shows or hides.
    The check waits a moment, so a window hidden to change its flags and shown
    again is not mistaken for a closed one.
    """

    _WINDOW_TYPES = (QtCore.Qt.Window, QtCore.Qt.Dialog, QtCore.Qt.Tool)

    def __init__(self, switchboard, delay_ms: int = 300):
        super().__init__(QtWidgets.QApplication.instance())
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._quit_if_nothing_shows)
        self._switchboard = switchboard
        self._windows = []
        switchboard.on_handler_entry_changed.connect(self._schedule)

    def watch(self, window: QtWidgets.QWidget) -> None:
        window.installEventFilter(self)
        self._windows.append(window)

    def disarm(self) -> None:
        """Stop watching for good: the run is over, and a caller's own event
        loop (a test, a host) may follow, which this must never quit."""
        self._timer.stop()
        for window in self._windows:
            try:
                window.removeEventFilter(self)
            except RuntimeError:  # the window's C++ side is already gone
                pass
        self._windows.clear()
        try:
            self._switchboard.on_handler_entry_changed.disconnect(self._schedule)
        except (RuntimeError, TypeError):
            pass
        self.setParent(None)  # freed with the run's last reference

    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.Hide, QtCore.QEvent.Close):
            self._schedule()
        return False

    def _schedule(self, *_args) -> None:
        self._timer.start()

    @classmethod
    def _shows(cls, widget: QtWidgets.QWidget) -> bool:
        return widget.isVisible() and widget.windowType() in cls._WINDOW_TYPES

    def _quit_if_nothing_shows(self) -> None:
        if not any(self._shows(w) for w in QtWidgets.QApplication.topLevelWidgets()):
            QtWidgets.QApplication.quit()


class _ExternalAppHubInternal:
    """Process setup, the window a run opens, and a shortcut's preconditions."""

    #: uitk's own icon, for a hub that declares none.
    _DEFAULT_ICON = str(Path(__file__).resolve().parents[3] / "icons" / "grid.svg")

    def _parse(self, argv: Optional[Sequence[str]]):
        import argparse

        parser = argparse.ArgumentParser(
            prog=f"python -m {self.package}",
            description=f"{self.title}: open one app, or a browser listing them all.",
        )
        parser.add_argument(
            "app", nargs="?", help="An app's name, as the browser lists it."
        )
        parser.add_argument(
            "--shortcut",
            choices=ptk.AppLauncher.SHORTCUT_LOCATIONS,
            help="Write a launcher for the hub (or for APP) there, then exit.",
        )
        return parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    def _app_id(self, app: Optional[str]) -> str:
        """The taskbar identity of the hub, or of one app opened alone (so a
        launcher for it groups and pins apart from the hub's)."""
        return f"{self.app_id}.{app}" if app else self.app_id

    def _switchboard(self):
        """A host-less switchboard whose external-app handler knows this package."""
        from qtpy import QtGui
        from uitk.handlers.external_app_handler import ExternalAppHandler
        from uitk.switchboard import Switchboard

        sb = Switchboard(handlers={"external_app": ExternalAppHandler, "editor": None})
        sb.app.setWindowIcon(QtGui.QIcon(self.icon or self._DEFAULT_ICON))
        handler = sb.handlers.external_app
        # A source checkout on PYTHONPATH has no installed entry points: as a
        # provider, its pyproject.toml is read instead (see discover()).
        handler.add_provider(self.package)
        handler.discover()
        return sb

    def _browser(self, sb):
        """The UI Browser over *sb*'s external apps, with this hub's shortcut
        buttons in its header menu."""
        from uitk.widgets.editors.switchboard_browser._switchboard_browser import (
            SwitchboardBrowser,
        )
        from uitk.widgets.editors.switchboard_browser.launch import SHORTCUT_ACTIONS
        from uitk.widgets.pushButton import PushButton

        browser = SwitchboardBrowser(switchboard=sb)
        browser.setWindowTitle(self.title)
        browser.header.setTitle(self.title)
        menu = browser.header.menu
        menu.add("Separator", setTitle="Launch from the desktop:")
        # The row menu's actions and labels, for the hub itself.
        for location, label in SHORTCUT_ACTIONS:
            button = menu.add(
                PushButton,
                setText=label,
                setObjectName=f"btn_hub_shortcut_{location}",
                setToolTip=f"A launcher that opens {self.title}.",
            )
            button.clicked.connect(
                lambda _=False, b=browser, loc=location: b._write_shortcut(
                    lambda: self.create_shortcut(loc), self.title
                )
            )
        return browser

    def _shortcut_icon(self) -> Optional[str]:
        """The icon file a shortcut can show: on Windows an ``.ico``, rendered
        once into :attr:`data_dir` (again when the source changes)."""
        source = self.icon or self._DEFAULT_ICON
        if not os.path.isfile(source):
            return None  # the target's own icon shows
        if sys.platform != "win32" or source.lower().endswith((".ico", ".exe", ".dll")):
            return source
        target = os.path.join(
            self.data_dir, os.path.splitext(os.path.basename(source))[0] + ".ico"
        )
        if os.path.isfile(target) and os.path.getmtime(target) >= os.path.getmtime(
            source
        ):
            return target
        from qtpy import QtGui

        if QtWidgets.QApplication.instance() is None:
            return None  # nothing to render with: the target's own icon shows
        reader = QtGui.QImageReader(source)
        reader.setScaledSize(QtCore.QSize(256, 256))
        image = reader.read()
        os.makedirs(self.data_dir, exist_ok=True)
        if image.isNull() or not image.save(target, "ICO"):
            return None
        return target

    @staticmethod
    def _desktop_environ() -> Optional[dict]:
        """The environment a shortcut's program starts with, as far as imports go.

        On Windows, this process's own with ``PYTHONPATH`` as the user's saved
        environment has it (a user value wins over the machine's): Explorer
        starts a shortcut with that, while a host's startup may have changed
        the live one. Elsewhere ``None`` (this process's): a desktop session's
        variables cannot be read from here.
        """
        if sys.platform != "win32":
            return None
        import winreg

        env = dict(ptk.AppLauncher.process_environ())
        env.pop("PYTHONPATH", None)
        for root, key in (
            (winreg.HKEY_CURRENT_USER, "Environment"),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            ),
        ):
            try:
                with winreg.OpenKey(root, key) as handle:
                    value = winreg.QueryValueEx(handle, "PYTHONPATH")[0]
            except OSError:
                continue
            if value:
                env["PYTHONPATH"] = os.path.expandvars(str(value))
                break
        return env

    def _import_problem(self, python: str) -> Optional[str]:
        """Why *python* cannot run this hub from the desktop, or None if it can."""
        check = f"import {self.package}.__main__, qtpy.QtWidgets"
        try:
            result = ptk.AppLauncher.run(
                python,
                ["-c", check],
                cwd=os.path.expanduser("~"),
                timeout=180,
                env=self._desktop_environ(),
                hide_window=True,
            )
        except Exception as error:  # noqa: BLE001 -- the reason is the answer
            return str(error)
        if result.returncode == 0:
            return None
        lines = (result.stderr or result.stdout or "").strip().splitlines()
        return lines[-1] if lines else f"exit code {result.returncode}"


class ExternalAppHub(_ExternalAppHubInternal):
    """A provider package's external apps as a standalone program.

    Declared as ``HUB`` in the package's ``__main__`` (see the module
    docstring); everything else is derived.

    Parameters:
        package: The provider's import name: ``python -m <package>`` runs this
            hub. Its browser lists every external app discovered, this
            package's included even from a source checkout.
        title: The window's and the hub shortcut's name; *package* when omitted.
        icon: An image (``.svg`` / ``.png`` / ``.ico``) for its windows and
            shortcuts; uitk's grid icon when omitted.
        app_id: Its Windows taskbar identity (AppUserModelID);
            ``uitk.<package>`` when omitted.
    """

    def __init__(
        self,
        package: str,
        title: Optional[str] = None,
        icon: Optional[str] = None,
        app_id: Optional[str] = None,
    ):
        self.package = package
        self.title = title or package
        self.icon = icon
        self.app_id = app_id or f"uitk.{package}"

    def __repr__(self) -> str:
        return f"ExternalAppHub({self.package!r}, title={self.title!r})"

    @classmethod
    def of(cls, package: str) -> Optional["ExternalAppHub"]:
        """The hub *package* declares as ``HUB`` in its ``__main__``, or None.

        The lookup is the external-app handler's (a host's browser asks it per
        row, below this layer): see ``ExternalAppHandler.hub_for``.
        """
        from uitk.handlers.external_app_handler import ExternalAppHandler

        return ExternalAppHandler._hub_of(package)

    @property
    def data_dir(self) -> str:
        """This hub's per-user folder: its log and rendered icon
        (``<user config root>/<package>``, see ``ptk.UserConfig``)."""
        return str(ptk.UserConfig.user_config_root() / self.package)

    @property
    def log_file(self) -> str:
        """Where a run's output goes when no console shows it."""
        return os.path.join(self.data_dir, f"{self.package}.log")

    def run(self, argv: Optional[Sequence[str]] = None) -> int:
        """Run the hub as this process's program; return its exit code.

        ``[app]`` opens that app alone; no argument opens the browser listing
        them all. ``--shortcut desktop|start_menu`` writes a launcher for the
        hub (or for *app*) and exits. The process quits once none of its
        windows shows.

        Started from the desktop, it sets itself up as a GUI program: it closes
        a console only it owns (``Bootstrap.detach_console``), writes its
        output to :attr:`log_file` when no console would show it, shows an
        uncaught error in a message box, and takes its own taskbar identity and
        icon.

        Parameters:
            argv: The arguments; ``sys.argv[1:]`` when omitted (a gui-script).

        Returns:
            The exit code: 0, or 1 when opening the app or writing the
            launcher failed (the error is shown and logged, not raised).
        """
        from uitk._bootstrap import Bootstrap

        log_file = Bootstrap.capture_output(
            self.log_file, force=Bootstrap.detach_console()
        )
        Bootstrap.report_uncaught(self.title, log_file)
        args = self._parse(argv)
        Bootstrap.set_app_id(self._app_id(args.app))
        Bootstrap.configure_high_dpi()
        sb = self._switchboard()
        try:
            if args.shortcut:
                handler = sb.handlers.external_app
                if args.app and not handler.is_registered(args.app):
                    # A launcher for a mistyped app would open nothing.
                    raise ValueError(handler._unresolvable_message(args.app))
                print(self.create_shortcut(args.shortcut, app=args.app))
                return 0
            window = self.open(sb, args.app)
        except Exception:  # noqa: BLE001 -- shown and logged by the hook
            sys.excepthook(*sys.exc_info())
            return 1
        if not isinstance(window, QtWidgets.QWidget):
            return 0  # a subprocess app: it runs on its own, nothing shows here
        quitter = _QuitWhenAllHidden(sb)
        quitter.watch(window)
        try:
            return sb.app.exec_()
        finally:
            quitter.disarm()

    def open(self, sb, app: Optional[str] = None):
        """Show app *app*, or the browser listing every app, and return it.

        The window :meth:`run` opens, for a caller running its own event loop
        (an app registered to run in a subprocess returns its process).

        Parameters:
            sb: A switchboard with an ``external_app`` handler.
            app: An app's name; the browser when omitted.

        Returns:
            The window shown, or what ``ExternalAppHandler.launch`` returns
            for an app that runs in a subprocess.
        """
        if app:
            return sb.handlers.external_app.launch(app)
        browser = self._browser(sb)
        browser.present()
        return browser

    def create_shortcut(
        self,
        location: str = "desktop",
        app: Optional[str] = None,
        python: Optional[str] = None,
    ) -> str:
        """Put a launcher for this hub, or one of its apps, on the desktop or
        in the start menu.

        The launcher runs ``<python> -m <package> [app]``. *python* defaults
        to this process's interpreter's windowless twin
        (``ptk.AppLauncher.windowless_python``): inside a DCC, the DCC's own
        Python. That interpreter has to import the package from the desktop,
        without the host's startup scripts, so this is tried first: a package
        that only a host's startup put on ``sys.path`` (``userSetup.py``,
        ``Maya.env``) is refused with the import error, and nothing is
        written. Install it into that Python with pip, or put its folder on a
        PYTHONPATH saved in the user's environment.

        Parameters:
            location: ``"desktop"``, ``"start_menu"``, or an existing directory.
            app: An app's name: the launcher opens it alone.
            python: The interpreter the launcher runs.

        Returns:
            The shortcut file's path.

        Raises:
            RuntimeError: No interpreter, or the package does not import in it.
        """
        python = python or ptk.AppLauncher.windowless_python()
        if not python:
            raise RuntimeError(
                f"No Python interpreter pairs with {sys.executable!r} to run "
                f"{self.package} from the desktop."
            )
        problem = self._import_problem(python)
        if problem:
            raise RuntimeError(
                f"{self.package} does not import in {python} outside this "
                f"application ({problem}). A desktop launcher runs that Python on "
                f"its own: install {self.package} into it with pip, or put its "
                f"folder on a PYTHONPATH saved in your user environment."
            )
        # One app's launcher carries the hub's name too: "Converter" alone
        # would replace any other program's shortcut of that name.
        name = f"{self.title} {app.replace('_', ' ').title()}" if app else self.title
        return ptk.AppLauncher.create_shortcut(
            name,
            python,
            ["-m", self.package] + ([app] if app else []),
            location=location,
            icon=self._shortcut_icon(),
            comment=f"Open {name}" if app else f"Open the {self.title} apps",
            app_id=self._app_id(app),
        )
