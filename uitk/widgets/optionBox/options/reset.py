# !/usr/bin/python
# coding=utf-8
"""Reset option for OptionBox — one-click reset-to-default, with a modifier-gated
"hold at default" (bypass) toggle.

A small icon button beside any value widget. A **plain click resets the wrapped
widget to its registry default** (a normal, persisted reset). Hold **Alt or
Ctrl** while clicking to instead **bypass** the parameter: the option snapshots
the current value, resets to default *transiently* (the persisted value stays
the user's), and greys the widget out; the icon goes the project "error" red so
bypassed parameters read at a glance. Clicking a bypassed button restores the
snapshot and re-enables the widget.

Bypass is non-persistent: each session starts un-bypassed, so a panel never
reopens with parameters mysteriously held at default.

The "default" is resolved automatically from the wrapped widget's window
``StateManager`` (``window.state.reset(widget)``) when no explicit ``reset``
callable is supplied — so on a uitk panel ``widget.option_box.set_reset()``
just works.

    sb.option_box.set_reset()                       # auto (window StateManager)
    sb.option_box.set_reset(reset=my_reset_func)    # explicit
"""
from typing import Callable, Optional

import pythontk as ptk
from qtpy import QtCore, QtWidgets

from ._options import ButtonOption
from uitk.managers.value_manager import ValueManager


_DEFAULT_DISABLED_COLOR: str = ptk.Palette.status()["error"][0]  # soft coral

# Holding either of these while clicking switches a plain reset into the
# bypass (hold-at-default) toggle.
_DEFAULT_BYPASS_MODIFIER = QtCore.Qt.AltModifier | QtCore.Qt.ControlModifier


