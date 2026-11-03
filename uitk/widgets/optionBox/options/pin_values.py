# !/usr/bin/python
# coding=utf-8
"""Pin Values option for OptionBox -- a list of pinned values, no history.

The pins-only face of the value-list option ``RecentValuesOption`` presents
too: the same popup and model with no history (``max_recent=0``), a pin glyph
that fills while the field's value is pinned, and its own storage namespace
(``PinValues``), where pins saved before the two plugins shared one model load
unchanged.
"""

from qtpy import QtCore
import pythontk as ptk

# The pin record lives with the model both faces share; its old home answers.
from uitk.managers.recent_values_store import PinnedValueEntry  # noqa: F401
from .recent_values import _ValueListOption


class PinValuesOption(_ValueListOption):
    """A pin button: values the user pins, names and restores.

    Clicking the button shows the pinned values, alphabetical by name, and a
    footer to pin the field's current value. A row restores on click; its pin
    unpins and ✎ names it. The button's glyph is the state: a filled pin while
    the field's value is pinned, hollow otherwise.

    For a history with pins on top, use ``RecentValuesOption``, its sibling.

    Example:
        line_edit = QtWidgets.QLineEdit()
        pin_option = PinValuesOption(line_edit, settings_key="my_pins")
        option_box = OptionBox(options=[pin_option])
        option_box.wrap(line_edit)
    """

    value_restored = QtCore.Signal(object)
    """Emitted with the value a click restored (alias of ``value_selected``)."""

    SETTINGS_APP = "PinValues"
    ICON = "pin_empty"
    TOOLTIP = "Pinned values"
    BUTTON_NAME = "pinButton"
    BUTTON_CLASS = "PinButton"
    EMPTY_TEXT = "No pinned values"

    @ptk.Deprecation.parameter(
        "double_click_to_edit", drop=True, remove_in="1.11.0", since="2026-11-03"
    )
    @ptk.Deprecation.parameter(
        "single_click_restore", drop=True, remove_in="1.11.0", since="2026-11-03"
    )
    def __init__(
        self,
        wrapped_widget=None,
        settings_key=None,
        max_pinned=10,
        double_click_to_edit=False,
        single_click_restore=False,
        popup_align="right",
        *,
        text_align="center",
        display_format="truncate",
    ):
        """Initialize the pin values option.

        Args:
            wrapped_widget: The widget whose values to pin.
            settings_key: Key for persistent settings. If provided, pinned
                values are saved and restored across sessions.
            max_pinned: Maximum number of pins; pinning past it drops the
                oldest.
            double_click_to_edit: Deprecated, removed in 1.11.0: nothing
                reads it. Passed by keyword it warns and is ignored; it keeps
                its place so *popup_align* stays the sixth argument.
            single_click_restore: Deprecated, removed in 1.11.0, as
                *double_click_to_edit*: a row restores on a single click.
            popup_align: ``"right"`` (default) aligns the popup's right edge
                to the parent window's; ``"left"`` aligns its left edge to the
                wrapped widget.
            text_align: ``"center"`` (default), ``"left"`` or ``"right"``.
            display_format: How values show (see ``RecentValuesOption``);
                ``"truncate"`` (default) shows each whole, middle-elided.
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            settings_key=settings_key,
            max_recent=0,
            max_pinned=max_pinned,
            display_format=display_format,
            popup_align=popup_align,
            text_align=text_align,
            pinning=True,
        )
        self.value_selected.connect(self.value_restored)

    def create_widget(self):
        """Create the pin button; its glyph follows the wrapped widget's value."""
        button = super().create_widget()
        self._connect_value_change_signals()
        return button

    def _connect_value_change_signals(self):
        """Connect to the wrapped widget's value change signals."""
        widget = self.wrapped_widget
        if not widget:
            return

        if hasattr(widget, "textChanged"):
            widget.textChanged.connect(self._update_button_visuals)
        elif hasattr(widget, "textEdited"):
            widget.textEdited.connect(self._update_button_visuals)
        if hasattr(widget, "valueChanged"):
            widget.valueChanged.connect(self._update_button_visuals)
        if hasattr(widget, "currentTextChanged"):
            widget.currentTextChanged.connect(self._update_button_visuals)
        if hasattr(widget, "currentIndexChanged"):
            widget.currentIndexChanged.connect(self._update_button_visuals)

    def _update_button_visuals(self, *_args):
        """Fill the pin while the field's value is pinned (subscribed to the store
        and to the field's value signals).

        The GLYPH is the state channel: filled = the value in the field right
        now is pinned, hollow = it isn't. No color tint — the icon swap alone
        carries the meaning, and the resting glyph follows the theme.
        """
        if self._widget is None:
            return
        count = len(self._store.pinned)
        if self._store.is_pinned(self._current_widget_record()):
            icon_name = "pin"
            tooltip = f"Pinned values ({count}) - current value is pinned"
        elif count:
            icon_name = "pin_empty"
            tooltip = f"Pinned values ({count})"
        else:
            icon_name = "pin_empty"
            tooltip = "Pin values"
        self._widget.setToolTip(tooltip)
        self._swap_state_icon(icon_name)
