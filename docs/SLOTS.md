# Slots

The contract between a Qt Designer `.ui` file and a Python class. Most of UITK reduces to this single idea: **widget name in Designer ↔ method name in Python**.

**Nav**: [← README](README.md) · [User Guide](USER_GUIDE.md) · [Widgets](WIDGETS.md) · [Marking Menu](MARKING_MENU.md) · [Architecture](ARCHITECTURE.md) · [Cookbook](COOKBOOK.md) · [API](API_REFERENCE.md)

---

## 1. Class resolution

Given `editor.ui`, the Switchboard looks for a slot class in this order:

1. Class name match: `EditorSlots`, then `Editor` (CamelCase-from-snake_case + `Slots` suffix).
2. Filename match: `editorSlots.py`, `editor_slots.py`, `editor.py`, `_editor.py` — first class found in the file is used.
3. Sole-class fallback: when neither matches and exactly one slot class is registered (e.g. an explicit `slot_source=SomeSlots`), that class is bound regardless of name.

Name candidates come from [switchboard/names.py](../uitk/switchboard/names.py) (`get_slot_class_names`, `get_slot_file_names`); the lookup order is `_find_slots_class` in [switchboard/slots.py](../uitk/switchboard/slots.py).

```python
# editor.ui  →  EditorSlots class
class EditorSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs["switchboard"]
        self.ui = self.sb.loaded_ui.editor
```

The `__init__` always receives `switchboard=` as a kwarg. Accept `**kwargs` to stay forward-compatible.

---

## 2. Method resolution

Widget `objectName` in Designer maps to two methods in the slot class:

| Method | When called | Signature |
|:---|:---|:---|
| `btn_save_init(self, widget)` | Once, when the widget registers (first `show()`, or first `self.ui.<name>` access) | `widget` positional |
| `btn_save(self, ...)` | Every time the widget's default signal fires | Varies — see §4 |

Init methods run before the widget's state is restored. Use them to build menus, set defaults, add children.

```python
def btn_save_init(self, widget):
    widget.setToolTip("Write document to disk")
    widget.menu.add("QPushButton", setText="Save As...", setObjectName="btn_save_as")
    widget.menu.btn_save_as.clicked.connect(self.save_as)
```

### Widget objectName with illegal characters

`menu#file.ui` has `objectName` `menu#file` (the `#` is an illegal attribute character). UITK resolves it through a legal alias — `sb.loaded_ui.menu_file` — matched back to the raw filename by `find_ui_filename`, the inverse of `convert_to_legal_name` (both in [switchboard/names.py](../uitk/switchboard/names.py)). The raw name stays on `objectName()`; `legal_name()` returns the alias, and `base_name()` returns the pre-tag base (`menu`).

---

## 3. Default signals

UITK auto-connects the slot method to the widget's default signal, chosen by base Qt type — see `default_signals` in [switchboard/slots.py](../uitk/switchboard/slots.py):

| Base type | Default signal | Callback args |
|:---|:---|:---|
| QAction | `triggered` | — |
| QCheckBox | `toggled` | `checked: bool` |
| QComboBox | `currentIndexChanged` | `index: int` |
| QDateEdit | `dateChanged` | `QDate` |
| QDateTimeEdit | `dateTimeChanged` | `QDateTime` |
| QDial | `valueChanged` | `int` |
| QDoubleSpinBox | `valueChanged` | `float` |
| QLabel | `released` | — |
| QLineEdit | `textChanged` | `text: str` |
| QListWidget | `itemClicked` | `QListWidgetItem` |
| QMenu / QMenuBar | `triggered` | `QAction` |
| QProgressBar | `valueChanged` | `int` |
| QPushButton | `clicked` | — |
| QRadioButton | `toggled` | `checked: bool` |
| QScrollBar | `valueChanged` | `int` |
| QSlider | `valueChanged` | `int` |
| QSpinBox | `valueChanged` | `int` |
| QStackedWidget | `currentChanged` | `int` |
| QTabBar / QTabWidget | `currentChanged` | `int` |
| QTableWidget | `cellChanged` | `row, column` |
| QTextEdit | `textChanged` | — |
| QTimeEdit | `timeChanged` | `QTime` |
| QToolBox | `currentChanged` | `int` |
| QTreeWidget | `itemClicked` | `item, column` |

