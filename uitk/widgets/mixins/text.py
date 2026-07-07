# !/usr/bin/python
# coding=utf-8
"""Text rendering for uitk widgets.

Hosts the stateless :class:`RichTextFormatter` (the single source of truth
for uitk's HTML/rich-text vocabulary) alongside the widget mixins that
render it — :class:`RichText` and :class:`TextOverlay` — plus the
:class:`TextTruncation` font-metrics helper.
"""
from typing import Optional, Union

from qtpy import QtWidgets, QtCore, QtGui


def _load_log_colors() -> dict:
    """Return pythontk's logging severity palette, or ``{}`` if unavailable.

    Sourced from pythontk's logging colours so the message boxes, text
    views, footers, and console logs all share one palette. Optional at
    this layer — a minimal environment without pythontk falls back to the
    per-token literal colours in :attr:`RichTextFormatter.PREFIX_SEVERITY`.
    """
    try:
        from pythontk.core_utils.logging_mixin import LoggingMixin

        return dict(LoggingMixin.LOG_COLORS)
    except Exception:  # noqa: BLE001 -- pythontk logging optional at this layer.
        return {}


class RichTextFormatter:
    """Stateless HTML pipeline shared by uitk's rich-text widgets.

    Pure class-method transforms used by :class:`MessageBox` (QLabel body)
    and :class:`TextViewBox` (QTextEdit body), and the single source of
    truth for uitk's styled-tag vocabulary so message boxes, text views,
    footers, and console logs all render the same palette. Both consumers
    route through Qt's QTextDocument engine, so the same pipeline yields
    matching output in either widget.

    Backgrounds are returned as CSS strings (see :meth:`resolve_background`)
    rather than baked into the HTML: ``background-color`` on inline
    ``<font>`` / ``<span>`` tags is unreliable across Qt builds, so the host
    widget applies the value via QSS on a stable selector instead.

    Retheme by subclassing and overriding the class attributes
    (``LOG_COLORS``, ``PREFIX_SEVERITY``, ``INLINE_STYLES``,
    ``DEFAULT_BACKGROUND_RGB``); the transform logic resolves against them
    at call time, so no method needs touching.
    """

    #: Severity -> colour. SSoT = pythontk's logging colours; ``{}`` falls
    #: back to the per-token literals in :attr:`PREFIX_SEVERITY`.
    LOG_COLORS = _load_log_colors()

    #: Level-prefix token -> (``LOG_COLORS`` severity key, literal fallback).
    #: Resolved against ``LOG_COLORS`` at call time, so overriding the palette
    #: restyles the prefixes for free.
    PREFIX_SEVERITY = {
        "Error:": ("ERROR", "red"),
        "Warning:": ("WARNING", "yellow"),
        "Note:": ("NOTICE", "blue"),
        "Result:": ("RESULT", "green"),
    }

    #: Bare HTML tag -> style-bearing equivalent.
    INLINE_STYLES = {
        "<p>": '<p style="color:white;">',
        "<hl>": '<hl style="color:yellow; font-weight: bold;">',
        "<body>": '<body style="color;">',
        "<b>": '<b style="font-weight: bold;">',
        "<strong>": '<strong style="font-weight: bold;">',
        "<mark>": '<font style="background-color: grey;">',
        "</mark>": "</font>",
    }

    #: Default background fill (R, G, B); see :meth:`resolve_background`.
    DEFAULT_BACKGROUND_RGB = (50, 50, 50)

    @classmethod
    def prefix_styles(cls) -> dict:
        """Map each level-prefix token to its coloured ``<hl>`` span."""
        return {
            token: f'<hl style="color:{cls.LOG_COLORS.get(key, fallback)};">{token}</hl>'
            for token, (key, fallback) in cls.PREFIX_SEVERITY.items()
        }

    @classmethod
    def apply_prefix_styles(cls, string: str) -> str:
        """Replace level-prefix tokens (``Error:``, ``Warning:`` ...) with styled spans."""
        for token, span in cls.prefix_styles().items():
            string = string.replace(token, span)
        return string

    @classmethod
    def apply_inline_styles(cls, string: str) -> str:
        """Replace bare HTML tags with their style-bearing equivalents."""
        for bare, styled in cls.INLINE_STYLES.items():
            string = string.replace(bare, styled)
        return string

    @staticmethod
    def wrap_font_color(string: str, color: str) -> str:
        return f"<font color={color}>{string}</font>"

    @staticmethod
    def wrap_font_size(string: str, size) -> str:
        return f"<font size={size}>{string}</font>"

    @classmethod
    def resolve_background(cls, background) -> Optional[str]:
        """Convert a background parameter to a CSS colour string or ``None``.

        Parameters:
            background: ``False`` / ``0`` -> ``None`` (no background);
                ``True`` -> opaque default dark grey;
                ``float`` in [0, 1] -> that opacity on the default dark grey;
                ``str`` -> returned verbatim (any valid CSS colour).
        """
        if background is False or background == 0:
            return None
        r, g, b = cls.DEFAULT_BACKGROUND_RGB
        if background is True:
            return f"rgba({r},{g},{b},255)"
        if isinstance(background, (int, float)):
            alpha = max(0, min(255, int(background * 255)))
            return f"rgba({r},{g},{b},{alpha})"
        return background

    @classmethod
    def format(
        cls,
        string: str,
        *,
        align: str = "left",
        font_color: str = "white",
        font_size: Union[int, str, None] = None,
    ) -> str:
        """Apply the standard uitk HTML pipeline to a string.

        Wraps in an alignment ``<div>`` (when no ``align=`` is already
        present), substitutes prefix tokens and known tags, then optionally
        wraps in ``<font color>`` / ``<font size>``.

        Parameters:
            string: Raw HTML or plain text.
            align: Alignment used only when *string* has no ``align=``.
            font_color: Foreground colour. Pass ``None`` or ``""`` to skip.
            font_size: ``<font size=N>`` value. Pass ``None`` to leave the
                host widget's native font size in effect.
        """
        if "align=" not in string:
            string = f"<div align='{align}'>{string}</div>"
        s = cls.apply_prefix_styles(string)
        s = cls.apply_inline_styles(s)
        if font_color:
            s = cls.wrap_font_color(s, font_color)
        if font_size is not None:
            s = cls.wrap_font_size(s, font_size)
        return s


