# !/usr/bin/python
# coding=utf-8
"""A combo's dropdown affordance -- one part of
:class:`~uitk.widgets.widgetComboBox.WidgetComboBox` (see
``widget_combo_box_parts``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from qtpy import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from uitk.widgets.widgetComboBox import WidgetComboBox


class _ArrowAffordance:
    """A :class:`WidgetComboBox`'s optional dropdown affordance, drawn after
    the displayed text: a font-scaled chevron, or a custom icon.

    Owns its direction, icon and opacity; holds the combo and paints on it.
    """

    # The unit vector each direction's chevron apex points along.
    APEX = {"down": (0, 1), "up": (0, -1), "left": (-1, 0), "right": (1, 0)}
    DIRECTIONS = (None, *APEX)

    # Chevron extents as fractions of the font's ascent: 0.8 em across, 0.4 em
    # deep -- the 2:1 of the icon set's ``chevron_down``.
    CHEVRON_HALF_SPAN = 0.4
    CHEVRON_HALF_DEPTH = 0.2

    def __init__(self, combo: "WidgetComboBox") -> None:
        self._combo = combo
        # Off by default — matching the base ``ComboBox``, which draws none.
        self.direction: Optional[str] = None
        self.icon: Optional[QtGui.QIcon] = None
        self.alpha: float = 1.0

    def set_direction(self, value: Optional[str]) -> None:
        if value not in self.DIRECTIONS:
            raise ValueError(
                f"arrow_direction must be one of {self.DIRECTIONS}, got {value!r}"
            )
        if value == self.direction:
            return
        self.direction = value
        self._combo.update()

    def set_icon(self, icon: Optional[QtGui.QIcon]) -> None:
        if icon is not None and not isinstance(icon, QtGui.QIcon):
            raise TypeError(
                f"arrow_icon must be a QIcon or None, got {type(icon).__name__}"
            )
        self.icon = icon
        self._combo.update()

    def set_alpha(self, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        if value == self.alpha:
            return
        self.alpha = value
        self._combo.update()

    def chevron(self, direction: str, em: float) -> QtGui.QPolygonF:
        """Build the open chevron polyline (arm, apex, arm) centred on the origin.

        ``em`` is a font-derived reference size (``fontMetrics.ascent``), so
        the chevron scales with the font.  The apex points *direction*; the
        arms spread across the perpendicular axis.
        """
        span = em * self.CHEVRON_HALF_SPAN
        depth = em * self.CHEVRON_HALF_DEPTH
        ax, ay = self.APEX[direction]
        px, py = abs(ay), abs(ax)  # the perpendicular the arms spread along
        return QtGui.QPolygonF(
            [
                QtCore.QPointF(-ax * depth - px * span, -ay * depth - py * span),
                QtCore.QPointF(ax * depth, ay * depth),
                QtCore.QPointF(-ax * depth + px * span, -ay * depth + py * span),
            ]
        )

    def paint(self) -> None:
        """Overlay the affordance on the combo just painted (see
        :meth:`WidgetComboBox.paintEvent`)."""
        combo = self._combo
        direction = self.direction
        icon = self.icon
        has_icon = icon is not None and not icon.isNull()
        if direction is None and not has_icon:
            return

        # The text AlignedComboBox.paintEvent draws: the header when no item
        # is current, otherwise the current item's text with its display-only
        # adornments (prefix and " *" suffix), so the arrow follows all of it.
        if combo.currentIndex() == -1 and getattr(combo, "header_text", None):
            text = combo.header_text
            alignment = getattr(combo, "header_alignment", QtCore.Qt.AlignLeft)
        else:
            text = combo.format_current_display_text(combo.currentText() or "")
            alignment = QtCore.Qt.AlignLeft

        if not text:
            return

        # Edit-field rect via the style → honours theme padding / frame.
        opt = QtWidgets.QStyleOptionComboBox()
        combo.initStyleOption(opt)
        field_rect = combo.style().subControlRect(
            QtWidgets.QStyle.CC_ComboBox,
            opt,
            QtWidgets.QStyle.SC_ComboBoxEditField,
            combo,
        )

        fm = QtGui.QFontMetrics(combo.font())
        text_width = fm.horizontalAdvance(text)
        em = fm.ascent()  # font-relative sizing: bigger font, bigger glyph + gap

        if has_icon:
            # A square a touch larger than the chevron's span, so a glyph
            # reads at a comparable weight.
            side = max(8, int(round(em * 1.2)))
            half_width = side / 2.0
        else:
            chevron = self.chevron(direction, em)
            half_width = chevron.boundingRect().width() / 2.0
        cx = (
            combo._compute_text_end_x(field_rect, text_width, alignment)
            + em * 0.5  # the gap after the text, ~6 px at a 12 px ascent
            + half_width
        )
        cy = field_rect.center().y() + 1

        painter = QtGui.QPainter(combo)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setOpacity(self.alpha)

            if has_icon:
                # Honour the disabled state the same way the chevron dims via
                # QPalette.Disabled.
                mode = QtGui.QIcon.Normal if combo.isEnabled() else QtGui.QIcon.Disabled
                pixmap = icon.pixmap(QtCore.QSize(side, side), mode)
                painter.drawPixmap(
                    QtCore.QPointF(cx - side / 2.0, cy - side / 2.0), pixmap
                )
            else:
                color = combo.palette().color(
                    QtGui.QPalette.Disabled
                    if not combo.isEnabled()
                    else QtGui.QPalette.Active,
                    QtGui.QPalette.Text,
                )
                # The icon set's stroke: 1.5 px at a 12 px ascent, round ends.
                pen = QtGui.QPen(color, max(1.0, em * 0.125))
                pen.setCapStyle(QtCore.Qt.RoundCap)
                pen.setJoinStyle(QtCore.Qt.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawPolyline(chevron.translated(cx, cy))
        finally:
            painter.end()
