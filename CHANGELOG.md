# uitk — Changelog

## 2026

- **Menu popup fixes** — fixed option menus not opening and flashing during init.
  - **Root cause**: `_register_with_main_window()` called synchronously inside `Menu.add()` triggered `mainWindow.register_widget()` → `widget.init_slot()` → `tb###_init()` recursively during menu population. Fixed by deferring via `QTimer.singleShot(0)`.
  - `showEvent`: skip `_apply_position()` when `show_as_popup()` already handled positioning (check `_current_anchor_widget`).
  - `_setup_as_popup`: consolidated double `setWindowFlags()` + `setParent()` into single `setParent(parent, flags)` — avoids double native window recreation.
  - `Header.show_menu`: changed `menu.setVisible(True)` → `menu.show_as_popup(anchor_widget=self, position="bottom")`.
  - `MenuOption` / `OptionMenuOption.set_wrapped_widget`: preserve popup flags via `setParent(widget, self._menu.windowFlags())`.
  - Added 13 regression tests in `test_menu.py` covering init visibility, deferred registration, header menu popup, option box menu flags.

- **Marking menu reshow fix** — fixed marking menu reopening on top of standalone windows while activation key is still held.
  - `_show_window`: always hides the MarkingMenu and clears `_activation_key_held`; reparents child widgets so they aren't hidden alongside the overlay.
  - `_transition_to_state`: guards against transitioning when MarkingMenu is already hidden, preventing `Key_F12` → startmenu reshow.
  - `_standalone_suppress` flag: set in `_show_window`, cleared in `_on_activation_release`. Blocks `_on_activation_press` from processing spurious key re-fires caused by focus changes in Maya.
  - Added 9 regression tests in `test_marking_menu.py`.
