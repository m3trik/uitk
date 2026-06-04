# uitk — API Changes

_Diff vs prior baseline. Generated 2026-06-04._

## Added (5)

- `bridge/slots.py::BridgeSlotsBase.make_preset_store(self)`
- `bridge/slots.py::BridgeSlotsBase.reveal_folder(self, path) -> bool`
- `widgets/mixins/preset_manager.py::PresetManager.source(self, name: str) -> Optional[str]`
- `widgets/mixins/style_sheet.py::StyleSheet.get_variable_px(cls, name: str, theme: str = 'light', widget: QtWidgets.QWidget = None, default: Union[int, None] = None) -> Union[int, None]`
- `widgets/widgetComboBox.py::WidgetComboBox.item_spacing(self, value: int) -> None`

## Signature changed (2)

- `widgets/mixins/preset_manager.py::PresetManager.from_widgets`
  - was: `(cls, preset_dir, widgets: List[QtWidgets.QWidget]) -> 'PresetManager'`
  - now: `(cls, preset_dir, widgets: List[QtWidgets.QWidget], builtin_dir: Optional[Union[str, Path]] = None) -> 'PresetManager'`
- `widgets/mixins/preset_manager.py::PresetManager.setup`
  - was: `(self, preset_dir=None, widgets: Optional[List[QtWidgets.QWidget]] = None, on_loaded=None, metadata_provider: Optional[Callable[[], dict]] = None, on_metadata_loaded: Optional[Callable[[dict], None]] = None) -> 'PresetManager'`
  - now: `(self, preset_dir=None, widgets: Optional[List[QtWidgets.QWidget]] = None, on_loaded=None, metadata_provider: Optional[Callable[[], dict]] = None, on_metadata_loaded: Optional[Callable[[dict], None]] = None, builtin_dir: Optional[Union[str, Path]] = None, value_provider: Optional[Callable[[], Dict[str, Any]]] = None, value_applier: Optional[Callable[[Dict[str, Any]], int]] = None) -> 'PresetManager'`
