# !/usr/bin/python
# coding=utf-8
"""Read a layout's contents without leaving ``QLayoutItem`` wrappers behind.

PySide's ``QLayout.itemAt`` (and ``QGridLayout.itemAtPosition``) parents the
item it returns to the layout's Python wrapper, so that item's wrapper lives as
long as the layout. Qt deletes the item itself, natively, when the widget it
holds is deleted or moved to another parent, and shiboken never hears of it:
the wrapper stays registered at the freed address. The next C++ object
allocated there comes back to Python as that ``QWidgetItem`` --
``QApplication.allWidgets()`` lists one, a widget's ``style()`` answers one, and
a Python ``QStyle`` override handed one as its ``widget`` faults natively the
moment it passes it on (PySide 6.10, in ``storePythonOverrideErrorOrPrint``):
the uitk suite's intermittent exit 139.

Everything here is read through objects shiboken does track: the direct child
widgets of the layout's parent widget (``indexOf`` places each one) and the
layout's own child layouts. A spacer, the one item that is neither, is still
read through ``itemAt``; that is safe for it, because Qt never deletes a spacer
behind Python's back.
"""

from typing import Dict, List, Optional, Union

from qtpy import QtWidgets


class _LayoutItems:
    """Wrapper-safe reads of a layout's items: its widgets, child layouts, spacers."""

    @staticmethod
    def _indexed_widgets(layout: QtWidgets.QLayout) -> Dict[int, QtWidgets.QWidget]:
        """``{index: widget}`` for each widget *layout* itself holds."""
        parent = layout.parentWidget()
        if parent is None:  # not installed yet: its widgets have no common parent
            return {}
        indexed = {}
        # children(), not findChildren(QWidget, ""): an empty name is not "any
        # name" there, it matches only the children whose objectName is empty.
        for child in parent.children():
            # Also drops a stale wrapper minted elsewhere that answers for a child.
            if not isinstance(child, QtWidgets.QWidget):
                continue
            index = layout.indexOf(child)
            if index >= 0:
                indexed[index] = child
        return indexed

    @staticmethod
    def _indexed_layouts(layout: QtWidgets.QLayout) -> Dict[int, QtWidgets.QLayout]:
        """``{index: child layout}`` for each layout nested directly in *layout*."""
        indexed = {}
        for child in layout.children():
            if isinstance(child, QtWidgets.QLayout):
                index = layout.indexOf(child)
                if index >= 0:
                    indexed[index] = child
        return indexed

    @classmethod
    def widgets(cls, layout: QtWidgets.QLayout) -> List[QtWidgets.QWidget]:
        """The widgets *layout* itself holds, in layout order.

        The same widgets ``itemAt(i).widget()`` yields for every index, without
        the item wrappers. Widgets of a nested layout belong to that layout.

        Parameters:
            layout: An installed layout (one with a parent widget); an
                uninstalled one has no widgets to report.

        Returns:
            The widgets, first item first.
        """
        indexed = cls._indexed_widgets(layout)
        return [indexed[i] for i in sorted(indexed)]

    @classmethod
    def widget_at(
        cls, layout: QtWidgets.QLayout, index: int
    ) -> Optional[QtWidgets.QWidget]:
        """The widget at *index* of *layout* -- ``itemAt(index).widget()``.

        Parameters:
            layout: An installed layout.
            index: The item index.

        Returns:
            The widget, or ``None`` when that item is a spacer or a nested
            layout, or *index* is out of range.
        """
        return cls._indexed_widgets(layout).get(index)

    @classmethod
    def layouts(cls, layout: QtWidgets.QLayout) -> List[QtWidgets.QLayout]:
        """The layouts nested directly in *layout*, in layout order.

        Parameters:
            layout: Any layout.

        Returns:
            The child layouts, first item first.
        """
        indexed = cls._indexed_layouts(layout)
        return [indexed[i] for i in sorted(indexed)]

    @classmethod
    def entries(
        cls, layout: QtWidgets.QLayout
    ) -> List[Union[QtWidgets.QWidget, QtWidgets.QLayout, QtWidgets.QLayoutItem]]:
        """One entry per item of *layout*, in layout order.

        Parameters:
            layout: An installed layout.

        Returns:
            For each item: its widget, its nested layout, or -- for a spacer --
            the item itself.
        """
        widgets = cls._indexed_widgets(layout)
        layouts = cls._indexed_layouts(layout)
        entries = []
        for i in range(layout.count()):
            if i in widgets:
                entries.append(widgets[i])
            elif i in layouts:
                entries.append(layouts[i])
            else:
                item = layout.itemAt(i)  # a spacer: never deleted behind our back
                if item is not None:
                    entries.append(item)
        return entries

    @staticmethod
    def is_empty(
        entry: Union[QtWidgets.QWidget, QtWidgets.QLayout, QtWidgets.QLayoutItem],
    ) -> bool:
        """``QLayoutItem.isEmpty()`` for one of :meth:`entries`.

        A widget entry answers as Qt's ``QWidgetItem`` would for it: empty
        when hidden without retaining its size, or a window.

        Parameters:
            entry: A widget, layout or item from :meth:`entries`.

        Returns:
            Whether the layout treats the item as empty (no space, no gap).
        """
        if isinstance(entry, QtWidgets.QWidget):
            return (
                entry.isHidden() and not entry.sizePolicy().retainSizeWhenHidden()
            ) or entry.isWindow()
        return entry.isEmpty()

    @classmethod
    def widget_at_position(
        cls, layout: QtWidgets.QGridLayout, row: int, column: int
    ) -> Optional[QtWidgets.QWidget]:
        """The widget in cell (*row*, *column*) -- ``itemAtPosition(...).widget()``.

        The first item covering the cell decides, spans counted, as in Qt.

        Parameters:
            layout: An installed grid.
            row: The cell's row.
            column: The cell's column.

        Returns:
            The widget, or ``None`` when no item or a non-widget item covers
            the cell.
        """
        widgets = cls._indexed_widgets(layout)
        for index in range(layout.count()):
            r, c, row_span, col_span = layout.getItemPosition(index)
            if r <= row < r + max(row_span, 1) and c <= column < c + max(col_span, 1):
                return widgets.get(index)
        return None

    @staticmethod
    def first_free_row(layout: QtWidgets.QGridLayout, column: int = 0) -> int:
        """The first row whose cell in *column* holds no item (spans count).

        The ``while itemAtPosition(row, column) is not None: row += 1`` scan,
        read from item positions instead of items.

        Parameters:
            layout: The grid.
            column: The column to scan.

        Returns:
            The row index.
        """
        taken = set()
        for i in range(layout.count()):
            row, col, row_span, col_span = layout.getItemPosition(i)
            if col <= column < col + max(col_span, 1):
                taken.update(range(row, row + max(row_span, 1)))
        row = 0
        while row in taken:
            row += 1
        return row
