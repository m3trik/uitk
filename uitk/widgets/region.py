# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore, QtGui
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins import ConvertMixin


class Region(QtWidgets.QWidget, AttributesMixin, ConvertMixin):
    """A custom QWidget that represents a region with a specified shape and size.
    Emits an on_enter signal when the mouse cursor enters the region.
    """

    on_enter = QtCore.Signal()
    on_leave = QtCore.Signal()

    def __init__(
        self,
        parent,
        position=(0, 0),
        size=(45, 45),
        shape=QtGui.QRegion.Ellipse,
        visible_on_mouse_over=False,
        **kwargs,
    ):
        """Initialize the Region widget.

        Parameters:
                parent (QtWidgets.QWidget): The parent widget for the Region instance.
                position (QPoint or tuple, optional): A tuple of (x, y) coordinates specifying the position of the center
                        of the region. Default is (0, 0).
                size (QSize or tuple, optional): A tuple of (width, height) specifying the size of the region. Default is (45, 45).
                shape (QRegion.Shape, optional): The shape of the region (default is QtGui.QRegion.Ellipse).
                visible_on_mouse_over (bool): Top level children are hidden when the mouse is not over the region.
                **kwargs: Additional keyword arguments to pass to the main window. ie. setVisible=False or setMouseTracking=True
        """
        super().__init__(parent)

        position = self.to_qobject(position, QtCore.QPoint)
        size = self.to_qobject(size, QtCore.QSize)

        self.resize(size)
        self.setGeometry(self.rect())

        # Create a QRegion with the specified shape
        rect = QtCore.QRect(0, 0, size.width(), size.height())
        self.region = QtGui.QRegion(rect, shape)

        self.visible_on_mouse_over = visible_on_mouse_over

        self.move(self.mapFromGlobal(position - self.rect().center()))

        self.cursor_inside = False  # Track whether the cursor is inside the region.

        self.setVisible(True)
        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    @property
    def visible_on_mouse_over(self):
        """Get or set the visibility of the top-level children of the Region widget when the mouse cursor is over it.

        When set to True, the top-level children widgets will be hidden initially and will be shown when the mouse cursor
        enters the region. The children widgets will be hidden again when the cursor leaves the region.

        When set to False, the top-level children widgets will remain visible regardless of the mouse cursor's position.
        """
        return self._visible_on_mouse_over

    @visible_on_mouse_over.setter
    def visible_on_mouse_over(self, value):
        """Set the visibility of the top-level children of the Region widget when the mouse cursor is over it.

        Parameters:
                value (bool): If True, the top-level children widgets will be hidden initially and will be shown when the
                        mouse cursor enters the region. The children widgets will be hidden again when the cursor leaves the
                        region. Else, top-level children widgets will remain visible regardless of the mouse cursor's position.
        """
        if value:
            self.hide_top_level_children()
            self.on_enter.connect(self.show_top_level_children)
            self.on_leave.connect(self.hide_top_level_children)
        else:
            try:
                self.on_enter.disconnect(self.show_top_level_children)
                self.on_leave.disconnect(self.hide_top_level_children)
            except RuntimeError:
                pass
        self._visible_on_mouse_over = value

    def hide_top_level_children(self):
        """Hide all top-level child widgets of the Region instance."""
        for child in self.children():
            if isinstance(child, QtWidgets.QWidget):
                child.hide()

    def show_top_level_children(self):
        """Show all top-level child widgets of the Region instance."""
        for child in self.children():
            if isinstance(child, QtWidgets.QWidget):
                child.show()

    def enterEvent(self, event):
        """Overrides the QWidget.enterEvent method. Emits the on_enter signal when
        the cursor enters the Region widget's area, ensuring that the signal is
        emitted only once.

        Parameters:
                event (QEvent): The event object passed to the method.
        """
        cursor_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        if not self.cursor_inside and self.rect().contains(cursor_pos):
            self.cursor_inside = True
            self.on_enter.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Overrides the QWidget.leaveEvent method. Emits the on_leave signal when
        the cursor leaves the Region widget's area, ensuring that the signal is
        emitted only once.

        Parameters:
                event (QEvent): The event object passed to the method.
        """
        cursor_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        if self.cursor_inside and not self.rect().contains(cursor_pos):
            self.cursor_inside = False
            self.on_leave.emit()
        super().leaveEvent(event)

    def hideEvent(self, event):
        """Overrides the QWidget.hideEvent method. Emits the on_leave signal when
        the widget is hidden.

        Parameters:
                event (QEvent): The event object passed to the method.
        """
        if self.visible_on_mouse_over:
            self.hide_top_level_children()
        self.cursor_inside = False
        super().hideEvent(event)

    def childEvent(self, event):
        """Overrides the QWidget.childEvent method. Hides the child widget if the
        visible_on_mouse_over flag is set to True.

        Parameters:
                event (QChildEvent): The event object passed to the method.
        """
        if self.visible_on_mouse_over and event.type() == QtCore.QEvent.ChildAdded:
            self.hide_top_level_children()

        super().childEvent(event)


# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    def on_region_enter():
        print("Mouse entered the region")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    main_window = QtWidgets.QMainWindow()
    main_window.setWindowTitle("Region Example")
    main_window.resize(300, 300)

    region_widget = Region(
        main_window, position=(150, 150), size=(50, 50), setMouseTracking=True
    )
    region_widget.on_enter.connect(on_region_enter)

    main_window.show()

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

# deprecated ---------------------
