# !/usr/bin/python
# coding=utf-8
from typing import Dict, Union, Optional
from qtpy import QtWidgets, QtGui, QtCore
from uitk.widgets.messageBox import MessageBox
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.menu_mixin import MenuMixin


class SpinBox(QtWidgets.QDoubleSpinBox, MenuMixin, AttributesMixin):
    """Unified SpinBox that supports both integer and float behavior, plus custom display values.

    Features:
    - Custom value-to-text mapping (e.g. -1 -> "Auto")
    - Dynamic step size adjustments with modifiers (Alt, Ctrl)
    - Lazy float/int behavior (using decimals)
    """

    # Class-level menu defaults
    _menu_defaults = {"hide_on_leave": True}

    def __init__(self, parent=None, **kwargs):
        QtWidgets.QDoubleSpinBox.__init__(self, parent)

        self.msgBox = MessageBox(self, timeout=1)
        self._custom_display_map: Dict[float, str] = {}
        self._custom_value_map: Dict[str, float] = {}

        # Default behavior: behave like QSpinBox (0 decimals) if no kwargs suggest otherwise
        if "decimals" not in kwargs:
            self.setDecimals(0)

        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    def value(self) -> Union[float, int]:
        """Return integer if decimals is 0, else float."""
        val = super().value()
        if self.decimals() == 0:
            return int(val)
        return val

    def setCustomDisplayValues(self, *args):
        """Set a mapping of values to custom display strings.

        Examples:
            setCustomDisplayValues({-1: "Auto"})
            setCustomDisplayValues(-1, "Auto")
        """
        if len(args) == 1 and isinstance(args[0], dict):
            mapping = args[0]
        elif len(args) == 2:
            mapping = {args[0]: args[1]}
        else:
            raise ValueError("setCustomDisplayValues expects a dict or (value, label)")

        self._custom_display_map = {float(k): v for k, v in mapping.items()}
        self._custom_value_map = {v: float(k) for k, v in mapping.items()}
        self.update()

    def textFromValue(self, value: float) -> str:
        """Format the text displayed in the spin box."""
        # Check custom mapping first
        for custom_val, custom_text in self._custom_display_map.items():
            if abs(value - custom_val) < 1e-9:  # Float comparison
                return custom_text

        # Standard formatting (remove trailing zeros/decimal if integer-like)
        return "{:g}".format(value)

    def valueFromText(self, text: str) -> float:
        """Convert text back to value."""
        if text in self._custom_value_map:
            return self._custom_value_map[text]
        return super().valueFromText(text)

    def validate(self, text: str, pos: int) -> object:
        """Validate input, allowing custom display strings."""
        if text in self._custom_value_map:
            return (QtGui.QValidator.Acceptable, text, pos)

        # Allow partial matches for custom strings
        for custom_text in self._custom_value_map:
            if custom_text.startswith(text):
                return (QtGui.QValidator.Intermediate, text, pos)

        return super().validate(text, pos)

    def setPrefix(self, prefix: str) -> None:
        """Add a tab space after the prefix for clearer display."""
        formatted_prefix = f"{prefix}\t"
        super().setPrefix(formatted_prefix)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """Handle wheel events with modifier keys."""
        modifiers = QtGui.QGuiApplication.keyboardModifiers()

        if modifiers == QtCore.Qt.AltModifier:
            self.adjustStepSize(event)
        elif modifiers == QtCore.Qt.ControlModifier:
            if modifiers & QtCore.Qt.AltModifier:  # Ctrl+Alt
                self.decreaseValueWithSmallStep(event)
            else:  # Ctrl only
                self.increaseValueWithLargeStep(event)
        elif modifiers == (QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier):
            self.decreaseValueWithSmallStep(event)
        else:
            super().wheelEvent(event)

    def adjustStepSize(self, event: QtGui.QWheelEvent) -> None:
        """Adjust the step size dynamically based on the Alt modifier key."""
        current_step = self.singleStep()
        decimals = self.decimals()
        if event.delta() > 0:
            new_step = max(
                min(current_step / 10, self.maximum() - self.value()), 10**-decimals
            )
        else:
            new_step = min(current_step * 10, self.maximum() - self.value())
        new_step = round(new_step, decimals)
        self.setSingleStep(new_step)
        self.message(f"Step: <font color='yellow'>{new_step}</font>")

    def increaseValueWithLargeStep(self, event: QtGui.QWheelEvent) -> None:
        """Increase the spin box value by a larger step when Ctrl is pressed."""
        current_step = self.singleStep()
        adjustment = current_step * 10
        self.setValue(
            self.value() + adjustment
            if event.delta() > 0
            else self.value() - adjustment
        )
        self.message(f"Step: <font color='yellow'>{adjustment}</font>")

    def decreaseValueWithSmallStep(self, event: QtGui.QWheelEvent) -> None:
        """Decrease the spin box value by a smaller step when Ctrl+Alt is pressed."""
        current_step = self.singleStep()
        decimals = self.decimals()
        adjustment = max(current_step / 10, 10**-decimals)
        self.setValue(
            self.value() + adjustment
            if event.delta() > 0
            else self.value() - adjustment
        )
        self.message(f"Step: <font color='yellow'>{adjustment}</font>")

    def message(self, text: str) -> None:
        """Display a temporary message box with the given text."""
        self.msgBox.setText(text)
        self.msgBox.show()
