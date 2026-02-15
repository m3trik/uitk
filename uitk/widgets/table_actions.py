# !/usr/bin/python
# coding=utf-8
"""Reusable action-column management for :class:`TableWidget`.

An *action column* is a narrow, fixed-width, non-selectable column whose
cells display state-dependent icons.  Clicking a cell triggers the
callback associated with its current state.

Usage::

    # One-time setup (typically in ``tbl000_init``)
    table.actions.add(
        column=1,
        states={
            "locked": {
                "icon": "lock",
                "color": "#e8c44a",
                "tooltip": "Locked — click to unlock",
                "action": toggle_lock,
                "background": "#2a2518",
            },
            "unlocked": {
                "icon": "unlock",
                "color": "#555555",
                "tooltip": "Unlocked — click to lock",
                "action": toggle_lock,
            },
        },
        header_icon="lock",
    )

    # Per-row state (after populating table data)
    table.actions.set(row, 1, "locked")

    # Query state
    table.actions.get(row, 1)  # -> "locked"
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from qtpy import QtWidgets, QtGui, QtCore

from uitk.widgets.mixins.icon_manager import IconManager

if TYPE_CHECKING:
    from uitk.widgets.tableWidget import TableWidget


class TableActions:
    """Manages action columns on a :class:`TableWidget`.

    Parameters
    ----------
    table : TableWidget
        The owning table widget.
    """

    def __init__(self, table: "TableWidget") -> None:
        self._table = table
        # col -> {"states": {name: {icon, color, action, tooltip}},
        #         "header_icon": str|None, "square": bool}
        self._columns: Dict[int, dict] = {}
        # (row, col) -> state name
        self._cell_states: Dict[tuple, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(
        self,
        column: int,
        states: Dict[str, Dict[str, Any]],
        header_icon: str | None = None,
        square: bool = True,
    ) -> None:
        """Register an action column.

        Parameters
        ----------
        column : int
            Column index.
        states : dict
            Mapping of state names to configuration dicts.  Each config may
            contain:

            - **icon** (*str*) — SVG icon name (required).
            - **color** (*str | None*) — Hex colour for the icon;  ``None``
              uses the current theme colour.
            - **tooltip** (*str*) — Tooltip text.
            - **action** (*callable(row, col)*) — Called on click.
            - **icon_size** (*tuple[int, int]*) — Override icon size
              (default ``(14, 14)``).
            - **background** (*str | None*) — Hex colour for the cell
              background.
            - **foreground** (*str | None*) — Hex colour for the cell
              foreground / text.
        header_icon : str, optional
            Icon name displayed in the column header.
        square : bool
            If ``True`` the column is fixed-width, matching row height.
        """
        self._columns[column] = {
            "states": states,
            "header_icon": header_icon,
            "square": square,
        }
        self._table.set_column_selectable(column, False)
        self._table.set_column_click_action(column, self._on_click)
        if header_icon is not None:
            self._set_header_icon(column, header_icon)
        if square:
            self._apply_sizing(column)

    def set(self, row: int, col: int, state_name: str) -> None:
        """Set a cell to a named state, updating its icon, tooltip, and style.

        If the cell has no ``QTableWidgetItem`` yet, a blank one is created
        automatically (action columns are self-contained).

        Parameters
        ----------
        row, col : int
            Cell coordinates.
        state_name : str
            Must match a key in the *states* dict passed to :meth:`add`.
        """
        cfg = self._columns.get(col)
        if cfg is None:
            return
        state = cfg["states"].get(state_name)
        if state is None:
            return

        self._cell_states[(row, col)] = state_name

        item = self._table.item(row, col)
        if item is None:
            item = QtWidgets.QTableWidgetItem()
            item.setFlags(
                item.flags() & ~QtCore.Qt.ItemIsEditable & ~QtCore.Qt.ItemIsSelectable
            )
            self._table.setItem(row, col, item)

        # Icon
        color = state.get("color")
        icon_size = state.get("icon_size", (14, 14))
        icon = IconManager.get(
            state["icon"],
            size=icon_size,
            color=color,
            use_theme=color is None,
        )
        item.setIcon(icon)

        # Tooltip
        tooltip = state.get("tooltip")
        if tooltip is not None:
            item.setToolTip(tooltip)

        # Style — background
        bg = state.get("background")
        if bg is not None:
            item.setBackground(QtGui.QColor(bg))

        # Style — foreground
        fg = state.get("foreground")
        if fg is not None:
            item.setForeground(QtGui.QColor(fg))

    def get(self, row: int, col: int) -> Optional[str]:
        """Return the current state name for a cell, or ``None``."""
        return self._cell_states.get((row, col))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _on_click(self, row: int, col: int) -> None:
        """Dispatch a cell click to the current state's action callback."""
        state_name = self._cell_states.get((row, col))
        cfg = self._columns.get(col)
        if not cfg or not state_name:
            return
        state = cfg["states"].get(state_name)
        if state and state.get("action"):
            state["action"](row, col)

    def _set_header_icon(self, column: int, icon_name: str) -> None:
        header_item = self._table.horizontalHeaderItem(column)
        if header_item is None:
            header_item = QtWidgets.QTableWidgetItem()
            self._table.setHorizontalHeaderItem(column, header_item)
        icon = IconManager.get(icon_name, size=(14, 14))
        header_item.setIcon(icon)
        header_item.setText("")

    def _apply_sizing(self, column: int) -> None:
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(column, QtWidgets.QHeaderView.Fixed)
        row_h = self._table.verticalHeader().defaultSectionSize()
        header.setMinimumSectionSize(min(header.minimumSectionSize(), row_h))
        self._table.setColumnWidth(column, row_h)

    def _reapply(self) -> None:
        """Re-apply sizing and header icons after a table rebuild.

        Called automatically by ``TableWidget.add()`` since
        ``setColumnCount(0)`` destroys header state.  Also clears stale
        per-cell state references.
        """
        self._cell_states.clear()
        for col, cfg in self._columns.items():
            if col >= self._table.columnCount():
                continue
            if cfg.get("square"):
                self._apply_sizing(col)
            icon_name = cfg.get("header_icon")
            if icon_name:
                self._set_header_icon(col, icon_name)
