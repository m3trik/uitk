# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtGui, QtWidgets

from uitk.widgets.attributes import Attributes


class ListWidget(QtWidgets.QListWidget, Attributes):
	"""A QListWidget subclass that adds functionality for adding and getting items, and for expanding and hiding sub-lists.

	Attributes:
		parent (obj): The parent object.
		child_height (int): The height of child widgets.
		position (str): The position of the menu relative to the parent widget.
		**kwargs: Additional keyword arguments to pass to the widget.

	Methods:
		__init__(self, parent=None, child_height=19, position='topLeft', **kwargs):
			Initializes a new instance of the ListWidget class.

		convert(self, items, to='QLabel', **kwargs):
			Converts the given items to a specified widget type.

		getItems(self):
			Returns a list of items in the list widget.

		getItemsByText(self, text):
			Returns a list of items in the list widget that have the specified text.

		getItemWidgets(self):
			Returns a list of widgets in the list widget.

		getItemWidgetsByText(self, text):
			Returns a list of widgets in the list widget that have the specified text.

		setData(self, wItem, data, typ=QtCore.Qt.UserRole):
			Sets data for the specified item widget.

		getData(self, wItem, typ=QtCore.Qt.UserRole):
			Returns the data for the specified item widget.

		addItem(self, i):
			Adds an item to the list widget.

		addItems(self, items):
			Adds multiple items to the list widget.

		add(self, w, data=None, **kwargs):
			Adds a widget to the list widget.

		_addList(self, w):
			Adds an expanding list to the specified widget.

		_hideLists(self, lw):
			Hides the specified list and all previous lists in its hierarchy.

		eventFilter(self, w, event):
			Filters events for the specified widget.

	"""
	def __init__(self, parent=None, child_height=19, position='topRight', **kwargs):
		"""Initializes a new instance of the ListWidget class.

		Parameters:
			parent (obj): The parent object.
			child_height (int): The height of child widgets.
			position (str): The position of the menu relative to the parent widget.
			**kwargs: Additional keyword arguments to pass to the widget.
		"""
		super().__init__(parent)

		self.child_height = child_height
		self.position = position
		self.setAttributes(**kwargs)


	def convert(self, items, to='QLabel', **kwargs):
		"""Converts the given items to a specified widget type.

        Parameters:
            items (list, tuple, set, dict): The items to convert.
            to (str): The widget type to convert the items to.
            **kwargs: Additional keyword arguments to pass to the widget.

        Example:
            self.convert(self.getItems(), 'QPushButton') #construct the list using the existing contents.
        """
		lst = lambda x: list(x) if isinstance(x, (list, tuple, set, dict)) else [x] #assure 'x' is a list.

		for item in lst(items):
			i = self.indexFromItem(item).row() #get the row as an int from the items QModelIndex.
			item = self.takeItem(i)
			self.add(to, setText=item.text(), **kwargs)


	def getItems(self):
		"""Returns a list of items in the list widget.
        """
		return [self.item(i) for i in range(self.count())]


	def getItemsByText(self, text):
		'''
		'''
		return [i for i in self.getItems() if i.text()==text]


	def getItemWidgets(self):
		'''
		'''
		return [self.itemWidget(self.item(i)) for i in range(self.count())]


	def getItemWidgetsByText(self, text):
		'''
		'''
		return [i for i in self.getItemWidgets() if hasattr(i, 'text') and i.text()==text]


	def setData(self, wItem, data, typ=QtCore.Qt.UserRole):
		'''
		'''
		wItem.setData(typ, data)


	def getData(self, wItem, typ=QtCore.Qt.UserRole):
		'''
		'''
		return wItem.data(typ)


	def addItem(self, i):
		'''
		'''
		return self.add(i)


	def addItems(self, items):
		'''
		'''
		if isinstance(items, dict):
			return [self.add(w, d) for w,d in items.items()]

		else:
			return [self.add(w) for w in items]


	def add(self, w, data=None, **kwargs):
		"""Add items to the menu.

		This method adds items to the menu, either as a single item or multiple items from a collection.
		The added item can be a widget object or a string representation of a widget class name. If the input
		is a string, it creates a label and sets the input string as the label's text. Additional attributes for
		the widget can be passed as keyword arguments.

		Parameters:
			w (str or obj): Widget object or string representation of a widget class name to be added to the menu.
			data (optional): Data to be associated with the added item(s).
			kwargs: Additional attributes for the widget.

		Returns:
			obj: The added item object.

		Example call:
			menu().add(w='QAction', setText='', insertSeparator=True)
		"""
		if isinstance(w, (dict, list, tuple, set)):
			if isinstance(data, (list, tuple, set)):
				w = dict(zip(w, data))
			return self.addItems(w)

		try: #get the widget from string class name.
			w = getattr(QtWidgets, w)(self) #ex. QtWidgets.QAction(self) object from string.
		except AttributeError: #if w is a widget object instead of string.
			try:
				w = w() #ex. QtWidgets.QAction(self) object.
			except TypeError:
				pass

		typ = w.__class__.__name__
		if typ=='str': #if 'w' is still a string; create a label and use the str value as the label's text.
			lbl = QtWidgets.QLabel(self)
			lbl.setText(w)
			w = lbl

		wItem = QtWidgets.QListWidgetItem(self)
		w.setFixedHeight(self.child_height)
		wItem.setSizeHint(w.size())
		self.setItemWidget(wItem, w)
		self.setData(wItem, data)
		wItem.getData = lambda i=wItem: self.getData(i)
		w.installEventFilter(self)
		super().addItem(wItem)

		w.__class__.list = property( #add an expandable list to the widget.
			lambda w: w.lw if hasattr(w, 'lw') else self._addList(w)
		)

		self.setAttributes(w, **kwargs) #set any additional given keyword args for the widget.
		self.raise_()

		return w


	def _addList(self, w):
		"""Add an expanding list to the given widget.

		This method adds an expandable list to the given widget. The expanding list is created as a ListWidget
		object and is initially hidden.

		Parameters:
			w (obj): Widget object to which the expandable list will be added.

		Returns:
			obj: The added ListWidget object.
		"""
		lw = ListWidget(self.window(), setVisible=False)
		w.lw = lw
		w.lw.prev = self

		w.lw.root = self
		while hasattr(w.lw.root, 'prev'):
			w.lw.root = w.lw.root.prev

		return w.lw


	def _hideLists(self, lw):
		"""Hide the given list and all previous lists in its hierarchy.

		This method hides the given list and all previous lists in its hierarchy, up to the point where the cursor
		is within the list's boundaries.

		Parameters:
			lw (obj): ListWidget object to start hiding from.
		"""
		while hasattr(lw, 'prev'):
			if lw.rect().contains(lw.mapFromGlobal(QtGui.QCursor.pos())):
				break
			lw.hide()
			lw = lw.prev


	def eventFilter(self, w, event):
		'''
		'''
		if event.type() == QtCore.QEvent.Enter:
			try:
				if self.position == 'topRight':
					pos = self.window().mapFromGlobal(w.mapToGlobal(w.rect().topRight()))
				elif self.position == 'topLeft':
					pos = self.window().mapFromGlobal(w.mapToGlobal(w.rect().topLeft()))
				elif self.position == 'bottomRight':
					pos = self.window().mapFromGlobal(w.mapToGlobal(w.rect().bottomRight()))
				elif self.position == 'bottomLeft':
					pos = self.window().mapFromGlobal(w.mapToGlobal(w.rect().bottomLeft()))
				else:
					raise ValueError("Invalid position value. Must be one of 'topRight', 'topLeft', 'bottomRight', 'bottomLeft'")

				w.list.move(pos)
				w.list.show()
			except AttributeError:
				pass

		elif event.type()==QtCore.QEvent.MouseButtonRelease:
			if QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())==w:
				try:
					if not self==w.lw.root:
						try:
							self.itemClicked.disconnect()
						except RuntimeError:
							pass
						self.itemClicked.connect(w.lw.root.itemClicked)
						index = self.indexAt(w.pos()) #Get the index of the item that contains the widget.
						wItem = self.item(index.row()) #Get the QListWidgetItem object.
						self.itemClicked.emit(wItem)
				except AttributeError:
					pass

		elif event.type() == QtCore.QEvent.Leave:
			try:
				if not w.list.rect().contains(w.list.mapFromGlobal(QtGui.QCursor.pos())):
					if hasattr(w, 'prev'):
						self.hide()
					if hasattr(w, 'lw'):
						w.lw.hide()
			except AttributeError:
				pass

		return super().eventFilter(w, event)


	def leaveEvent(self, event):
		'''
		'''
		self._hideLists(self)

		super().leaveEvent(event)


	def showEvent(self, event):
		'''
		'''
		self.resize(self.sizeHint().width(), (self.child_height+2)*self.count())

		super().showEvent(event)

