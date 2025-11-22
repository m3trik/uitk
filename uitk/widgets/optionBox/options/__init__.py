# !/usr/bin/python
# coding=utf-8
"""Option plugins for OptionBox.

This package contains modular, drop-in option plugins that can be added
to an OptionBox to extend its functionality.

Available Options:
    - ClearOption: Adds a clear button for text widgets
    - ActionOption: Adds a customizable action button
    - MenuOption: Adds a menu button
    - PinValuesOption: Adds a pin button to save/restore values
    - OptionMenuOption: Adds a dropdown menu with multiple choices
    - ContextMenuOption: Adds a dynamic context menu

Base Classes:
    - BaseOption: Abstract base class for all options
    - ButtonOption: Base class for button-based options

Example:
    from uitk.widgets.optionBox import OptionBox
    from uitk.widgets.optionBox.options import ClearOption, PinValuesOption

    line_edit = QtWidgets.QLineEdit()
    clear_opt = ClearOption(line_edit)
    pin_opt = PinValuesOption(line_edit)

    option_box = OptionBox(options=[clear_opt, pin_opt])
    option_box.wrap(line_edit)
"""

from ._options import BaseOption, ButtonOption
from .clear import ClearOption, ClearButton
from .action import ActionOption, MenuOption
from .pin_values import PinValuesOption
from .option_menu import OptionMenuOption, ContextMenuOption

__all__ = [
    # Base classes
    "BaseOption",
    "ButtonOption",
    # Option plugins
    "ClearOption",
    "ActionOption",
    "MenuOption",
    "PinValuesOption",
    "OptionMenuOption",
    "ContextMenuOption",
    # Legacy
    "ClearButton",
]
