# !/usr/bin/python
# coding=utf-8
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from qtpy import QtWidgets, QtGui, QtCore

# From this package:
from uitk.widgets.mixins.item_format import ItemFormatMixin
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.menu_mixin import MenuMixin
from uitk.widgets.column_config import ColumnConfig
from uitk.widgets.row_tags import RowTags
from uitk.widgets.table_actions import TableActions
from uitk.widgets.overflow_indicator import OverflowIndicator
from uitk.widgets.table_widget_parts._cell_formats import _CellFormats
from uitk.widgets.table_widget_parts._context_menu import _ContextMenu
from uitk.widgets.table_widget_parts._gestures import (
    _CellClicks,
    _RowDrag,
    _ScrubInput,
)


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


class _SortKeyItem(QtWidgets.QTableWidgetItem):
    """A cell that sorts by a key, not by its text (``TableWidget.set_sorted_cell``).

    A cell with no key sorts before every keyed one; two without fall back to
    the text.
    """

    KEY_ROLE = QtCore.Qt.UserRole + 64

    def __lt__(self, other):
        mine, theirs = self.data(self.KEY_ROLE), other.data(self.KEY_ROLE)
        if mine is None or theirs is None:
            if mine is None and theirs is None:
                return super().__lt__(other)
            return mine is None
        try:
            return mine < theirs
        except TypeError:
            return super().__lt__(other)


@dataclass
class _EditAsRequest:
    """One :meth:`TableWidget.edit_cell_as` request."""

    cell: Tuple[int, int]
    text: str
    on_commit: Callable[[str], Any]
    select: Tuple[int, int]


class _ZeroSpacingEditorDelegate(QtWidgets.QStyledItemDelegate):
    """Strip frame and internal padding from text editors so entering
    edit mode doesn't visually shift the cell's text.

    The default ``QStyledItemDelegate`` opens a ``QLineEdit`` with a
    frame, style-dependent text margins, and stylesheet padding — the
    sum visibly offsets the text from where the cell display rendered
    it.  Zeroing all three keeps the editor flush with the cell's
    text rect.

    Does not suppress ``State_Selected`` — the QSS-defined selection
    fill (blue ``BUTTON_HOVER`` by default) paints normally. Tables that
    want the row-spanning border with transparent selection (so colour-
    coded cell backgrounds remain visible) should set
    :class:`RowSelectionBorderDelegate` as their item delegate instead.

    Also applies the view's per-column display truncation
    (``TableWidget.set_column_truncation``) at paint time — a table that
    replaces this delegate wholesale opts out of that too.
    """

    #: ``ptk.truncate`` mode → the Qt elide that trims the *same* end.
    _ELIDE_BY_TRUNCATION_MODE = {
        "start": QtCore.Qt.ElideLeft,
        "left": QtCore.Qt.ElideLeft,
        "end": QtCore.Qt.ElideRight,
        "right": QtCore.Qt.ElideRight,
        "middle": QtCore.Qt.ElideMiddle,
        "path": QtCore.Qt.ElideMiddle,
    }

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # option.widget is the view during paint; self.parent() covers the
        # sizeHint / direct-call paths where it isn't populated.
        view = getattr(option, "widget", None) or self.parent()
        get_spec = getattr(view, "column_truncation", None)
        if get_spec is None or not option.text:
            return
        col = index.column()
        spec = get_spec(col)
        if not spec:
            return
        option.text = view.truncated_column_text(col, option.text)
        # A column too narrow for even the truncated text is elided by the
        # style on top of it — elide the same end the mode trims, or the width
        # elide eats the half the mode deliberately kept (a path truncated to
        # its filename, elided right, loses that filename again).
        option.textElideMode = self._ELIDE_BY_TRUNCATION_MODE.get(
            str(spec[1]).lower(), option.textElideMode
        )

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QtWidgets.QLineEdit):
            editor.setFrame(False)
            editor.setTextMargins(0, 0, 0, 0)
            editor.setContentsMargins(0, 0, 0, 0)
            # Stylesheet zeroing covers padding/margins the QStyle adds
            # on top of QLineEdit's own metrics.
            editor.setStyleSheet(
                "QLineEdit { padding: 0px; margin: 0px; border: 0px; }"
            )
        return editor

    #: Dynamic property carrying an ``edit_cell_as`` request on its editor --
    #: on the C++ object, which a collected Python wrapper cannot take with it.
    _EDIT_AS_PROPERTY = "uitkEditCellAs"

    @classmethod
    def _request_of(cls, editor) -> Optional[_EditAsRequest]:
        """The ``TableWidget.edit_cell_as`` request *editor* serves, or ``None``."""
        return editor.property(cls._EDIT_AS_PROPERTY)

    def _take_edit_as(self, editor, index) -> Optional[_EditAsRequest]:
        """The request *editor* serves: its own, else the table's pending one
        for *index*, moved onto the editor as it opens. Carried by its editor,
        a request ends however that editor does -- committed, cancelled, or
        its row removed under it -- and never waits on for the next edit of
        a cell in the same place."""
        pending = self._request_of(editor)
        if pending is not None:
            return pending
        table = self.parent()
        pending = getattr(table, "_edit_as_pending", None)
        if pending is None or pending.cell != (index.row(), index.column()):
            return None
        table._edit_as_pending = None
        editor.setProperty(self._EDIT_AS_PROPERTY, pending)
        return pending

    def setEditorData(self, editor, index):
        pending = self._take_edit_as(editor, index)
        if pending is None or not isinstance(editor, QtWidgets.QLineEdit):
            return super().setEditorData(editor, index)
        editor.setText(pending.text)
        start, length = pending.select

        def select():
            # After the view's own select-all on open, which would undo it.
            try:
                editor.setSelection(start, length)
            except RuntimeError:  # the editor closed first
                pass

        QtCore.QTimer.singleShot(0, select)

    def setModelData(self, editor, model, index):
        pending = self._request_of(editor)
        if pending is None:
            return super().setModelData(editor, model, index)
        text = editor.text() if isinstance(editor, QtWidgets.QLineEdit) else None
        if text is not None and text != pending.text:
            # Once the editor has closed: the host may rebuild the table.
            QtCore.QTimer.singleShot(0, lambda: pending.on_commit(text))


