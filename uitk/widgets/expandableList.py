# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtGui, QtWidgets
from uitk.widgets.mixins.attributes import AttributesMixin


class ExpandableList(QtWidgets.QWidget, AttributesMixin):
    """A QWidget subclass that adds functionality for adding and getting items, and for expanding and hiding sub-lists."""

    on_item_added = QtCore.Signal(object)
    on_item_interacted = QtCore.Signal(object)

    def __init__(
        self,
        parent=None,
        position="right",
        min_item_height=18,
        max_item_height=21,
        sublist_x_offset=0,
        sublist_y_offset=0,
        **kwargs,
    ):
        super().__init__(parent)
        if position not in ["right", "left", "top", "bottom", "center"]:
            raise ValueError(
                "Invalid position. Must be 'right', 'left', 'top', 'bottom', or 'center'."
            )
        self.position = position
        self.min_item_height = min_item_height
        self.max_item_height = max_item_height
        self.sublist_x_offset = sublist_x_offset
        self.sublist_y_offset = sublist_y_offset
        self.kwargs = kwargs

        self.widget_data = {}
        self.is_initialized = False

        # Create a new layout with no margins
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

        self.installEventFilter(self)
        # self.setMinimumWidth(100)
        self.set_attributes(**kwargs)

    def get_items(self):
        """Get all items in the list and its sublists.

        This method returns a list of all items in the list, including items in any sublists.

        Returns:
            list: A list of all items in the list and its sublists.
        """
        items = [self.layout.itemAt(i).widget() for i in range(self.layout.count())]
        for item in items:
            if hasattr(item, "sublist"):
                items.extend(item.sublist.get_items())
        return items

    def get_item_data(self, widget):
        """Get data associated with a widget in the list or its sublists.

        This method returns the data associated with a widget in the list or its sublists. If the widget is not found, it returns None.

        Parameters:
            widget (QtWidgets.QWidget): The widget to get the data for.

        Returns:
            The data associated with the widget, or None if the widget is not found.
        """
        if widget in self.get_items():
            return self.widget_data.get(widget, None)
        else:
            return None

    def set_item_data(self, widget, data):
        """Set data associated with a widget in the list or its sublists.

        This method sets the data associated with a widget in the list or its sublists. If the widget is not found, it does nothing.

        Parameters:
            widget (QtWidgets.QWidget): The widget to set the data for.
            data: The data to associate with the widget.
        """
        if widget in self.get_items():
            self.widget_data[widget] = data

    def add(self, x, data=None, **kwargs):
        """ """
        if isinstance(x, dict):
            return [self.add(key, data=val, **kwargs) for key, val in x.items()]

        elif isinstance(x, (list, tuple, set)):
            return [self.add(item, **kwargs) for item in x]

        elif isinstance(x, map):
            return [self.add(item, **kwargs) for item in list(x)]

        # get the widget from the value passed to x
        if isinstance(x, str):
            try:
                widget = getattr(QtWidgets, x)(self)
            except (AttributeError, TypeError):
                widget = QtWidgets.QLabel()
                widget.setText(x)

        elif isinstance(x, object):
            widget = x() if callable(x) else x

        else:
            raise TypeError(
                f"Unsupported item type: expected str, object, or a collection (list, tuple, set, map, dict), but got '{type(x)}'"
            )

        self.layout.addWidget(widget)
        self.on_item_added.emit(widget)

        self.set_item_data(widget, data)
        self._add_sublist(widget)

        if self.min_item_height is not None:
            widget.setMinimumHeight(self.min_item_height)
        if self.max_item_height is not None:
            widget.setMaximumHeight(self.max_item_height)

        self.set_attributes(widget, **kwargs)
        widget.installEventFilter(self)

        self.resize(self.sizeHint())

        self.layout.invalidate()

        return widget

    def _add_sublist(self, widget):
        """Add an expanding list to the given widget.

        This method adds an expandable list to the given widget. The expanding list is created as a ExpandableList
        object and is initially hidden.

        Parameters:
            widget (obj): Widget object to which the expandable list will be added.

        Returns:
            obj: The added ExpandableList object.
        """
        sublist = ExpandableList(
            self.parent(),
            position=self.position,
            min_item_height=self.min_item_height,
            max_item_height=self.max_item_height,
            sublist_x_offset=self.sublist_x_offset,
            sublist_y_offset=self.sublist_y_offset,
            **self.kwargs,  # Forward kwargs to the new ExpandableList
        )
        sublist.setVisible(False)

        # Connect the signals of the sublist to the signals of the parent list
        sublist.on_item_interacted.connect(self.on_item_interacted.emit)
        sublist.on_item_added.connect(self.on_item_added.emit)

        widget.sublist = sublist
        widget.sublist.parent_list = self
        widget.sublist.parent_item = widget
        # find the root list by iterating through its parent lists.
        widget.sublist.root_list = self
        while hasattr(widget.sublist.root_list, "parent_list"):
            widget.sublist.root_list = widget.sublist.root_list.parent_list

        return widget.sublist

    def _hide_sublists(self, sublist, force=False):
        """Hide the given list and all previous lists in its hierarchy.

        This method hides the given list and all previous lists in its hierarchy, up to the point where the cursor
        is within the list's boundaries.

        Parameters:
            sublist (obj): A sublist object to start hiding from.
        """
        while hasattr(sublist, "parent_list"):
            if (not force) and sublist.rect().contains(
                sublist.mapFromGlobal(QtGui.QCursor.pos())
            ):
                break
            sublist.hide()
            sublist = sublist.parent_list

    def get_padding(widget):
        """ """
        frame_geo = widget.frameGeometry()
        geo = widget.geometry()

        left_padding = geo.left() - frame_geo.left()
        right_padding = frame_geo.right() - geo.right()
        top_padding = geo.top() - frame_geo.top()
        bottom_padding = frame_geo.bottom() - geo.bottom()

        return (left_padding + right_padding, top_padding + bottom_padding)

    def sizeHint(self):
        """ """
        total_height = 0
        total_width = 0

        for i in range(self.layout.count()):
            widget = self.layout.itemAt(i).widget()
            if widget:
                total_height += widget.sizeHint().height() + self.layout.spacing()
                total_width = max(total_width, widget.sizeHint().width())

        # Adjust for layout's top and bottom margins
        total_height += (
            self.layout.contentsMargins().top() + self.layout.contentsMargins().bottom()
        )

        # Adjust for layout's left and right margins for width
        total_width += (
            self.layout.contentsMargins().left() + self.layout.contentsMargins().right()
        )

        return QtCore.QSize(total_width, total_height)

    def eventFilter(self, widget, event):
        """ """
        if event.type() == QtCore.QEvent.Enter:
            try:
                if widget.sublist.get_items():
                    widget.sublist.show()

                widget.updateGeometry()

                parent_list_width = self.width()
                parent_list_height = self.height()  # excluding window frame
                child_widget_width = widget.width()
                # child_widget_height = widget.height()
                new_list_width = widget.sublist.width()  # excluding window frame
                new_list_height = widget.sublist.height()  # excluding window frame

                padding_x, padding_y = self.get_padding()  # get the padding
                overlap = 1  # overlap value

                # dictionary for x and y coordinates
                pos_dict = {
                    "right": (
                        parent_list_width - overlap + self.sublist_x_offset,
                        self.sublist_y_offset,
                    ),
                    "left": (
                        -new_list_width + overlap + self.sublist_x_offset,
                        self.sublist_y_offset,
                    ),
                    "top": (
                        -child_widget_width // 2 + self.sublist_x_offset,
                        -new_list_height + overlap + self.sublist_y_offset,
                    ),
                    "bottom": (
                        -child_widget_width // 2 + self.sublist_x_offset,
                        parent_list_height - overlap + self.sublist_y_offset,
                    ),
                    "center": (
                        parent_list_width // 2
                        - new_list_width // 2
                        + self.sublist_x_offset,
                        parent_list_height // 2
                        - new_list_height // 2
                        + self.sublist_y_offset,
                    ),
                }

                pos = self.window().mapFromGlobal(
                    widget.mapToGlobal(
                        QtCore.QPoint(
                            pos_dict[self.position][0],  # x coordinate
                            pos_dict[self.position][1],  # y coordinate
                        )
                    )
                )
                widget.sublist.move(pos)

            except AttributeError:
                pass

        elif event.type() == QtCore.QEvent.MouseButtonRelease:
            # Check if widget is a child of this ExpandableList
            if widget in self.get_items():
                self.on_item_interacted.emit(widget)

        elif event.type() == QtCore.QEvent.MouseMove:
            # check if the mouse left the list widget
            if not self.rect().contains(self.mapFromGlobal(QtGui.QCursor.pos())):
                if hasattr(widget, "parent_list"):
                    self.hide()

        elif event.type() == QtCore.QEvent.Leave:
            try:
                if not widget.sublist.rect().contains(
                    widget.sublist.mapFromGlobal(QtGui.QCursor.pos())
                ):
                    if hasattr(widget, "sublist"):
                        widget.sublist.hide()
            except AttributeError:
                pass

        return super().eventFilter(widget, event)

    def leaveEvent(self, event):
        """ """
        self._hide_sublists(self)

        super().leaveEvent(event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    window = QtWidgets.QMainWindow()
    lw = ExpandableList(
        window, setMinimumWidth=120, min_item_height=21, sublist_x_offset=-1
    )
    w1 = lw.add("QPushButton", setObjectName="b001", setText="Button 1")
    w1.sublist.add("list A")
    w2 = lw.add("Label 1")
    w3, w4 = w2.sublist.add(["Label 2", "Label 3"])
    w3.sublist.add("QPushButton", setObjectName="b004", setText="Button 4")
    lw.add("QPushButton", setObjectName="b003", setText="Button 3")

    print("\nitems:", lw.get_items())

    lw.on_item_interacted.connect(lambda x: print(x))

    from uitk.widgets.mixins.style_sheet import StyleSheetMixin

    StyleSheetMixin().set_style(widget=lw.get_items(), theme="dark")

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
