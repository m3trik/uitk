# !/usr/bin/python
# coding=utf-8
import inspect
from typing import Optional, Union
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk
from uitk.widgets.optionBox import OptionBox
from uitk.widgets.header import Header
from uitk.widgets.mixins.style_sheet import StyleSheet
from uitk.widgets.mixins.attributes import AttributesMixin


class Menu(QtWidgets.QWidget, AttributesMixin):
    """A custom Qt Widget that serves as a menu with additional features.

    The Menu class inherits from QtWidgets.QWidget and mixes in AttributesMixin and StyleSheet.
    It provides a customizable menu with features such as draggable headers and apply buttons.
    The menu can be positioned relative to the cursor, a specific coordinate, a widget, or its parent.

    Attributes:
        on_item_added (QtCore.Signal): Signal emitted when an item is added to the menu.
        on_item_interacted (QtCore.Signal): Signal emitted when an item in the menu is interacted with.
    """

    on_item_added = QtCore.Signal(object)
    on_item_interacted = QtCore.Signal(object)

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        name: Optional[str] = None,
        mode: Optional[str] = None,
        position: Union[str, QtCore.QPoint, list, tuple, None] = "cursorPos",
        min_item_height: Optional[int] = None,
        max_item_height: Optional[int] = None,
        fixed_item_height: Optional[int] = None,
        add_header: bool = True,
        **kwargs,
    ):
        """Initializes a custom qwidget instance that acts as a menu.

        The menu can be positioned relative to the cursor, a specific coordinate, a widget, or its parent.
        It can also have a draggable header and an apply button.
        The menu can be styled using the provided keyword arguments.
        The menu can be set to different modes: 'context', 'option', or 'popup'.

        Parameters:
            parent (QtWidgets.QWidget, optional): The parent widget. Defaults to None.
            name (str, optional): The name of the menu. Defaults to None.
            mode (str, optional): Possible values include: 'context', 'option', and 'popup'.
            position (str, optional): The position of the menu. Can be "right", "cursorPos", a coordinate pair, or a widget.
            min_item_height (int, optional): The minimum height of items in the menu. Defaults to None.
            max_item_height (int, optional): The maximum height of items in the menu. Defaults to None.
            fixed_item_height (int, optional): The fixed height of items in the menu. Defaults to None.
            add_header (bool, optional): Whether to add a draggable  to the menu. Defaults to True.
            **kwargs: Additional keyword arguments to set attributes on the menu.

        Example:
                menu = Menu(parent=parent_widget, name="MyMenu", mode="context", position="cursorPos")
                menu.add("QLabel", setText="Label A")
                menu.add("QPushButton", setText="Button A")
                menu.show()
        """
        super().__init__(parent)

        if name is not None:
            if not isinstance(name, str):
                raise TypeError(f"Expected 'name' to be a string, got {type(name)}")
            self.setObjectName(name)

        self.mode = mode
        self.position = position
        self.min_item_height = min_item_height
        self.max_item_height = max_item_height
        self.fixed_item_height = fixed_item_height
        self.add_header = add_header
        self.kwargs = kwargs
        self.widget_data = {}
        self.prevent_hide = False
        self.option_box = None

        self.style = StyleSheet(self, log_level="WARNING")

        self.setProperty("class", "translucentBgWithBorder")
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.setMinimumWidth(147)

        self.init_layout()

        self.installEventFilter(self)
        if self.parent():
            self.parent().installEventFilter(self)
        self.set_attributes(**kwargs)

    def setCentralWidget(self, widget, overwrite=False):
        if not overwrite and getattr(self, "_central_widget", None) is widget:
            return  # skip if same

        current_central_widget = getattr(self, "_central_widget", None)
        if current_central_widget and current_central_widget is not widget:
            current_central_widget.setParent(None)  # Avoid deleteLater()

        self._central_widget = widget
        self._central_widget.setProperty("class", "centralWidget")
        self.layout.addWidget(self._central_widget)

    def centralWidget(self):
        """Return the central widget."""
        return self._central_widget

    def init_layout(self):
        """ """
        # Create a new layout with no margins
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(1)
        self.setLayout(self.layout)

        # Create a central widget and set it to the layout
        self.setCentralWidget(QtWidgets.QWidget(self))

        # Create a QVBoxLayout inside the central widget
        self.centralWidgetLayout = QtWidgets.QVBoxLayout(self._central_widget)
        self.centralWidgetLayout.setContentsMargins(2, 2, 2, 2)
        self.centralWidgetLayout.setSpacing(1)

        # Create a form layout inside the QVBoxLayout
        self.gridLayout = QtWidgets.QGridLayout()
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(1)

        if self.add_header:
            # Create Header instance and add it to the central widget layout
            self.header = Header(self, hide_button=True)
            self.centralWidgetLayout.addWidget(self.header)

        # Add grid layout to the central widget layout
        self.centralWidgetLayout.addLayout(self.gridLayout)

    def get_all_children(self):
        children = self.findChildren(QtWidgets.QWidget)
        return children

    @property
    def contains_items(self):
        """Check if the QMenu contains any items."""
        return bool(self.gridLayout.count())

    @ptk.cached_property
    def apply_button(self):
        """Property that returns an apply button."""
        if not self.parent():
            return None

        button = QtWidgets.QPushButton("Apply")
        button.setToolTip("Execute the command.")
        button.released.connect(lambda: self.parent().clicked.emit())
        button.setFixedHeight(26)
        button.hide()

        return button

    def title(self):
        """ """
        self.header.text()

    def setTitle(self, title="") -> None:
        """Set the menu's title to the given string.
        If no title is given, the function will attempt to use the menu parents text.

        Parameters:
            title (str): Text to apply to the menu's .
        """
        self.header.setText(title)

    def get_items(self, types=None):
        """Get all items in the list, optionally filtered by type.

        Parameters:
            types (str, type, list of str, list of type, optional): The type(s) or type name(s) of widgets to retrieve. Defaults to None.

        Returns:
            list: A list of all QWidget items in the list, filtered by type if specified.
        """
        items = [
            self.gridLayout.itemAt(i).widget() for i in range(self.gridLayout.count())
        ]

        if types is not None:
            # Ensure types is a list for easier processing
            if not isinstance(types, (list, tuple)):
                types = [types]

            # Convert string type names to actual types
            processed_types = []
            for type_item in types:
                if isinstance(type_item, str):
                    widget_type = getattr(QtWidgets, type_item, None)
                    if widget_type is not None:
                        processed_types.append(widget_type)
                else:
                    processed_types.append(type_item)

            items = [  # Filter items by type
                item
                for item in items
                if any(isinstance(item, t) for t in processed_types)
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
            widget/list: The added widget or list of added widgets.
        """
        if isinstance(x, dict):
            return [self.add(key, data=val, **kwargs) for key, val in x.items()]

        elif isinstance(x, (list, tuple, set)):
            return [self.add(item, **kwargs) for item in x]

        elif isinstance(x, zip):
            return [self.add(item, data, **kwargs) for item, data in x]

        elif isinstance(x, map):
            return [self.add(item, **kwargs) for item in list(x)]

        elif isinstance(x, QtWidgets.QAction):
            return self._add_action_widget(
                x, row=row, col=col, rowSpan=rowSpan, colSpan=colSpan
            )

        elif isinstance(x, str):
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
                f"Unsupported item type: expected str, QWidget, QAction, or a collection (list, tuple, set, dict, zip, map), got '{type(x)}'"
            )

        widget.item_text = lambda i=widget: self.get_item_text(i)
        widget.item_data = lambda i=widget: self.get_item_data(i)

        if row is None:
            row = 0
            while self.gridLayout.itemAtPosition(row, col) is not None:
                row += 1

        if colSpan is None:
            colSpan = self.gridLayout.columnCount() or 1

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
        setattr(self, widget.objectName(), widget)

        self.resize(self.sizeHint())
        self.layout.invalidate()

        return widget

    def _add_action_widget(
        self,
        action: QtWidgets.QAction,
        row: Optional[int] = None,
        col: int = 0,
        rowSpan: int = 1,
        colSpan: Optional[int] = None,
    ) -> Optional[QtWidgets.QWidget]:
        temp_menu = QtWidgets.QMenu(self)
        temp_menu.addAction(action)

        temp_menu.ensurePolished()
        temp_menu.show()
        QtWidgets.QApplication.processEvents()

        widget = temp_menu.widgetForAction(action)
        if not widget:
            temp_menu.hide()
            temp_menu.deleteLater()
            return None

        widget.setParent(self)
        temp_menu.hide()
        temp_menu.deleteLater()

        if row is None:
            row = 0
            while self.gridLayout.itemAtPosition(row, col):
                row += 1
        if colSpan is None:
            colSpan = self.gridLayout.columnCount() or 1

        self.gridLayout.addWidget(widget, row, col, rowSpan, colSpan)
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

    def create_option_box(self):
        """ """
        self.option_box = OptionBox()
        self.option_box.menu = self
        self.option_box.wrap(self.parent())

    def center_on_cursor_position(self):
        """ """
        pos = QtGui.QCursor.pos()  # global position
        center = QtCore.QPoint(
            pos.x() - (self.width() / 2), pos.y() - (self.height() / 4)
        )
        self.move(center)  # center on cursor position.

    def is_position_a_coordinate(self):
        """ """
        return isinstance(self.position, (tuple, list, set, QtCore.QPoint))

    def move_to_coordinate(self):
        """ """
        if not isinstance(self.position, QtCore.QPoint):
            self.position = QtCore.QPoint(self.position[0], self.position[1])
        self.move(self.position)

    def is_position_a_widget(self):
        """ """
        return not isinstance(self.position, (type(None), str))

    def move_to_widget_position(self):
        """ """
        pos = getattr(self.positionRelativeTo.rect(), self.position)
        self.move(self.positionRelativeTo.mapToGlobal(pos()))

    @staticmethod
    def position_widget_relative_to_parent(parent, widget, position):
        """ """
        # Get dimensions of the parent and the widget
        parent_width = parent.width()
        parent_height = parent.height()
        widget_width = widget.width()
        widget_height = widget.height()

        pos_dict = {  # Define position options
            "right": (
                parent_width,  # x coordinate
                parent_height // 2 - widget_height // 2,  # y coordinate
            ),
            "left": (
                -widget_width,  # x coordinate
                parent_height // 2 - widget_height // 2,  # y coordinate
            ),
            "top": (
                parent_width // 2 - widget_width // 2,  # x coordinate
                -widget_height,  # y coordinate
            ),
            "bottom": (
                parent_width // 2 - widget_width // 2,  # x coordinate
                parent_height,  # y coordinate
            ),
            "center": (
                parent_width // 2 - widget_width // 2,  # x coordinate
                parent_height // 2 - widget_height // 2,  # y coordinate
            ),
        }

        # If the position is not one of the options, raise an error
        if position not in pos_dict:
            raise ValueError(f"Invalid position: {position}")

        # Get the global position of the parent widget
        global_pos = parent.mapToGlobal(QtCore.QPoint(0, 0))
        # Add the local coordinates of the new position
        new_pos = global_pos + QtCore.QPoint(*pos_dict[position])
        widget.move(new_pos)

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

    def setVisible(self, visible) -> None:
        """Called every time the widget is shown or hidden on screen."""
        if self.prevent_hide:
            return

        if visible and self.contains_items:
            super().setVisible(True)
        else:
            super().setVisible(False)

    def showEvent(self, event) -> None:
        """ """
        # set menu position
        if self.position == "cursorPos":
            self.center_on_cursor_position()
        elif self.is_position_a_coordinate():
            self.move_to_coordinate()
        elif self.is_position_a_widget():
            self.move_to_widget_position()
        elif self.parent():
            self.position_widget_relative_to_parent(self.parent(), self, self.position)

        super().showEvent(event)

    def eventFilter(self, widget, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if widget is self.parent():
                if (
                    self.mode == "context" and event.button() == QtCore.Qt.RightButton
                ) or (self.mode == "popup" and event.button() == QtCore.Qt.LeftButton):
                    self.setVisible(not self.isVisible())

        elif event.type() == QtCore.QEvent.Show:
            if widget is self.parent() and self.contains_items:
                if self.mode == "option":
                    # Add apply button to the central widget layout
                    if hasattr(self.parent(), "clicked"):
                        self.centralWidgetLayout.addWidget(self.apply_button)
                        self.apply_button.show()
                    if self.option_box is None:
                        self.create_option_box()

        elif event.type() == QtCore.QEvent.MouseButtonRelease:
            if widget in self.get_items():
                self.on_item_interacted.emit(widget)

        return super().eventFilter(widget, event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    menu = Menu(position="cursorPos", setTitle="Drag Me")

    # Grid layout example
    # a = menu.add(["Label A", "Label B"])
    a = menu.add("Label A")
    b = menu.add("Label B")
    c = menu.add("QDoubleSpinBox", set_by_value=1.0, row=0, col=1)
    d = menu.add("QDoubleSpinBox", set_by_value=2.0, row=1, col=1)

    menu.on_item_interacted.connect(lambda x: print(x))

    menu.style.set(theme="dark")

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
