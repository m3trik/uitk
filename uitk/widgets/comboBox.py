# !/usr/bin/python
# coding=utf-8
import re
from typing import Union
from qtpy import QtWidgets, QtCore, QtGui
from uitk.switchboard import Signals
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
        # Only intercept when we know we're painting our own combobox.
        # Accepting widget=None would risk hijacking CE_ComboBoxLabel
        # drawing in unrelated contexts (e.g., the popup view paint).
        if isinstance(widget, AlignedComboBox):
            if element == QtWidgets.QStyle.CE_ComboBoxLabel:
                current_index = self.combo_box.currentIndex()
                if self.combo_box.has_header:
                    current_index -= 1

                if self.combo_box.header_text and (current_index == -1):
                    opt.text = self.combo_box.header_text
                    opt.displayAlignment = self.combo_box.header_alignment
                elif current_index >= 0:
                    opt.text = self.combo_box.itemText(current_index)
                    # Append a display-only suffix (e.g. " *" for unsaved edits)
                    # to the painted text; item data / itemText stay untouched.
                    suffix = getattr(self.combo_box, "current_text_suffix", "")
                    if suffix:
                        opt.text = f"{opt.text}{suffix}"

        super().drawControl(element, opt, painter, widget)

    @staticmethod
    def _strip_focus_state_for_combobox(control, opt):
        # Native Windows style paints a blue focus border on CC_ComboBox
        # whenever State_HasFocus is set; QSS `outline: none` doesn't suppress
        # it. Clear the flag before delegating to the base style.
        #
        # Mutate in place rather than copy (`QStyleOptionComboBox(opt)`): the
        # option Qt hands to `drawComplexControl` is statically typed
        # `QStyleOptionComplex`, and PySide6's strict copy-ctor rejects that
        # base type (`TypeError: ... called with wrong argument types:
        # (QStyleOptionComplex)`) — PySide2 silently accepted it. `QComboBox`
        # builds the option fresh per paint (`initStyleOption`), so clearing a
        # flag on it has no cross-call side effects.
        if control == QtWidgets.QStyle.CC_ComboBox:
            opt.state &= ~QtWidgets.QStyle.State_HasFocus
        return opt

    def drawComplexControl(self, control, opt, painter, widget=None):
        opt = self._strip_focus_state_for_combobox(control, opt)
        super().drawComplexControl(control, opt, painter, widget)

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        # Force list-view (not menu-style) popup rendering. With Fusion's
        # default SH_ComboBox_Popup == 1, Qt installs a menu-item delegate
        # that reserves a ~12px checkmark column on every item; the column
        # is what shifts text right on hover/selected. Returning 0 keeps
        # plain QStyledItemDelegate rendering — items render edge-to-edge.
        if hint == QtWidgets.QStyle.SH_ComboBox_Popup:
            return 0
        return super().styleHint(hint, option, widget, returnData)

    def pixelMetric(self, metric, option=None, widget=None):
        # Fusion's QStyledItemDelegate.sizeHint adds PM_FocusFrameVMargin
        # (typically 1px each side = +2px vertical) on top of QSS padding,
        # making rows appear taller than the QSS-configured 1px padding
        # intends. We don't paint a native focus frame on popup items, so
        # zeroing this lets QSS padding fully define row height.
        if metric == QtWidgets.QStyle.PM_FocusFrameVMargin:
            return 0
        return super().pixelMetric(metric, option, widget)


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

        # Wrap Fusion rather than the app style. Windows 11's native style
        # paints a blue accent border on focus and has unreliable :hover
        # delivery to combobox popup items — neither suppressible from QSS.
        # Fusion respects QSS faithfully; the visible chrome (drop-down arrow,
        # frame) is already QSS-painted so swapping the base is cosmetically
        # transparent.
        base_style = QtWidgets.QStyleFactory.create("Fusion") or self.style()
        self.custom_style = CustomStyle(base_style)
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


