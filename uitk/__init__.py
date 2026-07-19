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
        ui = sb.loaded_ui.my_app
        ui.show(app_exec=True)

    Using individual widgets::

        from uitk.widgets.pushButton import PushButton

        button = PushButton("Click Me")
        button.menu.add("Option 1")  # Built-in menu support

Key Modules:
    switchboard: Dynamic UI loader and event handler (also home of the
        ``Signals`` slot-annotation decorator, in ``switchboard.slots``)
    events: Event filters and mouse tracking utilities
    widgets: Enhanced Qt widget classes with mixins
    managers: Standalone services (settings, state, values, presets,
        icons, shortcuts, file registries) consumed compositionally
        across the package
    themes: QSS-based theming — the ``StyleSheet`` engine + ``style.qss``

Attributes:
    __version__: Current package version string.
"""
import importlib

from pythontk.core_utils.module_resolver import bootstrap_package

__package__ = "uitk"
__version__ = "1.3.28"


DEFAULT_INCLUDE = {
    # Standalone-process bootstrap (kept Switchboard-free so high-DPI setup
    # can run before any Qt machinery loads).
    "_bootstrap": "configure_high_dpi",
    # Switchboard symbols are mapped to their specific composition modules
    # (rather than the package facade) to preserve per-symbol lazy loading.
    # `from uitk import Signals` should not drag in the Switchboard machinery.
    "switchboard._core": "Switchboard",
    "switchboard.slots": ["Signals", "SlotWrapper"],
    "switchboard.shortcuts": "Shortcut",
    "events": ["EventFactoryFilter", "MouseTracking"],
    # Deprecated aliases for the registry classes (moved to
    # uitk.managers.registry_manager); resolving them warns via the shim.
    "file_manager": ["FileContainer", "FileManager"],
    "compile": ["compile_ui", "ensure_compiled", "is_compiled_fresh", "precompile_async"],
    "loaders": ["CompiledLoader", "RuntimeLoader"],
    "widgets.marking_menu._marking_menu": "MarkingMenu",
    # Widgets
    "widgets.attributeWindow._attributeWindow": "AttributeWindow",
    # AttributeSpec + the kind-handler registry live in ``uitk.bridge.spec``
    # so the AttributeWindow panels and the DCC bridges share one source of
    # truth.
    "bridge.spec": [
        "AttributeSpec",
        "KindHandler",
        "make_widget",
        "read_value",
        "set_value",
        "connect_changed",
        "infer_kind",
        "register_kind",
        "get_handler",
    ],
    "widgets.checkBox": "CheckBox",
    "widgets.collapsableGroup": "CollapsableGroup",
    "widgets.colorSwatch": "ColorSwatch",
    "widgets.editors.color_mapping_editor": [
        "ColorMappingEditor",
        "ColorMappingDialog",
    ],
    "widgets.editors.editor_panel": "EditorPanel",
    "widgets.comboBox": "ComboBox",
    "widgets.doubleSpinBox": "DoubleSpinBox",
    "widgets.embeddedMenu": ["EmbeddedMenuWidget", "PersistentMenu"],
    "widgets.expandableList": "ExpandableList",
    "widgets.header": "Header",
    "widgets.footer": "Footer",
    "widgets.label": "Label",
    "widgets.lineEdit": "LineEdit",
    "widgets.mainWindow": "MainWindow",
    "widgets.menu": "Menu",
    "widgets.menuButton": "MenuButton",
    "widgets.messageBox": "MessageBox",
    "widgets.optionBox._optionBox": [
        "OptionBox",
        "OptionBoxContainer",
    ],
    "widgets.optionBox.utils": [
        "OptionBoxManager",
        "add_option_box",
        "add_clear_option",
        "add_menu_option",
        "patch_widget_class",
        "patch_common_widgets",
    ],
    "widgets.optionBox.options._options": ["BaseOption", "ButtonOption"],
    "widgets.optionBox.options.action": ["ActionOption", "MenuOption"],
    "widgets.optionBox.options.browse": "BrowseOption",
    "widgets.optionBox.options.clear": ["ClearOption", "ClearButton"],
    "widgets.optionBox.options.reset": "ResetOption",
    "widgets.optionBox.options.pin_values": "PinValuesOption",
    "widgets.optionBox.options.toggle": "ToggleOption",
    "widgets.optionBox.options.disable": "DisableOption",
    "widgets.optionBox.options.value": "ValueOption",
    "widgets.optionBox.options.affix": "AffixOption",
    "widgets.optionBox.options.option_menu": ["OptionMenuOption", "ContextMenuOption"],
    "widgets.progressBar": "ProgressBar",
    "widgets.pushButton": "PushButton",
    "widgets.region": "Region",
    # Item-view delegates (uitk.widgets.delegates) — RowSelectionBorderDelegate
    # is the base; the capture delegates build on it and ship Bordered* variants.
    "widgets.delegates.row_selection": "RowSelectionBorderDelegate",
    "widgets.delegates.centered_icon": [
        "CenteredIconActionDelegate",
        "paint_centered_icon",
        "fill_cell_background",
    ],
    "widgets.delegates.shortcut_capture": [
        "ShortcutCaptureDelegate",
        "BorderedShortcutCaptureDelegate",
        "install_shortcut_capture",
    ],
    "widgets.delegates.choice_capture": [
        "ChoiceCaptureDelegate",
        "BorderedChoiceCaptureDelegate",
        "install_choice_capture",
    ],
    "widgets.separator": "Separator",
    "widgets.slider": "Slider",
    "widgets.tableWidget": "TableWidget",
    "widgets.scriptOutput": [
        "ScriptOutput",
        "ScriptHighlighter",
        "ScriptHighlightRule",
    ],
    "widgets.textEdit": "TextEdit",
    "widgets.textEditLogHandler": "TextEditLogHandler",
    "widgets.textViewBox": "TextViewBox",
    "widgets.windowPanel": "WindowPanel",
    "widgets.toolBox": "ToolBox",
    "widgets.treeWidget": "TreeWidget",
    "widgets.widgetComboBox": "WidgetComboBox",
    "widgets.sequencer._sequencer": ["SequencerWidget", "ClipData", "TrackData"],
    # Widget mixins
    "widgets.mixins.attributes": "AttributesMixin",
    "widgets.mixins.convert": "ConvertMixin",
    "widgets.mixins.menu_mixin": "MenuMixin",
    "widgets.mixins.option_box_mixin": "OptionBoxMixin",
    "widgets.mixins.text": [
        "RichTextFormatter",
        "TextTruncation",
        "RichText",
        "TextOverlay",
    ],
    # Standalone services (uitk.managers / uitk.themes)
    "managers.icon_manager": "IconManager",
    "managers.preset_manager": "PresetManager",
    "managers.recent_values_store": "RecentValuesStore",
    "managers.registry_manager": ["FileRegistry", "RegistryManager"],
    "managers.settings_manager": "SettingsManager",
    "managers.shortcut_manager": "ShortcutManager",
    "managers.state_manager": "StateManager",
    "managers.value_manager": "ValueManager",
    "themes.style_sheet": "StyleSheet",
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
