# uitk — API Changes

_Diff vs prior baseline. Generated 2026-08-07._

## Added (10)

- `switchboard/utils.py::OverrideCursorGuard(class)`
- `switchboard/utils.py::OverrideCursorGuard.apply(self) -> None`
- `switchboard/utils.py::OverrideCursorGuard.clear(self) -> None`
- `switchboard/utils.py::OverrideCursorGuard.holding(self) -> bool`
- `switchboard/utils.py::OverrideCursorGuard.holds(cls, shape) -> bool`
- `switchboard/utils.py::OverrideCursorGuard.is_stale(cls, cursor) -> bool`
- `switchboard/utils.py::OverrideCursorGuard.notify_stack_drained(cls) -> None`
- `switchboard/utils.py::OverrideCursorGuard.reconcile(cls) -> None`
- `switchboard/utils.py::OverrideCursorGuard.shape(self)`
- `widgets/marking_menu/overlay.py::Overlay.end_gesture(self) -> None`

## Signature changed (1)

- `widgets/marking_menu/overlay.py::Path.reset`
  - was: `(self)`
  - now: `(self, pos: QtCore.QPoint = None)`
