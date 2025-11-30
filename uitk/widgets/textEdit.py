# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.menu_mixin import MenuMixin


class TextEdit(QtWidgets.QTextEdit, MenuMixin, AttributesMixin):
    """Rich text editor with context menu and visibility signals."""

    shown = QtCore.Signal()
    hidden = QtCore.Signal()

    def __init__(self, parent=None, **kwargs):
        QtWidgets.QTextEdit.__init__(self, parent)

        self.viewport().setAutoFillBackground(False)

        # Customize standalone menu provided by MenuMixin
        self.menu.trigger_button = "right"
        self.menu.position = "cursorPos"
        self.menu.fixed_item_height = 20
        self.menu.hide_on_leave = True

        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    def insertText(self, text, color="LightGray", backround_color="rgb(50, 50, 50)"):
        """Append a new paragraph to the textEdit.

        Parameters:
                text (str): A value to append to the lineEdit as a new paragraph. The value is converted to a string if it isn't already.
        """
        # Appends a new paragraph with the given text to the end of the textEdit.
        self.append(
            f'<font style="color: {color}; background-color: {backround_color};">{text}'
        )

    def showEvent(self, event):
        """
        Parameters:
                event=<QEvent>
        """
        QtWidgets.QTextEdit.showEvent(self, event)
        self.shown.emit()

    def hideEvent(self, event):
        """
        Parameters:
                event=<QEvent>
        """
        self.clear()

        QtWidgets.QTextEdit.hideEvent(self, event)
        self.hidden.emit()


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv
    )  # return the existing QApplication object, or create a new one if none exists.

    w = TextEdit()

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

# deprecated: -----------------------------------

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
