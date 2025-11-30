# !/usr/bin/python
# coding=utf-8
import warnings
from qtpy import QtWidgets, QtGui, QtCore
from uitk.widgets.mixins import AttributesMixin, ConvertMixin


class ColorSwatch(QtWidgets.QPushButton, AttributesMixin, ConvertMixin):
    """Color picker button that displays and stores a selectable color value."""

    initializeRequested = QtCore.Signal()

    def __init__(self, parent=None, color=None, settings=None, **kwargs):
        super().__init__(parent)

        self._initialColor = color
        self._settings = None

        # Connect the custom signal to the initialization method
        self.initializeRequested.connect(
            self.initializeColor, QtCore.Qt.UniqueConnection
        )

        self.setMinimumSize(10, 10)
        # self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)  # Assume this method is defined elsewhere

        # Set settings last to ensure it can trigger initialization if necessary
        self.settings = settings

    @property
    def color(self):
        """Return the current color."""
        return self._color

    @color.setter
    def color(self, value):
        # Attempt to convert the value to a QColor using the ConvertMixin's to_qobject method
        converted_color = ConvertMixin.to_qobject(value, QtGui.QColor)

        if converted_color and isinstance(converted_color, QtGui.QColor):
            self._color = converted_color
        else:
            # Log an error or handle the case where conversion fails
            print(f"Conversion to QColor failed or invalid color: {value}")
            self._color = QtGui.QColor(QtCore.Qt.white)  # Default fallback color

        self.updateBackgroundColor()
        self.saveColor()

    @property
    def settings(self):
        return self._settings

    @settings.setter
    def settings(self, value):
        self._settings = value
        # Defer the initialization trigger to ensure all properties, like objectName, are set
        QtCore.QTimer.singleShot(0, self.initializeRequested.emit)

    def saveColor(self):
        if not self.objectName():
            warnings.warn(
                "Attempting to save settings for a ColorSwatch widget without an objectName set.",
                RuntimeWarning,
            )
            return  # Early return to avoid attempting to save without an objectName

        if self.canSaveLoadColor():
            self.settings.setValue(
                f"colorSwatch/{self.objectName()}/color", self._color.name()
            )

    def loadColor(self):
        if not self.objectName():
            warnings.warn(
                "Attempting to load settings for a ColorSwatch widget without an objectName set.",
                RuntimeWarning,
            )
            return  # Early return to avoid attempting to load without an objectName

        if self.canSaveLoadColor():
            colorValue = self.settings.value(
                f"colorSwatch/{self.objectName()}/color", None
            )

            # If colorValue is None (indicating no value was previously stored),
            # use a default QColor object instead of QtCore.Qt.white
            if colorValue is None:
                colorValue = QtGui.QColor(QtCore.Qt.white)

            self.color = colorValue

    def canSaveLoadColor(self):
        """Check if the widget is in a state that allows saving or loading the color."""
        return self.settings is not None and self.objectName()

    def initializeColor(self):
        self.loadColor()

        if not hasattr(self, "_color") or not self._color.isValid():
            self._color = (
                self._initialColor
                if self._initialColor is not None
                else QtGui.QColor(QtCore.Qt.white)
            )

        self.updateBackgroundColor()

    def updateBackgroundColor(self):
        """Updates the widget's background color based on the check state."""
        textColor = "black" if self._color.lightness() > 127 else "white"
        self.setStyleSheet(
            f"QPushButton {{"
            f"background-color: {self._color.name()};"
            f"color: {textColor};"
            f"border-radius: 5px;"
            f"border: 8px solid transparent;"  # Border color changes based on checked state
            f"}}"
            f"QPushButton:checked {{"
            f"border-color: {self._color.name()};"
            f"}}"
        )

    def mouseDoubleClickEvent(self, event):
        """Open a color dialog on double click to select a new color."""
        colorDialog = QtWidgets.QColorDialog(self._color, self)
        colorDialog.setStyleSheet(
            """
            QDialog {
                background-color: #555;
                color: #eee;
            }
            QPushButton {
                background-color: #444;
                border: 1px solid black;
                padding: 5px;
                border-radius: 2px;
                color: #eee;
            }
            QPushButton:hover {
                background-color: #666;
            }
            QPushButton:pressed {
                background-color: #777;
            }
            QLabel, QSpinBox, QLineEdit {
                color: #eee;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                border-left: 1px solid darkgray;
            }
            QSpinBox::up-arrow, QSpinBox::down-arrow {
                width: 7px;
                height: 7px;
            }
        """
        )
        if colorDialog.exec_():
            selectedColor = colorDialog.selectedColor()
            if selectedColor.isValid():
                self.color = selectedColor  # Setter handles updating and saving
        super().mouseDoubleClickEvent(event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from uitk import __package__

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    main_window = QtWidgets.QMainWindow()
    main_window.setWindowTitle("Color Swatch Example")
    main_window.setStyleSheet("QMainWindow {background-color: #555;}")
    main_window.resize(300, 100)

    # Create a widget to serve as the central widget
    central_widget = QtWidgets.QWidget()
    main_window.setCentralWidget(central_widget)

    # Create a layout for the central widget
    layout = QtWidgets.QHBoxLayout(central_widget)

    test_settings = QtCore.QSettings(__package__, "DefaultSettings")
    colors = ("red", "blue", "green", "cyan")
    for index, color in enumerate(colors):  # Use enumerate to get an index
        color_swatch = ColorSwatch(
            color=QtGui.QColor(color),
            settings=test_settings,
            setObjectName=f"colorSwatch{index}",
            set_fixed_size=(50, 50),
            setCheckable=True,
        )
        layout.addWidget(color_swatch)

    main_window.show()

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

# deprecated ---------------------
