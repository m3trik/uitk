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

UITK's custom widgets are registered automatically during `Switchboard.__init__` via `registry.widget_registry.extend("widgets", base_dir=<uitk package dir>, recursive=True)` — anchored on the `uitk/` package root so subpackages like `sequencer/` are picked up too. No manual registration needed.

---

## Universal enhancements

### `.menu` — lazy popup menu
Available on widgets that inherit `MenuMixin` (`PushButton`, `CheckBox`, `ComboBox`, `LineEdit`, `TextEdit`, `Label`, the spin boxes, `TreeWidget`, `TableWidget`, …). Creates the `Menu` instance on first access, not at widget-creation time.

```python
widget.menu.add("QCheckBox", setText="Auto-save", setObjectName="chk_auto")
widget.menu.add(["Option A", "Option B"])        # batch
widget.menu.add("QSeparator")
widget.menu.trigger_button = "right"             # open on right-click
widget.menu.hide_on_leave = True                 # auto-close on mouse leave
```

### `.option_box` — action panel beside the widget
Provided by `OptionBoxMixin` on `PushButton`, `ComboBox`, `LineEdit`, `Label`, and `SpinBox`. A container is injected that holds the widget plus a column of action buttons.

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
`RichText` mixin lets any text-carrying widget accept HTML. `IconManager` (`uitk/widgets/mixins/icon_manager.py`) is a theme-aware SVG icon loader — the active theme sets a default icon color via `IconManager.set_default_color`.

```python
button.setText('<b>Bold</b> and <i style="color:red;">Red</i>')
icon = sb.get_icon("save")    # registered icon, colored by the theme default
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
| [`Label`](#label) | `clicked` / `released` signals, `.menu`, `.option_box` |
| [`SpinBox`, `DoubleSpinBox`](#spinboxes) | Unified int/float, custom display values, wheel-step; `.option_box` on `SpinBox` |
| [`Slider`](#slider) | `.menu`, `.option_box` |
| [`TreeWidget`](#treewidget) | `.add()` hierarchical, type icons, `set_action_color`, batch actions, column config |
| [`TableWidget`](#tablewidget) | `.add(data, headers=...)`, section rows, action colors |
| [`Menu`](#menu) | `.add()` accepts widget classes, lists, dicts; built-in presets/defaults buttons |
| [`Header`](#header) | Draggable, `config_buttons(...)`, `toggled` signal |
| [`Footer`](#footer) | Status text, default message, size grip, action buttons |
| [`CollapsableGroup`](#collapsablegroup) | Collapsible section, persisted expand state |
| [`ColorSwatch`](#colorswatch) | Color picker, `colorChanged` signal |
| [`ProgressBar`](#progressbar) | `started`, `progressChanged`, `finished`, `cancelled` |
| [`MessageBox`](#messagebox) | Styled, HTML content |
| [`Region`](#region) | Layout region (shown on mouse-over) |
| [`Separator`](#separator) | Visual divider |
| [`AttributeWindow`](#attributewindow) | Popup attribute editor (Menu-based) |
| [`ExpandableList`](#expandablelist) | Tree-in-a-combo with cascading sublists |
| [`WidgetComboBox`](#widgetcombobox) | ComboBox holding arbitrary widgets |
| [`ToolBox`](#toolbox) | Enhanced tabbed container |
| [`WindowPanel`](#windowpanel) | Header / body / Footer window shell |
| [`TextViewBox`](#textviewbox) | Read-only rich-text viewer window |
| [`TextEditLogHandler`](#texteditloghandler) | Python `logging.Handler` routing logs into a TextEdit |
| [`ScriptOutput`](#scriptoutput) | Host-agnostic syntax-highlighted console |
| [`MenuButton`](MARKING_MENU.md) | Marking-menu navigation button — covered in [MARKING_MENU.md](MARKING_MENU.md) |

Complex packages:

| Package | What it provides |
|:---|:---|
| [`sequencer/`](#sequencer-package) | Full video/animation timeline — `SequencerWidget`, `ClipData`, `TrackData`, `ScrubPlayer`, keyframes, markers, transport controls |
| [`editors/`](#editors-package) | `EditorPanel`, `StyleEditor`, `ColorMappingEditor`, `ShortcutEditor`, `SwitchboardBrowser` — exposed via `sb.editors` |
| [`delegates/`](#delegates) | Item delegates — icon centering, in-cell choice/shortcut capture, row-selection border |
| [`marking_menu/`](MARKING_MENU.md) | Radial gesture menu — see dedicated doc |
| [`optionBox/`](#option-box-system) | Pluggable option system — `ClearOption`, `BrowseOption`, `PinValuesOption`, `RecentValuesOption`, `OptionMenuOption`, `ContextMenuOption`, `ActionOption`, `MenuOption` |

---

## PushButton

`uitk/widgets/pushButton.py` — `QPushButton` + `MenuMixin`, `OptionBoxMixin`, `AttributesMixin`, `RichText`, `TextOverlay`.

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

**Methods**: `add(x, data=None, header=None, header_alignment="left", clear=True, restore_index=False, ascending=False, …)`, `add_header(text)`, `add_single(item, data, ascending)`.

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

`set_validator("file" | "dir" | "path" | callable)` wires a debounced `textChanged` → predicate → action-color pipeline and emits `validated(bool, str)`.

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

Emits `clicked` and `released` signals (Qt's `QLabel` has neither). Default signal: `released`. Also carries `.menu` and `.option_box`.

## SpinBoxes

`SpinBox` (`uitk/widgets/spinBox.py`) is a unified int/float spin box with custom display values (`setCustomDisplayValues`) and `.option_box`. `DoubleSpinBox` adds modifier-driven wheel stepping without the option box.

Common pattern — coalesce rapid edits, disable mid-edit emissions:

```python
def spn_start_init(self, widget):
    widget.debounce = 400              # slot-level debounce — see SLOTS.md
    widget.setKeyboardTracking(False)
