# User Guide

A practical walk-through for building a real application with UITK.

**Nav**: [← README](README.md) · [Slots](SLOTS.md) · [Widgets](WIDGETS.md) · [Marking Menu](MARKING_MENU.md) · [Architecture](ARCHITECTURE.md) · [Cookbook](COOKBOOK.md) · [API](API_REFERENCE.md)

---

## 1. Install and verify

```bash
pip install uitk
```

Sanity check:
```python
from uitk import Switchboard
print(Switchboard.__module__)   # 'uitk.switchboard._core'
```

UITK works with either PySide2 or PySide6 via `qtpy`. If neither is installed, pick one: `pip install PySide6`.

---

## 2. Your first app

### Project layout

```
my_app/
├── ui/
│   └── editor.ui          # designed in Qt Designer
├── slots/
│   └── editor_slots.py    # class EditorSlots
└── main.py
```

### Design the UI

Create `editor.ui` in Qt Designer with:
- A `QMainWindow` base
- A `QLineEdit` named `txt_path`, promoted to uitk's `LineEdit` (promotion gives it `set_action_color`; see [WIDGETS.md](WIDGETS.md))
- A `QPushButton` named `btn_open`
- A `QTextEdit` named `txt_content`
- A `QLabel` named `lbl_status`

Save to `my_app/ui/editor.ui`.

### Write the slots

```python
# slots/editor_slots.py
class EditorSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs["switchboard"]
        self.ui = self.sb.loaded_ui.editor

    def btn_open_init(self, widget):
        widget.setText("Open")

    def btn_open(self):
        # file_types is a list of glob patterns; allow_multiple=True (the
        # default) returns a list, so opt out for a single path.
        path = self.sb.file_dialog(
            file_types=["*.txt"], filter_description="Text", allow_multiple=False
        )
        if not path:
            return
        with open(path) as f:
            self.ui.txt_content.setText(f.read())
        self.ui.txt_path.setText(path)
        self.ui.lbl_status.setText(f"Loaded {path}")

    def txt_path(self, text, widget):
        # LineEdit default signal is textChanged; text comes first.
        import os
        widget.set_action_color("valid" if os.path.isfile(text) else "invalid")
```

### Bootstrap

```python
# main.py
from uitk import Switchboard

sb = Switchboard(ui_source="./ui", slot_source="./slots")
ui = sb.loaded_ui.editor
ui.style.set(theme="dark", style_class="translucentBgWithBorder")
ui.show(pos="screen", app_exec=True)
```

Run it:
```bash
python main.py
```

That's a complete working application — file dialog, rich text loading, live path validation, persistent window geometry — in ~20 lines of Python.

---

## 3. The naming convention

| Filename / objectName | Matches | Example |
|:---|:---|:---|
| `editor.ui` | Slot class: `EditorSlots`, then `Editor`; or file: `editorSlots.py`, `editor_slots.py`, `editor.py`, `_editor.py` | `EditorSlots` |
| `editor#file.ui` | Same class resolution using base name `editor` | `EditorSlots` (shared) |
| `btn_save` objectName | Method `btn_save` (+ optional `btn_save_init`) | `def btn_save(self)` |
| `txt_path` objectName | Method `txt_path` — default signal is `textChanged(str)` | `def txt_path(self, text)` |

Complete details in [SLOTS.md](SLOTS.md).

---

## 4. Widget conveniences

uitk's widget classes (used when a Designer widget is promoted, or when built directly) gain lazy capabilities; `.option_box` is additionally patched onto the common plain Qt input widgets (`QLineEdit`, `QTextEdit`, `QPlainTextEdit`, `QPushButton`, `QComboBox`, spin boxes).

### `.menu`
```python
widget.menu.add("QCheckBox", setText="Auto-save", setObjectName="chk_auto")
widget.menu.add(["A", "B", "C"])              # batch
widget.menu.add("QSeparator")
widget.menu.trigger_button = "left"           # default is right-click
```

Added widgets are attributes by `objectName`:
```python
is_auto = widget.menu.chk_auto.isChecked()
```

