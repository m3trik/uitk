# !/usr/bin/python
# coding=utf-8
"""OptionBox - Plugin-based widget option system.

OptionBox provides a flexible system for adding action buttons, clear buttons,
and other options to Qt widgets. It uses a plugin architecture where options
are modular, drop-in components that can be easily added or removed.

Main Components:
    - OptionBox: Manager that wraps widgets with option buttons
    - OptionBoxContainer: Container widget for proper styling
    - OptionBoxManager: API for managing options via widget.option_box

Option Plugins (in the `options` subpackage):
    - ClearOption: Clear button for text widgets
    - ActionOption: Customizable action button
    - MenuOption: Menu display button
    - PinValuesOption: Pin/restore widget values

Basic Usage:
    from uitk.widgets.optionBox import OptionBox, add_option_box
    from uitk.widgets.optionBox.options import ClearOption

    # Method 1: Using convenience function
    line_edit = QtWidgets.QLineEdit()
    container = add_option_box(line_edit, show_clear=True)
    layout.addWidget(container)

    # Method 2: Using OptionBox directly
    line_edit = QtWidgets.QLineEdit()
    option_box = OptionBox(show_clear=True)
    container = option_box.wrap(line_edit)
    layout.addWidget(container)

    # Method 3: Using option plugins
    line_edit = QtWidgets.QLineEdit()
    clear_opt = ClearOption(line_edit)
    option_box = OptionBox(options=[clear_opt])
    container = option_box.wrap(line_edit)
    layout.addWidget(container)

Widget Manager API (after patch_common_widgets() is called):
    line_edit = QtWidgets.QLineEdit()
    line_edit.option_box.enable_clear()
    line_edit.option_box.enable_menu()
    container = line_edit.option_box.container
    layout.addWidget(container)
"""

# Import core classes
from ._optionBox import (
    OptionBox,
    OptionBoxContainer,
)

# Import utilities and helpers
from .utils import (
    OptionBoxManager,
    add_option_box,
    add_clear_option,
    add_menu_option,
    patch_widget_class,
    patch_common_widgets,
)

# Auto-patch common widgets on import for convenience
patch_common_widgets()

__all__ = [
    # Core classes
    "OptionBox",
    "OptionBoxContainer",
    # Utilities
    "OptionBoxManager",
    "add_option_box",
    "add_clear_option",
    "add_menu_option",
    "patch_widget_class",
    "patch_common_widgets",
]

# Note: Option plugins are in the `options` subpackage
# Import them explicitly:
#   from uitk.widgets.optionBox.options import ClearOption, ActionOption, etc.
