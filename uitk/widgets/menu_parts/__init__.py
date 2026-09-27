# coding=utf-8
"""The concept parts :class:`~uitk.widgets.menu.Menu` is built from.

``Menu`` stays defined in ``uitk/widgets/menu.py`` -- ``.ui`` headers and every
consumer name that path, so it is frozen -- and inherits one mixin per concept
from here (the same shape as ``widgets/marking_menu/``'s parts):

* ``_layout`` -- the frame: layouts, central widget, header / footer, size.
* ``_items`` -- adding, finding and removing items; the empty-state placeholder;
  the shortcut-bound item filter.
* ``_triggers`` -- the anchor's trigger hook and ``hide_on_trigger``.
* ``_leave`` -- ``hide_on_leave`` and the transient popup family.
* ``_popup_window`` -- window type, native input grab, screen clamp.
* ``_actions`` -- the Menu Actions section (Apply, Restore Defaults, presets)
  and :class:`ActionButtonManager`.
* ``_persistent_mode`` -- keep-open mode with a header Hide button.
* ``_registration`` -- deferred item registration with the owning window.

Internal: nothing here is registered at the package root; import ``Menu``.
"""
