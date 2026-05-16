# !/usr/bin/python
# coding=utf-8
from qtpy import QtCore, QtWidgets

# From this package:
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.menu_mixin import MenuMixin
from uitk.widgets.mixins.option_box_mixin import OptionBoxMixin


class LineEditFormatMixin:
    """Lazily formats QLineEdit with reversible visual state feedback.

    Provides ``set_action_color(key)`` / ``reset_action_color()`` for
    signaling validation state.  Styling is driven by a ``actionState``
    dynamic property and defined in style.qss.

    Also provides an optional ``set_validator()`` API that wires up
    debounced ``textChanged`` → user-supplied predicate → visual feedback
    (``actionState`` color + tooltip) → ``validated(bool, str)`` signal.

    Built-in string shortcuts for ``set_validator()``:
        - ``"file"``  — ``ptk.is_valid(text, "file")``
        - ``"dir"``   — ``ptk.is_valid(text, "dir")``
        - ``"path"``  — ``ptk.is_valid(text)`` (file or dir)

    Or pass any ``callable(text) -> bool`` for arbitrary validation.

    The host class must declare ``validated = QtCore.Signal(bool, str)``
    for the signal to be available; ``set_validator()`` still functions
    (color + tooltip updates) when no such signal exists.
    """

    def set_action_color(self, key: str) -> None:
        self.setProperty("actionState", key)
        self.style().unpolish(self)
        self.style().polish(self)

    def reset_action_color(self) -> None:
        self.setProperty("actionState", None)
        self.style().unpolish(self)
        self.style().polish(self)

    # ------------------------------------------------------------------
    # Validator API
    # ------------------------------------------------------------------

    _VALIDATOR_PRESETS = ("file", "dir", "path")

    @staticmethod
    def _resolve_validator(validator):
        """Convert a preset string into a callable, or return *validator* as-is."""
        if callable(validator):
            return validator
        if validator in LineEditFormatMixin._VALIDATOR_PRESETS:
            import pythontk as ptk

            kind = None if validator == "path" else validator
            return lambda text, _k=kind: bool(text) and ptk.is_valid(text, _k)
        raise ValueError(
            f"validator must be callable or one of "
            f"{LineEditFormatMixin._VALIDATOR_PRESETS!r}, got {validator!r}"
        )

    def set_validator(
        self,
        validator,
        *,
        debounce_ms: int = 300,
        invalid_tooltip: str = "Invalid",
        valid_tooltip=None,
        empty_tooltip=None,
        empty_is_valid: bool = True,
    ):
        """Install a debounced text validator with visual feedback.

        Parameters:
            validator: A callable ``(text) -> bool`` or a preset string
                (``"file"``, ``"dir"``, ``"path"``).
            debounce_ms: Delay before validating after the last keystroke.
                Set to 0 to validate immediately (typically only useful
                in tests).
            invalid_tooltip: Tooltip shown when validation fails.
            valid_tooltip: Tooltip shown when validation passes.  Can be
                a string, a callable ``(text) -> str``, or ``None`` to
                show the text itself.
            empty_tooltip: Tooltip shown when text is empty.  ``None``
                (default) preserves whatever tooltip was set on the
                widget before ``set_validator`` was called.
            empty_is_valid: When True (default), empty text resets the
                color and emits ``validated(True, "")``.  When False,
                empty text is treated as invalid.
        """
        callable_validator = self._resolve_validator(validator)

        # Capture pre-install tooltip so empty-text state can restore it
        prior_tooltip = self.toolTip()

        # Idempotent install — disconnect any prior wiring first
        self.clear_validator()

        # QTimer-based debouncer (replaces any pending validation)
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._run_validation)

        self._validator_callable = callable_validator
        self._validator_timer = timer
        self._validator_debounce_ms = max(0, int(debounce_ms))
        self._validator_invalid_tooltip = invalid_tooltip
        self._validator_valid_tooltip = valid_tooltip
        self._validator_empty_tooltip = (
            empty_tooltip if empty_tooltip is not None else prior_tooltip
        )
        self._validator_empty_is_valid = empty_is_valid
        self._last_validation_text = None
        self._last_validation_result = None

        self.textChanged.connect(self._on_text_changed_validate)

        # Run once now so the initial color/tooltip reflect current state
        self._run_validation()

    def clear_validator(self):
        """Remove any installed validator and reset visual state."""
        timer = getattr(self, "_validator_timer", None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        if getattr(self, "_validator_callable", None) is not None:
            try:
                self.textChanged.disconnect(self._on_text_changed_validate)
            except (TypeError, RuntimeError):
                pass
        self._validator_callable = None
        self._validator_timer = None
        self._last_validation_text = None
        self._last_validation_result = None
        self.reset_action_color()

    @property
    def is_valid(self):
        """Last validation result, or ``None`` if no validator is set."""
        return getattr(self, "_last_validation_result", None)

    def validate_now(self):
        """Cancel any pending debounce and validate the current text now.

        Useful from commit handlers (``editingFinished``) where stale
        ``is_valid`` would be wrong if the user pressed Enter before the
        debounce timer fired.
        """
        timer = getattr(self, "_validator_timer", None)
        if timer is not None:
            timer.stop()
        if getattr(self, "_validator_callable", None) is not None:
            self._run_validation()

    def _on_text_changed_validate(self, _text):
        timer = getattr(self, "_validator_timer", None)
        if timer is None:
            return
        if self._validator_debounce_ms <= 0:
            self._run_validation()
            return
        timer.start(self._validator_debounce_ms)

    def _run_validation(self):
        validator = getattr(self, "_validator_callable", None)
        if validator is None:
            return
        text = self.text()

        if not text and self._validator_empty_is_valid:
            ok = True
            self.reset_action_color()
            self.setToolTip(self._validator_empty_tooltip or "")
        else:
            try:
                ok = bool(validator(text))
            except Exception:
                ok = False

            if ok:
                self.set_action_color("reset")
                tip = self._validator_valid_tooltip
                if callable(tip):
                    tip = tip(text)
                self.setToolTip(tip if tip is not None else text)
            else:
                self.set_action_color("invalid")
                self.setToolTip(self._validator_invalid_tooltip)

        self._last_validation_text = text
        self._last_validation_result = ok

        emitter = getattr(self, "validated", None)
        if emitter is not None and hasattr(emitter, "emit"):
            emitter.emit(ok, text)


class LineEdit(
    QtWidgets.QLineEdit, MenuMixin, OptionBoxMixin, AttributesMixin, LineEditFormatMixin
):
    """LineEdit with automatic Menu and OptionBox integration.

    Features:
    - self.menu: Context menu (via MenuMixin)
    - self.option_box: OptionBox functionality (via OptionBoxMixin)
    - self.option_box.menu: Separate option box menu
    - self.option_box.clear_option: Enable/disable clear button
    - self.set_validator(...): Optional debounced text validation with
      visual feedback (via LineEditFormatMixin). Emits ``validated``.

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
    """

    shown = QtCore.Signal()
    hidden = QtCore.Signal()
    validated = QtCore.Signal(bool, str)
    """Emitted after debounced validation. (is_valid, text)."""

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

        # OptionBox is also available via OptionBoxMixin
        # Users can access: self.option_box.menu, self.option_box.clear_option, etc.

        # Set any provided attributes
        self.set_attributes(**kwargs)

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
    from uitk.widgets.optionBox.utils import add_clear_option, add_menu_option

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
    container4 = add_clear_option(line_edit4_legacy)
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

    container6 = add_menu_option(line_edit6, legacy_menu)
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
        "• Legacy: add_option_box(), add_clear_option() still supported\n"
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
