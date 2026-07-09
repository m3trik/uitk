# API Reference

Public signatures for the core UITK classes. For prose explanations, see the [User Guide](USER_GUIDE.md) and [Architecture](ARCHITECTURE.md).

**Nav**: [← README](README.md) · [User Guide](USER_GUIDE.md) · [Slots](SLOTS.md) · [Widgets](WIDGETS.md) · [Marking Menu](MARKING_MENU.md) · [Architecture](ARCHITECTURE.md) · [Cookbook](COOKBOOK.md)

Line references link to the current source.

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
) -> Switchboard
```

### Instance attributes

| Attr | Type | Meaning |
|:---|:---|:---|
| `loaded_ui` | `NamespaceHandler` | Dynamic resolver — `sb.loaded_ui.editor` → `MainWindow` |
| `registered_widgets` | `NamespaceHandler` | Custom widget classes discovered via `widget_source` |
| `registered_icons` | `NamespaceHandler` | Icon paths discovered via `icon_source` |
| `slot_instances` | `NamespaceHandler` | Instantiated slot class instances |
| `registry` | `FileManager` | Typed registries: `ui_registry`, `slot_registry`, `widget_registry`, `icon_registry` |
| `handlers` | `SimpleNamespace` | `sb.handlers.ui`, `sb.handlers.marking_menu`, custom handlers |
| `settings` | `SettingsManager` | QSettings wrapper with `namespace="switchboard"` |
| `configurable` | `SettingsManager` | Branch of `settings` for handler DEFAULTS + app config |
| `convert` | `ConvertMixin` | Type conversion helpers |
| `default_signals` | `dict[type, str]` | Qt widget class → default signal name |
| `app` | `QApplication` | Existing instance or new one created on import |

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
| `get_ui(ui=None) -> QWidget \| list \| None` | Resolve by name, return current if `None`, pass-through if already a widget |
| `get_ui_relatives(ui, upstream=False, exact=False, downstream=False, reverse=False) -> list` | Tag-depth-based relatives via shared base name |
| `find_ui_filename(legal_name, unique_match=False) -> str \| list \| None` | Legal-name-to-original-filename resolver |
| `ui_history(index=None, allow_duplicates=False, inc=[], exc=[])` | Ordered history of current-UI transitions |

### Methods — widgets & slots

| Method | Purpose |
|:---|:---|
| `get_widget(name, ui=None) -> QWidget \| None` | Find a registered widget by name, optionally in a specific UI |
| `register_widget(widget_class_info)` | Manually register a widget class (rare — usually automatic) |
| `get_slots_instance(ui) -> object \| None` | Return the slot class instance for a UI, creating on first access |
| `init_slot(widget)` | Run `<objectName>_init` for a widget |
| `connect_slot(widget, slot=None)` | Wire widget signals to slot method |
| `call_slot(widget, *args, **kwargs)` | Invoke the slot manually |
| `slot_history(index=None, add=None, allow_duplicates=False)` | Ordered history of slot calls |
| `prev_slot` *(property)* | Last executed slot method, or None |
| `get_default_signals(widget) -> set` | Default Qt signals available on a widget |
| `get_available_signals(widget, derived=True, exc=[]) -> set` | All Qt signals on a type, optionally including inherited |

### Methods — dialogs & widget helpers

| Method | Purpose |
|:---|:---|
| `message_box(text, *buttons) -> str \| None` | Themed QMessageBox replacement |
| `file_dialog(file_types="All Files (*)", caption=None, dir=None) -> str` | Themed file picker |
| `dir_dialog(caption=None, dir=None) -> str` | Themed directory picker |
| `center_widget(widget, pos=None, offset_x=0, offset_y=0, padding_x=None, padding_y=None, relative=None)` | Reposition + optionally resize |
| `get_cursor_offset_from_center(widget) -> QPoint` | Static — `QCursor.pos() - widget.rect().center()` |
| `toggle_multi(ui, **kwargs)` | Batch-set properties on named widgets |
| `connect_multi(ui, widgets, signals, slots)` | Batch signal-slot connection |
| `create_button_groups(ui, name_range)` | Radio groups from a range like `"chk_001-3"` |
| `unpack_names(name_string) -> list[str]` | Static — expand `"chk021-23,25,tb001"` into individual names |

### Methods — registration

| Method | Purpose |
|:---|:---|
| `register(ui_location=None, slot_location=None, widget_location=None, icon_location=None, base_dir=1, recursive=False, validate=0, tags=None)` | Add new sources after construction |
| `register_handler(name, instance, defaults=None)` | Attach `instance` at `sb.handlers.<name>`, merge `defaults` into `sb.configurable.<name>` |
| `register_shortcut(ui, sequence, callback)` | Register a keyboard shortcut on a UI |

### Properties

| Property | Type | Meaning |
|:---|:---|:---|
| `current_ui` | `QWidget` | Most recently shown / focused UI, auto-set from singletons |
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
    add_footer: bool = True,
    ensure_on_screen: bool = True,
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
| `settings` | `SettingsManager` | Branch keyed by window name |
| `state` | `StateManager` | Widget state persistence |
| `style` | `StyleSheet` | Theme manager with `.set(theme=..., style_class=...)` and `.theme_changed` signal |
| `footer` | `Footer \| None` | Auto-created unless `add_footer=False` |
| `header` | `Header \| None` | If one is present in the `.ui` |
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
| `request_hide() -> bool` | Pin-aware hide — returns True if hidden, False if blocked by pin |
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

Wraps the call in `self.blockSignals(True)` … `self.blockSignals(False)`. Use on slot methods that mutate widgets and would otherwise re-trigger themselves.

---

## `uitk.handlers.UiHandler`

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

DEFAULTS = {
    "default_position":   None,    # "cursor" | "screen" | "last" | (x, y)
    "remember_position":  True,
    "remember_size":      True,
    "style":              DEFAULT_STYLE,
}

UI_REGISTRY: dict = {}   # subclass override for manual ui-name → path maps
```

