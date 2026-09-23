# uitk — API Changes

_Diff vs the last release (origin/main @ 1d6a969)._

## Removed (3)

- `switchboard/utils.py::SwitchboardUtilsMixin.pop_override_cursor_stack` — was `(app)`
- `switchboard/utils.py::SwitchboardUtilsMixin.push_override_cursor_stack` — was `(app, saved)`
- `widgets/comboBox.py::CustomStyle.drawControl` — was `(self, element, opt, painter, widget=None)`

## Added (9)

- `managers/state_manager.py::StateManager.is_applying(self) -> bool`
- `widgets/optionBox/options/_options.py::BaseOption.clear_saved_default(self) -> bool`
- `widgets/optionBox/options/_options.py::BaseOption.save_default(self) -> bool`
- `widgets/optionBox/options/affix.py::AffixOption.clear_saved_default(self) -> bool`
- `widgets/optionBox/options/affix.py::AffixOption.save_default(self) -> bool`
- `widgets/optionBox/options/toggle.py::BinaryToggleOption.clear_saved_default(self) -> bool`
- `widgets/optionBox/options/toggle.py::BinaryToggleOption.save_default(self) -> bool`
- `widgets/optionBox/utils.py::OptionBoxManager.clear_option_defaults(self) -> int`
- `widgets/optionBox/utils.py::OptionBoxManager.save_option_defaults(self) -> int`