```

## Slider

`uitk/widgets/slider.py` — `QSlider` + `MenuMixin`, `OptionBoxMixin`, `AttributesMixin`. No added API of its own — it exists so sliders get `.menu` and `.option_box` support like the other input widgets.

## TreeWidget

A `QTreeWidget` extended with a high-level `.add()`, hierarchical icons, and per-item action colors.

```python
def tree_nodes_init(self, widget):
    widget.setHeaderLabels(["Name", "Type", "Path"])
    root = widget.create_item(["Scene", "scene", "/"])
    widget.set_item_type_icon(root, "folder")
    for name in ("cube1", "sphere1"):
        widget.create_item([name, "mesh", f"/{name}"], parent=root)
    widget.expand_all_items()

def tree_nodes(self, item, column):
    self.ui.lbl_status.setText(item.text(0))
```

`create_item(text, data=None, parent=None)` returns the `QTreeWidgetItem` (a list of strings fills columns). `add(data, headers=None, clear=True, parent=None)` bulk-loads dicts/lists as hierarchy (dict keys become parents, values children).

Methods: `add`, `create_item`, `set_item_type_icon`, `set_item_data`, `set_action_color`, `expand_all_items`, `collapse_all_items`, `set_selection_mode`.

## TableWidget

```python
def tbl_rows_init(self, widget):
    widget.add(
        [[1, "Alice", 30], [2, "Bob", 25]],
        headers=["ID", "Name", "Age"],
    )
    widget.add_section_row(widget, "Totals")   # static — spans all columns by default
```

`set_action_color(item, key, row=-1, col=-1)` tints cells using the same action-color keys as `LineEdit`.

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
widget.menu.add_defaults_button = True # "Restore Defaults"
widget.menu.add_presets = True         # Preset combo + option-box toolbar (Refresh/Save/⋯-menu)
widget.menu.presets.preset_dir = "~/.myapp/presets"  # custom preset dir
```

### Layout & behavior flags

