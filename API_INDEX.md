# uitk — API Index

_Auto-generated. Do not edit by hand. Compact symbol index — grep this for a name; for full signatures/docs, slice [API_REGISTRY.md](API_REGISTRY.md) (never Read it whole)._

_Generated: 2026-06-22_

### `_bootstrap.py` — Standalone-process bootstrap helpers.
- `configure_high_dpi() -> bool`

### `bridge/formatters.py` — Per-target-language value formatters for bridge parameter rendering.
- `python_literal(spec, value: Any) -> str`
- `lua_literal(spec, value: Any) -> str`
- `js_literal(spec, value: Any) -> str`
- `cli_raw(spec, value: Any) -> str`

### `bridge/parameters.py` — Registry helpers for bridge parameter dicts.
- `referenced_keys(script_text: str, params: Dict[str, AttributeSpec]) -> Set[str]`
- `defaults(params: Dict[str, AttributeSpec]) -> Dict[str, Any]`
- `render_context(values: Dict[str, Any], params: Dict[str, AttributeSpec], formatter: Callable[[AttributeSpec, Any], str] = python_literal) -> Dict[str, str]`

### `bridge/slots.py` — Generic DCC-bridge slot base class.
- `class BridgeSlotsBase`
  - methods: params_module, template_dir, make_bridge, make_preset_store, list_template_modes, b000, select_initial_template_index, default_output_dir, template_description, format_param_tooltip, bridge, resolved_output_dir, require_output_dir, collect_param_values, cmb000_init, refresh_templates, header_menu_items, help_spec, header_init, reveal_folder, open_templates_folder, clear_log

### `bridge/spec.py` — Attribute spec + kind-handler registry for parameterised forms.
- `infer_kind(value: Any) -> str`
- `register_kind(name: str, handler: KindHandler) -> None`
- `get_handler(kind: str) -> KindHandler`
- `make_widget(spec: AttributeSpec, parent: Optional[QtWidgets.QWidget] = None) -> QtWidgets.QWidget`
- `read_value(widget: QtWidgets.QWidget) -> Any`
- `set_value(widget: QtWidgets.QWidget, value: Any) -> None`
- `connect_changed(widget: QtWidgets.QWidget, callback: Callable[[Any], None]) -> None`
- `class AttributeSpec`
  - methods: from_value, display_label
- `class KindHandler`

### `bridge/tooltip.py` — Rich-text tooltip + template-description helpers for bridge panels.
- `format_param_tooltip(spec: AttributeSpec) -> str`
- `template_description(template_path: Path) -> Optional[str]`

### `compile.py` — Compile Qt Designer .ui files to switchboard-augmented _ui.py modules.
- `hash_ui_source(ui_path) -> str`
- `compiled_path_for(ui_path) -> Path`
- `read_embedded_hash(py_path) -> Optional[str]`
- `read_embedded_tags(py_path) -> set`
- `read_embedded_base_class(py_path) -> Optional[str]`
- `read_embedded_form_class(py_path) -> Optional[str]`
- `is_compiled_fresh(ui_path, py_path=None) -> bool`
- `extract_metadata(ui_path) -> dict`
- `compile_ui(ui_path, out_path=None, header_resolver=None) -> Path`
- `ensure_compiled(ui_path, header_resolver=None) -> Path`
- `precompile_async(*paths: Union[str, Path], jobs: Optional[int] = None, force: bool = False) -> PrecompileJob`
- `main()`
- `class PrecompileJob`
  - methods: is_alive

### `events.py` — Event handling utilities for Qt applications.
- `class EventFactoryFilter(QtCore.QObject)`
  - methods: install, uninstall, is_installed, eventFilter
- `class MouseTracking(QtCore.QObject, ptk.LoggingMixin)`
  - methods: should_capture_mouse, register_external_widgets, update_child_widgets, track, is_widget_valid, eventFilter

### `examples/example.py` — UITK Example — a polished tour of the framework.
- `class ExampleSlots(ptk.LoggingMixin)`
  - methods: header_init, txt_input_init, txt_input, cmb_options_init, cmb_options, cmb_view_init, tree_demo_init, tree_demo

### `file_manager.py` — File and directory management utilities for UITK.
- `class FileContainer(ptk.NamedTupleContainer)`
  - methods: extend
- `class FileManager(ptk.HelpMixin, ptk.LoggingMixin)`
  - methods: get_base_dir, resolve_path, create, contains_location, get_container, list_containers, remove_container

### `handlers/base_handler.py` — Common infrastructure for Switchboard handlers.
- `class BaseHandler(ptk.SingletonMixin, ptk.LoggingMixin)`
  - methods: instance, config
- `class LaunchableHandlerProtocol(Protocol)`
  - methods: entries, launch, close, is_visible

### `handlers/external_app_handler.py` — Register, install-on-demand, and launch external Python apps as subprocesses.
- `class ExternalAppHandler(BaseHandler)`
  - methods: discover, register, is_registered, unregister, entries, save_tags, close, is_visible, launch

### `handlers/handler_entry.py` — Unified launchable-entry data class shared by all Switchboard handlers.
- `class HandlerEntry`
  - methods: all_tags, editable_tags

### `handlers/ui_handler.py`
- `class UiHandler(BaseHandler)`
  - methods: editors, can_resolve, get, show, setup_lifecycle, apply_styles, entries, launch, close, is_visible, save_tags

