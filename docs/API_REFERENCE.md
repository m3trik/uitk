# API Reference

Public signatures for the core UITK classes. For prose explanations, see the [User Guide](USER_GUIDE.md) and [Architecture](ARCHITECTURE.md).

**Nav**: [← README](README.md) · [User Guide](USER_GUIDE.md) · [Slots](SLOTS.md) · [Widgets](WIDGETS.md) · [Marking Menu](MARKING_MENU.md) · [Architecture](ARCHITECTURE.md) · [Cookbook](COOKBOOK.md)

Signatures below are verified against the generated registry ([API_INDEX.md](../API_INDEX.md) / `API_REGISTRY.md`); source links go to the owning module.

---

## `uitk.Switchboard`

Source: [switchboard/_core.py](../uitk/switchboard/_core.py) (composes partials from sibling modules — `slots.py`, `widgets.py`, `utils.py`, `names.py`, `editors.py`, `style.py`, `shortcuts.py`)

```python
Switchboard(
    parent=None,
    ui_source=None,        # path | module | list thereof | class
    slot_source=None,      # path | module | list thereof | class
    widget_source=None,    # path | module | list thereof
    icon_source=None,      # path | module | list thereof
    handlers: dict = None, # {"name": HandlerClass | instance}
    tag_delimiter: str = None,         # default "#"
    ui_name_delimiters: str = None,    # default "."
    log_level: str = "warning",
    base_dir=None,
    loader="runtime",                  # "runtime" | "compiled"
    context_tags=None,                 # feature tags this host satisfies, e.g. {"maya"}
    on_missing_slot=None,              # callable(widget) for signal-bearing widgets with no slot
) -> Switchboard
```

### Instance attributes

| Attr | Type | Meaning |
|:---|:---|:---|
| `loaded_ui` | `NamespaceHandler` | Dynamic resolver — `sb.loaded_ui.editor` → `MainWindow` |
| `registered_widgets` | `NamespaceHandler` | Custom widget classes discovered via `widget_source` |
| `registered_icons` | `NamespaceHandler` | Icon paths discovered via `icon_source` |
| `slot_instances` | `NamespaceHandler` | Instantiated slot class instances |
| `registry` | `RegistryManager` | Typed registries: `ui_registry`, `slot_registry`, `widget_registry`, `icon_registry` |
| `handlers` | namespace object | `sb.handlers.ui`, `sb.handlers.marking_menu`, custom handlers |
| `settings` | `SettingsManager` | QSettings wrapper with `namespace="switchboard"` |
| `configurable` | `SettingsManager` | Branch of `settings` for handler DEFAULTS + app config |
| `convert` | `ConvertMixin` | Type conversion helpers |
| `default_signals` | `dict[type, str]` | Qt widget class → default signal name |
| `app` | `QApplication` | Lazy class property — existing instance, or one created on first access |

### Signals

| Signal | Payload | Fires when |
|:---|:---|:---|
| `on_ui_registered` | `str` | A new UI enters `ui_registry` via `register()` |
| `on_ui_loaded` | `str` | A UI actually materialises in `loaded_ui` (once per UI, any load path) |
| `on_ui_tags_changed` | `str` | `save_ui_tags()` persisted tags for an existing UI |
| `on_handler_entries_changed` | `str` (handler attr) | A launchable handler's entry set may have changed |
| `on_handler_entry_changed` | `str, str` (handler, entry) | One entry's live state (visibility/status) changed |

### Class attributes (naming convention)

```python
TAG_DELIMITER = "#"
UI_NAME_DELIMITER = "."
SLOT_SUFFIX = "Slots"
INIT_SUFFIX = "_init"
```

### Methods — UI management

| Method | Purpose |
|:---|:---|
| `load_ui(file: str) -> QMainWindow` | Load a `.ui` file via the configured loader delegate (runtime QUiLoader or compiled `_ui.py`) |
| `load_all_ui() -> list` | Load every UI in the registry |
| `add_ui(name, widget=None, parent=None, tags=None, path=None, overwrite=False, **kwargs) -> MainWindow` | Wrap a loaded widget in `MainWindow` and register it |
| `get_ui(ui=None) -> QWidget` | Resolve by name, return current if `None`, pass-through if already a widget |
| `get_ui_relatives(ui, upstream=False, exact=False, downstream=False, reverse=False) -> list` | Tag-depth-based relatives via shared base name |
| `find_ui_filename(legal_name, unique_match=False) -> str \| list \| None` | Legal-name-to-original-filename resolver |
| `save_ui_tags(path, tags)` | Persist tags into a `.ui` file as a Designer-safe dynamic property |
| `ui_history(index=None, allow_duplicates=False, inc=None, exc=None)` | Ordered history of current-UI transitions |
| `show_prev_ui() -> QWidget \| None` | Re-show the most-recent non-transient UI not already on screen |

### Methods — widgets & slots

