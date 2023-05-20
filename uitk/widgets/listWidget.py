# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtGui, QtWidgets
from uitk.widgets.mixins.attributes import AttributesMixin

import gc


class TrackGC:
    def __init__(self):
        self._tracked_refs = {}

    def track(self, obj):
        ref = id(obj)
        self._tracked_refs[ref] = obj

    def untrack(self, obj):
        ref = id(obj)
        if ref in self._tracked_refs:
            del self._tracked_refs[ref]

    def get_tracked(self):
        return self._tracked_refs.values()

    def check_garbage_collected(self):
        gc.collect()
        collected = []
        for ref, obj in list(self._tracked_refs.items()):
            if ref not in {id(o) for o in self.get_tracked()}:
                collected.append(obj)
                self.untrack(obj)
        return collected


tracker = TrackGC()


class ListWidget(QtWidgets.QListWidget, AttributesMixin):
    """A QListWidget subclass that adds functionality for adding and getting items, and for expanding and hiding sub-lists.

    AttributesMixin:
        parent (obj): The parent object.
        child_height (int): The height of child widgets.
        position (str): The position of the menu relative to the parent widget.
        **kwargs: Additional keyword arguments to pass to the widget.

    Methods:
        __init__(self, parent=None, child_height=19, position='topLeft', **kwargs):
                Initializes a new instance of the ListWidget class.

        convert(self, items, to='QLabel', **kwargs):
                Converts the given items to a specified widget type.

        getItems(self):
                Returns a list of items in the list widget.

        getItemsByText(self, text):
                Returns a list of items in the list widget that have the specified text.

        getItemWidgets(self):
                Returns a list of widgets in the list widget.

        getItemWidgetsByText(self, text):
                Returns a list of widgets in the list widget that have the specified text.

        setData(self, wItem, data, typ=QtCore.Qt.UserRole):
                Sets data for the specified item widget.

        getData(self, wItem, typ=QtCore.Qt.UserRole):
                Returns the data for the specified item widget.

        addItem(self, i):
                Adds an item to the list widget.

        addItems(self, items):
                Adds multiple items to the list widget.

        add(self, x, data=None, **kwargs):
                Adds a widget to the list widget.

        _addList(self, widget):
                Adds an expanding list to the specified widget.

        _hideLists(self, listWidget):
                Hides the specified list and all previous lists in its hierarchy.

        eventFilter(self, widget, event):
                Filters events for the specified widget.
    """

    def __init__(
        self,
        parent=None,
        position="right",
        x_offset=0,
        y_offset=0,
        child_width=120,
        child_height=18,
        max_child_width=400,
        drag_interaction=False,
        **kwargs,
    ):
        """Initializes a new instance of the ListWidget class.

        Parameters:
            parent (obj): The parent object.
            position (str): The position of the menu relative to the parent widget. valid values are: 'right', 'left', 'top', 'bottom'
            child_width (int): The width of child widgets.
            child_height (int): The height of child widgets.
            max_child_width (int): The maximum allowed width of child widgets.
            drag_interaction (bool): Interact with the list while in the mouse drag state.
            **kwargs: Additional keyword arguments to pass to the widget.
        """
        super().__init__(parent)

        if position not in ["right", "left", "top", "bottom", "center"]:
            raise ValueError(
                "Invalid position. Must be 'right', 'left', 'top', 'bottom', or 'center'."
            )

        self.position = position
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.child_width = child_width
        self.child_height = child_height
        self.max_child_width = max_child_width
        self.drag_interaction = drag_interaction

        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self.gc_protect = []

        self.viewport().installEventFilter(self)
        self.set_attributes(**kwargs)

    def getItems(self):
        """Returns a list of items in the list widget."""
        return [self.item(i) for i in range(self.count())]

    def getItemsByText(self, text):
        """ """
        return [i for i in self.getItems() if i.text() == text]

    def getItemWidgets(self):
        """ """
        return [self.itemWidget(self.item(i)) for i in range(self.count())]

    def getItemWidgetsByText(self, text):
        """ """
        return [
            i for i in self.getItemWidgets() if hasattr(i, "text") and i.text() == text
        ]

    def setData(self, wItem, data, typ=QtCore.Qt.UserRole):
        """ """
        wItem.setData(typ, data)

    def getData(self, wItem, typ=QtCore.Qt.UserRole):
        """ """
        return wItem.data(typ)

    def addItem(self, item):
        """ """
        return self.add(item)

    def addItems(self, items):
        """ """
        return self.add(items)

    def add(self, x, data=None, **kwargs):
        """Add items to the menu.

        This method adds item(s) to the menu, either as a single item or multiple items from a collection.
        The added item can be a widget object or a string representation of a widget class name. If the input
        is a string, it creates a label and sets the input string as the label's text. Additional attributes for
        the widget can be passed as keyword arguments.

        Parameters:
            x (str/QWidget): Widget or string representation of a the widget.
            data (optional): Data to be associated with the added item(s).
            kwargs: Set attributes for the widget using keyword arguments.

        Returns:
            obj: The added item.

        Example call:
            menu().add('QAction', setText='My Item', insertSeparator=True)
        """
        if isinstance(x, dict):
            return [self.add(key, data=val, **kwargs) for key, val in x.items()]
        elif isinstance(x, (list, tuple, set)):
            if isinstance(data, (list, tuple, set)) and len(x) == len(data):
                return [self.add(item, data=d, **kwargs) for item, d in zip(x, data)]
            else:
                return [self.add(item, **kwargs) for item in x]

        try:  # get the widget from string class name.
            x = getattr(QtWidgets, x)(self)
            # ex. QtWidgets.QAction(self) object from string.
        except AttributeError:  # if x is a widget object instead of string.
            try:
                x = x()  # ex. QtWidgets.QAction(self) object.
            except TypeError:
                pass

        # if 'x' is still a string; create a label and use the str value as the label's text.
        if isinstance(x, str):
            label = QtWidgets.QLabel(self)
            label.setText(x)
            x = label

        wItem = QtWidgets.QListWidgetItem(self)
        x.setFixedHeight(self.child_height)
        wItem.setSizeHint(x.size())
        self.setItemWidget(wItem, x)
        self.setData(wItem, data)
        wItem.getData = lambda i=wItem: self.getData(i)
        x.installEventFilter(self)
        super().addItem(wItem)

        widget_width = x.geometry().width()
        if widget_width > self.child_width:
            self.child_width = min(widget_width, self.max_child_width)

        x.__class__.list = property(  # add an expandable list to the widget.
            lambda x: x.listWidget if hasattr(x, "listWidget") else self._addList(x)
        )

        # set any additional given keyword args for the widget.
        self.set_attributes(x, **kwargs)

        # set the list height to be exactly the hight of its combined children.
        new_list_height = (self.child_height) * self.count()
        self.resize(self.child_width, new_list_height)

        self.raise_()
        return x

    def _addList(self, widget):
        """Add an expanding list to the given widget.

        This method adds an expandable list to the given widget. The expanding list is created as a ListWidget
        object and is initially hidden.

        Parameters:
            widget (obj): Widget object to which the expandable list will be added.

        Returns:
            obj: The added ListWidget object.
        """
        listWidget = ListWidget(
            self.parent(),
            position=self.position,
            x_offset=self.x_offset,
            y_offset=self.y_offset,
            child_height=self.child_height,
            drag_interaction=self.drag_interaction,
            setVisible=False,
        )
        widget.listWidget = listWidget
        self.gc_protect.append(listWidget)

        # my_object = widget.listWidget
        # tracker.track(my_object)

        widget.listWidget.prev = self
        widget.listWidget.root = self
        while hasattr(widget.listWidget.root, "prev"):
            widget.listWidget.root = widget.listWidget.root.prev

        return widget.listWidget

    def _hideLists(self, listWidget, force=False):
        """Hide the given list and all previous lists in its hierarchy.

        This method hides the given list and all previous lists in its hierarchy, up to the point where the cursor
        is within the list's boundaries.

        Parameters:
            listWidget (obj): ListWidget object to start hiding from.
        """
        while hasattr(listWidget, "prev"):
            if (not force) and listWidget.rect().contains(
                listWidget.mapFromGlobal(QtGui.QCursor.pos())
            ):
                break
            listWidget.hide()
            listWidget = listWidget.prev

    def eventFilter(self, widget, event):
        if event.type() == QtCore.QEvent.Enter:
            try:
                widget.list.show()
                widget.updateGeometry()

                parent_list_width = self.width()
                parent_list_height = self.height()  # excluding window frame
                child_widget_width = widget.width()
                child_widget_height = widget.height()
                new_list_width = widget.list.width()  # excluding window frame
                new_list_height = widget.list.height()  # excluding window frame

                if self.position == "right":
                    pos = self.window().mapFromGlobal(
                        widget.mapToGlobal(
                            QtCore.QPoint(
                                parent_list_width - (self.x_offset + 12),
                                -child_widget_height // 2 + (self.y_offset - 2),
                            )
                        )
                    )

                elif self.position == "left":
                    pos = self.window().mapFromGlobal(
                        widget.mapToGlobal(
                            QtCore.QPoint(
                                -new_list_width + (self.x_offset - 8),
                                -child_widget_height // 2 + (self.y_offset - 2),
                            )
                        )
                    )

                elif self.position == "top":
                    pos = self.window().mapFromGlobal(
                        widget.mapToGlobal(
                            QtCore.QPoint(
                                -child_widget_width // 2 + (self.x_offset - 30),
                                -new_list_height + (self.y_offset - 8),
                            )
                        )
                    )

                elif self.position == "bottom":
                    pos = self.window().mapFromGlobal(
                        widget.mapToGlobal(
                            QtCore.QPoint(
                                -child_widget_width // 2 + (self.x_offset - 30),
                                parent_list_height - (self.y_offset + 30),
                            )
                        )
                    )

                elif self.position == "center":
                    pos = self.window().mapFromGlobal(
                        widget.mapToGlobal(
                            QtCore.QPoint(
                                parent_list_width // 2
                                - new_list_width // 2
                                + (self.x_offset - 30),
                                parent_list_height // 2
                                - new_list_height // 2
                                + (self.y_offset + 0),
                            )
                        )
                    )

                else:
                    raise ValueError(
                        "Invalid position value. Must be one of 'right', 'left', 'top', 'bottom'"
                    )

                widget.list.move(pos)
            except AttributeError:
                pass

        elif event.type() == QtCore.QEvent.MouseButtonRelease:
            if self.drag_interaction and widget.underMouse():
                try:
                    print(0, widget.listWidget.root)
                    # if not self == widget.listWidget.root:
                    try:
                        self.itemClicked.disconnect()
                    except RuntimeError:
                        pass
                    self.itemClicked.connect(widget.listWidget.root.itemClicked)
                    index = self.indexAt(
                        widget.pos()
                    )  # Get the index of the item that contains the widget.
                    wItem = self.item(index.row())  # Get the QListWidgetItem object.
                    self.itemClicked.emit(wItem)
                    self._hideLists(
                        widget.listWidget, force=True
                    )  # assure the child lists are hidden after mouse release.
                except AttributeError:
                    pass

        elif event.type() == QtCore.QEvent.MouseMove:
            # check if the mouse left the list widget
            if not self.rect().contains(self.mapFromGlobal(QtGui.QCursor.pos())):
                if hasattr(widget, "prev"):
                    self.hide()

        elif event.type() == QtCore.QEvent.Leave:
            try:
                if not widget.list.rect().contains(
                    widget.list.mapFromGlobal(QtGui.QCursor.pos())
                ):
                    if hasattr(widget, "listWidget"):
                        widget.listWidget.hide()
            except AttributeError:
                pass

        return super().eventFilter(widget, event)

    def leaveEvent(self, event):
        """ """
        self._hideLists(self)

        super().leaveEvent(event)

    def showEvent(self, event):
        """ """
        # Check if widget is a child list and if it has child widgets
        if hasattr(self, "prev") and not self.getItemWidgets():
            return
        super().showEvent(event)

    def convert(self, items, to="QLabel", **kwargs):
        """Converts the given items to a specified widget type.

        Parameters:
            items (list, tuple, set, dict): The items to convert.
            to (str): The widget type to convert the items to.
            **kwargs: Additional keyword arguments to pass to the widget.

        Example:
            self.convert(self.getItems(), 'QPushButton') #construct the list using the existing contents.
        """
        # assure 'x' is a list.
        lst = lambda x: list(x) if isinstance(x, (list, tuple, set, dict)) else [x]

        for item in lst(items):
            # get the row as an int from the items QModelIndex.
            i = self.indexFromItem(item).row()

            item = self.takeItem(i)
            self.add(to, setText=item.text(), **kwargs)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    window = QtWidgets.QMainWindow()
    lw = ListWidget(window)
    w1 = lw.add("QPushButton", setObjectName="b001", setText="Button 1")
    w1.list.add("list A")
    w2 = lw.add("QPushButton", setObjectName="b002", setText="Button 2")
    w3, w4 = w2.list.addItems(["List B1", "List B2"])
    w3.list.add("QPushButton", setObjectName="b004", setText="Button 4")
    lw.add("QPushButton", setObjectName="b003", setText="Button 3")

    print("\nlist widget items       :", lw.getItems())
    print("\nlist widget item widgets:", lw.getItemWidgets())

    window.resize(765, 255)
    window.show()
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