### `loaders/compiled.py` — Switchboard delegate that loads UIs via compiled _ui.py modules.
- `class CompiledLoader`
  - methods: read_ui_tags, load, on_tags_written

### `loaders/runtime.py` — Switchboard delegate that loads UIs at runtime via QUiLoader.
- `class RuntimeLoader`
  - methods: load, read_ui_tags, on_tags_written

### `switchboard/_core.py`
- `class Switchboard(QtCore.QObject, ptk.HelpMixin, ptk.LoggingMixin, SwitchboardSlotsMixin, SwitchboardShortcutMixin, SwitchboardWidgetMixin, SwitchboardUtilsMixin, SwitchboardNameMixin, SwitchboardEditorsMixin, SwitchboardStyleMixin)`
  - methods: register_handler, iter_handler_entries, active_ui, current_ui, current_ui, prev_ui, prev_slot, visible_windows, register, load_all_ui, load_ui, add_ui, get_ui, get_ui_relatives, find_ui_filename, save_ui_tags, ui_history

### `switchboard/editors.py` — Mixin that exposes the bundled editor windows on the Switchboard.
- `class SwitchboardEditorsMixin`
  - methods: editors

### `switchboard/names.py`
- `class SwitchboardNameMixin`
  - methods: convert_to_legal_name, get_slot_class_names, get_slot_file_names, get_base_name, get_tags_from_name, has_tags, edit_tags, filter_tags, get_unknown_tags

### `switchboard/shortcuts.py` — Switchboard-side keyboard shortcut machinery.
- `class Shortcut`
- `class SwitchboardShortcutMixin`
  - methods: register_slots_shortcuts, get_shortcut_registry, set_user_shortcut

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

### `switchboard/utils.py`
- `pop_override_cursor_stack(app)`
- `push_override_cursor_stack(app, saved)`
- `class SwitchboardUtilsMixin`
  - methods: get_cursor_offset_from_center, center_widget, unpack_names, get_widgets_by_string_pattern, get_methods_by_string_pattern, create_button_groups, toggle_multi, connect_multi, add_reset_buttons, set_axis_for_checkboxes, get_axis_from_checkboxes, hide_unmatched_groupboxes, invert_on_modifier, progress, progress_adapter, message_box, text_view_dialog, file_dialog, dir_dialog, save_file_dialog, input_dialog, simulate_key_press, defer_with_timer, gc_protect, modal_menu

### `switchboard/widgets.py`
- `class SwitchboardWidgetMixin`
  - methods: is_registered_ui, ui_name_resolves, menu_button_target_name, menu_button_target_resolves, apply_visibility_policy, resolve_widget_class, get_icon, register_widget, get_widget, get_widget_from_slot, set_widget_attrs, is_widget, get_parent_widgets, get_all_windows, get_all_widgets, get_widget_at

### `widgets/_html_style.py` — HTML formatting helpers shared by uitk's rich-text widgets.
- `apply_prefix_styles(string: str) -> str`
- `apply_inline_styles(string: str) -> str`
- `wrap_font_color(string: str, color: str) -> str`
- `wrap_font_size(string: str, size) -> str`
- `resolve_background(background) -> Optional[str]`
- `format_rich_text(string: str, *, align: str = 'left', font_color: str = 'white', font_size: Union[int, str, None] = None) -> str`

### `widgets/attributeWindow/_attributeWindow.py`
- `class AttributeWindow(Menu)`
  - methods: initialize_ui, refresh_attributes, clear_ui_elements, default_get_attribute_func, create_set_attribute_func_wrapper, default_set_attribute_func, is_valid_attribute, is_type_supported, add_attributes, add_attribute_spec, emit_value_changed, emit_composite_value_changed, setup_label, on_label_toggled, on_button_clicked, add_to_layout, showEvent

### `widgets/checkBox.py`
- `class CheckBox(QtWidgets.QCheckBox, MenuMixin, AttributesMixin, RichText, TextOverlay)`
  - methods: set_checkbox_rich_text_style, checkState, setCheckState, hitButton, mousePressEvent

### `widgets/collapsableGroup.py`
- `class CollapsableGroup(QtWidgets.QGroupBox, AttributesMixin)`
  - methods: toggle_expand, setLayout, addWidget, addLayout, sizeHint, paintEvent

### `widgets/colorSwatch.py`
- `class ColorSwatch(QtWidgets.QPushButton, AttributesMixin, ConvertMixin)`
  - methods: color, color, settings, settings, saveColor, loadColor, canSaveLoadColor, initializeColor, updateBackgroundColor, mouseDoubleClickEvent

### `widgets/comboBox.py`
- `class CustomStyle(QtWidgets.QProxyStyle)`
  - methods: drawControl, drawComplexControl, styleHint, pixelMetric
- `class AlignedComboBox(QtWidgets.QComboBox)`
  - methods: setHeaderText, setHeaderAlignment, get_stylesheet_property, paintEvent
- `class ComboBox(AlignedComboBox, MenuMixin, OptionBoxMixin, AttributesMixin, RichText, TextOverlay)`
  - methods: clear, addItem, addItems, insertItem, insertItems, current_text_suffix, current_text_suffix, items, currentData, setCurrentData, currentText, setCurrentText, setItemText, setAsCurrent, setCurrentIndex, check_index, focusOutEvent, setEditable, force_header_display, add_header, add_single, add, removeItem, showPopup, keyPressEvent

