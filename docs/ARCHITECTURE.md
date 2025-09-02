# UITK Architecture

This document describes the actual architecture and design patterns of the UITK (UI Toolkit) package.

## Table of Contents
1. [Core Design Principles](#core-design-principles)
2. [System Architecture](#system-architecture)
3. [Key Components](#key-components)
4. [Class Loading System](#class-loading-system)
5. [Signal-Slot Connection System](#signal-slot-connection-system)
6. [State Management](#state-management)
7. [Widget Enhancement System](#widget-enhancement-system)
8. [Extension Points](#extension-points)

## Core Design Principles

UITK is built around several key principles:

1. **Convention over Configuration**: Widget and slot naming conventions automatically create signal-slot connections
2. **Dynamic Loading**: Classes and modules are loaded on-demand as needed
3. **Compatibility**: Built on qtpy for cross-platform Qt support
4. **Extensibility**: Mixin system allows extending widget functionality
5. **Simplicity**: Minimal boilerplate code for common UI patterns

## System Architecture

```
UITK Application
├── Switchboard (Core Orchestrator)
├── FileManager (Registry System)
├── Dynamic Class Loading
├── Enhanced Widgets
├── Event System
└── State Persistence
```

### High-Level Flow

1. **Initialization**: Switchboard created with UI and slot sources
2. **Dynamic Loading**: UI files and slot classes loaded on first access
3. **Auto-Connection**: Widgets automatically connected to slots via naming conventions
4. **Event Handling**: Qt signals routed through UITK's enhanced system
5. **State Management**: Widget states can be saved and restored

## Key Components

### Switchboard (Core)

The central orchestrator that manages all UI components:

```python
# Location: uitk/switchboard.py (~720 lines)
class Switchboard:
    def __init__(self, ui_source=None, slot_source=None, widget_source=None):
        self.loaded_ui = LoadedUi()
        self.file_manager = FileManager()
        # Registry setup and initialization
```

**Key Responsibilities**:
- Dynamic UI loading from .ui files
- Slot class instantiation and management
- Widget-to-slot signal connections
- Message box utilities
- Settings management

**Core Methods**:
- `__getattr__()`: Dynamic UI loading
- `_resolve_ui()`: UI file resolution
- `_connect_slots()`: Automatic signal-slot connections
- `message_box()`: Enhanced message dialogs

### FileManager (Registry)

Manages file discovery and registration:

```python
# Location: uitk/file_manager.py
class FileManager:
    def __init__(self):
        self.ui_files = {}
        self.slot_classes = {}
        self.widget_classes = {}
```

**Key Responsibilities**:
- UI file discovery and caching
- Slot class registration
- Custom widget registration
- Path resolution

### Dynamic Class Loading

UITK implements on-demand class loading:

```python
# Location: uitk/__init__.py
def __getattr__(name):
    """Dynamic class loading based on naming conventions"""
    if name in CLASS_TO_MODULE:
        module_name = CLASS_TO_MODULE[name]
        module = importlib.import_module(f".{module_name}", __name__)
        cls = getattr(module, name)
        globals()[name] = cls
        return cls
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
```

**Features**:
- Lazy loading reduces startup time
- Automatic module discovery
- Class-to-module mapping
- Error handling for missing classes

## Signal-Slot Connection System

### Naming Conventions

UITK automatically connects widgets to slots based on naming:

```python
# Widget name: "save_button"
# Slot method: "save_button()" - handles default signal (clicked)
# Init method: "save_button_init()" - called during widget initialization
```

### Signal Override System

Use the `@Signals` decorator to specify custom signals:

```python
from uitk import Signals

@Signals("released")  # Connect to 'released' instead of 'clicked'
def my_button(self, widget):
    pass

@Signals("textChanged", "returnPressed")  # Multiple signals
def text_field(self, widget):
    pass

@Signals()  # No automatic connection
def manual_widget(self, widget):
    pass
```

### Connection Process

1. **Widget Discovery**: All widgets in loaded UI are identified
2. **Slot Matching**: Slot methods are matched by widget name
3. **Signal Determination**: Default or decorator-specified signals
4. **Connection**: Qt signals connected to slot methods
5. **Initialization**: `*_init` methods called for setup

## State Management

### Basic State Persistence

UITK provides basic widget state management:

```python
# Widget state saving (in compatible widgets)
def get_state(self):
    return {"text": self.text(), "checked": self.isChecked()}

def set_state(self, state):
    if "text" in state:
        self.setText(state["text"])
    if "checked" in state:
        self.setChecked(state["checked"])
```

### Settings Integration

The Switchboard provides QSettings integration:

```python
# Settings are accessible via switchboard
sb = Switchboard()
sb.settings.setValue("theme", "dark")
theme = sb.settings.value("theme", "light")
```

## Widget Enhancement System

### Mixin Architecture

UITK enhances Qt widgets through mixins:

```python
# Example: Enhanced Button
from qtpy import QtWidgets
from uitk.widgets.mixins import AttributesMixin, RichText

class PushButton(QtWidgets.QPushButton, AttributesMixin, RichText):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.set_attributes(**kwargs)
```

### Available Mixins

1. **AttributesMixin**: Dynamic attribute setting
2. **RichText**: HTML text support  
3. **Menu**: Integrated context menus
4. **Additional mixins** for specific functionality

### Widget Registration

Custom widgets can be registered for automatic loading:

```python
# Widgets are discovered from widget_source directory
# Registration happens automatically based on class names
```

## Extension Points

### Custom Widget Development

Create enhanced widgets by inheriting from Qt widgets and UITK mixins:

```python
from qtpy import QtWidgets
from uitk.widgets.mixins import AttributesMixin

class CustomWidget(QtWidgets.QWidget, AttributesMixin):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)
```

### Event System Extension

UITK provides event filtering capabilities:

```python
from uitk.events import EventFactoryFilter

# Create custom event filters
filter = EventFactoryFilter(
    forward_events_to=self,
    event_name_prefix="custom_",
    event_types={"MousePress", "KeyPress"}
)
filter.install(widget)
```

### Slot Class Patterns

Slot classes follow these patterns:

```python
class MySlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.my_ui
        
    def widget_name_init(self, widget):
        """Initialize widget - called automatically"""
        pass
        
    def widget_name(self, widget):
        """Handle widget signal - called on interaction"""
        pass
```

## Data Flow

### UI Loading Flow

1. `sb.ui_name` accessed
2. FileManager locates .ui file
3. UI file loaded and parsed
4. Widgets extracted and enhanced
5. Slot class instantiated
6. Signal-slot connections made
7. Widget initialization methods called
8. UI returned ready for use

### Event Flow

1. User interacts with widget
2. Qt signal emitted
3. UITK routes to appropriate slot method
4. Slot method executes business logic
5. UI updates as needed

## Performance Considerations

### Lazy Loading

- Classes loaded only when accessed
- UI files loaded only when needed
- Minimal memory footprint until use

### Caching

- FileManager caches discovered files
- Loaded UIs cached in LoadedUi
- Class references cached after first load

### Memory Management

- Weak references where appropriate
- Cleanup methods for resource management
- Qt object lifetime management

## Integration Patterns

### Application Structure

```
my_app/
├── ui/              # Qt Designer files
├── slots/           # Business logic
├── widgets/         # Custom widgets
└── main.py         # Application entry point
```

### Recommended Usage

1. Design UIs in Qt Designer
2. Implement business logic in slot classes
3. Use naming conventions for automatic connections
4. Extend widgets through mixins when needed
5. Leverage state management for persistence

This architecture provides a solid foundation for building maintainable Qt applications while reducing boilerplate code and enforcing good separation of concerns.
