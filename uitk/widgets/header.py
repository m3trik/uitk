# !/usr/bin/python
# coding=utf-8
import os
from qtpy import QtWidgets, QtCore, QtGui, QtSvg
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

    # Define button properties with icon paths and callbacks
    button_definitions = {
        "menu_button": ("menu.svg", "show_menu"),
        "minimize_button": ("minimize.svg", "minimize_window"),
        "hide_button": ("hide.svg", "hide_window"),
        "pin_button": ("pin.svg", "toggle_pin"),
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

        # Extract button-related arguments
        button_args = {
            key: kwargs.pop(key)
            for key in list(kwargs.keys())
            if key in self.button_definitions
        }
        self.setProperty("class", self.__class__.__name__)
        font = self.font()
        font.setBold(True)
        self.setFont(font)

        self.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        self.setIndent(8)  # adds left-side indentation to the text
        self.setFixedHeight(20)
        self.config_buttons(**button_args)
        self.set_attributes(**kwargs)

    @property
    def menu(self):
        try:
            return self._menu
        except AttributeError:
            from uitk.widgets.menu import Menu

            # print(f"[Header.menu] constructing new menu for: {self.objectName()}")
            self._menu = Menu(self, fixed_item_height=20)
            return self._menu

    def get_icon_path(self, icon_filename):
        """Get the full path to an icon file in the uitk/icons directory."""
        # Get the directory where this module is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up one level to uitk, then into icons
        icons_dir = os.path.join(os.path.dirname(current_dir), "icons")
        return os.path.join(icons_dir, icon_filename)

    def create_svg_icon(self, icon_filename, size=16):
        """Create a QIcon from an SVG file."""
        icon_path = self.get_icon_path(icon_filename)
        if os.path.exists(icon_path):
            # Create a pixmap from SVG with proper scaling
            svg_renderer = QtSvg.QSvgRenderer(icon_path)
            pixmap = QtGui.QPixmap(size, size)
            pixmap.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pixmap)
            svg_renderer.render(painter)
            painter.end()
            return QtGui.QIcon(pixmap)
        else:
            # Fallback to empty icon if file not found
            return QtGui.QIcon()

    def create_button(self, icon_filename, callback, button_type=None):
        """Create a button with the given icon and callback."""
        button = QtWidgets.QPushButton(self)
        if button_type:
            button.setObjectName(button_type)

        # Set the icon
        icon = self.create_svg_icon(icon_filename, 16)
        button.setIcon(icon)
        button.setIconSize(QtCore.QSize(16, 16))

        button.setCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))
        button.clicked.connect(callback)
        return button

    def config_buttons(self, **kwargs):
        """Configure header buttons in the declared keyword order and align them to the right."""
        # Clear layout
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        self.buttons = {}

        # Re-add left-side stretch so buttons align to the right
        self.container_layout.addStretch(1)

        # Insert buttons in order (they go to the right)
        for param in kwargs:
            if param not in self.button_definitions:
                continue

            visible = kwargs[param]
            icon_filename, method_name = self.button_definitions[param]
            callback = getattr(self, method_name)

            button = self.create_button(icon_filename, callback, button_type=param)
            button.setVisible(visible)

            self.container_layout.addWidget(button)
            self.buttons[param] = button

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

    def unhide_window(self):
        """Unhide the parent window."""
        self.window().show()
        if not self.pinned:
            self.toggle_pin()

    def show_menu(self):
        """Show the menu."""
        self.menu.setVisible(True)

    def toggle_pin(self):
        """Toggle pinning of the window."""
        state = not self.pinned

        self.pinned = state
        self.window().prevent_hide = state

        # Switch between pin icons based on state
        pin_icon_filename = "pin_active.svg" if state else "pin.svg"

        pin_button = self.buttons.get("pin_button")
        if pin_button:
            icon = self.create_svg_icon(pin_icon_filename, 16)
            pin_button.setIcon(icon)
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
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._finalize_menu_button_visibility)

    def _finalize_menu_button_visibility(self):
        menu_button = self.buttons.get("menu_button")
        if menu_button:
            visible = self.menu.contains_items
            # print(
            #     f"[Header._finalize_menu_button_visibility] setting menu_button visible = {visible}"
            # )
            menu_button.setVisible(visible)

    def attach_to(self, widget: QtWidgets.QWidget) -> None:
        """Attach this header to the top of a QWidget or QMainWindow's centralWidget if appropriate."""
        # Avoid double-attachment
        if hasattr(widget, "header") and getattr(widget, "header") is self:
            return

        # If passed a QMainWindow (or subclass), redirect to its central widget.
        if isinstance(widget, QtWidgets.QMainWindow) and widget.centralWidget():
            widget = widget.centralWidget()

        # Attach to the widget's layout
        layout = widget.layout()
        if not isinstance(layout, QtWidgets.QLayout):
            layout = QtWidgets.QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            widget.setLayout(layout)
        layout.insertWidget(0, self)
        self.setParent(widget)
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
