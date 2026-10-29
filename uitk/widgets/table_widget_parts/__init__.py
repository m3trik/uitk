# !/usr/bin/python
# coding=utf-8
"""The collaborators :class:`~uitk.widgets.tableWidget.TableWidget` is built from.

``TableWidget`` stays defined in ``uitk/widgets/tableWidget.py`` -- ``.ui``
headers and every consumer name that path, so it is frozen -- and holds one of
each of these (the same shape as ``widgets/menu_parts/`` for ``Menu``), every
one owning its own state and reaching the table's public methods through it:

* ``_cell_formats`` -- ``_CellFormats``: the formatters per cell, column and
  header, column display truncation, and each cell's pre-format colours.
* ``_gestures`` -- the mouse: ``_ScrubInput`` (middle-mouse and wheel scrub),
  ``_RowDrag`` (the left-button drag down a column and its drag-edit fill) and
  ``_CellClicks`` (click actions, click-to-edit, cell-widget forwarding), which
  ``TableWidget``'s event handlers ask in turn.
* ``_context_menu`` -- ``_ContextMenu``: the popup and the actions registered
  to receive the selection.

Internal: nothing here is registered at the package root; import ``TableWidget``.
"""
