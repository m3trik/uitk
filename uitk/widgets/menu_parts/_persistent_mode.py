# !/usr/bin/python
# coding=utf-8
"""Persistent mode: keep the menu up until the user hides it explicitly.

Suspends every automatic hide (``prevent_hide``, ``hide_on_leave``) and puts a
Hide button in the header; hiding the menu, or that button, restores the
previous behavior.

One part of :class:`~uitk.widgets.menu.Menu`, which inherits it; it holds no
state of its own (``Menu.__init__`` declares every attribute used here) and
is never instantiated alone.
"""

from uitk.widgets.header import Header


class _MenuPersistentModeMixin:
    """Persistent mode: keep the menu up until the user hides it explicitly."""

    # ------------------------------------------------------------------
    # Persistent mode (keep menu visible even when parent hides)
    # ------------------------------------------------------------------

    def enable_persistent_mode(self, hide_button_tooltip: str = "Hide menu") -> None:
        """Keep the menu visible until the user explicitly hides it.

        This temporarily disables all automatic hide behaviour and injects a
        dedicated Hide button into the header. Call :meth:`disable_persistent_mode`
        to restore the original behaviour.

        Args:
            hide_button_tooltip: Tooltip shown on the injected Hide button.
        """
        if self._persistent_mode:
            return

        self.logger.debug("Menu.enable_persistent_mode: Activating persistent mode")

        # Snapshot state so we can restore it later
        self._persistent_state = {
            "prevent_hide": self.prevent_hide,
            "hide_on_leave": self.hide_on_leave,
            "had_header": self.add_header or bool(self.header),
        }

        self._persistent_mode = True

        # Block auto-hiding behaviour while in persistent mode
        self.prevent_hide = True
        self.hide_on_leave = False

        # Ensure the menu has a header to host the hide button. _ensure_chrome
        # builds it into the frame layout for add_header=True menus; the fallback
        # below injects one for headerless (add_header=False) menus.
        self._ensure_chrome()
        if not self.header:
            self.header = Header(config_buttons=["pin"])
            if self.centralWidgetLayout:
                self.centralWidgetLayout.insertWidget(0, self.header)

        self._install_persistent_hide_button(hide_button_tooltip)

    def disable_persistent_mode(self) -> None:
        """Restore default hide behaviour after persistent mode."""
        if not self._persistent_mode:
            return

        self.logger.debug("Menu.disable_persistent_mode: Restoring default behaviour")

        original = getattr(self, "_persistent_state", {}) or {}

        # Restore behaviour flags before removing the hide guard
        self.prevent_hide = original.get("prevent_hide", False)
        self.hide_on_leave = original.get("hide_on_leave", False)

        self._remove_persistent_hide_button()

        # Remove temporary header if we created one
        if not original.get("had_header", True) and self.header:
            if self.centralWidgetLayout:
                self.centralWidgetLayout.removeWidget(self.header)
            self.header.deleteLater()
            self.header = None

        self._persistent_mode = False
        self._persistent_state = {}

    @property
    def is_persistent_mode(self) -> bool:
        """Return True when persistent mode is active."""
        return self._persistent_mode

    def _install_persistent_hide_button(self, tooltip: str) -> None:
        """Ensure a dedicated hide button exists in persistent mode."""
        if not self.header:
            self.logger.warning(
                "Menu._install_persistent_hide_button: Cannot install without a header"
            )
            return

        # Remove any previous custom hide button before creating a new one
        self._remove_persistent_hide_button()

        # "close.svg" matches Header.button_definitions' own "hide" key; there
        # is no hide.svg in the icon set, and a bad name resolves to an empty
        # QIcon with no error anywhere (the button renders glyph-less).
        hide_button = self.header.create_button(
            "close.svg",
            self._on_persistent_hide_clicked,
            button_type="persistent_hide_button",
        )
        hide_button.setObjectName("persistentHideButton")
        hide_button.setToolTip(tooltip)
        hide_button.setProperty("class", "PersistentHideButton")
        hide_button.setAutoDefault(False)
        hide_button.setDefault(False)

        self.header.container_layout.addWidget(hide_button)
        self.header.buttons["persistent_hide_button"] = hide_button
        self.header.container_layout.invalidate()
        self.header.trigger_resize_event()

        self._persistent_hide_button = hide_button

    def _remove_persistent_hide_button(self) -> None:
        """Remove the injected persistent hide button, if any."""
        button = self._persistent_hide_button
        if not button:
            return

        if self.header:
            try:
                self.header.container_layout.removeWidget(button)
            except Exception:
                pass
            self.header.buttons.pop("persistent_hide_button", None)

        button.hide()
        button.deleteLater()
        self._persistent_hide_button = None

    def _on_persistent_hide_clicked(self) -> None:
        """Handle clicks on the injected Hide button."""
        # Restore default behaviour, then hide immediately
        self.disable_persistent_mode()
        self.hide(force=True)