### `widgets/doubleSpinBox.py`
- `class DoubleSpinBox(WheelStepMixin, FeedbackMixin, SpinBoxTextColorMixin, QtWidgets.QDoubleSpinBox, MenuMixin, AttributesMixin)`
  - methods: textFromValue, setPrefix

### `widgets/editors/color_mapping_editor.py` — Reusable color-mapping editor widget.
- `class ColorMappingEditor(QtWidgets.QWidget)`
  - methods: add_action_button, restore_defaults, color_map, apply_color_map
- `class ColorMappingDialog(QtWidgets.QDialog)`
  - methods: showEvent, header, footer, color_map

### `widgets/editors/editor_panel.py` — Editor panel: WindowPanel + optional preset save/load row.
- `class EditorPanel(WindowPanel)`
  - methods: init_preset_row, preset_dir, preset_dir, export_preset_data, import_preset_data, save_preset, load_preset, delete_preset, rename_preset

### `widgets/editors/hotkey_editor.py`
- `class CollisionConflict`
- `class KeyCaptureDialog(QtWidgets.QDialog)`
  - methods: keyPressEvent, clear_key, get_sequence
- `class HotkeyEditor(EditorPanel)`
  - methods: export_preset_data, import_preset_data, export_shortcuts, import_shortcuts, showEvent, refresh_ui_list, populate, on_cell_double_clicked, reset_shortcut, add_collision_checker, remove_collision_checker

### `widgets/editors/shortcut_editor.py` — Editor windows used by :meth:`ShortcutManager.show_editor`.
- `class KeyCaptureDialog(QtWidgets.QDialog)`
  - methods: keyPressEvent, get_sequence
- `class ShortcutEditorDialog(QtWidgets.QWidget)`
  - methods: panel, show, close

### `widgets/editors/style_editor.py`
- `class StyleEditor(EditorPanel)`
  - methods: export_preset_data, import_preset_data, populate, on_color_changed, on_length_changed, reset_variable, reset_all, refresh_row

### `widgets/editors/switchboard_browser.py` — Searchable, tag-filtered launcher for any handler-exposed entry.
- `class LaunchOptions`
- `class SwitchboardBrowserModel(QtCore.QAbstractTableModel)`
  - methods: refresh_after_launch, rowCount, columnCount, headerData, data, flags, setData, entry_for_name, all_unique_tags
- `class SwitchboardBrowser(EditorPanel)`
  - methods: hidden_uis, hidden_uis, hidden_tags, hidden_tags, set_search_scope, set_exclude_scope, launch_options, hide_inherited_tags, showEvent

### `widgets/expandableList.py`
- `class ExpandableList(QtWidgets.QWidget, AttributesMixin)`
  - methods: apply_preset, get_items, get_item_text, get_parent_item_text, get_item_data, get_parent_item_data, set_item_data, clear, add, hide, showEvent, hideEvent, get_padding, sizeHint, eventFilter, leaveEvent

### `widgets/footer.py`
- `class Footer(QtWidgets.QWidget, AttributesMixin, SizeGripMixin)`
  - methods: container_layout, alignment, update_font_size, font, add_widget, add_action_button, progress_bar, status_label, size_grip, size_grip, setText, text, setStatusText, setDefaultStatusText, statusText, start_progress, update_progress, finish_progress, cancel_progress, set_progress_total, progress, resizeEvent, showEvent, attach_to
- `class FooterProgressContext`
- `class FooterStatusController`
  - methods: set_resolver, set_truncation, update

### `widgets/header.py`
- `class Header(QtWidgets.QLabel, AttributesMixin, RichText, TextOverlay, ptk.LoggingMixin)`
  - methods: menu, get_icon_path, create_svg_icon, create_button, has_buttons, config_buttons, trigger_resize_event, resizeEvent, resize_buttons, update_font_size, setTitle, title, setVersion, version, setText, minimize_window, restore_window, toggle_maximize, toggle_fullscreen, hide_window, unhide_window, trigger_refresh, set_help_text, help_text, show_help, show_menu, toggle_collapse, collapse_window, expand_window, toggle_pin, reset_pin_state, mousePressEvent, mouseMoveEvent, mouseReleaseEvent, showEvent, attach_to, hideEvent

### `widgets/label.py`
- `class Label(QtWidgets.QLabel, MenuMixin, OptionBoxMixin, AttributesMixin)`
  - methods: mousePressEvent, mouseReleaseEvent

### `widgets/lineEdit.py`
- `class LineEditFormatMixin`
  - methods: set_action_color, reset_action_color, set_validator, clear_validator, is_valid, validate_now
- `class LineEdit(QtWidgets.QLineEdit, MenuMixin, OptionBoxMixin, AttributesMixin, LineEditFormatMixin)`
  - methods: contextMenuEvent, showEvent, hideEvent

### `widgets/mainWindow.py`
- `class MainWindow(QtWidgets.QMainWindow, AttributesMixin, TooltipMixin, ptk.LoggingMixin)`
  - methods: setCentralWidget, initialize_window_flags, edit_tags, pinned, pinned, set_pinned, is_pinned, request_hide, slots, presets, presets, is_stacked_widget, is_current_ui, is_current_ui, register_widget, trigger_deferred, run_when_ready, perform_restore_state, sync_widget_values, eventFilter, adjust_height_by, fit_height_to_content, save_window_geometry, restore_window_geometry, clear_saved_geometry, setVisible, show, showEvent, register_children, focusInEvent, focusOutEvent, resizeEvent, moveEvent, hideEvent, closeEvent, setStyleSheet, reset_style

