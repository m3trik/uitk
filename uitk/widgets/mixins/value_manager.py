# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore
from typing import Any, Optional


class ValueManager:
    """Flexible value getting/setting for most Qt widgets.

    This class provides a unified interface for getting and setting values
    across different widget types, handling their specific APIs automatically.

    Examples:
        # Get value from any widget
        current_value = ValueManager.get_value(widget)

        # Set value on any widget
        ValueManager.set_value(widget, value)

        # Get readable description
        info = ValueManager.get_widget_type_info(widget)
    """

    @staticmethod
    def get_value(widget):
        """Get the current value from a widget.

        Parameters:
            widget: Qt widget to get value from

        Returns:
            The current value of the widget, or None if unsupported
        """
        if hasattr(widget, "value") and callable(widget.value):
            return widget.value()
        elif hasattr(widget, "text") and callable(widget.text):
            return widget.text()
        elif hasattr(widget, "currentText") and callable(widget.currentText):
            return widget.currentText()
        elif hasattr(widget, "currentIndex") and callable(widget.currentIndex):
            return widget.currentIndex()
        elif hasattr(widget, "isChecked") and callable(widget.isChecked):
            return widget.isChecked()
        elif hasattr(widget, "checkState") and callable(widget.checkState):
            return widget.checkState()
        elif hasattr(widget, "toPlainText") and callable(widget.toPlainText):
            return widget.toPlainText()
        else:
            return None

    @staticmethod
    def set_value(widget, value, block_signals=False):
        """Set a value on a widget.

        Parameters:
            widget: Qt widget to set value on
            value: Value to set
            block_signals: Whether to block signals during value setting
        """
        if block_signals:
            widget.blockSignals(True)

        try:
            # Handle different widget types with proper value conversion
            if hasattr(widget, "setValue") and callable(widget.setValue):
                # Numeric widgets (QSpinBox, QDoubleSpinBox, QSlider, etc.)
                try:
                    widget.setValue(
                        float(value)
                        if isinstance(widget, QtWidgets.QDoubleSpinBox)
                        else int(value)
                    )
                except (ValueError, TypeError):
                    # Fallback for invalid numeric values
                    widget.setValue(widget.minimum())

            elif hasattr(widget, "setText") and callable(widget.setText):
                # Text-capable widgets (QLineEdit, QLabel, etc.)
                # Skip icon-only option buttons that should never display text
                if isinstance(widget, QtWidgets.QPushButton):
                    obj_name = widget.objectName() or ""
                    class_prop = widget.property("class") or ""
                    class_prop = (
                        " ".join(class_prop)
                        if isinstance(class_prop, (list, tuple))
                        else str(class_prop)
                    )

                    is_option_button = obj_name in {
                        "actionButton",
                        "optionMenuButton",
                    } or any(
                        token in class_prop
                        for token in ("ActionButton", "OptionMenuButton")
                    )

                    if is_option_button:
                        # Preserve icon-only appearance; state data uses ellipsis placeholder
                        return

                widget.setText(str(value))

            elif hasattr(widget, "setCurrentText") and callable(widget.setCurrentText):
                # QComboBox with text setting
                widget.setCurrentText(str(value))

            elif hasattr(widget, "setCurrentIndex") and callable(
                widget.setCurrentIndex
            ):
                # QComboBox with index setting, QTabWidget, etc.
                if (
                    isinstance(value, int)
                    and 0 <= value < getattr(widget, "count", lambda: float("inf"))()
                ):
                    widget.setCurrentIndex(value)

            elif hasattr(widget, "setChecked") and callable(widget.setChecked):
                # QCheckBox, QRadioButton, checkable QPushButton
                if isinstance(value, str):
                    widget.setChecked(value.lower() in ["true", "1", "yes", "on"])
                else:
                    widget.setChecked(bool(value))

            elif hasattr(widget, "setCheckState") and callable(widget.setCheckState):
                # QCheckBox with tri-state
                if isinstance(value, int):
                    widget.setCheckState(QtCore.Qt.CheckState(value))
                else:
                    widget.setCheckState(
                        QtCore.Qt.CheckState.Checked
                        if bool(value)
                        else QtCore.Qt.CheckState.Unchecked
                    )

            elif hasattr(widget, "setPlainText") and callable(widget.setPlainText):
                # QTextEdit, QPlainTextEdit
                widget.setPlainText(str(value))

        finally:
            if block_signals:
                widget.blockSignals(False)

    @staticmethod
    def get_widget_type_info(widget):
        """Get information about widget type for display purposes.

        Parameters:
            widget: Qt widget to analyze

        Returns:
            str: Human-readable description of the widget and its value
        """
        widget_type = widget.__class__.__name__
        value = ValueManager.get_value(widget)

        # Create a readable description
        if isinstance(
            widget, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)
        ):
            return f"Text: {str(value)[:50]}{'...' if len(str(value)) > 50 else ''}"
        elif isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            return f"Number: {value}"
        elif isinstance(widget, QtWidgets.QComboBox):
            return f"Selection: {value}"
        elif isinstance(widget, (QtWidgets.QCheckBox, QtWidgets.QPushButton)):
            if hasattr(widget, "isChecked"):
                return f"Checked: {value}"
            return f"Button: {widget.text()}"
        else:
            return f"{widget_type}: {value}"

    @staticmethod
    def is_supported_widget(widget):
        """Check if a widget type is supported for value operations.

        Parameters:
            widget: Qt widget to check

        Returns:
            bool: True if widget is supported, False otherwise
        """
        supported_types = (
            QtWidgets.QLineEdit,
            QtWidgets.QTextEdit,
            QtWidgets.QPlainTextEdit,
            QtWidgets.QSpinBox,
            QtWidgets.QDoubleSpinBox,
            QtWidgets.QComboBox,
            QtWidgets.QCheckBox,
            QtWidgets.QRadioButton,
            QtWidgets.QSlider,
            QtWidgets.QPushButton,  # If it has isChecked
        )
        return isinstance(widget, supported_types)

    @staticmethod
    def get_value_by_signal(widget, signal_name):
        """Get widget value based on its primary signal type.

        This method provides compatibility with signal-based systems like StateManager.

        Parameters:
            widget: Qt widget to get value from
            signal_name: Signal name that indicates the value type

        Returns:
            The current value based on signal type, or None if unsupported
        """
        signal_getters = {
            "textChanged": lambda w: w.text() if hasattr(w, "text") else None,
            "valueChanged": lambda w: w.value() if hasattr(w, "value") else None,
            "currentIndexChanged": lambda w: (
                w.currentIndex() if hasattr(w, "currentIndex") else None
            ),
            "toggled": lambda w: w.isChecked() if hasattr(w, "isChecked") else None,
            "stateChanged": lambda w: (
                w.checkState() if hasattr(w, "checkState") else None
            ),
        }

        getter = signal_getters.get(signal_name)
        return getter(widget) if getter else ValueManager.get_value(widget)

    @staticmethod
    def set_value_by_signal(widget, value, signal_name, block_signals=False):
        """Set widget value based on its primary signal type.

        This method provides compatibility with signal-based systems like StateManager.

        Parameters:
            widget: Qt widget to set value on
            value: Value to set
            signal_name: Signal name that indicates the value type
            block_signals: Whether to block signals during value setting
        """
        if block_signals:
            widget.blockSignals(True)

        try:
            signal_setters = {
                "textChanged": lambda w, v: (
                    w.setText(str(v)) if hasattr(w, "setText") else None
                ),
                "valueChanged": lambda w, v: (
                    ValueManager._set_numeric_value(w, v)
                    if hasattr(w, "setValue")
                    else None
                ),
                "currentIndexChanged": lambda w, v: (
                    ValueManager._set_index_value(w, v)
                    if hasattr(w, "setCurrentIndex")
                    else None
                ),
                "toggled": lambda w, v: (
                    ValueManager._set_boolean_value(w, v)
                    if hasattr(w, "setChecked")
                    else None
                ),
                "stateChanged": lambda w, v: (
                    ValueManager._set_check_state(w, v)
                    if hasattr(w, "setCheckState")
                    else None
                ),
            }

            setter = signal_setters.get(signal_name)
            if setter:
                # Special handling for QComboBox to prevent out-of-range errors
                if (
                    isinstance(widget, QtWidgets.QComboBox)
                    and signal_name == "currentIndexChanged"
                    and (not isinstance(value, int) or value >= widget.count())
                ):
                    return
                setter(widget, value)
            else:
                # Fallback to direct value setting
                ValueManager.set_value(
                    widget, value, block_signals=False
                )  # Already blocking

        finally:
            if block_signals:
                widget.blockSignals(False)

    @staticmethod
    def _set_numeric_value(widget, value):
        """Helper method for setting numeric values with error handling."""
        try:
            if isinstance(widget, QtWidgets.QDoubleSpinBox):
                widget.setValue(float(value))
            else:
                widget.setValue(int(float(value)))  # Handle string numbers
        except (ValueError, TypeError):
            # Use widget's current value as fallback
            pass

    @staticmethod
    def _set_index_value(widget, value):
        """Helper method for setting index values with bounds checking."""
        try:
            index = int(value)
            if hasattr(widget, "count") and 0 <= index < widget.count():
                widget.setCurrentIndex(index)
        except (ValueError, TypeError):
            pass

    @staticmethod
    def _set_boolean_value(widget, value):
        """Helper method for setting boolean values with string conversion."""
        try:
            if isinstance(value, str):
                widget.setChecked(value.lower() in ["true", "1", "yes", "on"])
            else:
                widget.setChecked(bool(value))
        except Exception:
            pass

    @staticmethod
    def _set_check_state(widget, value):
        """Helper method for setting check state values."""
        try:
            if isinstance(value, int):
                widget.setCheckState(QtCore.Qt.CheckState(value))
            else:
                state = (
                    QtCore.Qt.CheckState.Checked
                    if bool(value)
                    else QtCore.Qt.CheckState.Unchecked
                )
                widget.setCheckState(state)
        except (ValueError, TypeError):
            pass


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    """Test the WidgetValueManager functionality."""
    import sys
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # Test different widget types
    widgets = [
        QtWidgets.QLineEdit("Hello"),
        QtWidgets.QSpinBox(),
        QtWidgets.QComboBox(),
        QtWidgets.QCheckBox("Check me"),
    ]

    # Set some test values
    widgets[1].setValue(42)
    widgets[2].addItems(["A", "B", "C"])
    widgets[2].setCurrentText("B")
    widgets[3].setChecked(True)

    # Test getting values and info
    for widget in widgets:
        value = ValueManager.get_value(widget)
        info = ValueManager.get_widget_type_info(widget)
        supported = ValueManager.is_supported_widget(widget)
        print(f"{widget.__class__.__name__}: {value} | {info} | Supported: {supported}")

    print("WidgetValueManager test complete!")


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
This utility class provides a consistent interface for working with widget values
across the uitk package. It consolidates value management logic that was previously
duplicated across multiple classes.

Used by:
- StateManager: For widget state persistence
- OptionBox pin values: For saving/restoring widget values  
- Settings persistence: For form value management
- Value validation: For input handling
- Widget testing frameworks: For automated testing

Features:
- Direct widget value getting/setting
- Signal-based value operations (for compatibility with existing systems)
- Automatic type conversion and bounds checking
- Signal blocking support for programmatic changes
- Comprehensive error handling

The class is designed to be extended easily by adding new widget type
support in the get_value and set_value methods.

Consolidation Notes:
- Replaces duplicate value logic from StateManager
- Provides both direct and signal-based APIs for maximum compatibility
- Centralizes widget value operations for consistency across the codebase
"""
