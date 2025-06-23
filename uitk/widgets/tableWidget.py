# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtGui, QtCore
from typing import Optional, Callable, List

# From this package:
from uitk.widgets.mixins.convert import ConvertMixin


class HeaderMixin:
    def _init_header_behavior(self):
        self.horizontalHeader().setSectionsClickable(True)
        self.header_click_behavior = self.default_header_click_behavior
        self.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._sort_order = {}
        self.setSortingEnabled(True)

    def default_header_click_behavior(self, col):
        # Example: toggle ascending/descending
        current_order = self._sort_order.get(col, QtCore.Qt.AscendingOrder)
        order = (
            QtCore.Qt.DescendingOrder
            if current_order == QtCore.Qt.AscendingOrder
            else QtCore.Qt.AscendingOrder
        )
        self.sortItems(col, order)
        self._sort_order[col] = order

    def _on_header_clicked(self, col):
        self.header_click_behavior(col)


class CellFormatMixin(ConvertMixin):
    """Generic cell/column/header formatting for QTableWidget."""

    ACTION_COLOR_MAP = {
        "valid_fg": "#333333",
        "invalid_fg": "#B97A7A",
        "warning_fg": "#B49B5C",
        "info_fg": "#6D9BAA",
        "inactive_fg": "#AAAAAA",
        "invalid_bg": "#FBEAEA",
        "warning_bg": "#FFF6DC",
        "info_bg": "#E2F3F9",
        "selected_bg": "#E6E6E6",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._col_formatters = {}
        self._header_formatters = {}
        self._cell_formatters = {}
        self.cellChanged.connect(self._on_cell_edited)

    @staticmethod
    def action_color_formatter(item, value, *_):
        color = CellFormatMixin.ACTION_COLOR_MAP.get(str(value).lower())
        if color:
            item.setBackground(CellFormatMixin.to_qobject(color, QtGui.QColor))
            item.setForeground(CellFormatMixin.to_qobject("#222222", QtGui.QColor))

    @staticmethod
    def make_color_map_formatter(color_map):
        def _fmt(item, value, *_):
            key = str(value).lower()
            if key in color_map:
                item.setBackground(
                    CellFormatMixin.to_qobject(color_map[key], QtGui.QColor)
                )

        return _fmt

    def set_column_formatter(self, col, formatter, append=False):
        idx = self._resolve_col(col)
        if idx is None:
            return
        if append:
            self._col_formatters.setdefault(idx, []).append(formatter)
        else:
            self._col_formatters[idx] = [formatter]

    def set_header_formatter(self, header, formatter, append=False):
        idx = self._resolve_col(header)
        if idx is None:
            return
        if append:
            self._header_formatters.setdefault(header, []).append(formatter)
        else:
            self._header_formatters[header] = [formatter]

    def set_cell_formatter(self, row, col, formatter, append=False):
        key = (row, col)
        if append:
            self._cell_formatters.setdefault(key, []).append(formatter)
        else:
            self._cell_formatters[key] = [formatter]

    def clear_formatters(self):
        self._col_formatters.clear()
        self._header_formatters.clear()
        self._cell_formatters.clear()

    def apply_formatting(self):
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if not item:
                    continue
                for fmt in self._get_formatters(row, col):
                    fmt(
                        item,
                        item.data(QtCore.Qt.UserRole) or item.text(),
                        row,
                        col,
                        self,
                    )

    def _on_cell_edited(self, row, col):
        item = self.item(row, col)
        if item:
            for fmt in self._get_formatters(row, col):
                fmt(item, item.data(QtCore.Qt.UserRole) or item.text(), row, col, self)

    def _get_formatters(self, row, col) -> List[Callable]:
        formatters = []
        key = (row, col)
        if key in self._cell_formatters:
            formatters.extend(self._cell_formatters[key])
        if col in self._col_formatters:
            formatters.extend(self._col_formatters[col])
        header = self._header(col)
        if header in self._header_formatters:
            formatters.extend(self._header_formatters[header])
        return formatters

    def _resolve_col(self, col):
        if isinstance(col, int):
            return col
        for idx in range(self.columnCount()):
            hi = self.horizontalHeaderItem(idx)
            if hi and hi.text() == col:
                return idx
        return None

    def _header(self, col):
        hi = self.horizontalHeaderItem(col)
        return hi.text() if hi else str(col)


class TableWidget(QtWidgets.QTableWidget, HeaderMixin, CellFormatMixin):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self._init_header_behavior()
        CellFormatMixin.__init__(self)

        self.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)  # Always off, for all cells

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

    @property
    def menu(self):
        try:
            return self._menu
        except AttributeError:
            from uitk.widgets.menu import Menu

            self._menu = Menu(self, mode="option", fixed_item_height=20)
            return self._menu

    def item_data(self, row: int, column: int):
        item = self.item(row, column)
        if item is None:
            return None
        data = item.data(QtCore.Qt.UserRole)
        return data if data is not None else item.text()

    def set_item_data(self, row: int, column: int, value, user_data=None):
        item = QtWidgets.QTableWidgetItem(str(value) if value is not None else "")
        if user_data is not None:
            item.setData(QtCore.Qt.UserRole, user_data)
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        self.setItem(row, column, item)

    def add(self, data, clear: bool = True, headers: list = None):
        self.setUpdatesEnabled(False)
        try:
            if clear:
                self.setRowCount(0)
                self.setColumnCount(0)

            rows, cols, col_headers = [], 0, []

            if isinstance(data, dict) and all(
                isinstance(v, (list, tuple)) for v in data.values()
            ):
                col_headers = list(data.keys())
                cols = len(col_headers)
                maxlen = max(len(col) for col in data.values())
                rows = [
                    [data[k][i] if i < len(data[k]) else "" for k in col_headers]
                    for i in range(maxlen)
                ]
            elif isinstance(data, (list, tuple)) and data and isinstance(data[0], dict):
                col_headers = list(data[0].keys())
                cols = len(col_headers)
                rows = [[row.get(k, "") for k in col_headers] for row in data]
            elif (
                isinstance(data, (list, tuple))
                and data
                and isinstance(data[0], (list, tuple))
            ):
                cols = max(len(row) for row in data)
                rows = [list(row) + [""] * (cols - len(row)) for row in data]
            elif isinstance(data, (list, tuple)):
                cols, rows = 1, [[v] for v in data]
            elif isinstance(data, dict):
                col_headers = list(data.keys())
                cols, rows = len(col_headers), [[data[k] for k in col_headers]]
            else:
                cols, rows = 1, [[data]]

            if headers and len(headers) == cols:
                col_headers = [str(h) for h in headers]

            self.setColumnCount(cols)
            self.setRowCount(len(rows))
            if col_headers:
                self.setHorizontalHeaderLabels([str(h) for h in col_headers])

            self.blockSignals(True)
            for row_idx, row in enumerate(rows):
                for col_idx, value in enumerate(row):
                    # Accept (display, data) tuple or just value
                    if isinstance(value, tuple) and len(value) == 2:
                        text, data_val = value
                    else:
                        text, data_val = value, None
                    item = QtWidgets.QTableWidgetItem(
                        str(text) if text is not None else ""
                    )
                    if data_val is not None:
                        item.setData(QtCore.Qt.UserRole, data_val)
                    self.setItem(row_idx, col_idx, item)
            self.blockSignals(False)
        finally:
            self.setUpdatesEnabled(True)
        self.apply_formatting()

    def selected_node(self):
        row = self.currentRow()
        if row < 0:
            return None
        data = self.item(row, 1)
        return data.data(QtCore.Qt.UserRole) if data else None

    def selected_label(self):
        row = self.currentRow()
        if row < 0:
            return None
        data = self.item(row, 0)
        return data.text() if data else None

    def clear_all(self):
        self.setRowCount(0)

    def fit_to_path_column(self, path_col: int = 1):
        self.resizeColumnToContents(path_col)
        self.resizeRowsToContents()


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    tbl = TableWidget()
    tbl.add([("Texture1", "Node1"), ("Texture2", "Node2"), ("Texture3", "Node3")])
    tbl.on_cell_edited.connect(
        lambda row, col, text: print(f"Cell edited at ({row}, {col}): {text}")
    )
    tbl.on_row_selected.connect(
        lambda row, node: print(f"Row selected: {row}, Node: {node}")
    )
    tbl.on_context_menu.connect(lambda pos: print(f"Context menu requested at {pos}"))

    tbl.show()
    sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

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
