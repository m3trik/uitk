# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtGui, QtWidgets
from uitk.widgets.menu import Menu


class AttributeWindow(Menu):
    labelToggled = QtCore.Signal(str, bool)
    valueChanged = QtCore.Signal(str, object)

    def __init__(self, *args, checkable=False, **kwargs):
        super().__init__(*args, **kwargs)

        self.checkable = checkable

        # Initialize the labels and widgets lists
        self.labels = []
        self.widgets = []

        self.type_to_widget = {
            bool: (QtWidgets.QCheckBox, "setChecked", "isChecked", "stateChanged"),
            int: (QtWidgets.QSpinBox, "setValue", "value", "valueChanged"),
            float: (QtWidgets.QDoubleSpinBox, "setValue", "value", "valueChanged"),
            str: (QtWidgets.QLineEdit, "setText", "text", "textChanged"),
            list: (
                QtWidgets.QComboBox,
                "addItems",
                "currentText",
                "currentIndexChanged",
            ),
        }

    def add_attribute(self, attribute_name, attribute_value):
        (
            widget_class,
            set_value_method,
            get_value_method,
            signal_name,
        ) = self.type_to_widget.get(
            type(attribute_value),
            (QtWidgets.QLineEdit, "setText", "text", "textChanged"),
        )

        widget = widget_class(self)
        getattr(widget, set_value_method)(attribute_value)

        # Set boundaries for QSpinBox and QDoubleSpinBox
        if widget_class is QtWidgets.QSpinBox:
            widget.setRange(-2147483648, 2147483647)  # Range for a 32-bit integer
            widget.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        elif widget_class is QtWidgets.QDoubleSpinBox:
            widget.setRange(-1e100, 1e100)  # Large range for a float
            widget.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)

        getattr(widget, signal_name).connect(
            lambda: self.valueChanged.emit(
                attribute_name, getattr(widget, get_value_method)()
            )
        )

        # Create a QCheckBox for the attribute name
        label = QtWidgets.QCheckBox(attribute_name)
        label.setCheckable(self.checkable)
        if self.checkable:
            label.stateChanged.connect(
                lambda state: self.labelToggled.emit(attribute_name, bool(state))
            )

        # Set the size policy to expanding for the label and the widget
        label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum
        )

        widget.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Minimum
        )

        # Get the next available row
        row = 0
        while self.gridLayout.itemAtPosition(row, 0) is not None:
            row += 1

        # Add the QLabel and the widget to the lists
        self.labels.append(label)
        self.widgets.append(widget)

        # Use the add method from Menu to add the label and the widget
        self.add(label, row=row, col=0)
        self.add(widget, row=row, col=1)

        # Set the stretch factor for the label and the widget
        self.gridLayout.setColumnStretch(0, 1)
        self.gridLayout.setColumnStretch(1, 2)

    def showEvent(self, event):
        super().showEvent(event)  # Call the base class showEvent method

        # Get the maximum width among labels
        max_label_width = max(label.sizeHint().width() for label in self.labels)
        # Get the maximum width among widgets
        max_widget_width = max(widget.sizeHint().width() for widget in self.widgets)

        # Set the fixed width for labels and widgets
        for label in self.labels:
            label.setFixedSize(max_label_width, label.size().height())

        for widget in self.widgets:
            widget.setFixedSize(max_widget_width, widget.size().height())


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # Create an AttributeWindow
    window = AttributeWindow()

    # Add some attributes
    window.add_attribute("Name", "Cube")
    # window.add_attribute("Visible", True)
    window.add_attribute("Opacity", 0.5)
    window.add_attribute("Position", [0, 0, 0])
    window.add_attribute("Texture", "path/to/texture.png")

    window.set_style(theme="dark")

    # Show the window
    window.show()

    # Start the QApplication
    sys.exit(app.exec_())

# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------


# Deprecated: -------------------------------------
