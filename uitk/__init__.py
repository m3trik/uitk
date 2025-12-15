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
__version__ = "1.0.54"


DEFAULT_INCLUDE = {
    "signals": "Signals",
    "events": ["EventFactoryFilter", "MouseTracking"],
    "file_manager": ["FileContainer", "FileManager"],
    "switchboard": "Switchboard",
    # Widgets
    "widgets.attributeWindow": "AttributeWindow",
    "widgets.checkBox": "CheckBox",
    "widgets.collapsableGroup": "CollapsableGroup",
    "widgets.colorSwatch": "ColorSwatch",
    "widgets.comboBox": "ComboBox",
    "widgets.doubleSpinBox": "DoubleSpinBox",
    "widgets.expandableList": "ExpandableList",
    "widgets.header": "Header",
    "widgets.footer": "Footer",
    "widgets.label": "Label",
    "widgets.lineEdit": "LineEdit",
    "widgets.mainWindow": "MainWindow",
    "widgets.menu": "Menu",
    "widgets.messageBox": "MessageBox",
    "widgets.optionBox": [
        "OptionBox",
        "OptionBoxContainer",
        "OptionBoxWithOrdering",
        "OptionBoxManager",
        "ClearButton",
    ],
    "widgets.optionBox.options": [
        "OptionAction",
        "OptionClear",
        "OptionMenu",
        "OptionPinValues",
    ],
    "widgets.progressBar": "ProgressBar",
    "widgets.pushButton": "PushButton",
    "widgets.region": "Region",
    "widgets.separator": "Separator",
    "widgets.tableWidget": "TableWidget",
    "widgets.textEdit": "TextEdit",
    "widgets.textEditLogHandler": "TextEditLogHandler",
    "widgets.toolBox": "ToolBox",
    "widgets.treeWidget": "TreeWidget",
    "widgets.widgetComboBox": "WidgetComboBox",
    # Widget mixins
    "widgets.mixins.attributes": "AttributesMixin",
    "widgets.mixins.convert": "ConvertMixin",
    "widgets.mixins.docking": "DockingMixin",
    "widgets.mixins.icon_manager": "IconManager",
    "widgets.mixins.menu_mixin": "MenuMixin",
    "widgets.mixins.option_box_mixin": "OptionBoxMixin",
    "widgets.mixins.settings_manager": "SettingsManager",
    "widgets.mixins.shortcuts": ["ShortcutManager", "ShortcutMixin"],
    "widgets.mixins.state_manager": "StateManager",
    "widgets.mixins.style_sheet": "StyleSheet",
    "widgets.mixins.switchboard_slots": ["SlotWrapper", "SwitchboardSlotsMixin"],
    "widgets.mixins.switchboard_utils": "SwitchboardUtilsMixin",
    "widgets.mixins.switchboard_widgets": "SwitchboardWidgetMixin",
    "widgets.mixins.tasks": ["WorkIndicator", "TasksMixin"],
    "widgets.mixins.text": ["TextTruncation", "RichText", "TextOverlay"],
    "widgets.mixins.value_manager": "ValueManager",
}

# Fallbacks removed - fix imports at source
# Old fallback mappings are now in DEFAULT_INCLUDE above


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
    custom_getattr=_uitk_getattr,
)
# Test: 222117
