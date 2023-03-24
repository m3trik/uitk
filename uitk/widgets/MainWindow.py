# !/usr/bin/python
# coding=utf-8
import sys
from functools import partial
from PySide2 import QtCore, QtGui, QtWidgets
from pythontk import File
from uitk.widgets.attributes import Attributes


class MainWindow(QtWidgets.QMainWindow, Attributes):
	onShow = QtCore.Signal()

	def __init__(self, switchboard_instance, file, connectOnShow=True, **kwargs):
		'''Represents a main window in a GUI application.
		Inherits from QtWidgets.QMainWindow class, providing additional functionality for 
		managing user interface (UI) elements.

		Parameters:
			switchboard_instance (obj): An instance of the switchboard class
			file_path (str): The full path to the UI file
			connectOnShow (bool): While True, the UI will be set as current and connections established when it becomes visible.
			**kwargs: Additional keyword arguments to pass to the MainWindow. ie. setVisible=False

		Attributes:
			onShow: A signal that is emitted when the window is shown.
			sb: An instance of the switchboard class.
			name: The name of the UI file.
			path: The directory path containing the UI file.
			level: The UI level.
			isSubmenu: True if the UI is a submenu.
			isInitialized: True after the UI is first shown.
			isConnected: True if the UI is connected to its slots.
			preventHide: While True, the hide method is disabled.
			connectOnShow: If True, the UI will be set as current and connections established when it becomes visible.
			base: The base UI name.
			tags: Any UI tags as a list.
			_widgets: All the widgets of the UI.
			_deferred: A dictionary of deferred methods.

		Properties:
			<UI>.name (str): The UI filename
			<UI>.base (str): The base UI name
			<UI>.path (str): The directory path containing the UI file
			<UI>.tags (list): Any UI tags as a list
			<UI>.level (int): The UI level
			<UI>.isCurrentUi (bool): True if the UI is set as current
			<UI>.isSubmenu (bool): True if the UI is a submenu
			<UI>.isInitialized (bool): True after the UI is first shown
			<UI>.isConnected (bool): True if the UI is connected to its slots
			<UI>.preventHide (bool): While True, the hide method is disabled
			<UI>.widgets (list): All the widgets of the UI
			<UI>.slots (obj): The slots class instance
		'''
		super().__init__()

		self.sb = switchboard_instance
		self.name = File.formatPath(file, 'name')
		setattr(self.sb, self.name, self)
		if '#' in self.name: #set an alternate attribute name with legal characters.
			legal_name = self.name.replace('#', '_')
			if not hasattr(self.sb, legal_name):
				setattr(self.sb, legal_name, self)

		self.path = File.formatPath(file, 'path')
		self.level = self.sb._getUiLevelFromDir(file)
		self.isSubmenu = self.level==2
		self.isInitialized = False
		self.isConnected = False
		self.preventHide = False
		self.connectOnShow = connectOnShow
		self.base = next(iter(self.name.split('_')))
		self.tags = self.name.split('#')[1:]
		self._widgets = set()
		self._deferred = {}

		ui = self.sb.load(file)
		self.setWindowFlags(ui.windowFlags())
		self.setCentralWidget(ui.centralWidget())
		self.transferProperties(ui, self)
		self.setAttributes(**kwargs)

		if self.level>2:
			self.sb.setStyle(self, style=self.sb.style)

		self.onShow.connect(self._connectOnShow)


	def __getattr__(self, attr_name):
		"""Looks for the widget in the parent class.
		If found, the widget is initialized and returned, else an AttributeError is raised.

		Parameters:
			attr_name (str): the name of the attribute being accessed.

		Return:
			() The value of the widget attribute if it exists, or raises an AttributeError
			if the attribute cannot be found.
  
		Raises:
			AttributeError: if the attribute does not exist in the current instance
			or the parent class.
		"""
		found_widget = self.sb._getWidgetFromUi(self, attr_name)
		if found_widget:
			self.sb.initWidgets(self, found_widget)
			return found_widget

		raise AttributeError(f'{self.__class__.__name__} has no attribute `{attr_name}`')


	def event(self, event):
		"""Handles events that are sent to the widget.

		Parameters:
			event (QtCore.QEvent): The event that was sent to the widget.

		Return:
			bool: True if the event was handled, otherwise False.

		Notes:
			This method is called automatically by Qt when an event is sent to the widget.
			If the event is a `QEvent.ChildPolished` event, it calls the `on_child_polished`
			method with the child widget as an argument. Otherwise, it calls the superclass
			implementation of `event`.
		"""
		if event.type() == QtCore.QEvent.ChildPolished:
			child = event.child()
			self.on_child_polished(child)
		return super().event(event)


	def defer(self, func, *args, priority=0):
		"""Defer execution of a function until later. The function is added to a dictionary of deferred 
		methods, with a specified priority. Lower priority values will be executed before higher ones.
		
		Parameters:
			func (function): The function to defer.
			*args: Any arguments to be passed to the function.
			priority (int, optional): The priority of the deferred method. Lower values will be executed 
					first. Defaults to 0.
		"""
		method = partial(func, *args)
		if priority in self._deferred:
			self._deferred[priority] += (method,)
		else:
			self._deferred[priority] = (method,)


	def trigger_deferred(self):
		"""Executes all deferred methods, in priority order. Any arguments passed to the deferred functions
		will be applied at this point. Once all deferred methods have executed, the dictionary is cleared.
		"""
		for priority in sorted(self._deferred):
			for method in self._deferred[priority]:
				method()
		self._deferred.clear()


	@property
	def widgets(self):
		"""Returns a list of the widgets in the widget's widget dictionary or initializes the widget dictionary and returns all the widgets found in the widget's children.

		Return:
			set: A set of the widgets in the widget's widget dictionary or all the widgets found in the widget's children.
		"""
		return self._widgets or self.sb.initWidgets(self, self.findChildren(QtWidgets.QWidget), returnAllWidgets=True)


	@property
	def slots(self):
		"""Returns a list of the slots connected to the widget's signals.

		Return:
			list: A list of the slots connected to the widget's signals.
		"""
		return self.sb.getSlots(self)


	@property
	def isCurrentUi(self):
		"""Returns True if the widget is the currently active UI, False otherwise."""
		return self==self.sb.getCurrentUi()


	def setAsCurrent(self):
		"""Sets the widget as the currently active UI."""
		self.sb.setCurrentUi(self)


	def setConnections(self):
		"""Connects the widget's signals to their respective slots."""
		if not self.isConnected:
			self.sb.setConnections(self)


	def _connectOnShow(self):
		"""Connects the widget's signals to their respective slots when the widget becomes visible.
		"""
		if self.connectOnShow:
			self.sb.setConnections(self)


	def show(self, app_exec=False):
		"""Show the MainWindow.

		Parameters:
			app_exec (bool): Execute the given PySide2 application, display its window, wait for user input, 
					and then terminate the program with a status code returned from the application.
		"""
		if app_exec:
			exit_code = self.sb.app.exec_()
			if exit_code != -1:
				sys.exit(exit_code)
		super().show()


	def on_child_polished(self, w):
		"""Called after a child widget is polished. Initializes the widget dictionary with the child widget and connects its signals to their respective slots if the widget is connected.

		Parameters:
			w (QWidget): The polished child widget.
		"""
		if w not in self._widgets:
			self.sb.initWidgets(self, w)
			self.trigger_deferred()
			if self.isConnected:
				self.sb.connectSlots(self, w)


	def setVisible(self, state):
		"""Called every time the widget is shown or hidden on screen. If the widget is set to be prevented from hiding, it will not be hidden when state is False.

		Parameters:
			state (bool): Whether the widget is being shown or hidden.
		"""
		if state: #visible
			self.activateWindow()
			# self.raise_()
			self.setWindowFlags(self.windowFlags()|QtCore.Qt.WindowStaysOnTopHint)
			super().setVisible(True)
			self.onShow.emit()
			self.isInitialized = True

		elif not self.preventHide: #invisible
			super().setVisible(False)

# -----------------------------------------------------------------------------









# -----------------------------------------------------------------------------

if __name__ == "__main__":
	import sys


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

'''
Promoting a widget in designer to use a custom class:
>	In Qt Designer, select all the widgets you want to replace, 
		then right-click them and select 'Promote to...'. 

>	In the dialog:
		Base Class:		Class from which you inherit. ie. QWidget
		Promoted Class:	Name of the class. ie. "MyWidget"
		Header File:	Path of the file (changing the extension .py to .h)  ie. myfolder.mymodule.mywidget.h

>	Then click "Add", "Promote", 
		and you will see the class change from "QWidget" to "MyWidget" in the Object Inspector pane.
'''

# deprecated ---------------------