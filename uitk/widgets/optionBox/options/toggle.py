# !/usr/bin/python
# coding=utf-8
"""Toggle option for OptionBox — a persisted binary on/off button.

Unlike :class:`ActionOption` (a one-shot or N-state cycling action), a
:class:`ToggleOption` is a *stateful* boolean. The icon dims to the project's
"error" red while off so the user can see which control caused a dependent
widget / filter / process to stop working.

Common pattern (line-edit filter gate)::

    le.option_box.add_toggle(
        icon="filter",
        tooltip_on="Filter enabled. Click to disable.",
        tooltip_off="Filter disabled. Click to enable.",
        initial=current_flag,
    )
    le.option_box.find_option(ToggleOption).toggled.connect(on_filter_changed)

The toggle does *not* clear or disable its wrapped widget by default — that
loses user input. Pass ``gated_widgets=[le]`` if you genuinely want the
wrapped control disabled while off (e.g. a write-only field).
"""

from typing import Iterable, Optional, Union

from qtpy import QtCore

from ._options import ButtonOption, GatingMixin, _DEFAULT_DISABLED_COLOR
from ._persistence import PersistedOption


class BinaryToggleOption(GatingMixin, PersistedOption, ButtonOption):
    """Shared base for binary on/off option buttons.

    Implements the full state machine — ``is_on`` / :meth:`set_on`, click
    handling, persistence, gating, and the icon/tooltip swap — for any option
    that is fundamentally a *stateful boolean*. :class:`ToggleOption` (a generic
    persisted toggle) and :class:`DisableOption` (the universal "disable this
    widget" button) are **siblings** built on this base, rather than one being a
    subclass of the other. Keeping them siblings is deliberate: it avoids an
    ``isinstance`` subclass relationship between two concrete option types, which
    (because the option hierarchy uses ``ABCMeta``) can trip CPython's abc
    subclass-cache and intermittently mis-report ``issubclass``. ``_sort_options``
    keys off the two leaf classes (see ``_optionBox._TYPE_TO_KEY``) so both still
    group as a "toggle".

    Subclasses typically only set ``SETTINGS_APP`` and tweak the default icon /
    tooltips / gating; the constructor and behaviour live here (see
    :class:`ToggleOption` for the full argument reference)."""

    SETTINGS_APP = "ToggleOption"

    toggled = QtCore.Signal(bool)

    def __init__(
        self,
        wrapped_widget=None,
        *,
        icon: str = "filter",
        icon_off: Optional[str] = None,
        tooltip_on: str = "Enabled. Click to disable.",
        tooltip_off: str = "Disabled. Click to enable.",
        initial: bool = True,
        disabled_color: str = _DEFAULT_DISABLED_COLOR,
        active_color: Optional[str] = None,
        gated_widgets: Iterable = (),
        gate_wrapped: bool = False,
        keep_enabled_when_wrapped_disabled: bool = True,
        settings_key: Optional[Union[str, bool]] = None,
        order: Optional[int] = None,
    ):
        # callback=None — we wire ``clicked → _handle_click`` ourselves in
        # ``setup_widget`` to avoid the bound-method storage that
        # ``ButtonOption`` does when ``callback`` is truthy. Storing the
        # bound method would create a self→callback→self reference cycle
        # purely to satisfy ButtonOption's ``if self.callback:`` gate.
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon=icon,
            tooltip=tooltip_on,
            callback=None,
            order=order,
        )
        self._icon_on = icon
        self._icon_off = icon_off or icon
        self._tooltip_on = tooltip_on
        self._tooltip_off = tooltip_off
        self._is_on = bool(initial)

        # Gating behaviour (gated widgets, keep-live flag, disabled tint, icon
        # swap) lives in GatingMixin — shared by both subclasses.
        self._init_gating(
            gated_widgets=gated_widgets,
            gate_wrapped=gate_wrapped,
            disabled_color=disabled_color,
            active_color=active_color,
            keep_enabled_when_wrapped_disabled=keep_enabled_when_wrapped_disabled,
        )

        self._init_persistence(settings_key)
        self._load_state()  # may override _is_on before any UI exists

    # ------------------------------------------------------------------
    # Public state API
    # ------------------------------------------------------------------

    @property
    def is_on(self) -> bool:
        """Current state. ``True`` = enabled, ``False`` = disabled."""
        return self._is_on

    def set_on(self, value: bool, *, emit: bool = True) -> None:
        """Programmatically set the toggle state.

        Args:
            value: Target state.
            emit: When ``True`` (default), emit :attr:`toggled` if state
                actually changed. Pass ``False`` for silent restoration
                (preset loading, settings sync, test setup).
        """
        new = bool(value)
        if new == self._is_on:
            return
        self._is_on = new
        self._apply_visuals()
        self._apply_gating(self._is_on)
        self._save_state()
        if emit:
            self.toggled.emit(self._is_on)

    # ------------------------------------------------------------------
    # ButtonOption overrides
    # ------------------------------------------------------------------

    def setup_widget(self):
        # ButtonOption.setup_widget is a no-op here (callback=None passed in
        # __init__). Wire the click ourselves so the single connection target
        # is unambiguous and the bound method isn't stored on ``self.callback``.
        super().setup_widget()
        self._widget.clicked.connect(self._handle_click)
        # Keep the button clickable even when its wrapped widget is disabled
        # (otherwise gate_wrapped / an externally-disabled host would trap it).
        self._install_keep_enabled()
        # Apply current state visuals + gating now that the widget exists.
        # Done unconditionally on setup so initial=False is reflected.
        self._apply_visuals()
        self._apply_gating(self._is_on)

    def _handle_click(self):
        # User-driven flip — delegate to set_on so post-state work
        # (visuals, gating, persistence, emission) lives in one place.
        self.set_on(not self._is_on)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_visuals(self):
        # Icon/tooltip swap lives in GatingMixin._apply_icon_state.
        self._apply_icon_state(
            self._is_on,
            self._icon_on,
            self._icon_off,
            tooltip_active=self._tooltip_on,
            tooltip_inactive=self._tooltip_off,
        )

    def _save_state(self):
        if not self._settings:
            return
        self._settings.setValue("is_on", bool(self._is_on))
        self._settings.sync()

    def _load_state(self):
        if not self._settings:
            return
        saved = self._settings.value("is_on")
        if saved is None:
            return
        # QSettings stringifies bools on some backends.
        if isinstance(saved, str):
            saved = saved.lower() in ("1", "true", "yes")
        self._is_on = bool(saved)


