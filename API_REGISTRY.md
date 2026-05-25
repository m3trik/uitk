# uitk — API Registry

_Auto-generated. Do not edit by hand. Refresh via `m3trik/scripts/generate_api_registry.py`._

_Generated: 2026-05-25_

## Index

- [`_bootstrap.py`](#_bootstrap) — Standalone-process bootstrap helpers.
- [`bridge/formatters.py`](#bridge--formatters) — Per-target-language value formatters for bridge parameter rendering.
- [`bridge/parameters.py`](#bridge--parameters) — Registry helpers for bridge parameter dicts.
- [`bridge/slots.py`](#bridge--slots) — Generic DCC-bridge slot base class.
- [`bridge/spec.py`](#bridge--spec) — Attribute spec + kind-handler registry for parameterised forms.
- [`bridge/tooltip.py`](#bridge--tooltip) — Rich-text tooltip + template-description helpers for bridge panels.
- [`compile.py`](#compile) — Compile Qt Designer .ui files to switchboard-augmented _ui.py modules.
- [`events.py`](#events) — Event handling utilities for Qt applications.
- [`examples/example.py`](#examples--example) — UITK Example — a polished tour of the framework.
- [`file_manager.py`](#file_manager) — File and directory management utilities for UITK.
- [`handlers/base_handler.py`](#handlers--base_handler) — Common infrastructure for Switchboard handlers.
- [`handlers/external_app_handler.py`](#handlers--external_app_handler) — Register, install-on-demand, and launch external Python apps as subprocesses.
- [`handlers/handler_entry.py`](#handlers--handler_entry) — Unified launchable-entry data class shared by all Switchboard handlers.
- [`handlers/ui_handler.py`](#handlers--ui_handler)
- [`loaders/compiled.py`](#loaders--compiled) — Switchboard delegate that loads UIs via compiled _ui.py modules.
- [`loaders/runtime.py`](#loaders--runtime) — Switchboard delegate that loads UIs at runtime via QUiLoader.
- [`switchboard/_core.py`](#switchboard--_core)
- [`switchboard/editors.py`](#switchboard--editors) — Mixin that exposes the bundled editor windows on the Switchboard.
- [`switchboard/names.py`](#switchboard--names)
- [`switchboard/shortcuts.py`](#switchboard--shortcuts) — Switchboard-side keyboard shortcut machinery.
- [`switchboard/slots.py`](#switchboard--slots)
- [`switchboard/style.py`](#switchboard--style) — Mixin that exposes the :class:`StyleSheet` class on the Switchboard.
- [`switchboard/utils.py`](#switchboard--utils)
- [`switchboard/widgets.py`](#switchboard--widgets)
- [`widgets/_html_style.py`](#widgets--_html_style) — HTML formatting helpers shared by uitk's rich-text widgets.
- [`widgets/attributeWindow/_attributeWindow.py`](#widgets--attributeWindow--_attributeWindow)
- [`widgets/checkBox.py`](#widgets--checkBox)
- [`widgets/collapsableGroup.py`](#widgets--collapsableGroup)
- [`widgets/colorSwatch.py`](#widgets--colorSwatch)
- [`widgets/comboBox.py`](#widgets--comboBox)
- [`widgets/doubleSpinBox.py`](#widgets--doubleSpinBox)
- [`widgets/editors/color_mapping_editor.py`](#widgets--editors--color_mapping_editor) — Reusable color-mapping editor widget.
- [`widgets/editors/editor_panel.py`](#widgets--editors--editor_panel) — Editor panel: WindowPanel + optional preset save/load row.
- [`widgets/editors/hotkey_editor.py`](#widgets--editors--hotkey_editor)
- [`widgets/editors/shortcut_editor.py`](#widgets--editors--shortcut_editor) — Editor windows used by :meth:`ShortcutManager.show_editor`.
- [`widgets/editors/style_editor.py`](#widgets--editors--style_editor)
- [`widgets/editors/switchboard_browser.py`](#widgets--editors--switchboard_browser) — Searchable, tag-filtered launcher for any handler-exposed entry.
- [`widgets/expandableList.py`](#widgets--expandableList)
- [`widgets/footer.py`](#widgets--footer)
- [`widgets/header.py`](#widgets--header)
- [`widgets/label.py`](#widgets--label)
- [`widgets/lineEdit.py`](#widgets--lineEdit)
- [`widgets/mainWindow.py`](#widgets--mainWindow)
- [`widgets/marking_menu/_marking_menu.py`](#widgets--marking_menu--_marking_menu)
- [`widgets/marking_menu/_resolver.py`](#widgets--marking_menu--_resolver) — Pure menu-resolution logic for the MarkingMenu.
- [`widgets/marking_menu/overlay.py`](#widgets--marking_menu--overlay)
- [`widgets/menu.py`](#widgets--menu)
- [`widgets/messageBox.py`](#widgets--messageBox)
- [`widgets/mixins/attributes.py`](#widgets--mixins--attributes)
- [`widgets/mixins/convert.py`](#widgets--mixins--convert)
- [`widgets/mixins/docking.py`](#widgets--mixins--docking)
- [`widgets/mixins/icon_manager.py`](#widgets--mixins--icon_manager)
- [`widgets/mixins/menu_mixin.py`](#widgets--mixins--menu_mixin) — MenuMixin - provides automatic Menu integration for widgets.
- [`widgets/mixins/option_box_mixin.py`](#widgets--mixins--option_box_mixin) — OptionBoxMixin - simple drop-in mixin for OptionBox functionality.
- [`widgets/mixins/preset_manager.py`](#widgets--mixins--preset_manager)
- [`widgets/mixins/settings_manager.py`](#widgets--mixins--settings_manager)
- [`widgets/mixins/shortcuts.py`](#widgets--mixins--shortcuts) — Generic keyboard-shortcut primitives, usable by any Qt widget.
- [`widgets/mixins/size_grip.py`](#widgets--mixins--size_grip) — Reusable helper for attaching a QSizeGrip to arbitrary widgets.
- [`widgets/mixins/state_manager.py`](#widgets--mixins--state_manager)
- [`widgets/mixins/style_sheet.py`](#widgets--mixins--style_sheet)
- [`widgets/mixins/text.py`](#widgets--mixins--text)
- [`widgets/mixins/tooltip_mixin.py`](#widgets--mixins--tooltip_mixin)
- [`widgets/mixins/value_manager.py`](#widgets--mixins--value_manager)
- [`widgets/optionBox/_optionBox.py`](#widgets--optionBox--_optionBox) — OptionBox - Plugin-based container for wrapping widgets with action buttons.
- [`widgets/optionBox/options/_options.py`](#widgets--optionBox--options--_options)
- [`widgets/optionBox/options/_persistence.py`](#widgets--optionBox--options--_persistence) — Shared persistence wiring for OptionBox plugins.
- [`widgets/optionBox/options/action.py`](#widgets--optionBox--options--action) — Action option for OptionBox - provides customizable action buttons.
- [`widgets/optionBox/options/browse.py`](#widgets--optionBox--options--browse) — Browse option for OptionBox - provides file/folder browsing buttons.
- [`widgets/optionBox/options/clear.py`](#widgets--optionBox--options--clear) — Clear option for OptionBox - provides a clear button for text widgets.
- [`widgets/optionBox/options/option_menu.py`](#widgets--optionBox--options--option_menu) — Option Menu - A dropdown menu option for OptionBox.
- [`widgets/optionBox/options/pin_values.py`](#widgets--optionBox--options--pin_values) — Pin Values option for OptionBox - allows pinning/saving widget values.
- [`widgets/optionBox/options/recent_values.py`](#widgets--optionBox--options--recent_values) — Recent Values option for OptionBox — shows a selectable history list.
- [`widgets/optionBox/options/toggle.py`](#widgets--optionBox--options--toggle) — Toggle option for OptionBox — a persisted binary on/off button.
- [`widgets/optionBox/utils.py`](#widgets--optionBox--utils) — Utilities and helper functions for OptionBox.
- [`widgets/progressBar.py`](#widgets--progressBar)
- [`widgets/pushButton.py`](#widgets--pushButton)
- [`widgets/region.py`](#widgets--region)
- [`widgets/row_selection_delegate.py`](#widgets--row_selection_delegate) — Opt-in delegate for views whose cells carry their own background.
- [`widgets/separator.py`](#widgets--separator)
- [`widgets/sequencer/_clip.py`](#widgets--sequencer--_clip) — ClipItem — draggable, resizable clip rectangle on the timeline.
- [`widgets/sequencer/_data.py`](#widgets--sequencer--_data) — Data models and shared constants for the sequencer widget.
- [`widgets/sequencer/_drag_tooltip.py`](#widgets--sequencer--_drag_tooltip) — Floating scene-text that tracks the cursor during timeline drags.
- [`widgets/sequencer/_draggable.py`](#widgets--sequencer--_draggable) — Shared drag infrastructure for sequencer graphics items.
- [`widgets/sequencer/_keyframe.py`](#widgets--sequencer--_keyframe) — KeyframeItem — selectable, draggable keyframe dot on an attribute sub-row.
- [`widgets/sequencer/_markers.py`](#widgets--sequencer--_markers) — MarkerItem — named marker on the timeline with drag and context menu.
- [`widgets/sequencer/_overlays.py`](#widgets--sequencer--_overlays) — Range-related overlay items: static ranges, gap hatching, and highlights.
- [`widgets/sequencer/_playhead.py`](#widgets--sequencer--_playhead) — PlayheadItem — vertical playhead line with frame-number badge.
- [`widgets/sequencer/_ruler.py`](#widgets--sequencer--_ruler) — Ruler and shot-lane items for the timeline header area.
- [`widgets/sequencer/_scrub_player.py`](#widgets--sequencer--_scrub_player) — Qt-side audio scrub/playback helper for :class:`SequencerWidget`.
- [`widgets/sequencer/_sequencer.py`](#widgets--sequencer--_sequencer) — An NLE-style timeline sequencer widget.
- [`widgets/sequencer/_timeline.py`](#widgets--sequencer--_timeline) — Timeline view, scene, and track-header widgets.
- [`widgets/sequencer/_transport_controls.py`](#widgets--sequencer--_transport_controls) — Reusable Maya-style transport controls for :class:`SequencerWidget`.
- [`widgets/spinBox.py`](#widgets--spinBox)
- [`widgets/table_actions.py`](#widgets--table_actions) — Reusable action-column management for :class:`TableWidget`.
- [`widgets/tableWidget.py`](#widgets--tableWidget)
- [`widgets/textEdit.py`](#widgets--textEdit)
- [`widgets/textEditLogHandler.py`](#widgets--textEditLogHandler)
- [`widgets/textViewBox.py`](#widgets--textViewBox) — Scrollable rich-text viewer window.
- [`widgets/toolBox.py`](#widgets--toolBox)
- [`widgets/treeWidget.py`](#widgets--treeWidget)
- [`widgets/widgetComboBox.py`](#widgets--widgetComboBox)
- [`widgets/windowPanel.py`](#widgets--windowPanel) — Themed top-level uitk window: Header → body → Footer.

---

<a id="_bootstrap"></a>
### `_bootstrap.py`

Standalone-process bootstrap helpers.

- [`configure_high_dpi() -> bool`](uitk/uitk/_bootstrap.py#L13) — Configure Qt high-DPI scaling for a standalone process.

<a id="bridge--formatters"></a>
### `bridge/formatters.py`

Per-target-language value formatters for bridge parameter rendering.

- [`python_literal(spec, value: Any) -> str`](uitk/uitk/bridge/formatters.py#L29) — Render *value* as a Python source literal.
- [`lua_literal(spec, value: Any) -> str`](uitk/uitk/bridge/formatters.py#L44) — Render *value* as a Lua source literal.
- [`js_literal(spec, value: Any) -> str`](uitk/uitk/bridge/formatters.py#L59) — Render *value* as a JavaScript literal.
- [`cli_raw(spec, value: Any) -> str`](uitk/uitk/bridge/formatters.py#L75) — Render *value* as a raw command-line argv token (no quoting).

<a id="bridge--parameters"></a>
### `bridge/parameters.py`

Registry helpers for bridge parameter dicts.

- [`referenced_keys(script_text: str, params: Dict[str, AttributeSpec]) -> Set[str]`](uitk/uitk/bridge/parameters.py#L34) — Return registry keys whose ``__KEY__`` token appears in *script_text*.
- [`defaults(params: Dict[str, AttributeSpec]) -> Dict[str, Any]`](uitk/uitk/bridge/parameters.py#L48) — Return ``{key: default}`` for every registered parameter.
- [`render_context(values: Dict[str, Any], params: Dict[str, AttributeSpec], formatter: Callable[[AttributeSpec, Any], str] = python_literal) -> Dict[str, str]`](uitk/uitk/bridge/parameters.py#L53) — Format *values* through *formatter* for ``StrUtils.replace_delimited``.

<a id="bridge--slots"></a>
### `bridge/slots.py`

Generic DCC-bridge slot base class.

- **[`class BridgeSlotsBase`](uitk/uitk/bridge/slots.py#L83)** — Base class for DCC-bridge slot panels.
  - `BridgeSlotsBase.params_module(self)` *(property)*
  - `BridgeSlotsBase.template_dir(self) -> Path` *(property)*
  - `BridgeSlotsBase.make_bridge(self)` — Return a fresh bridge instance.
  - `BridgeSlotsBase.list_template_modes(self) -> List[Tuple[str, str]]`
  - `BridgeSlotsBase.b000(self)` — Implement the per-bridge send action.
  - `BridgeSlotsBase.select_initial_template_index(self, pairs: List[Tuple[str, str]]) -> int` — Return the index of the preferred initial entry in *pairs*.
  - `BridgeSlotsBase.default_output_dir(self) -> str` — Hook: fallback path when the user leaves Output Dir blank.
  - `BridgeSlotsBase.template_description(self, template_path: Path) -> Optional[str]` — Hook: extract a brief description from a template file.
  - `BridgeSlotsBase.format_param_tooltip(self, spec: AttributeSpec) -> str` — Hook: build the rich-text tooltip for one parameter spec.
  - `BridgeSlotsBase.bridge(self)` *(property)* — Lazy-instantiated bridge (caches a single instance per slot).
  - `BridgeSlotsBase.resolved_output_dir(self) -> str` — Return the current Output Dir text trimmed of whitespace.
  - `BridgeSlotsBase.require_output_dir(self) -> Optional[str]` — Return the Output Dir or log an error on empty.
  - `BridgeSlotsBase.collect_param_values(self) -> Dict[str, Any]` — Snapshot every widget's current value, regardless of visibility.
  - `BridgeSlotsBase.cmb000_init(self, widget) -> None` — Switchboard hook: populate the template combobox + wire change handler.
  - `BridgeSlotsBase.refresh_templates(self) -> None` — Re-scan disk and rebuild the template combo + parameter UI.
  - `BridgeSlotsBase.open_templates_folder(self) -> None` — Reveal :attr:`template_dir` in the OS file manager.
  - `BridgeSlotsBase.clear_log(self) -> None` — Clear the log panel (wired by subclass header menus).

<a id="bridge--spec"></a>
### `bridge/spec.py`

Attribute spec + kind-handler registry for parameterised forms.

- [`infer_kind(value: Any) -> str`](uitk/uitk/bridge/spec.py#L136) — Map a Python value to one of the built-in kinds.
- [`register_kind(name: str, handler: KindHandler) -> None`](uitk/uitk/bridge/spec.py#L161) — Register a new kind (or override an existing one).
- [`get_handler(kind: str) -> KindHandler`](uitk/uitk/bridge/spec.py#L166) — Return the handler for *kind* (raises KeyError if unregistered).
- [`make_widget(spec: AttributeSpec, parent: Optional[QtWidgets.QWidget] = None) -> QtWidgets.QWidget`](uitk/uitk/bridge/spec.py#L176) — Build a Qt widget for *spec*.
- [`read_value(widget: QtWidgets.QWidget) -> Any`](uitk/uitk/bridge/spec.py#L200) — Return the current value of a factory-built widget.
- [`set_value(widget: QtWidgets.QWidget, value: Any) -> None`](uitk/uitk/bridge/spec.py#L205) — Set the value of a factory-built widget.
- [`connect_changed(widget: QtWidgets.QWidget, callback: Callable[[Any], None]) -> None`](uitk/uitk/bridge/spec.py#L210) — Wire the widget's value-change signal to ``callback(new_value)``.
- **[`class AttributeSpec`](uitk/uitk/bridge/spec.py#L45)** — Description of one editable attribute / bridge parameter.
  - `AttributeSpec.from_value(cls, key: str, value: Any, *, label: str = '') -> 'AttributeSpec'` *(class)* — Build a minimal spec from a Python value (AttributeWindow style).
  - `AttributeSpec.display_label(self) -> str` *(property)*
- **[`class KindHandler`](uitk/uitk/bridge/spec.py#L105)** — Bundle of callables that build / read / write a widget kind.

<a id="bridge--tooltip"></a>
### `bridge/tooltip.py`

Rich-text tooltip + template-description helpers for bridge panels.

- [`format_param_tooltip(spec: AttributeSpec) -> str`](uitk/uitk/bridge/tooltip.py#L24) — Build a rich-text tooltip for one :class:`AttributeSpec`.
- [`template_description(template_path: Path) -> Optional[str]`](uitk/uitk/bridge/tooltip.py#L77) — Return *template_path*'s leading docstring / comment block, or *None*.

<a id="compile"></a>
### `compile.py`

Compile Qt Designer .ui files to switchboard-augmented _ui.py modules.

- [`hash_ui_source(ui_path) -> str`](uitk/uitk/compile.py#L122) — SHA-256 hex digest of the .ui file bytes.
- [`compiled_path_for(ui_path) -> Path`](uitk/uitk/compile.py#L127) — Return the _ui.py path paired with a given .ui path.
- [`read_embedded_hash(py_path) -> Optional[str]`](uitk/uitk/compile.py#L154) — Return __source_hash__ from a generated _ui.py header, or None.
- [`read_embedded_tags(py_path) -> set`](uitk/uitk/compile.py#L159) — Return __uitk_tags__ from a generated _ui.py header.
- [`read_embedded_base_class(py_path) -> Optional[str]`](uitk/uitk/compile.py#L170) — Return __base_class__ from a generated _ui.py header, or None.
- [`read_embedded_form_class(py_path) -> Optional[str]`](uitk/uitk/compile.py#L175) — Return __form_class__ from a generated _ui.py header, or None.
- [`is_compiled_fresh(ui_path, py_path=None) -> bool`](uitk/uitk/compile.py#L180) — True only if py_path carries a uitk hash matching ui_path's content.
- [`extract_metadata(ui_path) -> dict`](uitk/uitk/compile.py#L212) — Extract switchboard-relevant metadata from a .ui file.
- [`compile_ui(ui_path, out_path=None, header_resolver=None) -> Path`](uitk/uitk/compile.py#L302) — Compile a .ui file to a switchboard-augmented _ui.py.
- [`ensure_compiled(ui_path, header_resolver=None) -> Path`](uitk/uitk/compile.py#L368) — Return the _ui.py path for ui_path, regenerating if missing or stale.
- [`precompile_async(*paths: Union[str, Path], jobs: Optional[int] = None, force: bool = False) -> PrecompileJob`](uitk/uitk/compile.py#L481) — Pre-compile _ui.py files in a daemon background thread.
- [`main()`](uitk/uitk/compile.py#L526) — CLI entry point: python -m uitk.compile [paths...] [--check] [--force] [-j N].
- **[`class PrecompileJob`](uitk/uitk/compile.py#L447)** — Handle for an in-flight (or no-op) :func:`precompile_async` call.
  - `PrecompileJob.is_alive(self) -> bool`

<a id="events"></a>
### `events.py`

Event handling utilities for Qt applications.

- **[`class EventFactoryFilter(QtCore.QObject)`](uitk/uitk/events.py#L41)** — Efficient dynamic event filter with lazy handler resolution and scoped widget control.
  - `EventFactoryFilter.install(self, widgets: QtCore.QObject | Iterable[QtCore.QObject])` — Install this event filter on one or more widgets.
  - `EventFactoryFilter.uninstall(self, widgets: QtCore.QObject | Iterable[QtCore.QObject])` — Uninstall this event filter from one or more widgets.
  - `EventFactoryFilter.is_installed(self, widget: QtCore.QObject) -> bool` — Return whether a widget is being tracked (only valid if propagate_to_children=False).
  - `EventFactoryFilter.eventFilter(self, widget: QtCore.QObject, event: QtCore.QEvent) -> bool` — Event filter method that processes events and calls the appropriate handler.
- **[`class MouseTracking(QtCore.QObject, ptk.LoggingMixin)`](uitk/uitk/events.py#L160)** — MouseTracking is a QObject subclass that provides mouse enter and leave events for QWidget child wi…
  - `MouseTracking.should_capture_mouse(self, widget)` — Checks if a widget should capture the mouse.
  - `MouseTracking.register_external_widgets(self, widgets)` — Register widgets that should receive synthesized Enter/Leave events
  - `MouseTracking.update_child_widgets(self)` — Updates the set of child widgets of the parent.
  - `MouseTracking.track(self)` — Drive enter/leave + grab handoff for whatever's under the cursor.
  - `MouseTracking.is_widget_valid(widget)` *(static)* — Return True if the Qt widget and its C++ object still exist.
  - `MouseTracking.eventFilter(self, widget, event)` — Filter mouse move and release events.

<a id="examples--example"></a>
### `examples/example.py`

UITK Example — a polished tour of the framework.

- **[`class ExampleSlots(ptk.LoggingMixin)`](uitk/uitk/examples/example.py#L52)** — Slots for the UITK Example — method names match widget objectNames.
  - `ExampleSlots.header_init(self, widget)`
  - `ExampleSlots.txt_input_init(self, widget)` — Wire the full option_box plugin stack onto the path field.
  - `ExampleSlots.txt_input(self, text)` — Default signal = textChanged (debounced 300 ms via ``widget.debounce``).
  - `ExampleSlots.cmb_options_init(self, widget)` — Populate the package combo with every importable UITK subpackage.
  - `ExampleSlots.cmb_options(self, index)` — Default signal = currentIndexChanged.
  - `ExampleSlots.cmb_view_init(self, widget)` — Inline checkbox panel for tree view options.
  - `ExampleSlots.tree_demo_init(self, widget)`
  - `ExampleSlots.tree_demo(self, item, column, widget=None)` — Default signal = itemClicked.

<a id="file_manager"></a>
### `file_manager.py`

File and directory management utilities for UITK.

- **[`class FileContainer(ptk.NamedTupleContainer)`](uitk/uitk/file_manager.py#L31)** — A specialized NamedTupleContainer for file management.
  - `FileContainer.extend(self, objects: Union[List[namedtuple], List[tuple], Any], **metadata) -> None` — Extend the container with file objects using FileManager's processing logic.
- **[`class FileManager(ptk.HelpMixin, ptk.LoggingMixin)`](uitk/uitk/file_manager.py#L91)** — Manages files and directories, supporting file queries and path manipulations.
  - `FileManager.get_base_dir(self, caller_info: Union[str, int, Any] = 0) -> Optional[str]` — Identifies the base directory based on the caller's frame index or an object.
  - `FileManager.resolve_path(self, target_obj: Union[str, Any], validate: int = 0, path_type: str = 'Path', **metadata) -> Optional[str]` — Resolve a target object to an absolute path.
  - `FileManager.create(self, descriptor: str, objects: Optional[Union[str, List[str], Any]] = None, **metadata) -> ptk.NamedTupleContainer` — Creates a named tuple container for the specified files.
  - `FileManager.contains_location(self, location: Union[str, Any], container_descriptor: str) -> bool` — Checks if the container with the given descriptor contains a specific location.
  - `FileManager.get_container(self, descriptor: str) -> Optional[ptk.NamedTupleContainer]` — Get a container by its descriptor name.
  - `FileManager.list_containers(self) -> List[str]` — List all container descriptors.
  - `FileManager.remove_container(self, descriptor: str) -> bool` — Remove a container by its descriptor name.

<a id="handlers--base_handler"></a>
### `handlers/base_handler.py`

Common infrastructure for Switchboard handlers.

- **[`class BaseHandler(ptk.SingletonMixin, ptk.LoggingMixin)`](uitk/uitk/handlers/base_handler.py#L31)** — Common base for Switchboard handlers.
  - `BaseHandler.instance(cls, switchboard: 'Switchboard' = None, **kwargs)` *(class)*
  - `BaseHandler.config(self)` *(property)*
- **[`class LaunchableHandlerProtocol(Protocol)`](uitk/uitk/handlers/base_handler.py#L114)** — Structural type for handlers that participate in the launcher surface.
  - `LaunchableHandlerProtocol.entries(self) -> Iterable['HandlerEntry']`
  - `LaunchableHandlerProtocol.launch(self, name: str, **options)`
  - `LaunchableHandlerProtocol.close(self, name: str) -> None`
  - `LaunchableHandlerProtocol.is_visible(self, name: str) -> bool`

<a id="handlers--external_app_handler"></a>
### `handlers/external_app_handler.py`

Register, install-on-demand, and launch external Python apps as subprocesses.

- **[`class ExternalAppHandler(BaseHandler)`](uitk/uitk/handlers/external_app_handler.py#L114)** — Switchboard handler for launching external Python apps.
  - `ExternalAppHandler.discover(self, groups: Optional[Iterable[str]] = None) -> int` — Auto-register every app advertised under a uitk entry-point group.
  - `ExternalAppHandler.register(self, name: str, *, module: str, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: str = 'subprocess', tags: Optional[Iterable[str]] = None) -> None` — Pre-register an app so it can be launched by name.
  - `ExternalAppHandler.is_registered(self, name: str) -> bool`
  - `ExternalAppHandler.unregister(self, name: str) -> None` — Remove an app.
  - `ExternalAppHandler.entries(self) -> Iterable[HandlerEntry]` — Yield one :class:`HandlerEntry` per registered app.
  - `ExternalAppHandler.save_tags(self, name: str, tags: Iterable[str]) -> None` — Persist *tags* for *name* in the handler's config branch.
  - `ExternalAppHandler.close(self, name: str) -> None` — Hide an in-process widget;
  - `ExternalAppHandler.is_visible(self, name: str) -> bool`
  - `ExternalAppHandler.launch(self, name: Optional[str] = None, *, module: Optional[str] = None, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: Optional[str] = None, show: bool = True, **_options)` — Launch a registered app, or an ad-hoc app from kwargs.

<a id="handlers--handler_entry"></a>
### `handlers/handler_entry.py`

Unified launchable-entry data class shared by all Switchboard handlers.

- **[`class HandlerEntry`](uitk/uitk/handlers/handler_entry.py#L24)** — One launchable item exposed by a Switchboard handler.
  - `HandlerEntry.all_tags(self) -> FrozenSet[str]` *(property)*
  - `HandlerEntry.editable_tags(self) -> bool` *(property)*

<a id="handlers--ui_handler"></a>
### `handlers/ui_handler.py`

- **[`class UiHandler(BaseHandler)`](uitk/uitk/handlers/ui_handler.py#L12)** — A generic, dynamic UI Handler that supports recursive discovery of UI and Slot files.
  - `UiHandler.editors(self)` *(property)* — Shortcut to the bound switchboard's editor registry.
  - `UiHandler.get(self, name: str, reload: bool = False, **kwargs)` — Retrieve a standalone UI by name and apply default styling.
  - `UiHandler.show(self, ui, pos: Union[str, Tuple[int, int], QtCore.QPoint, None] = None, force: bool = False, **kwargs)` — Show a UI by name or widget reference.
  - `UiHandler.setup_lifecycle(self, ui, hide_signal=None)` — Connect a window to a hide signal, respecting its pin state.
  - `UiHandler.apply_styles(self, ui, style: Dict = None)` — Apply default styles to the UI instance.
  - `UiHandler.entries(self) -> Iterable[HandlerEntry]` — Yield one :class:`HandlerEntry` per .ui registered with the Switchboard.
  - `UiHandler.launch(self, name: str, **options)` — Launch the named UI applying the browser's per-launch style options.
  - `UiHandler.close(self, name: str) -> None` — Hide the named UI via its header (matches the in-window hide button).
  - `UiHandler.is_visible(self, name: str) -> bool`
  - `UiHandler.save_tags(self, name: str, tags: Iterable[str]) -> None` — Persist ``<uitk_tags>`` XML for the named UI.

<a id="loaders--compiled"></a>
### `loaders/compiled.py`

Switchboard delegate that loads UIs via compiled _ui.py modules.

- **[`class CompiledLoader`](uitk/uitk/loaders/compiled.py#L94)** — Switchboard delegate that loads UIs via compiled _ui.py modules.
  - `CompiledLoader.read_ui_tags(self, ui_path: str) -> set` — Return the uitk_tags set for a .ui file via direct XML extraction.
  - `CompiledLoader.load(self, ui_file: str)` — Build a widget tree from a .ui path via its compiled _ui.py module.
  - `CompiledLoader.on_tags_written(self, ui_path: str) -> None` — Regenerate _ui.py after the .ui has been written with new tags.

<a id="loaders--runtime"></a>
### `loaders/runtime.py`

Switchboard delegate that loads UIs at runtime via QUiLoader.

- **[`class RuntimeLoader`](uitk/uitk/loaders/runtime.py#L54)** — Switchboard delegate that loads UIs at runtime via QUiLoader.
  - `RuntimeLoader.load(self, ui_file: str) -> QtWidgets.QWidget` — Build a widget tree from a .ui path via QUiLoader.
  - `RuntimeLoader.read_ui_tags(self, ui_path: str) -> set` — Return the uitk_tags set for a .ui file via direct XML parse.
  - `RuntimeLoader.on_tags_written(self, ui_path: str) -> None` — Invalidate cached metadata after .ui content has changed.

<a id="switchboard--_core"></a>
### `switchboard/_core.py`

- **[`class Switchboard(QtCore.QObject, ptk.HelpMixin, ptk.LoggingMixin, SwitchboardSlotsMixin, SwitchboardShortcutMixin, SwitchboardWidgetMixin, SwitchboardUtilsMixin, SwitchboardNameMixin, SwitchboardEditorsMixin, SwitchboardStyleMixin)`](uitk/uitk/switchboard/_core.py#L29)** — Switchboard is a dynamic UI loader and event handler for PyQt/PySide applications.
  - `Switchboard.register_handler(self, name: str, instance, defaults: dict = None)` — Register a handler instance and apply defaults to its config.
  - `Switchboard.iter_handler_entries(self)` — Yield every :class:`HandlerEntry` from every launchable handler.
  - `Switchboard.active_ui(self) -> Optional[QtWidgets.QWidget]` *(property)* — Return the currently set UI, or None — no auto-load, no warning.
  - `Switchboard.current_ui(self) -> QtWidgets.QWidget` *(property)* — Get or load the current UI if not already set.
  - `Switchboard.current_ui(self, ui: QtWidgets.QWidget) -> None` — Set the current UI and record it in UI history.
  - `Switchboard.prev_ui(self) -> QtWidgets.QWidget` *(property)* — Get the previous UI from history.
  - `Switchboard.prev_slot(self) -> object` *(property)* — Get the last called slot.
  - `Switchboard.visible_windows(self) -> set` *(property)* — Return all currently visible MainWindow instances.
  - `Switchboard.register(self, ui_location=None, slot_location=None, widget_location=None, icon_location=None, base_dir=1, recursive: bool = False, validate=0, tags=None)` — Add new locations to the Switchboard registries.
  - `Switchboard.load_all_ui(self) -> list` — Extends the 'load_ui' method to load all UI from a given path.
  - `Switchboard.load_ui(self, file: str) -> QtWidgets.QMainWindow` — Load a UI from the given .ui path via its compiled _ui.py module.
  - `Switchboard.add_ui(self, name: str, widget: Optional[QtWidgets.QWidget] = None, parent: Optional[QtWidgets.QWidget] = None, tags: set = None, path: str = None, overwrite: bool = False, **kwargs) -> QtWidgets.QMainWindow`
  - `Switchboard.get_ui(self, ui=None) -> QtWidgets.QWidget` — Get a dynamic UI using its string name, or if no argument is given, return the current UI.
  - `Switchboard.get_ui_relatives(self, ui, upstream=False, exact=False, downstream=False, reverse=False)` — Get UIs related to the given UI via shared base name.
  - `Switchboard.find_ui_filename(self, legal_name: str, unique_match: bool = False) -> Union[str, List[str], None]` — Convert the given legal name to its original name(s) by searching the UI files.
  - `Switchboard.save_ui_tags(self, path: str, tags: Iterable[str]) -> None` — Persist tags into a .ui file as a Designer-safe dynamic property.
  - `Switchboard.ui_history(self, index=None, allow_duplicates=False, inc=None, exc=None)` — Get the UI history.

<a id="switchboard--editors"></a>
### `switchboard/editors.py`

Mixin that exposes the bundled editor windows on the Switchboard.

- **[`class SwitchboardEditorsMixin`](uitk/uitk/switchboard/editors.py#L225)** — Adds an ``editors`` property to Switchboard exposing the bundled editors.
  - `SwitchboardEditorsMixin.editors(self) -> _EditorRegistry` *(property)* — Cached editor registry — see :class:`_EditorRegistry`.

<a id="switchboard--names"></a>
### `switchboard/names.py`

- **[`class SwitchboardNameMixin`](uitk/uitk/switchboard/names.py#L9)** — Mixin for Switchboard name and tag management.
  - `SwitchboardNameMixin.convert_to_legal_name(name: str) -> str` *(static)* — Convert a name to a legal format by replacing non-alphanumeric characters with underscores.
  - `SwitchboardNameMixin.get_slot_class_names(self, base_name: str) -> List[str]` — Generate potential slot class names from a base name.
  - `SwitchboardNameMixin.get_slot_file_names(self, base_name: str) -> List[str]` — Generate potential slot file names from a base name.
  - `SwitchboardNameMixin.get_base_name(self, name: str) -> str`
  - `SwitchboardNameMixin.get_tags_from_name(self, name: str) -> set[str]` — Extract tags from a UI name string.
  - `SwitchboardNameMixin.has_tags(self, ui, tags=None) -> bool` — Check if any of the given tag(s) are present in the UI's tags set.
  - `SwitchboardNameMixin.edit_tags(self, target: Union[str, QtWidgets.QWidget], add: Union[str, List[str]] = None, remove: Union[str, List[str]] = None, clear: bool = False, reset: bool = False) -> Union[str, None]` — Edit tags on a widget or a tag string.
  - `SwitchboardNameMixin.filter_tags(self, tag_string: str, keep_tags: list[str] = None, remove_tags: list[str] = None) -> str` — Filter tags from a tag string - either keep only specified tags or remove specified tags.
  - `SwitchboardNameMixin.get_unknown_tags(self, tag_string: str, known_tags: list[str]) -> list[str]` — Get tags that are not in the known_tags list.

<a id="switchboard--shortcuts"></a>
### `switchboard/shortcuts.py`

Switchboard-side keyboard shortcut machinery.

- **[`class Shortcut`](uitk/uitk/switchboard/shortcuts.py#L32)** — Decorator to assign a keyboard shortcut to a slot method.
- **[`class SwitchboardShortcutMixin`](uitk/uitk/switchboard/shortcuts.py#L76)** — Mixin for managing keyboard shortcuts for Switchboard Slots.
  - `SwitchboardShortcutMixin.register_slots_shortcuts(self, ui: QtWidgets.QWidget, slots_instance: object) -> None` — Scan a Slots instance and register shortcuts for decorated methods.
  - `SwitchboardShortcutMixin.get_shortcut_registry(self, ui: QtWidgets.QWidget) -> List[Dict[str, Any]]` — Get a registry of all assignable slots and their shortcut status.
  - `SwitchboardShortcutMixin.set_user_shortcut(self, ui: QtWidgets.QWidget, slot_name: str, sequence: str, scope: Optional[str] = None) -> None` — Update a shortcut setting dynamically and live-update the active QShortcut.

<a id="switchboard--slots"></a>
### `switchboard/slots.py`

- **[`class Signals`](uitk/uitk/switchboard/slots.py#L11)** — Decorator to specify which signals a slot should connect to.
  - `Signals.blockSignals(cls, func)` *(class)* — Decorator that blocks widget signals during method execution.
- **[`class Cancelable`](uitk/uitk/switchboard/slots.py#L62)** — Decorator: enable cancel-with-Esc + warning dialog for a heavy slot.
- **[`class SlotWrapper`](uitk/uitk/switchboard/slots.py#L142)** — Wrapper class for slots to handle argument injection, history tracking, debounce, and timeout monit…
- **[`class SwitchboardSlotsMixin`](uitk/uitk/switchboard/slots.py#L327)** — Mixin for managing slot connections and signal-slot handling in the Switchboard.
  - `SwitchboardSlotsMixin.get_default_signals(self, widget: QtWidgets.QWidget) -> set` — Retrieves the default signals for a given widget type.
  - `SwitchboardSlotsMixin.get_available_signals(self, widget, derived=True, exc=None)` — Get all available signals for a type of widget.
  - `SwitchboardSlotsMixin.slots_instantiated(self, key: str) -> bool`
  - `SwitchboardSlotsMixin.get_slots_instance(self, ui: Union[str, QtWidgets.QWidget]) -> Optional[object]` — Get or create a slots instance for the given UI.
  - `SwitchboardSlotsMixin.init_slot(self, widget: QtWidgets.QWidget, block_signals: bool = True) -> None`
  - `SwitchboardSlotsMixin.call_slot(self, widget: QtWidgets.QWidget, *args, **kwargs)` — Call a slot method for a widget.
  - `SwitchboardSlotsMixin.get_slot(self, slot_class: object, slot_name: str, wrap: bool = False, widget: Optional[QtWidgets.QWidget] = None) -> Optional[Callable]`
  - `SwitchboardSlotsMixin.get_slot_from_widget(self, widget: QtWidgets.QWidget, wrap: bool = False) -> Optional[Callable]`
  - `SwitchboardSlotsMixin.connect_slot(self, widget, slot=None)` — Connect a widget's signals to its slot.
  - `SwitchboardSlotsMixin.slot_history(self, index=None, allow_duplicates=False, inc=None, exc=None, add=None, remove=None, length=200)` — Get the slot history.

<a id="switchboard--style"></a>
### `switchboard/style.py`

Mixin that exposes the :class:`StyleSheet` class on the Switchboard.

- **[`class SwitchboardStyleMixin`](uitk/uitk/switchboard/style.py#L27)** — Adds a lazy ``style`` property exposing the :class:`StyleSheet` class.
  - `SwitchboardStyleMixin.style(self)` *(property)* — The :class:`StyleSheet` class (imported lazily on first access).

<a id="switchboard--utils"></a>
### `switchboard/utils.py`

- **[`class SwitchboardUtilsMixin`](uitk/uitk/switchboard/utils.py#L10)** — Utility methods for widget positioning, centering, and screen geometry.
  - `SwitchboardUtilsMixin.get_cursor_offset_from_center(widget)` *(static)* — Get the relative position of the cursor with respect to the center of a given widget.
  - `SwitchboardUtilsMixin.center_widget(widget, pos=None, offset_x=0, offset_y=0, padding_x=None, padding_y=None, relative: QtWidgets.QWidget = None)` *(static)* — Adjust the widget's size to fit contents and center it at the given point, on the screen, at cursor…
  - `SwitchboardUtilsMixin.unpack_names(cls, name_string)` *(class)* — Unpacks a comma-separated string of names and returns a list of individual names.
  - `SwitchboardUtilsMixin.get_widgets_by_string_pattern(self, ui, name_string)` — Get a list of corresponding widgets from a single shorthand formatted string.
  - `SwitchboardUtilsMixin.get_methods_by_string_pattern(self, clss, name_string)` — Get a list of corresponding methods from a single shorthand formatted string.
  - `SwitchboardUtilsMixin.create_button_groups(self, ui: QtWidgets.QWidget, *args: str, allow_deselect: bool = False, allow_multiple: bool = False) -> List[QtWidgets.QButtonGroup]` — Create button groups for a set of widgets.
  - `SwitchboardUtilsMixin.toggle_multi(self, ui, trigger=None, signal=None, **kwargs)` — Set multiple boolean properties for multiple widgets at once, or connect a trigger to do so automat…
  - `SwitchboardUtilsMixin.connect_multi(self, ui, widgets, signals, slots)` — Connect multiple signals to multiple slots at once.
  - `SwitchboardUtilsMixin.set_axis_for_checkboxes(self, checkboxes, axis, ui=None)` — Set the given checkbox's check states to reflect the specified axis.
  - `SwitchboardUtilsMixin.get_axis_from_checkboxes(self, checkboxes, ui=None, return_type='str')` — Get the intended axis value as a string or integer by reading the multiple checkbox's check states.
  - `SwitchboardUtilsMixin.hide_unmatched_groupboxes(self, ui, unknown_tags) -> None` — Hides all QGroupBox widgets in the provided UI that do not match the unknown tags extracted
  - `SwitchboardUtilsMixin.invert_on_modifier(value)` *(static)* — Invert a numerical or boolean value if the alt key is pressed.
  - `SwitchboardUtilsMixin.progress(self, ui=None, total: Optional[int] = None, text: str = '')` — Context manager for cooperative progress / task feedback.
  - `SwitchboardUtilsMixin.progress_adapter(update: Callable[..., bool]) -> Callable[..., bool]` *(static)* — Adapt the footer ``update`` callable to the shape downstream
  - `SwitchboardUtilsMixin.message_box(self, string, *buttons, location='topMiddle', timeout=3, background=0.75)` — Spawns a message box with the given text and optionally sets buttons.
  - `SwitchboardUtilsMixin.text_view_dialog(self, text: str = '', *buttons, title: str = '', size=(640, 400), monospace: bool = False, word_wrap: bool = True, background=False, parent=None)` — Spawn a scrollable text-viewer window with optional buttons.
  - `SwitchboardUtilsMixin.file_dialog(file_types: Union[str, List[str]] = ['*.*'], title: str = 'Select files to open', start_dir: str = '/home', filter_description: str = 'All Files', allow_multiple: bool = True) -> Union[str, List[str]]` *(static)* — Open a file dialog to select files of the given type(s) using qtpy.
  - `SwitchboardUtilsMixin.dir_dialog(title: str = 'Select a directory', start_dir: str = '/home') -> str` *(static)* — Open a directory dialog to select a directory using qtpy.
  - `SwitchboardUtilsMixin.save_file_dialog(file_types: Union[str, List[str]] = ['*.*'], title: str = 'Save file', start_dir: str = '/home', filter_description: str = 'All Files') -> Optional[str]` *(static)* — Open a save-file dialog to choose a destination path.
  - `SwitchboardUtilsMixin.input_dialog(title: str = 'Input', label: str = 'Enter value:', text: str = '', parent: QtWidgets.QWidget = None, placeholder: str = '', validate: callable = None, error_text: str = 'Invalid input.') -> str` *(static)* — Show a modal text-input dialog and return the entered string.
  - `SwitchboardUtilsMixin.simulate_key_press(ui, key=QtCore.Qt.Key_F12, modifiers=QtCore.Qt.NoModifier, release=False)` *(static)* — Simulate a key press event for the given UI and optionally release the keyboard.
  - `SwitchboardUtilsMixin.defer_with_timer(self, func: callable, *args, ms: int = 300, **kwargs) -> None` — Defer execution of any callable with arguments after a delay.
  - `SwitchboardUtilsMixin.gc_protect(self, obj=None, clear=False)` — Protect the given object(s) from garbage collection by holding a strong reference.
  - `SwitchboardUtilsMixin.modal_menu(content_fn, parent=None, **kwargs)` *(static)* — Show a themed modal Menu popup, block until dismissed.

<a id="switchboard--widgets"></a>
### `switchboard/widgets.py`

- **[`class SwitchboardWidgetMixin`](uitk/uitk/switchboard/widgets.py#L8)** — Widget registration, resolution, and dynamic class loading for Switchboard.
  - `SwitchboardWidgetMixin.resolve_widget_class(self, class_name: str) -> Optional[Type[QtWidgets.QWidget]]` — Return the widget class registered under the given name.
  - `SwitchboardWidgetMixin.get_icon(self, icon_name: str) -> QtGui.QIcon` — Get a registered icon by name.
  - `SwitchboardWidgetMixin.register_widget(self, widget)` — Register any custom widgets using the module names.
  - `SwitchboardWidgetMixin.get_widget(self, name, ui=None)` — Case insensitive.
  - `SwitchboardWidgetMixin.get_widget_from_slot(self, method)` — Get the corresponding widget from a given method.
  - `SwitchboardWidgetMixin.set_widget_attrs(self, ui, widget_names, **kwargs)` — Set multiple properties, for multiple widgets, on multiple UI's at once.
  - `SwitchboardWidgetMixin.is_widget(self, obj)` — Returns True if the given obj is a valid widget.
  - `SwitchboardWidgetMixin.get_parent_widgets(widget, object_names=False)` *(static)* — Get the all parent widgets of the given widget.
  - `SwitchboardWidgetMixin.get_all_windows(name=None)` *(static)* — Get Qt windows.
  - `SwitchboardWidgetMixin.get_all_widgets(name=None)` *(static)* — Get Qt widgets.
  - `SwitchboardWidgetMixin.get_widget_at(pos, top_widget_only=True)` *(static)* — Get visible and enabled widget(s) located at the given position.

<a id="widgets--_html_style"></a>
### `widgets/_html_style.py`

HTML formatting helpers shared by uitk's rich-text widgets.

- [`apply_prefix_styles(string: str) -> str`](uitk/uitk/widgets/_html_style.py#L36) — Replace level-prefix tokens (``Error:``, ``Warning:`` ...) with styled spans.
- [`apply_inline_styles(string: str) -> str`](uitk/uitk/widgets/_html_style.py#L43) — Replace bare HTML tags with style-bearing equivalents.
- [`wrap_font_color(string: str, color: str) -> str`](uitk/uitk/widgets/_html_style.py#L50)
- [`wrap_font_size(string: str, size) -> str`](uitk/uitk/widgets/_html_style.py#L54)
- [`resolve_background(background) -> Optional[str]`](uitk/uitk/widgets/_html_style.py#L58) — Convert a background parameter to a CSS colour string or ``None``.
- [`format_rich_text(string: str, *, align: str = 'left', font_color: str = 'white', font_size: Union[int, str, None] = None) -> str`](uitk/uitk/widgets/_html_style.py#L77) — Apply the standard uitk HTML pipeline to a string.

<a id="widgets--attributeWindow--_attributeWindow"></a>
### `widgets/attributeWindow/_attributeWindow.py`

- **[`class AttributeWindow(Menu)`](uitk/uitk/widgets/attributeWindow/_attributeWindow.py#L11)** — Dynamic popup editor for inspecting and modifying object attributes.
  - `AttributeWindow.initialize_ui(self)` — Initializes the user interface components of the AttributeWindow.
  - `AttributeWindow.refresh_attributes(self)` — Refreshes the window with the latest attributes.
  - `AttributeWindow.clear_ui_elements(self)` — Clears existing labels and widgets from the UI.
  - `AttributeWindow.default_get_attribute_func(self)`
  - `AttributeWindow.create_set_attribute_func_wrapper(self, set_attribute_func)`
  - `AttributeWindow.default_set_attribute_func(self, name, value)`
  - `AttributeWindow.is_valid_attribute(attr_name)` *(static)*
  - `AttributeWindow.is_type_supported(attribute_type)` *(static)* — Return True if AttributeWindow can auto-build a widget for *attribute_type*.
  - `AttributeWindow.add_attributes(self, attributes, value=None)` — Adds a single attribute or multiple attributes to the attribute window.
  - `AttributeWindow.add_attribute_spec(self, spec)` — Add one attribute via an explicit :class:`uitk.AttributeSpec`.
  - `AttributeWindow.emit_value_changed(self, widget)` — Emit the valueChanged signal for a widget (or composite-aware).
  - `AttributeWindow.emit_composite_value_changed(self, attribute_name)` — Construct and emit the full attribute value for a composite attribute.
  - `AttributeWindow.setup_label(self, attribute_name)` — Set up the label for the attribute.
  - `AttributeWindow.on_label_toggled(self, label)` — Slot to be called when a label is toggled.
  - `AttributeWindow.on_button_clicked(self, button, checked)` — Slot for buttonClicked signal of QButtonGroup.
  - `AttributeWindow.add_to_layout(self, label, widget)` — Add the label and widget to the layout.
  - `AttributeWindow.showEvent(self, event)` — Handle the show event for the window.

<a id="widgets--checkBox"></a>
### `widgets/checkBox.py`

- **[`class CheckBox(QtWidgets.QCheckBox, MenuMixin, AttributesMixin, RichText, TextOverlay)`](uitk/uitk/widgets/checkBox.py#L9)** — Enhanced checkbox with rich text labels, overlays, and context menu.
  - `CheckBox.set_checkbox_rich_text_style(self, state)` — Update rich text style based on checkbox state.
  - `CheckBox.checkState(self)` — Get the state of a checkbox as an integer value.
  - `CheckBox.setCheckState(self, state)` — Set the state of a checkbox as an integer value.
  - `CheckBox.hitButton(self, pos: QtCore.QPoint) -> bool` — Overridden method from QAbstractButton, used internally by Qt to decide whether a mouse press event
  - `CheckBox.mousePressEvent(self, event)` — Overridden method from QWidget to handle mouse press events.

<a id="widgets--collapsableGroup"></a>
### `widgets/collapsableGroup.py`

- **[`class CollapsableGroup(QtWidgets.QGroupBox, AttributesMixin)`](uitk/uitk/widgets/collapsableGroup.py#L8)** — Expandable/collapsible group box that shows or hides its contents.
  - `CollapsableGroup.toggle_expand(self, checked)` — Toggle the expanded/collapsed state
  - `CollapsableGroup.setLayout(self, layout)` — Override setLayout.
  - `CollapsableGroup.addWidget(self, widget)` — Add a widget to the collapsible content area
  - `CollapsableGroup.addLayout(self, layout)` — Add a layout to the collapsible content area
  - `CollapsableGroup.sizeHint(self)` — Return appropriate size hint based on current state.

<a id="widgets--colorSwatch"></a>
### `widgets/colorSwatch.py`

- **[`class ColorSwatch(QtWidgets.QPushButton, AttributesMixin, ConvertMixin)`](uitk/uitk/widgets/colorSwatch.py#L9)** — Color picker button that displays and stores a selectable color value.
  - `ColorSwatch.color(self)` *(property)* — Return the current color.
  - `ColorSwatch.color(self, value)`
  - `ColorSwatch.settings(self)` *(property)*
  - `ColorSwatch.settings(self, value)`
  - `ColorSwatch.saveColor(self)`
  - `ColorSwatch.loadColor(self)`
  - `ColorSwatch.canSaveLoadColor(self)` — Check if the widget is in a state that allows saving or loading the color.
  - `ColorSwatch.initializeColor(self)`
  - `ColorSwatch.updateBackgroundColor(self)` — Updates the widget's background color based on the check state.
  - `ColorSwatch.mouseDoubleClickEvent(self, event)` — Open a color dialog on double click to select a new color.

<a id="widgets--comboBox"></a>
### `widgets/comboBox.py`

- **[`class CustomStyle(QtWidgets.QProxyStyle)`](uitk/uitk/widgets/comboBox.py#L13)** — Custom proxy style for ComboBox that handles header text display.
  - `CustomStyle.drawControl(self, element, opt, painter, widget=None)` — Override control drawing to handle header text display.
  - `CustomStyle.drawComplexControl(self, control, opt, painter, widget=None)`
  - `CustomStyle.styleHint(self, hint, option=None, widget=None, returnData=None)`
  - `CustomStyle.pixelMetric(self, metric, option=None, widget=None)`
- **[`class AlignedComboBox(QtWidgets.QComboBox)`](uitk/uitk/widgets/comboBox.py#L81)** — ComboBox with header text and alignment support.
  - `AlignedComboBox.setHeaderText(self, text)` — Set the header text displayed when no item is selected.
  - `AlignedComboBox.setHeaderAlignment(self, alignment)` — Set the alignment for header text.
  - `AlignedComboBox.get_stylesheet_property(self, property_name)` — Extract a numeric property value from the widget's stylesheet.
  - `AlignedComboBox.paintEvent(self, event)` — Custom paint event to draw header text when no selection.
- **[`class ComboBox(AlignedComboBox, MenuMixin, OptionBoxMixin, AttributesMixin, RichText, TextOverlay)`](uitk/uitk/widgets/comboBox.py#L269)** — QComboBox with automatic Menu and OptionBox integration.
  - `ComboBox.items(self)` *(property)*
  - `ComboBox.currentData(self)`
  - `ComboBox.setCurrentData(self, value)`
  - `ComboBox.currentText(self)`
  - `ComboBox.setCurrentText(self, text)` — Select the item whose rich or plain text matches *text*.
  - `ComboBox.setItemText(self, index, text)`
  - `ComboBox.setAsCurrent(self, i: Union[str, int], blockSignals: bool = False, strict: bool = False, fallback_index: int = None) -> None` — Set the current item by value or index, with optional fallback if not found.
  - `ComboBox.setCurrentIndex(self, index)`
  - `ComboBox.check_index(self, index)`
  - `ComboBox.focusOutEvent(self, event)`
  - `ComboBox.setEditable(self, editable, emit_signal=True)`
  - `ComboBox.force_header_display(self)`
  - `ComboBox.add_header(self, text)`
  - `ComboBox.add_single(self, item, data, ascending)`
  - `ComboBox.add(self, x, data=None, header=None, header_alignment='left', clear=True, restore_index=False, ascending=False, _recursion=False, prefix=None, **kwargs)`
  - `ComboBox.removeItem(self, index=None)`
  - `ComboBox.showPopup(self)`
  - `ComboBox.keyPressEvent(self, event)`

<a id="widgets--doubleSpinBox"></a>
### `widgets/doubleSpinBox.py`

- **[`class DoubleSpinBox(QtWidgets.QDoubleSpinBox, MenuMixin, AttributesMixin)`](uitk/uitk/widgets/doubleSpinBox.py#L9)** — Custom QDoubleSpinBox with enhanced step size adjustment capabilities.
  - `DoubleSpinBox.textFromValue(self, value: float) -> str` — Format the text displayed in the spin box, removing trailing zeros and unnecessary decimal points.
  - `DoubleSpinBox.setPrefix(self, prefix: str) -> None` — Add a tab space after the prefix for clearer display.
  - `DoubleSpinBox.wheelEvent(self, event: QtGui.QWheelEvent) -> None` — Handle wheel events with modifier keys.
  - `DoubleSpinBox.adjustStepSize(self, event: QtGui.QWheelEvent) -> None` — Adjust the step size dynamically based on the Alt modifier key.
  - `DoubleSpinBox.increaseValueWithLargeStep(self, event: QtGui.QWheelEvent) -> None` — Increase the spin box value by a larger step when Ctrl is pressed.
  - `DoubleSpinBox.decreaseValueWithSmallStep(self, event: QtGui.QWheelEvent) -> None` — Move the value by the lowest decimal place (Ctrl+Alt).
  - `DoubleSpinBox.message(self, text: str) -> None` — Display a temporary message box with the given text.

<a id="widgets--editors--color_mapping_editor"></a>
### `widgets/editors/color_mapping_editor.py`

Reusable color-mapping editor widget.

- **[`class ColorMappingEditor(QtWidgets.QWidget)`](uitk/uitk/widgets/editors/color_mapping_editor.py#L41)** — Reusable widget for editing named color mappings with optional sections.
  - `ColorMappingEditor.add_action_button(self, button: QtWidgets.QPushButton)` — Append *button* to the footer action row.
  - `ColorMappingEditor.restore_defaults(self)` — Clear overrides for keys owned by this editor and revert to defaults.
  - `ColorMappingEditor.color_map(self) -> Dict[str, ColorValue]` — Return the full mapping with user overrides applied.
  - `ColorMappingEditor.apply_color_map(self, cmap: Dict[str, ColorValue], save_to_settings: bool = True) -> None` — Apply *cmap* to the swatches and (optionally) persist to settings.
- **[`class ColorMappingDialog(QtWidgets.QDialog)`](uitk/uitk/widgets/editors/color_mapping_editor.py#L379)** — ``QDialog`` wrapper around :class:`ColorMappingEditor`.
  - `ColorMappingDialog.showEvent(self, event)`
  - `ColorMappingDialog.header(self)` *(property)* — The :class:`Header` widget at the top.
  - `ColorMappingDialog.footer(self)` *(property)* — The :class:`Footer` widget at the bottom.
  - `ColorMappingDialog.color_map(self)` — Return the full mapping with user overrides applied.

<a id="widgets--editors--editor_panel"></a>
### `widgets/editors/editor_panel.py`

Editor panel: WindowPanel + optional preset save/load row.

- **[`class EditorPanel(WindowPanel)`](uitk/uitk/widgets/editors/editor_panel.py#L24)** — Windowed editor with optional preset management.
  - `EditorPanel.init_preset_row(self, dir_name)` — Add a preset management row to the body layout.
  - `EditorPanel.preset_dir(self) -> Path` *(property)* — The directory where this editor's preset files live.
  - `EditorPanel.preset_dir(self, value) -> None` — Redirect this editor's preset directory.
  - `EditorPanel.export_preset_data(self) -> dict` — Override to provide data for preset saving.
  - `EditorPanel.import_preset_data(self, data: dict)` — Override to apply data from a loaded preset.
  - `EditorPanel.save_preset(self, name: str) -> Path` — Save current state to a named preset.
  - `EditorPanel.load_preset(self, name: str) -> bool` — Load a preset and apply it.
  - `EditorPanel.delete_preset(self, name: str) -> bool`
  - `EditorPanel.rename_preset(self, old: str, new: str) -> bool`

<a id="widgets--editors--hotkey_editor"></a>
### `widgets/editors/hotkey_editor.py`

- **[`class CollisionConflict`](uitk/uitk/widgets/editors/hotkey_editor.py#L21)** — A single conflict reported by a collision checker.
- **[`class KeyCaptureDialog(QtWidgets.QDialog)`](uitk/uitk/widgets/editors/hotkey_editor.py#L57)** — Modal dialog to capture a key sequence.
  - `KeyCaptureDialog.keyPressEvent(self, event)` — Capture key press event.
  - `KeyCaptureDialog.clear_key(self)`
  - `KeyCaptureDialog.get_sequence(self)`
- **[`class HotkeyEditor(EditorPanel)`](uitk/uitk/widgets/editors/hotkey_editor.py#L130)** — UI for editing global shortcuts with preset support.
  - `HotkeyEditor.export_preset_data(self)`
  - `HotkeyEditor.import_preset_data(self, data)`
  - `HotkeyEditor.export_shortcuts(self) -> dict` — Export all user-customised shortcuts across loaded UIs.
  - `HotkeyEditor.import_shortcuts(self, data: dict) -> int` — Bulk-apply shortcut bindings from a preset dict.
  - `HotkeyEditor.showEvent(self, event)` — Refresh data each time the editor is shown.
  - `HotkeyEditor.refresh_ui_list(self)` — Populate the UI combobox with every registered UI.
  - `HotkeyEditor.populate(self)` — Populate the table with shortcuts for the selected UI.
  - `HotkeyEditor.on_cell_double_clicked(self, row, column)` — Handle editing the shortcut.
  - `HotkeyEditor.reset_shortcut(self, ui, method_name, default_seq, default_scope='window')` — Reset sequence and scope to decorator defaults.
  - `HotkeyEditor.add_collision_checker(self, checker: Callable) -> None` — Register a collision checker.
  - `HotkeyEditor.remove_collision_checker(self, checker: Callable) -> None` — Unregister a previously added collision checker.

<a id="widgets--editors--shortcut_editor"></a>
### `widgets/editors/shortcut_editor.py`

Editor windows used by :meth:`ShortcutManager.show_editor`.

- **[`class KeyCaptureDialog(QtWidgets.QDialog)`](uitk/uitk/widgets/editors/shortcut_editor.py#L21)** — Modal dialog that captures a single key combination.
  - `KeyCaptureDialog.keyPressEvent(self, event)`
  - `KeyCaptureDialog.get_sequence(self) -> str`
- **[`class ShortcutEditorDialog(QtWidgets.QWidget)`](uitk/uitk/widgets/editors/shortcut_editor.py#L76)** — Editor panel for viewing and remapping ShortcutManager bindings.
  - `ShortcutEditorDialog.panel(self)` *(property)* — The :class:`EditorPanel` widget.
  - `ShortcutEditorDialog.show(self)`
  - `ShortcutEditorDialog.close(self)`

<a id="widgets--editors--style_editor"></a>
### `widgets/editors/style_editor.py`

- **[`class StyleEditor(EditorPanel)`](uitk/uitk/widgets/editors/style_editor.py#L42)** — UI for editing global stylesheet variables with preset support.
  - `StyleEditor.export_preset_data(self)`
  - `StyleEditor.import_preset_data(self, data)`
  - `StyleEditor.populate(self)` — Populate the table with variables for the current theme + tier.
  - `StyleEditor.on_color_changed(self, name, color)` — Handle color change from swatch.
  - `StyleEditor.on_length_changed(self, name, value)` — Handle length change from spinbox.
  - `StyleEditor.reset_variable(self, name)` — Reset a single variable.
  - `StyleEditor.reset_all(self)` — Reset all overrides.
  - `StyleEditor.refresh_row(self, name)` — Update the editor widget for a specific variable name.

<a id="widgets--editors--switchboard_browser"></a>
### `widgets/editors/switchboard_browser.py`

Searchable, tag-filtered launcher for any handler-exposed entry.

- **[`class LaunchOptions`](uitk/uitk/widgets/editors/switchboard_browser.py#L44)**
- **[`class SwitchboardBrowserModel(QtCore.QAbstractTableModel)`](uitk/uitk/widgets/editors/switchboard_browser.py#L55)** — Table model over a Switchboard's UI registry.
  - `SwitchboardBrowserModel.refresh_after_launch(self, name: str) -> None` — Public hook: caller invokes this after launching to refresh the row.
  - `SwitchboardBrowserModel.rowCount(self, parent=QtCore.QModelIndex()) -> int`
  - `SwitchboardBrowserModel.columnCount(self, parent=QtCore.QModelIndex()) -> int`
  - `SwitchboardBrowserModel.headerData(self, section, orientation, role=QtCore.Qt.DisplayRole)`
  - `SwitchboardBrowserModel.data(self, index, role=QtCore.Qt.DisplayRole)`
  - `SwitchboardBrowserModel.flags(self, index)`
  - `SwitchboardBrowserModel.setData(self, index, value, role=QtCore.Qt.EditRole)`
  - `SwitchboardBrowserModel.entry_for_name(self, name: str) -> Optional[HandlerEntry]`
  - `SwitchboardBrowserModel.all_unique_tags(self) -> List[str]`
- **[`class SwitchboardBrowser(EditorPanel)`](uitk/uitk/widgets/editors/switchboard_browser.py#L599)** — Searchable launcher for every UI registered with a Switchboard.
  - `SwitchboardBrowser.hidden_uis(self) -> Set[str]` *(property)*
  - `SwitchboardBrowser.hidden_uis(self, value: Iterable[str]) -> None`
  - `SwitchboardBrowser.hidden_tags(self) -> Set[str]` *(property)*
  - `SwitchboardBrowser.hidden_tags(self, value: Iterable[str]) -> None`
  - `SwitchboardBrowser.set_search_scope(self, value: str) -> None` — Public helper: set the search-line-edit scope to ``value``.
  - `SwitchboardBrowser.set_exclude_scope(self, value: str) -> None` — Public helper: set the exclude-line-edit scope to ``value``.
  - `SwitchboardBrowser.launch_options(self) -> LaunchOptions`
  - `SwitchboardBrowser.hide_inherited_tags(self) -> bool` *(property)*
  - `SwitchboardBrowser.showEvent(self, event) -> None`

<a id="widgets--expandableList"></a>
### `widgets/expandableList.py`

- **[`class ExpandableList(QtWidgets.QWidget, AttributesMixin)`](uitk/uitk/widgets/expandableList.py#L8)** — A subclass of QWidget that represents a list of widgets, each potentially having an expandable subl…
  - `ExpandableList.apply_preset(self, preset_name)` — Apply a named preset to configure expansion behavior.
  - `ExpandableList.get_items(self)` — Get all items in the list and its sublists.
  - `ExpandableList.get_item_text(self, widget)` — Get the textual representation of a widget.
  - `ExpandableList.get_parent_item_text(self, widget)` — Get the text attribute of the parent item of a widget's sublist.
  - `ExpandableList.get_item_data(self, widget)` — Get data associated with a widget in the list or its sublists.
  - `ExpandableList.get_parent_item_data(self, widget)` — Get the data associated with the parent item of a widget's sublist.
  - `ExpandableList.set_item_data(self, widget, data)` — Set data associated with a widget in the list or its sublists.
  - `ExpandableList.clear(self)` — Clear all items in the list and its sublists.
  - `ExpandableList.add(self, x, data=None, **kwargs)` — Add an item or multiple items to the list or its sublists.
  - `ExpandableList.hide(self)` — Hide this list, but only if no child sublist is still visible.
  - `ExpandableList.showEvent(self, event)` — On the root list's show, size to content and retroactively
  - `ExpandableList.hideEvent(self, event)` — Ensure all sublists are closed when this list is hidden.
  - `ExpandableList.get_padding(widget)` *(static)* — Get the padding values around a widget.
  - `ExpandableList.sizeHint(self)` — Return the recommended size for the widget.
  - `ExpandableList.eventFilter(self, widget, event)` — Filter events for the ExpandableList.
  - `ExpandableList.leaveEvent(self, event)` — Handle the cursor leaving this list widget.

<a id="widgets--footer"></a>
### `widgets/footer.py`

- **[`class Footer(QtWidgets.QWidget, AttributesMixin, SizeGripMixin)`](uitk/uitk/widgets/footer.py#L17)** — Footer is a widget that acts as a status bar with an integrated
  - `Footer.container_layout(self) -> QtWidgets.QHBoxLayout` *(property)* — Backward compatibility: return main_layout as container_layout.
  - `Footer.alignment(self) -> QtCore.Qt.Alignment` — Get alignment of the status label (backward compatibility).
  - `Footer.update_font_size(self)` — Public method for updating font size (backward compatibility).
  - `Footer.font(self) -> QtGui.QFont` — Get font from status label (backward compatibility).
  - `Footer.add_widget(self, widget: QtWidgets.QWidget, side: str = 'right', background: bool = False, rounded: bool = True) -> QtWidgets.QWidget` — Insert an arbitrary widget into the footer on the given side.
  - `Footer.add_action_button(self, text: str = '', icon_name: str = None, tooltip: str = '', callback=None, rounded: bool = True) -> QtWidgets.QPushButton` — Add an action button to the right side of the footer.
  - `Footer.progress_bar(self) -> ProgressBar` *(property)* — Get the embedded progress bar.
  - `Footer.status_label(self) -> QtWidgets.QLabel` *(property)* — Get the status label.
  - `Footer.size_grip(self) -> Optional[QtWidgets.QSizeGrip]` *(property)* — Get the size grip widget if it exists.
  - `Footer.size_grip(self, value: Optional[QtWidgets.QSizeGrip]) -> None` — Set the size grip widget (used internally by SizeGripMixin).
  - `Footer.setText(self, text: str) -> None` — Set the status text (convenience method matching QLabel API).
  - `Footer.text(self) -> str` — Get the current displayed text (convenience method matching QLabel API).
  - `Footer.setStatusText(self, text: str | None = None) -> None` — Set the status text of the footer.
  - `Footer.setDefaultStatusText(self, text: str | None = None) -> None` — Set fallback text shown when no explicit status is provided.
  - `Footer.statusText(self) -> str` — Get the status text of the footer.
  - `Footer.start_progress(self, total: Optional[int] = None, text: str = '') -> Callable[[Optional[int], Optional[str]], bool]` — Start showing progress in the footer.
  - `Footer.update_progress(self, value: Optional[int] = None, text: Optional[str] = None) -> bool` — Tick the progress bar and optionally update the status text.
  - `Footer.finish_progress(self, text: Optional[str] = None, delay_ms: int = 1000)` — Finish the progress and hide the bar.
  - `Footer.cancel_progress(self)` — Cancel the current progress operation.
  - `Footer.set_progress_total(self, total: int) -> None` — Adjust the bar's task total mid-flight.
  - `Footer.progress(self, total: Optional[int] = None, text: str = '') -> 'FooterProgressContext'` — Context manager for cooperative progress / task feedback.
  - `Footer.resizeEvent(self, event)` — Debounce resize: restart timer on each event so we only
  - `Footer.showEvent(self, event)` — Ensure text is properly sized and elided on first show.
  - `Footer.attach_to(self, widget: QtWidgets.QWidget) -> None` — Attach this footer to the bottom of a QWidget or QMainWindow's centralWidget.
- **[`class FooterProgressContext`](uitk/uitk/widgets/footer.py#L606)** — Context manager for footer progress tracking.
- **[`class FooterStatusController`](uitk/uitk/widgets/footer.py#L627)** — Helper that keeps a footer in sync with a resolver function.
  - `FooterStatusController.set_resolver(self, resolver: Callable[[], str]) -> None`
  - `FooterStatusController.set_truncation(self, truncate_kwargs: Optional[Mapping[str, Any]] = None, **extra_kwargs: Any) -> None` — Configure truncation behavior for footer updates via StrUtils.truncate kwargs.
  - `FooterStatusController.update(self) -> None`

<a id="widgets--header"></a>
### `widgets/header.py`

- **[`class Header(QtWidgets.QLabel, AttributesMixin, RichText, TextOverlay, ptk.LoggingMixin)`](uitk/uitk/widgets/header.py#L11)** — Header is a QLabel that can be dragged around the screen and can be pinned/unpinned.
  - `Header.menu(self)` *(property)*
  - `Header.get_icon_path(self, icon_filename)` — Get the full path to an icon file in the uitk/icons directory.
  - `Header.create_svg_icon(self, icon_filename, size=16)` — Create a QIcon from an SVG file.
  - `Header.create_button(self, icon_filename, callback, button_type=None)` — Create a button with the given icon and callback.
  - `Header.has_buttons(self, button_type=None)` — Check if the header has a specific button type or any button.
  - `Header.config_buttons(self, *button_list)` — Configure header buttons from a list and align them to the right.
  - `Header.trigger_resize_event(self)`
  - `Header.resizeEvent(self, event)`
  - `Header.resize_buttons(self)`
  - `Header.update_font_size(self)`
  - `Header.setTitle(self, title)` — Set the title of the header.
  - `Header.title(self)` — Get the title of the header (without any version suffix).
  - `Header.setVersion(self, version)` — Set an optional version string appended to the title.
  - `Header.version(self)` — Return the current version suffix (without the ``v`` prefix).
  - `Header.setText(self, text)` — Override to remember the untruncated title for elision.
  - `Header.minimize_window(self)` — Minimize the window: collapse to header-only, narrow to a fixed width,
  - `Header.restore_window(self)` — Restore a minimized window to its original size and position.
  - `Header.toggle_maximize(self)` — Toggle between maximized and normal window state.
  - `Header.toggle_fullscreen(self)` — Toggle between fullscreen and normal window state.
  - `Header.hide_window(self)` — Hide the parent window.
  - `Header.unhide_window(self)` — Unhide the parent window.
  - `Header.trigger_refresh(self)` — Emit the refresh_requested signal.
  - `Header.show_menu(self)` — Show the menu.
  - `Header.toggle_collapse(self)` — Toggle between collapsed (header only) and expanded window states.
  - `Header.collapse_window(self, fixed_width=None)` — Collapse the parent window to show only the header.
  - `Header.expand_window(self)` — Expand the window back to its original size.
  - `Header.toggle_pin(self, from_drag=False)` — Toggle pinning of the window.
  - `Header.reset_pin_state(self)` — Force the header into an unpinned state without hiding the window.
  - `Header.mousePressEvent(self, event)` — Handle the mouse press event.
  - `Header.mouseMoveEvent(self, event)` — Handle the mouse move event.
  - `Header.mouseReleaseEvent(self, event)`
  - `Header.showEvent(self, event)`
  - `Header.attach_to(self, widget: QtWidgets.QWidget) -> None` — Attach this header to the top of a QWidget or QMainWindow's centralWidget if appropriate.
  - `Header.hideEvent(self, event)` — Reset minimize/collapse state when header (and window) is hidden.

<a id="widgets--label"></a>
### `widgets/label.py`

- **[`class Label(QtWidgets.QLabel, MenuMixin, OptionBoxMixin, AttributesMixin)`](uitk/uitk/widgets/label.py#L9)** — Enhanced QLabel with click signals and context menu support.
  - `Label.mousePressEvent(self, event)` — Handle mouse press events to emit clicked signal.
  - `Label.mouseReleaseEvent(self, event)` — Handle mouse release events to emit released signal.

<a id="widgets--lineEdit"></a>
### `widgets/lineEdit.py`

- **[`class LineEditFormatMixin`](uitk/uitk/widgets/lineEdit.py#L11)** — Lazily formats QLineEdit with reversible visual state feedback.
  - `LineEditFormatMixin.set_action_color(self, key: str) -> None`
  - `LineEditFormatMixin.reset_action_color(self) -> None`
  - `LineEditFormatMixin.set_validator(self, validator, *, debounce_ms: int = 300, invalid_tooltip: str = 'Invalid', valid_tooltip=None, empty_tooltip=None, empty_is_valid: bool = True)` — Install a debounced text validator with visual feedback.
  - `LineEditFormatMixin.clear_validator(self)` — Remove any installed validator and reset visual state.
  - `LineEditFormatMixin.is_valid(self)` *(property)* — Last validation result, or ``None`` if no validator is set.
  - `LineEditFormatMixin.validate_now(self)` — Cancel any pending debounce and validate the current text now.
- **[`class LineEdit(QtWidgets.QLineEdit, MenuMixin, OptionBoxMixin, AttributesMixin, LineEditFormatMixin)`](uitk/uitk/widgets/lineEdit.py#L202)** — LineEdit with automatic Menu and OptionBox integration.
  - `LineEdit.contextMenuEvent(self, event)` — Override the standard context menu if there is a custom one.
  - `LineEdit.showEvent(self, event)` — Handle show event.
  - `LineEdit.hideEvent(self, event)` — Handle hide event.

<a id="widgets--mainWindow"></a>
### `widgets/mainWindow.py`

- **[`class MainWindow(QtWidgets.QMainWindow, AttributesMixin, TooltipMixin, ptk.LoggingMixin)`](uitk/uitk/widgets/mainWindow.py#L18)** — Application main window with state persistence and child widget management.
  - `MainWindow.setCentralWidget(self, widget: QtWidgets.QWidget) -> None` — Overrides QMainWindow's setCentralWidget to handle initialization when the central widget is set or…
  - `MainWindow.initialize_window_flags(self, central_widget: QtWidgets.QWidget) -> None` — Initializes the window flags based on the central widget.
  - `MainWindow.edit_tags(self, target: Union[str, QtWidgets.QWidget] = None, add: Union[str, List[str]] = None, remove: Union[str, List[str]] = None, clear: bool = False, reset: bool = False) -> Union[str, None]` — Edit tags on a widget or a tag string.
  - `MainWindow.pinned(self) -> bool` *(property)* — Whether the window is pinned (resists hide requests).
  - `MainWindow.pinned(self, value: bool) -> None`
  - `MainWindow.set_pinned(self, value: bool) -> None` — Set pin state (method form for signal connections).
  - `MainWindow.is_pinned(self) -> bool` *(property)* — Alias for pinned property.
  - `MainWindow.request_hide(self) -> bool` — Request to hide, respecting pin state.
  - `MainWindow.slots(self) -> list` *(property)* — Returns a list of the slots connected to the widget's signals.
  - `MainWindow.presets(self)` *(property)* — Lazy-initialized PresetManager for saving/loading named presets.
  - `MainWindow.presets(self, _)` — No-op setter so the switchboard can harmlessly reassign.
  - `MainWindow.is_stacked_widget(self) -> bool` *(property)* — Checks if the parent of the widget is a QStackedWidget.
  - `MainWindow.is_current_ui(self) -> bool` *(property)* — Returns True if the widget is the currently active UI, False otherwise.
  - `MainWindow.is_current_ui(self, value: bool) -> None` — Sets the widget as the currently active UI if value is True.
  - `MainWindow.register_widget(self, widget: QtWidgets.QWidget, **kwargs: Any) -> None` — Registers a widget with the main window, initializing it and connecting its signals.
  - `MainWindow.trigger_deferred(self) -> None` — Executes all deferred methods, in priority order.
  - `MainWindow.perform_restore_state(self, widget: QtWidgets.QWidget, force=False) -> None` — Restores the state of a given widget if it has a restore_state attribute.
  - `MainWindow.sync_widget_values(self, widget: QtWidgets.QWidget, value: Any) -> None` — Sync a widget's state value across related UIs and apply the value using StateManager.
  - `MainWindow.eventFilter(self, watched, event) -> bool` — Override the event filter to register widgets when they are polished.
  - `MainWindow.adjust_height_by(self, delta: int) -> None` — Apply a signed pixel delta to the window's height.
  - `MainWindow.fit_height_to_content(self) -> None` — Snap the window's height to its layout's natural content size.
  - `MainWindow.save_window_geometry(self) -> None` — Save the current window geometry (size and position) to settings.
  - `MainWindow.restore_window_geometry(self) -> None` — Restore the window geometry (size and position) from settings.
  - `MainWindow.clear_saved_geometry(self) -> None` — Clear any saved window geometry from settings.
  - `MainWindow.setVisible(self, visible: bool) -> None` — Override setVisible to respect pin state when hiding.
  - `MainWindow.show(self, pos=None, app_exec=False) -> None` — Show the MainWindow.
  - `MainWindow.showEvent(self, event) -> None` — Override the show event to initialize untracked widgets and restore their states.
  - `MainWindow.register_children(self, root_widget: Optional[QtWidgets.QWidget] = None) -> None` — Registers all child widgets starting from the given widget (or central widget if None).
  - `MainWindow.focusInEvent(self, event) -> None` — Override the focus event to set the current UI when this window gains focus.
  - `MainWindow.focusOutEvent(self, event) -> None`
  - `MainWindow.resizeEvent(self, event) -> None` — Save geometry on resize so pinned/non-hidden windows persist size.
  - `MainWindow.moveEvent(self, event) -> None` — Save geometry on move so pinned/non-hidden windows persist position.
  - `MainWindow.hideEvent(self, event) -> None` — Reimplement hideEvent to emit custom signal when window is hidden.
  - `MainWindow.closeEvent(self, event) -> None` — Reimplement closeEvent to save window geometry and emit custom signal.
  - `MainWindow.setStyleSheet(self, style: str) -> None` — Overrides the setStyleSheet method to respect locking.
  - `MainWindow.reset_style(self) -> None` — Resets the window's stylesheet to its original state.

<a id="widgets--marking_menu--_marking_menu"></a>
### `widgets/marking_menu/_marking_menu.py`

- **[`class MarkingMenu(QtWidgets.QWidget, ptk.SingletonMixin, ptk.LoggingMixin, ptk.HelpMixin)`](uitk/uitk/widgets/marking_menu/_marking_menu.py#L113)** — MarkingMenu is a marking menu based on a QWidget.
  - `MarkingMenu.instance(cls, switchboard: Optional[Switchboard] = None, **kwargs) -> 'MarkingMenu'` *(class)*
  - `MarkingMenu.default_bindings(self) -> dict` *(property)* — The original bindings passed at construction time.
  - `MarkingMenu.bindings(self) -> dict` *(property)* — Get bindings from persistent storage.
  - `MarkingMenu.bindings(self, value: dict)` — Set bindings (auto-persists and triggers rebuild via callback).
  - `MarkingMenu.ui_handler(self)` *(property)* — Accessor for the UI handler.
  - `MarkingMenu.get(self, name: str, **kwargs) -> QtWidgets.QWidget` — Get a UI widget by name.
  - `MarkingMenu.addWidget(self, widget: QtWidgets.QWidget) -> None` — Add a widget to the MarkingMenu window.
  - `MarkingMenu.currentWidget(self) -> Optional[QtWidgets.QWidget]` — Get the currently active widget.
  - `MarkingMenu.setCurrentWidget(self, widget: QtWidgets.QWidget) -> None` — Set the current widget and position it at the cursor.
  - `MarkingMenu.setCurrentIndex(self, index: int) -> None` — Set the current widget index (compatibility method).
  - `MarkingMenu.mousePressEvent(self, event) -> None` — Handle mouse press: route through the central state-sync.
  - `MarkingMenu.keyPressEvent(self, event) -> None` — Handle key press for non-activation key bindings.
  - `MarkingMenu.mouseDoubleClickEvent(self, event) -> None`
  - `MarkingMenu.mouseReleaseEvent(self, event) -> None` — Handle mouse release: dispatch click action or sync menu state.
  - `MarkingMenu.show(self, ui: Optional[str] = None, pos=None, force: bool = False, **kwargs) -> QtWidgets.QWidget` — Central hub for showing any UI component.
  - `MarkingMenu.hide(self)` — Override hide to properly reset stacked widget state.
  - `MarkingMenu.hideEvent(self, event)` — Clean up on hide - ensures mouse grab is released even if hide() was bypassed.
  - `MarkingMenu.dim_other_windows(self) -> None` — Dim all visible windows except the current one.
  - `MarkingMenu.restore_other_windows(self) -> None` — Restore all previously dimmed windows.
  - `MarkingMenu.add_child_event_filter(self, widgets) -> None` — Initialize child widgets with an event filter.
  - `MarkingMenu.child_enterEvent(self, w, event) -> None` — Handle the enter event for child widgets.
  - `MarkingMenu.child_leaveEvent(self, w, event) -> None` — Handle the leave event for child widgets.
  - `MarkingMenu.child_mouseButtonReleaseEvent(self, w, event) -> bool` — Forward release events to the child's normal handler.

<a id="widgets--marking_menu--_resolver"></a>
### `widgets/marking_menu/_resolver.py`

Pure menu-resolution logic for the MarkingMenu.

- [`normalize_key(parts) -> str`](uitk/uitk/widgets/marking_menu/_resolver.py#L26) — Sort and join binding parts into a canonical lookup string.
- [`build_state_key(activation_key_str: Optional[str], buttons: int, modifiers: int, extra_key: Optional[str] = None) -> str`](uitk/uitk/widgets/marking_menu/_resolver.py#L31) — Build a normalized lookup key from a complete input state.
- [`priority_button(buttons: int) -> int`](uitk/uitk/widgets/marking_menu/_resolver.py#L63) — Pick the highest-priority single button from a button mask.
- [`count_buttons(buttons: int) -> int`](uitk/uitk/widgets/marking_menu/_resolver.py#L74) — Count distinct buttons set in the mask.
- [`resolve_target_menu(*, activation_held: bool, activation_key_str: Optional[str], buttons: int, modifiers: int, bindings: Mapping[str, str], extra_key: Optional[str] = None) -> Optional[str]`](uitk/uitk/widgets/marking_menu/_resolver.py#L86) — Return the UI name that should be visible for the given input state.
- [`parse_binding_keys(raw_bindings: Mapping[str, str]) -> tuple`](uitk/uitk/widgets/marking_menu/_resolver.py#L137) — Parse user-supplied bindings into (normalized_dict, activation_key_str).

<a id="widgets--marking_menu--overlay"></a>
### `widgets/marking_menu/overlay.py`

- **[`class OverlayFactoryFilter(QtCore.QObject)`](uitk/uitk/widgets/marking_menu/overlay.py#L8)**
  - `OverlayFactoryFilter.eventFilter(self, widget, event)`
- **[`class Path`](uitk/uitk/widgets/marking_menu/overlay.py#L38)** — The Path class represents a sequence of widget positions and cursor positions
  - `Path.is_empty(self) -> bool` *(property)* — Check if path has no entries.
  - `Path.intermediate_entries(self)` *(property)* — Entries between start and end (for cloning).
  - `Path.start_pos(self) -> QtCore.QPoint` *(property)* — Gets the starting position of the path.
  - `Path.widget_positions(self) -> dict` *(property)* — Gets the global position of the center of a specific widget in the path.
  - `Path.widget_position(self, target_widget)` — Gets the global position of the center of a specific widget in the path.
  - `Path.reset(self)` — Clears the path and appends the current cursor position as the new starting position.
  - `Path.clear(self)` — Clears the entire path.
  - `Path.clear_to_origin(self)` — Clears the path but retains the original starting position.
  - `Path.add(self, ui, widget)` — Adds a widget and its global position to the path.
  - `Path.remove(self, target_ui)` — Removes all references to the provided ui object from the path.
- **[`class Overlay(QtWidgets.QWidget)`](uitk/uitk/widgets/marking_menu/overlay.py#L173)** — Handles paint events as an overlay on top of an existing widget.
  - `Overlay.draw_tangent(self, start_point, end_point, ellipseSize=7)` — Draws a tangent line between two points with an ellipse at the start point.
  - `Overlay.init_region(self, ui, *args, **kwargs)` — Initializes a Region widget with the specified properties and adds it to the given UI's central wid…
  - `Overlay.start_gesture(self, global_pos: QtCore.QPoint) -> None` — Begin a gesture at the given global position.
  - `Overlay.clone_widgets_along_path(self, ui, return_func)` — Re-constructs the relevant widgets from the previous UI for the new UI, and positions them.
  - `Overlay.clear_paint_events(self)` — Clear paint events by disabling drawing and updating the overlay.
  - `Overlay.paintEvent(self, event)` — Handles the paint event for the overlay, drawing the tangent paths as needed.
  - `Overlay.mousePressEvent(self, event)` — Handle mouse press by starting gesture at the event position.
  - `Overlay.mouseReleaseEvent(self, event)` — Handle mouse release by restoring cursor and clearing painting.
  - `Overlay.mouseMoveEvent(self, event)`
  - `Overlay.hideEvent(self, event)` — Clears the path and restores the cursor when the overlay is hidden.

<a id="widgets--menu"></a>
### `widgets/menu.py`

- **[`class MenuConfig`](uitk/uitk/widgets/menu.py#L71)** — Configuration for Menu initialization.
  - `MenuConfig.for_context_menu(cls, parent: Optional[QtWidgets.QWidget] = None, **overrides) -> 'MenuConfig'` *(class)* — Create config for a context menu.
  - `MenuConfig.for_dropdown_menu(cls, parent: Optional[QtWidgets.QWidget] = None, **overrides) -> 'MenuConfig'` *(class)* — Create config for a dropdown menu.
  - `MenuConfig.for_popup_menu(cls, parent: Optional[QtWidgets.QWidget] = None, **overrides) -> 'MenuConfig'` *(class)* — Create config for a popup menu.
- **[`class ActionButtonManager`](uitk/uitk/widgets/menu.py#L158)** — Manages action buttons for Menu widgets.
  - `ActionButtonManager.container(self) -> QtWidgets.QWidget` *(property)* — Get or create the collapsible action button container.
  - `ActionButtonManager.create_button(self, button_id: str, config: _ActionButtonConfig) -> QtWidgets.QPushButton` — Create an action button with the given configuration.
  - `ActionButtonManager.add_button(self, button_id: str, config: _ActionButtonConfig, index: int = -1) -> QtWidgets.QPushButton` — Add an action button to the container.
  - `ActionButtonManager.add_widget(self, widget_id: str, widget: QtWidgets.QWidget, index: int = -1) -> QtWidgets.QWidget` — Add an arbitrary widget to the action container.
  - `ActionButtonManager.get_widget(self, widget_id: str) -> Optional[QtWidgets.QWidget]` — Get a managed widget by ID.
  - `ActionButtonManager.remove_widget(self, widget_id: str) -> bool` — Remove a managed widget entirely.
  - `ActionButtonManager.get_button(self, button_id: str) -> Optional[QtWidgets.QPushButton]` — Get an action button by ID.
  - `ActionButtonManager.show_button(self, button_id: str) -> bool` — Show an action button.
  - `ActionButtonManager.hide_button(self, button_id: str) -> bool` — Hide an action button.
  - `ActionButtonManager.remove_button(self, button_id: str) -> bool` — Remove an action button entirely.
  - `ActionButtonManager.has_visible_items(self) -> bool` — Check if any buttons or widgets are currently visible.
- **[`class MenuPositioner`](uitk/uitk/widgets/menu.py#L329)** — Encapsulates menu positioning and width matching logic.
  - `MenuPositioner.center_on_cursor(widget: QtWidgets.QWidget) -> None` *(static)* — Center menu on cursor position.
  - `MenuPositioner.position_at_coordinate(widget: QtWidgets.QWidget, position: Union[QtCore.QPoint, tuple, list]) -> None` *(static)* — Position menu at specific coordinates.
  - `MenuPositioner.position_relative_to_widget(menu: QtWidgets.QWidget, target_widget: QtWidgets.QWidget, position: str) -> None` *(static)* — Position menu relative to another widget.
  - `MenuPositioner.apply_width_matching(menu: QtWidgets.QWidget, anchor_widget: Optional[QtWidgets.QWidget], match_parent_width: bool, position: Union[str, QtCore.QPoint, tuple, list, None], logger: Optional[Any] = None) -> None` *(static)* — Apply width matching if conditions are met.
  - `MenuPositioner.position_and_match_width(menu: QtWidgets.QWidget, anchor_widget: Optional[QtWidgets.QWidget], position: Union[str, QtCore.QPoint, tuple, list, None], match_parent_width: bool, logger: Optional[Any] = None) -> None` *(static)* — Position menu and apply width matching in one operation.
- **[`class Menu(QtWidgets.QWidget, AttributesMixin, ptk.LoggingMixin)`](uitk/uitk/widgets/menu.py#L555)** — A custom Qt Widget that serves as a popup menu with additional features.
  - `Menu.create_context_menu(cls, parent: Optional[QtWidgets.QWidget] = None, **overrides)` *(class)* — Factory method: Create a standalone context menu with sensible defaults.
  - `Menu.create_dropdown_menu(cls, parent: Optional[QtWidgets.QWidget] = None, **overrides)` *(class)* — Factory method: Create a dropdown menu for option boxes.
  - `Menu.from_config(cls, config: MenuConfig)` *(class)* — Create a Menu from a MenuConfig object.
  - `Menu.run_modal(content_fn, parent=None, title='', buttons=None, size=None, min_size=None, center=True, **menu_kwargs)` *(static)* — Show a themed modal Menu popup, block until dismissed.
  - `Menu.trigger_button(self) -> Union[QtCore.Qt.MouseButton, tuple, None, bool]` *(property)* — Get the current trigger button(s).
  - `Menu.trigger_button(self, value: Union[QtCore.Qt.MouseButton, str, tuple, list, None]) -> None` — Set the trigger button(s).
  - `Menu.presets(self)` *(property)* — Lazy-initialized PresetManager namespace for saving/loading named presets.
  - `Menu.presets(self, _)` — No-op setter so the switchboard can harmlessly reassign.
  - `Menu.hide_on_leave(self) -> bool` *(property)* — Get whether menu auto-hides when mouse leaves.
  - `Menu.hide_on_leave(self, value: bool) -> None` — Set whether menu auto-hides when mouse leaves.
  - `Menu.enable_persistent_mode(self, hide_button_tooltip: str = 'Hide menu') -> None` — Keep the menu visible until the user explicitly hides it.
  - `Menu.disable_persistent_mode(self) -> None` — Restore default hide behaviour after persistent mode.
  - `Menu.is_persistent_mode(self) -> bool` *(property)* — Return True when persistent mode is active.
  - `Menu.setVisible(self, visible: bool) -> None` — Override to apply deferred popup setup before becoming visible.
  - `Menu.show(self) -> None` — Show the menu.
  - `Menu.show_as_popup(self, anchor_widget: Optional[QtWidgets.QWidget] = None, position: Union[str, QtCore.QPoint, tuple, list] = 'bottom') -> None` — Show this menu as a popup at the specified position.
  - `Menu.setCentralWidget(self, widget, overwrite=False)`
  - `Menu.centralWidget(self)` — Return the central widget.
  - `Menu.init_layout(self)` — Initialize the menu layout.
  - `Menu.add_defaults_button(self) -> bool` *(property)* — Whether the 'Restore Defaults' button is enabled.
  - `Menu.add_defaults_button(self, value: bool) -> None`
  - `Menu.add_presets(self) -> bool` *(property)* — Whether the presets combo is enabled.
  - `Menu.add_presets(self, value: bool) -> None`
  - `Menu.get_all_children(self)`
  - `Menu.is_pinned(self) -> bool` *(property)* — Check if the menu is pinned (should not auto-hide).
  - `Menu.contains_items(self) -> bool` *(property)* — Check if the QMenu contains any genuine items.
  - `Menu.title(self) -> str` — Get the menu's title text.
  - `Menu.setTitle(self, title='') -> None` — Set the menu's title to the given string.
  - `Menu.get_items(self, types=None)` — Get all items in the list, optionally filtered by type.
  - `Menu.get_item(self, identifier)` — Return a QAction or QWidgetAction by index or text.
  - `Menu.get_item_text(self, widget: QtWidgets.QWidget) -> Optional[str]` — Get the textual representation of a widget.
  - `Menu.get_item_data(self, widget)` — Get data associated with a widget in the list or its sublists.
  - `Menu.set_item_data(self, widget, data)` — Set data associated with a widget in the list or its sublists.
  - `Menu.remove_widget(self, widget)` — Remove a widget from the layout.
  - `Menu.clear(self) -> None` — Clear all items in the list.
  - `Menu.add(self, x: Union[str, QtWidgets.QWidget, type, dict, list, tuple, set, zip, map], data: Any = None, row: Optional[int] = None, col: int = 0, rowSpan: int = 1, colSpan: Optional[int] = None, **kwargs) -> Union[QtWidgets.QWidget, list]` — Add an item or multiple items to the list.
  - `Menu.get_padding(widget)` — Get the padding values around a widget.
  - `Menu.sizeHint(self)` — Return the recommended size for the widget.
  - `Menu.showEvent(self, event) -> None` — Handle show event with positioning (optimized for performance).
  - `Menu.hide(self, force: bool = False) -> bool` — Hide the menu, respecting the pinned state.
  - `Menu.hideEvent(self, event) -> None` — Handle hide event.
  - `Menu.eventFilter(self, widget, event)` — Handle events for the menu and its children.
  - `Menu.trigger_from_widget(self, widget: Optional[QtWidgets.QWidget] = None, *, button: QtCore.Qt.MouseButton = QtCore.Qt.LeftButton) -> None` — Toggle visibility using the same rules as the parent click event.

<a id="widgets--messageBox"></a>
### `widgets/messageBox.py`

- **[`class MessageBox(QtWidgets.QMessageBox, AttributesMixin)`](uitk/uitk/widgets/messageBox.py#L8)** — Displays a message box with HTML formatting for a set time before closing.
  - `MessageBox.setStandardButtons(self, *buttons)` — Set the standard buttons for the message box.
  - `MessageBox.move_(self, location) -> None`
  - `MessageBox.setText(self, string, fontColor='white', background=0.75, fontSize=5) -> None` — Set the text to be displayed with the specified alignment unless overridden by HTML.
  - `MessageBox.autoClose(self)`
  - `MessageBox.showEvent(self, event)`
  - `MessageBox.hideEvent(self, event)`
  - `MessageBox.exec_(self)`

<a id="widgets--mixins--attributes"></a>
### `widgets/mixins/attributes.py`

- **[`class AttributesMixin`](uitk/uitk/widgets/mixins/attributes.py#L7)** — A mixin class providing a comprehensive interface for setting attributes on Qt widgets.
  - `AttributesMixin.set_flags(self, **flags)` — Sets or unsets given window flags, safely ignoring unsupported cases.
  - `AttributesMixin.set_legal_attribute(self, obj, name, value, also_set_original=False)` — If the original name contains illegal characters, this method sets an attribute using
  - `AttributesMixin.set_attributes(self, *objects, **attributes)`

<a id="widgets--mixins--convert"></a>
### `widgets/mixins/convert.py`

- **[`class ConvertMixin`](uitk/uitk/widgets/mixins/convert.py#L8)** — Class providing utility methods to handle common conversions related to Qt objects.
  - `ConvertMixin.can_convert(value, q_object_type) -> bool` *(static)* — Check if a value can be converted to the specified QObject type (accepts class or string).
  - `ConvertMixin.to_qobject(value, q_object_type)` *(static)* — Convert a value to a QObject of the specified type (accepts class or string).
  - `ConvertMixin.to_qkey(key: Union[str, QtCore.Qt.Key]) -> Optional[QtCore.Qt.Key]` *(static)* — Convert a given key identifier to a Qt key constant.
  - `ConvertMixin.to_qmousebutton(button: Union[str, QtCore.Qt.MouseButton, tuple, list, None]) -> Union[QtCore.Qt.MouseButton, tuple, None, bool]` *(static)* — Convert button identifier(s) to Qt MouseButton constant(s).
  - `ConvertMixin.to_int(val, default=0) -> int` *(static)* — Safely convert a value (including Qt Enum/Flag) to an integer.

<a id="widgets--mixins--docking"></a>
### `widgets/mixins/docking.py`

- **[`class DockingOverlay(QWidget)`](uitk/uitk/widgets/mixins/docking.py#L14)**
  - `DockingOverlay.update(self)`
  - `DockingOverlay.paintEvent(self, event)`
- **[`class DockingWindow(QMainWindow)`](uitk/uitk/widgets/mixins/docking.py#L74)**
  - `DockingWindow.add_tool_window(self, tool_window, position)`
  - `DockingWindow.remove_tool_window(self, tool_window)`
  - `DockingWindow.get_docked_widgets(self)`
- **[`class CustomDockWidget(QDockWidget)`](uitk/uitk/widgets/mixins/docking.py#L98)**
  - `CustomDockWidget.handle_top_level_change(self, floating)`
  - `CustomDockWidget.eventFilter(self, widget, event)`
- **[`class DockingMixin(QObject)`](uitk/uitk/widgets/mixins/docking.py#L136)** — Enables window docking with visual overlay for dock position preview.
  - `DockingMixin.docking_enabled(self)` *(property)*
  - `DockingMixin.docking_enabled(self, value)`
  - `DockingMixin.dock_position(self)` *(property)*
  - `DockingMixin.dock_position(self, value)`
  - `DockingMixin.dock(self, target_window, position)`
  - `DockingMixin.dock_positions(self)` *(property)*
  - `DockingMixin.update_docking_position(self)`
  - `DockingMixin.eventFilter(self, widget, event)`

<a id="widgets--mixins--icon_manager"></a>
### `widgets/mixins/icon_manager.py`

- **[`class IconManager`](uitk/uitk/widgets/mixins/icon_manager.py#L10)** — Theme-aware SVG icon loader with caching and color customization.
  - `IconManager.set_default_color(cls, color: str)` *(class)* — Set the default icon color for icons created without explicit color.
  - `IconManager.register_icon_dir(cls, path)` *(class)* — Register an additional icon directory (searched first).
  - `IconManager.get(cls, name: str, size=(16, 16), color: str = None, use_theme: bool = True) -> QtGui.QIcon` *(class)* — Get an icon, optionally colorized.
  - `IconManager.fit_size(container_size, margin: int = 4, min_size: int = 8) -> int` *(static)* — Compute a square icon extent that fits inside ``container_size`` px.
  - `IconManager.fit_icon(cls, widget, name: str, container_size, margin: int = 4, min_size: int = 8, color: str = None, auto_theme: bool = True) -> int` *(class)* — Render *name* onto *widget* sized to fit a square container.
  - `IconManager.swap_icon(cls, widget, name: str, color: str = None, auto_theme: bool = True, fallback_size=(16, 16)) -> None` *(class)* — Replace the icon on *widget* without changing its display size.
  - `IconManager.set_icon(cls, widget, name: str, size=(16, 16), color: str = None, auto_theme: bool = True)` *(class)* — Set an icon on a widget.
  - `IconManager.update_widget_icons(cls, root_widget: QtWidgets.QWidget, color: str)` *(class)* — Update all registered icons under a widget tree with a new color.
  - `IconManager.clear_cache(cls)` *(class)* — Clear all cached icons and SVG content.
  - `IconManager.get_cache_stats(cls) -> dict` *(class)* — Get statistics about the icon cache.

<a id="widgets--mixins--menu_mixin"></a>
### `widgets/mixins/menu_mixin.py`

MenuMixin - provides automatic Menu integration for widgets.

- **[`class MenuMixin`](uitk/uitk/widgets/mixins/menu_mixin.py#L146)** — Simple drop-in mixin that provides automatic Menu integration.
  - `MenuMixin.configure_menu(self, **config) -> None` — Configure menu properties without triggering creation.
  - `MenuMixin.has_menu(self) -> bool` *(property)* — Check if a menu has been created without triggering creation.

<a id="widgets--mixins--option_box_mixin"></a>
### `widgets/mixins/option_box_mixin.py`

OptionBoxMixin - simple drop-in mixin for OptionBox functionality.

- **[`class OptionBoxMixin`](uitk/uitk/widgets/mixins/option_box_mixin.py#L33)** — Mixin that provides automatic OptionBox integration for widgets.
  - `OptionBoxMixin.option_box(self) -> Optional['OptionBoxManager']` *(property)*
  - `OptionBoxMixin.container(self)` *(property)* — Return the OptionBox container for this widget if available.
  - `OptionBoxMixin.options(self) -> 'OptionBoxMixin._OptionsWrapper'` *(property)*

<a id="widgets--mixins--preset_manager"></a>
### `widgets/mixins/preset_manager.py`

- [`QStandardPaths_writableLocation() -> str`](uitk/uitk/widgets/mixins/preset_manager.py#L716) — Return Qt's per-application writable config directory.
- [`QStandardPaths_genericConfigLocation() -> str`](uitk/uitk/widgets/mixins/preset_manager.py#L733) — Return Qt's host-independent writable config directory.
- [`get_presets_root() -> Path`](uitk/uitk/widgets/mixins/preset_manager.py#L861) — Root directory under which every relative ``preset_dir`` is resolved.
- **[`class PresetManager(ptk.LoggingMixin)`](uitk/uitk/widgets/mixins/preset_manager.py#L17)** — Manages named presets for widget state, stored as external JSON files.
  - `PresetManager.from_widgets(cls, preset_dir, widgets: List[QtWidgets.QWidget]) -> 'PresetManager'` *(class)* — Create a standalone PresetManager for an explicit list of widgets.
  - `PresetManager.setup(self, preset_dir=None, widgets: Optional[List[QtWidgets.QWidget]] = None, on_loaded=None, metadata_provider: Optional[Callable[[], dict]] = None, on_metadata_loaded: Optional[Callable[[dict], None]] = None) -> 'PresetManager'` — Configure and optionally auto-wire a preset combo.
  - `PresetManager.preset_dir(self) -> Path` *(property)* — The directory where preset files are stored.
  - `PresetManager.preset_dir(self, value) -> None` — Set the preset directory (accepts str, Path, or None for auto-derive).
  - `PresetManager.on_change(self, callback) -> None` — Register a callback invoked when presets are modified.
  - `PresetManager.save(self, name: str, scope: Optional[QtWidgets.QWidget] = None) -> Path` — Save the current widget values as a named preset.
  - `PresetManager.load(self, name: str, scope: Optional[QtWidgets.QWidget] = None, block_signals: bool = True) -> int` — Load a named preset and apply its values to the matching widgets.
  - `PresetManager.list(self) -> List[str]` — Return a sorted list of available preset names.
  - `PresetManager.delete(self, name: str) -> bool` — Delete a named preset file.
  - `PresetManager.rename(self, old_name: str, new_name: str) -> bool` — Rename an existing preset.
  - `PresetManager.exists(self, name: str) -> bool` — Check whether a named preset exists on disk.
  - `PresetManager.wire_combo(self, combo, on_loaded=None) -> None` — Wire a ``WidgetComboBox`` as a fully-functional preset selector.

<a id="widgets--mixins--settings_manager"></a>
### `widgets/mixins/settings_manager.py`

- **[`class SettingsManager`](uitk/uitk/widgets/mixins/settings_manager.py#L166)** — Manages persistent storage and retrieval of settings via QSettings.
  - `SettingsManager.branch(self, name: str) -> 'SettingsManager'` — Create a new SettingsManager instance targeted at a sub-namespace.
  - `SettingsManager.set_defaults(self, defaults: dict) -> None` — Apply default values for a set of keys if they are not already set.
  - `SettingsManager.value(self, key: str, default: Any = None) -> Any`
  - `SettingsManager.setValue(self, key: str, value: Any) -> None`
  - `SettingsManager.on_change(self, key: str, callback: Callable[[Any], None]) -> None` — Register a callback to be invoked when a key's value changes.
  - `SettingsManager.keys(self) -> list` — Return all keys in the current namespace.
  - `SettingsManager.setByteArray(self, key: str, value: QtCore.QByteArray) -> None` — Set a QByteArray value directly without JSON serialization.
  - `SettingsManager.getByteArray(self, key: str, default: QtCore.QByteArray = None) -> QtCore.QByteArray` — Get a QByteArray value directly.
  - `SettingsManager.clear(self, key: Optional[str] = None) -> None` — Clears a specific key, or all keys in the current namespace.
  - `SettingsManager.sync(self) -> None`

<a id="widgets--mixins--shortcuts"></a>
### `widgets/mixins/shortcuts.py`

Generic keyboard-shortcut primitives, usable by any Qt widget.

- [`context_to_scope_name(context: QtCore.Qt.ShortcutContext) -> str`](uitk/uitk/widgets/mixins/shortcuts.py#L34) — Convert a Qt.ShortcutContext to its persistence string.
- [`scope_name_to_context(name: str) -> QtCore.Qt.ShortcutContext`](uitk/uitk/widgets/mixins/shortcuts.py#L39) — Convert a persisted scope string to a Qt.ShortcutContext.
- [`create_standard_shortcuts_config() -> List[Tuple[QtGui.QKeySequence, str, str]]`](uitk/uitk/widgets/mixins/shortcuts.py#L642) — Create a standard set of shortcut configurations
- [`apply_standard_shortcuts(widget, shortcuts_to_apply: Optional[List[str]] = None)`](uitk/uitk/widgets/mixins/shortcuts.py#L665) — Apply standard shortcuts to a widget that has corresponding methods
- **[`class GlobalShortcut(QtCore.QObject)`](uitk/uitk/widgets/mixins/shortcuts.py#L44)** — A robust global shortcut handler that detects both press and release events.
  - `GlobalShortcut.eventFilter(self, obj, event)` — Monitor global events for the specific key release.
  - `GlobalShortcut.setEnabled(self, enabled: bool)`
  - `GlobalShortcut.setKey(self, key_sequence: Union[str, QtGui.QKeySequence])`
  - `GlobalShortcut.setContext(self, context: QtCore.Qt.ShortcutContext)` — Live-update the underlying QShortcut's context.
- **[`class ShortcutManager`](uitk/uitk/widgets/mixins/shortcuts.py#L203)** — Centralized shortcut management with clear separation of concerns
  - `ShortcutManager.add_shortcut(self, key_sequence: Union[str, QtGui.QKeySequence], action: Callable, description: str = '', context: QtCore.Qt.ShortcutContext = QtCore.Qt.WidgetShortcut) -> QtWidgets.QShortcut` — Add a keyboard shortcut with optional description and context
  - `ShortcutManager.add_shortcuts_batch(self, shortcuts_config: List[Tuple[Union[str, QtGui.QKeySequence], Callable, str]]) -> List[QtWidgets.QShortcut]` — Add multiple shortcuts from a configuration list
  - `ShortcutManager.add_global_shortcut(self, key_sequence: Union[str, QtGui.QKeySequence], on_press: Callable = None, on_release: Callable = None, description: str = '') -> GlobalShortcut` — Add a global shortcut (robust press/release detection).
  - `ShortcutManager.add_info_entry(self, key_label: str, description: str) -> None` — Register a display-only entry (e.g.
  - `ShortcutManager.remove_shortcut(self, key_sequence: Union[str, QtGui.QKeySequence]) -> bool` — Remove a specific shortcut
  - `ShortcutManager.clear_all(self) -> None` — Remove all shortcuts
  - `ShortcutManager.on_change(self, callback: Callable) -> None` — Register a callback invoked after any shortcut is rebound.
  - `ShortcutManager.rebind_shortcut(self, old_key: str, new_key: str) -> bool` — Change the key sequence for an existing shortcut.
  - `ShortcutManager.show_editor(self, parent=None, title: str = 'Shortcuts') -> None` — Open an editor window for viewing and editing registered shortcuts.
  - `ShortcutManager.get_shortcuts_info(self) -> Dict[str, str]` — Get information about all registered shortcuts
  - `ShortcutManager.has_shortcut(self, key_sequence: Union[str, QtGui.QKeySequence]) -> bool` — Check if a shortcut is registered
  - `ShortcutManager.get_shortcut(self, key_sequence: Union[str, QtGui.QKeySequence]) -> Optional[QtWidgets.QShortcut]` — Get a specific shortcut object
- **[`class ShortcutMixin`](uitk/uitk/widgets/mixins/shortcuts.py#L468)** — Mixin class that provides easy shortcut management for any Qt widget
  - `ShortcutMixin.shortcut_manager(self) -> ShortcutManager` *(property)* — Lazy initialization of shortcut manager
  - `ShortcutMixin.add_shortcut(self, key_sequence: Union[str, QtGui.QKeySequence], action: Callable, description: str = '', context: QtCore.Qt.ShortcutContext = QtCore.Qt.WidgetShortcut) -> QtWidgets.QShortcut` — Add a keyboard shortcut
  - `ShortcutMixin.add_shortcuts_from_config(self, shortcuts_config: List[Tuple[Union[str, QtGui.QKeySequence], Callable, str]]) -> List[QtWidgets.QShortcut]` — Add multiple shortcuts from configuration
  - `ShortcutMixin.remove_shortcut(self, key_sequence: Union[str, QtGui.QKeySequence]) -> bool` — Remove a shortcut
  - `ShortcutMixin.clear_all_shortcuts(self) -> None` — Clear all shortcuts
  - `ShortcutMixin.get_shortcuts_info(self) -> Dict[str, str]` — Get all shortcuts information
  - `ShortcutMixin.add_shortcuts_to_context_menu(self, menu: QtWidgets.QMenu, submenu_title: str = 'Keyboard Shortcuts') -> QtWidgets.QMenu` — Add shortcuts information to a context menu
  - `ShortcutMixin.add_menu_actions_with_shortcuts(self, menu: Optional[QtWidgets.QMenu] = None, actions_config: Optional[List[Tuple[str, Callable, Optional[Union[str, QtGui.QKeySequence]]]]] = None, auto_match_shortcuts: bool = True) -> QtWidgets.QMenu` — Add menu actions with inline shortcut display
  - `ShortcutMixin.create_context_menu(self, actions_config, **kwargs)` — Convenience method to create a new context menu with shortcuts
  - `ShortcutMixin.add_actions_to_menu(self, menu, actions_config, **kwargs)` — Convenience method to add actions to an existing menu

<a id="widgets--mixins--size_grip"></a>
### `widgets/mixins/size_grip.py`

Reusable helper for attaching a QSizeGrip to arbitrary widgets.

- **[`class CornerSizeGrip(QtWidgets.QSizeGrip)`](uitk/uitk/widgets/mixins/size_grip.py#L9)** — Custom QSizeGrip with a simple diagonal corner indicator.
  - `CornerSizeGrip.enterEvent(self, event: QtCore.QEvent) -> None`
  - `CornerSizeGrip.leaveEvent(self, event: QtCore.QEvent) -> None`
  - `CornerSizeGrip.getBaseColor(self) -> QtGui.QColor`
  - `CornerSizeGrip.setBaseColor(self, value) -> None`
  - `CornerSizeGrip.getHoverColor(self) -> QtGui.QColor`
  - `CornerSizeGrip.setHoverColor(self, value) -> None`
  - `CornerSizeGrip.paintEvent(self, event: QtGui.QPaintEvent) -> None`
- **[`class SizeGripMixin`](uitk/uitk/widgets/mixins/size_grip.py#L98)** — Mixin that provides a consistent QSizeGrip attachment helper.
  - `SizeGripMixin.create_size_grip(self, container: Optional[QtWidgets.QWidget] = None, layout: Optional[QtWidgets.QLayout] = None, *, alignment: Optional[QtCore.Qt.Alignment] = None) -> Optional[QtWidgets.QSizeGrip]` — Create or reuse a size grip and ensure it is inserted in *layout*.

<a id="widgets--mixins--state_manager"></a>
### `widgets/mixins/state_manager.py`

- **[`class StateManager(ptk.LoggingMixin)`](uitk/uitk/widgets/mixins/state_manager.py#L11)** — Manages widget state persistence using QSettings.
  - `StateManager.apply(self, widget: QtWidgets.QWidget, value: Any) -> None` — Apply the given value to the widget using ValueManager.
  - `StateManager.suppress_save(self)` — Context manager that temporarily suppresses QSettings writes.
  - `StateManager.save(self, widget: QtWidgets.QWidget, value: Any = None) -> None` — Save the current value of the widget to QSettings.
  - `StateManager.load(self, widget: QtWidgets.QWidget) -> None` — Load the saved value from QSettings and apply it to the widget.
  - `StateManager.reset_all(self, block_signals: bool = False) -> None` — Reset all widgets with stored defaults to their original values.
  - `StateManager.reset(self, widget: QtWidgets.QWidget) -> None` — Reset a widget to its default value.
  - `StateManager.clear(self, widget: QtWidgets.QWidget) -> None` — Removes the stored state for the widget from QSettings.
  - `StateManager.has_default(self, widget: QtWidgets.QWidget) -> bool` — Check if a widget has a stored default value.
  - `StateManager.capture_default(self, widget: QtWidgets.QWidget) -> None` — Capture the current widget value as its default.
  - `StateManager.set_default(self, widget: QtWidgets.QWidget, value: Any) -> None` — Explicitly set a widget's default value.
  - `StateManager.save_custom(self, key: str, value: Any) -> None` — Persist an arbitrary key/value pair through QSettings.
  - `StateManager.load_custom(self, key: str, default: Any = None) -> Any` — Retrieve a previously stored custom key/value pair.
  - `StateManager.clear_custom(self, key: str) -> None` — Remove a single custom key from storage.

<a id="widgets--mixins--style_sheet"></a>
### `widgets/mixins/style_sheet.py`

- **[`class StyleSheet(QtCore.QObject, ptk.LoggingMixin)`](uitk/uitk/widgets/mixins/style_sheet.py#L14)** — Theme and stylesheet manager with light/dark theme support.
  - `StyleSheet.get_icon_color(cls, widget: QtWidgets.QWidget = None) -> str` *(class)* — Get the icon color for a widget based on its current theme.
  - `StyleSheet.set_theme(cls, theme: str, widget: QtWidgets.QWidget = None)` *(class)* — Set a new theme for a specific widget or all registered widgets.
  - `StyleSheet.reload(cls, widget: QtWidgets.QWidget = None)` *(class)* — Reload the style for a specific widget or all registered widgets.
  - `StyleSheet.clear_caches(cls) -> None` *(class)* — Drop QSS + parsed-template caches.
  - `StyleSheet.set_variable(cls, name: str, value: Union[str, QtGui.QColor, None], theme: str = 'light', widget: QtWidgets.QWidget = None)` *(class)* — Set a theme variable override.
  - `StyleSheet.get_variable(cls, name: str, theme: str = 'light', widget: QtWidgets.QWidget = None) -> str` *(class)* — Get a theme variable value, resolving overrides.
  - `StyleSheet.get_variables(cls, theme: str = 'light') -> list[str]` *(class)* — Get list of available theme variables.
  - `StyleSheet.export_overrides(cls) -> dict` *(class)* — Export the current global overrides as a plain dict.
  - `StyleSheet.import_overrides(cls, data: dict) -> None` *(class)* — Bulk-replace global overrides from a dict and reload once.
  - `StyleSheet.reset_overrides(cls, widget: QtWidgets.QWidget = None)` *(class)* — Clear overrides.

<a id="widgets--mixins--text"></a>
### `widgets/mixins/text.py`

- **[`class TextTruncation`](uitk/uitk/widgets/mixins/text.py#L6)** — Mixin providing reusable text truncation functionality for UI widgets.
  - `TextTruncation.calculate_text_truncation(self, text, container_width=None, reserved_width=0, min_text_width=100, elide_mode=QtCore.Qt.ElideMiddle, font=None, custom_suffix='...')` — Calculate truncated text that fits within available width using Qt font metrics.
  - `TextTruncation.calculate_character_truncation(self, text, max_chars, elide_mode=QtCore.Qt.ElideMiddle, suffix='...')` — Truncate text by character count (not pixel-based).
  - `TextTruncation.calculate_word_truncation(self, text, max_chars, elide_mode=QtCore.Qt.ElideMiddle, suffix='...', word_boundary=True)` — Truncate text respecting word boundaries.
  - `TextTruncation.calculate_path_truncation(self, path, max_chars, preserve_filename=True, preserve_extension=True, suffix='...')` — Truncate file/directory paths intelligently.
  - `TextTruncation.apply_text_truncation(self, widget, text, container_width=None, reserved_width=0, tooltip=None, truncation_type='pixel')` — Apply text truncation to an existing widget.
  - `TextTruncation.create_truncated_button(self, text, container_width=None, reserved_width=0, tooltip=None, truncation_type='pixel', **button_kwargs)` — Create a QPushButton with properly truncated text.
  - `TextTruncation.create_truncated_label(self, text, container_width=None, reserved_width=0, tooltip=None, truncation_type='pixel', **label_kwargs)` — Create a QLabel with properly truncated text.
  - `TextTruncation.update_widget_text_truncation(self, widget, text, container_width=None, reserved_width=0, tooltip=None, truncation_type='pixel')` — Update an existing widget's text with proper truncation.
- **[`class RichText`](uitk/uitk/widgets/mixins/text.py#L450)** — Rich text support for widgets.
  - `RichText.richTextLabelDict(self)` *(property)* — Returns a list containing any rich text labels that have been created.
  - `RichText.richTextSizeHintDict(self)` *(property)* — Returns a list containing the sizeHint any rich text labels that have been created.
  - `RichText.richTextSizeHint(self, index=0)` — The richTextSizeHint is the sizeHint of the actual widget if it were containing the text.
  - `RichText.set_rich_text_style(self, index=0, textColor='white')` — Set the stylesheet for a QLabel.
  - `RichText.getRichTextLabel(self, index=0)`
  - `RichText.richText(self, index=None)` — Returns:
  - `RichText.setRichText(self, text, index=0)` — If the text string contains rich text formatting:
  - `RichText.setAlignment(self, alignment='AlignLeft', index=0)` — Override setAlignment to accept string alignment arguments as well as QtCore.Qt.AlignmentFlags.
- **[`class TextOverlay`](uitk/uitk/widgets/mixins/text.py#L648)**
  - `TextOverlay.textOverlayLabel(self)` *(property)* — Return a QLabel inside a QHBoxLayout.
  - `TextOverlay.setTextOverlay(self, text, color=None, alignment=None)` — If the text string contains rich text formatting:
  - `TextOverlay.setTextOverlayAlignment(self, alignment='AlignLeft')` — Override setAlignment to accept string alignment arguments as well as QtCore.Qt.AlignmentFlags.
  - `TextOverlay.setTextOverlayColor(self, color)` — Set the stylesheet for a QLabel.

<a id="widgets--mixins--tooltip_mixin"></a>
### `widgets/mixins/tooltip_mixin.py`

- [`fmt(title: str = None, body: str = None, bullets: list = None, steps: list = None, rows: list = None, sections: list = None) -> str`](uitk/uitk/widgets/mixins/tooltip_mixin.py#L80) — Build a rich-text HTML tooltip string.
- **[`class TooltipProxy`](uitk/uitk/widgets/mixins/tooltip_mixin.py#L36)** — Per-widget tooltip namespace stamped on each registered MainWindow widget.
  - `TooltipProxy.bind(self, provider) -> None` — Register a callable() -> str called lazily on QEvent.ToolTip hover.
- **[`class TooltipMixin`](uitk/uitk/widgets/mixins/tooltip_mixin.py#L163)** — Mixin for MainWindow — stamps ``widget.tooltip`` on every registered widget.

<a id="widgets--mixins--value_manager"></a>
### `widgets/mixins/value_manager.py`

- **[`class ValueManager`](uitk/uitk/widgets/mixins/value_manager.py#L7)** — Flexible value getting/setting for most Qt widgets.
  - `ValueManager.get_value(widget)` *(static)* — Get the current value from a widget.
  - `ValueManager.set_value(widget, value, block_signals=False)` *(static)* — Set a value on a widget.
  - `ValueManager.get_widget_type_info(widget)` *(static)* — Get information about widget type for display purposes.
  - `ValueManager.is_supported_widget(widget)` *(static)* — Check if a widget type is supported for value operations.
  - `ValueManager.get_value_by_signal(widget, signal_name)` *(static)* — Get widget value based on its primary signal type.
  - `ValueManager.set_value_by_signal(widget, value, signal_name, block_signals=False)` *(static)* — Set widget value based on its primary signal type.

<a id="widgets--optionBox--_optionBox"></a>
### `widgets/optionBox/_optionBox.py`

OptionBox - Plugin-based container for wrapping widgets with action buttons.

- **[`class OptionBoxContainer(QtWidgets.QWidget)`](uitk/uitk/widgets/optionBox/_optionBox.py#L8)** — Container widget that wraps a widget with option buttons.
  - `OptionBoxContainer.changeEvent(self, event)`
  - `OptionBoxContainer.eventFilter(self, obj, event)` — Watch the wrapped widget for enabled-state changes.
- **[`class OptionBox`](uitk/uitk/widgets/optionBox/_optionBox.py#L57)** — Plugin-based option manager that wraps widgets with action buttons.
  - `OptionBox.add_option(self, option)` — Add an option plugin instance.
  - `OptionBox.remove_option(self, option)` — Remove an option plugin instance.
  - `OptionBox.get_options(self)` — Get all registered option plugins.
  - `OptionBox.show_clear(self)` *(property)* — Get clear button state.
  - `OptionBox.show_clear(self, value)` — Set clear button visibility.
  - `OptionBox.set_clear_button_visible(self, visible=True)` — Enable or disable the clear button.
  - `OptionBox.wrap(self, wrapped_widget: QtWidgets.QWidget, frameless=False)` — Wrap target widget with option buttons.

<a id="widgets--optionBox--options--_options"></a>
### `widgets/optionBox/options/_options.py`

- **[`class QObjectABCMeta(type(QtCore.QObject), ABCMeta)`](uitk/uitk/widgets/optionBox/options/_options.py#L8)**
- **[`class BaseOption(QtCore.QObject, ABC)`](uitk/uitk/widgets/optionBox/options/_options.py#L12)** — Base class for all option plugins.
  - `BaseOption.widget(self)` *(property)* — Get the widget for this option.
  - `BaseOption.create_widget(self)` — Create and return the widget for this option.
  - `BaseOption.setup_widget(self)` — Setup the widget after creation.
  - `BaseOption.on_wrap(self, option_box, container)` — Called when the option is added to a wrapped widget.
  - `BaseOption.set_wrapped_widget(self, widget)` — Set or update the wrapped widget.
- **[`class ButtonOption(BaseOption)`](uitk/uitk/widgets/optionBox/options/_options.py#L95)** — Base class for button-based options.
  - `ButtonOption.create_widget(self)` — Create a QPushButton widget.
  - `ButtonOption.setup_widget(self)` — Setup button connections.
  - `ButtonOption.block_next_click(self)` — Block the next click event (used when popup closes to prevent immediate reopen).
  - `ButtonOption.set_checked(self, checked)` — Set the checked state of the button.

<a id="widgets--optionBox--options--_persistence"></a>
### `widgets/optionBox/options/_persistence.py`

Shared persistence wiring for OptionBox plugins.

- **[`class PersistedOption`](uitk/uitk/widgets/optionBox/options/_persistence.py#L15)** — Mixin that adds ``settings_key`` resolution + lazy SettingsManager.

<a id="widgets--optionBox--options--action"></a>
### `widgets/optionBox/options/action.py`

Action option for OptionBox - provides customizable action buttons.

- **[`class ActionOption(ButtonOption)`](uitk/uitk/widgets/optionBox/options/action.py#L9)** — A customizable action button option.
  - `ActionOption.create_widget(self)` — Create the action button widget.
  - `ActionOption.set_action_handler(self, handler)` — Set or update the action handler.
  - `ActionOption.current_state(self)` *(property)* — The current state index (0-based).
  - `ActionOption.current_state(self, index)`
  - `ActionOption.set_states(self, states)` — Set multiple cycling states.
- **[`class MenuOption(ActionOption)`](uitk/uitk/widgets/optionBox/options/action.py#L234)** — A menu action option specifically for showing menus.
  - `MenuOption.set_menu(self, menu)` — Set or update the menu.
  - `MenuOption.set_wrapped_widget(self, widget)` — Update wrapped widget and reparent menu if needed.

<a id="widgets--optionBox--options--browse"></a>
### `widgets/optionBox/options/browse.py`

Browse option for OptionBox - provides file/folder browsing buttons.

- **[`class BrowseOption(ButtonOption)`](uitk/uitk/widgets/optionBox/options/browse.py#L9)** — A file/folder browse button option.
  - `BrowseOption.file_types(self)` *(property)*
  - `BrowseOption.file_types(self, value)`
  - `BrowseOption.start_dir(self)` *(property)*
  - `BrowseOption.start_dir(self, value)` — Set start directory.
  - `BrowseOption.create_widget(self)` — Create the browse button widget.
  - `BrowseOption.browse(self)` — Open the appropriate file dialog and apply the result.

<a id="widgets--optionBox--options--clear"></a>
### `widgets/optionBox/options/clear.py`

Clear option for OptionBox - provides a clear button for text widgets.

- **[`class ClearOption(ButtonOption)`](uitk/uitk/widgets/optionBox/options/clear.py#L9)** — A clear button option that can clear text from input widgets.
  - `ClearOption.create_widget(self)` — Create the clear button widget.
  - `ClearOption.setup_widget(self)` — Setup button connections and show event handling.
  - `ClearOption.eventFilter(self, obj, event)` — Filter show events to update visibility after state restoration.
  - `ClearOption.set_wrapped_widget(self, widget)` — Set the wrapped widget and connect text change signals.
- **[`class ClearButton(QtWidgets.QPushButton)`](uitk/uitk/widgets/optionBox/options/clear.py#L143)** — A standalone clear button (legacy compatibility).

<a id="widgets--optionBox--options--option_menu"></a>
### `widgets/optionBox/options/option_menu.py`

Option Menu - A dropdown menu option for OptionBox.

- **[`class OptionMenuOption(ButtonOption, ptk.LoggingMixin)`](uitk/uitk/widgets/optionBox/options/option_menu.py#L14)** — A dropdown menu option that displays a list of choices.
  - `OptionMenuOption.create_widget(self)` — Create the menu button widget.
  - `OptionMenuOption.setup_widget(self)` — Setup the widget after creation.
  - `OptionMenuOption.set_wrapped_widget(self, widget)` — Update wrapped widget and reparent menu if needed.
  - `OptionMenuOption.menu(self)` *(property)* — Get the underlying Menu instance.
- **[`class ContextMenuOption(OptionMenuOption)`](uitk/uitk/widgets/optionBox/options/option_menu.py#L122)** — A context menu option that shows a menu based on wrapped widget state.

<a id="widgets--optionBox--options--pin_values"></a>
### `widgets/optionBox/options/pin_values.py`

Pin Values option for OptionBox - allows pinning/saving widget values.

- **[`class PinnedValueEntry`](uitk/uitk/widgets/optionBox/options/pin_values.py#L16)** — Represents a pinned value with an optional alias.
  - `PinnedValueEntry.display_text(self)` *(property)* — Get the text to display (alias if set, otherwise value).
- **[`class PinnedValuesPopup(QtCore.QObject)`](uitk/uitk/widgets/optionBox/options/pin_values.py#L37)** — A popup that displays pinned values using the Menu widget.
  - `PinnedValuesPopup.menu(self)` *(property)* — Get the underlying Menu widget.
  - `PinnedValuesPopup.eventFilter(self, watched, event)` — Close popup when any parent widget is hidden or a window-ancestor moves.
  - `PinnedValuesPopup.connect_signals(self, on_value_pinned=None, on_value_unpinned=None, on_value_selected=None, on_alias_changed=None)` — Connect signal handlers.
  - `PinnedValuesPopup.clear(self)` — Clear all items from the popup.
  - `PinnedValuesPopup.show(self)` — Show the popup.
  - `PinnedValuesPopup.close(self)` — Close the popup and clean up event filters.
  - `PinnedValuesPopup.move(self, pos)` — Move the popup to a position.
  - `PinnedValuesPopup.adjustSize(self)` — Adjust the popup size.
  - `PinnedValuesPopup.width(self)` — Get popup width.
  - `PinnedValuesPopup.add_current_value(self, value, is_pinned=False)` — Add the current value row.
  - `PinnedValuesPopup.add_separator(self)` — Add a separator line.
  - `PinnedValuesPopup.add_pinned_value(self, entry)` — Add a pinned value row.
  - `PinnedValuesPopup.add_empty_message(self)` — Add a message when there are no pinned values.
- **[`class PinValuesOption(ButtonOption)`](uitk/uitk/widgets/optionBox/options/pin_values.py#L347)** — A pin button option that manages pinned widget values.
  - `PinValuesOption.create_widget(self)` — Create the pin button widget.
  - `PinValuesOption.pinned_values(self)` *(property)* — Get the list of pinned values (raw values, not entries).
  - `PinValuesOption.pinned_entries(self)` *(property)* — Get the list of PinnedValueEntry objects.
  - `PinValuesOption.has_pinned_values(self)` *(property)* — Check if there are any pinned values.
  - `PinValuesOption.clear_pinned_values(self)` — Clear all pinned values.
  - `PinValuesOption.add_pinned_value(self, value, alias=None)` — Programmatically add a pinned value.

<a id="widgets--optionBox--options--recent_values"></a>
### `widgets/optionBox/options/recent_values.py`

Recent Values option for OptionBox — shows a selectable history list.

- **[`class RecentValuesPopup(QtCore.QObject)`](uitk/uitk/widgets/optionBox/options/recent_values.py#L64)** — Popup that displays recent values using the Menu widget.
  - `RecentValuesPopup.menu(self)` *(property)* — Get the underlying Menu widget.
  - `RecentValuesPopup.eventFilter(self, watched, event)` — Close popup when any parent widget is hidden or a window-ancestor moves.
  - `RecentValuesPopup.connect_signals(self, on_value_selected=None, on_value_removed=None)` — Connect signal handlers.
  - `RecentValuesPopup.clear(self)`
  - `RecentValuesPopup.show(self)`
  - `RecentValuesPopup.close(self)`
  - `RecentValuesPopup.move(self, pos)`
  - `RecentValuesPopup.adjustSize(self)`
  - `RecentValuesPopup.width(self)`
  - `RecentValuesPopup.add_recent_value(self, value, is_current=False, display_text=None)` — Add a recent-value row.
  - `RecentValuesPopup.add_separator(self)`
  - `RecentValuesPopup.add_empty_message(self)`
- **[`class RecentValuesOption(ButtonOption)`](uitk/uitk/widgets/optionBox/options/recent_values.py#L241)** — A history button that manages recent widget values.
  - `RecentValuesOption.create_widget(self)`
  - `RecentValuesOption.record(self, value=None)` — Record a value into the recent list.
  - `RecentValuesOption.add_recent_value(self, value)` — Programmatically seed a recent value (appends if not duplicate).
  - `RecentValuesOption.set_wrapped_widget(self, widget)` — Set or update the wrapped widget, re-installing auto-record if enabled.
  - `RecentValuesOption.recent_values(self)` *(property)* — Return a copy of the recent values list (most-recent first).
  - `RecentValuesOption.clear_recent_values(self)` — Clear all recent values.

<a id="widgets--optionBox--options--toggle"></a>
### `widgets/optionBox/options/toggle.py`

Toggle option for OptionBox — a persisted binary on/off button.

- **[`class ToggleOption(PersistedOption, ButtonOption)`](uitk/uitk/widgets/optionBox/options/toggle.py#L37)** — Persisted binary toggle button.
  - `ToggleOption.is_on(self) -> bool` *(property)* — Current state.
  - `ToggleOption.set_on(self, value: bool, *, emit: bool = True) -> None` — Programmatically set the toggle state.
  - `ToggleOption.setup_widget(self)`

<a id="widgets--optionBox--utils"></a>
### `widgets/optionBox/utils.py`

Utilities and helper functions for OptionBox.

- [`add_option_box(widget, show_clear=False, options=None, **kwargs)`](uitk/uitk/widgets/optionBox/utils.py#L950) — Add an option box to any widget with one function call.
- [`add_clear_option(widget, **kwargs)`](uitk/uitk/widgets/optionBox/utils.py#L973) — Add just a clear button to a text widget.
- [`add_menu_option(widget, menu, **kwargs)`](uitk/uitk/widgets/optionBox/utils.py#L986) — Add a menu option to any widget.
- [`patch_widget_class(widget_class)`](uitk/uitk/widgets/optionBox/utils.py#L1005) — Add option_box attribute to a widget class.
- [`patch_common_widgets()`](uitk/uitk/widgets/optionBox/utils.py#L1020) — Patch common Qt widgets with option box support.
- **[`class OptionBoxManager(ptk.LoggingMixin)`](uitk/uitk/widgets/optionBox/utils.py#L10)** — Elegant manager for option box functionality accessible as widget.option_box
  - `OptionBoxManager.clear_option(self)` *(property)* — Get/set clear option state
  - `OptionBoxManager.clear_option(self, enabled)` — Enable/disable clear option
  - `OptionBoxManager.option_order(self)` *(property)* — Get/set option ordering: ['clear', 'action'] or ['action', 'clear']
  - `OptionBoxManager.option_order(self, order)` — Set option ordering
  - `OptionBoxManager.pin(self, settings_key: Optional[str] = None, *, double_click_to_edit: bool = False, single_click_restore: bool = False)` — Enable pin values option (fluent interface).
  - `OptionBoxManager.recent(self, settings_key: Optional[str] = None, *, max_recent: int = 10, **kwargs)` — Enable recent values option (fluent interface).
  - `OptionBoxManager.set_action(self, callback=None, icon='option_box', tooltip='Options', text=None, replace=True, states=None, settings_key=None)` — Set the action handler (fluent interface).
  - `OptionBoxManager.add_action(self, callback=None, icon='option_box', tooltip='Options', text=None, states=None, settings_key=None)` — Add an action button without replacing existing ones.
  - `OptionBoxManager.set_toggle(self, *, icon: str = 'filter', icon_off: Optional[str] = None, tooltip_on: str = 'Enabled. Click to disable.', tooltip_off: str = 'Disabled. Click to enable.', initial: bool = True, disabled_color: Optional[str] = None, gated_widgets=(), settings_key=None, replace: bool = True, on_toggled=None)` — Add a persisted binary toggle button (fluent interface).
  - `OptionBoxManager.add_toggle(self, **kwargs)` — Add a toggle without replacing existing ones.
  - `OptionBoxManager.browse(self, file_types=None, title='Browse', start_dir=None, mode='file', icon='folder', tooltip='Browse...', callback=None)` — Enable file/folder browse button (fluent interface).
  - `OptionBoxManager.enable_clear(self)` — Enable clear option (fluent interface)
  - `OptionBoxManager.disable_clear(self)` — Disable clear option (fluent interface)
  - `OptionBoxManager.clear_options(self)` — Clear all added options.
  - `OptionBoxManager.find_option(self, option_type)` — Find the first option of the given type.
  - `OptionBoxManager.set_order(self, order)` — Set option order (fluent interface)
  - `OptionBoxManager.clear_first(self)` — Set clear button to appear first (fluent interface)
  - `OptionBoxManager.enabled(self)` *(property)* — Check if option box is enabled
  - `OptionBoxManager.widget(self)` *(property)* — Get the actual option box widget
  - `OptionBoxManager.menu(self)` *(property)* — Get or create a Menu instance for this option box.
  - `OptionBoxManager.get_menu(self, create=False)` — Get menu, optionally creating if it doesn't exist.
  - `OptionBoxManager.menu(self, value)` — Set an existing menu instance.
  - `OptionBoxManager.enable_menu(self, menu=None, **menu_kwargs)` — Enable menu option using the MenuOption plugin.
  - `OptionBoxManager.disable_menu(self)` — Disable menu option (fluent interface).
  - `OptionBoxManager.add_option(self, option)` — Add an option plugin to this option box.
  - `OptionBoxManager.container(self)` *(property)* — Get the container widget (for layout management).
  - `OptionBoxManager.remove(self)` — Remove option box completely

<a id="widgets--progressBar"></a>
### `widgets/progressBar.py`

- **[`class ProgressBar(QtWidgets.QProgressBar, AttributesMixin)`](uitk/uitk/widgets/progressBar.py#L9)** — A feature-rich progress bar with task execution support.
  - `ProgressBar.is_cancelled(self) -> bool` *(property)* — Check if the operation was cancelled.
  - `ProgressBar.auto_hide(self) -> bool` *(property)* — Get auto-hide setting.
  - `ProgressBar.auto_hide(self, value: bool)` — Set auto-hide behavior.
  - `ProgressBar.cancel(self)` — Cancel the current operation.
  - `ProgressBar.reset(self)` — Reset the progress bar state.
  - `ProgressBar.set_total(self, total: int) -> None` — Adjust the task total mid-flight.
  - `ProgressBar.start_task(self, total: Optional[int] = 100, text: str = '', show: bool = True) -> None` — Start a new task.
  - `ProgressBar.update_progress(self, value: int, text: Optional[str] = None) -> bool` — Update progress value.
  - `ProgressBar.finish_task(self, text: Optional[str] = None)` — Complete the current task.
  - `ProgressBar.step(self, progress: int, length: int = 100) -> bool` — Legacy step method for backward compatibility.
  - `ProgressBar.task(self, total: Optional[int] = 100, text: str = '') -> 'ProgressTaskContext'` — Context manager for progress tracking.
  - `ProgressBar.showEvent(self, event)` — Handle show event.
- **[`class ProgressTaskContext`](uitk/uitk/widgets/progressBar.py#L375)** — Context manager for progress bar tasks.

<a id="widgets--pushButton"></a>
### `widgets/pushButton.py`

- **[`class PushButton(MenuMixin, QtWidgets.QPushButton, OptionBoxMixin, AttributesMixin, RichText, TextOverlay)`](uitk/uitk/widgets/pushButton.py#L10)** — Enhanced QPushButton with menu, option box, and rich text support.

<a id="widgets--region"></a>
### `widgets/region.py`

- **[`class Region(QtWidgets.QWidget, AttributesMixin, ConvertMixin)`](uitk/uitk/widgets/region.py#L8)** — A custom QWidget that represents a region with a specified shape and size.
  - `Region.visible_on_mouse_over(self)` *(property)* — Get or set the visibility of the top-level children of the Region widget when the mouse cursor is o…
  - `Region.visible_on_mouse_over(self, value)` — Set the visibility of the top-level children of the Region widget when the mouse cursor is over it.
  - `Region.hide_top_level_children(self)` — Hide all top-level child widgets of the Region instance.
  - `Region.show_top_level_children(self)` — Show all top-level child widgets of the Region instance.
  - `Region.enterEvent(self, event)` — Overrides the QWidget.enterEvent method.
  - `Region.leaveEvent(self, event)` — Overrides the QWidget.leaveEvent method.
  - `Region.hideEvent(self, event)` — Overrides the QWidget.hideEvent method.
  - `Region.childEvent(self, event)` — Overrides the QWidget.childEvent method.

<a id="widgets--row_selection_delegate"></a>
### `widgets/row_selection_delegate.py`

Opt-in delegate for views whose cells carry their own background.

- **[`class RowSelectionBorderDelegate(QtWidgets.QStyledItemDelegate)`](uitk/uitk/widgets/row_selection_delegate.py#L28)** — Paints a 1 px row-spanning selection border.
  - `RowSelectionBorderDelegate.paint(self, painter, option, index)`
  - `RowSelectionBorderDelegate.paint_row_selection_border(self, painter, option, index)` — Paint this cell's share of a row-spanning selection border.

<a id="widgets--separator"></a>
### `widgets/separator.py`

- **[`class Separator(QtWidgets.QFrame, AttributesMixin)`](uitk/uitk/widgets/separator.py#L10)** — A simple horizontal separator with optional title and styling.
  - `Separator.title(self) -> str` *(property)* — Get the separator title.
  - `Separator.title(self, value: str) -> None` — Set the separator title.
  - `Separator.setTitle(self, value: str) -> None` — Set the separator title (alias for title property).
  - `Separator.resizeEvent(self, event) -> None` — Position the title label on resize.

<a id="widgets--sequencer--_clip"></a>
### `widgets/sequencer/_clip.py`

ClipItem — draggable, resizable clip rectangle on the timeline.

- **[`class ClipItem(DraggableItemMixin, QtWidgets.QGraphicsRectItem)`](uitk/uitk/widgets/sequencer/_clip.py#L29)** — A draggable, resizable rectangle representing one clip on the timeline.
  - `ClipItem.clip_data(self) -> ClipData` *(property)*
  - `ClipItem.boundingRect(self)`
  - `ClipItem.paint(self, painter: QtGui.QPainter, option, widget=None)`
  - `ClipItem.hoverMoveEvent(self, event)`
  - `ClipItem.hoverLeaveEvent(self, event)`
  - `ClipItem.mousePressEvent(self, event)`
  - `ClipItem.mouseMoveEvent(self, event)`
  - `ClipItem.mouseReleaseEvent(self, event)`
  - `ClipItem.contextMenuEvent(self, event)`
  - `ClipItem.mouseDoubleClickEvent(self, event)`

<a id="widgets--sequencer--_data"></a>
### `widgets/sequencer/_data.py`

Data models and shared constants for the sequencer widget.

- [`register_pattern(name: str, painter: PatternPainter) -> None`](uitk/uitk/widgets/sequencer/_data.py#L171) — Register (or override) a tile-painter for :func:`pattern_brush`.
- [`pattern_brush(style: str, color: QtGui.QColor, spacing: int = HATCH_MEDIUM, line_width: float = 1.0) -> QtGui.QBrush`](uitk/uitk/widgets/sequencer/_data.py#L228) — Return a cached tiled brush for the registered ``style`` (``line_width`` doubles as dot radius for…
- [`paint_pattern(painter: QtGui.QPainter, rect: QtCore.QRectF, spec: PatternSpec) -> None`](uitk/uitk/widgets/sequencer/_data.py#L259) — Fill ``rect`` with ``spec``;
- **[`class PatternSpec`](uitk/uitk/widgets/sequencer/_data.py#L21)** — Declarative, hashable description of a tiled background pattern.
  - `PatternSpec.brush(self) -> QtGui.QBrush`
- **[`class ClipData`](uitk/uitk/widgets/sequencer/_data.py#L40)** — Lightweight data record for a single clip on a track.
  - `ClipData.end(self) -> float` *(property)*
- **[`class TrackData`](uitk/uitk/widgets/sequencer/_data.py#L60)** — Lightweight data record for a track row.
- **[`class MarkerData`](uitk/uitk/widgets/sequencer/_data.py#L72)** — Lightweight data record for a timeline marker.

<a id="widgets--sequencer--_drag_tooltip"></a>
### `widgets/sequencer/_drag_tooltip.py`

Floating scene-text that tracks the cursor during timeline drags.

- **[`class FrameTooltip`](uitk/uitk/widgets/sequencer/_drag_tooltip.py#L35)** — Floating ``QGraphicsSimpleTextItem`` that tracks the cursor.
  - `FrameTooltip.format_frame(t: float) -> str` *(static)* — Format a frame value — integer when exact, one decimal otherwise.
  - `FrameTooltip.show(self, scene: Optional[QtWidgets.QGraphicsScene], scene_pos: QtCore.QPointF, label: str = '', color: Optional[str] = None) -> None` — Attach the tooltip to *scene* at *scene_pos*.
  - `FrameTooltip.update(self, scene_pos: QtCore.QPointF, label: Optional[str] = None, color: Optional[str] = None) -> None` — Reposition (and optionally retext/recolor) the tooltip.
  - `FrameTooltip.hide(self) -> None` — Remove the tooltip from the scene, if any.
  - `FrameTooltip.is_visible(self) -> bool`

<a id="widgets--sequencer--_draggable"></a>
### `widgets/sequencer/_draggable.py`

Shared drag infrastructure for sequencer graphics items.

- [`snap_time(value: float, timeline) -> float`](uitk/uitk/widgets/sequencer/_draggable.py#L14) — Snap *value* to the timeline's grid, or to 1 when Ctrl is held.
- **[`class DraggableItemMixin`](uitk/uitk/widgets/sequencer/_draggable.py#L25)** — Standard Escape-to-cancel support for QGraphicsItems.
  - `DraggableItemMixin.cancel_drag(self) -> bool`

<a id="widgets--sequencer--_keyframe"></a>
### `widgets/sequencer/_keyframe.py`

KeyframeItem — selectable, draggable keyframe dot on an attribute sub-row.

- **[`class KeyframeItem(DraggableItemMixin, QtWidgets.QGraphicsEllipseItem)`](uitk/uitk/widgets/sequencer/_keyframe.py#L17)** — An interactive keyframe indicator inside a sub-row :class:`ClipItem`.
  - `KeyframeItem.time(self) -> float` *(property)*
  - `KeyframeItem.value(self) -> float` *(property)*
  - `KeyframeItem.paint(self, painter: QtGui.QPainter, option, widget=None)`
  - `KeyframeItem.boundingRect(self) -> QtCore.QRectF`
  - `KeyframeItem.shape(self) -> QtGui.QPainterPath` — Larger hit area for easier clicking.
  - `KeyframeItem.hoverEnterEvent(self, event)`
  - `KeyframeItem.hoverLeaveEvent(self, event)`
  - `KeyframeItem.mousePressEvent(self, event)`
  - `KeyframeItem.mouseMoveEvent(self, event)`
  - `KeyframeItem.mouseReleaseEvent(self, event)`

<a id="widgets--sequencer--_markers"></a>
### `widgets/sequencer/_markers.py`

MarkerItem — named marker on the timeline with drag and context menu.

- **[`class MarkerItem(DraggableItemMixin, QtWidgets.QGraphicsItem)`](uitk/uitk/widgets/sequencer/_markers.py#L25)** — A named marker on the timeline: triangle at the ruler + dashed line.
  - `MarkerItem.marker_data(self) -> MarkerData` *(property)*
  - `MarkerItem.boundingRect(self) -> QtCore.QRectF`
  - `MarkerItem.shape(self) -> QtGui.QPainterPath`
  - `MarkerItem.sync(self)`
  - `MarkerItem.paint(self, painter: QtGui.QPainter, option, widget=None)`
  - `MarkerItem.hoverEnterEvent(self, event)`
  - `MarkerItem.hoverLeaveEvent(self, event)`
  - `MarkerItem.mousePressEvent(self, event)`
  - `MarkerItem.mouseMoveEvent(self, event)`
  - `MarkerItem.mouseReleaseEvent(self, event)`
  - `MarkerItem.mouseDoubleClickEvent(self, event)`
  - `MarkerItem.contextMenuEvent(self, event)`

<a id="widgets--sequencer--_overlays"></a>
### `widgets/sequencer/_overlays.py`

Range-related overlay items: static ranges, gap hatching, and highlights.

- **[`class RangeHighlightItem(DraggableItemMixin, QtWidgets.QGraphicsItem)`](uitk/uitk/widgets/sequencer/_overlays.py#L375)** — A semi-transparent rectangle highlighting a time range on the timeline.
  - `RangeHighlightItem.locked(self) -> bool` *(property)*
  - `RangeHighlightItem.locked(self, value: bool)`
  - `RangeHighlightItem.start(self) -> float` *(property)*
  - `RangeHighlightItem.start(self, value: float)`
  - `RangeHighlightItem.end(self) -> float` *(property)*
  - `RangeHighlightItem.end(self, value: float)`
  - `RangeHighlightItem.set_range(self, start: float, end: float)`
  - `RangeHighlightItem.color(self) -> QtGui.QColor` *(property)*
  - `RangeHighlightItem.color(self, value)`
  - `RangeHighlightItem.opacity_value(self) -> int` *(property)*
  - `RangeHighlightItem.opacity_value(self, alpha: int)`
  - `RangeHighlightItem.sync(self)`
  - `RangeHighlightItem.boundingRect(self) -> QtCore.QRectF`
  - `RangeHighlightItem.paint(self, painter: QtGui.QPainter, option, widget=None)`
  - `RangeHighlightItem.hoverMoveEvent(self, event)`
  - `RangeHighlightItem.mousePressEvent(self, event)`
  - `RangeHighlightItem.mouseMoveEvent(self, event)`
  - `RangeHighlightItem.mouseReleaseEvent(self, event)`

<a id="widgets--sequencer--_playhead"></a>
### `widgets/sequencer/_playhead.py`

PlayheadItem — vertical playhead line with frame-number badge.

- **[`class PlayheadItem(QtWidgets.QGraphicsItem)`](uitk/uitk/widgets/sequencer/_playhead.py#L16)** — A vertical line with a frame-number badge at the ruler.
  - `PlayheadItem.time(self) -> float` *(property)*
  - `PlayheadItem.time(self, value: float)`
  - `PlayheadItem.boundingRect(self) -> QtCore.QRectF`
  - `PlayheadItem.sync(self)`
  - `PlayheadItem.paint(self, painter: QtGui.QPainter, option, widget=None)`

<a id="widgets--sequencer--_ruler"></a>
### `widgets/sequencer/_ruler.py`

Ruler and shot-lane items for the timeline header area.

- **[`class ShotLaneItem(QtWidgets.QGraphicsItem)`](uitk/uitk/widgets/sequencer/_ruler.py#L33)** — Renders coloured shot blocks in a thin lane below the ruler.
  - `ShotLaneItem.set_blocks(self, blocks: list) -> None`
  - `ShotLaneItem.clear_blocks(self) -> None`
  - `ShotLaneItem.mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent)`
  - `ShotLaneItem.boundingRect(self) -> QtCore.QRectF`
  - `ShotLaneItem.paint(self, painter: QtGui.QPainter, option, widget=None)`
- **[`class RulerItem(QtWidgets.QGraphicsItem)`](uitk/uitk/widgets/sequencer/_ruler.py#L158)** — Draws the frame-number ruler at the top of the timeline.
  - `RulerItem.set_shot_blocks(self, blocks: list) -> None`
  - `RulerItem.clear_shot_blocks(self) -> None`
  - `RulerItem.boundingRect(self)`
  - `RulerItem.paint(self, painter: QtGui.QPainter, option, widget=None)`

<a id="widgets--sequencer--_scrub_player"></a>
### `widgets/sequencer/_scrub_player.py`

Qt-side audio scrub/playback helper for :class:`SequencerWidget`.

- **[`class ScrubPlayer(QtCore.QObject)`](uitk/uitk/widgets/sequencer/_scrub_player.py#L36)** — Seek-and-grain player for NLE-style audio scrub.
  - `ScrubPlayer.available(self) -> bool` *(property)* — True if ``QtMultimedia`` is importable in this environment.
  - `ScrubPlayer.source_path(self) -> str` *(property)* — Current source path, or empty string.
  - `ScrubPlayer.set_source(self, path: str) -> bool` — Point the player at an audio file.
  - `ScrubPlayer.clear_source(self) -> None` — Drop the current source and stop playback.
  - `ScrubPlayer.play_at_frame(self, frame: float, fps: float) -> None` — Seek to ``frame`` and play a short grain for scrub feedback.
  - `ScrubPlayer.play(self, from_frame: Optional[float] = None, fps: float = 24.0) -> None` — Transport play from ``from_frame`` (or current position).
  - `ScrubPlayer.stop(self) -> None` — Stop playback and cancel any pending grain timeout.
  - `ScrubPlayer.set_volume(self, vol: float) -> None` — Volume in [0.0, 1.0].
  - `ScrubPlayer.set_grain_ms(self, grain_ms: int) -> None` — Override the grain window length at runtime.

<a id="widgets--sequencer--_sequencer"></a>
### `widgets/sequencer/_sequencer.py`

An NLE-style timeline sequencer widget.

- **[`class AttributeColorDialog(ColorMappingDialog)`](uitk/uitk/widgets/sequencer/_sequencer.py#L54)** — Dialog for configuring attribute-type color mappings.
  - `AttributeColorDialog.load_color_map() -> Dict[str, str]` *(static)* — Return the persisted attribute color map without opening a dialog.
- **[`class SequencerWidget(QtWidgets.QSplitter, AttributesMixin)`](uitk/uitk/widgets/sequencer/_sequencer.py#L135)** — A split-view NLE sequencer widget.
  - `SequencerWidget.window_shortcuts(self) -> bool` *(property)* — When ``True``, sequencer shortcuts are active whenever the
  - `SequencerWidget.window_shortcuts(self, enabled: bool) -> None`
  - `SequencerWidget.showEvent(self, event: QtGui.QShowEvent) -> None`
  - `SequencerWidget.eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool` — Intercept ShortcutOverride on the window when window_shortcuts is on.
  - `SequencerWidget.event(self, event: QtCore.QEvent) -> bool`
  - `SequencerWidget.keyPressEvent(self, event)` — Dispatch registered shortcuts when focus is on a non-timeline child.
  - `SequencerWidget.add_track(self, name: str, icon=None, dimmed: bool = False, italic: bool = False, color: Optional[str] = None, text_color: Optional[str] = None) -> int` — Add a new track row.
  - `SequencerWidget.add_clip(self, track_id: int, start: float, duration: float, label: str = '', color: Optional[str] = None, sub_row: str = '', locked: bool = False, **data) -> int` — Add a clip to an existing track.
  - `SequencerWidget.remove_clip(self, clip_id: int)` — Remove a clip by id.
  - `SequencerWidget.set_clip_label(self, clip_id: int, label: str)` — Set the display label for a clip.
  - `SequencerWidget.set_clip_locked(self, clip_id: int, locked: bool)` — Lock or unlock a clip, preventing drag/resize/rename/selection.
  - `SequencerWidget.remove_track(self, track_id: int)` — Remove a track and all its clips.
  - `SequencerWidget.get_clip(self, clip_id: int) -> Optional[ClipData]` — Return the data for a clip, or None.
  - `SequencerWidget.get_track(self, track_id: int) -> Optional[TrackData]` — Return the data for a track, or None.
  - `SequencerWidget.tracks(self) -> List[TrackData]` — Return a list of all track data.
  - `SequencerWidget.clips(self, track_id: Optional[int] = None) -> List[ClipData]` — Return clip data, optionally filtered by track.
  - `SequencerWidget.swap_clips(self, clip_id_a: int, clip_id_b: int) -> None` — Swap the timeline positions of two clips and emit ``clips_reordered``.
  - `SequencerWidget.set_playhead(self, time: float)` — Move the playhead to a specific time.
  - `SequencerWidget.set_audio_source(self, path: str, fps: float = 24.0) -> bool` — Bind an audio file (typically a composite WAV) for scrub playback.
  - `SequencerWidget.clear_audio_source(self) -> None` — Drop the bound audio source and stop any in-flight scrub.
  - `SequencerWidget.clear(self, *, keep_range_highlight: bool = False)` — Remove all tracks, clips, and markers.
  - `SequencerWidget.clear_decorations(self, *, keep_range_highlight: bool = False)` — Remove markers, overlays, and shot lane without touching tracks or clips.
  - `SequencerWidget.add_marker(self, time: float, note: str = '', color: Optional[str] = None, draggable: bool = True, style: str = 'triangle', line_style: str = 'dashed', opacity: float = 1.0) -> int` — Add a marker at *time*.
  - `SequencerWidget.remove_marker(self, marker_id: int)` — Remove a marker by id.
  - `SequencerWidget.get_marker(self, marker_id: int) -> Optional[MarkerData]` — Return marker data, or None.
  - `SequencerWidget.markers(self) -> List[MarkerData]` — Return all markers.
  - `SequencerWidget.clear_markers(self)` — Remove all markers.
  - `SequencerWidget.set_range_highlight(self, start: float, end: float, color: Optional[str] = None, alpha: int = 30)` — Show or update a translucent highlight over a time range.
  - `SequencerWidget.clear_range_highlight(self)` — Remove the range highlight from the timeline.
  - `SequencerWidget.add_range_overlay(self, start: float, end: float, color: str = '#888888', alpha: int = 15)` — Add a non-interactive range overlay (e.g.
  - `SequencerWidget.clear_range_overlays(self)` — Remove all non-interactive range overlays.
  - `SequencerWidget.add_gap_overlay(self, start: float, end: float, color: str = '#555555', alpha: int = 120, locked: bool = False)` — Add a diagonal-hatch overlay for a gap between shots.
  - `SequencerWidget.clear_gap_overlays(self)` — Remove all gap overlays.
  - `SequencerWidget.set_all_gap_overlays_locked(self, locked: bool)` — Set the locked state on every gap overlay.
  - `SequencerWidget.set_shot_blocks(self, blocks: list) -> None` — Show coloured shot-block indicators on the ruler.
  - `SequencerWidget.clear_shot_blocks(self) -> None` — Remove all shot-block indicators from the ruler.
  - `SequencerWidget.range_highlight(self) -> Optional[tuple]` — Return ``(start, end)`` of the active highlight, or ``None``.
  - `SequencerWidget.set_hidden_tracks(self, names: List[str])` — Store a list of hidden track names for the 'show hidden' menu.
  - `SequencerWidget.set_active_range(self, start: float, end: float)` — Set the active-shot time range painted as a column tint.
  - `SequencerWidget.clear_active_range(self)` — Remove the active-shot column tint.
  - `SequencerWidget.step_forward(self)` — Advance the playhead by one step (snap_interval or 1 frame).
  - `SequencerWidget.step_backward(self)` — Move the playhead back by one step (snap_interval or 1 frame).
  - `SequencerWidget.go_to_next_key(self)` — Jump the playhead to the next clip boundary.
  - `SequencerWidget.go_to_prev_key(self)` — Jump the playhead to the previous clip boundary.
  - `SequencerWidget.go_to_start(self)` — Jump the playhead to frame 0.
  - `SequencerWidget.go_to_end(self)` — Jump the playhead to the end of the last clip.
  - `SequencerWidget.add_marker_at_playhead(self)` — Add a marker at the current playhead position.
  - `SequencerWidget.frame_shot(self)` — Zoom and scroll the timeline to frame the active shot range.
  - `SequencerWidget.undo(self)` — Revert to the previous clip state.
  - `SequencerWidget.redo(self)` — Re-apply a previously undone change.
  - `SequencerWidget.snap_interval(self) -> float` *(property)* — Time-snap interval.
  - `SequencerWidget.snap_interval(self, value: float)`
  - `SequencerWidget.show_range_overlays(self) -> bool` *(property)*
  - `SequencerWidget.show_range_overlays(self, value: bool)`
  - `SequencerWidget.show_gap_overlays(self) -> bool` *(property)*
  - `SequencerWidget.show_gap_overlays(self, value: bool)`
  - `SequencerWidget.show_range_highlight(self) -> bool` *(property)*
  - `SequencerWidget.show_range_highlight(self, value: bool)`
  - `SequencerWidget.shift_held_at_press(self) -> bool` *(property)* — Whether Shift was held when the last drag interaction started.
  - `SequencerWidget.shift_held_at_press(self, value: bool) -> None`
  - `SequencerWidget.attribute_colors(self) -> Dict[str, str]` *(property)* — Mapping of attribute name to hex color string.
  - `SequencerWidget.attribute_colors(self, value: Dict[str, str])`
  - `SequencerWidget.sub_row_height(self) -> int` *(property)* — Pixel height of expanded attribute sub-rows (default half track height).
  - `SequencerWidget.sub_row_height(self, value: int)`
  - `SequencerWidget.sub_row_provider(self)` *(property)* — Callable providing sub-row data for track expansion.
  - `SequencerWidget.sub_row_provider(self, fn)`
  - `SequencerWidget.expand_track(self, track_id: int, sub_row_data=None)` — Expand *track_id* to show sub-rows beneath it.
  - `SequencerWidget.set_bg_curve_preview(self, track_id: int, sub_row: str, preview: dict, color: str = '#CCCCCC') -> None` — Set or clear a background curve preview for a sub-row.
  - `SequencerWidget.collapse_track(self, track_id: int)` — Collapse a previously expanded track, removing its sub-row clips.
  - `SequencerWidget.is_track_expanded(self, track_id: int) -> bool` — Return True if the track is currently expanded.
  - `SequencerWidget.toggle_track_expanded(self, track_id: int)` — Toggle expansion state.
  - `SequencerWidget.selected_clips(self) -> List[int]` — Return clip IDs for all currently selected clips.

<a id="widgets--sequencer--_timeline"></a>
### `widgets/sequencer/_timeline.py`

Timeline view, scene, and track-header widgets.

- **[`class TrackHeaderWidget(QtWidgets.QWidget)`](uitk/uitk/widgets/sequencer/_timeline.py#L68)** — Left-pane widget showing track labels, vertically synced to the timeline.
  - `TrackHeaderWidget.set_top_margin(self, margin: int) -> None`
  - `TrackHeaderWidget.add_track_label(self, name: str, icon=None, dimmed: bool = False, italic: bool = False, color: str = None, text_color: str = None)`
  - `TrackHeaderWidget.set_track_expanded(self, track_idx: int, sub_names: List[str], sub_height: int)`
  - `TrackHeaderWidget.set_track_collapsed(self, track_idx: int)`
  - `TrackHeaderWidget.eventFilter(self, obj, event)`
  - `TrackHeaderWidget.selected_names(self) -> List[str]`
  - `TrackHeaderWidget.clear_tracks(self)`
- **[`class TimelineScene(QtWidgets.QGraphicsScene)`](uitk/uitk/widgets/sequencer/_timeline.py#L336)** — Scene that owns the ruler, playhead, and all clip items.
  - `TimelineScene.ruler(self) -> RulerItem` *(property)*
  - `TimelineScene.playhead(self) -> PlayheadItem` *(property)*
- **[`class TimelineView(QtWidgets.QGraphicsView)`](uitk/uitk/widgets/sequencer/_timeline.py#L361)** — QGraphicsView providing zoom, pan, and coordinate mapping.
  - `TimelineView.event(self, event: QtCore.QEvent) -> bool`
  - `TimelineView.keyPressEvent(self, event)`
  - `TimelineView.keyReleaseEvent(self, event)`
  - `TimelineView.enterEvent(self, event)`
  - `TimelineView.pixels_per_unit(self) -> float` *(property)*
  - `TimelineView.pixels_per_unit(self, value: float)`
  - `TimelineView.time_to_x(self, t: float) -> float`
  - `TimelineView.x_to_time(self, x: float) -> float`
  - `TimelineView.resizeEvent(self, event)`
  - `TimelineView.wheelEvent(self, event)`
  - `TimelineView.mousePressEvent(self, event)`
  - `TimelineView.mouseMoveEvent(self, event)`
  - `TimelineView.mouseReleaseEvent(self, event)`
  - `TimelineView.mouseDoubleClickEvent(self, event)`
  - `TimelineView.paintEvent(self, event)`
  - `TimelineView.contextMenuEvent(self, event)`
  - `TimelineView.drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF)`

<a id="widgets--sequencer--_transport_controls"></a>
### `widgets/sequencer/_transport_controls.py`

Reusable Maya-style transport controls for :class:`SequencerWidget`.

- **[`class PlayController(Protocol)`](uitk/uitk/widgets/sequencer/_transport_controls.py#L31)** — Minimal transport API the controls drive.
  - `PlayController.is_playing(self) -> bool`
  - `PlayController.play(self, forward: bool) -> None`
  - `PlayController.stop(self) -> None`
- **[`class ScrubPlayerPlayController`](uitk/uitk/widgets/sequencer/_transport_controls.py#L39)** — Default :class:`PlayController` backed by the sequencer's ScrubPlayer.
  - `ScrubPlayerPlayController.set_fps(self, fps: float) -> None`
  - `ScrubPlayerPlayController.is_playing(self) -> bool`
  - `ScrubPlayerPlayController.play(self, forward: bool) -> None`
  - `ScrubPlayerPlayController.stop(self) -> None`
- **[`class TransportControls(QtWidgets.QWidget)`](uitk/uitk/widgets/sequencer/_transport_controls.py#L83)** — Maya-style 8-button transport row bound to a :class:`SequencerWidget`.
  - `TransportControls.play_controller(self) -> PlayController` *(property)*
  - `TransportControls.set_play_controller(self, pc: PlayController) -> None`
  - `TransportControls.set_interrupt_mode(self, mode: str) -> None`
  - `TransportControls.interrupt_mode(self) -> str`
  - `TransportControls.button(self, name: str) -> Optional[QtWidgets.QToolButton]` — Lookup a button by name (e.g.
  - `TransportControls.attach_to_footer(self, footer, side: str = 'right') -> None` — Insert this row into *footer*'s main layout on the given side.

<a id="widgets--spinBox"></a>
### `widgets/spinBox.py`

- **[`class SpinBox(QtWidgets.QDoubleSpinBox, MenuMixin, OptionBoxMixin, AttributesMixin)`](uitk/uitk/widgets/spinBox.py#L12)** — Unified SpinBox that supports both integer and float behavior, plus custom display values.
  - `SpinBox.value(self) -> Union[float, int]` — Return integer if decimals is 0, else float.
  - `SpinBox.setCustomDisplayValues(self, *args)` — Set a mapping of values to custom display strings.
  - `SpinBox.textFromValue(self, value: float) -> str` — Format the text displayed in the spin box.
  - `SpinBox.valueFromText(self, text: str) -> float` — Convert text back to value.
  - `SpinBox.validate(self, text: str, pos: int) -> object` — Validate input, allowing custom display strings.
  - `SpinBox.setPrefix(self, prefix: str) -> None` — Add a tab space after the prefix for clearer display.
  - `SpinBox.wheelEvent(self, event: QtGui.QWheelEvent) -> None` — Handle wheel events with modifier keys.
  - `SpinBox.stepBy(self, steps: int) -> None` — Step by the given number of steps, snapping to the step-size grid.
  - `SpinBox.adjustStepSize(self, event: QtGui.QWheelEvent) -> None` — Adjust the step size dynamically based on the Alt modifier key.
  - `SpinBox.increaseValueWithLargeStep(self, event: QtGui.QWheelEvent) -> None` — Increase the spin box value by a larger step when Ctrl is pressed.
  - `SpinBox.decreaseValueWithSmallStep(self, event: QtGui.QWheelEvent) -> None` — Move the value by the lowest decimal place (Ctrl+Alt).
  - `SpinBox.message(self, text: str) -> None` — Display a temporary message box with the given text.

<a id="widgets--table_actions"></a>
### `widgets/table_actions.py`

Reusable action-column management for :class:`TableWidget`.

- **[`class TableActions`](uitk/uitk/widgets/table_actions.py#L139)** — Manages action columns on a :class:`TableWidget`.
  - `TableActions.add(self, column: int, states: Dict[str, Dict[str, Any]], header_icon: str | None = None, square: bool = True) -> None` — Register an action column.
  - `TableActions.set(self, row: int, col: int, state_name: str) -> None` — Set a cell to a named state, updating its icon, tooltip, and style.
  - `TableActions.get(self, row: int, col: int) -> Optional[str]` — Return the current state name for a cell, or ``None``.
  - `TableActions.update_for_row_height(self) -> None` — Re-size action columns and icons to fit the current row height.

<a id="widgets--tableWidget"></a>
### `widgets/tableWidget.py`

- **[`class HeaderMixin`](uitk/uitk/widgets/tableWidget.py#L16)**
  - `HeaderMixin.default_header_click_behavior(self, col)`
- **[`class CellFormatMixin(ConvertMixin)`](uitk/uitk/widgets/tableWidget.py#L43)** — Generic cell/column/header formatting for QTableWidget.
  - `CellFormatMixin.set_column_formatter(self, col, formatter, append=False)` — Set a formatter for a specific column.
  - `CellFormatMixin.set_header_formatter(self, header, formatter, append=False)` — Set a formatter for a specific header.
  - `CellFormatMixin.set_cell_formatter(self, row, col, formatter, append=False)` — Set a formatter for a specific cell (row, column).
  - `CellFormatMixin.clear_formatters(self)` — Clear all column, header, and cell formatters.
  - `CellFormatMixin.apply_formatting(self)` — Apply formatting based on the registered formatters.
  - `CellFormatMixin.ensure_valid_color(self, color, color_type, item, row, col)` — Ensure a valid QColor, using fallback if needed.
  - `CellFormatMixin.format_item(self, item: QtWidgets.QTableWidgetItem, key: str = None, italic: bool = None, bold: bool = None, fg: Any = None, bg: Any = None)` — Apply formatting to a table item.
  - `CellFormatMixin.set_action_color(self, item: QtWidgets.QTableWidgetItem, key: str, row: int = -1, col: int = -1, use_bg: bool = False)` — Apply semantic color, but skip reset if nothing defined.
  - `CellFormatMixin.action_color_formatter(self, item, value, *_)`
  - `CellFormatMixin.make_color_map_formatter(self, color_map: dict)`
  - `CellFormatMixin.add_section_row(table: QtWidgets.QTableWidget, title: str, row: int = -1, col_count: int = None, bg: Any = None, fg: Any = '#999', bold: bool = True, font_delta: int = -1, height: int = 22) -> int` *(static)* — Insert a non-selectable section header that spans all columns.
  - `CellFormatMixin.is_section_row(table: QtWidgets.QTableWidget, row: int) -> bool` *(static)* — Return ``True`` if *row* is a section header.
- **[`class TableSelection`](uitk/uitk/widgets/tableWidget.py#L421)** — Immutable representation of a single selected row.
  - `TableSelection.get(self, key: str, default: Any = None)`
  - `TableSelection.item(self, key: str) -> Optional[QtWidgets.QTableWidgetItem]`
  - `TableSelection.text(self, key: str, default: str = '') -> str`
- **[`class TableWidget(QtWidgets.QTableWidget, MenuMixin, HeaderMixin, AttributesMixin, CellFormatMixin)`](uitk/uitk/widgets/tableWidget.py#L473)** — Enhanced QTableWidget with cell formatting, sorting, and context menu support.
  - `TableWidget.set_scrub_columns(self, columns: Iterable[int]) -> None` — Enable MMB-drag value scrubbing for *columns*.
  - `TableWidget.add_scrub_column(self, column: int) -> None` — Add a single column to the MMB-scrub set.
  - `TableWidget.remove_scrub_column(self, column: int) -> None` — Remove a column from the MMB-scrub set.
  - `TableWidget.is_scrubbing(self) -> bool` — ``True`` while an MMB scrub-drag is in progress.
  - `TableWidget.set_wheel_scrub_columns(self, columns: Iterable[int]) -> None` — Enable mouse-wheel value adjustment for *columns*.
  - `TableWidget.add_wheel_scrub_column(self, column: int) -> None` — Add a single column to the wheel-scrub set.
  - `TableWidget.remove_wheel_scrub_column(self, column: int) -> None` — Remove a column from the wheel-scrub set.
  - `TableWidget.set_single_click_edit_columns(self, columns: Iterable[int]) -> None` — Enable click-to-edit for *columns* (no double-click required).
  - `TableWidget.add_single_click_edit_column(self, column: int) -> None` — Add a single column to the single-click-edit set.
  - `TableWidget.remove_single_click_edit_column(self, column: int) -> None` — Remove a column from the single-click-edit set.
  - `TableWidget.mousePressEvent(self, event)`
  - `TableWidget.mouseMoveEvent(self, event)`
  - `TableWidget.mouseReleaseEvent(self, event)`
  - `TableWidget.wheelEvent(self, event)` — Consume wheel events on wheel-scrub columns;
  - `TableWidget.eventFilter(self, obj, event)` — Catch wheel events on editors so wheel-scrub also works in
  - `TableWidget.active_editor(self) -> Optional[QtWidgets.QWidget]` — Return the currently-open cell editor widget, or ``None``.
  - `TableWidget.refresh_active_editor(self) -> None` — If a cell editor is currently open, refresh its display from
  - `TableWidget.closeEditor(self, editor, hint)` — Propagate committed value to all drag-selected cells.
  - `TableWidget.selectionCommand(self, index, event=None)` — Optionally restrict selection changes.
  - `TableWidget.set_column_selectable(self, column: int, selectable: bool)` — Set whether a specific column can trigger selection changes.
  - `TableWidget.set_selection_validator(self, validator: Callable[[QtCore.QModelIndex], bool])` — Set a function to validate if an index can be selected.
  - `TableWidget.set_column_click_action(self, column: int, action: Callable[[int, int], None])` — Set a callback for when a cell in a specific column is clicked.
  - `TableWidget.set_left_click_select_only(self, enabled: bool)` — Toggle whether non-left clicks can change selection.
  - `TableWidget.set_selection_mode(self, mode_str)` — Change the selection mode after initialization.
  - `TableWidget.item_data(self, row: int, column: int)`
  - `TableWidget.set_item_data(self, row: int, column: int, value, user_data=None)`
  - `TableWidget.add(self, data, clear: bool = True, headers: list = None, **kwargs)`
  - `TableWidget.selected_node(self)`
  - `TableWidget.selected_label(self)`
  - `TableWidget.selected_nodes(self)` — Get all selected nodes (UserRole data from column 1)
  - `TableWidget.selected_labels(self)` — Get all selected labels (text from column 0)
  - `TableWidget.selected_rows(self, include_current=False)` — Get all selected row numbers
  - `TableWidget.clear_all(self)`
  - `TableWidget.set_stretch_column(self, col: int)` — Set a column to automatically stretch to fill the available space.
  - `TableWidget.resizeEvent(self, event)`
  - `TableWidget.stretch_column_to_fill(self, stretch_col: int)`
  - `TableWidget.get_selected_data(self, columns=None, include_current=True)` — Get data from selected rows for specified columns.
  - `TableWidget.get_selection(self, columns: Optional[Union[Sequence[Union[int, str]], Dict[str, Union[int, str]]]] = None, include_current: bool = True) -> List[TableSelection]` — Return detailed selection payload keyed by column aliases.
  - `TableWidget.register_menu_action(self, object_name: str, handler: Callable[[List[TableSelection]], None], *, columns: Optional[Union[Sequence[Union[int, str]], Dict[str, Union[int, str]]]] = None, include_current: bool = True, allow_empty: bool = False, transform: Optional[Callable[[List[TableSelection]], Any]] = None, pass_widget: bool = False)` — Attach a context-menu item to a callable that receives selection data.
  - `TableWidget.unregister_menu_action(self, object_name: str)`

<a id="widgets--textEdit"></a>
### `widgets/textEdit.py`

- **[`class TextEdit(QtWidgets.QTextEdit, MenuMixin, AttributesMixin)`](uitk/uitk/widgets/textEdit.py#L8)** — Rich text editor with context menu and visibility signals.
  - `TextEdit.insertText(self, text, color='LightGray', backround_color='rgb(50, 50, 50)')` — Append a new paragraph to the textEdit.
  - `TextEdit.showEvent(self, event)` — Parameters:
  - `TextEdit.hideEvent(self, event)` — Parameters:

<a id="widgets--textEditLogHandler"></a>
### `widgets/textEditLogHandler.py`

- **[`class TextEditLogHandler(logging.Handler)`](uitk/uitk/widgets/textEditLogHandler.py#L9)** — Custom logging handler for Qt QTextEdit widgets.
  - `TextEditLogHandler.emit(self, record: logging.LogRecord) -> None`
  - `TextEditLogHandler.get_color(self, level: str) -> str`
  - `TextEditLogHandler.available_columns(self) -> int` — Return the number of monospace columns that fit in the viewport.

<a id="widgets--textViewBox"></a>
### `widgets/textViewBox.py`

Scrollable rich-text viewer window.

- **[`class TextViewBox(WindowPanel)`](uitk/uitk/widgets/textViewBox.py#L58)** — Read-only rich-text viewer with optional standard buttons.
  - `TextViewBox.setStandardButtons(self, *buttons) -> None` — Configure the visible buttons by name.
  - `TextViewBox.setText(self, string: str, fontColor: str = 'white', background=False, fontSize=None) -> None` — Set the body text, replacing any existing content.
  - `TextViewBox.append_text(self, string: str, fontColor: str = 'white', fontSize=None) -> None` — Append a paragraph without clearing existing content.
  - `TextViewBox.clear_text(self) -> None`
  - `TextViewBox.clicked_button(self)` *(property)* — Canonical name of the last clicked button, or ``None``.

<a id="widgets--toolBox"></a>
### `widgets/toolBox.py`

- **[`class HoverSwitcher(QtCore.QObject)`](uitk/uitk/widgets/toolBox.py#L7)** — Helper class to handle hover switching logic for ToolBox.
  - `HoverSwitcher.eventFilter(self, obj, event)` — Handle mouse move events for hover switching.
- **[`class ToolBox(QtWidgets.QToolBox, AttributesMixin)`](uitk/uitk/widgets/toolBox.py#L81)** — A customized QToolBox with additional features and styling support.
  - `ToolBox.sizeHint(self)` — Calculate size hint based on current page and tabs.
  - `ToolBox.add(self, widget, text, icon=None, **kwargs)` — Add a widget as a new tab item.

<a id="widgets--treeWidget"></a>
### `widgets/treeWidget.py`

- **[`class HierarchyIconMixin`](uitk/uitk/widgets/treeWidget.py#L15)** — Mixin to handle custom hierarchy icons in tree widgets using CSS branch styling.
  - `HierarchyIconMixin.set_icon_style(self, style: str)` — Set the icon style for hierarchy indicators.
  - `HierarchyIconMixin.enable_hierarchy_icons(self, enabled=True)` — Enable or disable custom hierarchy icons.
  - `HierarchyIconMixin.get_available_icon_styles(self) -> list` — Get list of available icon styles.
  - `HierarchyIconMixin.get_current_icon_style(self) -> str` — Get the currently active icon style.
- **[`class TreeFormatMixin(ConvertMixin)`](uitk/uitk/widgets/treeWidget.py#L187)** — Generic item/column formatting for QTreeWidget.
  - `TreeFormatMixin.set_item_formatter(self, item_id, formatter, append=False)` — Set a formatter for a specific item by ID.
  - `TreeFormatMixin.set_column_formatter(self, col, formatter, append=False)` — Set a formatter for a specific column.
  - `TreeFormatMixin.clear_formatters(self)` — Clear all item and column formatters.
  - `TreeFormatMixin.apply_formatting(self)` — Apply formatting based on the registered formatters.
  - `TreeFormatMixin.ensure_valid_color(self, color, color_type, item, col)` — Ensure a valid QColor, using fallback if needed.
  - `TreeFormatMixin.set_action_color(self, item: QtWidgets.QTreeWidgetItem, key: str, col: int = 0, use_bg: bool = False)` — Apply semantic color to a tree item.
  - `TreeFormatMixin.action_color_formatter(self, item, value, col, *_)` — Formatter that applies action colors based on item value.
  - `TreeFormatMixin.make_color_map_formatter(self, color_map: dict)` — Create a formatter from a color mapping dictionary.
- **[`class TreeWidget(QtWidgets.QTreeWidget, MenuMixin, AttributesMixin, TreeFormatMixin, HierarchyIconMixin)`](uitk/uitk/widgets/treeWidget.py#L566)** — Enhanced QTreeWidget with flexible data handling, formatting capabilities, and custom hierarchy ico…
  - `TreeWidget.selection_style(self) -> str` *(property)* — Visual style for selected items: ``"border"`` or ``"tint"``.
  - `TreeWidget.selection_style(self, value: str)`
  - `TreeWidget.header_actions(self) -> _HeaderActionBar` *(property)* — Right-aligned icon-button strip overlaid on the tree header.
  - `TreeWidget.set_column_tint(self, column: int, color) -> None` — Apply a tint overlay to every cell in *column*.
  - `TreeWidget.clear_column_tints(self) -> None` — Remove all column tint overlays.
  - `TreeWidget.set_selection_mode(self, mode_str)` — Change the selection mode after initialization.
  - `TreeWidget.ctrl_toggle(self)` *(property)* — Whether Ctrl+click toggles (deselects) an already-selected item.
  - `TreeWidget.ctrl_toggle(self, value)`
  - `TreeWidget.mousePressEvent(self, event)` — Track pre-click state;
  - `TreeWidget.mouseReleaseEvent(self, event)` — Handle Ctrl+click toggle after Qt finalises selection.
  - `TreeWidget.create_item(self, text: Union[str, List[str]], data: Any = None, parent: QtWidgets.QTreeWidgetItem = None) -> QtWidgets.QTreeWidgetItem` — Create a new tree widget item.
  - `TreeWidget.item_data(self, item: QtWidgets.QTreeWidgetItem, column: int = 0)` — Get data from an item.
  - `TreeWidget.set_item_data(self, item: QtWidgets.QTreeWidgetItem, data: Any, column: int = 0)` — Set data for an item.
  - `TreeWidget.find_item_by_text(self, text: str, column: int = 0) -> Optional[QtWidgets.QTreeWidgetItem]` — Find an item by its text in the specified column.
  - `TreeWidget.find_item_by_data(self, data: Any, column: int = 0) -> Optional[QtWidgets.QTreeWidgetItem]` — Find an item by its user data.
  - `TreeWidget.add(self, data: Union[Dict, List, str, Any], headers: Optional[List[str]] = None, clear: bool = True, parent: Optional[QtWidgets.QTreeWidgetItem] = None, **kwargs)` — Add data to the tree widget with flexible input handling.
  - `TreeWidget.selected_item(self) -> Optional[QtWidgets.QTreeWidgetItem]` — Get the currently selected item.
  - `TreeWidget.selected_items(self) -> List[QtWidgets.QTreeWidgetItem]` — Get all selected items.
  - `TreeWidget.selected_data(self, column: int = 0) -> Any` — Get data from the currently selected item.
  - `TreeWidget.selected_data_list(self, column: int = 0) -> List[Any]` — Get data from all selected items.
  - `TreeWidget.selected_text(self, column: int = 0) -> Optional[str]` — Get text from the currently selected item.
  - `TreeWidget.selected_text_list(self, column: int = 0) -> List[str]` — Get text from all selected items.
  - `TreeWidget.select_items_by_data(self, data_list: List[Any], column: int = 0)` — Select multiple items by their data values.
  - `TreeWidget.select_items_by_text(self, text_list: List[str], column: int = 0)` — Select multiple items by their text values.
  - `TreeWidget.set_stretch_column(self, col: int)` — Set a column to automatically stretch to fill available space.
  - `TreeWidget.enable_column_config(self, settings=None, settings_key=None)` — Enable header right-click menu for column visibility and drag reorder.
  - `TreeWidget.restore_column_state(self)` — Apply persisted visibility and order.
  - `TreeWidget.resizeEvent(self, event)`
  - `TreeWidget.showEvent(self, event)`
  - `TreeWidget.stretch_column_to_fill(self, stretch_col: int)` — Resize one column to fill remaining horizontal space.
  - `TreeWidget.expand_all_items(self)` — Expand all items in the tree.
  - `TreeWidget.collapse_all_items(self)` — Collapse all items in the tree.
  - `TreeWidget.get_all_items(self) -> List[QtWidgets.QTreeWidgetItem]` — Get all items in the tree.
  - `TreeWidget.remove_item(self, item: QtWidgets.QTreeWidgetItem)` — Remove an item from the tree.
  - `TreeWidget.set_item_icon(self, item: QtWidgets.QTreeWidgetItem, icon_name: str, color: str = None)` — Set a custom icon for a specific item.
  - `TreeWidget.set_item_type_icon(self, item: QtWidgets.QTreeWidgetItem, icon_name: str, column: int = 0, color: str = None)` — Set a custom type icon for a specific item (separate from hierarchy indicators).
  - `TreeWidget.refresh_item_icons(self, color: str = None)` — Refresh all item icons with the current theme color.

<a id="widgets--widgetComboBox"></a>
### `widgets/widgetComboBox.py`

- **[`class WidgetComboBox(ComboBox)`](uitk/uitk/widgets/widgetComboBox.py#L118)** — ComboBox extended with widget embedding support.
  - `WidgetComboBox.setItemText(self, index, text)` — Override to work with QStandardItemModel.
  - `WidgetComboBox.addWidgetItem(self, widget: QtWidgets.QWidget, label: str = '', *, data: Any = None, select: bool = False) -> int` — Insert *widget* as a selectable row.
  - `WidgetComboBox.addWidgetAction(self, action: QtWidgets.QAction, label: str = '', *, select: bool = False) -> int` — Insert a QWidgetAction (or plain QAction) as a widget row.
  - `WidgetComboBox.widgetAt(self, row: int) -> Optional[QtWidgets.QWidget]` — Return the widget stored at *row* if present.
  - `WidgetComboBox.takeWidgetAt(self, row: int) -> Optional[QtWidgets.QWidget]` — Remove and return the widget stored at *row*.
  - `WidgetComboBox.currentWidget(self) -> Optional[QtWidgets.QWidget]` — Convenience accessor for the selected widget.
  - `WidgetComboBox.actions(self) -> _ActionsNamespace` *(property)* — Namespace for managing persistent action buttons at the bottom of
  - `WidgetComboBox.showPopup(self) -> None` — Override to expand popup to widest widget and update overflow.
  - `WidgetComboBox.hidePopup(self) -> None` — Override to hide overflow indicator when popup is hidden.
  - `WidgetComboBox.arrow_direction(self) -> Optional[str]` *(property)* — Direction of the dropdown-affordance arrow drawn after the text.
  - `WidgetComboBox.arrow_direction(self, value: Optional[str]) -> None`
  - `WidgetComboBox.paintEvent(self, event) -> None` — Paint the base combo, then overlay an arrow immediately after the
  - `WidgetComboBox.eventFilter(self, obj, event)` — Event filter to reposition indicator on scroll and resize events.
  - `WidgetComboBox.add(self, x, data=None, header=None, header_alignment='left', clear=True, restore_index=False, ascending=False, _recursion=False, **kwargs)` — Populate the combo box with text, widgets or actions.
  - `WidgetComboBox.add_defaults_button(self) -> bool` *(property)* — When True, adds a "Restore Defaults" action at the bottom of the
  - `WidgetComboBox.add_defaults_button(self, value: bool) -> None`
  - `WidgetComboBox.clear(self) -> None`

<a id="widgets--windowPanel"></a>
### `widgets/windowPanel.py`

Themed top-level uitk window: Header → body → Footer.

- **[`class WindowPanel(QtWidgets.QWidget)`](uitk/uitk/widgets/windowPanel.py#L26)** — Themed top-level window with a Header / body / Footer layout.
  - `WindowPanel.style(self) -> 'StyleSheet'` *(property)* — Lazy :class:`StyleSheet` bound to this panel.
  - `WindowPanel.showEvent(self, event)`
  - `WindowPanel.header(self)` *(property)* — The :class:`Header` widget at the top.
  - `WindowPanel.footer(self)` *(property)* — The :class:`Footer` widget at the bottom.
  - `WindowPanel.body_layout(self)` *(property)* — ``QVBoxLayout`` for panel content.
  - `WindowPanel.tighten_sublayouts(self, spacing: int = 1) -> None` — Set every nested sub-layout inside ``body_layout`` to *spacing*.
  - `WindowPanel.icon_button(icon_name: str = '', size: int = 24, tooltip: str = '', icon_size=None) -> QtWidgets.QPushButton` *(static)* — Build a square, flat, icon-only button for table cells / toolbars.
