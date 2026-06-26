# !/usr/bin/python
# coding=utf-8
"""In-cell choice (dropdown) capture for item views.

The dropdown sibling of
:mod:`uitk.widgets.hotkey_capture_delegate`: instead of a *persistent*
``QComboBox`` cell widget — which paints over the cell, eats hover/select
events, and reads as a permanently-armed control — the cell stays a plain
item and a combo editor opens only on demand. Double-click (or
:meth:`QAbstractItemView.editItem`) opens a ``QComboBox`` seeded with a
fixed set of choices and commits the moment the user picks (or types, when
``editable``) — no persistent widget, no select-on-hover.

Reusable by any ``QTableWidget`` / ``QTableView`` column via
:func:`install_choice_capture`. Consumers receive the committed value
through the delegate's ``captured(row, col, value)`` signal and decide how
to persist it.

Two delegate flavours, matching the hotkey module:

* :class:`ChoiceCaptureDelegate` — default cell painting.
* :class:`BorderedChoiceCaptureDelegate` — also paints the row-spanning
  selection border from
  :class:`uitk.widgets.row_selection_delegate.RowSelectionBorderDelegate`,
  for tables that install that delegate elsewhere.
"""
from __future__ import annotations

from typing import Iterable, List

from qtpy import QtCore, QtWidgets

from uitk.widgets.row_selection_delegate import RowSelectionBorderDelegate


class ChoiceCaptureDelegate(QtWidgets.QStyledItemDelegate):
    """Item delegate that edits a cell via an in-cell dropdown.

    Emits ``captured(row, col, value)`` when the user commits a choice.
    The emit is deferred one event-loop tick so a slot may safely rebuild
    the view (e.g. ``setRowCount(0)``) without the editor being torn down
    mid-commit — identical to
    :class:`uitk.widgets.hotkey_capture_delegate.HotkeyCaptureDelegate`.

    Args:
        parent: Owning object (typically the view).
        choices: The fixed set of options offered in the dropdown.
        editable: When ``True`` (default) the user may also type a value
            not present in ``choices`` (the combo is editable).
    """

    captured = QtCore.Signal(int, int, str)

    def __init__(self, parent=None, *, choices: Iterable[str] = (), editable: bool = True):
        super().__init__(parent)
        self._choices: List[str] = [str(c) for c in choices]
        self._editable = bool(editable)

    def set_choices(self, choices: Iterable[str]) -> None:
        """Replace the dropdown's option list (applies to the next edit)."""
        self._choices = [str(c) for c in choices]

    def createEditor(self, parent, option, index):
        editor = QtWidgets.QComboBox(parent)
        editor.setEditable(self._editable)
        editor.addItems(self._choices)
        # A dropdown pick commits + closes immediately (the editingFinished /
        # focus-out path that Qt wires for typed text is left to the default
        # delegate machinery, so setModelData stays the single commit point).
        editor.activated.connect(lambda _i, e=editor: self._commit(e))
        return editor

    def _commit(self, editor):
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.NoHint)

    def setEditorData(self, editor, index):
        value = index.data() or ""
        # Honour a stored value that isn't one of the canonical choices
        # (e.g. a user-typed custom category) without dropping it.
        if value and editor.findText(value) < 0:
            editor.addItem(value)
        editor.setCurrentText(value)
        # NB: deliberately no auto-``showPopup`` here. Opening the list on the
        # same double-click that created the editor lets the click's trailing
        # mouse-release land in the freshly-opened popup — on a cell whose
        # value is already a list item that release re-selects the current row
        # and commits a no-op (the cell reads as "not editable"), while an
        # empty cell has nothing highlighted under the cursor and so opens
        # fine. Let the user open the dropdown with a deliberate click instead.

    def setModelData(self, editor, model, index):
        value = editor.currentText().strip()
        model.setData(index, value, QtCore.Qt.DisplayRole)
        # Defer one event-loop tick (2-arg singleShot — supported on every
        # Qt binding incl. Maya's bundled PySide6) so the emit lands at top
        # level: a capture slot may rebuild the view (setRowCount(0)) without
        # the editor being torn down mid-commit.
        row, col = index.row(), index.column()
        QtCore.QTimer.singleShot(0, lambda: self.captured.emit(row, col, value))


class BorderedChoiceCaptureDelegate(ChoiceCaptureDelegate, RowSelectionBorderDelegate):
    """:class:`ChoiceCaptureDelegate` that paints the row-spanning
    selection border.

    Use on tables that install
    :class:`~uitk.widgets.row_selection_delegate.RowSelectionBorderDelegate`
    as their general delegate, so the choice column keeps the same
    transparent-selection outline instead of the QSS blue fill. Edit
    behaviour resolves to :class:`ChoiceCaptureDelegate`; ``paint`` to
    :class:`RowSelectionBorderDelegate` (both share the single
    ``QStyledItemDelegate`` Qt base, so the MRO is unambiguous).
    """


def install_choice_capture(
    table: QtWidgets.QTableWidget,
    column: int,
    choices: Iterable[str],
    on_capture,
    *,
    editable: bool = True,
    bordered: bool = False,
) -> ChoiceCaptureDelegate:
    """Wire in-cell dropdown capture onto a table column.

    Installs the capture delegate on ``column`` and opens it on a
    double-click of that column — independent of the table's
    ``editTriggers``, so tables set to ``NoEditTriggers`` work too. The
    target cell's item must carry ``Qt.ItemIsEditable`` (the default for
    ``QTableWidgetItem``) for the editor to open. Programmatic opens via
    ``table.editItem(item)`` (e.g. a context-menu action) route through the
    same delegate and fire ``on_capture`` identically.

    Mirrors :func:`uitk.widgets.hotkey_capture_delegate.install_hotkey_capture`
    so a table can give its enum/category columns the same double-click-to-
    edit feel as its hotkey column, instead of a persistent combo cell widget.

    Recommended: set the table to ``NoEditTriggers``. The default triggers
    include ``AnyKeyPressed``/``EditKeyPressed``, so a stray keystroke on a
    selected editable cell would open the editor; the double-click wired
    here works regardless of triggers.

    Args:
        table: Target table (``QTableWidget`` or compatible view).
        column: Column index to make choice-editable.
        choices: The fixed set of dropdown options.
        on_capture: Callable ``(row, col, value) -> None`` invoked once a
            value is committed (``value`` is the chosen / typed string).
        editable: When ``True`` (default) the combo also accepts a typed
            value not present in ``choices``.
        bordered: Use :class:`BorderedChoiceCaptureDelegate` for tables that
            paint the row-spanning selection border elsewhere.

    Returns:
        The installed delegate (already connected to ``on_capture``).
    """
    delegate_cls = BorderedChoiceCaptureDelegate if bordered else ChoiceCaptureDelegate
    delegate = delegate_cls(table, choices=choices, editable=editable)
    delegate.captured.connect(on_capture)
    table.setItemDelegateForColumn(column, delegate)

    def _open(row, col):
        if col != column:
            return
        item = table.item(row, col)
        if item is not None and (item.flags() & QtCore.Qt.ItemIsEditable):
            table.editItem(item)

    table.cellDoubleClicked.connect(_open)
    return delegate
