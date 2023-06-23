# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtWidgets
from uitk.widgets.mixins.attributes import AttributesMixin


class MessageBox(QtWidgets.QMessageBox, AttributesMixin):
    """Displays a message box with HTML formatting for a set time before closing.

    Parameters:
        location (str)(point) = move the messagebox to the specified location. Can be given as a qpoint or string value. default is: 'topMiddle'
        timeout (int): time in seconds before the messagebox auto closes.
    """

    def __init__(self, parent=None, location="topMiddle", timeout=2, **kwargs):
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

        self.menu_timer = QtCore.QTimer()
        self.menu_timer.setSingleShot(True)
        self.menu_timer.timeout.connect(self.hide)

        self.setTextFormat(QtCore.Qt.RichText)

        self.location = location

        self.set_attributes(**kwargs)

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
        """Set style for specific keywords in the given string.

        Returns:
                (str)
        """
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
        """
        Returns:
                (str)
        """
        return "<font color=" + color + ">" + string + "</font>"

    def _setBackgroundColor(self, string, color):
        """
        Returns:
                (str)
        """
        return '<mark style="background-color:' + color + '">' + string + "</mark>"

    def _setFontSize(self, string, size) -> str:
        """
        Returns:
                (str)
        """
        return "<font size=" + str(size) + ">" + string + "</font>"

    def setText(
        self, string, fontColor="white", backgroundColor="rgb(50,50,50)", fontSize=5
    ) -> None:
        """Set the text to be displayed.

        Parameters:
                fontColor (str): text color.
                backgroundColor (str): text background color.
                fontSize (int): text size.
        """
        s = self._setPrefixStyle(string)
        s = self._setHTML(s)
        s = self._setFontColor(s, fontColor)
        s = self._setBackgroundColor(s, backgroundColor)
        s = self._setFontSize(s, fontSize)

        super().setText(s)

    def showEvent(self, event) -> None:
        """ """
        self.menu_timer.start(1000)  # 5000 milliseconds = 5 seconds
        self.move_(self.location)

        super().showEvent(event)

    def hideEvent(self, event) -> None:
        """ """
        self.menu_timer.stop()

        super().hideEvent(event)


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = MessageBox()
    w.setText("Warning: Backface Culling is now <hl>Off</hl>")
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

# deprecated: -----------------------------------


# class ShowMessageBox(MessageBox):
#     """Spawns a message box with the given text.
#     Supports HTML formatting.
#     Prints a formatted version of the given string to console, stripped of html tags, to the console.

#     Parameters:
#         message_type (str/optional): The message context type. ex. 'Error', 'Warning', 'Info', 'Result'
#         location (str/QPoint/optional) = move the messagebox to the specified location. default is: 'topMiddle'
#         timeout (int/optional): time in seconds before the messagebox auto closes. default is: 3
#     """

#     def __init__(
#         self,
#         string,
#         message_type="",
#         location="topMiddle",
#         timeout=3,
#         **kwargs,
#     ):
#         super().__init__(
#             QtWidgets.QApplication.instance(), **kwargs
#         )  # Set the QApplication instance as the parent

#         if message_type:
#             string = f"{message_type.capitalize()}: {string}"

#         self.location = location
#         self.timeout = timeout

#         self.setText(string)
#         self.setVisible(True)

#         # strip everything between '<' and '>' (html tags)
#         print(f"# {re.sub('<.*?>', '', string)}")

#     def hideEvent(self, event) -> None:
#         """ """
#         self.menu_timer.stop()

#         super().hideEvent(event)


# def insertText(self, dict_):
#   '''
#   Parameters:
#       dict_ = {dict} - contents to add.  for each key if there is a value, the key and value pair will be added.
#   '''
#   highlight = QtGui.QColor(255, 255, 0)
#   baseColor = QtGui.QColor(185, 185, 185)

#   #populate the textedit with any values
#   for key, value in dict_.items():
#       if value:
#           self.setTextColor(baseColor)
#           self.append(key) #textEdit.append(key+str(value))
#           self.setTextColor(highlight)
#           self.insertPlainText(str(value))
