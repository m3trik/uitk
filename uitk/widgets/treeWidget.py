# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtGui, QtCore
from typing import Optional, Callable, List, Union, Any, Dict

# From this package:
from uitk.widgets.mixins.convert import ConvertMixin
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.signals import Signals


class TreeFormatMixin(ConvertMixin):
    """Generic item/column formatting for QTreeWidget."""

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
        self._item_formatters = {}
        self._column_formatters = {}
        self._item_defaults = {}  # {item_id: (fg, bg)}
        self.itemChanged.connect(self._on_item_edited)

    # Public API
    def set_item_formatter(self, item_id, formatter, append=False):
        """Set a formatter for a specific item by ID."""
        if append:
            self._item_formatters.setdefault(item_id, []).append(formatter)
        else:
            self._item_formatters[item_id] = [formatter]

    def set_column_formatter(self, col, formatter, append=False):
        """Set a formatter for a specific column."""
        if append:
            self._column_formatters.setdefault(col, []).append(formatter)
        else:
            self._column_formatters[col] = [formatter]

    def clear_formatters(self):
        """Clear all item and column formatters."""
        self._item_formatters.clear()
        self._column_formatters.clear()
        self._item_defaults.clear()

    def apply_formatting(self):
        """Apply formatting based on the registered formatters."""
        iterator = QtWidgets.QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            for col in range(self.columnCount()):
                for fmt in self._get_formatters(item, col):
                    fmt(
                        item,
                        item.data(col, QtCore.Qt.UserRole) or item.text(col),
                        col,
                        self,
                    )
            iterator += 1

    def ensure_valid_color(self, color, color_type, item, col):
        """Ensure a valid QColor, using fallback if needed."""
        try:
            return self.to_qobject(color, "QColor")
        except Exception:
            pass

        cached = self._get_default_colors(item, col)[0 if color_type == "fg" else 1]
        try:
            return self.to_qobject(cached, "QColor")
        except Exception:
            print(
                f"[WARNING] Invalid {color_type} color: {color!r}, and fallback {cached!r} failed. Using None."
            )
            return None

    def set_action_color(
        self,
        item: QtWidgets.QTreeWidgetItem,
        key: str,
        col: int = 0,
        use_bg: bool = False,
    ):
        """Apply semantic color to a tree item."""
        fg_raw, bg_raw = self.ACTION_COLOR_MAP.get(str(key).lower(), (None, None))

        # Skip entirely if reset and nothing to restore
        if key == "reset" and fg_raw is None and bg_raw is None:
            return

        fg = self.ensure_valid_color(fg_raw, "fg", item, col)
        bg = self.ensure_valid_color(bg_raw, "bg", item, col) if use_bg else None

        default_fg, default_bg = self._get_default_colors(item, col)
        fg = fg or self.to_qobject(default_fg, "QColor")
        if use_bg:
            bg = bg or self.to_qobject(default_bg, "QColor")

        if fg:
            item.setForeground(col, fg)
        if use_bg and bg:
            item.setBackground(col, bg)

    def action_color_formatter(self, item, value, col, *_):
        """Formatter that applies action colors based on item value."""
        key = str(value).lower()
        fg, bg = TreeFormatMixin.ACTION_COLOR_MAP.get(key, (None, None))
        fg = self.ensure_valid_color(fg, "fg", item, col)
        bg = self.ensure_valid_color(bg, "bg", item, col)
        if fg:
            item.setForeground(col, fg)
        if bg:
            item.setBackground(col, bg)

    def make_color_map_formatter(self, color_map: dict):
        """Create a formatter from a color mapping dictionary."""

        def _fmt(item, value, col, *_):
            key = str(value).lower()
            fg, bg = color_map.get(key, (None, None))
            fg = self.ensure_valid_color(fg, "fg", item, col)
            bg = self.ensure_valid_color(bg, "bg", item, col)
            if fg:
                item.setForeground(col, fg)
            if bg:
                item.setBackground(col, bg)

        return _fmt

    # Private methods
    def _on_item_edited(self, item, col):
        """Handle item editing to reapply formatting."""
        for fmt in self._get_formatters(item, col):
            fmt(item, item.data(col, QtCore.Qt.UserRole) or item.text(col), col, self)

    def _get_default_colors(self, item, col: int):
        """Get the cached default colors for the item at the given column."""
        item_id = id(item)
        if not hasattr(self, "_item_defaults"):
            self._item_defaults = {}
        key = (item_id, col)
        cache = self._item_defaults
        if key not in cache:
            fg = item.foreground(col).color().name()
            bg = item.background(col).color().name()
            cache[key] = (fg, bg)
        return cache[key]

    def _get_formatters(self, item, col) -> list:
        """Get all formatters that apply to the given item and column."""
        formatters = []
        item_id = id(item)

        # Item-specific formatters
        if item_id in self._item_formatters:
            formatters.extend(self._item_formatters[item_id])

        # Column formatters
        if col in self._column_formatters:
            formatters.extend(self._column_formatters[col])

        return formatters


