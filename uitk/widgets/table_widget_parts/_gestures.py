# !/usr/bin/python
# coding=utf-8
"""A table's mouse gestures -- parts of
:class:`~uitk.widgets.tableWidget.TableWidget` (see ``table_widget_parts``):
the scrubs, the left-button row drag and the per-column click behaviour, which
the table's own event handlers ask in turn."""

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, Dict, List, NamedTuple, Optional

from qtpy import QtCore, QtWidgets

from uitk.managers.cursor_manager import CursorManager

if TYPE_CHECKING:
    from uitk.widgets.tableWidget import TableWidget


class _ScrubInput:
    """A :class:`TableWidget`'s opt-in scrub gestures: a middle-mouse drag on a
    scrub column (Maya channel-box virtual slider) and the wheel over a
    wheel-scrub column.

    Owns the opted-in columns, the drag in flight and the wheel's sub-notch
    remainder, and reports through the table's signals; the table's Qt event
    handlers ask it first.
    """

    def __init__(self, table: "TableWidget"):
        self._table = table
        # ``columns`` is the opt-in set of columns where MMB-drag scrubs the
        # cell value; ``active`` tracks an in-flight drag.
        self.columns: set = set()
        self.active: Optional[Dict[str, Any]] = None
        # Wheel-scroll value adjustment (opt-in via ``set_wheel_scrub_columns``).
        self.wheel_columns: set = set()
        # The wheel's carried sub-notch delta, and the cell it belongs to.
        self._wheel_accum_cell = None
        self._wheel_accum = 0

    def press(self, event, index) -> bool:
        """Start a scrub on an MMB press over a scrub column; True if it did."""
        if not (
            event.button() == QtCore.Qt.MiddleButton
            and self.columns
            and index.isValid()
            and index.column() in self.columns
        ):
            return False
        table = self._table
        self.active = {
            "row": index.row(),
            "col": index.column(),
            "start": event.pos(),
        }
        CursorManager.push(table, QtCore.Qt.SizeHorCursor)
        table.cellScrubStarted.emit(index.row(), index.column())
        event.accept()
        return True

    def move(self, event) -> bool:
        """Report an active scrub's total delta; True while one is active."""
        if self.active is None:
            return False
        start = self.active["start"]
        dx = event.pos().x() - start.x()
        dy = event.pos().y() - start.y()
        self._table.cellScrubMoved.emit(self.active["row"], self.active["col"], dx, dy)
        event.accept()
        return True

    def release(self, event) -> bool:
        """Finish an active scrub on its MMB release; True if it did."""
        if event.button() != QtCore.Qt.MiddleButton or self.active is None:
            return False
        row = self.active["row"]
        col = self.active["col"]
        self.active = None
        table = self._table
        CursorManager.pop(table)
        table.cellScrubFinished.emit(row, col)
        event.accept()
        return True

    def wheel(self, event) -> bool:
        """Consume a wheel event over a wheel-scrub cell; True if it did."""
        if not self.wheel_columns:
            return False
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        index = self._table.indexAt(pos)
        if not (index.isValid() and index.column() in self.wheel_columns):
            return False
        self.emit_wheel(index, event)
        event.accept()
        return True

    def editor_wheel(self, event) -> bool:
        """Route a wheel event on an open editor of a wheel-scrub cell through
        the same signal; True if it did."""
        table = self._table
        if (
            self.wheel_columns
            and table.state() == QtWidgets.QAbstractItemView.EditingState
        ):
            idx = table.currentIndex()
            if idx.isValid() and idx.column() in self.wheel_columns:
                self.emit_wheel(idx, event)
                return True
        return False

    @staticmethod
    def _wheel_signed_delta(event) -> int:
        """Return whichever axis of ``event.angleDelta()`` carries the delta.

        When Alt is held some platforms / Qt6 builds transpose the wheel
        delta from ``.y()`` onto ``.x()``; reading only ``.y()`` would
        miss Alt-modified scrolls entirely (the channels-cell symptom
        where Alt and Ctrl+Alt did nothing).
        """
        delta = event.angleDelta()
        return delta.y() or delta.x()

    def emit_wheel(self, index, event):
        """Emit ``cellWheelScrolled`` after quantizing the wheel angle
        to whole notches.

        ``event`` is the original ``QWheelEvent`` so we can both read
        its modifier mask (passed via the signal so the receiver doesn't
        race-poll ``QApplication.keyboardModifiers()``) and fall back to
        the X axis when Alt has transposed the delta.

        The slot is expected to update the underlying model
        synchronously and then call :meth:`TableWidget.refresh_active_editor`
        to sync any open editor.  Decoupling editor-refresh from
        wheel-event delivery makes the behavior identical regardless
        of which Qt path delivers the wheel (eventFilter vs
        wheelEvent).
        """
        signed = self._wheel_signed_delta(event)
        # Accumulate per cell so precision touchpads / free-spin wheels that
        # only ever send sub-notch deltas (e.g. ±8) still reach a full notch
        # across events — plain truncation made them permanently dead in both
        # directions. Truncate toward zero (not floor) so equal-magnitude
        # up/down accumulations quantize symmetrically, and keep the residual
        # so nothing is lost between events. The residual resets when the
        # hovered cell changes (no cross-cell carry-over).
        cell = (index.row(), index.column())
        if self._wheel_accum_cell != cell:
            self._wheel_accum_cell = cell
            self._wheel_accum = 0
        self._wheel_accum += signed
        steps = int(self._wheel_accum / 120)
        if not steps:
            return
        self._wheel_accum -= steps * 120
        self._table.cellWheelScrolled.emit(
            cell[0], cell[1], int(steps), event.modifiers()
        )


