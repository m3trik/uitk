# uitk — API Changes

_Diff vs the last release (origin/main @ 1b0939e)._

## Added (24)

- `managers/host_exit_guard.py::HostExitGuard(class)`
- `managers/host_exit_guard.py::HostExitGuard.arm(cls, app=None) -> bool`
- `managers/host_exit_guard.py::HostExitGuard.note(cls, obj) -> None`
- `managers/host_exit_guard.py::HostExitGuard.release(cls) -> int`
- `widgets/column_config.py::ColumnConfig(class)`
- `widgets/column_config.py::ColumnConfig.attach(cls, view: QtWidgets.QAbstractItemView, settings=None, settings_key: Optional[str] = None, locked: Iterable[int] = (), app: str = 'ColumnConfig', movable: bool = True, reorderable: bool = False) -> 'ColumnConfig'`
- `widgets/column_config.py::ColumnConfig.build_menu(self) -> QtWidgets.QMenu`
- `widgets/column_config.py::ColumnConfig.can_hide(self, column: int) -> bool`
- `widgets/column_config.py::ColumnConfig.configure(self, view: QtWidgets.QAbstractItemView, settings=None, settings_key: Optional[str] = None, locked: Iterable[int] = (), app: str = 'ColumnConfig', movable: bool = True, reorderable: bool = False) -> None`
- `widgets/column_config.py::ColumnConfig.header(self) -> QtWidgets.QHeaderView`
- `widgets/column_config.py::ColumnConfig.header_of(view: QtWidgets.QAbstractItemView) -> QtWidgets.QHeaderView`
- `widgets/column_config.py::ColumnConfig.labels(self) -> List[str]`
- `widgets/column_config.py::ColumnConfig.of(cls, view: QtWidgets.QAbstractItemView) -> Optional['ColumnConfig']`
- `widgets/column_config.py::ColumnConfig.order(self) -> List[int]`
- `widgets/column_config.py::ColumnConfig.restore(self) -> None`
- `widgets/column_config.py::ColumnConfig.save(self) -> None`
- `widgets/column_config.py::ColumnConfig.set_hidden(self, column: int, hidden: bool = True) -> bool`
- `widgets/column_config.py::ColumnConfig.set_order(self, order: Iterable[int]) -> bool`
- `widgets/column_config.py::ColumnConfig.settings(self)`
- `widgets/column_config.py::ColumnConfig.show_menu(self, pos: QtCore.QPoint) -> None`
- `widgets/editors/preset_editor.py::PresetEditor.build_tree_menu(self, prefix: str)`
- `widgets/editors/preset_editor.py::PresetEditor.hide_presets(self, entries=None, flag: bool = True) -> int`
- `widgets/tableWidget.py::TableWidget.enable_column_config(self, settings=None, settings_key=None, locked=(), reorderable=False)`
- `widgets/tableWidget.py::TableWidget.restore_column_state(self)`

## Deprecations (1)

_Live retirement debt, earliest deadline first. An **EXPIRED** row has outlived its window: delete the alias and its tests rather than moving the date. A **HELD** row is due by version, but its notice has not yet had its calendar window._

- `bridge/parameters.py::Parameters.shader_type_spec` — remove in 1.7.0, not before 2026-10-26

## Signature changed (1)

- `widgets/treeWidget.py::TreeWidget.enable_column_config`
  - was: `(self, settings=None, settings_key=None)`
  - now: `(self, settings=None, settings_key=None, locked=(), reorderable=False)`
