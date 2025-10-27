# OptionBox - Modular Widget Option System

A flexible, plugin-based system for adding action buttons, clear buttons, and other options to Qt widgets in the uitk framework.

## Overview

OptionBox provides a modular architecture where options are drop-in components that can be easily added, removed, or customized. This design makes it simple to extend widgets with common functionality while maintaining clean, reusable code.

## Package Structure

```
optionBox/
├── __init__.py              # Main package exports
├── _optionBox.py            # Core OptionBox classes
├── utils.py                 # Helper functions and manager
└── options/                 # Option plugin modules
    ├── __init__.py          # Options package exports
    ├── _options.py          # Base option classes
    ├── clear.py             # Clear button option
    ├── action.py            # Action/menu options
    ├── pin_values.py        # Pin values option
    └── option_menu.py       # Dropdown menu options
```

## Core Components

### OptionBox
The main widget that wraps other widgets and manages option plugins.

```python
from uitk.widgets.optionBox import OptionBox

option_box = OptionBox(show_clear=True)
container = option_box.wrap(my_widget)
```

### OptionBoxContainer
Container widget that provides proper styling and layout for wrapped widgets.

### OptionBoxManager
Elegant API for managing options via `widget.option_box` property (auto-patched on common widgets).

```python
line_edit = QtWidgets.QLineEdit()
line_edit.option_box.enable_clear()
line_edit.option_box.set_action(my_callback)
container = line_edit.option_box.container
```

## Available Option Plugins

**Design Note**: All option plugins that use menus (like `OptionMenuOption` and `ContextMenuOption`)
leverage the custom `Menu` class from `uitk.widgets.menu`. This ensures consistency across the
framework and provides access to all Menu features including `hide_on_leave`, smart positioning,
event filtering, and keyboard navigation.

### ClearOption
Adds a clear button for text input widgets.

```python
from uitk.widgets.optionBox.options import ClearOption

clear_opt = ClearOption(line_edit)
option_box = OptionBox(options=[clear_opt])
option_box.wrap(line_edit)
```

### ActionOption
Adds a customizable action button.

```python
from uitk.widgets.optionBox.options import ActionOption

action_opt = ActionOption(
    callback=lambda: print("Clicked!"),
    icon="settings",
    tooltip="Settings"
)
option_box = OptionBox(options=[action_opt])
option_box.wrap(my_widget)
```

### MenuOption
Specialized action option for displaying menus.

```python
from uitk.widgets.optionBox.options import MenuOption

menu_opt = MenuOption(menu=my_menu)
option_box = OptionBox(options=[menu_opt])
option_box.wrap(my_widget)
```

### PinValuesOption
Allows pinning/saving and restoring widget values.

```python
from uitk.widgets.optionBox.options import PinValuesOption

pin_opt = PinValuesOption(line_edit, auto_restore=True)
option_box = OptionBox(options=[pin_opt])
option_box.wrap(line_edit)
```

### OptionMenuOption
Displays a dropdown menu with multiple choices. Uses the custom `Menu` class
to leverage all Menu features including `hide_on_leave` (enabled by default),
smart positioning, and event handling.

```python
from uitk.widgets.optionBox.options import OptionMenuOption

menu_items = [
    ("Option 1", callback1),
    ("Option 2", callback2),
    "separator",
    ("Option 3", callback3),
]

menu_opt = OptionMenuOption(menu_items=menu_items)
option_box = OptionBox(options=[menu_opt])
option_box.wrap(my_widget)

# The menu automatically hides when mouse leaves (hide_on_leave=True)
# and positions itself below the button (position="bottom")
```

### ContextMenuOption
Dynamic context menu that changes based on widget state.

```python
from uitk.widgets.optionBox.options import ContextMenuOption

def get_menu_items(widget):
    if widget.text():
        return [("Copy", copy_func), ("Clear", clear_func)]
    else:
        return [("Paste", paste_func)]

context_opt = ContextMenuOption(menu_provider=get_menu_items)
option_box = OptionBox(options=[context_opt])
option_box.wrap(line_edit)
```

## Usage Examples

### Basic Usage - Convenience Functions

```python
from uitk.widgets.optionBox import add_option_box, add_clear_option

# Add clear button only
line_edit = QtWidgets.QLineEdit()
container = add_clear_option(line_edit)
layout.addWidget(container)

# Add action button
button = QtWidgets.QPushButton()
container = add_option_box(button, action=my_callback)
layout.addWidget(container)
```

