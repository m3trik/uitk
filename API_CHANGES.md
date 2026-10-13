# uitk — API Changes

_Diff vs the last release (origin/main @ bdde331)._

## Added (8)

- `_bootstrap.py::Bootstrap.set_shadow(widget: QtWidgets.QWidget, shadow: Union[ShadowSpec, None, Callable[[QtWidgets.QWidget], Optional[ShadowSpec]]]) -> bool`
- `_bootstrap.py::Bootstrap.shadows() -> bool`
- `themes/style_sheet.py::StyleSheet.base_style(cls) -> QtWidgets.QStyle`
- `themes/style_sheet.py::StyleSheet.cast_shadow(cls, widget: QtWidgets.QWidget) -> bool`
- `themes/style_sheet.py::StyleSheet.pin_base_style(cls, widget: QtWidgets.QWidget) -> None`
- `themes/style_sheet.py::StyleSheet.window_shadow(cls, widget: QtWidgets.QWidget) -> Optional[Tuple[QtGui.QColor, int, int]]`
- `widgets/editors/style_editor.py::EFFECT_SWITCHES(constant)`
- `widgets/editors/style_editor.py::EFFECT_TOKENS(constant)`

## Deprecations (1)

_Live retirement debt, earliest deadline first. An **EXPIRED** row has outlived its window: delete the alias and its tests rather than moving the date. A **HELD** row is due by version, but its notice has not yet had its calendar window._

- **HELD** `bridge/parameters.py::Parameters.shader_type_spec` — remove in 1.7.0, not before 2026-10-26
