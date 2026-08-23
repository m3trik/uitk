# uitk — API Changes

_Diff vs the last release (origin/main @ 803e126). Generated 2026-08-23._

## Added (7)

- `bridge/parameters.py::Parameters.carrier_spec(default: str = 'fbx', section: str = '') -> AttributeSpec`
- `switchboard/utils.py::SwitchboardUtilsMixin.text_from(self, ui, targets: Union[str, Any, List[Any]], sources: Union[str, Any, List[Any]], formatter: Callable[..., str], signal: Optional[str] = None, value: Optional[Union[Callable[[Any], Any], Dict[str, Callable[[Any], Any]]]] = None) -> Callable[[], None]`
- `widgets/editors/shortcut_editor/registry_editor.py::ShortcutEditor.open_over_facade(cls, facade_factory, *, existing=None, parent=None, hide_columns=(), window_title=None, collision_checker=None) -> 'ShortcutEditor'`
- `widgets/optionBox/options/_persistence.py::PersistedOption.host_suffix_for(widget) -> str`
- `widgets/optionBox/options/_persistence.py::PersistedOption.settings_for(app: str, key: str, widget=None) -> Optional['SettingsManager']`
- `widgets/windowPanel.py::WindowPanel.is_in_popup_context(self) -> bool`
- `widgets/windowPanel.py::WindowPanel.present(self, raise_window: bool = True) -> 'WindowPanel'`