### Methods

| Method | Purpose |
|:---|:---|
| `get(name, reload=False, **kw) -> QWidget \| None` | Resolve UI + apply styles |
| `show(ui, pos=None, force=False, **kw) -> QWidget` | Show and position a UI |
| `apply_styles(ui, style=None)` | Apply `DEFAULT_STYLE` (or override) with tag-based adjustments |
| `setup_lifecycle(ui, hide_signal=None)` | Connect a signal to `ui.request_hide()` |

Subclass for DCC integration — override `show`, `apply_styles`, or provide a `UI_REGISTRY`.

---

## `uitk.MarkingMenu`

Source: [widgets/marking_menu/_marking_menu.py](../uitk/widgets/marking_menu/_marking_menu.py)

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
| `hide()` | Reset state, release mouse grab, emit parent raise |
| `dim_other_windows()` | Set opacity 0.15 on sibling windows |
| `restore_other_windows()` | Restore opacity |
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
    event_name_prefix: str = "",           # e.g. "child_" → "child_mousePressEvent"
    event_types: set[str | int] = None,    # {"MouseButtonPress", "KeyPress", ...}
    propagate_to_children: bool = False,
)
```

Install on widgets: `filter.install(widgets)` — accepts single widget or iterable.

Handler lookup is lazy: when an event fires, the filter looks for `forward_events_to.<prefix><EventName>(event, widget)` and calls it if present. Handlers are cached per (widget_id, event_type) for efficiency.

### `MouseTracking`

```python
MouseTracking(
    parent: QWidget,
    auto_update: bool = True,
)
```

Emits `enter(widget)` and `leave(widget)` signals for child widgets. `update_child_widgets()` rebuilds the tracked set.

---

## `uitk.FileContainer`, `uitk.FileManager`

Source: [file_manager.py](../uitk/file_manager.py)

`FileManager` owns the four registries on `Switchboard`. Its `create(name, objects, **cfg)` instantiates a `FileContainer` per registry with filter patterns (`inc_files`, `exc_files`).

```python
sb.registry.ui_registry.get("filename")           # list of filenames
sb.registry.slot_registry.get(classname="EditorSlots", return_field="classobj")
sb.registry.ui_registry.get(filename="editor.ui", return_field="filepath")
```

For the full FileContainer query API see [file_manager.py](../uitk/file_manager.py) source.

---

## `SettingsManager` & `SettingItem`

Source: [widgets/mixins/settings_manager.py](../uitk/widgets/mixins/settings_manager.py)

```python
SettingsManager(
    namespace: str = None,
    org: str = None,
    app: str = None,
    parent: QObject = None,
)
```

### Access pattern

Attribute access yields a `SettingItem` proxy:

```python
item = sb.settings.my_key
item.get(default=42)
item.set(100)
item.changed.connect(callback)
```

Legacy attribute-style access works via `__setattr__` intercept:
```python
sb.settings.my_key = 100      # equivalent to sb.settings.my_key.set(100)
```

### Methods

| Method | Purpose |
|:---|:---|
| `value(key, default=None)` | Get raw value (direct QSettings-style) |
| `setValue(key, value)` | Set raw value |
| `branch(name) -> SettingsManager` | Nested namespace |
| `set_defaults(defaults: dict)` | Register default values for keys that don't exist |
| `on_change(key, callback)` | Legacy signal subscription (prefer `.changed.connect`) |
| `clear(key)` | Remove a key |
| `sync()` | Flush to disk |
| `setByteArray(key, qba)` / `getByteArray(key)` | For raw `QByteArray` (used for window geometry) |

---

## `StateManager`

Source: [widgets/mixins/state_manager.py](../uitk/widgets/mixins/state_manager.py)

```python
StateManager(qsettings: QSettings, log_level="WARNING")
```

### Methods

| Method | Purpose |
|:---|:---|
| `save(widget, value)` | Persist value under `<objectName>/<signal_name>` |
| `load(widget) -> Any` | Read persisted value and apply it via `apply()` |
| `apply(widget, value)` | Set widget value (routes by signal type via `ValueManager`) |
| `capture_default(widget)` | Snapshot current value as the reset-to default |
| `get_default(widget) -> Any` | Retrieve captured default |
| `reset(widget)` | Apply captured default |

### Widget-level flags

- `widget.restore_state: bool` — opt out (default `True`).
- `widget.block_signals_on_restore: bool` — restore silently (default `False`).

---

## `StyleSheet`

Source: [widgets/mixins/style_sheet.py](../uitk/widgets/mixins/style_sheet.py)

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
| `set(theme: str = None, style_class: str = None, widget: QWidget = None)` | Apply theme and/or style class, optionally to a specific widget |
| `get_theme_vars(theme=None) -> dict` | Palette dict for a theme |
| `get_active_theme() -> str` | Currently applied theme name |

---

## `PresetManager`

Source: [widgets/mixins/preset_manager.py](../uitk/widgets/mixins/preset_manager.py)

```python
PresetManager(
    parent: QWidget = None,
    state: StateManager = None,
    preset_dir: str | Path = None,
    widgets: list[QWidget] = None,
    log_level: str = "WARNING",
)

