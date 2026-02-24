[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![Version](https://img.shields.io/badge/Version-1.0.94-blue.svg)](https://pypi.org/project/uitk/)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide6%20|%20PyQt5-green.svg)](https://doc.qt.io/)
[![Tests](https://img.shields.io/badge/tests-582%20passed-brightgreen.svg)](test/)

# UITK

<!-- short_description_start -->
**Name it, and it connects.** UITK is a convention-driven Qt framework that eliminates boilerplate. Design in Qt Designer, name your widgets, write matching Python methods—everything else is automatic. While conventions handle the common cases, you retain full control to customize anything.
<!-- short_description_end -->

## Installation

```bash
pip install uitk
```

---

## Quick Start

```python
from uitk import Switchboard

class MySlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.my_app
    
    def btn_save_init(self, widget):
        """Called once when widget registers."""
        widget.setText("Save")
    
    def btn_save(self):
        """Called on every click."""
        print("Saved!")

sb = Switchboard(ui_source="./", slot_source=MySlots)
sb.loaded_ui.my_app.show(app_exec=True)
```

That's it. No `connect()` calls. No widget lookups. No manual state management.

---

## Where Convention Applies

UITK uses naming conventions to automatically wire your application. Understanding where convention applies helps you work with the framework effectively.

### What Gets Auto-Wired

| Convention | Pattern | What Happens |
|------------|---------|--------------|
| **UI → Slot Class** | `my_app.ui` → `MyAppSlots` | Slot class discovered and instantiated |
| **Widget → Slot** | `btn_save` → `def btn_save()` | Widget's default signal connected to method |
| **Widget → Init** | `btn_save` → `def btn_save_init(widget)` | Method called once when widget registers |
| **UI Hierarchy** | `menu.file.ui` | Child of `menu.ui`, accessed via `get_ui_relatives()` |
| **Tags** | `panel#floating.ui` | Tags extracted to `ui.tags` set |

### What You Still Control

Conventions provide sensible defaults, but you can always override:

```python
from uitk import Signals

# Override default signal
@Signals("textChanged")  # Instead of editingFinished
def txt_search(self, text):
    self.filter_results(text)

# Connect additional signals manually
widget.clicked.connect(my_handler)

# Use any Qt API directly
widget.setStyleSheet("background: red;")
```

---

## Naming Conventions

### UI File → Slot Class

| UI Filename | Slot Class Name |
|-------------|-----------------|
| `editor.ui` | `EditorSlots` |
| `file_browser.ui` | `FileBrowserSlots` |
| `export-dialog.ui` | `ExportDialogSlots` |

### Widget → Methods

| Widget objectName | Slot Method | Init Method |
|-------------------|-------------|-------------|
| `btn_save` | `def btn_save(self)` | `def btn_save_init(self, widget)` |
| `txt_name` | `def txt_name(self)` | `def txt_name_init(self, widget)` |
| `cmb_type` | `def cmb_type(self, index)` | `def cmb_type_init(self, widget)` |
| `chk_active` | `def chk_active(self, state)` | `def chk_active_init(self, widget)` |

### Default Signals

| Widget Type | Default Signal | Slot Receives |
|-------------|----------------|---------------|
| `QPushButton` | `clicked` | — |
| `QCheckBox` | `stateChanged` | `state` |
| `QRadioButton` | `toggled` | `checked` |
| `QComboBox` | `currentIndexChanged` | `index` |
| `QLineEdit` | `editingFinished` | — |
| `QTextEdit` | `textChanged` | — |
| `QSpinBox` | `valueChanged` | `value` |
| `QDoubleSpinBox` | `valueChanged` | `value` |
| `QSlider` | `valueChanged` | `value` |
| `QListWidget` | `itemSelectionChanged` | — |
| `QTreeWidget` | `itemClicked` | `item, column` |
| `QTableWidget` | `cellClicked` | `row, column` |

### Slot Parameter Injection

Slots can request any combination of these parameters:

```python
def btn_action(self):                           # No params
def btn_action(self, widget):                   # Widget only
def btn_action(self, widget, ui):               # Widget + UI
def btn_action(self, widget, ui, sb):           # All three
def cmb_option(self, index, widget, ui, sb):    # Signal arg + all three
```

---

## Widget Enhancements

Every widget automatically gains these capabilities:

### `.menu` — Popup Menu

```python
def btn_options_init(self, widget):
    menu = widget.menu
    menu.setTitle("Settings")
    menu.add("QCheckBox", setText="Auto-save", setObjectName="chk_auto")
    menu.add("QSpinBox", setPrefix="Interval: ", setObjectName="spn_int")
    menu.add("QSeparator")
    menu.add("QPushButton", setText="Apply", setObjectName="btn_apply")

def btn_options(self):
    menu = self.ui.btn_options.menu
    auto = menu.chk_auto.isChecked()
    interval = menu.spn_int.value()
```

### `.option_box` — Action Panel

```python
def txt_path_init(self, widget):
    menu = widget.option_box.menu
    menu.add(
        "QPushButton",
        setText="Browse...",
        setObjectName="btn_browse"
    )
    menu.btn_browse.clicked.connect(self.browse)
```

### `menu.add()` Flexibility

```python
# Widget type as string
menu.add("QDoubleSpinBox", setValue=1.0, setObjectName="spn")

# Batch add from list
menu.add(["Option A", "Option B", "Option C"])

# Dict with data
menu.add({"Save": save_data, "Load": load_data})

# Separator
menu.add("QSeparator")

# Access added widgets by objectName
value = menu.spn.value()
```

---

## Automatic State Persistence

Widget values save on change and restore on next show:

```python
# User sets spinbox to 5, closes app
# Next launch: spinbox is 5 again

# Disable per widget
widget.restore_state = False

# Disable for entire UI
ui.restore_widget_states = False

# Window geometry also persists automatically
ui.restore_window_size = False  # Disable if needed
```

---

## Theming

```python
# Apply theme
ui.style.set(theme="dark", style_class="translucentBgWithBorder")

# Icons are monochrome and auto-colored to match the theme
icon = sb.get_icon("save")
```

---

## UI Hierarchy & Tags

### Hierarchy via Naming

```
menu.ui              # Parent
menu.file.ui         # Child of menu
menu.file.recent.ui  # Grandchild
```

```python
ancestors = sb.get_ui_relatives(ui, upstream=True)
children = sb.get_ui_relatives(ui, downstream=True)
```

### Tags via `#`

```
panel#floating.ui       # tags: {"floating"}
dialog#modal#dark.ui    # tags: {"modal", "dark"}
```

```python
if ui.has_tags("modal"):
    ui.edit_tags(add="active")
```

---

## MainWindow

Every UI is wrapped in `MainWindow`, providing these properties and methods:

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `ui.sb` | `Switchboard` | Reference to switchboard |
| `ui.widgets` | `set` | All registered child widgets |
| `ui.slots` | `object` | Slot class instance |
| `ui.settings` | `SettingsManager` | Persistent settings |
| `ui.state` | `StateManager` | Widget state persistence |
| `ui.style` | `StyleSheet` | Theme manager |
| `ui.tags` | `set` | Tags from UI name |
| `ui.path` | `str` | Path to .ui file |
| `ui.is_initialized` | `bool` | True after first show |
| `ui.is_current_ui` | `bool` | True if active UI |
| `ui.is_pinned` | `bool` | True if pinned (won't auto-hide) |
| `ui.header` | `Header` | Header widget (if present) |
| `ui.footer` | `Footer` | Footer widget (if present) |

### Signals

| Signal | Emitted When |
|--------|--------------|
| `on_show` | Window shown |
| `on_hide` | Window hidden |
| `on_close` | Window closed |
| `on_focus_in` | Window gains focus |
| `on_focus_out` | Window loses focus |
| `on_child_registered` | Widget registered |
| `on_child_changed` | Widget value changes |

### Methods

```python
# Window configuration
ui.set_attributes(WA_TranslucentBackground=True)
ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)

# Show with positioning
ui.show()                    # Default position
ui.show(pos="screen")        # Center on screen
ui.show(pos="cursor")        # At cursor
ui.show(app_exec=True)       # Start event loop

# Tag management
ui.has_tags("submenu")
ui.edit_tags(add="active", remove="inactive")
```

---

## Widget Attributes Added by Registration

When widgets register, they gain these attributes:

| Attribute | Description |
|-----------|-------------|
| `widget.ui` | Parent MainWindow |
| `widget.base_name()` | Name without tags/suffixes |
| `widget.legal_name()` | Name with special chars replaced |
| `widget.type` | Widget class |
| `widget.derived_type` | Qt base type |
| `widget.default_signals()` | Default signal names |
| `widget.get_slot()` | Get connected slot method |
| `widget.call_slot()` | Manually invoke slot |
| `widget.init_slot()` | Trigger init method |
| `widget.connect_slot()` | Connect to slot |
| `widget.is_initialized` | True after init called |
| `widget.restore_state` | Enable/disable persistence |

---

## Switchboard Utilities

The switchboard provides many helper methods:

### Dialogs

```python
sb.message_box("Operation complete!")
sb.message_box("Choose:", "Yes", "No", "Cancel")

path = sb.file_dialog(file_types="Images (*.png *.jpg)")
folder = sb.dir_dialog()
```

### Widget Helpers

```python
sb.center_widget(widget)                    # Center on screen
sb.center_widget(widget, relative=other)    # Size relative to another widget

sb.toggle_multi(ui, setDisabled="btn_a,btn_b")  # Batch property toggle
sb.connect_multi(ui, widgets, signals, slots)   # Batch connect

sb.create_button_groups(ui, "chk_001-3")    # Radio group from range
```

### UI Navigation

```python
sb.current_ui                  # Active UI
sb.prev_ui                     # Previous UI
sb.ui_history()                # Full UI history
sb.ui_history(-1)              # Previous UI by index
sb.get_ui("editor")            # Get by name
sb.get_ui_relatives(ui, upstream=True)
```

---

## Custom Widgets Included

UITK provides enhanced versions of common widgets:

| Widget | Enhancements |
|--------|--------------|
| `PushButton` | Menu, option box, rich text |
| `CheckBox` | Menu, option box |
| `ComboBox` | Header text, alignment, menu |
| `LineEdit` | Action colors (valid/invalid/warning), menu |
| `TextEdit` | Enhanced text handling |
| `Label` | Rich text, text overlay |
| `TreeWidget` | Hierarchy icons, item helpers |
| `TableWidget` | Enhanced cell handling |
| `Menu` | Dynamic add(), grid layout, positioning |
| `Header` | Draggable, pin/minimize/close buttons |
| `Footer` | Status text, size grip |
| `CollapsableGroup` | Expandable/collapsible sections |
| `ColorSwatch` | Color picker widget |
| `ProgressBar` | Enhanced progress display |
| `MessageBox` | Styled message dialogs |

---

## Package Structure

```
uitk/
├── __init__.py
├── switchboard.py              # Core: UI loading, slot wiring, registries
├── signals.py                  # @Signals decorator
├── events.py                   # EventFactoryFilter, MouseTracking
├── file_manager.py             # FileContainer, FileManager
│
├── widgets/
│   ├── mainWindow.py           # MainWindow wrapper
│   ├── menu.py                 # Dynamic Menu
│   ├── header.py               # Draggable header bar
│   ├── footer.py               # Status bar with size grip
│   ├── pushButton.py           # Enhanced button
│   ├── checkBox.py             # Enhanced checkbox
│   ├── comboBox.py             # ComboBox with header
│   ├── lineEdit.py             # Input with action colors
│   ├── textEdit.py             # Enhanced text editor
│   ├── label.py                # Rich text label
│   ├── treeWidget.py           # Tree with icons
│   ├── tableWidget.py          # Enhanced table
│   ├── progressBar.py          # Progress display
│   ├── messageBox.py           # Styled dialogs
│   ├── collapsableGroup.py     # Expandable sections
│   ├── colorSwatch.py          # Color picker
│   ├── separator.py            # Visual separator
│   ├── region.py               # Layout region
│   │
│   ├── optionBox/              # Option box system
│   │   ├── _optionBox.py       # OptionBox, OptionBoxContainer
│   │   ├── utils.py            # OptionBoxManager
│   │   └── options/            # ClearOption, PinOption, etc.
│   │
│   └── mixins/
│       ├── attributes.py       # set_attributes(), set_flags()
│       ├── menu_mixin.py       # .menu property
│       ├── option_box_mixin.py # .option_box property
│       ├── state_manager.py    # Widget state persistence
│       ├── settings_manager.py # QSettings wrapper
│       ├── style_sheet.py      # Theme management
│       ├── value_manager.py    # Widget value get/set
│       ├── icon_manager.py     # Icon loading and theming
│       ├── text.py             # RichText, TextOverlay
│       ├── convert.py          # Type conversions
│       ├── shortcuts.py        # Keyboard shortcuts
│       ├── tasks.py            # Background tasks
│       ├── docking.py          # Docking behavior
│       ├── switchboard_slots.py    # Slot connection logic
│       ├── switchboard_widgets.py  # Widget registration
│       ├── switchboard_utils.py    # Helper utilities
│       └── switchboard_names.py    # Name/tag handling
│
├── icons/                      # Monochrome icons (auto-colored by theme)
└── examples/                   # Example application
```

---

## Complete Example

```python
from uitk import Switchboard

class EditorSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.editor

    # Button initialization
    def btn_open_init(self, widget):
        menu = widget.menu
        menu.add("QPushButton", setText="Recent...", setObjectName="btn_recent")
        menu.btn_recent.clicked.connect(self.show_recent)

    def btn_open(self):
        path = self.sb.file_dialog(file_types="Text (*.txt)")
        if path:
            self.ui.txt_content.setText(open(path).read())
            self.ui.lbl_status.setText(f"Opened: {path}")

    def btn_save(self):
        self.sb.message_box("Saved!")

    # ComboBox with index parameter
    def cmb_font_init(self, widget):
        widget.addItems(["Arial", "Helvetica", "Courier"])

    def cmb_font(self, index):
        font_name = self.ui.cmb_font.currentText()
        self.ui.txt_content.setFont(self.sb.QtGui.QFont(font_name))

    # Checkbox with state parameter
    def chk_wrap(self, state):
        QTextEdit = self.sb.QtWidgets.QTextEdit
        mode = QTextEdit.WidgetWidth if state else QTextEdit.NoWrap
        self.ui.txt_content.setLineWrapMode(mode)

    def show_recent(self):
        self.sb.message_box("Recent files...")

sb = Switchboard(ui_source="./", slot_source=EditorSlots)
ui = sb.loaded_ui.editor
ui.style.set(theme="dark")
ui.show(pos="screen", app_exec=True)
```

---

## Feature Summary

### Core Architecture
- Convention-based UI loading and slot connection
- Automatic widget registration with attribute injection
- Lazy loading of UIs on first access
- UI hierarchy via filename patterns
- Tag system for UI categorization

### Signal/Slot System
- Auto-connection via naming convention
- Default signal mappings for all widget types
- `@Signals` decorator for custom signals
- Parameter injection (widget, ui, sb)
- Slot history tracking

### State Management
- Automatic widget value persistence
- Window geometry save/restore
- Cross-UI widget sync
- Per-widget and per-UI control
- QSettings-based storage

### Widget Enhancements
- `.menu` popup on any widget
- `.option_box` action panels
- Rich text support
- Action colors for validation
- Menu with dynamic `add()`

### Theming
- Light/dark themes with custom theme support
- Monochrome icons auto-colored by theme
- StyleSheet manager
- Translucent window styles

### Utilities
- Message box dialogs
- File/directory dialogs
- Widget centering
- Batch operations
- Button group creation
- Deferred execution

### Custom Widgets
- Enhanced versions of all common widgets
- Draggable header with controls
- Collapsable groups
- Color swatches
- Tree with hierarchy icons

### Event Handling
- EventFactoryFilter for custom events
- MouseTracking for hover detection
- Focus tracking
- Window lifecycle signals

---

## Contributing

```bash
python -m pytest test/ -v
```

## License

LGPL v3 — See [LICENSE](../COPYING.LESSER)
