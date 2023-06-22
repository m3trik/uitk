# !/usr/bin/python
# coding=utf-8
from PySide2 import QtWidgets, QtCore
from uitk.widgets.mixins.menu_instance import MenuInstance
from uitk.widgets.mixins.attributes import AttributesMixin


class Label(QtWidgets.QLabel, MenuInstance, AttributesMixin):
    """ """

    clicked = QtCore.Signal()
    released = QtCore.Signal()

    def __init__(self, parent=None, **kwargs):
        QtWidgets.QLabel.__init__(self, parent)

        self.setTextFormat(QtCore.Qt.RichText)
        self.set_attributes(**kwargs)

    def mousePressEvent(self, event):
        """
        Parameters:
                event (QEvent) =
        """
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
            self.option_menu.show()

        if event.button() == QtCore.Qt.RightButton:
            self.ctx_menu.show()

        QtWidgets.QLabel.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        """
        Parameters:
                event (QEvent) =
        """
        if event.button() == QtCore.Qt.LeftButton:
            self.released.emit()

        QtWidgets.QLabel.mouseReleaseEvent(self, event)


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv
    )  # return the existing QApplication object, or create a new one if none exists.

    w = Label(setText="QLabel", setVisible=True)
    w.resize(w.sizeHint().width(), 19)
    menuItem = w.option_menu.add(Label, setText="menu item")
    ctxMenuItem = w.ctx_menu.add(Label, setText="context menu item")
    print(menuItem, ctxMenuItem)
    # w.show()
    sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

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