# -----------------------------------------------------------------------------









# -----------------------------------------------------------------------------

if __name__ == "__main__":
	import sys
	app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv) #return the existing QApplication object, or create a new one if none exists.

	window = QtWidgets.QWidget()
	lw = ListWidget(window)
	w1 = lw.add('QPushButton', setObjectName='b001', setText='Button 1')
	w1.list.add('list A')
	w2 = lw.add('QPushButton', setObjectName='b002', setText='Button 2')
	w3, w4 = w2.list.addItems(['List B1', 'List B2'])
	w3.list.add('QPushButton', setObjectName='b004', setText='Button 4')
	lw.add('QPushButton', setObjectName='b003', setText='Button 3')

	# print (lw.getItems())
	# print (lw.getItemWidgets())

	window.resize(765, 255)
	window.show()
	sys.exit(app.exec_())


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


	# def event(self, event):
	# 	"""Handles events that are sent to the widget.

	# 	Parameters:
	# 		event (QtCore.QEvent): The event that was sent to the widget.

	# 	Return:
	# 		bool: True if the event was handled, otherwise False.

	# 	Notes:
	# 		This method is called automatically by Qt when an event is sent to the widget.
	# 		If the event is a `QEvent.ChildPolished` event, it calls the `on_child_polished`
	# 		method with the child widget as an argument. Otherwise, it calls the superclass
	# 		implementation of `event`.
	# 	"""
	# 	if event.type() == QtCore.QEvent.HoverMove:
	# 		print ('event_hoverMoveEvent'.ljust(25), self.mouseGrabber())
	# 		# window = QtWidgets.QApplication.activeWindow()
	# 		# if window and not self.rect().contains(self.mapFromGlobal(QtGui.QCursor.pos())):
	# 		# 	if window.mouseGrabber() == self:
	# 		# 		self.releaseMouse()

	# 	elif event.type() == QtCore.QEvent.HoverLeave:
	# 		print ('event_hoverLeaveEvent'.ljust(25), self.mouseGrabber())
	# 		# window = QtWidgets.QApplication.activeWindow()
	# 		# if window and not self.rect().contains(self.mapFromGlobal(QtGui.QCursor.pos())):
	# 			# if window.mouseGrabber() == self:
	# 		self.releaseMouse()

	# 	return super().event(event)