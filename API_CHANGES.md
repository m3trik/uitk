# uitk — API Changes

_Diff vs the last release (origin/main @ 5752159)._

## Added (28)

- `widgets/comboBox.py::ComboBox.add_cells(self, cells: dict, data=None) -> int`
- `widgets/comboBox.py::ComboBox.begin_cell_edit(self, index=None) -> None`
- `widgets/comboBox.py::ComboBox.cell_editing(self) -> bool`
- `widgets/comboBox.py::ComboBox.cell_spec(self) -> list`
- `widgets/comboBox.py::ComboBox.cell_text(self, cells: dict) -> str`
- `widgets/comboBox.py::ComboBox.format_cell(spec: dict, value) -> str`
- `widgets/comboBox.py::ComboBox.item_cells(self, index: int)`
- `widgets/comboBox.py::ComboBox.resizeEvent(self, event)`
- `widgets/comboBox.py::ComboBox.set_cells(self, spec, cell_format=None) -> None`
- `widgets/comboBox.py::ComboBox.set_item_cells(self, index: int, cells: dict) -> None`
- `widgets/context_menu.py::ContextMenu(class)`
- `widgets/context_menu.py::ContextMenu.add(self, x, data=None, *, parent: Optional[QtWidgets.QWidget] = None, callback=None, **kwargs) -> QtWidgets.QWidget`
- `widgets/context_menu.py::ContextMenu.add_entries(self, entries, parent=None) -> list`
- `widgets/context_menu.py::ContextMenu.add_separator(self, title: str = '') -> QtWidgets.QWidget`
- `widgets/context_menu.py::ContextMenu.dispose(self) -> None`
- `widgets/context_menu.py::ContextMenu.exec_(self, global_pos: Optional[QtCore.QPoint] = None, dispose: bool = True) -> None`
- `widgets/context_menu.py::ContextMenu.keyPressEvent(self, event) -> None`
- `widgets/context_menu.py::ContextMenu.list(self) -> ExpandableList`
- `widgets/context_menu.py::ContextMenu.popup(self, global_pos: Optional[QtCore.QPoint] = None) -> None`
- `widgets/context_menu.py::MenuRow(class)`
- `widgets/context_menu.py::MenuRow.add_option_menu(self, tooltip: str = 'Options', **menu_config)`
- `widgets/context_menu.py::MenuRow.has_flyout(self) -> bool`
- `widgets/context_menu.py::MenuRow.option_menu(self)`
- `widgets/context_menu.py::MenuRow.paintEvent(self, event) -> None`
- `widgets/context_menu.py::MenuRow.resizeEvent(self, event) -> None`
- `widgets/context_menu.py::MenuRow.sizeHint(self) -> QtCore.QSize`
- `widgets/expandableList.py::ExpandableList.contains_items(self) -> bool`
- `widgets/sequencer/_timeline.py::TimelineView.default_context_entries(self, t: float) -> list`

## Signature changed (1)

- `widgets/sequencer/_sequencer.py::SequencerWidget.add_gap_overlay`
  - was: `(self, start: float, end: float, color: str = '#555555', alpha: int = 120, locked: bool = False, tail: bool = False)`
  - now: `(self, start: float, end: float, color: str = '#555555', alpha: int = 120, locked: bool = False, tail: bool = False, head: bool = False)`
