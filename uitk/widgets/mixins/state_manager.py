# !/usr/bin/python
# coding=utf-8
import json
from typing import Any, Optional
from qtpy import QtWidgets, QtCore
import pythontk as ptk
from uitk.widgets.mixins.value_manager import ValueManager


class StateManager(ptk.LoggingMixin):
    """Manages widget state persistence using QSettings.

    This class has been refactored to use WidgetValueManager for all value
    getting/setting operations, eliminating code duplication and ensuring
    consistent behavior across the codebase.

    Widget Attributes:
    - restore_state (bool): If True, widget state is saved/restored. Default: True
    - block_signals_on_restore (bool): If True, signals are blocked during state
      restoration to prevent side effects. Set to False to allow signals during
      restore (useful for widgets that need to trigger updates). Default: True

    Protections:
    - Skips applying None values to text-based widgets to prevent clearing valid text
    - Only saves primitive types (int, float, str, bool) to prevent state corruption
    - Handles non-stateful signals (like 'clicked') by not triggering state sync
    """

    def __init__(self, qsettings: QtCore.QSettings):
        super().__init__()
        self.logger.setLevel("WARNING")
        self.qsettings = qsettings
        self._defaults = {}

    def _get_settings(self, widget: QtWidgets.QWidget) -> QtCore.QSettings:
        return self.qsettings

    def _get_state_key(
        self, widget: QtWidgets.QWidget, prefix: str = ""
    ) -> Optional[str]:
        """Returns the state key for a widget based on its objectName and signal type."""
        if not getattr(widget, "restore_state", False):
            return None
        name = widget.objectName()
        signal_name = widget.derived_type and widget.default_signals()
        if not name or not signal_name:
            self.logger.debug(f"Invalid state key: name={name}, signal={signal_name}")
            return None
        return f"{prefix}{name}/{signal_name}"

    def _get_current_value(self, widget: QtWidgets.QWidget) -> Any:
        """Get the current value from the widget using ValueManager."""
        signal_name = widget.derived_type and widget.default_signals()
        if signal_name:
            # Use signal-based approach for compatibility
            return ValueManager.get_value_by_signal(widget, signal_name)
        else:
            # Fallback to direct value getting
            return ValueManager.get_value(widget)

    def apply(self, widget: QtWidgets.QWidget, value: Any) -> None:
        """Apply the given value to the widget using ValueManager."""
        signal_name = widget.derived_type and widget.default_signals()

        # Don't apply None values for text-based widgets to prevent clearing valid text
        if value is None:
            if hasattr(widget, "text") and callable(widget.text):
                # Skip applying None to widgets with text (like QPushButton, QLineEdit, etc.)
                self.logger.debug(
                    f"Skipping apply of None value to text widget {widget.objectName()}"
                )
                return

        # Check if widget wants signals blocked during restore (default: True)
        block_signals = getattr(widget, "block_signals_on_restore", True)

        try:
            if signal_name:
                # Use signal-based approach for compatibility with existing behavior
                ValueManager.set_value_by_signal(
                    widget, value, signal_name, block_signals=block_signals
                )
            else:
                # Fallback to direct value setting
                ValueManager.set_value(widget, value, block_signals=block_signals)

        except Exception as e:
            self.logger.debug(
                f"Could not apply value '{value}' to widget {widget}: {e}"
            )

    def save(self, widget: QtWidgets.QWidget, value: Any = None) -> None:
        """Save the current value of the widget to QSettings.

        If no value is provided, it attempts to retrieve it automatically
        using the widget's default signal mapping.

        Parameters:
            widget (QtWidgets.QWidget): The widget whose state should be saved.
            value (Any, optional): The value to save. If None, it will be derived.
        """
        if value is None:
            value = self._get_current_value(widget)

        key = self._get_state_key(widget)
        if not key:
            return

        # Serialize non-primitive values
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value)
        elif not isinstance(value, (int, float, str, bool)):
            self.logger.debug(f"Unsupported type for {key}: {type(value)}")
            return

        try:
            self._get_settings(widget).setValue(key, value)
            self.logger.debug(f"Stored state: {key} -> {value}")
        except Exception as e:
            self.logger.warning(f"Failed to store state for {key}: {e}")

    def load(self, widget: QtWidgets.QWidget) -> None:
        """Load the saved value from QSettings and apply it to the widget."""
        key = self._get_state_key(widget)
        if not key:
            return

        if widget not in self._defaults:
            self._defaults[widget] = self._get_current_value(widget)

        try:
            value = self._get_settings(widget).value(key)
            if value is not None:
                try:
                    parsed_value = json.loads(value)
                except (TypeError, json.JSONDecodeError):
                    parsed_value = value
                self.apply(widget, parsed_value)
                self.logger.debug(f"Loaded state: {key} -> {parsed_value}")
        except EOFError:
            self.logger.debug(f"EOFError reading state for {key}")

    def reset_all(self) -> None:
        """Reset all widgets with stored defaults to their original values."""
        for widget, default_value in self._defaults.items():
            self.apply(widget, default_value)

    def reset(self, widget: QtWidgets.QWidget) -> None:
        """Reset a widget to its default value."""
        if widget in self._defaults:
            self.apply(widget, self._defaults[widget])

    def clear(self, widget: QtWidgets.QWidget) -> None:
        """Removes the stored state for the widget from QSettings."""
        key = self._get_state_key(widget)
        if key:
            self._get_settings(widget).remove(key)
            self.logger.debug(f"Cleared stored state for: {key}")

    def has_default(self, widget: QtWidgets.QWidget) -> bool:
        """Check if a widget has a stored default value."""
        return widget in self._defaults


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ...


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
Refactoring Notes:
==================
This StateManager has been refactored to use WidgetValueManager for all value operations.

Removed methods (now handled by WidgetValueManager):
- _set_numeric_value() -> WidgetValueManager.set_value_by_signal()
- _set_index_value() -> WidgetValueManager.set_value_by_signal()  
- _set_boolean_value() -> WidgetValueManager.set_value_by_signal()
- _set_check_state() -> WidgetValueManager.set_value_by_signal()
- Complex apply() method -> Simplified to use WidgetValueManager
- Signal-based getter dict -> WidgetValueManager.get_value_by_signal()

Benefits:
- Eliminated ~50 lines of duplicate code
- Improved error handling and type conversion
- Consistent behavior with other value management systems
- Single source of truth for widget value operations
"""