### `widgets/marking_menu/_marking_menu.py`
- `class MarkingMenu(QtWidgets.QWidget, ptk.SingletonMixin, ptk.LoggingMixin, ptk.HelpMixin)`
  - methods: instance, default_bindings, bindings, bindings, on_bindings_changed, ui_handler, get, addWidget, currentWidget, setCurrentWidget, setCurrentIndex, mousePressEvent, keyPressEvent, mouseDoubleClickEvent, mouseReleaseEvent, show, hide, hideEvent, enable_input_logging, disable_input_logging, dim_other_windows, restore_other_windows, add_child_event_filter, child_enterEvent, child_leaveEvent, child_mouseButtonReleaseEvent

### `widgets/marking_menu/_resolver.py` — Pure menu-resolution logic for the MarkingMenu.
- `normalize_key(parts) -> str`
- `build_state_key(activation_key_str: Optional[str], buttons: int, modifiers: int, extra_key: Optional[str] = None) -> str`
- `priority_button(buttons: int) -> int`
- `count_buttons(buttons: int) -> int`
- `resolve_target_menu(*, activation_held: bool, activation_key_str: Optional[str], buttons: int, modifiers: int, bindings: Mapping[str, str], extra_key: Optional[str] = None) -> Optional[str]`
- `parse_binding_keys(raw_bindings: Mapping[str, str]) -> tuple`

### `widgets/marking_menu/overlay.py`
- `class OverlayFactoryFilter(QtCore.QObject)`
  - methods: eventFilter
- `class Path`
  - methods: is_empty, intermediate_entries, start_pos, widget_positions, widget_position, reset, clear, clear_to_origin, add, remove
- `class Overlay(QtWidgets.QWidget)`
  - methods: draw_tangent, init_region, start_gesture, clone_widgets_along_path, clear_paint_events, paintEvent, mousePressEvent, mouseReleaseEvent, mouseMoveEvent, hideEvent

### `widgets/menu.py`
- `class MenuConfig`
  - methods: for_context_menu, for_dropdown_menu, for_popup_menu
- `class ActionButtonManager`
  - methods: container, create_button, add_button, add_widget, get_widget, remove_widget, get_button, show_button, hide_button, remove_button, has_visible_items
- `class MenuPositioner`
  - methods: center_on_cursor, position_at_coordinate, position_relative_to_widget, apply_width_matching, position_and_match_width
- `class Menu(QtWidgets.QWidget, AttributesMixin, ptk.LoggingMixin)`
  - methods: create_context_menu, create_dropdown_menu, from_config, run_modal, trigger_button, trigger_button, presets, presets, hide_on_leave, hide_on_leave, enable_persistent_mode, disable_persistent_mode, is_persistent_mode, setVisible, show, show_as_popup, setCentralWidget, centralWidget, init_layout, add_defaults_button, add_defaults_button, add_presets, add_presets, get_all_children, is_pinned, contains_items, title, setTitle, get_items, get_item, get_item_text, get_item_data, set_item_data, remove_widget, clear, add, sizeHint, showEvent, hide, hideEvent, eventFilter, trigger_from_widget

### `widgets/menuButton.py`
- `class MenuButton(QtWidgets.QPushButton, AttributesMixin)`
  - methods: getTarget, setTarget, getFilterTags, setFilterTags, filter_tag_list, submenu_name, hideEvent

### `widgets/messageBox.py`
- `class MessageBox(QtWidgets.QMessageBox, AttributesMixin)`
  - methods: setStandardButtons, move_, setText, autoClose, showEvent, hideEvent, exec_

### `widgets/mixins/attributes.py`
- `class AttributesMixin`
  - methods: set_flags, set_legal_attribute, set_attributes

### `widgets/mixins/convert.py`
- `class ConvertMixin`
  - methods: can_convert, to_qobject, to_qkey, to_qmousebutton, to_int

### `widgets/mixins/docking.py`
- `class DockingOverlay(QWidget)`
  - methods: update, paintEvent
- `class DockingWindow(QMainWindow)`
  - methods: add_tool_window, remove_tool_window, get_docked_widgets
- `class CustomDockWidget(QDockWidget)`
  - methods: handle_top_level_change, eventFilter
- `class DockingMixin(QObject)`
  - methods: docking_enabled, docking_enabled, dock_position, dock_position, dock, dock_positions, update_docking_position, eventFilter

### `widgets/mixins/feedback.py` — Mixin: transient HUD-style feedback for any QWidget.
- `class FeedbackMixin`
  - methods: show_feedback

### `widgets/mixins/icon_manager.py`
- `class IconManager`
  - methods: set_default_color, register_icon_dir, get, fit_size, fit_icon, swap_icon, set_icon, update_widget_icons, clear_cache, get_cache_stats

### `widgets/mixins/menu_mixin.py` — MenuMixin - provides automatic Menu integration for widgets.
- `class MenuMixin`
  - methods: configure_menu, has_menu

### `widgets/mixins/option_box_mixin.py` — OptionBoxMixin - simple drop-in mixin for OptionBox functionality.
- `class OptionBoxMixin`
  - methods: option_box, container, options

