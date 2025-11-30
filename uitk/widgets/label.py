# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.menu_mixin import MenuMixin


class Label(QtWidgets.QLabel, MenuMixin, AttributesMixin):
    """Enhanced QLabel with click signals and context menu support.

    Extends QLabel with:
    - Click and release signals for interactive labels
    - Built-in right-click context menu (via MenuMixin)
    - Rich text support enabled by default
    - Attribute setting via kwargs

    Signals:
        clicked: Emitted on left mouse button press.
        released: Emitted on left mouse button release.

    Attributes:
        menu: Context menu accessible via right-click (from MenuMixin).

    Example:
        label = Label(setText="<b>Click me</b>")
        label.clicked.connect(lambda: print("Clicked!"))
        label.menu.add("Copy")
    """

    clicked = QtCore.Signal()
    released = QtCore.Signal()

    def __init__(self, parent=None, **kwargs):
        """Initialize the Label.

        Parameters:
            parent (QWidget, optional): Parent widget.
            **kwargs: Additional attributes to set via set_attributes().
        """
        QtWidgets.QLabel.__init__(self, parent)

        # Customize standalone menu provided by MenuMixin
        self.menu.trigger_button = "right"
        self.menu.position = "cursorPos"
        self.menu.fixed_item_height = 20
        self.menu.hide_on_leave = True

        self.setTextFormat(QtCore.Qt.RichText)
        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    def mousePressEvent(self, event):
        """Handle mouse press events to emit clicked signal.

        Parameters:
            event (QMouseEvent): The mouse event.
        """
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()

        QtWidgets.QLabel.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release events to emit released signal.

        Parameters:
            event (QMouseEvent): The mouse event.
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
    menuItem = w.menu.add(Label, setText="menu item")
    ctxMenuItem = w.menu.add(Label, setText="context menu item")
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