class _CurrentItemIndicatorDelegate(QtWidgets.QStyledItemDelegate):
    """Paints a left-edge accent strip on the combobox's current item.

    Replaces the menu-style checkmark column that ``SH_ComboBox_Popup``
    suppressed (the column shifted text right on hover). The strip is
    rendered on top of the standard item paint, so item geometry is
    unchanged across all states.

    Colour is sourced from the theme's ``BUTTON_CHECKED`` token (the same
    accent used elsewhere for "this is the active selection"), with a
    hardcoded orange fallback if the theme can't be resolved.
    """

    _STRIP_WIDTH = 4
    _FALLBACK_COLOR = QtGui.QColor(165, 135, 110)  # matches BUTTON_CHECKED

    def __init__(self, combo_box):
        super().__init__(combo_box.view())
        self._combo = combo_box
        self._strip_color = self._resolve_strip_color()
        self._row_height = self._resolve_row_height()

    def _resolve_strip_color(self):
        """Resolve BUTTON_CHECKED for the combo's active theme, fall back
        to ``_FALLBACK_COLOR`` if the theme can't be inferred or parsed."""
        try:
            from uitk.widgets.mixins.style_sheet import StyleSheet
            theme = self._resolve_active_theme()
            color_str = StyleSheet.get_variable("BUTTON_CHECKED", theme=theme)
            if color_str:
                parsed = self._parse_color(color_str)
                if parsed is not None and parsed.isValid():
                    return parsed
        except Exception:
            pass
        return self._FALLBACK_COLOR

    def _resolve_active_theme(self):
        """Walk up the combobox's parent chain to find the nearest widget
        registered with ``StyleSheet`` and return its theme."""
        from uitk.widgets.mixins.style_sheet import StyleSheet
        widget = self._combo
        while widget is not None:
            if widget in StyleSheet._widget_configs:
                return StyleSheet._widget_configs[widget].get("theme", "light")
            widget = widget.parent()
        return "light"

    def _resolve_row_height(self):
        """Resolve the ``COMBOBOX_ITEM_HEIGHT`` token (px) for the combo's
        active theme. Returns the integer height, or ``None`` if the token
        can't be read — in which case ``sizeHint`` leaves rows at their
        natural height."""
        try:
            from uitk.widgets.mixins.style_sheet import StyleSheet
            return StyleSheet.get_variable_px(
                "COMBOBOX_ITEM_HEIGHT", theme=self._resolve_active_theme()
            )
        except Exception:
            return None

    @staticmethod
    def _parse_color(color_str):
        """Parse a CSS ``rgb()``/``rgba()`` string into a ``QColor``."""
        m = re.match(
            r"rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(\d+))?\)",
            color_str.strip(),
        )
        if m:
            r, g, b, a = m.groups()
            return QtGui.QColor(int(r), int(g), int(b), int(a) if a else 255)
        c = QtGui.QColor(color_str)
        return c if c.isValid() else None

    def sizeHint(self, option, index):
        # Force popup rows to COMBOBOX_ITEM_HEIGHT. QSS ``min-height`` is only
        # a floor, so a large UI font or the combobox's icon-size reservation
        # (AdjustToMinimumContentsLengthWithIcon reserves the icon height per
        # row) otherwise inflates rows past the configured height. An explicit
        # per-row hint is respected as-is — WidgetComboBox rows that embed a
        # taller widget set Qt.SizeHintRole via _apply_uniform_height.
        explicit = index.data(QtCore.Qt.SizeHintRole)
        if isinstance(explicit, QtCore.QSize) and explicit.isValid():
            return explicit
        base = super().sizeHint(option, index)
        if self._row_height is None:
            return base
        return QtCore.QSize(base.width(), self._row_height)

    def paint(self, painter, option, index):
        # Suppress hover/selection bg only for rows that host an embedded
        # widget (WidgetComboBox). With uniform-height rows + AlignVCenter,
        # a shorter embedded widget leaves a gap above/below where the row's
        # BUTTON_HOVER bg would otherwise show as a blue frame. Text-only
        # rows keep the full hover styling.
        view = self._combo.view()
        if view is not None and view.indexWidget(index) is not None:
            paint_opt = QtWidgets.QStyleOptionViewItem(option)
            paint_opt.state &= ~QtWidgets.QStyle.State_MouseOver
            paint_opt.state &= ~QtWidgets.QStyle.State_Selected
            super().paint(painter, paint_opt, index)
        else:
            super().paint(painter, option, index)

        if index.row() == self._combo.currentIndex():
            painter.save()
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(self._strip_color)
            rect = option.rect
            painter.drawRect(
                rect.x(), rect.y(), self._STRIP_WIDTH, rect.height()
            )
            painter.restore()


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

    # Class-level menu defaults (applied when menu is first accessed)
    _menu_defaults = {"hide_on_leave": True}

    def __init__(self, parent=None, editable=False, **kwargs):
        super().__init__(parent)
        self.restore_previous_index = False
        self.prev_index = -1
        self.has_header = False
        self.header_text = None
        self._current_text_suffix = ""
        self.editable = editable

        self.currentIndexChanged.connect(self.check_index)

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
    def current_text_suffix(self) -> str:
        """Text appended to the *displayed* current selection only.

        Affects what the collapsed combo paints (via the style's
        ``drawControl``), not ``itemText`` / item data — so a marker like
        ``" *"`` (unsaved edits) can be shown without corrupting the underlying
        name used for load/rename/delete. Setting it repaints.
        """
        return self._current_text_suffix

    @current_text_suffix.setter
    def current_text_suffix(self, value: str) -> None:
        value = value or ""
        if value != self._current_text_suffix:
            self._current_text_suffix = value
            self.update()

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
        """Select the item whose rich or plain text matches *text*.

        Matches Qt's ``QComboBox.setCurrentText`` contract: the current
        index moves to the first item with the given text. The previous
        override called ``setRichText(text, currentIndex())`` which
        renamed item-0 in place and left the index untouched — silently
        dropping the selected item's data on every restore-by-text.
        """
        for i in range(self.count()):
            if self.richText(i) == text or self.itemText(i) == text:
                self.setCurrentIndex(i)
                return
        super().setCurrentText(text)

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
            # QComboBox.lineEdit() returns None when the combo is not editable.
            # Fall back to currentText() so calling setEditable(False) on an
            # already-non-editable combo (e.g. from a .ui setting editable=False)
            # is a no-op rather than an AttributeError.
            new_text = lineEdit.text() if lineEdit is not None else self.currentText()
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
        prefix=None,
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

        def process_and_add(label, item_data):
            """Helper to process item before adding."""
            display_text = str(label)
            stored_data = item_data

            if prefix:
                # When prefix is active, we auto-format the label and ensure data is stored
                formatted_label = display_text.replace("_", " ").title()
                display_text = f"{prefix}\t{formatted_label}"

                # If no specific data was provided, use the original label as data
                if stored_data is None:
                    stored_data = label

            self.add_single(display_text, stored_data, ascending)

        # Handle list of (label, data) tuples
        if (
            isinstance(x, (list, tuple))
            and x
            and isinstance(x[0], (tuple, list))
            and len(x[0]) == 2
        ):
            for label, value in x:
                process_and_add(label, value)
        elif isinstance(x, dict):
            [process_and_add(k, v) for k, v in x.items()]
        elif isinstance(x, (list, tuple, set)):
            [process_and_add(item, data) for item in x]
        elif isinstance(x, (zip, map)):
            [process_and_add(i, d) for i, d in x]
        elif isinstance(x, str):
            process_and_add(x, data)
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
        view = self.view()
        view.setMinimumWidth(view.sizeHintForColumn(0))
        # Popup view defaults vary by Qt version / platform style; force
        # both so QSS ``::item:hover`` fires reliably for every row.
        view.setMouseTracking(True)
        view.setStyle(self.custom_style)
        # Marker for the current selection (left-edge strip). Installed
        # once; setItemDelegate without replacing is a no-op so re-calling
        # is cheap, but caching keeps the delegate identity stable for
        # tests and inspection.
        if not isinstance(view.itemDelegate(), _CurrentItemIndicatorDelegate):
            view.setItemDelegate(_CurrentItemIndicatorDelegate(self))
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
