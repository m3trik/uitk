# coding=utf-8
"""The collaborators :class:`~uitk.widgets.menu.Menu` is built from.

``Menu`` stays defined in ``uitk/widgets/menu.py`` -- ``.ui`` headers and every
consumer name that path, so it is frozen -- and holds one of each of these,
every one owning its own state and holding the menu:

* ``_layout`` -- ``_MenuFrame``: layouts, central widget, header / footer, size.
* ``_items`` -- ``_MenuItems``: adding, finding and removing items; the
  empty-state placeholder; the shortcut-bound item filter.
* ``_triggers`` -- ``_MenuTrigger``: the anchor's trigger hook and
  ``hide_on_trigger``.
* ``_leave`` -- ``_MenuLeave``: ``hide_on_leave`` and the transient popup family.
* ``_popup_window`` -- ``_MenuPopupWindow``: window type, native input grab,
  screen clamp.
* ``_actions`` -- ``_MenuActions``: the Menu Actions section (Apply, Restore
  Defaults, presets) over :class:`ActionButtonManager`.
* ``_persistent_mode`` -- ``_MenuPersistentMode``: keep-open mode with a header
  Hide button.
* ``_registration`` -- ``_MenuRegistration``: deferred item registration with
  the owning window.

Internal: nothing here is registered at the package root; import ``Menu``.
"""