class TreeWidget(QtWidgets.QTreeWidget, AttributesMixin, TreeFormatMixin):
    """Enhanced QTreeWidget with flexible data handling and formatting capabilities."""

    # Signals
    item_selected = QtCore.Signal(QtWidgets.QTreeWidgetItem)
    item_data_changed = QtCore.Signal(QtWidgets.QTreeWidgetItem, int)

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        TreeFormatMixin.__init__(self)

        # Default settings
        self.setProperty("class", self.__class__.__name__)
        self.setAlternatingRowColors(False)
        self.setRootIsDecorated(True)
        self.setIndentation(20)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

        # Connect signals
        self.itemSelectionChanged.connect(self._on_selection_changed)

        self.set_attributes(**kwargs)

    @property
    def menu(self):
        """Get or create the context menu."""
        try:
            return self._menu
        except AttributeError:
            from uitk.widgets.menu import Menu

            self._menu = Menu(self, mode="option", fixed_item_height=20)
            return self._menu

    def _on_selection_changed(self):
        """Handle selection changes."""
        current = self.currentItem()
        if current:
            self.item_selected.emit(current)

    def create_item(
        self,
        text: Union[str, List[str]],
        data: Any = None,
        parent: QtWidgets.QTreeWidgetItem = None,
    ) -> QtWidgets.QTreeWidgetItem:
        """Create a new tree widget item."""
        if isinstance(text, str):
            text = [text]

        item = QtWidgets.QTreeWidgetItem(parent or self, text)

        if data is not None:
            item.setData(0, QtCore.Qt.UserRole, data)

        # Make item editable if needed
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)

        return item

    def item_data(self, item: QtWidgets.QTreeWidgetItem, column: int = 0):
        """Get data from an item."""
        if item is None:
            return None
        data = item.data(column, QtCore.Qt.UserRole)
        return data if data is not None else item.text(column)

    def set_item_data(
        self, item: QtWidgets.QTreeWidgetItem, data: Any, column: int = 0
    ):
        """Set data for an item."""
        if item:
            item.setData(column, QtCore.Qt.UserRole, data)

    def find_item_by_text(
        self, text: str, column: int = 0
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        """Find an item by its text in the specified column."""
        items = self.findItems(
            text, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, column
        )
        return items[0] if items else None

    def find_item_by_data(
        self, data: Any, column: int = 0
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        """Find an item by its user data."""
        iterator = QtWidgets.QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            if item.data(column, QtCore.Qt.UserRole) == data:
                return item
            iterator += 1
        return None

    @Signals.blockSignals
    def add(
        self,
        data: Union[Dict, List, str, Any],
        headers: Optional[List[str]] = None,
        clear: bool = True,
        parent: Optional[QtWidgets.QTreeWidgetItem] = None,
        **kwargs,
    ):
        """Add data to the tree widget with flexible input handling.

        Args:
            data: The data to add. Can be:
                - Dict: Keys become parent items, values become children
                - List of dicts: Each dict becomes a top-level item with key-value children
                - List of strings: Each string becomes a top-level item
                - List of tuples: (text, data) pairs
                - Nested structures: Recursively handled
            headers: Column headers for the tree
            clear: Whether to clear existing items
            parent: Parent item to add under (None for root)
            **kwargs: Additional attributes to set
        """
        self.setUpdatesEnabled(False)
        try:
            if clear and parent is None:
                self.clear()

            # Set headers if provided
            if headers:
                self.setHeaderLabels([str(h) for h in headers])
            elif not self.headerItem() or not self.headerItem().text(0):
                # Set default header if none exists
                self.setHeaderLabels(["Name"])

            self.blockSignals(True)
            self._add_recursive(data, parent)
            self.blockSignals(False)

        finally:
            self.setUpdatesEnabled(True)

        self.set_attributes(**kwargs)
        self.apply_formatting()

    def _add_recursive(
        self, data: Any, parent: Optional[QtWidgets.QTreeWidgetItem] = None
    ):
        """Recursively add data to the tree."""
        if isinstance(data, dict):
            for key, value in data.items():
                item = self.create_item(str(key), key, parent)
                if isinstance(value, (dict, list)):
                    self._add_recursive(value, item)
                else:
                    child_item = self.create_item(str(value), value, item)

        elif isinstance(data, (list, tuple)):
            for item_data in data:
                if isinstance(item_data, dict):
                    # Dict becomes parent with key-value children
                    for key, value in item_data.items():
                        parent_item = self.create_item(str(key), key, parent)
                        if isinstance(value, (dict, list)):
                            self._add_recursive(value, parent_item)
                        else:
                            self.create_item(str(value), value, parent_item)

                elif isinstance(item_data, (tuple, list)) and len(item_data) >= 2:
                    # Tuple/list: (text, data, [children])
                    text, user_data = item_data[0], item_data[1]
                    item = self.create_item(str(text), user_data, parent)

                    # Handle children if present
                    if len(item_data) > 2 and item_data[2]:
                        self._add_recursive(item_data[2], item)

                elif isinstance(item_data, (dict, list)):
                    # Nested structure
                    self._add_recursive(item_data, parent)
                else:
                    # Simple value
                    self.create_item(str(item_data), item_data, parent)
        else:
            # Single value
            self.create_item(str(data), data, parent)

    def selected_item(self) -> Optional[QtWidgets.QTreeWidgetItem]:
        """Get the currently selected item."""
        return self.currentItem()

    def selected_data(self, column: int = 0) -> Any:
        """Get data from the currently selected item."""
        item = self.selected_item()
        return self.item_data(item, column) if item else None

    def selected_text(self, column: int = 0) -> Optional[str]:
        """Get text from the currently selected item."""
        item = self.selected_item()
        return item.text(column) if item else None

    def expand_all_items(self):
        """Expand all items in the tree."""
        self.expandAll()

    def collapse_all_items(self):
        """Collapse all items in the tree."""
        self.collapseAll()

    def get_all_items(self) -> List[QtWidgets.QTreeWidgetItem]:
        """Get all items in the tree."""
        items = []
        iterator = QtWidgets.QTreeWidgetItemIterator(self)
        while iterator.value():
            items.append(iterator.value())
            iterator += 1
        return items

    def remove_item(self, item: QtWidgets.QTreeWidgetItem):
        """Remove an item from the tree."""
        if item:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                index = self.indexOfTopLevelItem(item)
                if index >= 0:
                    self.takeTopLevelItem(index)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    tree = TreeWidget()

    # Test with different data structures
    test_data = {
        "Root 1": {"Child 1": "Value 1", "Child 2": ["Item A", "Item B", "Item C"]},
        "Root 2": [
            ("Node A", "data_a"),
            ("Node B", "data_b", {"Sub1": "SubValue1", "Sub2": "SubValue2"}),
        ],
    }

    tree.add(test_data, headers=["Items", "Data"])
    tree.expand_all_items()

    # Set up some formatting
    tree.set_column_formatter(0, tree.action_color_formatter)

    tree.show()
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