class ResetOption(ButtonOption):
    """Reset-to-default button with a modifier-gated *bypass* toggle.

    Plain click resets the wrapped widget to its default (persisted). Hold a
    modifier (``Alt`` or ``Ctrl`` by default) while clicking to toggle *bypass*
    — snapshot the value, reset to default transiently, and grey the widget
    out; click the bypassed button again to restore.

    Args:
        wrapped_widget: The widget this option resets/bypasses.
        reset: Optional callable applied to put the widget at its default. When
            ``None``, the wrapped widget's window ``StateManager`` is used
            (``window.state.reset(widget)``).
        icon: Icon name (theme-coloured normally, ``disabled_color`` while
            bypassed).
        tooltip: Tooltip while active (plain reset / modifier bypass).
        tooltip_bypassed: Tooltip while bypassed (click to restore).
        disabled_color: Hex tint for the icon while bypassed. Defaults to
            ``pythontk.Palette.status()["error"][0]``.
        bypass_modifier: Keyboard modifier(s) that switch a click from reset to
            the bypass toggle. Defaults to ``Alt | Ctrl``.
        order: Explicit sort position. See :class:`BaseOption`.

    Signals:
        toggled(bool): Emitted when the bypass state changes (``True`` = now
            bypassed / held at default). A plain reset does not emit.
    """

    toggled = QtCore.Signal(bool)

    def __init__(
        self,
        wrapped_widget=None,
        *,
        reset: Optional[Callable] = None,
        icon: str = "undo",
        tooltip: str = "Reset to default.    Alt/Ctrl+click: hold at default (bypass).",
        tooltip_bypassed: str = "Held at default (bypassed). Click to restore your value.",
        disabled_color: str = _DEFAULT_DISABLED_COLOR,
        bypass_modifier: QtCore.Qt.KeyboardModifier = _DEFAULT_BYPASS_MODIFIER,
        order: Optional[int] = None,
    ):
        # callback=None: we wire clicked -> _handle_click ourselves (mirrors
        # ToggleOption) and track the bypass state internally rather than via a
        # checkable button, so there's no Qt checked-state to keep in sync.
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon=icon,
            tooltip=tooltip,
            callback=None,
            order=order,
        )
        self._reset = reset
        self._icon = icon
        self._tooltip = tooltip
        self._tooltip_bypassed = tooltip_bypassed
        self._disabled_color = disabled_color
        self._bypass_modifier = bypass_modifier
        self._is_bypassed = False
        self._saved = None  # in-memory snapshot of the user's value while bypassed

    # ------------------------------------------------------------------ state
    @property
    def is_bypassed(self) -> bool:
        """``True`` while the parameter is bypassed (held at its default)."""
        return self._is_bypassed

    def reset(self) -> None:
        """Reset the wrapped widget to its default (one-shot, persisted).

        This is the plain-click action; unlike :meth:`set_bypassed` it does not
        snapshot, grey out, or suppress persistence — the default is the value
        the user chose, so it should stick.
        """
        self._apply_reset(suppress=False)

    def set_bypassed(self, value: bool, *, emit: bool = True) -> None:
        """Bypass (``True``) or restore (``False``) the widget.

        Bypassing snapshots the current value, resets it to default
        *transiently* (the persisted value stays the user's), and greys the
        widget out. Pass ``emit=False`` for a silent change (preset restore,
        tests).
        """
        new = bool(value)
        if new == self._is_bypassed:
            return
        self._is_bypassed = new
        w = self.wrapped_widget
        if new:
            # Snapshot the user's value, reset to default, then grey out.
            self._saved = self._capture_value()
            self._apply_reset(suppress=True)
            if w is not None:
                w.setEnabled(False)
                # Registered *after* the reset above so that reset doesn't fire
                # the hook on ourselves. Lets a centralized reset-to-default
                # (window StateManager.reset_all) refresh our snapshot while
                # bypassed, so we don't restore a stale value over the reset.
                w.sync_stored_default = self._on_external_reset
        else:
            # Re-enable and restore the snapshot, emitting the widget's value
            # signal so a connected slot / live preview re-runs (same as the
            # reset path did on the way in).
            if w is not None:
                w.setEnabled(True)
                w.sync_stored_default = None
            if self._saved is not None:
                self._apply_value(self._saved)
        self._apply_visuals()
        if emit:
            self.toggled.emit(new)

    def _on_external_reset(self, default_value):
        """A centralized reset ran while bypassed: refresh the snapshot to the
        new default so a later restore yields the default, not the stale value.

        Re-reads the widget (the reset just set it to its default) so the
        snapshot is the default in the widget's native type — ``default_value``
        may be a raw persisted form.
        """
        self._saved = self._capture_value()

    # ------------------------------------------------------ ButtonOption hooks
    def setup_widget(self):
        super().setup_widget()  # no-op (callback=None)
        # Bypass greys out the wrapped widget itself, which would otherwise
        # cascade-disable this very button (via the container's enabled-sync)
        # and trap the toggle. Opt out so the button stays clickable to restore.
        self._widget.setProperty("keepEnabledWhenWrappedDisabled", True)
        self._widget.clicked.connect(self._handle_click)
        self._apply_visuals()

    def _handle_click(self):
        # While bypassed, any click restores: the greyed row's only live control
        # shouldn't be a confusing no-op (a plain reset would be — the value is
        # already at default).
        if self._is_bypassed:
            self.set_bypassed(False)
            return
        if self._current_modifiers() & self._bypass_modifier:
            self.set_bypassed(True)
        else:
            self.reset()

    def _current_modifiers(self):
        """Active keyboard modifiers at click time (seam for testing/DI)."""
        return QtWidgets.QApplication.keyboardModifiers()

    # ----------------------------------------------------- value (type-correct)
    def _signal_name(self):
        """The wrapped widget's Switchboard default-signal name, if registered.

        Registered uitk widgets carry a ``default_signals()`` lambda (set by
        ``MainWindow``) returning the signal name slots are wired to for that
        widget *type* — e.g. ``valueChanged`` (spin box), ``toggled`` (check
        box), ``currentIndexChanged`` (combo box). ``None`` for unregistered
        widgets, where the generic value accessors are used instead.
        """
        getter = getattr(self.wrapped_widget, "default_signals", None)
        if not callable(getter):
            return None
        try:
            return getter()
        except Exception:
            return None

    def _capture_value(self):
        """Read the wrapped widget's value by its type's value signal.

        Using the signal-keyed getter round-trips correctly with
        :meth:`_apply_value` — e.g. a combo box snapshots its *index* (not the
        display text) and a check box its *checked state* (not its label).
        """
        w = self.wrapped_widget
        name = self._signal_name()
        if name:
            return ValueManager.get_value_by_signal(w, name)
        return ValueManager.get_value(w)

    def _apply_value(self, value):
        """Set *value* on the wrapped widget, emitting its type's value signal.

        Routing through the widget's default signal (rather than a generic
        setter) guarantees the change reaches the slot the Switchboard
        connected for that widget type — otherwise the value changes silently
        (e.g. a combo box restored by index fires ``currentIndexChanged``).
        """
        w = self.wrapped_widget
        name = self._signal_name()
        if name:
            ValueManager.set_value_by_signal(w, value, name)
        else:
            ValueManager.set_value(w, value)

    # ---------------------------------------------------------------- internal
    def _apply_reset(self, *, suppress: bool):
        """Put the wrapped widget at its default — via the injected ``reset``,
        else the wrapped widget's window ``StateManager``.

        ``suppress`` wraps the StateManager reset in ``suppress_save()`` (when
        present) so the *persisted* value stays the user's real one. The bypass
        path passes ``suppress=True`` (a transient hold: closing while bypassed
        doesn't bury the value at its default, and any live preview still
        re-runs); a plain reset passes ``suppress=False`` so the default
        actually persists — the user deliberately chose it. An injected
        ``reset`` callable owns its own persistence semantics either way."""
        if self._reset is not None:
            self._reset()
            return
        w = self.wrapped_widget
        state = getattr(self._find_parent_window(), "state", None)
        if w is None or state is None or not hasattr(state, "reset"):
            return
        suppress_save = getattr(state, "suppress_save", None)
        if suppress and callable(suppress_save):
            with suppress_save():
                state.reset(w)
        else:
            state.reset(w)

    def _apply_visuals(self):
        if not self._widget:
            return
        from uitk.managers.icon_manager import IconManager

        if self._is_bypassed:
            IconManager.swap_icon(
                self._widget,
                self._icon,
                color=self._disabled_color,
                auto_theme=False,
                fallback_size=(15, 15),
            )
            self._widget.setToolTip(self._tooltip_bypassed)
        else:
            IconManager.swap_icon(
                self._widget,
                self._icon,
                color=None,
                auto_theme=True,
                fallback_size=(15, 15),
            )
            self._widget.setToolTip(self._tooltip)
