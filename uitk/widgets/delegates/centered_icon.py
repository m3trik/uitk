# !/usr/bin/python
# coding=utf-8
"""Centered icon painting for item-view cells.

An *action cell* holds an icon-only item (a clickable scope toggle, a
reset button, a lock indicator, …).  Qt's default delegate positions the
decoration via ``QStyle::SE_ItemViewItemDecoration`` — style-dependent,
left-aligned, and offset by the cell's ``::item`` padding — so a small
icon ends up shoved sideways and clipping inconsistently.

:func:`paint_centered_icon` is the single source of truth for "draw this
icon centered in this cell", shared by:

- :class:`CenteredIconActionDelegate` — centers the icon **and** keeps the
  row-spanning selection border (for tables that opt into
  :class:`~uitk.widgets.delegates.row_selection.RowSelectionBorderDelegate`).
- :class:`uitk.widgets.table_actions._CenteredIconDelegate` — centers the
  icon with the plain (filled) selection.
"""
from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from uitk.widgets.delegates.row_selection import RowSelectionBorderDelegate

# Optional per-item icon opacity (0..1) read by CenteredIconActionDelegate. Set
# it on an item (``item.setData(ICON_OPACITY_ROLE, 0.4)``) to render a dimmed
# "disabled" icon — the delegate-painted equivalent of Qt greying a disabled
# button's icon. Absent / 1.0 paints at full opacity.
ICON_OPACITY_ROLE = QtCore.Qt.UserRole + 200


def fill_cell_background(painter, rect, index):
    """Paint an item's ``BackgroundRole`` tint into *rect*; ``True`` if it did.

    A delegate that paints its own content (a centered icon) and lets the style
    draw the cell chrome must fill the item brush itself: the stylesheet style's
    ``CE_ItemViewItem`` drops the item's ``BackgroundRole`` in favour of the QSS
    ``::item`` rules, so a per-state tint (a ``TableActions`` ``background``
    state, a "modified" cue) silently vanishes otherwise. Call this *before*
    ``drawControl`` (and clear ``opt.backgroundBrush`` so the style doesn't
    double-fill); the style still layers hover / selection over the tint.
    """
    brush = index.data(QtCore.Qt.BackgroundRole)
    if isinstance(brush, QtGui.QBrush) and brush.style() != QtCore.Qt.NoBrush:
        painter.fillRect(rect, brush)
        return True
    if isinstance(brush, QtGui.QColor) and brush.alpha() > 0:
        painter.fillRect(rect, brush)
        return True
    return False


def paint_centered_icon(painter, icon, cell, decoration_size, hover=False, opacity=1.0):
    """Draw *icon* centered within the *cell* rect.

    Parameters
    ----------
    painter : QtGui.QPainter
        Active painter (the delegate's).
    icon : QtGui.QIcon | None
        Icon to paint; ``None`` / null is a no-op.
    cell : QtCore.QRect
        The cell rectangle (``option.rect``).
    decoration_size : QtCore.QSize
        Preferred icon size (``option.decorationSize``); when invalid a
        square that fits the cell minus a small margin is used instead.
    hover : bool
        When ``True`` the icon's own opaque pixels are brightened
        (``SourceAtop``) so faint "inactive" tones read on hover without
        tinting the surrounding cell.
    opacity : float
        Painter opacity for the icon (``< 1.0`` dims it, e.g. a disabled cell).
    """
    if icon is None or icon.isNull():
        return

    target_size = decoration_size
    if not target_size.isValid() or target_size.width() <= 0:
        edge = max(8, min(cell.width(), cell.height()) - 4)
        target_size = QtCore.QSize(edge, edge)

    actual = icon.actualSize(target_size)
    if actual.width() <= 0 or actual.height() <= 0:
        edge = max(8, min(cell.width(), cell.height()) - 4)
        actual = QtCore.QSize(edge, edge)
    # Clamp so the pixmap never overflows the cell.
    actual = QtCore.QSize(
        min(actual.width(), cell.width()),
        min(actual.height(), cell.height()),
    )

    pixmap = icon.pixmap(actual)

    if hover:
        pixmap = pixmap.copy()
        p = QtGui.QPainter(pixmap)
        p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceAtop)
        p.fillRect(pixmap.rect(), QtGui.QColor(255, 255, 255, 110))
        p.end()

    x = cell.x() + (cell.width() - pixmap.width()) // 2
    y = cell.y() + (cell.height() - pixmap.height()) // 2
    if opacity < 1.0:
        painter.save()
        painter.setOpacity(opacity)
        painter.drawPixmap(x, y, pixmap)
        painter.restore()
    else:
        painter.drawPixmap(x, y, pixmap)


class CenteredIconActionDelegate(RowSelectionBorderDelegate):
    """Centers an item's icon while preserving the row-selection border.

    For an icon-only *action* column on a table that uses
    :class:`RowSelectionBorderDelegate` for selection: the base draws the
    cell background with the filled ``:selected`` highlight suppressed, the
    icon is painted centered (so the themed ``::item`` padding can't offset
    it), and — when the row is selected — the row-spanning outline segment
    is drawn so the border stays continuous across the action cells.

    The icon, its colour, and any background tint come from the item's
    ``DecorationRole`` / ``BackgroundRole`` (set by the caller), so a state
    change is a plain ``setIcon`` / ``setBackground`` — no widget churn.
    """

    def paint(self, painter, option, index):
        is_selected, opt = self._make_unselected_option(option, index)

        # Pull the icon from the model *before* clearing — reading ``opt.icon``
        # back after clearing returns a null wrapper in PySide.
        icon_data = index.data(QtCore.Qt.DecorationRole)
        if isinstance(icon_data, QtGui.QIcon):
            icon = icon_data
        elif icon_data is None:
            icon = None
        else:
            icon = QtGui.QIcon(icon_data)

        # Paint the item's BackgroundRole tint ourselves (a state cue, e.g. a
        # green 'modified' or a command-badge fill) — the stylesheet style would
        # otherwise drop it; cleared from ``opt`` so drawControl doesn't double-
        # fill. (Shared with table_actions._CenteredIconDelegate.)
        fill_cell_background(painter, option.rect, index)
        opt.backgroundBrush = QtGui.QBrush()

        # Let the style paint only the rest of the cell background (hover /
        # selection states): drop the default (left-aligned) decoration + text so
        # they don't compete with the centered icon.
        opt.icon = QtGui.QIcon()
        opt.text = ""
        opt.features &= ~QtWidgets.QStyleOptionViewItem.HasDecoration
        opt.features &= ~QtWidgets.QStyleOptionViewItem.HasDisplay
        widget = opt.widget
        style = widget.style() if widget else QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, opt, painter, widget)

        opacity = index.data(ICON_OPACITY_ROLE)
        paint_centered_icon(
            painter,
            icon,
            option.rect,
            option.decorationSize,
            hover=bool(option.state & QtWidgets.QStyle.State_MouseOver),
            opacity=float(opacity) if opacity is not None else 1.0,
        )

        if is_selected:
            self.paint_row_selection_border(painter, option, index)
