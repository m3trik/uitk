# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtGui, QtCore
from typing import Optional, Callable, List

# From this package:
from uitk.widgets.mixins.convert import ConvertMixin
from uitk.widgets.mixins.attributes import AttributesMixin


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
        "valid": ("#3C8D3C", "#E6F4EA"),
        "invalid": ("#B97A7A", "#FBEAEA"),
        "warning": ("#B49B5C", "#FFF6DC"),
        "info": ("#6D9BAA", "#E2F3F9"),
        "inactive": ("#AAAAAA", None),
        "reset": (None, None),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._col_formatters = {}
        self._header_formatters = {}
        self._cell_formatters = {}
        self._item_defaults = {}  # {(row, col): (fg, bg)}
        self.cellChanged.connect(self._on_cell_edited)

    # Public API
    def set_column_formatter(self, col, formatter, append=False):
        """Set a formatter for a specific column."""
        idx = self._resolve_col(col)
        if idx is None:
            return
        if append:
            self._col_formatters.setdefault(idx, []).append(formatter)
        else:
            self._col_formatters[idx] = [formatter]

    def set_header_formatter(self, header, formatter, append=False):
        """Set a formatter for a specific header."""
        idx = self._resolve_col(header)
        if idx is None:
            return
        if append:
            self._header_formatters.setdefault(header, []).append(formatter)
        else:
            self._header_formatters[header] = [formatter]

    def set_cell_formatter(self, row, col, formatter, append=False):
        """Set a formatter for a specific cell (row, column)."""
        key = (row, col)
        if append:
            self._cell_formatters.setdefault(key, []).append(formatter)
        else:
            self._cell_formatters[key] = [formatter]

    def clear_formatters(self):
        """Clear all column, header, and cell formatters."""
        self._col_formatters.clear()
        self._header_formatters.clear()
        self._cell_formatters.clear()
        self._item_defaults.clear()

    def apply_formatting(self):
        """Apply formatting based on the registered formatters."""
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

    def ensure_valid_color(self, color, color_type, item, row, col):
        """Ensure a valid QColor, using fallback if needed."""
        try:
            return self.to_qobject(color, "QColor")
        except Exception:
            pass

        cached = self._get_default_colors(item, row, col)[
            0 if color_type == "fg" else 1
        ]
        try:
            return self.to_qobject(cached, "QColor")
        except Exception:
            print(
                f"[WARNING] Invalid {color_type} color: {color!r}, and fallback {cached!r} failed. Using None."
            )
            return None

    def set_action_color(
        self,
        item: QtWidgets.QTableWidgetItem,
        key: str,
        row: int = -1,
        col: int = -1,
        use_bg: bool = False,
    ):
        """Apply semantic color, but skip reset if nothing defined."""
        fg_raw, bg_raw = self.ACTION_COLOR_MAP.get(str(key).lower(), (None, None))

        # Skip entirely if reset and nothing to restore
        if key == "reset" and fg_raw is None and bg_raw is None:
            return

        fg = self.ensure_valid_color(fg_raw, "fg", item, row, col)
        bg = self.ensure_valid_color(bg_raw, "bg", item, row, col) if use_bg else None

        if row >= 0 and col >= 0:
            default_fg, default_bg = self._get_default_colors(item, row, col)
            fg = fg or self.to_qobject(default_fg, "QColor")
            if use_bg:
                bg = bg or self.to_qobject(default_bg, "QColor")

        if fg:
            item.setForeground(fg)
        if use_bg and bg:
            item.setBackground(bg)

    def action_color_formatter(self, item, value, *_):
        key = str(value).lower()
        fg, bg = CellFormatMixin.ACTION_COLOR_MAP.get(key, (None, None))
        fg = self.ensure_valid_color(fg, "fg", item, item.row(), item.column())
        bg = self.ensure_valid_color(bg, "bg", item, item.row(), item.column())
        item.setForeground(fg)
        item.setBackground(bg)

    def make_color_map_formatter(self, color_map: dict):
        def _fmt(item, value, *_):
            key = str(value).lower()
            fg, bg = color_map.get(key, (None, None))
            fg = self.ensure_valid_color(fg, "fg", item, item.row(), item.column())
            bg = self.ensure_valid_color(bg, "bg", item, item.row(), item.column())
            item.setForeground(fg)
            item.setBackground(bg)

        return _fmt

    # Private methods
    def _on_cell_edited(self, row, col):
        item = self.item(row, col)
        if item:
            for fmt in self._get_formatters(row, col):
                fmt(item, item.data(QtCore.Qt.UserRole) or item.text(), row, col, self)

    @staticmethod
    def _get_default_colors(item, row: int, col: int):
        """Get the cached default colors for the item at the given row and col."""
        table = item.tableWidget()
        if not hasattr(table, "_item_defaults"):
            table._item_defaults = {}
        key = (row, col)
        cache = table._item_defaults
        if key not in cache:
            fg = item.foreground().color().name()
            bg = item.background().color().name()
            cache[key] = (fg, bg)
        return cache[key]

    def _get_formatters(self, row, col) -> list:
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


