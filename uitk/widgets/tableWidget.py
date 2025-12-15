# !/usr/bin/python
# coding=utf-8
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from qtpy import QtWidgets, QtGui, QtCore

# From this package:
from uitk.widgets.mixins.convert import ConvertMixin
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.menu_mixin import MenuMixin


class HeaderMixin:
    def _init_header_behavior(self):
        self.horizontalHeader().setSectionsClickable(True)
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        self.horizontalHeader().setDefaultAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
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
        "current": ("#6A8CA8", None),
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

    def format_item(
        self,
        item: QtWidgets.QTableWidgetItem,
        key: str = None,
        italic: bool = None,
        bold: bool = None,
        fg: Any = None,
        bg: Any = None,
    ):
        """
        Apply formatting to a table item.

        Args:
            item: The item to format.
            key: Semantic color key from ACTION_COLOR_MAP.
            italic: True/False to set italic, None to ignore.
            bold: True/False to set bold, None to ignore.
            fg: Explicit foreground color. Overrides key.
            bg: Explicit background color. Overrides key.
        """
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
                key_fg, key_bg = self.ACTION_COLOR_MAP.get(key_lower, (None, None))

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
            self._get_default_colors(item, row, col)

            # Foreground
            q_fg = self.ensure_valid_color(final_fg, "fg", item, row, col)
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
                    _, map_bg = self.ACTION_COLOR_MAP.get(key_lower, (None, None))
                    if map_bg is not None:
                        should_set_bg = True

            if should_set_bg:
                q_bg = self.ensure_valid_color(final_bg, "bg", item, row, col)
                if q_bg:
                    item.setBackground(q_bg)

    def set_action_color(
        self,
        item: QtWidgets.QTableWidgetItem,
        key: str,
        row: int = -1,
        col: int = -1,
        use_bg: bool = False,
    ):
        """Apply semantic color, but skip reset if nothing defined."""
        # Delegate to format_item for consistency, but maintain exact behavior
        # set_action_color has specific behavior for 'reset' (returns early if no colors)
        # and use_bg flag.

        key_lower = str(key).lower()
        fg_raw, bg_raw = self.ACTION_COLOR_MAP.get(key_lower, (None, None))

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


@dataclass(frozen=True)
class TableSelection:
    """Immutable representation of a single selected row."""

    row: int
    values: Dict[str, Any]
    items: Dict[str, Optional[QtWidgets.QTableWidgetItem]]

    def __getitem__(self, key: str):
        return self.values[key]

    def get(self, key: str, default: Any = None):
        return self.values.get(key, default)

    def item(self, key: str) -> Optional[QtWidgets.QTableWidgetItem]:
        return self.items.get(key)

    def text(self, key: str, default: str = "") -> str:
        widget_item = self.items.get(key)
        return widget_item.text() if widget_item is not None else default


