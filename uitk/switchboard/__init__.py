# !/usr/bin/python
# coding=utf-8
"""Switchboard package — dynamic UI loader and event handler.

The Switchboard class composes partials co-located in this package, one
concept each: ``slots.py``, ``shortcuts.py``, ``widgets.py`` (registration +
gating), ``widget_values.py`` (what a control's value means), ``rules.py``
(``enable_when`` / ``show_when`` / ``text_from`` / ``value_from``),
``control_groups.py`` (button groups, multi-toggles, linked spin boxes, ...),
``dialogs.py`` (dialogs, progress, busy cursor), ``placement.py``,
``event_loop.py``, ``names.py`` (names, tags, name patterns), ``editors.py``,
``style.py``, ``namespace.py``. They are implementation pieces, not standalone
mixins to be reused outside this package — the enclosing ``switchboard``
subpackage is the encapsulation boundary.

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
