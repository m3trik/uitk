# !/usr/bin/python
# coding=utf-8
import os
from qtpy import QtWidgets, QtCore, QtGui, QtSvg
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay
from uitk.widgets.mixins.icon_manager import IconManager


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
        "menu": ("menu.svg", "show_menu"),
        "collapse": ("chevron_up.svg", "toggle_collapse"),
        "minimize": ("minimize.svg", "minimize_window"),
        "maximize": ("maximize.svg", "toggle_maximize"),
        "hide": ("close.svg", "hide_window"),
        "pin": ("close.svg", "toggle_pin"),  # Default: close icon (hide mode)
    }

    def __init__(
        self,
        parent=None,
        config_buttons=None,
        pin_on_drag_only=True,
        **kwargs,
    ):
        """Initialize the Header with buttons and layout.

        Parameters:
            parent (QWidget, optional): The parent widget. Defaults to None.
            config_buttons (list, optional): List of button names to show in order.
                Example: ['menu', 'pin']
                Available buttons: 'menu', 'collapse', 'minimize', 'maximize', 'hide', 'pin'
            pin_on_drag_only (bool, optional): If True (default), clicking the pin button hides
                the window, and only dragging the header pins it. If False, clicking the pin
                button toggles traditional pin/unpin behavior.
                Defaults to True.
            **kwargs: Additional attributes for the header (e.g., setTitle="My Title").
        """
        super().__init__(parent)
        self.pinned = False  # unpinned, pinned
        self.pin_on_drag_only = pin_on_drag_only
        self._collapsed = False
        self._saved_size = None
        self._saved_min_size = None
        self._saved_max_size = None
        self.__mousePressPos = None
        self.buttons = {}  # Initialize buttons dict to avoid AttributeError

        self.container_layout = QtWidgets.QHBoxLayout(self)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(1)
        self.container_layout.addStretch(1)

        self.setLayout(self.container_layout)
        self.setCursor(QtGui.QCursor(QtCore.Qt.OpenHandCursor))

        self.setProperty("class", self.__class__.__name__)
        font = self.font()
        font.setBold(True)
        self.setFont(font)

        self.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        self.setIndent(8)  # adds left-side indentation to the text
        self.setFixedHeight(20)

        if config_buttons:
            # Unpack the list when calling the method
            if isinstance(config_buttons, (list, tuple)):
                self.config_buttons(*config_buttons)
            else:
                self.config_buttons(config_buttons)

        self.set_attributes(**kwargs)

    @property
    def menu(self):
        try:
            return self._menu
        except AttributeError:
            from uitk.widgets.menu import Menu

            self._menu = Menu(self, fixed_item_height=20, hide_on_leave=True)
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
            # Prefix with 'hdr_' to avoid conflicts with QWidget methods
            # when MainWindow's __getattr__ searches for widgets by name
            button.setObjectName(f"hdr_{button_type}")

        # Set the icon using IconManager for theme support
        icon_name = icon_filename.replace(".svg", "")
        IconManager.set_icon(button, icon_name, size=(16, 16))

        button.setCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))
        button.clicked.connect(callback)
        return button

    def has_buttons(self, button_type=None):
        """Check if the header has a specific button type or any button.

        Parameters:
            button_type (str or list, optional): The button type(s) to check for.
                If None, checks if any button exists.

        Returns:
            bool: True if the button exists, False otherwise.
        """
        if button_type is None:
            return bool(self.buttons)

        if isinstance(button_type, str):
            return button_type in self.buttons

        if isinstance(button_type, (list, tuple)):
            return any(btn in self.buttons for btn in button_type)

        return False

    def config_buttons(self, *button_list):
        """Configure header buttons from a list and align them to the right.

        Parameters:
            *button_list: Button names in display order (as args or single list).
                Examples:
                    config_buttons('pin', 'menu')
                    config_buttons(['pin', 'menu'])
                Available: 'menu', 'collapse', 'minimize', 'maximize', 'hide', 'pin'
        """
        # Support both styles: config_buttons('a', 'b') and config_buttons(['a', 'b'])
        if len(button_list) == 1 and isinstance(button_list[0], (list, tuple)):
            button_list = button_list[0]

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
        for button_name in button_list:
            if button_name not in self.button_definitions:
                continue

            icon_filename, method_name = self.button_definitions[button_name]
            callback = getattr(self, method_name)

            button = self.create_button(
                icon_filename, callback, button_type=button_name
            )
            button.setVisible(True)

            # Set initial hideMode property and stylesheet for pin button
            if button_name == "pin":
                # Default icon is close (hide mode) so apply red hover
                button.setProperty("hideMode", True)
                button.setStyleSheet(
                    "QPushButton:hover { background-color: red; border: none; }"
                )

            self.container_layout.addWidget(button)
            self.buttons[button_name] = button

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

    def toggle_maximize(self):
        """Toggle between maximized and normal window state."""
        window = self.window()
        if window.isMaximized():
            window.showNormal()
            # Update icon to maximize
            if "maximize" in self.buttons:
                IconManager.set_icon(
                    self.buttons["maximize"], "maximize", size=(16, 16)
                )
        else:
            window.showMaximized()
            # Update icon to restore (overlapping windows)
            if "maximize" in self.buttons:
                IconManager.set_icon(self.buttons["maximize"], "restore", size=(16, 16))

    def hide_window(self):
        """Hide the parent window."""
        if self.pinned:
            self.toggle_pin(from_drag=True)  # Programmatic toggle, not user click

        # Reset collapse state when hiding
        if self._collapsed:
            self.expand_window()

        self.window().hide()

    def unhide_window(self):
        """Unhide the parent window."""
        self.window().show()
        if not self.pinned:
            self.toggle_pin(from_drag=True)  # Programmatic toggle, not user click

    def show_menu(self):
        """Show the menu."""
        menu = self.menu
        grid = menu.gridLayout

        if grid:
            for i in range(grid.count()):
                item = grid.itemAt(i)
                widget = item.widget() if item else None
                if widget:
                    row, col, rowSpan, colSpan = grid.getItemPosition(i)
                    text = (
                        widget.text()
                        if hasattr(widget, "text") and callable(widget.text)
                        else ""
                    )
        menu.setVisible(True)

    def toggle_collapse(self):
        """Toggle between collapsed (header only) and expanded window states."""
        if self._collapsed:
            self.expand_window()
        else:
            self.collapse_window()

    def collapse_window(self):
        """Collapse the parent window to show only the header."""
        if self._collapsed:
            return

        window = self.window()

        # Save current size and size constraints (not position - that can change while collapsed)
        self._saved_size = window.size()
        self._saved_min_size = window.minimumSize()
        self._saved_max_size = window.maximumSize()

        # Calculate collapsed height (header height + small margin for border)
        collapsed_height = self.height() + 4

        # Collapse the window
        window.setMinimumHeight(0)
        window.setMaximumHeight(collapsed_height)
        window.resize(window.width(), collapsed_height)

        # Update icon to expand (chevron down)
        if "collapse" in self.buttons:
            IconManager.set_icon(
                self.buttons["collapse"], "chevron_down", size=(16, 16)
            )

        self._collapsed = True

    def expand_window(self):
        """Expand the window back to its original size."""
        if not self._collapsed:
            return

        window = self.window()

        # Restore size constraints first
        if self._saved_min_size:
            window.setMinimumSize(self._saved_min_size)
        if self._saved_max_size:
            window.setMaximumSize(self._saved_max_size)

        # Don't restore size - let the window adjust naturally to its content
        # This allows groupbox visibility changes to properly resize the window
        window.setMaximumHeight(16777215)  # Qt's default max height
        window.adjustSize()

        # Update icon to collapse (chevron up)
        if "collapse" in self.buttons:
            IconManager.set_icon(self.buttons["collapse"], "chevron_up", size=(16, 16))

        self._collapsed = False

    def toggle_pin(self, from_drag=False):
        """Toggle pinning of the window.

        Parameters:
            from_drag (bool): If True, this was triggered by dragging the header.
                Used to differentiate between click and drag when pin_on_drag_only is enabled.
        """
        # Default behavior: clicking hides, dragging pins
        if self.pin_on_drag_only and not from_drag:
            if self.pinned:
                # Unpin without hiding (hiding happens below)
                self.pinned = False
                self.window().prevent_hide = False
                pin_button = self.buttons.get("pin")
                if pin_button:
                    IconManager.set_icon(pin_button, "close", size=(16, 16))
                    pin_button.setProperty("hideMode", True)
                    self._refresh_button_style(pin_button)
                self.toggled.emit(False)
            # Always hide on click regardless of pin state
            self.window().hide()
            return

        # Standard pin button behavior OR drag behavior
        state = not self.pinned

        self.pinned = state
        self.window().prevent_hide = state

        # Icon: close when unpinned (hide mode), radio when pinned (pinned mode)
        icon_name = "radio" if state else "close"

        pin_button = self.buttons.get("pin")
        if pin_button:
            IconManager.set_icon(pin_button, icon_name, size=(16, 16))
            # Set hideMode property for styling
            is_hide_mode = icon_name == "close"
            pin_button.setProperty("hideMode", is_hide_mode)
            # Force style refresh
            self._refresh_button_style(pin_button)
            if not state and not self.pin_on_drag_only:
                # Standard behavior: when unpinned via button, hide the window
                self.window().hide()

        self.toggled.emit(state)

    def reset_pin_state(self):
        """Force the header into an unpinned state without hiding the window."""
        if not self.pinned:
            return

        self.pinned = False
        self.window().prevent_hide = False

        pin_button = self.buttons.get("pin")
        if pin_button:
            IconManager.set_icon(pin_button, "close", size=(16, 16))
            pin_button.setProperty("hideMode", True)
            self._refresh_button_style(pin_button)

        self.toggled.emit(False)

    def _refresh_button_style(self, button):
        """Force a button to refresh its stylesheet after property changes."""
        # For the pin button in hide mode, apply red hover background directly
        if button.property("hideMode") is not None:
            hide_mode = button.property("hideMode")
            if hide_mode:
                # Apply the same red hover style as the hide button
                button.setStyleSheet(
                    "QPushButton:hover { background-color: red; border: none; }"
                )
            else:
                # Clear custom stylesheet for normal pin mode
                button.setStyleSheet("")

        button.update()

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
                    self.toggle_pin(from_drag=True)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # No need to toggle pin state here, as pinning is controlled by the button
        self.__mousePressPos = None
        super().mouseReleaseEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._finalize_menu_button_visibility)

    def _finalize_menu_button_visibility(self):
        menu_button = self.buttons.get("menu")
        if menu_button:
            visible = self.menu.contains_items
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

    def hideEvent(self, event):
        """Reset collapse state when header (and window) is hidden."""
        if self._collapsed:
            self.expand_window()
        super().hideEvent(event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(w)
    header = Header(
        config_buttons=["menu", "collapse", "minimize", "pin", "hide"],
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
