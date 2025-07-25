[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![Version](https://img.shields.io/badge/Version-1.0.27-blue.svg)](https://pypi.org/project/uitk/)

# UITK: Dynamic UI Management for Python with qtpy

UITK is dynamic UI loader designed to manage multiple UI from one central switchboard.  Leverages naming convention to dynamically load UI files, register custom widgets, auto connect slots, set styles, restore and sync states, etc.

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
from uitk import Switchboard
from uitk import example

sb = Switchboard(ui_source=example, slot_source=example.ExampleSlots)
ui = sb.example  # Access the UI using its filename.

ui.set_attributes(WA_TranslucentBackground=True)  # Set properties using keyword arguments.
ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)
ui.style.set(theme="dark", style_class="translucentBgWithBorder")

print(repr(ui))
ui.show(pos="screen", app_exec=True)
```
## Advanced Example:

https://github.com/m3trik/tentacle
