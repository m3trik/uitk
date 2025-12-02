# !/usr/bin/python
# coding=utf-8
"""Clear option for OptionBox - provides a clear button for text widgets."""

from qtpy import QtWidgets, QtCore
from ._options import ButtonOption


class ClearOption(ButtonOption):
    """A clear button option that can clear text from input widgets.

    This option automatically works with text input widgets like QLineEdit,
    QTextEdit, QPlainTextEdit, QComboBox, etc.

    The button automatically hides when there is no text to clear, and shows
    when text is present.

    Example:
        line_edit = QtWidgets.QLineEdit("Some text")
        clear_option = ClearOption(line_edit)
        option_box = OptionBox(options=[clear_option])
        option_box.wrap(line_edit)
    """

    def __init__(self, wrapped_widget=None, auto_hide=True):
        """Initialize the clear option.

        Args:
            wrapped_widget: The text widget to clear
            auto_hide: If True, automatically hide when there's no text (default: True)
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon="clear",
            tooltip="Clear text",
            callback=self._clear_text,
        )
        self._auto_hide = auto_hide
        self._connected = False

    def create_widget(self):
        """Create the clear button widget."""
        button = super().create_widget()

        if not button.objectName():
            button.setObjectName("clearButton")

        button.setProperty("class", "ClearButton")
        return button

    def setup_widget(self):
        """Setup button connections and show event handling."""
        super().setup_widget()

        # Install event filter to catch show events for deferred visibility update
        if self._auto_hide and self._widget:
            self._widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Filter show events to update visibility after state restoration."""
        if event.type() == QtCore.QEvent.Show and obj is self._widget:
            # Defer visibility update to after state restoration completes
            QtCore.QTimer.singleShot(0, self._update_visibility)
        return super().eventFilter(obj, event)

    def set_wrapped_widget(self, widget):
        """Set the wrapped widget and connect text change signals."""
        super().set_wrapped_widget(widget)
        if self._auto_hide:
            self._connect_text_signals(widget)

    def _connect_text_signals(self, widget):
        """Connect to text change signals to update visibility."""
        if self._connected or not widget:
            return

        # QLineEdit
        if hasattr(widget, "textChanged") and isinstance(widget, QtWidgets.QLineEdit):
            widget.textChanged.connect(self._update_visibility)
            self._connected = True
        # QTextEdit, QPlainTextEdit
        elif hasattr(widget, "textChanged"):
            widget.textChanged.connect(self._update_visibility)
            self._connected = True
        # QComboBox (editable)
        elif hasattr(widget, "currentTextChanged"):
            widget.currentTextChanged.connect(self._update_visibility)
            self._connected = True
        # QSpinBox, QDoubleSpinBox
        elif hasattr(widget, "valueChanged"):
            widget.valueChanged.connect(self._update_visibility)
            self._connected = True

    def _get_text(self):
        """Get the current text from the wrapped widget."""
        if not self.wrapped_widget:
            return ""

        widget = self.wrapped_widget

        # QLineEdit
        if hasattr(widget, "text") and callable(widget.text):
            return widget.text()
        # QTextEdit, QPlainTextEdit
        elif hasattr(widget, "toPlainText"):
            return widget.toPlainText()
        # QComboBox
        elif hasattr(widget, "currentText"):
            return widget.currentText()
        # QSpinBox, QDoubleSpinBox - always have a value, check if it's the minimum
        elif hasattr(widget, "value") and hasattr(widget, "minimum"):
            # Consider "empty" if at minimum value
            return "" if widget.value() == widget.minimum() else str(widget.value())

        return ""

    def _update_visibility(self, *args):
        """Update button visibility based on whether there's text to clear."""
        if not self._auto_hide:
            return

        has_text = bool(self._get_text())
        if self._widget:
            self._widget.setVisible(has_text)

    def _clear_text(self):
        """Clear text from the wrapped widget."""
        if not self.wrapped_widget:
            return

        widget = self.wrapped_widget

        # Handle different types of text widgets
        if hasattr(widget, "clear"):
            widget.clear()
        elif hasattr(widget, "setText"):
            widget.setText("")
        elif hasattr(widget, "setPlainText"):
            widget.setPlainText("")


# Legacy compatibility - standalone clear button class
class ClearButton(QtWidgets.QPushButton):
    """A standalone clear button (legacy compatibility).

    Note: For new code, use ClearOption instead.
    """

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        from uitk.widgets.mixins.text import RichText
        from uitk.widgets.mixins.icon_manager import IconManager
        from uitk.widgets.mixins.attributes import AttributesMixin

        # Apply mixins dynamically
        RichText.__init__(self)
        AttributesMixin.__init__(self)

        self.text = self.richText
        self.setText = self.setRichText
        self.sizeHint = self.richTextSizeHint

        if not self.objectName():
            self.setObjectName("clearButton")

        # Use the new modern SVG icon
        IconManager.set_icon(self, "clear", size=(17, 17))
        self.setToolTip("Clear text")

        self.clicked.connect(self._clear_text)
        self.setProperty("class", self.__class__.__name__)

        if hasattr(self, "set_attributes"):
            self.set_attributes(**kwargs)

    def _clear_text(self):
        """Clear text from the wrapped widget."""
        if hasattr(self, "wrapped_widget"):
            widget = self.wrapped_widget
            # Handle different types of text widgets
            if hasattr(widget, "clear"):
                widget.clear()
            elif hasattr(widget, "setText"):
                widget.setText("")
            elif hasattr(widget, "setPlainText"):
                widget.setPlainText("")