```python
menu.trigger_button = "right"       # "left"/"right"/"middle"/"any"/"none", Qt button, or tuple
menu.hide_on_leave = True
menu.position = "bottom"            # "bottom", "right", "cursorPos", a coord pair, or a widget
menu.add("QPushButton", row=0, col=1)  # grid placement via add(row=…, col=…, rowSpan=…, colSpan=…)
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

Status bar with integrated size grip. Opt-in on `MainWindow`: pass `add_footer=True` (default `False`) to lazily construct one when no `Footer` is embedded in the `.ui` file.

```python
self.ui.footer.setDefaultStatusText("Select an item to view details")  # fallback text
self.ui.footer.setText("Loaded 42 items", level="success")  # level: info/success/warning/error
self.ui.footer.add_action_button("Refresh", callback=self.refresh)
```

## CollapsableGroup

Checkable `QGroupBox` that shows/hides its contents. Collapse state persists via `SettingsManager` (keyed `CollapsableGroup/<objectName>/checked`; disable with `restore_state = False`). State is settled before window geometry restore — see [CHANGELOG.md entry](../CHANGELOG.md) for the settling rationale.

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

`QFrame` HLine divider with an optional inline `title` label. Mouse-transparent — purely visual.

## AttributeWindow

`uitk/widgets/attributeWindow/` — a `Menu`-based popup editor for inspecting and modifying an object's attributes. Pass the target `obj` plus optional `get_attribute_func` / `set_attribute_func` callables to adapt any backend; populate with `add_attributes(attributes)`. Editor widgets are chosen per value kind by the registry in [`attributeWindow/_factory.py`](../uitk/widgets/attributeWindow/_factory.py) (bool / int / float / str / choice / path / file_list). Labels can be checkable (`checkable=True`, `single_check=True`).

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

**Presets**: `"expand_right"`, `"expand_left"`, `"expand_up"`, `"expand_down"`, `"expand_overlay"`, `"expand_overlay_left"` control cascade direction/placement.

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

## WindowPanel

Themed top-level window shell with a `Header` / body / `Footer` layout — the base for standalone uitk windows (the [`EditorPanel` family](#editors-package) extends it). Subclasses populate `body_layout`; the header buttons, status text, and size-gripped footer come standard. `persist_geometry(settings)` opts in to saving/restoring window geometry; `WindowPanel.icon_button(...)` is a static icon-button helper.

See [uitk/widgets/windowPanel.py](../uitk/widgets/windowPanel.py) (`WindowPanel`).

## TextViewBox

Read-only rich-text viewer window (`WindowPanel` subclass) whose parameters mirror `MessageBox` where they overlap. `setText` / `append_text` fill the body, `setStandardButtons("Ok", "Cancel", …)` adds a `QDialogButtonBox` from MessageBox-style names, and `clicked_button` reports which one closed it. Supports monospace and no-wrap modes for log/tabular content.

See [uitk/widgets/textViewBox.py](../uitk/widgets/textViewBox.py) (`TextViewBox`).

## TextEditLogHandler

A `logging.Handler` subclass that writes to a UITK `TextEdit`. Colors log records by level using theme palette colors.

```python
import logging
from uitk.widgets.textEditLogHandler import TextEditLogHandler

