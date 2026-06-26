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

    Thin wrapper around the Menu class: creates a button that shows a dropdown
    menu when clicked. Pass command rows as ``(label, callback)`` pairs via
    ``menu_items`` -- each becomes a real clickable button wired to its
    callback (see ``_add_menu_item``). Do NOT use ``option.menu.add(label,
    callback)`` for a command row: ``Menu.add`` turns a label string into a
    non-interactive QLabel and stores the callback as inert data, so it never
    fires. ``option.menu.add(<widget>)`` to add a pre-built custom widget is
    fine.

    Example:
        option = OptionMenuOption(menu_items=[
            ("Option 1", lambda: print("Option 1")),
            ("Option 2", lambda: print("Option 2")),
        ])
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

        # The dropdown Menu is built LAZILY (on first access / first show), not
        # here. Creating it eagerly applies the menu's QSS + builds its chrome
        # at wrap time -- a measurable init cost paid by every option-box menu
        # whether or not the user ever opens it (it dominated the preset combo's
        # added init time under a heavy DCC stylesheet). ``_ensure_menu`` /
        # the ``menu`` property create it on demand; nothing the option-box
        # framework does at wrap touches the menu.
        self._menu = None

    def _ensure_menu(self):
        """Create the dropdown Menu on first use and return it.

        Lazily builds the menu (parented to the current wrapped widget) and
        populates any static ``menu_items``. Idempotent -- subsequent calls
        return the existing instance.
        """
        if self._menu is None:
            from uitk.widgets.menu import Menu

            self._menu = Menu.create_dropdown_menu(
                parent=self.wrapped_widget, **self._menu_config
            )
            for item in self._menu_items:
                self._add_menu_item(item)
        return self._menu

    def _add_menu_item(self, item):
        """Add one ``(label, callback)`` entry as a real, clickable menu row.

        ``Menu.add(text)`` maps a non-widget string to a QLabel -- which shows
        no hover feedback and emits no ``clicked`` signal -- and stores any
        second positional arg as inert item-DATA that is never invoked. Passing
        ``(label, callback)`` straight to it therefore yields a dead row (the
        reason option-box context-menu items did not respond to hover or
        clicks). Build an actual button and wire its ``clicked`` to the
        callback so the row both highlights and fires.

        The menu is hidden BEFORE the callback runs so the pop-up releases its
        focus / input grab before the action executes (an action may open a
        dialog or move focus to the wrapped widget for inline editing).

        Parameters:
            item: ``"separator"`` (skipped -- Menu has no separator row yet) or
                a ``(label, callback)`` pair. Other shapes are ignored.

        Returns:
            QtWidgets.QPushButton | None: The created row, or None when the
            entry maps to no clickable row.
        """
        from qtpy import QtWidgets

        if isinstance(item, str):  # e.g. "separator" -- no separator row yet
            return None
        if not (isinstance(item, (tuple, list)) and len(item) >= 2):
            return None

        label, callback = item[0], item[1]
        button = self._menu.add("QPushButton", setText=str(label))

        def _on_clicked(_checked=False, cb=callback):
            self._menu.hide()  # release grab/focus before running the action
            if callable(cb):
                cb()

        button.clicked.connect(_on_clicked)
        return button

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
        # Only reparent if the menu has already been built -- never force lazy
        # creation here (the menu picks up the current wrapped widget as its
        # parent when it is first created). Reparent preserves popup window
        # flags (Qt.Tool | Qt.FramelessWindowHint); a bare setParent(widget)
        # would reset it to a plain child and stop it appearing as a popup.
        if self._menu is not None and widget:
            self._menu.setParent(widget, self._menu.windowFlags())

    def _show_menu(self):
        """Show the menu at the button position."""
        if self._widget:
            menu = self._ensure_menu()
            menu.show_as_popup(anchor_widget=self._widget, position=menu.position)

    @property
    def menu(self):
        """The underlying Menu instance (built on first access).

        Returns:
            Menu: The Menu widget
        """
        return self._ensure_menu()


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
        """Rebuild the menu from the provider, then show it."""
        if self._menu_provider and self.wrapped_widget:
            # Get dynamic menu items, then (re)build the menu's rows. Building
            # the menu lazily here keeps it off the wrap-time init path.
            menu_items = self._menu_provider(self.wrapped_widget)
            menu = self._ensure_menu()
            menu.clear()
            # Add dynamic items as real clickable rows (see _add_menu_item).
            for item in menu_items:
                self._add_menu_item(item)

        # Ensure + show via the base (idempotent _ensure_menu).
        super()._show_menu()
