# !/usr/bin/python
# coding=utf-8
import inspect
from PySide2 import QtCore, QtGui, QtWidgets
from pythontk import cached_property
from uitk.widgets.draggableHeader import DraggableHeader
from uitk.widgets.mixins.attributes import AttributesMixin


class Menu(QtWidgets.QWidget, AttributesMixin):
    """ """

    on_item_added = QtCore.Signal(object)
    on_item_interacted = QtCore.Signal(object)

    def __init__(
        self,
        parent=None,
        position="right",
        min_item_height=None,
        max_item_height=None,
        fixed_item_height=None,
        **kwargs,
    ):
        super().__init__(parent)

        self.position = position
        self.min_item_height = min_item_height
        self.max_item_height = max_item_height
        self.fixed_item_height = fixed_item_height
        self.kwargs = kwargs
        self.widget_data = {}
        self.prevent_hide = False

        self.setProperty("class", "translucentBgWithBorder")
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

        # Create a new layout with no margins
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(1)

        self.init_default_layout()
        self.setLayout(self.layout)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

        self.installEventFilter(self)
        self.set_attributes(**kwargs)

    def setCentralWidget(self, widget):
        """Set a widget as the central widget, replacing the current one."""
        current_central_widget = getattr(self, "_central_widget", None)
        if current_central_widget:
            current_central_widget.deleteLater()  # delete the current central widget
        self._central_widget = widget  # set the new central widget
        self._central_widget.setProperty("class", "centralWidget")  # for stylesheet
        self.layout.addWidget(self._central_widget)  # add it to the layout

    def centralWidget(self):
        """Return the central widget."""
        return self._central_widget

    def init_default_layout(self):
        """ """
        # Create a central widget and set it to the layout
        self.setCentralWidget(QtWidgets.QWidget(self))

        # Create a QVBoxLayout inside the central widget
        self.centralWidgetLayout = QtWidgets.QVBoxLayout(self._central_widget)
        self.centralWidgetLayout.setContentsMargins(12, 12, 12, 12)
        self.centralWidgetLayout.setSpacing(1)

        # Create a form layout inside the QVBoxLayout
        self.gridLayout = QtWidgets.QGridLayout()
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(1)

        # Create DraggableHeader instance and add it to the central widget layout
        self.draggable_header = DraggableHeader(self)
        self.centralWidgetLayout.addWidget(self.draggable_header)

        # Add grid layout to the central widget layout
        self.centralWidgetLayout.addLayout(self.gridLayout)

        # Add apply button to the central widget layout
        self.centralWidgetLayout.addWidget(self.apply_button)

    def get_all_children(self):
        children = self.findChildren(QtWidgets.QWidget)
        return children

    @property
    def contains_items(self):
        """Check if the QMenu contains any items."""
        return bool(self.gridLayout.count())

    @cached_property
    def apply_button(self):
        """Property that returns an apply button."""
        if not self.parent():
            return None

        button = QtWidgets.QPushButton("Apply")
        button.setToolTip("Execute the command.")
        button.released.connect(lambda: self.parent().clicked.emit())
        button.setMinimumSize(119, 26)
        button.hide()

        return button

    def title(self):
        """ """
        self.draggable_header.text()

    def setTitle(self, title="") -> None:
        """Set the menu's title to the given string.
        If no title is given, the function will attempt to use the menu parents text.

        Parameters:
            title (str): Text to apply to the menu's header.
        """
        if not title:
            try:
                title = self.parent().text()
            except AttributeError:
                try:
                    title = self.parent().currentText()
                except AttributeError:
                    pass
            if title:
                title = title.upper()

        self.draggable_header.setText(title)

    def get_items(self):
        """Get all items in the list.

        Returns:
            list: A list of all QWidget items in the list.
        """
        items = [
            self.gridLayout.itemAt(i).widget() for i in range(self.gridLayout.count())
        ]

        return items

    def get_item(self, identifier):
        """Return a QAction or QWidgetAction by index or text.

        Parameters:
            identifier (int or str): If an int, treats it as an index. If a str, treats it as the text of the item.

        Raises:
            ValueError: If the identifier is not an integer (index) or string (text).

        Returns:
            QAction or QWidgetAction: The item found by the identifier.
        """
        items = self.get_items()

        if isinstance(identifier, int):  # get by index
            if identifier < 0 or identifier >= len(items):
                raise ValueError("Index out of range.")
            item = items[identifier]
        elif isinstance(identifier, str):  # get by text
            for i in items:
                if i.text() == identifier:
                    item = i
                    break
            else:
                raise ValueError("No item found with the given text.")
        else:
            raise ValueError(
                f"Expected an integer (index) or string (text), got '{type(identifier)}'"
            )

        return item

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

    def set_item_data(self, widget, data):
        """Set data associated with a widget in the list or its sublists.

        This method sets the data associated with a widget in the list. If the widget is not found, it does nothing.

        Parameters:
            widget (QtWidgets.QWidget): The widget to set the data for.
            data: The data to associate with the widget.
        """
        if widget in self.get_items():
            self.widget_data[widget] = data

    def remove_widget(self, widget):
        """Remove a widget from the layout."""
        self.gridLayout.removeWidget(widget)
        if widget in self.widget_data:
            del self.widget_data[widget]

    def clear(self):
        """Clear all items in the list."""
        # We're going backwards to avoid index errors.
        for i in reversed(range(self.gridLayout.count())):
            widget = self.gridLayout.itemAt(i).widget()
            if widget:
                self.gridLayout.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # Reset the widget_data dictionary
        self.widget_data = {}

    def add(self, x, data=None, row=None, col=0, rowSpan=1, colSpan=None, **kwargs):
        """Add an item or multiple items to the list.

        The function accepts a string, an object, or a collection of items (a dictionary, list, tuple, set, or map).

        Parameters:
            x (str, object, dict, list, tuple, set, map): The item or items to add.
            data: Data to associate with the added item or items. Default is None.
            row (int): The row index at which to add the widget. Default is the last row.
            col (int): The column index at which to add the widget. Default is 0.
            rowSpan (int): The number of rows the widget should span. Default is 1.
            colSpan (int): The number of columns the widget should span. Default is the total number of columns.
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

        elif isinstance(x, QtWidgets.QWidget) or (
            inspect.isclass(x) and issubclass(x, QtWidgets.QWidget)
        ):
            widget = x(self) if callable(x) else x

        else:
            raise TypeError(
                f"Unsupported item type: expected str, QWidget, a subclass of QWidget, or a collection (list, tuple, set, map, dict), but got '{type(x)}'"
            )

        widget.item_text = lambda i=widget: self.get_item_text(i)
        widget.item_data = lambda i=widget: self.get_item_data(i)

        # If no position is specified, place the widget at the last row and first column
        if row is None:
            row = 0
            while self.gridLayout.itemAtPosition(row, col) is not None:
                row += 1

        # If no span is specified, make the widget span across all columns
        if colSpan is None:
            colSpan = self.gridLayout.columnCount()

        self.gridLayout.addWidget(widget, row, col, rowSpan, colSpan)
        self.on_item_added.emit(widget)

        self.set_item_data(widget, data)

        if self.min_item_height is not None:
            widget.setMinimumHeight(self.min_item_height)
        if self.max_item_height is not None:
            widget.setMaximumHeight(self.max_item_height)
        if self.fixed_item_height is not None:
            widget.setFixedHeight(self.fixed_item_height)

        self.set_attributes(widget, **kwargs)
        widget.installEventFilter(self)
        # Add the widget as a menu attribute
        setattr(self, widget.objectName(), widget)

        self.resize(self.sizeHint())
        self.layout.invalidate()

        return widget

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
        if event.type() == QtCore.QEvent.MouseButtonRelease:
            # Check if widget is a child of this ExpandableList
            if widget in self.get_items():
                self.on_item_interacted.emit(widget)

        return super().eventFilter(widget, event)

    def setVisible(self, state) -> None:
        """Called every time the widget is shown or hidden on screen."""
        if self.prevent_hide:  # invisible
            return

        super().setVisible(state)

    def showEvent(self, event) -> None:
        # set menu position
        if self.position == "cursorPos":
            self.center_on_cursor_position()
        elif self.is_position_a_coordinate():
            self.move_to_coordinate()
        elif self.is_position_a_widget():
            self.move_to_widget_position()
        elif self.parent():
            self.move_relative_to_parent()

        if not self.title():
            self.setTitle()

        if isinstance(self.parent(), QtWidgets.QPushButton):
            self.apply_button.show()

        super().showEvent(event)

    def center_on_cursor_position(self):
        pos = QtGui.QCursor.pos()  # global position
        center = QtCore.QPoint(
            pos.x() - (self.width() / 2), pos.y() - (self.height() / 4)
        )
        self.move(center)  # center on cursor position.

    def is_position_a_coordinate(self):
        return isinstance(self.position, (tuple, list, set, QtCore.QPoint))

    def move_to_coordinate(self):
        if not isinstance(self.position, QtCore.QPoint):
            self.position = QtCore.QPoint(self.position[0], self.position[1])
        self.move(self.position)

    def is_position_a_widget(self):
        return not isinstance(self.position, (type(None), str))

    def move_to_widget_position(self):
        pos = getattr(self.positionRelativeTo.rect(), self.position)
        self.move(self.positionRelativeTo.mapToGlobal(pos()))

    def move_relative_to_parent(self):
        pos = getattr(
            self.parent().rect(),
            self.position if not self.position == "cursorPos" else "bottomLeft",
        )
        pos = self.parent().mapToGlobal(pos())
        self.move(pos)

    def hide_on_leave(self) -> None:
        """Hides the menu if the cursor is not within the menu's boundaries when the timer times out.
        This method is connected to the menu_timer's timeout signal.
        """
        if not self.rect().contains(QtGui.QCursor.pos()):
            self.hide()

    def leaveEvent(self, event) -> None:
        """ """
        self.hide()

        super().leaveEvent(event)

    def hide(self, force=False) -> None:
        """Sets the widget as invisible.
        Prevents hide event under certain circumstances.

        Parameters:
            force (bool): override prevent_hide.
        """
        if force or not self.prevent_hide:
            for w in self.get_items():
                try:
                    if w.view().isVisible():  # comboBox menu open.
                        return
                except AttributeError:
                    pass

            super().hide()


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # # grid layout example
    menu = Menu(position="cursorPos", setTitle="Drag Me")
    print(menu)
    # a = menu.add(["Label A", "Label B"])
    a = menu.add("Label A")
    b = menu.add("Label B")
    c = menu.add("QDoubleSpinBox", set_spinbox_by_value=1.0, row=0, col=1)
    d = menu.add("QDoubleSpinBox", set_spinbox_by_value=2.0, row=1, col=1)

    menu.on_item_interacted.connect(lambda x: print(x))

    from uitk.widgets.mixins.style_sheet import StyleSheet

    StyleSheet().set_style(widget=menu, theme="dark")

    menu.show()
    print(menu.get_items())
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

# depricated:

# def hide(self, force=False):
#   '''Sets the widget as invisible.
#   Prevents hide event under certain circumstances.

#   Parameters:
#       force (bool): override prevent_hide.
#   '''
#   if force or not self.prevent_hide:

#       for w in self.get_items():
#           try:
#               if w.view().isVisible(): #comboBox menu open.
#                   return
#           except AttributeError as error:
#               pass

#       super().hide()


# def show(self):
#   '''Show the menu.
#   '''
#   if not self.contains_items: #prevent show if the menu is empty.
#       return

#   if not self.title():
#           self.setTitle()

#   if hasattr(self.parent(), 'released') and not self.parent().objectName()=='draggable_header':
#       # print (f'show menu | title: {self.title()} | {self.parent().objectName()} has attr released.') #debug
#       self.applyButton.show()

#   checkboxes = self.get_items(inc=['QCheckBox'])
#   if checkboxes: #returns None if the menu doesn't contain checkboxes.
#       self.toggleAllButton.show()

#   super().show()


# def showEvent(self, event):
#   '''
#   Parameters:
#       event = <QEvent>
#   '''
#   self.resize(self.sizeHint().width(), self.sizeHint().height()+10) #self.setMinimumSize(width, self.sizeHint().height()+5)
#   get_center = lambda w, p: QtCore.QPoint(p.x()-(w.width()/2), p.y()-(w.height()/4)) #get widget center position.

#   #set menu position
#   if self.position=='cursorPos':
#       pos = QtGui.QCursor.pos() #global position
#       self.move(get_center(self, pos)) #move to cursor position.

#   elif not isinstance(self.position, (type(None), str)): #if a widget is passed to 'position' (move to the widget's position).
#       pos = getattr(self.positionRelativeTo.rect(), self.position)
#       self.move(self.positionRelativeTo.mapToGlobal(pos()))

#   elif self.parent(): #if parent: map relative to parent.
#       pos = getattr(self.parent().rect(), self.position if not self.position=='cursorPos' else 'bottomLeft')
#       pos = self.parent().mapToGlobal(pos())
#       self.move(pos) # self.move(get_center(self, pos))

#   QtWidgets.QMenu.showEvent(self, event)
