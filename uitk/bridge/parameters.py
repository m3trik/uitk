# !/usr/bin/python
# coding=utf-8
"""Registry helpers for bridge parameter dicts.

A "PARAMS" dict is a per-bridge constant of the form::

    PARAMS = {
        "BAKE_SIZE": AttributeSpec(key="BAKE_SIZE", kind="choice", default=4096, ...),
        ...
    }

The :class:`Parameters` staticmethods here operate over such a dict:
scan a script body for which placeholders it references, return the
registry defaults, format values for substitution via a target
formatter from :class:`uitk.bridge.formatters.Formatters`.

Each per-bridge ``parameters.py`` wraps these once with its own
``PARAMS`` + chosen formatter, so the slot machinery calls
``params_module.referenced_keys(text)`` without ever passing the dict
explicitly.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Set

from uitk.bridge.spec import AttributeSpec
from uitk.bridge.formatters import Formatters


class _ParametersInternal(object):
    """Internal state/helpers for :class:`Parameters`."""

    _PLACEHOLDER_RE = re.compile(r"__([A-Z][A-Z0-9_]*)__")


class Parameters(_ParametersInternal):
    """Registry helpers operating over a ``{key: AttributeSpec}`` PARAMS dict."""

    @staticmethod
    def referenced_keys(script_text: str, params: Dict[str, AttributeSpec]) -> Set[str]:
        """Return registry keys whose ``__KEY__`` token appears in *script_text*.

        Tokens that don't match a registry entry are silently ignored --
        substitution leaves them intact, and the target app surfaces the
        error if it actually mattered. The slot uses this to decide which
        parameter rows to show for a given template.
        """
        found = set(_ParametersInternal._PLACEHOLDER_RE.findall(script_text))
        return found & params.keys()

    @staticmethod
    def defaults(params: Dict[str, AttributeSpec]) -> Dict[str, Any]:
        """Return ``{key: default}`` for every registered parameter."""
        return {key: spec.default for key, spec in params.items()}

    @staticmethod
    def render_context(
        values: Dict[str, Any],
        params: Dict[str, AttributeSpec],
        formatter: Callable[[AttributeSpec, Any], str] = Formatters.python_literal,
    ) -> Dict[str, str]:
        """Format *values* through *formatter* for ``StrUtils.replace_delimited``.

        Unknown keys (internal tokens like ``FBX_PATH`` that the bridge
        injects directly) fall through to ``str(value)``. Registered keys
        go through the formatter so floats keep their precision, booleans
        pick up the right ``True``/``true``/``false`` casing, and strings
        get the right quoting for the target language.
        """
        out: Dict[str, str] = {}
        for key, val in values.items():
            spec = params.get(key)
            out[key] = formatter(spec, val) if spec else str(val)
        return out
