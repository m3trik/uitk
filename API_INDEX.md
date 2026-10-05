# uitk — API Index

_Auto-generated. Do not edit by hand. Compact symbol index — grep this for a name; for full signatures/docs, slice [API_REGISTRY.md](API_REGISTRY.md) (never Read it whole)._

### `__init__.py` — UITK - User Interface Toolkit for Qt/PySide applications.
- constants: DEFAULT_INCLUDE

### `_bootstrap.py` — Standalone-process bootstrap helpers.
- `class Bootstrap`
  - methods: configure_platform, positions_windows, composites, set_translucent, screen_backdrop, fades_windows, configure_high_dpi

### `bridge/attribute_spec.py` — The Qt-free half of the parameter-panel contract: :class:`AttributeSpec`.
- `class AttributeSpec`
  - methods: from_value, display_label, infer_kind

### `bridge/formatters.py` — Per-target-language value formatters for bridge parameter rendering.
- `class Formatters(_FormattersInternal)`
  - methods: python_literal, lua_literal, js_literal, cli_raw

### `bridge/parameters.py` — Registry helpers for bridge parameter dicts.
- `class Parameters(_ParametersInternal)`
  - methods: scope_spec, shader_type_spec, carrier_spec, rig_mode_spec, referenced_keys, defaults, affix_parts, render_context
- `class ParamRegistry(object)`
  - methods: referenced_keys, defaults, render_context, affix_parts

### `bridge/slots.py` — Generic DCC-bridge slot base class.
- `class BridgeSlotsBase(_BridgeSlotsInternal)`
  - methods: params_module, template_dir, make_bridge, list_template_modes, b000, optional_packages, optional_package_available, ensure_optional_package, resolve_scope_objects, empty_scope_message, scoped_objects, bridge, peek_bridge, panel_log, default_output_dir, ensure_bridge_temp_dir, resolved_output_dir, require_output_dir, format_param_tooltip, live_param_tooltips, live_param_tooltip_blocks, set_param_enabled, param_supersessions, collect_param_values, make_preset_store, select_initial_template_index, template_description, cmb000_init, refresh_templates, open_templates_folder, register_log_link_handler, docs_url, clear_log, header_menu_items, help_spec, header_init, reveal_folder

### `bridge/spec.py` — Kind-handler registry for parameterised forms (the Qt half of the contract).
- constants: INT_MIN, INT_MAX, FLOAT_MIN, FLOAT_MAX
- `class KindHandler`
- `class KindFactory(_KindFactoryInternal)`
  - methods: infer_kind, register_kind, get_handler, make_widget, kind_of, read_value, set_value, set_choices, to_literal, affix_parts, connect_changed

### `bridge/tooltip.py` — Rich-text tooltip + template-description helpers for bridge panels.
- `class Tooltip(_TooltipInternal)`
  - methods: format_param_tooltip, template_description

### `compile.py` — Compile Qt Designer .ui files to switchboard-augmented _ui.py modules.
- constants: UIC_TIMEOUT_SECONDS, UIC_BINDINGS
- `class PrecompileJob`
  - methods: is_alive
- `class UiCompiler(_UiCompilerInternal)`
  - methods: hash_ui_source, compiled_path_for, read_embedded_hash, read_embedded_tags, read_embedded_base_class, read_embedded_form_class, is_compiled_fresh, extract_metadata, compile_ui, ensure_compiled, precompile_async, main

### `designer/_designer.py` — Publish uitk widgets to Qt Designer's widget box.
- constants: PLUGIN_PATH_ENV
- `class DesignerWidget(NamedTuple)`
  - methods: xml
- `class DesignerPlugin(_DesignerPluginInternal)`
  - methods: is_design_time, set_design_time, collect, register, plugin_dirs, environment, launch

### `events.py` — Event handling utilities for Qt applications.
- `class EventFactoryFilter(QtCore.QObject)`
  - methods: install, uninstall, is_installed, eventFilter
- `class MouseTracking(QtCore.QObject, pythontk.LoggingMixin)`
  - methods: should_capture_mouse, register_external_widgets, update_child_widgets, track, is_widget_valid, eventFilter
- `class TreeDragReparentFilter(QtCore.QObject)`
  - methods: install, eventFilter

### `examples/example.py` — UITK Example — a polished tour of the framework.
- `class ExampleSlots(pythontk.LoggingMixin)`
  - methods: header_init, txt_input_init, txt_input, cmb_options_init, cmb_options, cmb_view_init, tree_demo_init, tree_demo

### `handlers/base_handler.py` — Common infrastructure for Switchboard handlers.
- `class BaseHandler(pythontk.SingletonMixin, pythontk.LoggingMixin)`
  - methods: instance, config
- `class LaunchableHandlerProtocol(Protocol)`
  - methods: entries, launch, close, is_visible

### `handlers/editor_handler.py` — Launchable-contract front end for the Switchboard's bundled editors.
- `class EditorHandler(BaseHandler)`
  - methods: entries, launch, focus, close, is_visible, launch_code

### `handlers/external_app_handler.py` — Register, install-on-demand, and launch external Python apps as subprocesses.
- `class ExternalAppHandler(BaseHandler)`
  - methods: discover, add_provider, register, is_registered, unregister, entries, save_tags, close, is_visible, launch_code, launch

### `handlers/handler_entry.py` — Unified launchable-entry data class shared by all Switchboard handlers.
- `class HandlerEntry`
  - methods: all_tags, editable_tags

### `handlers/ui_handler.py`
- `class UiHandler(BaseHandler)`
  - methods: editors, can_resolve, get, show, setup_lifecycle, pin_click_hides, pin_on_tap, default_persistence, window_persistence, persistence_override, set_persistence_override, resolve_persistence, is_persistence_explicit, reapply_persistence, apply_styles, entries, hosting_handler, launch, close, is_visible, focus, launch_code, bootstrap_code, save_tags

### `loaders/compiled.py` — Switchboard delegate that loads UIs via compiled _ui.py modules.
- `class CompiledLoader`
  - methods: read_ui_tags, load, on_tags_written

### `loaders/runtime.py` — Switchboard delegate that loads UIs at runtime via QUiLoader.
- `class RuntimeLoader`
  - methods: load, read_ui_tags, on_tags_written

### `managers/cancel_manager.py` — Host strategy for cancelling long-running slots.
- `class CancelProvider`
  - methods: install, report_warning, report_info, open_bracket, close_bracket, current_bracket, create_sources, begin, tick, end, pump
- `class CancelManager`
  - methods: register, provider, reset, new_scope

### `managers/color_model.py` — The observable colour value a picker and its widgets share.
- `class ColorModel`
  - methods: hsva, hue, saturation, value, alpha, rgbf, rgbaf, color, hex, mixed, set_hsv, set_rgbf, set_color, to_rgbaf, set_mixed, subscribe, unsubscribe, muted

### `managers/cursor_manager.py` — One owner for every cursor change in uitk.
- `class OverrideCursorGuard(QtCore.QObject)`
  - methods: shape, holding, apply, clear, holds, is_stale, notify_stack_drained, reconcile
- `class CursorManager`
  - methods: pop_stack, push_stack, suspend, drain, release, busy, has_explicit_cursor, push, pop, heal_hover

### `managers/field_visibility.py` — Which fields a container shows, per named mode.
- `class FieldVisibility`
  - methods: register, divider, group, define, bind, keys, mode, visible, show, set_visible, set_widget_visible, is_hidden_field

### `managers/host_exit_guard.py` — Keep a host application's exit from faulting in shiboken's static teardown.
- `class HostExitGuard`
  - methods: arm, note, release

### `managers/icon_manager.py`
- `class IconManager`
  - methods: set_default_color, register_icon_dir, get, fit_size, fit_icon, swap_icon, set_icon, set_label_icon, registered_info, update_widget_icons, clear_cache, get_cache_stats

