[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![PyPI](https://img.shields.io/pypi/v/uitk.svg)](https://pypi.org/project/uitk/)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide2%20|%20PySide6-green.svg)](https://doc.qt.io/)
[![Tests](https://img.shields.io/badge/tests-2682%20passed-brightgreen.svg)](../test/)

# uitk

<!-- short_description_start -->
**Name it, and it connects.** UITK is a convention-driven Qt framework that eliminates boilerplate. Design in Qt Designer, name your widgets, write matching Python methods — UITK discovers the files, auto-wires signals, persists state, and applies themes. Every convention is overridable when you need control.
<!-- short_description_end -->

Built on `qtpy` (PySide2 / PySide6). Runs standalone or hosted inside DCCs (Maya, Blender, 3ds Max) through a pluggable handler ecosystem, and ships a marking-menu subsystem for radial-menu tool shells.

## Why

UITK comes from years of building artist tooling for DCC pipelines, where you don't need one big application — you need *dozens of small ones*, and each traditionally pays the same Qt tax before doing anything useful: load the `.ui`, `findChild()` every widget, `.connect()` every signal, restore and save state, style it, handle standalone-vs-hosted. None of that code is the tool, and hand-rolling it per tool is how toolkits drift into thirty apps by thirty authors.

UITK's intent is to make the *well-behaved* version of a tool the cheapest one to build: names do the wiring, persistence and theming are defaults rather than features, and one shared convention makes a fleet of tools feel like a single application. Every convention has an escape hatch (`@Signals`, handlers, per-widget opt-outs), so growing out of the defaults never means fighting them.

## Install

```bash
pip install uitk qtpy PySide6   # standalone — PySide2 works too
```

<!-- sync:qt-install-note -->
Inside a DCC, install only `uitk qtpy` — the host provides its own Qt binding (uitk deliberately doesn't pull one in).
<!-- /sync:qt-install-note -->

## Live demo

The package ships an interactive example window that exercises the full feature set — option_box plugins, the pythontk logging console, header/footer, themes, and more:

```bash
python -m uitk.examples.example
```

## Quickstart

<!-- sync:quickstart -->
```python
from uitk import Switchboard

class EditorSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs["switchboard"]
        self.ui = self.sb.loaded_ui.editor

    def btn_save_init(self, widget):   # runs once when btn_save registers
        widget.setText("Save")

    def btn_save(self):                # runs on clicked (QPushButton default signal)
        self.sb.message_box("Saved")

sb = Switchboard(ui_source="editor.ui", slot_source=EditorSlots)
sb.loaded_ui.editor.show(pos="screen", app_exec=True)
```

Widget `btn_save` in `editor.ui` is connected to `EditorSlots.btn_save` because the names match.
<!-- /sync:quickstart -->

No `.connect()` calls. No `findChild()`. No manual state restore.

---

## How it wires up

| Convention | Example | Result |
|:---|:---|:---|
| UI file → slot class | `editor.ui` → `EditorSlots` | Class discovered, instantiated with `switchboard=` kwarg |
| Widget → slot method | `btn_save` (`objectName`) → `def btn_save(self)` | Widget's default signal connected |
| Widget → init hook | `btn_save` → `def btn_save_init(self, widget)` | Called once on registration |
| UI hierarchy | `menu#file.ui` is child of `menu.ui` | Resolvable via `sb.get_ui_relatives(ui, upstream=True)` |
| Tags | `panel#floating.ui` | Exposed as `ui.tags == {"floating"}` |

**Default signals** by base Qt type:

| Widget | Signal | Callback arg |
|:---|:---|:---|
| QPushButton | `clicked` | — |
| QCheckBox | `toggled` | `checked: bool` |
| QRadioButton | `toggled` | `checked: bool` |
| QComboBox | `currentIndexChanged` | `index: int` |
| QLineEdit | `textChanged` | `text: str` |
| QTextEdit | `textChanged` | — |
| QSpinBox / QDoubleSpinBox | `valueChanged` | `value` |
| QSlider / QDial / QScrollBar | `valueChanged` | `value: int` |
| QListWidget / QTreeWidget | `itemClicked` | `item[, column]` |
| QTableWidget | `cellChanged` | `row, column` |
| QTabWidget / QStackedWidget / QToolBox | `currentChanged` | `index: int` |

**Override with `@Signals`** — declare one or more signals to connect instead of the default. `@Signals.blockSignals` is a companion decorator that suppresses widget signals while the slot runs (useful for programmatic state changes):

```python
from uitk import Signals

@Signals("released")           # override default (e.g. "clicked") on a button
def btn_confirm(self):
    self.commit()

@Signals("textChanged", "editingFinished")  # connect to multiple signals
def txt_search(self, *args):
    self.filter_results()

@Signals.blockSignals          # run without firing widget signals
def refresh_spinbox(self):
    self.ui.spn_count.setValue(10)
```

**Parameter injection** — slots can request `widget` by name; UITK introspects the signature:

```python
def btn_save(self): ...                       # no params
def btn_save(self, widget): ...               # widget injected
def cmb_font(self, index): ...                # signal arg only
def cmb_font(self, index, widget): ...        # signal arg + widget
```

---

## Widget enhancements

Every registered widget gains these lazy-initialized properties.

### `.menu` — dynamic popup menu

```python
def btn_options_init(self, widget):
    widget.menu.add("QCheckBox", setText="Auto-save", setObjectName="chk_auto")
    widget.menu.add("QSpinBox", setPrefix="Interval: ", setObjectName="spn_int")
    widget.menu.add("QSeparator")
    widget.menu.add("QPushButton", setText="Apply", setObjectName="btn_apply")

def btn_options(self):
    auto = self.ui.btn_options.menu.chk_auto.isChecked()
    interval = self.ui.btn_options.menu.spn_int.value()
```

`menu.add()` accepts a widget class string, a list of strings (shorthand for multiple items), a dict (text → data), or another widget instance. Added widgets are accessible by `objectName` on the menu.

### `.option_box` — action panel attached to input widgets

```python
def txt_path_init(self, widget):
    widget.option_box.menu.add("QPushButton", setText="Browse...", setObjectName="btn_browse")
    widget.option_box.menu.btn_browse.clicked.connect(self.browse)
```

Pluggable option system: `ClearOption`, `BrowseOption`, `PinValuesOption`, `ActionOption`, `MenuOption`, `ContextMenuOption`, `RecentValuesOption`. See [WIDGETS.md](https://github.com/m3trik/uitk/blob/main/docs/WIDGETS.md#option-box-system).

### State persistence

Widget values save on change, restore on show:

```python
# User sets spinbox to 5, closes app. Next launch: spinbox is 5 again.

widget.restore_state = False        # per-widget opt-out
ui.restore_widget_states = False    # per-UI opt-out
ui.restore_window_size = False      # skip window geometry

widget.block_signals_on_restore = True  # restore without firing slot
```

Window geometry also persists automatically, debounced to 500ms on resize/move.

### Slot-level controls

```python
widget.debounce = 300          # coalesce rapid signals into one slot call after 300ms
widget.slot_timeout = 60       # opt this slot into Esc-cancel after 60s (runtime form)
widget.refresh_on_show = True  # call *_init again on every subsequent show
ui.default_slot_timeout = 360  # UI-wide opt-in fallback (not auto-set by marking menu)

# Or declare at the slot site (recommended for static intent):
from uitk.switchboard import Cancelable
@Cancelable(60)
def btn_heavy(self, widget): ...
```

---

## Theming

```python
ui.style.set(theme="dark", style_class="translucentBgWithBorder")
```

Themes (`light`, `dark`) are palette dicts — `WIDGET_BACKGROUND`, `BUTTON_HOVER`, `BORDER_COLOR`, etc. QSS variables are substituted at apply time. Monochrome SVG icons in `uitk/icons/` are auto-colored to match `ICON_COLOR`. `sb.editors.show("style")` opens a live theme editor — tweak any variable at runtime, export/import overrides.

## Hierarchy & tags

UI filenames with `#` encode hierarchy and metadata:

```
menu.ui              # base
menu#file.ui         # child of menu (tag "file")
menu#file#recent.ui  # grandchild (tags "file", "recent")
panel#floating.ui    # base "panel" with tag "floating"
```

- `ui.tags` — set of tags
- `ui.has_tags("floating")` — check
- `ui.edit_tags(add="active", remove="inactive")`
- `sb.get_ui_relatives(ui, upstream=True)` — ancestors
- `sb.get_ui_relatives(ui, downstream=True)` — children
- `sb.get_ui_relatives(ui, exact=True)` — siblings

Cross-UI widget value sync: when a widget's value changes, `MainWindow.on_child_changed` syncs that widget's value to same-named widgets in related UIs via `get_ui_relatives`.

---

## MainWindow

Every UI is wrapped in a `MainWindow` instance.

**Lifecycle signals** — `on_show`, `on_first_show`, `on_hide`, `on_close`, `on_focus_in`, `on_focus_out`, `on_child_registered(widget)`, `on_child_changed(widget, value)`, `on_pinned_changed(bool)`.

**Key properties** — `ui.sb`, `ui.widgets` (set), `ui.slots` (slot instance), `ui.settings` (SettingsManager branch), `ui.state` (StateManager), `ui.style` (StyleSheet), `ui.tags` (set), `ui.path` (str), `ui.is_initialized`, `ui.is_current_ui`, `ui.is_pinned`, `ui.header`, `ui.footer`, `ui.presets`.

**Show positioning** — `ui.show(pos="screen" | "cursor" | QPoint, app_exec=False)`. `app_exec=True` starts the Qt event loop and exits the process on close.

## Handler ecosystem

Extend UITK without editing it. Handlers are classes with a `DEFAULTS` dict that register under `sb.handlers.<name>`:

```python
sb = Switchboard(
    ui_source="...",
    handlers={"ui": MyCustomUiHandler},   # replaces the default UiHandler
)

sb.handlers.ui.apply_styles(ui)
sb.handlers.ui.show(ui, pos="cursor")
sb.configurable.ui.default_position.set("cursor")  # handler DEFAULTS merged here
```

The built-in `UiHandler` applies default styling and positions windows. `MarkingMenu` registers itself as `sb.handlers.marking_menu`. Consumers like tentacle ship subclassed handlers (`MayaUiHandler`) for DCC-specific behavior.

---

## Consumer patterns

### Standalone app
```python
sb = Switchboard(ui_source="./ui", slot_source="./slots")
sb.loaded_ui.main.show(app_exec=True)
```

### Hosted-or-standalone tool (mayatk pattern)
```python
def launch(sb=None):
    if sb is None:
        sb = Switchboard(ui_source="my_tool.ui", slot_source=MyToolSlots)
        ui = sb.loaded_ui.my_tool
        ui.show(pos="screen")
    else:
        ui = sb.handlers.marking_menu.show("my_tool")
    return ui
```

### Marking-menu DCC shell (tentacle pattern)
```python
from uitk import MarkingMenu

class TclMaya(MarkingMenu):
    def __init__(self, parent=None, **kwargs):
        bindings = {
            "Key_F12": "main#startmenu",
            "Key_F12|LeftButton": "cameras#startmenu",
            "Key_F12|RightButton": "scene#startmenu",
        }
        super().__init__(parent, ui_source="ui", slot_source="slots",
                         bindings=bindings, **kwargs)
```

---

## Beyond the basics

One line each — the deep docs are linked below:

- **Timeline sequencer** — `SequencerWidget`, an NLE-style timeline: tracks, draggable clips and keyframes, markers, shot lanes, range/gap overlays, undo/redo, transport controls, audio scrubbing. Powers mayatk's Shot Sequencer.
- **Compiled UI loading** — `.ui` files compile to hash-stamped `_ui.py` modules (`python -m uitk.compile`, `--check` for CI); stale output recompiles automatically, `precompile_async()` warms a fleet in the background, and compilation uses the running binding's own `uic` so output stays loadable across mixed PySide versions (a venv's PySide6 vs. Maya's bundled one).
- **Shortcut registry & editor** — slot hotkeys, app-global shortcuts (`GlobalShortcut`), and named commands share one registry; `sb.editors.show("shortcut")` opens a table editor with in-cell key capture, collision checking, and preset import/export.
- **Named presets** — `ui.presets` (`PresetManager`) snapshots widget values into named presets backed by pythontk's `PresetStore`; `make_preset_combo()` returns a ready-wired picker.
- **Scrubbable tables** — `TableWidget` columns can be drag- or wheel-scrubbed like DCC channel-box cells, with per-cell formatters, action columns, and in-cell shortcut/choice-capture delegates.
- **Bridge panels** — parameterised script panels that drive external DCC processes: `AttributeSpec`s render as form widgets, values serialize per target language (Python / Lua / JS, or raw CLI strings), and templates, presets, and logging share one engine.
- **Script console** — `ScriptOutput`, a host-agnostic syntax-highlighted console, plus `TextEditLogHandler` to pipe Python `logging` into any text panel.
- **External-app launching** — `ExternalAppHandler` registers, installs on demand, and launches external Python tools as subprocesses; `sb.editors.show("browser")` is a searchable, tag-filtered launcher over every handler entry.

## Deeper documentation

Rendered from the GitHub repository:

- [User Guide](https://github.com/m3trik/uitk/blob/main/docs/USER_GUIDE.md) — building your first real app
- [Slots Contract](https://github.com/m3trik/uitk/blob/main/docs/SLOTS.md) — naming, signals, parameter injection, debounce, timeout, refresh
- [Widgets](https://github.com/m3trik/uitk/blob/main/docs/WIDGETS.md) — per-widget reference with the sequencer and editors subpackages
- [Marking Menu](https://github.com/m3trik/uitk/blob/main/docs/MARKING_MENU.md) — radial menu subsystem
- [Architecture](https://github.com/m3trik/uitk/blob/main/docs/ARCHITECTURE.md) — Switchboard mixins, registries, lifecycle
- [Cookbook](https://github.com/m3trik/uitk/blob/main/docs/COOKBOOK.md) — recipes from real consumers
- [Tutorial](https://github.com/m3trik/uitk/blob/main/docs/EXAMPLES.md) — step-by-step walkthrough
- [API Reference](https://github.com/m3trik/uitk/blob/main/docs/API_REFERENCE.md) — public signatures

## License

LGPL-3.0-or-later — see [COPYING.LESSER](https://github.com/m3trik/uitk/blob/main/COPYING.LESSER).
