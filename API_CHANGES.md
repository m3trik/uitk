# uitk — API Changes

_Diff vs prior baseline. Generated 2026-07-29._

## Removed (2)

- `widgets/scriptOutput.py::ScriptOutput.event` — was `(self, event: QtCore.QEvent)`
- `widgets/scriptOutput.py::ScriptOutput.eventFilter` — was `(self, obj, event: QtCore.QEvent)`

## Added (18)

- `bridge/slots.py::BridgeSlotsBase.optional_package_available(spec: str, import_name: str = None) -> bool`
- `bridge/slots.py::BridgeSlotsBase.panel_log(self, message: str, level: str = 'info') -> None`
- `bridge/slots.py::BridgeSlotsBase.peek_bridge(self)`
- `handlers/ui_handler.py::UiHandler.default_persistence(self, ui) -> str`
- `handlers/ui_handler.py::UiHandler.is_persistence_explicit(self, ui, name: Optional[str] = None) -> bool`
- `handlers/ui_handler.py::UiHandler.persistence_override(self, name: str) -> Optional[str]`
- `handlers/ui_handler.py::UiHandler.pin_click_hides(self) -> bool`
- `handlers/ui_handler.py::UiHandler.reapply_persistence(self, name: Optional[str] = None) -> None`
- `handlers/ui_handler.py::UiHandler.resolve_persistence(self, ui, name: Optional[str] = None, context_default: Optional[str] = None) -> str`
- `handlers/ui_handler.py::UiHandler.set_persistence_override(self, name: str, mode: Optional[str]) -> None`
- `handlers/ui_handler.py::UiHandler.window_persistence(self) -> str`
- `widgets/header.py::Header.eventFilter(self, watched, event)`
- `widgets/header.py::Header.pin_on_drag_only(self) -> bool`
- `widgets/header.py::Header.set_default_pin_on_drag_only(cls, value: bool) -> None`
- `widgets/mixins/shortcut_guard.py::ShortcutGuardMixin(class)`
- `widgets/mixins/shortcut_guard.py::ShortcutGuardMixin.claims_shortcut(self, event: QtGui.QKeyEvent) -> bool`
- `widgets/mixins/shortcut_guard.py::ShortcutGuardMixin.event(self, event: QtCore.QEvent)`
- `widgets/mixins/shortcut_guard.py::ShortcutGuardMixin.is_read_only(self) -> bool`

## Signature changed (1)

- `bridge/slots.py::BridgeSlotsBase.ensure_optional_package`
  - was: `(self, spec: str, import_name: str = None, *, feature: str = None, reask: bool = False) -> bool`
  - now: `(self, spec: str, import_name: str = None, *, feature: str = None) -> bool`
