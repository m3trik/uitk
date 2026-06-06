# !/usr/bin/python
# coding=utf-8
"""Disable option for OptionBox — a per-widget "bypass to default" toggle.

A one-click way to neutralise a single parameter. When turned **on** the option
snapshots the wrapped widget's current value, resets it to its registry default,
and greys the widget out; when turned **off** it restores the snapshot and
re-enables the widget. The icon goes the project "error" red while disabled so
it reads at a glance which parameters are bypassed.

Non-persistent by default: each session starts active, so a panel never reopens
with parameters mysteriously disabled (pass ``settings_key`` only if you build a
persisted variant on top of this).

The "default" is resolved automatically from the wrapped widget's window
``StateManager`` (``window.state.reset(widget)``) when no explicit ``reset``
callable is supplied — so on a uitk panel ``widget.option_box.set_disable()``
just works.

    sb.option_box.set_disable()                       # auto (window StateManager)
    sb.option_box.set_disable(reset=my_reset_func)    # explicit
"""
from typing import Callable, Optional

import pythontk as ptk
from qtpy import QtCore

from ._options import ButtonOption
from uitk.widgets.mixins.value_manager import ValueManager


_DEFAULT_DISABLED_COLOR: str = ptk.Palette.status()["error"][0]  # soft coral


class DisableOption(ButtonOption):
    """Per-widget bypass toggle: reset-to-default + grey-out when on.

    Args:
        wrapped_widget: The widget this option bypasses (read/reset/restore).
        reset: Optional callable applied to put the widget at its default when
            the toggle goes on. When ``None``, the wrapped widget's window
            ``StateManager`` is used (``window.state.reset(widget)``).
        icon: Icon name (theme-coloured while active, ``disabled_color`` while
            disabled).
        tooltip_off: Tooltip while active (click to disable).
        tooltip_on: Tooltip while disabled (click to restore).
        disabled_color: Hex tint for the icon while disabled. Defaults to
            ``pythontk.Palette.status()["error"][0]``.
        order: Explicit sort position. See :class:`BaseOption`.

    Signals:
        toggled(bool): Emitted on a user click or ``set_disabled(..., emit=True)``;
            ``True`` means the parameter is now disabled (at default).
    """

    toggled = QtCore.Signal(bool)

    def __init__(
        self,
        wrapped_widget=None,
        *,
        reset: Optional[Callable] = None,
        icon: str = "undo",
        tooltip_off: str = "Disable: reset this value to its default.",
        tooltip_on: str = "Disabled (at default). Click to restore your value.",
        disabled_color: str = _DEFAULT_DISABLED_COLOR,
        order: Optional[int] = None,
    ):
        # callback=None: we wire clicked -> _handle_click ourselves (mirrors
        # ToggleOption) and track state internally rather than via a checkable
        # button, so there's no Qt checked-state to keep in sync.
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon=icon,
            tooltip=tooltip_off,
            callback=None,
            order=order,
        )
        self._reset = reset
        self._icon = icon
        self._tooltip_off = tooltip_off
        self._tooltip_on = tooltip_on
        self._disabled_color = disabled_color
        self._is_disabled = False
        self._saved = None  # in-memory snapshot of the user's value while disabled

    # ------------------------------------------------------------------ state
    @property
    def is_disabled(self) -> bool:
        """``True`` while the parameter is bypassed (held at its default)."""
        return self._is_disabled

    def set_disabled(self, value: bool, *, emit: bool = True) -> None:
        """Programmatically bypass (``True``) or restore (``False``) the widget.

        Pass ``emit=False`` for a silent change (preset restore, tests).
        """
        new = bool(value)
        if new == self._is_disabled:
            return
        self._is_disabled = new
        w = self.wrapped_widget
        if new:
            # Snapshot the user's value, reset to default, then grey out.
            self._saved = ValueManager.get_value(w)
            self._apply_reset()
            if w is not None:
                w.setEnabled(False)
        else:
            # Re-enable and restore the snapshot (drives the same valueChanged
            # the reset did, so a live preview re-runs either way).
            if w is not None:
                w.setEnabled(True)
            if self._saved is not None:
                ValueManager.set_value(w, self._saved)
        self._apply_visuals()
        if emit:
            self.toggled.emit(new)

    # ------------------------------------------------------ ButtonOption hooks
    def setup_widget(self):
        super().setup_widget()  # no-op (callback=None)
        self._widget.clicked.connect(self._handle_click)
        self._apply_visuals()

    def _handle_click(self):
        self.set_disabled(not self._is_disabled)

    # ---------------------------------------------------------------- internal
    def _apply_reset(self):
        """Put the wrapped widget at its default — via the injected ``reset``,
        else the wrapped widget's window ``StateManager``.

        The StateManager reset is wrapped in ``suppress_save()`` (when present)
        so the *persisted* value stays the user's real one — the disable is
        transient, matching the non-persistent toggle: closing while disabled
        doesn't bury the value at its default. The widget still shows the
        default and any live preview still re-runs (only the persistence save
        is suppressed, not the widget's other ``valueChanged`` listeners)."""
        if self._reset is not None:
            self._reset()
            return
        w = self.wrapped_widget
        state = getattr(self._find_parent_window(), "state", None)
        if w is None or state is None or not hasattr(state, "reset"):
            return
        suppress = getattr(state, "suppress_save", None)
        if callable(suppress):
            with suppress():
                state.reset(w)
        else:
            state.reset(w)

    def _apply_visuals(self):
        if not self._widget:
            return
        from uitk.widgets.mixins.icon_manager import IconManager

        if self._is_disabled:
            IconManager.swap_icon(
                self._widget,
                self._icon,
                color=self._disabled_color,
                auto_theme=False,
                fallback_size=(15, 15),
            )
            self._widget.setToolTip(self._tooltip_on)
        else:
            IconManager.swap_icon(
                self._widget,
                self._icon,
                color=None,
                auto_theme=True,
                fallback_size=(15, 15),
            )
            self._widget.setToolTip(self._tooltip_off)
