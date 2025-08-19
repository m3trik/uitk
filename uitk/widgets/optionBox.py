# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore
from uitk.widgets.mixins.text import RichText
from uitk.widgets.mixins.icon_manager import IconManager
from uitk.widgets.mixins.attributes import AttributesMixin


class ClearButton(QtWidgets.QPushButton, AttributesMixin, RichText):
    """A clear button that can clear text from input widgets."""

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        # rich text overrides
        self.text = self.richText
        self.setText = self.setRichText
        self.sizeHint = self.richTextSizeHint

        if not self.objectName():
            self.setObjectName("clearButton")

        # Use the new modern SVG icon
        IconManager.set_icon(self, "clear", size=(17, 17))
        self.setToolTip("Clear text")

        self.clicked.connect(self._clear_text)
        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    def _clear_text(self):
        """Clear text from the wrapped widget."""
        if hasattr(self, "wrapped_widget"):
            widget = self.wrapped_widget
            # Handle different types of text widgets
            if hasattr(widget, "clear"):
                widget.clear()
            elif hasattr(widget, "setText"):
                widget.setText("")
            elif hasattr(widget, "setPlainText"):
                widget.setPlainText("")


class OptionBoxContainer(QtWidgets.QWidget):
    """Dedicated container so QSS can target the class name directly.

    Styled purely via style.qss rule: `OptionBoxContainer { ... }`.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        # Provide both objectName and class-style property hooks for QSS.
        if not self.objectName():
            self.setObjectName("optionBoxContainer")
        self.setProperty("class", "withBorder")


class OptionBox(QtWidgets.QPushButton, AttributesMixin, RichText):
    """Lightweight option trigger that can wrap another widget.

    Goal: provide a small square button (icon) attached to the right side of any
    existing widget while preserving the outer border as a single rectangle.
    The outer container draws the border; the wrapped widget + option box sit
    inside a zero-margin horizontal layout so the outline reaches both edges.
    """

    def __init__(
        self,
        parent=None,
        action_handler=None,  # Legacy compatibility
        action=None,  # New streamlined API
        menu=None,  # New streamlined API
        show_clear_button=False,  # Legacy compatibility
        show_clear=False,  # New streamlined API
        **kwargs,
    ):
        super().__init__(parent)
        # rich text overrides
        self.text = self.richText
        self.setText = self.setRichText
        self.sizeHint = self.richTextSizeHint

        # Handle both legacy and new API
        self._action_handler = action_handler or action or menu
        self._menu = menu
        self._show_clear_button = show_clear_button or show_clear
        self._clear_button = None
        self.wrapped_widget = None
        self.container = None

        # Styling (border removal, sizing) is handled purely by QSS now; no inline styles.
        if not self.objectName():
            self.setObjectName("optionBox")
        IconManager.set_icon(self, "option_box", size=(17, 17))
        self.clicked.connect(self._handle_click)
        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    # ------------------------------------------------------------------
    # Backward compatibility with previous 'menu' attribute usage
    @property
    def menu(self):
        return self._action_handler

    @menu.setter
    def menu(self, value):  # noqa: D401
        self._action_handler = value

    # ------------------------------------------------------------------
    # New streamlined API methods
    # ------------------------------------------------------------------

    def set_action(self, action):
        """Set the action handler."""
        self._action_handler = action

    def set_menu(self, menu):
        """Set the menu."""
        self._menu = menu
        self._action_handler = menu

    @property
    def show_clear(self):
        """Get clear button state."""
        return self._show_clear_button

    @show_clear.setter
    def show_clear(self, value):
        """Set clear button visibility."""
        self._show_clear_button = value
        if hasattr(self, "container") and self._clear_button:
            self._clear_button.setVisible(value)

    # ------------------------------------------------------------------
    def set_action_handler(self, handler):
        self._action_handler = handler

    # ------------------------------------------------------------------
    def set_clear_button_visible(self, visible=True):
        """Enable or disable the clear button functionality."""
        self._show_clear_button = visible
        if hasattr(self, "container") and self._clear_button:
            self._clear_button.setVisible(visible)

    # ------------------------------------------------------------------
    def _is_text_widget(self, widget):
        """Check if the widget is a text input widget that can benefit from a clear button."""
        text_widget_types = (
            QtWidgets.QLineEdit,
            QtWidgets.QTextEdit,
            QtWidgets.QPlainTextEdit,
            QtWidgets.QSpinBox,
            QtWidgets.QDoubleSpinBox,
            QtWidgets.QComboBox,
        )
        return isinstance(widget, text_widget_types)

    # ------------------------------------------------------------------
    def _handle_click(self):
        h = self._action_handler
        if h is None:
            return
        if callable(h):  # direct callable
            try:
                h()
            except Exception as e:  # pragma: no cover - defensive
                print(f"OptionBox handler error: {e}")
            return
        # Heuristic method lookup order
        for attr in ("show", "execute", "run", "trigger"):
            if hasattr(h, attr) and callable(getattr(h, attr)):
                getattr(h, attr)()
                return
        # Fallback attempt
        try:
            h()
        except Exception:  # pragma: no cover
            print(f"Warning: OptionBox handler {h} not invokable")

    # ------------------------------------------------------------------
    # Helper methods for DRY code
    # ------------------------------------------------------------------

    def _create_container_and_layout(self, wrapped_widget):
        """Create container and layout - shared by both wrap implementations."""
        parent = wrapped_widget.parent()
        container = OptionBoxContainer(parent)

        # Replace original widget in parent layout
        if parent and parent.layout():
            parent.layout().replaceWidget(wrapped_widget, container)
        else:
            container.move(wrapped_widget.pos())

        # Zero‑margin layout so border reaches edges
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setParent(container)
        layout.addWidget(wrapped_widget)

        return container, layout

    def _apply_border_styling(
        self, wrapped_widget, clear_button=None, is_clear_last=True
    ):
        """Apply border styling to prevent double borders."""
        # Remove right border from wrapped widget
        wrapped_widget.setStyleSheet(
            wrapped_widget.styleSheet() + "; border-right: none !important;"
        )

        # Remove right border from clear button if it's not the last widget
        if clear_button and not is_clear_last:
            clear_button.setStyleSheet(
                clear_button.styleSheet() + "; border-right: none !important;"
            )

    def _finalize_container(self, container, wrapped_widget, clear_button=None):
        """Finalize container sizing and display."""
        container.adjustSize()
        h = wrapped_widget.height() or wrapped_widget.sizeHint().height()
        self.setFixedSize(h, h)
        if clear_button:
            clear_button.setFixedSize(h, h)
        wrapped_widget.setMinimumHeight(h)
        container.adjustSize()
        self.container = container
        container.show()
        return container

    # ------------------------------------------------------------------
    def wrap(self, wrapped_widget: QtWidgets.QWidget):
        """Wrap target widget with a border container and attach self to the right."""
        self.wrapped_widget = wrapped_widget
        container, layout = self._create_container_and_layout(wrapped_widget)

        # Add clear button if enabled and widget is a text widget
        clear_button = None
        if self._show_clear_button and self._is_text_widget(wrapped_widget):
            clear_button = ClearButton(container)
            clear_button.wrapped_widget = wrapped_widget
            self._clear_button = clear_button
            layout.addWidget(clear_button)

        layout.addWidget(self)

        # Apply border styling
        self._apply_border_styling(wrapped_widget, clear_button, is_clear_last=False)

        # Finalize and return
        return self._finalize_container(container, wrapped_widget, clear_button)

    # ------------------------------------------------------------------
    def add_clear_button(self):
        """Add a clear button to an already wrapped widget."""
        if not hasattr(self, "container") or not hasattr(self, "wrapped_widget"):
            print("Warning: OptionBox must be wrapped before adding clear button")
            return

        if not self._is_text_widget(self.wrapped_widget):
            print("Warning: Clear button is only useful for text input widgets")
            return

        if self._clear_button is not None:
            print("Warning: Clear button already exists")
            return

        # Create clear button
        self._clear_button = ClearButton(self.container)
        self._clear_button.wrapped_widget = self.wrapped_widget

        # Insert clear button before the option box in the layout
        layout = self.container.layout()
        layout.insertWidget(layout.count() - 1, self._clear_button)

        # Adjust sizing
        h = self.wrapped_widget.height() or self.wrapped_widget.sizeHint().height()
        self._clear_button.setFixedSize(h, h)
        self.container.adjustSize()
        self._show_clear_button = True

    # Convenience for legacy calls
    def show_menu(self):  # pragma: no cover
        if hasattr(self._action_handler, "contains_items") and hasattr(
            self._action_handler, "show"
        ):
            if (
                not getattr(self, "wrapped_widget", None)
                or self.wrapped_widget.isVisible()
            ):
                self._action_handler.show()
            else:
                orig = getattr(self._action_handler, "position", None)
                if orig is not None:
                    self._action_handler.position = "cursorPos"
                self._action_handler.show()
                if orig is not None:
                    self._action_handler.position = orig


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    window = QtWidgets.QWidget()
    window.setWindowTitle("OptionBox Examples")
    layout = QtWidgets.QVBoxLayout(window)

    # Example 1: Basic button with custom callback
    button1 = QtWidgets.QPushButton("Button with Callback")
    option_box1 = OptionBox(action_handler=lambda: print("Custom callback executed!"))
    option_box1.wrap(button1)
    layout.addWidget(option_box1.container)

    # Example 2: Button with custom action object
    class CustomAction:
        def execute(self):
            print("Custom action executed!")

    button2 = QtWidgets.QPushButton("Button with Action Object")
    option_box2 = OptionBox(action_handler=CustomAction())
    option_box2.wrap(button2)
    layout.addWidget(option_box2.container)

    # Example 3: Backward compatibility with menu (original behavior)
    button3 = QtWidgets.QPushButton("Button with Menu (legacy)")
    option_box3 = OptionBox(setText='<hl style="color:red;">⛾</hl>')
    option_box3.wrap(button3)

    # Simulate the menu assignment that would be done by Menu class
    class MockMenu:
        contains_items = True
        position = "cursorPos"

        def show(self):
            print("Menu shown!")

    option_box3.menu = MockMenu()
    layout.addWidget(option_box3.container)

    # Example 4: Dialog action
    def show_dialog():
        dialog = QtWidgets.QMessageBox()
        dialog.setText("Hello from OptionBox!")
        dialog.exec_()

    button4 = QtWidgets.QPushButton("Button with Dialog")
    option_box4 = OptionBox(action_handler=show_dialog)
    option_box4.wrap(button4)
    layout.addWidget(option_box4.container)

    # Example 5: LineEdit with clear button
    line_edit1 = QtWidgets.QLineEdit("Type something here...")
    option_box5 = OptionBox(
        action_handler=lambda: print("LineEdit option clicked!"), show_clear_button=True
    )
    option_box5.wrap(line_edit1)
    layout.addWidget(option_box5.container)

    # Example 6: TextEdit with clear button
    text_edit1 = QtWidgets.QTextEdit()
    text_edit1.setPlainText("This is some default text that can be cleared.")
    text_edit1.setMaximumHeight(80)  # Keep it compact for the example
    option_box6 = OptionBox(
        action_handler=lambda: print("TextEdit option clicked!"), show_clear_button=True
    )
    option_box6.wrap(text_edit1)
    layout.addWidget(option_box6.container)

    # Example 7: ComboBox with clear button
    combo_box1 = QtWidgets.QComboBox()
    combo_box1.addItems(["Option 1", "Option 2", "Option 3"])
    combo_box1.setEditable(True)
    combo_box1.setCurrentText("Select or type...")
    option_box7 = OptionBox(
        action_handler=lambda: print("ComboBox option clicked!"), show_clear_button=True
    )
    option_box7.wrap(combo_box1)
    layout.addWidget(option_box7.container)

    # Example 8: Adding clear button after wrapping
    line_edit2 = QtWidgets.QLineEdit("Add clear button after wrapping")
    option_box8 = OptionBox(
        action_handler=lambda: print("Post-wrap clear button example!")
    )
    option_box8.wrap(line_edit2)
    option_box8.add_clear_button()  # Add clear button after wrapping
    layout.addWidget(option_box8.container)

    window.show()
    sys.exit(app.exec_())


# -------------------------------------------------------------------------
# Convenience functions for easy integration
# -------------------------------------------------------------------------


def add_option_box(widget, action=None, menu=None, show_clear=False, **kwargs):
    """Add an option box to any widget with one function call.

    Args:
        widget: The widget to wrap
        action: Action function to call when clicked
        menu: Menu object to show when clicked
        show_clear: Whether to show clear button for text widgets
        **kwargs: Additional options

    Returns:
        The container widget that should be added to layouts

    Example:
        line_edit = QtWidgets.QLineEdit()
        container = add_option_box(line_edit, show_clear=True)
        layout.addWidget(container)
    """
    option_box = OptionBox(action=action, menu=menu, show_clear=show_clear, **kwargs)
    return option_box.wrap(widget)


def add_clear_option(widget, **kwargs):
    """Add just a clear button to a text widget.

    Args:
        widget: The text widget to add clear button to
        **kwargs: Additional options

    Returns:
        The container widget that should be added to layouts
    """
    return add_option_box(widget, show_clear=True, **kwargs)


def add_menu_option(widget, menu, **kwargs):
    """Add a menu option to any widget.

    Args:
        widget: The widget to wrap
        menu: Menu object to show
        **kwargs: Additional options

    Returns:
        The container widget that should be added to layouts
    """
    return add_option_box(widget, menu=menu, **kwargs)


# -------------------------------------------------------------------------
# Elegant OptionBox Manager for widget attribute access
# -------------------------------------------------------------------------


class OptionBoxManager:
    """Elegant manager for option box functionality accessible as widget.option_box"""

    def __init__(self, widget):
        self._widget = widget
        self._option_box = None
        self._container = None
        self._clear_enabled = False
        self._action_handler = None
        self._menu = None
        self._option_order = [
            "clear",
            "action",
        ]  # Default order: clear button first, then action button

    @property
    def clear_option(self):
        """Get/set clear option state"""
        return self._clear_enabled

    @clear_option.setter
    def clear_option(self, enabled):
        """Enable/disable clear option"""
        self._clear_enabled = enabled
        self._update_option_box()

    @property
    def option_order(self):
        """Get/set option ordering: ['clear', 'action'] or ['action', 'clear']"""
        return self._option_order

    @option_order.setter
    def option_order(self, order):
        """Set option ordering

        Args:
            order: List like ['clear', 'action'] or ['action', 'clear']
        """
        if not isinstance(order, (list, tuple)):
            raise ValueError("Option order must be a list or tuple")

        valid_options = {"clear", "action"}
        if not all(opt in valid_options for opt in order):
            raise ValueError(
                f"Invalid options in order. Valid options: {valid_options}"
            )

        self._option_order = list(order)
        if self._option_box:
            # Recreate with new order
            self._recreate_option_box()

    def enable_clear(self):
        """Enable clear option (fluent interface)"""
        self.clear_option = True
        return self

    def disable_clear(self):
        """Disable clear option (fluent interface)"""
        self.clear_option = False
        return self

    def set_action(self, action_handler):
        """Set action handler (fluent interface)"""
        self._action_handler = action_handler
        self._update_option_box()
        return self

    def set_menu(self, menu):
        """Set menu (fluent interface)"""
        self._menu = menu
        self._action_handler = menu
        self._update_option_box()
        return self

    def set_order(self, order):
        """Set option order (fluent interface)

        Args:
            order: List like ['clear', 'action'] or ['action', 'clear']
        """
        self.option_order = order
        return self

    def clear_first(self):
        """Set clear button to appear first (fluent interface)"""
        return self.set_order(["clear", "action"])

    def action_first(self):
        """Set action button to appear first (fluent interface)"""
        return self.set_order(["action", "clear"])

    @property
    def enabled(self):
        """Check if option box is enabled"""
        return self._option_box is not None

    @property
    def widget(self):
        """Get the actual option box widget"""
        self._update_option_box()  # Ensure option box is created if needed
        return self._option_box

    @property
    def container(self):
        """Get the container widget (for layout management)"""
        # If we don't have a container yet, but widget has a menu with items,
        # try to get the container from the menu's option box
        if not self._container and hasattr(self._widget, "menu"):
            menu = self._widget.menu
            if (
                hasattr(menu, "option_box")
                and menu.option_box
                and hasattr(menu.option_box, "container")
            ):
                self._container = menu.option_box.container
                self._option_box = menu.option_box
        return self._container

    def _update_option_box(self):
        """Update or create option box based on current settings"""
        # If we already have an option box, just update it
        if self._option_box:
            self._option_box.set_clear_button_visible(self._clear_enabled)
            if self._action_handler:
                self._option_box.set_action_handler(self._action_handler)
            return

        # Check if widget already has a menu with an option box
        existing_option_box = self._find_existing_option_box()

        if existing_option_box:
            # Use the existing option box from menu
            self._option_box = existing_option_box
            self._container = existing_option_box.container
            # Update its settings
            if self._clear_enabled:
                self._option_box.set_clear_button_visible(True)
        elif self._clear_enabled or self._action_handler:
            # Create new option box if none exists
            self._create_option_box()

    def _find_existing_option_box(self):
        """Find existing option box created by menu or other systems"""
        # Check if widget has a menu with an option box
        if hasattr(self._widget, "menu") and hasattr(self._widget.menu, "option_box"):
            menu_option_box = self._widget.menu.option_box
            if menu_option_box and hasattr(menu_option_box, "container"):
                return menu_option_box

        # Check if widget is already wrapped in an option box container
        parent = self._widget.parent()
        if (
            parent
            and hasattr(parent, "objectName")
            and parent.objectName() == "optionBoxContainer"
        ):
            # Find the option box widget in the container
            for child in parent.children():
                if isinstance(child, OptionBox):
                    return child

        return None

    def _create_option_box(self):
        """Create and wrap the option box"""
        self._option_box = OptionBoxWithOrdering(
            action_handler=self._action_handler,
            show_clear=self._clear_enabled,
            option_order=self._option_order,
        )
        self._container = self._option_box.wrap(self._widget)

    def _recreate_option_box(self):
        """Recreate option box with new settings"""
        if self._option_box and self._container:
            # Store current settings
            action_handler = self._action_handler
            clear_enabled = self._clear_enabled

            # Remove existing
            self.remove()

            # Recreate with new order
            self._action_handler = action_handler
            self._clear_enabled = clear_enabled
            self._create_option_box()

    def remove(self):
        """Remove option box completely"""
        if self._option_box and self._container:
            # Restore widget to original state
            parent = self._container.parent()
            if parent and parent.layout():
                parent.layout().replaceWidget(self._container, self._widget)
            else:
                self._widget.setParent(parent)
                self._widget.move(self._container.pos())

            self._container.deleteLater()
            self._option_box = None
            self._container = None
            self._clear_enabled = False
            self._action_handler = None
            self._menu = None


class OptionBoxWithOrdering(OptionBox):
    """OptionBox that supports configurable option ordering"""

    def __init__(self, *args, option_order=None, **kwargs):
        self._option_order = option_order or ["clear", "action"]
        super().__init__(*args, **kwargs)

    def wrap(self, wrapped_widget: QtWidgets.QWidget):
        """Wrap target widget with configurable option ordering."""
        self.wrapped_widget = wrapped_widget
        container, layout = self._create_container_and_layout(wrapped_widget)

        # Create clear button if needed
        clear_button = None
        if self._show_clear_button and self._is_text_widget(wrapped_widget):
            clear_button = ClearButton(container)
            clear_button.wrapped_widget = wrapped_widget
            self._clear_button = clear_button

        # Add options in specified order
        for option_type in self._option_order:
            if option_type == "clear" and clear_button:
                layout.addWidget(clear_button)
            elif option_type == "action":
                layout.addWidget(self)

        # Apply border styling (check if clear button is last)
        is_clear_last = self._option_order[-1] == "clear"
        self._apply_border_styling(wrapped_widget, clear_button, is_clear_last)

        # Finalize and return
        return self._finalize_container(container, wrapped_widget, clear_button)


# -------------------------------------------------------------------------
# Widget patching for elegant usage
# -------------------------------------------------------------------------


def patch_widget_class(widget_class):
    """Add option_box attribute to a widget class."""

    def get_option_box(self):
        """Get or create option box manager"""
        if not hasattr(self, "_option_box_manager"):
            self._option_box_manager = OptionBoxManager(self)
        return self._option_box_manager

    # Only add if not already present
    if not hasattr(widget_class, "option_box"):
        widget_class.option_box = property(get_option_box)
    return widget_class


def patch_common_widgets():
    """Patch common Qt widgets with option box support."""
    common_widgets = [
        QtWidgets.QLineEdit,
        QtWidgets.QTextEdit,
        QtWidgets.QPlainTextEdit,
        QtWidgets.QPushButton,
        QtWidgets.QComboBox,
        QtWidgets.QSpinBox,
        QtWidgets.QDoubleSpinBox,
    ]

    for widget_class in common_widgets:
        patch_widget_class(widget_class)


# Auto-patch on import for convenience
patch_common_widgets()


# -------------------------------------------------------------------------
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

# Deprecated: --------------------
