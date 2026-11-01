# !/usr/bin/python
# coding=utf-8
"""Text rendering for uitk widgets.

Hosts the stateless :class:`RichTextFormatter` (the single source of truth
for uitk's HTML/rich-text vocabulary) alongside the widget mixins that
render it — :class:`RichText` and :class:`TextOverlay`.
"""

import re
from typing import Optional, Union

from qtpy import QtWidgets, QtCore

#: A region whose newlines HTML already honours, so a ``<br>`` would double
#: them. Captured (not consumed) so :func:`re.split` hands the block back.
_PRESERVED_REGION = re.compile(r"(<pre\b.*?</pre>)", re.IGNORECASE | re.DOTALL)

#: A newline an explicit ``<br>`` already accounts for, either side of it.
#: ``[^\S\n]`` is "whitespace that is not the newline itself", so only the
#: indentation between the tag and the break is absorbed.
_REDUNDANT_NEWLINE = re.compile(
    r"(<br\s*/?>)[^\S\n]*\n|\n[^\S\n]*(?=<br\s*/?>)", re.IGNORECASE
)

#: Markup, split out (and handed back by :func:`re.split`) so only the text
#: between tags is searched for addresses.
_TAG = re.compile(r"(<[^>]*>)")

#: An anchor's opening or closing tag; group 1 is a closing tag's slash.
_ANCHOR_TAG = re.compile(r"<\s*(/?)\s*a\b", re.IGNORECASE)

#: A web address in running text: up to whitespace, markup, a quote, or an
#: escaped bracket or quote (``&lt;https://x&gt;``).
_WEB_ADDRESS = re.compile(
    r"https?://(?:(?!&(?:lt|gt|quot|apos|#0*39);)[^\s<>\"'])+", re.IGNORECASE
)

#: What ends the sentence around an address rather than the address:
#: ``live at http://127.0.0.1:8118/.`` links the address, not the full stop.
_SENTENCE_END = ".,;:!?…"