class _DragGesture(NamedTuple):
    """How an LMB drag ended -- :meth:`_RowDrag.finish` hands it to the rest
    of the release."""

    was_drag: bool
    had_modifier: bool
    is_action: bool
    column: Optional[int]
    rows: List[int]


class _RowDrag:
    """A :class:`TableWidget`'s LMB drag down a column (Maya channel-box
    style): over an action column it fires every row it crossed; over an
    editable one it opens the editor on release and, when that edit commits,
    fills every drag-selected cell from it.

    Owns the gesture in flight and the fill armed for the editor it opened.
    """

    def __init__(self, table: "TableWidget"):
        self._table = table
        self.reset()
        # A drag edit's fill: the cells, and the editor they belong to.
        self.selected_indexes = None
        self.editor = None

    def reset(self):
        """Clear all drag-tracking fields."""
        self.start_pos = None
        self.occurred = False
        self.has_modifier = False
        self.column = None  # column where the drag started
        self.rows = []  # rows traversed during drag
        self.is_action = False  # True when dragging over an action column

    def press(self, event, index):
        self.start_pos = event.pos()
        self.has_modifier = bool(
            event.modifiers() & (QtCore.Qt.ShiftModifier | QtCore.Qt.ControlModifier)
        )
        self.occurred = False

        # An action column has no selection for Shift / Ctrl to extend (its
        # cells are non-selectable) and panels read those modifiers per row --
        # the Channels Key column breaks a connection on Ctrl -- so a modifier
        # drag tracks rows there; on any other column it stays a selection
        # gesture and fires nothing.
        is_action = index.isValid() and index.column() in self._table.actions._columns
        if (
            index.isValid()
            and event.button() == QtCore.Qt.LeftButton
            and (is_action or not self.has_modifier)
        ):
            self.column = index.column()
            self.rows = [index.row()]
            self.is_action = is_action
        else:
            self.column = None
            self.rows = []
            self.is_action = False

    def move(self, event):
        if (
            not self.occurred
            and self.start_pos is not None
            and (event.pos() - self.start_pos).manhattanLength()
            > QtWidgets.QApplication.startDragDistance()
        ):
            self.occurred = True

        # Track the rows the drag travels over, the skipped ones included.
        if self.column is not None and self.occurred:
            self.track_row(event.pos())

    def track_row(self, pos):
        """Record the row under *pos* and every row between it and the last
        row recorded.

        Mouse moves are sampled, so a drag quicker than that sampling lands
        events on a few rows only — without filling the gap a drag covers its
        two ends and misses the rows in between.  The column is ignored: the
        gesture belongs to the column the press started in, so drifting
        sideways (or past the last row) doesn't drop rows.  Hidden rows are
        left out, and a row crossed twice is recorded once.
        """
        row = self.row_at(pos.y())
        if row == -1 or not self.rows:
            return
        last = self.rows[-1]
        step = 1 if row >= last else -1
        for r in range(last + step, row + step, step):
            if r not in self.rows and not self._table.isRowHidden(r):
                self.rows.append(r)

    def row_at(self, y):
        """The row under viewport *y*, clamped to the nearest one past the ends.

        ``rowAt`` reports -1 above the first row and below the last (including
        the empty space under a short table), yet dragging out past the end is
        exactly how one covers the final rows — clamping keeps them in the
        gesture instead of ending it at the last row an event landed on.
        """
        table = self._table
        row = table.rowAt(y)
        if row != -1:
            return row
        visible = [r for r in range(table.rowCount()) if not table.isRowHidden(r)]
        if not visible:
            return -1
        first_top = table.visualRect(table.model().index(visible[0], 0)).top()
        return visible[0] if y < first_top else visible[-1]

    def finish(self, event) -> _DragGesture:
        """End the gesture on its release: what it was, with the tracking
        cleared for the next."""
        # The release point can sit rows away from the last move event.
        if self.occurred and self.column is not None:
            self.track_row(event.pos())
        gesture = _DragGesture(
            was_drag=self.occurred,
            had_modifier=self.has_modifier,
            is_action=self.is_action,
            column=self.column,
            rows=list(self.rows),
        )
        self.reset()
        return gesture

    def dispatch(self, event, gesture: _DragGesture):
        """Act on a finished drag: fire an action column's rows, or open the
        release cell's editor armed to fill the drag-selected cells."""
        if not (
            gesture.was_drag
            and event.button() == QtCore.Qt.LeftButton
            and (gesture.is_action or not gesture.had_modifier)
        ):
            return

        table = self._table
        if gesture.is_action and gesture.column is not None and gesture.rows:
            # Action column — dispatch every traversed row
            table.actions._on_drag(gesture.rows, gesture.column)
        else:
            # Editable column — open editor on release cell, propagate on commit
            index = table.indexAt(event.pos())
            item = table.item(index.row(), index.column()) if index.isValid() else None
            if item and (item.flags() & QtCore.Qt.ItemIsEditable):
                selected = [
                    idx
                    for idx in table.selectedIndexes()
                    if idx.column() == index.column()
                ]
                table.editItem(item)
                # Armed only for the editor this opened: a drag down a
                # read-only column (selecting rows) opens none, and its cells
                # must not be filled by a later, ordinary edit.
                editor = table.indexWidget(index)
                if editor is not None:
                    self.selected_indexes = selected
                    self.editor = editor

    def commit(self, editor, base_commit: Callable[[QtWidgets.QWidget], None]):
        """Commit *editor* through *base_commit* (the view's own); a drag edit's
        commit then fills every drag-selected cell."""
        if self.selected_indexes is None or editor is not self.editor:
            base_commit(editor)
            return
        table = self._table
        # Plain cells, read before the commit: a host that rebuilds the table
        # on ``cellChanged`` (blendertk's Channels) leaves the current index
        # and the stored indexes stale after the first write.
        current = table.currentIndex()
        source = (current.row(), current.column())
        targets = [
            (i.row(), i.column())
            for i in self.selected_indexes
            if i.row() != current.row()
        ]
        table.editBatchStarted.emit()
        try:
            base_commit(editor)
            if current.isValid():
                self.propagate(source, targets)
        finally:
            # One fill per drag edit: the editor's focus-out after Enter
            # commits again.
            self.disarm()
            table.editBatchFinished.emit()

    def disarm(self):
        """Drop the armed fill: its edit is over, or never was a drag's."""
        self.selected_indexes = self.editor = None

    def propagate(self, source, targets):
        """Copy the edited cell's value to every other drag-selected cell.

        Parameters:
            source (tuple[int, int]): The edited cell's ``(row, column)``.
            targets (list[tuple[int, int]]): The cells to fill.  Cells, not
                items: each write may make the host rebuild the table.
        """
        table = self._table
        edited_item = table.item(*source)
        if not edited_item:
            return

        new_text = edited_item.text()
        new_data = edited_item.data(QtCore.Qt.UserRole)

        for row, col in targets:
            target = table.item(row, col)
            if target:
                target.setText(new_text)
                if new_data is not None:
                    target = table.item(row, col)  # rebuilt on the text write?
                    if target:
                        target.setData(QtCore.Qt.UserRole, new_data)

        table.apply_formatting()


