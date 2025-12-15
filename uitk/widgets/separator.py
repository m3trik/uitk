# !/usr/bin/python
# coding=utf-8
from typing import Optional
from qtpy import QtWidgets, QtCore

# From this package:
from uitk.widgets.mixins.attributes import AttributesMixin


class Separator(QtWidgets.QFrame, AttributesMixin):
    """A simple horizontal separator with optional title and styling."""

    def __init__(
        self, parent: Optional[QtWidgets.QWidget] = None, title: str = "", **kwargs
    ):
        super().__init__(parent)

        self.setProperty("class", "separator")
        self.setFrameShape(QtWidgets.QFrame.HLine)
        self.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.setFixedHeight(9)  # Total height including padding
        self.setLineWidth(1)
        self.setMidLineWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        # Disable mouse interaction - separators are purely visual
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

        # Title label (hidden by default)
        self._title_label: Optional[QtWidgets.QLabel] = None

        if title:
            self.title = title

        self.set_attributes(self, **kwargs)

    @property
    def title(self) -> str:
        """Get the separator title."""
        if self._title_label:
            return self._title_label.text()
        return ""

    @title.setter
    def title(self, value: str) -> None:
        """Set the separator title. Empty string hides the title."""
        if value:
            if not self._title_label:
                self._create_title_label()
            self._title_label.setText(value)
            self._title_label.show()
            # Adjust height to accommodate title
            self.setFixedHeight(12)
            # Change to NoFrame when showing title
            self.setFrameShape(QtWidgets.QFrame.NoFrame)
        elif self._title_label:
            self._title_label.hide()
            self.setFixedHeight(9)
            self.setFrameShape(QtWidgets.QFrame.HLine)

    def setTitle(self, value: str) -> None:
        """Set the separator title (alias for title property)."""
        self.title = value

    def _create_title_label(self) -> None:
        """Create the title label widget."""
        self._title_label = QtWidgets.QLabel(self)
        self._title_label.setProperty("class", "separator-title")
        self._title_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

    def resizeEvent(self, event) -> None:
        """Position the title label on resize."""
        super().resizeEvent(event)
        if self._title_label and self._title_label.isVisible():
            self._title_label.adjustSize()
            # Center the label vertically, align left with small margin
            y = (self.height() - self._title_label.height()) // 2
            self._title_label.move(4, y)


# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from qtpy.QtCore import QSize

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv
    )  # return the existing QApplication object, or create a new one if none exists.

    w = Separator(setStyleSheet="background-color: red;", setMinimumSize=QSize(200, 1))
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
