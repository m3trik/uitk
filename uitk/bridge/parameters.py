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
    def scope_spec(
        default: str = "selected", section: str = "Export"
    ) -> AttributeSpec:
        """The shared **Scope** parameter every hand-off bridge exposes.

        Which objects a send acts on is a property of hand-off bridges in
        general, not of any one target app, so the spec lives here rather than
        being copy-pasted into each ``parameters.py``: one label set, one
        choice vocabulary, one tooltip across every bridge and both DCCs.
        Only the *resolution* is DCC-specific -- each package's bridge-slots
        base turns the chosen value into real objects (``cmds.ls`` vs ``bpy``).

        Returns a FRESH spec per call: ``AttributeSpec`` is a mutable
        dataclass, and a single shared instance handed to a dozen registries
        would let one bridge's tweak leak into all the others.
        """
        return AttributeSpec(
            key="SCOPE",
            label="Scope",
            kind="choice",
            default=default,
            choices=[
                ("Selected", "selected"),
                ("Entire Scene", "all"),
                ("Visible Only", "visible"),
            ],
            section=section,
            tooltip=(
                "Which objects to export:\n"
                "• Selected — the current selection.\n"
                "• Entire Scene — every mesh in the scene.\n"
                "• Visible Only — every currently-visible mesh."
            ),
        )

    @staticmethod
    def shader_type_spec(default: str = "stingray", section: str = "") -> AttributeSpec:
        """The shared **Rebuild Shader** parameter a material-rebuilding bridge exposes.

        Which shader a hand-off rebuilds materials as is a property of the
        rebuild, not of the direction it travels or which app launched it: a
        Blender->Maya *send* and a Maya-side *pull of a .blend* run the very
        same rebuild. The spec lives here so every panel that grows this control
        gets one label set, one choice vocabulary and one tooltip rather than a
        copy that drifts. The values are the shader engine's own
        (``mayatk.GameShader``), so no second spelling exists to keep in step.

        Panel-side there is one consumer today (blendertk's Maya-bridge send);
        the pull direction takes the same choice as an ``import_scene``
        keyword, defaulted to match, because it has no parameter panel at all.

        Unlike :meth:`scope_spec`, *section* defaults to EMPTY (no divider): a
        titled separator claims every following spec until the next section, so
        one sectioned param dropped into an otherwise unsectioned registry
        re-labels its neighbours rather than grouping itself. Pass a section
        only where the whole registry is organised into contiguous ones.

        Default ``stingray``: Maya's game shader is the game-engine-bound
        target, and it is the only family that DECLARES its texture slots --
        which is what lets a material round-trip back out with its maps intact
        instead of being re-guessed from filenames.

        Returns a FRESH spec per call: ``AttributeSpec`` is a mutable dataclass,
        and a single shared instance handed to several registries would let one
        bridge's tweak leak into the others.
        """
        return AttributeSpec(
            key="SHADER_TYPE",
            label="Rebuild Shader",
            kind="choice",
            default=default,
            choices=[
                ("Stingray PBS", "stingray"),
                ("Standard Surface", "standard_surface"),
                ("OpenPBR Surface", "open_pbr"),
            ],
            section=section,
            tooltip=(
                "Which Maya shader the materials are rebuilt as:\n"
                "• Stingray PBS — the game shader; its declared texture slots\n"
                "  round-trip back out intact. Needs the shaderFX plugin.\n"
                "• Standard Surface — renders anywhere, no plugin needed.\n"
                "• OpenPBR Surface — the open PBR standard; needs a recent Maya 2025+.\n"
                "A type this Maya cannot build falls back to Standard Surface."
            ),
        )

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
