[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![Version](https://img.shields.io/badge/Version-1.0.35-blue.svg)](https://pypi.org/project/uitk/)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide6%20|%20PyQt5-green.svg)](https://doc.qt.io/)
[![Tests](https://img.shields.io/badge/tests-554%20passed-brightgreen.svg)](test/)

# UITK: UI Toolkit for Dynamic Qt Applications

<!-- short_description_start -->
UITK is a **convention-based Qt UI framework** that eliminates manual signal/slot wiring. It dynamically loads `.ui` files, auto-connects widgets to Python methods by name, and provides enhanced widgets with built-in menus, state persistence, and rich text support.
<!-- short_description_end -->

## Why UITK?

| Traditional Qt | With UITK |
|----------------|-----------|
| Manual `connectSlotsByName()` calls | Automatic connection by naming convention |
| Boilerplate signal/slot wiring | Just name your method after the widget |
| Basic widgets | Enhanced widgets with menus, state persistence |
| Manual state saving/loading | Automatic widget state persistence |
| Scattered styling code | Centralized theming system |

## Installation

```bash
pip install uitk
```

**Requirements:** Python 3.8+, PySide6 or PyQt5

## Quick Start

### 1. Create Your UI
Design your UI in Qt Designer and save as `task_manager.ui` with widgets named:
- `btn_add` (QPushButton)
- `txt_task` (QLineEdit)  
- `list_tasks` (QListWidget)

### 2. Create Slot Class

```python
# task_slots.py
from uitk import Signals

class TaskSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.task_manager

    # Called once when widget initializes
    def btn_add_init(self, widget):
        widget.setText("➕ Add Task")
        # Add a priority menu (right-click)
        widget.menu.add("QRadioButton", setText="🔴 High", setObjectName="high")
        widget.menu.add("QRadioButton", setText="🟡 Normal", setObjectName="normal", setChecked=True)
        widget.menu.add("QRadioButton", setText="🟢 Low", setObjectName="low")

    # Called on button click
    def btn_add(self):
        task = self.ui.txt_task.text().strip()
        if task:
            priority = "🔴" if self.ui.btn_add.menu.high.isChecked() else \
                       "🟢" if self.ui.btn_add.menu.low.isChecked() else "🟡"
            self.ui.list_tasks.addItem(f"{priority} {task}")
            self.ui.txt_task.clear()

    # Use custom signal instead of default
    @Signals("returnPressed")
    def txt_task(self, widget):
        self.btn_add()  # Add task on Enter key
```

### 3. Run Application

```python
from uitk import Switchboard
from task_slots import TaskSlots

sb = Switchboard(
    ui_source="./ui_files",    # Directory with .ui files
    slot_source=TaskSlots,      # Class with slot methods
)

ui = sb.task_manager           # Loads task_manager.ui
ui.show(app_exec=True)         # Show and start event loop
```

**That's it!** No manual signal connections needed.

## Core Concepts

### Naming Conventions

UITK auto-connects widgets to methods based on naming:

| Widget Name | Slot Method | Init Method | Purpose |
|-------------|-------------|-------------|---------|
| `btn_save` | `btn_save()` | `btn_save_init(widget)` | Button clicked |
| `txt_name` | `txt_name(widget)` | `txt_name_init(widget)` | Text editing finished |
| `cmb_filter` | `cmb_filter(index, widget)` | `cmb_filter_init(widget)` | Selection changed |
| `chk_active` | `chk_active(state, widget)` | `chk_active_init(widget)` | State changed |
| `spn_count` | `spn_count(value, widget)` | `spn_count_init(widget)` | Value changed |

### Default Signal Mappings

| Widget Type | Default Signal | Slot Receives |
|-------------|----------------|---------------|
| `QPushButton` | `clicked` | `()` |
| `QCheckBox` | `stateChanged` | `(state, widget)` |
| `QComboBox` | `currentIndexChanged` | `(index, widget)` |
| `QSpinBox/QDoubleSpinBox` | `valueChanged` | `(value, widget)` |
| `QLineEdit` | `editingFinished` | `(widget)` |
| `QTextEdit` | `textChanged` | `(widget)` |
| `QSlider` | `valueChanged` | `(value, widget)` |
| `QListWidget` | `itemSelectionChanged` | `(widget)` |

### Override Signals with @Signals Decorator

```python
from uitk import Signals

@Signals("textChanged")  # Instead of default editingFinished
def txt_search(self, widget):
    self.filter_results(widget.text())

@Signals("clicked", "doubleClicked")  # Multiple signals
def list_items(self, widget):
    self.handle_selection()
```

## Enhanced Widgets

UITK provides enhanced versions of standard Qt widgets:

### PushButton
```python
def btn_options_init(self, widget):
    widget.setText("Options")
    widget.setRichText("<b>Bold</b> Text")  # Rich text support
    
    # Built-in menu (right-click by default)
    widget.menu.setTitle("Settings")
    widget.menu.add("QCheckBox", setText="Auto-save", setObjectName="chk_autosave")
    widget.menu.add("QSpinBox", setValue=5, setObjectName="spn_interval")
    
    # Option box (expandable panel)
    widget.option_box.add("QSlider", setObjectName="slider_opacity")
```

### Menu System
```python
# Create standalone menu
from uitk.widgets.menu import Menu

menu = Menu.create_context_menu()  # Right-click menu
menu = Menu.create_dropdown_menu() # Dropdown below widget

# Add items
menu.add("QLabel", setText="Header")
menu.add("QPushButton", setText="Action", data={"id": 1})
menu.add(["Option A", "Option B", "Option C"])  # Quick add multiple

# Query items
items = menu.get_items(types="QPushButton")
data = menu.get_item_data(button)

# Positioning
menu.show_as_popup(position="cursorPos")  # At cursor
menu.show_as_popup(position="bottom")      # Below parent
```

### LineEdit
```python
def txt_email_init(self, widget):
    # Action colors for validation feedback
    widget.set_action_color("valid")    # Green indicator
    widget.set_action_color("invalid")  # Red indicator
    widget.set_action_color("warning")  # Yellow indicator
    
    # Built-in context menu
    widget.menu.add("QAction", setText="Clear", triggered=widget.clear)
```

### ComboBox
```python
def cmb_font_init(self, widget):
    widget.setHeaderText("Select Font")
    widget.setHeaderAlignment("center")
    widget.addItems(["Arial", "Helvetica", "Times"])
```

### MainWindow Features
```python
# Styling
ui.set_attributes(WA_TranslucentBackground=True)
ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)
ui.style.set(theme="dark", style_class="translucentBgWithBorder")

# State persistence (automatic)
# Widget values, geometry, and visibility persist across sessions

# Window positioning
ui.show(pos="screen")   # Center on screen
ui.show(pos="cursor")   # At cursor position
ui.show(pos=QPoint(100, 100))  # Specific position
```

## Advanced Features

### Multiple UIs
```python
sb = Switchboard(
    ui_source="./ui_files",
    slot_source=MySlots,
)

# Access different UIs
main_ui = sb.main_window
settings_ui = sb.settings_dialog
about_ui = sb.about

# Navigate between them
settings_ui.show()
main_ui.hide()
```

### Button Groups
```python
def setup_init(self):
    # Create exclusive button group
    self.sb.create_button_groups(
        self.ui.menu,
        "chk_option_001-3",  # Range: chk_option_001, 002, 003
        allow_deselect=False,
        allow_multiple=False,
    )
```

### Custom Widget Registration
```python
from uitk.widgets.pushButton import PushButton as UitkPushButton

sb = Switchboard(
    ui_source="./ui_files",
    slot_source=MySlots,
    widget_source=[UitkPushButton],  # Register custom widgets
)
```

### Icon Management
```python
sb = Switchboard(
    ui_source="./ui_files",
    slot_source=MySlots,
    icon_source="./icons",  # Icon directory
)

icon = sb.get_icon("save")  # Gets save.svg/png from icons folder
```

## Package Structure

```
uitk/
├── switchboard.py      # Core UI loader and signal router
├── signals.py          # @Signals decorator for custom signal binding
├── events.py           # Event filtering (EventFactoryFilter, MouseTracking)
├── file_manager.py     # Registry for UI files, slots, widgets
└── widgets/
    ├── mainWindow.py   # Main window with state/settings managers
    ├── menu.py         # Dynamic menu system with positioning
    ├── header.py       # Draggable window header
    ├── footer.py       # Status bar with auto-truncation
    ├── pushButton.py   # Button with menu + option box
    ├── lineEdit.py     # Input with action colors
    ├── comboBox.py     # ComboBox with header alignment
    ├── checkBox.py     # Enhanced checkbox
    ├── label.py        # Rich text label
    ├── textEdit.py     # Enhanced text editor
    └── mixins/         # Shared functionality
        ├── menu_mixin.py        # Menu integration
        ├── state_manager.py     # Widget state persistence
        ├── settings_manager.py  # Application settings
        ├── style_sheet.py       # Theming system
        └── text.py              # Rich text support
```

## Running the Example

```python
from uitk import Switchboard, examples

sb = Switchboard(
    ui_source=examples,
    slot_source=examples.ExampleSlots,
)

ui = sb.example
ui.show(pos="screen", app_exec=True)
```

## API Quick Reference

### Switchboard
```python
sb = Switchboard(
    parent=None,              # Parent widget
    ui_source=None,           # Path/module for .ui files
    slot_source=None,         # Class/module with slot methods
    widget_source=None,       # Custom widget classes to register
    icon_source=None,         # Icon directory path
)

# Access UIs
ui = sb.loaded_ui.my_window   # By loaded_ui property
ui = sb.my_window             # Direct attribute access

# Utilities
sb.message_box("Hello!")      # Message dialog
sb.get_icon("save")           # Get registered icon
sb.registered_widgets         # Access widget registry
```

### MainWindow
```python
ui.show(pos="cursor"|"screen"|QPoint, app_exec=False)
ui.hide()
ui.close()

ui.set_attributes(WA_TranslucentBackground=True, ...)
ui.set_flags(FramelessWindowHint=True, ...)
ui.style.set(theme="dark", style_class="...")

ui.widgets                    # Set of registered widgets
ui.slots                      # Slots instance
ui.settings                   # Settings manager
ui.state                      # State manager
```

### Menu
```python
menu = Menu(parent=widget, trigger_button="right", position="cursorPos")
menu = Menu.create_context_menu()
menu = Menu.create_dropdown_menu()

menu.add("QLabel", setText="Item")
menu.add(["A", "B", "C"])
menu.add({"Key": "Value"})

menu.get_items(types="QPushButton")
menu.get_item(0)              # By index
menu.get_item("Item Text")    # By text
menu.clear()

menu.show_as_popup()
menu.hide()
```

## Contributing

Contributions welcome! Please run tests before submitting:

```bash
cd uitk
python -m pytest test/ -v
```

## License

LGPL v3 - See [LICENSE](../COPYING.LESSER) for details.
