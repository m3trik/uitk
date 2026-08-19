# uitk — API Changes

_Diff vs the last release (origin/main @ 8f2d105). Generated 2026-08-19._

## Added (14)

- `bridge/slots.py::BridgeSlotsBase.live_param_tooltips(self) -> Dict[str, Callable[[], str]]`
- `switchboard/widgets.py::SwitchboardWidgetMixin.gate(self, widget, available, reason: str = '') -> bool`
- `switchboard/widgets.py::SwitchboardWidgetMixin.recheck_gates(self) -> int`
- `switchboard/widgets.py::SwitchboardWidgetMixin.unmet_policy(self) -> str`
- `widgets/comboBox.py::ComboBox.begin_rename(self)`
- `widgets/comboBox.py::ComboBox.mouseDoubleClickEvent(self, event)`
- `widgets/comboBox.py::ComboBox.mousePressEvent(self, event)`
- `widgets/messageBox.py::MessageBox.as_prompt(self)`
- `widgets/mixins/tooltip_mixin.py::TooltipFormat.stored_items(items, *, title: str = None, body: str = None, formatter=None, max_items: int = None, noun: str = 'item(s)', empty_text: str = None, notes: list = None) -> str`
- `widgets/optionBox/options/_options.py::BaseOption.restore_default(self) -> None`
- `widgets/optionBox/options/_options.py::BaseOption.sibling_options(self)`
- `widgets/optionBox/options/toggle.py::BinaryToggleOption.restore_default(self) -> None`
- `widgets/optionBox/utils.py::OptionBoxManager.get_options(self)`
- `widgets/optionBox/utils.py::OptionBoxManager.restore_option_defaults(self)`

## Signature changed (2)

- `bridge/slots.py::BridgeSlotsBase.require_output_dir`
  - was: `(self) -> Optional[str]`
  - now: `(self, mode: Optional[str] = None) -> Optional[str]`
- `switchboard/utils.py::SwitchboardUtilsMixin.link_spinboxes`
  - was: `(self, ui, widgets=None, *, types=(QtWidgets.QAbstractSpinBox,), skip=(), icon: str = 'lock', icon_off: str = 'unlock', tooltip_on: str = 'Linked. Changing this shifts the other linked fields by the same amount. Click to unlink.', tooltip_off: str = 'Unlinked. Click to link this field so it moves with the others.', initial: bool = False, **set_toggle_kwargs)`
  - now: `(self, ui, widgets=None, *, types=(QtWidgets.QAbstractSpinBox,), skip=(), icon: str = 'lock', icon_off: str = 'unlock', tooltip_on: str = 'Linked. Changing this shifts the other linked fields by the same amount. Click to unlink.', tooltip_off: str = 'Unlinked. Click to link this field so it moves with the others.', initial: bool = False, active_color: str = _LOCK_ACTIVE_COLOR, disabled_color: str = _LOCK_INACTIVE_COLOR, **set_toggle_kwargs)`