def _make_translucent_label(parent) -> QtWidgets.QLabel:
    """Build a rich-text QLabel inside a zero-margin QHBoxLayout on *parent*.

    Shared scaffold for :class:`RichText` and :class:`TextOverlay`: a
    translucent, click-through QLabel that renders Qt rich text as an
    overlay on the host widget. The layout is parented to (and owned by)
    *parent*; the configured label is returned for the caller to style and
    track.
    """
    layout = QtWidgets.QHBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)

    label = QtWidgets.QLabel(parent)
    label.setTextFormat(QtCore.Qt.RichText)
    label.setAttribute(QtCore.Qt.WA_TranslucentBackground)
    label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
    layout.addWidget(label)
    return label


class TextTruncation:
    """Mixin providing reusable text truncation functionality for UI widgets."""

    def calculate_text_truncation(
        self,
        text,
        container_width=None,
        reserved_width=0,
        min_text_width=100,
        elide_mode=QtCore.Qt.ElideMiddle,
        font=None,
        custom_suffix="...",
    ):
        """
        Calculate truncated text that fits within available width using Qt font metrics.

        Parameters:
            text (str): The text to truncate
            container_width (int): Total container width. If None, uses self.width() or default
            reserved_width (int): Width reserved for other elements (buttons, icons, etc.)
            min_text_width (int): Minimum width to preserve for text
            elide_mode (Qt.TextElideMode): Truncation type:
                - QtCore.Qt.ElideLeft: "...end of text"
                - QtCore.Qt.ElideMiddle: "start...end" (default)
                - QtCore.Qt.ElideRight: "start of text..."
                - QtCore.Qt.ElideNone: No truncation (returns original text)
            font (QFont): Font to use for metrics. If None, uses self.font()
            custom_suffix (str): Custom suffix for manual truncation (when not using Qt elision)

        Returns:
            tuple: (truncated_text, available_width, original_width)
        """
        if not text:
            return "", 0, 0

        # Get font metrics
        if font is None:
            font = getattr(self, "font", lambda: QtGui.QFont())()
        fm = QtGui.QFontMetrics(font)

        # Calculate container width
        if container_width is None:
            # Try to get width from self, fallback to reasonable default
            if hasattr(self, "width"):
                container_width = self.width() if self.width() > 0 else 250
            else:
                container_width = 250

        # Calculate available width for text
        available_width = max(min_text_width, container_width - reserved_width)

        # Get original text width
        original_width = fm.horizontalAdvance(text)

        # Truncate if necessary
        if original_width <= available_width:
            truncated_text = text
        else:
            truncated_text = fm.elidedText(text, elide_mode, available_width)

        return truncated_text, available_width, original_width

    def calculate_character_truncation(
        self, text, max_chars, elide_mode=QtCore.Qt.ElideMiddle, suffix="..."
    ):
        """
        Truncate text by character count (not pixel-based).

        Parameters:
            text (str): Text to truncate
            max_chars (int): Maximum number of characters
            elide_mode (Qt.TextElideMode): Where to truncate
            suffix (str): Truncation indicator

        Returns:
            str: Truncated text
        """
        if not text or len(text) <= max_chars:
            return text

        if elide_mode == QtCore.Qt.ElideLeft:
            return suffix + text[-(max_chars - len(suffix)) :]
        elif elide_mode == QtCore.Qt.ElideRight:
            return text[: max_chars - len(suffix)] + suffix
        elif elide_mode == QtCore.Qt.ElideMiddle:
            if max_chars <= len(suffix):
                return suffix[:max_chars]
            available = max_chars - len(suffix)
            start_len = available // 2
            end_len = available - start_len
            return (
                text[:start_len] + suffix + text[-end_len:]
                if end_len > 0
                else text[:start_len] + suffix
            )
        else:  # ElideNone
            return text

    def calculate_word_truncation(
        self,
        text,
        max_chars,
        elide_mode=QtCore.Qt.ElideMiddle,
        suffix="...",
        word_boundary=True,
    ):
        """
        Truncate text respecting word boundaries.

        Parameters:
            text (str): Text to truncate
            max_chars (int): Maximum number of characters
            elide_mode (Qt.TextElideMode): Where to truncate
            suffix (str): Truncation indicator
            word_boundary (bool): Whether to respect word boundaries

        Returns:
            str: Truncated text
        """
        if not text or len(text) <= max_chars:
            return text

        if not word_boundary:
            return self.calculate_character_truncation(
                text, max_chars, elide_mode, suffix
            )

        words = text.split()
        if not words:
            return text

        if elide_mode == QtCore.Qt.ElideRight:
            result = ""
            for word in words:
                test_text = result + (" " if result else "") + word
                if len(test_text + suffix) <= max_chars:
                    result = test_text
                else:
                    break
            return result + suffix if result != text else text

        elif elide_mode == QtCore.Qt.ElideLeft:
            result = ""
            for word in reversed(words):
                test_text = word + (" " if result else "") + result
                if len(suffix + test_text) <= max_chars:
                    result = test_text
                else:
                    break
            return suffix + result if result != text else text

        elif elide_mode == QtCore.Qt.ElideMiddle:
            if len(suffix) >= max_chars:
                return suffix[:max_chars]

            # Try to keep first and last words
            if len(words) >= 2:
                first_word = words[0]
                last_word = words[-1]
                if len(first_word + last_word + suffix) <= max_chars:
                    return first_word + suffix + last_word

            # Fallback to character truncation
            return self.calculate_character_truncation(
                text, max_chars, elide_mode, suffix
            )

        return text

    def calculate_path_truncation(
        self,
        path,
        max_chars,
        preserve_filename=True,
        preserve_extension=True,
        suffix="...",
    ):
        """
        Truncate file/directory paths intelligently.

        Parameters:
            path (str): File or directory path
            max_chars (int): Maximum number of characters
            preserve_filename (bool): Keep filename intact if possible
            preserve_extension (bool): Keep file extension if possible
            suffix (str): Truncation indicator

        Returns:
            str: Truncated path
        """
        if not path or len(path) <= max_chars:
            return path

        # Handle different path separators
        separator = "\\" if "\\" in path else "/"
        parts = path.split(separator)

        if len(parts) <= 1:
            # No path separators, treat as simple text
            return self.calculate_character_truncation(
                path, max_chars, QtCore.Qt.ElideMiddle, suffix
            )

        filename = parts[-1] if parts[-1] else parts[-2]  # Handle trailing separators

        if preserve_filename and len(filename + suffix) <= max_chars:
            # Try to preserve filename and truncate directory path
            available = max_chars - len(filename) - len(suffix) - 1  # -1 for separator
            if available > 0:
                dir_path = separator.join(parts[:-1])
                if len(dir_path) <= available:
                    return path
                else:
                    truncated_dir = self.calculate_character_truncation(
                        dir_path, available, QtCore.Qt.ElideMiddle, ""
                    )
                    return truncated_dir + suffix + separator + filename
            else:
                # Not enough space, truncate filename too
                if preserve_extension and "." in filename:
                    name, ext = filename.rsplit(".", 1)
                    available_for_name = (
                        max_chars - len(ext) - len(suffix) - 1
                    )  # -1 for dot
                    if available_for_name > 0:
                        truncated_name = self.calculate_character_truncation(
                            name, available_for_name, QtCore.Qt.ElideLeft, ""
                        )
                        return truncated_name + suffix + "." + ext

                return self.calculate_character_truncation(
                    filename, max_chars, QtCore.Qt.ElideMiddle, suffix
                )

        # Fallback to simple character truncation
        return self.calculate_character_truncation(
            path, max_chars, QtCore.Qt.ElideMiddle, suffix
        )

    def _calculate_truncation_with_type(
        self, text, container_width, reserved_width, truncation_type
    ):
        """
        Internal helper to calculate text truncation based on type.

        Returns:
            tuple: (truncated_text, avail_width, orig_width, was_truncated)
        """
        if truncation_type == "pixel":
            truncated_text, avail_width, orig_width = self.calculate_text_truncation(
                text, container_width, reserved_width
            )
            was_truncated = orig_width > avail_width
        else:
            # For non-pixel types, estimate character limit from width
            avail_width = 0  # Not applicable for non-pixel modes
            orig_width = 0  # Not applicable for non-pixel modes

            if container_width:
                font = getattr(self, "font", lambda: QtGui.QFont())()
                fm = QtGui.QFontMetrics(font)
                avg_char_width = fm.averageCharWidth()
                available_width = max(50, (container_width or 250) - reserved_width)
                estimated_chars = max(5, available_width // avg_char_width)
            else:
                estimated_chars = 30  # Default

            if truncation_type == "char":
                truncated_text = self.calculate_character_truncation(
                    text, estimated_chars
                )
            elif truncation_type == "word":
                truncated_text = self.calculate_word_truncation(text, estimated_chars)
            elif truncation_type == "path":
                truncated_text = self.calculate_path_truncation(text, estimated_chars)
            else:
                truncated_text = text  # Unknown type, use original

            was_truncated = truncated_text != text

        return truncated_text, avail_width, orig_width, was_truncated

    def _apply_tooltip_if_needed(
        self, widget, text, truncated_text, tooltip, truncation_type, was_truncated
    ):
        """
        Internal helper to apply tooltip if text was truncated or custom tooltip provided.
        Only applies tooltip if widget supports setToolTip method.
        """
        # Check if widget supports tooltips before trying to set one
        if hasattr(widget, "setToolTip") and callable(getattr(widget, "setToolTip")):
            if tooltip:
                widget.setToolTip(tooltip)
            elif was_truncated:
                widget.setToolTip(text)  # Show full text in tooltip

    def apply_text_truncation(
        self,
        widget,
        text,
        container_width=None,
        reserved_width=0,
        tooltip=None,
        truncation_type="pixel",
    ):
        """
        Apply text truncation to an existing widget.

        Parameters:
            widget: Widget to apply truncation to (must have setText method)
            text (str): Text to truncate and apply
            container_width (int): Container width for calculation
            reserved_width (int): Width reserved for other elements
            tooltip (str): Tooltip text. If None, uses original text if truncated
            truncation_type (str): Type of truncation:
                - "pixel": Pixel-based using Qt font metrics (default)
                - "char": Character-based truncation
                - "word": Word-boundary aware truncation
                - "path": Intelligent path truncation

        Returns:
            tuple: (truncated_text, was_truncated) - the applied text and whether it was truncated

        Raises:
            TypeError: If widget doesn't have setText method
        """
        # Validate that the widget supports text setting
        if not hasattr(widget, "setText") or not callable(getattr(widget, "setText")):
            widget_type = type(widget).__name__
            supported_types = "QPushButton, QLabel, QLineEdit, QComboBox, QCheckBox, QRadioButton, etc."
            raise TypeError(
                f"Widget type '{widget_type}' does not support text truncation. "
                f"Widget must have a 'setText' method. Supported types include: {supported_types}"
            )

        truncated_text, avail_width, orig_width, was_truncated = (
            self._calculate_truncation_with_type(
                text, container_width, reserved_width, truncation_type
            )
        )

        widget.setText(truncated_text)

        self._apply_tooltip_if_needed(
            widget, text, truncated_text, tooltip, truncation_type, was_truncated
        )

        return truncated_text, was_truncated

    def create_truncated_button(
        self,
        text,
        container_width=None,
        reserved_width=0,
        tooltip=None,
        truncation_type="pixel",
        **button_kwargs,
    ):
        """
        Create a QPushButton with properly truncated text.

        Parameters:
            text (str): Button text to truncate
            container_width (int): Container width for calculation
            reserved_width (int): Width reserved for other elements
            tooltip (str): Tooltip text. If None, uses original text if truncated
            truncation_type (str): Type of truncation:
                - "pixel": Pixel-based using Qt font metrics (default)
                - "char": Character-based truncation
                - "word": Word-boundary aware truncation
                - "path": Intelligent path truncation
            **button_kwargs: Additional arguments passed to QPushButton constructor

        Returns:
            QPushButton: Button with truncated text and tooltip
        """
        button = QtWidgets.QPushButton(**button_kwargs)
        self.apply_text_truncation(
            button, text, container_width, reserved_width, tooltip, truncation_type
        )
        return button

    def create_truncated_label(
        self,
        text,
        container_width=None,
        reserved_width=0,
        tooltip=None,
        truncation_type="pixel",
        **label_kwargs,
    ):
        """
        Create a QLabel with properly truncated text.

        Parameters:
            text (str): Label text to truncate
            container_width (int): Container width for calculation
            reserved_width (int): Width reserved for other elements
            tooltip (str): Tooltip text. If None, uses original text if truncated
            truncation_type (str): Type of truncation ("pixel", "char", "word", "path")
            **label_kwargs: Additional arguments passed to QLabel constructor

        Returns:
            QLabel: Label with truncated text and tooltip
        """
        label = QtWidgets.QLabel(**label_kwargs)
        self.apply_text_truncation(
            label, text, container_width, reserved_width, tooltip, truncation_type
        )
        return label

    def update_widget_text_truncation(
        self,
        widget,
        text,
        container_width=None,
        reserved_width=0,
        tooltip=None,
        truncation_type="pixel",
    ):
        """
        Update an existing widget's text with proper truncation.

        Note: This method is now an alias for apply_text_truncation for backwards compatibility.

        Parameters:
            widget: Widget to update (must have setText method)
            text (str): New text to set
            container_width (int): Container width for calculation
            reserved_width (int): Width reserved for other elements
            tooltip (str): Tooltip text. If None, uses original text if truncated
            truncation_type (str): Type of truncation ("pixel", "char", "word", "path")

        Returns:
            tuple: (truncated_text, was_truncated) - the applied text and whether it was truncated
        """
        return self.apply_text_truncation(
            widget, text, container_width, reserved_width, tooltip, truncation_type
        )


class RichText:
    """Rich-text support mixin for widgets.

    When the text contains HTML tags it is rendered as Qt rich text via an
    overlay QLabel; otherwise it falls through to the widget's normal text
    handling. The styled-tag vocabulary (``<hl>``, ``<mark>``, the severity
    prefixes, ...) is defined once on :class:`RichTextFormatter` — the SSoT
    the rich-text widgets format against.

    Escape literal angle brackets as ``&lt;`` / ``&gt;``.
    """

    has_rich_text = False

    @property
    def richTextLabelDict(self):
        """Returns a list containing any rich text labels that have been created.
        Item indices are used the keys to retrieve the label values.

        Returns:
                (list)
        """
        try:
            return self._richTextLabelDict

        except AttributeError:
            self._richTextLabelDict = {}
            return self._richTextLabelDict

    @property
    def richTextSizeHintDict(self):
        """Returns a list containing the sizeHint any rich text labels that have been created.
        Item indices are used the keys to retrieve the size values.

        Returns:
                (list)
        """
        try:
            return self._richTextSizeHintDict

        except AttributeError:
            self._richTextSizeHintDict = {}
            return self._richTextSizeHintDict

    def richTextSizeHint(self, index=0):
        """The richTextSizeHint is the sizeHint of the actual widget if it were containing the text.

        Returns:
                (str) the widget's or the label's sizeHint.
        """
        if self.has_rich_text:
            return self._richTextSizeHintDict[index]

        else:
            return self.__class__.__base__.sizeHint(
                self
            )  # return standard widget sizeHint

    def _createRichTextLabel(self, index):
        """Return a translucent rich-text QLabel inside a QHBoxLayout."""
        label = _make_translucent_label(self)
        self.richTextLabelDict[index] = label

        self.set_rich_text_style(index)
        self.has_rich_text = True

        return label

    def set_rich_text_style(self, index=0, textColor="white"):
        """Set the stylesheet for a QLabel.

        Parameters:

        """
        label = self.getRichTextLabel(index)
        label.setStyleSheet(
            """
            QLabel {{
                color: {0};
                margin: 3px 0px 0px 0px; /* top, right, bottom, left */
                padding: 0px 5px 0px 5px; /* top, right, bottom, left */
            }}
        """.format(
                textColor
            )
        )

    def getRichTextLabel(self, index=0):
        """ """
        try:
            label = self.richTextLabelDict[index]
        except KeyError:
            label = self._createRichTextLabel(index)

        return label

    def _text(self, index=None):
        """Gets the text for the widget or widget item.

        Parameters:
                item (str)(int): item text or item index
        """
        try:
            return self.__class__.__base__.text(self)

        except AttributeError:
            if index is not None:
                return self.__class__.__base__.itemText(self, index)
            else:
                return self.__class__.__base__.currentText(self)

    def richText(self, index=None):
        """
        Returns:
                (str) the widget's or the label's text.
        """
        try:
            index = index if index else 0
            label = self.richTextLabelDict[index]
            return label.text()
        except KeyError:  # no rich text at that index. return standard text.
            pass

        return self._text(index)  # return standard widget text

    def _setText(self, text, index=0):
        """Sets the text for the widget or widget item.

        Parameters:
                item (str)(int): item text or item index
        """
        try:
            self.__class__.__base__.setText(self, text)

        except AttributeError:
            self.__class__.__base__.setItemText(self, index, text)

    def setRichText(self, text, index=0):
        """If the text string contains rich text formatting:
                Set the rich text label text.
                Add whitespace to the actual widget text until it matches the sizeHint of what it would containing the label's text.

        Parameters:
                text (str): The desired widget's display text.
                index (int): For setting text requires an index. ie. comboBox
        """
        if text and all(
            i in text for i in ("<", ">")
        ):  # check the text string for rich text formatting.
            label = self.getRichTextLabel(index)

            label.setText(text)
            self.updateGeometry()

            self._setText(
                text, index
            )  # temporarily set the text to get the sizeHint value.
            sizeHint = self.richTextSizeHintDict[index] = (
                self.__class__.__base__.sizeHint(self)
            )

            self._setText(
                None, index
            )  # clear the text, and add whitespaces until the sizeHint is the correct size.
            whiteSpace = " "
            while sizeHint.width() > self.__class__.__base__.sizeHint(self).width():
                self._setText(whiteSpace, index)
                whiteSpace += " "

        else:
            self._setText(text, index)  # set standard widget text

    def setAlignment(self, alignment="AlignLeft", index=0):
        """Override setAlignment to accept string alignment arguments as well as QtCore.Qt.AlignmentFlags.

        Parameters:
                alignment (str/obj): TextMixin alignment. valid values are: 'AlignLeft', 'AlignCenter', 'AlignRight' or QtCore.Qt.AlignLeft etc.
        """
        if isinstance(alignment, str):
            alignment = getattr(QtCore.Qt, alignment)

        label = self.getRichTextLabel(index)
        label.setAlignment(alignment)


class TextOverlay:
    """ """

    hasTextOverlay = False

    @property
    def textOverlayLabel(self):
        """Return a QLabel inside a QHBoxLayout."""
        try:
            return self._textOverlayLabel

        except AttributeError:
            self._textOverlayLabel = _make_translucent_label(self)
            self._textOverlayLabel.setStyleSheet(
                """
                    QLabel {
                        margin: 3px 0px 0px 0px; /* top, right, bottom, left */
                        padding: 0px 2px 0px 2px; /* top, right, bottom, left */
                    }"""
            )

            self.hasTextOverlay = True

            return self._textOverlayLabel

    def setTextOverlay(self, text, color=None, alignment=None):
        """If the text string contains rich text formatting:
                Set the rich text label text.
                Add whitespace to the actual widget text until it matches the sizeHint of what it would containing the label's text.

        Parameters:
                text (str): The desired widget's display text.
                index (int): For setting text requires an index. ie. comboBox
                color (str):  The desired text color.
                alignment (str/obj): TextMixin alignment. valid values are: 'AlignLeft', 'AlignCenter', 'AlignRight' or QtCore.Qt.AlignLeft etc.
        """
        self.textOverlayLabel.setText(text)

        if color is not None:
            self.setTextOverlayColor(color)

        if alignment is not None:
            self.setTextOverlayAlignment(alignment)

    def setTextOverlayAlignment(self, alignment="AlignLeft"):
        """Override setAlignment to accept string alignment arguments as well as QtCore.Qt.AlignmentFlags.

        Parameters:
                alignment (str/obj): TextMixin alignment. valid values are: 'AlignLeft', 'AlignCenter', 'AlignRight' or QtCore.Qt.AlignLeft etc.
        """
        if isinstance(alignment, str):
            alignment = getattr(QtCore.Qt, alignment)

        self.textOverlayLabel.setAlignment(alignment)

    def setTextOverlayColor(self, color):
        """Set the stylesheet for a QLabel.

        Parameters:
                color (str):  The desired text color.

        Example: setTextOverlayColor('rgb(185,185,185)')
        """
        self.setStyleSheet(
            """
                QLabel {{
                    color: {0};
                }}
            """.format(
                color
            )
        )


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv
    )  # return the existing QApplication object, or create a new one if none exists.

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