### `managers/model_binding.py` — Keep widgets in step with a model uitk never sees: read on change, write on edit.
- `class ModelBinding`
  - methods: bind, refresh

### `managers/optional_package_manager.py` — Provisioning for optional packages a panel needs importable in THIS session.
- `class OptionalPackageManager(_OptionalPackageManagerInternal)`
  - methods: available, pip_python, default_install, install, ensure, version_tuple, split_requirement

### `managers/preset_manager.py`
- constants: PRESETS_ROOT_ENV_VAR
- `class PresetManager(_PresetWidgetScope, _PresetRootMigration, pythontk.LoggingMixin)`
  - methods: from_widgets, setup, preset_dir, on_change, active_preset, is_modified, on_modified_changed, refresh_modified_state, connect_value_widgets, save, load, list, source, is_read_only, is_locked, key, notify, delete, rename, exists, read, refresh_combo, make_preset_combo, wire_combo, get_presets_root, scope, exclude, include, QStandardPaths_writableLocation, QStandardPaths_genericConfigLocation

### `managers/recent_values_store.py` — Widget-free *recent values* model — the shared source of truth for value history.
- `class RecentValueEntry`
- `class RecentValuesStore`
  - methods: normalize_value, subscribe, unsubscribe, values, is_valid, valid_values, record, add, remove, clear, prune_invalid, display_map

### `managers/registry_manager.py` — Typed file registries backing Switchboard discovery.
- `class FileRegistry(pythontk.NamedTupleContainer)`
  - methods: extend
- `class RegistryManager(pythontk.HelpMixin, pythontk.LoggingMixin)`
  - methods: get_base_dir, resolve_path, create, contains_location, get_container, list_containers, remove_container

### `managers/reset_gesture.py` — ``ResetGesture`` — the click grammar every *Restore Defaults* control shares.
- `class ResetGesture(QtCore.QObject)`
  - methods: action_for, modifier_keys, supports_saving, tooltip, perform, trigger, refresh_tooltip, flash, eventFilter

### `managers/settings_manager.py`
- constants: DEFAULT_ORG_NAME, DEFAULT_APP_NAME
- `class SettingsManager`
  - methods: branch, set_defaults, value, decode_stored_value, encode_stored_value, setValue, on_change, keys, setByteArray, getByteArray, remove, clear, sync

### `managers/shortcut_manager.py` — Generic keyboard-shortcut primitives, usable by any Qt widget.
- constants: SCOPE_NAME_TO_CONTEXT, SCOPE_CONTEXT_TO_NAME
- `class GlobalShortcut(QtCore.QObject)`
  - methods: eventFilter, setEnabled, isEnabled, setKey, setContext, dispose
- `class ShortcutManager`
  - methods: register_host_window, unregister_host_window, host_window_names, hide_bound_menu_items, set_hide_bound_menu_items, context_to_scope_name, scope_name_to_context, host_namespace_suffix, resolve_application_host, find_duplicate_application_shortcuts, add_shortcut, add_shortcuts_batch, add_global_shortcut, add_info_entry, add_gesture, overlay, remove_shortcut, clear_all, on_change, rebind_shortcut, show_editor, get_shortcuts_info, has_shortcut, get_shortcut, get_registry

### `managers/state_manager.py`
- `class StateManager(pythontk.LoggingMixin)`
  - methods: apply, suppress_save, is_applying, save, save_value, load, for_widget, reset_all, reset, clear, has_default, default_for, save_defaults, clear_saved_defaults, has_saved_defaults, capture_default, set_default, save_custom, load_custom, clear_custom

### `managers/value_manager.py`
- `class ValueManager`
  - methods: combo_value, get_value, set_value, get_widget_type_info, is_supported_widget, get_value_by_signal, set_value_by_signal

### `managers/window_auto_hide.py` — Hide a floating window once the cursor has visited it and left.
- `class WindowAutoHide(QtCore.QObject)`
  - methods: eventFilter, cursor_inside, check

### `managers/window_height.py` — How a window follows the height of what it is holding.
- `class WindowHeight`
  - methods: activate_layouts, sync_min, adjust_by, fit_to_content, fit_host, fit_host_later

### `switchboard/_core.py`
- `class Switchboard(QtCore.QObject, pythontk.HelpMixin, pythontk.LoggingMixin, SwitchboardSlotsMixin, SwitchboardShortcutMixin, SwitchboardWidgetMixin, SwitchboardRulesMixin, SwitchboardWidgetValuesMixin, SwitchboardControlGroupsMixin, SwitchboardDialogsMixin, SwitchboardPlacementMixin, SwitchboardEventLoopMixin, SwitchboardNameMixin, SwitchboardEditorsMixin, SwitchboardStyleMixin, SwitchboardNamespaceMixin)`
  - methods: register_handler, iter_handler_entries, active_ui, current_ui, prev_ui, prev_slot, visible_windows, register, load_all_ui, load_ui, add_ui, get_ui, get_ui_relatives, find_ui_filename, save_ui_tags, ui_history, show_prev_ui, repeat_last

### `switchboard/control_groups.py`
- `class SwitchboardControlGroupsMixin`
  - methods: create_button_groups, toggle_multi, connect_multi, add_reset_buttons, link_spinboxes, set_axis_for_checkboxes, get_axis_from_checkboxes, hide_unmatched_groupboxes

### `switchboard/dialogs.py`
- `class SwitchboardDialogsMixin`
  - methods: busy_cursor, progress, progress_adapter, confirm, message_box, text_view_dialog, data_view_dialog, save_data_dialog, file_dialog, dir_dialog, save_file_dialog, input_dialog, list_input_dialog, form_dialog, form_panel, modal_menu

### `switchboard/editors.py` — Mixin that exposes the bundled editor windows on the Switchboard.
- `class SwitchboardEditorsMixin`
  - methods: editors

### `switchboard/event_loop.py`
- `class SwitchboardEventLoopMixin`
  - methods: invert_on_modifier, simulate_key_press, defer_with_timer, gc_protect

### `switchboard/history.py` — Ordered, capped history with optional weak storage and key-based filtering.
- `class History`
  - methods: maxlen, add, remove, clear, view, get

### `switchboard/names.py`
- `class SwitchboardNameMixin`
  - methods: convert_to_legal_name, get_slot_class_names, get_slot_file_names, get_base_name, get_tags_from_name, has_tags, edit_tags, filter_tags, get_unknown_tags, unpack_names, get_widgets_by_string_pattern, get_methods_by_string_pattern

### `switchboard/namespace.py` — Mixin that falls back to the uitk package namespace for unknown attributes.
- `class SwitchboardNamespaceMixin`

### `switchboard/placement.py`
- `class SwitchboardPlacementMixin`
  - methods: get_cursor_offset_from_center, center_widget

### `switchboard/rules.py`
- `class SwitchboardRulesMixin`
  - methods: enable_when, show_when, text_from, value_from, refresh_dependencies

### `switchboard/shortcuts.py` — Switchboard-side keyboard shortcut machinery.
- `class Shortcut`
- `class SwitchboardShortcutMixin`
  - methods: register_slots_shortcuts, widget_has_shortcut, get_shortcut_registry, get_static_shortcut_registry, set_user_shortcut, dispose_shortcuts, register_command, unregister_command, get_command_registry, set_command_shortcut, set_binding_hidden, set_binding_editable

### `switchboard/slots.py`
- `class Signals`
  - methods: blockSignals
- `class Cancelable`
- `class SlotWrapper`
- `class SwitchboardSlotsMixin`
  - methods: get_default_signals, get_available_signals, slots_instantiated, get_slots_instance, init_slot, call_slot, get_slot, get_slot_from_widget, mark_missing_slot, notify_missing_slot, connect_slot, slot_history

### `switchboard/style.py` — Mixin that exposes the :class:`StyleSheet` class on the Switchboard.
- `class SwitchboardStyleMixin`
  - methods: style

### `switchboard/widget_values.py`
- `class SwitchboardWidgetValuesMixin`

