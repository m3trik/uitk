# uitk — API Changes

_Diff vs the last release (origin/main @ 7851b0b)._

## Added (22)

- `switchboard/shortcuts.py::SwitchboardShortcutMixin.dispose_shortcuts(self) -> int`
- `widgets/marking_menu/_marking_menu.py::MarkingMenu.retire_all(cls) -> list`
- `widgets/mixins/text.py::RichTextFormatter.apply_line_breaks(cls, string: str) -> str`
- `widgets/sequencer/_clip.py::ClipItem.is_selectable(self) -> bool`
- `widgets/sequencer/_clip.py::ClipItem.sync_selectable(self) -> None`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem(class)`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem.boundingRect(self) -> QtCore.QRectF`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem.hi(self) -> float`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem.hoverEnterEvent(self, event)`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem.hoverLeaveEvent(self, event)`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem.lo(self) -> float`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem.mouseMoveEvent(self, event)`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem.mousePressEvent(self, event)`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem.mouseReleaseEvent(self, event)`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem.paint(self, painter: QtGui.QPainter, option, widget=None)`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem.set_span(self, lo: float, hi: float, top: float, bottom: float) -> None`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem.shape(self) -> QtGui.QPainterPath`
- `widgets/sequencer/_keyframe.py::KeyScaleBoxItem.side(self) -> str`
- `widgets/sequencer/_sequencer.py::SequencerWidget.clear_key_scale_box(self) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.refresh_key_scale_box(self) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.set_shift_held(self, held: bool) -> None`
- `widgets/sequencer/_timeline.py::TimelineView.focusOutEvent(self, event)`
