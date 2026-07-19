# !/usr/bin/python
# coding=utf-8
"""Utilities and helper functions for OptionBox."""

from qtpy import QtWidgets, QtCore
from typing import Optional, Union
import pythontk as ptk


class OptionBoxManager(ptk.LoggingMixin):
    """Elegant manager for option box functionality accessible as widget.option_box"""

    def __init__(self, widget, log_level: Optional[Union[int, str]] = "WARNING"):
        self.logger.setLevel(log_level)
        self.logger.debug(
            f"OptionBoxManager.__init__: Creating for widget={type(widget).__name__}"
        )
        self._widget = widget
        self._option_box = None
        self._container = None
        self._clear_enabled = False
        self._menu = None
        # Default order. "value" first so an inline ValueOption field sits flush
        # against the wrapped widget, ahead of every icon button. Mirrors
        # OptionBox._option_order (the fallback when no order is passed here).
        self._option_order = [
            "value",
            "affix",
            "clear",
            "recent",
            "pin",
            "reset",
            "toggle",
            "action",
            "browse",
            "menu",
        ]
        self._pending_options = []  # Store options until wrapping is needed
        self._wrap_retry_scheduled = False  # Prevent duplicate timer scheduling
        self._wrap_retry_count = 0  # Track retries while waiting for parent assignment
        self._wrap_retry_timer: Optional[QtCore.QTimer] = None
        self._is_wrapped = False  # Track if wrap() has been called

    @property
    def clear_option(self):
        """Get/set clear option state"""
        return self._clear_enabled

    @clear_option.setter
    def clear_option(self, enabled):
        """Enable/disable clear option"""
        self._clear_enabled = enabled
        self._update_option_box()

    @property
    def option_order(self):
        """Get/set option ordering: ['clear', 'action'] or ['action', 'clear']"""
        return self._option_order

    @option_order.setter
    def option_order(self, order):
        """Set option ordering

        Args:
            order: List like ['clear', 'action'] or ['action', 'clear']
        """
        if not isinstance(order, (list, tuple)):
            raise ValueError("Option order must be a list or tuple")

        valid_options = {
            "value",
            "affix",
            "clear",
            "recent",
            "pin",
            "reset",
            "toggle",
            "action",
            "browse",
            "menu",
        }
        if not all(opt in valid_options for opt in order):
            raise ValueError(
                f"Invalid options in order. Valid options: {valid_options}"
            )

        self._option_order = list(order)
        # Preserve every option already added. Pending (not-yet-wrapped)
        # options stay queued and pick up the new order when wrapped; an
        # already-wrapped box is re-sorted in place. The prior code wiped
        # _pending_options and recreated the box from scratch — silently
        # discarding every option that had been added before the reorder.
        if self._option_box:
            self._option_box.set_option_order(self._option_order)

    def pin(
        self,
        settings_key: Optional[str] = None,
        *,
        double_click_to_edit: bool = False,
        single_click_restore: bool = False,
    ):
        """Enable pin values option (fluent interface).

        Args:
            settings_key: Key for persistent settings (not yet implemented)
            double_click_to_edit: Require double click to edit pinned value
            single_click_restore: Restore value on single click
        """
        from ..optionBox.options.pin_values import PinValuesOption

        # Create pin option
        pin_option = PinValuesOption(
            wrapped_widget=self._widget,
            settings_key=settings_key,
            double_click_to_edit=double_click_to_edit,
            single_click_restore=single_click_restore,
        )
        self.add_option(pin_option)
        return self

    def recent(
        self,
        settings_key: Optional[str] = None,
        *,
        max_recent: int = 10,
        **kwargs,
    ):
        """Enable recent values option (fluent interface).

        Args:
            settings_key: Key for persistent settings.
            max_recent: Maximum number of recent values to keep.
            **kwargs: Forwarded to ``RecentValuesOption``
                (e.g. ``display_format``).
        """
        from ..optionBox.options.recent_values import RecentValuesOption

        recent_option = RecentValuesOption(
            wrapped_widget=self._widget,
            settings_key=settings_key,
            max_recent=max_recent,
            **kwargs,
        )
        self.add_option(recent_option)
        return self

    def _remove_options(self, predicate):
        """Remove every option matching *predicate(option)* — pending and live.

        The shared body of the ``replace=True`` path across set_action /
        set_toggle / set_reset / add_value: each replaces only its own option
        type, so they pass a type/predicate test and this drops the matches
        from both the pending list and an already-wrapped option box.
        """
        self._pending_options = [
            o for o in self._pending_options if not predicate(o)
        ]
        if self._option_box:
            for o in [o for o in self._option_box.get_options() if predicate(o)]:
                self._option_box.remove_option(o)

    def set_action(
        self,
        callback=None,
        icon="option_box",
        tooltip="Options",
        text=None,
        replace=True,
        states=None,
        settings_key=None,
    ):
        """Set the action handler (fluent interface).

        Args:
            callback: Function or object to call/trigger when clicked
            icon: Icon name for the button (default: "option_box")
            tooltip: Tooltip text (default: "Options")
            text: Optional text to display instead of icon
            replace: If True, removes any existing ActionOptions first
                (default: True).  MenuOption instances are never removed.
            states: Optional list of state dicts for multi-state cycling.
                Each dict may have 'icon', 'tooltip', and 'callback' keys.
                When provided, clicking cycles through the states.
            settings_key: Optional explicit persistence key. When omitted
                the key is auto-derived from the widget's objectName.
                Pass ``False`` to disable persistence entirely.

        Returns:
            The created :class:`ActionOption`. Keep a reference to a
            state-cycling action so app code can sync its visuals to
            externally-owned state via ``action.current_state``.
        """
        # from ..optionBox.options import ActionOption
        # Use absolute import to ensure type consistency
        from uitk.widgets.optionBox.options.action import ActionOption, MenuOption

        if replace:
            # Remove existing ActionOption instances (but NOT MenuOption
            # subclasses — those are managed by enable_menu/disable_menu).
            self._remove_options(
                lambda opt: isinstance(opt, ActionOption)
                and not isinstance(opt, MenuOption)
            )

        action_option = ActionOption(
            wrapped_widget=self._widget,
            callback=callback,
            icon=icon,
            tooltip=tooltip,
            text=text,
            states=states,
            settings_key=settings_key,
        )
        self.add_option(action_option)
        return action_option

    def add_action(
        self,
        callback=None,
        icon="option_box",
        tooltip="Options",
        text=None,
        states=None,
        settings_key=None,
    ):
        """Add an action button without replacing existing ones.

        Convenience wrapper around ``set_action(replace=False)``.
        Use when a widget needs multiple independent action buttons.

        Args:
            callback: Function or object to call/trigger when clicked
            icon: Icon name for the button (default: "option_box")
            tooltip: Tooltip text (default: "Options")
            text: Optional text to display instead of icon
            states: Optional list of state dicts for multi-state cycling.
            settings_key: Optional explicit persistence key.

        Returns:
            The created :class:`ActionOption` (see :meth:`set_action`).
        """
        return self.set_action(
            callback=callback,
            icon=icon,
            tooltip=tooltip,
            text=text,
            replace=False,
            states=states,
            settings_key=settings_key,
        )

    def set_toggle(
        self,
        *,
        icon: str = "filter",
        icon_off: Optional[str] = None,
        tooltip_on: str = "Enabled. Click to disable.",
        tooltip_off: str = "Disabled. Click to enable.",
        initial: bool = True,
        disabled_color: Optional[str] = None,
        active_color: Optional[str] = None,
        gated_widgets=(),
        gate_wrapped: bool = False,
        keep_enabled_when_wrapped_disabled: bool = True,
        settings_key=None,
        replace: bool = True,
        on_toggled=None,
    ):
        """Add a persisted binary toggle button (fluent interface).

        Args:
            icon: Icon name. Same icon is used for on and off states unless
                ``icon_off`` is provided.
            icon_off: Optional alternate icon for the off state.
            tooltip_on: Tooltip while on.
            tooltip_off: Tooltip while off.
            initial: Starting state. Overridden by any persisted value.
            disabled_color: Hex tint for the off state. ``None`` uses the
                project's default error red (``Palette.status()["error"]``).
            active_color: Hex tint for the on state. ``None`` uses the auto
                theme colour.
            gated_widgets: Optional widgets to disable while the toggle is
                off. Caller owns lifecycle.
            gate_wrapped: When ``True``, the wrapped widget itself is disabled
                while the toggle is off (the button stays live to re-enable it).
                Use for a filter/enable toggle that should grey out its own
                field when off.
            keep_enabled_when_wrapped_disabled: Keep the button clickable when
                its wrapped widget is disabled (default ``True``).
            settings_key: Persistence namespace. ``str`` for explicit key,
                ``None`` to auto-derive from wrapped widget's objectName,
                ``False`` to opt out.
            replace: When ``True`` (default), removes any existing
                ToggleOption first. Pass ``False`` to stack multiple toggles.
            on_toggled: Optional callable connected to the toggle's
                ``toggled(bool)`` signal as a convenience.

        Returns:
            self: For fluent chaining. Access the option via
            ``find_option(ToggleOption)``.
        """
        from uitk.widgets.optionBox.options.toggle import ToggleOption

        if replace:
            # ToggleOption and DisableOption are siblings, so this never touches
            # a DisableOption (managed via set_disable()).
            self._remove_options(lambda o: isinstance(o, ToggleOption))

        kwargs = dict(
            wrapped_widget=self._widget,
            icon=icon,
            icon_off=icon_off,
            tooltip_on=tooltip_on,
            tooltip_off=tooltip_off,
            initial=initial,
            gated_widgets=gated_widgets,
            gate_wrapped=gate_wrapped,
            keep_enabled_when_wrapped_disabled=keep_enabled_when_wrapped_disabled,
            settings_key=settings_key,
        )
        if disabled_color is not None:
            kwargs["disabled_color"] = disabled_color
        if active_color is not None:
            kwargs["active_color"] = active_color
        toggle = ToggleOption(**kwargs)
        if on_toggled is not None:
            toggle.toggled.connect(on_toggled)
        self.add_option(toggle)
        return self

    def add_toggle(self, **kwargs):
        """Add a toggle without replacing existing ones.

        Convenience wrapper around ``set_toggle(replace=False)``.
        """
        kwargs.setdefault("replace", False)
        return self.set_toggle(**kwargs)

    def set_filter(
        self,
        *,
        settings,
        text_key: str,
        on_changed,
        enabled_key: Optional[str] = None,
        initial_enabled: bool = True,
        on_toggled=None,
        tooltip_on: str = "Filter enabled. Click to disable.",
        tooltip_off: str = "Filter disabled. Click to enable.",
        scopes=None,
        scope_key: Optional[str] = None,
        default_scope: Optional[str] = None,
        on_scope_changed=None,
        replace: bool = True,
    ):
        """Turn the wrapped text widget into a filter field (fluent interface).

        Adds a :class:`FilterOption` — the single, reusable home for the "filter
        line-edit" pattern (search/exclude rows, action filters, …). The wrapped
        widget gets a filter on/off toggle (the field dims while off), text that
        persists + restores via ``settings``, and — when ``scopes`` is given — a
        scope-cycle button beside the toggle.

        Requires a text-bearing wrapped widget; an incompatible host is skipped
        with a warning (see :meth:`FilterOption.is_compatible`).

        Args:
            settings: ``QSettings``-like store backing text/scope/enabled state.
            text_key: Key under which the verbatim text is persisted per edit.
            on_changed: Called (no args) after each edit — wire to the re-filter.
            enabled_key: Optional key persisting the on/off flag. ``None`` leaves
                on/off non-persistent.
            initial_enabled: Starting on/off state (overridden by persistence).
            on_toggled: Optional callable connected to the toggle's
                ``toggled(bool)`` signal (e.g. ``lambda _on: self._apply_filter()``).
            tooltip_on / tooltip_off: Toggle-button tooltips.
            scopes: Optional ``[{"key", "icon"}, …]`` for an N-state scope cycle.
            scope_key / default_scope / on_scope_changed: Required with ``scopes``.
            replace: When ``True`` (default), removes any existing FilterOption
                (and its scope button) first.

        Returns:
            self: For fluent chaining. Retrieve the option via
            ``find_option(FilterOption)`` to read ``is_on`` / ``patterns()`` /
            ``scope``.
        """
        from uitk.widgets.optionBox.options.filter import FilterOption

        if replace:
            existing = self.find_option(FilterOption)
            if existing is not None and existing.scope_action is not None:
                scope_action = existing.scope_action
                self._remove_options(lambda o: o is scope_action)
            self._remove_options(lambda o: isinstance(o, FilterOption))

        option = FilterOption(
            wrapped_widget=self._widget,
            settings=settings,
            text_key=text_key,
            on_changed=on_changed,
            enabled_key=enabled_key,
            initial_enabled=initial_enabled,
            on_toggled=on_toggled,
            tooltip_on=tooltip_on,
            tooltip_off=tooltip_off,
            scopes=scopes,
            scope_key=scope_key,
            default_scope=default_scope,
            on_scope_changed=on_scope_changed,
        )
        self.add_option(option)
        # Add the sibling scope button only when the host is compatible — i.e.
        # only when add_option accepted the FilterOption itself. The scope
        # ActionOption is compatible with anything (default gate), so without
        # this it would be added as an orphan on a non-text host. Gating on the
        # same condition the FilterOption gate uses is correct regardless of
        # ``replace`` (a find_option(FilterOption) identity check would return a
        # *prior* filter on a replace=False second call and wrongly skip this one).
        if option.scope_action is not None and FilterOption.is_compatible(self._widget):
            self.add_option(option.scope_action)
        return self

    def set_disable(
        self,
        *,
        icon: str = "ban",
        tooltip_on: str = "Enabled. Click to disable.",
        tooltip_off: str = "Disabled. Click to enable.",
        initial: bool = True,
        gate_wrapped: bool = True,
        gated_widgets=(),
        disabled_color: Optional[str] = None,
        active_color: Optional[str] = None,
        settings_key=None,
        replace: bool = True,
        on_toggled=None,
    ):
        """Add a universal *disable* button (fluent interface).

        Toggles the wrapped widget's enabled state while keeping the button
        itself clickable, so it can always be re-enabled. The icon (default the
        ``ban`` glyph) tints to the project error colour while disabled. This is
        the centralized primitive for "disable this widget" across the codebase
        — prefer it over a bare ``setEnabled(False)`` paired with a sibling
        toggle (which traps itself; see :class:`DisableOption`).

        Args:
            icon: Icon name (default ``"ban"``).
            tooltip_on / tooltip_off: Tooltips for the enabled / disabled states.
            initial: Starting state (``True`` = enabled). Overridden by any
                persisted value.
            gate_wrapped: Disable the wrapped widget itself (default ``True``).
            gated_widgets: Additional widgets to disable in sync.
            disabled_color: Hex tint while disabled (``None`` = project error
                red).
            active_color: Hex tint while enabled (``None`` = auto theme colour).
            settings_key: Persistence namespace. ``str`` explicit, ``None``
                auto-derive from the wrapped widget's objectName, ``False`` to
                opt out.
            replace: When ``True`` (default), removes any existing
                DisableOption first.
            on_toggled: Optional callable connected to ``toggled(bool)``
                (``True`` = now enabled).

        Returns:
            self: For fluent chaining. Retrieve via ``find_option(DisableOption)``.
        """
        from uitk.widgets.optionBox.options.disable import DisableOption

        if replace:
            self._remove_options(lambda o: isinstance(o, DisableOption))

        kwargs = dict(
            wrapped_widget=self._widget,
            icon=icon,
            tooltip_on=tooltip_on,
            tooltip_off=tooltip_off,
            initial=initial,
            gate_wrapped=gate_wrapped,
            gated_widgets=gated_widgets,
            settings_key=settings_key,
        )
        if disabled_color is not None:
            kwargs["disabled_color"] = disabled_color
        if active_color is not None:
            kwargs["active_color"] = active_color
        option = DisableOption(**kwargs)
        if on_toggled is not None:
            option.toggled.connect(on_toggled)
        self.add_option(option)
        return self

    def add_disable(self, **kwargs):
        """Add a disable button without replacing existing ones.

        Convenience wrapper around ``set_disable(replace=False)``.
        """
        kwargs.setdefault("replace", False)
        return self.set_disable(**kwargs)

    def add_value(
        self,
        *,
        width: int = 46,
        decimals=None,
        suffix: str = "",
        order=None,
        replace: bool = True,
    ):
        """Add an inline editable value field that mirrors the wrapped widget.

        A compact, button-less spin box sits flush beside the wrapped widget
        and stays in two-way sync with its value — dragging the widget updates
        the field; typing in the field updates the widget (and lets it emit, so
        any connected slot still fires). Pairs naturally with :class:`Slider`.

        Args:
            width: Fixed pixel width of the field.
            decimals: Decimal places; ``None`` inherits the wrapped widget's
                ``decimals()`` (else 0 — integer, e.g. a slider).
            suffix: Optional unit suffix after the number (e.g. ``"°"``).
            order: Explicit sort position. See :class:`BaseOption`.
            replace: When ``True`` (default), removes any existing ValueOption
                first. Pass ``False`` to stack more than one.

        Returns:
            self: For fluent chaining. Access the option via
            ``find_option(ValueOption)``.
        """
        from uitk.widgets.optionBox.options.value import ValueOption

        if replace:
            self._remove_options(lambda o: isinstance(o, ValueOption))

        self.add_option(
            ValueOption(
                wrapped_widget=self._widget,
                width=width,
                decimals=decimals,
                suffix=suffix,
                order=order,
            )
        )
        return self

    def set_affix(
        self,
        *,
        default: str = "auto",
        on_change=None,
        tooltip: Optional[str] = None,
        order=None,
        replace: bool = True,
    ):
        """Add an inline affix-mode picker (Auto / Suffix / Prefix) — fluent.

        Turns the wrapped text field into an affix entry with a compact combobox
        beside it declaring how the field's text applies to a base name. The
        parsing lives in ``pythontk.StrUtils.split_affix``; read the selection
        back with :attr:`affix_mode` / :meth:`resolve_affix`. Requires a
        text-bearing host (skipped + warned otherwise — see
        :meth:`AffixOption.is_compatible`).

        Args:
            default: Initial mode — ``"auto"``, ``"suffix"`` or ``"prefix"``.
            on_change: Optional callable invoked with the new mode string
                whenever the user changes the picker.
            tooltip: Override the picker tooltip (defaults to the mode guide).
            order: Explicit sort position. See :class:`BaseOption`.
            replace: When ``True`` (default), removes any existing AffixOption
                first.

        Returns:
            self: For fluent chaining. Retrieve the option via
            ``find_option(AffixOption)`` (or use :attr:`affix_mode` /
            :meth:`resolve_affix`).
        """
        from uitk.widgets.optionBox.options.affix import AffixOption

        if replace:
            self._remove_options(lambda o: isinstance(o, AffixOption))

        # Only forward an explicit tooltip; None lets AffixOption apply its own
        # default (the full mode guide) rather than blanking the tooltip.
        extra = {} if tooltip is None else {"tooltip": tooltip}
        self.add_option(
            AffixOption(
                wrapped_widget=self._widget,
                default=default,
                on_change=on_change,
                order=order,
                **extra,
            )
        )
        return self

    @property
    def affix_mode(self) -> str:
        """Current affix mode (``"auto"`` when no AffixOption is present)."""
        from uitk.widgets.optionBox.options.affix import AffixOption

        option = self.find_option(AffixOption)
        return option.mode if option is not None else "auto"

    def resolve_affix(self, *, default: str = "prefix"):
        """Return ``(prefix, suffix)`` for the wrapped field under its mode.

        Reads the wrapped widget's text and the AffixOption's mode (``"auto"``
        when no picker was added) and splits via
        ``pythontk.StrUtils.split_affix``. *default* is the fallback mode used
        when Auto is selected but the text has no boundary delimiter.
        """
        from uitk.widgets.optionBox.options.affix import AffixOption

        option = self.find_option(AffixOption)
        if option is not None:
            return option.resolve(default=default)
        text = self._widget.text() if hasattr(self._widget, "text") else ""
        return ptk.StrUtils.split_affix(text, mode="auto", default=default)

    def set_reset(
        self,
        *,
        reset=None,
        icon: str = "undo",
        tooltip: str = "Reset to default.    Alt/Ctrl+click: hold at default (bypass).",
        tooltip_bypassed: str = "Held at default (bypassed). Click to restore your value.",
        disabled_color: Optional[str] = None,
        bypass_modifier=None,
        replace: bool = True,
        on_toggled=None,
    ):
        """Add a per-widget *reset-to-default* button (fluent).

        A plain click resets the widget to its default (persisted). Hold a
        modifier (``Alt`` or ``Ctrl`` by default) while clicking to *bypass*:
        snapshot the value, reset to default transiently, and grey the widget
        out; click the bypassed button again to restore. The default is
        resolved from the widget's window ``StateManager`` unless a ``reset``
        callable is given. Bypass is non-persistent (each session starts
        un-bypassed).

        Args:
            reset: Optional callable to put the widget at its default. ``None``
                auto-uses ``window.state.reset(widget)``.
            icon: Icon name (theme-coloured normally, red while bypassed).
            tooltip / tooltip_bypassed: Tooltips for the active / bypassed states.
            disabled_color: Hex tint while bypassed (``None`` = project error red).
            bypass_modifier: Modifier(s) that switch a click from reset to the
                bypass toggle (``None`` = ``Alt | Ctrl``).
            replace: When ``True`` (default), removes any existing ResetOption.
            on_toggled: Optional callable connected to ``toggled(bool)``
                (``True`` = now bypassed).

        Returns:
            self: For fluent chaining. Retrieve via ``find_option(ResetOption)``.
        """
        from uitk.widgets.optionBox.options.reset import ResetOption

        if replace:
            self._remove_options(lambda o: isinstance(o, ResetOption))

        kwargs = dict(
            wrapped_widget=self._widget,
            reset=reset,
            icon=icon,
            tooltip=tooltip,
            tooltip_bypassed=tooltip_bypassed,
        )
        if disabled_color is not None:
            kwargs["disabled_color"] = disabled_color
        if bypass_modifier is not None:
            kwargs["bypass_modifier"] = bypass_modifier
        option = ResetOption(**kwargs)
        if on_toggled is not None:
            option.toggled.connect(on_toggled)
        self.add_option(option)
        return self

    def browse(
        self,
        file_types=None,
        title="Browse",
        start_dir=None,
        mode="file",
        icon="folder",
        tooltip="Browse...",
        callback=None,
    ):
        """Enable file/folder browse button (fluent interface).

        Args:
            file_types: File filter string for QFileDialog
                (e.g. ``"Images (*.png *.jpg);;All Files (*.*)"``).
                Ignored when *mode* is ``"directory"``.
            title: Dialog window title.
            start_dir: Initial directory. When *None*, inferred from
                the current widget value or defaults to home.
            mode: ``"file"`` (default), ``"files"`` (multi-select),
                ``"save"``, or ``"directory"``.
            icon: Icon name for the button (default: ``"folder"``).
            tooltip: Tooltip text (default: ``"Browse..."``).
            callback: Optional callable invoked with the selected
                path(s) after the widget value has been set.

        Returns:
            self: For fluent interface chaining.
        """
        from uitk.widgets.optionBox.options.browse import BrowseOption

        browse_option = BrowseOption(
            wrapped_widget=self._widget,
            file_types=file_types,
            title=title,
            start_dir=start_dir,
            mode=mode,
            icon=icon,
            tooltip=tooltip,
            callback=callback,
        )
        self.add_option(browse_option)
        return self

    def enable_clear(self):
        """Enable clear option (fluent interface)"""
        self.clear_option = True
        return self

    def disable_clear(self):
        """Disable clear option (fluent interface)"""
        self.clear_option = False
        return self

    def clear_options(self):
        """Clear all added options."""
        if self._option_box:
            # Copy list to avoid modification during iteration
            for opt in self._option_box.get_options():
                # Don't remove clear button if managed by property
                from ..optionBox.options.clear import ClearOption

                if isinstance(opt, ClearOption) and self._clear_enabled:
                    continue
                self._option_box.remove_option(opt)

        self._pending_options = []
        return self

    def find_option(self, option_type):
        """Find the first option of the given type.

        Searches both pending and live options.

        Args:
            option_type: The class (or tuple of classes) to match.

        Returns:
            The first matching option instance, or None.
        """
        for opt in self._pending_options:
            if isinstance(opt, option_type):
                return opt
        if self._option_box:
            for opt in self._option_box.get_options():
                if isinstance(opt, option_type):
                    return opt
        return None

    def set_order(self, order):
        """Set option order (fluent interface)

        Args:
            order: List like ['clear', 'action'] or ['action', 'clear']
        """
        self.option_order = order
        return self

    def clear_first(self):
        """Set clear button to appear first (fluent interface)"""
        return self.set_order(["clear", "pin", "action"])

    @property
    def enabled(self):
        """Check if option box is enabled"""
        return self._option_box is not None

    @property
    def widget(self):
        """Get the actual option box widget"""
        self._update_option_box()  # Ensure option box is created if needed
        return self._option_box

    @property
    def menu(self):
        """Get or create a Menu instance for this option box.

        For backward compatibility, this property auto-creates the menu if needed.
        This maintains existing API behavior where `widget.option_box.menu.add()`
        always works.

        The performance impact is minimal because:
        1. Menu creation is lazy (doesn't build UI until items added)
        2. MenuMixin descriptor caches the result
        3. This is only called when explicitly accessing option_box.menu

        Returns:
            Menu: The menu instance (created if necessary)
        """
        if self._menu is None:
            self.enable_menu()
        return self._menu

    def get_menu(self, create=False):
        """Get menu, optionally creating if it doesn't exist.

        This method provides explicit control over menu creation.
        The .menu property auto-creates for backward compatibility.

        Args:
            create: If True and menu doesn't exist, creates one via enable_menu()

        Returns:
            Menu: The menu instance, or None if it doesn't exist and create=False
        """
        if self._menu is None and create:
            self.enable_menu()
        return self._menu

    @menu.setter
    def menu(self, value):
        """Set (or clear) the option-box menu.

        Assigning a :class:`Menu` produces exactly one menu button via
        :meth:`enable_menu`; reassigning first tears down any prior button
        (:meth:`disable_menu`) so buttons never duplicate. Assigning ``None``
        disables the menu entirely.

        Previously this only stored ``self._menu`` and never produced a button
        — so ``widget.option_box.menu = my_menu`` was a dead-end, and a
        subsequent ``enable_menu`` short-circuited on the already-set ``_menu``.

        Args:
            value: A Menu instance to use, or None to disable.
        """
        from uitk.widgets.menu import Menu

        # Tear down any existing menu + its button first (idempotent).
        self.disable_menu()
        if value is None:
            return
        if isinstance(value, Menu):
            self.enable_menu(menu=value)
        else:
            # Non-Menu value: legacy passthrough — stored without a button.
            self._menu = value

    def enable_menu(self, menu=None, **menu_kwargs):
        """Enable menu option using the MenuOption plugin.

        This follows the same pattern as enable_clear() - it creates
        the appropriate option plugin and adds it to the option box.

        Coordinates with MenuMixin to avoid duplicate menu creation:
        - Checks for existing menu via MenuMixin's _menu_instance
        - Reuses existing menu if found
        - Creates new menu only if needed

        Args:
            menu: Optional existing Menu instance. If None, will check for
                  existing menu or create a new one.
            **menu_kwargs: Additional kwargs passed to Menu() constructor if
                          creating a new menu (e.g., position, add_header, etc.)

        Returns:
            self: For fluent interface chaining
        """
        # PERFORMANCE: Only enable timing if logger level is DEBUG (10) or lower
        # In production with INFO (20) or higher, this adds 50-100ms overhead
        timing_enabled = self.logger.level <= 10

        if timing_enabled:
            import time

            enable_menu_start = time.perf_counter()
            _step_time = enable_menu_start

            def _log_step(step_name):
                nonlocal _step_time
                now = time.perf_counter()
                duration_ms = (now - _step_time) * 1000
                total_ms = (now - enable_menu_start) * 1000
                self.logger.debug(
                    f"OptionBoxManager.enable_menu [{step_name}]: {duration_ms:.3f}ms (total: {total_ms:.3f}ms)"
                )
                _step_time = now

        else:
            # No-op function when timing disabled
            def _log_step(step_name):
                pass

        self.logger.debug(
            f"OptionBoxManager.enable_menu: Called with menu={menu}, "
            f"menu_kwargs={list(menu_kwargs.keys())}"
        )

        if self._menu is None:
            from uitk.widgets.menu import Menu

            _log_step("import_Menu")

            # Only use explicitly passed menu - do NOT reuse widget's context menu
            # The option box menu should be completely separate from the widget's
            # right-click context menu (which is managed by MenuMixin)
            if menu is not None and isinstance(menu, Menu):
                self.logger.debug(
                    "OptionBoxManager.enable_menu: Using explicitly passed menu"
                )
                self._menu = menu
                _log_step("use_passed_menu")
            else:
                # Create a new Menu with appropriate defaults
                # Merge defaults with user-provided kwargs
                default_kwargs = {
                    "parent": self._widget,
                    "trigger_button": "none",  # OptionBox button handles triggering
                    "match_parent_width": False,  # Don't constrain width to prevent cropping
                    "add_apply_button": True,  # Enable apply button for option box menus
                    "add_defaults_button": True,  # Show restore defaults for option box menus
                    "hide_on_leave": True,  # Auto-hide when mouse leaves
                }
                default_kwargs.update(menu_kwargs)

                # Auto-name the menu based on the parent widget if not provided
                if (
                    "name" not in default_kwargs
                    and self._widget
                    and self._widget.objectName()
                ):
                    default_kwargs["name"] = f"{self._widget.objectName()}_option_menu"

                self.logger.debug(
                    f"OptionBoxManager.enable_menu: Creating NEW menu with kwargs={list(default_kwargs.keys())}"
                )

                self._menu = Menu(**default_kwargs)
                _log_step("Menu_creation")

                self.logger.debug(
                    "OptionBoxManager.enable_menu: Menu created (separate from widget context menu)"
                )
                _log_step("menu_created")

            # Create and add the MenuOption plugin
            # MenuOption is a plugin that creates its own button, so we don't need
            # to set _action_handler - that would create a duplicate button
            from ..optionBox.options.action import MenuOption

            _log_step("import_MenuOption")

            menu_option = MenuOption(wrapped_widget=self._widget, menu=self._menu)
            _log_step("MenuOption_creation")

            self.add_option(menu_option)
            _log_step("add_option")

        if timing_enabled:
            total_duration = (time.perf_counter() - enable_menu_start) * 1000
            self.logger.debug(
                f"OptionBoxManager.enable_menu: TOTAL completed in {total_duration:.3f}ms"
            )
        return self

    def enable_option_menu(
        self,
        *,
        title: Optional[str] = None,
        items=None,
        build_menu=None,
        position: str = "cursorPos",
        add_header: bool = True,
        tooltip: str = "Options",
        menu=None,
    ):
        """Add a dropdown *option menu* button (fluent interface).

        Builds an :class:`OptionMenuOption` — a button that pops a ``Menu`` of
        command rows — and adds it to the option box. Backs the
        ``widget.options.option_menu(...)`` fluent wrapper (which previously
        called this nonexistent method and raised ``AttributeError``).

        Args:
            title: Optional dropdown-menu title.
            items: Iterable of ``(label, callback)`` rows; each becomes a real
                clickable button wired to its callback.
            build_menu: Optional ``callable(menu)`` for custom population, run
                after ``items``.
            position: Menu popup position (default ``"cursorPos"``).
            add_header: Whether the dropdown ``Menu`` shows a draggable header.
            tooltip: Button tooltip.
            menu: Optional pre-built :class:`Menu` used verbatim.

        Returns:
            self: For fluent interface chaining.
        """
        from uitk.widgets.optionBox.options.option_menu import OptionMenuOption

        item_list = list(items) if items else None
        option = OptionMenuOption(
            wrapped_widget=self._widget,
            menu_items=item_list,
            tooltip=tooltip,
            position=position,
            add_header=add_header,
        )
        # A caller-supplied Menu is used verbatim (bypasses lazy creation), so
        # its rows must be added explicitly — _ensure_menu only populates
        # menu_items when it builds the menu itself.
        if menu is not None:
            option._menu = menu
            for item in item_list or []:
                option._add_menu_item(item)
        self.add_option(option)

        # Force the (otherwise lazy) menu build only when there is something to
        # apply beyond the static items the option already carries.
        if title is not None or build_menu is not None:
            built = option.menu
            if title is not None:
                built.setTitle(title)
            if build_menu is not None:
                build_menu(built)
        return self

    def disable_menu(self):
        """Disable the menu option (fluent interface).

        Removes the MenuOption button — from both the pending list and an
        already-wrapped option box — and drops the menu reference, so a later
        :meth:`enable_menu` (or the ``menu`` setter) rebuilds a *single* fresh
        button instead of stacking a duplicate on top of an orphaned one.

        Returns:
            self: For fluent interface chaining
        """
        from ..optionBox.options.action import MenuOption

        self._remove_options(lambda o: isinstance(o, MenuOption))
        self._menu = None
        return self

    def add_option(self, option):
        """Add an option plugin to this option box.

        This is the central method for adding any option plugin,
        maintaining consistency across all option types.

        LAZY LOADING: Options are stored in _pending_options and only
        wrapped when the container is actually accessed via .container property.

        Args:
            option: An option plugin instance to add

        Returns:
            self: For fluent interface chaining
        """
        # PERFORMANCE: Only enable timing if logger level is DEBUG (10) or lower
        timing_enabled = self.logger.level <= 10

        if timing_enabled:
            import time

            add_option_start = time.perf_counter()
            _step_time = add_option_start

            def _log_step(step_name):
                nonlocal _step_time
                now = time.perf_counter()
                duration_ms = (now - _step_time) * 1000
                total_ms = (now - add_option_start) * 1000
                self.logger.debug(
                    f"OptionBoxManager.add_option [{step_name}]: {duration_ms:.3f}ms (total: {total_ms:.3f}ms)"
                )
                _step_time = now

        else:

            def _log_step(step_name):
                pass

        # Compatibility gate: an option type may declare it only applies to
        # certain hosts (e.g. FilterOption needs a text field). Skip + warn
        # rather than silently mis-wiring an incompatible widget. This is the
        # "plugins only seen by compatible widgets" hook (BaseOption.is_compatible).
        is_compatible = getattr(type(option), "is_compatible", None)
        if callable(is_compatible):
            try:
                compatible = is_compatible(self._widget)
            except Exception:
                compatible = True  # never let a buggy check block a valid option
            if not compatible:
                self.logger.warning(
                    f"{type(option).__name__} is not compatible with "
                    f"{type(self._widget).__name__}; skipping."
                )
                return self

        # If already wrapped, add option directly to option box
        if self._is_wrapped and self._option_box:
            self._option_box.add_option(option)
            _log_step("direct_add_to_wrapped")
            if timing_enabled:
                total_duration = (time.perf_counter() - add_option_start) * 1000
                self.logger.debug(
                    f"OptionBoxManager.add_option: TOTAL (already wrapped) in {total_duration:.3f}ms"
                )
            return self

        # Check for existing option box (from menu or other systems)
        if not self._option_box:
            existing_option_box = self._find_existing_option_box()
            _log_step("find_existing")

            if existing_option_box:
                # Reuse existing option box - it's already wrapped
                self._option_box = existing_option_box
                self._container = existing_option_box.container
                self._is_wrapped = True
                # Migrate already-queued options into the adopted box before
                # adding the current one. Without this, options queued while the
                # widget was still unparented (awaiting the wrap-retry timer) are
                # silently dropped: once _is_wrapped is True,
                # _attempt_wrap_when_ready returns early and _pending_options is
                # never wrapped.
                for pending in self._pending_options:
                    self._option_box.add_option(pending)
                self._pending_options = []
                self._option_box.add_option(option)
                _log_step("reuse_and_add")
                if timing_enabled:
                    total_duration = (time.perf_counter() - add_option_start) * 1000
                    self.logger.debug(
                        f"OptionBoxManager.add_option: TOTAL (reused existing) in {total_duration:.3f}ms"
                    )
                return self

        # LAZY LOADING: Store option for later, don't wrap yet!
        self._pending_options.append(option)
        _log_step("store_pending")

        # Ensure the widget gets wrapped once it's part of a layout
        self._schedule_wrap_if_needed()

        if timing_enabled:
            total_duration = (time.perf_counter() - add_option_start) * 1000
            self.logger.debug(
                f"OptionBoxManager.add_option: TOTAL (deferred wrapping) in {total_duration:.3f}ms"
            )
        return self

    def _schedule_wrap_if_needed(self):
        """Schedule a wrap attempt once the widget is laid out.

        The option box needs to wrap the underlying widget to display buttons.
        Strategy:

        - **Fast path (parent already attached)**: perform the wrap
          synchronously.  The vast majority of slot-init calls happen with
          the widget already inserted into a layout, so this is the common
          case.  Running the wrap synchronously means the
          ``parent.layout().replaceWidget(...)`` reparent completes before
          ``MainWindow.showEvent`` returns control to the event loop —
          eliminating the visible flicker between ``super().showEvent()``
          and the deferred-timer-driven wrap firing on the next tick.

        - **Slow path (parent missing)**: fall back to the
          ``_schedule_wrap_retry`` / ``_attempt_wrap_when_ready`` retry loop
          so widgets parented late (e.g. via ``setParent`` after
          construction) still get wrapped once their parent attaches.

        Re-entrancy: ``_perform_wrap`` reparents *this* widget into a new
        ``OptionBoxContainer``.  ``register_children`` walks via a
        ``findChildren`` snapshot, so reparenting mid-walk is safe.
        Menu-item registration (Contract 2) remains deferred via the
        coalesced drain in :class:`Menu`.

        **Observable consequence for slot authors**: when called from
        inside a ``<name>_init(widget)`` body (which is the normal entry
        point), ``widget.parent()`` changes *during* the slot body — from
        the original layout parent (e.g. the central widget) to the new
        ``OptionBoxContainer``.  Code in the slot body that reads
        ``widget.parent()`` *after* wiring an option must account for
        this; reading it *before* the option_box call sees the original
        parent.  No tentacle / mayatk slot in the current monorepo
        relies on the post-wiring parent (verified by grep).
        """

        if self._is_wrapped or not self._pending_options:
            return  # Nothing to do or already wrapped

        if self._wrap_retry_scheduled:
            return  # A retry is already pending

        widget = getattr(self, "_widget", None)
        if widget is not None and widget.parent() is not None:
            # Fast path: synchronous wrap — completes before showEvent paints.
            self._perform_wrap()
            return

        self._wrap_retry_scheduled = True
        self._schedule_wrap_retry(0)

    def _schedule_wrap_retry(self, delay_ms: int) -> None:
        """Arm the retry-until-parented timer, parented to the wrapped widget
        (not a bare ``QTimer.singleShot``) so it is destroyed along with the
        widget instead of firing ``_attempt_wrap_when_ready`` into a deleted
        ``self._widget`` (observed live: ``RuntimeError: Internal C++ object
        ... already deleted`` from ``widget.parent()`` when a widget is torn
        down mid-retry, e.g. test teardown right after construction)."""
        widget = getattr(self, "_widget", None)
        if widget is None:
            return
        if self._wrap_retry_timer is None:
            self._wrap_retry_timer = QtCore.QTimer(widget)
            self._wrap_retry_timer.setSingleShot(True)
            self._wrap_retry_timer.timeout.connect(self._attempt_wrap_when_ready)
        self._wrap_retry_timer.start(delay_ms)

    def _attempt_wrap_when_ready(self):
        """Attempt to wrap the widget, retrying until a parent exists."""

        self._wrap_retry_scheduled = False

        if self._is_wrapped or not self._pending_options:
            self._wrap_retry_count = 0
            return

        widget = getattr(self, "_widget", None)
        if widget is None:
            return

        parent = widget.parent()
        if parent is None:
            # Parent not assigned yet; retry with a small delay (up to a limit)
            if self._wrap_retry_count >= 50:
                self.logger.warning(
                    "OptionBoxManager: Unable to wrap option box - widget has no parent"
                )
                return

            self._wrap_retry_count += 1
            self._wrap_retry_scheduled = True
            self._schedule_wrap_retry(15)
            return

        # Parent exists - perform the wrap now
        try:
            self._perform_wrap()
        finally:
            self._wrap_retry_count = 0

    @property
    def container(self):
        """Get the container widget (for layout management).

        LAZY LOADING TRIGGER: Accessing this property will trigger wrapping
        if there are pending options that haven't been wrapped yet.
        """
        # If we have pending options and haven't wrapped yet, do it now
        if self._pending_options and not self._is_wrapped:
            self.logger.debug(
                f"OptionBoxManager.container: Triggering lazy wrap for {len(self._pending_options)} pending options"
            )
            self._perform_wrap()

        # If we don't have a container yet, but widget has a menu with items,
        # try to get the container from the menu's option box. Use the
        # non-creating ``has_menu`` check — ``hasattr(widget, "menu")`` would
        # materialize a context menu via the lazy MenuMixin descriptor.
        if not self._container and getattr(self._widget, "has_menu", False):
            menu = self._widget.menu
            if (
                hasattr(menu, "option_box")
                and menu.option_box
                and hasattr(menu.option_box, "container")
            ):
                self._container = menu.option_box.container
                self._option_box = menu.option_box
                # The adopted box already wraps the widget; mark wrapped so a
                # later add_option routes through the direct-add branch instead
                # of building a SECOND OptionBox and re-wrapping the widget
                # (which corrupts the layout). Mirrors the two sibling adoption
                # sites (add_option reuse branch and _update_option_box).
                self._is_wrapped = True

        return self._container

    def _perform_wrap(self):
        """Perform the actual wrapping of pending options.

        This is called lazily when container is first accessed.
        Wraps the widget with all pending options at once for efficiency.
        """
        # PERFORMANCE: Only enable timing if logger level is DEBUG (10) or lower
        timing_enabled = self.logger.level <= 10

        if timing_enabled:
            import time

            wrap_start = time.perf_counter()
            _step_time = wrap_start

            def _log_step(step_name):
                nonlocal _step_time
                now = time.perf_counter()
                duration_ms = (now - _step_time) * 1000
                total_ms = (now - wrap_start) * 1000
                self.logger.debug(
                    f"OptionBoxManager._perform_wrap [{step_name}]: {duration_ms:.3f}ms (total: {total_ms:.3f}ms)"
                )
                _step_time = now

        else:

            def _log_step(step_name):
                pass

        if not self._pending_options:
            return  # Nothing to wrap

        from ._optionBox import OptionBox

        _log_step("import_OptionBox")

        # Create option box with ALL pending options at once
        self._option_box = OptionBox(
            show_clear=self._clear_enabled,
            option_order=self._option_order,
            options=self._pending_options,
        )
        _log_step("OptionBox_created")

        # Perform the wrap (expensive operation - but only done once)
        self._container = self._option_box.wrap(self._widget)
        _log_step("wrap_widget")

        # Mark as wrapped and clear pending options
        self._is_wrapped = True
        self._pending_options = []
        _log_step("cleanup")

        if timing_enabled:
            total_duration = (time.perf_counter() - wrap_start) * 1000
            self.logger.debug(
                f"OptionBoxManager._perform_wrap: TOTAL wrap completed in {total_duration:.3f}ms"
            )

    def _update_option_box(self):
        """Update option box based on current settings."""
        # If we already have an option box, just update it
        if self._option_box:
            self._option_box.set_clear_button_visible(self._clear_enabled)
            return

        # Check if widget already has a menu with an option box
        existing_option_box = self._find_existing_option_box()

        if existing_option_box:
            # Use the existing option box from menu
            self._option_box = existing_option_box
            self._container = existing_option_box.container
            self._is_wrapped = True
            # Migrate already-queued options into the adopted box so they aren't
            # dropped once _is_wrapped short-circuits the deferred wrap path.
            for pending in self._pending_options:
                self._option_box.add_option(pending)
            self._pending_options = []
            if self._clear_enabled:
                self._option_box.set_clear_button_visible(True)
        elif self._clear_enabled:
            # Create and wrap immediately if clear is enabled
            self._create_option_box()

    def _find_existing_option_box(self):
        """Find existing option box created by menu or other systems.

        Uses the non-creating ``has_menu`` check instead of touching
        ``widget.menu`` directly: the MenuMixin ``.menu`` descriptor lazily
        *creates* a standalone context menu on first access, so probing it
        here would materialize an otherwise-unused menu for every wrapped
        widget at register time.
        """
        if not getattr(self._widget, "has_menu", False):
            return None

        menu = self._widget.menu
        if hasattr(menu, "option_box"):
            menu_option_box = menu.option_box
            if menu_option_box and hasattr(menu_option_box, "container"):
                return menu_option_box

        return None

    def _create_option_box(self):
        """Create and wrap the option box."""
        from ._optionBox import OptionBox

        # Include any pending plugins
        pending = self._pending_options or None

        self._option_box = OptionBox(
            show_clear=self._clear_enabled,
            option_order=self._option_order,
            options=pending,
        )
        self._container = self._option_box.wrap(self._widget)
        self._is_wrapped = True

        # Clear pending options
        self._pending_options = []
        self._wrap_retry_scheduled = False

    def remove(self):
        """Remove option box completely"""
        if self._option_box and self._container:
            # Restore widget to original state
            parent = self._container.parent()
            if parent and parent.layout():
                parent.layout().replaceWidget(self._container, self._widget)
            else:
                self._widget.setParent(parent)
                self._widget.move(self._container.pos())

            self._container.deleteLater()
            self._option_box = None
            self._container = None
            self._clear_enabled = False
            self._menu = None
            self._is_wrapped = False
            self._pending_options = []


