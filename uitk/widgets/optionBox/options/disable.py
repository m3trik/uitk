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

Value suppression — "disabled" means *no value*
-----------------------------------------------
On a text host (``QLineEdit`` / ``QTextEdit`` / ``QPlainTextEdit``) the button
also **holds the field's value aside and empties the field** (``suppress_value``,
on by default). That is the point of the button: a temporarily disabled field
must not still be read. Because the field is genuinely empty, *every* reader —
``text()``, ``option_box.resolve_affix()``, a slot that never heard of this
button — takes the same "not set" branch it already takes for a field the user
left blank. Clicking again puts the value back; the held text is persisted
beside the on/off flag, so a field left disabled still hands its value back in
the next session.

Emptying, rather than shadowing the accessor, is deliberate: a widget whose
``text()`` lied would break its own validator, its clear button, and the state
persistence that reads the same accessor. Since the field can no longer show
what it is holding, the button's tooltip names it.

Suppression covers the *wrapped* widget only; extra ``gated_widgets`` are
disabled but keep their values (give one its own ``DisableOption`` to suppress
it). A hidden data payload (``LineEdit.set_value(value, display=…)``) is held
for the session but not persisted — only the text is.
"""

from typing import Any, Iterable, Optional, Tuple, Union

from qtpy import QtWidgets

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
        suppress_value: Hold the wrapped widget's value aside and empty the
            field while disabled, so nothing can read it (default ``True``).
            Applies to text hosts only (:attr:`SUPPRESSIBLE_TYPES`) and only
            when ``gate_wrapped``; a no-op elsewhere. See the module docstring.
        disabled_color: Hex tint for the icon while disabled. ``None`` uses the
            project error red.
        active_color: Hex tint for the icon while enabled. ``None`` uses the
            auto theme colour.
        settings_key: Persistence namespace (see :class:`ToggleOption`). Backs
            both the on/off flag and the held value.
        order: Explicit sort position. See :class:`BaseOption`.

    Signals:
        toggled(bool): Emitted when the state changes (``True`` = now enabled).
    """

    # Persist under a distinct app namespace so a DisableOption and a plain
    # ToggleOption on the same widget never collide on the auto-derived key.
    SETTINGS_APP = "DisableOption"

    #: Hosts whose value can honestly be emptied. Deliberately narrower than
    #: ``OptionBox._is_text_widget``: a spin box has no "no value" state, and a
    #: button's / label's text is a static caption rather than a value.
    SUPPRESSIBLE_TYPES: Tuple[type, ...] = (
        QtWidgets.QLineEdit,
        QtWidgets.QTextEdit,
        QtWidgets.QPlainTextEdit,
    )

    #: Settings key holding the suppressed text (see :meth:`_save_state`).
    _HELD_KEY = "held_value"

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
        suppress_value: bool = True,
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
        # ``_held`` is seeded by _load_state, which the base constructor calls.
        super().__init__(**kwargs)
        self._suppress_value = bool(suppress_value)
        self._guard_connected = False

    # ------------------------------------------------------------------
    # Value suppression
    # ------------------------------------------------------------------

    @property
    def held_value(self) -> Optional[str]:
        """Text held aside while disabled (``None`` when nothing is held)."""
        return None if self._held is None else self._held[0]

    def _suppressible(self):
        """The wrapped widget when its value can be emptied, else ``None``."""
        if not getattr(self, "_suppress_value", False) or not self._gate_wrapped:
            return None
        w = self.wrapped_widget
        return w if isinstance(w, self.SUPPRESSIBLE_TYPES) else None

    @staticmethod
    def _read(w) -> Tuple[str, Any]:
        """``(text, data)`` for *w* — data is the hidden payload, if any."""
        text = w.toPlainText() if hasattr(w, "toPlainText") else w.text()
        # uitk LineEdit can show a friendly display over a distinct payload.
        data = w.data() if callable(getattr(w, "data", None)) else None
        return text, data

    @staticmethod
    def _write(w, text: str, data: Any = None) -> None:
        """Put *text* (and any hidden *data* payload) back into *w*."""
        if data is not None and callable(getattr(w, "set_value", None)):
            w.set_value(data, display=text)
        elif hasattr(w, "setPlainText"):  # before setText: QTextEdit has both
            w.setPlainText(text)
        else:
            w.setText(text)

    @staticmethod
    def _empty(w) -> None:
        """Empty *w*, dropping any hidden payload with it."""
        # clear() only touches the visible text; a LineEdit payload survives it
        # (only a *manual* edit invalidates one), and value() would still return
        # the payload of a field that reads empty.
        if callable(getattr(w, "clear_value", None)):
            w.clear_value()
        w.clear()

    def _hold_value(self, w) -> None:
        """Take the field's value aside and empty it. Idempotent.

        Re-entered on every ``_apply_gating(False)`` — including the one
        ``setup_widget`` runs to reflect a persisted off state — so an existing
        hold is never overwritten with the empty field it already produced.
        """
        if self._held is None:
            text, data = self._read(w)
            if text:
                self._held = (text, data)
                self._save_state()
        self._empty(w)

    def _release_value(self, w) -> None:
        """Put a held value back (no-op when nothing is held)."""
        if self._held is None:
            return
        text, data = self._held
        self._held = None
        self._write(w, text, data)
        self._save_state()

    def _connect_suppression_guard(self) -> None:
        """Watch for values written into the field while it is disabled."""
        w = self._suppressible()
        if w is None or self._guard_connected:
            return
        signal = getattr(w, "textChanged", None)
        if signal is None:
            return
        signal.connect(self._on_wrapped_text_changed)
        self._guard_connected = True

    def _on_wrapped_text_changed(self, *_args) -> None:
        """Absorb any value written into the field while it is disabled.

        The field is disabled, so this can only be a *programmatic* write — a
        state restore landing after the option was built, or a slot seeding a
        default. Adopting it into the held value and re-emptying keeps the
        "disabled = no value" invariant true no matter who writes, and hands the
        value over on re-enable rather than dropping it. Our own emptying
        re-enters here with no text and returns, so there is no recursion.
        """
        if self._is_on:
            return
        w = self._suppressible()
        if w is None:
            return
        text, data = self._read(w)
        if not text:
            return
        self._held = (text, data)
        self._save_state()
        self._empty(w)

    # ------------------------------------------------------------------
    # BinaryToggleOption overrides
    # ------------------------------------------------------------------

    def setup_widget(self):
        """Wire the base button, then guard the wrapped field's value."""
        super().setup_widget()
        self._connect_suppression_guard()

    def _apply_gating(self, active: bool) -> None:
        """Enable/disable the gated widgets, holding the value aside while off."""
        w = self._suppressible()
        if w is not None:
            if active:
                self._release_value(w)
            else:
                self._hold_value(w)
        super()._apply_gating(active)
        self._refresh_held_tooltip()

    def _refresh_held_tooltip(self) -> None:
        """Name the held value in the off-state tooltip.

        The field reads empty while disabled, so the button is the only place
        left that can say what is coming back. Runs after ``_apply_visuals`` has
        set the plain off tooltip (``set_on`` / ``setup_widget`` order).
        """
        if self._widget is None or self._is_on:
            return
        held = self.held_value
        if held:
            self._widget.setToolTip(f"{self._tooltip_off}\nHolding: {held!r}")

    def _save_state(self):
        """Persist the on/off flag (base) plus the held text."""
        super()._save_state()
        if not self._settings:
            return
        if self._held is None:
            self._settings.remove(self._HELD_KEY)
        else:
            self._settings.setValue(self._HELD_KEY, self._held[0])
        self._settings.sync()

    def _load_state(self):
        """Restore the on/off flag (base) plus any held text.

        Only the text survives a session: a hidden data payload is an arbitrary
        object with no stable serialization, so it is held in memory only.
        """
        super()._load_state()
        self._held: Optional[Tuple[str, Any]] = None
        if not self._settings:
            return
        held = self._settings.value(self._HELD_KEY)
        if held:
            self._held = (str(held), None)
