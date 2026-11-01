# !/usr/bin/python
# coding=utf-8
"""Switchboard package — dynamic UI loader and event handler.

The Switchboard class (``_core.py``) is a facade: its public methods delegate
to private collaborators co-located in this package, one concept each and each
owning its own state: ``slots.py`` (``_Slots``), ``shortcuts.py``
(``_Shortcuts``), ``widgets.py`` (``_Widgets`` registration, ``_Gates``
gating), ``widget_values.py`` (``_WidgetValues``: what a control's value
means), ``rules.py`` (``_Rules``: ``enable_when`` / ``show_when`` /
``text_from`` / ``value_from``), ``control_groups.py`` (``_ControlGroups``:
button groups, multi-toggles, linked spin boxes, ...), ``dialogs.py``
(``_Dialogs``: dialogs, progress, busy cursor), ``placement.py``,
``event_loop.py``, ``names.py`` (``_Names``: names, tags, name patterns),
``editors.py`` (``_EditorRegistry``) and ``namespace.py``. They are
implementation pieces, never imported outside this package — the enclosing
``switchboard`` subpackage is the encapsulation boundary.

Public surface (resolved lazily via ``pythontk``'s ``lazy_exports`` so that e.g.
``from uitk.switchboard import Signals`` does not pull in the
Switchboard class and all its dependencies):

    Switchboard   — main class
    Signals       — slot signal-binding decorator
    SlotWrapper   — slot invocation wrapper
    Shortcut      — slot keyboard-shortcut decorator
    Cancelable    — slot decorator enabling Esc-cancel + warning dialog

Application override-cursor policy — the stack primitives, the busy scope
with its modal suspension, the drain, ``OverrideCursorGuard`` — lives in
``uitk.managers.cursor_manager`` and is published from the ``uitk`` root.
The slot dispatcher and the switchboard dialogs consume it; they do not own
it.
"""

from pythontk.core_utils.module_resolver import lazy_exports

# The imported submodule is the only thing loaded -- _core (and the rest of the
# composition) stays unimported until something actually needs Switchboard.
lazy_exports(
    globals(),
    {
        "_core": "Switchboard",
        "slots": ("Signals", "SlotWrapper", "Cancelable"),
        "shortcuts": "Shortcut",
    },
)
