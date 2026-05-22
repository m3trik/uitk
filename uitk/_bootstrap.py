# !/usr/bin/python
# coding=utf-8
"""Standalone-process bootstrap helpers.

These run *before* ``QApplication`` is constructed, so this module must
stay self-contained — importing ``uitk._bootstrap`` should not pull in
``Switchboard`` (which constructs a ``QApplication`` at class-body time)
or any widget module.
"""
from qtpy import QtCore, QtWidgets


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