### `.option_box`
For input widgets (LineEdit, SpinBox, ComboBox). A set of helper buttons beside the widget.

```python
widget.option_box.enable_clear()                         # clear button
widget.option_box.set_action(self.browse, icon="folder") # custom action
widget.option_box.menu.add("QPushButton", setText="More...")
```

### `.set_attributes()`
Bulk config from kwargs — attribute setters, method calls, or signal connections (framework auto-detects which):

```python
widget.set_attributes(
    setText="Save",
    setToolTip="Write to disk",
    clicked=self.save,
)
```

### `.set_action_color()` on uitk's LineEdit

```python
def txt_path(self, text, widget):
    widget.set_action_color("valid" if os.path.isfile(text) else "invalid")
```

Keys: `valid`, `invalid`, `warning`, `info`, `inactive`. Colors from the active theme palette (`ACTION_*` variables).

See [WIDGETS.md](WIDGETS.md) for the full widget catalog.

---

## 5. State persistence

UITK auto-saves widget values on change and restores them on next show. No setup required.

```python
# User types in txt_path, closes app.
# Next launch: txt_path still has that text.
```

Per-widget opt-out:
```python
widget.restore_state = False              # in *_init
widget.block_signals_on_restore = True    # restore silently
```

Combo boxes persist their selection **by index** by default. For a combo whose
items are rebuilt each session (dynamic contents), the stored index can select
the wrong item — restore by the item's identity instead:
```python
combo.restore_by = "text"   # match the saved item by display text (or "data")
```

Per-UI opt-out:
```python
ui.restore_widget_states = False
ui.restore_window_size = False
```

Window geometry (size + position) also persists, debounced to 500ms.

