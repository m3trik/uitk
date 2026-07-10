# Marking Menu

`uitk.MarkingMenu` — a radial gesture menu driven by keyboard + mouse chord bindings. The flagship consumer pattern for UITK. Used by [tentacle](https://github.com/m3trik/tentacle) as the DCC shell for Maya, 3ds Max, and Blender.

**Nav**: [← README](README.md) · [User Guide](USER_GUIDE.md) · [Slots](SLOTS.md) · [Widgets](WIDGETS.md) · [Architecture](ARCHITECTURE.md) · [Cookbook](COOKBOOK.md) · [API](API_REFERENCE.md)

---

## What it is

Hold a key (e.g. `F12`). A radial menu appears centered at the cursor. Flick the mouse in a direction to invoke a command; the gesture leaves a trail. Press a mouse button *while* the key is held to switch between different menu sets. Release the key to dismiss.

The same system also launches standalone windows — any UI without the `#startmenu` / `#submenu` tag is treated as a regular `MainWindow` that the marking menu shows on demand.

Implementation: [uitk/widgets/marking_menu/_marking_menu.py](../uitk/widgets/marking_menu/_marking_menu.py) — one of the largest single classes in the package. Subclasses `QWidget + SingletonMixin + LoggingMixin + HelpMixin`. Pure chord→menu resolution lives in [\_resolver.py](../uitk/widgets/marking_menu/_resolver.py) (Qt-free, unit-testable).

A process hosts at most **one** input-owning marking menu: constructing a new instance calls `retire()` on every prior live instance (disposes its activation `GlobalShortcut`, cancels timers, ends any live gesture — irreversible; the dev-reload path).

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

Chord parts are `|`-separated and order-independent (`"LeftButton|Key_F12"` == `"Key_F12|LeftButton"` — `normalize_key` sorts parts into a canonical form).

### Part kinds

| Kind | Values recognized by the resolver |
|:---|:---|
| Key | `Key_F12`, `Key_Space`, … (any `QtCore.Qt.Key_*` name). A bare part that isn't a button/modifier (`"F12"`) is auto-prefixed to `"Key_F12"` by `parse_binding_keys` |
| Mouse button | `LeftButton`, `RightButton`, `MiddleButton` — only these three |
| Modifier | `ShiftModifier`, `ControlModifier`, `AltModifier`, `MetaModifier` |

The **activation key** (the one that triggers the menu) is auto-detected by `parse_binding_keys` as the first `Key_*` part found across all bindings. It drives the application-scoped `GlobalShortcut` (`_install_activation_shortcut` — falls back to `Key_F12` with a warning when the bindings carry no valid key) and re-show suppression while held. Change it at runtime with `set_activation_key` (see [Shortcut editor integration](#shortcut-editor-integration--route-targets)).

### Resolution order

`resolve_target_menu` maps the live input state to a UI name. It returns `None` (menu hidden) when the activation key isn't held; otherwise it tries, in order:

1. **Exact match** on the full normalized state (activation key + extra key + modifiers + all held buttons).
2. Multi-button mask **collapsed to its priority button** — priority is `Right > Middle > Left` (`priority_button`).
3. Same state with **modifiers stripped** (then again with the priority-button collapse).
4. **Default binding** — the activation key alone.

So `F12+L+R` prefers an explicit `Key_F12|LeftButton|RightButton` binding, falls back to `Key_F12|RightButton`, and finally to `Key_F12`. A second *keyboard* key pressed while the menu is up participates as an `extra_key` chord part (`keyPressEvent` → `resolve_target_menu(extra_key=...)`), so bindings like `Key_F12|Key_A` also resolve.

### Persistence

Bindings persist to a **host-namespaced** `sb.configurable` key: `"marking_menu_bindings" + host_namespace_suffix(context_tags)` (`_binding_store_key`) — e.g. `marking_menu_bindings_maya` vs `marking_menu_bindings_blender`, so two DCCs sharing the QSettings backend can't clobber each other's chords. An empty/absent context (standalone) keeps the un-suffixed key.

At construction, `_reconcile_bindings` merges: first run seeds the store with the constructor defaults; later runs forward-merge `{**defaults, **stored}` so newly-shipped default chords appear while the user's customizations of existing keys win.

Runtime changes are picked up via the store's `changed` signal → `_build_bindings` (re-parse + refresh the shortcut-editor entries). External editors subscribe through the public hook `on_bindings_changed(callback)` rather than touching the storage key.

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
| `#startmenu` | Radial entry point | Added to the stacked overlay; menu centered at the gesture origin; activation-key chord switches between startmenus |
| `#submenu` | Radial child | Transitioned to on hover over a `MenuButton` nav launcher; overlay path grows |
| *(none)* | Standalone window | Shown as a regular `MainWindow`; marking menu hides; pinnable and lifecycle-managed |

Examples:

```
main#startmenu.ui         # Root radial for "main" group
main#submenu.ui           # Child radial under main
cameras#startmenu.ui      # Alt radial reached via F12|LeftButton
texture_editor.ui         # Standalone window launched from a menu button
```

Tag detection: `ui.has_tags(_MARKING_MENU_TAGS)` where `_MARKING_MENU_TAGS = ("startmenu", "submenu")` — a module-level constant in [_marking_menu.py](../uitk/widgets/marking_menu/_marking_menu.py).

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

If a `switchboard=` Switchboard is passed, the marking menu joins that one (registering any given sources onto it); otherwise it creates a private Switchboard with the given sources. Further opt-in kwargs: `suppress_default_on_reentry` (don't bounce back to the default menu after a non-default one was shown in the same hold), `precompile` (background pre-compile of stale `_ui.py` files, only under the `CompiledLoader`), `preload` (scoped preloading, below), and `context_tags` (host identity — drives `requires`-tag widget filtering and the binding store's namespace).

### Scoped preloading (`preload=True` / `preload_menus`)

A cold page pays its entire initialization inside the first gesture — the `.ui` load, slot-class instantiation and signal wiring, QSS polish, content fit — and because the overlay presents **last**, that first-show work lands *after* the page was already centered on the gesture anchor. Symptom: the first activation lags and settles visibly ("the first press feels uninitialized"); every later one is consistent.

`preload=True` warms the **distinct binding-target menus** (never the whole UI registry — standalone tool windows stay lazy) through the real show path while nothing paints, using the same `WA_DontShowOnScreen` suppressed-present trick construction uses to realize the overlay. Deferred and staggered — one page per event-loop tick once the host is idle, waiting out any live gesture — so DCC startup isn't blocked. `preload_menus(names=None, defer=True)` can also be called directly (it's idempotent; re-run it after a bindings change to warm only new targets), and `defer=False` warms synchronously for hosts that preload behind a splash screen.

As a backstop for pages that still reach the activation path cold (preloading off, or a freshly retargeted binding), `_show_marking_menu` re-centers such a page on its gesture anchor right after the present delivers its first `showEvent` — so even a cold first activation ends positioned exactly like every later one.

### Subclassing for a DCC shell

The canonical pattern — a DCC-specific subclass ([tcl_maya.py](../../tentacle/tentacle/tcl_maya.py), condensed):

```python
from uitk.widgets.marking_menu._marking_menu import MarkingMenu
import mayatk as mtk
from mayatk.ui_utils.maya_ui_handler import MayaUiHandler

class TclMaya(MarkingMenu):
    def __init__(self, parent=None, slot_source="slots/maya", log_level="WARNING", **kwargs):
        parent = parent or mtk.get_main_window()

        key_show = kwargs.pop("key_show", "F12")
        key_show = f"Key_{key_show}" if not key_show.startswith("Key_") else key_show
        bindings = kwargs.pop("bindings", None) or {
            key_show:                            "hud#startmenu",
            f"{key_show}|LeftButton":            "cameras#startmenu",
            f"{key_show}|MiddleButton":          "editors#startmenu",
            f"{key_show}|RightButton":           "main#startmenu",
            f"{key_show}|LeftButton|RightButton": "maya#startmenu",
        }

        super().__init__(
            parent,
            ui_source=("ui", "ui/maya_menus"),
            slot_source=slot_source,
            bindings=bindings,
            handlers={"ui": MayaUiHandler},
            log_level=log_level,
            suppress_default_on_reentry=True,
            precompile=True,
            preload=True,
            context_tags={"maya"},
            **kwargs,
        )

        # DCC-specific editor wiring: run when the shortcut editors are built.
        for name in ("shortcut", "global_shortcuts"):
            self.sb.editors.add_post_build_hook(
                name,
                lambda editor: editor.add_collision_checker(mtk.maya_collision_checker),
            )
```

Instantiate once: `main = TclMaya(); main.show()`. The activation `GlobalShortcut` is auto-installed when a `parent` is supplied.

---

## Lifecycle

| Event | What happens |
|:---|:---|
| Activation key pressed | `_on_activation_press` — dismiss external popups, resolve the current chord via `_sync_menu_to_state` (→ `resolve_target_menu`) and show that UI, transfer mouse control if a button is already held, dim other windows |
| Mouse button pressed (while held) | `mousePressEvent` — a lone **Left** press over an interactive item of the current menu is classified as a click (`_is_menu_item_press`) and left for the release to dispatch; any other press re-syncs the chord and switches menus |
| Secondary key pressed (while held) | `keyPressEvent` — resolved as an `extra_key` chord part; a non-default match shows that menu |
| Hover over a nav `MenuButton` | `child_enterEvent` → `_set_submenu` — transition to the button's `submenu_name()`, overlay path grows |
| Mouse released over an owned item | `mouseReleaseEvent` / `child_mouseButtonReleaseEvent` → `_handle_menu_item_release` — the click dispatches **immediately on the first release** of a chord; the per-gesture `_action_dispatched` latch swallows the trailing release so it fires exactly once |
| Mouse released over empty overlay | Chord **navigation** — `_defer_partial_or_settle` + `_sync_menu_to_state` switch to the menu the remaining state resolves to |
| Activation key released | `_on_activation_release` — hide menu, restore dimmed windows, `request_hide()` visible standalone windows |

Chord-release tolerance (`CHORD_RELEASE_TOLERANCE_MS = 75`) governs **navigation only, never item selection**: when a release over empty overlay leaves another button still held (a "partial" — real both-button releases lift a few ms apart), the decision is deferred by the tolerance window. If the other button also releases within it, the gesture settles on the final all-up state; if it's still held at expiry, the user meant to switch, and the menu navigates to the remaining-button menu.

Dimming (`dim_other_windows`) is a once-per-hold snapshot: windows and open menus visible at key-press fade to near-transparent and become mouse-transparent; anything opened *during* the hold stays bright. `restore_other_windows` undoes it on release.

---

## Showing UIs programmatically

`MarkingMenu.show(ui=None, pos=None, force=False)` is the central dispatcher (`ui=None` shows the activation key's default menu):

```python
mm.show("cameras#startmenu")       # radial
mm.show("texture_editor")          # standalone window, positioned at cursor
mm.show("texture_editor", pos="screen", force=True)
```

- If the target UI has `#startmenu` / `#submenu` tags → `_show_marking_menu` (stacked).
- Otherwise → `_show_window` (standalone, reparented, styled via `UiHandler`).

On activation-key release, every visible standalone window gets a `request_hide()`. Per `MainWindow.request_hide`, a window auto-hides only when it **has a pin button** (`ui.header`) and is currently **unpinned** — pinned windows and windows without a pin button refuse the request and stay open until dismissed explicitly.

### From slot classes

```python
class CamerasSlots(SlotsMaya):
    def btn_editor(self, widget):
        # Launch standalone editor from inside a radial menu
        self.sb.handlers.marking_menu.show("texture_editor")
```

---

## Integration with UiHandler

The marking menu registers itself as `sb.handlers.marking_menu` (`_setup_registry`). It also installs a `UiHandler` instance as `sb.handlers.ui` (default, from the `HANDLERS` class attr) or whatever subclass you passed via `handlers={}`.

`UiHandler.setup_lifecycle(ui, hide_signal=mm.key_show_release)` wires standalone windows to auto-hide on activation release, subject to `request_hide()` as above.

See [Architecture — Handler ecosystem](ARCHITECTURE.md#handler-ecosystem) for how handler `DEFAULTS` merge into `sb.configurable`.

---

## Shortcut editor integration — route targets

The marking menu's bindings surface in the unified Shortcut Editor via `_register_shortcut_editor_bindings`, re-run on every binding change. All entries use `Switchboard.register_command(..., bind=False)` — the register creates **no** `QShortcut`; the menu's own activation `GlobalShortcut` owns the real key (a second one would collide as an ambiguous overload).

- **Activation key** — registered as the `marking_menu_show` command: visible and editable, `clearable=False` (the menu must always keep a working activation key), its live value read via `value_getter`, and edits routed through `on_rebind` → **`set_activation_key`**.
- **`set_activation_key(new_key)`** rewrites the `Key_*` part of *every* chord, persists the set (rebuild + editor refresh), and re-installs the activation `GlobalShortcut` on the new key. Accepts `"Key_F11"` or bare `"F11"`; a no-op when empty, unchanged, or not a valid `QtCore.Qt.Key_*`.
- **Chord→menu routes** — the four mouse gestures in `_ROUTE_GESTURES` (`left`, `middle`, `right`, `left_right`) register as `marking_menu_route_<gesture>` entries: hidden and read-only (a routing table isn't a key trigger); the row's Action column names the target menu it opens (e.g. "Marking Menu: Cameras"). They're edited through the host's "Menu Bindings" combos instead, via:
- **`get_route_target(buttons)` / `set_route_target(buttons, menu)`** — gesture-keyed accessors where `buttons` is a sequence of Qt button-flag names (`("LeftButton",)`, `("LeftButton", "RightButton")`; `()` = the key-only default). Activation-key-agnostic: they resolve against the *current* activation key, so they stay correct after `set_activation_key`.
- **`start_menu_names(short=True)`** — the sorted `#startmenu` UI names the binding combos pick targets from (`short=True` strips the tag).

The focused entry point is **`sb.editors.show("global_shortcuts")`** — the same `ShortcutEditor` built with `focus="commands"` (see `_EditorRegistry._EDITORS` in [switchboard/editors.py](../uitk/switchboard/editors.py)): pinned to the Commands view, cached separately from the full `"shortcut"` editor.

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

## Navigation buttons — `MenuButton`

Radial navigation is owned by the `uitk.MenuButton` widget ([widgets/menuButton.py](../uitk/widgets/menuButton.py)) — the marking menu detects it **by type** (`isinstance(w, MenuButton)`); there is no name prefix or `accessibleName` convention. Routing lives in two Qt properties, settable in Designer and round-tripped through `.ui` files:

- `target` — the destination UI name (bare `"cameras"` or fully-qualified `"cameras#submenu"`).
- `filterTags` — optional tags that compose into the submenu name and reveal only matching groupboxes of a shared submenu.

**Hover** (`child_enterEvent` → `_set_submenu`) opens the button's `submenu_name()` — `target` + `filterTags` + the `submenu` tag: `target="polygons"`, `filterTags="edge"` → `"polygons#edge#submenu"`.

**Click** (`_handle_widget_action` → `_resolve_button_menu`) resolves through the shared `Switchboard.menu_button_target_name` SSoT: a `target` that itself resolves to a UI opens directly (as a standalone window when untagged — e.g. a native DCC menu); otherwise the composed submenu opens in the overlay.

A `MenuButton` whose target doesn't resolve in the current context auto-hides (`Switchboard.apply_visibility_policy`), and breadcrumb clones keep navigating because `target` / `filterTags` are declared in `MenuButton.clone_properties` (see [Overlay](#overlay)). Nested radial menus are built entirely in Qt Designer — no Python wiring for navigation.

---

## Widget centering

Within a `#startmenu` / `#submenu`, the content-fit resize is **nav-only**: `MenuButton`s get a center-preserving fit to their content hint — `sb.center_widget(w, padding_x=35)` in `add_child_event_filter` ([_marking_menu.py](../uitk/widgets/marking_menu/_marking_menu.py)) — while regular slot buttons, labels and checkboxes keep their Designer-authored geometry. An option-box-wrapped widget is fitted by its `OptionBoxContainer` instead (`_adjust_to_content`, on by default), which sizes the whole container — wrapped widget plus option buttons — anchored on the wrapped widget's Designer-authored center, with the authored width kept as the wrapped widget's minimum (a floor, not a ceiling) so the label never collapses to its bare text hint. The first option square also tucks over the button's edge by a fraction of the perceived side padding (`OptionBox._seam_overlap` / `_SEAM_OVERLAP_FRACTION`, a negative layout spacer) so the text-to-option seam reads a fraction of the normal padding without touching the theme QSS. The nav resize also raises a too-small `maximumWidth` rather than let it silently truncate the request (a stale Designer-authored ceiling used to clamp buttons back below their own `minimumSizeHint`, cramming the label against the edges) — unless `minimumWidth == maximumWidth`, a deliberate fixed-size lock that is left untouched. The menu window itself is centered on the cursor / gesture origin by `setCurrentWidget`.

`Region` widgets (from `uitk.Region`) inside menus get `visible_on_mouse_over = True` — they act as invisible reveal zones that can contain arbitrary content.

---

## Overlay

The visible gesture trail is drawn by `uitk.widgets.marking_menu.overlay.Overlay` (the marking menu constructs it with `antialiasing=True`). It:

1. Starts a new path on `start_gesture(pos)` (first menu appearance; sets a cross cursor).
2. Adds waypoints via `path.add(ui, widget)` at each submenu transition — the returned captured global center is the single source of truth for downstream positioning.
3. Renders the trail (`draw_tangent` per segment).
4. `clone_widgets_along_path(ui, return_func)` places a `Region` return zone at the gesture origin (hover = return to the startmenu) and clones the path's intermediate widgets onto the new UI, so they stay visible / clickable after the menu transitions away. Clones copy `CLONE_ATTRS` plus any properties a widget declares in `clone_properties`.

Path cloning runs on first visit per UI — tracked via `_last_ui_history_check` in `MarkingMenu._handle_overlay_cloning`.

---

## Diagnostics

Input-handoff logging (who holds the mouse grab, activation flags, launch/release records): `mm.enable_input_logging(path)` tees DEBUG logs from the menu and its `MouseTracking` to a file (`disable_input_logging` stops it). Auto-enabled at construction when the `UITK_INPUT_LOG` environment variable names a path; zero cost otherwise.

---

## See also

- [Cookbook — Marking menu recipes](COOKBOOK.md#marking-menu-recipes)
- [Architecture — Handler ecosystem](ARCHITECTURE.md#handler-ecosystem)
- [tentacle `tcl_maya.py`](https://github.com/m3trik/tentacle/blob/main/tentacle/tcl_maya.py) — working reference
- [tentacle `slots/maya/`](https://github.com/m3trik/tentacle/tree/main/tentacle/slots/maya) — per-domain slot modules used by the marking menu