### `switchboard/widgets.py`
- `class SwitchboardWidgetMixin`
  - methods: unmet_policy, gate, recheck_gates, is_registered_ui, ui_name_resolves, menu_button_target_name, menu_button_target_resolves, apply_visibility_policy, resolve_widget_class, get_icon, register_widget, get_widget, get_widget_from_slot, is_widget, get_parent_widgets, get_all_windows, get_all_widgets, get_widget_at

### `testing.py` — Test isolation for every suite in the ecosystem — keep test runs off live user state.
- `class TestSandbox(_TestSandboxInternal, pythontk.TestSandbox)`
  - methods: qsettings, presets, activate, is_active

### `themes/style_sheet.py`
- `class StyleSheet(QtCore.QObject, pythontk.LoggingMixin)`
  - methods: repolish_tree, theme_changed, get_icon_color, set_theme, set_theme_overrides, apply_theme, reload, clear_caches, set_variable, get_variable, get_variable_px, get_variables, export_overrides, import_overrides, reset_overrides, set

### `widgets/attribute_window.py` — Dynamic attribute editor -- :class:`AttributeWindow`, a ``Menu`` popup whose
- `class AttributeWindow(Menu)`
  - methods: initialize_ui, refresh_attributes, clear_ui_elements, default_get_attribute_func, create_set_attribute_func_wrapper, default_set_attribute_func, is_valid_attribute, is_type_supported, add_attributes, add_attribute_spec, emit_value_changed, emit_composite_value_changed, setup_label, on_label_toggled, on_button_clicked, add_to_layout, showEvent

### `widgets/checkBox.py`
- `class CheckBox(QtWidgets.QCheckBox, MenuMixin, AttributesMixin, RichText, TextOverlay)`
  - methods: set_checkbox_rich_text_style, checkState, setCheckState, hitButton, mousePressEvent

### `widgets/collapsableGroup.py`
- `class CollapsableGroup(QtWidgets.QGroupBox, AttributesMixin)`
  - methods: getRestoreState, setRestoreState, toggle_expand, setLayout, addWidget, addLayout, sizeHint, paintEvent

### `widgets/colorSwatch.py`
- `class ColorSwatch(QtWidgets.QPushButton, AttributesMixin, ConvertMixin)`
  - methods: color, keep_square, setSwatchColor, setKeepSquare, resizeEvent, settings, saveColor, loadColor, canSaveLoadColor, initializeColor, updateBackgroundColor, mouseDoubleClickEvent

### `widgets/column_config.py` — A view's header menu of columns to show, hide and reorder, with the layout remembered.
- `class ColumnConfig(QtCore.QObject)`
  - methods: attach, of, header_of, configure, header, settings, labels, order, can_hide, set_hidden, set_order, build_menu, show_menu, save, restore

### `widgets/comboBox.py`
- `class CustomStyle(QtWidgets.QProxyStyle)`
  - methods: drawComplexControl, styleHint, pixelMetric
- `class AlignedComboBox(QtWidgets.QComboBox)`
  - methods: setHeaderText, setHeaderAlignment, get_stylesheet_property, format_current_display_text, paintEvent
- `class ComboBox(AlignedComboBox, MenuMixin, OptionBoxMixin, AttributesMixin, RichText, TextOverlay)`
  - methods: clear, addItem, addItems, insertItem, insertItems, current_text_suffix, current_text_prefix, setCurrentTextPrefix, setCurrentTextSuffix, items, currentData, setCurrentData, currentText, setCurrentText, setItemText, setAsCurrent, setCurrentIndex, check_index, mousePressEvent, mouseDoubleClickEvent, begin_rename, set_cells, cell_spec, format_cell, cell_text, add_cells, item_cells, set_item_cells, begin_cell_edit, cell_editing, resizeEvent, focusOutEvent, editable, setEditable, force_header_display, add_header, add_single, add, removeItem, showPopup, keyPressEvent

### `widgets/context_menu.py` — A popup context menu whose rows can expand into sub-rows.
- `class MenuRow(QtWidgets.QPushButton, OptionBoxMixin)`
  - methods: has_flyout, add_option_menu, option_menu, resizeEvent, sizeHint, paintEvent
- `class ContextMenu(Menu)`
  - methods: list, add, add_separator, add_entries, keyPressEvent, popup, exec_, dispose

### `widgets/delegates/centered_icon.py` — Centered icon painting for item-view cells.
- constants: ICON_OPACITY_ROLE, ACTION_NONINTERACTIVE_ROLE
- `class CenteredIconActionDelegate(RowSelectionBorderDelegate)`
  - methods: fill_cell_background, suppress_hover_if_noninteractive, paint_centered_icon, paint

### `widgets/delegates/choice_capture.py` — In-cell choice (dropdown) capture for item views.
- `class ChoiceCaptureDelegate(QtWidgets.QStyledItemDelegate)`
  - methods: set_choices, createEditor, setEditorData, setModelData, install_choice_capture
- `class BorderedChoiceCaptureDelegate(ChoiceCaptureDelegate, RowSelectionBorderDelegate)`

### `widgets/delegates/row_selection.py` — Opt-in delegate for views whose cells carry their own background.
- `class RowSelectionBorderDelegate(QtWidgets.QStyledItemDelegate)`
  - methods: paint, paint_row_selection_border

### `widgets/delegates/shortcut_capture.py` — In-cell key-combination capture for item views.
- `class ShortcutCaptureEdit(QtWidgets.QLineEdit)`
  - methods: sequence, event, keyPressEvent
- `class ShortcutCaptureDelegate(QtWidgets.QStyledItemDelegate)`
  - methods: createEditor, setEditorData, setModelData, install_shortcut_capture
- `class BorderedShortcutCaptureDelegate(ShortcutCaptureDelegate, RowSelectionBorderDelegate)`

### `widgets/doubleSpinBox.py`
- `class DoubleSpinBox(WheelStepMixin, SpinBoxAdjustingMixin, FeedbackMixin, SpinBoxTextColorMixin, PrefixColumnMixin, QtWidgets.QDoubleSpinBox, MenuMixin, AttributesMixin)`
  - methods: textFromValue

### `widgets/editors/color_editor.py` — An embeddable colour editor, and the popup that is merely one of its hosts.
- `class ColorEditor(QtWidgets.QWidget, AttributesMixin)`
  - methods: model, color, qcolor, set_mixed, register_section, section, add_slider
- `class PulseWaveform`
  - methods: set_shape, shape, period
- `class FadeWaveform`
  - methods: set_shape, shape, period
- `class RampPreview(QtWidgets.QFrame)`
  - methods: set_stops, set_shape, shape, waveform, elapsed, set_base, sample, composite, display, showEvent, hideEvent, paintEvent
- `class ColorRampEditor(QtWidgets.QWidget)`
  - methods: set_shape, set_reference, labels, editors, editor, colors, decided, set_colors, set_mixed
- `class ColorEditorPopup(QtWidgets.QDialog)`
  - methods: keyPressEvent, color, qcolor, get_color

### `widgets/editors/color_mapping_editor.py` — Reusable color-mapping editor widget.
- `class ColorMappingEditor(QtWidgets.QWidget)`
  - methods: add_action_button, restore_defaults, color_map, apply_color_map
- `class ColorMappingDialog(QtWidgets.QDialog)`
  - methods: showEvent, header, footer, color_map

### `widgets/editors/editor_panel.py` — Editor panel: WindowPanel + optional preset save/load row.
- `class EditorPanel(WindowPanel)`
  - methods: init_preset_row, preset_dir, export_preset_data, import_preset_data, save_preset, load_preset, delete_preset, rename_preset

### `widgets/editors/naming_convention_editor.py` — An editor for a naming convention, built into a uitk ``Menu``.
- `class NamingConventionEditor`
  - methods: default_groups, default_tooltip, build, add_row, save, fields, apply_preset

