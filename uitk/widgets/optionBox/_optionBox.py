# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore
from uitk.widgets.mixins.text import RichText
from uitk.widgets.mixins.icon_manager import IconManager
from uitk.widgets.mixins.attributes import AttributesMixin


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

    This class now acts as a plugin host, managing dynamically loaded option plugins.
    """

    def __init__(
        self,
        parent=None,
        action_handler=None,  # Legacy compatibility
        action=None,  # New streamlined API
        menu=None,  # New streamlined API
        show_clear_button=False,  # Legacy compatibility
        show_clear=False,  # New streamlined API
        options=None,  # List of option plugin instances to add
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
        self._options = []  # List of option plugin instances
        self.wrapped_widget = None
        self.container = None

        # Styling (border removal, sizing) is handled purely by QSS now; no inline styles.
        if not self.objectName():
            self.setObjectName("optionBox")

        # Clear any default text to prevent artifacts next to icon
        super().setText("")

        IconManager.set_icon(self, "option_box", size=(17, 17))
        self.clicked.connect(self._handle_click)
        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

        # Register options if provided
        if options:
            for option in options:
                self.add_option(option)

    # ------------------------------------------------------------------
    # Option plugin management
    # ------------------------------------------------------------------

    def add_option(self, option):
        """Add an option plugin instance to this option box.

        Args:
            option: An option plugin instance (must have a widget property)
        """
        if option not in self._options:
            self._options.append(option)
            if self.container:
                self._rebuild_layout()

    def remove_option(self, option):
        """Remove an option plugin instance from this option box."""
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

        # Add all option widgets
        for option in self._options:
            if hasattr(option, "widget"):
                widget = option.widget
                widget.setParent(self.container)
                layout.addWidget(widget)

        # Only add the main option box button if using legacy direct action_handler
        # (not plugin-based options like MenuOption or ActionOption)
        from .options.action import MenuOption, ActionOption

        has_action_plugin = any(
            isinstance(opt, (MenuOption, ActionOption)) for opt in self._options
        )

        if self._action_handler and not has_action_plugin:
            layout.addWidget(self)

        # Update sizing
        self._update_sizing()

    def _update_sizing(self):
        """Update sizing for all option widgets."""
        if not self.wrapped_widget:
            return
        h = self.wrapped_widget.height() or self.wrapped_widget.sizeHint().height()
        self.setFixedSize(h, h)
        for option in self._options:
            if hasattr(option, "widget"):
                option.widget.setFixedSize(h, h)
        if self.container:
            self.container.adjustSize()

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
        # Update clear option if it exists
        from .options.clear import ClearOption

        for option in self._options:
            if isinstance(option, ClearOption):
                option.widget.setVisible(value)
                return

    # ------------------------------------------------------------------
    def set_action_handler(self, handler):
        self._action_handler = handler

    # ------------------------------------------------------------------
    def set_clear_button_visible(self, visible=True):
        """Enable or disable the clear button functionality."""
        self._show_clear_button = visible
        # Update clear option if it exists
        from .options.clear import ClearOption

        for option in self._options:
            if isinstance(option, ClearOption):
                option.widget.setVisible(visible)
                return

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

    def _apply_border_styling(self, wrapped_widget, option_widgets=None):
        """Apply border styling to prevent double borders.

        Args:
            wrapped_widget: The main wrapped widget
            option_widgets: List of option widgets (will remove right border from all except last)
        """
        # Remove right border from wrapped widget using more explicit rule
        # Use border-right-width: 0px and border-right-style: none for complete removal
        existing_style = wrapped_widget.styleSheet()
        wrapped_widget.setStyleSheet(
            existing_style + "; border-right-width: 0px; border-right-style: none;"
        )

        if option_widgets:
            first_widget = option_widgets[0]
            first_style = first_widget.styleSheet()
            first_widget.setStyleSheet(
                first_style
                + "; border-left-width: 0px; border-left-style: none; border-left-color: transparent;"
            )

            # Remove right border from all option widgets except the last
            for widget in option_widgets[:-1]:
                existing_style = widget.styleSheet()
                widget.setStyleSheet(
                    existing_style
                    + "; border-right-width: 0px; border-right-style: none; border-right-color: transparent;"
                )

    def _finalize_container(self, container, wrapped_widget):
        """Finalize container sizing and display."""
        container.adjustSize()
        h = wrapped_widget.height() or wrapped_widget.sizeHint().height()
        self.setFixedSize(h, h)

        # Size all option widgets
        for option in self._options:
            if hasattr(option, "widget"):
                option.widget.setFixedSize(h, h)

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
        if self._show_clear_button and self._is_text_widget(wrapped_widget):
            from .options.clear import ClearOption

            clear_option = ClearOption(wrapped_widget)
            self.add_option(clear_option)

        # Add all option widgets
        option_widgets = []
        for option in self._options:
            # Update option's wrapped_widget reference before accessing .widget
            # This ensures the option knows about the wrapped widget when it's created
            if hasattr(option, "set_wrapped_widget"):
                option.set_wrapped_widget(wrapped_widget)

            if hasattr(option, "widget"):
                widget = option.widget
                widget.setParent(container)
                layout.addWidget(widget)
                option_widgets.append(widget)

        layout.addWidget(self)

        # Apply border styling
        self._apply_border_styling(wrapped_widget, option_widgets)

        # Finalize and return
        return self._finalize_container(container, wrapped_widget)

    # ------------------------------------------------------------------
    def add_clear_button(self):
        """Add a clear button to an already wrapped widget."""
        if not hasattr(self, "container") or not hasattr(self, "wrapped_widget"):
            print("Warning: OptionBox must be wrapped before adding clear button")
            return

        if not self._is_text_widget(self.wrapped_widget):
            print("Warning: Clear button is only useful for text input widgets")
            return

        # Check if clear option already exists
        from .options.clear import ClearOption

        for option in self._options:
            if isinstance(option, ClearOption):
                print("Warning: Clear button already exists")
                return

        # Add clear option
        clear_option = ClearOption(self.wrapped_widget)
        self.add_option(clear_option)
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


class OptionBoxWithOrdering(OptionBox):
    """OptionBox that supports configurable option ordering"""

    def __init__(self, *args, option_order=None, **kwargs):
        self._option_order = option_order or ["clear", "action"]
        super().__init__(*args, **kwargs)

    def wrap(self, wrapped_widget: QtWidgets.QWidget):
        """Wrap target widget with configurable option ordering."""
        self.wrapped_widget = wrapped_widget
        container, layout = self._create_container_and_layout(wrapped_widget)

        # Create clear option if needed
        clear_option = None
        if self._show_clear_button and self._is_text_widget(wrapped_widget):
            from .options.clear import ClearOption

            clear_option = ClearOption(wrapped_widget)
            self.add_option(clear_option)

        # Check if we're using the plugin system or legacy direct action_handler
        # If MenuOption or ActionOption is in _options, don't add self (the main button)
        # because the plugin creates its own button
        from .options.action import MenuOption, ActionOption
        from .options.clear import ClearOption

        has_action_plugin = any(
            isinstance(opt, (MenuOption, ActionOption)) for opt in self._options
        )

        # Sort options based on option_order
        def get_option_priority(option):
            """Get priority for sorting options based on option_order."""
            if isinstance(option, ClearOption):
                try:
                    return self._option_order.index("clear")
                except ValueError:
                    return 0
            elif isinstance(option, (MenuOption, ActionOption)):
                try:
                    return self._option_order.index("action")
                except ValueError:
                    return 1
            else:
                # Unknown option types go last
                return 999

        sorted_options = sorted(self._options, key=get_option_priority)

        # Add plugin option widgets in sorted order
        option_widgets = []
        for option in sorted_options:
            if hasattr(option, "widget"):
                widget = option.widget
                widget.setParent(container)
                layout.addWidget(widget)
                option_widgets.append(widget)

        # Only add the main option box button (self) if:
        # 1. We have a direct _action_handler set (legacy mode), AND
        # 2. We're NOT using action plugins (which create their own buttons)
        if self._action_handler and not has_action_plugin:
            layout.addWidget(self)

        # Apply border styling
        self._apply_border_styling(wrapped_widget, option_widgets)

        # Finalize and return
        return self._finalize_container(container, wrapped_widget)
