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
  standalone :class:`~uitk.managers.shortcut_manager.ShortcutManager` (e.g. the
  sequencer's bindings). Reached via ``ShortcutManager.show_editor()``.

The bespoke ``ShortcutEditorDialog`` and the mayatk/blendertk
``macro_manager`` panels were retired in favour of this single editor as part
of the binding-registry-unification work.

The re-exports resolve lazily (PEP 562 module ``__getattr__``, same shape as
:mod:`uitk.switchboard`). ``uitk/__init__.py`` bootstraps through ``pythontk``'s
module resolver, whose ``pkgutil.walk_packages`` scan imports every subpackage
``__init__`` -- so eager re-exports here charged the ~1900-line
``registry_editor`` (and its delegate/option-box dependencies) to every plain
``import uitk`` in the ecosystem. Names and import forms are unchanged; only the
moment the implementation module loads is.
"""

__all__ = [
    "ShortcutEditor",
    "CollisionConflict",
    "RegistrySwitchboardFacade",
    "ManagerSwitchboardFacade",
]

# Public name -> submodule it lives on, grouped by submodule so this block
# stays a 1:1 reading of the old import list.
_LAZY = {
    name: module_suffix
    for module_suffix, names in {
        "registry_editor": ("ShortcutEditor", "CollisionConflict"),
        "registry_facade": ("RegistrySwitchboardFacade",),
        "manager_facade": ("ManagerSwitchboardFacade",),
    }.items()
    for name in names
}


def __getattr__(name):
    try:
        module_suffix = _LAZY[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    import importlib

    module = importlib.import_module(f"{__name__}.{module_suffix}")
    value = getattr(module, name)
    globals()[name] = value  # cache for subsequent accesses
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
