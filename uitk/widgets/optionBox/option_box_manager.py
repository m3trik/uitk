# !/usr/bin/python
# coding=utf-8
"""The :class:`OptionBoxManager` facade -- ``widget.option_box``.

The fluent option API (``set_action`` / ``set_toggle`` / ``set_filter`` /
``set_reset`` / ``browse`` ...) and the class-level factories live here; the
menu binding (:mod:`._menu_binding`) and the deferred wrap
(:mod:`._deferred_wrap`) are partials this class composes.
"""

from qtpy import QtWidgets, QtCore
from typing import Optional, Union
import pythontk as ptk
from ._optionBox import DEFAULT_OPTION_ORDER

from ._menu_binding import _OptionBoxMenuMixin
from ._deferred_wrap import _OptionBoxWrapMixin


class OptionBoxManager(_OptionBoxMenuMixin, _OptionBoxWrapMixin, ptk.LoggingMixin):
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
        # Shared default placement (see DEFAULT_OPTION_ORDER) -- "value" first
        # so an inline ValueOption field sits flush against the wrapped widget,
        # ahead of every icon button, then "clear" leading the icon buttons.
        self._option_order = list(DEFAULT_OPTION_ORDER)
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

        valid_options = set(DEFAULT_OPTION_ORDER)
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
        self._pending_options = [o for o in self._pending_options if not predicate(o)]
        if self._option_box:
            for o in [o for o in self._option_box.get_options() if predicate(o)]:
                self._option_box.remove_option(o)

    def set_action(
        self,
        callback=None,
        icon="menu",
        tooltip="Options",
        text=None,
        replace=True,
        states=None,
        settings_key=None,
    ):
        """Set the action handler (fluent interface).

        Args:
            callback: Function or object to call/trigger when clicked
            icon: Icon name for the button (default: "menu"; pass
                "option_box" explicitly for a Maya-style option box)
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
                lambda opt: (
                    isinstance(opt, ActionOption) and not isinstance(opt, MenuOption)
                )
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
        icon="menu",
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
            icon: Icon name for the button (default: "menu"; pass
                "option_box" explicitly for a Maya-style option box)
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

    def add_choice(self, **kwargs):
        """Add a filter facet: an icon button picking one value from a popup.

        Never replaces: a filter row carries one :class:`ChoiceOption` per
        dimension it narrows by (a collection, a status, a tag), in the order
        they are added, after the filter's on/off toggle. See
        :class:`~uitk.widgets.optionBox.options.choice.ChoiceOption` for the
        keyword arguments (``icon``, ``label``, ``choices``, ``default``,
        ``on_changed``, ``settings`` / ``settings_key``).

        Returns:
            The created :class:`ChoiceOption` -- keep it to read ``value`` and
            to ``refresh()`` it after the data its choices come from changes.
        """
        from uitk.widgets.optionBox.options.choice import ChoiceOption

        option = ChoiceOption(wrapped_widget=self._widget, **kwargs)
        self.add_option(option)
        return option

    def set_disable(
        self,
        *,
        icon: str = "ban",
        tooltip_on: str = "Enabled. Click to disable.",
        tooltip_off: str = "Disabled. Click to enable.",
        initial: bool = True,
        gate_wrapped: bool = True,
        gated_widgets=(),
        suppress_value: bool = True,
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

        On a text field it also empties the field while disabled (holding the
        value aside until re-enabled), so a disabled value cannot be read back
        by anything — see ``suppress_value``.

        Args:
            icon: Icon name (default ``"ban"``).
            tooltip_on / tooltip_off: Tooltips for the enabled / disabled states.
            initial: Starting state (``True`` = enabled). Overridden by any
                persisted value.
            gate_wrapped: Disable the wrapped widget itself (default ``True``).
            gated_widgets: Additional widgets to disable in sync.
            suppress_value: Hold the wrapped text field's value aside and empty
                it while disabled (default ``True``), so every reader sees an
                unset field. Text hosts only; a no-op elsewhere.
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
            suppress_value=suppress_value,
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
        modes=None,
        convention_key=None,
        on_change=None,
        tooltip: Optional[str] = None,
        settings_key=None,
        order=None,
        replace: bool = True,
    ):
        """Add an inline affix-mode picker — fluent.

        Turns the wrapped text field into an affix entry with a cycling icon
        button beside it declaring how the field's text applies to a base name.
        The cycle is the three built-in modes (Auto → Suffix → Prefix) unless
        *modes* or *convention_key* says otherwise. The manual parsing lives in
        ``pythontk.StrUtils.split_affix``; read the selection back with
        :attr:`affix_mode` / :meth:`resolve_affix`. Requires a text-bearing
        host (skipped + warned otherwise — see
        :meth:`AffixOption.is_compatible`).

        Args:
            default: Initial mode key. A mode persisted by a previous session
                overrides it.
            modes: The cycle, as built-in keys and/or ``AffixMode`` instances.
                ``None`` uses the three built-ins. Pass e.g.
                ``("suffix", "prefix")`` for a two-state picker, or include a
                custom ``AffixMode`` for a state of your own.
            convention_key: Shorthand for appending a fourth, *custom* state
                bound to ``pythontk.NamingConvention`` for that type key — the
                field then shows the shared convention's affix and goes
                read-only (still enabled, so the value reads) while selected.
                Pass a ``() -> key`` callable for a field whose target type is
                not fixed (the locator rig's child is a mesh or a camera
                depending on what is selected): it is resolved per read, and
                showing the box re-pulls, so the field previews what the
                current target would get. Ignored when *modes* is given
                explicitly.
            on_change: Optional callable invoked with the new mode string
                whenever the user changes the picker. It does NOT fire for the
                restore of a persisted mode (nothing the user just did) — read
                :attr:`affix_mode` once after this call to sync anything the
                mode drives (a placeholder, a dependent label).
            tooltip: Static tooltip override (defaults to a per-state tooltip
                naming the current mode).
            settings_key: Persistence namespace for the selected mode. ``None``
                auto-derives from the field's ``objectName`` — pass an explicit
                string for a generic name (``txt000``), ``False`` to opt out.
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
                modes=modes,
                convention_key=convention_key,
                on_change=on_change,
                settings_key=settings_key,
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

    def resolve_affix(self, text: Optional[str] = None, *, default: str = "prefix"):
        """Return ``(prefix, suffix)`` for the wrapped field under its mode.

        Reads the wrapped widget's text and the AffixOption's mode (``"auto"``
        when no picker was added) and splits via that mode — for the three
        built-ins, ``pythontk.StrUtils.split_affix``; a custom mode answers from
        its own source. *text* overrides the widget's text —
        e.g. to fall back to the field's ``placeholderText()`` when it is empty.
        *default* is the fallback mode used when Auto is selected but the text
        has no boundary delimiter.
        """
        from uitk.widgets.optionBox.options.affix import AffixOption

        option = self.find_option(AffixOption)
        if option is not None:
            return option.resolve(text, default=default)
        if text is None:
            text = self._widget.text() if hasattr(self._widget, "text") else ""
        return ptk.StrUtils.split_affix(text, mode="auto", default=default)

    def set_reset(
        self,
        *,
        reset=None,
        icon: str = "undo",
        tooltip: Optional[str] = None,
        tooltip_bypassed: Optional[str] = None,
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
            tooltip / tooltip_bypassed: Tooltips for the active / bypassed states
                (``None`` = :class:`ResetOption`'s own defaults).
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
        )
        if tooltip is not None:
            kwargs["tooltip"] = tooltip
        if tooltip_bypassed is not None:
            kwargs["tooltip_bypassed"] = tooltip_bypassed
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

    def get_options(self):
        """Every option on this widget — pending (not yet wrapped) and live."""
        options = list(self._pending_options)
        if self._option_box:
            options.extend(self._option_box.get_options())
        return options

    def restore_option_defaults(self):
        """Ask every option to return its own state to its default.

        The field-level counterpart to a value reset (see
        ``BaseOption.restore_default``): clears a lock / disable toggle while
        leaving user data — pinned and recent values — alone. Called by a
        panel-wide ``StateManager.reset_all``; the per-field reset button goes
        through ``ResetOption`` instead, which skips itself.
        """
        self._each_option("restore_default")
        return self

    def save_option_defaults(self) -> int:
        """Make every option's current state its default (``BaseOption.save_default``).

        The save half of what :meth:`restore_option_defaults` resets, reached
        by a panel-wide *Save as Defaults*. Returns how many options wrote one.
        """
        return self._each_option("save_default")

    def clear_option_defaults(self) -> int:
        """Forget every option's saved default (``BaseOption.clear_saved_default``).

        A factory reset, which runs before the values are restored. Returns how
        many saved defaults were removed.
        """
        return self._each_option("clear_saved_default")

    def _each_option(self, method: str) -> int:
        """Call *method* on every option; count the truthy answers.

        One bad plugin must not eat the batch, so each call is guarded
        individually and logged at debug.
        """
        done = 0
        for option in self.get_options():
            try:
                done += bool(getattr(option, method)())
            except Exception as e:
                self.logger.debug(f"{method} failed on {option!r}: {e}")
        return done

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

    # -------------------------------------------------------------------------
    # Convenience factories & widget patching (class-only public surface)
    # -------------------------------------------------------------------------

    @staticmethod
    def add_option_box(widget, show_clear=False, options=None, **kwargs):
        """Add an option box to any widget with one call.

        Args:
            widget: The widget to wrap
            show_clear: Whether to show clear button for text widgets
            options: List of option plugins to add
            **kwargs: Additional options

        Returns:
            The container widget that should be added to layouts

        Example:
            line_edit = QtWidgets.QLineEdit()
            container = OptionBoxManager.add_option_box(line_edit, show_clear=True)
            layout.addWidget(container)
        """
        from ._optionBox import OptionBox

        option_box = OptionBox(show_clear=show_clear, options=options, **kwargs)
        return option_box.wrap(widget)

    @staticmethod
    def add_clear_option(widget, **kwargs):
        """Add just a clear button to a text widget.

        Args:
            widget: The text widget to add clear button to
            **kwargs: Additional options

        Returns:
            The container widget that should be added to layouts
        """
        return OptionBoxManager.add_option_box(widget, show_clear=True, **kwargs)

    @staticmethod
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

        return OptionBoxManager.add_option_box(
            widget, options=[MenuOption(menu=menu)], **kwargs
        )

    @staticmethod
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

    @staticmethod
    def patch_common_widgets():
        """Patch common Qt widgets with option box support."""
        common_widgets = [
            QtWidgets.QLineEdit,
            QtWidgets.QTextEdit,
            QtWidgets.QPlainTextEdit,
            QtWidgets.QPushButton,
            QtWidgets.QCheckBox,
            QtWidgets.QComboBox,
            QtWidgets.QSpinBox,
            QtWidgets.QDoubleSpinBox,
        ]

        for widget_class in common_widgets:
            OptionBoxManager.patch_widget_class(widget_class)
