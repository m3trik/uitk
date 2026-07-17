# !/usr/bin/python
# coding=utf-8
"""Shortcut editor windows.

One unified editor serves every shortcut backend:

* :mod:`~uitk.widgets.editors.shortcut_editor.registry_editor` —
  :class:`ShortcutEditor`, the preset-aware, collision-checking editor for the
  Switchboard global shortcut **registry** (``sb.get_shortcut_registry``,
  UI-less commands, scopes). Reached via ``sb.editors.show("shortcut")``.

* :mod:`~uitk.widgets.editors.shortcut_editor.registry_facade` —
  :class:`RegistrySwitchboardFacade`, the generic Switchboard-shaped adapter:
  any grouped binding store (plain callables) renders in that same editor —
  groups become the target combobox, with optional re-branding and a preset
  row over the provider's own store. Used by the mayatk/blendertk Macro
  Manager (``Macros.show_editor()``).

* :mod:`~uitk.widgets.editors.shortcut_editor.manager_facade` —
  :class:`ManagerSwitchboardFacade`, the facade's thinnest configuration: a
  standalone :class:`~uitk.widgets.mixins.shortcuts.ShortcutManager` (e.g. the
  sequencer's bindings). Reached via ``ShortcutManager.show_editor()``.

The bespoke ``ShortcutEditorDialog`` and the mayatk/blendertk
``macro_manager`` panels were retired in favour of this single editor as part
of the binding-registry-unification work.
"""
from uitk.widgets.editors.shortcut_editor.registry_editor import (
    ShortcutEditor,
    CollisionConflict,
)
from uitk.widgets.editors.shortcut_editor.registry_facade import (
    RegistrySwitchboardFacade,
)
from uitk.widgets.editors.shortcut_editor.manager_facade import ManagerSwitchboardFacade

__all__ = [
    "ShortcutEditor",
    "CollisionConflict",
    "RegistrySwitchboardFacade",
    "ManagerSwitchboardFacade",
]