class TableWidget(
    QtWidgets.QTableWidget, HeaderMixin, AttributesMixin, CellFormatMixin
):

    def __init__(self, parent=None, selection_mode="extended", **kwargs):
        """
        Initialize TableWidget.

        Args:
            parent: Parent widget
            selection_mode: Selection mode string. Options:
                - "none": No selection allowed
                - "single": Single item selection only
                - "extended": Ctrl+Click multi-selection (default)
                - "multi": Click to toggle selection
            **kwargs: Additional attributes to set
        """
        super().__init__(parent)
        self._init_header_behavior()
        CellFormatMixin.__init__(self)

        self.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(False)
        self.setWordWrap(False)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Set selection mode
        self._set_selection_mode(selection_mode)

        self.set_attributes(**kwargs)

    def _set_selection_mode(self, mode_str):
        """Set the selection mode from a string."""
        mode_map = {
            "none": QtWidgets.QAbstractItemView.NoSelection,
            "single": QtWidgets.QAbstractItemView.SingleSelection,
            "extended": QtWidgets.QAbstractItemView.ExtendedSelection,
            "multi": QtWidgets.QAbstractItemView.MultiSelection,
        }

        mode = mode_map.get(
            mode_str.lower(), QtWidgets.QAbstractItemView.ExtendedSelection
        )
        self.setSelectionMode(mode)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)

    def set_selection_mode(self, mode_str):
        """Change the selection mode after initialization."""
        self._set_selection_mode(mode_str)

    def _show_context_menu(self, position):
        """Show the context menu at the given position."""
        if self.menu.contains_items:
            # Set the position before showing
            global_pos = self.mapToGlobal(position)
            self.menu.position = global_pos
            self.menu.show()

    @property
    def menu(self):
        try:
            return self._menu
        except AttributeError:
            from uitk.widgets.menu import Menu

            self._menu = Menu(
                self, trigger_button="right", fixed_item_height=20, hide_on_leave=True
            )
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

    def add(self, data, clear: bool = True, headers: list = None, **kwargs):
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
        self.set_attributes(**kwargs)
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

    def selected_nodes(self):
        """Get all selected nodes (UserRole data from column 1)"""
        selected_items = self.selectedItems()
        nodes = []
        processed_rows = set()

        for item in selected_items:
            row = item.row()
            if row not in processed_rows:
                processed_rows.add(row)
                data_item = self.item(row, 1)
                if data_item:
                    node_data = data_item.data(QtCore.Qt.UserRole)
                    if node_data:
                        nodes.append(node_data)
        return nodes

    def selected_labels(self):
        """Get all selected labels (text from column 0)"""
        selected_items = self.selectedItems()
        labels = []
        processed_rows = set()

        for item in selected_items:
            row = item.row()
            if row not in processed_rows:
                processed_rows.add(row)
                label_item = self.item(row, 0)
                if label_item:
                    labels.append(label_item.text())
        return labels

    def selected_rows(self):
        """Get all selected row numbers"""
        selected_items = self.selectedItems()
        return sorted(set(item.row() for item in selected_items))

    def clear_all(self):
        self.setRowCount(0)

    def stretch_column_to_fill(self, stretch_col: int):
        header = self.horizontalHeader()
        for col in range(self.columnCount()):
            if col == stretch_col:
                header.setSectionResizeMode(col, QtWidgets.QHeaderView.Stretch)
            else:
                header.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)


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