Custom UITK widgets inherit these by base type (a `uitk.PushButton` is a `QPushButton`), and add their own signals — e.g. `ExpandableList.on_item_interacted`.

---

## 4. Parameter injection

UITK introspects your slot's signature (in [switchboard/slots.py](../uitk/switchboard/slots.py)) and injects `widget` as a kwarg if the name is present. The signal's own args are passed positionally as usual.

```python
def btn_save(self): ...                       # no params
def btn_save(self, widget): ...               # widget injected

def cmb_font(self, index): ...                # signal arg: index
def cmb_font(self, index, widget): ...        # signal arg + widget

def chk_wrap(self, state): ...                # QCheckBox.toggled's checked arg
def chk_wrap(self, state, widget): ...        # + widget

def tbl_cells(self, row, column): ...         # QTableWidget.cellChanged
def tbl_cells(self, row, column, widget): ... # + widget
```

Signatures are cached per-slot, so introspection cost is paid once.

---

## 5. `@Signals` — overriding the default

```python
from uitk import Signals

# Connect to a different signal on a standard widget
@Signals("released")
def btn_save(self, widget): ...

# Connect to multiple signals (e.g. click OR Enter key)
@Signals("clicked", "returnPressed")
def btn_submit(self): ...

# Connect to a custom signal on a custom widget
@Signals("on_item_interacted")
def list000(self, item): ...

# Empty - no automatic connection (you wire manually)
@Signals()
def custom_widget(self, widget):
    widget.some_custom_signal.connect(self._handler)
```

### `@Signals.blockSignals` — suppress emissions during a method

```python
@Signals.blockSignals
def update_spinbox(self):
    self.ui.spn_value.setValue(10)   # Won't fire valueChanged
    self.ui.spn_value.setValue(20)   # Also won't fire
```

Blocks with `self.blockSignals(True)` for the call, then restores the *prior* block state on exit — so a decorated method called from a caller that already blocked signals doesn't silently re-enable them.

---

## 6. Slot-level controls

These are **widget attributes**, not method decorators. Set them in `*_init` (or at the top of the slot class `__init__`).

### `widget.debounce: int`

Milliseconds to wait before firing the slot. Each new signal resets the timer. Useful for spinboxes, sliders, search fields.

```python
def spn_start_init(self, widget):
    widget.debounce = 400   # coalesce rapid clicks into one call
```

Implementation: [switchboard/slots.py](../uitk/switchboard/slots.py).

### `@Cancelable(timeout=N)` (recommended) and `widget.slot_timeout`

Two equivalent ways to opt a slot into cooperative cancellation — a `ptk.CancelScope` for the call, the host's Esc source, a warning dialog and near-cursor spinner after `timeout` seconds. Plain slots skip the wrapper entirely (no per-call thread spawn).

```python
from uitk.switchboard import Cancelable

class MyTool(SlotsBase):
    # Static declaration at the slot site — visible to readers.
    @Cancelable(30)
    def btn_long_job(self, widget):
        ...

    # Ask the host to undo partial work if cancelled (Maya: undo chunk).
    @Cancelable(300, rollback=True)
    def btn_bake(self, widget):
        ...

    # Runtime override (wins over the decorator):
    def btn_other_init(self, widget):
        widget.slot_timeout = 60.0
```

Fallback: `ui.default_slot_timeout` applies to slots without either of the above — only honoured when a UI explicitly sets it (the marking menu does not).

**Cancellation is cooperative — the slot must have checkpoints.** Requesting a cancel sets a flag; the slot stops when it next reaches a checkpoint. Two ways to have one, both feeding the same scope:

| Style | Call | Stops by |
|:---|:---|:---|
| bool | `if not update(i): break` (via `sb.progress`) | returning normally |
| exception | `ptk.CancelScope.check()` | raising `OperationCancelled`, caught by the dispatcher |

A slot whose body is a single long host call has no checkpoint and therefore cannot be stopped; the warning dialog reports that instead of implying otherwise. Nothing in-process can preempt a native call.