### `widgets/editors/preset_editor.py` — One window over every preset in the ecosystem: browse, lock, collect, share.
- `class PresetEditor(EditorPanel)`
  - methods: register_app_label, showEvent, tool_label, set_entry_filter, refresh, selected_prefix, select_prefix, selected_entries, select_entries, lock, hide_presets, duplicate, assign, delete, build_context_menu, build_tree_menu, build_collection_cell_menu, eventFilter, collection_filter, set_collection_filter, picked_collection, create_collection, edit_collection, delete_collection, build_collection_menu, prompt_new_collection, prompt_edit_collection, export_collection, import_bundle, apply_import, cancel_import

### `widgets/editors/shortcut_editor/_action_cells.py` — The Scope and Reset icon cells of a ShortcutEditor row, and the scope vocabulary.
- constants: USER_SCOPES, SCOPE_LABELS, SCOPE_ICONS, SCOPE_TOOLTIPS

### `widgets/editors/shortcut_editor/collision_conflict.py` — A shortcut collision a checker reports -- Qt-free.
- `class CollisionConflict`
  - methods: display_label

### `widgets/editors/shortcut_editor/manager_facade.py` — Adapter that lets the unified :class:`ShortcutEditor` render a standalone
- `class ManagerSwitchboardFacade(RegistrySwitchboardFacade)`

### `widgets/editors/shortcut_editor/registry_editor.py` — The unified shortcut editor: every binding in a Switchboard's registry.
- `class ShortcutEditor(_ActionCellsMixin, _CollisionChecksMixin, EditorPanel)`
  - methods: export_preset_data, import_preset_data, export_shortcuts, import_shortcuts, showEvent, refresh_ui_list, populate, open_over_facade, set_columns_hidden, reset_shortcut, scope_at, scope_interactive, add_collision_checker, remove_collision_checker

### `widgets/editors/shortcut_editor/registry_facade.py` — Generic Switchboard-shaped adapter for the unified :class:`ShortcutEditor`.
- `class RegistrySwitchboardFacade`
  - methods: get_ui, convert_to_legal_name, get_shortcut_registry, get_static_shortcut_registry, set_user_shortcut

### `widgets/editors/style_editor.py`
- constants: BUILTIN_THEMES_DIR, BASIC_TOKENS, LENGTH_TOKENS, ROW_H, CELL_EDITOR_H
- `class StyleEditor(EditorPanel)`
  - methods: theme, set_tier, export_preset_data, import_preset_data, populate, on_color_changed, on_length_changed, reset_variable, reset_all, refresh_row

### `widgets/editors/switchboard_browser/_switchboard_browser.py` — The browser panel: search, tag chips, row actions, and the header menu.
- `class SwitchboardBrowser(_LaunchMixin, EditorPanel)`
  - methods: hidden_uis, hidden_tags, set_search_scope, set_entry_filter, hide_inherited_tags, showEvent, launch_options

### `widgets/editors/switchboard_browser/filtering.py` — Which rows the browser lists: the show modes, the search scopes, the proxy.
- constants: SHOW_VISIBLE, SHOW_HIDDEN, SHOW_ALL, SCOPE_NAME, SCOPE_TAGS, SCOPE_BOTH, SCOPES, SCOPE_ICONS

### `widgets/editors/switchboard_browser/launch.py` — How the browser launches an entry: the options, the window persistence, the handler calls.
- constants: PERSISTENCE_STICKY, PERSISTENCE_TRANSIENT, PERSISTENCE_CONTEXT, PERSISTENCE_DEFAULT, PERSISTENCE_CHOICES
- `class LaunchOptions`

### `widgets/editors/switchboard_browser/model.py` — The browser's table model: one row per handler-exposed entry, nothing loaded.
- `class SwitchboardBrowserModel(QtCore.QAbstractTableModel)`
  - methods: refresh_after_launch, rowCount, columnCount, headerData, data, flags, setData, set_entry_filter, entry_for_name, all_unique_tags

### `widgets/embeddedMenu.py` — Host a live ``QMenu`` as ordinary widget content (non-popup), sized exactly to it.
- `class PersistentMenu(QtWidgets.QMenu)`
  - methods: setVisible
- `class EmbeddedMenuWidget(QtWidgets.QWidget)`
  - methods: init_ui, content_size, sizeHint, minimumSizeHint, resizeEvent, showEvent, fit_to_window

### `widgets/expandableList.py`
- `class ExpandableList(QtWidgets.QWidget, AttributesMixin)`
  - methods: getExpandPosition, setExpandPosition, setMinItemHeight, setMaxItemHeight, setFixedItemHeight, setSublistXOffset, setSublistYOffset, setOpenDelay, apply_preset, contains_items, get_items, get_item_text, get_parent_item_text, get_item_data, get_parent_item_data, set_item_data, clear, add, hide, showEvent, hideEvent, get_padding, sizeHint, eventFilter, leaveEvent

### `widgets/footer.py`
- `class Footer(QtWidgets.QWidget, AttributesMixin, SizeGripMixin)`
  - methods: container_layout, alignment, update_font_size, font, add_widget, add_action_button, progress_bar, status_label, size_grip, setText, text, setStatusText, setDefaultStatusText, statusText, getDefaultStatusText, getSizeGripEnabled, setSizeGripEnabled, setStatus, start_progress, update_progress, finish_progress, cancel_progress, set_progress_total, progress, busy_indicator, is_busy, set_busy, resizeEvent, showEvent, status_controller, attach_to
- `class FooterProgressContext`
- `class FooterStatusController`
  - methods: set_resolver, set_truncation, update

### `widgets/formPanel.py` — Themed form window: Header → labelled rows → output log → Footer.
- `class FormPanel(WindowPanel)`
  - methods: add, clear_rows, set_fields, revalidate, values, set_values, editor, logger, clear_output, set_status, run, apply_pending, pending_commit, arm_apply, disarm_apply, exec_panel, hideEvent, closeEvent, keyPressEvent

### `widgets/form_rows.py` — A form any layout can hold: labelled rows built the way a Menu is built.
- `class FormRows(QtWidgets.QWidget, AttributesMixin)`
  - methods: rows_layout, row_widgets, showEvent, add, add_section, clear_rows

### `widgets/gradient_slider.py` — A slider whose track shows the colour it is about to set.
- constants: STEPS
- `class GradientSlider(Slider)`
  - methods: channel, model, bind, refresh, event

### `widgets/header.py`
- `class Header(QtWidgets.QLabel, AttributesMixin, RichText, TextOverlay, pythontk.LoggingMixin)`
  - methods: pin_on_drag_only, set_default_pin_on_drag_only, pin_on_tap, set_default_pin_on_tap, claim_hide_as_tap, menu, get_icon_path, create_svg_icon, create_button, has_buttons, config_buttons, trigger_resize_event, resizeEvent, resize_buttons, update_font_size, setTitle, title, setVersion, version, setText, minimize_window, restore_window, toggle_maximize, toggle_fullscreen, hide_window, unhide_window, trigger_refresh, set_help_text, help_text, show_help, show_menu, toggle_collapse, collapse_window, expand_window, toggle_pin, reset_pin_state, eventFilter, mousePressEvent, event, mouseMoveEvent, mouseReleaseEvent, showEvent, attach_to, hideEvent, setHelpText, setPinOnDragOnly, getConfigButtons, setConfigButtons, getAutoHideWithOsFrame, setAutoHideWithOsFrame

### `widgets/label.py`
- `class Label(QtWidgets.QLabel, MenuMixin, OptionBoxMixin, AttributesMixin)`
  - methods: mousePressEvent, mouseReleaseEvent

### `widgets/lineEdit.py`
- `class LineEditFormatMixin(TextValidationMixin)`
- `class LineEdit(ShortcutGuardMixin, QtWidgets.QLineEdit, MenuMixin, OptionBoxMixin, AttributesMixin, LineEditFormatMixin)`
  - methods: set_value, value, data, clear_value, contextMenuEvent, showEvent, hideEvent

