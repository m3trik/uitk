# coding=utf-8
"""Item-view delegates — reusable ``QStyledItemDelegate`` subclasses.

:class:`~uitk.widgets.delegates.row_selection.RowSelectionBorderDelegate` is
the base (row-spanning selection border for views with colour-coded cells);
the in-cell capture delegates build on it:

* :mod:`uitk.widgets.delegates.shortcut_capture` — double-click a cell to
  capture a key chord.
* :mod:`uitk.widgets.delegates.choice_capture` — double-click a cell to pick
  from a dropdown.

Public API lives in the root ``uitk`` package via ``DEFAULT_INCLUDE``.
"""
