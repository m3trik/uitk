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

from qtpy import QtCore, QtGui, QtWidgets


class Bootstrap:
    """Standalone-process bootstrap helpers (pre-``QApplication`` setup), and
    the window-system capabilities uitk's widgets branch on.

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