# -------------------------------------------------------------------------
# Convenience functions for easy integration
# -------------------------------------------------------------------------


def add_option_box(widget, show_clear=False, options=None, **kwargs):
    """Add an option box to any widget with one function call.

    Args:
        widget: The widget to wrap
        show_clear: Whether to show clear button for text widgets
        options: List of option plugins to add
        **kwargs: Additional options

    Returns:
        The container widget that should be added to layouts

    Example:
        line_edit = QtWidgets.QLineEdit()
        container = add_option_box(line_edit, show_clear=True)
        layout.addWidget(container)
    """
    from ._optionBox import OptionBox

    option_box = OptionBox(show_clear=show_clear, options=options, **kwargs)
    return option_box.wrap(widget)


def add_clear_option(widget, **kwargs):
    """Add just a clear button to a text widget.

    Args:
        widget: The text widget to add clear button to
        **kwargs: Additional options

    Returns:
        The container widget that should be added to layouts
    """
    return add_option_box(widget, show_clear=True, **kwargs)


def add_menu_option(widget, menu, **kwargs):
    """Add a menu option to any widget.

    Args:
        widget: The widget to wrap
        menu: Menu object to show
        **kwargs: Additional options

    Returns:
        The container widget that should be added to layouts
    """
    # ``menu`` is not an OptionBox constructor argument; it configures a
    # MenuOption plugin. Passing it straight through raised TypeError.
    from .options.action import MenuOption

    return add_option_box(widget, options=[MenuOption(menu=menu)], **kwargs)


# -------------------------------------------------------------------------
# Widget patching for elegant usage
# -------------------------------------------------------------------------


def patch_widget_class(widget_class):
    """Add option_box attribute to a widget class."""

    def get_option_box(self):
        """Get or create option box manager"""
        if not hasattr(self, "_option_box_manager"):
            self._option_box_manager = OptionBoxManager(self)
        return self._option_box_manager

    # Only add if not already present
    if not hasattr(widget_class, "option_box"):
        widget_class.option_box = property(get_option_box)
    return widget_class


def patch_common_widgets():
    """Patch common Qt widgets with option box support."""
    common_widgets = [
        QtWidgets.QLineEdit,
        QtWidgets.QTextEdit,
        QtWidgets.QPlainTextEdit,
        QtWidgets.QPushButton,
        QtWidgets.QComboBox,
        QtWidgets.QSpinBox,
        QtWidgets.QDoubleSpinBox,
    ]

    for widget_class in common_widgets:
        patch_widget_class(widget_class)
