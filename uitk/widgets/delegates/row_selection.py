# !/usr/bin/python
# coding=utf-8
"""Opt-in delegate for views whose cells carry their own background.

The default QSS selection is a filled blue
(``QAbstractItemView::item:selected``), which obliterates colour-coded
cell backgrounds — color swatches in
:class:`uitk.widgets.editors.color_mapping_editor.ColorMappingEditor`,
status palettes in
:class:`uitk.widgets.editors.shortcut_editor.registry_editor.ShortcutEditor`, etc.

This delegate mutes ``State_Selected`` before invoking the base paint
(so the QSS fill never lands) and instead draws a single continuous
1 px outline at the row edges.  In ``SelectRows`` mode the outline
spans the row by combining each cell's segment; in ``SelectItems`` /
``SelectColumns`` mode each selected cell gets its own outlined box.

Apply via ``view.setItemDelegate(RowSelectionBorderDelegate(view))``
after the view is fully configured.  Works on ``QTableView``,
``QTableWidget``, ``QListView``, and ``QListWidget`` — any
``QAbstractItemView``.
"""
from __future__ import annotations

from qtpy import QtGui, QtWidgets


class RowSelectionBorderDelegate(QtWidgets.QStyledItemDelegate):
    """Paints a 1 px row-spanning selection border.

    Subclasses that need their own cell rendering (e.g. an HTML
    delegate) should:

    1. Call :meth:`_make_unselected_option` at the top of ``paint`` to
       get an option with ``State_Selected`` cleared.
    2. Draw their custom cell content using that option.
    3. If the cell was originally selected, call
       :meth:`paint_row_selection_border` at the end.

    See :class:`uitk.widgets.editors.switchboard_browser._BrowserRowDelegate`
    for an HTML-rendering subclass.
    """

    #: Row-spanning selection border.  Subtle white at 140 alpha — the
    #: delegate's whole purpose is to keep cell backgrounds visible
    #: (color swatches, status palettes, tag chips), so the border has
    #: to read as a thin outline rather than overpower the content.
    #: Independent of the QSS ``:selected`` rule by design: editors
    #: that install this delegate are opting *out* of the default
    #: filled-blue selection.
    BORDER_COLOR = QtGui.QColor(255, 255, 255, 140)

    def paint(self, painter, option, index):
        is_selected, opt = self._make_unselected_option(option, index)
        widget = opt.widget
        style = widget.style() if widget else QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, opt, painter, widget)
        if is_selected:
            self.paint_row_selection_border(painter, option, index)

    def _make_unselected_option(self, option, index):
        """Return ``(is_selected, opt)`` with ``State_Selected`` cleared.

        Used by subclasses that need to draw cell content with the
        default :selected QSS suppressed so the row-spanning border
        isn't competing with per-cell outlines.
        """
        is_selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        if is_selected:
            opt.state &= ~QtWidgets.QStyle.State_Selected
        return is_selected, opt

    def paint_row_selection_border(self, painter, option, index):
        """Paint this cell's share of a row-spanning selection border.

        For ``SelectRows`` views every selected cell paints top +
        bottom; only the leftmost column paints the left edge, only
        the rightmost the right edge — combining into one continuous
        outline around the row.

        For other selection behaviors (``SelectItems`` /
        ``SelectColumns``) the four edges of the selected cell are
        drawn, giving a per-cell outline that matches the QSS one we
        suppressed.
        """
        model = index.model()
        if model is None:
            return

        view = option.widget
        behavior = (
            view.selectionBehavior()
            if hasattr(view, "selectionBehavior")
            else QtWidgets.QAbstractItemView.SelectItems
        )

        col = index.column()
        row = index.row()
        last_col = model.columnCount(index.parent()) - 1
        last_row = model.rowCount(index.parent()) - 1

        pen = QtGui.QPen(self.BORDER_COLOR)
        pen.setWidth(1)
        painter.save()
        painter.setPen(pen)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)

        # adjusted(0, 0, -1, -1) keeps the 1 px pen inside the cell
        # rect so the bottom/right edges aren't clipped by the next
        # cell's paint pass.
        r = option.rect.adjusted(0, 0, -1, -1)

        if behavior == QtWidgets.QAbstractItemView.SelectRows:
            painter.drawLine(r.left(), r.top(), r.right(), r.top())
            painter.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
            if col == 0:
                painter.drawLine(r.left(), r.top(), r.left(), r.bottom())
            if col == last_col:
                painter.drawLine(r.right(), r.top(), r.right(), r.bottom())
        elif behavior == QtWidgets.QAbstractItemView.SelectColumns:
            painter.drawLine(r.left(), r.top(), r.left(), r.bottom())
            painter.drawLine(r.right(), r.top(), r.right(), r.bottom())
            if row == 0:
                painter.drawLine(r.left(), r.top(), r.right(), r.top())
            if row == last_row:
                painter.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        else:
            painter.drawRect(r)

        painter.restore()