# Alternative constructor for standalone mode (no StateManager required):
PresetManager.from_widgets(preset_dir, widgets)
```

### Methods

| Method | Purpose |
|:---|:---|
| `save(name: str)` | Write current widget values to `<preset_dir>/<name>.json` |
| `load(name: str)` | Apply a preset |
| `delete(name: str)` | Remove preset file |
| `list_presets() -> list[str]` | Names of available presets |
| `wire_combo(combo, on_loaded=None)` | Wire a `ComboBox` as a preset selector (option-box toolbar: Refresh/Save/⋯-menu, inline naming). Returns the option-box container. |
| `make_preset_combo(parent=None, name=None, tooltip=None, on_loaded=None)` | Build + wire a preset `ComboBox`; returns its option-box container (`container.preset_combo` reaches the combo). |

`preset_dir` accepts absolute paths, `~` expansion, `$ENV` variables, or short names resolved under `QStandardPaths.AppConfigLocation`.

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
| `widget.default_signals()` | `str` | Default signal name for this type |
| `widget.get_slot()` | `callable \| None` | Connected slot method |
| `widget.init_slot(*a)` | — | Manually run `<objectName>_init` |
| `widget.call_slot(*a, **kw)` | — | Manually invoke the handler |
| `widget.connect_slot(s=None)` | — | Wire widget signal to slot |
| `widget.perform_restore_state(force=False)` | — | Re-apply persisted state |
| `widget.register_children()` | — | Walk subtree and register descendants |
| `widget.is_initialized` | `bool` | Set after first `*_init` |
| `widget.refresh_on_show` | `bool` | Re-init on each show (default `False`) |
| `widget.restore_state` | `bool` | Persist value (default `True`) |
| `widget.debounce` | `int` | Milliseconds to coalesce signals (default `0`) |
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

## See also

- [User Guide](USER_GUIDE.md) — narrative introduction
- [Slots](SLOTS.md) — slot contract in depth
- [Widgets](WIDGETS.md) — per-widget API
- [Marking Menu](MARKING_MENU.md) — radial menu subsystem
- [Architecture](ARCHITECTURE.md) — internals
- [Cookbook](COOKBOOK.md) — patterns from real usage
