# uitk — API Changes

_Diff vs the last release (origin/main @ 7673278)._

## Added (11)

- `switchboard/utils.py::SwitchboardUtilsMixin.data_view_dialog(self, data: Any, *, title: str = '', save_path: Optional[str] = '', empty_message: str = 'Nothing to show.', size=(720, 560), parent=None)`
- `switchboard/utils.py::SwitchboardUtilsMixin.save_data_dialog(self, data: Any, title: str = '', path: str = '', parent=None) -> Optional[str]`
- `widgets/mixins/text_validation.py::TextValidationMixin(class)`
- `widgets/mixins/text_validation.py::TextValidationMixin.clear_validator(self)`
- `widgets/mixins/text_validation.py::TextValidationMixin.is_valid(self)`
- `widgets/mixins/text_validation.py::TextValidationMixin.reset_action_color(self) -> None`
- `widgets/mixins/text_validation.py::TextValidationMixin.set_action_color(self, key: str) -> None`
- `widgets/mixins/text_validation.py::TextValidationMixin.set_validator(self, validator, *, debounce_ms: int = 300, invalid_tooltip: str = 'Invalid', valid_tooltip=None, empty_tooltip=None, empty_is_valid: bool = True, deferred=None, pending_tooltip: str = 'Checking…', reasons=None, revert_on_commit=False)`
- `widgets/mixins/text_validation.py::TextValidationMixin.validate_now(self, run_deferred: bool = True)`
- `widgets/mixins/text_validation.py::TextValidationMixin.validation_message(self)`
- `widgets/textViewBox.py::TextViewBox.format_data(cls, data, indent: int = 2) -> str`

## Moved (6)

_Still resolvable at the same call site -- hoisted to a base class or re-exported from another module. NOT a removal: no alias or minor bump is owed._

- `widgets/lineEdit.py::LineEditFormatMixin.clear_validator`
- `widgets/lineEdit.py::LineEditFormatMixin.is_valid`
- `widgets/lineEdit.py::LineEditFormatMixin.reset_action_color`
- `widgets/lineEdit.py::LineEditFormatMixin.set_action_color`
- `widgets/lineEdit.py::LineEditFormatMixin.set_validator`
- `widgets/lineEdit.py::LineEditFormatMixin.validate_now`
