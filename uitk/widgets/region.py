# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtGui, QtWidgets
from uitk.widgets.attributes import Attributes


class Region(QtWidgets.QWidget, Attributes):
	"""A custom QWidget that represents a region with a specified shape and size.
	Emits an onEnter signal when the mouse cursor enters the region.
	"""
	onEnter = QtCore.Signal()
	onLeave = QtCore.Signal()

	def __init__(self, parent, position=(0, 0), size=(45, 45), shape=QtGui.QRegion.Ellipse, transparentForMouseEvents=False, **kwargs):
		"""Initialize the Region widget.

		Parameters:
			parent (QtWidgets.QWidget): The parent widget for the Region instance.
			position (QPoint or tuple, optional): A tuple of (x, y) coordinates specifying the position of the center
				of the region. Default is (0, 0).
			size (QSize or tuple, optional): A tuple of (width, height) specifying the size of the region. Default is (45, 45).
			shape (QRegion.Shape, optional): The shape of the region (default is QtGui.QRegion.Ellipse).
			transparentForMouseEvents (bool): Allow events to pass through to the widget's underlying parent or sibling widgets.
			**kwargs: Additional keyword arguments to pass to the MainWindow. ie. setVisible=False
		"""
		super().__init__(parent)

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
		self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, transparentForMouseEvents)
		self.setAttributes(**kwargs)

		self.event_filter = RegionEventFilter(self)
		self.window().installEventFilter(self.event_filter)


	def hide_top_level_children(self):
		"""Hide all top-level child widgets of the Region instance.
		"""
		for child in self.children():
			if isinstance(child, QtWidgets.QWidget):
				child.hide()


	def show_top_level_children(self):
		"""Show all top-level child widgets of the Region instance.
		"""
		for child in self.children():
			if isinstance(child, QtWidgets.QWidget):
				child.show()



class RegionEventFilter(QtCore.QObject):
    def __init__(self, region):
        super().__init__()
        self.region = region

    def eventFilter(self, obj, event):
        if self.region.isVisible() and event.type() == QtCore.QEvent.MouseMove:
            cursor_inside_now = self.region.region.contains(self.region.mapFromGlobal(QtGui.QCursor.pos()))
            if cursor_inside_now and not self.region.cursor_inside:
                self.region.onEnter.emit()
                print('emit enter', obj.objectName())
            elif not cursor_inside_now and self.region.cursor_inside:
                self.region.onLeave.emit()
                print('emit leave', obj.objectName())
            self.region.cursor_inside = cursor_inside_now
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