# uitk — API Changes

_Diff vs the last release (origin/main @ f36ed12). Generated 2026-08-18._

## Added (3)

- `switchboard/utils.py::SwitchboardUtilsMixin.enable_when(self, ui, targets, trigger, condition=True, signal=None, value=None, invert=False)`
- `switchboard/utils.py::SwitchboardUtilsMixin.refresh_dependencies(self, ui) -> None`
- `widgets/separator.py::Separator.paintEvent(self, event) -> None`

## Signature changed (1)

- `switchboard/utils.py::SwitchboardUtilsMixin.toggle_multi`
  - was: `(self, ui, trigger=None, signal=None, **kwargs)`
  - now: `(self, ui, trigger=None, signal=None, apply_now=True, **kwargs)`
