"""Generic DCC-bridge / parameterised-form infrastructure.

This subpackage owns everything reusable for "kind-driven" parameter
panels -- panels whose widgets are built from a registry of
:class:`AttributeSpec` dataclasses keyed by a ``kind`` string
(``int / float / bool / str / choice / path / file_list / ...``).

Both the original ``uitk.widgets.attributeWindow`` and the DCC handoff
bridges (marmoset / substance / rizom in mayatk) consume this single
contract. New consumers register new kinds via
:meth:`KindFactory.register_kind`; new target languages for bridge
value-rendering register as small formatter staticmethods on
:class:`uitk.bridge.formatters.Formatters`.

Re-exports the class surface so callers can ``from uitk.bridge import
AttributeSpec, KindFactory, Formatters, Parameters, Tooltip,
BridgeSlotsBase``. This is class-only -- there are no flat function
re-exports; the former module-level helpers now live as staticmethods
on these classes (``KindFactory.make_widget``, ``Formatters.python_literal``,
``Parameters.referenced_keys``, ``Tooltip.format_param_tooltip``,
``BridgeSlotsBase.register_log_link_handler`` ...).

The re-exports resolve lazily (PEP 562 module ``__getattr__``, same shape
as :mod:`uitk.switchboard`). ``uitk/__init__.py`` bootstraps through
``pythontk``'s module resolver, whose ``pkgutil.walk_packages`` scan
imports every subpackage ``__init__`` -- so an eager
``from uitk.bridge.slots import BridgeSlotsBase`` here charged the whole
1500-line slots module (and the widget tree it pulls) to every plain
``import uitk`` in the ecosystem. Names and import forms are unchanged;
only the moment the implementation module loads is.
"""

__all__ = [
    "AttributeSpec",
    "BridgeParam",
    "BridgeSlotsBase",
    "Formatters",
    "KindFactory",
    "KindHandler",
    "Parameters",
    "Tooltip",
]

# Public name -> (submodule suffix, attribute) it lives on, grouped by
# submodule so this block stays a 1:1 reading of the old import list.
_LAZY = {
    name: (module_suffix, name)
    for module_suffix, names in {
        "spec": ("AttributeSpec", "KindHandler", "KindFactory"),
        "formatters": ("Formatters",),
        "parameters": ("Parameters",),
        "tooltip": ("Tooltip",),
        "slots": ("BridgeSlotsBase",),
    }.items()
    for name in names
}

# Friendlier alias for bridge consumers -- the dataclass IS the bridge
# parameter spec; the older "BridgeParam" name is kept so existing call
# sites don't have to rename if they don't want to.
_LAZY["BridgeParam"] = ("spec", "AttributeSpec")


def __getattr__(name):
    try:
        module_suffix, attr = _LAZY[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    import importlib

    module = importlib.import_module(f"{__name__}.{module_suffix}")
    value = getattr(module, attr)
    globals()[name] = value  # cache for subsequent accesses
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
