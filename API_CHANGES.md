# uitk — API Changes

_Diff vs the last release (origin/main @ ddd41a9)._

## Removed (1)

- `managers/registry_manager.py::FileRegistry.file_manager` — was `(self) -> 'RegistryManager'`

## Added (10)

- `bridge/parameters.py::Parameters.rig_mode_spec(default: str = 'auto', section: str = '') -> AttributeSpec`
- `managers/shortcut_manager.py::ShortcutManager.hide_bound_menu_items() -> bool`
- `managers/shortcut_manager.py::ShortcutManager.set_hide_bound_menu_items(value: bool) -> None`
- `switchboard/shortcuts.py::SwitchboardShortcutMixin.widget_has_shortcut(self, widget: QtWidgets.QWidget) -> bool`
- `widgets/sequencer/_keyframe.py::KeyframeItem.weighted_handles(self) -> bool`
- `widgets/sequencer/_keyframe.py::TangentHandleItem.drag_participant(self) -> bool`
- `widgets/sequencer/_sequencer.py::SequencerWidget.modifiers_held(self) -> int`
- `widgets/sequencer/_sequencer.py::SequencerWidget.set_modifiers_held(self, modifiers) -> None`
- `widgets/sequencer/_sequencer.py::SequencerWidget.shortcut_overlay_mode(self) -> str`
- `widgets/sequencer/_sequencer.py::SequencerWidget.shortcut_overlay_tracking(self) -> bool`
