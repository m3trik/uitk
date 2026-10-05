# uitk — API Changes

_Diff vs the last release (origin/main @ 82814a0)._

## Added (17)

- `managers/model_binding.py::ModelBinding(class)`
- `managers/model_binding.py::ModelBinding.bind(self, field: str, widget: QtWidgets.QWidget, getter: Optional[Callable[[], Any]] = None, setter: Optional[Callable[[Any], Any]] = None, signal: Optional[str] = None) -> QtWidgets.QWidget`
- `managers/model_binding.py::ModelBinding.refresh(self, *_args) -> None`
- `managers/window_height.py::WindowHeight.fit_host_later(widget) -> None`
- `widgets/form_rows.py::FormRows(class)`
- `widgets/form_rows.py::FormRows.add(self, x: Union[str, QtWidgets.QWidget, type, list, tuple], label: Optional[str] = None, hint: Optional[str] = None, tooltip: Optional[str] = None, companions=(), label_align=None, **kwargs) -> Union[QtWidgets.QWidget, list]`
- `widgets/form_rows.py::FormRows.add_section(self, title: str, **kwargs) -> 'FormRows'`
- `widgets/form_rows.py::FormRows.clear_rows(self) -> None`
- `widgets/form_rows.py::FormRows.row_widgets(self, widget: QtWidgets.QWidget) -> list`
- `widgets/form_rows.py::FormRows.rows_layout(self) -> QtWidgets.QFormLayout`
- `widgets/form_rows.py::FormRows.showEvent(self, event)`
- `widgets/messageBox.py::MessageBox.reading_time(cls, text: str) -> float`
- `widgets/messageBox.py::MessageBox.set_default_button(self, name: str) -> None`
- `widgets/messageBox.py::MessageBox.timeout(self)`
- `widgets/tableWidget.py::TableWidget.edit_cell_as(self, row: int, column: int, text: str, on_commit: Callable[[str], Any], select: Optional[Tuple[int, int]] = None) -> bool`
- `widgets/tableWidget.py::TableWidget.set_sorted_cell(self, row: int, column: int, text: str, key: Any, editable: bool = False) -> QtWidgets.QTableWidgetItem`
- `widgets/windowPanel.py::WindowPanel.form(self) -> FormRows`

## Deprecations (1)

_Live retirement debt, earliest deadline first. An **EXPIRED** row has outlived its window: delete the alias and its tests rather than moving the date. A **HELD** row is due by version, but its notice has not yet had its calendar window._

- **HELD** `bridge/parameters.py::Parameters.shader_type_spec` — remove in 1.7.0, not before 2026-10-26

## Signature changed (6)

- `switchboard/dialogs.py::SwitchboardDialogsMixin.message_box`
  - was: `(self, string, *buttons, location='topMiddle', timeout=3, background=0.75)`
  - now: `(self, string, *buttons, location='topMiddle', timeout='auto', background=0.75, default=None)`
- `widgets/column_config.py::ColumnConfig.attach`
  - was: `(cls, view: QtWidgets.QAbstractItemView, settings=None, settings_key: Optional[str] = None, locked: Iterable[int] = (), app: str = 'ColumnConfig', movable: bool = True, reorderable: bool = False) -> 'ColumnConfig'`
  - now: `(cls, view: QtWidgets.QAbstractItemView, settings=None, settings_key: Optional[str] = None, locked: Iterable[int] = (), app: str = 'ColumnConfig', movable: bool = True, reorderable: bool = False, hidden_by_default: Iterable[int] = ()) -> 'ColumnConfig'`
- `widgets/column_config.py::ColumnConfig.configure`
  - was: `(self, view: QtWidgets.QAbstractItemView, settings=None, settings_key: Optional[str] = None, locked: Iterable[int] = (), app: str = 'ColumnConfig', movable: bool = True, reorderable: bool = False) -> None`
  - now: `(self, view: QtWidgets.QAbstractItemView, settings=None, settings_key: Optional[str] = None, locked: Iterable[int] = (), app: str = 'ColumnConfig', movable: bool = True, reorderable: bool = False, hidden_by_default: Iterable[int] = ()) -> None`
- `widgets/optionBox/options/choice.py::ChoiceOption.choices`
  - was: `(self) -> List[Optional[Tuple[str, Any, str]]]`
  - now: `(self) -> List[Union[None, 'ChoiceOption.Section', Tuple[str, Any, str]]]`
- `widgets/tableWidget.py::TableWidget.enable_column_config`
  - was: `(self, settings=None, settings_key=None, locked=(), reorderable=False)`
  - now: `(self, settings=None, settings_key=None, locked=(), reorderable=False, hidden_by_default=())`
- `widgets/treeWidget.py::TreeWidget.enable_column_config`
  - was: `(self, settings=None, settings_key=None, locked=(), reorderable=False)`
  - now: `(self, settings=None, settings_key=None, locked=(), reorderable=False, hidden_by_default=())`