class ToggleOption(BinaryToggleOption):
    """Persisted binary toggle button.

    Args:
        wrapped_widget: The widget this option is attached to (used for
            objectName-based persistence keying and parenting).
        icon: Icon name (drawn theme-coloured when on, dimmed-red when off).
            Defaults to ``"filter"`` since that is the most common toggle
            use-case; pass any other icon name for non-filter toggles.
        icon_off: Optional alternate icon shown in the off state. When omitted
            the same icon is shown in the off-state color.
        tooltip_on: Tooltip while the toggle is on.
        tooltip_off: Tooltip while the toggle is off.
        initial: Starting state (default ``True``). Overridden by any value
            previously persisted under ``settings_key``.
        disabled_color: Hex string used to tint the icon when off. Defaults
            to ``pythontk.Palette.status()["error"][0]`` (soft coral red fg).
        active_color: Hex string used to tint the icon when on. ``None``
            (default) uses the auto theme colour.
        gated_widgets: Optional iterable of widgets to disable while the
            toggle is off. Caller owns lifecycle — toggle does not restore
            gated state on destruction.
        gate_wrapped: When ``True``, the wrapped widget itself is included in
            the gated set (disabled while off). Pairs with
            ``keep_enabled_when_wrapped_disabled`` so the button stays live.
        keep_enabled_when_wrapped_disabled: When ``True`` (default), the toggle
            button stays clickable even when the wrapped widget is disabled —
            so a toggle that disables its own row can always re-enable it. The
            container's enabled-sync honours this via the
            ``keepEnabledWhenWrappedDisabled`` widget property.
        settings_key: Persistence namespace. ``str`` for explicit key,
            ``None`` to auto-derive from the wrapped widget's objectName,
            or ``False`` to opt out (consumer owns external storage).
        order: Explicit sort position. See :class:`BaseOption`.

    Signals:
        toggled(bool): Emitted whenever the on/off state changes from a
            user click or a ``set_on(...)`` call with ``emit=True``. Not
            emitted for initial-state or persisted-state restoration.
    """

    # The full state machine lives in BinaryToggleOption; ToggleOption is the
    # generic persisted toggle (filter-style defaults inherited from the base).
    SETTINGS_APP = "ToggleOption"
