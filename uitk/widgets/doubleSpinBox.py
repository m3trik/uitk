# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtGui, QtCore
from uitk.widgets.messageBox import MessageBox
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.menu_mixin import MenuMixin


class DoubleSpinBox(QtWidgets.QDoubleSpinBox, MenuMixin, AttributesMixin):
    """Custom QDoubleSpinBox with enhanced step size adjustment capabilities.
    Includes handling for Alt, Ctrl, and Ctrl+Alt modifiers for dynamic step size adjustment.
    """

    def __init__(self, parent=None, **kwargs):
        QtWidgets.QDoubleSpinBox.__init__(self, parent)

        # Customize standalone menu provided by MenuMixin
        self.menu.trigger_button = "right"
        self.menu.fixed_item_height = 20
        self.menu.hide_on_leave = True
        self.msgBox = MessageBox(self, timeout=1)

        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    def textFromValue(self, value: float) -> str:
        """Format the text displayed in the spin box, removing trailing zeros and unnecessary decimal points."""
        return "{:g}".format(value)

    def setPrefix(self, prefix: str) -> None:
        """Add a tab space after the prefix for clearer display."""
        formatted_prefix = f"{prefix}\t"
        super().setPrefix(formatted_prefix)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """Handle wheel events with modifier keys to adjust the step size or value dynamically."""
        modifiers = QtGui.QGuiApplication.keyboardModifiers()

        if modifiers == QtCore.Qt.AltModifier:
            self.adjustStepSize(event)
        elif modifiers == QtCore.Qt.ControlModifier:
            self.decreaseValueWithSmallStep(event)
        elif modifiers == (QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier):
            self.increaseValueWithLargeStep(event)
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
        """Decrease the spin box value by a smaller step when Ctrl+Alt is pressed, fine-tuning the adjustment."""
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


# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from qtpy.QtCore import QSize

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv
    )  # return the existing QApplication object, or create a new one if none exists.

    w = DoubleSpinBox(
        parent=None,
        setObjectName="button_test",
        setPrefix="Prefix:",
        resize=QSize(125, 45),
        # setVisible=True,
    )

    w.set_attributes(set_limits=(-100000, 100000, 1, 4))

    w.show()
    sys.exit(app.exec_())


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
