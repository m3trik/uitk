# !/usr/bin/python
# coding=utf-8
"""OptionBox - Plugin-based container for wrapping widgets with action buttons."""

from qtpy import QtWidgets, QtCore


class OptionBoxContainer(QtWidgets.QWidget):
    """Container widget that wraps a widget with option buttons.

    Styled via style.qss rule: `OptionBoxContainer { ... }`.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        if not self.objectName():
            self.setObjectName("optionBoxContainer")
        self.setProperty("class", "withBorder")


class OptionBox:
    """Plugin-based option manager that wraps widgets with action buttons.

    Wraps any widget in an OptionBoxContainer with optional action buttons
    (clear, pin, menu, etc.) provided by the plugin system. Each plugin
    creates its own button widget.

    This class is NOT a widget itself - it only manages the container and plugins.
    """

    def __init__(
        self,
        show_clear=False,
        options=None,
        option_order=None,
    ):
        self._show_clear_button = show_clear
        self._options = []
        self._option_order = option_order or ["clear", "pin", "action"]
        self.wrapped_widget = None
        self.container = None

        # Register options if provided
        if options:
            for option in options:
                self.add_option(option)

    # ------------------------------------------------------------------
    # Option plugin management
    # ------------------------------------------------------------------

    def add_option(self, option):
        """Add an option plugin instance.

        Args:
            option: An option plugin instance (must have a widget property)
        """
        if option not in self._options:
            self._options.append(option)
            if self.container:
                self._rebuild_layout()

    def remove_option(self, option):
        """Remove an option plugin instance."""
        if option in self._options:
            self._options.remove(option)
            if self.container:
                self._rebuild_layout()

    def get_options(self):
        """Get all registered option plugins."""
        return list(self._options)

    def _rebuild_layout(self):
        """Rebuild the layout with all current options."""
        if not self.container or not self.wrapped_widget:
            return

        layout = self.container.layout()

        # Clear all widgets except the wrapped widget
        while layout.count() > 1:
            item = layout.takeAt(1)
            if item.widget():
                item.widget().setParent(None)

        # Sort and add option widgets
        sorted_options = self._sort_options()
        for option in sorted_options:
            if hasattr(option, "widget"):
                widget = option.widget
                widget.setParent(self.container)
                self._wire_option_widget(widget, option, self.container)
                layout.addWidget(widget)

        self._update_sizing()

    def _sort_options(self):
        """Sort options based on option_order."""
        from .options.action import MenuOption, ActionOption
        from .options.clear import ClearOption
        from .options.pin_values import PinValuesOption

        def get_priority(option):
            if isinstance(option, ClearOption):
                try:
                    return self._option_order.index("clear")
                except ValueError:
                    return 0
            elif isinstance(option, PinValuesOption):
                try:
                    return self._option_order.index("pin")
                except ValueError:
                    return 1
            elif isinstance(option, (MenuOption, ActionOption)):
                try:
                    return self._option_order.index("action")
                except ValueError:
                    return 2
            else:
                return 999

        return sorted(self._options, key=get_priority)

    def _update_sizing(self):
        """Update sizing for all option widgets."""
        if not self.wrapped_widget:
            return
        h = self.wrapped_widget.height() or self.wrapped_widget.sizeHint().height()
        for option in self._options:
            if hasattr(option, "widget"):
                option.widget.setFixedSize(h, h)
        if self.container:
            self.container.adjustSize()

    def _assign_option_object_name(self, option_widget, option):
        """Ensure option widgets have stable, descriptive object names."""
        if option_widget is None:
            return

        parent_name = "optionHost"
        if self.wrapped_widget is not None:
            parent_name = (
                self.wrapped_widget.objectName()
                or self.wrapped_widget.__class__.__name__
            )

        option_type = option.__class__.__name__ if option is not None else "Option"
        option_widget.setObjectName(f"{parent_name}_{option_type}")

    def _propagate_option_context(self, option_widget):
        """Copy contextual attributes from the wrapped widget to option widgets."""
        if option_widget is None or not self.wrapped_widget:
            return

        host = self.wrapped_widget

        # Provide UI + Switchboard references when available
        for attr in ("ui", "sb"):
            if hasattr(host, attr):
                setattr(option_widget, attr, getattr(host, attr, None))

        # Mirror helper lambdas that the main window injects
        if hasattr(host, "base_name"):
            option_widget.base_name = host.base_name
        else:
            option_widget.base_name = lambda: option_widget.objectName()

        if hasattr(host, "legal_name"):
            option_widget.legal_name = host.legal_name
        else:
            option_widget.legal_name = lambda: option_widget.objectName()

        # Allow downstream code to find the originating widget if needed
        option_widget.option_host = host

    def _wire_option_widget(self, option_widget, option, container):
        """Wire up an option widget with naming, context, and callbacks."""
        if option_widget is None:
            return

        self._assign_option_object_name(option_widget, option)
        self._propagate_option_context(option_widget)

        if hasattr(option, "on_wrap"):
            option.on_wrap(self, container)

    # ------------------------------------------------------------------
    # Clear button helpers
    # ------------------------------------------------------------------

    @property
    def show_clear(self):
        """Get clear button state."""
        return self._show_clear_button

    @show_clear.setter
    def show_clear(self, value):
        """Set clear button visibility."""
        self._show_clear_button = value
        from .options.clear import ClearOption

        for option in self._options:
            if isinstance(option, ClearOption):
                option.widget.setVisible(value)
                return

    def set_clear_button_visible(self, visible=True):
        """Enable or disable the clear button."""
        self.show_clear = visible

    def _is_text_widget(self, widget):
        """Check if the widget can benefit from a clear button."""
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
    # Wrapping
    # ------------------------------------------------------------------

    def wrap(self, wrapped_widget: QtWidgets.QWidget):
        """Wrap target widget with option buttons.

        Args:
            wrapped_widget: The widget to wrap

        Returns:
            OptionBoxContainer: The container holding the widget and buttons
        """
        self.wrapped_widget = wrapped_widget

        # Create container
        parent = wrapped_widget.parent()
        container = OptionBoxContainer(parent)

        # Replace original widget in parent layout
        if parent and parent.layout():
            parent.layout().replaceWidget(wrapped_widget, container)
        else:
            container.move(wrapped_widget.pos())

        # Create layout
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(wrapped_widget)

        # Add clear option if needed
        if self._show_clear_button and self._is_text_widget(wrapped_widget):
            from .options.clear import ClearOption

            self.add_option(ClearOption(wrapped_widget))

        # Sort and add option widgets
        sorted_options = self._sort_options()
        option_widgets = []
        for option in sorted_options:
            if hasattr(option, "set_wrapped_widget"):
                option.set_wrapped_widget(wrapped_widget)

            if hasattr(option, "widget"):
                widget = option.widget
                widget.setParent(container)
                self._wire_option_widget(widget, option, container)
                layout.addWidget(widget)
                option_widgets.append(widget)

        # Apply border styling
        self._apply_border_styling(wrapped_widget, option_widgets)

        # Finalize
        container.adjustSize()
        h = wrapped_widget.height() or wrapped_widget.sizeHint().height()

        for option in self._options:
            if hasattr(option, "widget"):
                option.widget.setFixedSize(h, h)

        wrapped_widget.setMinimumHeight(h)
        container.adjustSize()
        self.container = container
        container.show()

        return container

    def _apply_border_styling(self, wrapped_widget, option_widgets=None):
        """Apply border styling to prevent double borders."""
        existing_style = wrapped_widget.styleSheet()
        wrapped_widget.setStyleSheet(
            existing_style + "; border-right-width: 0px; border-right-style: none;"
        )

        if option_widgets:
            # Remove left border from first option widget
            first_widget = option_widgets[0]
            first_style = first_widget.styleSheet()
            first_widget.setStyleSheet(
                first_style
                + "; border-left-width: 0px; border-left-style: none; border-left-color: transparent;"
            )

            # Remove right border from all except last
            for widget in option_widgets[:-1]:
                existing_style = widget.styleSheet()
                widget.setStyleSheet(
                    existing_style
                    + "; border-right-width: 0px; border-right-style: none; border-right-color: transparent;"
                )


# Alias for existing imports
OptionBoxWithOrdering = OptionBox
