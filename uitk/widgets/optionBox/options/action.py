# !/usr/bin/python
# coding=utf-8
"""Action option for OptionBox - provides customizable action buttons."""

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
        states=None,
        order=None,
        settings_key=None,
    ):
        """Initialize the action option.

        Args:
            wrapped_widget: The widget this option is attached to
            callback: Function or object to call/trigger when clicked
            icon: Icon name for the button (default: "option_box")
            tooltip: Tooltip text (default: "Options")
            text: Optional text to display instead of icon
            states: Optional list of state dicts for multi-state cycling.
                Each dict may contain 'icon', 'tooltip', and 'callback' keys.
                When provided, clicking cycles through the states.
                Per-state callbacks override the top-level callback.
            order: Explicit sort position (int). See BaseOption.
            settings_key: Optional explicit key for persistent storage.
                When omitted, the key is auto-derived from the wrapped
                widget's objectName (if available). Pass ``False`` to
                disable persistence entirely.
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon=icon,
            tooltip=tooltip,
            callback=lambda: self._handle_action(),
            order=order,
        )
        self._action_handler = callback
        self._text = text
        self._state_cycle = None
        self._settings_key = settings_key
        self._settings = None
        # Persistence is only meaningful for state-cycling options. set_states()
        # initializes the settings handle and restores the persisted index; a
        # state-less option (plain action button / MenuOption) opens no QSettings.
        if states:
            self.set_states(states)

    def create_widget(self):
        """Create the action button widget."""
        button = super().create_widget()

        if not button.objectName():
            button.setObjectName("actionButton")

        if self._text:
            button.setText(self._text)

        button.setProperty("class", "ActionButton")

        # Attach the state cycle so the current state's visuals appear on
        # first render instead of the constructor defaults.
        if self._state_cycle:
            self._widget = button  # Host bookkeeping expects _widget set
            self._state_cycle.widget = button

        return button

    def set_action_handler(self, handler):
        """Set or update the action handler.

        Args:
            handler: Callable or object with show/execute/run/trigger method
        """
        self._action_handler = handler

    @property
    def current_state(self):
        """The current state index (0-based). Only meaningful when states are set.

        Assign it to sync the button's visuals to externally-owned app
        state — the change is applied (and persisted) but no state
        callback fires.
        """
        return self._state_cycle.current_state if self._state_cycle else 0

    @current_state.setter
    def current_state(self, index):
        if self._state_cycle:
            self._state_cycle.current_state = index

    def set_states(self, states):
        """Set multiple cycling states.

        Args:
            states: list of dicts, each with optional keys: icon, color,
                tooltip, callback (see :class:`IconStates`).
                e.g. [{"icon": "play", "tooltip": "Run", "callback": run_fn},
                      {"icon": "pause", "tooltip": "Pause", "callback": pause_fn},
                      {"icon": "stop",  "tooltip": "Stop",  "callback": stop_fn}]
        """
        from uitk.widgets.mixins.icon_states import IconStates

        self._state_cycle = IconStates(
            states,
            widget=self._widget,
            on_change=lambda _index: self._save_state(),
        )
        # States now exist, so persistence is meaningful — initialize the
        # settings handle lazily here (it is skipped at construction for the
        # no-states case) before restoring the persisted index.
        self._init_settings()
        self._load_state()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _resolve_settings_key(self):
        """Derive the persistence key.

        Priority:
          1. Explicit ``settings_key`` string passed at construction.
          2. Auto-derived from ``wrapped_widget.objectName()``.
          3. ``None`` (no persistence) — when the widget has no name
             or ``settings_key=False`` was passed.
        """
        if self._settings_key is False:
            return None
        if self._settings_key:
            return self._settings_key
        # Auto-derive from the wrapped widget's objectName
        w = self.wrapped_widget
        if w and hasattr(w, "objectName") and w.objectName():
            return w.objectName()
        return None

    def _init_settings(self):
        if self._settings is not None:
            return
        # No states => nothing is ever persisted (current_state is only saved
        # while cycling, which requires states). Skip the SettingsManager /
        # QSettings construction entirely; this is the common MenuOption /
        # plain-action case and runs synchronously per widget at register time.
        if not self._state_cycle:
            return
        key = self._resolve_settings_key()
        if not key:
            return
        from uitk.widgets.mixins.settings_manager import SettingsManager

        self._settings = SettingsManager(org="uitk", app="ActionOption", namespace=key)

    def _save_state(self):
        if not self._settings:
            return
        self._settings.setValue("current_state", self._state_cycle.current_state)
        self._settings.sync()

    def _load_state(self):
        if not self._settings:
            return
        saved = self._settings.value("current_state")
        if saved is not None and self._state_cycle:
            try:
                index = int(saved)
            except (ValueError, TypeError):
                return
            # notify=False: restoring a persisted index must not re-save it.
            self._state_cycle.set_current_state(index, notify=False)

    def _handle_action(self):
        """Handle the action click, cycling state if multi-state is active."""
        if self._state_cycle:
            self._state_cycle.activate(
                fallback=self._action_handler, runner=self._invoke_handler
            )
        else:
            self._invoke_handler(self._action_handler)

    def _invoke_handler(self, h):
        """Invoke *h*: call it directly, else try show/execute/run/trigger."""
        if h is None:
            return
        if callable(h):
            try:
                h()
            except Exception as e:  # pragma: no cover - defensive
                print(f"ActionOption handler error: {e}")
        else:
            # Heuristic method lookup order
            for attr in ("show", "execute", "run", "trigger"):
                if hasattr(h, attr) and callable(getattr(h, attr)):
                    getattr(h, attr)()
                    break
            else:
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
            # Reparent menu to wrapped widget while preserving popup window flags
            # (Qt.Tool | Qt.FramelessWindowHint set by _setup_as_popup).
            # Calling setParent(widget) without flags resets the menu to a
            # plain child widget, preventing it from appearing as a popup.
            self._menu.setParent(widget, self._menu.windowFlags())

    def _show_menu(self):
        """Show the menu at the button position."""
        if not self._menu:
            return

        position = getattr(self._menu, "position", "bottom")
        self._menu.show_as_popup(anchor_widget=self._widget, position=position)

        # If this button lives inside another Menu (nested option box), adopt
        # this menu into that host so its hide_on_leave keeps it open while the
        # user interacts here. No-op for the common case where the button sits
        # in a bare option-box container.
        self._adopt_popup_into_enclosing_menu(self._menu)
