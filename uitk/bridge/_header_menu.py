# !/usr/bin/python
# coding=utf-8
"""The header menu of a bridge panel: one part of :class:`~uitk.bridge.slots.BridgeSlotsBase`.

The ``header_init`` Switchboard hook: a "Utilities" separator, the declared
menu items (data, not code), and the rich-text help button.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # annotation only; the facade imports this module
    from uitk.bridge.slots import BridgeSlotsBase


class _HeaderMenu(object):
    """A bridge panel's declarative header menu, its help, and the folder reveal.

    Holds no state of its own, so every method takes the panel, and reads its
    knobs (``HEADER_MENU_TITLE``) and hooks (``header_menu_items``,
    ``help_spec``, ``docs_url``) through it.
    """

    @staticmethod
    def header_init(panel: "BridgeSlotsBase", widget) -> None:
        widget.menu.add("Separator", setTitle=panel.HEADER_MENU_TITLE)
        for label, name, tooltip, handler in panel.header_menu_items():
            widget.menu.add(
                "QPushButton",
                setText=label,
                setObjectName=name,
                setToolTip=tooltip,
            )
            getattr(widget.menu, name).clicked.connect(getattr(panel, handler))

        # The help card ends in the panel's docs link (``docs_url``), the
        # same one the log pane shows at startup.
        spec, url = panel.help_spec(), panel.docs_url()
        if spec or url:
            try:
                from pythontk import TooltipFormat

                text = TooltipFormat.fmt(**spec) if spec else ""
                widget.set_help_text(text, url=url)
            except Exception:  # noqa: BLE001 - help is non-essential chrome
                pass

    @staticmethod
    def reveal_folder(panel: "BridgeSlotsBase", path) -> bool:
        if not path or not os.path.isdir(str(path)):
            panel.bridge.logger.info(f"Folder not found: {path or '(unset)'}")
            return False
        try:
            panel._open_in_file_manager(str(path))
            return True
        except Exception as e:  # noqa: BLE001
            panel.bridge.logger.error(f"Could not open folder: {e}")
            return False
