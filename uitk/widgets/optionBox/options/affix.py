# !/usr/bin/python
# coding=utf-8
"""Affix-mode picker option for OptionBox.

An :class:`AffixOption` turns a text field into an affix entry with a compact,
inline "Auto / Suffix / Prefix" mode picker sitting flush beside it — the single,
reusable home for the pattern previously duplicated across the DCC toolkits
(mayatk / blendertk ``mat_utils``). The mode declares how the field's text is
applied to a base name:

* **Auto** — placement inferred from the delimiter: a leading ``_`` (``"_MAT"``)
  is treated as a suffix; a trailing ``_`` (``"MAT_"``) is treated as a prefix.
* **Suffix** — always appended (``"brick" + "_MAT" → "brick_MAT"``).
* **Prefix** — always prepended (``"MAT_" + "brick" → "MAT_brick"``).

The parsing itself is the widget-free :func:`pythontk.StrUtils.split_affix`
primitive; this option only wires the picker widget and exposes the selection.

Usage — the ``option_box`` manager form works on any widget (``.option_box`` is
autopatched onto plain ``QLineEdit``/etc.), so prefer it in slot code; the
``.options`` fluent sugar exists only on ``OptionBoxMixin`` widgets::

    le.option_box.set_affix(default="auto", on_change=on_mode_changed)
    le.options.affix(default="auto")                       # fluent equiv (mixin widgets)

    mode = le.option_box.affix_mode                        # 'auto'|'suffix'|'prefix'
    prefix, suffix = le.option_box.resolve_affix(default="suffix")
"""
from typing import Callable, Optional, Sequence, Tuple

from qtpy import QtCore
import pythontk as ptk

from ._options import BaseOption


# Canonical mode values. The default display labels are intentionally terse so
# the inline picker stays narrow; the long-form guidance lives in the tooltip.
AFFIX_MODE_VALUES: Tuple[str, str, str] = ("auto", "suffix", "prefix")
AFFIX_MODE_LABELS: Tuple[str, str, str] = ("Auto", "Suffix", "Prefix")
AFFIX_MODE_TOOLTIP = (
    "How the affix text is applied to the base name:\n"
    "  Auto — leading '_' (e.g. '_MAT') is treated as a suffix;\n"
    "         trailing '_' (e.g. 'MAT_') is treated as a prefix.\n"
    "  Suffix — always appended (e.g. 'brick' + '_MAT' → 'brick_MAT').\n"
    "  Prefix — always prepended (e.g. 'MAT_' + 'brick' → 'MAT_brick')."
)


class AffixOption(BaseOption):
    """Inline affix-mode picker (Auto / Suffix / Prefix) for a text widget."""

    # Opt out of OptionBox's icon-square (h x h) sizing — the picker needs its
    # natural combobox width, exactly like ValueOption's editable field.
    square = False

    def __init__(
        self,
        wrapped_widget=None,
        *,
        default: str = "auto",
        on_change: Optional[Callable[[str], None]] = None,
        labels: Sequence[str] = AFFIX_MODE_LABELS,
        values: Sequence[str] = AFFIX_MODE_VALUES,
        tooltip: str = AFFIX_MODE_TOOLTIP,
        order: Optional[int] = None,
    ):
        """Initialize the affix option.

        Args:
            wrapped_widget: The text field this picker is attached to.
            default: Initial mode — one of *values* (``"auto"`` / ``"suffix"`` /
                ``"prefix"``). Ignored (falls back to the first value) if unknown.
            on_change: Optional callable invoked with the new mode string
                whenever the user changes the picker.
            labels: Display labels for the picker, positionally paired with
                *values*.
            values: Mode strings returned by :attr:`mode`, positionally paired
                with *labels*.
            tooltip: Tooltip shown on the picker.
            order: Explicit sort position. See :class:`BaseOption`.
        """
        super().__init__(wrapped_widget, order=order)
        self._labels = tuple(labels)
        self._values = tuple(values)
        if len(self._labels) != len(self._values):
            raise ValueError("labels and values must be the same length")
        self._default = default if default in self._values else self._values[0]
        self._on_change = on_change
        self._tooltip = tooltip

    # ------------------------------------------------------------------
    # Compatibility
    # ------------------------------------------------------------------

    @classmethod
    def is_compatible(cls, widget) -> bool:
        """Attach only to text-bearing hosts (``resolve`` reads ``text()``)."""
        return widget is not None and hasattr(widget, "text")

    # ------------------------------------------------------------------
    # BaseOption overrides
    # ------------------------------------------------------------------

    def create_widget(self):
        """Create the compact, inline mode combobox."""
        from uitk.widgets.comboBox import ComboBox

        combo = ComboBox()
        combo.addItems(list(self._labels))
        combo.setToolTip(self._tooltip)
        combo.setFocusPolicy(QtCore.Qt.ClickFocus)
        # QSS hook so a theme can style the inline picker distinctly.
        combo.setProperty("class", "AffixOption")
        return combo

    def setup_widget(self):
        """Seed the default selection (silently) and wire change -> callback."""
        combo = self._widget
        # Seed with signals blocked so the initial selection never fires
        # on_change (matches the seed-before-connect order of the original).
        combo.blockSignals(True)
        try:
            combo.setCurrentIndex(self._values.index(self._default))
        finally:
            combo.blockSignals(False)
        combo.currentIndexChanged.connect(self._on_index_changed)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        """Current mode string — one of *values* (the default while unbuilt).

        A pure read: before the picker widget is built it reports the seeded
        default (what the widget will show), so reading the mode never forces
        early widget construction.
        """
        if self._widget is None:
            return self._default
        idx = self._widget.currentIndex()
        if 0 <= idx < len(self._values):
            return self._values[idx]
        return self._default

    def set_mode(self, mode: str) -> None:
        """Select *mode* if it is one of this picker's values (else no-op).

        Before the widget is built this just updates the seeded default (applied
        when the picker is first shown); after, it moves the combobox.
        """
        if mode not in self._values:
            return
        if self._widget is None:
            self._default = mode
        else:
            self._widget.setCurrentIndex(self._values.index(mode))

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
        return ptk.StrUtils.split_affix(text, mode=self.mode, default=default)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_index_changed(self, _index: int) -> None:
        if self._on_change is not None:
            self._on_change(self.mode)