### `widgets/mixins/preset_manager.py`
- `QStandardPaths_writableLocation() -> str`
- `QStandardPaths_genericConfigLocation() -> str`
- `get_presets_root() -> Path`
- `class PresetManager(ptk.LoggingMixin)`
  - methods: from_widgets, setup, preset_dir, preset_dir, on_change, active_preset, active_preset, is_modified, on_modified_changed, refresh_modified_state, connect_value_widgets, save, load, list, source, delete, rename, exists, wire_combo

### `widgets/mixins/recent_values_store.py` — Widget-free *recent values* model — the shared source of truth for value history.
- `normalize_value(value)`
- `class RecentValuesStore`
  - methods: subscribe, unsubscribe, values, is_valid, valid_values, record, add, remove, clear, prune_invalid, display_map

### `widgets/mixins/settings_manager.py`
- `class SettingsManager`
  - methods: branch, set_defaults, value, setValue, on_change, keys, setByteArray, getByteArray, clear, sync

### `widgets/mixins/shortcuts.py` — Generic keyboard-shortcut primitives, usable by any Qt widget.
- `context_to_scope_name(context: QtCore.Qt.ShortcutContext) -> str`
- `scope_name_to_context(name: str) -> QtCore.Qt.ShortcutContext`
- `create_standard_shortcuts_config() -> List[Tuple[QtGui.QKeySequence, str, str]]`
- `apply_standard_shortcuts(widget, shortcuts_to_apply: Optional[List[str]] = None)`
- `class GlobalShortcut(QtCore.QObject)`
  - methods: eventFilter, setEnabled, setKey, setContext
- `class ShortcutManager`
  - methods: add_shortcut, add_shortcuts_batch, add_global_shortcut, add_info_entry, remove_shortcut, clear_all, on_change, rebind_shortcut, show_editor, get_shortcuts_info, has_shortcut, get_shortcut
- `class ShortcutMixin`
  - methods: shortcut_manager, add_shortcut, add_shortcuts_from_config, remove_shortcut, clear_all_shortcuts, get_shortcuts_info, add_shortcuts_to_context_menu, add_menu_actions_with_shortcuts, create_context_menu, add_actions_to_menu

### `widgets/mixins/size_grip.py` — Reusable helper for attaching a QSizeGrip to arbitrary widgets.
- `class CornerSizeGrip(QtWidgets.QSizeGrip)`
  - methods: enterEvent, leaveEvent, getBaseColor, setBaseColor, getHoverColor, setHoverColor, paintEvent
- `class SizeGripMixin`
  - methods: create_size_grip

### `widgets/mixins/spin_box_text_color.py` — Shared value-text coloring for spin-box widgets.
- `class SpinBoxTextColorMixin`
  - methods: set_text_color, text_color

### `widgets/mixins/state_manager.py`
- `class StateManager(ptk.LoggingMixin)`
  - methods: apply, suppress_save, save, save_value, load, reset_all, reset, clear, has_default, capture_default, set_default, save_custom, load_custom, clear_custom

### `widgets/mixins/style_sheet.py`
- `class StyleSheet(QtCore.QObject, ptk.LoggingMixin)`
  - methods: get_icon_color, set_theme, reload, clear_caches, set_variable, get_variable, get_variable_px, get_variables, export_overrides, import_overrides, reset_overrides

### `widgets/mixins/text.py`
- `class TextTruncation`
  - methods: calculate_text_truncation, calculate_character_truncation, calculate_word_truncation, calculate_path_truncation, apply_text_truncation, create_truncated_button, create_truncated_label, update_widget_text_truncation
- `class RichText`
  - methods: richTextLabelDict, richTextSizeHintDict, richTextSizeHint, set_rich_text_style, getRichTextLabel, richText, setRichText, setAlignment
- `class TextOverlay`
  - methods: textOverlayLabel, setTextOverlay, setTextOverlayAlignment, setTextOverlayColor

### `widgets/mixins/tooltip_mixin.py`
- `kbd(*keys: str) -> str`
- `hl(text: str, color: str = _C_ACCENT) -> str`
- `fmt(title: str = None, body: str = None, bullets: list = None, steps: list = None, rows: list = None, sections: list = None, notes: list = None) -> str`
- `class TooltipProxy`
  - methods: bind
- `class TooltipMixin`

### `widgets/mixins/value_manager.py`
- `class ValueManager`
  - methods: get_value, set_value, get_widget_type_info, is_supported_widget, get_value_by_signal, set_value_by_signal

### `widgets/mixins/wheel_step.py` — Shared modifier-driven wheel-step handling for spin-box widgets.
- `class WheelStepMixin`
  - methods: wheelEvent

### `widgets/optionBox/_optionBox.py` — OptionBox - Plugin-based container for wrapping widgets with action buttons.
- `class OptionBoxContainer(QtWidgets.QWidget)`
  - methods: changeEvent, showEvent, eventFilter
- `class OptionBox`
  - methods: add_option, remove_option, get_options, show_clear, show_clear, set_clear_button_visible, wrap

### `widgets/optionBox/options/_options.py`
- `class OptionButton(QtWidgets.QPushButton, AttributesMixin)`
- `class QObjectABCMeta(type(QtCore.QObject), ABCMeta)`
- `class BaseOption(QtCore.QObject, ABC)`
  - methods: widget, create_widget, setup_widget, on_wrap, set_wrapped_widget
