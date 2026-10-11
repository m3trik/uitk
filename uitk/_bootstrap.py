# !/usr/bin/python
# coding=utf-8
"""Standalone-process bootstrap helpers.

These run *before* ``QApplication`` is constructed, so this module must
stay self-contained — importing ``uitk._bootstrap`` should not pull in
``Switchboard`` (which constructs a ``QApplication`` at class-body time)
or any widget module.
"""

import os
import sys
from typing import Callable, Union

from qtpy import QtCore, QtGui, QtWidgets

from uitk._window_blur import _WindowBlur


class Bootstrap:
    """Standalone-process bootstrap helpers (pre-``QApplication`` setup, and
    the console / output / error / taskbar setup of a program started from the
    desktop), and the window-system capabilities uitk's widgets branch on.

    Class-only surface so callers use ``Bootstrap.configure_high_dpi()``;
    the module stays Switchboard-free (see the module docstring).
    """

    @staticmethod
    def configure_platform() -> bool:
        """Run a standalone process's Qt on X11 when a Wayland session offers it.

        uitk's popups, marking menu and flyouts are placed at the cursor and
        dragged by the client; native Wayland allows neither (the compositor
        places top-levels and hides the global pointer). Maya is an X11 app
        for the same reason. So on a Wayland session with XWayland running
        (``DISPLAY`` set), ``QT_QPA_PLATFORM`` becomes ``xcb;wayland`` -- X11
        first, native Wayland if the xcb plug-in cannot load (Qt 6 tries the
        list in order). An explicit ``QT_QPA_PLATFORM`` always wins, and
        nothing changes once a ``QApplication`` exists (a DCC host's own).

        Returns:
            ``True`` when it set the platform, else ``False``.
        """
        if QtWidgets.QApplication.instance() is not None:
            return False
        if not sys.platform.startswith("linux") or os.environ.get("QT_QPA_PLATFORM"):
            return False
        if not (os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY")):
            return False
        os.environ["QT_QPA_PLATFORM"] = "xcb;wayland"
        return True

    @staticmethod
    def positions_windows() -> bool:
        """Whether this process may place its own top-level windows and read
        the global pointer -- False on native Wayland, where the compositor
        places top-levels, ignores ``move()`` and reports no cursor position."""
        return not QtGui.QGuiApplication.platformName().startswith("wayland")

    @staticmethod
    def composites() -> bool:
        """Whether a translucent top-level actually shows what is behind it.

        False on X11 without a compositing manager (bare window managers,
        VNC/XRDP, Xvfb): alpha is dropped and a translucent window paints
        black. Every other window system composites.
        """
        if QtGui.QGuiApplication.platformName() != "xcb":
            return True
        import pythontk as ptk

        return ptk.X11.has_compositor() is not False

    @staticmethod
    def set_translucent(widget, on: bool = True) -> bool:
        """``WA_TranslucentBackground`` on a TOP-LEVEL window, where it shows.

        Without a compositor (see :meth:`composites`) a translucent window's
        clear pixels paint black; the window is left opaque there instead --
        square corners on its own background. (A child widget's translucency
        is drawn within its parent and needs none of this.)

        Returns:
            Whether the window is now translucent.
        """
        on = bool(on) and Bootstrap.composites()
        widget.setAttribute(QtCore.Qt.WA_TranslucentBackground, on)
        return on

    @staticmethod
    def blurs() -> bool:
        """Whether :meth:`set_blur` can blur what shows through a translucent
        window here: Windows 10+, KDE Plasma on X11 while its blur effect is
        on, and macOS. Elsewhere (native Wayland, other X11 window managers)
        it is a no-op."""
        return _WindowBlur.available()

    @staticmethod
    def set_blur(
        widget: QtWidgets.QWidget,
        on: Union[bool, Callable[[QtWidgets.QWidget], bool]] = True,
    ) -> bool:
        """Blur the desktop seen through a translucent TOP-LEVEL window.

        The window's own pixels composite over the blurred backdrop, so a
        translucent background color becomes a frosted tint. Shows only
        where the window is translucent (see :meth:`set_translucent`); an
        opaque window covers its blur. Declarative, like the attribute it
        complements: set once, it survives hide/show and the native-window
        recreation a ``setWindowFlags`` causes (re-applied on each show),
        and it waits for a window not yet created.

        Parameters:
            widget: The window (a child widget is never touched).
            on: True/False, or a ``(widget) -> bool`` resolver read at every
                show -- for a window whose setting can change while it is
                hidden (a popup following its owner's theme).

        Returns:
            Whether the window is set to blur -- from its first show, if it has
            no native window yet (False where :meth:`blurs` is False).
        """
        return _WindowBlur.set(widget, on)

    @staticmethod
    def screen_backdrop(widget) -> "QtGui.QPixmap | None":
        """What a full-screen overlay should paint behind itself, or None.

        None where translucency composites. Without a compositor, a snapshot of
        the screen *widget* is on: painted as the overlay's background it
        stands in for the desktop the overlay covers (else black). Take it
        before the overlay maps -- in its ``showEvent`` -- or it captures
        itself.
        """
        if Bootstrap.composites():
            return None
        screen = widget.screen() or QtGui.QGuiApplication.primaryScreen()
        return screen.grabWindow(0) if screen is not None else None

    @staticmethod
    def fades_windows() -> bool:
        """Whether ``setWindowOpacity`` shows: not on native Wayland (no
        protocol for it) nor on X11 without a compositor."""
        return Bootstrap.positions_windows() and Bootstrap.composites()

    @staticmethod
    def configure_high_dpi() -> bool:
        """Configure Qt high-DPI scaling for a standalone process.

        No-ops when a ``QApplication`` already exists (i.e. when running
        inside a DCC host like Maya, Blender, or Unity — those hosts pick
        their own policy on the QApplication they own, and overriding it
        post-construction is both ineffective and noisy).

        Sets, when the symbols exist on the current Qt binding:

        * ``Qt.AA_EnableHighDpiScaling`` — Qt 5.6-5.13 opt-in; default and
          deprecated on Qt 5.14+ / Qt 6.
        * ``Qt.AA_UseHighDpiPixmaps`` — Qt 5 only; pixmaps are always
          high-DPI on Qt 6.
        * ``Qt.HighDpiScaleFactorRoundingPolicy.PassThrough`` — Qt 5.14+
          and Qt 6. Disables rounding of fractional OS scale factors
          (1.25x, 1.5x, 1.75x are common on Windows), preserving the
          user's chosen scale rather than snapping to the nearest integer.

        Returns:
            ``True`` if the helper applied settings, ``False`` if it
            no-opped because a ``QApplication`` was already present.
        """
        if QtWidgets.QApplication.instance() is not None:
            return False

        # Legacy opt-in attributes are only meaningful on Qt 5 — on Qt 6
        # high-DPI is always on and the same enum values are present but
        # deprecated (setting them emits a DeprecationWarning for no gain).
        if QtCore.qVersion().startswith("5."):
            for attr in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
                flag = getattr(QtCore.Qt, attr, None)
                if flag is not None:
                    QtCore.QCoreApplication.setAttribute(flag, True)

        policy_enum = getattr(QtCore.Qt, "HighDpiScaleFactorRoundingPolicy", None)
        set_policy = getattr(
            QtWidgets.QApplication, "setHighDpiScaleFactorRoundingPolicy", None
        )
        if policy_enum is not None and set_policy is not None:
            set_policy(policy_enum.PassThrough)

        return True

    # ── A standalone process started from the desktop ────────────────────

    @staticmethod
    def detach_console() -> bool:
        """Close the console a desktop shortcut opened beside this GUI process.

        A shortcut to a console interpreter opens a console window with the
        program. DCC Pythons have no windowless twin (``mayapy``, Blender's
        ``python.exe``; see ``ptk.AppLauncher.windowless_python``), so a
        shortcut into one does exactly that. When this process is its
        console's only client -- nothing started it from a terminal -- it
        detaches (``FreeConsole``) and the console closes: the process then
        runs as it would under ``pythonw``. A console shared with a terminal is
        left alone. Pass the result to :meth:`capture_output`, whose streams
        would otherwise write into the closed console.

        Returns:
            ``True`` when it detached (Windows only).
        """
        if sys.platform != "win32":
            return False
        import ctypes

        kernel32 = ctypes.windll.kernel32
        console = ctypes.WINFUNCTYPE(ctypes.c_void_p)(("GetConsoleWindow", kernel32))
        if not console():
            return False
        clients = (ctypes.c_uint32 * 2)()
        if kernel32.GetConsoleProcessList(clients, 2) != 1:
            return False  # a terminal (or a launcher) shares it: not ours
        return bool(kernel32.FreeConsole())

    @staticmethod
    def capture_output(log_file: str, force: bool = False) -> "str | None":
        """Send this process's output to *log_file* when nothing would show it.

        Under ``pythonw`` (a pip gui-script, a shortcut to ``pythonw.exe``)
        ``sys.stdout`` and ``sys.stderr`` are ``None``, so every traceback, log
        record and warning vanishes; a process that just detached from its
        console (*force*, from :meth:`detach_console`) writes to handles that
        lead nowhere. Here they go to *log_file* instead: UTF-8,
        line-buffered, the previous run's log kept as ``<log_file>.1``, with a
        native fault (a Qt access violation) dumped there too
        (``faulthandler``). A process with live streams (a console, a pipe, a
        Linux session journal) is left alone unless *force* is set.

        Call it before anything builds a logger: pythontk's ``LoggingMixin``
        handlers capture ``sys.stderr`` when they are created, so one built
        while it was ``None`` stays silent for good. Loggers come with a
        Switchboard or a handler, not with ``import uitk``.

        Parameters:
            log_file: The log's path; its folder is created.
            force: Redirect even though the streams exist.

        Returns:
            *log_file* when output now goes there, else ``None`` -- also when the
            log cannot be written (an unwritable folder): the program runs on
            without one rather than dying before its first window.
        """
        if not force and sys.stdout is not None and sys.stderr is not None:
            return None
        mode = "w"
        if os.path.exists(log_file):
            try:
                os.replace(log_file, log_file + ".1")
            except OSError:
                mode = "a"  # another instance holds it open (Windows): share it
        try:
            os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
            stream = open(
                log_file, mode, encoding="utf-8", errors="backslashreplace", buffering=1
            )
        except OSError:
            if force:  # the detached console's handles lead nowhere: drop them
                sys.stdout = sys.stderr = None
            return None
        sys.stdout = sys.stderr = stream
        import faulthandler

        faulthandler.enable(stream)
        return log_file

    @staticmethod
    def report_uncaught(title: str, log_file: "str | None" = None) -> None:
        """Show an uncaught error in a message box, not only in a log.

        Started from the desktop, a GUI process's traceback lands in a log
        (:meth:`capture_output`) or the session journal, where nobody looks:
        to its user the click simply did nothing. This installs a
        ``sys.excepthook`` that still runs the previous one (so the traceback
        is written as before), then shows the error once per distinct error,
        never a second box while one is open, and only on the GUI thread of a
        running ``QApplication``. Installing it twice keeps one.

        Parameters:
            title: The message box's title (the application's name).
            log_file: Named in the box as where the full log is.
        """
        previous = sys.excepthook
        if getattr(previous, "_uitk_reports_uncaught", False):
            return
        shown, state = set(), {"open": False}

        def hook(exc_type, value, tb):
            previous(exc_type, value, tb)
            import threading
            import traceback

            app = QtWidgets.QApplication.instance()
            key = (exc_type, str(value))
            if (
                app is None
                or state["open"]
                or key in shown
                or threading.current_thread() is not threading.main_thread()
            ):
                return
            shown.add(key)
            box = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Critical,
                title,
                f"{exc_type.__name__}: {value}",
            )
            if log_file:
                box.setInformativeText(f"The full log is in:\n{log_file}")
            box.setDetailedText(
                "".join(traceback.format_exception(exc_type, value, tb))
            )
            state["open"] = True
            try:
                box.exec_()
            finally:
                state["open"] = False

        hook._uitk_reports_uncaught = True
        sys.excepthook = hook

    @staticmethod
    def set_app_id(app_id: str) -> bool:
        """Give this process its own identity on the Windows taskbar.

        A Python program's windows otherwise belong to the interpreter: the
        taskbar shows its icon, groups them with every other Python program,
        and pinning one pins the bare interpreter. With an explicit
        AppUserModelID they show the application's window icon
        (``QApplication.setWindowIcon``), and a shortcut stamped with the same
        id (``ptk.AppLauncher.create_shortcut(app_id=...)``) is what the
        taskbar pins and relaunches. Call it before the first window shows.

        Parameters:
            app_id: A dotted id, ``Company.Product[.SubProduct]``.

        Returns:
            ``True`` when set (Windows only).
        """
        if sys.platform != "win32":
            return False
        import ctypes

        try:
            set_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        except AttributeError:
            return False
        return set_id(ctypes.c_wchar_p(app_id)) == 0
