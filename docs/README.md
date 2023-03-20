## The UI Toolkit is a Python3/PySide2 dynamic ui loader.


## Design:

##### 

*This is a Python3/PySide2 UI toolkit with a QUiLoader at it's core. Dynamic UI are loaded on demand and subclassed with convienience properties and automatic slot connections that make getting a full featured UI up and running quick and easy.*

![alt text](https://raw.githubusercontent.com/m3trik/tentacle/master/docs/toolkit_demo.gif) \*Example re-opening the last scene, renaming a material, and selecting geometry by that material.

## 

---

<!-- ## Structure: -->

<!-- ![alt text](https://raw.githubusercontent.com/m3trik/tentacle/master/docs/dependancy_graph.jpg) -->


Example | Description
------- | -------
[switchboard](https://github.com/m3trik/uitk/blob/main/uitk/switchboard.py) | *Loads dynamic ui and custom widgets on demand. Assigns properties and provides convenience 
[events](https://github.com/m3trik/uitk/blob/main/uitk/events.py) | *Event handling for dynamic ui.*
[overlay](https://github.com/m3trik/tentacle/blob/main/tentacle/overlay.py) | *Tracks cursor position and ui hierarchy to generate paint events that overlay it's parent widget.*
methods for interacting with the ui.*

---

## Installation:

#####

To install:
Add the `uitk` folder to a directory on your python path, or
install via pip in a command line window using:
```
python -m pip install uitk
```

Example:
	1. Create a subclass of Switchboard to load your project ui and connect slots for the UI events.
```	
		Class MyProject():
			...

		Class MyProject_slots(MyProject):
			def __init__(self):
				super().__init__()
				self.sb = self.get_switchboard_instance() #slot classes are given the `get_switchboard_instance` function when they are initialized.
				print (self.sb.ui) #access the current ui. if a single ui is loaded that will automatically be assigned as current, else you must set a ui as current using: self.sb.ui = self.sb.getUi(<ui_name>)

		class MyProject_sb(Switchboard):
			def __init__(self, parent=None, **kwargs):
				super().__init__(parent)
				self.ui_location = 'path/to/your/dynamic ui file(s)' #specify the location of your ui.
				self.slots_location = MyProject_slots #give the slots directory or the class itself.
```
	2. Instantiate the subclass and show the UI.
```
		sb = MyProject_sb()
		sb.ui.show()
```
	3. Run the app, show the window, wait for input, then terminate program with the status code returned from app.
```
		exit_code = sb.app.exec_()
		if exit_code != -1:
			sys.exit(exit_code)
```