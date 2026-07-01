# !/usr/bin/python
# coding=utf-8
"""Disable option for OptionBox — the universal "disable this widget" button.

A small icon button beside any widget that toggles the wrapped widget's enabled
state. Unlike a bare :class:`ToggleOption`, ``DisableOption`` is the semantic
*inverse*: its "on" state means the wrapped widget is **enabled**, and clicking
**disables** it (plus any extra ``gated_widgets``). Crucially, the button itself
stays clickable while the widget is disabled — so the user can always re-enable
it. The icon tints to the project's "error" colour while disabled, so a disabled
control reads at a glance.

It uses the universal ``ban`` glyph (a circle with a diagonal slash) by default.

    le.option_box.set_disable()                       # disables `le` itself
    le.option_box.set_disable(gated_widgets=[other])  # also gate siblings
    le.options.disable()                              # fluent equivalent
"""

from typing import Iterable, Optional, Union

from .toggle import BinaryToggleOption


class DisableOption(BinaryToggleOption):
    """Universal disable button — toggles the wrapped widget's enabled state.

    A thin specialisation of :class:`BinaryToggleOption` (a *sibling* of
    :class:`ToggleOption`, not a subclass — see the base for why): it defaults to
    gating the wrapped widget (``gate_wrapped=True``), the universal ``ban`` icon,
    and "Enabled / Disabled" tooltips. The button stays live while the widget is
    disabled (inherited keep-alive behaviour), so re-enabling is always possible.

    Args:
        wrapped_widget: The widget to enable/disable.
        icon: Icon name (default ``"ban"``). Theme-coloured while enabled,
            tinted ``disabled_color`` while disabled.
        tooltip_on: Tooltip while the widget is enabled.
        tooltip_off: Tooltip while the widget is disabled.
        initial: Starting state (``True`` = enabled). Overridden by any
            persisted value.
        gate_wrapped: Include the wrapped widget in the gated set. Defaults to
            ``True`` (the whole point of this option); pass ``False`` to gate
            only ``gated_widgets``.
        gated_widgets: Additional widgets to disable alongside the wrapped one.
        disabled_color: Hex tint for the icon while disabled. ``None`` uses the
            project error red.
        active_color: Hex tint for the icon while enabled. ``None`` uses the
            auto theme colour.
        settings_key: Persistence namespace (see :class:`ToggleOption`).
        order: Explicit sort position. See :class:`BaseOption`.

    Signals:
        toggled(bool): Emitted when the state changes (``True`` = now enabled).
    """

    # Persist under a distinct app namespace so a DisableOption and a plain
    # ToggleOption on the same widget never collide on the auto-derived key.
    SETTINGS_APP = "DisableOption"

    def __init__(
        self,
        wrapped_widget=None,
        *,
        icon: str = "ban",
        tooltip_on: str = "Enabled. Click to disable.",
        tooltip_off: str = "Disabled. Click to enable.",
        initial: bool = True,
        gate_wrapped: bool = True,
        gated_widgets: Iterable = (),
        disabled_color: Optional[str] = None,
        active_color: Optional[str] = None,
        settings_key: Optional[Union[str, bool]] = None,
        order: Optional[int] = None,
    ):
        kwargs = dict(
            wrapped_widget=wrapped_widget,
            icon=icon,
            tooltip_on=tooltip_on,
            tooltip_off=tooltip_off,
            initial=initial,
            gate_wrapped=gate_wrapped,
            gated_widgets=gated_widgets,
            settings_key=settings_key,
            order=order,
        )
        if disabled_color is not None:
            kwargs["disabled_color"] = disabled_color
        if active_color is not None:
            kwargs["active_color"] = active_color
        super().__init__(**kwargs)