- `class ButtonOption(BaseOption)`
  - methods: create_widget, setup_widget, block_next_click, set_checked

### `widgets/optionBox/options/_persistence.py` — Shared persistence wiring for OptionBox plugins.
- `class PersistedOption`

### `widgets/optionBox/options/action.py` — Action option for OptionBox - provides customizable action buttons.
- `class ActionOption(ButtonOption)`
  - methods: create_widget, set_action_handler, current_state, current_state, set_states
- `class MenuOption(ActionOption)`
  - methods: set_menu, set_wrapped_widget

### `widgets/optionBox/options/browse.py` — Browse option for OptionBox - provides file/folder browsing buttons.
- `class BrowseOption(ButtonOption)`
  - methods: file_types, file_types, start_dir, start_dir, create_widget, browse

### `widgets/optionBox/options/clear.py` — Clear option for OptionBox - provides a clear button for text widgets.
- `class ClearOption(ButtonOption)`
  - methods: create_widget, setup_widget, eventFilter, set_wrapped_widget
- `class ClearButton(QtWidgets.QPushButton)`

### `widgets/optionBox/options/option_menu.py` — Option Menu - A dropdown menu option for OptionBox.
- `class OptionMenuOption(ButtonOption, ptk.LoggingMixin)`
  - methods: create_widget, setup_widget, set_wrapped_widget, menu
- `class ContextMenuOption(OptionMenuOption)`

### `widgets/optionBox/options/pin_values.py` — Pin Values option for OptionBox - allows pinning/saving widget values.
- `class PinnedValueEntry`
  - methods: display_text
- `class PinnedValuesPopup(QtCore.QObject)`
  - methods: menu, eventFilter, connect_signals, clear, show, close, move, adjustSize, width, add_current_value, add_separator, add_pinned_value, add_empty_message
- `class PinValuesOption(ButtonOption)`
  - methods: create_widget, pinned_values, pinned_entries, has_pinned_values, clear_pinned_values, add_pinned_value

### `widgets/optionBox/options/recent_values.py` — Recent Values option for OptionBox — shows a selectable history list.
- `class RecentValuesPopup(QtCore.QObject)`
  - methods: menu, eventFilter, connect_signals, clear, show, close, move, adjustSize, width, add_recent_value, add_separator, add_empty_message
- `class RecentValuesOption(ButtonOption)`
  - methods: store, create_widget, record, add_recent_value, set_wrapped_widget, recent_values, clear_recent_values

### `widgets/optionBox/options/reset.py` — Reset option for OptionBox — one-click reset-to-default, with a modifier-gated
- `class ResetOption(ButtonOption)`
  - methods: is_bypassed, reset, set_bypassed, setup_widget

### `widgets/optionBox/options/toggle.py` — Toggle option for OptionBox — a persisted binary on/off button.
- `class ToggleOption(PersistedOption, ButtonOption)`
  - methods: is_on, set_on, setup_widget

### `widgets/optionBox/utils.py` — Utilities and helper functions for OptionBox.
- `add_option_box(widget, show_clear=False, options=None, **kwargs)`
- `add_clear_option(widget, **kwargs)`
- `add_menu_option(widget, menu, **kwargs)`
- `patch_widget_class(widget_class)`
- `patch_common_widgets()`
- `class OptionBoxManager(ptk.LoggingMixin)`
  - methods: clear_option, clear_option, option_order, option_order, pin, recent, set_action, add_action, set_toggle, add_toggle, set_reset, browse, enable_clear, disable_clear, clear_options, find_option, set_order, clear_first, enabled, widget, menu, get_menu, menu, enable_menu, disable_menu, add_option, container, remove

### `widgets/progressBar.py`
- `class ProgressBar(QtWidgets.QProgressBar, AttributesMixin)`
  - methods: is_cancelled, auto_hide, auto_hide, cancel, reset, set_total, start_task, update_progress, finish_task, step, task, showEvent
- `class ProgressTaskContext`

### `widgets/pushButton.py`
- `class PushButton(MenuMixin, QtWidgets.QPushButton, OptionBoxMixin, AttributesMixin, RichText, TextOverlay)`

### `widgets/region.py`
- `class Region(QtWidgets.QWidget, AttributesMixin, ConvertMixin)`
  - methods: visible_on_mouse_over, visible_on_mouse_over, hide_top_level_children, show_top_level_children, enterEvent, leaveEvent, hideEvent, childEvent

### `widgets/row_selection_delegate.py` — Opt-in delegate for views whose cells carry their own background.
- `class RowSelectionBorderDelegate(QtWidgets.QStyledItemDelegate)`
  - methods: paint, paint_row_selection_border

### `widgets/separator.py`
- `class Separator(QtWidgets.QFrame, AttributesMixin)`
  - methods: title, title, setTitle, sizeHint, minimumSizeHint, resizeEvent

### `widgets/sequencer/_clip.py` — ClipItem — draggable, resizable clip rectangle on the timeline.
- `class ClipItem(DraggableItemMixin, QtWidgets.QGraphicsRectItem)`
  - methods: clip_data, boundingRect, paint, hoverMoveEvent, hoverLeaveEvent, mousePressEvent, mouseMoveEvent, mouseReleaseEvent, contextMenuEvent, mouseDoubleClickEvent

