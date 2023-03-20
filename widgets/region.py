# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtGui, QtWidgets


class Region(QtWidgets.QWidget):
	"""A custom QWidget that represents a region with a specified shape and size.
	Emits an onEnter signal when the mouse cursor enters the region.
	"""
	onEnter = QtCore.Signal()

	def __init__(self, parent, position=(0, 0), size=(45, 45), shape=QtGui.QRegion.Ellipse, mouseTracking=False):
		"""Initialize the Region widget.

		Parameters:
			parent (QtWidgets.QWidget): The parent widget for the Region instance.
			position (QPoint or tuple, optional): A tuple of (x, y) coordinates specifying the position of the center
				of the region. Default is (0, 0).
			size (QSize or tuple, optional): A tuple of (width, height) specifying the size of the region. Default is (45, 45).
			shape (QRegion.Shape, optional): The shape of the region (default is QtGui.QRegion.Ellipse).
			mouseTracking (bool, optional): Whether to enable mouse tracking for the region. Default is False.
		"""
		super().__init__(parent)

		self.setMouseTracking(mouseTracking)
		self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

		if not isinstance(position, QtCore.QPoint):
			position = QtCore.QPoint(position[0], position[1])

		if not isinstance(size, QtCore.QSize):
			size = QtCore.QSize(size[0], size[1])

		self.resize(size)
		self.setGeometry(self.rect())

		# Create a QRegion with the specified shape
		rect = QtCore.QRect(0, 0, size.width(), size.height())
		self.region = QtGui.QRegion(rect, shape)

		self.move(self.mapFromGlobal(position - self.rect().center()))

		self.cursor_inside = False # Track whether the cursor is inside the region.

		self.setVisible(True)

		self.window().installEventFilter(self)


	def eventFilter(self, obj, event):
		"""Filter mouse move events and emit the onEnter signal when the mouse cursor enters the region.

		Parameters:
			obj (QObject): The object that is the target of the event.
			event (QEvent): The event that is being filtered.

		Returns:
			bool: Whether the event has been handled. If the event is handled, it is stopped; otherwise, it is propagated.
		"""
		if self.isVisible() and event.type() == QtCore.QEvent.MouseMove:
			cursor_inside_now = self.region.contains(self.mapFromGlobal(QtGui.QCursor.pos()))
			if cursor_inside_now and not self.cursor_inside:
				self.onEnter.emit()
			self.cursor_inside = cursor_inside_now
		return super().eventFilter(obj, event)

# -----------------------------------------------------------------------------









# -----------------------------------------------------------------------------

if __name__ == "__main__":
	import sys

	def on_region_enter():
		print("Mouse entered the region")

	app = QtWidgets.QApplication(sys.argv)

	main_window = QtWidgets.QMainWindow()
	main_window.setWindowTitle("Region Example")
	main_window.resize(300, 300)

	region_widget = Region(main_window, position=(150, 150), size=(50, 50), mouseTracking=True)
	region_widget.onEnter.connect(on_region_enter)

	main_window.show()

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