class TableWidget(QtWidgets.QTableWidget, MenuMixin, AttributesMixin, ItemFormatMixin):
    """Enhanced QTableWidget with cell formatting, sorting, and context menu support."""

    # A facade: cell formatting, the scrub gestures, the LMB row drag, the
    # per-column click behaviour and the context menu's registered actions are
    # collaborators in ``table_widget_parts`` (``_CellFormats``, ``_ScrubInput``, ``_RowDrag``,
    # ``_CellClicks``, ``_ContextMenu``), each owning its state and holding the
    # table; every public method stays here, and the Qt event handlers ask them.

    # Qt Designer widget-box entry.
    designer_spec = {"icon": "table", "object_name": "tbl", "size": (280, 160)}

    # Class-level menu defaults (applied when menu is first accessed)
    _menu_defaults = {"hide_on_leave": True}

    #: Emitted just before the context menu opens, so a host can fit its items
    #: to the selection -- relabel, hide or disable them. The menu has no
    #: per-selection hook of its own.
    context_menu_about_to_show = QtCore.Signal()

    #: An :meth:`edit_cell_as` request until its editor opens and takes it.
    _edit_as_pending: Optional[_EditAsRequest] = None

    # Middle-mouse scrub-edit signals (opt-in via ``set_scrub_columns``).
    # Callers translate pixel deltas into value changes — the widget is
    # value-type agnostic.
    cellScrubStarted = QtCore.Signal(int, int)  # (row, col)
    cellScrubMoved = QtCore.Signal(int, int, int, int)  # (row, col, dx, dy) total px
    cellScrubFinished = QtCore.Signal(int, int)  # (row, col)

    # Mouse-wheel scroll over a cell (opt-in via ``set_wheel_scrub_columns``).
    # ``steps`` is the signed Qt notch count -- read from whichever axis of
    # ``angleDelta()`` carries the delta (Alt-held wheels transpose ``.y()``
    # onto ``.x()`` on some platforms / Qt6 builds, so a ``.y()``-only check
    # would miss them entirely). ``modifiers`` is captured from the wheel
    # event itself rather than polled, so receivers don't race against
    # ``QApplication.keyboardModifiers()``.
    cellWheelScrolled = QtCore.Signal(
        int, int, int, object
    )  # (row, col, steps, modifiers)

    # One user edit that writes several cells: a drag edit's commit and its
    # fill of every other drag-selected cell.  Each cell's ``cellChanged``
    # fires in between, so a host can make the burst one step (one undo
    # chunk, one refresh) instead of one per cell.
    editBatchStarted = QtCore.Signal()
    editBatchFinished = QtCore.Signal()

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
        self._formats = _CellFormats(self)
        # Arrows at the top/bottom edge while rows are scrolled out of view.
        OverflowIndicator.attach(self)

        self._left_click_select_only = bool(left_click_select_only)
        self._non_selectable_columns = set()
        self._selection_validator = None
        self._clicks = _CellClicks(self)
        self.actions = TableActions(self)
        self._context_menu = _ContextMenu(self)
        self._stretch_column = None

        # The LMB drag down a column (editable-cell and action-column paths),
        # and the opt-in MMB / wheel scrub gestures.
        self._drag = _RowDrag(self)
        self._scrub = _ScrubInput(self)

        # Zero-spacing editor delegate keeps cell text from visibly
        # jumping when the cell enters edit mode.  Downstream consumers
        # that need a framed editor can replace this with their own
        # delegate via ``setItemDelegate``.
        self.setItemDelegate(_ZeroSpacingEditorDelegate(self))

        self.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked)
        # Hover tracking on the viewport so item delegates receive
        # State_MouseOver in their paint option (action-column hover
        # tint depends on this).
        self.viewport().setAttribute(QtCore.Qt.WA_Hover, True)
        self.verticalHeader().setVisible(False)
        compact_row_height = max(self.fontMetrics().height() + 4, 18)
        self.verticalHeader().setDefaultSectionSize(compact_row_height)
        self.setAlternatingRowColors(False)
        self.setWordWrap(False)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Set selection mode
        self._set_selection_mode(selection_mode)

        self.set_attributes(**kwargs)

    # ------------------------------------------------------------------
    # Header click sorting
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Cell formatting (``_CellFormats``)
    # ------------------------------------------------------------------

    def set_column_formatter(self, col, formatter, append=False):
        """Set a formatter for a specific column."""
        self._formats.set_column_formatter(col, formatter, append)

    def set_header_formatter(self, header, formatter, append=False):
        """Set a formatter for a specific header."""
        self._formats.set_header_formatter(header, formatter, append)

    def set_cell_formatter(self, row, col, formatter, append=False):
        """Set a formatter for a specific cell (row, column)."""
        self._formats.set_cell_formatter(row, col, formatter, append)

    def clear_formatters(self):
        """Clear all column, header, and cell formatters."""
        self._formats.clear_formatters()

    def set_column_truncation(
        self, col, length=None, mode="start", insert="..", head=None
    ):
        """Shorten a column's *displayed* text, leaving its data untouched.

        Purely a paint-time transform, applied by the item delegate through
        :meth:`truncated_column_text`: ``item.text()``, the edit editor, the
        tooltip, sorting and every formatter keep seeing the full value. That
        separation is the point — the reason to want this (long filesystem
        paths crowding a column) is also the reason the full value has to
        survive for the commands reading the cell.

        Parameters:
            col (int/str): Column index or header text.
            length (int): Maximum displayed characters. None/0 clears
                truncation for the column.
            mode (str): ``ptk.truncate`` mode — "start" keeps the tail (the
                filename end of a path), "end" the head, "middle" both, "path"
                both but cutting only at separators (whole path components).
            insert (str): Characters marking the trimmed area.
            head (int): "path" mode only — cap the leading components kept
                (``head=1`` = drive/root), handing the rest of the budget to
                the filename end. None grows the head greedily.
        """
        self._formats.set_column_truncation(col, length, mode, insert, head)

    def column_truncation(self, col):
        """Return a column's ``(length, mode, insert, head)`` spec, or None when off."""
        return self._formats.column_truncation_of(col)

    def truncated_column_text(self, col: int, text: str) -> str:
        """Display form of ``text`` for ``col`` — the item's own data is unchanged.

        The delegate hook behind :meth:`set_column_truncation`; returns
        ``text`` verbatim for columns with no truncation configured.
        """
        return self._formats.truncated_column_text(col, text)

    def apply_formatting(self):
        """Apply formatting based on the registered formatters."""
        self._formats.apply_formatting()

    def ensure_valid_color(self, color, color_type, item, row, col):
        """Ensure a valid QColor, using fallback if needed."""
        return self._formats.ensure_valid_color(color, color_type, item, row, col)

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
        self._formats.format_item(item, key, italic, bold, fg, bg)

    def set_action_color(
        self,
        item: QtWidgets.QTableWidgetItem,
        key: str,
        row: int = -1,
        col: int = -1,
        use_bg: bool = False,
    ):
        """Apply semantic color, but skip reset if nothing defined."""
        self._formats.set_action_color(item, key, row, col, use_bg)

    def action_color_formatter(self, item, value, *_):
        self._formats.action_color_formatter(item, value)

    def make_color_map_formatter(self, color_map: dict):
        return self._formats.make_color_map_formatter(color_map)

    @property
    def _item_defaults(self):
        # Where ``_CellFormats.default_colors`` finds this table's cache.
        return self._formats.item_defaults

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

    # -- Section / category rows -------------------------------------------

    _SECTION_ROLE = QtCore.Qt.UserRole + 900

    @staticmethod
    def add_section_row(
        table: QtWidgets.QTableWidget,
        title: str,
        row: int = -1,
        col_count: int = None,
        bg: Any = None,
        fg: Any = "#999",
        bold: bool = True,
        font_delta: int = -1,
        height: int = 22,
    ) -> int:
        """Insert a non-selectable section header that spans all columns.

        Parameters
        ----------
        table : QTableWidget
            Target table (works with plain QTableWidget or TableWidget).
        title : str
            Section label text.
        row : int
            Row index to insert at.  ``-1`` appends after the last row.
        col_count : int, optional
            Columns to span.  Defaults to ``table.columnCount()``.
        bg : color, optional
            Background colour.  Defaults to ``rgba(255,255,255,20)``.
        fg : color, optional
            Foreground colour.  Defaults to ``#999``.
        bold : bool
            Whether the label is bold.
        font_delta : int
            Point-size adjustment relative to the table font.
        height : int
            Row height in pixels.

        Returns
        -------
        int
            The row index immediately *after* the inserted section row,
            convenient for chaining inserts.
        """
        if row < 0:
            row = table.rowCount()
        if col_count is None:
            col_count = table.columnCount()
        table.insertRow(row)

        bg_color = bg or "transparent"
        fg_color = fg or "#999"

        # Tag column-0 item so is_section_row() works
        tag_item = QtWidgets.QTableWidgetItem()
        tag_item.setFlags(QtCore.Qt.ItemIsEnabled)
        tag_item.setData(TableWidget._SECTION_ROLE, True)
        table.setItem(row, 0, tag_item)

        for c in range(1, col_count):
            filler = QtWidgets.QTableWidgetItem()
            filler.setFlags(QtCore.Qt.ItemIsEnabled)
            filler.setData(TableWidget._SECTION_ROLE, True)
            table.setItem(row, c, filler)

        table.setSpan(row, 0, 1, col_count)

        # Cell widget paints on top of QSS item backgrounds
        label = QtWidgets.QLabel(title)
        label.setIndent(4)
        label_font = label.font()
        label_font.setBold(bold)
        if font_delta and label_font.pointSize() > 0:
            label_font.setPointSize(max(label_font.pointSize() + font_delta, 6))
        label.setFont(label_font)
        label.setStyleSheet(
            f"background: {bg_color}; color: {fg_color};"
            f" border-bottom: 1px solid {fg_color}; padding-left: 2px;"
        )
        table.setCellWidget(row, 0, label)

        table.setRowHeight(row, height)
        return row + 1

    @staticmethod
    def is_section_row(table: QtWidgets.QTableWidget, row: int) -> bool:
        """Return ``True`` if *row* is a section header."""
        item = table.item(row, 0)
        if item is None:
            return False
        return bool(item.data(TableWidget._SECTION_ROLE))

    # The opt-in column sets, read off the table by panels' tests.
    @property
    def _scrub_columns(self) -> set:
        return self._scrub.columns

    @property
    def _single_click_edit_columns(self) -> set:
        return self._clicks.edit_columns

    # ------------------------------------------------------------------
    # Middle-mouse scrub-edit (opt-in — Maya channel-box virtual slider)
    # ------------------------------------------------------------------

    def set_scrub_columns(self, columns: Iterable[int]) -> None:
        """Enable MMB-drag value scrubbing for *columns*.

        Pass an empty iterable to disable.  When a user middle-clicks a
        cell in any of these columns and drags, the widget emits
        ``cellScrubStarted``, ``cellScrubMoved`` (per move event), and
        ``cellScrubFinished`` (on release).  The widget reports raw
        pixel deltas; consumers translate those into value changes
        appropriate for the underlying type / sensitivity.
        """
        self._scrub.columns = set(int(c) for c in columns)

    def add_scrub_column(self, column: int) -> None:
        """Add a single column to the MMB-scrub set."""
        self._scrub.columns.add(int(column))

    def remove_scrub_column(self, column: int) -> None:
        """Remove a column from the MMB-scrub set."""
        self._scrub.columns.discard(int(column))

    def is_scrubbing(self) -> bool:
        """``True`` while an MMB scrub-drag is in progress."""
        return self._scrub.active is not None

    # ------------------------------------------------------------------
    # Wheel-scroll value adjustment (opt-in)
    # ------------------------------------------------------------------

    def set_wheel_scrub_columns(self, columns: Iterable[int]) -> None:
        """Enable mouse-wheel value adjustment for *columns*.

        Wheel events on cells in these columns emit ``cellWheelScrolled``
        with a signed step count (Qt notches, ``angleDelta / 120``) and
        are consumed (no fall-through to the table's own scroll bar).
        Pass an empty iterable to disable.
        """
        self._scrub.wheel_columns = set(int(c) for c in columns)

    def add_wheel_scrub_column(self, column: int) -> None:
        """Add a single column to the wheel-scrub set."""
        self._scrub.wheel_columns.add(int(column))

    def remove_wheel_scrub_column(self, column: int) -> None:
        """Remove a column from the wheel-scrub set."""
        self._scrub.wheel_columns.discard(int(column))

    # ------------------------------------------------------------------
    # Single-click edit (opt-in)
    # ------------------------------------------------------------------

    def set_single_click_edit_columns(self, columns: Iterable[int]) -> None:
        """Enable click-to-edit for *columns* (no double-click required).

        A bare LMB click+release (no drag, no modifier) on a cell in
        these columns immediately opens the editor.  Drags still behave
        normally — the click must release without movement.  Pass an
        empty iterable to disable.
        """
        self._clicks.edit_columns = set(int(c) for c in columns)

    def add_single_click_edit_column(self, column: int) -> None:
        """Add a single column to the single-click-edit set."""
        self._clicks.edit_columns.add(int(column))

    def remove_single_click_edit_column(self, column: int) -> None:
        """Remove a column from the single-click-edit set."""
        self._clicks.edit_columns.discard(int(column))

    # ------------------------------------------------------------------
    # Cell-widget click-forwarding (opt-in)
    # ------------------------------------------------------------------

    def set_cell_widget_click_columns(self, columns: Iterable[int]) -> None:
        """Forward dead-space clicks to embedded cell widgets in *columns*.

        A cell widget (``setCellWidget``) that doesn't span the full cell
        leaves the surrounding area interactive-looking but inert: a click
        there reaches the table, not the widget, so nothing happens.  For
        the registered columns, a bare LMB click on that empty area is
        forwarded to the cell's embedded widget — a combobox opens its
        popup, a button is clicked, other controls take focus.

        Only fires when the click actually reaches the view (i.e. the
        widget didn't cover that point), so it never double-activates a
        widget that received the click directly.  Pass an empty iterable
        to disable.
        """
        self._clicks.widget_columns = set(int(c) for c in columns)

    def add_cell_widget_click_column(self, column: int) -> None:
        """Add a single column to the cell-widget click-forward set."""
        self._clicks.widget_columns.add(int(column))

    def remove_cell_widget_click_column(self, column: int) -> None:
        """Remove a column from the cell-widget click-forward set."""
        self._clicks.widget_columns.discard(int(column))

    def _forward_click_to_cell_widget(self, widget: QtWidgets.QWidget) -> None:
        self._clicks.forward(widget)

    # ------------------------------------------------------------------
    # Mouse gestures: the scrubs, the LMB row drag, the click columns
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())

        # Middle-mouse scrub-edit takes priority over the LMB drag-select
        # path so MMB on a scrub column never falls through to selection.
        if self._scrub.press(event, index):
            return
        self._drag.press(event, index)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Active MMB scrub: emit deltas, suppress base move handling so
        # selection rubber-band etc. don't interfere.
        if self._scrub.move(event):
            return
        self._drag.move(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # Finish an active MMB scrub before falling through to the LMB
        # drag-select cleanup.
        if self._scrub.release(event):
            return
        gesture = self._drag.finish(event)
        # A drag ending on the cell it started from still emits ``clicked``;
        # the drag dispatch below owns every row it travelled, so the click
        # must not fire that row's action a second time.
        with self._clicks.suppressed(gesture.was_drag):
            super().mouseReleaseEvent(event)
        # A bare click: click-to-edit, else cell-widget forwarding; a drag:
        # its own dispatch.
        if self._clicks.release(event, gesture):
            return
        self._drag.dispatch(event, gesture)

    def wheelEvent(self, event):
        """Consume wheel events on wheel-scrub columns; emit signal.

        Fires whether or not the cell is in edit mode — when an editor
        is open the wheel event sometimes reaches us via the
        ``eventFilter`` path on the editor and sometimes via direct
        propagation from the editor through the viewport to here.
        Either path emits the same signal; the slot then calls
        :meth:`refresh_active_editor` to keep the editor display in
        sync with the model.
        """
        if self._scrub.wheel(event):
            return
        super().wheelEvent(event)

    def eventFilter(self, obj, event):
        """Catch wheel events on editors so wheel-scrub also works in
        edit mode.

        ``QAbstractItemView`` automatically installs the view as an
        event filter on every editor it opens (to handle Tab/Enter/Esc).
        We piggy-back on that registration: when a wheel event arrives
        while editing a wheel-scrub cell, route it through the same
        ``cellWheelScrolled`` path.
        """
        # The type test first: the view filters events from construction on
        # (``OverflowIndicator.attach`` in ``__init__`` already sends some),
        # before the collaborators exist.
        if event.type() == QtCore.QEvent.Wheel and self._scrub.editor_wheel(event):
            return True
        return super().eventFilter(obj, event)

    def _emit_wheel_scrub(self, index, event):
        self._scrub.emit_wheel(index, event)

    def active_editor(self) -> Optional[QtWidgets.QWidget]:
        """Return the currently-open cell editor widget, or ``None``.

        Found via ``viewport().focusWidget()`` because ``QAbstractItemView``
        always gives the editor focus when it opens.  Caller should
        ``isinstance``-check the return value if a specific editor type
        is expected (e.g. ``QLineEdit``) — non-editor focus widgets and
        ``None`` are both valid "no editor open" indicators.
        """
        viewport = self.viewport()
        if viewport is None:
            return None
        return viewport.focusWidget()

    def refresh_active_editor(self) -> None:
        """If a cell editor is currently open, refresh its display from
        the model.

        Use this after programmatically updating an item whose cell is
        currently being edited so the user sees the new value in the
        editor instead of the stale text the editor was opened with.

        Finds the editor via ``viewport().focusWidget()`` — reliable
        across Qt versions because ``QAbstractItemView`` always gives
        the editor focus when it opens.  For ``QLineEdit`` editors, also
        force-sets the text directly: some Qt styles don't repaint
        ``QLineEdit`` when its ``text`` property is set via
        ``QStyledItemDelegate.setEditorData`` while the editor has focus.
        An :meth:`edit_cell_as` editor is left alone: it shows the host's
        text, not the cell's.
        """
        if self.state() != QtWidgets.QAbstractItemView.EditingState:
            return
        viewport = self.viewport()
        if viewport is None:
            return
        editor = viewport.focusWidget()
        if editor is None:
            return
        if _ZeroSpacingEditorDelegate._request_of(editor) is not None:
            return  # an edit_cell_as editor shows the host's text, not the cell's
        index = self.currentIndex()
        if not index.isValid():
            return
        try:
            delegate = self.itemDelegate(index)
            if delegate is not None:
                delegate.setEditorData(editor, index)
            if isinstance(editor, QtWidgets.QLineEdit):
                new_value = index.data(QtCore.Qt.EditRole)
                if new_value is None:
                    new_value = index.data(QtCore.Qt.DisplayRole)
                if new_value is not None:
                    text = str(new_value)
                    if editor.text() != text:
                        # Preserve cursor position relative to text end
                        # so the user's caret doesn't jump to col 0 on
                        # every notch.
                        cursor_from_end = len(editor.text()) - editor.cursorPosition()
                        editor.setText(text)
                        new_pos = max(0, len(text) - cursor_from_end)
                        editor.setCursorPosition(new_pos)
        except Exception:
            pass

    def set_sorted_cell(
        self, row: int, column: int, text: str, key: Any, editable: bool = False
    ) -> QtWidgets.QTableWidgetItem:
        """Show *text* in a cell that sorts by *key* rather than by its text.

        For a column of figures written for reading -- ``"900 KB"`` sorts after
        ``"2 MB"`` as text -- give the number as *key* (``None`` sorts first).
        Replaces the cell's item the first time, keeping its tooltip, user data
        and colours; re-keys it in place after. Read-only unless *editable*.

        Returns:
            The cell's item.
        """
        item = self.item(row, column)
        if not isinstance(item, _SortKeyItem):
            fresh = _SortKeyItem()
            if item is not None:
                for role in (
                    QtCore.Qt.ToolTipRole,
                    QtCore.Qt.UserRole,
                    QtCore.Qt.ForegroundRole,
                    QtCore.Qt.BackgroundRole,
                ):
                    fresh.setData(role, item.data(role))
            item = fresh
            self.setItem(row, column, item)
        item.setText(text)
        item.setData(_SortKeyItem.KEY_ROLE, key)
        flags = item.flags()
        item.setFlags(
            flags | QtCore.Qt.ItemIsEditable
            if editable
            else flags & ~QtCore.Qt.ItemIsEditable
        )
        return item

    def edit_cell_as(
        self,
        row: int,
        column: int,
        text: str,
        on_commit: Callable[[str], Any],
        select: Optional[Tuple[int, int]] = None,
    ) -> bool:
        """Open a cell's inline editor on *text* instead of the cell's own,
        handing what is typed to *on_commit*.

        For an edit of PART of what a cell shows -- a rename that offers just
        the file name of a path cell, in place. The cell keeps its text: Enter
        (or leaving the editor) calls ``on_commit(new_text)`` once the editor
        has closed, only when the text changed, and writes nothing to the cell
        -- no ``cellChanged``; Esc cancels. The request is for this one edit:
        the next opens on the cell's own text again. Needs the table's own
        editor delegate: a cell drawn by another (``setItemDelegate``) is
        refused.

        Parameters:
            row, column: The cell; it must hold an editable item.
            text: What the editor opens on.
            on_commit: Called with the new text.
            select: ``(start, length)`` pre-selected. Default: the stem --
                everything before the last dot -- as a file manager selects a
                name for renaming.

        Returns:
            False when the cell cannot be edited this way (no item, not
            editable, another delegate, an editor already open); nothing is
            opened then.
        """
        item = self.item(row, column)
        if item is None or not item.flags() & QtCore.Qt.ItemIsEditable:
            return False
        if self.state() == QtWidgets.QAbstractItemView.EditingState:
            return False
        delegate = self.itemDelegateForIndex(self.indexFromItem(item))
        if not isinstance(delegate, _ZeroSpacingEditorDelegate):
            return False  # another editor would show and write the cell's own text
        if select is None:
            dot = text.rfind(".")
            select = (0, dot if dot > 0 else len(text))
        self._edit_as_pending = _EditAsRequest((row, column), text, on_commit, select)
        self._drag.disarm()  # a drag's propagation is not this
        self.scrollToItem(item)
        self.editItem(item)
        # The editor took the request as it opened; with none open, nothing will.
        self._edit_as_pending = None
        return self.state() == QtWidgets.QAbstractItemView.EditingState

    def commitData(self, editor):
        """Commit *editor*; a drag edit then fills every drag-selected cell.

        The commit and the fill are one user edit, so they run between
        ``editBatchStarted`` and ``editBatchFinished``.  Filling here rather
        than on close leaves a reverted edit (Esc) unfilled: Qt commits only
        an accepted one.
        """
        self._drag.commit(editor, super().commitData)

    def closeEditor(self, editor, hint):
        """End a drag edit, committed or reverted."""
        super().closeEditor(editor, hint)
        self._drag.disarm()

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
        self._clicks.click_actions[column] = action

    def set_left_click_select_only(self, enabled: bool):
        """Toggle whether non-left clicks can change selection."""
        self._left_click_select_only = bool(enabled)

    def setLeftClickSelectOnly(self, enabled: bool) -> None:
        """Qt-property setter for :meth:`set_left_click_select_only`.

        ``pyside6-uic`` compiles a ``.ui`` property into a ``set<Name>`` call,
        so the camelCase spelling has to exist alongside the snake_case one.
        """
        self.set_left_click_select_only(enabled)

    #: Qt-property mirror of :meth:`set_left_click_select_only`, so the option
    #: is a checkbox in Designer and round-trips through the ``.ui`` file.
    leftClickSelectOnly = QtCore.Property(
        bool,
        fget=lambda self: self._left_click_select_only,
        fset=setLeftClickSelectOnly,
    )

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
        was_blocked = self.signalsBlocked()
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
                maxlen = max((len(col) for col in data.values()), default=0)
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

                    # Action columns are non-editable/non-selectable
                    if col_idx in self.actions._columns:
                        item.setFlags(
                            item.flags()
                            & ~QtCore.Qt.ItemIsEditable
                            & ~QtCore.Qt.ItemIsSelectable
                        )

                    # Set tooltip to text content by default
                    if text_str:
                        item.setToolTip(text_str)

                    if data_val is not None:
                        item.setData(QtCore.Qt.UserRole, data_val)
                    self.setItem(row_idx, col_idx, item)
        finally:
            # Restore in finally: an exception mid-populate previously skipped
            # the unblock, leaving the table permanently signal-dead.
            self.blockSignals(was_blocked)
            self.setUpdatesEnabled(True)
        self.set_attributes(**kwargs)
        self.apply_formatting()
        self.actions._reapply()

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

    # -- Column configuration (visibility, reorder, persistence) ----------

    def enable_column_config(
        self,
        settings=None,
        settings_key=None,
        locked=(),
        reorderable=False,
        hidden_by_default=(),
    ):
        """Enable header right-click menu for column visibility and drag reorder.

        The shared :class:`~uitk.widgets.column_config.ColumnConfig`, as
        ``TreeWidget.enable_column_config``: one checkable row per column, the
        last visible (and any *locked*) column kept, the layout saved on every
        change.

        Parameters:
            settings: A SettingsManager instance (or any object with
                ``branch(name)`` / ``value(key, default)`` /
                ``setValue(key, value)`` / ``sync()``).  If *None*, a
                SettingsManager (``org="uitk"``, ``app="TableWidget"``) is
                created automatically.
            settings_key: Namespace prefix for stored keys.  Defaults to
                the widget's ``objectName()`` or ``"TableWidget"``.
            locked: Logical columns that can't be hidden.
            reorderable: The menu's rows can also be dragged into another
                column order (see ``ColumnConfig``).
            hidden_by_default: Logical columns hidden until the user's own
                layout is saved -- optional columns they turn on from the menu.
        """
        ColumnConfig.attach(
            self,
            settings=settings,
            settings_key=settings_key or self.objectName() or "TableWidget",
            locked=locked,
            app="TableWidget",
            reorderable=reorderable,
            hidden_by_default=hidden_by_default,
        )

    def restore_column_state(self):
        """Apply persisted visibility and order.  Call after headers are set."""
        config = ColumnConfig.of(self)
        if config is not None:
            config.restore()

    # -- Row colour tags ---------------------------------------------------

    def enable_row_tags(self, settings=None, settings_key=None, defaults=None):
        """Show per-row colour tags as a strip down the left edge.

        The shared :class:`~uitk.widgets.row_tags.RowTags`, as
        ``TreeWidget.enable_row_tags``: tag rows with ``set_tag``, offer the
        quick-pick swatches with ``add_to_menu`` (a uitk ``Menu`` keeps the
        row and tags the selection at the moment of the pick), and hear the
        user's picks on ``assigned``.

        Parameters:
            settings: A SettingsManager the palette is saved in.  If *None*, a
                SettingsManager (``org="uitk"``, ``app="TableWidget"``) is
                created automatically.
            settings_key: The palette's branch.  Defaults to the widget's
                ``objectName()`` or ``"TableWidget"``.
            defaults: ``{slot: colour}`` in order; ``Palette.tags()`` if *None*.

        Returns:
            The view's :class:`~uitk.widgets.row_tags.RowTags`.
        """
        return RowTags.attach(
            self,
            settings=settings,
            settings_key=settings_key or self.objectName() or "TableWidget",
            app="TableWidget",
            defaults=defaults,
        )

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

    # ------------------------------------------------------------------
    # Auto-fit the host window to the table's contents
    # ------------------------------------------------------------------

    # Default ceiling for :meth:`fit_window_to_contents`, as a fraction of
    # the screen's available geometry — ``(width, height)``.  Past this the
    # window stops growing and the table scrolls instead; an unbounded row
    # count would otherwise size the window larger than the display, with
    # no way to reach the bottom rows.
    MAX_AUTOFIT_FRACTION = (0.5, 0.5)

    @staticmethod
    def compute_autofit_size(content, chrome, scrollbar, maximum, minimum):
        """Return the ``(w, h)`` window size that shows *content* whole, capped.

        Pure arithmetic — no Qt — so the sizing policy is testable on its own.

        Parameters:
            content (tuple): Total width of the visible columns, total
                height of the visible rows.
            chrome (tuple): Window furniture outside the table's scrollable
                viewport (margins, table frame, the table's own headers).
                Must *exclude* the scrollbars — those are applied from
                *scrollbar*, for the post-resize state.
            scrollbar (tuple): ``(vertical_width, horizontal_height)``, added
                only on the axis where the cap forces a scrollbar to appear.
            maximum (tuple): Size ceiling.
            minimum (tuple): The window's minimum size. Wins over *maximum*.

        Returns:
            (tuple) The target ``(width, height)``.
        """
        w = content[0] + chrome[0]
        h = content[1] + chrome[1]

        # Capping the height clips rows, so a vertical scrollbar appears
        # and eats viewport width — widen to keep the columns whole.
        if h > maximum[1]:
            h = maximum[1]
            w += scrollbar[0]
        # Mirror case: a width cap brings in the horizontal scrollbar,
        # which eats height that the height cap must still bound.
        if w > maximum[0]:
            w = maximum[0]
            h = min(h + scrollbar[1], maximum[1])

        return (max(w, minimum[0]), max(h, minimum[1]))

    def max_autofit_size(self, max_fraction=None):
        """Return the ``(w, h)`` ceiling for :meth:`fit_window_to_contents`.

        *max_fraction* (default :attr:`MAX_AUTOFIT_FRACTION`) of the available
        geometry of the screen this table's window sits on — multi-monitor
        safe — falling back to the primary screen and finally to no cap.
        """
        win = self.window()
        screen = None
        getter = getattr(win, "screen", None) if win else None  # Qt 5.14+
        if callable(getter):
            screen = getter()
        if screen is None:
            screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            return (16777215, 16777215)  # QWIDGETSIZE_MAX — no cap
        avail = screen.availableGeometry()
        frac_w, frac_h = max_fraction or self.MAX_AUTOFIT_FRACTION
        return (int(avail.width() * frac_w), int(avail.height() * frac_h))

    def fit_window_to_contents(self, max_fraction=None, defer=True):
        """Resize this table's window so the table's contents fit exactly.

        Growth stops at :meth:`max_autofit_size`; past that the table keeps
        its own scrollbars (``ScrollBarAsNeeded``) and the user scrolls. The
        window widens to absorb the scrollbar a cap brings in, so no column
        is clipped.

        Only ``ResizeToContents`` columns are recomputed — a blanket
        ``resizeColumnsToContents()`` would override ``Fixed``-width columns
        (action columns sized to row height by :class:`TableActions`) and
        inflate them, masking the real content total.

        Args:
            max_fraction (tuple, optional): Override the screen-fraction
                ceiling for this call.
            defer (bool): Run on a later event-loop tick (default). Deferring
                twice lets a caller's ``setUpdatesEnabled`` / signal-block
                unwind, then gives ``ResizeToContents`` columns a tick to
                apply their final widths before they are measured. Pass
                ``False`` only when the table is already fully laid out.
        """
        if not defer:
            self._do_fit_window_to_contents(max_fraction)
            return
        QtCore.QTimer.singleShot(
            0,
            lambda: QtCore.QTimer.singleShot(
                0, lambda: self._do_fit_window_to_contents(max_fraction)
            ),
        )

    def _do_fit_window_to_contents(self, max_fraction=None):
        """Measure and apply the fit. See :meth:`fit_window_to_contents`."""
        try:
            win = self.window()
            if win is None:
                return

            QHV = QtWidgets.QHeaderView
            header = self.horizontalHeader()
            for col in range(self.columnCount()):
                if (
                    not self.isColumnHidden(col)
                    and header.sectionResizeMode(col) == QHV.ResizeToContents
                ):
                    self.resizeColumnToContents(col)

            lay = win.layout()
            if lay is not None:
                lay.activate()
            cw = win.centralWidget() if hasattr(win, "centralWidget") else None
            if cw is not None and cw.layout() is not None:
                cw.layout().activate()

            header_len = header.length()
            if header_len <= 0:
                return

            viewport = self.viewport()
            if viewport.width() <= 0 or viewport.height() <= 0:
                return  # not laid out yet — nothing meaningful to measure

            # Chrome = every pixel of the window OUTSIDE the scrollable
            # viewport: window margins, table frame, and the table's own
            # headers (which live in the viewport margins, not the
            # viewport).  One ``win - viewport`` measurement captures all
            # of it — adding frame / header sizes on top double-counts
            # them.  It also includes whichever scrollbars are showing
            # *right now*, so those are subtracted back out and re-applied
            # by ``compute_autofit_size`` for the post-resize state.
            vbar = self.verticalScrollBar()
            hbar = self.horizontalScrollBar()
            vsb_now = vbar.width() if (vbar and vbar.isVisible()) else 0
            hsb_now = hbar.height() if (hbar and hbar.isVisible()) else 0
            chrome_w = max(win.width() - viewport.width() - vsb_now, 0)
            chrome_h = max(win.height() - viewport.height() - hsb_now, 0)

            rows_h = 0
            for row in range(self.rowCount()):
                if not self.isRowHidden(row):
                    rows_h += self.rowHeight(row)

            target_w, target_h = self.compute_autofit_size(
                content=(header_len, rows_h),
                chrome=(chrome_w, chrome_h),
                scrollbar=(
                    vbar.sizeHint().width() if vbar else 0,
                    hbar.sizeHint().height() if hbar else 0,
                ),
                maximum=self.max_autofit_size(max_fraction),
                minimum=(win.minimumWidth(), win.minimumHeight()),
            )

            if target_w != win.width() or target_h != win.height():
                win.resize(target_w, target_h)
        except RuntimeError:
            pass  # widget (or its window) destroyed mid-fit

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
        self._context_menu.register(
            object_name,
            handler,
            columns,
            include_current,
            allow_empty,
            transform,
            pass_widget,
        )

    def unregister_menu_action(self, object_name: str):
        self._context_menu.unregister(object_name)

    def _dispatch_registered_menu_action(self, widget: QtWidgets.QWidget):
        # The menu's ``on_item_interacted`` slot (see ``_ContextMenu``).
        self._context_menu.dispatch(widget)

    def _show_context_menu(self, position):
        # The popup's slot: connected in ``__init__``, and reconnected by a host
        # that rewires ``customContextMenuRequested`` (tentacle's Channels runs
        # its own pass first).
        self._context_menu.show_at(position)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
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
