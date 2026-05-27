# uitk — API Changes

_Diff vs prior baseline. Generated 2026-05-27._

## Added (7)

- `widgets/header.py::Header.help_text(self)`
- `widgets/header.py::Header.set_help_text(self, text)`
- `widgets/header.py::Header.show_help(self)`
- `widgets/mixins/tooltip_mixin.py::hl(text: str, color: str = _C_ACCENT) -> str`
- `widgets/mixins/tooltip_mixin.py::kbd(*keys: str) -> str`
- `widgets/separator.py::Separator.minimumSizeHint(self) -> QtCore.QSize`
- `widgets/separator.py::Separator.sizeHint(self) -> QtCore.QSize`

## Signature changed (1)

- `widgets/mixins/tooltip_mixin.py::fmt`
  - was: `(title: str = None, body: str = None, bullets: list = None, steps: list = None, rows: list = None, sections: list = None) -> str`
  - now: `(title: str = None, body: str = None, bullets: list = None, steps: list = None, rows: list = None, sections: list = None, notes: list = None) -> str`