class _CellClicks:
    """A :class:`TableWidget`'s per-column click behaviour: each column's click
    action, click-to-edit, and the forwarding of a click on a cell widget's
    dead space to that widget.

    Owns the opted-in columns and the latch that keeps the release ending a
    drag from firing a click action too.
    """

    #: Widget types whose click has an unambiguous "activate" meaning.
    INTERACTIVE_WIDGETS = (
        QtWidgets.QComboBox,
        QtWidgets.QAbstractButton,
        QtWidgets.QAbstractSpinBox,
        QtWidgets.QLineEdit,
        QtWidgets.QAbstractSlider,
    )

    def __init__(self, table: "TableWidget"):
        self._table = table
        self.click_actions = {}  # {column: callable(row, col)}
        # Single-click-edit (opt-in via ``set_single_click_edit_columns``):
        # LMB click + release without drag enters edit mode immediately,
        # bypassing the default DoubleClicked edit trigger for those
        # columns only.
        self.edit_columns: set = set()
        # Cell-widget click-forwarding (opt-in via
        # ``set_cell_widget_click_columns``): a bare LMB click on the empty
        # part of a cell hosting an embedded widget is forwarded to that
        # widget. A cell widget can be narrower than its cell — e.g. a combo
        # with ``AdjustToContents`` self-resizes to its content width after
        # the view's layout and isn't re-stretched until the next relayout —
        # leaving the rest of the cell interactive-looking but inert.
        self.widget_columns: set = set()
        # Latched over the release that ends a drag — see ``suppressed``.
        self._suppress = False
        table.cellClicked.connect(self.on_cell_clicked)

    def on_cell_clicked(self, row, col):
        """Handle cell clicks and dispatch to registered actions."""
        if self._suppress:
            return
        if col in self.click_actions:
            self.click_actions[col](row, col)

    @contextmanager
    def suppressed(self, on: bool):
        """Hold click actions back for the release ending a drag (*on*): a
        drag ending on the cell it started from still emits ``clicked``, and
        the drag's own dispatch owns every row it travelled."""
        self._suppress = on
        try:
            yield
        finally:
            self._suppress = False

    def release(self, event, gesture: _DragGesture) -> bool:
        """Act on a bare LMB click: open a click-to-edit cell's editor, else
        forward to a cell widget; True if either did."""
        if (
            gesture.was_drag
            or gesture.had_modifier
            or event.button() != QtCore.Qt.LeftButton
        ):
            return False
        table = self._table

        # Single-click edit: a registered column opens the editor
        # immediately.  Cells with an embedded widget (combobox, etc.)
        # handle their own input — skip those.
        if self.edit_columns:
            index = table.indexAt(event.pos())
            if (
                index.isValid()
                and index.column() in self.edit_columns
                and table.cellWidget(index.row(), index.column()) is None
            ):
                item = table.item(index.row(), index.column())
                if item and (item.flags() & QtCore.Qt.ItemIsEditable):
                    table.editItem(item)
                    return True

        # Cell-widget click-forward: a bare click on the empty part of a
        # cell that hosts an embedded widget (so the click reached the
        # table, not the widget) is routed to that widget.  Placed after
        # single-click-edit so numeric/text cells still open their editor;
        # only cells with a cell widget are forwarded.
        if self.widget_columns:
            index = table.indexAt(event.pos())
            if index.isValid() and index.column() in self.widget_columns:
                cell_widget = table.cellWidget(index.row(), index.column())
                if cell_widget is not None:
                    self.forward(cell_widget)
                    return True
        return False

    def forward(self, widget: QtWidgets.QWidget) -> None:
        """Activate *widget* (or its primary control) as if clicked.

        Cells often wrap the real control in a centering container, so the
        cell widget itself may be a plain ``QWidget`` — resolve to the first
        interactive descendant before acting.  A combobox opens its popup, a
        button is clicked, everything else focusable takes focus.
        """
        target = widget
        if not isinstance(widget, self.INTERACTIVE_WIDGETS):
            target = next(
                (
                    c
                    for c in widget.findChildren(QtWidgets.QWidget)
                    if isinstance(c, self.INTERACTIVE_WIDGETS)
                ),
                None,
            )
        if target is None:
            return
        if isinstance(target, QtWidgets.QComboBox):
            target.showPopup()
        elif isinstance(target, QtWidgets.QAbstractButton):
            target.click()
        elif target.focusPolicy() != QtCore.Qt.NoFocus:
            target.setFocus(QtCore.Qt.MouseFocusReason)
