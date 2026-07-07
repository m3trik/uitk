# Marking Menu

`uitk.MarkingMenu` — a radial gesture menu driven by keyboard + mouse chord bindings. The flagship consumer pattern for UITK. Used by [tentacle](https://github.com/m3trik/tentacle) as the DCC shell for Maya, 3ds Max, and Blender.

**Nav**: [← README](README.md) · [User Guide](USER_GUIDE.md) · [Slots](SLOTS.md) · [Widgets](WIDGETS.md) · [Architecture](ARCHITECTURE.md) · [Cookbook](COOKBOOK.md) · [API](API_REFERENCE.md)

---

## What it is

Hold a key (e.g. `F12`). A radial menu appears centered at the cursor. Flick the mouse in a direction to invoke a command; the gesture leaves a trail. Press a mouse button *while* the key is held to switch between different menu sets. Release the key to dismiss.

The same system also launches standalone windows — any UI without the `#startmenu` / `#submenu` tag is treated as a regular `MainWindow` that the marking menu shows on demand.

Implementation: [uitk/widgets/marking_menu/_marking_menu.py](../uitk/widgets/marking_menu/_marking_menu.py) — one of the largest single classes in the package. Subclasses `QWidget + SingletonMixin + LoggingMixin + HelpMixin`.

---

## Bindings — the central concept

A binding maps a **chord string** to a **UI name**:

```python
bindings = {
    "Key_F12":                           "main#startmenu",
    "Key_F12|LeftButton":                "cameras#startmenu",
    "Key_F12|RightButton":               "scene#startmenu",
    "Key_F12|MiddleButton":              "editors#startmenu",
    "Key_F12|LeftButton|RightButton":    "maya#startmenu",
    "Key_F12|ControlModifier":           "advanced#startmenu",
}
```

Chord parts are `|`-separated and order-independent (`"LeftButton|Key_F12"` == `"Key_F12|LeftButton"` after normalization).

### Part kinds

| Kind | Examples |
|:---|:---|
| Key | `Key_F12`, `Key_Space`, `Key_Tab` (any `QtCore.Qt.Key_*` name) |
| Mouse button | `LeftButton`, `RightButton`, `MiddleButton` |
| Modifier | `ShiftModifier`, `ControlModifier`, `AltModifier`, `MetaModifier` |

The **activation key** (the one that triggers the menu) is auto-detected as the first `Key_*` part found across all bindings. It's used for the global shortcut installation and for suppressing re-show while held.

### Persistence

Bindings persist to `sb.configurable.marking_menu_bindings`. Runtime changes are picked up via `changed.connect(self._build_bindings)`.

```python
mm.bindings = {"Key_F11": "tools#startmenu"}  # setter persists + rebuilds
current = mm.bindings                          # getter reads persisted value
defaults = mm.default_bindings                 # original constructor value
```

---

## Tags drive the layout

A UI's tags determine how the marking menu displays it.

| Tags | Role | Behavior |
|:---|:---|:---|
| `#startmenu` | Radial entry point | Added to the stacked overlay; widgets centered around cursor; activation-key chord switches between startmenus |
| `#submenu` | Radial child | Transitioned to on hover over an `i`-button; overlay path grows |
| *(none)* | Standalone window | Shown as a regular `MainWindow`; marking menu hides; pinnable and lifecycle-managed |

Examples:

```
main#startmenu.ui         # Root radial for "main" group
main#submenu.ui           # Child radial under main
cameras#startmenu.ui      # Alt radial reached via F12|LeftButton
texture_editor.ui         # Standalone window launched from a menu button
```

Tag detection: `ui.has_tags(["startmenu", "submenu"])` in [_marking_menu.py](../uitk/widgets/marking_menu/_marking_menu.py).

---

## Construction

```python
from uitk import MarkingMenu

mm = MarkingMenu(
    parent=maya_main_window,      # host window (Maya, Max, Blender)
    ui_source="ui",               # directory or module with .ui files
    slot_source="slots",          # directory or module with slot classes
    widget_source=None,           # optional extra custom widget dir
    bindings={
        "Key_F12":              "main#startmenu",
        "Key_F12|LeftButton":   "cameras#startmenu",
    },
    handlers={"ui": MayaUiHandler},  # DCC-specific window handler
    log_level="WARNING",
)
```

If a `switchboard=` Switchboard is passed, the marking menu joins that one; otherwise it creates a private Switchboard with the given sources.

### Subclassing for a DCC shell

The canonical pattern — a DCC-specific subclass ([tcl_maya.py](../../tentacle/tentacle/tcl_maya.py)):

```python
from uitk.widgets.marking_menu._marking_menu import MarkingMenu
import mayatk as mtk
from mayatk.ui_utils.maya_ui_handler import MayaUiHandler

class TclMaya(MarkingMenu):
    def __init__(self, parent=None, key_show="F12", **kwargs):
        parent = parent or mtk.get_main_window()

        key = f"Key_{key_show}" if not key_show.startswith("Key_") else key_show
        bindings = kwargs.pop("bindings", None) or {
            key:                        "hud#startmenu",
            f"{key}|LeftButton":        "cameras#startmenu",
            f"{key}|MiddleButton":      "editors#startmenu",
            f"{key}|RightButton":       "main#startmenu",
            f"{key}|LeftButton|RightButton": "maya#startmenu",
        }

        super().__init__(
            parent,
            ui_source=("ui", "ui/maya_menus"),
            slot_source="slots/maya",
            bindings=bindings,
            handlers={"ui": MayaUiHandler},
            **kwargs,
        )
```

Instantiate once: `main = TclMaya(); main.show()`. The global shortcut is auto-installed when a `parent` is supplied.

---

## Lifecycle

| Event | What happens |
|:---|:---|
| Activation key pressed | `_on_activation_press` — dismiss external popups, look up binding for `key + current_buttons`, show that UI, dim other windows |
| Mouse button pressed (while held) | `mousePressEvent` — rebuild lookup with new chord, switch to that `#startmenu` |
| Mouse moved over `i`-button | `child_enterEvent` — transition to linked `#submenu`, grow overlay path |
| Mouse released over widget | `mouseReleaseEvent` — execute widget click (if inside a stacked menu), with chord-release tolerance for near-simultaneous releases |
| Activation key released | `_on_activation_release` — hide menu, restore dimmed windows, hide non-pinned standalone windows |

Chord release tolerance: if multiple buttons are held and released near-simultaneously, UITK waits a small window (40ms single-button, 75ms multi-button) before deciding the final state. Prevents flicker when a user intends to release two buttons together.

---

## Showing UIs programmatically

`MarkingMenu.show(ui, pos=None, force=False)` is the central dispatcher:

```python
mm.show("cameras#startmenu")       # radial
mm.show("texture_editor")          # standalone window, positioned at cursor
mm.show("texture_editor", pos="screen", force=True)
```

- If the target UI has `#startmenu` / `#submenu` tags → `_show_marking_menu` (stacked).
- Otherwise → `_show_window` (standalone, reparented, styled via `UiHandler`).

Standalone windows launched from a marking menu button stay open until dismissed. Pinnable windows (`ui.header` has a `pin` button) ignore auto-hide when the activation key is released; unpinned windows auto-hide.

### From slot classes

```python
class CamerasSlots(SlotsMaya):
    def btn_editor(self, widget):
        # Launch standalone editor from inside a radial menu
        self.sb.handlers.marking_menu.show("texture_editor")
```

---

## Integration with UiHandler

The marking menu registers itself as `sb.handlers.marking_menu`. It also installs a `UiHandler` instance as `sb.handlers.ui` (default) or whatever subclass you passed via `handlers={}`.

`UiHandler.setup_lifecycle(ui, hide_signal=mm.key_show_release)` wires standalone windows to auto-hide on activation release. Pinned windows ignore the signal via `request_hide()`.

See [Architecture — Handler ecosystem](ARCHITECTURE.md#handler-ecosystem) for how handler `DEFAULTS` merge into `sb.configurable`.

---

## Signals

| Signal | Emitted on |
|:---|:---|
| `key_show_press` | Activation key pressed |
| `key_show_release` | Activation key released (drives auto-hide) |
| `left_mouse_double_click` | Double-click inside a stacked menu |
| `left_mouse_double_click_ctrl` | Ctrl + double-click |
| `middle_mouse_double_click` | |
| `right_mouse_double_click` | |
| `right_mouse_double_click_ctrl` | |

Useful for hooking "quick tool" gestures:

```python
mm.left_mouse_double_click.connect(self.quick_save)
```

---

## The `i`-button convention

Buttons named `i` inside a `#startmenu` or `#submenu` are treated as navigation launchers. Their `accessibleName` specifies the target menu name.

```
In Designer:
  - Button objectName: "i"
  - Button accessibleName: "cameras#submenu"
```

Hovering over the `i`-button transitions to that submenu. Clicking an `i` with a standalone UI name launches it as a window and dismisses the marking menu.

This lets you build nested radial menus entirely in Qt Designer — no Python wiring for navigation.

---

## Widget centering

Within a `#startmenu` / `#submenu`, interactable widgets (`QPushButton`, `QLabel`, `QCheckBox`, `QRadioButton`) are automatically centered around the cursor when the menu opens, and given a `padding_x` of 35 via `center_widget` — a content-fit resize that also raises a too-small `maximumWidth`/`maximumHeight` rather than let it silently truncate the request (a stale Designer-authored ceiling used to clamp buttons back below their own `minimumSizeHint`, cramming the label against the edges). This is done in `add_child_event_filter` ([_marking_menu.py](../uitk/widgets/marking_menu/_marking_menu.py)).

`Region` widgets (from `uitk.Region`) inside menus get `visible_on_mouse_over = True` — they act as invisible reveal zones that can contain arbitrary content.

---

## Overlay

The visible gesture trail is drawn by `uitk.widgets.marking_menu.overlay.Overlay`. It:

1. Starts a new path on `start_gesture(pos)` (first menu appearance).
2. Adds waypoints via `path.add(ui, widget)` at each submenu transition.
3. Renders the trail with antialiasing.
4. Clones interactive widgets along the path so they stay visible / clickable even after the menu transitions away from them.

Path cloning runs on first visit per UI — tracked via `_last_ui_history_check`.

---

## See also

- [Cookbook — Marking menu recipes](COOKBOOK.md#marking-menu-recipes)
- [Architecture — Handler ecosystem](ARCHITECTURE.md#handler-ecosystem)
- [tentacle `tcl_maya.py`](https://github.com/m3trik/tentacle/blob/main/tentacle/tcl_maya.py) — working reference
- [tentacle `slots/maya/`](https://github.com/m3trik/tentacle/tree/main/tentacle/slots/maya) — per-domain slot modules used by the marking menu
