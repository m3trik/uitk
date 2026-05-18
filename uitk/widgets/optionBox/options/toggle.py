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

import pythontk as ptk
from qtpy import QtCore

from ._options import ButtonOption
from ._persistence import PersistedOption


_DEFAULT_DISABLED_COLOR: str = ptk.Palette.status()["error"][0]  # soft coral


class ToggleOption(PersistedOption, ButtonOption):
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
        gated_widgets: Optional iterable of widgets to disable while the
            toggle is off. Caller owns lifecycle — toggle does not restore
            gated state on destruction.
        settings_key: Persistence namespace. ``str`` for explicit key,
            ``None`` to auto-derive from the wrapped widget's objectName,
            or ``False`` to opt out (consumer owns external storage).
        order: Explicit sort position. See :class:`BaseOption`.

    Signals:
        toggled(bool): Emitted whenever the on/off state changes from a
            user click or a ``set_on(...)`` call with ``emit=True``. Not
            emitted for initial-state or persisted-state restoration.
    """

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
        gated_widgets: Iterable = (),
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
        self._disabled_color = disabled_color
        self._gated_widgets = list(gated_widgets)
        self._is_on = bool(initial)

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
        self._apply_gating()
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
        # Apply current state visuals + gating now that the widget exists.
        # Done unconditionally on setup so initial=False is reflected.
        self._apply_visuals()
        self._apply_gating()

    def _handle_click(self):
        # User-driven flip — delegate to set_on so post-state work
        # (visuals, gating, persistence, emission) lives in one place.
        self.set_on(not self._is_on)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_visuals(self):
        if not self._widget:
            return
        from uitk.widgets.mixins.icon_manager import IconManager

        if self._is_on:
            IconManager.swap_icon(
                self._widget,
                self._icon_on,
                color=None,
                auto_theme=True,
                fallback_size=(15, 15),
            )
            self._widget.setToolTip(self._tooltip_on)
        else:
            IconManager.swap_icon(
                self._widget,
                self._icon_off,
                color=self._disabled_color,
                auto_theme=False,
                fallback_size=(15, 15),
            )
            self._widget.setToolTip(self._tooltip_off)

    def _apply_gating(self):
        for w in self._gated_widgets:
            try:
                w.setEnabled(self._is_on)
            except RuntimeError:
                # Underlying C++ widget already deleted; skip.
                pass

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