| Method | Purpose |
|:---|:---|
| `get_widget(name, ui=None) -> QWidget \| None` | Find a registered widget by name, optionally in a specific UI |
| `register_widget(widget)` | Manually register a custom widget class (rare — usually automatic) |
| `get_slots_instance(ui) -> object \| None` | Return the slot class instance for a UI, creating on first access |
| `init_slot(widget, block_signals=True)` | Run `<objectName>_init` for a widget |
| `connect_slot(widget, slot=None)` | Wire widget signals to slot method |
| `call_slot(widget, *args, **kwargs)` | Invoke the slot manually |
| `slot_history(index=None, allow_duplicates=False, inc=None, exc=None, add=None, remove=None, length=200)` | Ordered history of slot calls |
| `prev_slot` *(property)* | Last executed slot method, or None |
| `repeat_last()` | Re-invoke the last slot with the exact args it last ran with |
| `get_default_signals(widget) -> set` | Default Qt signals available on a widget |
| `get_available_signals(widget, derived=True, exc=None) -> set` | All Qt signals on a type, optionally including inherited |

### Methods — dialogs & widget helpers

| Method | Purpose |
|:---|:---|
| `message_box(string, *buttons, location="topMiddle", timeout=3, background=0.75)` | Themed QMessageBox replacement |
| `file_dialog(file_types=["*.*"], title="Select files to open", start_dir="/home", filter_description="All Files", allow_multiple=True) -> str \| list` | Static — themed file picker |
| `dir_dialog(title="Select a directory", start_dir="/home") -> str` | Static — themed directory picker |
| `save_file_dialog(file_types=["*.*"], title="Save file", start_dir="/home", filter_description="All Files") -> str \| None` | Static — save-destination picker |
| `center_widget(widget, pos=None, offset_x=0, offset_y=0, padding_x=None, padding_y=None, relative=None)` | Reposition + optionally resize |
| `get_cursor_offset_from_center(widget) -> QPoint` | Static — `QCursor.pos() - widget.rect().center()` |
| `toggle_multi(ui, trigger=None, signal=None, apply_now=True, **kwargs)` | Batch-set boolean properties on named widgets; with `trigger`, re-apply an `on_<state>` mapping on its change signal (and once at wire time) |
| `enable_when(ui, targets, trigger, condition=True, signal=None, value=None, invert=False)` | Keep `targets` enabled exactly while `trigger`'s value satisfies `condition` (callable / value / set / truthiness); multi-trigger, order-independent, idempotent |
| `text_from(ui, target, sources, formatter, signal=None, value=None)` | Keep `target`'s text derived from `sources` — the button names its own outcome instead of hiding it behind a gear icon; re-applies on a blocked-signal preset load like `enable_when` |
| `value_from(ui, targets, sources, resolver, signal=None, value=None)` | Keep `targets`' **value** derived from `sources` — a preset combo that reads *Custom* the moment a dial it filled is overridden; writes by the inverse of the reader table (combo: data → label → row), a `None` resolver result declines |
| `refresh_dependencies(ui)` | Re-apply every declarative rule — `enable_when`'s, `text_from`'s and `value_from`'s — after a bulk blocked-signal change (a preset load) |
| `connect_multi(ui, widgets, signals, slots)` | Batch signal-slot connection |
| `create_button_groups(ui, *args, allow_deselect=False, allow_multiple=False) -> list[QButtonGroup]` | Radio groups from ranges like `"chk_001-3"` |
| `unpack_names(name_string) -> list[str]` | Class method — expand `"chk021-23,25,tb001"` into individual names |

### Methods — registration

| Method | Purpose |
|:---|:---|
| `register(ui_location=None, slot_location=None, widget_location=None, icon_location=None, base_dir=1, recursive=False, validate=1, tags=None)` | Add new sources after construction |
| `register_handler(name, instance, defaults=None)` | Attach `instance` at `sb.handlers.<name>`, merge `defaults` into `sb.configurable.<name>` |
| `register_command(name, callback, ...)` / `set_command_shortcut(name, sequence)` | Register a UI-less command and bind a shortcut to it (for slot shortcuts, decorate the slot with `@Shortcut("Ctrl+S")`) |

### Properties

| Property | Type | Meaning |
|:---|:---|:---|
| `active_ui` | `QWidget \| None` | Currently set UI — no auto-load, no warning |
| `current_ui` | `QWidget` | Most recently shown / focused UI (loads on first access) |
| `prev_ui` | `QWidget` | Previous UI from history |
| `visible_windows` | `set[MainWindow]` | All currently visible loaded UIs |

---

## `uitk.MainWindow`

Source: [widgets/mainWindow.py](../uitk/widgets/mainWindow.py)

```python
MainWindow(
    name: str,
    switchboard_instance: Switchboard,
    central_widget: QWidget = None,
    parent: QWidget = None,
    tags: set = None,
    path: str = None,
    log_level: str = "WARNING",
    restore_window_size: bool = True,
    add_footer: bool = False,
    ensure_on_screen: bool = True,
    fit_to_content_on_show: bool = True,
    default_slot_timeout: float = None,
    settings: SettingsManager = None,
    **kwargs,  # forwarded to set_attributes
)
```

