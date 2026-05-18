# uitk — API Changes

_Diff vs prior baseline. Generated 2026-05-18._

## Removed (6)

- `handlers/external_tool_handler.py::ExternalToolHandler.config` — was `(self)`
- `handlers/external_tool_handler.py::ExternalToolHandler.instance` — was `(cls, switchboard: Switchboard = None, **kwargs)`
- `handlers/ui_handler.py::UiHandler.config` — was `(self)`
- `handlers/ui_handler.py::UiHandler.instance` — was `(cls, switchboard: Switchboard = None, **kwargs) -> 'UiHandler'`
- `widgets/editors/switchboard_browser.py::TagEditDialog` — was `(class)`
- `widgets/editors/switchboard_browser.py::TagEditDialog.tags` — was `(self) -> Set[str]`

## Added (37)

- `handlers/base_handler.py::BaseHandler(class)`
- `handlers/base_handler.py::BaseHandler.config(self)`
- `handlers/base_handler.py::BaseHandler.instance(cls, switchboard: 'Switchboard' = None, **kwargs)`
- `handlers/base_handler.py::LaunchableHandlerProtocol(class)`
- `handlers/base_handler.py::LaunchableHandlerProtocol.close(self, name: str) -> None`
- `handlers/base_handler.py::LaunchableHandlerProtocol.entries(self) -> Iterable['HandlerEntry']`
- `handlers/base_handler.py::LaunchableHandlerProtocol.is_visible(self, name: str) -> bool`
- `handlers/base_handler.py::LaunchableHandlerProtocol.launch(self, name: str, **options)`
- `handlers/external_tool_handler.py::ExternalToolHandler.close(self, name: str) -> None`
- `handlers/external_tool_handler.py::ExternalToolHandler.discover(self, groups: Optional[Iterable[str]] = None) -> int`
- `handlers/external_tool_handler.py::ExternalToolHandler.entries(self) -> Iterable[HandlerEntry]`
- `handlers/external_tool_handler.py::ExternalToolHandler.is_visible(self, name: str) -> bool`
- `handlers/external_tool_handler.py::ExternalToolHandler.save_tags(self, name: str, tags: Iterable[str]) -> None`
- `handlers/external_tool_handler.py::ExternalToolHandler.unregister(self, name: str) -> None`
- `handlers/handler_entry.py::HandlerEntry(class)`
- `handlers/handler_entry.py::HandlerEntry.all_tags(self) -> FrozenSet[str]`
- `handlers/handler_entry.py::HandlerEntry.editable_tags(self) -> bool`
- `handlers/ui_handler.py::UiHandler.close(self, name: str) -> None`
- `handlers/ui_handler.py::UiHandler.entries(self) -> Iterable[HandlerEntry]`
- `handlers/ui_handler.py::UiHandler.is_visible(self, name: str) -> bool`
- `handlers/ui_handler.py::UiHandler.launch(self, name: str, **options)`
- `handlers/ui_handler.py::UiHandler.save_tags(self, name: str, tags: Iterable[str]) -> None`
- `switchboard/_core.py::Switchboard.iter_handler_entries(self)`
- `widgets/editors/editor_panel.py::EditorPanel.tighten_sublayouts(self, spacing: int = 1) -> None`
- `widgets/editors/switchboard_browser.py::SwitchboardBrowser.hide_inherited_tags(self) -> bool`
- `widgets/editors/switchboard_browser.py::SwitchboardBrowser.showEvent(self, event) -> None`
- `widgets/editors/switchboard_browser.py::SwitchboardBrowserModel.entry_for_name(self, name: str) -> Optional[HandlerEntry]`
- `widgets/optionBox/options/_persistence.py::PersistedOption(class)`
- `widgets/optionBox/options/toggle.py::ToggleOption(class)`
- `widgets/optionBox/options/toggle.py::ToggleOption.is_on(self) -> bool`
- `widgets/optionBox/options/toggle.py::ToggleOption.set_on(self, value: bool, *, emit: bool = True) -> None`
- `widgets/optionBox/options/toggle.py::ToggleOption.setup_widget(self)`
- `widgets/optionBox/utils.py::OptionBoxManager.add_toggle(self, **kwargs)`
- `widgets/optionBox/utils.py::OptionBoxManager.set_toggle(self, *, icon: str = 'filter', icon_off: Optional[str] = None, tooltip_on: str = 'Enabled. Click to disable.', tooltip_off: str = 'Disabled. Click to enable.', initial: bool = True, disabled_color: Optional[str] = None, gated_widgets=(), settings_key=None, replace: bool = True, on_toggled=None)`
- `widgets/row_selection_delegate.py::RowSelectionBorderDelegate(class)`
- `widgets/row_selection_delegate.py::RowSelectionBorderDelegate.paint(self, painter, option, index)`
- `widgets/row_selection_delegate.py::RowSelectionBorderDelegate.paint_row_selection_border(self, painter, option, index)`

## Signature changed (2)

- `handlers/external_tool_handler.py::ExternalToolHandler.launch`
  - was: `(self, name: Optional[str] = None, *, module: Optional[str] = None, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: Optional[str] = None)`
  - now: `(self, name: Optional[str] = None, *, module: Optional[str] = None, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: Optional[str] = None, **_options)`
- `handlers/external_tool_handler.py::ExternalToolHandler.register`
  - was: `(self, name: str, *, module: str, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: str = 'subprocess') -> None`
  - now: `(self, name: str, *, module: str, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: str = 'subprocess', tags: Optional[Iterable[str]] = None) -> None`
