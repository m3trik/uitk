[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![Version](https://img.shields.io/badge/Version-1.0.30-blue.svg)](https://pypi.org/project/uitk/)

# UITK: UI Toolkit for Dynamic Qt Applications

UITK is dynamic UI loader designed to manage multiple UI from one central switchboard.  Leverages naming convention to dynamically load UI files, register custom widgets, auto connect slots, set styles, restore and sync states, etc.

## What UITK Does

UITK's primary goal is to eliminate the manual wiring typically required in Qt applications. Instead of manually connecting signals to slots and managing UI loading, UITK uses file and method naming conventions to automatically establish these connections.

### Core Features

**Dynamic UI Loading**
- Automatically loads .ui files created in Qt Designer
- Connects UI widgets to Python methods based on naming conventions
- Supports multiple UI file locations and sources

**Convention-Based Signal Connection**
- Widget named `save_button` automatically connects to method `save_button()`
- Initialization methods like `save_button_init()` are called during setup
- Override default signals using the `@Signals()` decorator

**Enhanced Widgets**
- Extended Qt widgets with additional functionality
- Rich text support in buttons, labels, and other text widgets
- Integrated menu system for buttons and other controls
- Bulk attribute setting with `set_attributes()`

**State Management**
- Basic widget state persistence across application sessions
- Window geometry and position restoration
- Configurable state saving per widget

**File Organization**
- Registry system for tracking UI files, slot classes, and custom widgets
- Support for multiple source directories
- Lazy loading of components

## Package Structure

```
uitk/
├── switchboard.py          # Core UI loading and connection management
├── file_manager.py         # File discovery and registry management  
├── events.py              # Event filtering and handling utilities
├── signals.py             # Signal management decorators
├── widgets/               # Enhanced Qt widgets
│   ├── mainWindow.py      # Enhanced QMainWindow
│   ├── pushButton.py      # Button with rich text and menus
│   ├── lineEdit.py        # Enhanced line edit
│   ├── comboBox.py        # Enhanced combo box
│   └── mixins/            # Reusable functionality mixins
│       ├── attributes.py  # Bulk attribute setting
│       ├── text.py        # Rich text rendering
│       ├── style_sheet.py # Styling capabilities
│       └── state_manager.py # Widget state persistence
└── examples/              # Working example implementation
```

## Installation

```bash
pip install uitk
```

## Basic Usage

### 1. Project Structure
```
your_app/
├── ui/                    # Qt Designer .ui files
│   └── main_window.ui
├── slots/                 # Python slot classes  
│   └── main_window_slots.py
└── main.py
```

### 2. Create Slot Class
```python
# slots/main_window_slots.py
class MainWindowSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.main_window

    def save_button_init(self, widget):
        """Called once during UI setup"""
        widget.setText("💾 Save")
        widget.setToolTip("Save the document")

    def save_button(self, widget):
        """Called when button is clicked"""
        self.sb.message_box("File saved!")

    def filename_edit(self, text, widget):
        """Called when text changes (default signal: textChanged)"""
        self.ui.save_button.setEnabled(bool(text.strip()))
```

### 3. Load and Display UI
```python
# main.py
from uitk import Switchboard

sb = Switchboard(
    ui_source="./ui",           # Directory containing .ui files
    slot_source="./slots"       # Directory containing slot classes
)

ui = sb.main_window             # Loads main_window.ui and MainWindowSlots
ui.show(pos="center", app_exec=True)
```

## Key Features Explained

### Naming Convention Connections

UITK automatically connects widgets to methods based on naming:

```python
# Widget in UI file: objectName="export_button"
# Slot class methods:

def export_button_init(self, widget):
    # Called once during UI initialization
    pass

def export_button(self, widget):  
    # Called when button's default signal (clicked) is emitted
    pass
```

### Signal Override

Use the `@Signals()` decorator to specify different signals:

```python
from uitk import Signals

@Signals("textChanged", "returnPressed")
def search_field(self, widget):
    # Handles both text changes and Enter key
    pass
```

### Enhanced Widgets

UITK widgets extend standard Qt widgets:

```python
# Rich text in buttons
button = PushButton(
    setText='<b>Bold</b> and <i style="color:red;">Red</i> text'
)

# Bulk attribute setting
widget.set_attributes(
    setObjectName="my_widget",
    setText="Hello World",
    setEnabled=True,
    resize=QtCore.QSize(200, 100)
)
```

### Widget Menus

Some widgets support integrated menus:

```python
def export_button_init(self, widget):
    widget.menu.setTitle("Export Options")
    widget.menu.add("QAction", setText="Export PDF", triggered=self.export_pdf)
    widget.menu.add("QAction", setText="Export Excel", triggered=self.export_excel)
```

## Limitations and Considerations

**What UITK Does Well:**
- Reduces boilerplate for simple Qt applications
- Simplifies signal-slot connections through naming conventions
- Provides some useful widget enhancements
- Handles basic state persistence

**What UITK Doesn't Do:**
- Complex event handling scenarios may require manual implementation
- State management is basic and may not cover all use cases
- Styling system is limited to predefined themes
- Performance optimization for large applications may require additional work
- Advanced Qt features may need to bypass UITK's conventions

**Best Suited For:**
- Rapid prototyping of Qt applications
- Simple to medium complexity desktop applications
- Projects where naming convention discipline can be maintained
- Applications that benefit from reduced Qt boilerplate

## Working Example

UITK includes a complete working example in the `examples/` directory that demonstrates:
- UI file loading and slot connection
- Rich text widgets
- Menu integration
- State persistence
- Signal override using decorators

```python
from uitk import Switchboard
from uitk import example

sb = Switchboard(ui_source=example, slot_source=example.ExampleSlots)
ui = sb.example

ui.set_attributes(WA_TranslucentBackground=True)
ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)
ui.style.set(theme="dark", style_class="translucentBgWithBorder")

ui.show(pos="screen", app_exec=True)
```

## Real-World Usage

For a comprehensive example of UITK in a production environment, see the [Tentacle project](https://github.com/m3trik/tentacle), which demonstrates UITK's capabilities in a 3D application toolkit.

## Contributing

UITK is actively developed and welcomes contributions. The codebase is straightforward and well-documented, making it accessible for developers wanting to extend or improve the functionality.

## License

UITK is licensed under the LGPL v3 license, allowing use in both open source and commercial projects.