### Signals

| Signal | Args | Fires when |
|:---|:---|:---|
| `on_show` | — | Window shown |
| `on_first_show` | — | First show only |
| `on_hide` | — | Window hidden |
| `on_close` | — | Window closed |
| `on_focus_in` / `on_focus_out` | — | Focus transitions |
| `on_child_registered` | `widget` | Widget registered on the window |
| `on_child_changed` | `widget, value` | Widget's default signal fires |
| `on_pinned_changed` | `bool` | Pin state flipped |

### Instance attributes

| Attr | Type | Meaning |
|:---|:---|:---|
| `sb` | `Switchboard` | Owning switchboard |
| `widgets` | `set[QWidget]` | All registered child widgets |
| `tags` | `set[str]` | Tags parsed from the filename |
| `path` | `str` | Path to the source `.ui` file |
| `settings` | `SettingsManager` | Own store keyed by window name (or the injected `settings`) |
| `state` | `StateManager` | Widget state persistence |
| `style` | `StyleSheet` | Theme manager with `.set(theme=..., style_class=...)` and `.theme_changed` signal |
| `footer` | `Footer \| None` | `Footer` found in the `.ui`, else auto-created only when `add_footer=True` |
| `header` | `Header \| None` | If one is present in the `.ui` |
| `fit_to_content_on_show` | `bool` | Snap height to layout content on show (default `True`) |
| `is_initialized` | `bool` | `True` after first show |
| `is_current_ui` | `bool` | `True` if `self is sb.current_ui` |
| `is_pinned` | `bool` | Alias for `pinned` |
| `pinned` | `bool` | If True, resists `request_hide` |
| `restore_widget_states` | `bool` | Master toggle for state restoration |
| `restore_window_size` | `bool` | Master toggle for geometry restoration |
| `ensure_on_screen` | `bool` | Clamp to monitor on show |
| `default_slot_timeout` | `float \| None` | UI-wide fallback for slot timeout |
| `connected_slots` | `NamespaceHandler` | Registered slot namespaces |
| `presets` *(property)* | `PresetManager` | Lazy-init; save/load named state snapshots |
| `slots` *(property)* | `object` | Slot class instance (shortcut to `sb.get_slots_instance(self)`) |

### Methods

| Method | Purpose |
|:---|:---|
| `show(pos=None, app_exec=False)` | Display; `pos` is `"screen"` / `"cursor"` / `QPoint` / `(x,y)` |
| `set_attributes(**kw)` | Bulk attribute / method / signal setup |
| `set_flags(**flags)` | Toggle window flags — `FramelessWindowHint=True`, `WindowStaysOnTopHint=False`, … |
| `register_widget(widget, **kw)` | Inject UITK attrs on a widget and add it to the widget set |
| `register_children(root_widget=None)` | Walk the tree and register anything with an `objectName` |
| `has_tags(tags=None) -> bool` | Check if any provided tag is present (empty → check for any tags) |
| `edit_tags(target=None, add=None, remove=None, clear=False, reset=False)` | Mutate tags |
| `request_hide() -> bool` | Pin-aware hide — returns True if hidden, False if blocked by pin (or claimed as a tap, see `Header.pin_on_tap`) |
| `visible_duration_ms() -> int` | Milliseconds since the window last became visible on screen (`-1` if never shown) |
| `set_pinned(value: bool)` | Method form of the `pinned` setter |
| `save_window_geometry()` | Persist size/pos to settings |
| `restore_window_geometry()` | Restore from settings |
| `clear_saved_geometry()` | Remove the stored geometry |
| `perform_restore_state(widget, force=False)` | Re-apply persisted state to a widget |
| `sync_widget_values(widget, value)` | Propagate value to same-named widgets in related UIs |
| `setStyleSheet(style)` | Override of QMainWindow — honors `lock_style` |
| `reset_style()` | Revert to previous stylesheet |
| `trigger_deferred()` | Execute deferred setup functions (priority-ordered) |

---

## `uitk.Signals`

Source: [switchboard/slots.py](../uitk/switchboard/slots.py)

### Decorator form

```python
@Signals(*signal_names)
def slot_method(self, ...): ...
```

- `Signals("clicked", "pressed")` — connect to each named signal.
- `Signals()` — empty tuple — disables auto-connection.
- `Signals("nonexistent")` — no-op for signals that don't exist on the widget.

Signal names are attached to the wrapped function as `func.signals`.

### `@Signals.blockSignals`

```python
@Signals.blockSignals
def update_widget(self): ...
```

Blocks `self`'s signals for the duration of the call, restoring the *prior* block state on exit (not an unconditional unblock). Use on slot methods that mutate widgets and would otherwise re-trigger themselves.

---

## `uitk.UiHandler`

Source: [handlers/ui_handler.py](../uitk/handlers/ui_handler.py)

