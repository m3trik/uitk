"""Generic DCC-bridge / parameterised-form infrastructure.

This subpackage owns everything reusable for "kind-driven" parameter
panels -- panels whose widgets are built from a registry of
:class:`AttributeSpec` dataclasses keyed by a ``kind`` string
(``int / float / bool / str / choice / path / file_list / ...``).

Both the original ``uitk.widgets.attributeWindow`` and the DCC handoff
bridges (marmoset / substance / rizom in mayatk) consume this single
contract. New consumers register new kinds via :func:`register_kind`;
new target languages for bridge value-rendering register as small
formatter functions in :mod:`uitk.bridge.formatters`.

Re-exports the most-used names so callers can ``from uitk.bridge import
AttributeSpec, BridgeSlotsBase, ...`` without spelunking submodules.
"""
from uitk.bridge.spec import (
    AttributeSpec,
    KindHandler,
    register_kind,
    get_handler,
    infer_kind,
    make_widget,
    read_value,
    set_value,
    connect_changed,
)
from uitk.bridge.formatters import (
    python_literal,
    lua_literal,
    js_literal,
    cli_raw,
)
from uitk.bridge.parameters import (
    referenced_keys,
    defaults,
    render_context,
)
from uitk.bridge.tooltip import (
    format_param_tooltip,
    template_description,
)
from uitk.bridge.slots import BridgeSlotsBase


# Friendlier alias for bridge consumers -- the dataclass IS the bridge
# parameter spec; the older "BridgeParam" name is kept so existing call
# sites don't have to rename if they don't want to.
BridgeParam = AttributeSpec
