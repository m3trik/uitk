# Widgets

UITK ships enhanced versions of every common Qt widget. Each inherits from its Qt base plus a set of mixins that add lazy `.menu` / `.option_box`, rich text, state persistence, attribute bulk-setting, and icon theming.

**Nav**: [← README](README.md) · [User Guide](USER_GUIDE.md) · [Slots](SLOTS.md) · [Marking Menu](MARKING_MENU.md) · [Architecture](ARCHITECTURE.md) · [Cookbook](COOKBOOK.md) · [API](API_REFERENCE.md)

---

## Promoting in Qt Designer

In Designer, right-click a widget → **Promote to…**:

| Base Class | Promoted Class | Header File |
|:---|:---|:---|
| `QPushButton` | `PushButton` | `uitk.widgets.pushButton.h` |
| `QLineEdit` | `LineEdit` | `uitk.widgets.lineEdit.h` |
| `QComboBox` | `ComboBox` | `uitk.widgets.comboBox.h` |
| `QWidget` | `Header`, `Footer`, `Region` | `uitk.widgets.header.h`, … |

UITK's custom widgets are registered automatically during `Switchboard.__init__` via `registry.widget_registry.extend("widgets", base_dir=self, recursive=True)` — no manual registration needed.

---

## Universal enhancements

### `.menu` — lazy popup menu
Available on every registered widget via `MenuMixin`. Creates the `Menu` instance on first access, not at widget-creation time.

```python
widget.menu.add("QCheckBox", setText="Auto-save", setObjectName="chk_auto")
widget.menu.add(["Option A", "Option B"])        # batch
widget.menu.add("QSeparator")
widget.menu.trigger_button = "right"             # open on right-click
widget.menu.hide_on_leave = True                 # auto-close on mouse leave
```

### `.option_box` — action panel beside the widget
Auto-patched onto `QLineEdit`, `QSpinBox`, `QDoubleSpinBox`, `QComboBox` via `OptionBoxMixin`. A container is injected that holds the widget plus a column of action buttons.