### `widgets/mainWindow.py`
- `class MainWindow(QtWidgets.QMainWindow, AttributesMixin, TooltipMixin, pythontk.LoggingMixin)`
  - methods: setCentralWidget, initialize_window_flags, edit_tags, pinned, set_pinned, is_pinned, visible_duration_ms, request_hide, slots, presets, is_stacked_widget, is_current_ui, register_widget, register_menu, menus, trigger_deferred, run_when_ready, perform_restore_state, sync_widget_values, eventFilter, adjust_height_by, fit_height_to_content, save_window_geometry, restore_window_geometry, clear_saved_geometry, setVisible, show, showEvent, register_children, focusInEvent, focusOutEvent, resizeEvent, moveEvent, hideEvent, closeEvent, setStyleSheet, reset_style

### `widgets/marking_menu/_marking_menu.py`
- `class MarkingMenu(_BindingsMixin, _HostingMixin, _NavigationMixin, _InputMixin, _PresentationMixin, QtWidgets.QWidget, pythontk.SingletonMixin, pythontk.LoggingMixin, pythontk.HelpMixin)`
  - methods: retire_all, retire, instance, ui_handler, get, stored_activation_key, default_bindings, bindings, on_bindings_changed, set_activation_key, start_menu_names, get_route_target, set_route_target, menu_theme, window_theme, resolve_hosted_theme, hosts_ui, addWidget, currentWidget, setCurrentWidget, setCurrentIndex, preload_menus, add_child_event_filter, child_enterEvent, child_leaveEvent, child_mouseButtonReleaseEvent, mousePressEvent, keyPressEvent, mouseDoubleClickEvent, mouseReleaseEvent, enable_input_logging, disable_input_logging, show, dismiss_for_action, hide, showEvent, paintEvent, hideEvent, dim_other_windows, restore_other_windows

### `widgets/marking_menu/_resolver.py` — Pure menu-resolution logic for the MarkingMenu.
- constants: LEFT_BUTTON, RIGHT_BUTTON, MIDDLE_BUTTON, SHIFT_MOD, CTRL_MOD, ALT_MOD, META_MOD
- `class MenuResolver`
  - methods: normalize_key, build_state_key, priority_button, count_buttons, resolve_target_menu, parse_binding_keys

### `widgets/marking_menu/overlay.py`
- `class OverlayFactoryFilter(QtCore.QObject)`
  - methods: eventFilter
- `class Path`
  - methods: is_empty, intermediate_entries, start_pos, widget_positions, widget_position, reset, clear, clear_to_origin, add, remove
- `class Overlay(QtWidgets.QWidget)`
  - methods: draw_tangent, init_region, start_gesture, end_gesture, clone_widgets_along_path, clear_paint_events, paintEvent, mousePressEvent, mouseReleaseEvent, mouseMoveEvent, hideEvent

### `widgets/menu.py` — ``Menu``: uitk's popup menu widget -- the facade, its configuration and placement.
- `class MenuConfig`
  - methods: for_context_menu, for_dropdown_menu, for_popup_menu
- `class MenuPositioner`
  - methods: center_on_cursor, position_at_coordinate, position_relative_to_widget, apply_width_matching, position_and_match_width
- `class Menu(_MenuLayoutMixin, _MenuItemsMixin, _MenuTriggersMixin, _MenuLeaveMixin, _MenuPopupWindowMixin, _MenuActionsMixin, _MenuPersistentModeMixin, _MenuRegistrationMixin, QtWidgets.QWidget, AttributesMixin, pythontk.LoggingMixin)`
  - methods: create_context_menu, create_dropdown_menu, from_config, run_modal, setVisible, show, show_as_popup, nearest_enclosing, get_all_children, is_pinned, showEvent, hide, hideEvent, setCentralWidget, centralWidget, init_layout, ensure_chrome, title, setTitle, sizeHint, contains_items, get_items, get_item, get_item_text, get_item_data, set_item_data, remove_widget, clear, add, add_row, trigger_button, set_hide_on_trigger, eventFilter, trigger_from_widget, hide_on_leave, adopt_transient, presets, add_defaults_button, add_presets, enable_persistent_mode, disable_persistent_mode, is_persistent_mode, owner_window

### `widgets/menuButton.py`
- `class MenuButton(QtWidgets.QPushButton, AttributesMixin)`
  - methods: getTarget, setTarget, getFilterTags, setFilterTags, filter_tag_list, submenu_name, hideEvent

### `widgets/menu_parts/_actions.py` — The "Menu Actions" section: Apply, Restore Defaults and the presets selector.
- `class ActionButtonManager`
  - methods: container, create_button, add_button, add_widget, get_widget, remove_widget, get_button, show_button, hide_button, remove_button, has_visible_items

### `widgets/messageBox.py`
- `class MessageBox(QtWidgets.QMessageBox, AttributesMixin)`
  - methods: timeout, reading_time, setStandardButtons, set_default_button, move_, setText, autoClose, showEvent, hideEvent, as_prompt, exec_

### `widgets/mixins/attributes.py`
- `class AttributesMixin`
  - methods: is_design_time, set_design_time, set_flags, set_legal_attribute, set_attributes

### `widgets/mixins/convert.py`
- `class ConvertMixin`
  - methods: can_convert, to_qobject, to_qkey, to_qmousebutton, to_int

### `widgets/mixins/feedback.py` — Mixin: transient HUD-style feedback for any QWidget.
- `class FeedbackMixin`
  - methods: show_feedback

### `widgets/mixins/icon_states.py` — Shared multi-state icon behavior for state-cycling buttons.
- `class IconStates`
  - methods: states, widget, current_state, set_current_state, apply, resolve_callback, activate

### `widgets/mixins/item_format.py` — The shared core of uitk's item-view format mixins.
- `class ItemFormatMixin(ConvertMixin)`

### `widgets/mixins/menu_mixin.py` — MenuMixin - provides automatic Menu integration for widgets.
- `class MenuMixin`
  - methods: configure_menu, has_menu

### `widgets/mixins/option_box_mixin.py` — OptionBoxMixin - simple drop-in mixin for OptionBox functionality.
- `class OptionBoxMixin`
  - methods: option_box, container, options

### `widgets/mixins/shortcut_guard.py` — Keep an editing chord with the widget the user is actually typing in.
- `class ShortcutGuardMixin`
  - methods: claim_override, claims, is_read_only, has_selection, event, claims_shortcut
- `class ShortcutGuardFilter(QtCore.QObject)`
  - methods: eventFilter

### `widgets/mixins/size_grip.py` — Reusable helper for attaching a QSizeGrip to arbitrary widgets.
- constants: QWIDGETSIZE_MAX
- `class CornerSizeGrip(QtWidgets.QSizeGrip)`
  - methods: enterEvent, event, mousePressEvent, leaveEvent, getBaseColor, setBaseColor, getHoverColor, setHoverColor, paintEvent
- `class SizeGripMixin`
  - methods: content_max_size, content_min_height, sync_window_max_to_content, create_size_grip

### `widgets/mixins/spin_box_display.py` — Shared display behaviour for the spin-box widgets.
- `class SpinBoxTextColorMixin`
  - methods: set_text_color, text_color
- `class PrefixColumnMixin`
  - methods: setPrefix, prefix_label, resizeEvent, showEvent, changeEvent, sizeHint, minimumSizeHint

### `widgets/mixins/text.py` — Text rendering for uitk widgets.
- `class RichTextFormatter`
  - methods: prefix_styles, apply_prefix_styles, apply_inline_styles, apply_line_breaks, linkify, wrap_font_color, wrap_font_size, resolve_background, format
- `class TextTruncation`
  - methods: calculate_text_truncation, calculate_character_truncation, calculate_word_truncation, calculate_path_truncation, apply_text_truncation, create_truncated_button, create_truncated_label, update_widget_text_truncation
