# !/usr/bin/python
# coding=utf-8
import re
from typing import Union
from qtpy import QtWidgets, QtCore, QtGui
from uitk.signals import Signals
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay
from uitk.widgets.mixins.menu_mixin import MenuMixin
from uitk.widgets.mixins.option_box_mixin import OptionBoxMixin


class CustomStyle(QtWidgets.QProxyStyle):
    """Custom proxy style for ComboBox that handles header text display.

    This style overrides CE_ComboBoxLabel drawing to display custom header
    text when no item is selected (currentIndex == -1).

    Attributes:
        combo_box: Reference to the AlignedComboBox using this style.
    """

    def __init__(self, style):
        super().__init__(style)
        self.combo_box = None  # Initialize to None, will be set later

    def drawControl(self, element, opt, painter, widget=None):
        """Override control drawing to handle header text display."""
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
    """ComboBox with header text and alignment support.

    Extends QComboBox to support:
    - Header text displayed when no item is selected
    - Custom text alignment for headers
    - Stylesheet-aware padding for proper text positioning

    Attributes:
        header_text (str): Text displayed when currentIndex is -1.
        header_alignment (Qt.Alignment): Alignment for header text.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.header_text = None
        self.header_alignment = QtCore.Qt.AlignCenter

        self.custom_style = CustomStyle(self.style())
        self.custom_style.combo_box = self  # Set the combo_box reference here
        self.setStyle(self.custom_style)

    def setHeaderText(self, text):
        """Set the header text displayed when no item is selected.

        Parameters:
            text (str): The header text to display.
        """
        self.header_text = text
        self.update()

    def setHeaderAlignment(self, alignment):
        """Set the alignment for header text.

        Parameters:
            alignment (str): One of 'left', 'right', or 'center'.
        """
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
        """Extract a numeric property value from the widget's stylesheet.

        Parameters:
            property_name (str): The CSS property name to extract.

        Returns:
            int: The property value, or 0 if not found.
        """
        stylesheet = self.styleSheet()
        match = re.search(rf"{property_name} *: *(\d+)", stylesheet)
        if match:
            return int(match.group(1))
        return 0

    def paintEvent(self, event):
        """Custom paint event to draw header text when no selection."""
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

            # Add extra left padding for header text (4px)
            header_left_padding = 4
            rect = self.rect().adjusted(
                left_padding + header_left_padding,
                top_padding,
                -right_padding,
                -bottom_padding,
            )

            alignment = self.header_alignment
            painter.drawText(rect, alignment | QtCore.Qt.AlignVCenter, self.header_text)
            painter.end()


class ComboBox(
    AlignedComboBox, MenuMixin, OptionBoxMixin, AttributesMixin, RichText, TextOverlay
):
    """QComboBox with automatic Menu and OptionBox integration.

    Features:
    - self.menu: Standalone menu (via MenuMixin)
    - self.option_box: OptionBox functionality (via OptionBoxMixin)
    - self.option_box.menu: Separate option box menu
    """

    before_popup_shown = QtCore.Signal()
    on_editing_finished = QtCore.Signal(str)
    on_item_deleted = QtCore.Signal(str)

    def __init__(self, parent=None, editable=False, **kwargs):
        super().__init__(parent)
        self.restore_previous_index = False
        self.prev_index = -1
        self.has_header = False
        self.header_text = None
        self.restore_state = False
        self.editable = editable

        self.currentIndexChanged.connect(self.check_index)

        # Customize standalone menu (provided by MenuMixin)
        self.menu.trigger_button = "right"
        self.menu.fixed_item_height = 20
        self.menu.hide_on_leave = True

        # OptionBox is also available via OptionBoxMixin
        # Users can access: self.option_box.menu, self.option_box.clear_option, etc.

        # Set maximum visible items to 40
        self.setMaxVisibleItems(40)

        self.setProperty("class", self.__class__.__name__)
        self.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
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

    def setAsCurrent(
        self,
        i: Union[str, int],
        blockSignals: bool = False,
        strict: bool = False,
        fallback_index: int = None,
    ) -> None:
        """Set the current item by value or index, with optional fallback if not found.

        Parameters:
            i (str|int): The item text or index to set as current.
            blockSignals (bool): Whether to block signals during the operation.
            strict (bool): If True, raise error if item is not found.
            fallback_index (int): Index to use if item is not found and strict is False.
                                Defaults to -1 if header is present, else 0.
        """
        if blockSignals:
            self.blockSignals(True)

        index = None
        try:
            index = (
                self.items.index(i)
                if isinstance(i, str)
                else i if isinstance(i, int) and 0 <= i < self.count() else None
            )
        except ValueError:
            if strict:
                raise ValueError(
                    f"The item '{i}' was not found in ComboBox. "
                    f"Available items are {[str(item) for item in self.items]}."
                )

        if index is None:
            index = fallback_index
            if index is None:
                index = -1 if self.has_header else 0
            print(f"ComboBox: '{i}' not found. Defaulting to index {index}.")

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

    def focusOutEvent(self, event):
        if self.isEditable():
            # Exit edit mode without emitting a signal
            self.setEditable(False, emit_signal=False)  # Pass emit_signal as False
        super().focusOutEvent(event)

    def setEditable(self, editable, emit_signal=True):
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
            if emit_signal:
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
        self.restore_previous_index = restore_index
        if restore_index:
            self.prev_index = self.currentIndex()

        if not _recursion and clear:
            self.clear()

        if header:
            self.setHeaderText(header)
            self.setHeaderAlignment(header_alignment)
            self.has_header = True
        else:
            self.has_header = False

        # Handle list of (label, data) tuples
        if (
            isinstance(x, (list, tuple))
            and x
            and isinstance(x[0], (tuple, list))
            and len(x[0]) == 2
        ):
            for label, value in x:
                self.add_single(label, value, ascending)
        elif isinstance(x, dict):
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

        self.restore_state = not self.has_header
        self.set_attributes(**kwargs)

        if not _recursion:
            if header or self.header_text:
                self.force_header_display()
            final_index = -1 if self.header_text else 0
            if restore_index and self.prev_index > -1:
                self.setCurrentIndex(self.prev_index)
                final_index = self.prev_index
            elif self.header_text:
                self.prev_index = -1
                final_index = -1
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
