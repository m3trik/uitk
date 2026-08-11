# uitk — API Changes

_Diff vs prior baseline. Generated 2026-08-11._

## Signature changed (1)

- `widgets/tableWidget.py::CellFormatMixin.set_column_truncation`
  - was: `(self, col, length=None, mode='start', insert='..')`
  - now: `(self, col, length=None, mode='start', insert='..', head=None)`
