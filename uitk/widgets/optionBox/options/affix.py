# !/usr/bin/python
# coding=utf-8
"""Affix-mode picker option for OptionBox.

An :class:`AffixOption` turns a text field into an affix entry with a compact,
tri-state icon button sitting flush beside it — the single, reusable home for
the pattern previously duplicated across the DCC toolkits (mayatk / blendertk
``mat_utils``). Clicking the button cycles the mode (Auto → Suffix → Prefix),
which declares how the field's text is applied to a base name:

* **Auto** — placement inferred from the delimiter: a leading ``_`` (``"_MAT"``)
  is treated as a suffix; a trailing ``_`` (``"MAT_"``) is treated as a prefix.
* **Suffix** — always appended (``"brick" + "_MAT" → "brick_MAT"``).
* **Prefix** — always prepended (``"MAT_" + "brick" → "MAT_brick"``).

The parsing itself is the widget-free :func:`pythontk.StrUtils.split_affix`
primitive; this option only wires the picker button and exposes the selection.

Usage — the ``option_box`` manager form works on any widget (``.option_box`` is
autopatched onto plain ``QLineEdit``/etc.), so prefer it in slot code; the
``.options`` fluent sugar exists only on ``OptionBoxMixin`` widgets::

    le.option_box.set_affix(default="auto", on_change=on_mode_changed)
    le.options.affix(default="auto")                       # fluent equiv (mixin widgets)

    mode = le.option_box.affix_mode                        # 'auto'|'suffix'|'prefix'
    prefix, suffix = le.option_box.resolve_affix(default="suffix")
"""
from typing import Callable, Dict, Optional, Tuple

import pythontk as ptk

from ._options import ButtonOption


# Canonical mode values, in the click-cycle order.
AFFIX_MODE_VALUES: Tuple[str, str, str] = ("auto", "suffix", "prefix")


class AffixOption(ButtonOption):
    """Tri-state affix-mode cycle button (Auto / Suffix / Prefix) for a text widget."""

    #: mode -> (display label, icon name, how-the-text-applies description).
    #: The icon reads as "where the affix lands": start of the name (prefix),
    #: end of the name (suffix), or wildcard-inferred (auto).
    _MODES: Dict[str, Tuple[str, str, str]] = {
        "auto": (
            "Auto",
            "asterisk",
            "leading '_' (e.g. '_MAT') is a suffix; trailing '_' (e.g. 'MAT_') "
            "is a prefix",
        ),
        "suffix": (
            "Suffix",
            "arrow_right",
            "always appended (e.g. 'brick' + '_MAT' → 'brick_MAT')",
        ),
        "prefix": (
            "Prefix",
            "arrow_left",
            "always prepended (e.g. 'MAT_' + 'brick' → 'MAT_brick')",
        ),
    }

    def __init__(
        self,
        wrapped_widget=None,
        *,
        default: str = "auto",
        on_change: Optional[Callable[[str], None]] = None,
        tooltip: Optional[str] = None,
        order: Optional[int] = None,
    ):
        """Initialize the affix option.

        Args:
            wrapped_widget: The text field this picker is attached to.
            default: Initial mode — ``"auto"`` / ``"suffix"`` / ``"prefix"``.
                Ignored (falls back to ``"auto"``) if unknown.
            on_change: Optional callable invoked with the new mode string
                whenever the mode changes on the built button (click or
                programmatic :meth:`set_mode`).
            tooltip: Static tooltip override. ``None`` (default) shows a
                per-state tooltip naming the current mode and the cycle hint.
            order: Explicit sort position. See :class:`BaseOption`.
        """
        self._mode = default if default in self._MODES else AFFIX_MODE_VALUES[0]
        self._on_change = on_change
        self._tooltip_override = tooltip
        super().__init__(
            wrapped_widget,
            icon=self._MODES[self._mode][1],
            tooltip=tooltip,
            callback=self._cycle,
            order=order,
        )

    # ------------------------------------------------------------------
    # Compatibility
    # ------------------------------------------------------------------

    @classmethod
    def is_compatible(cls, widget) -> bool:
        """Attach only to text-bearing hosts (``resolve`` reads ``text()``)."""
        return widget is not None and hasattr(widget, "text")

    # ------------------------------------------------------------------
    # ButtonOption overrides
    # ------------------------------------------------------------------

    def create_widget(self):
        """Create the standard option button, seeded with the current mode's glyph."""
        # set_mode may have moved the mode between __init__ and first build.
        self.icon = self._MODES[self._mode][1]
        return super().create_widget()

    def setup_widget(self):
        """Wire the cycle click and show the current mode's tooltip."""
        super().setup_widget()
        self._widget.setToolTip(self._tooltip_for(self._mode))

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        """Current mode string — ``"auto"`` / ``"suffix"`` / ``"prefix"``.

        A pure read: the mode is plugin-owned, so reading it never forces
        widget construction.
        """
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Select *mode* if it is a known value (else no-op).

        On the built button this swaps the glyph/tooltip and fires
        ``on_change``; before build it just re-seeds the initial state
        (applied when the button is first shown, without firing).
        """
        if mode not in self._MODES or mode == self._mode:
            return
        self._mode = mode
        if self._widget is not None:
            self._apply_mode_visual()
            if self._on_change is not None:
                self._on_change(mode)

    def resolve(
        self, text: Optional[str] = None, *, default: str = "prefix"
    ) -> Tuple[str, str]:
        """Return ``(prefix, suffix)`` for *text* under the current mode.

        *text* defaults to the wrapped widget's current text. *default* is the
        fallback mode used when Auto is selected but *text* has no boundary
        delimiter (matches :func:`pythontk.StrUtils.split_affix`).
        """
        if text is None:
            w = self.wrapped_widget
            text = w.text() if (w is not None and hasattr(w, "text")) else ""
        return ptk.StrUtils.split_affix(text, mode=self._mode, default=default)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cycle(self) -> None:
        """Advance to the next mode (button click)."""
        i = AFFIX_MODE_VALUES.index(self._mode)
        self.set_mode(AFFIX_MODE_VALUES[(i + 1) % len(AFFIX_MODE_VALUES)])

    def _apply_mode_visual(self) -> None:
        """Swap the built button's glyph and tooltip to the current mode."""
        self._swap_state_icon(self._MODES[self._mode][1], fallback_size=(15, 15))
        self._widget.setToolTip(self._tooltip_for(self._mode))

    def _tooltip_for(self, mode: str) -> str:
        """Per-state tooltip (or the static override when one was given)."""
        if self._tooltip_override is not None:
            return self._tooltip_override
        label, _icon, desc = self._MODES[mode]
        return (
            f"Affix mode: {label} — {desc}.\n"
            "Click to cycle: Auto → Suffix → Prefix."
        )
