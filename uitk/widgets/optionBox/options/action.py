# !/usr/bin/python
# coding=utf-8
"""Action option for OptionBox - provides customizable action buttons."""

from qtpy import QtWidgets
from ._options import ButtonOption


class ActionOption(ButtonOption):
    """A customizable action button option.

    This option can execute any callable when clicked, or trigger
    objects that have show(), execute(), run(), or trigger() methods.

    Example:
        def my_action():
            print("Action clicked!")

        action_option = ActionOption(callback=my_action, icon="settings", tooltip="Settings")
        option_box = OptionBox(options=[action_option])
        option_box.wrap(my_widget)
    """

    def __init__(
        self,
        wrapped_widget=None,
        callback=None,
        icon="option_box",
        tooltip="Options",
        text=None,
    ):
        """Initialize the action option.

        Args:
            wrapped_widget: The widget this option is attached to
            callback: Function or object to call/trigger when clicked
            icon: Icon name for the button (default: "option_box")
            tooltip: Tooltip text (default: "Options")
            text: Optional text to display instead of icon
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon=icon,
            tooltip=tooltip,
            callback=lambda: self._handle_action(),
        )
        self._action_handler = callback
        self._text = text

    def create_widget(self):
        """Create the action button widget."""
        button = super().create_widget()

        if not button.objectName():
            button.setObjectName("actionButton")

        if self._text:
            button.setText(self._text)

        button.setProperty("class", "ActionButton")
        return button

    def set_action_handler(self, handler):
        """Set or update the action handler.

        Args:
            handler: Callable or object with show/execute/run/trigger method
        """
        self._action_handler = handler

    def _handle_action(self):
        """Handle the action click."""
        h = self._action_handler
        if h is None:
            return

        if callable(h):  # direct callable
            try:
                h()
            except Exception as e:  # pragma: no cover - defensive
                print(f"ActionOption handler error: {e}")
            return

        # Heuristic method lookup order
        for attr in ("show", "execute", "run", "trigger"):
            if hasattr(h, attr) and callable(getattr(h, attr)):
                getattr(h, attr)()
                return

        # Fallback attempt
        try:
            h()
        except Exception:  # pragma: no cover
            print(f"Warning: ActionOption handler {h} not invokable")


class MenuOption(ActionOption):
    """A menu action option specifically for showing menus.

    This is a specialized version of ActionOption designed for
    displaying popup menus.

    Example:
        from uitk.widgets.menu import Menu

        menu = Menu()
        menu.add_item("Item 1", lambda: print("Item 1"))
        menu.add_item("Item 2", lambda: print("Item 2"))

        menu_option = MenuOption(menu=menu)
        option_box = OptionBox(options=[menu_option])
        option_box.wrap(my_widget)
    """

    def __init__(
        self, wrapped_widget=None, menu=None, icon="option_box", tooltip="Show menu"
    ):
        """Initialize the menu option.

        Args:
            wrapped_widget: The widget this option is attached to
            menu: Menu object to show when clicked
            icon: Icon name for the button (default: "option_box")
            tooltip: Tooltip text (default: "Show menu")
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            callback=self._show_menu,
            icon=icon,
            tooltip=tooltip,
        )
        self._menu = menu

    def set_menu(self, menu):
        """Set or update the menu.

        Args:
            menu: Menu object to show
        """
        self._menu = menu

    def set_wrapped_widget(self, widget):
        """Update wrapped widget and reparent menu if needed."""
        super().set_wrapped_widget(widget)
        if self._menu and widget:
            # Reparent menu to wrapped widget for proper anchoring
            self._menu.setParent(widget)

    def _show_menu(self):
        """Show the menu at the button position."""
        if not self._menu:
            return

        # Use wrapped widget as anchor if available, otherwise use button
        anchor = self.wrapped_widget if self.wrapped_widget else self._widget
        position = getattr(self._menu, "position", "bottom")

        self._menu.show_as_popup(anchor_widget=anchor, position=position)