### `widgets/sequencer/_data.py` — Data models and shared constants for the sequencer widget.
- `register_pattern(name: str, painter: PatternPainter) -> None`
- `pattern_brush(style: str, color: QtGui.QColor, spacing: int = HATCH_MEDIUM, line_width: float = 1.0) -> QtGui.QBrush`
- `paint_pattern(painter: QtGui.QPainter, rect: QtCore.QRectF, spec: PatternSpec) -> None`
- `class PatternSpec`
  - methods: brush
- `class ClipData`
  - methods: end
- `class TrackData`
- `class MarkerData`

### `widgets/sequencer/_drag_tooltip.py` — Floating scene-text that tracks the cursor during timeline drags.
- `class FrameTooltip`
  - methods: format_frame, show, update, hide, is_visible

### `widgets/sequencer/_draggable.py` — Shared drag infrastructure for sequencer graphics items.
- `snap_time(value: float, timeline) -> float`
- `class DraggableItemMixin`
  - methods: cancel_drag

### `widgets/sequencer/_keyframe.py` — KeyframeItem — selectable, draggable keyframe dot on an attribute sub-row.
- `class KeyframeItem(DraggableItemMixin, QtWidgets.QGraphicsEllipseItem)`
  - methods: time, value, paint, boundingRect, shape, hoverEnterEvent, hoverLeaveEvent, mousePressEvent, mouseMoveEvent, mouseReleaseEvent

### `widgets/sequencer/_markers.py` — MarkerItem — named marker on the timeline with drag and context menu.
- `class MarkerItem(DraggableItemMixin, QtWidgets.QGraphicsItem)`
  - methods: marker_data, boundingRect, shape, sync, paint, hoverEnterEvent, hoverLeaveEvent, mousePressEvent, mouseMoveEvent, mouseReleaseEvent, mouseDoubleClickEvent, contextMenuEvent

### `widgets/sequencer/_overlays.py` — Range-related overlay items: static ranges, gap hatching, and highlights.
- `class RangeHighlightItem(DraggableItemMixin, QtWidgets.QGraphicsItem)`
  - methods: locked, locked, start, start, end, end, set_range, color, color, opacity_value, opacity_value, sync, boundingRect, paint, hoverMoveEvent, mousePressEvent, mouseMoveEvent, mouseReleaseEvent

### `widgets/sequencer/_playhead.py` — PlayheadItem — vertical playhead line with frame-number badge.
- `class PlayheadItem(QtWidgets.QGraphicsItem)`
  - methods: time, time, boundingRect, sync, paint

### `widgets/sequencer/_ruler.py` — Ruler and shot-lane items for the timeline header area.
- `class ShotLaneItem(QtWidgets.QGraphicsItem)`
  - methods: set_blocks, clear_blocks, mousePressEvent, boundingRect, paint
- `class RulerItem(QtWidgets.QGraphicsItem)`
  - methods: set_shot_blocks, clear_shot_blocks, boundingRect, paint

### `widgets/sequencer/_scrub_player.py` — Qt-side audio scrub/playback helper for :class:`SequencerWidget`.
- `class ScrubPlayer(QtCore.QObject)`
  - methods: available, source_path, set_source, clear_source, play_at_frame, play, stop, set_volume, set_grain_ms

### `widgets/sequencer/_sequencer.py` — An NLE-style timeline sequencer widget.
- `class AttributeColorDialog(ColorMappingDialog)`
  - methods: load_color_map
- `class SequencerWidget(QtWidgets.QSplitter, AttributesMixin)`
  - methods: window_shortcuts, window_shortcuts, showEvent, eventFilter, event, keyPressEvent, add_track, add_clip, remove_clip, set_clip_label, set_clip_locked, remove_track, get_clip, get_track, tracks, clips, swap_clips, set_playhead, set_audio_source, clear_audio_source, clear, clear_decorations, add_marker, remove_marker, get_marker, markers, clear_markers, set_range_highlight, clear_range_highlight, add_range_overlay, clear_range_overlays, add_gap_overlay, clear_gap_overlays, set_all_gap_overlays_locked, set_shot_blocks, clear_shot_blocks, range_highlight, set_hidden_tracks, set_active_range, clear_active_range, step_forward, step_backward, go_to_next_key, go_to_prev_key, go_to_start, go_to_end, add_marker_at_playhead, frame_shot, undo, redo, snap_interval, snap_interval, show_range_overlays, show_range_overlays, show_gap_overlays, show_gap_overlays, show_range_highlight, show_range_highlight, shift_held_at_press, shift_held_at_press, attribute_colors, attribute_colors, sub_row_height, sub_row_height, sub_row_provider, sub_row_provider, expand_track, set_bg_curve_preview, collapse_track, is_track_expanded, toggle_track_expanded, selected_clips

### `widgets/sequencer/_timeline.py` — Timeline view, scene, and track-header widgets.
- `class TrackHeaderWidget(QtWidgets.QWidget)`
  - methods: set_top_margin, add_track_label, set_track_expanded, set_track_collapsed, eventFilter, selected_names, clear_tracks
- `class TimelineScene(QtWidgets.QGraphicsScene)`
  - methods: ruler, playhead