class TableWidget(
    QtWidgets.QTableWidget, MenuMixin, HeaderMixin, AttributesMixin, CellFormatMixin
):
    """Enhanced QTableWidget with cell formatting, sorting, and context menu support."""

    def __init__(
        self,
        parent=None,
        selection_mode="extended",
        left_click_select_only=False,
        **kwargs,
    ):
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

        self._left_click_select_only = bool(left_click_select_only)
        self._non_selectable_columns = set()
        self._selection_validator = None
        self._column_click_actions = {}
        self._menu_action_registry: Dict[str, Dict[str, Any]] = {}
        self._menu_dispatch_connected = False
        self._stretch_column = None

        self.cellClicked.connect(self._on_cell_clicked)

        self.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked)
        self.verticalHeader().setVisible(False)
        compact_row_height = max(self.fontMetrics().height() + 4, 18)
        self.verticalHeader().setDefaultSectionSize(compact_row_height)
        self.setAlternatingRowColors(False)
        self.setWordWrap(False)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Customize standalone menu provided by MenuMixin
        self.menu.trigger_button = "right"
        self.menu.fixed_item_height = 20
        self.menu.hide_on_leave = True

        # Set selection mode
        self._set_selection_mode(selection_mode)

        self.set_attributes(**kwargs)

    def selectionCommand(self, index, event=None):
        """Optionally restrict selection changes."""
        if index.isValid():
            # Check column blacklist
            if index.column() in self._non_selectable_columns:
                return QtCore.QItemSelectionModel.NoUpdate

            # Check custom validator
            if self._selection_validator and not self._selection_validator(index):
                return QtCore.QItemSelectionModel.NoUpdate

        if (
            self._left_click_select_only
            and event
            and isinstance(event, QtGui.QMouseEvent)
        ):
            if event.button() != QtCore.Qt.LeftButton:
                return QtCore.QItemSelectionModel.NoUpdate
        return super().selectionCommand(index, event)

    def set_column_selectable(self, column: int, selectable: bool):
        """Set whether a specific column can trigger selection changes."""
        if selectable:
            self._non_selectable_columns.discard(column)
        else:
            self._non_selectable_columns.add(column)

    def set_selection_validator(self, validator: Callable[[QtCore.QModelIndex], bool]):
        """Set a function to validate if an index can be selected.

        Args:
            validator: A function that takes a QModelIndex and returns bool.
        """
        self._selection_validator = validator

    def set_column_click_action(self, column: int, action: Callable[[int, int], None]):
        """Set a callback for when a cell in a specific column is clicked.

        Args:
            column: The column index.
            action: Function receiving (row, col).
        """
        self._column_click_actions[column] = action

    def _on_cell_clicked(self, row, col):
        """Handle cell clicks and dispatch to registered actions."""
        if col in self._column_click_actions:
            self._column_click_actions[col](row, col)

    def set_left_click_select_only(self, enabled: bool):
        """Toggle whether non-left clicks can change selection."""
        self._left_click_select_only = bool(enabled)

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

                    text_str = str(text) if text is not None else ""
                    item = QtWidgets.QTableWidgetItem(text_str)

                    # Set tooltip to text content by default
                    if text_str:
                        item.setToolTip(text_str)

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

    def selected_rows(self, include_current=False):
        """Get all selected row numbers"""
        selected_items = self.selectedItems()
        rows = {item.row() for item in selected_items}
        if not rows and include_current:
            curr = self.currentRow()
            if curr >= 0:
                rows.add(curr)
        return sorted(rows)

    def clear_all(self):
        self.setRowCount(0)

    def set_stretch_column(self, col: int):
        """Set a column to automatically stretch to fill the available space."""
        self._stretch_column = col
        self.stretch_column_to_fill(col)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._stretch_column is not None:
            self.stretch_column_to_fill(self._stretch_column)

    def stretch_column_to_fill(self, stretch_col: int):
        if stretch_col < 0 or stretch_col >= self.columnCount():
            return

        header = self.horizontalHeader()
        header.setStretchLastSection(False)

        for col in range(self.columnCount()):
            header.setSectionResizeMode(col, QtWidgets.QHeaderView.Interactive)

        # Simulate stretch by setting width manually to allow user resizing
        total_width = self.viewport().width()
        if total_width <= 0:
            return

        other_cols_width = 0
        for col in range(self.columnCount()):
            if col != stretch_col:
                other_cols_width += self.columnWidth(col)

        new_width = max(50, total_width - other_cols_width)
        self.setColumnWidth(stretch_col, new_width)

    def get_selected_data(self, columns=None, include_current=True):
        """
        Get data from selected rows for specified columns.

        Args:
            columns (list[int], optional): List of column indices to retrieve data from.
                                           If None, returns data from all columns.
            include_current (bool): If True, falls back to current row if no selection.

        Returns:
            list[dict]: A list of dictionaries, one for each selected row.
                        Each dictionary maps column index to the item's data.
        """
        normalized = self._normalize_column_targets(columns)
        selections = self._build_selection_payload(normalized, include_current)

        result = []
        for selection in selections:
            row_data = {}
            for key, col_idx in normalized:
                row_data[col_idx] = selection.values.get(key)
            result.append(row_data)

        return result

    # ------------------------------------------------------------------
    # Selection helpers & menu integrations
    # ------------------------------------------------------------------
    def get_selection(
        self,
        columns: Optional[
            Union[Sequence[Union[int, str]], Dict[str, Union[int, str]]]
        ] = None,
        include_current: bool = True,
    ) -> List[TableSelection]:
        """Return detailed selection payload keyed by column aliases."""

        normalized = self._normalize_column_targets(columns)
        return self._build_selection_payload(normalized, include_current)

    def register_menu_action(
        self,
        object_name: str,
        handler: Callable[[List[TableSelection]], None],
        *,
        columns: Optional[
            Union[Sequence[Union[int, str]], Dict[str, Union[int, str]]]
        ] = None,
        include_current: bool = True,
        allow_empty: bool = False,
        transform: Optional[Callable[[List[TableSelection]], Any]] = None,
        pass_widget: bool = False,
    ):
        """Attach a context-menu item to a callable that receives selection data."""

        if not object_name:
            raise ValueError("object_name is required")
        if not callable(handler):
            raise TypeError("handler must be callable")

        normalized = self._normalize_column_targets(columns)
        self._menu_action_registry[object_name] = {
            "handler": handler,
            "columns": normalized,
            "include_current": bool(include_current),
            "allow_empty": bool(allow_empty),
            "transform": transform,
            "pass_widget": bool(pass_widget),
        }
        self._ensure_menu_dispatch_hook()

    def unregister_menu_action(self, object_name: str):
        self._menu_action_registry.pop(object_name, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_menu_dispatch_hook(self):
        if self._menu_dispatch_connected:
            return
        menu = getattr(self, "menu", None)
        signal = getattr(menu, "on_item_interacted", None)
        if signal is None:
            return
        signal.connect(self._dispatch_registered_menu_action)
        self._menu_dispatch_connected = True

    def _dispatch_registered_menu_action(self, widget: QtWidgets.QWidget):
        if widget is None:
            return
        object_name = widget.objectName()
        if not object_name:
            return
        payload = self._menu_action_registry.get(object_name)
        if not payload:
            return

        selections = self._build_selection_payload(
            payload["columns"], payload["include_current"]
        )
        if not selections and not payload["allow_empty"]:
            return

        data = selections
        transform = payload.get("transform")
        if transform:
            data = transform(selections)

        handler = payload["handler"]

        def _call_handler_with_compatible_arity(func, argv):
            """Call handler with as many args as it can accept.

            Supports legacy handlers that take no args (besides bound self),
            and newer handlers that accept (data) or (data, widget).
            """

            try:
                sig = inspect.signature(func)
            except (TypeError, ValueError):
                return func(*argv)

            params = list(sig.parameters.values())

            # If this is an unbound method/function, ignore explicit 'self'
            if params and params[0].name == "self":
                params = params[1:]

            has_var_positional = any(
                p.kind == inspect.Parameter.VAR_POSITIONAL for p in params
            )
            if has_var_positional:
                return func(*argv)

            positional = [
                p
                for p in params
                if p.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
            max_positional = len(positional)

            # Try to pass as much as possible, but degrade gracefully.
            if len(argv) >= 2:
                if max_positional >= 2:
                    return func(argv[0], argv[1])
                if max_positional >= 1:
                    return func(argv[0])
                return func()

            if len(argv) == 1:
                if max_positional >= 1:
                    return func(argv[0])
                return func()

            return func()

        if payload["pass_widget"]:
            _call_handler_with_compatible_arity(handler, (data, widget))
        else:
            _call_handler_with_compatible_arity(handler, (data,))

    def _normalize_column_targets(
        self,
        columns: Optional[Union[Sequence[Union[int, str]], Dict[str, Union[int, str]]]],
    ) -> List[Tuple[str, int]]:
        targets: List[Tuple[str, int]] = []
        used_keys = set()

        def _make_key(idx: int, label: Optional[str] = None) -> str:
            base = (label or "").strip() or f"column_{idx}"
            key = base
            suffix = 2
            while key in used_keys:
                key = f"{base}_{suffix}"
                suffix += 1
            used_keys.add(key)
            return key

        if columns is None:
            for idx in range(self.columnCount()):
                header = self.horizontalHeaderItem(idx)
                label = header.text() if header else None
                targets.append((_make_key(idx, label), idx))
            return targets

        iterable: Iterable[Tuple[Optional[str], Union[int, str]]]
        if isinstance(columns, dict):
            iterable = columns.items()
        else:
            iterable = ((None, col) for col in columns)

        for alias, ref in iterable:
            idx = self._resolve_col(ref)
            if idx is None:
                continue
            header = self.horizontalHeaderItem(idx)
            label = alias or (header.text() if header else None)
            targets.append((_make_key(idx, label), idx))

        return targets

    def _build_selection_payload(
        self,
        normalized_columns: List[Tuple[str, int]],
        include_current: bool,
    ) -> List[TableSelection]:
        rows = self.selected_rows(include_current=include_current)
        selections: List[TableSelection] = []

        for row in rows:
            values: Dict[str, Any] = {}
            items: Dict[str, Optional[QtWidgets.QTableWidgetItem]] = {}
            for key, col_idx in normalized_columns:
                items[key] = self.item(row, col_idx)
                values[key] = self.item_data(row, col_idx)
            selections.append(TableSelection(row=row, values=values, items=items))
        return selections


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