### Using Option Plugins

```python
from uitk.widgets.optionBox import OptionBox
from uitk.widgets.optionBox.options import ClearOption, ActionOption

# Single option
line_edit = QtWidgets.QLineEdit()
clear_opt = ClearOption(line_edit)
option_box = OptionBox(options=[clear_opt])
container = option_box.wrap(line_edit)

# Multiple options
line_edit = QtWidgets.QLineEdit()
clear_opt = ClearOption(line_edit)
action_opt = ActionOption(callback=lambda: print("Action!"))
option_box = OptionBox(options=[clear_opt, action_opt])
container = option_box.wrap(line_edit)
```

### Using Widget Manager API

```python
# Auto-patched on common widgets
line_edit = QtWidgets.QLineEdit()
line_edit.option_box.enable_clear()
line_edit.option_box.set_action(lambda: print("Action!"))
container = line_edit.option_box.container
layout.addWidget(container)
```

### Backward Compatibility

The new modular structure maintains full backward compatibility:

```python
# Old API still works
option_box = OptionBox(show_clear=True, action_handler=my_callback)
container = option_box.wrap(my_widget)

# Legacy ClearButton class still available
from uitk.widgets.optionBox import ClearButton
clear_btn = ClearButton()
```

## Creating Custom Options

Extend `BaseOption` or `ButtonOption` to create custom option plugins:

```python
from uitk.widgets.optionBox.options import ButtonOption

class MyCustomOption(ButtonOption):
    def __init__(self, wrapped_widget=None):
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon="my_icon",
            tooltip="My custom action",
            callback=self.do_something
        )
    
    def do_something(self):
        print("Custom option clicked!")
        # Access wrapped widget
        if self.wrapped_widget:
            print(f"Widget value: {self.wrapped_widget.text()}")

# Use it
line_edit = QtWidgets.QLineEdit()
custom_opt = MyCustomOption(line_edit)
option_box = OptionBox(options=[custom_opt])
option_box.wrap(line_edit)
```

### Advanced Custom Options

For more complex options, override additional methods:

```python
from uitk.widgets.optionBox.options import BaseOption

class AdvancedOption(BaseOption):
    def create_widget(self):
        """Create and return the option widget."""
        widget = QtWidgets.QPushButton("Advanced")
        return widget
    
    def setup_widget(self):
        """Setup widget after creation."""
        self._widget.clicked.connect(self.on_click)
    
    def on_wrap(self, option_box, container):
        """Called when option is wrapped."""
        print("Option was added to OptionBox")
    
    def on_click(self):
        """Handle click."""
        print("Advanced option clicked!")
```

## Migration Guide

If you have existing code using the old `optionBox.py` module:

1. **No changes needed!** The new structure is fully backward compatible.
2. Imports remain the same:
   ```python
   from uitk.widgets.optionBox import OptionBox, add_option_box
   ```
3. All existing APIs continue to work as before.

To take advantage of the new modular system:

```python
# Old way (still works)
option_box = OptionBox(show_clear=True)
option_box.wrap(line_edit)

# New modular way
from uitk.widgets.optionBox.options import ClearOption
clear_opt = ClearOption(line_edit)
option_box = OptionBox(options=[clear_opt])
option_box.wrap(line_edit)
```

## Benefits of the Modular Design

1. **Extensibility**: Easy to create custom option plugins
2. **Reusability**: Options can be reused across different widgets
3. **Composability**: Mix and match options as needed
4. **Maintainability**: Each option is self-contained in its own module
5. **Testing**: Options can be tested independently
6. **Backward Compatibility**: Existing code continues to work

## Demo

Run the demo to see all features in action:

```bash
python demo_optionbox_modular.py
```

## Notes

- Options are added to the OptionBox in the order they are provided
- Each option is responsible for creating and managing its own widget
- Options can interact with the wrapped widget through the `wrapped_widget` attribute
- The OptionBox automatically handles sizing and layout
- Auto-patching adds `option_box` property to common Qt widgets on import

## Future Extensions

The modular design makes it easy to add new option types:

- Save/Load options for configuration management
- Validation options with visual feedback
- History/Undo options for text widgets
- Preset/Template options for quick value selection
- Custom toolbar options for complex widgets

Simply create a new module in the `options/` directory following the `BaseOption` interface!
