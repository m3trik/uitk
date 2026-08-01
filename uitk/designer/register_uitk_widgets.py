# !/usr/bin/python
# coding=utf-8
"""Qt Designer entry point — imported by Designer itself, not by uitk.

PySide6's Designer plugin scans every directory listed in
``PYSIDE_DESIGNER_PLUGINS`` for files matching ``register*.py`` and imports each
one it finds. That import *is* the registration hook, so this module runs its
work at import time — the one place in uitk where that is correct.

Add this file's directory to ``PYSIDE_DESIGNER_PLUGINS`` and start Designer, or
just run ``python -m uitk.designer``, which does it for you.
"""

import logging


def _register() -> None:
    """Register uitk's widgets, logging rather than raising on failure.

    An exception escaping here is swallowed by Designer's plugin loader and
    surfaces only as an empty widget box, so the failure is reported explicitly
    instead.
    """
    try:
        from uitk.designer._designer import DesignerPlugin

        DesignerPlugin.register()
    except Exception:  # noqa: BLE001 - a plugin must never take Designer down
        logging.getLogger(__name__).exception(
            "uitk widgets could not be registered with Qt Designer"
        )


_register()