- `class RichText`
  - methods: richTextLabelDict, richTextSizeHintDict, richTextSizeHint, set_rich_text_style, getRichTextLabel, richText, setRichText, setAlignment
- `class TextOverlay`
  - methods: textOverlayLabel, setTextOverlay, setTextOverlayAlignment, setTextOverlayColor

### `widgets/mixins/text_validation.py` — Validation feedback for a text field -- the red "refused" state.
- `class TextValidationMixin`
  - methods: set_action_color, reset_action_color, set_validator, clear_validator, is_valid, validation_message, validate_now

### `widgets/mixins/tooltip_mixin.py` — Tooltip presentation for managed widgets: :class:`TooltipPresenter`, the
- `class TooltipPresenter`
  - methods: manage, show_text
- `class TooltipProxy(pythontk.TooltipFormat)`
  - methods: bind
- `class TooltipNamespace(pythontk.TooltipFormat)`
  - methods: bind, manage
- `class TooltipMixin`

### `widgets/mixins/wheel_step.py` — Shared input handling for spin-box widgets: the modifier-driven wheel
- `class WheelStepMixin`
  - methods: wheelEvent
- `class SpinBoxAdjustingMixin`
  - methods: adjusting, mousePressEvent, mouseReleaseEvent, keyPressEvent, focusOutEvent

### `widgets/optionBox/_optionBox.py` — OptionBox - Plugin-based container for wrapping widgets with action buttons.
- constants: DEFAULT_OPTION_ORDER
- `class OptionBoxContainer(QtWidgets.QWidget)`
  - methods: changeEvent, showEvent, eventFilter
- `class OptionBox`
  - methods: add_option, remove_option, get_options, set_option_order, show_clear, set_clear_button_visible, wrap

### `widgets/optionBox/option_box_manager.py` — The :class:`OptionBoxManager` facade -- ``widget.option_box``.
- `class OptionBoxManager(_OptionBoxMenuMixin, _OptionBoxWrapMixin, pythontk.LoggingMixin)`
  - methods: clear_option, option_order, pin, recent, set_action, add_action, set_toggle, add_toggle, set_filter, add_choice, set_disable, add_disable, add_value, set_affix, affix_mode, resolve_affix, set_reset, browse, enable_clear, disable_clear, clear_options, get_options, restore_option_defaults, save_option_defaults, clear_option_defaults, find_option, set_order, clear_first, enabled, widget, add_option, add_option_box, add_clear_option, add_menu_option, patch_widget_class, patch_common_widgets, menu, get_menu, enable_menu, enable_option_menu, disable_menu, container, remove

### `widgets/optionBox/options/_options.py`
- `class OptionButton(QtWidgets.QPushButton, AttributesMixin)`
- `class QObjectABCMeta(type(QtCore.QObject), ABCMeta)`
- `class BaseOption(QtCore.QObject, ABC)`
  - methods: is_compatible, widget, create_widget, setup_widget, on_wrap, sibling_options, restore_default, save_default, clear_saved_default, refresh, set_wrapped_widget
- `class ButtonOption(BaseOption)`
  - methods: create_widget, setup_widget, block_next_click, set_checked
- `class GatingMixin`

### `widgets/optionBox/options/_persistence.py` — Shared persistence wiring for OptionBox plugins.
- `class PersistedOption`
  - methods: host_suffix_for, settings_for

### `widgets/optionBox/options/action.py` — Action option for OptionBox - provides customizable action buttons.
- `class ActionOption(PersistedOption, ButtonOption)`
  - methods: create_widget, set_action_handler, current_state, set_states
- `class MenuOption(ActionOption)`
  - methods: set_menu, set_wrapped_widget

### `widgets/optionBox/options/affix.py` — Affix-mode picker option for OptionBox.
- constants: AFFIX_MODE_VALUES, BUILTIN_AFFIX_MODES
- `class AffixMode`
  - methods: resolve, text, convention
- `class AffixOption(PersistedOption, ButtonOption)`
  - methods: modes, mode_spec, is_compatible, create_widget, setup_widget, mode, set_mode, restore_default, save_default, clear_saved_default, refresh, resolve

### `widgets/optionBox/options/browse.py` — Browse option for OptionBox - provides file/folder browsing buttons.
- `class BrowseOption(ButtonOption)`
  - methods: file_types, start_dir, create_widget, browse

### `widgets/optionBox/options/choice.py` — Choice option for OptionBox -- an icon button that picks from a popup.
- `class ChoiceOption(ButtonOption)`
  - methods: value, is_active, set_value, toggle, restore_default, refresh, choices, choice_values, text_of, is_marked, build_menu, show_menu, setup_widget

### `widgets/optionBox/options/clear.py` — Clear option for OptionBox - provides a clear button for text widgets.
- `class ClearOption(ButtonOption)`
  - methods: create_widget, setup_widget, eventFilter, set_wrapped_widget
- `class ClearButton(QtWidgets.QPushButton)`

### `widgets/optionBox/options/disable.py` — Disable option for OptionBox — the universal "disable this widget" button.
- `class DisableOption(BinaryToggleOption)`
  - methods: held_value, setup_widget

### `widgets/optionBox/options/filter.py` — Filter option for OptionBox — turns a text widget into a filter field.
- constants: NEGATE_PREFIX
- `class FilterOption(BinaryToggleOption)`
  - methods: is_compatible, to_patterns, patterns, scope_action, scope, set_scope, text_key, scope_key

### `widgets/optionBox/options/option_menu.py` — Option Menu - A dropdown menu option for OptionBox.
- `class OptionMenuOption(ButtonOption, pythontk.LoggingMixin)`
  - methods: create_widget, setup_widget, set_wrapped_widget, menu
- `class ContextMenuOption(OptionMenuOption)`

### `widgets/optionBox/options/pin_values.py` — Pin Values option for OptionBox - allows pinning/saving widget values.
- `class PinnedValueEntry`
  - methods: display_text
- `class PinnedValuesPopup(QtCore.QObject)`
  - methods: menu, connect_signals, clear, show, close, move, adjustSize, width, add_current_value, add_separator, add_pinned_value, add_empty_message
- `class PinValuesOption(ButtonOption)`
  - methods: create_widget, pinned_values, pinned_entries, has_pinned_values, clear_pinned_values, add_pinned_value

### `widgets/optionBox/options/recent_values.py` — Recent Values option for OptionBox — shows a selectable history list.
- `class RecentValuesPopup(QtCore.QObject)`
  - methods: menu, connect_signals, clear, show, close, move, adjustSize, width, add_recent_value, add_empty_message
- `class RecentValuesOption(ButtonOption)`
  - methods: store, create_widget, record, add_recent_value, set_wrapped_widget, recent_values, clear_recent_values

### `widgets/optionBox/options/reset.py` — Reset option for OptionBox — one-click reset-to-default, with a modifier-gated
- `class ResetOption(ButtonOption, pythontk.LoggingMixin)`
  - methods: is_bypassed, reset, save_as_default, set_bypassed, setup_widget

### `widgets/optionBox/options/toggle.py` — Toggle option for OptionBox — a persisted binary on/off button.
- `class BinaryToggleOption(GatingMixin, PersistedOption, ButtonOption)`
  - methods: is_on, set_on, restore_default, save_default, clear_saved_default, setup_widget
- `class ToggleOption(BinaryToggleOption)`

### `widgets/optionBox/options/value.py` — Inline editable value readout for OptionBox.
- `class ValueOption(BaseOption)`
  - methods: create_widget, setup_widget, on_wrap, refresh, set_wrapped_widget

### `widgets/overflow_indicator.py` — Arrows at the edges of a scroll view where its content continues past them.
- `class OverflowIndicator(QtWidgets.QWidget)`
  - methods: attach, of, detach, area, shown_edges, refresh, eventFilter, paintEvent

### `widgets/popup/dismissal.py` — Event watchers that dismiss a popup: its host moved or hid, or the user left.
- `class AncestorDismissal(QtCore.QObject)`
  - methods: eventFilter, detach
