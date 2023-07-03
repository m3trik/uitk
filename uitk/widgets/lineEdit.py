# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtWidgets
from uitk.widgets.menu import Menu
from uitk.widgets.mixins.attributes import AttributesMixin


class LineEdit(QtWidgets.QLineEdit, AttributesMixin):
    """ """

    shown = QtCore.Signal()
    hidden = QtCore.Signal()

    def __init__(self, parent=None, **kwargs):
        QtWidgets.QLineEdit.__init__(self, parent)

        self.menu = Menu(self, position="cursorPos")

        self.set_attributes(**kwargs)

    def contextMenuEvent(self, event):
        """Override the standard context menu if there is a custom one.

        Parameters:
                event=<QEvent>
        """
        if self.menu.contains_items:
            self.menu.show()
        else:
            super().contextMenuEvent(event)

    def showEvent(self, event):
        """
        Parameters:
                event=<QEvent>
        """
        self.shown.emit()

        QtWidgets.QLineEdit.showEvent(self, event)

    def hideEvent(self, event):
        """
        Parameters:
                event=<QEvent>
        """
        self.hidden.emit()

        QtWidgets.QLineEdit.hideEvent(self, event)


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv
    )  # return the existing QApplication object, or create a new one if none exists.

    w = LineEdit()

    w.insertText(
        'Selected: <font style="color: Yellow;">8 <font style="color: LightGray;">/1486 faces'
    )
    w.insertText('Previous Camera: <font style="color: Yellow;">Perspective')

    w.show()
    sys.exit(app.exec_())


# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------

"""
Promoting a widget in designer to use a custom class:
>   In Qt Designer, select all the widgets you want to replace, 
        then right-click them and select 'Promote to...'. 

>   In the dialog:
        Base Class:     Class from which you inherit. ie. QWidget
        Promoted Class: Name of the class. ie. "MyWidget"
        Header File:    Path of the file (changing the extension .py to .h)  ie. myfolder.mymodule.mywidget.h

>   Then click "Add", "Promote", 
        and you will see the class change from "QWidget" to "MyWidget" in the Object Inspector pane.
"""

# deprecated:

# if pm.progressBar ("progressBar_", q=True, isCancelled=1):
# break


# def insertText(self, dict_):
#   '''
#   Parameters:
#       dict_ = {dict} - contents to add.  for each key if there is a value, the key and value pair will be added.
#   '''
#   highlight = QtGui.QColor(255, 255, 0)
#   baseColor = QtGui.QColor(185, 185, 185)

#   #populate the textedit with any values
#   for key, value in dict_.items():
#       if value:
#           self.setTextColor(baseColor)
#           self.append(key) #Appends a new paragraph with text to the end of the text edit.
#           self.setTextColor(highlight)
#           self.insertPlainText(str(value)) #inserts text at the current cursor position.
