# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtGui, QtWidgets

from uitk.widgets.attributes import Attributes
from uitk.widgets.text import RichText, TextOverlay
from uitk.widgets.menu import MenuInstance
from uitk.widgets.pushButton_optionBox import PushButton_optionBox


class Draggable_header(QtWidgets.QLabel, MenuInstance, Attributes, RichText, TextOverlay):
	'''Draggable/Checkable QLabel.
	'''
	__mousePressPos = QtCore.QPoint()

	def __init__(self, parent=None, **kwargs):
		QtWidgets.QLabel.__init__(self, parent)

		self.setStyleSheet(parent.styleSheet()) if parent else None

		self.checkable = True
		self.checked = False

		self.setStyleSheet('''
			QLabel {
				background-color: rgba(127,127,127,2);
				border: 1px solid transparent;
			}

			QLabel::hover {
				background-color: rgba(127,127,127,2);
				border: 1px solid transparent;
			}''')

		self.setCursor(QtGui.QCursor(QtCore.Qt.OpenHandCursor))

		#override built-ins
		self.text = self.richText
		self.setText = self.setRichText
		self.sizeHint = self.richTextSizeHint

		self.optionBox = None

		self.setAttributes(**kwargs)


	def setCheckable(self, state):
		self.checkable = state


	def isChecked(self):
		return self.checked


	def setChecked(self, state):
		if self.checkable:
			self.checked = state


	def mousePressEvent(self, event):
		'''
		Parameters:
			event=<QEvent>
		'''
		if event.button()==QtCore.Qt.LeftButton:
			self.__mousePressPos = event.globalPos() #mouse positon at press.
			self.__mouseMovePos = event.globalPos() #mouse move position from last press. (updated on move event) 

			self.setChecked(True) #setChecked to prevent window from closing.
			self.window().preventHide = True

		if event.button()==QtCore.Qt.RightButton:
			self.ctxMenu.show()

		QtWidgets.QLabel.mousePressEvent(self, event)


	def mouseMoveEvent(self, event):
		'''
		Parameters:
			event=<QEvent>
		'''
		self.setCursor(QtGui.QCursor(QtCore.Qt.ClosedHandCursor))

		#move window:
		curPos = self.window().mapToGlobal(self.window().pos())
		globalPos = event.globalPos()

		try: #if hasattr(self, '__mouseMovePos'):
			diff = globalPos - self.__mouseMovePos

			self.window().move(self.window().mapFromGlobal(curPos + diff))
			self.__mouseMovePos = globalPos
		except AttributeError as error:
			pass

		QtWidgets.QLabel.mouseMoveEvent(self, event)


	def mouseReleaseEvent(self, event):
		'''
		Parameters:
			event=<QEvent>
		'''
		self.setCursor(QtGui.QCursor(QtCore.Qt.OpenHandCursor))

		moveAmount = event.globalPos() - self.__mousePressPos

		if moveAmount.manhattanLength() > 5:  # if widget moved:
			self.setChecked(True)  # setChecked to prevent window from closing.
			self.window().preventHide = True
		else:
			self.setChecked(not self.isChecked())  # toggle check state

		self.window().preventHide = self.isChecked()
		if not self.window().preventHide:  # prevent the parent window from hiding if checked.
			self.window().hide()

		QtWidgets.QLabel.mouseReleaseEvent(self, event)


	def createOptionBox(self):
		'''
		'''
		self.optionBox = PushButton_optionBox(self) #create an option box
		self.optionBox.create()


	def showEvent(self, event):
		'''
		Parameters:
			event = <QEvent>
		'''
		if self.ctxMenu.containsMenuItems:
			# self.ctxMenu.setTitle(self.text())
			# self.setTextOverlay('⧉', alignment='AlignRight')
			if not self.optionBox:
				self.createOptionBox()

		QtWidgets.QLabel.showEvent(self, event)


	def hideEvent(self, event):
		'''
		Parameters:
			event = <QEvent>
		'''

		QtWidgets.QLabel.hideEvent(self, event)

# -----------------------------------------------------------------------------









# -----------------------------------------------------------------------------

if __name__ == "__main__":
	import sys
	app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv) #return the existing QApplication object, or create a new one if none exists.
		
	w = Draggable_header()
	w.show()

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


# Deprecated: --------------------

