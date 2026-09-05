# uitk — API Changes

_Diff vs the last release (origin/main @ 78f044c)._

## Removed (9)

- `switchboard/utils.py::OverrideCursorGuard` — was `(class)`
- `switchboard/utils.py::OverrideCursorGuard.apply` — was `(self) -> None`
- `switchboard/utils.py::OverrideCursorGuard.clear` — was `(self) -> None`
- `switchboard/utils.py::OverrideCursorGuard.holding` — was `(self) -> bool`
- `switchboard/utils.py::OverrideCursorGuard.holds` — was `(cls, shape) -> bool`
- `switchboard/utils.py::OverrideCursorGuard.is_stale` — was `(cls, cursor) -> bool`
- `switchboard/utils.py::OverrideCursorGuard.notify_stack_drained` — was `(cls) -> None`
- `switchboard/utils.py::OverrideCursorGuard.reconcile` — was `(cls) -> None`
- `switchboard/utils.py::OverrideCursorGuard.shape` — was `(self)`

## Added (36)

- `managers/cursor_manager.py::CursorManager(class)`
- `managers/cursor_manager.py::CursorManager.busy(shape=QtCore.Qt.WaitCursor, suspend_for_modals: bool = True)`
- `managers/cursor_manager.py::CursorManager.drain() -> None`
- `managers/cursor_manager.py::CursorManager.has_explicit_cursor(target) -> bool`
- `managers/cursor_manager.py::CursorManager.heal_hover(widget, global_pos) -> bool`
- `managers/cursor_manager.py::CursorManager.pop(cls, target) -> bool`
- `managers/cursor_manager.py::CursorManager.pop_stack(app=None) -> List[QtGui.QCursor]`
- `managers/cursor_manager.py::CursorManager.push(cls, target, shape) -> None`
- `managers/cursor_manager.py::CursorManager.push_stack(saved, app=None) -> None`
- `managers/cursor_manager.py::CursorManager.release(shape, app=None) -> bool`
- `managers/cursor_manager.py::CursorManager.suspend()`
- `managers/cursor_manager.py::OverrideCursorGuard(class)`
- `managers/cursor_manager.py::OverrideCursorGuard.apply(self) -> None`
- `managers/cursor_manager.py::OverrideCursorGuard.clear(self) -> None`
- `managers/cursor_manager.py::OverrideCursorGuard.holding(self) -> bool`
- `managers/cursor_manager.py::OverrideCursorGuard.holds(cls, shape) -> bool`
- `managers/cursor_manager.py::OverrideCursorGuard.is_stale(cls, cursor) -> bool`
- `managers/cursor_manager.py::OverrideCursorGuard.notify_stack_drained(cls) -> None`
- `managers/cursor_manager.py::OverrideCursorGuard.reconcile(cls) -> None`
- `managers/cursor_manager.py::OverrideCursorGuard.shape(self)`
- `managers/shortcut_manager.py::GlobalShortcut.isEnabled(self) -> bool`
- `switchboard/utils.py::SwitchboardUtilsMixin.busy_cursor(shape=QtCore.Qt.WaitCursor)`
- `widgets/footer.py::Footer.busy_indicator(self) -> QtWidgets.QLabel`
- `widgets/footer.py::Footer.is_busy(self) -> bool`
- `widgets/footer.py::Footer.set_busy(self, busy: bool) -> None`
- `widgets/header.py::Header.event(self, event)`
- `widgets/mixins/size_grip.py::CornerSizeGrip.event(self, event: QtCore.QEvent) -> bool`
- `widgets/sequencer/_overlays.py::RangeHighlightItem.begin_edge_drag(self, edge: str, scene_x: float) -> None`
- `widgets/sequencer/_overlays.py::RangeHighlightItem.finish_edge_drag(self) -> bool`
- `widgets/sequencer/_overlays.py::RangeHighlightItem.update_edge_drag(self, scene_x: float) -> None`
- `widgets/sequencer/_overlays.py::RangeHighlightItem.zone_at(self, scene_x: float) -> str`
- `widgets/sequencer/_ruler.py::RulerItem.set_content_left(self, left: float) -> None`
- `widgets/sequencer/_ruler.py::RulerItem.set_key_ticks(self, times) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.resizeEvent(self, event: QtGui.QResizeEvent) -> None`
- `widgets/sequencer/_timeline.py::TimelineView.add_default_context_actions(self, menu, t: float)`
- `widgets/sequencer/_timeline.py::TimelineView.content_time_bounds(self) -> tuple`

## Signature changed (7)

- `switchboard/utils.py::SwitchboardUtilsMixin.progress`
  - was: `(self, ui=None, total: Optional[int] = None, text: str = '')`
  - now: `(self, ui=None, total: Optional[int] = None, text: str = '', busy: Optional[bool] = None)`
- `widgets/footer.py::Footer.progress`
  - was: `(self, total: Optional[int] = None, text: str = '') -> 'FooterProgressContext'`
  - now: `(self, total: Optional[int] = None, text: str = '', busy: Optional[bool] = None) -> 'FooterProgressContext'`
- `widgets/footer.py::Footer.start_progress`
  - was: `(self, total: Optional[int] = None, text: str = '') -> Callable[[Optional[int], Optional[str]], bool]`
  - now: `(self, total: Optional[int] = None, text: str = '', busy: Optional[bool] = None) -> Callable[[Optional[int], Optional[str]], bool]`
- `widgets/lineEdit.py::LineEditFormatMixin.set_validator`
  - was: `(self, validator, *, debounce_ms: int = 300, invalid_tooltip: str = 'Invalid', valid_tooltip=None, empty_tooltip=None, empty_is_valid: bool = True)`
  - now: `(self, validator, *, debounce_ms: int = 300, invalid_tooltip: str = 'Invalid', valid_tooltip=None, empty_tooltip=None, empty_is_valid: bool = True, deferred=None, pending_tooltip: str = 'Checking…')`
- `widgets/lineEdit.py::LineEditFormatMixin.validate_now`
  - was: `(self)`
  - now: `(self, run_deferred: bool = True)`
- `widgets/optionBox/options/affix.py::AffixMode.convention`
  - was: `(cls, convention_key: str, *, key: str = 'convention', label: str = 'Scene', icon: str = 'link', description: str = '') -> 'AffixMode'`
  - now: `(cls, convention_key: Union[str, Callable[[], str]], *, key: str = 'convention', label: str = 'Scene', icon: str = 'link', description: str = '') -> 'AffixMode'`
- `widgets/optionBox/utils.py::OptionBoxManager.set_affix`
  - was: `(self, *, default: str = 'auto', modes=None, convention_key: Optional[str] = None, on_change=None, tooltip: Optional[str] = None, settings_key=None, order=None, replace: bool = True)`
  - now: `(self, *, default: str = 'auto', modes=None, convention_key=None, on_change=None, tooltip: Optional[str] = None, settings_key=None, order=None, replace: bool = True)`
