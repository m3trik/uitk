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
"""

from uitk.bridge.spec import (  # noqa: F401 -- re-export surface
    AttributeSpec,
    KindHandler,
    KindFactory,
)
from uitk.bridge.formatters import Formatters  # noqa: F401 -- re-export surface
from uitk.bridge.parameters import Parameters  # noqa: F401 -- re-export surface
from uitk.bridge.tooltip import Tooltip  # noqa: F401 -- re-export surface
from uitk.bridge.slots import BridgeSlotsBase  # noqa: F401 -- re-export surface


# Friendlier alias for bridge consumers -- the dataclass IS the bridge
# parameter spec; the older "BridgeParam" name is kept so existing call
# sites don't have to rename if they don't want to.
BridgeParam = AttributeSpec
