[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![Version](https://img.shields.io/badge/Version-1.0.35-blue.svg)](https://pypi.org/project/uitk/)
[![Tests](https://img.shields.io/badge/tests-399%20passed-brightgreen.svg)](test/)

# UITK: UI Toolkit for Dynamic Qt Applications

<!-- short_description_start -->
UITK is a convention-based Qt UI framework that eliminates manual signal/slot wiring. It dynamically loads `.ui` files, auto-connects widgets to Python methods by name, and provides enhanced widgets with built-in menus, state persistence, and rich text support.
<!-- short_description_end -->

## Installation

```bash
pip install uitk
```

## Quick Start

```python
from uitk import Switchboard

# Create switchboard with UI and slot sources
sb = Switchboard(
    ui_source="path/to/ui_files",      # Directory with .ui files
    slot_source=MySlotClass,            # Class with slot methods
)

# Access and show a UI (filename: my_window.ui)
ui = sb.my_window
ui.show(app_exec=True)
```

## How It Works

UITK uses **naming conventions** to automatically connect widgets to methods:

| Widget Name | Connected Method | Init Method |
|-------------|------------------|-------------|
| `save_button` | `save_button()` | `save_button_init(widget)` |
| `txt_task` | `txt_task(widget)` | `txt_task_init(widget)` |
| `cmb_filter` | `cmb_filter(index, widget)` | `cmb_filter_init(widget)` |

### Slot Class Example

```python
from uitk import Signals

class TaskManagerSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.task_manager

    # Called once during widget initialization
    def btn_add_init(self, widget):
        """Set up button with a priority menu."""
        widget.setText("Add Task")
        widget.menu.setTitle("PRIORITY")
        widget.menu.add("QRadioButton", setText="High", setObjectName="high")
        widget.menu.add("QRadioButton", setText="Normal", setObjectName="normal", setChecked=True)
    
    # Called on button click (default signal)
    def btn_add(self):
        """Add task with selected priority."""
        priority = "High" if self.ui.btn_add.menu.high.isChecked() else "Normal"
        self.ui.list_tasks.addItem(f"[{priority}] {self.ui.txt_task.text()}")

    # Override default signal with @Signals decorator
    @Signals("returnPressed")
    def txt_task(self, widget):
        """Add task when Enter is pressed."""
        self.btn_add()
```

## Key Features

### Dynamic UI Loading
- Auto-discovers `.ui` files from specified directories
- Lazy-loads UIs on first access via attribute syntax (`sb.my_window`)
- Registers custom widgets automatically

### Enhanced Widgets
Extended Qt widgets with additional capabilities:

| Widget | Enhancements |
|--------|--------------|
| `PushButton` | Built-in menu system, rich text, option box support |
| `LineEdit` | Context menus, action colors, show/hide signals |
| `ComboBox` | Header alignment, enhanced item management |
| `Menu` | Grid layout, item data, persistent mode, positioning |
| `MainWindow` | State/settings managers, footer, header integration |
| `Header/Footer` | Draggable window header, status bar with auto-truncation |

### Built-in Menu System
```python
def my_button_init(self, widget):
    widget.menu.setTitle("Options")
    widget.menu.add("QComboBox", addItems=["A", "B"], setObjectName="choice")
    widget.menu.add("QSpinBox", setValue=10, setObjectName="amount")

def my_button(self, widget):
    choice = widget.menu.choice.currentText()
    amount = widget.menu.amount.value()
```

### State Persistence
Widget states (values, geometry, visibility) automatically persist across sessions.

### Styling
```python
ui.set_attributes(WA_TranslucentBackground=True)
ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)
ui.style.set(theme="dark", style_class="translucentBgWithBorder")
```

## Package Structure

```
uitk/
├── switchboard.py      # Core UI loader and signal router
├── signals.py          # @Signals decorator for custom signal binding
├── events.py           # Event filtering and mouse tracking
├── file_manager.py     # Registry for UI files, slots, and widgets
└── widgets/            # Enhanced Qt widgets
    ├── mainWindow.py   # Main window with state management
    ├── menu.py         # Dynamic menu system
    ├── header.py       # Draggable header with buttons
    ├── footer.py       # Status footer with truncation
    ├── pushButton.py   # Button with menu/option box
    ├── lineEdit.py     # Enhanced line input
    ├── comboBox.py     # Enhanced combo box
    ├── checkBox.py     # Enhanced checkbox
    ├── label.py        # Rich text label
    ├── textEdit.py     # Enhanced text editor
    ├── optionBox/      # Collapsible option containers
    └── mixins/         # Shared widget functionality
        ├── menu_mixin.py        # Menu integration
        ├── state_manager.py     # State persistence
        ├── settings_manager.py  # Settings storage
        ├── style_sheet.py       # Theme and styling
        └── ...
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

## Default Signal Mappings

| Widget Type | Default Signal |
|-------------|----------------|
| `QPushButton` | `clicked` |
| `QCheckBox` | `stateChanged` |
| `QComboBox` | `currentIndexChanged` |
| `QSpinBox` | `valueChanged` |
| `QLineEdit` | `editingFinished` |
| `QTextEdit` | `textChanged` |

Override any default with `@Signals("signal_name")` decorator.

## API Reference

### Switchboard

```python
Switchboard(
    parent=None,                    # Parent widget
    ui_source=None,                 # Path/module for .ui files
    slot_source=None,               # Class/module with slot methods  
    widget_source=None,             # Custom widget classes
    icon_source=None,               # Icon directory
)
```

**Key Methods:**
- `sb.loaded_ui.<name>` - Access loaded UI by filename
- `sb.registered_widgets.<WidgetClass>` - Access registered widget classes
- `sb.message_box(text)` - Show message dialog
- `sb.get_icon(name)` - Get icon from registered sources

### MainWindow

```python
ui.show(pos="cursor"|"screen"|QPoint, app_exec=False)
ui.set_attributes(**attrs)          # Set Qt widget attributes
ui.set_flags(**flags)               # Set Qt window flags
ui.style.set(theme=..., style_class=...)
```

## License

LGPL v3 - See [LICENSE](../COPYING.LESSER) for details.
