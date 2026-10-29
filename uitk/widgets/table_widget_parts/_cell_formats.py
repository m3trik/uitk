# !/usr/bin/python
# coding=utf-8
"""A table's cell formatting -- one part of
:class:`~uitk.widgets.tableWidget.TableWidget` (see ``table_widget_parts``)."""

from typing import TYPE_CHECKING

from qtpy import QtCore

import pythontk as ptk

from uitk.widgets.mixins.item_format import ItemFormatMixin

if TYPE_CHECKING:
    from uitk.widgets.tableWidget import TableWidget


class _CellFormats:
    """A :class:`TableWidget`'s cell formatting: the formatters registered per
    cell, column and header, each column's display truncation, and every
    cell's colours from before it was first formatted.

    Holds its table and reaches the table's public methods through it, so an
    override on the table (or a test's ``patch.object``) reaches every caller.
    The colour map, formatter store and colour resolution are the table's
    :class:`~uitk.widgets.mixins.item_format.ItemFormatMixin`, shared with the
    tree's ``TreeFormatMixin``.
    """

    def __init__(self, table: "TableWidget"):
        self._table = table
        self.col_formatters = {}
        self.header_formatters = {}
        self.cell_formatters = {}
        self.item_defaults = {}  # {(row, col): (fg, bg)}
        self.column_truncation = {}  # {col: (length, mode, insert, head)}
        table.cellChanged.connect(self.on_cell_edited)

    def set_column_formatter(self, col, formatter, append):
        table = self._table
        idx = table._resolve_col(col)
        if idx is None:
            return
        table._set_formatter(self.col_formatters, idx, formatter, append)

    def set_header_formatter(self, header, formatter, append):
        table = self._table
        idx = table._resolve_col(header)
        if idx is None:
            return
        # Key by the resolved, canonical header text so storage matches the
        # lookup in formatters (which keys by table._header(col)). Storing
        # under the raw `header` arg would miss when it is an int column index.
        key = table._header(idx)
        table._set_formatter(self.header_formatters, key, formatter, append)

    def set_cell_formatter(self, row, col, formatter, append):
        self._table._set_formatter(self.cell_formatters, (row, col), formatter, append)

    def clear_formatters(self):
        self.col_formatters.clear()
        self.header_formatters.clear()
        self.cell_formatters.clear()
        self.item_defaults.clear()

    def set_column_truncation(self, col, length, mode, insert, head):
        table = self._table
        idx = table._resolve_col(col)
        if idx is None:
            return
        if not length or int(length) <= 0:
            self.column_truncation.pop(idx, None)
        else:
            self.column_truncation[idx] = (int(length), mode, insert, head)
        table.viewport().update()

    def column_truncation_of(self, col):
        idx = self._table._resolve_col(col)
        return self.column_truncation.get(idx) if idx is not None else None

    def truncated_column_text(self, col: int, text: str) -> str:
        spec = self.column_truncation.get(col)
        if not spec or not text:
            return text
        length, mode, insert, head = spec
        return ptk.truncate(text, length, mode=mode, insert=insert, head=head)

    def apply_formatting(self):
        table = self._table
        # Block signals for the duration: format_item modifies item roles
        # (foreground/background), which fires cellChanged → on_cell_edited
        # → formatters → format_item → cellChanged → ... (infinite recursion
        # → stack overflow on tables with many formatted cells).
        with table._formatting_signals_blocked():
            for row in range(table.rowCount()):
                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    if not item:
                        continue
                    for fmt in self.formatters(row, col):
                        fmt(
                            item,
                            item.data(QtCore.Qt.UserRole) or item.text(),
                            row,
                            col,
                            table,
                        )

    def ensure_valid_color(self, color, color_type, item, row, col):
        return self._table._valid_color(
            color, color_type, lambda: self.default_colors(item, row, col)
        )

    def format_item(self, item, key, italic, bold, fg, bg):
        table = self._table
        # Font
        if italic is not None or bold is not None:
            font = item.font()
            if italic is not None:
                font.setItalic(italic)
            if bold is not None:
                font.setBold(bold)
            item.setFont(font)

        # Colors
        if key or fg is not None or bg is not None:
            # Resolve colors from key
            key_fg, key_bg = (None, None)
            if key:
                key_lower = str(key).lower()
                key_fg, key_bg = table.ACTION_COLOR_MAP.get(key_lower, (None, None))

                # Special handling for reset: clear roles to let stylesheet take over
                if key_lower == "reset" and fg is None and bg is None:
                    item.setData(QtCore.Qt.ForegroundRole, None)
                    item.setData(QtCore.Qt.BackgroundRole, None)
                    return

            # Explicit overrides key
            final_fg = fg if fg is not None else key_fg
            final_bg = bg if bg is not None else key_bg

            row, col = item.row(), item.column()

            # Ensure defaults are cached before applying any changes
            self.default_colors(item, row, col)

            # Foreground
            q_fg = table.ensure_valid_color(final_fg, "fg", item, row, col)
            if q_fg:
                item.setForeground(q_fg)

            # Background logic
            should_set_bg = False
            if bg is not None:
                should_set_bg = True
            elif key:
                key_lower = str(key).lower()
                if key_lower == "reset":
                    should_set_bg = True
                else:
                    # Check if key has a bg defined
                    _, map_bg = table.ACTION_COLOR_MAP.get(key_lower, (None, None))
                    if map_bg is not None:
                        should_set_bg = True

            if should_set_bg:
                q_bg = table.ensure_valid_color(final_bg, "bg", item, row, col)
                if q_bg:
                    item.setBackground(q_bg)

    def set_action_color(self, item, key, row, col, use_bg):
        table = self._table
        # Delegate to format_item for consistency, but maintain exact behavior
        # set_action_color has specific behavior for 'reset' (returns early if no colors)
        # and use_bg flag.

        key_lower = str(key).lower()
        fg_raw, bg_raw = table.ACTION_COLOR_MAP.get(key_lower, (None, None))

        # Skip entirely if reset and nothing to restore (legacy behavior)
        if key == "reset" and fg_raw is None and bg_raw is None:
            return

        # Use format_item logic but we need to respect use_bg
        # If use_bg is False, we pass bg=None and ensure key doesn't trigger bg set
        # But format_item logic for key triggers bg set if key has bg.
        # So we might need to manually call ensure_valid_color here to preserve exact legacy behavior
        # or update format_item to support use_bg.
        # For now, let's keep set_action_color as is to avoid regression,
        # but maybe update it to use ensure_valid_color which it already does.

        fg = table.ensure_valid_color(fg_raw, "fg", item, row, col)
        bg = table.ensure_valid_color(bg_raw, "bg", item, row, col) if use_bg else None

        if row >= 0 and col >= 0:
            default_fg, default_bg = self.default_colors(item, row, col)
            fg = fg or table.to_qobject(default_fg, "QColor")
            if use_bg:
                bg = bg or table.to_qobject(default_bg, "QColor")

        if fg:
            item.setForeground(fg)
        if use_bg and bg:
            item.setBackground(bg)

    def action_color_formatter(self, item, value):
        table = self._table
        key = str(value).lower()
        fg, bg = ItemFormatMixin.ACTION_COLOR_MAP.get(key, (None, None))
        fg = table.ensure_valid_color(fg, "fg", item, item.row(), item.column())
        bg = table.ensure_valid_color(bg, "bg", item, item.row(), item.column())
        item.setForeground(fg)
        item.setBackground(bg)

    def make_color_map_formatter(self, color_map: dict):
        table = self._table

        def _fmt(item, value, *_):
            key = str(value).lower()
            fg, bg = color_map.get(key, (None, None))
            fg = table.ensure_valid_color(fg, "fg", item, item.row(), item.column())
            bg = table.ensure_valid_color(bg, "bg", item, item.row(), item.column())
            item.setForeground(fg)
            item.setBackground(bg)

        return _fmt

    def on_cell_edited(self, row, col):
        table = self._table
        item = table.item(row, col)
        if item:
            for fmt in self.formatters(row, col):
                fmt(item, item.data(QtCore.Qt.UserRole) or item.text(), row, col, table)

    @staticmethod
    def default_colors(item, row: int, col: int):
        """Get the cached default colors for the item at the given row and col.

        The cache is the item's table's ``_item_defaults``: a
        :class:`TableWidget` serves its formats' ``item_defaults``, a plain
        ``QTableWidget`` grows the attribute.
        """
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

    def formatters(self, row, col) -> list:
        formatters = []
        key = (row, col)
        if key in self.cell_formatters:
            formatters.extend(self.cell_formatters[key])
        if col in self.col_formatters:
            formatters.extend(self.col_formatters[col])
        header = self._table._header(col)
        if header in self.header_formatters:
            formatters.extend(self.header_formatters[header])
        return formatters
