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
__version__ = "1.6.2"


DEFAULT_INCLUDE = {
    # Standalone-process bootstrap (kept Switchboard-free so high-DPI setup
    # can run before any Qt machinery loads).
    "_bootstrap": "Bootstrap",
    # Switchboard symbols are mapped to their specific composition modules
    # (rather than the package facade) to preserve per-symbol lazy loading.
    # `from uitk import Signals` should not drag in the Switchboard machinery.
    "switchboard._core": "Switchboard",
    "switchboard.slots": ["Signals", "SlotWrapper", "Cancelable"],
    "switchboard.shortcuts": "Shortcut",
    "events": ["EventFactoryFilter", "MouseTracking", "TreeDragReparentFilter"],
    # Launchable-entry handlers. ``UiHandler`` / ``ExternalAppHandler`` are what a
    # DCC host composes its handler set from (the DCC-specific ones subclass
    # ``UiHandler`` downstream), so they belong on the package namespace like every
    # other public class — consumers must not reach into ``uitk.handlers.*``.
    "handlers.base_handler": "BaseHandler",
    "handlers.handler_entry": "HandlerEntry",
    "handlers.ui_handler": "UiHandler",
    "handlers.external_app_handler": "ExternalAppHandler",
    "handlers.editor_handler": "EditorHandler",
    # ``.ui`` compilation and the two loaders (compiled ``_ui.py`` / runtime).
    "compile": ["UiCompiler", "PrecompileJob"],
    "loaders": ["CompiledLoader", "RuntimeLoader"],
    # Qt Designer widget-box registrar (`python -m uitk.designer`).
    "designer._designer": ["DesignerPlugin", "DesignerWidget"],
    "widgets.marking_menu._marking_menu": "MarkingMenu",
    "widgets.marking_menu._resolver": "MenuResolver",
    # Widgets
    "widgets.attribute_window": "AttributeWindow",
    # AttributeSpec (Qt-free, ``uitk.bridge.attribute_spec``) + the kind-handler
    # registry (``uitk.bridge.spec``) so the AttributeWindow panels and the DCC
    # bridges share one source of truth.
    "bridge.attribute_spec": "AttributeSpec",
    "bridge.spec": [
        "KindHandler",
        "KindFactory",
    ],
    # The rest of the bridge surface a CONSUMER needs, mapped per module so the
    # laziness ``uitk.bridge`` was built for survives the promotion: reaching
    # ``Parameters`` must not charge the caller ``bridge.slots`` and its widget
    # tree. Here rather than left to ``from uitk.bridge import ...`` because a
    # tentacle slot module may not deep-import (``test_dcc_invariants``
    # .TestSlotImportDiscipline) -- it reaches uitk through ``self.sb``, which
    # resolves exactly this namespace.
    "bridge.parameters": ["Parameters", "ParamRegistry"],
    "bridge.slots": "BridgeSlotsBase",
    "widgets.checkBox": "CheckBox",
    "widgets.collapsableGroup": "CollapsableGroup",
    "widgets.colorSwatch": "ColorSwatch",
    "widgets.gradient_slider": "GradientSlider",
    "widgets.editors.color_editor": [
        "ColorEditor",
        "ColorEditorPopup",
        "ColorRampEditor",
        "RampPreview",
        "PulseWaveform",
        "FadeWaveform",
    ],
    "widgets.editors.color_mapping_editor": [
        "ColorMappingEditor",
        "ColorMappingDialog",
    ],
    "widgets.editors.editor_panel": "EditorPanel",
    # Affix-field rows in a Menu editing any ptk.NamingConvention-shaped store.
    "widgets.editors.naming_convention_editor": "NamingConventionEditor",
    "widgets.editors.preset_editor": "PresetEditor",
    # Qt-free: what a host's hotkey-collision checker returns to ShortcutEditor.
    "widgets.editors.shortcut_editor.collision_conflict": "CollisionConflict",
    "widgets.comboBox": "ComboBox",
    "widgets.doubleSpinBox": "DoubleSpinBox",
    "widgets.spinBox": "SpinBox",
    "widgets.embeddedMenu": ["EmbeddedMenuWidget", "PersistentMenu"],
    "widgets.expandableList": "ExpandableList",
    "widgets.context_menu": ["ContextMenu", "MenuRow"],
    # A view header's show / hide / reorder menu (TableWidget / TreeWidget option).
    "widgets.column_config": "ColumnConfig",
    "widgets.header": "Header",
    "widgets.footer": ["Footer", "FooterStatusController"],
    "widgets.formPanel": "FormPanel",
    "widgets.label": "Label",
    "widgets.lineEdit": "LineEdit",
    "widgets.mainWindow": "MainWindow",
    "widgets.menu": "Menu",
    "widgets.menuButton": "MenuButton",
    "widgets.messageBox": "MessageBox",
    "widgets.overflow_indicator": "OverflowIndicator",
    "widgets.optionBox._optionBox": [
        "OptionBox",
        "OptionBoxContainer",
    ],
    "widgets.optionBox.option_box_manager": "OptionBoxManager",
    "widgets.optionBox.options._options": ["BaseOption", "ButtonOption"],
    "widgets.optionBox.options.action": ["ActionOption", "MenuOption"],
    "widgets.optionBox.options.browse": "BrowseOption",
    "widgets.optionBox.options.clear": ["ClearOption", "ClearButton"],
    "widgets.optionBox.options.reset": "ResetOption",
    "widgets.optionBox.options.pin_values": "PinValuesOption",
    "widgets.optionBox.options.recent_values": "RecentValuesOption",
    "widgets.optionBox.options.toggle": "ToggleOption",
    "widgets.optionBox.options.disable": "DisableOption",
    "widgets.optionBox.options.value": "ValueOption",
    "widgets.optionBox.options.affix": "AffixOption",
    "widgets.optionBox.options.choice": "ChoiceOption",
    "widgets.optionBox.options.option_menu": ["OptionMenuOption", "ContextMenuOption"],
    "widgets.progressBar": "ProgressBar",
    "widgets.pushButton": "PushButton",
    "widgets.region": "Region",
    # Item-view delegates (uitk.widgets.delegates) — RowSelectionBorderDelegate
    # is the base; the capture delegates build on it and ship Bordered* variants.
    "widgets.delegates.row_selection": "RowSelectionBorderDelegate",
    "widgets.delegates.centered_icon": [
        "CenteredIconActionDelegate",
        "ICON_OPACITY_ROLE",
    ],
    "widgets.delegates.shortcut_capture": [
        "ShortcutCaptureDelegate",
        "BorderedShortcutCaptureDelegate",
    ],
    "widgets.delegates.choice_capture": [
        "ChoiceCaptureDelegate",
        "BorderedChoiceCaptureDelegate",
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
    "widgets.form_rows": "FormRows",
    "widgets.toolBox": "ToolBox",
    "widgets.treeWidget": "TreeWidget",
    "widgets.widgetComboBox": "WidgetComboBox",
    "widgets.sequencer._sequencer": [
        "SequencerWidget",
        "ClipData",
        "TrackData",
        "AttributeColorDialog",
    ],
    "widgets.sequencer._keyframe": ["KeyframeItem"],
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
    "managers.cancel_manager": ["CancelManager", "CancelProvider"],
    "managers.cursor_manager": ["CursorManager", "OverrideCursorGuard"],
    "managers.color_model": "ColorModel",
    "managers.field_visibility": "FieldVisibility",
    "managers.host_exit_guard": "HostExitGuard",
    "managers.window_height": "WindowHeight",
    "managers.window_auto_hide": "WindowAutoHide",
    "managers.icon_manager": "IconManager",
    "managers.optional_package_manager": "OptionalPackageManager",
    "managers.preset_manager": "PresetManager",
    "managers.recent_values_store": "RecentValuesStore",
    "managers.registry_manager": ["FileRegistry", "RegistryManager"],
    "managers.settings_manager": "SettingsManager",
    "managers.shortcut_manager": "ShortcutManager",
    "managers.state_manager": "StateManager",
    "managers.reset_gesture": "ResetGesture",
    "managers.value_manager": "ValueManager",
    "managers.model_binding": "ModelBinding",
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
