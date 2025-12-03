# !/usr/bin/python
# coding=utf-8
"""UITK - User Interface Toolkit for Qt/PySide applications.

A comprehensive UI framework that extends Qt Designer workflows with:
- Dynamic UI loading via Switchboard
- Custom widget classes with enhanced functionality
- Automatic signal-slot connection management
- Theme and style management
- State persistence and settings

Example:
    Basic usage with Switchboard::

        from uitk import Switchboard

        sb = Switchboard(ui_source="my_app.ui", slot_source=MySlots)
        ui = sb.my_app
        ui.show(app_exec=True)

    Using individual widgets::

        from uitk.widgets.pushButton import PushButton

        button = PushButton("Click Me")
        button.menu.add("Option 1")  # Built-in menu support

Key Modules:
    switchboard: Dynamic UI loader and event handler
    signals: Signal decorator for slot annotations
    events: Event filters and mouse tracking utilities
    file_manager: File and path management utilities
    widgets: Enhanced Qt widget classes with mixins

Attributes:
    __version__: Current package version string.
"""
import importlib

from pythontk.core_utils.module_resolver import bootstrap_package

__package__ = "uitk"
__version__ = "1.0.36"


DEFAULT_INCLUDE = {
    "signals": "Signals",
    "events": "*",
    "file_manager": "*",
    "switchboard": "*",
    # Widgets
    "widgets.attributeWindow": "*",
    "widgets.checkBox": "*",
    "widgets.collapsableGroup": "*",
    "widgets.colorSwatch": "*",
    "widgets.comboBox": "*",
    "widgets.doubleSpinBox": "*",
    "widgets.expandableList": "*",
    "widgets.header": "*",
    "widgets.label": "*",
    "widgets.lineEdit": "*",
    "widgets.mainWindow": "*",
    "widgets.menu": "*",
    "widgets.messageBox": "*",
    "widgets.optionBox": [
        "OptionBox",
        "OptionBoxContainer",
        "OptionBoxWithOrdering",
        "OptionBoxManager",
        "ClearButton",
    ],
    "widgets.optionBox.options": "*",
    "widgets.progressBar": "*",
    "widgets.pushButton": "*",
    "widgets.region": "*",
    "widgets.separator": "*",
    "widgets.tableWidget": "*",
    "widgets.textEdit": "*",
    "widgets.textEditLogHandler": "*",
    "widgets.treeWidget": "*",
    "widgets.widgetComboBox": "*",
    # Widget mixins
    "widgets.mixins.attributes": "*",
    "widgets.mixins.convert": "*",
    "widgets.mixins.docking": "*",
    "widgets.mixins.icon_manager": "*",
    "widgets.mixins.menu_mixin": "*",
    "widgets.mixins.option_box_mixin": "*",
    "widgets.mixins.settings_manager": "*",
    "widgets.mixins.shortcuts": "*",
    "widgets.mixins.state_manager": "*",
    "widgets.mixins.style_sheet": "*",
    "widgets.mixins.switchboard_slots": "*",
    "widgets.mixins.switchboard_utils": "*",
    "widgets.mixins.switchboard_widgets": "*",
    "widgets.mixins.tasks": "*",
    "widgets.mixins.text": "*",
    "widgets.mixins.value_manager": "*",
}

DEFAULT_FALLBACKS = {
    "add_option_box": "uitk.widgets.optionBox",
    "add_clear_option": "uitk.widgets.optionBox",
    "add_menu_option": "uitk.widgets.optionBox",
    "patch_widget_class": "uitk.widgets.optionBox",
    "patch_common_widgets": "uitk.widgets.optionBox",
}


def _uitk_getattr(name: str):
    """Handle special-case exports before falling back to the shared resolver."""
    if name == "examples":
        return importlib.import_module("uitk.examples")

    resolver = globals().get("_RESOLVER")
    if resolver is not None:
        return resolver.resolve(name)

    raise AttributeError(f"module {__package__} has no attribute '{name}'")


bootstrap_package(
    globals(),
    include=DEFAULT_INCLUDE,
    fallbacks=DEFAULT_FALLBACKS,
    custom_getattr=_uitk_getattr,
)
