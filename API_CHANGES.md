# uitk — API Changes

_Diff vs the last release (origin/main @ 8004002)._

## Signature changed (1)

- `switchboard/_core.py::Switchboard.register`
  - was: `(self, ui_location=None, slot_location=None, widget_location=None, icon_location=None, base_dir=1, recursive: bool = False, validate=1, tags=None)`
  - now: `(self, ui_location=None, slot_location=None, widget_location=None, icon_location=None, base_dir=1, recursive: bool = False, validate=1, tags=None, exclude=None)`