- `class TimelineView(QtWidgets.QGraphicsView)`
  - methods: event, keyPressEvent, keyReleaseEvent, enterEvent, pixels_per_unit, pixels_per_unit, time_to_x, x_to_time, resizeEvent, wheelEvent, mousePressEvent, mouseMoveEvent, mouseReleaseEvent, mouseDoubleClickEvent, paintEvent, contextMenuEvent, drawBackground

### `widgets/sequencer/_transport_controls.py` — Reusable Maya-style transport controls for :class:`SequencerWidget`.
- `class PlayController(Protocol)`
  - methods: is_playing, play, stop
- `class ScrubPlayerPlayController`
  - methods: set_fps, is_playing, play, stop
- `class TransportControls(QtWidgets.QWidget)`
  - methods: play_controller, set_play_controller, set_interrupt_mode, interrupt_mode, button, attach_to_footer

### `widgets/spinBox.py`
- `class SpinBox(WheelStepMixin, FeedbackMixin, SpinBoxTextColorMixin, QtWidgets.QDoubleSpinBox, MenuMixin, OptionBoxMixin, AttributesMixin)`
  - methods: value, setCustomDisplayValues, textFromValue, valueFromText, validate, setPrefix, stepBy

### `widgets/table_actions.py` — Reusable action-column management for :class:`TableWidget`.
- `class TableActions`
  - methods: add, set, get, update_for_row_height

### `widgets/tableWidget.py`
- `class HeaderMixin`
  - methods: default_header_click_behavior
- `class CellFormatMixin(ConvertMixin)`
  - methods: set_column_formatter, set_header_formatter, set_cell_formatter, clear_formatters, apply_formatting, ensure_valid_color, format_item, set_action_color, action_color_formatter, make_color_map_formatter, add_section_row, is_section_row
- `class TableSelection`
  - methods: get, item, text
- `class TableWidget(QtWidgets.QTableWidget, MenuMixin, HeaderMixin, AttributesMixin, CellFormatMixin)`
  - methods: set_scrub_columns, add_scrub_column, remove_scrub_column, is_scrubbing, set_wheel_scrub_columns, add_wheel_scrub_column, remove_wheel_scrub_column, set_single_click_edit_columns, add_single_click_edit_column, remove_single_click_edit_column, mousePressEvent, mouseMoveEvent, mouseReleaseEvent, wheelEvent, eventFilter, active_editor, refresh_active_editor, closeEditor, selectionCommand, set_column_selectable, set_selection_validator, set_column_click_action, set_left_click_select_only, set_selection_mode, item_data, set_item_data, add, selected_node, selected_label, selected_nodes, selected_labels, selected_rows, clear_all, set_stretch_column, resizeEvent, stretch_column_to_fill, get_selected_data, get_selection, register_menu_action, unregister_menu_action

### `widgets/textEdit.py`
- `class TextEdit(QtWidgets.QTextEdit, MenuMixin, AttributesMixin)`
  - methods: insertText, showEvent, hideEvent

### `widgets/textEditLogHandler.py`
- `class TextEditLogHandler(logging.Handler)`
  - methods: emit, get_color, available_columns

### `widgets/textViewBox.py` — Scrollable rich-text viewer window.
- `class TextViewBox(WindowPanel)`
  - methods: setStandardButtons, setText, append_text, clear_text, clicked_button

### `widgets/toolBox.py`
- `class HoverSwitcher(QtCore.QObject)`
  - methods: eventFilter
- `class ToolBox(QtWidgets.QToolBox, AttributesMixin)`
  - methods: sizeHint, add

### `widgets/treeWidget.py`
- `class HierarchyIconMixin`
  - methods: set_icon_style, enable_hierarchy_icons, get_available_icon_styles, get_current_icon_style
- `class TreeFormatMixin(ConvertMixin)`
  - methods: set_item_formatter, set_column_formatter, clear_formatters, apply_formatting, ensure_valid_color, set_action_color, action_color_formatter, make_color_map_formatter
- `class TreeWidget(QtWidgets.QTreeWidget, MenuMixin, AttributesMixin, TreeFormatMixin, HierarchyIconMixin)`
  - methods: selection_style, selection_style, header_actions, set_column_tint, clear_column_tints, set_selection_mode, ctrl_toggle, ctrl_toggle, mousePressEvent, mouseReleaseEvent, create_item, item_data, set_item_data, find_item_by_text, find_item_by_data, add, selected_item, selected_items, selected_data, selected_data_list, selected_text, selected_text_list, select_items_by_data, select_items_by_text, set_stretch_column, enable_column_config, restore_column_state, resizeEvent, showEvent, stretch_column_to_fill, expand_all_items, collapse_all_items, get_all_items, remove_item, set_item_icon, set_item_type_icon, refresh_item_icons

### `widgets/widgetComboBox.py`
- `class WidgetComboBox(ComboBox)`
  - methods: setItemText, addWidgetItem, addWidgetAction, widgetAt, takeWidgetAt, currentWidget, item_spacing, item_spacing, actions, action_columns, action_columns, action_icon_only, action_icon_only, show_action_separator, show_action_separator, showPopup, hidePopup, arrow_direction, arrow_direction, paintEvent, eventFilter, add, add_defaults_button, add_defaults_button, clear

### `widgets/windowPanel.py` — Themed top-level uitk window: Header → body → Footer.
- `class WindowPanel(QtWidgets.QWidget)`
  - methods: style, showEvent, header, footer, body_layout, tighten_sublayouts, icon_button
