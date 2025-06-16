# !/usr/bin/python
# coding=utf-8
import json
from typing import Any, Optional
from qtpy import QtWidgets, QtCore
import pythontk as ptk


class StateManager(ptk.LoggingMixin):
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
        """Gets the current value of the widget using its mapped signal getter."""
        signal_name = widget.derived_type and widget.default_signals()
        if not signal_name:
            return None
        getter = {
            "textChanged": lambda w: w.text() if hasattr(w, "text") else None,
            "valueChanged": lambda w: w.value() if hasattr(w, "value") else None,
            "currentIndexChanged": lambda w: (
                w.currentIndex() if hasattr(w, "currentIndex") else None
            ),
            "toggled": lambda w: w.isChecked() if hasattr(w, "isChecked") else None,
            "stateChanged": lambda w: (
                w.checkState() if hasattr(w, "checkState") else None
            ),
        }.get(signal_name)
        return getter(widget) if getter else None

    def _set_numeric_value(self, widget, value):
        try:
            widget.setValue(float(value))
        except (ValueError, TypeError):
            self.logger.debug(f"Could not set numeric value '{value}' on {widget}")

    def _set_index_value(self, widget, value):
        try:
            widget.setCurrentIndex(int(value))
        except (ValueError, TypeError):
            self.logger.debug(f"Could not set index value '{value}' on {widget}")

    def _set_boolean_value(self, widget, value):
        try:
            widget.setChecked(value in ["true", "True", 1, "1"])
        except Exception:
            self.logger.debug(f"Could not set checked state '{value}' on {widget}")

    def _set_check_state(self, widget, value):
        try:
            widget.setCheckState(QtCore.Qt.CheckState(int(value)))
        except (ValueError, TypeError):
            self.logger.debug(f"Could not set check state '{value}' on {widget}")

    def _apply(self, widget: QtWidgets.QWidget, value: Any) -> None:
        """Apply the given value to the widget based on its signal type."""
        signal_name = widget.derived_type and widget.default_signals()
        if not signal_name:
            return

        action_map = {
            "textChanged": lambda w, v: (
                w.setText(str(v)) if hasattr(w, "setText") else None
            ),
            "valueChanged": lambda w, v: (
                self._set_numeric_value(w, v) if hasattr(w, "setValue") else None
            ),
            "currentIndexChanged": lambda w, v: (
                self._set_index_value(w, v) if hasattr(w, "setCurrentIndex") else None
            ),
            "toggled": lambda w, v: (
                self._set_boolean_value(w, v) if hasattr(w, "setChecked") else None
            ),
            "stateChanged": lambda w, v: (
                self._set_check_state(w, v) if hasattr(w, "setCheckState") else None
            ),
        }

        action = action_map.get(signal_name)
        if action:
            try:
                if (
                    isinstance(widget, QtWidgets.QComboBox)
                    and signal_name == "currentIndexChanged"
                    and (not isinstance(value, int) or value >= widget.count())
                ):
                    return
                widget.blockSignals(True)
                action(widget, value)
            finally:
                widget.blockSignals(False)

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
                self._apply(widget, parsed_value)
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
