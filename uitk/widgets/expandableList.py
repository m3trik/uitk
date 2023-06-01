# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtGui, QtWidgets
from uitk.widgets.mixins.attributes import AttributesMixin


class ExpandableList(QtWidgets.QWidget, AttributesMixin):
    """A subclass of QWidget that represents a list of widgets, each potentially having an expandable sublist.

    ExpandableList is a versatile QWidget subclass that manages a collection of widgets. Each widget in the list can be associated
    with data, can have its own sublist of widgets, and can emit signals when it is interacted with or when a new widget is added.

    The ExpandableList can be positioned relative to its parent widget, and each widget in the list can be assigned minimum, maximum,
    or fixed height parameters.

    Signals:
        on_item_added: Emitted when an item is added to the list or any sublist. The new widget is passed as the argument.
        on_item_interacted: Emitted when an item in the list or any sublist is clicked. The interacted widget is passed as the argument.

    Attributes:
        position (str): The relative position of the ExpandableList. Can be 'right', 'left', 'top', 'bottom', or 'center'.
        min_item_height (int): The minimum height for items in the list. If None, the minimum height is not set.
        max_item_height (int): The maximum height for items in the list. If None, the maximum height is not set.
        fixed_item_height (int): The fixed height for items in the list. If None, the height is not fixed.
        sublist_x_offset (int): The x offset for sublists.
        sublist_y_offset (int): The y offset for sublists.
        widget_data (dict): Dictionary mapping widgets to their associated data.
        kwargs: Any additional built in widget attributes can be defined here. ie. setMinimumWidth=120 or setVisible=False

    Example:
        expandable_list = ExpandableList(position='right', fixed_item_height=30)
        expandable_list.add('QPushButton', data='Button Data')
        expandable_list.add(['Item 1', 'Item 2'])
        button = QtWidgets.QPushButton()
        expandable_list.add(button, data='Another Button')

        # Connect to signals
        expandable_list.on_item_added.connect(my_item_added_func)
        expandable_list.on_item_interacted.connect(my_item_interacted_func)
    """

    on_item_added = QtCore.Signal(object)
    on_item_interacted = QtCore.Signal(object)

    def __init__(
        self,
        parent=None,
        position="right",
        min_item_height=None,
        max_item_height=None,
        fixed_item_height=None,
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
        self.fixed_item_height = fixed_item_height
        self.sublist_x_offset = sublist_x_offset
        self.sublist_y_offset = sublist_y_offset
        self.kwargs = kwargs

        self.widget_data = {}

        # Create a new layout with no margins
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0.5)
        self.setLayout(self.layout)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

        self.installEventFilter(self)
        self.set_attributes(**kwargs)

    def get_items(self):
        """Get all items in the list and its sublists.

        This method recursively retrieves all items from the list, including items from all nested sublists.

        Returns:
            list: A list of all QWidget items in the list and its sublists.
        """
        items = [self.layout.itemAt(i).widget() for i in range(self.layout.count())]
        for item in items:
            if hasattr(item, "sublist"):
                items.extend(item.sublist.get_items())
        return items

    def get_item_text(self, widget):
        """Get the textual representation of a widget.

        This method tries to retrieve the text attribute of the passed widget. If the widget does not possess a text attribute, it will return None.

        Parameters:
            widget (QtWidgets.QWidget): The widget for which to get the text.

        Returns:
            str: The text associated with the widget, or None if the widget does not have a text attribute.
        """
        try:
            return widget.text()
        except AttributeError:
            return None

    def get_parent_item_text(self, widget):
        """Get the text attribute of the parent item of a widget's sublist.

        This method attempts to retrieve the text attribute of the widget's parent item in the sublist. If the parent item does not exist or does not have a text attribute, it returns None.

        Parameters:
            widget (QtWidgets.QWidget): The widget for which to get the parent item's text.

        Returns:
            str: The text of the parent item, or None if the parent item does not exist or does not have a text attribute.
        """
        try:
            return widget.sublist.parent_list.parent_item.text()
        except AttributeError:
            return None

    def get_item_data(self, widget):
        """Get data associated with a widget in the list or its sublists.

        This method returns the data associated with the widget in the list or any sublist. If the widget is not found, it returns None.

        Parameters:
            widget (QtWidgets.QWidget): The widget to get the data for.

        Returns:
            Any: The data associated with the widget, or None if the widget is not found.
        """
        try:
            return self.widget_data.get(widget)
        except KeyError:
            return None

    def get_parent_item_data(self, widget):
        """Get the data associated with the parent item of a widget's sublist.

        This method attempts to retrieve the data associated with the widget's parent item in the sublist. If the parent item does not exist or does not have associated data, it returns None.

        Parameters:
            widget (QtWidgets.QWidget): The widget for which to get the parent item's data.

        Returns:
            Any: The data associated with the parent item, or None if the parent item does not exist or does not have associated data.
        """
        try:
            return self.widget_data.get(widget.sublist.parent_list.parent_item)
        except KeyError:
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

    def clear(self):
        """Clear all items in the list and its sublists.

        This method recursively removes all items from the list, including items from all nested sublists.
        """
        for i in reversed(
            range(self.layout.count())
        ):  # We're going backwards to avoid index errors.
            widget = self.layout.itemAt(i).widget()
            if widget:
                # If the widget has a sublist, clear it too
                if hasattr(widget, "sublist"):
                    widget.sublist.clear()

                self.layout.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # Reset the widget_data dictionary
        self.widget_data = {}

    def add(self, x, data=None, **kwargs):
        """Add an item or multiple items to the list or its sublists.

        The function accepts a string, an object, or a collection of items (a dictionary, list, tuple, set, or map).

        Parameters:
            x (str, object, dict, list, tuple, set, map): The item or items to add.
            data: Data to associate with the added item or items. Default is None.
            **kwargs: Additional arguments to set on the added item or items.

        Returns:
            widget: The added widget or list of added widgets.
        """
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

        elif isinstance(x, QtWidgets.QWidget):
            widget = x() if callable(x) else x

        else:
            raise TypeError(
                f"Unsupported item type: expected str, QWidget, or a collection (list, tuple, set, map, dict), but got '{type(x)}'"
            )

        widget.item_text = lambda i=widget: self.get_item_text(i)
        widget.item_data = lambda i=widget: self.get_item_data(i)
        widget.parent_item_text = lambda i=widget: self.get_parent_item_text(i)
        widget.parent_item_data = lambda i=widget: self.get_parent_item_data(i)

        self.layout.addWidget(widget)
        self.on_item_added.emit(widget)

        self.set_item_data(widget, data)
        self._add_sublist(widget)

        if self.min_item_height is not None:
            widget.setMinimumHeight(self.min_item_height)
        if self.max_item_height is not None:
            widget.setMaximumHeight(self.max_item_height)
        if self.fixed_item_height is not None:
            widget.setFixedHeight(self.fixed_item_height)

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
            fixed_item_height=self.fixed_item_height,
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
        widget.sublist.parent_item = widget  # Set the parent_item of the widget

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
        """Get the padding values around a widget.

        This method calculates the padding values (distance from content to frame boundary) for a widget in all four directions.

        Parameters:
            widget (obj): A widget object to get the padding values for.

        Returns:
            tuple: A tuple containing padding values (horizontal padding, vertical padding).
        """
        frame_geo = widget.frameGeometry()
        geo = widget.geometry()

        left_padding = geo.left() - frame_geo.left()
        right_padding = frame_geo.right() - geo.right()
        top_padding = geo.top() - frame_geo.top()
        bottom_padding = frame_geo.bottom() - geo.bottom()

        return (left_padding + right_padding, top_padding + bottom_padding)

    def sizeHint(self):
        """Return the recommended size for the widget.

        This method calculates the total size of the widgets contained in the layout of the ExpandableList, including margins and spacing.

        Returns:
            QtCore.QSize: The recommended size for the widget.
        """
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
        """Filter events for the ExpandableList.

        This method filters the events of the ExpandableList and its widgets, such as mouse movement and button presses.

        Parameters:
            widget (obj): The object that the event was sent to.
            event (obj): The event that occurred.

        Returns:
            bool: False if the event should be further processed, and True if the event should be ignored.
        """
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
        """Handle the event when the cursor leaves the ExpandableList.

        This method hides all sublists when the cursor leaves the ExpandableList.

        Parameters:
            event (obj): The event that occurred.
        """
        self._hide_sublists(self)

        super().leaveEvent(event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    window = QtWidgets.QMainWindow()
    lw = ExpandableList(
        window, setMinimumWidth=120, fixed_item_height=21, sublist_x_offset=-1
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
