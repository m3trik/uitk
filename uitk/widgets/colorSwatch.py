# !/usr/bin/python
# coding=utf-8
import warnings
from qtpy import QtWidgets, QtGui, QtCore
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.convert import ConvertMixin


class ColorSwatch(QtWidgets.QPushButton, AttributesMixin, ConvertMixin):
    """Color picker button that displays and stores a selectable color value."""

    initializeRequested = QtCore.Signal()
    colorChanged = QtCore.Signal(QtGui.QColor)

    def __init__(self, parent=None, color=None, settings=None, **kwargs):
        super().__init__(parent)

        # Default/override color used when nothing is persisted. May be set
        # externally AFTER construction: mayatk/blendertk Color ID build
        # swatches from a .ui (so they get no `color=` kwarg) and then assign
        # `button._initialColor` to seed the per-column pastel default.
        # initializeColor() honors it as the no-settings fallback.
        self._initialColor = color
        self._settings = None
        self._keep_square = False

        # Resolve a valid _color synchronously so `.color` / updateBackgroundColor
        # work before the deferred initializeColor() runs — reading `.color`
        # (or any repaint) before the event loop spun previously raised
        # AttributeError, since _color was only created in that deferred call.
        # initializeColor() still overrides this from persisted settings.
        converted = (
            ConvertMixin.to_qobject(color, QtGui.QColor) if color is not None else None
        )
        self._color = (
            converted
            if isinstance(converted, QtGui.QColor) and converted.isValid()
            else QtGui.QColor(QtCore.Qt.white)
        )

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
        self.colorChanged.emit(self._color)

    @property
    def keep_square(self):
        """Whether the swatch keeps a 1:1 aspect ratio, tracking its width."""
        return self._keep_square

    @keep_square.setter
    def keep_square(self, value):
        # Opt-in: when True the swatch pins its height to its current width on
        # every resize, so it stays square as its grid column stretches. Off by
        # default so explicit setFixedSize callers are left untouched.
        self._keep_square = bool(value)
        if self._keep_square:
            self._apply_square()

    def _apply_square(self):
        w = self.width()
        if w > 0 and self.height() != w:
            self.setFixedHeight(w)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._keep_square:
            self._apply_square()

    @property
    def settings(self):
        return self._settings

    @settings.setter
    def settings(self, value):
        self._settings = value
        # Defer the initialization trigger to ensure all properties, like objectName, are set
        QtCore.QTimer.singleShot(0, self.initializeRequested.emit)

    def saveColor(self):
        if self.settings is None:
            return

        if not self.objectName():
            warnings.warn(
                "Attempting to save settings for a ColorSwatch widget without an objectName set.",
                RuntimeWarning,
            )
            return  # Early return to avoid attempting to save without an objectName

        # HexArgb (#AARRGGBB), not name() (#RRGGBB): the picker enables
        # ShowAlphaChannel, so alpha must survive the round-trip. Legacy
        # #RRGGBB values still load (alpha defaults to opaque).
        self.settings.setValue(
            f"colorSwatch/{self.objectName()}/color",
            self._color.name(QtGui.QColor.HexArgb),
        )

    def loadColor(self) -> bool:
        """Apply this swatch's persisted color, if one exists.

        Returns:
            bool: True if a saved value was found and applied; False otherwise
                (so initializeColor can fall back to _initialColor).
        """
        if self.settings is None:
            return False

        if not self.objectName():
            warnings.warn(
                "Attempting to load settings for a ColorSwatch widget without an objectName set.",
                RuntimeWarning,
            )
            return False  # Early return to avoid attempting to load without an objectName

        colorValue = self.settings.value(f"colorSwatch/{self.objectName()}/color", None)

        # Nothing persisted yet — let initializeColor apply the _initialColor
        # fallback (or keep the color resolved synchronously in __init__).
        if colorValue is None:
            return False

        self.color = colorValue
        return True

    def canSaveLoadColor(self):
        """Check if the widget is in a state that allows saving or loading the color."""
        return self.settings is not None and self.objectName()

    def initializeColor(self):
        # _color is resolved synchronously in __init__; loadColor overrides it
        # from persisted settings when present. With nothing persisted, honor
        # _initialColor — which may have been set externally after construction
        # (the mayatk/blendertk Color ID pastel defaults) — instead of leaving
        # the __init__ white fallback in place.
        if not self.loadColor() and self._initialColor is not None:
            converted = ConvertMixin.to_qobject(self._initialColor, QtGui.QColor)
            if isinstance(converted, QtGui.QColor) and converted.isValid():
                self._color = converted

        # Update UI without emitting signal
        self.updateBackgroundColor()

    def updateBackgroundColor(self):
        """Updates the widget's background color based on the check state."""
        textColor = "black" if self._color.lightness() > 127 else "white"
        # Fixed black outline so light fills don't blend into the panel.
        self.setStyleSheet(
            f"QPushButton {{"
            f"background-color: {self._color.name()};"
            f"color: {textColor};"
            f"border-radius: 5px;"
            f"border: 1px solid black;"
            f"}}"
            f"QPushButton:checked {{"
            f"border-color: {self._color.name()};"
            f"}}"
        )

    def mouseDoubleClickEvent(self, event):
        """Open a color dialog on double click to select a new color."""
        if event.button() != QtCore.Qt.LeftButton:
            super().mouseDoubleClickEvent(event)
            return

        # Don't call super — it internally calls mousePressEvent which
        # would toggle the checked state a second time on double-click.
        event.accept()

        colorDialog = QtWidgets.QColorDialog(self._color, self)
        colorDialog.setOption(QtWidgets.QColorDialog.ShowAlphaChannel, True)
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

        # Store original color for revert on Cancel
        original_color = self._color

        # Enable live updates
        def update_live(color):
            self.color = color

        colorDialog.currentColorChanged.connect(update_live)

        if colorDialog.exec_():
            self.color = colorDialog.selectedColor()
        else:
            # Revert to original color on Cancel (unless we want to keep "Apply" effect?
            # Standard dialog behavior is Cancel reverts everything.
            # "Apply" usually commits. but since we only have live update...)
            self.color = original_color


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
