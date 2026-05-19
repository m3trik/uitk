# !/usr/bin/python
# coding=utf-8
"""Per-target-language value formatters for bridge parameter rendering.

Each function has the signature ``formatter(spec, value) -> str`` and
renders *value* as a literal in the target language. Callers feed one
of these into :func:`uitk.bridge.parameters.render_context` to produce
the substitution dict that gets passed to
:func:`pythontk.str_utils.StrUtils.replace_delimited`.

Decoupling formatters from the spec dataclass (instead of putting
``format_value`` on a per-bridge subclass) lets one ``AttributeSpec``
serve any number of target languages -- the bridge author just picks
a formatter at render time.
"""
from __future__ import annotations

import os
from typing import Any


def _strip_trailing_zeros(spec, value: float) -> str:
    """Float renderer used by every dialect -- honours ``spec.decimals``."""
    if spec.decimals:
        return f"{value:.{spec.decimals}f}".rstrip("0").rstrip(".") or "0"
    return repr(value)


def python_literal(spec, value: Any) -> str:
    """Render *value* as a Python source literal.

    Used by marmoset Toolbag templates (executed by ``-run``) and any
    other ``.py`` substitution target.
    """
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, float):
        return _strip_trailing_zeros(spec, value)
    return str(value)


def lua_literal(spec, value: Any) -> str:
    """Render *value* as a Lua source literal.

    Used by RizomUV ``.lua`` preset scripts. Lua uses lowercase ``true``
    / ``false`` (vs Python's capitalized). Strings are passed through
    bare on the assumption Rizom presets quote them where needed in
    the template body.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return _strip_trailing_zeros(spec, value)
    return str(value)


def js_literal(spec, value: Any) -> str:
    """Render *value* as a JavaScript literal.

    Used by Substance Painter RPC payloads. Strings become double-quoted
    JS literals with backslash + double-quote escaping.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, float):
        return _strip_trailing_zeros(spec, value)
    return str(value)


def cli_raw(spec, value: Any) -> str:
    """Render *value* as a raw command-line argv token (no quoting).

    Used by Substance Painter ``--mesh ...`` style flags. Lists/tuples
    (``file_list`` specs) are joined with the OS path separator -- but
    templates should not generally feed file_list into argv slots; the
    bridge stages those files separately and the manifest carries the
    final paths.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return os.pathsep.join(str(v) for v in value)
    if isinstance(value, float):
        return _strip_trailing_zeros(spec, value)
    return str(value)
