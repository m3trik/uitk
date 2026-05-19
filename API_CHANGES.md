# uitk — API Changes

_Diff vs prior baseline. Generated 2026-05-19._

## Removed (4)

- `widgets/mixins/option_box_mixin.py::OptionBoxMixin.get_pin_values_service` — was `(self)`
- `widgets/mixins/option_box_mixin.py::OptionBoxMixin.has_pin_values` — was `(self) -> bool`
- `widgets/optionBox/_optionBox.py::OptionBoxContainer.resizeEvent` — was `(self, event)`
- `widgets/optionBox/_optionBox.py::OptionBoxContainer.setPassThrough` — was `(self, enabled: bool)`

## Added (1)

- `widgets/mixins/preset_manager.py::get_presets_root() -> Path`

## Signature changed (1)

- `widgets/editors/editor_panel.py::EditorPanel.preset_dir`
  - was: `(self) -> Path`
  - now: `(self, value) -> None`
