# !/usr/bin/python
# coding=utf-8
"""Pin Values option for OptionBox - allows pinning/saving widget values.

This is an example template showing how to create a custom option plugin
that maintains state and interacts with the wrapped widget.
"""

from qtpy import QtWidgets, QtCore
from ._options import ButtonOption


class PinValuesOption(ButtonOption):
    """A pin button option that saves and restores widget values.

    This option allows users to "pin" the current value of a widget,
    making it easy to save and restore values. Useful for workflows
    where users need to remember and reuse specific settings.

    Example:
        line_edit = QtWidgets.QLineEdit()
        pin_option = PinValuesOption(line_edit)
        option_box = OptionBox(options=[pin_option])
        option_box.wrap(line_edit)

    Features:
        - Click to pin/unpin current value
        - Visual feedback (icon changes when pinned)
        - Automatically restores pinned value
        - Works with most input widgets
    """

    # Signal emitted when value is pinned/unpinned
    value_pinned = QtCore.Signal(bool, object)  # (is_pinned, value)

    def __init__(self, wrapped_widget=None, auto_restore=True):
        """Initialize the pin values option.

        Args:
            wrapped_widget: The widget whose values to pin
            auto_restore: If True, automatically restore pinned value on widget changes
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon="pin",
            tooltip="Pin value",
            callback=self._toggle_pin,
        )
        self._pinned = False
        self._pinned_value = None
        self._auto_restore = auto_restore
        self._original_icon = "pin"
        self._pinned_icon = "pinned"

    def create_widget(self):
        """Create the pin button widget."""
        button = super().create_widget()

        if not button.objectName():
            button.setObjectName("pinButton")

        button.setProperty("class", "PinButton")
        button.setCheckable(True)  # Make it a toggle button
        return button

    def setup_widget(self):
        """Setup the widget and connect signals."""
        super().setup_widget()

        # Update icon when toggled
        self._widget.toggled.connect(self._update_icon)

    def _toggle_pin(self):
        """Toggle the pin state."""
        if self._pinned:
            self._unpin()
        else:
            self._pin()

    def _pin(self):
        """Pin the current value."""
        if not self.wrapped_widget:
            return

        value = self._get_widget_value()
        if value is not None:
            self._pinned_value = value
            self._pinned = True
            self._widget.setChecked(True)
            self._widget.setToolTip(f"Unpin value: {value}")

            # Emit signal
            if hasattr(self, "value_pinned"):
                self.value_pinned.emit(True, value)

    def _unpin(self):
        """Unpin the value."""
        self._pinned = False
        self._pinned_value = None
        self._widget.setChecked(False)
        self._widget.setToolTip("Pin value")

        # Emit signal
        if hasattr(self, "value_pinned"):
            self.value_pinned.emit(False, None)

    def _update_icon(self, checked):
        """Update the icon based on pin state."""
        from uitk.widgets.mixins.icon_manager import IconManager

        icon = self._pinned_icon if checked else self._original_icon
        IconManager.set_icon(self._widget, icon, size=(17, 17))

    def _get_widget_value(self):
        """Get the current value from the wrapped widget."""
        if not self.wrapped_widget:
            return None

        widget = self.wrapped_widget

        # Try different value getters
        if hasattr(widget, "text"):
            return widget.text()
        elif hasattr(widget, "value"):
            return widget.value()
        elif hasattr(widget, "currentText"):
            return widget.currentText()
        elif hasattr(widget, "toPlainText"):
            return widget.toPlainText()
        elif hasattr(widget, "isChecked"):
            return widget.isChecked()

        return None

    def _set_widget_value(self, value):
        """Set the value on the wrapped widget."""
        if not self.wrapped_widget or value is None:
            return

        widget = self.wrapped_widget

        # Try different value setters
        try:
            if hasattr(widget, "setText"):
                widget.setText(str(value))
            elif hasattr(widget, "setValue"):
                widget.setValue(value)
            elif hasattr(widget, "setCurrentText"):
                widget.setCurrentText(str(value))
            elif hasattr(widget, "setPlainText"):
                widget.setPlainText(str(value))
            elif hasattr(widget, "setChecked"):
                widget.setChecked(bool(value))
        except Exception as e:
            print(f"PinValuesOption: Error setting value: {e}")

    def restore_pinned_value(self):
        """Restore the pinned value to the widget."""
        if self._pinned and self._pinned_value is not None:
            self._set_widget_value(self._pinned_value)

    @property
    def is_pinned(self):
        """Check if a value is currently pinned."""
        return self._pinned

    @property
    def pinned_value(self):
        """Get the currently pinned value."""
        return self._pinned_value

    def on_wrap(self, option_box, container):
        """Called when option is wrapped - setup auto-restore if enabled."""
        super().on_wrap(option_box, container)

        if self._auto_restore and self.wrapped_widget:
            # Connect to widget value changes to restore pinned value
            self._setup_auto_restore()

    def _setup_auto_restore(self):
        """Setup auto-restore functionality."""
        widget = self.wrapped_widget

        # Connect to appropriate signals for auto-restore
        if hasattr(widget, "textChanged"):
            widget.textChanged.connect(self._check_restore)
        elif hasattr(widget, "valueChanged"):
            widget.valueChanged.connect(self._check_restore)
        elif hasattr(widget, "currentTextChanged"):
            widget.currentTextChanged.connect(self._check_restore)

    def _check_restore(self):
        """Check if we should restore the pinned value."""
        if not self._pinned or not self._auto_restore:
            return

        current_value = self._get_widget_value()
        if current_value != self._pinned_value:
            # Value changed, restore it
            self.restore_pinned_value()
