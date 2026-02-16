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
__version__ = "1.0.85"


DEFAULT_INCLUDE = {
    "widgets.mixins.shortcuts": "Shortcut",
    "events": ["EventFactoryFilter", "MouseTracking"],
    "file_manager": ["FileContainer", "FileManager"],
    "switchboard": "Switchboard",
    "widgets.marking_menu._marking_menu": "MarkingMenu",
    "managers.window_manager": "WindowManager",
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
    "widgets.optionBox._optionBox": [
        "OptionBox",
        "OptionBoxContainer",
        "OptionBoxWithOrdering",
    ],
    "widgets.optionBox.utils": [
        "OptionBoxManager",
        "add_option_box",
        "add_clear_option",
        "add_menu_option",
        "patch_widget_class",
        "patch_common_widgets",
    ],
    "widgets.optionBox.options.clear": "ClearButton",
    "widgets.optionBox.options._options": ["BaseOption", "ButtonOption"],
    "widgets.optionBox.options.action": ["ActionOption", "MenuOption"],
    "widgets.optionBox.options.clear": ["ClearOption", "ClearButton"],
    "widgets.optionBox.options.pin_values": "PinValuesOption",
    "widgets.optionBox.options.option_menu": ["OptionMenuOption", "ContextMenuOption"],
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
    "widgets.mixins.switchboard_slots": "Signals",
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
        try:
            return resolver.resolve(name)
        except Exception as e:
            # Provide a clearer error for ImportErrors during resolution
            # This helps debug issues in environments like Maya's deferred evaluation
            raise AttributeError(
                f"Failed to resolve '{name}' in '{__package__}'.\n"
                f"  Check '{__package__}.__init__.py' mappings.\n"
                f"  Original Error: {e}"
            ) from e

    raise AttributeError(f"module {__package__} has no attribute '{name}'")


bootstrap_package(
    globals(),
    include=DEFAULT_INCLUDE,
    custom_getattr=_uitk_getattr,
)
# Test: 222117
