# !/usr/bin/python
# coding=utf-8
from qtpy import QtCore, QtWidgets

# From this package:
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.menu_mixin import MenuMixin
from uitk.widgets.mixins.option_box_mixin import OptionBoxMixin
from uitk.widgets.mixins.shortcut_guard import ShortcutGuardMixin
from uitk.widgets.mixins.text_validation import TextValidationMixin


class LineEditFormatMixin(TextValidationMixin):
    """:class:`LineEdit`'s validation feedback -- the shared
    :class:`~uitk.widgets.mixins.text_validation.TextValidationMixin`, whose
    commit is ``editingFinished`` (Enter / focus-out), so
    ``set_validator(revert_on_commit=...)`` works here.

    Kept under this name: it is what ``LineEdit`` has always mixed in, and
    hosts still call its ``set_action_color`` / ``reset_action_color`` on
    fields of their own.  The validator API itself is documented on the
    shared mixin, which :class:`~uitk.widgets.textEdit.TextEdit` uses too.
    """

    def _commit_signal(self):
        return self.editingFinished


class LineEdit(
    ShortcutGuardMixin,
    QtWidgets.QLineEdit,
    MenuMixin,
    OptionBoxMixin,
    AttributesMixin,
    LineEditFormatMixin,
):
    """LineEdit with automatic Menu and OptionBox integration.

    Features:
    - self.menu: Context menu (via MenuMixin)
    - self.option_box: OptionBox functionality (via OptionBoxMixin)
    - self.option_box.clear_option: Enable/disable clear button
    - self.option_box.menu: Separate option box menu
    - The standard editing chords — ``Ctrl+A``/``C``/``X``/``V``/``Z``/``Y`` and
      word-delete — stay with the field even when a host binds the same sequence
      (via ShortcutGuardMixin, which must precede ``QLineEdit`` in the MRO so its
      ``event`` override wins). Read-only-aware: such a field keeps Copy and
      Select All and releases the writes.
    - self.set_validator(...): Optional debounced text validation with
      visual feedback (via LineEditFormatMixin). Emits ``validated``;
      ``set_validator("name")`` enforces a legal name as the user types.

    Usage Examples:
        # Basic LineEdit
        line_edit = LineEdit()
        layout.addWidget(line_edit)

        # Enable clear button via option box
        line_edit.option_box.clear_option = True
        layout.addWidget(line_edit.option_box.container)

        # Add items to option box menu
        line_edit.option_box.menu.add("Copy")
        line_edit.option_box.menu.add("Paste")

        # Standalone context menu
        line_edit.menu.add("Context Item")

        # Validate as a directory path with debounced feedback
        line_edit.set_validator("dir", debounce_ms=300)
        line_edit.validated.connect(lambda ok, text: ...)

        # A legal name: marked red with the reason until it is one
        line_edit.set_validator("name")
    """

    # Qt Designer widget-box entry.
    designer_spec = {"icon": "edit", "object_name": "txt"}

    shown = QtCore.Signal()
    hidden = QtCore.Signal()
    validated = QtCore.Signal(bool, str)
    """Emitted after debounced validation. (is_valid, text)."""
    deferred_validated = QtCore.Signal(int, bool, object)
    """Internal: a ``deferred`` validator's answer crossing back to the Qt
    thread. (generation, is_valid, message)."""
    commit_refused = QtCore.Signal(str, str)
    """A refused value was committed and ``revert_on_commit`` put the field
    back. (refused text, reason)."""

    # Class-level menu defaults (applied when menu is first accessed)
    _menu_defaults = {"hide_on_leave": True}

    def __init__(self, parent=None, **kwargs):
        """Initialize LineEdit with Menu and OptionBox mixins.

        Parameters:
            parent: Parent widget
            **kwargs: Attributes to set on the widget
        """
        super().__init__(parent)
        self.setProperty("class", self.__class__.__name__)

        # Optional hidden data payload — see ``set_value``/``value``/``data``.
        # A manual edit clears it so the typed text becomes the value again.
        self._value_data = None
        self.textEdited.connect(self._invalidate_value_data)

        # OptionBox is also available via OptionBoxMixin
        # Users can access: self.option_box.menu, self.option_box.clear_option, etc.

        # Set any provided attributes
        self.set_attributes(**kwargs)

    # ------------------------------------------------------------------
    # Display / data split (Qt item-data style, single payload)
    # ------------------------------------------------------------------

    def set_value(self, value, display=None):
        """Set the field's underlying value and an optional display string.

        When *display* is given (and differs from ``str(value)``) the field
        shows the friendlier *display* text while :meth:`value` / :meth:`data`
        return the real *value* — e.g. a field that lists texture-set names
        but carries the full file paths as data. When *display* is omitted the
        field behaves exactly like ``setText(str(value))`` and carries no
        separate payload (``text == value``).

        A subsequent manual edit by the user clears the stored payload, so the
        typed text becomes the value again.
        """
        text = str(value) if display is None else str(display)
        if display is not None and str(display) != str(value):
            self._value_data = value
        else:
            self._value_data = None
        self.setText(text)

    def value(self):
        """The field's value: the stored data payload, or :meth:`text` if none."""
        return self._value_data if self._value_data is not None else self.text()

    def data(self):
        """The stored data payload, or ``None`` when the text *is* the value.

        Presenters use this to detect a display/data split: ``None`` means the
        field carries no hidden payload and ``text()`` should be used directly.
        """
        return self._value_data

    def clear_value(self):
        """Drop the stored data payload (leaves the visible text untouched)."""
        self._value_data = None

    def _invalidate_value_data(self, *_args):
        self._value_data = None

    def _validation_value(self):
        """Validate against the data payload when present, else the text."""
        return self.value()

    def _set_validation_value(self, value):
        """The revert on commit restores a VALUE (no display split)."""
        self.set_value(value)

    def contextMenuEvent(self, event):
        """Override the standard context menu if there is a custom one."""
        if self.has_menu and self.menu.contains_items:
            self.menu.show()
        else:
            super().contextMenuEvent(event)

    def showEvent(self, event):
        """Handle show event."""
        self.shown.emit()
        super().showEvent(event)

    def hideEvent(self, event):
        """Handle hide event."""
        self.hidden.emit()
        super().hideEvent(event)


