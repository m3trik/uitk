# uitk — API Changes

_Diff vs the last release (origin/main @ 7851b0b)._

## Added (21)

- `switchboard/shortcuts.py::SwitchboardShortcutMixin.dispose_shortcuts(self) -> int`
- `widgets/marking_menu/_marking_menu.py::MarkingMenu.retire_all(cls) -> list`
- `widgets/mixins/text.py::RichTextFormatter.apply_line_breaks(cls, string: str) -> str`
- `widgets/sequencer/_clip.py::ClipItem.is_selectable(self) -> bool`
- `widgets/sequencer/_clip.py::ClipItem.sync_selectable(self) -> None`
- `widgets/sequencer/_keyframe.py::KeyScaleHandleItem(class)`
- `widgets/sequencer/_keyframe.py::KeyScaleHandleItem.boundingRect(self) -> QtCore.QRectF`
- `widgets/sequencer/_keyframe.py::KeyScaleHandleItem.cancel_drag(self) -> bool`
- `widgets/sequencer/_keyframe.py::KeyScaleHandleItem.hoverEnterEvent(self, event)`
- `widgets/sequencer/_keyframe.py::KeyScaleHandleItem.hoverLeaveEvent(self, event)`
- `widgets/sequencer/_keyframe.py::KeyScaleHandleItem.mouseMoveEvent(self, event)`
- `widgets/sequencer/_keyframe.py::KeyScaleHandleItem.mousePressEvent(self, event)`
- `widgets/sequencer/_keyframe.py::KeyScaleHandleItem.mouseReleaseEvent(self, event)`
- `widgets/sequencer/_keyframe.py::KeyScaleHandleItem.set_span(self, time: float, top: float, bottom: float) -> None`
- `widgets/sequencer/_keyframe.py::KeyScaleHandleItem.shape(self) -> QtGui.QPainterPath`
- `widgets/sequencer/_keyframe.py::KeyScaleHandleItem.side(self) -> str`
- `widgets/sequencer/_keyframe.py::KeyScaleHandleItem.time(self) -> float`
- `widgets/sequencer/_sequencer.py::SequencerWidget.clear_key_scale_handles(self) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.refresh_key_scale_handles(self) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.set_shift_held(self, held: bool) -> None`
- `widgets/sequencer/_timeline.py::TimelineView.focusOutEvent(self, event)`
