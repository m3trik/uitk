"""Generic DCC-bridge / parameterised-form infrastructure.

This subpackage owns everything reusable for "kind-driven" parameter
panels -- panels whose widgets are built from a registry of
:class:`AttributeSpec` dataclasses keyed by a ``kind`` string
(``int / float / bool / str / choice / path / file_list / ...``).

Both ``uitk.widgets.attribute_window`` and the DCC handoff
bridges (marmoset / substance / rizom in mayatk) consume this single
contract. New consumers register new kinds via
:meth:`KindFactory.register_kind`; new target languages for bridge
value-rendering register as small formatter staticmethods on
:class:`uitk.bridge.formatters.Formatters`.

Re-exports the class surface so callers can ``from uitk.bridge import
AttributeSpec, KindFactory, Formatters, Parameters, ParamRegistry, Tooltip,
BridgeSlotsBase``. This is class-only -- there are no flat function
re-exports; the former module-level helpers now live as staticmethods
on these classes (``KindFactory.make_widget``, ``Formatters.python_literal``,
``Parameters.referenced_keys``, ``Tooltip.format_param_tooltip``,
``BridgeSlotsBase.register_log_link_handler`` ...).

The re-exports resolve lazily (``pythontk``'s ``lazy_exports``, the one
subpackage idiom -- CODE_STANDARD section 4). ``uitk/__init__.py`` bootstraps through
``pythontk``'s module resolver, whose ``pkgutil.walk_packages`` scan
imports every subpackage ``__init__`` -- so an eager
``from uitk.bridge.slots import BridgeSlotsBase`` here charged the whole
1500-line slots module (and the widget tree it pulls) to every plain
``import uitk`` in the ecosystem. Names and import forms are unchanged;
only the moment the implementation module loads is.
"""

from pythontk.core_utils.module_resolver import lazy_exports

lazy_exports(
    globals(),
    {
        # Qt-free: a registry is declared without a binding.
        "attribute_spec": "AttributeSpec",
        "spec": ("KindHandler", "KindFactory"),
        "formatters": "Formatters",
        "parameters": ("Parameters", "ParamRegistry"),
        "tooltip": "Tooltip",
        "slots": "BridgeSlotsBase",
    },
)
