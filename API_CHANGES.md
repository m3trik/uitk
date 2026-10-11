# uitk — API Changes

_Diff vs the last release (origin/main @ 12bf794)._

## Added (57)

- `_bootstrap.py::Bootstrap.blurs() -> bool`
- `_bootstrap.py::Bootstrap.capture_output(log_file: str, force: bool = False) -> 'str | None'`
- `_bootstrap.py::Bootstrap.detach_console() -> bool`
- `_bootstrap.py::Bootstrap.report_uncaught(title: str, log_file: 'str | None' = None) -> None`
- `_bootstrap.py::Bootstrap.set_app_id(app_id: str) -> bool`
- `_bootstrap.py::Bootstrap.set_blur(widget: QtWidgets.QWidget, on: Union[bool, Callable[[QtWidgets.QWidget], bool]] = True) -> bool`
- `handlers/external_app_handler.py::ExternalAppHandler.can_create_shortcut(self, name: str) -> bool`
- `handlers/external_app_handler.py::ExternalAppHandler.create_shortcut(self, name: str, location: str = 'desktop') -> str`
- `handlers/external_app_handler.py::ExternalAppHandler.hub_for(self, name: str)`
- `managers/preset_manager.py::PresetManager.builtin_dir(self) -> Optional[Path]`
- `testing.py::TestSandbox.activated(cls)`
- `themes/style_sheet.py::StyleSheet.is_on(value) -> bool`
- `themes/style_sheet.py::StyleSheet.resolve_variable(cls, name: str, widget: QtWidgets.QWidget = None, default: str = '') -> str`
- `themes/style_sheet.py::StyleSheet.window_blur(cls, widget: QtWidgets.QWidget) -> bool`
- `widgets/editors/style_editor.py::SWITCH_TOKENS(constant)`
- `widgets/editors/style_editor.py::StyleEditor.on_switch_changed(self, name, on)`
- `widgets/editors/switchboard_browser/external_app_hub.py::ExternalAppHub(class)`
- `widgets/editors/switchboard_browser/external_app_hub.py::ExternalAppHub.create_shortcut(self, location: str = 'desktop', app: Optional[str] = None, python: Optional[str] = None) -> str`
- `widgets/editors/switchboard_browser/external_app_hub.py::ExternalAppHub.data_dir(self) -> str`
- `widgets/editors/switchboard_browser/external_app_hub.py::ExternalAppHub.log_file(self) -> str`
- `widgets/editors/switchboard_browser/external_app_hub.py::ExternalAppHub.of(cls, package: str) -> Optional['ExternalAppHub']`
- `widgets/editors/switchboard_browser/external_app_hub.py::ExternalAppHub.open(self, sb, app: Optional[str] = None)`
- `widgets/editors/switchboard_browser/external_app_hub.py::ExternalAppHub.run(self, argv: Optional[Sequence[str]] = None) -> int`
- `widgets/editors/switchboard_browser/launch.py::SHORTCUT_ACTIONS(constant)`
- `widgets/row_tags.py::RowTags(class)`
- `widgets/row_tags.py::RowTags.add_to_menu(self, menu, rows: Rows = None) -> QtWidgets.QWidget`
- `widgets/row_tags.py::RowTags.attach(cls, view: QtWidgets.QAbstractItemView, settings=None, settings_key: Optional[str] = None, app: str = 'RowTags', defaults: Optional[Mapping[str, Any]] = None, inherit: bool = True) -> 'RowTags'`
- `widgets/row_tags.py::RowTags.auto_tag(self, row: Row) -> Optional[str]`
- `widgets/row_tags.py::RowTags.color(self, slot: Optional[str]) -> Optional[str]`
- `widgets/row_tags.py::RowTags.colors(self) -> Dict[str, str]`
- `widgets/row_tags.py::RowTags.configure(self, view: QtWidgets.QAbstractItemView, settings=None, settings_key: Optional[str] = None, app: str = 'RowTags', defaults: Optional[Mapping[str, Any]] = None, inherit: bool = True) -> None`
- `widgets/row_tags.py::RowTags.detach(self) -> None`
- `widgets/row_tags.py::RowTags.edit_color(self, slot: str, pos: Optional[QtCore.QPoint] = None) -> bool`
- `widgets/row_tags.py::RowTags.eventFilter(self, obj, event)`
- `widgets/row_tags.py::RowTags.menu_row(self, rows: Rows = None, parent=None) -> QtWidgets.QWidget`
- `widgets/row_tags.py::RowTags.of(cls, view: QtWidgets.QAbstractItemView) -> Optional['RowTags']`
- `widgets/row_tags.py::RowTags.paintEvent(self, event)`
- `widgets/row_tags.py::RowTags.qcolor(self, slot: Optional[str]) -> Optional[QtGui.QColor]`
- `widgets/row_tags.py::RowTags.reset_colors(self) -> None`
- `widgets/row_tags.py::RowTags.selected_rows(self) -> List[QtCore.QModelIndex]`
- `widgets/row_tags.py::RowTags.set_color(self, slot: str, color: Any) -> None`
- `widgets/row_tags.py::RowTags.set_tag(self, rows: Iterable[Row], slot: Optional[str], auto: bool = False) -> List[QtCore.QModelIndex]`
- `widgets/row_tags.py::RowTags.settings(self)`
- `widgets/row_tags.py::RowTags.shown_tag(self, row: Row) -> Optional[str]`
- `widgets/row_tags.py::RowTags.slots(self) -> List[str]`
- `widgets/row_tags.py::RowTags.tag(self, row: Row) -> Optional[str]`
- `widgets/row_tags.py::RowTags.view(self) -> Optional[QtWidgets.QAbstractItemView]`
- `widgets/sequencer/_data.py::ClipData.key_hidden(self, index: int) -> bool`
- `widgets/sequencer/_data.py::ClipData.shown_key_times(self) -> List[float]`
- `widgets/sequencer/_draggable.py::HeldGeometryMixin(class)`
- `widgets/sequencer/_draggable.py::HeldGeometryMixin.sync(self) -> None`
- `widgets/tableWidget.py::TableWidget.commitData(self, editor)`
- `widgets/tableWidget.py::TableWidget.enable_row_tags(self, settings=None, settings_key=None, defaults=None)`
- `widgets/treeWidget.py::TreeWidget.elided_tooltips(self) -> bool`
- `widgets/treeWidget.py::TreeWidget.enable_row_tags(self, settings=None, settings_key=None, defaults=None, inherit=True)`
- `widgets/treeWidget.py::TreeWidget.is_elided(self, index) -> bool`
- `widgets/treeWidget.py::TreeWidget.item_tooltip(self, index, text: Optional[str]) -> Optional[str]`

## Deprecations (1)

_Live retirement debt, earliest deadline first. An **EXPIRED** row has outlived its window: delete the alias and its tests rather than moving the date. A **HELD** row is due by version, but its notice has not yet had its calendar window._

- **HELD** `bridge/parameters.py::Parameters.shader_type_spec` — remove in 1.7.0, not before 2026-10-26

## Moved (3)

_Still resolvable at the same call site -- hoisted to a base class or re-exported from another module. NOT a removal: no alias or minor bump is owed._

- `widgets/sequencer/_markers.py::MarkerItem.sync`
- `widgets/sequencer/_overlays.py::RangeHighlightItem.sync`
- `widgets/sequencer/_playhead.py::PlayheadItem.sync`

## Signature changed (1)

- `widgets/editors/color_editor.py::ColorEditorPopup.get_color`
  - was: `(cls, initial=None, parent=None, title='Colour', **editor_kwargs)`
  - now: `(cls, initial=None, parent=None, title='Colour', pos=None, **editor_kwargs)`
