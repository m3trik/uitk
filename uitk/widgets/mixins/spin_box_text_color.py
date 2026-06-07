# !/usr/bin/python
# coding=utf-8
"""Shared value-text coloring for spin-box widgets.

Used by :class:`uitk.widgets.spinBox.SpinBox` and
:class:`uitk.widgets.doubleSpinBox.DoubleSpinBox` — both derive from
``QDoubleSpinBox``. This mixin tints the displayed value text (e.g. red / green
/ blue for an X / Y / Z position triplet) as a thin, theme-friendly alternative
to per-axis prefixes.
"""
import re


# Our color directive is tagged with a ``/*tc*/`` marker so it can be replaced
# or removed without disturbing any other inline style on the widget (e.g. the
# option-box border tweaks appended during wrapping).
_TC_DIRECTIVE = re.compile(r"\s*/\*tc\*/[^;]*;")


class SpinBoxTextColorMixin:
    """Tint a spin box's displayed value text.

    The tint is applied as a ``color`` directive on the **spin box itself** (not
    its internal ``lineEdit()``): under the uitk theme the displayed value is
    drawn via the ``QAbstractSpinBox`` color rule, which overrides a color set
    on the embedded line edit — so the spin box is the only level that reliably
    wins. The directive is merged into (not allowed to clobber) any existing
    inline stylesheet. Pass ``None`` / ``""`` to clear it and fall back to the
    theme color.
    """

    def set_text_color(self, color) -> None:
        """Tint the displayed value text.

        Args:
            color: Any QSS color string (``"#ff5555"``, ``"red"``,
                ``"rgb(220,80,80)"``) — or ``None`` to clear the override.
        """
        self._text_color = color or None
        base = _TC_DIRECTIVE.sub("", self.styleSheet())
        if self._text_color:
            base = "{} /*tc*/color: {};".format(base, self._text_color).strip()
        self.setStyleSheet(base)

    def text_color(self):
        """The current value-text color override, or ``None`` if unset."""
        return getattr(self, "_text_color", None)
