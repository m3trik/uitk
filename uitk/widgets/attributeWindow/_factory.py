# !/usr/bin/python
# coding=utf-8
"""Back-compat shim -- factory moved to :mod:`uitk.bridge.spec`.

Existing imports of ``uitk.widgets.attributeWindow._factory`` (notably
:class:`AttributeWindow` itself) keep working: every public symbol is
re-exported below. New code should import from :mod:`uitk.bridge` --
the canonical location since the registry now powers both
AttributeWindow panels and the DCC handoff bridges.

Importing this module triggers the registration of the built-in kind
handlers (bool/int/float/str/choice/path/file_list) as a side effect
of importing :mod:`uitk.bridge.spec`.
"""
from uitk.bridge.spec import (  # noqa: F401 -- re-export surface
    AttributeSpec,
    ChoiceItem,
    ChoicesSeq,
    KindHandler,
    INT_MIN,
    INT_MAX,
    FLOAT_MIN,
    FLOAT_MAX,
    connect_changed,
    get_handler,
    infer_kind,
    make_widget,
    read_value,
    register_kind,
    set_value,
)
