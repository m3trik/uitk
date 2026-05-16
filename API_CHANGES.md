# uitk — API Changes

_Diff vs prior baseline. Generated 2026-05-16._

## Added (11)

- `widgets/header.py::Header.setVersion(self, version)`
- `widgets/header.py::Header.toggle_fullscreen(self)`
- `widgets/header.py::Header.version(self)`
- `widgets/lineEdit.py::LineEditFormatMixin.clear_validator(self)`
- `widgets/lineEdit.py::LineEditFormatMixin.is_valid(self)`
- `widgets/lineEdit.py::LineEditFormatMixin.set_validator(self, validator, *, debounce_ms: int = 300, invalid_tooltip: str = 'Invalid', valid_tooltip=None, empty_tooltip=None, empty_is_valid: bool = True)`
- `widgets/lineEdit.py::LineEditFormatMixin.validate_now(self)`
- `widgets/mixins/icon_manager.py::IconManager.fit_icon(cls, widget, name: str, container_size, margin: int = 4, min_size: int = 8, color: str = None, auto_theme: bool = True) -> int`
- `widgets/mixins/icon_manager.py::IconManager.fit_size(container_size, margin: int = 4, min_size: int = 8) -> int`
- `widgets/mixins/icon_manager.py::IconManager.swap_icon(cls, widget, name: str, color: str = None, auto_theme: bool = True, fallback_size=(16, 16)) -> None`
- `widgets/optionBox/options/recent_values.py::RecentValuesOption.set_wrapped_widget(self, widget)`

## Signature changed (2)

- `widgets/footer.py::Footer.add_action_button`
  - was: `(self, text: str = '', icon_name: str = None, tooltip: str = '', callback=None) -> QtWidgets.QPushButton`
  - now: `(self, text: str = '', icon_name: str = None, tooltip: str = '', callback=None, rounded: bool = True) -> QtWidgets.QPushButton`
- `widgets/footer.py::Footer.add_widget`
  - was: `(self, widget: QtWidgets.QWidget, side: str = 'right', background: bool = False) -> QtWidgets.QWidget`
  - now: `(self, widget: QtWidgets.QWidget, side: str = 'right', background: bool = False, rounded: bool = True) -> QtWidgets.QWidget`
