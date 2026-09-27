# coding=utf-8
"""Popup kit: the mechanics every uitk popup surface shares.

A popup here is any widget that leaves its parent's layout to float on its own
-- a ``Menu``, an ``ExpandableList`` flyout, an option-box value popup -- and
the same three questions come up for each of them:

* :mod:`~uitk.widgets.popup.placement` -- :class:`PopupPlacement`: which screen
  a top-level surface belongs to, and the clamp that keeps it fully on that
  screen (also used by ``MainWindow``).
* :mod:`~uitk.widgets.popup.window` -- :class:`PopupWindow`: promoting a plain
  child widget to a frameless top-level popup window in one native-handle
  recreation.
* :mod:`~uitk.widgets.popup.dismissal` -- :class:`AncestorDismissal` (the
  anchor's window moved or an ancestor hid) and :class:`OutsideClickDismissal`
  (a press outside the popup, or Escape).

Each widget used to carry its own copy of these; the kit is the one owner. The
modules are imported by path inside uitk; nothing here is registered at the
package root.
"""
