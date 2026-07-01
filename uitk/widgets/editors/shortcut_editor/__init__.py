# !/usr/bin/python
# coding=utf-8
"""Shortcut editor windows.

One unified editor serves every shortcut backend:

* :mod:`~uitk.widgets.editors.shortcut_editor.registry_editor` —
  :class:`ShortcutEditor`, the preset-aware, collision-checking editor for the
  Switchboard global shortcut **registry** (``sb.get_shortcut_registry``,
  UI-less commands, scopes). Reached via ``sb.editors.show("shortcut")``.

* :mod:`~uitk.widgets.editors.shortcut_editor.manager_facade` —
  :class:`ManagerSwitchboardFacade` lets that same editor render a standalone
  :class:`~uitk.widgets.mixins.shortcuts.ShortcutManager` (e.g. the sequencer's
  bindings). Reached via ``ShortcutManager.show_editor()``.

The bespoke ``ShortcutEditorDialog`` was retired in favour of this single
editor as part of the binding-registry-unification work.
"""
from uitk.widgets.editors.shortcut_editor.registry_editor import (
    ShortcutEditor,
    CollisionConflict,
)
from uitk.widgets.editors.shortcut_editor.manager_facade import ManagerSwitchboardFacade

__all__ = [
    "ShortcutEditor",
    "CollisionConflict",
    "ManagerSwitchboardFacade",
]
