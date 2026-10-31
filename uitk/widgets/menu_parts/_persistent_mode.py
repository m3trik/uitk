# !/usr/bin/python
# coding=utf-8
"""Persistent mode: keep the menu up until the user hides it explicitly.

Suspends every automatic hide (``prevent_hide``, ``hide_on_leave``) and puts a
Hide button in the header; hiding the menu, or that button, restores the
previous behavior.

One part of :class:`~uitk.widgets.menu.Menu` (see ``menu_parts``).
"""

from typing import TYPE_CHECKING, Any, Dict, Optional

from qtpy import QtWidgets

from uitk.widgets.header import Header

if TYPE_CHECKING:
    from uitk.widgets.menu import Menu


class _MenuPersistentMode:
    """A :class:`Menu`'s persistent mode: on or off, what it suspended, its Hide button."""

    def __init__(self, menu: "Menu") -> None:
        self._menu = menu
        self.active = False
        # The hide behavior enable() suspended, restored by disable().
        self.state: Dict[str, Any] = {}
        self.hide_button: Optional[QtWidgets.QPushButton] = None

    def enable(self, hide_button_tooltip: str = "Hide menu") -> None:
        if self.active:
            return
        menu = self._menu

        menu.logger.debug("Menu.enable_persistent_mode: Activating persistent mode")

        # Snapshot state so we can restore it later
        self.state = {
            "prevent_hide": menu.prevent_hide,
            "hide_on_leave": menu.hide_on_leave,
            "had_header": menu.add_header or bool(menu.header),
        }

        self.active = True

        # Block auto-hiding behaviour while in persistent mode
        menu.prevent_hide = True
        menu.hide_on_leave = False

        # Ensure the menu has a header to host the hide button. ensure_chrome
        # builds it into the frame layout for add_header=True menus; the fallback
        # below injects one for headerless (add_header=False) menus.
        menu._ensure_chrome()
        if not menu.header:
            menu.header = Header(config_buttons=["pin"])
            if menu.centralWidgetLayout:
                menu.centralWidgetLayout.insertWidget(0, menu.header)

        self.install_hide_button(hide_button_tooltip)

    def disable(self) -> None:
        if not self.active:
            return
        menu = self._menu

        menu.logger.debug("Menu.disable_persistent_mode: Restoring default behaviour")

        original = self.state or {}

        # Restore behaviour flags before removing the hide guard
        menu.prevent_hide = original.get("prevent_hide", False)
        menu.hide_on_leave = original.get("hide_on_leave", False)

        self.remove_hide_button()

        # Remove temporary header if we created one
        if not original.get("had_header", True) and menu.header:
            if menu.centralWidgetLayout:
                menu.centralWidgetLayout.removeWidget(menu.header)
            menu.header.deleteLater()
            menu.header = None

        self.active = False
        self.state = {}

    def install_hide_button(self, tooltip: str) -> None:
        """Ensure a dedicated hide button exists in persistent mode."""
        menu = self._menu
        header = menu.header
        if not header:
            menu.logger.warning(
                "Menu._install_persistent_hide_button: Cannot install without a header"
            )
            return

        # Remove any previous custom hide button before creating a new one
        self.remove_hide_button()

        # "close.svg" matches Header.button_definitions' own "hide" key; there
        # is no hide.svg in the icon set, and a bad name resolves to an empty
        # QIcon with no error anywhere (the button renders glyph-less). The
        # menu's own slot is the callback, so the button dies with the menu.
        hide_button = header.create_button(
            "close.svg",
            menu._on_persistent_hide_clicked,
            button_type="persistent_hide_button",
        )
        hide_button.setObjectName("persistentHideButton")
        hide_button.setToolTip(tooltip)
        hide_button.setProperty("class", "PersistentHideButton")
        hide_button.setAutoDefault(False)
        hide_button.setDefault(False)

        header.container_layout.addWidget(hide_button)
        header.buttons["persistent_hide_button"] = hide_button
        header.container_layout.invalidate()
        header.trigger_resize_event()

        self.hide_button = hide_button

    def remove_hide_button(self) -> None:
        """Remove the injected persistent hide button, if any."""
        button = self.hide_button
        if not button:
            return
        header = self._menu.header

        if header:
            try:
                header.container_layout.removeWidget(button)
            except Exception:
                pass
            header.buttons.pop("persistent_hide_button", None)

        button.hide()
        button.deleteLater()
        self.hide_button = None

    def on_hide_clicked(self) -> None:
        """Handle clicks on the injected Hide button."""
        menu = self._menu
        # Restore default behaviour, then hide immediately
        menu.disable_persistent_mode()
        menu.hide(force=True)