```python
UiHandler(
    switchboard: Switchboard,
    ui_root: str | list = None,
    slot_root: str | list = None,
    discover_slots: bool = False,
    recursive: bool = True,
    log_level: str = "WARNING",
    source_tags: set = None,
    **kwargs,
)
```

### Class attributes

```python
DEFAULT_STYLE = {
    "attributes": {"WA_TranslucentBackground": True},
    "flags":      {"FramelessWindowHint": True},
    "theme":      "dark",
    "style_class": "translucentBgWithBorder",
    "header_buttons": ("menu", "collapse", "pin"),
}

TRANSIENT_HEADER = ("menu", "collapse", "pin")    # auto-hides with the marking menu
STICKY_HEADER    = ("menu", "collapse", "hide")   # stays open until dismissed

DEFAULTS = {
    "default_position":   None,    # "cursor" | "screen" | "last" | (x, y)
    "remember_position":  True,
    "remember_size":      True,
    "style":              DEFAULT_STYLE,
    "pin_click_hides":    True,       # pin-button click dismisses
    "pin_on_tap":         False,      # tap the activation key to pin open
    "window_persistence": "context",  # "context" | "sticky" | "transient"
}

UI_REGISTRY: dict = {}   # subclass override for manual ui-name → path maps
```

### Methods

| Method | Purpose |
|:---|:---|
| `get(name, **kwargs) -> QWidget \| None` | Resolve UI + apply styles (extra kwargs accepted and ignored for call-site compatibility) |
| `can_resolve(name) -> bool` | Whether `get` would resolve `name` — without building it |
| `show(ui, pos=None, force=False, **kw) -> QWidget` | Show and position a UI |
| `apply_styles(ui, style=None, theme=None)` | Apply `DEFAULT_STYLE` (or override) with tag-based adjustments; `theme` overrides for this call |
| `setup_lifecycle(ui, hide_signal=None)` | Connect a signal to `ui.request_hide()` |

### Window persistence

Pin vs hide chrome for **every** window, whatever opened it. Resolution order:
per-window override → global default → the window's own default.

| Member | Purpose |
|:---|:---|
| `default_persistence(ui) -> str` | **Subclass hook** — the per-window default (base: `"transient"`) |
| `window_persistence` (property) | Global default: `"context"` (per-window) / `"sticky"` / `"transient"` |
| `persistence_override(name) -> str \| None` | Stored per-window override |
| `set_persistence_override(name, mode)` | Set (mode) or clear (`None`); live-applies |
| `resolve_persistence(ui, name=None, context_default=None) -> str` | Effective mode, never `"context"` |
| `reapply_persistence(name=None)` | Re-chrome loaded windows after a change |

An unconfigured header takes the mode's whole button set; a header a panel
configured itself (`header_init` → `config_buttons`) is left alone unless the
user set an explicit choice, and then only its dismissal button is swapped — so
a panel keeps its `refresh` button either way.

Subclass for DCC integration — override `show`, `default_persistence`, or provide a `UI_REGISTRY`.

---

## `uitk.BaseHandler`, `uitk.HandlerEntry`, `uitk.ExternalAppHandler`

Source: [handlers/base_handler.py](../uitk/handlers/base_handler.py) · [handlers/handler_entry.py](../uitk/handlers/handler_entry.py) · [handlers/external_app_handler.py](../uitk/handlers/external_app_handler.py). Handler-ecosystem prose (registration, `DEFAULTS`, `sb.handlers.*`): [Architecture](ARCHITECTURE.md).