- `class OutsideClickDismissal(QtCore.QObject)`
  - methods: attach, detach, eventFilter

### `widgets/popup/placement.py` — Where a top-level popup surface may sit: its screen, and the on-screen clamp.
- `class PopupPlacement`
  - methods: screen_for, clamp_to_screen

### `widgets/popup/window.py` — Promoting a plain child widget to a frameless top-level popup window.
- `class PopupWindow`
  - methods: promote, active_window

### `widgets/progressBar.py`
- `class ProgressBar(QtWidgets.QProgressBar, AttributesMixin)`
  - methods: scope, is_cancelled, auto_hide, getCancelHoldMs, setCancelHoldMs, setAutoHide, cancel, reset, set_total, start_task, update_progress, finish_task, step, task, showEvent
- `class ProgressTaskContext`

### `widgets/pushButton.py`
- `class PushButton(MenuMixin, QtWidgets.QPushButton, OptionBoxMixin, AttributesMixin, RichText, TextOverlay)`

### `widgets/region.py`
- `class Region(QtWidgets.QWidget, AttributesMixin, ConvertMixin)`
  - methods: visible_on_mouse_over, setVisibleOnMouseOver, hide_top_level_children, show_top_level_children, enterEvent, leaveEvent, hideEvent, childEvent

### `widgets/scriptOutput.py` — Host-agnostic script-output console widget.
- constants: PARAGRAPH_BREAK_RE, COLOR_COMMENT, COLOR_WARNING, COLOR_ERROR, COLOR_RESULT, COLOR_INFO
- `class ScriptHighlightRule`
- `class ScriptBlockRule`
  - methods: starts, continues
- `class ScriptHighlighter(QtGui.QSyntaxHighlighter)`
  - methods: default_rules, default_block_rules, default_level_formats, highlightBlock, stamp_level
- `class ScriptOutput(ShortcutGuardMixin, QtWidgets.QTextEdit)`
  - methods: set_clear_callback, set_context_menu_hook, set_rules, set_block_rules, append_text, enterEvent, keyPressEvent, build_context_menu

### `widgets/separator.py`
- `class Separator(QtWidgets.QFrame, AttributesMixin)`
  - methods: getTitle, setTitle, isCheckable, setCheckable, isChecked, setChecked, toggle, mousePressEvent, sizeHint, minimumSizeHint, resizeEvent, paintEvent

### `widgets/sequencer/_clip.py` — ClipItem — draggable, resizable clip rectangle on the timeline.
- `class ClipItem(DraggableItemMixin, QtWidgets.QGraphicsRectItem)`
  - methods: clip_data, is_selectable, sync_selectable, keys_editable, boundingRect, paint, hoverMoveEvent, hoverLeaveEvent, mousePressEvent, mouseMoveEvent, mouseReleaseEvent, contextMenuEvent, mouseDoubleClickEvent

### `widgets/sequencer/_data.py` — Data models and shared constants for the sequencer widget.
- constants: HATCH_DENSE, HATCH_MEDIUM, HATCH_SPARSE, SELECTED_ACCENT, DISPLAY_COLORS
- `class PatternSpec`
  - methods: brush
- `class ClipData`
  - methods: end
- `class TrackData`
- `class MarkerData`
- `class MenuUtils`
- `class CurveUtils`
  - methods: make_value_mapper, unmap_value, build_curve_path
- `class PatternRegistry`
  - methods: register_pattern, pattern_brush, paint_pattern

### `widgets/sequencer/_drag_tooltip.py` — Floating scene-text that tracks the cursor during timeline drags.
- `class FrameTooltip`
  - methods: format_frame, show, update, hide, is_visible

### `widgets/sequencer/_draggable.py` — Shared drag infrastructure for sequencer graphics items.
- `class ItemRetirement`
  - methods: retire
- `class DraggableItemMixin`
  - methods: snap_time, sceneEvent, cancel_drag

### `widgets/sequencer/_keyframe.py` — The interactive items of an expanded attribute sub-row.
- `class KeyframeItem(DraggableItemMixin, QtWidgets.QGraphicsEllipseItem)`
  - methods: time, value, paint, boundingRect, itemChange, weighted_handles, is_broken, shape, hoverEnterEvent, hoverLeaveEvent, mousePressEvent, mouseMoveEvent, mouseReleaseEvent, contextMenuEvent
- `class TangentHandleItem(QtWidgets.QGraphicsEllipseItem)`
  - methods: side, key, slot, drag_participant, control_point, paint, shape, hoverEnterEvent, hoverLeaveEvent, mousePressEvent, mouseMoveEvent, mouseReleaseEvent, contextMenuEvent
- `class KeyScaleBoxItem(DraggableItemMixin, QtWidgets.QGraphicsRectItem)`
  - methods: lo, hi, side, set_span, shape, boundingRect, paint, hoverEnterEvent, hoverLeaveEvent, mousePressEvent, mouseMoveEvent, mouseReleaseEvent

### `widgets/sequencer/_markers.py` — MarkerItem — named marker on the timeline with drag and context menu.
- `class MarkerItem(DraggableItemMixin, QtWidgets.QGraphicsItem)`
  - methods: marker_data, boundingRect, shape, sync, paint, hoverEnterEvent, hoverLeaveEvent, mousePressEvent, mouseMoveEvent, mouseReleaseEvent, mouseDoubleClickEvent, contextMenuEvent

### `widgets/sequencer/_overlays.py` — Range-related overlay items: static ranges, gap hatching, and highlights.
- `class RangeHighlightItem(DraggableItemMixin, QtWidgets.QGraphicsItem)`
  - methods: start, end, set_range, color, opacity_value, sync, boundingRect, paint, zone_at, begin_edge_drag, hoverMoveEvent, mousePressEvent, mouseMoveEvent, update_edge_drag, finish_edge_drag, mouseReleaseEvent

### `widgets/sequencer/_playhead.py` — PlayheadItem — vertical playhead line with frame-number badge.
- `class PlayheadItem(QtWidgets.QGraphicsItem)`
  - methods: time, boundingRect, sync, paint

### `widgets/sequencer/_ruler.py` — Ruler item for the timeline header area.
- `class RulerItem(QtWidgets.QGraphicsItem)`
  - methods: set_shot_blocks, clear_shot_blocks, selected_block, shot_block_at, set_content_width, set_key_ticks, set_content_left, boundingRect, paint

### `widgets/sequencer/_scrub_player.py` — Qt-side audio scrub/playback helper for :class:`SequencerWidget`.
- `class ScrubPlayer(QtCore.QObject)`
  - methods: available, source_path, set_source, clear_source, play_at_frame, play, stop, is_playing, set_volume, set_grain_ms

### `widgets/sequencer/_sequencer.py` — An NLE-style timeline sequencer widget.
- `class AttributeColorDialog(ColorMappingDialog)`
  - methods: load_color_map
- `class SequencerWidget(QtWidgets.QSplitter, AttributesMixin)`
  - methods: window_shortcuts, showEvent, resizeEvent, eventFilter, event, keyPressEvent, add_track, bulk_updates, add_clip, remove_clip, set_clip_label, set_clip_locked, remove_track, get_clip, get_track, tracks, clips, clip_attributes, swap_clips, set_playhead, set_audio_source, clear_audio_source, clear, clear_decorations, add_marker, remove_marker, get_marker, markers, clear_markers, set_range_highlight, clear_range_highlight, add_range_overlay, clear_range_overlays, add_gap_overlay, clear_gap_overlays, set_all_gap_overlays_locked, set_shot_blocks, selected_shot, clear_shot_blocks, range_highlight, set_hidden_tracks, set_active_range, clear_active_range, step_forward, step_backward, go_to_next_key, go_to_prev_key, go_to_start, go_to_end, add_marker_at_playhead, frame_shot, undo, redo, snap_interval, snap_guides_enabled, snap_to_keys, alignment_times, nearest_alignment, set_snap_guides, clear_snap_guides, show_range_overlays, show_gap_overlays, show_range_highlight, zone_menu_enabled, shift_held_at_press, ctrl_held_at_press, record_press_modifiers, shortcut_overlay, shortcut_overlay_visible, shortcut_overlay_mode, shortcut_overlay_tracking, attribute_colors, set_attribute_color, sub_row_height, sub_row_provider, expand_track, set_bg_curve_preview, collapse_track, is_track_expanded, toggle_track_expanded, selected_clips, selected_keys, select_keys, show_key_menu, refresh_key_scale_box, clear_key_scale_box, set_shift_held, modifiers_held, set_modifiers_held

