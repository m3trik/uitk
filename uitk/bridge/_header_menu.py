# !/usr/bin/python
# coding=utf-8
"""The header menu of a bridge panel: one part of :class:`~uitk.bridge.slots.BridgeSlotsBase`.

The ``header_init`` Switchboard hook: a "Utilities" separator, the declared
menu items (data, not code), and the rich-text help button.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple


class _HeaderMenuMixin(object):
    """The declarative header menu, its help, and the folder-reveal action."""

    # ------------------ Header menu (declarative) ---------------------
    # The default :meth:`header_init` builds a "Utilities" separator, the
    # declared menu items, and the rich-text help -- so subclasses set
    # *data*, not code. Each item is
    # ``(label, objectName, tooltip, handler_method_name)``; the handler is
    # resolved on the slot via ``getattr`` and connected to ``clicked``.
    #
    # The default item set is the script-template bridges' menu (marmoset /
    # substance / blender / maya). Bridges with a different menu shape
    # (rizom's UV-editor + scripts, unity's project folder, the
    # photogrammetry panels' cancel/output) override ``HEADER_MENU_ITEMS``;
    # the handlers they name live on the subclass.
    #
    # Template management deliberately does NOT live here: the template combo
    # owns those tasks (it re-scans on panel open, and its context menu --
    # built in ``cmb000_init`` -- carries Refresh / Open Folder), so the
    # header stays for panel-level utilities only.
    HEADER_MENU_TITLE: str = "Utilities"
    HEADER_MENU_ITEMS: Tuple[Tuple[str, str, str, str], ...] = (
        ("Clear Log", "btn_clear_log", "Clear the log panel below.", "clear_log"),
    )
    # ``fmt()`` keyword dict (``title`` / ``body`` / ``steps`` / ``sections`` /
    # ``notes``) for the header help button, or ``None`` for no help.
    # Subclasses set this (or override :meth:`help_spec` to compute it).
    HELP_SPEC: Optional[Dict[str, Any]] = None

    # ------------------ Header menu utilities -------------------------

    def header_menu_items(self) -> Tuple[Tuple[str, str, str, str], ...]:
        """Hook: the header-menu items. Default = :attr:`HEADER_MENU_ITEMS`."""
        return self.HEADER_MENU_ITEMS

    def help_spec(self) -> Optional[Dict[str, Any]]:
        """Hook: the ``fmt()`` keyword dict for the header help, or ``None``.

        Default = :attr:`HELP_SPEC` (static). Override to compute it (e.g. a
        panel whose help depends on runtime state)."""
        return self.HELP_SPEC

    def header_init(self, widget) -> None:
        """Default header menu: a "Utilities" separator, the declared
        :meth:`header_menu_items` (each wired to a handler method on this slot),
        and the rich-text help from :meth:`help_spec`.

        Subclasses customise by setting :attr:`HEADER_MENU_ITEMS` /
        :attr:`HELP_SPEC` (or overriding the two hooks) -- *data, not code*. A
        bridge that needs extra wiring can still override this method wholesale.
        """
        widget.menu.add("Separator", setTitle=self.HEADER_MENU_TITLE)
        for label, name, tooltip, handler in self.header_menu_items():
            widget.menu.add(
                "QPushButton",
                setText=label,
                setObjectName=name,
                setToolTip=tooltip,
            )
            getattr(widget.menu, name).clicked.connect(getattr(self, handler))

        spec = self.help_spec()
        if spec:
            try:
                from pythontk import TooltipFormat

                widget.set_help_text(TooltipFormat.fmt(**spec))
            except Exception:  # noqa: BLE001 - help is non-essential chrome
                pass

    def reveal_folder(self, path) -> bool:
        """Open *path* in the OS file manager (logs + returns False if missing).

        Shared by header-menu "Open … folder" actions so subclasses don't each
        re-implement the existence check + cross-platform reveal + error log.
        """
        if not path or not os.path.isdir(str(path)):
            self.bridge.logger.info(f"Folder not found: {path or '(unset)'}")
            return False
        try:
            self._open_in_file_manager(str(path))
            return True
        except Exception as e:  # noqa: BLE001
            self.bridge.logger.error(f"Could not open folder: {e}")
            return False