**`BaseHandler`** — common base for Switchboard handlers (`ptk.SingletonMixin` + `ptk.LoggingMixin`): `instance(switchboard=None, **kwargs)` classmethod and a `config` property (the handler's `sb.configurable` branch). A handler that wants to appear in the launcher (`sb.editors.show("browser")`) additionally satisfies `LaunchableHandlerProtocol`: `entries()`, `launch(name, **options)`, `close(name)`, `is_visible(name)`.

**`HandlerEntry`** — the launchable-entry data class every handler yields from `entries()`; `all_tags` and `editable_tags` properties.

**`ExternalAppHandler`** — registers, installs on demand, and launches external Python apps as subprocesses (or in-process widgets):

| Method | Purpose |
|:---|:---|
| `register(name, *, module, entry=None, install_spec=None, python=None, show_kwargs=None, mode="subprocess", tags=None, hidden_in=None)` | Pre-register an app so it can be launched by name |
| `discover(groups=None) -> int` | Auto-register every app advertised under a uitk entry-point group |
| `add_provider(install_spec, *, probe_module=None, group=None, python=None)` | Register a provider package that ships discoverable apps |
| `is_registered(name)` / `unregister(name)` | Query / remove |
| `launch(name=None, *, module=None, entry=None, install_spec=None, python=None, show_kwargs=None, mode=None, show=True)` | Launch a registered app, or an ad-hoc app from kwargs |
| `entries()` / `close(name)` / `is_visible(name)` / `save_tags(name, tags)` | Launchable contract + tag persistence |

---

## `uitk.MarkingMenu`

Source: [widgets/marking_menu/_marking_menu.py](../uitk/widgets/marking_menu/_marking_menu.py). Full subsystem doc: [Marking Menu](MARKING_MENU.md).

```python
MarkingMenu(
    parent: QWidget = None,
    ui_source=None,
    slot_source=None,
    widget_source=None,
    bindings: dict = None,          # {"Key_F12|LeftButton": "ui_name", ...}
    handlers: dict = None,
    switchboard: Switchboard = None,
    log_level: str = "DEBUG",
    suppress_default_on_reentry: bool = False,
    precompile: bool = False,
    preload: bool = False,
    context_tags=None,
    **kwargs,
)
```

### Class attributes

```python
HANDLERS = {"ui": UiHandler}   # merged with any `handlers` arg at construction
```

### Signals

`left_mouse_double_click`, `left_mouse_double_click_ctrl`, `middle_mouse_double_click`, `right_mouse_double_click`, `right_mouse_double_click_ctrl`, `key_show_press`, `key_show_release`.

### Methods & properties

| Name | Purpose |
|:---|:---|
| `bindings` *(property, persisted)* | Current chord → ui-name map |
| `default_bindings` *(property)* | Original construction-time map |
| `ui_handler` *(property)* | Shortcut to `sb.handlers.ui` |
| `show(ui=None, pos=None, force=False, **kw)` | Central dispatcher — stacked or standalone based on tags |
| `get(name, **kw) -> QWidget \| None` | Resolve a UI, apply styles, init if needed |
| `hide()` | Reset state, release mouse grab, un-dim, emit parent raise |
| `dim_other_windows()` | Set opacity 0.15 on sibling windows + their open menus (once per hold, only while visible) |
| `restore_other_windows()` | Restore opacity — called by `hideEvent`, so any hide un-dims; callers rarely need it |
| `setCurrentWidget(widget)` | Stacked-widget-style current-widget swap |
| `add_child_event_filter(widgets)` | Install the internal child event filter on widgets |

### Subclass override points

- `HANDLERS` class dict — register DCC-specific handlers.
- `_setup_registry` — custom handler initialization logic.
- `_init_ui`, `_show_window` — customize per-UI-type lifecycle.

---

## `uitk.events`

Source: [events.py](../uitk/events.py)

### `EventFactoryFilter`

```python
EventFactoryFilter(
    parent: QObject = None,
    forward_events_to: object = None,      # typically `self`
    event_name_prefix: str = "",           # e.g. "child_" → "child_mouseButtonPressEvent"
    event_types: set[str | int] = None,    # {"MouseButtonPress", "KeyPress", ...}
    propagate_to_children: bool = False,
)
```

Install on widgets: `filter.install(widgets)` — accepts single widget or iterable; `uninstall(widgets)` / `is_installed(widget)` complete the set.

Handler lookup is lazy: when an event fires, the filter looks for `forward_events_to.<prefix><EventName>(widget, event)` — the event-type enum name with a lowered first letter plus `Event` (`MouseButtonPress` → `mouseButtonPressEvent`) — and calls it if present. Handlers are cached per (forward-target, event_type).

### `MouseTracking`

```python
MouseTracking(
    parent: QWidget,
    track_on_drag_only: bool = True,
    log_level: str = "WARNING",
    auto_update: bool = True,
    buttons_provider=None,
)
```

Tracks the widget under the cursor and delivers synthetic enter/leave (and release) **Qt events** to the child widgets themselves — it defines no Qt signals; observe `enterEvent`/`leaveEvent` on the widgets. `update_child_widgets()` rebuilds the tracked set.

---

## `uitk.FileRegistry`, `uitk.RegistryManager`

Source: [managers/registry_manager.py](../uitk/managers/registry_manager.py)

`RegistryManager` owns the four registries on `Switchboard`. Its `create(descriptor, objects=None, **metadata)` instantiates a `FileRegistry` per registry with filter patterns (`inc_files`, `exc_files`).

```python
sb.registry.ui_registry.get("filename")           # list of filenames
sb.registry.slot_registry.get(classname="EditorSlots", return_field="classobj")
sb.registry.ui_registry.get(filename="editor.ui", return_field="filepath")
```

For the full FileRegistry query API see [managers/registry_manager.py](../uitk/managers/registry_manager.py) source.

> Deprecated aliases: `uitk.FileManager` / `uitk.FileContainer` (and the
> `uitk.file_manager` module) still resolve to these classes and emit a
> `DeprecationWarning`.

---

## `SettingsManager` & `SettingItem`

Source: [managers/settings_manager.py](../uitk/managers/settings_manager.py)

```python
SettingsManager(
    org: str = None,
    app: str = None,
    namespace: str = None,
    qsettings: QSettings = None,
)
```

### Access pattern

Attribute access yields a `SettingsManager.SettingItem` proxy:

```python
item = sb.settings.my_key
item.get(default=42)
item.set(100)
item.changed.connect(callback)
```

Direct attribute **assignment is rejected** — `sb.settings.my_key = 100` raises
`AttributeError` (deliberate, to avoid ambiguity between assigning a proxy and a
value). Always go through `.set(value)`.

### Methods

| Method | Purpose |
|:---|:---|
| `value(key, default=None)` | Get raw value (direct QSettings-style) |
| `setValue(key, value)` | Set raw value |
| `branch(name) -> SettingsManager` | Nested namespace |
| `set_defaults(defaults: dict)` | Register default values for keys that don't exist |
| `on_change(key, callback)` | Callback subscription (`.changed.connect` is the proxy form of the same) |
| `keys() -> list` | All keys in the current namespace |
| `remove(key)` | Remove a single key |
| `clear(key=None)` | Clear a specific key, or all keys in the namespace |
| `sync()` | Flush to disk |
| `setByteArray(key, qba)` / `getByteArray(key)` | For raw `QByteArray` (used for window geometry) |

---

## `StateManager`

Source: [managers/state_manager.py](../uitk/managers/state_manager.py)

```python
StateManager(qsettings: QSettings | SettingsManager, log_level="WARNING")
```

### Methods

| Method | Purpose |
|:---|:---|
| `save(widget, value=None)` | Persist value under `<objectName>/<signal_name>` (current value when `None`) |
| `load(widget)` | Read persisted value and apply it via `apply()` |
| `apply(widget, value)` | Set widget value (routes by signal type via `ValueManager`) |
| `capture_default(widget)` | Snapshot current value as the reset-to default |
| `has_default(widget) -> bool` / `set_default(widget, value)` | Query / explicitly set a widget's default |
| `reset(widget)` / `reset_all(block_signals=False)` | Apply captured default(s) |
| `clear(widget)` | Remove the stored state |
| `save_custom(key, value)` / `load_custom(key, default=None)` / `clear_custom(key)` | Arbitrary key/value persistence through the same store |

### Widget-level flags

- `widget.restore_state: bool` — opt out (default `True`).
- `widget.block_signals_on_restore: bool` — restore silently (default `False`).

---

## `StyleSheet`

Source: [themes/style_sheet.py](../uitk/themes/style_sheet.py)

Attached to every `MainWindow` as `ui.style`.

### Class attributes

```python
themes: dict[str, dict[str, str]]     # "dark" / "light" palettes
```

### Signals

| Signal | Args |
|:---|:---|
| `theme_changed(widget, theme_name, theme_vars)` | Emitted after `set()` |

### Methods

| Method | Purpose |
|:---|:---|
| `set(widget=None, theme="light", style_class="", recursive=False)` | Apply theme and/or style class, optionally to a specific widget |
| `set_theme(theme, widget=None)` | Apply just the theme (no style class) |
| `get_variables(theme="light") -> list[str]` | Variable names defined for a theme |
| `get_variable(name, theme="light")` / `get_variable_px(name, theme="light")` | One variable's value (raw / pixel int) |

---

## `PresetManager`

Source: [managers/preset_manager.py](../uitk/managers/preset_manager.py)

```python
PresetManager(
    parent: QWidget = None,
    state: StateManager = None,
    preset_dir: str | Path = None,
    widgets: list[QWidget] = None,
    log_level: str = "WARNING",
    builtin_dir: str | Path = None,        # read-only second tier of presets
    value_provider=None,                   # custom capture callable
    value_applier=None,                    # custom apply callable
    modified_value_provider=None,
)

# Alternative constructor for standalone mode (no StateManager required):
PresetManager.from_widgets(preset_dir, widgets, builtin_dir=None)
```

### Methods

| Method | Purpose |
|:---|:---|
| `save(name, scope=None) -> Path` | Write current widget values to `<preset_dir>/<name>.json` |
| `load(name, scope=None, block_signals=True) -> int` | Apply a preset; returns the number of widgets set |
| `delete(name) -> bool` | Remove a *user* preset (built-ins are read-only) |
| `rename(old_name, new_name) -> bool` / `exists(name)` / `read(name)` | Rename / probe / read-without-applying |
| `list() -> list[str]` | Names of available presets across both tiers (user + builtin) |
| `wire_combo(combo, on_loaded=None, placeholder=None)` | Wire a `ComboBox` as a preset selector (option-box toolbar: Refresh/Save/⋯-menu, inline naming). Returns the option-box container. |
| `make_preset_combo(parent=None, name=None, tooltip=None, on_loaded=None, placeholder=None)` | Build + wire a preset `ComboBox`; returns its option-box container (`container.preset_combo` reaches the combo). |

`preset_dir` accepts absolute paths, `~` expansion, `$ENV` variables, or short names (`"mayatk/reference_manager"`) resolved under `PresetManager.get_presets_root()` — `<QStandardPaths.GenericConfigLocation>/uitk` by default, redirectable wholesale via `$UITK_PRESETS_ROOT`.

---

## Widget-registration attributes

When a widget registers on a `MainWindow`, it gains these attributes:

| Attribute | Type | Meaning |
|:---|:---|:---|
| `widget.ui` | `MainWindow` | Back-reference to parent UI |
| `widget.base_name()` | `str` | Name without trailing digits / tags |
| `widget.legal_name()` | `str` | Name with illegal chars replaced by `_` |
| `widget.type` | `type` | `type(widget)` |
| `widget.derived_type` | `type` | Nearest `QtWidgets` base |
| `widget.default_signals()` | `str \| None` | Default signal name for this type |
| `widget.tooltip` | `TooltipProxy` | Rich-tooltip formatting proxy ([mixins/tooltip_mixin.py](../uitk/widgets/mixins/tooltip_mixin.py)) |
| `widget.get_slot()` | `callable \| None` | Connected slot method |
| `widget.init_slot(*a)` | — | Manually run `<objectName>_init` |
| `widget.call_slot(*a, **kw)` | — | Manually invoke the handler |
| `widget.connect_slot(s=None)` | — | Wire widget signal to slot |
| `widget.perform_restore_state(force=False)` | — | Re-apply persisted state |
| `widget.register_children()` | — | Walk subtree and register descendants |
| `widget.is_initialized` | `bool` | Set after first `*_init` |
| `widget.refresh_on_show` | `bool` | Re-init on each show (default `False`) |
| `widget.restore_state` | `bool` | Persist value (default `True`) |
| `widget.debounce` | `int` | Milliseconds to coalesce signals (default `0`); also a `.ui` dynamic property. Held while `widget.adjusting` is `True` (the spin boxes: a mouse button down, an uncommitted edit) |
| `widget.slot_timeout` | `float` | Per-widget timeout (seconds); falls back to `ui.default_slot_timeout` |
| `widget.block_signals_on_restore` | `bool` | Restore silently (default `False`) |

Mixin-provided properties:

| Property | Mixin | Type |
|:---|:---|:---|
| `widget.menu` | `MenuMixin` | `Menu` — lazy-created on first access |
| `widget.option_box` | `OptionBoxMixin` | `OptionBoxManager` |
| `widget.set_attributes(**kw)` | `AttributesMixin` | — |
| `widget.set_flags(**kw)` | `AttributesMixin` | — |

---

## Text mixins — `RichTextFormatter`, `TextTruncation`, `RichText`, `TextOverlay`

Source: [widgets/mixins/text.py](../uitk/widgets/mixins/text.py)

- **`RichTextFormatter`** — stateless HTML pipeline shared by the rich-text widgets. `RichTextFormatter.format(string, *, align="left", font_color="white", font_size=None)` applies the standard pipeline; `apply_prefix_styles(string)` colors level-prefix tokens (`Error:`, `Warning:`, …), `apply_inline_styles(string)` upgrades bare HTML tags, `wrap_font_color(string, color)` / `wrap_font_size(string, size)` / `resolve_background(background)` are the primitives.
- **`TextTruncation`** — reusable elision: `calculate_text_truncation` (pixel-based via font metrics), `calculate_character_truncation`, `calculate_word_truncation`, `calculate_path_truncation`, plus `apply_text_truncation` / `create_truncated_button` / `create_truncated_label` / `update_widget_text_truncation`.
- **`RichText`** / **`TextOverlay`** — the widget-inheritance mixins (HTML text via an internal label; overlay text). Which widgets carry them: [Widgets](WIDGETS.md).

---

## Default signals table

From `default_signals` in [switchboard/slots.py](../uitk/switchboard/slots.py):

| Qt class | Default signal |
|:---|:---|
| QAction | `triggered` |
| QCheckBox | `toggled` |
| QComboBox | `currentIndexChanged` |
| QDateEdit | `dateChanged` |
| QDateTimeEdit | `dateTimeChanged` |
| QDial | `valueChanged` |
| QDoubleSpinBox | `valueChanged` |
| QLabel | `released` |
| QLineEdit | `textChanged` |
| QListWidget | `itemClicked` |
| QMenu | `triggered` |
| QMenuBar | `triggered` |
| QProgressBar | `valueChanged` |
| QPushButton | `clicked` |
| QRadioButton | `toggled` |
| QScrollBar | `valueChanged` |
| QSlider | `valueChanged` |
| QSpinBox | `valueChanged` |
| QStackedWidget | `currentChanged` |
| QTabBar | `currentChanged` |
| QTabWidget | `currentChanged` |
| QTableWidget | `cellChanged` |
| QTextEdit | `textChanged` |
| QTimeEdit | `timeChanged` |
| QToolBox | `currentChanged` |
| QTreeWidget | `itemClicked` |

Custom UITK widgets add their own signals — see [WIDGETS.md](WIDGETS.md) for each widget's full signal list.

---

## Everything else on the `uitk` namespace

The remaining public top-level symbols (`uitk/__init__.py` → `DEFAULT_INCLUDE`) and where each is documented:

| Symbols | Home |
|:---|:---|
| Widget classes — `CheckBox`, `CollapsableGroup`, `ColorSwatch`, `ComboBox`, `DoubleSpinBox`, `SpinBox`, `ExpandableList`, `Header`, `Footer` / `FooterStatusController`, `Label`, `LineEdit`, `Menu`, `MenuButton`, `MessageBox`, `ProgressBar`, `PushButton`, `Region`, `Separator`, `Slider`, `TableWidget`, `TextEdit`, `ToolBox`, `TreeWidget`, `WidgetComboBox`, `WindowPanel`, `TextViewBox`, `AttributeWindow`, `ScriptOutput` / `ScriptHighlighter` / `ScriptHighlightRule`, `TextEditLogHandler`, `SequencerWidget` / `ClipData` / `TrackData` | [Widgets](WIDGETS.md) — the per-widget catalog |
| Option-box system — `OptionBox`, `OptionBoxContainer`, `OptionBoxManager`, `BaseOption` / `ButtonOption` and the option classes (`ActionOption`, `MenuOption`, `BrowseOption`, `ClearOption` / `ClearButton`, `ResetOption`, `PinValuesOption`, `ToggleOption`, `DisableOption`, `ValueOption`, `AffixOption`, `OptionMenuOption`, `ContextMenuOption`) | [Widgets § Option Box system](WIDGETS.md) |
| Item-view delegates — `RowSelectionBorderDelegate`, `CenteredIconActionDelegate` (+ `ICON_OPACITY_ROLE`), `ShortcutCaptureDelegate`, `ChoiceCaptureDelegate`, and their `Bordered*` variants | [Widgets § Delegates](WIDGETS.md) |
| Editors — `EditorPanel`, `ColorMappingEditor` / `ColorMappingDialog` (and the `ShortcutEditor` / browser views reached via `sb.editors`) | [Widgets § Editors](WIDGETS.md) |
| Widget mixins — `AttributesMixin`, `ConvertMixin`, `MenuMixin`, `OptionBoxMixin` | [Widgets](WIDGETS.md); the properties they provide are tabled above |
| `Shortcut` (slot decorator) | [Widgets § Shortcut & command registry](WIDGETS.md), with `register_command` above |
| `ShortcutManager`, `GlobalShortcut` | [Widgets § Shortcut & command registry](WIDGETS.md) |
| `SlotWrapper` | [Architecture](ARCHITECTURE.md) § SlotWrapper |
| `Cancelable` | [Slots](SLOTS.md) § `@Cancelable`; host strategy `CancelManager` / `CancelProvider` ([managers/cancel_manager.py](../uitk/managers/cancel_manager.py)) is covered there too |
| `RuntimeLoader`, `CompiledLoader`, `UiCompiler`, `PrecompileJob` | [Architecture](ARCHITECTURE.md) § UI loading & compilation |
| `DesignerPlugin`, `DesignerWidget` | [Widgets § Using the widgets in Qt Designer](WIDGETS.md) |
| `AttributeSpec`, `KindHandler`, `KindFactory` | [Bridge](BRIDGE.md) — the kind-handler registry |
| `Bootstrap` | [_bootstrap.py](../uitk/_bootstrap.py) — pre-`QApplication` setup for standalone processes; `Bootstrap.configure_high_dpi() -> bool` is the whole surface |
| `EmbeddedMenuWidget`, `PersistentMenu` | [widgets/embeddedMenu.py](../uitk/widgets/embeddedMenu.py) — host a live `QMenu` as ordinary widget content, sized exactly to it (`content_size`, `fit_to_window`; `PersistentMenu` ignores hide attempts) |
| `IconManager` | Theme-aware SVG icon loader — `get(name, size, color)`, `set_icon`, `register_icon_dir`, `set_default_color`; usage notes in [Widgets](WIDGETS.md) |
| `ValueManager` | Static get/set for most Qt widget values, routed by type or signal name ([managers/value_manager.py](../uitk/managers/value_manager.py)); `StateManager.apply` builds on it |
| `OptionalPackageManager` | Probe for / offer to install an optional package importable in this session — `available(spec)`, `ensure(spec, feature=...)` ([managers/optional_package_manager.py](../uitk/managers/optional_package_manager.py)); bridge panels expose it via `ensure_optional_package` ([Bridge](BRIDGE.md)) |
| `RecentValuesStore` | Widget-free most-recent-first value history — `record`, `values`, `subscribe`, `prune_invalid` ([managers/recent_values_store.py](../uitk/managers/recent_values_store.py)); backs the `RecentValuesOption` in [Widgets](WIDGETS.md) |
| `FileManager`, `FileContainer` | Deprecated aliases — see the `FileRegistry` / `RegistryManager` section above |

---

## See also

- [User Guide](USER_GUIDE.md) — narrative introduction
- [Slots](SLOTS.md) — slot contract in depth
- [Widgets](WIDGETS.md) — per-widget API
- [Marking Menu](MARKING_MENU.md) — radial menu subsystem
- [Architecture](ARCHITECTURE.md) — internals
- [Cookbook](COOKBOOK.md) — patterns from real usage