#: A closing bracket -> its opener. Trailing, it is the address's own only
#: when the address opened it: ``(see https://x/a)`` vs ``https://x/Foo_(bar)``.
_BRACKETS = {")": "(", "]": "[", "}": "{"}


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

    @staticmethod
    def _load_log_colors() -> dict:
        """Return pythontk's logging severity palette, or ``{}`` if unavailable.

        Sourced from pythontk's logging colours so the message boxes, text
        views, footers, and console logs all share one palette. Optional at
        this layer — a minimal environment without pythontk falls back to the
        per-token literal colours in :attr:`PREFIX_SEVERITY`.
        """
        try:
            from pythontk.core_utils.logging_mixin import LoggingMixin

            return dict(LoggingMixin.LOG_COLORS)
        except Exception:  # noqa: BLE001 -- pythontk logging optional at this layer.
            return {}

    #: Severity -> colour. SSoT = pythontk's logging colours; ``{}`` falls
    #: back to the per-token literals in :attr:`PREFIX_SEVERITY`.
    # ``.__func__`` unwraps the staticmethod: a bare ``staticmethod`` object is
    # not directly callable before Python 3.10, and this runs at class-body time.
    LOG_COLORS = _load_log_colors.__func__()

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

    @classmethod
    def apply_line_breaks(cls, string: str) -> str:
        """Render each newline as a line break instead of collapsing it.

        Both consumers set ``Qt.RichText``, and HTML collapses whitespace, so
        a newline in a message body renders as a SPACE and every intended
        break is lost silently. Measured across the six packages 2026-09-10:
        667 rich-text strings carry a real newline, 665 of which want the
        break. The two that do not are one ``__main__`` demo, whose newlines
        sit inside ``<pre>`` where HTML already honours them.

        Two things are therefore left alone: a ``<pre>`` region, and a newline
        an author already wrote a ``<br>`` for (three extapps tooltips wrap
        their SOURCE that way, and converting would give them a blank line).

        Line endings are normalised first. ``TextViewBox`` shows captured
        subprocess output, which on Windows arrives CRLF, and absorbing before
        normalising would leave the bare CR to become a second break of its
        own -- a blank line between every line of a build log.

        Parameters:
            string: Raw HTML or plain text, mid-pipeline.

        Returns:
            The same string with every free newline rendered as ``<br>``.
        """
        if "\n" not in string and "\r" not in string:
            return string
        parts = _PRESERVED_REGION.split(string)
        # split() with one capturing group alternates outside/inside, starting
        # outside, so the even indices are everything not inside a <pre>.
        for i in range(0, len(parts), 2):
            normalised = parts[i].replace("\r\n", "\n").replace("\r", "\n")
            absorbed = _REDUNDANT_NEWLINE.sub(lambda m: m.group(1) or "", normalised)
            parts[i] = absorbed.replace("\n", "<br>")
        return "".join(parts)

    @classmethod
    def linkify(cls, string: str) -> str:
        """Make each bare ``http(s)`` address in *string* a link.

        Messages give addresses as plain text -- a share link, the page that
        enables a provider, where to install a tool -- which a dialog or log
        pane then showed as text to select and copy by hand. Only running text
        is touched: markup (an ``<img src>``, a ``title``), the text of an
        existing ``<a>`` and every other scheme (``action://``, ``file://``)
        pass through, and so does the punctuation ending the sentence around
        an address. What opens a link is the host widget's (a log pane routes
        web links to the browser; a message box opens them itself).

        Parameters:
            string: Raw HTML or plain text.

        Returns:
            The same string with each bare web address wrapped in ``<a href>``.
        """
        if "://" not in string:
            return string
        parts = _TAG.split(string)
        in_anchor = False
        # split() with one capturing group alternates text/tag, text first.
        for i, part in enumerate(parts):
            if i % 2:
                anchor = _ANCHOR_TAG.match(part)
                if anchor:
                    in_anchor = not anchor.group(1)
            elif not in_anchor and "://" in part:
                parts[i] = _WEB_ADDRESS.sub(cls._link_address, part)
        return "".join(parts)

    @staticmethod
    def _link_address(match) -> str:
        """One :func:`linkify` match, linked -- less the sentence around it."""
        address = match.group(0)
        end = len(address)
        while end:
            char = address[end - 1]
            opener = _BRACKETS.get(char)
            if char in _SENTENCE_END or (
                opener and address.count(char, 0, end) > address.count(opener, 0, end)
            ):
                end -= 1
            else:
                break
        address, tail = address[:end], address[end:]
        if address.endswith("://"):  # a scheme with nothing after it
            return match.group(0)
        return f'<a href="{address}">{address}</a>{tail}'

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
        present), substitutes prefix tokens and known tags, links bare web
        addresses (:meth:`linkify`), renders newlines as line breaks
        (:meth:`apply_line_breaks`), then optionally wraps in
        ``<font color>`` / ``<font size>``.

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
        s = cls.linkify(s)
        s = cls.apply_line_breaks(s)
        if font_color:
            s = cls.wrap_font_color(s, font_color)
        if font_size is not None:
            s = cls.wrap_font_size(s, font_size)
        return s


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

    @staticmethod
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
            # ``has_rich_text`` is set by ``_createRichTextLabel`` (reachable
            # via ``setAlignment`` / ``getRichTextLabel`` with no ``setRichText``
            # call), so the size dict may not hold this index yet. Route through
            # the lazy property and fall back to the base sizeHint when absent
            # rather than raising AttributeError/KeyError.
            size = self.richTextSizeHintDict.get(index)
            if size is not None:
                return size

        return self.__class__.__base__.sizeHint(self)  # return standard widget sizeHint

    def _createRichTextLabel(self, index):
        """Return a translucent rich-text QLabel inside a QHBoxLayout."""
        label = RichText._make_translucent_label(self)
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
        """.format(textColor)
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
            self._textOverlayLabel = RichText._make_translucent_label(self)
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
            """.format(color)
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
