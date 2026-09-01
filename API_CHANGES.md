# uitk — API Changes

_Diff vs the last release (origin/main @ b5d5d32)._

## Added (18)

- `handlers/ui_handler.py::UiHandler.pin_on_tap(self) -> bool`
- `switchboard/utils.py::SwitchboardUtilsMixin.value_from(self, ui, targets: Union[str, Any, List[Any]], sources: Union[str, Any, List[Any]], resolver: Callable[..., Any], signal: Optional[str] = None, value: Optional[Union[Callable[[Any], Any], Dict[str, Callable[[Any], Any]]]] = None) -> Callable[[], None]`
- `widgets/header.py::Header.claim_hide_as_tap(self, elapsed_ms) -> bool`
- `widgets/header.py::Header.pin_on_tap(self) -> bool`
- `widgets/header.py::Header.set_default_pin_on_tap(cls, value: bool) -> None`
- `widgets/mainWindow.py::MainWindow.visible_duration_ms(self) -> int`
- `widgets/sequencer/_draggable.py::DraggableItemMixin.sceneEvent(self, event)`
- `widgets/sequencer/_draggable.py::ItemRetirement(class)`
- `widgets/sequencer/_draggable.py::ItemRetirement.retire(cls, item) -> None`
- `widgets/sequencer/_ruler.py::RulerItem.selected_block(self) -> Optional[dict]`
- `widgets/sequencer/_sequencer.py::SequencerWidget.alignment_times(self, exclude_clip_ids=(), exclude_times=(), exclude_spans=()) -> List[float]`
- `widgets/sequencer/_sequencer.py::SequencerWidget.clear_snap_guides(self) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.nearest_alignment(self, time: float, candidates, tolerance: Optional[float] = None) -> Optional[float]`
- `widgets/sequencer/_sequencer.py::SequencerWidget.selected_shot(self) -> Optional[dict]`
- `widgets/sequencer/_sequencer.py::SequencerWidget.set_snap_guides(self, times) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.snap_guides_enabled(self) -> bool`
- `widgets/sequencer/_sequencer.py::SequencerWidget.snap_to_keys(self) -> bool`
- `widgets/sequencer/_transport_controls.py::TransportControls.set_range_fn(self, fn: Optional[Callable[[], tuple]]) -> None`

## Signature changed (4)

- `widgets/formPanel.py::FormPanel.add`
  - was: `(self, x, label: Optional[str] = None, hint: Optional[str] = None, tooltip: Optional[str] = None, companions=(), enabled_by: Optional[str] = None, **kwargs)`
  - now: `(self, x, label: Optional[str] = None, hint: Optional[str] = None, tooltip: Optional[str] = None, companions=(), label_align=None, enabled_by: Optional[str] = None, **kwargs)`
- `widgets/sequencer/_sequencer.py::SequencerWidget.add_gap_overlay`
  - was: `(self, start: float, end: float, color: str = '#555555', alpha: int = 120, locked: bool = False)`
  - now: `(self, start: float, end: float, color: str = '#555555', alpha: int = 120, locked: bool = False, tail: bool = False)`
- `widgets/sequencer/_transport_controls.py::TransportControls.attach_to_footer`
  - was: `(self, footer, side: str = 'right') -> None`
  - now: `(self, footer, side: str = 'center') -> None`
- `widgets/windowPanel.py::WindowPanel.add`
  - was: `(self, x: Union[str, QtWidgets.QWidget, type, list, tuple], label: Optional[str] = None, hint: Optional[str] = None, tooltip: Optional[str] = None, companions=(), **kwargs) -> Union[QtWidgets.QWidget, list]`
  - now: `(self, x: Union[str, QtWidgets.QWidget, type, list, tuple], label: Optional[str] = None, hint: Optional[str] = None, tooltip: Optional[str] = None, companions=(), label_align=None, **kwargs) -> Union[QtWidgets.QWidget, list]`
