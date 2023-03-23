## UITK

<!-- short_description_start -->
uitk is a versatile package for managing user interfaces, widgets, and event handling in Python using PySide2. Using naming convention, the switchboard module provides a convenient way to load UI files, register custom widgets, manage slots and styles, and interact with widgets. It aims to simplify the development and management of complex user interfaces.
<!-- short_description_end -->

## Features

- Dynamically load UI files
- Register and use custom widgets
- Subclass the MainWindows with utility properties
- Initialize child widgets with utility properties
- Manages slot connections and event handling
- Supports UI heirarchy navigation and submenus
- Supports UI tags for custom event behavior.
- Store and retrieve UI and slot history
- Garbage collection protection for widgets

<!-- ![alt text](https://raw.githubusercontent.com/m3trik/tentacle/master/docs/toolkit_demo.gif) \*Example re-opening the last scene, renaming a material, and selecting geometry by that material. -->

## Design:
---
<!-- ## Structure: -->
<!-- ![alt text](https://raw.githubusercontent.com/m3trik/tentacle/master/docs/dependancy_graph.jpg) -->

Module | Description
------- | -------
[switchboard](https://github.com/m3trik/uitk/blob/main/uitk/switchboard.py) | *Load dynamic UI, assign convenience properties, and handle slot connections.*
[events](https://github.com/m3trik/uitk/blob/main/uitk/events.py) | *Event handling for dynamic UI widgets.*
[stylesheet](https://github.com/m3trik/tentacle/blob/main/uitk/stylesheet.py) | *Define stylesheet presets and have them auto applied to your UI on initialization.*
[widgets](https://github.com/m3trik/tentacle/blob/main/uitk/widgets) | *A source directory for custom widgets.*
---

## Installation:

#####

To install:
Add the `uitk` folder to a directory on your python path, or
install via pip in a command line window using:
```
python -m pip install uitk
```

## Basic Example:
	Create an instance of Switchboard to load your project ui and connect slots for the UI events.
```python
from uitk import Switchboard

class MyProject():
    ...

class MySlots(MyProject):
    def __init__(self):
        self.sb = self.get_switchboard_instance()

    def MyButtonsObjectName(self):
        print("Button clicked!")


sb = Switchboard(slots_location=MySlots)
ui = sb.example #Get the UI using it's name

print ('ui:'.ljust(20), ui) #The loaded UI
print ('ui name:'.ljust(20), ui.name) #The UI filename
print ('ui path:'.ljust(20), ui.path) #The directory path containing the UI file
print ('ui tags:'.ljust(20), ui.tags) #Any UI tags as a list
print ('ui level:'.ljust(20), ui.level) #The UI level
print ('is current ui:'.ljust(20), ui.isCurrentUi) #True if the UI is set as current
print ('is submenu:'.ljust(20), ui.isSubmenu) #True if the UI is a submenu
print ('is initialized:'.ljust(20), ui.isInitialized) #True after the UI is first shown
print ('is connected:'.ljust(20), ui.isConnected) #True if the UI is connected to its slots
print ('slots:'.ljust(20), ui.slots) #The associated slots class instance
print ('method:'.ljust(20), ui.MyButtonsObjectName.getSlot())
print ('widget from method:'.ljust(20), sb.getWidgetFromMethod(ui.MyButtonsObjectName.getSlot()))
for w in ui.widgets: print ('child widget:'.ljust(20), (w.name or type(w).__name__).ljust(20), w.prefix.ljust(20), w.type.ljust(15), w.derivedType.ljust(15), id(w)) #All the widgets of the UI

ui.show(app_exec=True)
```
<!-- ## Advanced Example:
```python

```
 -->
