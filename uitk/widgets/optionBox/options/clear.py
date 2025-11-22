# !/usr/bin/python
# coding=utf-8
"""Clear option for OptionBox - provides a clear button for text widgets."""

from qtpy import QtWidgets
from ._options import ButtonOption


class ClearOption(ButtonOption):
    """A clear button option that can clear text from input widgets.

    This option automatically works with text input widgets like QLineEdit,
    QTextEdit, QPlainTextEdit, QComboBox, etc.

    Example:
        line_edit = QtWidgets.QLineEdit("Some text")
        clear_option = ClearOption(line_edit)
        option_box = OptionBox(options=[clear_option])
        option_box.wrap(line_edit)
    """

    def __init__(self, wrapped_widget=None):
        """Initialize the clear option.

        Args:
            wrapped_widget: The text widget to clear
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon="clear",
            tooltip="Clear text",
            callback=self._clear_text,
        )

    def create_widget(self):
        """Create the clear button widget."""
        button = super().create_widget()

        if not button.objectName():
            button.setObjectName("clearButton")

        button.setProperty("class", "ClearButton")
        return button

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


# Legacy compatibility - standalone ClearButton class
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
