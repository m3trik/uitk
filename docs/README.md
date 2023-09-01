[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
![Version](https://img.shields.io/badge/Version-0.8.6-blue.svg)

# UITK: Dynamic UI Management for Python with PySide2

UITK is a comprehensive Python package designed to streamline the creation, management, and interaction of user interfaces (UIs) using Python3|PySide2. With a focus on versatility, UITK leverages a naming convention-based switchboard module to dynamically load UI files, register custom widgets, manage slots, styles, states, and facilitate interaction with widgets. The primary goal of UITK is to simplify the development process of complex UIs and enhance the efficiency of event handling.

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
[file_manager](https://github.com/m3trik/uitk/blob/main/uitk/file_manager.py) | Allows for setting multiple locations for dynamic UI files, custom widgets, and slot modules.
[switchboard](https://github.com/m3trik/uitk/blob/main/uitk/switchboard.py) | Handles dynamic UI loading, assigns convenience properties, manages slot connections, syncs, saves, and restores widget states, etc.
[events](https://github.com/m3trik/uitk/blob/main/uitk/events.py) | Manages event handling for dynamic UI widgets.
[widgets](https://github.com/m3trik/tentacle/blob/main/uitk/widgets) | A source directory for the custom widgets included with this package.

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

    @signals("released")  # Specify signal(s) other than the default.
    def MyButtonsObjectName(self):
        self.sb.message_box("Button Pressed")


sb = Switchboard(ui_location="example", slot_location=MyProjectSlots)

ui = sb.example  # Access the UI using its filename.
ui.text_edit.setText("Text Edit")
ui.header.configureButtons(menu_button=True, minimize_button=True, hide_button=True)
ui.header.menu.setTitle("EXAMPLE MENU")
ui.header.menu.add(["Item A", "Item B"])  # Supports widgets and data using dict. Defaults to label.

ui.set_attributes(WA_TranslucentBackground=True)  # Set properties using keyword arguments.
ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)
ui.set_style(theme="dark", style_class="translucentBgWithBorder")

print(repr(ui))
ui.show(pos="screen", app_exec=True)
```
## Advanced Example:

https://github.com/m3trik/tentacle