logger = logging.getLogger(__name__)
logger.addHandler(TextEditLogHandler(self.ui.txt_output))
```

## ScriptOutput

`uitk/widgets/scriptOutput.py` — a read-only, monospace, syntax-highlighted console for mirroring a DCC's script/output log. Host concerns are injected rather than baked in: `set_clear_callback()`, `set_context_menu_hook()`, `set_rules()` (regex `ScriptHighlightRule`s — coloring matches words like `Error` / `Warning` in the text itself, so a Maya reporter mirror and a Blender stdout redirect color identically), and `append_text()` to feed it. Pairs with [`TextEditLogHandler`](#texteditloghandler) for `logging` routing.

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

Further options ship in [`optionBox/options/`](../uitk/widgets/optionBox/options/): `ValueOption` (inline editable value field), `AffixOption` (Auto/Suffix/Prefix picker), `ResetOption` (reset-to-default with bypass toggle), `DisableOption`, `FilterOption`, `ToggleOption`.

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

## Delegates

`uitk/widgets/delegates/` — reusable `QStyledItemDelegate`s for item views (the [Shortcut editor](#shortcut--command-registry) and `ColorMappingEditor` are built on them):

| Delegate | What it does |
|:---|:---|
| `RowSelectionBorderDelegate` | Paints a 1 px row-spanning selection border instead of the per-cell fill ([row_selection.py](../uitk/widgets/delegates/row_selection.py)) |
| `CenteredIconActionDelegate` | Centers an icon-only "action cell" while preserving the row-selection border — Qt's default decoration placement is left-aligned and offset by `::item` padding ([centered_icon.py](../uitk/widgets/delegates/centered_icon.py)) |
| `ChoiceCaptureDelegate` | Edits a cell via an in-cell dropdown; `install_choice_capture(table, column, choices, on_capture)` wires it in one call ([choice_capture.py](../uitk/widgets/delegates/choice_capture.py)) |
| `ShortcutCaptureDelegate` | Edits a cell via in-cell key-chord capture; `install_shortcut_capture(table, column, on_capture)` wires it ([shortcut_capture.py](../uitk/widgets/delegates/shortcut_capture.py)) |

Both capture delegates emit `captured(int, int, str)` (row, column, value) and have `Bordered*` variants that mix in the row-selection border.

---

## Sequencer package

`uitk/widgets/sequencer/` (~13 modules) — an NLE-style timeline widget family. Used by mayatk's Shot Sequencer for non-linear animation editing. `SequencerWidget` is a split-view `QSplitter`: track headers on the left, a `TimelineView` scene on the right.

Capabilities, with the key `SequencerWidget` API:

- **Tracks & clips** — `add_track`, `remove_track`, `add_clip`, `remove_clip`, `swap_clips`, `get_clip` / `get_track`, `tracks()` / `clips()`, `selected_clips()`; clip lock/rename via `set_clip_locked` / `set_clip_label`. Data records are the `ClipData` / `TrackData` / `MarkerData` dataclass-style types in [`_data.py`](../uitk/widgets/sequencer/_data.py).
- **Keyframes & expanded tracks** — `expand_track` / `collapse_track` / `toggle_track_expanded` show per-attribute sub-rows (`sub_row_provider` supplies them); key edits emit `keys_moved`, `keys_deleted`, `key_selection_changed`.
- **Playhead & navigation** — `set_playhead`, `step_forward` / `step_backward`, `go_to_next_key` / `go_to_prev_key`, `go_to_start` / `go_to_end`, `frame_shot`; `snap_interval` property.
- **Markers & shot lane** — `add_marker`, `add_marker_at_playhead`, `remove_marker`, `markers()`; `set_shot_blocks(blocks)` draws the shot lane (`shot_switch_requested`; right-click surfaces via `zone_context_menu_requested` with the `"shot_lane"` zone).
- **Range / gap overlays** — `set_range_highlight`, `add_range_overlay`, `add_gap_overlay`, `set_active_range`, plus `show_*` toggle properties; gap edits emit `gap_resized` / `gap_moved` / `gap_lock_changed`.
- **Undo/redo** — `undo()` / `redo()` restore internal snapshots; `undo_requested` / `redo_requested` let a host DCC own history instead.
- **Audio scrub** — `set_audio_source(path, fps)` routes playhead drags through `ScrubPlayer` ([`_scrub_player.py`](../uitk/widgets/sequencer/_scrub_player.py)), a seek-and-grain audio player.
- **Transport** — `TransportControls` ([`_transport_controls.py`](../uitk/widgets/sequencer/_transport_controls.py)) is a Maya-style 8-button row driving the playhead; pluggable `PlayController` protocol, `ScrubPlayerPlayController` default. Window-level shortcut keys toggle via the `window_shortcuts` property.

Interaction signals follow the pattern above: `clip_moved(int, float)`, `clips_batch_moved(list)`, `clip_resized`, `clip_selected`, `selection_changed`, `playhead_moved(float)`, `marker_*`, `track_*`, and a generic `app_event(str, object)` bridge — see the signal block at the top of [`_sequencer.py`](../uitk/widgets/sequencer/_sequencer.py) (`SequencerWidget`).

Entry point:
```python
from uitk import SequencerWidget, ClipData, TrackData
# or
from uitk.widgets.sequencer import SequencerWidget, ClipData, TrackData, ScrubPlayer
```

Real-world integration: [mayatk's shot_sequencer_slots.py](https://github.com/m3trik/mayatk/blob/main/mayatk/anim_utils/shots/shot_sequencer/shot_sequencer_slots.py).

---

## Editors package

`uitk/widgets/editors/` — the bundled editor windows.

| Class | Purpose |
|:---|:---|
| `EditorPanel` | Shared base ([editor_panel.py](../uitk/widgets/editors/editor_panel.py)): a `WindowPanel` with opt-in preset management — subclasses call `init_preset_row(dir_name)` and override `export_preset_data` / `import_preset_data`; save/load/rename/delete delegate to `PresetManager` |
| `StyleEditor` | Edits global stylesheet variables (color and length tokens) live, with presets ([style_editor.py](../uitk/widgets/editors/style_editor.py)) |
| `ColorMappingEditor` / `ColorMappingDialog` | Named color-mapping editor — `color_map()` / `apply_color_map()`, `colors_changed(dict)` signal; the dialog wrapper adds header/footer and presets ([color_mapping_editor.py](../uitk/widgets/editors/color_mapping_editor.py)) |
| `ShortcutEditor` | Edits shortcut and command bindings — see [Shortcut & command registry](#shortcut--command-registry) below ([shortcut_editor/registry_editor.py](../uitk/widgets/editors/shortcut_editor/registry_editor.py)) |
| `SwitchboardBrowser` | Searchable launcher over every UI registered with a Switchboard — filter by name/tags, launch, hide, open in Designer ([switchboard_browser.py](../uitk/widgets/editors/switchboard_browser.py)) |

They're exposed on the Switchboard via `sb.editors` ([uitk/switchboard/editors.py](../uitk/switchboard/editors.py)) — a lazy, auto-recovering singleton registry with names `style`, `shortcut`, `global_shortcuts` (the ShortcutEditor pinned to its Commands view), and `browser`:

```python
sb.editors.show("style")          # open / focus by name
sb.editors.browser                # property access (style / shortcut / browser)
sb.editors.add_post_build_hook("shortcut", wire_dcc_collision_checker)
```

### Shortcut & command registry

Shortcuts live in two layers; `ShortcutEditor` is the single UI over both.

**Widget-side primitives** — [`uitk/widgets/mixins/shortcuts.py`](../uitk/widgets/mixins/shortcuts.py), usable without a Switchboard:

- `GlobalShortcut` — wraps a `QShortcut` for press activation and adds an application-level event filter to reliably detect key **release** (which plain `QShortcut` can't) — for hold-and-release interactions like the marking menu, in hosts (Maya) that swallow key events. Signals: `pressed`, `released`.
- `ShortcutManager` — per-widget registry: `add_shortcut(key, action, description, context)`, `add_global_shortcut`, `add_shortcuts_batch`, `rebind_shortcut(old, new)`, `get_registry()`; `show_editor()` opens `ShortcutEditor` over a bare manager via `ManagerSwitchboardFacade` ([manager_facade.py](../uitk/widgets/editors/shortcut_editor/manager_facade.py)), which presents the manager as a one-UI Switchboard.
- `host_namespace_suffix(context_tags)` — the settings-key suffix (`"_maya"` / `"_blender"`, `""` standalone) that namespaces persisted bindings per host, shared by the marking-menu binding store and the Switchboard shortcut store so per-DCC overrides can't collide.

**Switchboard-side registry** — [`uitk/switchboard/shortcuts.py`](../uitk/switchboard/shortcuts.py) (`SwitchboardShortcutMixin`):

- Slot shortcuts: decorate a slot with `@Shortcut("Ctrl+S")`; `register_slots_shortcuts(ui, slots_instance)` scans the Slots class, applies user overrides from `ui.settings`, and live-binds. `set_user_shortcut(ui, slot_name, sequence, scope)` persists an override and rebinds the active shortcut.
- Commands: `register_command(name, callback, sequence=..., scope=...)` registers a UI-less, shortcut-bindable command (listed under the editor's "⌘ Commands" pseudo-UI; may ship unbound, hidden, or non-editable). `set_command_shortcut(name, sequence, scope)` is the command twin of `set_user_shortcut`; an empty sequence unbinds.

**The editor** — `ShortcutEditor` lists both slot bindings (per registered UI) and commands in one table with in-cell key capture, a per-row window/application scope toggle, reset-to-default, and pluggable collision checking (`add_collision_checker`; conflicts are `CollisionConflict` records that can offer a clear action). The `global_shortcuts` editor name opens the same class focused on commands only.

---

## See also

- [Slots](SLOTS.md) — how widgets connect to methods
- [Marking Menu](MARKING_MENU.md) — radial menu built on top of these widgets
- [Architecture](ARCHITECTURE.md) — how widgets register, why mixins, lifecycle
- [Cookbook](COOKBOOK.md) — patterns: option_box with browse, preset menus, tree population
