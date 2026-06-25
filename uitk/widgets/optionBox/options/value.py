# !/usr/bin/python
# coding=utf-8
"""Inline editable value readout for OptionBox.

A :class:`ValueOption` is a *non-button* option: instead of an icon-square
action button, it shows the wrapped widget's current value in a compact spin
box and writes edits back — so a :class:`Slider` (or any value-bearing widget)
gains a typeable, live numeric readout sitting flush beside it.

Bidirectional + live: dragging the wrapped widget updates the field; editing
the field updates the wrapped widget (and lets it emit, so any slot connected
to the wrapped widget still fires). Reusable across any widget exposing
``value()`` / ``setValue()`` plus a ``valueChanged`` signal (slider, spin box,
dial).

Usage::

    sld.option_box.add_value(width=46, suffix="°")
"""
from typing import Optional

from qtpy import QtWidgets, QtCore

from ._options import BaseOption


class ValueOption(BaseOption):
    """Inline, editable numeric field mirroring the wrapped widget's value."""

    # Opt out of OptionBox's icon-square (h x h) sizing — a value field needs
    # width. OptionBox._update_sizing checks this flag (default True elsewhere).
    square = False

    def __init__(
        self,
        wrapped_widget=None,
        *,
        width: int = 46,
        decimals: Optional[int] = None,
        suffix: str = "",
        order: Optional[int] = None,
    ):
        """Initialize the value option.

        Args:
            wrapped_widget: The value widget this field mirrors.
            width: Fixed pixel width of the field (height is squared to the
                wrapped widget's row height by OptionBox).
            decimals: Decimal places. ``None`` inherits the wrapped widget's
                ``decimals()`` if it has one, else 0 (integer, e.g. a slider).
            suffix: Optional unit suffix shown after the number (e.g. ``"°"``).
            order: Explicit sort position. See :class:`BaseOption`.
        """
        super().__init__(wrapped_widget, order=order)
        self._width = width
        self._decimals = decimals
        self._suffix = suffix
        # Guards the field<->widget echo so a programmatic set never loops.
        self._syncing = False
        # The widget our valueChanged handler is currently wired to (None = not
        # connected). Tracked so re-wiring is idempotent and we never attempt a
        # disconnect on a signal we never connected (PySide6 warns on that).
        self._connected_to = None

    # ------------------------------------------------------------------
    # BaseOption overrides
    # ------------------------------------------------------------------

    def create_widget(self):
        """Create the compact, button-less spin box field."""
        from uitk.widgets.spinBox import SpinBox

        field = SpinBox()
        field.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        field.setFocusPolicy(QtCore.Qt.ClickFocus)
        field.setFixedWidth(self._width)
        field.setAlignment(QtCore.Qt.AlignCenter)
        # QSS hook so a theme can style the inline field distinctly.
        field.setProperty("class", "ValueOption")
        return field

    def setup_widget(self):
        """Mirror the wrapped widget into the field and wire field -> widget."""
        self._configure_field()
        self._sync_field_from_wrapped()
        self._widget.valueChanged.connect(self._on_field_changed)

    def on_wrap(self, option_box, container):
        # Wrapped widget is guaranteed set by now; wire widget -> field.
        self._connect_wrapped()
        self._sync_field_from_wrapped()

    def refresh(self):
        """Re-sync the field from the wrapped widget's current value.

        Call after changing the wrapped widget programmatically *with its
        signals blocked* (so the field's automatic mirror didn't fire) — e.g.
        a panel pulling live state into its widgets.
        """
        self._sync_field_from_wrapped()

    def set_wrapped_widget(self, widget):
        super().set_wrapped_widget(widget)
        # If the field already exists (option re-pointed after creation),
        # reconfigure + re-wire to the new wrapped widget.
        if self._widget is not None:
            self._configure_field()
            self._connect_wrapped()
            self._sync_field_from_wrapped()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _configure_field(self):
        """Match the field's range/step/decimals to the wrapped widget."""
        w, field = self.wrapped_widget, self._widget
        if w is None or field is None:
            return
        if hasattr(w, "minimum") and hasattr(w, "maximum"):
            field.setRange(w.minimum(), w.maximum())
        decimals = self._decimals
        if decimals is None:
            decimals = w.decimals() if hasattr(w, "decimals") else 0
        field.setDecimals(decimals)
        if hasattr(w, "singleStep"):
            field.setSingleStep(w.singleStep())
        if self._suffix:
            field.setSuffix(self._suffix)

    def _connect_wrapped(self):
        """Wire the wrapped widget's change signal to the field (idempotent)."""
        w = self.wrapped_widget
        if w is None or not hasattr(w, "valueChanged"):
            return
        if self._connected_to is w:
            return  # already wired to this widget — no double-connect
        if self._connected_to is not None:
            try:
                self._connected_to.valueChanged.disconnect(self._on_wrapped_changed)
            except (TypeError, RuntimeError):
                pass  # old widget already gone
        w.valueChanged.connect(self._on_wrapped_changed)
        self._connected_to = w

    def _sync_field_from_wrapped(self):
        w = self.wrapped_widget
        if w is None or self._widget is None or not hasattr(w, "value"):
            return
        self._set_silent(self._widget, w.value())

    def _on_field_changed(self, value):
        """User edited the field -> push to the wrapped widget (let it emit)."""
        if self._syncing:
            return
        w = self.wrapped_widget
        if w is None or not hasattr(w, "setValue"):
            return
        # Do NOT block the wrapped widget's signal — downstream slots
        # (e.g. the panel's value handler) must still fire on a typed edit.
        self._syncing = True
        try:
            w.setValue(value)
        finally:
            self._syncing = False

    def _on_wrapped_changed(self, value):
        """Wrapped widget moved -> reflect in the field (silently)."""
        if self._syncing:
            return
        self._syncing = True
        try:
            self._set_silent(self._widget, value)
        finally:
            self._syncing = False

    @staticmethod
    def _set_silent(field, value):
        if field is None:
            return
        field.blockSignals(True)
        try:
            field.setValue(value)
        finally:
            field.blockSignals(False)
