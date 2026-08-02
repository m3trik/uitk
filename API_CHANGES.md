# uitk — API Changes

_Diff vs prior baseline. Generated 2026-08-02._

## Signature changed (2)

- `widgets/optionBox/utils.py::OptionBoxManager.add_action`
  - was: `(self, callback=None, icon='option_box', tooltip='Options', text=None, states=None, settings_key=None)`
  - now: `(self, callback=None, icon='menu', tooltip='Options', text=None, states=None, settings_key=None)`
- `widgets/optionBox/utils.py::OptionBoxManager.set_action`
  - was: `(self, callback=None, icon='option_box', tooltip='Options', text=None, replace=True, states=None, settings_key=None)`
  - now: `(self, callback=None, icon='menu', tooltip='Options', text=None, replace=True, states=None, settings_key=None)`