### `widgets/sequencer/_timeline.py` — Timeline view, scene, and track-header widgets.
- `class TrackHeaderWidget(QtWidgets.QWidget)`
  - methods: set_top_margin, add_track_label, set_track_expanded, set_track_collapsed, selected_sub_rows, eventFilter, selected_names, clear_tracks
- `class TimelineScene(QtWidgets.QGraphicsScene)`
  - methods: ruler, playhead
- `class TimelineView(QtWidgets.QGraphicsView)`
  - methods: event, keyPressEvent, keyReleaseEvent, enterEvent, focusOutEvent, pixels_per_unit, time_to_x, x_to_time, resizeEvent, wheelEvent, mousePressEvent, mouseMoveEvent, leaveEvent, mouseReleaseEvent, mouseDoubleClickEvent, paintEvent, contextMenuEvent, default_context_entries, add_default_context_actions, content_time_bounds, drawBackground

### `widgets/sequencer/_transport_controls.py` — Reusable Maya-style transport controls for :class:`SequencerWidget`.
- `class PlayController(Protocol)`
  - methods: is_playing, play, stop
- `class ScrubPlayerPlayController`
  - methods: set_fps, is_playing, play, stop
- `class TransportControls(QtWidgets.QWidget)`
  - methods: showEvent, hideEvent, play_controller, set_range_fn, set_play_controller, set_interrupt_mode, interrupt_mode, button, attach_to_footer

### `widgets/shortcut_overlay.py` — A corner legend of a widget's mouse gestures and keyboard shortcuts.
- `class ShortcutOverlay(QtWidgets.QWidget)`
  - methods: context, shown_group, set_context, refresh, paintEvent, eventFilter

### `widgets/slider.py`
- `class Slider(QtWidgets.QSlider, MenuMixin, OptionBoxMixin, AttributesMixin)`

### `widgets/spinBox.py`
- `class SpinBox(WheelStepMixin, SpinBoxAdjustingMixin, FeedbackMixin, SpinBoxTextColorMixin, PrefixColumnMixin, QtWidgets.QDoubleSpinBox, MenuMixin, OptionBoxMixin, AttributesMixin)`
  - methods: value, setCustomDisplayValues, textFromValue, valueFromText, validate, stepBy

### `widgets/tableWidget.py`
- `class HeaderMixin`
  - methods: default_header_click_behavior
- `class CellFormatMixin(ItemFormatMixin)`
  - methods: set_column_formatter, set_header_formatter, set_cell_formatter, clear_formatters, set_column_truncation, column_truncation, truncated_column_text, apply_formatting, ensure_valid_color, format_item, set_action_color, action_color_formatter, make_color_map_formatter, add_section_row, is_section_row
- `class TableSelection`
  - methods: get, item, text
- `class TableWidget(QtWidgets.QTableWidget, MenuMixin, HeaderMixin, AttributesMixin, CellFormatMixin)`
  - methods: set_scrub_columns, add_scrub_column, remove_scrub_column, is_scrubbing, set_wheel_scrub_columns, add_wheel_scrub_column, remove_wheel_scrub_column, set_single_click_edit_columns, add_single_click_edit_column, remove_single_click_edit_column, set_cell_widget_click_columns, add_cell_widget_click_column, remove_cell_widget_click_column, mousePressEvent, mouseMoveEvent, mouseReleaseEvent, wheelEvent, eventFilter, active_editor, refresh_active_editor, set_sorted_cell, edit_cell_as, closeEditor, selectionCommand, set_column_selectable, set_selection_validator, set_column_click_action, set_left_click_select_only, setLeftClickSelectOnly, set_selection_mode, item_data, set_item_data, add, selected_node, selected_label, selected_nodes, selected_labels, selected_rows, clear_all, set_stretch_column, enable_column_config, restore_column_state, resizeEvent, stretch_column_to_fill, compute_autofit_size, max_autofit_size, fit_window_to_contents, get_selected_data, get_selection, register_menu_action, unregister_menu_action

### `widgets/table_actions.py` — Reusable action-column management for :class:`TableWidget`.
- `class TableActions`
  - methods: add, set, get, update_for_row_height

### `widgets/textEdit.py`
- `class TextEdit(ShortcutGuardMixin, QtWidgets.QTextEdit, MenuMixin, AttributesMixin, TextValidationMixin)`
  - methods: insertText, showEvent, hideEvent

### `widgets/textEditLogHandler.py`
- `class TextEditLogHandler(logging.Handler)`
  - methods: route_links, open_web_link, emit, get_color, available_columns

### `widgets/textViewBox.py` — Scrollable rich-text viewer window.
- `class TextViewBox(WindowPanel)`
  - methods: format_data, setStandardButtons, setText, append_text, clear_text, clicked_button

### `widgets/toolBox.py`
- `class HoverSwitcher(QtCore.QObject)`
  - methods: eventFilter
- `class ToolBox(QtWidgets.QToolBox, AttributesMixin)`
  - methods: sizeHint, add

### `widgets/treeWidget.py`
- `class HierarchyIconMixin`
  - methods: set_icon_style, enable_hierarchy_icons, get_available_icon_styles, get_current_icon_style
- `class TreeFormatMixin(ItemFormatMixin)`
  - methods: set_item_formatter, set_column_formatter, clear_formatters, apply_formatting, ensure_valid_color, set_action_color, action_color_formatter, make_color_map_formatter
- `class TreeWidget(QtWidgets.QTreeWidget, MenuMixin, AttributesMixin, TreeFormatMixin, HierarchyIconMixin)`
  - methods: selection_style, header_actions, setChildRowColor, setParentRowColor, getSelectionStyle, setSelectionStyle, getCtrlToggle, setCtrlToggle, set_column_tint, clear_column_tints, set_selection_mode, ctrl_toggle, mousePressEvent, mouseReleaseEvent, create_item, item_data, set_item_data, find_item_by_text, find_item_by_data, add, selected_item, selected_items, selected_data, selected_data_list, selected_text, selected_text_list, select_items_by_data, select_items_by_text, set_stretch_column, enable_column_config, restore_column_state, resizeEvent, showEvent, stretch_column_to_fill, expand_all_items, collapse_all_items, get_all_items, remove_item, set_item_icon, set_item_type_icon, refresh_item_icons

### `widgets/widgetComboBox.py`
- `class WidgetComboBox(ComboBox)`
  - methods: setItemText, addWidgetItem, addWidgetAction, widgetAt, takeWidgetAt, currentWidget, row_of, row_container, set_row_visible, is_row_visible, field_key, fields, host_of, item_spacing, actions, action_columns, action_icon_only, show_action_separator, showPopup, arrow_direction, arrow_icon, arrow_alpha, paintEvent, add, add_defaults_button, clear

### `widgets/windowPanel.py` — Themed top-level uitk window: Header → body → Footer.
- `class WindowPanel(QtWidgets.QWidget, AttributesMixin)`
  - methods: style, showEvent, persist_geometry, save_window_geometry, restore_window_geometry, clear_saved_geometry, resizeEvent, moveEvent, hideEvent, closeEvent, present, is_in_popup_context, header, footer, body_layout, rows_layout, form, add, clear_rows, tighten_sublayouts, icon_button
