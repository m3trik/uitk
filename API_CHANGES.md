# uitk — API Changes

_Diff vs prior baseline. Generated 2026-05-17._

## Removed (21)

- `widgets/attributeWindow.py::AttributeWindow` — was `(class)`
- `widgets/attributeWindow.py::AttributeWindow.add_attributes` — was `(self, attributes, value=None)`
- `widgets/attributeWindow.py::AttributeWindow.add_to_layout` — was `(self, label, widget)`
- `widgets/attributeWindow.py::AttributeWindow.clear_ui_elements` — was `(self)`
- `widgets/attributeWindow.py::AttributeWindow.configure_widget` — was `(self, widget, set_value_method, get_value_method, signal_name, attribute_name)`
- `widgets/attributeWindow.py::AttributeWindow.create_set_attribute_func_wrapper` — was `(self, set_attribute_func)`
- `widgets/attributeWindow.py::AttributeWindow.create_widget` — was `(self, widget_class, attribute_value)`
- `widgets/attributeWindow.py::AttributeWindow.default_get_attribute_func` — was `(self)`
- `widgets/attributeWindow.py::AttributeWindow.default_set_attribute_func` — was `(self, name, value)`
- `widgets/attributeWindow.py::AttributeWindow.emit_composite_value_changed` — was `(self, attribute_name)`
- `widgets/attributeWindow.py::AttributeWindow.emit_value_changed` — was `(self, widget)`
- `widgets/attributeWindow.py::AttributeWindow.get_widget_info` — was `(self, attribute_value)`
- `widgets/attributeWindow.py::AttributeWindow.initialize_ui` — was `(self)`
- `widgets/attributeWindow.py::AttributeWindow.is_type_supported` — was `(attribute_type)`
- `widgets/attributeWindow.py::AttributeWindow.is_valid_attribute` — was `(attr_name)`
- `widgets/attributeWindow.py::AttributeWindow.on_button_clicked` — was `(self, button, checked)`
- `widgets/attributeWindow.py::AttributeWindow.on_label_toggled` — was `(self, label)`
- `widgets/attributeWindow.py::AttributeWindow.refresh_attributes` — was `(self)`
- `widgets/attributeWindow.py::AttributeWindow.setup_label` — was `(self, attribute_name)`
- `widgets/attributeWindow.py::AttributeWindow.setup_widget` — was `(self, widget_class, set_value_method, attribute_value, get_value_method, signal_name, attribute_name)`
- `widgets/attributeWindow.py::AttributeWindow.showEvent` — was `(self, event)`

## Added (35)

- `handlers/external_tool_handler.py::ExternalToolHandler(class)`
- `handlers/external_tool_handler.py::ExternalToolHandler.config(self)`
- `handlers/external_tool_handler.py::ExternalToolHandler.instance(cls, switchboard: Switchboard = None, **kwargs)`
- `handlers/external_tool_handler.py::ExternalToolHandler.is_registered(self, name: str) -> bool`
- `handlers/external_tool_handler.py::ExternalToolHandler.launch(self, name: Optional[str] = None, *, module: Optional[str] = None, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: Optional[str] = None)`
- `handlers/external_tool_handler.py::ExternalToolHandler.register(self, name: str, *, module: str, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: str = 'subprocess') -> None`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow(class)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.add_attribute_spec(self, spec)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.add_attributes(self, attributes, value=None)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.add_to_layout(self, label, widget)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.clear_ui_elements(self)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.create_set_attribute_func_wrapper(self, set_attribute_func)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.default_get_attribute_func(self)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.default_set_attribute_func(self, name, value)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.emit_composite_value_changed(self, attribute_name)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.emit_value_changed(self, widget)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.initialize_ui(self)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.is_type_supported(attribute_type)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.is_valid_attribute(attr_name)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.on_button_clicked(self, button, checked)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.on_label_toggled(self, label)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.refresh_attributes(self)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.setup_label(self, attribute_name)`
- `widgets/attributeWindow/_attributeWindow.py::AttributeWindow.showEvent(self, event)`
- `widgets/attributeWindow/_factory.py::AttributeSpec(class)`
- `widgets/attributeWindow/_factory.py::AttributeSpec.display_label(self) -> str`
- `widgets/attributeWindow/_factory.py::AttributeSpec.from_value(cls, key: str, value: Any, *, label: str = '') -> 'AttributeSpec'`
- `widgets/attributeWindow/_factory.py::KindHandler(class)`
- `widgets/attributeWindow/_factory.py::connect_changed(widget: QtWidgets.QWidget, callback: Callable[[Any], None]) -> None`
- `widgets/attributeWindow/_factory.py::get_handler(kind: str) -> KindHandler`
- `widgets/attributeWindow/_factory.py::infer_kind(value: Any) -> str`
- `widgets/attributeWindow/_factory.py::make_widget(spec: AttributeSpec, parent: Optional[QtWidgets.QWidget] = None) -> QtWidgets.QWidget`
- `widgets/attributeWindow/_factory.py::read_value(widget: QtWidgets.QWidget) -> Any`
- `widgets/attributeWindow/_factory.py::register_kind(name: str, handler: KindHandler) -> None`
- `widgets/attributeWindow/_factory.py::set_value(widget: QtWidgets.QWidget, value: Any) -> None`