# def event(self, event):
#   """Handles events that are sent to the widget.

#   Parameters:
#       event (QtCore.QEvent): The event that was sent to the widget.

#   Returns:
#       bool: True if the event was handled, otherwise False.

#   Notes:
#       This method is called automatically by Qt when an event is sent to the widget.
#       If the event is a `QEvent.ChildPolished` event, it calls the `on_child_polished`
#       method with the child widget as an argument. Otherwise, it calls the superclass
#       implementation of `event`.
#   """
#   if event.type() == QtCore.QEvent.HoverMove:
#       print ('event_hoverMoveEvent'.ljust(25), self.mouseGrabber())
#       # window = QtWidgets.QApplication.activeWindow()
#       # if window and not self.rect().contains(self.mapFromGlobal(QtGui.QCursor.pos())):
#       #   if window.mouseGrabber() == self:
#       #       self.releaseMouse()

#   elif event.type() == QtCore.QEvent.HoverLeave:
#       print ('event_hoverLeaveEvent'.ljust(25), self.mouseGrabber())
#       # window = QtWidgets.QApplication.activeWindow()
#       # if window and not self.rect().contains(self.mapFromGlobal(QtGui.QCursor.pos())):
#           # if window.mouseGrabber() == self:
#       self.releaseMouse()

#   return super().event(event)
