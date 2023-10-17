# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtGui, QtWidgets
from uitk.widgets.menu import Menu
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay


class CustomListView(QtWidgets.QListView):
    def __init__(self, parent):
        super().__init__(parent)
        self.combobox = parent  # Store a reference to the parent combobox

    def paintEvent(self, event):
        if self.combobox.header_text:  # Check if a header is present
            # Get the index of the first item
            index = self.model().index(0, 0)
            # Get the item rectangle
            rect = self.visualRect(index)
            # Check if the event rect intersects with the first item rectangle
            if event.rect().intersects(rect):
                # Adjust the event rect to exclude the first item rectangle
                event = QtGui.QPaintEvent(event.rect().translated(0, rect.height()))
        super().paintEvent(event)


class AlignedComboBox(QtWidgets.QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.header_alignment = QtCore.Qt.AlignLeft
        self.header_text = None  # New field to store the header text
        self.setView(CustomListView(self))  # Set the custom view

    def setHeader(self, header, alignment="left"):
        self.header_text = header
        self.setHeaderAlignment(alignment)
        self.insertItem(0, header)
        self.setCurrentIndex(0)

    def setHeaderAlignment(self, alignment):
        if isinstance(alignment, str):
            alignment_map = {
                "left": QtCore.Qt.AlignLeft,
                "center": QtCore.Qt.AlignCenter,
                "right": QtCore.Qt.AlignRight,
            }
            self.header_alignment = alignment_map.get(
                alignment.lower(), QtCore.Qt.AlignLeft
            )
        elif isinstance(alignment, QtCore.Qt.AlignmentFlag):
            self.header_alignment = alignment
        else:
            raise ValueError(f"Unsupported alignment type: {type(alignment)}")

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(event.rect(), self.palette().base())

        if self.currentIndex() == 0 and self.header_text:
            painter.save()
            rect = event.rect().adjusted(4, 0, 0, 0)  # Adjust margin if needed
            painter.drawText(rect, self.header_alignment, self.currentText())
            painter.restore()

        painter.end()
        super().paintEvent(event)

    def showPopup(self):
        self.model().showingPopup = True  # Set flag before showing popup
        super().showPopup()

    def hidePopup(self):
        self.model().showingPopup = False  # Reset flag after hiding popup
        super().hidePopup()


class ComboBox(AlignedComboBox, AttributesMixin, RichText, TextOverlay):
    """Custom ComboBox widget with additional features and custom signal handling."""

    before_popup_shown = QtCore.Signal()
    on_editing_finished = QtCore.Signal(str)
    on_item_deleted = QtCore.Signal(str)

    def __init__(self, parent=None, editable=False, **kwargs):
        super().__init__(parent)

        self.editable = editable
        self.menu = Menu(self, mode="option", fixed_item_height=20)

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

    def add(
        self,
        x,
        data=None,
        header=None,
        header_alignment="left",
        clear=True,
        restore_index=False,
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
            restore_index (bool, optional): Whether to restore the previous index after clearing. Defaults to False.
            ascending (bool, optional): Whether to insert in ascending order. If True, new item(s) will be added to the top of the list. Defaults to False.
            _recursion (bool, optional): Internal use only. Differentiates between the initial call and recursive calls.
            kwargs: Arbitrary keyword arguments to set attributes for the added items.

        Returns:
            widget/list: The added widget or list of added widgets.

        Raises:
            TypeError: If the type of 'x' is unsupported.
        """
        self.blockSignals(True)

        last_added_data = None
        last_added_text = None

        def add_single(item, data):
            nonlocal last_added_data, last_added_text
            if ascending:
                self.insertItem(0, item, data)
            else:
                self.addItem(item, data)
            last_added_data = data
            last_added_text = item

        if not _recursion and clear:
            prev_index = self.currentIndex()
            self.clear()

        if isinstance(x, dict):
            [add_single(k, v) for k, v in x.items()]
        elif isinstance(x, (list, tuple, set)):
            [add_single(item, data) for item in x]
        elif isinstance(x, (zip, map)):
            [add_single(i, d) for i, d in x]
        elif isinstance(x, str):
            add_single(x, data)
        else:
            raise TypeError(
                f"Unsupported item type: '{type(x)}'. Expected str, list, tuple, set, map, zip, or dict."
            )

        self.set_attributes(**kwargs)

        if not _recursion:
            self.blockSignals(True)

            final_index = 0  # Default index is 0
            if restore_index and prev_index > 0:
                final_index = prev_index

            self.setCurrentIndex(final_index)

            if header:
                self.setHeader(header, header_alignment)

            self.blockSignals(False)
            self.currentIndexChanged.emit(final_index)

    @block_signals
    def removeItem(self, index=None):
        if index is None:
            index = self.currentIndex()
        item_text = self.itemText(index)
        super().removeItem(index)
        self.item_deleted.emit(item_text)

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

    def setCurrentItem(self, i, block_signals=False):
        if block_signals:
            self.blockSignals(True)

        try:
            index = (
                self.items.index(i)
                if isinstance(i, str)
                else i
                if isinstance(i, int)
                else None
            )
        except ValueError:
            raise ValueError(
                f"The item '{i}' was not found in ComboBox. Available items are {self.items}."
            )

        if index is None:
            raise RuntimeError(
                f"Failed to set current item in ComboBox: expected int or str, got {i, type(i)}"
            )

        self.setCurrentIndex(index)

        if block_signals:
            self.blockSignals(False)

    def setEditable(self, editable):
        if editable:
            current_text = self.currentText()
            super().setEditable(True)
            lineEdit = self.lineEdit()
            lineEdit.setText(current_text)
            lineEdit.deselect()
        else:
            lineEdit = self.lineEdit()
            new_text = lineEdit.text()
            super().setEditable(False)
            self.setCurrentText(new_text)
            self.on_editing_finished.emit(new_text)

    def showPopup(self):
        self.view().setMinimumWidth(self.sizeHint().width())
        self.before_popup_shown.emit()
        super().showPopup()

    def keyPressEvent(self, event):
        if self.isEditable() and event.key() == QtCore.Qt.Key_Return:
            self.setEditable(False)

        super().keyPressEvent(event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    cmb = ComboBox()
    cmb.editable = True
    cmb.add(["Item A", "Item B"], header="Items:", header_alignment="center")

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
