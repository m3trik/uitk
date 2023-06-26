[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)

# UITK: Dynamic UI Management for Python with PySide2

UITK is a comprehensive Python package designed to streamline the creation, management, and interaction of user interfaces (UIs) using PySide2. With a focus on versatility, UITK leverages a naming convention-based switchboard module to dynamically load UI files, register custom widgets, manage slots and styles, and facilitate interaction with widgets. The primary goal of UITK is to simplify the development process of complex UIs and enhance the efficiency of event handling.

## Key Features

- Dynamic UI file loading
- Custom widget registration
- Utility properties for MainWindow and child widget subclassing
- Management of slot connections and event handling
- Support for UI hierarchy navigation and submenus
- Custom event behavior through UI tags
- UI and slot history storage and retrieval
- Widget syncing and state management.

## Module Overview

Module | Description
------- | -------
[switchboard](https://github.com/m3trik/uitk/blob/main/uitk/switchboard.py) | Handles dynamic UI loading, assigns convenience properties, and manages slot connections.
[events](https://github.com/m3trik/uitk/blob/main/uitk/events.py) | Manages event handling for dynamic UI widgets.
[stylesheet](https://github.com/m3trik/tentacle/blob/main/uitk/stylesheet.py) | Defines stylesheet presets and auto-applies them to your UI upon initialization.
[widgets](https://github.com/m3trik/tentacle/blob/main/uitk/widgets) | A source directory for custom widgets.

---

## Installation:

Add the `uitk` folder to a directory on your python path, or
install via pip in a command line window using:
```shell
python -m pip install uitk
```

## Basic Example:

Create an instance of Switchboard to load and connect your dynamic ui.
```python
from uitk import Switchboard, signals


class MyProject:
    ...


class MyProjectSlots(MyProject):
    def __init__(self):
        self.sb = self.switchboard()

    @signals("released")  # Specify signal(s) other than the default
    def MyButtonsObjectName(self):
        self.sb.message_box("Button Pressed")


sb = Switchboard(ui_location="example", slots_location=MyProjectSlots)
ui = sb.example
ui.set_style(theme="dark")

print("ui:".ljust(20), type(ui))
print("ui name:".ljust(20), ui.name)
print("ui path:".ljust(20), ui.path)  # The directory path containing the UI file
print("is current ui:".ljust(20), ui.is_current)
print("is connected:".ljust(20), ui.is_connected)
print("is initialized:".ljust(20), ui.is_initialized)
print("slots:".ljust(20), ui.slots)  # The associated slots class instance
print("method:".ljust(20), ui.MyButtonsObjectName.get_slot())
print(
    "widget from method:".ljust(20),
    sb.get_widget_from_method(ui.MyButtonsObjectName.get_slot()),
)
for w in ui.widgets:  # All the widgets of the UI
    print(
        "child widget:".ljust(20),
        (w.name or type(w).__name__).ljust(20),
        w.base_name.ljust(20),
        id(w),
    )

ui.show(app_exec=True)
```
## Advanced Example:

https://github.com/m3trik/tentacle
