# uitk — API Changes

_Diff vs the last release (origin/main @ f8148d3)._

## Added (38)

- `bridge/parameters.py::Parameters.affix_parts(value: Any, *, default: str = 'prefix')`
- `bridge/slots.py::BridgeSlotsBase.live_param_tooltip_blocks(self) -> Dict[str, Callable[[], str]]`
- `bridge/spec.py::KindFactory.affix_parts(value: Any, *, default: str = 'prefix') -> Tuple[str, str]`
- `bridge/spec.py::KindFactory.to_literal(spec: AttributeSpec, value: Any) -> Any`
- `switchboard/utils.py::SwitchboardUtilsMixin.form_dialog(fields, title: str = 'Options', parent: QtWidgets.QWidget = None, ok_text: Union[str, Callable] = 'OK', validate: Callable = None, message: str = '') -> Optional[dict]`
- `switchboard/utils.py::SwitchboardUtilsMixin.form_panel(fields, title: str = 'Options', parent: QtWidgets.QWidget = None, ok_text: Union[str, Callable] = 'OK', cancel_text: str = None, validate: Callable = None, message: str = '', help_text: str = '', on_run: Callable = None, apply_text: str = 'Apply', output: bool = True, min_width: int = 560, settings=None, settings_key: str = 'window_geometry')`
- `widgets/formPanel.py::FormPanel(class)`
- `widgets/formPanel.py::FormPanel.add(self, x, label: Optional[str] = None, hint: Optional[str] = None, tooltip: Optional[str] = None, companions=(), enabled_by: Optional[str] = None, **kwargs)`
- `widgets/formPanel.py::FormPanel.apply_pending(self) -> None`
- `widgets/formPanel.py::FormPanel.arm_apply(self, commit: Callable, note: str = None) -> None`
- `widgets/formPanel.py::FormPanel.clear_output(self) -> None`
- `widgets/formPanel.py::FormPanel.clear_rows(self) -> None`
- `widgets/formPanel.py::FormPanel.closeEvent(self, event)`
- `widgets/formPanel.py::FormPanel.disarm_apply(self) -> None`
- `widgets/formPanel.py::FormPanel.editor(self, name: str)`
- `widgets/formPanel.py::FormPanel.exec_panel(self) -> bool`
- `widgets/formPanel.py::FormPanel.hideEvent(self, event)`
- `widgets/formPanel.py::FormPanel.keyPressEvent(self, event)`
- `widgets/formPanel.py::FormPanel.logger(self)`
- `widgets/formPanel.py::FormPanel.pending_commit(self)`
- `widgets/formPanel.py::FormPanel.revalidate(self, *_args) -> str`
- `widgets/formPanel.py::FormPanel.run(self, values: dict = None) -> None`
- `widgets/formPanel.py::FormPanel.set_fields(self, fields) -> None`
- `widgets/formPanel.py::FormPanel.set_status(self, text: str, level: Optional[str] = None) -> None`
- `widgets/formPanel.py::FormPanel.set_values(self, values: dict) -> None`
- `widgets/formPanel.py::FormPanel.values(self) -> dict`
- `widgets/optionBox/options/_options.py::BaseOption.refresh(self) -> None`
- `widgets/optionBox/options/affix.py::AffixMode(class)`
- `widgets/optionBox/options/affix.py::AffixMode.convention(cls, convention_key: str, *, key: str = 'convention', label: str = 'Scene', icon: str = 'link', description: str = '') -> 'AffixMode'`
- `widgets/optionBox/options/affix.py::AffixMode.resolve(self, text: str, default: str = 'prefix') -> Tuple[str, str]`
- `widgets/optionBox/options/affix.py::AffixMode.text(self) -> Optional[str]`
- `widgets/optionBox/options/affix.py::AffixOption.mode_spec(self, key: Optional[str] = None) -> AffixMode`
- `widgets/optionBox/options/affix.py::AffixOption.modes(self) -> List[str]`
- `widgets/optionBox/options/affix.py::AffixOption.refresh(self) -> None`
- `widgets/optionBox/options/affix.py::AffixOption.restore_default(self) -> None`
- `widgets/windowPanel.py::WindowPanel.add(self, x: Union[str, QtWidgets.QWidget, type, list, tuple], label: Optional[str] = None, hint: Optional[str] = None, tooltip: Optional[str] = None, companions=(), **kwargs) -> Union[QtWidgets.QWidget, list]`
- `widgets/windowPanel.py::WindowPanel.clear_rows(self) -> None`
- `widgets/windowPanel.py::WindowPanel.rows_layout(self) -> QtWidgets.QFormLayout`

## Signature changed (1)

- `widgets/optionBox/utils.py::OptionBoxManager.set_affix`
  - was: `(self, *, default: str = 'auto', on_change=None, tooltip: Optional[str] = None, order=None, replace: bool = True)`
  - now: `(self, *, default: str = 'auto', modes=None, convention_key: Optional[str] = None, on_change=None, tooltip: Optional[str] = None, settings_key=None, order=None, replace: bool = True)`
