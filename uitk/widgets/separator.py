# !/usr/bin/python
# coding=utf-8
from typing import Optional
from qtpy import QtWidgets
from uitk.widgets.mixins.attributes import AttributesMixin


class Separator(QtWidgets.QFrame, AttributesMixin):
    """A simple horizontal separator with optional styling and attributes."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, **kwargs):
        super().__init__(parent)

        self.setProperty("class", "separator")
        self.setFrameShape(QtWidgets.QFrame.HLine)
        self.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.setFixedHeight(1)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.set_attributes(self, **kwargs)


# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from qtpy.QtCore import QSize

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv
    )  # return the existing QApplication object, or create a new one if none exists.

    w = Separator(setStyleSheet="background-color: red;", setMinimumSize=QSize(200, 1))
    w.show()
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