For named preset save/load, see [Presets in the Cookbook](COOKBOOK.md#presets--named-value-sets).

---

## 6. Rapid-fire slots: debounce, timeout, refresh

Three mechanisms shape slot execution:

### `widget.debounce = ms`
Coalesce rapid signals into a single slot call. Essential for spinboxes and sliders:
```python
def spn_start_init(self, widget):
    widget.debounce = 400
    widget.setKeyboardTracking(False)   # don't fire valueChanged mid-edit
```

### `@Cancelable(timeout=seconds)` — enable Esc-cancel for heavy slots
```python
from uitk.switchboard import Cancelable

@Cancelable(300)
def btn_render(self, widget):
    with self.sb.progress(total=len(frames), text="Rendering") as update:
        for i, frame in enumerate(frames):
            if not update(i + 1):   # False once the user cancelled
                break
            render_frame(frame)
```

Cancellation is cooperative: Esc sets a flag and the slot stops at its next checkpoint. Reporting progress *is* a checkpoint; deep helpers can add one with `ptk.CancelScope.check()`. A slot with no checkpoints (one long host call) can't be stopped — the warning dialog says so. Add `rollback=True` to have the host undo partial work on cancel — honored only when the host's registered `CancelProvider` declares `supports_rollback` (Maya's does; the default Qt provider doesn't, and the dispatcher warns instead).

Equivalent runtime override: `widget.slot_timeout = 300.0` in the `*_init`. UI-wide opt-in: `ui.default_slot_timeout = N`. Plain slots skip the monitor wrapper — opt-in keeps the per-call overhead off normal UI clicks.

### `widget.refresh_on_show = True`
Re-run `*_init` on every subsequent show, not just the first. For UIs that reflect changing environment state (workspace folders, scene contents):
```python
def list000_init(self, widget):
    widget.refresh_on_show = True
    widget.clear()
    for item in scan_workspace():
        widget.add(item)
```

---

## 7. Tags and UI hierarchy

Tags in filenames encode metadata and hierarchy.

```
menu.ui               # base (depth 0)
menu#file.ui          # child  (depth 1, tag "file")
menu#file#recent.ui   # grandchild (depth 2)
panel#floating.ui     # base "panel" with tag "floating"
```

Access the tags set:
```python
ui.tags                          # {"file"}
ui.has_tags("file")              # True
ui.edit_tags(add="active")
```

Navigate the hierarchy:
```python
ancestors = sb.get_ui_relatives(ui, upstream=True)
children  = sb.get_ui_relatives(ui, downstream=True)
siblings  = sb.get_ui_relatives(ui, exact=True)
```

**Slot class resolution always uses the base name** — `menu.ui`, `menu#file.ui`, and `menu#file#recent.ui` all map to `MenuSlots`. This is why tags don't fragment your slot code.

---

## 8. Theming

Three built-in themes (`light`, `dark`, `high-contrast`), each a palette dict keyed by well-known variables (`WIDGET_BACKGROUND`, `BUTTON_HOVER`, `TEXT_COLOR`, `ACTION_VALID_FG`, …).

```python
ui.style.set(theme="dark", style_class="translucentBgWithBorder")
ui.style.set(theme="light")                    # just the theme
ui.style.set(style_class="bgWithBorder")       # just the style class
```

Every style apply emits `ui.style.theme_changed(widget, theme_name, theme_vars)` — hook for icon recoloring, custom overlay widgets, etc. (the signal is shared process-wide, so subscribers on any instance receive it).

Monochrome SVG icons in `uitk/icons/` are recolored to the theme's `ICON_COLOR` by `IconManager` — widget icons it applied are refreshed on every `style.set`:
```python
from uitk import IconManager
button.setIcon(IconManager.get("save"))   # theme-colored
icon = sb.get_icon("save")                # raw registered QIcon (no recoloring)
```

Live theme editing:
```python
from uitk.widgets.editors.style_editor import StyleEditor
editor = StyleEditor()
editor.show()
```

---

## 9. Dialogs and helpers

```python
sb.message_box("Operation complete!")
sb.message_box("Proceed?", "Yes", "No", "Cancel")

files = sb.file_dialog(file_types=["*.png", "*.jpg"], filter_description="Images")
folder = sb.dir_dialog()
```

`file_types` is a list of glob patterns. `file_dialog` returns a list by default; pass `allow_multiple=False` for a single path (or `None` on cancel).

```python
sb.center_widget(widget, pos="cursor")     # or pos="screen", a QPoint, or None
sb.center_widget(widget, padding_x=40)     # resize to min-size-hint width + 40
```

Batch-operate on multiple widgets:
```python
sb.toggle_multi(ui, setDisabled="btn_a,btn_b,btn_c")
sb.connect_multi(ui, widgets, signals, slots)
sb.create_button_groups(ui, "chk001-3")    # exclusive group from a range
```

Declare a dependency once instead of hand-wiring both branches — the rule reads the
trigger's value (combos: `currentData`, else index; buttons: `isChecked`), applies at
wire time, and picks up targets that register later (WidgetComboBox rows, option-box items):
```python
sb.enable_when(ui, "cmb_glb_textures", "cmb_format", lambda fmt: fmt != "fbx")
sb.enable_when(ui, "s_max_size", "chk_optimize")              # truthiness
sb.enable_when(ui, "s001,chk002", "cmb_mode", {"x", "both"})  # membership
sb.enable_when(ui, "d000", "chk_master", invert=True)          # the other branch
sb.enable_when(ui, "cmb_out", ["chk_a", "cmb_b"], lambda a, b: a or bool(b))
```

Range shorthand (`"chk001-3"` → `chk001`–`chk003`) keeps only letters and digits — a `chk_001`-style underscore is dropped during expansion, so it only works for names without separators.

---

## 10. Persistent configuration

Beyond widget state, the Switchboard exposes `sb.configurable` — a `SettingsManager` namespace backed by `QSettings`. Handlers register their `DEFAULTS` under their name (`register_handler` applies them via `configurable.branch(name).set_defaults(...)`); consumers read/write through a branch:

```python
ui_cfg = sb.configurable.branch("ui")
ui_cfg.default_position.get()       # "cursor", "screen", "last", (x, y) — or None
ui_cfg.default_position.set("screen")

ui_cfg.default_position.changed.connect(self._on_pos_changed)

sb.configurable.branch("my_feature").enabled.set(True)   # any namespace you want
```

Nesting goes through `.branch()` — `sb.configurable.ui` is a value proxy for the key `"ui"`, not a sub-namespace. `.changed` callbacks fire when the value is set through the same manager object; writes made via a different branch instance (or another process) don't trigger them.

---

## 11. Common patterns

### Slot class constructor — touch widgets up front

```python
class EditorSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs["switchboard"]
        self.ui = self.sb.loaded_ui.editor

        # Debounce all spinner inputs
        for name in ("spn_start", "spn_end", "spn_step"):
            w = getattr(self.ui, name, None)
            if w is not None:
                w.debounce = 400
                w.setKeyboardTracking(False)
```

Accessing `self.ui.<name>` triggers lazy widget registration — safe in `__init__`.

### @Signals for custom widgets
UITK widgets sometimes emit their own signals not in the default table:
```python
from uitk import Signals

@Signals("on_item_interacted")    # ExpandableList custom signal
def list000(self, item):
    print(item.item_text())
```

### Block signals during bulk updates
`@Signals.blockSignals` blocks signals on `self` for the method's duration (restoring the prior block state on exit) — so it belongs on **widget-class** methods, where `self` is the widget:

```python
class QuietSpinBox(QtWidgets.QSpinBox):
    @Signals.blockSignals
    def set_silently(self, value):
        self.setValue(value)   # won't emit valueChanged
```

From a slots class, block per widget instead: `widget.blockSignals(True)` … `widget.blockSignals(False)`.

### Cross-UI sync
When a widget's value changes, UITK persists it into — and mirrors it onto — same-named widgets in ancestor/descendant UIs (same base name, fewer or more `#` tag segments). Same-depth siblings are not synced.

```
scene.ui         has chk_lock
scene#submenu.ui has chk_lock       # kept in sync automatically
```

See `MainWindow.sync_widget_values` in [mainWindow.py](../uitk/widgets/mainWindow.py).

---

## 12. Debugging

Enable debug logging on construction:
```python
sb = Switchboard(ui_source="./ui", slot_source="./slots", log_level="debug")
```

Inspect registries and loaded state:
```python
list(sb.registry.ui_registry.get("filename"))
list(sb.registry.slot_registry.get("classname"))
list(sb.loaded_ui.keys())
list(sb.registered_widgets.keys())   # custom widget *classes*
ui.widgets                           # this UI's registered widget instances
```

Manually connect for troubleshooting:
```python
widget.clicked.connect(lambda: print("clicked!"))
```

Track slot history:
```python
print(sb.slot_history())     # all
print(sb.prev_slot)          # last one
```

---

## 13. Common issues

**Widget not connecting.**
Verify `objectName` in Designer matches the method name exactly. Check `ui.widgets` — if missing, the widget never registered (likely missing `objectName` or outside the UI's central widget tree).

**State not persisting.**
Widget must have a non-empty `objectName` and a recognized default signal (see [SLOTS.md §3](SLOTS.md#3-default-signals)). Check `widget.restore_state` hasn't been set to `False`.

**UI file not found.**
Verify `ui_source` path. `find_ui_filename` does pattern-matching against the registry; if the name has unusual characters, it may not match. Try `sb.registry.ui_registry.get("filename")` to see what's registered.

**Slot class not loading.**
Check both class name and file name resolution rules in [SLOTS.md §1](SLOTS.md#1-class-resolution). An exception during the slot class `__init__` doesn't propagate — it's logged at error level with a full traceback (visible at the default `warning` log level).

**QCheckBox not firing `chk_xxx` on check change.**
Default signal is `toggled(bool)` — your method must accept `state: bool`. If you need `stateChanged(int)` (tristate), use `@Signals("stateChanged")`.

---

## See also

- [Slots Contract](SLOTS.md) — the full wiring spec
- [Widgets](WIDGETS.md) — every custom widget's API
- [Cookbook](COOKBOOK.md) — real patterns from mayatk and tentacle
- [Tutorial](EXAMPLES.md) — step-by-step building a larger example
- [Architecture](ARCHITECTURE.md) — how it all works internally
