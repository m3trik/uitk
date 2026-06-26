# !/usr/bin/python
# coding=utf-8
"""In-cell key-combination capture for item views.

Drop-in replacement for "double-click a row → modal dialog → type a
chord → OK" flows: the cell itself becomes the capture surface. Double-
click (or :meth:`QAbstractItemView.editItem`) opens a read-only editor
that interprets the next key chord as a shortcut, commits it, and closes
immediately — no dialog, no OK button.

Reusable by any ``QTableWidget`` / ``QTableView`` column via
:func:`install_hotkey_capture`. Consumers receive the captured sequence
through the delegate's ``captured(row, col, sequence)`` signal and decide
how to persist it (uitk shortcut registry, Maya hotkey set, etc.).

Two delegate flavours:

* :class:`HotkeyCaptureDelegate` — default cell painting.
* :class:`BorderedHotkeyCaptureDelegate` — also paints the row-spanning
  selection border from
  :class:`uitk.widgets.row_selection_delegate.RowSelectionBorderDelegate`,
  for tables that install that delegate elsewhere (so the captured column
  doesn't fall back to the QSS blue selection fill and break the outline).
"""
from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from uitk.widgets.row_selection_delegate import RowSelectionBorderDelegate
from uitk.widgets.mixins.convert import ConvertMixin


class HotkeyCaptureEdit(QtWidgets.QLineEdit):
    """Read-only line edit that captures a single key chord.

    Every key press is interpreted as a shortcut rather than literal
    text. A lone modifier (Ctrl/Shift/Alt/Meta) is ignored until paired
    with a real key; Backspace/Delete clears the binding. The moment a
    chord (or a clear) registers, :data:`chordCaptured` fires so the
    delegate can commit and close.
    """

    chordCaptured = QtCore.Signal()

    _MODIFIER_KEYS = (
        QtCore.Qt.Key_Control,
        QtCore.Qt.Key_Shift,
        QtCore.Qt.Key_Alt,
        QtCore.Qt.Key_Meta,
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setPlaceholderText("Press keys… (Backspace clears, Esc cancels)")
        self._sequence = None  # None until captured; Esc leaves it None

    def sequence(self):
        """Captured sequence string, ``""`` for cleared, or ``None``."""
        return self._sequence

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        if key in self._MODIFIER_KEYS:
            event.accept()
            return  # wait for the non-modifier key

        event.accept()
        if key in (QtCore.Qt.Key_Backspace, QtCore.Qt.Key_Delete):
            self._sequence = ""
            self.setText("")
        else:
            # ``key`` and ``modifiers`` may be Qt enum members; OR-ing a
            # plain int with a Qt.KeyboardModifier routes through a
            # deprecated PySide6 __ror__ that builds a QKeyCombination with
            # swapped arg types and raises. Coerce both to plain ints (via
            # the canonical ConvertMixin.to_int, which handles enum/flag and
            # int across PySide2/6) so the OR yields an int QKeySequence accepts.
            combo = ConvertMixin.to_int(key) | ConvertMixin.to_int(modifiers)
            seq = QtGui.QKeySequence(combo)
            self._sequence = seq.toString(QtGui.QKeySequence.NativeText)
            self.setText(self._sequence)
        self.chordCaptured.emit()


class HotkeyCaptureDelegate(QtWidgets.QStyledItemDelegate):
    """Item delegate that edits a cell via in-cell key capture.

    Emits ``captured(row, col, sequence)`` when the user commits a chord.
    The emit is deferred one event-loop tick so a slot may safely rebuild
    the view (e.g. ``setRowCount(0)``) without the editor being torn down
    mid-commit.
    """

    captured = QtCore.Signal(int, int, str)

    def createEditor(self, parent, option, index):
        editor = HotkeyCaptureEdit(parent)
        editor.chordCaptured.connect(lambda e=editor: self._commit(e))
        return editor

    def _commit(self, editor):
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.NoHint)

    def setEditorData(self, editor, index):
        editor.setText(index.data() or "")

    def setModelData(self, editor, model, index):
        seq = editor.sequence()
        if seq is None:  # closed without capturing (Esc / focus loss)
            return
        # Defer one event-loop tick (2-arg singleShot — supported on every
        # Qt binding incl. Maya's bundled PySide6) so the emit lands at top
        # level: an on_capture slot may rebuild the view (setRowCount(0))
        # without the editor being torn down mid-commit.
        row, col = index.row(), index.column()
        QtCore.QTimer.singleShot(0, lambda: self.captured.emit(row, col, seq))


class BorderedHotkeyCaptureDelegate(HotkeyCaptureDelegate, RowSelectionBorderDelegate):
    """:class:`HotkeyCaptureDelegate` that paints the row-spanning
    selection border.

    Use on tables that install
    :class:`~uitk.widgets.row_selection_delegate.RowSelectionBorderDelegate`
    as their general delegate, so the captured column keeps the same
    transparent-selection outline instead of the QSS blue fill. Capture
    behaviour resolves to :class:`HotkeyCaptureDelegate`; ``paint`` to
    :class:`RowSelectionBorderDelegate` (both share the single
    ``QStyledItemDelegate`` Qt base, so the MRO is unambiguous).
    """


def install_hotkey_capture(
    table: QtWidgets.QTableWidget,
    column: int,
    on_capture,
    *,
    bordered: bool = False,
) -> HotkeyCaptureDelegate:
    """Wire in-cell hotkey capture onto a table column.

    Installs the capture delegate on ``column`` and opens it on a
    double-click of that column — independent of the table's
    ``editTriggers``, so tables set to ``NoEditTriggers`` work too. The
    target cell's item must carry ``Qt.ItemIsEditable`` (the default for
    ``QTableWidgetItem``) for the editor to open. Programmatic opens via
    ``table.editItem(item)`` (e.g. a context-menu "Assign…" action) route
    through the same delegate and fire ``on_capture`` identically.

    Recommended: set the table to ``NoEditTriggers``. The default triggers
    include ``AnyKeyPressed``/``EditKeyPressed``, so a stray keystroke on a
    selected editable cell would open the editor and silently rebind; the
    double-click wired here works regardless of triggers.

    Args:
        table: Target table (``QTableWidget`` or compatible view).
        column: Column index to make capture-editable.
        on_capture: Callable ``(row, col, sequence) -> None`` invoked once
            a chord is committed. ``sequence`` is a NativeText shortcut
            string, ``""`` when cleared.
        bordered: Use :class:`BorderedHotkeyCaptureDelegate` for tables
            that paint the row-spanning selection border elsewhere.

    Returns:
        The installed delegate (already connected to ``on_capture``).
    """
    delegate_cls = BorderedHotkeyCaptureDelegate if bordered else HotkeyCaptureDelegate
    delegate = delegate_cls(table)
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
