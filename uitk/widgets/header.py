# !/usr/bin/python
# coding=utf-8
from qtpy import QtCore, QtGui, QtWidgets
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay


class Header(QtWidgets.QLabel, AttributesMixin, RichText, TextOverlay):
    """Header is a QLabel that can be dragged around the screen and can be pinned/unpinned. It provides a customizable
    header bar with buttons for common window actions such as minimizing, hiding, and pinning.

    Signals:
        toggled(bool): Emitted when the pin state is toggled.

    Attributes:
        button_definitions (dict): Defines the properties of the buttons available in the header.
        state (str): Represents the current state of the header ("unpinned", "pinned").
    """

    toggled = QtCore.Signal(bool)

    # Define button properties
    button_definitions = {
        "menu_button": ("≡", "show_menu"),
        "minimize_button": ("–", "minimize_window"),
        "hide_button": ("×", "hide_window"),
        "pin_button": ("\u25CB", "toggle_pin"),
    }

    def __init__(
        self,
        parent=None,
        **kwargs,
    ):
        super().__init__(parent)
        """Initialize the Header with buttons and layout.

        Parameters:
            parent (QWidget, optional): The parent widget. Defaults to None.
            **kwargs: Additional keyword arguments to configure buttons and other attributes.
                      Accepts keys corresponding to the button_definitions, and any additional attributes.
        """
        self.pinned = False  # unpinned, pinned
        self.__mousePressPos = None

        self.container_layout = QtWidgets.QHBoxLayout(self)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(1)
        self.container_layout.addStretch(1)

        self.setLayout(self.container_layout)
        self.setCursor(QtGui.QCursor(QtCore.Qt.OpenHandCursor))
        self.setStyleSheet(self.get_style_sheet())

        # Extract button-related arguments
        button_args = {
            key: kwargs.pop(key)
            for key in list(kwargs.keys())
            if key in self.button_definitions
        }

        self.setFixedHeight(20)
        self.configure_buttons(**button_args)
        self.set_attributes(**kwargs)

    def get_button_style_sheet(self):
        """Return the stylesheet for buttons."""
        return """
            QPushButton { background-color: transparent; border: none;}
            QPushButton:hover { background-color: rgba(127,127,127,200); border: none;}
            QPushButton#hide_button:hover { background-color: rgba(255,0,0,200); border: none;}
        """

    def get_style_sheet(self):
        """Return the stylesheet for the header label."""
        return """
            QLabel {
                background-color: rgba(127,127,127,200);
                border: none;
                font-weight: bold;
            }
            QLabel::hover {
                background-color: rgba(127,127,127,200);
                border: none;
            }
        """

    def create_button(self, text, callback, button_type=None):
        """Create a button with the given text and callback."""
        button = QtWidgets.QPushButton(text, self)
        if button_type:
            button.setObjectName(button_type)
        button.setCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))
        button.setStyleSheet(self.get_button_style_sheet())
        button.clicked.connect(callback)
        return button

    def configure_buttons(self, **kwargs):
        """Configure buttons based on the given parameters."""
        # Clear existing buttons from the layout
        for i in reversed(range(self.container_layout.count())):
            widget = self.container_layout.itemAt(i).widget()
            if isinstance(widget, QtWidgets.QPushButton):
                self.container_layout.removeWidget(widget)

        # Create and add buttons to the layout based on parameters
        self.buttons = {}
        for param, visible in kwargs.items():
            if param in self.button_definitions and visible:
                text, method_name = self.button_definitions[param]
                callback = getattr(self, method_name)
                button = self.create_button(text, callback, button_type=param)
                self.container_layout.addWidget(button)
                button.show()
                self.buttons[param] = button

        # Ensure layout is updated
        self.container_layout.invalidate()
        self.trigger_resize_event()

    def trigger_resize_event(self):
        current_size = self.size()
        resize_event = QtGui.QResizeEvent(current_size, current_size)
        self.resizeEvent(resize_event)

    def resizeEvent(self, event):
        self.resize_buttons()
        self.update_font_size()
        super().resizeEvent(event)

    def resize_buttons(self):
        button_size = self.height()
        margin = button_size * 0.05
        for button_name, button in self.buttons.items():
            button.setFixedSize(button_size - margin, button_size - margin)

    def update_font_size(self):
        # Calculate font size for the label and buttons relative to widget's height
        label_font_size = self.height() * 0.4
        button_font_size = self.height() * 0.6  # 60% of the widget's height

        # Apply font size to the label
        label_font = self.font()
        label_font.setPointSizeF(label_font_size)
        self.setFont(label_font)

        # Iterate through the widgets in the layout and update the font size for the buttons
        for i in range(self.container_layout.count()):
            widget = self.container_layout.itemAt(i).widget()
            if isinstance(widget, QtWidgets.QPushButton):
                button_font = widget.font()
                button_font.setPointSizeF(button_font_size)
                widget.setFont(button_font)

    def setTitle(self, title):
        """Set the title of the header.

        Parameters:
            title (str): The new title.
        """
        self.setText(title)

    def title(self):
        """Get the title of the header.

        Returns:
            str: The current title.
        """
        return self.text()

    def minimize_window(self):
        """Minimize the parent window."""
        self.window().showMinimized()

    def hide_window(self):
        """Hide the parent window."""
        if self.pinned:
            self.toggle_pin()
        self.window().hide()

    @property
    def menu(self):
        try:
            return self._menu
        except AttributeError:
            from uitk.widgets.menu import Menu

            self._menu = Menu(self, fixed_item_height=20)
            return self._menu

    def show_menu(self):
        """Show the menu."""
        self.menu.setVisible(True)

    def toggle_pin(self):
        """Toggle pinning of the window."""
        state = not self.pinned

        self.pinned = state
        self.window().prevent_hide = state
        pin_button_text = "\u25CF" if state else "\u25CB"

        pin_button = self.buttons.get("pin_button")
        if pin_button:
            pin_button.setText(pin_button_text)
            if not state:
                self.window().hide()

        self.toggled.emit(state)

    def mousePressEvent(self, event):
        """Handle the mouse press event. If the left button is pressed, store the global position of the mouse cursor.

        Parameters:
            event (QMouseEvent): The mouse event.
        """
        if event.button() == QtCore.Qt.LeftButton:
            self.__mousePressPos = event.globalPos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle the mouse move event."""
        if self.__mousePressPos is not None:
            moveAmount = event.globalPos() - self.__mousePressPos
            if moveAmount.manhattanLength() > 5:
                self.window().move(self.window().pos() + moveAmount)
                self.__mousePressPos = event.globalPos()
                if not self.pinned:  # Only change state if not already pinned
                    self.toggle_pin()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # No need to toggle pin state here, as pinning is controlled by the button
        self.__mousePressPos = None
        super().mouseReleaseEvent(event)

    def showEvent(self, event):
        """Show the menu button if it exists and contains items."""
        menu_button = self.buttons.get("menu_button")
        if menu_button:
            menu_button.setVisible(self.menu.contains_items)

        super().showEvent(event)

    def attach_to(self, widget: QtWidgets.QWidget):
        """Attaches the header to the given widget by adding the header on top.
        After which, the header can be accessed as an attribute of the widget. <widget>.header

        Parameters:
            widget (QWidget): The widget to which the header will be attached.
        """
        # Check if the widget is a QMainWindow
        if isinstance(widget, QtWidgets.QMainWindow):
            # Check if the QMainWindow uses setMenuWidget()
            menu_widget = widget.menuWidget()
            if menu_widget:
                # Create a container to hold the header and the menu widget
                container = QtWidgets.QWidget(widget)
                container_layout = QtWidgets.QVBoxLayout(container)
                container_layout.setContentsMargins(0, 0, 0, 0)
                container_layout.setSpacing(0)

                # Add the header and the existing menu widget to the container layout
                container_layout.addWidget(self)
                container_layout.addWidget(menu_widget)

                # Set the container as the new menu widget
                widget.setMenuWidget(container)

            else:
                # Handle case where QMainWindow uses a central widget
                existing_central_widget = widget.centralWidget()
                if not existing_central_widget:
                    # Create a new central widget if none exists
                    existing_central_widget = QtWidgets.QWidget()
                    widget.setCentralWidget(existing_central_widget)

                # Get or create the layout for the central widget
                existing_layout = existing_central_widget.layout()
                if not existing_layout:
                    existing_layout = QtWidgets.QVBoxLayout(existing_central_widget)
                    existing_central_widget.setLayout(existing_layout)

                # Insert the header at the top of the central layout
                existing_layout.insertWidget(0, self)

        else:
            # Handle generic QWidget or any other widget type
            layout = widget.layout() or QtWidgets.QVBoxLayout(widget)
            widget.setLayout(layout)

            # Insert the header as the first widget in the layout
            layout.insertWidget(0, self)

        # Set the header as an attribute of the widget for reference
        setattr(widget, "header", self)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(w)
    header = Header(
        menu_button=True,
        minimize_button=True,
        pin_button=True,
        hide_button=True,
        setTitle="DRAG ME!",
    )
    header.toggled.connect(lambda state: print(f"Header pinned: {state}!"))
    header.menu.add(["Menu Item A", "Menu Item B"])

    layout.addWidget(header)
    w.show()

    # sys.exit(app.exec_())


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
