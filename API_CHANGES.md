# uitk — API Changes

_Diff vs prior baseline. Generated 2026-06-21._

## Added (8)

- `handlers/ui_handler.py::UiHandler.can_resolve(self, name: str) -> bool`
- `switchboard/widgets.py::SwitchboardWidgetMixin.ui_name_resolves(self, name: str) -> bool`
- `widgets/comboBox.py::ComboBox.addItem(self, *args, **kwargs)`
- `widgets/comboBox.py::ComboBox.addItems(self, *args, **kwargs)`
- `widgets/comboBox.py::ComboBox.clear(self)`
- `widgets/comboBox.py::ComboBox.insertItem(self, *args, **kwargs)`
- `widgets/comboBox.py::ComboBox.insertItems(self, *args, **kwargs)`
- `widgets/mainWindow.py::MainWindow.run_when_ready(self, callback: Callable[[], Any]) -> None`
