# Architecture

How UITK is built internally, and why. Read this after the [User Guide](USER_GUIDE.md) and [Slots](SLOTS.md) — those explain *what* to do; this explains *how it works*.

**Nav**: [← README](README.md) · [User Guide](USER_GUIDE.md) · [Slots](SLOTS.md) · [Widgets](WIDGETS.md) · [Marking Menu](MARKING_MENU.md) · [Cookbook](COOKBOOK.md) · [API](API_REFERENCE.md)

---

## 1. Design principles

1. **Convention over configuration.** Names carry meaning. UI filenames map to slot classes; `objectName`s map to methods; `#`-tags map to UI hierarchy. Every convention is overridable.
2. **Composition over inheritance.** Widgets gain capabilities through narrow mixins (`MenuMixin`, `OptionBoxMixin`, `AttributesMixin`, `RichText`), not deep class trees. The Switchboard itself is split into private partials co-located in [uitk/switchboard/](../uitk/switchboard/) and glued together by `Switchboard` in `_core.py`.
3. **Lazy everything.** Widgets register on first access. UIs load on first attribute access (`sb.loaded_ui.editor`). Menus and option boxes create themselves only when touched. Slot signatures are introspected once, then cached.
4. **Dependency injection, not global state.** Slot classes receive the `Switchboard` via constructor kwargs. Handlers are registered with the Switchboard. No singletons in the hot paths (`MarkingMenu` uses `SingletonMixin` only because there's one radial menu per host at a time).
5. **Extend via registries and handlers.** New widgets, slots, icons, and UIs get added to typed registries. New behaviors (window positioning, styling, DCC integration) get added as handlers on `sb.handlers.*`.

---

## 2. System overview

```
                     ┌─────────────────────────────────────┐
                     │           Switchboard                │
                     │ (QUiLoader + 5 mixins + FileManager) │
                     └─────────────────────────────────────┘
                                       │
          ┌────────────────┬───────────┼─────────────┬──────────────────┐
          │                │           │             │                  │
          ▼                ▼           ▼             ▼                  ▼
    FileManager     loaded_ui   registered_    slot_instances      sb.handlers
    ui_registry    (WeakValue)  widgets        (per-UI)            .ui  (UiHandler)
    slot_registry               registered_                         .marking_menu
    widget_registry             icons                               .<custom>
    icon_registry
          │
          │ MainWindow(QMainWindow + AttributesMixin + LoggingMixin)
          ▼
    ┌──────────────────────────────────────────────────────┐
    │ tags · state · settings · style · widgets set · slots │
    │ lifecycle signals · pin state · footer · size grip    │
    └──────────────────────────────────────────────────────┘
          │
          ▼  child widgets registered via QEvent.ChildPolished filter
    Widget (base Qt class + MenuMixin + OptionBoxMixin + mixins)
    widget.ui · widget.base_name() · widget.type · widget.derived_type
    widget.default_signals() · widget.get_slot() · widget.init_slot()
    widget.restore_state · widget.debounce · widget.slot_timeout
```

---

## 3. Switchboard — the orchestrator

[uitk/switchboard/_core.py](../uitk/switchboard/_core.py). The Switchboard
class composes private partials co-located in the
[uitk/switchboard/](../uitk/switchboard/) package:

```python
class Switchboard(
    QtCore.QObject,
    ptk.HelpMixin,                 # introspection helpers
    ptk.LoggingMixin,              # named logger, log_prefix
    SwitchboardSlotsMixin,         # slot resolution, Signals, SlotWrapper
    SwitchboardShortcutMixin,      # keyboard shortcut registration
    SwitchboardWidgetMixin,        # widget resolution + registration
    SwitchboardUtilsMixin,         # center_widget, unpack_names, dialogs
    SwitchboardNameMixin,          # tag/base name parsing, legal-name conversion
    SwitchboardEditorsMixin,       # sb.editors registry (style/hotkey/browser)
    SwitchboardStyleMixin,         # sb.style — lazy StyleSheet accessor
): ...
```

Each partial lives in `uitk/switchboard/_<name>.py` (e.g. `_slots.py`,
`_shortcuts.py`). The leading underscore signals these are not
standalone mixins — they exist only as composition pieces of
`Switchboard` and aren't intended for reuse outside this package.

The companion module [uitk/widgets/mixins/shortcuts.py](../uitk/widgets/mixins/shortcuts.py)
holds the *generic* shortcut primitives (``GlobalShortcut``,
``ShortcutManager``, ``ShortcutMixin``) that any Qt widget can adopt
without involving Switchboard.

### Registries

Built by `FileManager` in [uitk/file_manager.py](../uitk/file_manager.py). Four typed registries:

| Registry | Inclusion pattern | Fields |
|:---|:---|:---|
| `ui_registry` | `*.ui` | filename, filepath |
| `slot_registry` | `*.py` (excluding `*_ui.py`) | classname, classobj, filename, filepath |
| `widget_registry` | `*.py` (excluding `*_ui.py`) | classname, classobj, filename, filepath |
| `icon_registry` | `*.svg, *.png, *.jpg, *.bmp, *.ico` | filename, filepath |

Each accepts paths, module objects, directories (recursive or not), or class objects. The `FileContainer` abstraction extends `ptk.NamedTupleContainer` for query / filter operations.

### Namespace handlers

Four `ptk.NamespaceHandler` instances give dot-notation access with lazy resolution:

```python
sb.loaded_ui.editor            # calls _resolve_ui("editor") → returns MainWindow
sb.registered_widgets.PushButton
sb.registered_icons.save
sb.slot_instances.editor       # returns EditorSlots instance (weak-ref caches removed here)
```

Three use `WeakValueDictionary` under the hood (`loaded_ui`, `registered_widgets`, `registered_icons`) so destroyed widgets don't pin memory.

### Settings

`sb.settings = SettingsManager(namespace="switchboard")` — QSettings wrapper with dot-notation `SettingItem` proxies. Each key supports `.get()`, `.set()`, `.changed.connect(cb)`.

`sb.configurable = sb.settings.branch("configurable")` — nested namespace for handler DEFAULTS and app-wide config.

```python
sb.configurable.ui.default_position.set("cursor")
sb.configurable.my_feature.enabled.changed.connect(self._on_toggle)
```

### Handler ecosystem

`sb.handlers` is a plain namespace. Handlers registered at construction or via `register_handler(name, instance, defaults)`:

```python
sb = Switchboard(handlers={"ui": UiHandler, "my_svc": MyService})
sb.handlers.ui                    # instance
sb.handlers.my_svc.do_something()
```

Handler class attribute `DEFAULTS = {...}` is merged into `sb.configurable.<handler_name>` so handler config is automatically persistent and reactive. See [handlers/ui_handler.py:30](../uitk/handlers/ui_handler.py#L30) for the `UiHandler.DEFAULTS` example.

---

## 4. Package bootstrap — lazy symbol exposure

`uitk/__init__.py` uses `pythontk.bootstrap_package` to expose ~50 public symbols via a module-level `__getattr__`. The `DEFAULT_INCLUDE` dict maps symbol names to `module.path : ClassName`:

```python
DEFAULT_INCLUDE = {
    "switchboard": ["Switchboard", "Signals", "SlotWrapper", "Shortcut"],
    "widgets.pushButton": "PushButton",
    ...
}
```

Result: `from uitk import Signals, PushButton, Switchboard` works without any of those modules actually importing at package load time. First access triggers the import and caches the class on the package.

This matters because UITK is used inside DCCs (Maya, Blender) where import-time cost is visible to the user and import-time side effects are banned (a `PushButton` import that accidentally built a `QApplication` would crash a Maya startup).

---

## 5. MainWindow — the UI wrapper

[uitk/widgets/mainWindow.py](../uitk/widgets/mainWindow.py), 837 lines. Every loaded `.ui` file is wrapped in a `MainWindow` (not the `QMainWindow` from the `.ui` — UITK wraps it).

### Responsibilities

- Store **tags**, **path**, **settings branch** (`SettingsManager(org="uitk", app=<name>)`).
- Hold the **StateManager** for widget persistence.
- Hold the **StyleSheet** manager for theming.
- Track registered widgets in `self.widgets` (set).
- Emit **lifecycle signals**: `on_show`, `on_first_show`, `on_hide`, `on_close`, `on_focus_in/out`, `on_child_registered(widget)`, `on_child_changed(widget, value)`, `on_pinned_changed(bool)`.
- Auto-create a **footer** with size grip (unless `add_footer=False` or one exists in the `.ui`).
- Debounced **geometry save** (500ms timer) on resize/move.
- **Pin state** via `_pinned` + `request_hide()` — pinned windows refuse `request_hide`.

### Child widget registration

The clever bit. When a widget is added to the central widget tree, Qt fires a `QEvent.ChildPolished` on the `MainWindow`. The `MainWindow.eventFilter` catches it and calls `register_widget(child)`. No manual registration, no timing issues.

```python
def eventFilter(self, watched, event):
    if watched is self and event.type() == QtCore.QEvent.ChildPolished:
        child = event.child()
        if isinstance(child, QtWidgets.QWidget):
            if child.objectName() and child not in self.widgets:
                self.register_widget(child)
    return super().eventFilter(watched, event)
```

`register_widget` injects these attributes onto the widget:

| Attribute | Role |
|:---|:---|
| `widget.ui` | Back-reference to `MainWindow` |
| `widget.base_name()` | Name with tags and trailing digits stripped |
| `widget.legal_name()` | Illegal chars replaced with `_` |
| `widget.type` | `type(widget)` |
| `widget.derived_type` | Nearest `QtWidgets` base class |
| `widget.default_signals()` | Default signal name for this type |
| `widget.get_slot()` | Connected slot method or None |
| `widget.init_slot(*a, **kw)` | Manually invoke `*_init` |
| `widget.call_slot(*a, **kw)` | Manually invoke the handler |
| `widget.connect_slot(s=None)` | Connect widget signal → slot |
| `widget.is_initialized` | Flag for first-show setup |
| `widget.refresh_on_show` | Re-run `*_init` on each show |
| `widget.restore_state` | Opt out of state persistence |

The widget is then added to `self.widgets`, `on_child_registered` is emitted, and `widget.init_slot()` is called (which runs the slot class's `<name>_init` method if one exists).

### Lifecycle sequence on first show

```
1. showEvent()
2. CollapsableGroup._enforce_state(suppress_resize=True)  # settle groups
3. restore_window_geometry()                              # restore size/pos
4. _ensure_on_screen()                                    # clamp to monitor
5. register_children()                                    # catch widgets not caught by ChildPolished
6. trigger_deferred()                                     # run deferred setup
7. on_first_show signal                                   # slot classes can hook here
8. on_show signal
9. is_initialized = True
```

Subsequent shows skip steps 2-5.

### Cross-UI state sync

When a widget's default signal fires, `MainWindow._add_child_changed_signal` forwards the value to `on_child_changed(widget, value)`, which calls `sync_widget_values` → iterates `get_ui_relatives(widget.ui, upstream=True, downstream=True)`, saves + applies the value to same-named widgets in related UIs.

---

## 6. Slot system — how `btn_save()` actually gets called

Implementation: [switchboard/_slots.py](../uitk/switchboard/_slots.py).

### Resolution

1. Widget registers on `MainWindow`.
2. `init_slot(widget)` runs → looks up `slots.<objectName>_init` → calls it if found.
3. `connect_slot(widget)` runs:
   - Find `slots.<objectName>` method.
   - Determine signals: from `@Signals` decorator (wrapper attribute), or `widget.default_signals()`.
   - Wrap the slot in `SlotWrapper(slot, widget, sb)`.
   - Connect each signal to the wrapper.

### SlotWrapper

The wrapper handles four concerns:

1. **Parameter injection.** Caches `inspect.signature(slot)` per slot function, checks if `widget` is in the param names. If yes and caller didn't pass it, injects `widget=self.widget`.
2. **Debounce.** If `widget.debounce > 0`, stores args in `_debounce_args`, starts/restarts a single-shot `QTimer`, defers `_invoke` until the timer fires.
3. **Timeout.** If `widget.slot_timeout > 0` (or `ui.default_slot_timeout`), wraps the call in `ptk.ExecutionMonitor.execution_monitor(threshold=..., indicator=True, allow_escape_cancel=True)`. Shows a progress overlay and lets the user press Esc to cancel long-running slots.
4. **History.** Pushes slot onto `sb.slot_history` before execution.

### `@Signals` — the decorator

```python
class Signals:
    def __init__(self, *signals):      # @Signals("clicked", "pressed")
        self.signals = signals
    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper.signals = self.signals  # The mixin reads this attribute
        return wrapper
```

The wrapper annotation (`wrapper.signals`) is the override signal. `Signals()` with no args still attaches an empty tuple — used to mean "don't auto-connect".

`@Signals.blockSignals` is a separate classmethod decorator that wraps in `self.blockSignals(True)` / `False` during execution.

---

## 7. State management

Layered — each layer speaks to one concern.

```
    Widget value                 (int, str, bool, QColor, …)
         │
         ▼
    ValueManager                 get_value_by_signal / set_value_by_signal
         │ (per widget type: uses text(), value(), isChecked(), currentIndex())
         ▼
    StateManager                 save / load / apply / capture_default
         │ (per-widget state key: "<objectName>/<signal_name>")
         │ (protections: no None to text widgets, only primitives serialized)
         ▼
    SettingsManager              QSettings-backed key/value store
         │ (SettingItem proxies: .get(), .set(), .changed.connect())
         │ (namespaces via .branch(name))
         ▼
    QSettings                    Platform-native persistent storage
```

`MainWindow.state = StateManager(self.settings)`. `ui.settings = sb.settings.branch(name)` — each UI gets its own namespace, keyed by `objectName`.

Protections in `StateManager`:
- Skips applying `None` to text widgets (would clear valid text).
- Serializes only `int`, `float`, `str`, `bool` — objects are ignored.
- Handles non-stateful signals (e.g. `clicked`) by not writing state.

---

## 8. Handler ecosystem in detail

Handlers extend UITK without subclassing `Switchboard`. Three touchpoints:

1. **Instantiation.** Pass `handlers={"name": HandlerClass}` to `Switchboard`. Each class is instantiated with `switchboard=self` (or `HandlerClass.instance(switchboard=self)` if it has an `instance` classmethod, as `SingletonMixin` does).
2. **Defaults.** `HandlerClass.DEFAULTS = {...}` is merged into `sb.configurable.<name>`. The handler reads its config via `self.sb.configurable.<name>.<key>.get()`.
3. **Registration.** The handler instance is attached at `sb.handlers.<name>`. Slot classes and other handlers access it directly: `self.sb.handlers.ui.apply_styles(ui)`.

### Built-in handlers

`UiHandler` ([handlers/ui_handler.py](../uitk/handlers/ui_handler.py)):
- `DEFAULT_STYLE` — `{attributes, flags, theme, style_class, header_buttons}`.
- `apply_styles(ui)` — merges DEFAULT_STYLE with tag overrides (stacked menus get `translucentBgNoBorder`), applies to widget.
- `show(ui, pos, force)` — positions window (`cursor`/`screen`/QPoint/tuple) with layout activation for accurate sizing.
- `setup_lifecycle(ui, hide_signal)` — wires a hide signal (typically `marking_menu.key_show_release`) to `ui.request_hide()` for pin-aware auto-hide.

`MarkingMenu` registers itself as `sb.handlers.marking_menu`. See [MARKING_MENU.md](MARKING_MENU.md).

### Custom handler example

```python
class ClipboardHandler(ptk.LoggingMixin):
    DEFAULTS = {"history_size": 50}

    def __init__(self, switchboard, **kwargs):
        self.sb = switchboard
        self._history = []

    @property
    def history_size(self):
        return self.sb.configurable.clipboard.history_size.get(50)

    def push(self, value):
        self._history.append(value)
        self._history = self._history[-self.history_size:]

sb = Switchboard(handlers={"clipboard": ClipboardHandler})
sb.handlers.clipboard.push("foo")
sb.configurable.clipboard.history_size.set(100)
```

---

## 9. StyleSheet & theming

[widgets/mixins/style_sheet.py](../uitk/widgets/mixins/style_sheet.py). Palette-driven theming rather than free-form CSS.

Themes are Python dicts:
```python
themes = {
    "dark": {
        "WIDGET_BACKGROUND": "rgb(60,60,60)",
        "BUTTON_HOVER":      "rgba(100,130,150,225)",
        "TEXT_COLOR":        "rgb(220,220,220)",
        "ACTION_VALID_FG":   "rgb(168,213,162)",
        ...
    },
    "light": { ... }
}
```

`ui.style.set(theme=..., style_class=...)` substitutes `%(KEY)s` placeholders in the theme's QSS template (`widgets/mixins/style.qss`) and applies it to the window. Emits `theme_changed(widget, name, vars)` for downstream consumers (icon recoloring, custom overlays).

Action colors on `LineEdit`, `TableWidget`, `TreeWidget` read directly from the palette — `ACTION_VALID_FG/BG`, `ACTION_INVALID_FG/BG`, `ACTION_WARNING_FG/BG`, `ACTION_INFO_FG/BG`, `ACTION_INACTIVE_FG`.

Monochrome SVG icons are auto-colored by the `IconManager` mixin, reading `ICON_COLOR` from the active palette.

---

## 10. UI hierarchy via tag depth

`get_ui_relatives(ui, upstream=False, exact=False, downstream=False, reverse=False)` in [switchboard.py:549](../uitk/switchboard.py#L549).

1. Resolve target to base name (`get_base_name("menu#file") == "menu"`).
2. Find all UIs in `ui_registry` sharing that base name.
3. Filter by tag depth (`name.count("#")`) vs. target's depth:
   - `upstream` → depth < target
   - `downstream` → depth > target
   - `exact` → depth == target

Returns names or loaded widgets depending on input type. Enables:
- Nested menus (`menu#file#recent` is descendant of `menu#file` is descendant of `menu`).
- Sibling navigation (all `cameras#*` submenus).
- Ancestor traversal for state sync.

---

## 11. Resolution order for `sb.loaded_ui.xxx`

From [switchboard.py:254](../uitk/switchboard.py#L254):

```
sb.loaded_ui.editor
       │
       ▼
_resolve_ui("editor")
       │
       ├── find_ui_filename("editor", unique_match=True)
       │   ├── regex-match against ui_registry filenames
       │   └── returns "editor" or "editor#something" if unique
       │
       ├── if no filename match:
       │   └── _resolve_ui_using_slots("editor")
       │         ├── find slot class by name
       │         ├── if found: create empty UI + attach slot instance
       │         └── (enables "headless" slot classes without a .ui)
       │
       └── if filename match:
           ├── load_ui(filepath)    # QUiLoader
           ├── get_property_from_ui_file → discover custom widgets
           │    → register each unknown custom widget class
           ├── load via QUiLoader
           ├── add_ui(name, widget, path)
           │    ├── wrap in MainWindow
           │    ├── merge tags from filename + source tags
           │    ├── attach settings branch
           │    └── store in loaded_ui
           └── return MainWindow
```

Source tags come from `sb.register(ui_location=..., tags={"menu"})` — tag all UIs in a directory without renaming them.

---

## 12. Extension points — where to hook, where not to

| Task | How | Don't |
|:---|:---|:---|
| Add a custom widget | Subclass Qt widget + UITK mixins, let Qt Designer promote, ensure it's in `widget_source` or `DEFAULT_INCLUDE` | Don't edit `DEFAULT_INCLUDE` in your app — use `widget_source` |
| Add a DCC-specific window handler | Subclass `UiHandler`, pass via `handlers={"ui": MyUiHandler}` | Don't subclass `Switchboard` |
| Add cross-cutting behavior | New handler with `DEFAULTS` dict, register via `handlers={...}` | Don't monkeypatch `Switchboard` |
| Add a widget capability | New mixin in your own package, declare on your widgets | Don't edit UITK's mixins in-place |
| Run slots in background | Wrap slot body in `QThread` or use `uitk.widgets.mixins.tasks.WorkIndicator` | Don't offload inside the SlotWrapper |
| Persist custom config | `sb.configurable.<namespace>.<key>.set/get/.changed.connect` | Don't bypass with raw `QSettings` |
| React to theme change | Connect to `ui.style.theme_changed(widget, name, vars)` | Don't poll styles |
| React to widget lifecycle | Connect to `ui.on_show`, `on_first_show`, `on_child_registered`, etc. | Don't override `showEvent` without super |

---

## 13. File map

```
uitk/
├── __init__.py                # DEFAULT_INCLUDE + bootstrap_package
├── switchboard.py             # orchestrator (729 lines)
├── file_manager.py            # typed registries (563 lines)
├── events.py                  # EventFactoryFilter, MouseTracking
│
├── handlers/
│   └── ui_handler.py          # UiHandler (sb.handlers.ui)
│
├── widgets/
│   ├── mainWindow.py          # UI wrapper (837 lines)
│   ├── menu.py                # Menu (2762 lines)
│   ├── header.py, footer.py   # frameless window chrome
│   ├── pushButton.py, checkBox.py, comboBox.py, lineEdit.py, ...
│   ├── marking_menu/
│   │   ├── _marking_menu.py   # MarkingMenu (1385 lines)
│   │   └── overlay.py         # gesture trail + widget cloning
│   ├── optionBox/
│   │   ├── _optionBox.py      # OptionBox, OptionBoxContainer
│   │   ├── utils.py           # OptionBoxManager + widget patching
│   │   └── options/           # ClearOption, BrowseOption, PinValuesOption, ...
│   ├── sequencer/             # full animation timeline
│   ├── editors/               # ColorMappingEditor, HotkeyEditor, StyleEditor
│   └── mixins/
│       ├── switchboard_*.py   # slots / widgets / utils / names mixins
│       ├── attributes.py      # set_attributes / set_flags
│       ├── menu_mixin.py      # .menu descriptor
│       ├── option_box_mixin.py # .option_box descriptor
│       ├── state_manager.py   # widget state persistence
│       ├── settings_manager.py # QSettings wrapper
│       ├── value_manager.py   # get/set widget value by signal
│       ├── style_sheet.py     # themes + QSS template
│       ├── icon_manager.py    # theme-aware icon coloring
│       ├── shortcuts.py       # keyboard shortcuts
│       ├── preset_manager.py  # named preset save/load
│       ├── tasks.py           # WorkIndicator, TasksMixin
│       ├── text.py            # RichText, TextOverlay, TextTruncation
│       ├── convert.py, docking.py, size_grip.py, style.qss
│
├── icons/                     # monochrome SVGs (auto-colored)
└── examples/
    └── example.py             # UITK package explorer app
```

---

## See also

- [Slots](SLOTS.md) — the slot method contract in detail
- [Widgets](WIDGETS.md) — widget catalog and option system
- [Marking Menu](MARKING_MENU.md) — the flagship consumer pattern
- [API Reference](API_REFERENCE.md) — public signatures
