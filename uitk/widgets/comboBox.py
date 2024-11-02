# !/usr/bin/python
# coding=utf-8
import re
from qtpy import QtCore, QtGui, QtWidgets
from uitk.signals import Signals
from uitk.widgets.menu import Menu
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay


class CustomStyle(QtWidgets.QProxyStyle):
    def __init__(self, style):
        super().__init__(style)
        self.combo_box = None  # Initialize to None, will be set later

    def drawControl(self, element, opt, painter, widget=None):
        if widget is None or isinstance(widget, AlignedComboBox):
            if element == QtWidgets.QStyle.CE_ComboBoxLabel:
                current_index = self.combo_box.currentIndex()
                if self.combo_box.has_header:
                    current_index -= 1

                if self.combo_box.header_text and (current_index == -1):
                    opt.text = self.combo_box.header_text
                    opt.displayAlignment = self.combo_box.header_alignment
                elif current_index >= 0:
                    opt.text = self.combo_box.itemText(current_index)

        super().drawControl(element, opt, painter, widget)


class AlignedComboBox(QtWidgets.QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.header_text = None
        self.header_alignment = QtCore.Qt.AlignCenter

        self.custom_style = CustomStyle(self.style())
        self.custom_style.combo_box = self  # Set the combo_box reference here
        self.setStyle(self.custom_style)

    def setHeaderText(self, text):
        self.header_text = text
        self.update()

    def setHeaderAlignment(self, alignment):
        if alignment == "left":
            self.header_alignment = QtCore.Qt.AlignLeft
        elif alignment == "right":
            self.header_alignment = QtCore.Qt.AlignRight
        elif alignment == "center":
            self.header_alignment = QtCore.Qt.AlignHCenter
        else:
            self.header_alignment = QtCore.Qt.AlignLeft
        self.update()

    def get_stylesheet_property(self, property_name):
        stylesheet = self.styleSheet()
        match = re.search(f"{property_name} *: *(\d+)", stylesheet)
        if match:
            return int(match.group(1))
        return 0

    def paintEvent(self, event):
        # Always call the parent class's paintEvent to ensure all elements are drawn
        super().paintEvent(event)

        # Then do custom paint for the header text
        if self.header_text and self.currentIndex() == -1:
            painter = QtGui.QPainter(self)

            # Get the text color from the stylesheet
            color = self.palette().color(QtGui.QPalette.Text)
            painter.setPen(color)

            # Retrieve padding from the stylesheet
            left_padding = self.get_stylesheet_property("padding-left")
            right_padding = self.get_stylesheet_property("padding-right")
            top_padding = self.get_stylesheet_property("padding-top")
            bottom_padding = self.get_stylesheet_property("padding-bottom")

            rect = self.rect().adjusted(
                left_padding, top_padding, -right_padding, -bottom_padding
            )

            alignment = self.header_alignment
            painter.drawText(rect, alignment | QtCore.Qt.AlignVCenter, self.header_text)
            painter.end()


class ComboBox(AlignedComboBox, AttributesMixin, RichText, TextOverlay):
    before_popup_shown = QtCore.Signal()
    on_editing_finished = QtCore.Signal(str)
    on_item_deleted = QtCore.Signal(str)

    def __init__(self, parent=None, editable=False, **kwargs):
        super().__init__(parent)
        self.restore_previous_index = False
        self.prev_index = -1
        self.has_header = False
        self.header_text = None

        self.editable = editable
        self.menu = Menu(self, mode="option", fixed_item_height=20)

        self.currentIndexChanged.connect(self.check_index)

        self.set_attributes(**kwargs)

    @property
    def items(self):
        return [
            self.itemData(i) if self.itemData(i) else self.itemText(i)
            for i in range(self.count())
        ]

    @Signals.blockSignals
    def currentData(self):
        return self.itemData(self.currentIndex())

    @Signals.blockSignals
    def setCurrentData(self, value):
        self.setItemData(self.currentIndex(), value)

    @Signals.blockSignals
    def currentText(self):
        return self.richText(self.currentIndex())

    @Signals.blockSignals
    def setCurrentText(self, text):
        self.setRichText(text, self.currentIndex())

    @Signals.blockSignals
    def setItemText(self, index, text):
        self.setRichText(text, index)

    def setAsCurrent(self, i, blockSignals=False):
        if blockSignals:
            self.blockSignals(True)

        try:
            index = (
                self.items.index(i)
                if isinstance(i, str)
                else i if isinstance(i, int) else None
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

        if blockSignals:
            self.blockSignals(False)

    def setCurrentIndex(self, index):
        if index < 0:
            self.blockSignals(True)
        super().setCurrentIndex(index)
        if index < 0:
            self.blockSignals(False)

    def check_index(self, index):
        if self.has_header and index != -1:
            clicked_item_text = self.itemText(index)
            self.setCurrentText(clicked_item_text)
            self.setCurrentIndex(-1)
        elif index == -1 and self.has_header:
            self.setEditText(self.header_text)

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

    def force_header_display(self):
        if self.header_text:
            super().setCurrentIndex(-1)

    def add_header(self, text):
        self.insertItem(0, text)
        self.header_text = text
        self.has_header = True
        self.setCurrentIndex(-1)

    def add_single(self, item, data, ascending):
        if ascending:
            self.insertItem(0, item, data)
        else:
            self.addItem(item, data)

    @Signals.blockSignals
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
        self.restore_previous_index = restore_index
        if restore_index:
            self.prev_index = self.currentIndex()

        if not _recursion and clear:
            self.clear()

        if header:
            self.setHeaderText(header)
            self.setHeaderAlignment(header_alignment)
            self.has_header = True  # Set has_header to True
        else:
            self.has_header = False  # Set has_header to False

        if isinstance(x, dict):
            [self.add_single(k, v, ascending) for k, v in x.items()]
        elif isinstance(x, (list, tuple, set)):
            [self.add_single(item, data, ascending) for item in x]
        elif isinstance(x, (zip, map)):
            [self.add_single(i, d, ascending) for i, d in x]
        elif isinstance(x, str):
            self.add_single(x, data, ascending)
        else:
            raise TypeError(
                f"Unsupported item type: '{type(x)}'. Expected str, list, tuple, set, map, zip, or dict."
            )

        self.set_attributes(**kwargs)

        # At the end of the add method
        if not _recursion:
            if header or self.header_text:
                self.force_header_display()
            # Default index based on header presence
            final_index = -1 if self.header_text else 0

            if restore_index and self.prev_index > -1:
                self.setCurrentIndex(self.prev_index)
                final_index = self.prev_index
            elif self.header_text:
                self.prev_index = -1  # Set prev_index to header index
                final_index = -1  # Force the header display

            self.currentIndexChanged.emit(final_index)

    @Signals.blockSignals
    def removeItem(self, index=None):
        if index is None:
            index = self.currentIndex()
        item_text = self.itemText(index)
        super().removeItem(index)
        self.item_deleted.emit(item_text)

    def showPopup(self):
        self.view().setMinimumWidth(self.view().sizeHintForColumn(0))
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
