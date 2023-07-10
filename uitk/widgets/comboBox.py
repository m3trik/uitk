# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtWidgets
from uitk.widgets.menu import Menu
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay


class ComboBox(QtWidgets.QComboBox, AttributesMixin, RichText, TextOverlay):
    """Custom ComboBox widget with additional features and custom signal handling."""

    before_popup_shown = QtCore.Signal()
    before_popup_hidden = QtCore.Signal()
    on_editing_finished = QtCore.Signal(str)

    def __init__(self, parent=None, double_click_interval=100, **kwargs):
        super().__init__(parent)
        self.menu = Menu(self, mode="option")  # Initialize context menu

        # Initialize other properties for handling double click and editing
        self.lastClickTime = QtCore.QTime.currentTime()
        self.double_click_interval = 500
        self.doubleClicked = False
        self.editingInProgress = False
        self.latestEditedText = ""

        self.set_attributes(**kwargs)

    @property
    def items(self):
        return [
            self.itemData(i) if self.itemData(i) else self.itemText(i)
            for i in range(self.count())
        ]

    def block_signals(fn):
        def wrapper(self, *args, **kwargs):
            self.blockSignals(True)
            rtn = fn(self, *args, **kwargs)
            self.blockSignals(False)
            return rtn

        return wrapper

    @block_signals
    def add(
        self,
        x,
        data=None,
        header=None,
        clear=True,
        ascending=False,
        _recursion=False,
        **kwargs,
    ):
        """Add items to the combobox's standard modelView without triggering any signals.

        Parameters:
            x (str/list/dict): A string, list of strings, or dict with 'string':data pairs to fill the comboBox with.
            data (optional): The data associated with the items.
            header (str, optional): An optional value for the first index of the comboBox's list.
            clear (bool, optional): Whether to clear any previous items before adding new. Defaults to True.
            ascending (bool, optional): Whether to insert in ascending order. If True, new item(s) will be added to the top of the list. Defaults to False.
            _recursion (bool, optional): Internal use only. Differentiates between the initial call and recursive calls.
            kwargs: Arbitrary keyword arguments.

        Returns:
            widget/list: The added widget or list of added widgets.

        Raises:
            TypeError: If the type of 'x' is unsupported.
        """
        if not _recursion and clear:
            self.clear()

        if isinstance(x, dict):
            return [
                self.add(key, val, ascending=ascending, _recursion=True, **kwargs)
                for key, val in x.items()
            ]
        elif isinstance(x, (list, tuple, set)):
            return [
                self.add(item, data, ascending=ascending, _recursion=True, **kwargs)
                for item in x
            ]
        elif isinstance(x, zip):
            return [
                self.add(item, data, ascending=ascending, _recursion=True, **kwargs)
                for item, d in x
            ]
        elif isinstance(x, map):
            return [
                self.add(item, data, ascending=ascending, _recursion=True, **kwargs)
                for item in list(x)
            ]
        elif isinstance(x, str):
            if x is not None:
                if ascending:
                    self.insertItem(0, x, data)
                else:
                    self.addItem(x, data)
            return x
        else:
            raise TypeError(
                f"Unsupported item type: expected str or a collection (list, tuple, set, map, zip, dict), but got '{type(x)}'"
            )

        if not _recursion and header:
            self.insertItem(0, header)

        if not _recursion:
            self.setCurrentIndex(0)

        return x

    @block_signals
    def currentData(self):
        return self.itemData(self.currentIndex())

    @block_signals
    def setCurrentData(self, value):
        self.setItemData(self.currentIndex(), value)

    @block_signals
    def currentText(self):
        return self.richText(self.currentIndex())

    @block_signals
    def setCurrentText(self, text):
        self.setRichText(text, self.currentIndex())

    @block_signals
    def setItemText(self, index, text):
        self.setRichText(text, index)

    @block_signals
    def setCurrentItem(self, i):
        try:
            self.setCurrentIndex(self.items.index(i))
        except Exception:
            try:
                self.setCurrentText(i)
            except Exception as e:
                if i:
                    print(f"{__file__}: setCurrentItem: {e}")

    def showPopup(self):
        self.view().setMinimumWidth(self.sizeHint().width())
        self.before_popup_shown.emit()
        super().showPopup()

    def hidePopup(self):
        self.before_popup_hidden.emit()
        super().hidePopup()

    def mousePressEvent(self, event):
        clickTime = QtCore.QTime.currentTime()
        elapsed = clickTime.msecsTo(self.lastClickTime) * -1
        if elapsed < self.double_click_interval:
            self.double_click_behavior()
            self.doubleClicked = True
        else:
            self.doubleClicked = False
        self.lastClickTime = clickTime
        event.accept()

    def mouseReleaseEvent(self, event):
        if not self.doubleClicked and event.button() == QtCore.Qt.LeftButton:
            if self.view().isVisible():
                self.hidePopup()
            else:
                self.showPopup()
        event.accept()

    def double_click_behavior(self):
        """Sets the ComboBox to editable mode on double click, selecting all text and disconnecting any existing slots from signals."""
        self.setEditable(True)
        QtCore.QTimer.singleShot(100, self.hidePopup)
        self.editingIndex = self.currentIndex()
        lineEdit = self.lineEdit()
        currentText = self.currentText()
        lineEdit.setText(currentText)
        self.latestEditedText = currentText
        lineEdit.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        lineEdit.selectAll()
        try:
            lineEdit.textEdited.disconnect()
        except Exception:
            pass
        try:
            lineEdit.editingFinished.disconnect()
        except Exception:
            pass
        QtCore.QTimer.singleShot(
            100, lambda: lineEdit.textEdited.connect(self.save_edited_text)
        )
        QtCore.QTimer.singleShot(
            100, lambda: lineEdit.editingFinished.connect(self.make_uneditable_delayed)
        )

    def save_edited_text(self, text):
        """Save the latest edited text.

        Parameters:
            text (str): The text entered by the user.
        """
        self.latestEditedText = text

    def replace_item_text(self):
        """Replaces the current item's text with the text in the QLineEdit."""
        currentIndex = self.currentIndex()
        newText = self.latestEditedText.strip()
        self.setItemText(currentIndex, newText)
        self.setCurrentIndex(currentIndex)
        self.update()

    def make_uneditable_delayed(self):
        """Delays the call to 'make_uneditable' by 100 ms."""
        QtCore.QTimer.singleShot(100, self.make_uneditable)

    def make_uneditable(self):
        """Reverts the ComboBox back to uneditable mode, disconnects signals, and emits 'on_editing_finished' signal."""
        if not self.editingInProgress:
            self.replace_item_text()
            self.lineEdit().editingFinished.disconnect(self.make_uneditable_delayed)
            self.editingInProgress = False
            self.on_editing_finished.emit(self.currentText())
            self.lineEdit().textEdited.disconnect(self.save_edited_text)
            self.setEditable(False)

    def keyPressEvent(self, event):
        """Overrides key press event. If editable and 'Enter' is pressed, emits 'editingFinished' signal, otherwise proceeds with default keyPressEvent."""
        if self.isEditable() and event.key() == QtCore.Qt.Key_Return:
            self.lineEdit().editingFinished.emit()
        else:
            super().keyPressEvent(event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    cmb = ComboBox()
    cmb.show()
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
