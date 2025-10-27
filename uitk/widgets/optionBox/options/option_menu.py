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

    This option creates a button that, when clicked, shows a dropdown
    menu with customizable items. Uses the custom Menu class to leverage
    all existing functionality including hide_on_leave behavior.

    Example:
        def handler1():
            print("Option 1 selected")

        def handler2():
            print("Option 2 selected")

        menu_items = [
            ("Option 1", handler1),
            ("Option 2", handler2),
            ("separator", None),
            ("Option 3", lambda: print("Option 3"))
        ]

        option = OptionMenuOption(menu_items=menu_items)
        option_box = OptionBox(options=[option])
        option_box.wrap(my_widget)
    """

    def __init__(
        self,
        wrapped_widget=None,
        menu_items=None,
        icon="menu",
        tooltip="Show options",
        hide_on_leave=True,
        position="bottom",
        match_parent_width=False,
        min_item_height=None,
        max_item_height=None,
        fixed_item_height=None,
        add_header=True,
        add_apply_button=True,
    ):
        """Initialize the option menu.

        Args:
            wrapped_widget: The widget this option is attached to
            menu_items: List of (label, callback) tuples or "separator"
            icon: Icon name for the button (default: "menu")
            tooltip: Tooltip text (default: "Show options")
            hide_on_leave: Whether menu auto-hides when mouse leaves (default: True)
            position: Menu position relative to button (default: "bottom")
            match_parent_width: Whether menu matches parent width (default: False).
                Set to True if you want dropdown-style menus that match widget width.
            min_item_height: Minimum item height in pixels (default: None)
            max_item_height: Maximum item height in pixels (default: None)
            fixed_item_height: Fixed item height in pixels (default: None)
            add_header: Whether to add a draggable header (default: True)
            add_apply_button: Whether to add an apply button (default: True)
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon=icon,
            tooltip=tooltip,
            callback=self._show_menu,
        )
        self._menu_items = menu_items or []
        self._menu = None

        # Store default values for menu attributes (used before menu is created)
        self._hide_on_leave_default = hide_on_leave
        self._position_default = position
        self._match_parent_width_default = match_parent_width
        self._min_item_height_default = min_item_height
        self._max_item_height_default = max_item_height
        self._fixed_item_height_default = fixed_item_height
        self._add_header_default = add_header
        self._add_apply_button_default = add_apply_button

    def create_widget(self):
        """Create the menu button widget."""
        button = super().create_widget()

        if not button.objectName():
            button.setObjectName("optionMenuButton")

        button.setProperty("class", "OptionMenuButton")
        return button

    def setup_widget(self):
        """Setup the widget after creation.

        Note: We don't create the menu here because wrapped_widget may not be
        set yet. Menu creation is deferred to first show.
        """
        super().setup_widget()

    def _create_menu(self):
        """Create the custom Menu with items.

        This is called lazily on first show to ensure wrapped_widget is available.
        """
        from uitk.widgets.menu import Menu

        # Use wrapped_widget as parent if available (the actual LineEdit/etc),
        # otherwise fall back to the option button widget.
        # This is important for match_parent_width to work correctly - we want
        # the menu to match the width of the wrapped widget, not the tiny option button.
        menu_parent = self.wrapped_widget if self.wrapped_widget else self._widget

        # Use factory method for dropdown menus with stored defaults
        self._menu = Menu.create_dropdown_menu(
            parent=menu_parent,
            position=self._position_default,
            min_item_height=self._min_item_height_default,
            max_item_height=self._max_item_height_default,
            fixed_item_height=self._fixed_item_height_default,
            add_header=self._add_header_default,
            add_apply_button=self._add_apply_button_default,
            hide_on_leave=self._hide_on_leave_default,
            match_parent_width=self._match_parent_width_default,
        )

        # Add menu items
        for item in self._menu_items:
            if isinstance(item, str) and item.lower() == "separator":
                self._menu.addSeparator()
            elif isinstance(item, (tuple, list)) and len(item) >= 2:
                label, callback = item[0], item[1]
                self._menu.add(label, callback)
            else:
                print(f"Warning: Invalid menu item format: {item}")

    def _show_menu(self):
        """Show the menu at the button position."""
        # Create menu lazily on first show - this ensures wrapped_widget is set
        if not self._menu:
            self._create_menu()

        if self._menu and self._widget:
            # Use wrapped_widget as anchor if available (for proper width matching),
            # otherwise use the button widget. This ensures match_parent_width
            # matches the actual widget being wrapped, not the tiny option button.
            anchor = self.wrapped_widget if self.wrapped_widget else self._widget
            self._menu.show_as_popup(anchor_widget=anchor, position=self._menu.position)

    def add_menu_item(self, label, callback=None):
        """Add a new item to the menu.

        Args:
            label: The text label for the menu item
            callback: Function to call when item is clicked
        """
        self._menu_items.append((label, callback))
        # Update menu if it's already been created
        if self._menu:
            self._menu.add(label, callback)

    def add_separator(self):
        """Add a separator to the menu."""
        self._menu_items.append("separator")
        # Update menu if it's already been created
        if self._menu:
            self._menu.addSeparator()

    def clear_menu(self):
        """Clear all menu items."""
        self._menu_items.clear()
        # Update menu if it's already been created
        if self._menu:
            self._menu.clear()

    # Menu attribute pass-through properties
    @property
    def hide_on_leave(self):
        """Get whether menu auto-hides when mouse leaves.

        Returns:
            bool: True if menu auto-hides on leave, False otherwise
        """
        if self._menu:
            return self._menu.hide_on_leave
        return self._hide_on_leave_default

    @hide_on_leave.setter
    def hide_on_leave(self, value):
        """Set whether menu auto-hides when mouse leaves.

        This can be set at any time - before or after menu creation.

        Args:
            value: True to enable auto-hide on leave, False to disable
        """
        self._hide_on_leave_default = bool(value)
        if self._menu:
            self._menu.hide_on_leave = bool(value)

    @property
    def position(self):
        """Get the menu position relative to the button.

        Returns:
            str: Position string ("bottom", "top", "left", "right", "cursorPos")
        """
        if self._menu:
            return self._menu.position
        return self._position_default

    # Simplified property delegation - other menu properties can be accessed directly
    # via the menu property or by setting attributes before menu creation
    def __getattr__(self, name):
        """Delegate unknown attributes to the underlying menu if it exists.

        This allows direct access to menu properties without explicit pass-through.
        For example: option.position = 'bottom' works even if menu exists.
        """
        # Only delegate to menu if it exists, otherwise raise AttributeError
        # to allow normal Python attribute behavior (setting new attributes)
        if name.startswith("_"):
            # Don't intercept private attributes
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

        if self._menu is not None and hasattr(self._menu, name):
            return getattr(self._menu, name)

        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    def __setattr__(self, name, value):
        """Set attributes, forwarding menu properties to underlying menu if it exists."""
        # These are our own attributes - set them directly
        if name in (
            "_menu",
            "_menu_items",
            "_widget",
            "wrapped_widget",
            "icon",
            "tooltip",
            "callback",
            "_hide_on_leave_default",
            "_position_default",
            "_match_parent_width_default",
            "_min_item_height_default",
            "_max_item_height_default",
            "_fixed_item_height_default",
            "_add_header_default",
            "_add_apply_button_default",
        ):
            object.__setattr__(self, name, value)
            return

        # Forward menu properties to the actual menu if it exists
        menu_properties = {
            "position",
            "match_parent_width",
            "min_item_height",
            "max_item_height",
            "fixed_item_height",
            "add_header",
            "add_apply_button",
        }

        if name in menu_properties:
            # Update default for pre-creation configuration
            default_name = f"_{name}_default"
            if hasattr(self, default_name):
                object.__setattr__(self, default_name, value)

            # Forward to menu if it exists
            if hasattr(self, "_menu") and self._menu is not None:
                setattr(self._menu, name, value)
            return

        # For everything else, use normal attribute setting
        object.__setattr__(self, name, value)

    @property
    def menu(self):
        """Get the underlying Menu instance.

        Returns:
            Menu: The Menu widget, or None if not yet created
        """
        return self._menu

    def set_menu_items(self, menu_items):
        """Replace all menu items.

        Args:
            menu_items: List of (label, callback) tuples or "separator"
        """
        self._menu_items = menu_items or []
        # If menu already exists, clear it and repopulate
        # Otherwise items will be added when menu is created on first show
        if self._menu:
            self._menu.clear()
            for item in self._menu_items:
                if isinstance(item, str) and item.lower() == "separator":
                    self._menu.addSeparator()
                elif isinstance(item, (tuple, list)) and len(item) >= 2:
                    label, callback = item[0], item[1]
                    self._menu.add(label, callback)


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
        hide_on_leave=True,
        position="bottom",
        match_parent_width=False,
        min_item_height=None,
        max_item_height=None,
        fixed_item_height=None,
        add_header=True,
        add_apply_button=True,
    ):
        """Initialize the context menu option.

        Args:
            wrapped_widget: The widget this option is attached to
            menu_provider: Function that returns menu_items list based on widget state
            icon: Icon name for the button
            tooltip: Tooltip text
            hide_on_leave: Whether menu auto-hides when mouse leaves (default: True)
            position: Menu position relative to button (default: "bottom")
            match_parent_width: Whether menu matches parent width (default: False).
                Set to True if you want dropdown-style menus that match widget width.
            min_item_height: Minimum item height in pixels (default: None)
            max_item_height: Maximum item height in pixels (default: None)
            fixed_item_height: Fixed item height in pixels (default: None)
            add_header: Whether to add a draggable header (default: True)
            add_apply_button: Whether to add an apply button (default: True)
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            menu_items=[],
            icon=icon,
            tooltip=tooltip,
            hide_on_leave=hide_on_leave,
            position=position,
            match_parent_width=match_parent_width,
            min_item_height=min_item_height,
            max_item_height=max_item_height,
            fixed_item_height=fixed_item_height,
            add_header=add_header,
            add_apply_button=add_apply_button,
        )
        self._menu_provider = menu_provider

    def _show_menu(self):
        """Show the menu with dynamically generated items."""
        if self._menu_provider and self.wrapped_widget:
            # Get dynamic menu items
            menu_items = self._menu_provider(self.wrapped_widget)
            self.set_menu_items(menu_items)

        # Show the menu
        super()._show_menu()

    def set_menu_provider(self, provider):
        """Set the menu provider function.

        Args:
            provider: Function that takes wrapped_widget and returns menu_items list
        """
        self._menu_provider = provider
