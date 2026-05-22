# !/usr/bin/python
# coding=utf-8
"""Switchboard package — dynamic UI loader and event handler.

The Switchboard class composes partials co-located in this package as
``slots.py``, ``shortcuts.py``, ``widgets.py``, ``utils.py``,
``names.py``, ``editors.py``, ``style.py``. They are implementation
pieces, not standalone mixins to be reused outside this package — the
enclosing ``switchboard`` subpackage is the encapsulation boundary.

Public surface (resolved lazily via PEP 562 ``__getattr__`` so that e.g.
``from uitk.switchboard import Signals`` does not pull in the
Switchboard class and all its dependencies):

    Switchboard   — main class
    Signals       — slot signal-binding decorator
    SlotWrapper   — slot invocation wrapper
    Shortcut      — slot keyboard-shortcut decorator
    Cancelable    — slot decorator enabling Esc-cancel + warning dialog
"""

__all__ = ["Switchboard", "Signals", "SlotWrapper", "Shortcut", "Cancelable"]

# Map public symbol -> (submodule suffix, attribute name). Resolved on
# first attribute access; the imported submodule is the only thing
# loaded — _core (and the rest of the composition) stays unimported
# until something actually needs Switchboard itself.
_LAZY = {
    "Switchboard": ("_core", "Switchboard"),
    "Signals": ("slots", "Signals"),
    "SlotWrapper": ("slots", "SlotWrapper"),
    "Shortcut": ("shortcuts", "Shortcut"),
    "Cancelable": ("slots", "Cancelable"),
}


def __getattr__(name):
    try:
        module_suffix, attr = _LAZY[name]
    except KeyError as exc:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
    import importlib

    module = importlib.import_module(f"{__name__}.{module_suffix}")
    value = getattr(module, attr)
    globals()[name] = value  # cache for subsequent accesses
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
