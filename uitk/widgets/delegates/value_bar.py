# !/usr/bin/python
# coding=utf-8
"""A number in an item-view cell drawn as a bar: how much, at a glance."""

from __future__ import annotations

import math
from typing import Any, Callable, Optional, Sequence, Tuple

from qtpy import QtCore, QtGui, QtWidgets


class ValueBarDelegate(QtWidgets.QStyledItemDelegate):
    """Draws a cell's number as a bar between *minimum* and *maximum*, its value as text.

    The view's own background and selection are drawn first and the bar inset
    over them, so a selected row reads the same across every column. Editing is
    the base delegate's: a double-click types a new value.

    Parameters:
        minimum, maximum: The values at the bar's two ends (clamped between).
        scale: ``"linear"``, or ``"log"`` -- equal ratios take equal lengths,
            for a value spanning decades (needs ``minimum > 0``).
        color: The bar's fill (any QColor spelling); default the palette's highlight.
        gradient: ``[(position 0..1, color), ...]``: the track shows this
            gradient and the value is a marker on it -- for a value that is a
            point on a scale the gradient draws (a colour temperature).
        decimals: Places in the text (when no *formatter*).
        formatter: ``value -> text`` instead.
        ghost_role: An item data role holding a second value, drawn as a
            dashed marker -- a proposed value beside the current one.
        value_role: The role the number is read from (default ``EditRole``,
            falling back to the display text).

    Raises:
        ValueError: an unknown *scale*, a log scale from zero or below, or
            ``maximum <= minimum``.
    """

    SCALES = ("linear", "log")

    def __init__(
        self,
        parent=None,
        minimum: float = 0.0,
        maximum: float = 1.0,
        scale: str = "linear",
        color: Any = None,
        gradient: Optional[Sequence[Tuple[float, Any]]] = None,
        decimals: int = 2,
        formatter: Optional[Callable[[float], str]] = None,
        ghost_role: Optional[int] = None,
        value_role: int = QtCore.Qt.EditRole,
    ):
        super().__init__(parent)
        if scale not in self.SCALES:
            raise ValueError(f"Unknown scale {scale!r}; one of {self.SCALES}.")
        if scale == "log" and minimum <= 0:
            raise ValueError("A log scale starts above zero (minimum > 0).")
        if maximum <= minimum:
            raise ValueError("maximum must be above minimum.")
        self.minimum, self.maximum, self.scale = float(minimum), float(maximum), scale
        self.color = QtGui.QColor(color) if color is not None else None
        self.gradient = [(float(p), QtGui.QColor(c)) for p, c in gradient or ()]
        self.decimals = int(decimals)
        self.formatter = formatter
        self.ghost_role = ghost_role
        self.value_role = value_role

    # ------------------------------------------------------------------ values
    def fraction(self, value: float) -> float:
        """Where *value* sits along the bar, 0..1."""
        if self.scale == "log":
            if value <= 0:
                return 0.0
            low, high = math.log(self.minimum), math.log(self.maximum)
            f = (math.log(value) - low) / (high - low)
        else:
            f = (value - self.minimum) / (self.maximum - self.minimum)
        return min(1.0, max(0.0, f))

    def value_of(self, index: QtCore.QModelIndex, role: Optional[int] = None) -> Optional[float]:
        """The number *index* holds in *role* (default: :attr:`value_role`, then
        the display text), or ``None`` when it holds none."""
        roles = (role,) if role is not None else (self.value_role, QtCore.Qt.DisplayRole)
        for r in roles:
            data = index.data(r)
            if data is None or isinstance(data, bool):
                continue
            try:
                return float(data)
            except (TypeError, ValueError):
                continue
        return None

    def text_of(self, value: float) -> str:
        return self.formatter(value) if self.formatter else f"{value:.{self.decimals}f}"

    # ------------------------------------------------------------------ painting
    def paint(self, painter, option, index) -> None:
        value = self.value_of(index)
        if value is None:
            super().paint(painter, option, index)
            return
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""  # the background and selection only: the text goes over the bar
        widget = opt.widget
        style = widget.style() if widget else QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, opt, painter, widget)

        track = QtCore.QRectF(opt.rect.adjusted(3, 4, -3, -4))
        if track.width() <= 0 or track.height() <= 0:
            return
        palette = opt.palette
        selected = bool(opt.state & QtWidgets.QStyle.State_Selected)
        ink = palette.color(QtGui.QPalette.HighlightedText if selected else QtGui.QPalette.Text)
        x = track.left() + self.fraction(value) * track.width()
        painter.save()
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            if self.gradient:
                ramp = QtGui.QLinearGradient(track.topLeft(), track.topRight())
                for position, color in self.gradient:
                    ramp.setColorAt(position, color)
                painter.fillRect(track, ramp)
                self._marker(painter, x, track, ink, QtCore.Qt.SolidLine)
            else:
                rest = QtGui.QColor(palette.color(QtGui.QPalette.Mid))
                rest.setAlpha(70)
                painter.fillRect(track, rest)
                fill = QtGui.QColor(self.color or palette.color(QtGui.QPalette.Highlight))
                fill.setAlpha(170)
                painter.fillRect(
                    QtCore.QRectF(track.left(), track.top(), x - track.left(), track.height()),
                    fill,
                )
            if self.ghost_role is not None:
                ghost = self.value_of(index, self.ghost_role)
                if ghost is not None:
                    gx = track.left() + self.fraction(ghost) * track.width()
                    self._marker(painter, gx, track, ink, QtCore.Qt.DashLine)
            painter.setPen(ink)
            painter.drawText(
                track.adjusted(4, 0, -4, 0),
                int(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight),
                self.text_of(value),
            )
        finally:
            painter.restore()

    @staticmethod
    def _marker(painter, x: float, track: QtCore.QRectF, ink, style) -> None:
        """A vertical marker at *x*: ink over a dark edge, readable on any fill."""
        edge = QtGui.QPen(QtGui.QColor(0, 0, 0, 160), 3.5)
        painter.setPen(edge)
        painter.drawLine(QtCore.QPointF(x, track.top()), QtCore.QPointF(x, track.bottom()))
        pen = QtGui.QPen(ink, 1.5, style)
        painter.setPen(pen)
        painter.drawLine(QtCore.QPointF(x, track.top()), QtCore.QPointF(x, track.bottom()))
