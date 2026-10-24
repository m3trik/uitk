# uitk — API Changes

_Diff vs the last release (origin/main @ ea54816)._

## Added (3)

- `widgets/mainWindow.py::MainWindow.changeEvent(self, event) -> None`
- `widgets/table_actions.py::TableActions.clear(self, row: int, col: int) -> None`
- `widgets/textViewBox.py::TextViewBox.keyPressEvent(self, event)`

## Deprecations (1)

_Live retirement debt, earliest deadline first. An **EXPIRED** row has outlived its window: delete the alias and its tests rather than moving the date. A **HELD** row is due by version, but its notice has not yet had its calendar window._

- **HELD** `bridge/parameters.py::Parameters.shader_type_spec` — remove in 1.7.0, not before 2026-10-26

## Signature changed (2)

- `_bootstrap.py::Bootstrap.set_translucent`
  - was: `(widget, on: bool = True) -> bool`
  - now: `(widget, on: bool = True, opaque_full_screen: bool = True) -> bool`
- `switchboard/dialogs.py::SwitchboardDialogsMixin.text_view_dialog`
  - was: `(self, text: str = '', *buttons, title: str = '', size=(640, 400), monospace: bool = False, word_wrap: bool = True, background=False, parent=None, link_handler=None)`
  - now: `(self, text: str = '', *buttons, title: str = '', size=(640, 400), monospace: bool = False, word_wrap: bool = True, background=False, parent=None, link_handler=None, on_refresh: Optional[Callable[[], Any]] = None)`
