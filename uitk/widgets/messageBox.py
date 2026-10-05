# !/usr/bin/python
# coding=utf-8
from qtpy import QtCore, QtGui, QtWidgets
from uitk._bootstrap import Bootstrap
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichTextFormatter


class MessageBox(QtWidgets.QMessageBox, AttributesMixin):
    """Displays a message box with HTML formatting for a set time before closing.

    Parameters:
        location (str)(point) = move the messagebox to the specified location. Can be given as a qpoint or string value. default is: 'topMiddle'
        timeout (float/str/None): seconds before a box without buttons
            closes itself; ``"auto"`` times it to its text
            (:meth:`reading_time`); ``None`` or ``0`` never closes it. A box
            with buttons waits for its answer.
    """

    buttonMapping = {
        "Ok": QtWidgets.QMessageBox.Ok,
        "Open": QtWidgets.QMessageBox.Open,
        "Save": QtWidgets.QMessageBox.Save,
        "Cancel": QtWidgets.QMessageBox.Cancel,
        "Close": QtWidgets.QMessageBox.Close,
        "Discard": QtWidgets.QMessageBox.Discard,
        "Apply": QtWidgets.QMessageBox.Apply,
        "Reset": QtWidgets.QMessageBox.Reset,
        "RestoreDefaults": QtWidgets.QMessageBox.RestoreDefaults,
        "Help": QtWidgets.QMessageBox.Help,
        "SaveAll": QtWidgets.QMessageBox.SaveAll,
        "Yes": QtWidgets.QMessageBox.Yes,
        "YesToAll": QtWidgets.QMessageBox.YesToAll,
        "No": QtWidgets.QMessageBox.No,
        "NoToAll": QtWidgets.QMessageBox.NoToAll,
        "Abort": QtWidgets.QMessageBox.Abort,
        "Retry": QtWidgets.QMessageBox.Retry,
        "Ignore": QtWidgets.QMessageBox.Ignore,
        "NoButton": QtWidgets.QMessageBox.NoButton,
        None: QtWidgets.QMessageBox.NoButton,
    }

    #: Default StyleSheet theme registered for new MessageBox instances.
    #: Set to ``None`` on the class to skip auto-registration globally
    #: (caller takes over styling).
    _default_theme = "dark"

    # Sentinel — using a class-level constant resolved at call time so changes
    # to ``MessageBox._default_theme`` after import affect new instances.
    _USE_DEFAULT_THEME = object()

    #: Label -> button for the non-standard names :meth:`setStandardButtons`
    #: was given. Read-only here; each box rebinds its own.
    _labelled_buttons: dict = {}

    #: ``timeout="auto"``: a glance to find the box plus the visible text at
    #: READING_CHARS_PER_SECOND (~200 wpm), clamped to AUTO_TIMEOUT_RANGE. The
    #: ceiling keeps a long message from lingering; the full text is logged.
    READING_GLANCE = 1.0
    READING_CHARS_PER_SECOND = 20
    AUTO_TIMEOUT_RANGE = (1.5, 4.0)

    # A MessageBox is two widgets wearing one class: a PASSIVE TOAST that must
    # never take focus, and an INTERACTIVE PROMPT that cannot work unless it
    # does. Only the toast flags were ever applied, to both.
    _TOAST_FLAGS = (
        QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
        | QtCore.Qt.WindowStaysOnTopHint
        | QtCore.Qt.Tool
        | QtCore.Qt.FramelessWindowHint
    )
    # ``exec_()`` is app-modal by definition: it blocks the host DCC until the
    # user answers. Carrying WindowDoesNotAcceptFocus there produced a prompt
    # that halted the host while refusing every keypress meant to dismiss it,
    # and ``autoClose`` deliberately skips buttoned boxes, so nothing else
    # could close it either -- an unrecoverable hang. Qt.Tool is dropped for the
    # same reason: a Tool window need not appear in the task bar or above the
    # host, so the thing blocking the session could not be found. Frameless and
    # always-on-top are KEPT -- they are the styled look, and neither prevents
    # answering the prompt.
    # Qt.Dialog is REQUIRED, not decorative: a flag set carrying only hints has
    # no window-type bit, and on a PARENTED widget (the production path always
    # passes one) Qt resolves that to Qt.Widget -- an embedded child, not a
    # top-level window. Measured: hints-only gives type 0x0 with a parent and
    # 0x1 without, so testing this unparented hides it.
    _PROMPT_FLAGS = (
        QtCore.Qt.Dialog
        | QtCore.Qt.WindowStaysOnTopHint
        | QtCore.Qt.FramelessWindowHint
    )

    def __init__(
        self,
        parent=None,
        location="topMiddle",
        align="left",
        timeout=None,
        theme=_USE_DEFAULT_THEME,
        **kwargs,
    ):
        QtWidgets.QMessageBox.__init__(self, parent)

        self.setWindowModality(QtCore.Qt.NonModal)
        self.setStandardButtons(QtWidgets.QMessageBox.NoButton)
        Bootstrap.set_translucent(self)
        self.setWindowFlags(self._TOAST_FLAGS)

        self.setTextFormat(QtCore.Qt.RichText)

        self.location = location
        self.align = align

        # Always initialize the timer
        self.menu_timer = QtCore.QTimer(self)
        self.menu_timer.setSingleShot(True)
        self.menu_timer.timeout.connect(self.autoClose)

        self.timeout = timeout

        self.setProperty("class", self.__class__.__name__)
        # Resolve default sentinel against the *class* attribute at call time
        # so subclasses or runtime overrides of ``_default_theme`` win without
        # rebinding the default expression on this method.
        self._theme = self._default_theme if theme is self._USE_DEFAULT_THEME else theme
        # Apply uitk theme so the popup picks up PANEL_BACKGROUND / TEXT_COLOR
        # / BORDER tokens; per-call ``background=`` overrides in setText are
        # applied on the inner label (not via ``self.setStyleSheet``) so the
        # themed QSS isn't clobbered.
        self._apply_theme()
        self.set_attributes(**kwargs)

    @property
    def timeout(self):
        """Seconds before a buttonless box closes itself, ``"auto"``, or
        ``None`` (never). Set ``None``, ``0`` or less to never close."""
        return self._timeout

    @timeout.setter
    def timeout(self, value) -> None:
        if isinstance(value, str):
            if value != "auto":
                raise ValueError(f"timeout must be seconds, 'auto' or None: {value!r}")
            self._timeout = value
        else:
            self._timeout = float(value) if value and value > 0 else None

    @classmethod
    def reading_time(cls, text: str) -> float:
        """Seconds to read *text* (HTML or plain) -- the ``"auto"`` timeout.

        Counts the visible characters, so markup costs nothing and a long
        path costs what it takes to read; clamped to
        :attr:`AUTO_TIMEOUT_RANGE`.
        """
        doc = QtGui.QTextDocument()
        doc.setHtml(text or "")
        chars = len(" ".join(doc.toPlainText().split()))
        low, high = cls.AUTO_TIMEOUT_RANGE
        seconds = cls.READING_GLANCE + chars / cls.READING_CHARS_PER_SECOND
        return min(max(seconds, low), high)

    def _present(self) -> None:
        """Time and place the box for its current text: (re)start the
        auto-close countdown and move it to :attr:`location`. A box with
        buttons is waiting for an answer and gets no countdown."""
        seconds = (
            self.reading_time(self.text()) if self._timeout == "auto" else self._timeout
        )
        if seconds is None or self.buttons():
            self.menu_timer.stop()
        else:
            self.menu_timer.start(round(seconds * 1000))
        self.move_(self.location)

    def _apply_theme(self) -> None:
        """Register with the StyleSheet engine for theme tokens."""
        if self._theme is None:
            return
        try:
            from uitk.themes.style_sheet import StyleSheet
        except Exception:  # noqa: BLE001 — style engine optional at this layer.
            return
        StyleSheet(self).set(theme=self._theme)

    def setStandardButtons(self, *buttons):
        """Set the box's buttons; none given means no buttons.

        Each is a Qt ``StandardButton`` or its name (case-insensitive,
        ``"YesToAll"``), or any other string, which becomes a button wearing
        that label -- so a prompt can name what each answer does
        (``"Override All"``) instead of borrowing Yes/No. Labelled buttons sit
        after the standard ones' roles in the platform's order, among
        themselves in the order given, and :meth:`exec_` answers with the
        label. Calling again replaces every button.
        """
        for custom in self._labelled_buttons.values():
            self.removeButton(custom)
            custom.deleteLater()
        self._labelled_buttons = {}
        if not buttons:
            # Set to no buttons if none are provided
            super().setStandardButtons(QtWidgets.QMessageBox.NoButton)
            return

        standardButtons = QtWidgets.QMessageBox.StandardButtons()
        labels = []
        for button in buttons:
            if isinstance(button, str):
                resolved = self._standard_button(button)
                if resolved is None:
                    # Not a Qt name: a button of its own. (A dropped name left
                    # a dialog missing its affirmative action -- live-caught:
                    # "Fix" produced a Cancel-only box.)
                    labels.append(button)
                    continue
                standardButtons |= resolved
            elif isinstance(button, QtWidgets.QMessageBox.StandardButton):
                standardButtons |= button

        super().setStandardButtons(standardButtons)
        for label in labels:
            self._labelled_buttons[label] = self.addButton(
                label, QtWidgets.QMessageBox.ActionRole
            )

    def set_default_button(self, name: str) -> None:
        """Make the button called *name* the one Enter answers.

        *name* is a standard button's name or a labelled button's label, as
        given to :meth:`setStandardButtons`. Left unset, Qt picks one itself
        -- for a prompt that can waive a safety check, name the safe answer.

        Raises:
            ValueError: No button of the box is called *name*.
        """
        button = self._labelled_buttons.get(name)
        if button is None:
            standard = self._standard_button(name)
            button = self.button(standard) if standard is not None else None
        if button is None:
            raise ValueError(f"MessageBox has no button called {name!r}.")
        self.setDefaultButton(button)

    @classmethod
    def _standard_button(cls, name: str):
        """The Qt ``StandardButton`` *name* spells, case-insensitively, or None.

        Matched against the real names: ``str.capitalize()`` once lowercased
        interior capitals, so "RestoreDefaults" / "YesToAll" never resolved.
        """
        wanted = str(name).lower()
        return next(
            (
                v
                for k, v in cls.buttonMapping.items()
                if isinstance(k, str) and k.lower() == wanted
            ),
            None,
        )

    def move_(self, location) -> None:
        # Honor an explicit QPoint — the class docstring promises point support.
        if isinstance(location, QtCore.QPoint):
            self.move(location)
            return

        # Position relative to the screen under the cursor rather than a
        # hardcoded primary monitor, so the popup lands on the active display.
        # ``rect`` carries the screen's global offset (non-zero left/top on a
        # secondary monitor), so every point below is anchored to it.
        screen = (
            QtWidgets.QApplication.screenAt(QtGui.QCursor.pos())
            or QtWidgets.QApplication.primaryScreen()
        )
        rect = screen.geometry()

        offset_x = self.sizeHint().width() / 2
        offset_y = self.sizeHint().height() / 2

        if location == "topMiddle":
            point = QtCore.QPoint(
                rect.left() + rect.width() / 2 - offset_x, rect.top() + 150
            )
        elif location == "bottomRight":
            point = QtCore.QPoint(
                rect.left() + rect.width() - offset_x,
                rect.top() + rect.height() - offset_y,
            )
        elif location == "topLeft":
            point = QtCore.QPoint(rect.left() + offset_x, rect.top() + offset_y)
        elif location == "bottomLeft":
            point = QtCore.QPoint(
                rect.left() + offset_x, rect.top() + rect.height() - offset_y
            )
        else:  # default to the middle of the screen if location is not recognized
            point = QtCore.QPoint(
                rect.left() + rect.width() / 2 - offset_x,
                rect.top() + rect.height() / 2 - offset_y,
            )

        self.move(point)

    def setText(
        self,
        string,
        fontColor="white",
        background=None,
        fontSize=5,
    ) -> None:
        """Set the text to be displayed with the specified alignment unless overridden by HTML.

        Parameters:
            string (str): The text or HTML content to display.
            fontColor (str): The text color.
            background (bool/float/str/None): Optional inline override for
                the label background. ``None`` (default) leaves the uitk
                theme styling in place. ``True`` uses default dark grey at
                100% opacity; ``False`` / ``0`` forces transparent; a
                ``float`` 0–1 sets opacity on the default dark grey;
                a CSS color ``str`` is used verbatim. Override is applied
                to the inner ``qt_msgbox_label`` directly so the host
                MessageBox's themed QSS is preserved.
            fontSize (int): The font size of the text.
        """
        s = RichTextFormatter.format(
            string, align=self.align, font_color=fontColor, font_size=fontSize
        )
        super().setText(s)
        # A reused, still-showing box gets no showEvent from show(): time and
        # place the new text here, or it inherits what was left of the old
        # one's time and grows off-centre from the old one's position.
        if self.isVisible():
            self._present()

        if background is None:
            return  # Theme handles styling.

        # Inline override -- apply to the inner label, not to ``self``.
        # ``self.setStyleSheet`` would replace the themed QSS entirely;
        # the label-scoped override layers on top without disturbing it.
        label = self.findChild(QtWidgets.QLabel, "qt_msgbox_label")
        if label is None:
            return
        bg_css = RichTextFormatter.resolve_background(background)
        if bg_css:
            label.setStyleSheet(f"background-color: {bg_css}; padding: 8px;")
        else:
            label.setStyleSheet("background-color: transparent; padding: 8px;")

    def autoClose(self):
        # Only a buttonless box closes itself. Asked of buttons(), not
        # standardButtons(): a prompt whose buttons are all labelled has no
        # standard one, and was closed before it was answered.
        if not self.buttons():
            self.accept()

    def showEvent(self, event):
        self._present()
        super().showEvent(event)

    def hideEvent(self, event):
        # Stop the timer when the MessageBox is hidden
        self.menu_timer.stop()
        super().hideEvent(event)

    def as_prompt(self):
        """Re-flag this box as an interactive prompt rather than a toast.

        Idempotent, and applied before the window is realised so the change
        costs no flicker. Kept separate from :meth:`exec_` so the flag
        contract is assertable without entering a modal event loop -- a test
        that has to spin ``exec_()`` to check a window flag is a test that
        hangs the suite the same way the bug hangs the host.
        """
        # ORDER IS LOAD-BEARING: setWindowModality() RESETS the window flags to
        # Qt's defaults for the widget type (measured: 0x40801 -> 0x8003003, i.e.
        # the frameless/on-top set replaced by Dialog|Title|SysMenu|Close). Setting
        # the flags first therefore discards them silently, which is why modality
        # is applied FIRST here and in __init__.
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowFlags(self._PROMPT_FLAGS)
        return self

    def exec_(self):
        # A modal prompt needs focus and needs to be findable; the toast flags
        # set in __init__ deny both. See _PROMPT_FLAGS.
        self.as_prompt()

        # Call the original exec_ method and store the result
        resultEnum = super().exec_()

        # A labelled button answers with its label. Asked FIRST: Qt returns an
        # opaque index for a non-standard button, which could collide with a
        # standard button's enum value.
        clicked = self.clickedButton()
        for label, button in self._labelled_buttons.items():
            if button is clicked:
                return label

        # Convert the enum result to a string using the buttonMapping
        resultString = next(
            (k for k, v in MessageBox.buttonMapping.items() if v == resultEnum),
            None,
        )

        # Return the string representation of the result
        return resultString


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = MessageBox()
    w.setText("Warning: Backface Culling is now <hl>OFF</hl>")
    w.show()

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