if __name__ == "__main__":
    import sys
    from uitk.widgets.menu import Menu
    from uitk.widgets.optionBox.utils import OptionBoxManager

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    window = QtWidgets.QWidget()
    window.setWindowTitle("Streamlined LineEdit Demo")
    window.resize(500, 500)
    layout = QtWidgets.QVBoxLayout(window)

    # Example 1: Basic LineEdit (no option box)
    layout.addWidget(QtWidgets.QLabel("1. Basic LineEdit (no options):"))
    line_edit1 = LineEdit()
    line_edit1.setText("Basic line edit")
    layout.addWidget(line_edit1)

    # Example 2: LineEdit with clear button using ELEGANT interface (NEW)
    layout.addWidget(QtWidgets.QLabel("2. LineEdit with Clear Button (elegant):"))
    line_edit2 = LineEdit()
    line_edit2.setText("Clear me with the button")
    line_edit2.option_box.clear_option = True
    layout.addWidget(line_edit2.option_box.container)

    # Example 3: LineEdit with custom action using ELEGANT interface (NEW)
    layout.addWidget(QtWidgets.QLabel("3. LineEdit with Custom Action (elegant):"))
    line_edit3 = LineEdit()
    line_edit3.setText("Count these words")

    def count_words():
        text = line_edit3.text()
        word_count = len(text.split()) if text else 0
        print(f"Word count: {word_count}")

    line_edit3.option_box.enable_clear().set_action(count_words)
    layout.addWidget(line_edit3.option_box.container)

    # Example 4: LineEdit with clear button using legacy function
    layout.addWidget(QtWidgets.QLabel("4. LineEdit with Clear Button (legacy):"))
    line_edit4_legacy = LineEdit()
    line_edit4_legacy.setText("Legacy clear button approach")
    container4 = OptionBoxManager.add_clear_option(line_edit4_legacy)
    layout.addWidget(container4)

    # Example 5: LineEdit with menu using ELEGANT interface (NEW)
    layout.addWidget(QtWidgets.QLabel("5. LineEdit with Menu (elegant):"))
    line_edit5 = LineEdit()
    line_edit5.setText("Text with menu options")

    # Create menu
    custom_menu = Menu(line_edit5, trigger_button="left", position="cursorPos")
    custom_menu.add("QPushButton", setText="Option 1", setObjectName="opt1")
    custom_menu.add("QPushButton", setText="Option 2", setObjectName="opt2")
    custom_menu.add("QPushButton", setText="Option 3", setObjectName="opt3")

    # Connect actions
    custom_menu.opt1.clicked.connect(lambda: print("Option 1 clicked"))
    custom_menu.opt2.clicked.connect(lambda: print("Option 2 clicked"))
    custom_menu.opt3.clicked.connect(lambda: print("Option 3 clicked"))

    line_edit5.option_box.set_menu(custom_menu)
    layout.addWidget(line_edit5.option_box.container)

    # Example 6: LineEdit with menu using legacy function
    layout.addWidget(QtWidgets.QLabel("6. LineEdit with Menu (legacy):"))
    line_edit6 = LineEdit()
    line_edit6.setText("Legacy menu approach")

    # Create another menu for legacy example
    legacy_menu = Menu(line_edit6, trigger_button="left", position="cursorPos")
    legacy_menu.add("QPushButton", setText="Legacy Option 1", setObjectName="leg1")
    legacy_menu.add("QPushButton", setText="Legacy Option 2", setObjectName="leg2")

    # Connect actions
    legacy_menu.leg1.clicked.connect(lambda: print("Legacy Option 1 clicked"))
    legacy_menu.leg2.clicked.connect(lambda: print("Legacy Option 2 clicked"))

    container6 = OptionBoxManager.add_menu_option(line_edit6, legacy_menu)
    layout.addWidget(container6)

    # Example 7: Any Qt widget works (demo with QTextEdit using elegant interface)
    layout.addWidget(
        QtWidgets.QLabel("7. Any Qt Widget (QTextEdit with elegant interface):")
    )
    text_edit = QtWidgets.QTextEdit()
    text_edit.setPlainText("This QTextEdit has elegant option box functionality!")
    text_edit.setMaximumHeight(80)

    def text_info():
        text = text_edit.toPlainText()
        chars = len(text)
        words = len(text.split()) if text else 0
        lines = text.count("\n") + 1 if text else 0
        print(f"Text stats: {chars} chars, {words} words, {lines} lines")

    text_edit.option_box.enable_clear().set_action(text_info)
    layout.addWidget(text_edit.option_box.container)

    # Instructions
    instructions = QtWidgets.QLabel(
        "✅ ELEGANT OPTIONBOX INTERFACE:\n"
        "• NEW: widget.option_box.clear_option = True  (elegant attribute access)\n"
        "• NEW: widget.option_box.enable_clear().set_action(func)  (fluent interface)\n"
        "• Factories: OptionBoxManager.add_option_box(), .add_clear_option()\n"
        "• Similar to menu: widget.menu.add() → widget.option_box.clear_option\n"
        "• Works with ANY widget: LineEdit, TextEdit, Button, ComboBox, etc.\n"
        "• Menu compatible: Menu class works exactly the same as before\n"
        "• Container access: widget.option_box.container for layout management\n"
        "• Clean API: No complex setup or inheritance needed"
    )
    instructions.setStyleSheet(
        "color: #2d5a2d; font-size: 10px; margin: 10px; padding: 8px; "
        "background-color: #e8f5e8; border: 1px solid #4a7c59; border-radius: 4px;"
    )
    layout.addWidget(instructions)

    window.show()
    sys.exit(app.exec_())


# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------

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

# deprecated:

# if pm.progressBar ("progressBar_", q=True, isCancelled=1):
# break


# def insertText(self, dict_):
#   '''
#   Parameters:
#       dict_ = {dict} - contents to add.  for each key if there is a value, the key and value pair will be added.
#   '''
#   highlight = QtGui.QColor(255, 255, 0)
#   baseColor = QtGui.QColor(185, 185, 185)

#   #populate the textedit with any values
#   for key, value in dict_.items():
#       if value:
#           self.setTextColor(baseColor)
#           self.append(key) #Appends a new paragraph with text to the end of the text edit.
#           self.setTextColor(highlight)
#           self.insertPlainText(str(value)) #inserts text at the current cursor position.
