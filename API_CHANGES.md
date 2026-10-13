# uitk — API Changes

_Diff vs the last release (origin/main @ 40c18d4)._

## Added (4)

- `widgets/comboBox.py::ComboBox.wheelEvent(self, event)`
- `widgets/comboBox.py::ComboBox.wheel_selects(self) -> bool`
- `widgets/treeWidget.py::TreeWidget.row_tooltip(self, item) -> Optional[str]`
- `widgets/treeWidget.py::TreeWidget.set_row_tooltip(self, item, text: Optional[str]) -> None`

## Deprecations (1)

_Live retirement debt, earliest deadline first. An **EXPIRED** row has outlived its window: delete the alias and its tests rather than moving the date. A **HELD** row is due by version, but its notice has not yet had its calendar window._

- **HELD** `bridge/parameters.py::Parameters.shader_type_spec` — remove in 1.7.0, not before 2026-10-26
