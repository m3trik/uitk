# !/usr/bin/python
# coding=utf-8
"""Dynamic attribute editor — :class:`AttributeWindow` widget + spec-driven factory.

Public symbols are lazy-loaded via the root ``uitk`` package's
``DEFAULT_INCLUDE``. Import them from there::

    from uitk import (
        AttributeWindow,
        AttributeSpec, KindHandler,
        make_widget, read_value, set_value, connect_changed,
        infer_kind, register_kind, get_handler,
    )

Implementation lives in:

* :mod:`uitk.widgets.attributeWindow._attributeWindow` — the popup widget.
* :mod:`uitk.bridge.spec` — canonical home of the :class:`AttributeSpec`
  dataclass and the kind-handler registry shared with the DCC bridges.
  The sibling ``_factory.py`` is a back-compat shim that re-exports from
  :mod:`uitk.bridge.spec` for existing call sites.
"""
