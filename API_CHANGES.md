# uitk — API Changes

_Diff vs prior baseline. Generated 2026-05-23._

## Removed (1)

- `widgets/sequencer/_data.py::hatch_brush` — was `(color: QtGui.QColor, spacing: int = HATCH_SPARSE, line_width: float = 1.0) -> QtGui.QBrush`

## Added (7)

- `widgets/editors/style_editor.py::StyleEditor.on_length_changed(self, name, value)`
- `widgets/mixins/style_sheet.py::StyleSheet.clear_caches(cls) -> None`
- `widgets/sequencer/_data.py::PatternSpec(class)`
- `widgets/sequencer/_data.py::PatternSpec.brush(self) -> QtGui.QBrush`
- `widgets/sequencer/_data.py::paint_pattern(painter: QtGui.QPainter, rect: QtCore.QRectF, spec: PatternSpec) -> None`
- `widgets/sequencer/_data.py::pattern_brush(style: str, color: QtGui.QColor, spacing: int = HATCH_MEDIUM, line_width: float = 1.0) -> QtGui.QBrush`
- `widgets/sequencer/_data.py::register_pattern(name: str, painter: PatternPainter) -> None`
