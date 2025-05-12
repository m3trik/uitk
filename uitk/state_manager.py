import json
from typing import Any, Optional
from qtpy import QtWidgets, QtCore
import pythontk as ptk


class StateManager(ptk.LoggingMixin):
    """Manages persistent widget state using QSettings."""

    def __init__(self):
        super().__init__()
        self.logger.setLevel("WARNING")
        self._defaults = {}

    def _get_settings(self, widget: QtWidgets.QWidget) -> QtCore.QSettings:
        return widget.ui.settings

    def _get_state_key(
        self, widget: QtWidgets.QWidget, prefix: str = ""
    ) -> Optional[str]:
        if not getattr(widget, "restore_state", False):
            return None

        name = widget.objectName()
        signal_name = widget.derived_type and widget.ui.sb.default_signals.get(
            widget.derived_type
        )

        if not name or not signal_name:
            self.logger.debug(f"Invalid state key: name={name}, signal={signal_name}")
            return None

        return f"{prefix}{name}/{signal_name}"

    def _get_current_value(self, widget: QtWidgets.QWidget) -> Any:
        signal_name = widget.derived_type and widget.ui.sb.default_signals.get(
            widget.derived_type
        )
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
            pass

    def _set_index_value(self, widget, value):
        try:
            widget.setCurrentIndex(int(value))
        except (ValueError, TypeError):
            pass

    def _set_boolean_value(self, widget, value):
        widget.setChecked(value in ["true", "True", 1, "1"])

    def _set_check_state(self, widget, value):
        try:
            widget.setCheckState(QtCore.Qt.CheckState(int(value)))
        except (ValueError, TypeError):
            pass

    def store(self, widget: QtWidgets.QWidget, value: Any) -> None:
        key = self._get_state_key(widget)
        if not key:
            return

        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value)
        elif not isinstance(value, (int, float, str, bool)):
            return

        self._get_settings(widget).setValue(key, value)

    def restore(self, widget: QtWidgets.QWidget) -> None:
        key = self._get_state_key(widget)
        if not key:
            return

        # Capture the default only once
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
        except EOFError:
            return

    def clear(self, widget: QtWidgets.QWidget) -> None:
        key = self._get_state_key(widget)
        if key:
            self._get_settings(widget).remove(key)
            self.logger.debug(f"Cleared stored state for: {key}")

    def apply(self, widget: QtWidgets.QWidget, value: Any) -> None:
        signal_name = widget.derived_type and widget.ui.sb.default_signals.get(
            widget.derived_type
        )
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

    def has_default(self, widget: QtWidgets.QWidget) -> bool:
        """Check if a widget has a stored default value."""
        return widget in self._defaults

    def reset_all(self) -> None:
        """Reset all widgets with stored defaults to their original values."""
        for widget, default_value in self._defaults.items():
            self.apply(widget, default_value)

    def reset(self, widget: QtWidgets.QWidget) -> None:
        if widget in self._defaults:
            self.apply(widget, self._defaults[widget])


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    from uitk import Switchboard


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------
