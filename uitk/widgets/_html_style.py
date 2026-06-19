# !/usr/bin/python
# coding=utf-8
"""HTML formatting helpers shared by uitk's rich-text widgets.

Pure stateless transforms used by :class:`MessageBox` (QLabel body) and
:class:`TextViewBox` (QTextEdit body). Both render through Qt's
QTextDocument engine so the same HTML pipeline produces matching output
in either widget.

Backgrounds are returned as CSS strings rather than baked into the HTML
because ``background-color`` on inline ``<font>`` / ``<span>`` tags is
unreliable across Qt builds. The host widget applies the value via QSS
on a stable selector instead.
"""
from typing import Optional, Union

# Severity → colour palette, sourced from pythontk's logging colours so the
# message boxes, text views, footers, and console logs all share one SSoT.
# Falls back to an empty dict (per-use literal fallbacks below) if pythontk's
# logging module isn't importable in a minimal environment.
try:
    from pythontk.core_utils.logging_mixin import LoggingMixin as _LoggingMixin

    LOG_COLORS = dict(_LoggingMixin.LOG_COLORS)
except Exception:  # noqa: BLE001 — pythontk logging optional at this layer.
    LOG_COLORS = {}


# Level-prefix tokens → coloured span, keyed by the ``LOG_COLORS`` severity.
_PREFIX_COLOR = {
    "Error:": LOG_COLORS.get("ERROR", "red"),
    "Warning:": LOG_COLORS.get("WARNING", "yellow"),
    "Note:": LOG_COLORS.get("NOTICE", "blue"),
    "Result:": LOG_COLORS.get("RESULT", "green"),
}
PREFIX_STYLES = {
    token: f'<hl style="color:{color};">{token}</hl>'
    for token, color in _PREFIX_COLOR.items()
}

INLINE_STYLES = {
    "<p>": '<p style="color:white;">',
    "<hl>": '<hl style="color:yellow; font-weight: bold;">',
    "<body>": '<body style="color;">',
    "<b>": '<b style="font-weight: bold;">',
    "<strong>": '<strong style="font-weight: bold;">',
    "<mark>": '<font style="background-color: grey;">',
    "</mark>": "</font>",
}


def apply_prefix_styles(string: str) -> str:
    """Replace level-prefix tokens (``Error:``, ``Warning:`` ...) with styled spans."""
    for k, v in PREFIX_STYLES.items():
        string = string.replace(k, v)
    return string


def apply_inline_styles(string: str) -> str:
    """Replace bare HTML tags with style-bearing equivalents."""
    for k, v in INLINE_STYLES.items():
        string = string.replace(k, v)
    return string


def wrap_font_color(string: str, color: str) -> str:
    return f"<font color={color}>{string}</font>"


def wrap_font_size(string: str, size) -> str:
    return f"<font size={size}>{string}</font>"


def resolve_background(background) -> Optional[str]:
    """Convert a background parameter to a CSS colour string or ``None``.

    Parameters:
        background: ``False`` / ``0`` → ``None`` (no background);
            ``True`` → opaque default dark grey;
            ``float`` in [0, 1] → that opacity on the default dark grey;
            ``str`` → returned verbatim (any valid CSS colour).
    """
    if background is False or background == 0:
        return None
    if background is True:
        return "rgba(50,50,50,255)"
    if isinstance(background, (int, float)):
        alpha = max(0, min(255, int(background * 255)))
        return f"rgba(50,50,50,{alpha})"
    return background


def format_rich_text(
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
    s = apply_prefix_styles(string)
    s = apply_inline_styles(s)
    if font_color:
        s = wrap_font_color(s, font_color)
    if font_size is not None:
        s = wrap_font_size(s, font_size)
    return s
