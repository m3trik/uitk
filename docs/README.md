[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![Version](https://img.shields.io/badge/Version-1.0.35-blue.svg)](https://pypi.org/project/uitk/)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide6%20|%20PyQt5-green.svg)](https://doc.qt.io/)
[![Tests](https://img.shields.io/badge/tests-554%20passed-brightgreen.svg)](test/)

# UITK

<!-- short_description_start -->
**Name it, and it connects.** UITK is a zero-boilerplate Qt framework where naming conventions replace manual wiring. Design in Qt Designer, name your widgets, write matching Python methods—everything else is automatic.
<!-- short_description_end -->

## The Philosophy

```python
# Traditional Qt: 47 lines of boilerplate
# UITK: 3 lines
sb = Switchboard(ui_source="./", slot_source=MySlots)
sb.my_app.show(app_exec=True)
```

UITK eliminates the ceremony. No `connect()` calls. No widget lookups. No state save/restore code. Just naming conventions that wire everything automatically.

## Installation

```bash
pip install uitk
```

## How It Works

### 1. Name Your Widgets in Qt Designer

Design `snap.ui` with buttons named `b000`, `b001`, `b002`.

### 2. Write Matching Methods

```python
class SnapSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")  # Switchboard injected
        self.ui = self.sb.loaded_ui.snap      # Access UI by name
    
    # Called ONCE when b000 is first registered
    def b000_init(self, widget):
        widget.option_box.menu.setTitle("Snap to Surface")
        widget.option_box.menu.add("QDoubleSpinBox",
            setPrefix="Offset: ",
            setObjectName="s000",
            setValue=0.0)
    
    # Called on EVERY b000 click
    def b000(self):
        offset = self.ui.b000.menu.s000.value()  # Access menu widgets
        self.sb.message_box(f"Offset: {offset}")
```

### 3. Run

```python
sb = Switchboard(ui_source="./", slot_source=SnapSlots)
sb.snap.show(app_exec=True)
```

**That's it.** The button click connects automatically. The spinbox value persists between sessions automatically. The option menu appears on the button automatically.

---

## Naming Convention Reference

### UI File → Slot Class

| UI Filename | Slot Class |
|-------------|------------|
| `snap.ui` | `SnapSlots` |
| `my_window.ui` | `MyWindowSlots` |
| `export-dialog.ui` | `ExportDialogSlots` |

### Widget → Methods

| Widget `objectName` | Slot Method | Init Method |
|---------------------|-------------|-------------|
| `btn_save` | `def btn_save(self)` | `def btn_save_init(self, widget)` |
| `txt_input` | `def txt_input(self, widget)` | `def txt_input_init(self, widget)` |
| `cmb_options` | `def cmb_options(self, index)` | `def cmb_options_init(self, widget)` |

### Default Signals (Auto-Connected)

| Widget Type | Signal | Slot Receives |
|-------------|--------|---------------|
| `QPushButton` | `clicked` | — |
| `QCheckBox` | `stateChanged` | `state` |
| `QComboBox` | `currentIndexChanged` | `index` |
| `QLineEdit` | `editingFinished` | — |
| `QSpinBox` | `valueChanged` | `value` |
| `QSlider` | `valueChanged` | `value` |

### Slot Parameter Injection

Write slots with any combination of parameters—UITK injects what you ask for:

```python
def btn_save(self):                        # No params
def btn_save(self, widget):                # Just widget
def btn_save(self, widget, ui):            # Widget + MainWindow
def btn_save(self, widget, ui, sb):        # All three
def cmb_option(self, index, widget, sb):   # Signal arg + widget + switchboard
```

---

## Widget Enhancements

Every widget gains automatic superpowers:

### `.menu` — Popup Menus on Any Widget

```python
def btn_options_init(self, widget):
    widget.menu.setTitle("Settings")
    widget.menu.add("QCheckBox", setText="Auto-save", setObjectName="chk_auto")
    widget.menu.add("QSpinBox", setPrefix="Interval: ", setObjectName="spn_int")
    widget.menu.add("QSeparator")
    widget.menu.add("QPushButton", setText="Reset", setObjectName="btn_reset")

def btn_options(self):
    if self.ui.btn_options.menu.chk_auto.isChecked():
        interval = self.ui.btn_options.menu.spn_int.value()
```

### `.option_box` — Expandable Option Panels

```python
def txt_path_init(self, widget):
    widget.option_box.menu.add("QPushButton", 
        setText="Browse...", 
        setObjectName="btn_browse")
    widget.option_box.menu.btn_browse.clicked.connect(self.browse_path)
```

### `menu.add()` — Flexible Widget Creation

```python
# String → Widget type
menu.add("QDoubleSpinBox", setValue=1.0, setObjectName="spn")

# List → Batch add
menu.add(["Option A", "Option B", "Option C"])

# Dict → Items with data
menu.add({"Save": save_fn, "Load": load_fn})

# Access by objectName
menu.spn.value()
menu.btn_browse.clicked.connect(handler)
```

---

## Automatic State Persistence

Widget values are **saved on change** and **restored on show**:

```python
# User sets spinbox to 5, closes app
# Next launch: spinbox is 5 again

# Per-widget control
widget.restore_state = False  # Disable for this widget

# Per-UI control  
ui.restore_widget_states = False  # Disable for entire UI
```

Window geometry (size/position) also persists automatically.

---

## Theming & Icons

```python
# Set theme
ui.style.set(theme="dark", style_class="translucentBgWithBorder")

# Icons auto-switch with theme
# save.svg      → light theme
# save_dark.svg → dark theme (auto-selected)

icon = sb.get_icon("save")  # Returns themed QIcon
```

---

## UI Hierarchy & Tags

### Parent/Child UIs via Naming

```
menu.ui           # Parent
menu.file.ui      # Child of menu
menu.file.recent.ui  # Grandchild
```

```python
relatives = sb.get_ui_relatives(ui, upstream=True)   # Get ancestors
relatives = sb.get_ui_relatives(ui, downstream=True) # Get descendants
```

### Tags via `#` Delimiter

```
panel#floating.ui    → tags: {"floating"}
menu#submenu#dark.ui → tags: {"submenu", "dark"}
```

```python
if ui.has_tags("submenu"):
    ui.edit_tags(add="active")
```

---

## Override Default Signals

```python
from uitk import Signals

@Signals("textChanged")  # Instead of editingFinished
def txt_search(self, text, widget):
    self.filter_results(text)

@Signals("pressed", "released")  # Multiple signals
def btn_hold(self, widget):
    pass
```

---

## MainWindow Properties

Every UI is wrapped in `MainWindow` providing:

| Property | Description |
|----------|-------------|
| `ui.sb` | Reference to Switchboard |
| `ui.widgets` | Set of all registered widgets |
| `ui.settings` | `SettingsManager` for persistence |
| `ui.state` | `StateManager` for widget values |
| `ui.style` | `StyleSheet` manager for theming |
| `ui.tags` | Set of tags from UI name |
| `ui.slots` | The slot class instance |

### Window Configuration

```python
ui.set_attributes(WA_TranslucentBackground=True)
ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)
ui.show(pos="screen")   # Center on screen
ui.show(pos="cursor")   # At cursor position
```

---

## Real-World Example

```python
class ImageTracerSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.image_tracer

    def txt_image_path_init(self, widget):
        """Setup browse button in option box."""
        widget.option_box.menu.add("QPushButton",
            setText="Browse...",
            setObjectName="btn_browse")
        widget.option_box.menu.btn_browse.clicked.connect(self.browse_image)

    def browse_image(self):
        path = self.sb.file_dialog(file_types="Images (*.png *.jpg)")
        if path:
            self.ui.txt_image_path.setText(path)

    def btn_trace_init(self, widget):
        """Setup tracing options."""
        widget.option_box.menu.setTitle("Trace Options")
        widget.option_box.menu.add("QDoubleSpinBox",
            setPrefix="Simplify: ", setObjectName="spn_simplify",
            set_limits=[0, 10, 0.1, 2], setValue=1.0)
        widget.option_box.menu.add("QCheckBox",
            setText="Smooth curves", setObjectName="chk_smooth",
            setChecked=True)

    def btn_trace(self):
        """Trace button clicked."""
        path = self.ui.txt_image_path.text()
        simplify = self.ui.btn_trace.menu.spn_simplify.value()
        smooth = self.ui.btn_trace.menu.chk_smooth.isChecked()
        
        # Values persist automatically for next session
        result = ImageTracer.trace(path, simplify=simplify, smooth=smooth)
        self.sb.message_box(f"Created {result} curves")

# Run
sb = Switchboard(ui_source="./", slot_source=ImageTracerSlots)
sb.image_tracer.show(app_exec=True)
```

---

## Package Structure

```
uitk/
├── switchboard.py          # Core: UI loading, slot connection, registries
├── signals.py              # @Signals decorator
├── events.py               # EventFactoryFilter, MouseTracking
├── file_manager.py         # FileManager for discovery
└── widgets/
    ├── mainWindow.py       # MainWindow wrapper (state, settings, style)
    ├── menu.py             # Dynamic Menu with add()
    ├── header.py           # Draggable header with pin/close buttons
    ├── pushButton.py       # Button + menu + option_box
    ├── lineEdit.py         # Input + action colors
    ├── comboBox.py         # ComboBox + header text
    ├── treeWidget.py       # Tree + hierarchy icons
    └── mixins/
        ├── menu_mixin.py           # .menu on any widget
        ├── option_box_mixin.py     # .option_box on any widget
        ├── state_manager.py        # Widget value persistence
        ├── settings_manager.py     # QSettings wrapper
        └── style_sheet.py          # Theming
```

---

## Quick Reference

### Switchboard

```python
sb = Switchboard(
    ui_source="./ui",        # Path to .ui files
    slot_source=MySlots,     # Slot class
    icon_source="./icons",   # Icon directory
)

ui = sb.my_window            # Load + access UI
sb.message_box("Done!")      # Utility dialogs
sb.file_dialog()             # File picker
```

### Widget Access

```python
# From UI
value = ui.my_spinbox.value()
ui.my_button.setText("Click")

# From menu
checked = ui.my_button.menu.chk_option.isChecked()

# From option box menu
offset = ui.btn_action.option_box.menu.spn_offset.value()
```

### Menu.add()

```python
menu.add("QCheckBox", setText="Option", setObjectName="chk")
menu.add("QDoubleSpinBox", setValue=1.0, set_limits=[0, 10, 0.1, 2])
menu.add("QSeparator")
menu.add(["Item 1", "Item 2", "Item 3"])
```

---

## Contributing

```bash
python -m pytest test/ -v  # Run tests first
```

## License

LGPL v3 — See [LICENSE](../COPYING.LESSER)
