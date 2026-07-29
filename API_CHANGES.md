# uitk — API Changes

_Diff vs prior baseline. Generated 2026-07-29._

## Signature changed (1)

- `bridge/slots.py::BridgeSlotsBase.ensure_optional_package`
  - was: `(self, spec: str, import_name: str = None, *, feature: str = None) -> bool`
  - now: `(self, spec: str, import_name: str = None, *, feature: str = None, reask: bool = False) -> bool`
