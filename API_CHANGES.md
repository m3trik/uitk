# uitk — API Changes

_Diff vs the last release (origin/main @ 7ab4bde)._

## Added (41)

- `managers/shortcut_manager.py::ShortcutManager.add_gesture(self, group: str, keys: str, description: str) -> None`
- `managers/shortcut_manager.py::ShortcutManager.overlay(self, host: QtWidgets.QWidget, anchor: str = 'bottom-right', max_keys: int = 4)`
- `widgets/mixins/wheel_step.py::SpinBoxAdjustingMixin(class)`
- `widgets/mixins/wheel_step.py::SpinBoxAdjustingMixin.adjusting(self) -> bool`
- `widgets/mixins/wheel_step.py::SpinBoxAdjustingMixin.focusOutEvent(self, event) -> None`
- `widgets/mixins/wheel_step.py::SpinBoxAdjustingMixin.keyPressEvent(self, event) -> None`
- `widgets/mixins/wheel_step.py::SpinBoxAdjustingMixin.mousePressEvent(self, event) -> None`
- `widgets/mixins/wheel_step.py::SpinBoxAdjustingMixin.mouseReleaseEvent(self, event) -> None`
- `widgets/sequencer/_clip.py::ClipItem.keys_editable(self) -> bool`
- `widgets/sequencer/_data.py::CurveUtils.unmap_value(rect_top: float, rect_height: float, val_min: float, val_max: float, y: float) -> float`
- `widgets/sequencer/_keyframe.py::KeyframeItem.contextMenuEvent(self, event)`
- `widgets/sequencer/_keyframe.py::KeyframeItem.is_broken(self, index: Optional[int] = None) -> bool`
- `widgets/sequencer/_keyframe.py::KeyframeItem.itemChange(self, change, value)`
- `widgets/sequencer/_keyframe.py::TangentHandleItem(class)`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.contextMenuEvent(self, event)`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.control_point(self) -> Optional[tuple]`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.hoverEnterEvent(self, event)`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.hoverLeaveEvent(self, event)`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.key(self) -> KeyframeItem`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.mouseMoveEvent(self, event)`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.mousePressEvent(self, event)`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.mouseReleaseEvent(self, event)`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.paint(self, painter: QtGui.QPainter, option, widget=None)`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.shape(self) -> QtGui.QPainterPath`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.side(self) -> str`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.slot(self) -> tuple`
- `widgets/sequencer/_sequencer.py::SequencerWidget.ctrl_held_at_press(self) -> bool`
- `widgets/sequencer/_sequencer.py::SequencerWidget.record_press_modifiers(self, modifiers) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.select_keys(self, wanted: List[dict], replace: bool = True) -> int`
- `widgets/sequencer/_sequencer.py::SequencerWidget.selected_keys(self) -> List[dict]`
- `widgets/sequencer/_sequencer.py::SequencerWidget.shortcut_overlay(self)`
- `widgets/sequencer/_sequencer.py::SequencerWidget.shortcut_overlay_visible(self) -> bool`
- `widgets/sequencer/_sequencer.py::SequencerWidget.show_key_menu(self, global_pos) -> bool`
- `widgets/sequencer/_timeline.py::TimelineView.leaveEvent(self, event)`
- `widgets/shortcut_overlay.py::ShortcutOverlay(class)`
- `widgets/shortcut_overlay.py::ShortcutOverlay.context(self) -> Optional[str]`
- `widgets/shortcut_overlay.py::ShortcutOverlay.eventFilter(self, obj, event)`
- `widgets/shortcut_overlay.py::ShortcutOverlay.paintEvent(self, event)`
- `widgets/shortcut_overlay.py::ShortcutOverlay.refresh(self) -> None`
- `widgets/shortcut_overlay.py::ShortcutOverlay.set_context(self, group: Optional[str]) -> None`
- `widgets/shortcut_overlay.py::ShortcutOverlay.shown_group(self) -> Optional[str]`
