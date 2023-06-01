# !/usr/bin/python
# coding=utf-8
from PySide2 import QtWidgets, QtCore
from uitk.widgets.menu import MenuInstance
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay


class CheckBox(QtWidgets.QCheckBox, MenuInstance, AttributesMixin, RichText, TextOverlay):
    """ """

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)

        self.setCheckBoxRichTextStyle(
            self.isChecked()
        )  # set the initial style for rich text depending on the current state.
        self.stateChanged.connect(
            lambda state: self.setCheckBoxRichTextStyle(state)
        )  # set the style on future state changes.

        # override built-ins
        self.text = self.richText
        self.setText = self.setRichText
        self.sizeHint = self.richTextSizeHint

        self.set_attributes(**kwargs)

    def setCheckBoxRichTextStyle(self, state):
        """ """
        if self.hasRichText:
            self.setRichTextStyle(textColor="black" if state > 0 else "white")

    def checkState_(self):
        """Get the state of a checkbox as an integer value.
        Simplifies working with tri-state checkboxes.
        """
        if self.isTristate():
            state = {
                QtCore.Qt.CheckState.Unchecked: 0,
                QtCore.Qt.CheckState.PartiallyChecked: 1,
                QtCore.Qt.CheckState.Checked: 2,
            }
            return state[self.checkState()]

        else:
            return 1 if self.isChecked() else 0

    def set_check_state(self, state):
        """Set the state of a checkbox as an integer value.
        Simplifies working with tri-state checkboxes.

        Parameters:
                state (int)(bool): 0 or False: unchecked, 1 or True: checked.
                        If tri-state: 0: unchecked, 1: paritally checked, 2: checked.
        """
        if self.isTristate():
            s = {
                0: QtCore.Qt.CheckState.Unchecked,
                1: QtCore.Qt.CheckState.PartiallyChecked,
                2: QtCore.Qt.CheckState.Checked,
            }
            return self.setCheckState(s[state])

        else:
            self.setChecked(state)

    def mousePressEvent(self, event):
        """
        Parameters:
                event (QEvent)

        Returns:
                (QEvent)
        """
        if event.button() == QtCore.Qt.RightButton:
            if self.ctx_menu:
                self.ctx_menu.show()

        super().mousePressEvent(event)

    def showEvent(self, event):
        """
        Parameters:
                event=<QEvent>
        """
        # self.setTextOverlay('±', alignment='AlignRight')

        super().showEvent(event)


if __name__ == "__main__":
    import sys
    from PySide2.QtCore import QSize

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv
    )  # return the existing QApplication object, or create a new one if none exists.

    w = CheckBox(
        parent=None,
        setObjectName="chk000",
        setText="A Check Box <b>w/Rich TextMixin</b>",
        resize=QSize(125, 45),
        setWhatsThis="",
        setChecked=False,
        setVisible=True,
    )
    # w.show()

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

# Deprecated:
