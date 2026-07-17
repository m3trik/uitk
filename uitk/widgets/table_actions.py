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

from typing import Any, Dict, Optional, TYPE_CHECKING

from qtpy import QtWidgets, QtGui, QtCore

from uitk.managers.icon_manager import IconManager
from uitk.widgets.delegates.centered_icon import (
    fill_cell_background,
    paint_centered_icon,
)

if TYPE_CHECKING:
    from uitk.widgets.tableWidget import TableWidget


class _CenteredIconDelegate(QtWidgets.QStyledItemDelegate):
    """Paints item-decoration icons centered in the cell.

    Action columns hold icon-only items.  Qt's default delegate
    positions the decoration via ``QStyle::SE_ItemViewItemDecoration``,
    which is style-dependent and not reliably influenced by
    ``Qt.TextAlignmentRole`` for empty-text items — the icon ends up
    left-aligned with style-dictated margins, and shrinks/clips
    inconsistently when the row height changes.

    This delegate lets the base draw the cell background (selection,
    focus, alternating colours), but suppresses the default icon /
    text paint and renders the icon manually at the cell's centre.
    """

    def paint(self, painter, option, index):
        # Fetch the icon directly from the model — relying on
        # ``opt.icon`` after clearing it leaves a dangling wrapper in
        # PySide and the icon comes back null.
        icon_data = index.data(QtCore.Qt.DecorationRole)
        if isinstance(icon_data, QtGui.QIcon):
            icon = icon_data
        elif icon_data is None:
            icon = QtGui.QIcon()
        else:
            icon = QtGui.QIcon(icon_data)

        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # Action cells visually opt out of the row-selection highlight.
        # In SelectRows mode Qt sets State_Selected on every column of
        # a selected row, which paints over the icon's own background
        # and makes non-selectable action cells look interactive.
        opt.state &= ~QtWidgets.QStyle.State_Selected

        # Paint a per-state ``background`` tint ourselves — the stylesheet
        # style's CE_ItemViewItem drops the item brush for the QSS ``::item``
        # rules; cleared from ``opt`` so drawControl doesn't double-fill.
        fill_cell_background(painter, option.rect, index)
        opt.backgroundBrush = QtGui.QBrush()

        # Clear icon/text and the corresponding feature flags so the
        # style only paints the cell background + selection state.
        # ``super().paint()`` would re-run ``initStyleOption`` on its
        # own copy and undo this — call ``style.drawControl`` directly.
        opt.icon = QtGui.QIcon()
        opt.text = ""
        opt.features &= ~QtWidgets.QStyleOptionViewItem.HasDecoration
        opt.features &= ~QtWidgets.QStyleOptionViewItem.HasDisplay

        widget = option.widget
        style = widget.style() if widget else QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, opt, painter, widget)

        # Centered-icon painting is shared with CenteredIconActionDelegate.
        paint_centered_icon(
            painter,
            icon,
            option.rect,
            option.decorationSize,
            hover=bool(option.state & QtWidgets.QStyle.State_MouseOver),
        )


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
        # Shared delegate that paints icons centered in their cells —
        # one instance covers every action column on this table.
        self._icon_delegate: Optional[_CenteredIconDelegate] = None

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
        self._install_icon_delegate(column)

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
            self._table.setItem(row, col, item)

        # Always ensure action items are non-editable and non-selectable
        item.setFlags(
            item.flags() & ~QtCore.Qt.ItemIsEditable & ~QtCore.Qt.ItemIsSelectable
        )

        # Center the icon in the cell.  Qt positions the decoration via
        # the item's TextAlignmentRole even when text is empty; without
        # this the icon hugs the left edge and visibly clips when the
        # cell is small (e.g. compact-mode rows).
        item.setTextAlignment(QtCore.Qt.AlignCenter)

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

    def _install_icon_delegate(self, column: int) -> None:
        """Set the centered-icon delegate on *column*.

        Idempotent — uses a single shared delegate per ``TableActions``
        instance so adding/refreshing many action columns doesn't
        accumulate delegate objects.  Re-calling this on the same
        column is a no-op for Qt because ``setItemDelegateForColumn``
        replaces the previous delegate with the same instance.
        """
        if self._icon_delegate is None:
            self._icon_delegate = _CenteredIconDelegate(self._table)
        self._table.setItemDelegateForColumn(column, self._icon_delegate)

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
            self._install_icon_delegate(col)

    def update_for_row_height(self) -> None:
        """Re-size action columns and icons to fit the current row height.

        Action columns are square (width = row height) and icons fit
        within that — but column width is set once at registration and
        icons default to ``(14, 14)``.  When the table's row height
        changes (e.g. a compact-mode toggle), icons can clip at the row
        boundary because Qt's style margins consume a fixed number of
        pixels regardless of cell size.

        Call this after changing ``defaultSectionSize`` so action
        columns track the new height and icons re-render at the right
        size.  Idempotent.
        """
        row_h = self._table.verticalHeader().defaultSectionSize()
        # Leave 4 px of padding so the icon never butts the row edge —
        # Qt's style draws ~2 px of focus/decoration margin around items.
        icon_dim = IconManager.fit_size(row_h, margin=4)
        icon_size = (icon_dim, icon_dim)

        # The view-wide ``iconSize`` controls the decoration rect Qt
        # asks the painter to fill.  Without setting it explicitly Qt
        # falls back to the style hint (typically ~16×16), which
        # overflows compact rows even after we've sized the QIcon
        # itself to fit.
        self._table.setIconSize(QtCore.QSize(icon_dim, icon_dim))

        for col, cfg in self._columns.items():
            # Update the stored icon_size for future ``set()`` calls so
            # rows added later get the right size automatically.
            for state_cfg in cfg["states"].values():
                state_cfg["icon_size"] = icon_size
            if cfg.get("square"):
                self._apply_sizing(col)
            icon_name = cfg.get("header_icon")
            if icon_name:
                self._set_header_icon(col, icon_name)
            self._install_icon_delegate(col)

        # Re-apply existing cells with the new icon size.  ``set`` reads
        # ``icon_size`` from the state config (just updated above).
        for (row, col), state_name in list(self._cell_states.items()):
            if col in self._columns and row < self._table.rowCount():
                self.set(row, col, state_name)
