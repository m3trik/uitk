# !/usr/bin/python
# coding=utf-8
"""Lazy exports for UITK widgets with explicit include maps."""

from pythontk.core_utils.module_resolver import bootstrap_package


DEFAULT_INCLUDE = {
    "attributeWindow": "*",
    "checkBox": "*",
    "collapsableGroup": "*",
    "colorSwatch": "*",
    "comboBox": "*",
    "doubleSpinBox": "*",
    "expandableList": "*",
    "footer": "*",
    "header": "*",
    "label": "*",
    "lineEdit": "*",
    "mainWindow": "*",
    "menu": "*",
    "messageBox": "*",
    "optionBox": [
        "OptionBox",
        "OptionBoxContainer",
        "OptionBoxWithOrdering",
        "OptionBoxManager",
        "ClearButton",
    ],
    "optionBox.options": "*",
    "progressBar": "*",
    "pushButton": "*",
    "region": "*",
    "separator": "*",
    "tableWidget": "*",
    "textEdit": "*",
    "textEditLogHandler": "*",
    "treeWidget": "*",
    "widgetComboBox": "*",
    # Mixins subpackage (re-exposed here for convenience)
    "mixins.attributes": "*",
    "mixins.convert": "*",
    "mixins.docking": "*",
    "mixins.icon_manager": "*",
    "mixins.menu_mixin": "*",
    "mixins.option_box_mixin": "*",
    "mixins.settings_manager": "*",
    "mixins.shortcuts": "*",
    "mixins.state_manager": "*",
    "mixins.style_sheet": "*",
    "mixins.switchboard_slots": "*",
    "mixins.switchboard_utils": "*",
    "mixins.switchboard_widgets": "*",
    "mixins.tasks": "*",
    "mixins.text": "*",
    "mixins.value_manager": "*",
}

DEFAULT_FALLBACKS = {
    "add_option_box": "uitk.widgets.optionBox",
    "add_clear_option": "uitk.widgets.optionBox",
    "add_menu_option": "uitk.widgets.optionBox",
    "patch_widget_class": "uitk.widgets.optionBox",
    "patch_common_widgets": "uitk.widgets.optionBox",
}


bootstrap_package(
    globals(),
    include=DEFAULT_INCLUDE,
    fallbacks=DEFAULT_FALLBACKS,
)
