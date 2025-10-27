# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore
from uitk.widgets.menu import Menu
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay


class CheckBox(QtWidgets.QCheckBox, AttributesMixin, RichText, TextOverlay):
    """ """

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)

        # Set the initial style for rich text depending on the current state.
        self.set_checkbox_rich_text_style(self.isChecked())
        # Set the style on future state changes.
        self.stateChanged.connect(
            lambda state: self.set_checkbox_rich_text_style(state)
        )

        # Override built-ins
        self.text = self.richText
        self.setText = self.setRichText
        self.sizeHint = self.richTextSizeHint
        self.menu = Menu(
            self, trigger_button="right", fixed_item_height=20, hide_on_leave=True
        )

        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    def set_checkbox_rich_text_style(self, state):
        """ """
        if self.has_rich_text:
            self.set_rich_text_style(textColor="black" if state > 0 else "white")

    def checkState(self):
        """Get the state of a checkbox as an integer value.
        Simplifies working with tri-state checkboxes.
        """
        if self.isTristate():
            state = {
                QtCore.Qt.CheckState.Unchecked: 0,
                QtCore.Qt.CheckState.PartiallyChecked: 1,
                QtCore.Qt.CheckState.Checked: 2,
            }
            return state[super().checkState()]
        else:
            return 1 if self.isChecked() else 0

    def setCheckState(self, state):
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
            return super().setCheckState(s[state])
        else:
            self.setChecked(state)

    def hitButton(self, pos: QtCore.QPoint) -> bool:
        """Overridden method from QAbstractButton, used internally by Qt to decide whether a mouse press event
        should change the checkbox's state.

        This implementation extends the clickable area to the entire widget's bounds (including empty space),
        not just the checkbox and its label.

        Parameters:
            pos (QPoint): The position of the mouse event.

        Returns:
            bool: True if the position of the mouse event is within the widget's bounds, otherwise False.
        """
        return QtCore.QRect(QtCore.QPoint(0, 0), self.size()).contains(pos)

    def mousePressEvent(self, event):
        """Overridden method from QWidget to handle mouse press events.

        This implementation checks if the event is a right click or a left click.
        For a right click, it shows the context menu if one is defined.
        For a left click, it toggles the state of the checkbox.

        Parameters:
            event (QMouseEvent): The mouse event.

        Note:
            Other mouse events are passed to the parent class.
        """
        # if event.button() == QtCore.Qt.RightButton:
        #     if self.menu:
        #         self.menu.show()

        if self.isTristate():
            # The next_state dictionary defines the order in which states should be cycled.
            next_state = {
                QtCore.Qt.CheckState.Unchecked: QtCore.Qt.CheckState.PartiallyChecked,
                QtCore.Qt.CheckState.PartiallyChecked: QtCore.Qt.CheckState.Checked,
                QtCore.Qt.CheckState.Checked: QtCore.Qt.CheckState.Unchecked,
            }
            # Change the checkbox's state.
            self.setCheckState(next_state[self.checkState()])
        else:
            super().mousePressEvent(event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from qtpy.QtCore import QSize

    # Return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = CheckBox(
        parent=None,
        setObjectName="chk000",
        setText="A Check Box <b>w/Rich TextMixin</b>",
        resize=QSize(125, 45),
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
