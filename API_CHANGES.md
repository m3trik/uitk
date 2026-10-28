# uitk — API Changes

_Diff vs the last release (origin/main @ 8004002)._

## Moved out (11)

- `widgets/sequencer/_ruler.py::RulerItem.clear_shot_blocks` → `tentacle.slots.tools._shot_sequencer.shot_layer.ShotLayer.clear_shot_blocks` (from 1.9.0)
- `widgets/sequencer/_ruler.py::RulerItem.selected_block` → `tentacle.slots.tools._shot_sequencer.shot_layer.ShotLayer.selected_shot` (from 1.9.0)
- `widgets/sequencer/_ruler.py::RulerItem.set_shot_blocks` → `tentacle.slots.tools._shot_sequencer.shot_layer.ShotLayer.set_shot_blocks` (from 1.9.0)
- `widgets/sequencer/_ruler.py::RulerItem.shot_block_at` → `tentacle.slots.tools._shot_sequencer.shot_layer.ShotLayer.shot_block_at` (from 1.9.0)
- `widgets/sequencer/_sequencer.py::SequencerWidget.add_gap_overlay` → `tentacle.slots.tools._shot_sequencer.shot_layer.ShotLayer.add_gap_overlay` (from 1.9.0)
- `widgets/sequencer/_sequencer.py::SequencerWidget.clear_gap_overlays` → `tentacle.slots.tools._shot_sequencer.shot_layer.ShotLayer.clear_gap_overlays` (from 1.9.0)
- `widgets/sequencer/_sequencer.py::SequencerWidget.clear_shot_blocks` → `tentacle.slots.tools._shot_sequencer.shot_layer.ShotLayer.clear_shot_blocks` (from 1.9.0)
- `widgets/sequencer/_sequencer.py::SequencerWidget.selected_shot` → `tentacle.slots.tools._shot_sequencer.shot_layer.ShotLayer.selected_shot` (from 1.9.0)
- `widgets/sequencer/_sequencer.py::SequencerWidget.set_all_gap_overlays_locked` → `tentacle.slots.tools._shot_sequencer.shot_layer.ShotLayer.set_all_gap_overlays_locked` (from 1.9.0)
- `widgets/sequencer/_sequencer.py::SequencerWidget.set_shot_blocks` → `tentacle.slots.tools._shot_sequencer.shot_layer.ShotLayer.set_shot_blocks` (from 1.9.0)
- `widgets/sequencer/_sequencer.py::SequencerWidget.show_gap_overlays` → `tentacle.slots.tools._shot_sequencer.shot_layer.ShotLayer.show_gap_overlays` (from 1.9.0)

## Added (25)

- `widgets/sequencer/_data.py::MenuUtils.menu_exec_pos(event) -> QtCore.QPoint`
- `widgets/sequencer/_data.py::MenuUtils.styled_menu(parent=None) -> QtWidgets.QMenu`
- `widgets/sequencer/_layer.py::SequencerLayer(class)`
- `widgets/sequencer/_layer.py::SequencerLayer.claims_press(self, scene_pos) -> bool`
- `widgets/sequencer/_layer.py::SequencerLayer.clear(self) -> None`
- `widgets/sequencer/_layer.py::SequencerLayer.context_entries(self, time: float, entries: List[Optional[dict]]) -> List[Optional[dict]]`
- `widgets/sequencer/_layer.py::SequencerLayer.gesture_group_at(self, viewport_pos) -> Optional[str]`
- `widgets/sequencer/_layer.py::SequencerLayer.legend(self, editor: str, rows: Tuple[Gesture, ...]) -> Sequence[Gesture]`
- `widgets/sequencer/_layer.py::SequencerLayer.menu_zone(self, zone: str, time: float) -> str`
- `widgets/sequencer/_layer.py::SequencerLayer.mouse_move(self, event) -> bool`
- `widgets/sequencer/_layer.py::SequencerLayer.mouse_press(self, event) -> bool`
- `widgets/sequencer/_layer.py::SequencerLayer.mouse_release(self, event) -> bool`
- `widgets/sequencer/_layer.py::SequencerLayer.paint_lane(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None`
- `widgets/sequencer/_layer.py::SequencerLayer.relayout(self) -> None`
- `widgets/sequencer/_layer.py::SequencerLayer.time_bounds(self) -> Optional[Tuple[float, float]]`
- `widgets/sequencer/_ruler.py::RulerItem.set_height(self, height: float) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.add_layer(self, layer: SequencerLayer) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.add_track_item(self, item: QtWidgets.QGraphicsItem) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.content_span(self) -> Tuple[float, float]`
- `widgets/sequencer/_sequencer.py::SequencerWidget.layer(self, name: str) -> SequencerLayer`
- `widgets/sequencer/_sequencer.py::SequencerWidget.range_highlight_item(self) -> Optional[RangeHighlightItem]`
- `widgets/sequencer/_sequencer.py::SequencerWidget.refresh_extent(self) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.remove_track_item(self, item: QtWidgets.QGraphicsItem) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.timeline(self) -> TimelineView`
- `widgets/sequencer/_timeline.py::TimelineView.hit_zone(self, viewport_y: float) -> str`

## Signature changed (1)

- `switchboard/_core.py::Switchboard.register`
  - was: `(self, ui_location=None, slot_location=None, widget_location=None, icon_location=None, base_dir=1, recursive: bool = False, validate=1, tags=None)`
  - now: `(self, ui_location=None, slot_location=None, widget_location=None, icon_location=None, base_dir=1, recursive: bool = False, validate=1, tags=None, exclude=None)`
