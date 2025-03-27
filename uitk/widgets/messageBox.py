# !/usr/bin/python
# coding=utf-8
from qtpy import QtCore, QtWidgets
from uitk.widgets.mixins.attributes import AttributesMixin


class MessageBox(QtWidgets.QMessageBox, AttributesMixin):
    """Displays a message box with HTML formatting for a set time before closing.

    Parameters:
        location (str)(point) = move the messagebox to the specified location. Can be given as a qpoint or string value. default is: 'topMiddle'
        timeout (int): time in seconds before the messagebox auto closes.
    """

    buttonMapping = {
        "Ok": QtWidgets.QMessageBox.Ok,
        "Open": QtWidgets.QMessageBox.Open,
        "Save": QtWidgets.QMessageBox.Save,
        "Cancel": QtWidgets.QMessageBox.Cancel,
        "Close": QtWidgets.QMessageBox.Close,
        "Discard": QtWidgets.QMessageBox.Discard,
        "Apply": QtWidgets.QMessageBox.Apply,
        "Reset": QtWidgets.QMessageBox.Reset,
        "RestoreDefaults": QtWidgets.QMessageBox.RestoreDefaults,
        "Help": QtWidgets.QMessageBox.Help,
        "SaveAll": QtWidgets.QMessageBox.SaveAll,
        "Yes": QtWidgets.QMessageBox.Yes,
        "YesToAll": QtWidgets.QMessageBox.YesToAll,
        "No": QtWidgets.QMessageBox.No,
        "NoToAll": QtWidgets.QMessageBox.NoToAll,
        "Abort": QtWidgets.QMessageBox.Abort,
        "Retry": QtWidgets.QMessageBox.Retry,
        "Ignore": QtWidgets.QMessageBox.Ignore,
        "NoButton": QtWidgets.QMessageBox.NoButton,
        None: QtWidgets.QMessageBox.NoButton,
    }

    def __init__(
        self,
        parent=None,
        location="topMiddle",
        align="left",
        timeout=None,
        **kwargs,
    ):
        QtWidgets.QMessageBox.__init__(self, parent)

        self.setWindowModality(QtCore.Qt.NonModal)
        self.setStandardButtons(QtWidgets.QMessageBox.NoButton)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowFlags(
            QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool
            | QtCore.Qt.FramelessWindowHint
        )

        self.setTextFormat(QtCore.Qt.RichText)

        self.location = location
        self.align = align

        # Always initialize the timer
        self.menu_timer = QtCore.QTimer(self)
        self.menu_timer.setSingleShot(True)
        self.menu_timer.timeout.connect(self.autoClose)

        # Start the timer only if timeout is set and valid
        if timeout is not None and timeout > 0:
            self.timeout = timeout
        else:
            self.timeout = None

        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    def setStandardButtons(self, *buttons):
        """Set the standard buttons for the message box. Defaults to no buttons if none are provided."""
        if not buttons:
            # Set to no buttons if none are provided
            super().setStandardButtons(QtWidgets.QMessageBox.NoButton)
            return

        standardButtons = QtWidgets.QMessageBox.StandardButtons()
        for button in buttons:
            if isinstance(button, str):
                button = button.capitalize()  # Normalize the string
                standardButtons |= self.buttonMapping.get(
                    button, QtWidgets.QMessageBox.NoButton
                )
            elif isinstance(button, QtWidgets.QMessageBox.StandardButton):
                standardButtons |= button

        super().setStandardButtons(standardButtons)

    def move_(self, location) -> None:
        # Get the screen's geometry
        screen = QtWidgets.QApplication.screens()[0]
        rect = screen.geometry()

        offset_x = self.sizeHint().width() / 2
        offset_y = self.sizeHint().height() / 2

        if location == "topMiddle":
            point = QtCore.QPoint(rect.width() / 2 - offset_x, rect.top() + 150)
        elif location == "bottomRight":
            point = QtCore.QPoint(rect.width() - offset_x, rect.height() - offset_y)
        elif location == "topLeft":
            point = QtCore.QPoint(rect.left() + offset_x, rect.top() + offset_y)
        elif location == "bottomLeft":
            point = QtCore.QPoint(rect.left() + offset_x, rect.height() - offset_y)
        else:  # default to the middle of the screen if location is not recognized
            point = QtCore.QPoint(
                rect.width() / 2 - offset_x, rect.height() / 2 - offset_y
            )

        self.move(point)

    def _setPrefixStyle(self, string) -> str:
        """Set style for specific keywords in the given string."""
        style = {
            "Error:": '<hl style="color:red;">Error:</hl>',
            "Warning:": '<hl style="color:yellow;">Warning:</hl>',
            "Note:": '<hl style="color:blue;">Note:</hl>',
            "Result:": '<hl style="color:green;">Result:</hl>',
        }

        for k, v in style.items():
            string = string.replace(k, v)

        return string

    def _setHTML(self, string) -> str:
        """<p style="font-size:160%;">text</p>
        <p style="text-align:center;">Centered paragraph.</p>
        <p style="font-family:courier;">This is a paragraph.</p>

        Returns:
            (str)
        """
        style = {
            "<p>": '<p style="color:white;">',  # paragraph <p>' </p>'
            "<hl>": '<hl style="color:yellow; font-weight: bold;">',  # heading <h1>' </h1>'
            "<body>": '<body style="color;">',  # body <body> </body>
            "<b>": '<b style="font-weight: bold;">',  # bold <b> </b>
            "<strong>": '<strong style="font-weight: bold;">',  # <strong> </strong>
            "<mark>": '<mark style="background-color: grey">',  # highlight <mark> </mark>
        }

        for k, v in style.items():
            string = string.replace(k, v)

        return string

    def _setFontColor(self, string, color) -> str:
        """ """
        return "<font color=" + color + ">" + string + "</font>"

    def _setBackgroundColor(self, string, color):
        """ """
        return '<mark style="background-color:' + color + '">' + string + "</mark>"

    def _setFontSize(self, string, size) -> str:
        """ """
        return "<font size=" + str(size) + ">" + string + "</font>"

    def setText(
        self, string, fontColor="white", backgroundColor="rgb(50,50,50)", fontSize=5
    ) -> None:
        """Set the text to be displayed with the specified alignment unless overridden by HTML.

        Parameters:
            string (str): The text or HTML content to display.
            fontColor (str): The text color.
            backgroundColor (str): The background color of the text.
            fontSize (int): The font size of the text.
        """
        # Apply default alignment if not overridden in the HTML
        if "align=" not in string:
            string = f"<div align='{self.align}'>{string}</div>"

        s = self._setPrefixStyle(string)
        s = self._setHTML(s)
        s = self._setFontColor(s, fontColor)
        s = self._setBackgroundColor(s, backgroundColor)
        s = self._setFontSize(s, fontSize)

        super().setText(s)

    def autoClose(self):
        # Close the MessageBox if no standard buttons are set
        if self.standardButtons() == QtWidgets.QMessageBox.NoButton:
            self.accept()

    def showEvent(self, event):
        # Start the timer when the MessageBox is shown and a timeout is set
        if self.timeout is not None:
            self.menu_timer.start(
                self.timeout * 1000
            )  # Convert seconds to milliseconds
        self.move_(self.location)
        super().showEvent(event)

    def hideEvent(self, event):
        # Stop the timer when the MessageBox is hidden
        self.menu_timer.stop()
        super().hideEvent(event)

    def exec_(self):
        # Call the original exec_ method and store the result
        resultEnum = super().exec_()

        # Convert the enum result to a string using the buttonMapping
        resultString = next(
            (k for k, v in MessageBox.buttonMapping.items() if v == resultEnum),
            None,
        )

        # Return the string representation of the result
        return resultString


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = MessageBox()
    w.setText("Warning: Backface Culling is now <hl>OFF</hl>")
    w.show()

    sys.exit(app.exec_())

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------

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