**Host differences** are supplied by a `CancelProvider` registered at startup (`mtk.MayaCancelProvider`, `btk.BlenderCancelProvider`). The provider decides what Esc means, whether progress mirrors into host-native UI, whether `rollback=True` can be honoured (`supports_rollback` — Maya yes, Blender/standalone no), and whether the progress pump excludes queued user input. See [managers/cancel_manager.py](../uitk/managers/cancel_manager.py).

### `widget.refresh_on_show: bool`

Re-run the `*_init` method on every subsequent show (not just the first). Useful for UIs that reflect environment state — workspace folders, active scene, recent files.

```python
def list000_init(self, widget):
    widget.refresh_on_show = True
    widget.clear()
    # populate from current workspace state
```

### `widget.restore_state: bool`

Opt out of QSettings-backed value persistence for this widget. Default `True`. Disable when the value is driven by an external store.

```python
def txt_shot_name_init(self, widget):
    widget.restore_state = False   # backed by ShotStore instead
```

### `widget.block_signals_on_restore: bool`

When state is restored from QSettings, block signals during the write so the slot doesn't fire as a side effect. Default `False`.

```python
def chk_mode_init(self, widget):
    widget.block_signals_on_restore = True
```

### `widget.perform_restore_state(force=False)`

Manually re-apply persisted state to the widget. Rarely needed.

---

## 7. The slot class constructor

A canonical slot class:

```python
class EditorSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs["switchboard"]
        self.ui = self.sb.loaded_ui.editor

        # Per-widget tweaks that apply regardless of init order:
        for name in ("spn_start", "spn_end"):
            w = getattr(self.ui, name, None)
            if w is not None:
                w.debounce = 400
                w.setKeyboardTracking(False)
```

Accessing `self.ui.<widget_name>` triggers lazy widget registration (see `MainWindow.__getattr__` in [mainWindow.py](../uitk/widgets/mainWindow.py)) — safe to touch during `__init__`.

### Per-domain slot splitting

Large apps split slot logic by domain. Each slot class handles one UI; a shared base holds cross-cutting concerns:

```
slots/
├── maya/
│   ├── _slots_maya.py     # class SlotsMaya: shared DCC base
│   ├── cameras.py         # class Cameras(SlotsMaya)
│   ├── editors.py         # class Editors(SlotsMaya)
│   ├── selection.py       # class Selection(SlotsMaya)
│   └── scene.py           # class Scene(SlotsMaya)
```

Each slot class wires a single UI (`cameras.ui`, `editors.ui`, …). The shared `_slots_maya` base carries `self.sb` setup, logging, common helpers.

See `tentacle/tentacle/slots/maya/` for a full example.

---

## 8. Slot history

The Switchboard tracks recently-called slots in `sb.slot_history()`. Useful for undo / redo bars, debug UIs, re-run-last-action buttons.

```python
last = self.sb.prev_slot          # last called slot method
history = self.sb.slot_history()  # full list, most recent last
```

---

## 9. What UITK does *not* do for slots

- **No validation.** The dispatcher puts no `try/except` around your slot: an exception propagates through Qt's signal dispatch (traceback on the console; the app keeps running) and the widget stays connected. Add your own `try/except` + user feedback (`sb.message_box`) for risky operations. (`*_init` methods are the exception — errors there are caught and logged so one widget can't abort the panel open.)
- **No automatic thread offload.** Long-running slots block the UI thread unless you wrap them yourself (`QThread` / `QtConcurrent.run`); `@Cancelable` adds cancellation and a warning dialog, not offload. Surface progress via `sb.progress(...)` (routes to the active UI's `Footer.progress`).
- **No input-argument coercion.** Signal args are passed through as Qt delivers them. A `QSpinBox.valueChanged(int)` slot gets an `int`; a `QTreeWidget.itemClicked(item, column)` slot gets both.

---

## See also

- [User Guide](USER_GUIDE.md) — tutorial-style introduction
- [Widgets](WIDGETS.md) — what custom signals each UITK widget adds
- [Cookbook](COOKBOOK.md) — patterns: hosted/standalone launch, cross-UI sync, debounced search, custom handlers
- [Architecture](ARCHITECTURE.md) — how the connection actually happens internally
