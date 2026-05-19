# uitk — API Changes

_Diff vs prior baseline. Generated 2026-05-19._

## Removed (11)

- `widgets/attributeWindow/_factory.py::AttributeSpec` — was `(class)`
- `widgets/attributeWindow/_factory.py::AttributeSpec.display_label` — was `(self) -> str`
- `widgets/attributeWindow/_factory.py::AttributeSpec.from_value` — was `(cls, key: str, value: Any, *, label: str = '') -> 'AttributeSpec'`
- `widgets/attributeWindow/_factory.py::KindHandler` — was `(class)`
- `widgets/attributeWindow/_factory.py::connect_changed` — was `(widget: QtWidgets.QWidget, callback: Callable[[Any], None]) -> None`
- `widgets/attributeWindow/_factory.py::get_handler` — was `(kind: str) -> KindHandler`
- `widgets/attributeWindow/_factory.py::infer_kind` — was `(value: Any) -> str`
- `widgets/attributeWindow/_factory.py::make_widget` — was `(spec: AttributeSpec, parent: Optional[QtWidgets.QWidget] = None) -> QtWidgets.QWidget`
- `widgets/attributeWindow/_factory.py::read_value` — was `(widget: QtWidgets.QWidget) -> Any`
- `widgets/attributeWindow/_factory.py::register_kind` — was `(name: str, handler: KindHandler) -> None`
- `widgets/attributeWindow/_factory.py::set_value` — was `(widget: QtWidgets.QWidget, value: Any) -> None`

## Added (38)

- `bridge/formatters.py::cli_raw(spec, value: Any) -> str`
- `bridge/formatters.py::js_literal(spec, value: Any) -> str`
- `bridge/formatters.py::lua_literal(spec, value: Any) -> str`
- `bridge/formatters.py::python_literal(spec, value: Any) -> str`
- `bridge/parameters.py::defaults(params: Dict[str, AttributeSpec]) -> Dict[str, Any]`
- `bridge/parameters.py::referenced_keys(script_text: str, params: Dict[str, AttributeSpec]) -> Set[str]`
- `bridge/parameters.py::render_context(values: Dict[str, Any], params: Dict[str, AttributeSpec], formatter: Callable[[AttributeSpec, Any], str] = python_literal) -> Dict[str, str]`
- `bridge/slots.py::BridgeSlotsBase(class)`
- `bridge/slots.py::BridgeSlotsBase.b000(self)`
- `bridge/slots.py::BridgeSlotsBase.bridge(self)`
- `bridge/slots.py::BridgeSlotsBase.clear_log(self) -> None`
- `bridge/slots.py::BridgeSlotsBase.cmb000_init(self, widget) -> None`
- `bridge/slots.py::BridgeSlotsBase.collect_param_values(self) -> Dict[str, Any]`
- `bridge/slots.py::BridgeSlotsBase.default_output_dir(self) -> str`
- `bridge/slots.py::BridgeSlotsBase.format_param_tooltip(self, spec: AttributeSpec) -> str`
- `bridge/slots.py::BridgeSlotsBase.list_template_modes(self) -> List[Tuple[str, str]]`
- `bridge/slots.py::BridgeSlotsBase.make_bridge(self)`
- `bridge/slots.py::BridgeSlotsBase.open_templates_folder(self) -> None`
- `bridge/slots.py::BridgeSlotsBase.params_module(self)`
- `bridge/slots.py::BridgeSlotsBase.refresh_templates(self) -> None`
- `bridge/slots.py::BridgeSlotsBase.require_output_dir(self) -> Optional[str]`
- `bridge/slots.py::BridgeSlotsBase.resolved_output_dir(self) -> str`
- `bridge/slots.py::BridgeSlotsBase.select_initial_template_index(self, pairs: List[Tuple[str, str]]) -> int`
- `bridge/slots.py::BridgeSlotsBase.template_description(self, template_path: Path) -> Optional[str]`
- `bridge/slots.py::BridgeSlotsBase.template_dir(self) -> Path`
- `bridge/spec.py::AttributeSpec(class)`
- `bridge/spec.py::AttributeSpec.display_label(self) -> str`
- `bridge/spec.py::AttributeSpec.from_value(cls, key: str, value: Any, *, label: str = '') -> 'AttributeSpec'`
- `bridge/spec.py::KindHandler(class)`
- `bridge/spec.py::connect_changed(widget: QtWidgets.QWidget, callback: Callable[[Any], None]) -> None`
- `bridge/spec.py::get_handler(kind: str) -> KindHandler`
- `bridge/spec.py::infer_kind(value: Any) -> str`
- `bridge/spec.py::make_widget(spec: AttributeSpec, parent: Optional[QtWidgets.QWidget] = None) -> QtWidgets.QWidget`
- `bridge/spec.py::read_value(widget: QtWidgets.QWidget) -> Any`
- `bridge/spec.py::register_kind(name: str, handler: KindHandler) -> None`
- `bridge/spec.py::set_value(widget: QtWidgets.QWidget, value: Any) -> None`
- `bridge/tooltip.py::format_param_tooltip(spec: AttributeSpec) -> str`
- `bridge/tooltip.py::template_description(template_path: Path) -> Optional[str]`