See [Option Box System](#option-box-system) below.

### `.set_attributes()` / `.set_flags()`
Bulk-set Qt attributes, call setter methods, and connect signals from kwargs.

```python
widget.set_attributes(
    setText="Save",
    setToolTip="Write to disk",
    clicked=self.save,
    setEnabled=True,
)
widget.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)
```

### Rich text & icons
`RichText` mixin lets any text-carrying widget accept HTML. `IconManager` mixin provides theme-aware monochrome icons.

```python
button.setText('<b>Bold</b> and <i style="color:red;">Red</i>')
icon = sb.get_icon("save")    # auto-colored to theme's ICON_COLOR
```

---

## The widget catalog

| Widget | Key additions |
|:---|:---|
| [`PushButton`](#pushbutton) | `.menu`, `.option_box`, rich text |
| [`CheckBox`](#checkbox) | `.menu`, `.option_box`, tristate helpers |
| [`ComboBox`](#combobox) | `.add()` fluent API, header, custom popup, deletion signal |
| [`LineEdit`](#lineedit) | `.set_action_color()` (valid/invalid/warning/info), `.option_box` clear button |
| [`TextEdit`](#textedit) | Log-ready, HTML-aware |
| [`Label`](#label) | `clicked` / `released` signals, rich text, text overlay |
| [`SpinBox`, `DoubleSpinBox`](#spinboxes) | `.option_box`, debounce-friendly |
| [`TreeWidget`](#treewidget) | `.add()` hierarchical, type icons, `set_action_color`, batch actions, column config |
| [`TableWidget`](#tablewidget) | `.add(data, headers=...)`, section rows, action colors |
| [`Menu`](#menu) | `.add()` accepts widget classes, lists, dicts; built-in presets/defaults buttons |
| [`Header`](#header) | Draggable, `config_buttons(...)`, `toggled` signal |
| [`Footer`](#footer) | Status text, default message, size grip, action buttons |
| [`CollapsableGroup`](#collapsablegroup) | Expandable section with animation |
| [`ColorSwatch`](#colorswatch) | Color picker, `colorChanged` signal |
| [`ProgressBar`](#progressbar) | `started`, `progressChanged`, `finished`, `cancelled` |
| [`MessageBox`](#messagebox) | Styled, HTML content |
| [`Region`](#region) | Layout region (shown on mouse-over) |
| [`Separator`](#separator) | Visual divider |
| [`AttributeWindow`](#attributewindow) | Generic attribute form |
| [`ExpandableList`](#expandablelist) | Tree-in-a-combo with cascading sublists |
| [`WidgetComboBox`](#widgetcombobox) | ComboBox holding arbitrary widgets |
| [`ToolBox`](#toolbox) | Enhanced tabbed container |
| [`TextEditLogHandler`](#texteditloghandler) | Python `logging.Handler` routing logs into a TextEdit |

Complex packages:

| Package | What it provides |
|:---|:---|
| [`sequencer/`](#sequencer-package) | Full video/animation timeline — `SequencerWidget`, `ClipData`, `TrackData`, `ScrubPlayer`, keyframes, markers, transport controls |
| [`editors/`](#editors-package) | `ColorMappingEditor`, `HotkeyEditor`, `StyleEditor`, `EditorPanel` |
| [`marking_menu/`](MARKING_MENU.md) | Radial gesture menu — see dedicated doc |
| [`optionBox/`](#option-box-system) | Pluggable option system — `ClearOption`, `BrowseOption`, `PinValuesOption`, `RecentValuesOption`, `OptionMenuOption`, `ContextMenuOption`, `ActionOption`, `MenuOption` |

---

## PushButton

`uitk/widgets/pushButton.py` — `QPushButton` + `AttributesMixin`, `RichText`, `MenuMixin`, `OptionBoxMixin`.

```python
def btn_export_init(self, widget):
    widget.setText('<b>Export</b>')
    widget.menu.add("QCheckBox", setText="Include hidden", setObjectName="chk_hidden")
    widget.option_box.menu.add("QPushButton", setText="Export Settings...",
                               setObjectName="btn_settings")
```

## CheckBox

`QCheckBox` + mixins. Default signal `toggled(bool)`.

```python
def chk_wrap(self, checked):
    self.ui.txt_content.setLineWrapMode(
        QtWidgets.QTextEdit.WidgetWidth if checked
        else QtWidgets.QTextEdit.NoWrap
    )
```

## ComboBox

`QComboBox` with a fluent `.add()` API and extra signals.

```python
def cmb_preset_init(self, widget):
    widget.add(["Fast", "Balanced", "Quality"], header="Render preset")
    # Or with data:
    widget.add({"Fast": low_settings, "Balanced": mid_settings, "Quality": hi_settings})
```

**Signals**: `before_popup_shown`, `on_editing_finished(str)`, `on_item_deleted(str)`.

**Methods**: `add(items, data=None, ascending=False, header=None, clear=True)`, `add_header(text)`, `add_single(item, data, ascending)`.

## LineEdit

Adds semantic "action colors" that tint the field based on validation state.

```python
def txt_path(self, text, widget):
    if os.path.isfile(text):
        widget.set_action_color("valid")     # green tint
    elif text == "":
        widget.set_action_color("inactive")  # muted
    elif text.startswith("~"):
        widget.set_action_color("warning")   # amber
    else:
        widget.set_action_color("invalid")   # red tint
```

Available keys: `valid`, `invalid`, `warning`, `info`, `inactive`. Colors come from the active theme palette (`ACTION_VALID_FG/BG`, etc.).

Combine with `option_box.enable_clear()` for a clear-on-right button.

## TextEdit

Enhanced `QTextEdit`. Pair with `TextEditLogHandler` to make it a live log viewer:

```python
import logging
from uitk.widgets.textEditLogHandler import TextEditLogHandler

logger = logging.getLogger("my_app")
logger.addHandler(TextEditLogHandler(self.ui.txt_log))
logger.setLevel(logging.DEBUG)
```

## Label

Emits `clicked` and `released` signals (Qt's `QLabel` has neither). Default signal: `released`. Supports rich HTML text and overlay text (badge-style layered strings).

## SpinBoxes

`SpinBox` (int) and `DoubleSpinBox` (float). `.option_box` enabled by default.

Common pattern — debounce rapid clicks, disable mid-edit emissions:

```python
def spn_start_init(self, widget):
    widget.debounce = 400
    widget.setKeyboardTracking(False)
```

## TreeWidget

A `QTreeWidget` extended with a high-level `.add()`, hierarchical icons, and per-item action colors.

```python
def tree_nodes_init(self, widget):
    widget.setHeaderLabels(["Name", "Type", "Path"])
    root = widget.add(["Scene", "scene", "/"])
    widget.set_item_type_icon(root, "folder")
    for name in ("cube1", "sphere1"):
        widget.add([name, "mesh", f"/{name}"], parent=root)
    widget.expand_all_items()

def tree_nodes(self, item, column):
    self.ui.lbl_status.setText(item.text(0))
```

Methods: `add`, `create_item`, `set_item_type_icon`, `set_item_data`, `set_action_color`, `expand_all_items`, `collapse_all_items`, `set_selection_mode`.

## TableWidget

```python
def tbl_rows_init(self, widget):
    widget.add(
        [[1, "Alice", 30], [2, "Bob", 25]],
        headers=["ID", "Name", "Age"],
    )
    widget.add_section_row("Totals", columns=3)
```

`set_action_color(row, col, key)` tints cells using the same palette as `LineEdit`.

See `uitk/widgets/table_actions.py` for bulk action helpers.

## Menu

The workhorse — a full standalone widget, not just a `QMenu`. See [uitk/widgets/menu.py](../uitk/widgets/menu.py) for the full surface.

### `.add()` is the universal entry

```python
menu.add("QPushButton", setText="Apply", setObjectName="btn_apply")   # by class name
menu.add(my_existing_widget)                                          # by instance
menu.add(["A", "B", "C"])                                             # shorthand list
menu.add({"Save": save_data, "Load": load_data})                      # with data
menu.add("QSeparator")                                                # visual
```

Added widgets are accessible by `objectName` on the menu: `menu.btn_apply.clicked.connect(...)`.

### Built-in Apply / Defaults / Presets bars

```python
widget.menu.add_apply_button = True    # "Apply" bar at bottom
widget.menu.add_defaults_button = True # "Reset to defaults"
widget.menu.add_presets = True         # Preset combo + save/load
widget.menu.add_presets = "~/.myapp/presets"  # or a custom dir
```

### Layout & behavior flags

```python
menu.trigger_button = "right"       # "left", "right", "middle", "hover", None
menu.hide_on_leave = True
menu.position = "bottom"            # "bottom", "right", "cursor"
menu.columns = 3                    # grid layout
```

### Signals
`on_item_added(widget)`, `on_item_interacted(widget)`, `on_hidden()`.

## Header

Draggable header bar for frameless windows. Provides standard window controls.

```python
from uitk.widgets.mixins.tooltip_mixin import fmt, kbd

def header_init(self, widget):
    widget.config_buttons("menu", "minimize", "maximize", "pin", "hide")
    widget.menu.add("QComboBox", setObjectName="cmb_theme", addItems=["Dark", "Light"])
    widget.set_help_text(fmt(
        title="My Tool",
        body="One-line summary.",
        steps=["Select objects.", "Press <b>Run</b>."],
        sections=[("Keyboard", [f"{kbd('Ctrl', 'Z')} — undo"])],
        notes=["Requires the Foo plugin."],
    ))
```

Button keys: `refresh`, `menu`, `help`, `collapse`, `minimize`, `maximize`, `fullscreen`, `pin`, `hide`.

`help` is auto-added on first call to `set_help_text(...)` (no need to list it
in `config_buttons`); clicking the `?` pops the help text as a tooltip via
`QToolTip.showText`. The text persists across `config_buttons` rebuilds.

Rich-text help is built via `fmt(...)` from
[`uitk.widgets.mixins.tooltip_mixin`](../uitk/widgets/mixins/tooltip_mixin.py)
— supports `title`, `body`, `bullets`, `steps`, `rows`, `sections`, and
`notes` (italic muted callouts). Companion helpers: `kbd(*keys)` for
keyboard chips, `hl(text, color)` for inline color highlights.

`UiHandler.DEFAULT_STYLE["header_buttons"]` = `("menu", "collapse", "pin")` — applied if no buttons configured manually.

## Footer

Status bar with integrated size grip. Auto-created on every `MainWindow` unless `add_footer=False`.

```python
self.ui.footer.setDefaultStatusText("Select an item to view details")
self.ui.footer.setText("Loaded 42 items")    # temporary, reverts to default after clear
self.ui.footer.add_action_button("Refresh", callback=self.refresh)
```

## CollapsableGroup

`QGroupBox` that expands/collapses its contents with animation. State persists via the widget state system. Collapse state is settled before window geometry restore — see [CHANGELOG.md entry](../CHANGELOG.md) for the settling rationale.

```python
def output_group_init(self, widget):
    widget.setChecked(True)   # start expanded
```

## ColorSwatch

```python
widget.colorChanged.connect(lambda color: print(color.name()))
```

## ProgressBar

Lifecycle signals beyond Qt's standard:
`started`, `progressChanged(current, total)`, `finished`, `cancelled`.

## MessageBox

Styled dialog matching the active theme.

```python
result = sb.message_box("Save changes?", "Yes", "No", "Cancel")
```

## Region

A `QWidget` that becomes visible on mouse-over. Used by `MarkingMenu` to define invisible "reveal" zones.

## Separator

`QFrame`-based visual divider with theme-aware border color.

## AttributeWindow

Generic attribute editor — given a dict, renders a two-column form with label + value editor per attribute, type-aware (int → SpinBox, bool → CheckBox, color → ColorSwatch, string → LineEdit, etc.).

Signals: `labelToggled(str, bool)`, `valueChanged(str, object)`, `refreshRequested()`.

Used by tools like [mayatk's Channels](https://github.com/m3trik/mayatk/blob/main/mayatk/node_utils/attributes/channels/).

## ExpandableList

A cascade-style list where each item can have a `sublist` of further items. Used heavily in tentacle for hierarchical type browsers.

```python
def list000_init(self, widget):
    widget.fixed_item_height = 18
    widget.apply_preset("expand_up")
    root = widget.add("By Type")
    for category, types in categories.items():
        w = root.sublist.add(category)
        w.sublist.add(sorted(types))

@Signals("on_item_interacted")   # custom signal — override needed
def list000(self, item):
    selection = item.item_text()
    ...
```

**Signals**: `on_item_added(item)`, `on_item_interacted(item)`.

**Presets**: `"expand_up"`, `"expand_down"` control cascade direction.

## WidgetComboBox

A combo whose items can be arbitrary widgets (checkboxes, spinboxes). Used when a dropdown needs rich, interactive content rather than a flat item list.

```python
widget.add([
    (QCheckBox("Show types"), "Types"),
    (QCheckBox("Auto-expand"), "Expand"),
], header="VIEW OPTIONS")
```

## ToolBox

Enhanced `QToolBox`. `.add(widget, text, icon=None)`.

## TextEditLogHandler

A `logging.Handler` subclass that writes to a UITK `TextEdit`. Colors log records by level using theme palette colors.

```python
import logging
from uitk.widgets.textEditLogHandler import TextEditLogHandler

logger = logging.getLogger(__name__)
logger.addHandler(TextEditLogHandler(self.ui.txt_output))
```

---

## Option box system

`uitk/widgets/optionBox/` — a pluggable action system attached to input widgets via `.option_box`.

Each option is a class extending `BaseOption` or `ButtonOption`. Multiple options can be combined.

| Option | What it does |
|:---|:---|
| `ClearOption` | Clear button for text input |
| `BrowseOption` | Opens a file / dir dialog, sets result on widget |
| `PinValuesOption` | Pin / unpin values for quick re-selection |
| `RecentValuesOption` | Keeps last-N values in a dropdown |
| `OptionMenuOption` | Static dropdown of (label, callback) pairs |
| `ContextMenuOption` | Dynamic menu — provider callable returns items based on widget state |
| `ActionOption` | Generic icon button triggering any callback |
| `MenuOption` | Button that opens a pre-built `Menu` instance |

Basic usage via the manager (auto-patched):

```python
def txt_path_init(self, widget):
    widget.option_box.enable_clear()                         # ClearOption shorthand
    widget.option_box.set_action(self.browse, icon="folder") # ActionOption shorthand
```

Plugin-style for custom combinations:

```python
from uitk.widgets.optionBox import OptionBox
from uitk.widgets.optionBox.options import ClearOption, ActionOption

clear = ClearOption(line_edit)
action = ActionOption(callback=self.browse, icon="folder", tooltip="Browse...")
container = OptionBox(options=[clear, action]).wrap(line_edit)
layout.addWidget(container)
```

See [uitk/widgets/optionBox/README.md](../uitk/widgets/optionBox/README.md) for the full option catalog, custom-option authoring, and the backward-compat shim.

---

## Sequencer package

`uitk/widgets/sequencer/` — a full editable timeline widget family. Used by mayatk's Shot Sequencer for non-linear animation editing.

Classes:

| Class | Purpose |
|:---|:---|
| `SequencerWidget` | Top-level timeline container |
| `ClipData` | Data model for a clip on a track |
| `TrackData` | Data model for a track |
| `ScrubPlayer` | Playhead-driven preview / scrubber |
| Internal modules: `_clip`, `_keyframe`, `_markers`, `_overlays`, `_ruler`, `_playhead`, `_transport_controls`, `_drag_tooltip`, `_draggable`, `_timeline` |

Entry point:
```python
from uitk import SequencerWidget, ClipData, TrackData
# or
from uitk.widgets.sequencer import SequencerWidget, ClipData, TrackData, ScrubPlayer
```

Real-world integration: [mayatk's shot_sequencer_slots.py](https://github.com/m3trik/mayatk/blob/main/mayatk/anim_utils/shots/shot_sequencer/shot_sequencer_slots.py).

---

## Editors package

`uitk/widgets/editors/` — composable mini-editors.

| Class | Purpose |
|:---|:---|
| `ColorMappingEditor` / `ColorMappingDialog` | Bidirectional `dict[str, QColor]` editor |
| `HotkeyEditor` | Keybinding capture and persistence |
| `StyleEditor` | Live theme palette tweaker |
| `EditorPanel` | Collapsible multi-editor container |

```python
from uitk.widgets.editors.style_editor import StyleEditor
from uitk.widgets.editors.hotkey_editor import HotkeyEditor

panel = EditorPanel()
panel.add(StyleEditor())
panel.add(HotkeyEditor())
```

---

## See also

- [Slots](SLOTS.md) — how widgets connect to methods
- [Marking Menu](MARKING_MENU.md) — radial menu built on top of these widgets
- [Architecture](ARCHITECTURE.md) — how widgets register, why mixins, lifecycle
- [Cookbook](COOKBOOK.md) — patterns: option_box with browse, preset menus, tree population
