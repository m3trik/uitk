# UITK Instructions

> **System Prompt Override**:
> You are an expert Python UI Developer (Qt/PySide).
> Your primary goal is **modularity**, **themeability**, and **DCC compatibility**.
>
> **Global Standards**: For general workflow, testing, and coding standards, refer to the [Main Copilot Instructions](../../.github/copilot-instructions.md).
>
> **Work Logs**: When completing a task, you MUST update the **Work Logs** at the bottom of this file.

---

## 1. Meta-Instructions

- **Living Document**: This file (`uitk/.github/copilot-instructions.md`) is the SSoT for UITK specific workflows.
- **Compatibility**: Code must work across PySide2 and PySide6 if possible (using `Qt.py` or internal abstraction).
- **Naming**: Qt often uses camelCase, but we prefer snake_case for Python wrappers unless overriding specific Qt methods.

## 2. Architecture

- **Widgets**: Reusable UI components.
- **Themes**: Style management.

---

## 3. Work Logs & History
- [x] **Initial Setup** — Repository established.
- [x] **Menu popup fixes** — Fixed option menus not opening and flashing during init:
  - **Root cause**: `_register_with_main_window()` called synchronously inside `Menu.add()` triggered `mainWindow.register_widget()` → `widget.init_slot()` → `tb###_init()` recursively during menu population. Fixed by deferring via `QTimer.singleShot(0)`.
  - `showEvent`: Skip `_apply_position()` when `show_as_popup()` already handled positioning (check `_current_anchor_widget`).
  - `_setup_as_popup`: Consolidated double `setWindowFlags()`+`setParent()` into single `setParent(parent, flags)` to avoid double native window recreation.
  - `Header.show_menu`: Changed `menu.setVisible(True)` → `menu.show_as_popup(anchor_widget=self, position="bottom")`.
  - `MenuOption`/`OptionMenuOption.set_wrapped_widget`: Preserve popup flags via `setParent(widget, self._menu.windowFlags())`.
  - Added 13 regression tests in `test_menu.py` covering initialization visibility, deferred registration, header menu popup, and option box menu flags.
- [x] **Marking menu reshow fix** — Fixed marking menu reopening on top of standalone windows (animation, mayatk, etc.) while activation key is still held:
  - `_show_window`: Always hides the MarkingMenu and clears `_activation_key_held`. Reparents child widgets so they aren't hidden alongside the overlay.
  - `_transition_to_state`: Guards against transitioning when the MarkingMenu is already hidden, preventing `"Key_F12"` → startmenu reshow.
  - `_standalone_suppress` flag: Set in `_show_window`, cleared in `_on_activation_release`. Blocks `_on_activation_press` from processing spurious key re-fires caused by focus changes in Maya.
  - Added 9 regression tests in `test_marking_menu.py`.
