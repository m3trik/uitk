# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtWidgets
from uitk.widgets.menu import Menu
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay


class ComboBox(QtWidgets.QComboBox, AttributesMixin, RichText, TextOverlay):
    """ """

    returnPressed = QtCore.Signal()
    beforePopupShown = QtCore.Signal()
    beforePopupHidden = QtCore.Signal()

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        """ """
        self.menu = Menu(self, mode="option")

        self.view().installEventFilter(self)
        self.set_attributes(**kwargs)

    @property
    def items(self):
        """Get a list of each items's text or it's data if it exists from the standard model/view.

        Returns:
            (list)
        """
        return [
            self.itemData(i) if self.itemData(i) else self.itemText(i)
            for i in range(self.count())
        ]

    def block_signals(fn):
        """A decorator that blocks signals before executing a function, and unblocks them after.

        Parameters:
            fn (obj): The function to be decorated.
        """

        def wrapper(self, *args, **kwargs):
            self.blockSignals(True)  # prevent triggering currentIndexChanged
            rtn = fn(self, *args, **kwargs)
            self.blockSignals(False)
            return rtn

        return wrapper

    @block_signals
    def add(self, items, header=None, clear=True, ascending=False):
        """Add items to the combobox's standard modelView without triggering any signals.

        Parameters:
            items (str/list)(dict): A string, list of strings, or dict with 'string':data pairs to fill the comboBox with.
            header (str): An optional value for the first index of the comboBox's list.
            clear (bool): Clear any previous items before adding new.
            ascending (bool): Insert in ascending order. New item(s) will be added to the top of the list.

        Returns:
            (list) comboBox's current item list minus any header.

        Example:
            comboBox.add(["Import file", "Import Options"], "Import")
            comboBox.add({'Import file':<obj>, "Import Options":<obj>}, "Import") #example of adding items with data.
        """
        if not isinstance(items, (str, list, set, tuple, dict)):
            raise TypeError(
                f"Incorrect datatype. Expected str, list, set, tuple, or dict, got {type(items)}"
            )

        # Get the current index before refreshing list. avoid negative values.
        index = self.currentIndex() if self.currentIndex() > 0 else 0

        if clear:
            self.clear()

        if isinstance(items, str):
            items = [items]
        if isinstance(items, (list, tuple, set)):
            items = {i: None for i in items}

        for item, data in items.items():
            if item is not None:
                if ascending:
                    self.insertItem(0, item, data)
                else:
                    self.addItem(item, data)
        if header:
            self.insertItem(-1, header)

        self.setCurrentIndex(index)

        return items

    @block_signals
    def currentData(self):
        """Get the data at the current index.

        Returns:
            () data
        """
        index = self.currentIndex()
        return self.itemData(index)

    @block_signals
    def setCurrentData(self, value):
        """Sets the data for the current index.

        Parameters:
            value () = The current item's data value.
        """
        index = self.currentIndex()
        self.setItemData(index, value)

    @block_signals
    def currentText(self):
        """Get the text at the current index.

        Returns:
            (str)
        """
        index = self.currentIndex()
        return self.richText(index)

    @block_signals
    def setCurrentText(self, text):
        """Sets the text for the current index.

        Parameters:
            item (str): The current item's text value.
        """
        index = self.currentIndex()
        self.setRichText(text, index)

    @block_signals
    def setItemText(self, index, text):
        """Set the text at the given index.
        Override for setItemText built-in method.

        Parameters:
            item (str): Item text.
            index (int): Item index
        """
        self.setRichText(text, index)

    @block_signals
    def setCurrentItem(self, i):
        """Sets the current item from the given item text or index without triggering any signals.

        Parameters:
            i (str)(int): item text or item index
        """
        try:  # set by item index:
            self.setCurrentIndex(self.items.index(i))
        except Exception:  # set by item text:
            try:
                self.setCurrentText(i)
            except Exception as e:
                if i:
                    print(f"{__file__}: setCurrentItem: {e}")

    def showPopup(self):
        """Show the popup menu."""
        width = self.sizeHint().width()
        self.view().setMinimumWidth(width)

        self.beforePopupShown.emit()
        super().showPopup()

    def hidePopup(self):
        """ """
        self.beforePopupHidden.emit()
        super().hidePopup()

    def clear(self):
        """ """
        super().clear()

    def keyPressEvent(self, event):
        """ """
        if event.key() == QtCore.Qt.Key_Return and not event.isAutoRepeat():
            self.returnPressed.emit()
            self.setEditable(False)

        super().keyPressEvent(event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv
    )  # return the existing QApplication object, or create a new one if none exists.

    cmb = ComboBox(popupStyle="qmenu")
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

# deprecated ---------------------
