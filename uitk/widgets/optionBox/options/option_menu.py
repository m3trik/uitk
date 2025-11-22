# !/usr/bin/python
# coding=utf-8
"""Option Menu - A dropdown menu option for OptionBox.

This option uses the custom Menu class to provide a dropdown menu
with all the standard Menu features including hide_on_leave, positioning,
and event handling.
"""

from ._options import ButtonOption
import pythontk as ptk


class OptionMenuOption(ButtonOption, ptk.LoggingMixin):
    """A dropdown menu option that displays a list of choices.

    This is a thin wrapper around the Menu class. Simply creates a button
    that shows a dropdown menu when clicked. All menu configuration and
    item management is delegated to the Menu instance.

    Example:
        option = OptionMenuOption()
        option.menu.add("Option 1", lambda: print("Option 1"))
        option.menu.add("Option 2", lambda: print("Option 2"))

        option_box = OptionBox(options=[option])
        option_box.wrap(my_widget)
    """

    def __init__(
        self,
        wrapped_widget=None,
        menu_items=None,
        icon="menu",
        tooltip="Show options",
        **menu_config,
    ):
        """Initialize the option menu.

        Args:
            wrapped_widget: The widget this option is attached to
            menu_items: List of (label, callback) tuples or "separator" (optional)
            icon: Icon name for the button (default: "menu")
            tooltip: Tooltip text (default: "Show options")
            **menu_config: Any Menu configuration (position, hide_on_leave, etc.)
                Default config for dropdown menus is applied via Menu.create_dropdown_menu()
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon=icon,
            tooltip=tooltip,
            callback=self._show_menu,
        )
        self._menu_items = menu_items or []
        self._menu_config = menu_config

        # Create menu immediately instead of deferring
        from uitk.widgets.menu import Menu

        menu_parent = wrapped_widget if wrapped_widget else None
        self._menu = Menu.create_dropdown_menu(parent=menu_parent, **menu_config)

        # Add initial menu items if provided
        for item in menu_items or []:
            if isinstance(item, str) and item.lower() == "separator":
                # Menu doesn't have addSeparator - skip for now
                pass
            elif isinstance(item, (tuple, list)) and len(item) >= 2:
                label, callback = item[0], item[1]
                self._menu.add(label, callback)

    def create_widget(self):
        """Create the menu button widget."""
        from qtpy import QtWidgets

        button = super().create_widget()

        if not button.objectName():
            button.setObjectName("optionMenuButton")

        button.setProperty("class", "OptionMenuButton")

        # CRITICAL: Ensure no text is rendered (prevents artifacts)
        # Clear text using both native Qt and any overridden setText
        QtWidgets.QPushButton.setText(button, "")
        if hasattr(button, "setText") and button.text():
            button.setText("")

        return button

    def setup_widget(self):
        """Setup the widget after creation."""
        super().setup_widget()

    def set_wrapped_widget(self, widget):
        """Update wrapped widget and reparent menu if needed."""
        super().set_wrapped_widget(widget)
        if self._menu and widget:
            # Reparent menu to wrapped widget for proper anchoring
            self._menu.setParent(widget)

    def _show_menu(self):
        """Show the menu at the button position."""
        if self._menu and self._widget:
            # Use wrapped_widget as anchor if available (for proper width matching)
            anchor = self.wrapped_widget if self.wrapped_widget else self._widget
            self._menu.show_as_popup(anchor_widget=anchor, position=self._menu.position)

    @property
    def menu(self):
        """Get the underlying Menu instance.

        Returns:
            Menu: The Menu widget
        """
        return self._menu


class ContextMenuOption(OptionMenuOption):
    """A context menu option that shows a menu based on wrapped widget state.

    This extends OptionMenuOption to provide dynamic menus that can
    change based on the current state of the wrapped widget.

    Example:
        def get_dynamic_items(widget):
            if widget.text():
                return [
                    ("Copy", lambda: copy_text(widget)),
                    ("Clear", lambda: widget.clear())
                ]
            else:
                return [("Paste", lambda: paste_text(widget))]

        option = ContextMenuOption(menu_provider=get_dynamic_items)
        option_box = OptionBox(options=[option])
        option_box.wrap(my_widget)
    """

    def __init__(
        self,
        wrapped_widget=None,
        menu_provider=None,
        icon="menu",
        tooltip="Context menu",
        **menu_config,
    ):
        """Initialize the context menu option.

        Args:
            wrapped_widget: The widget this option is attached to
            menu_provider: Function that returns menu_items list based on widget state
            icon: Icon name for the button
            tooltip: Tooltip text
            **menu_config: Any Menu configuration (position, hide_on_leave, etc.)
        """
        # Don't pass menu_items to parent - we'll populate dynamically
        super().__init__(
            wrapped_widget=wrapped_widget,
            menu_items=None,
            icon=icon,
            tooltip=tooltip,
            **menu_config,
        )
        self._menu_provider = menu_provider

    def _show_menu(self):
        """Show the menu with dynamically generated items."""
        if self._menu_provider and self.wrapped_widget:
            # Get dynamic menu items
            menu_items = self._menu_provider(self.wrapped_widget)

            # Clear menu
            self._menu.clear()

            # Add dynamic items
            for item in menu_items:
                if isinstance(item, str) and item.lower() == "separator":
                    # Menu doesn't have addSeparator - skip for now
                    pass
                elif isinstance(item, (tuple, list)) and len(item) >= 2:
                    label, callback = item[0], item[1]
                    self._menu.add(label, callback)

        # Show the menu
        if self._menu and self._widget:
            anchor = self.wrapped_widget if self.wrapped_widget else self._widget
            self._menu.show_as_popup(anchor_widget=anchor, position=self._menu.position)
