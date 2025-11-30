# !/usr/bin/python
# coding=utf-8
"""Lazy export facade for mixin helpers used by UITK widgets."""

from pythontk.core_utils.module_resolver import bootstrap_package


DEFAULT_INCLUDE = {
    "add_items": "*",
    "attributes": "*",
    "convert": "*",
    "docking": "*",
    "icon_manager": "*",
    "menu_mixin": "*",
    "option_box_mixin": "*",
    "settings_manager": "*",
    "shortcuts": "*",
    "state_manager": "*",
    "size_grip": "*",
    "style_sheet": "*",
    "switchboard_slots": "*",
    "switchboard_utils": "*",
    "switchboard_widgets": "*",
    "switchboard_names": "*",
    "tasks": "*",
    "text": "*",
    "value_manager": "*",
}


bootstrap_package(globals(), include=DEFAULT_INCLUDE)
