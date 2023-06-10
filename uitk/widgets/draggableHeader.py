# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtGui, QtWidgets
from uitk.widgets.mixins.menu_instance import MenuInstance
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay


class DraggableHeader(
    QtWidgets.QLabel, MenuInstance, AttributesMixin, RichText, TextOverlay
):
    """Draggable/Checkable QLabel."""

    headerPinned = QtCore.Signal()
    headerUnpinned = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.checkable = True
        self.checked = False
        self.dragged = False
        self.__mousePressPos = None

        self.setStyleSheet(
            """
            QLabel {
                background-color: rgba(127,127,127,2);
                border: 1px solid transparent;
                font-weight: bold;
            }

            QLabel::hover {
                background-color: rgba(127,127,127,2);
                border: 1px solid transparent;
            }"""
        )

        self.setCursor(QtGui.QCursor(QtCore.Qt.OpenHandCursor))

        # Connect the signals to the local slots
        self.headerPinned.connect(self.pin_header)
        self.headerUnpinned.connect(self.unpin_header)

    def pin_header(self):
        """Slot to handle the header being pinned."""
        self.window().prevent_hide = True

    def unpin_header(self):
        """Slot to handle the header being unpinned."""
        self.window().prevent_hide = False
        if not self.isChecked():
            print("window:", self.window())
            self.window().hide()

    def setCheckable(self, state):
        self.checkable = state

    def isChecked(self):
        return self.checked

    def setChecked(self, state):
        if self.checkable:
            self.checked = state

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.__mousePressPos = event.globalPos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.__mousePressPos is not None:
            moveAmount = event.globalPos() - self.__mousePressPos
            if moveAmount.manhattanLength() > 5:
                self.headerPinned.emit()
                # Move the top-level widget
                self.window().move(self.window().pos() + moveAmount)
                self.__mousePressPos = event.globalPos()
                self.dragged = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.__mousePressPos is not None:
            moveAmount = event.globalPos() - self.__mousePressPos
            if moveAmount.manhattanLength() <= 5 and not self.dragged:
                self.setChecked(not self.isChecked())
                self.headerUnpinned.emit()
                if not self.isChecked():
                    self.window().hide()
            if self.dragged:
                self.setChecked(True)
                self.dragged = False
        self.__mousePressPos = None
        super().mouseReleaseEvent(event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(w)
    header = DraggableHeader(w)
    header.setText("Drag me!")
    header.headerPinned.connect(lambda: print("Header pinned!"))
    header.headerUnpinned.connect(lambda: print("Header unpinned!"))
    layout.addWidget(header)
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


# Deprecated: --------------------
