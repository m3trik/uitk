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

A per-bridge ``parameters.py`` declares its ``PARAMS`` and binds them once
through :class:`ParamRegistry` (``class Parameters(ParamRegistry): PARAMS =
PARAMS``), so the slot machinery calls ``params_module.referenced_keys(text)``
and an engine ``Parameters.defaults()`` without ever passing the dict.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional, Set, Tuple

import pythontk as ptk
from uitk.bridge.spec import AttributeSpec, KindFactory
from uitk.bridge.formatters import Formatters


class _ParametersInternal(object):
    """Internal state/helpers for :class:`Parameters`."""

    _PLACEHOLDER_RE = re.compile(r"__([A-Z][A-Z0-9_]*)__")


class Parameters(_ParametersInternal):
    """Registry helpers operating over a ``{key: AttributeSpec}`` PARAMS dict."""

    @staticmethod
    def scope_spec(
        default: str = ptk.HandoffScope.SELECTED, section: str = "Export"
    ) -> AttributeSpec:
        """The shared **Scope** parameter every hand-off bridge exposes.

        Which objects a send acts on is a property of hand-off bridges in
        general, not of any one target app, so the spec lives here rather than
        being copy-pasted into each ``parameters.py``: one label set, one
        choice vocabulary, one tooltip across every bridge and both DCCs.
        The words and their precedence are :class:`pythontk.HandoffScope`'s;
        only the scene *reads* are DCC-specific -- each package's bridge-slots
        base hands its own (``cmds.ls`` vs ``bpy``) to that one resolver.

        Returns a FRESH spec per call: the dataclass is frozen, but its
        ``choices`` list is not — a single shared instance handed to a dozen
        registries would let one bridge's in-place choice refill leak into
        all the others.
        """
        labels = {
            ptk.HandoffScope.SELECTED: "Selected",
            ptk.HandoffScope.ALL: "Entire Scene",
            ptk.HandoffScope.VISIBLE: "Visible Only",
        }
        return AttributeSpec(
            key=ptk.HandoffScope.PARAM,
            label="Scope",
            kind="choice",
            default=default,
            choices=[(labels[word], word) for word in ptk.HandoffScope.WORDS],
            section=section,
            tooltip=(
                "Which objects to export:\n"
                "• Selected — the current selection.\n"
                "• Entire Scene — every mesh in the scene.\n"
                "• Visible Only — every currently-visible mesh."
            ),
        )

    @staticmethod
    @ptk.Deprecation.symbol(
        "an AttributeSpec in the host bridge's own parameters "
        "(blendertk.env_utils.maya_bridge.parameters.PARAMS['SHADER_TYPE'])",
        remove_in="1.7.0",
        since="2026-09-26",
        reason="Its values are Maya's shader vocabulary; uitk carries no host's.",
    )
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

        Returns a FRESH spec per call: the dataclass is frozen, but its
        ``choices`` list is not — a single shared instance handed to several
        registries would let one bridge's in-place choice refill leak into
        the others.
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
    def carrier_spec(default: str = "fbx", section: str = "") -> AttributeSpec:
        """The shared **Format** parameter: which interchange carrier the payload
        leaves as (FBX or USD).

        What format a hand-off is written in is a property of hand-off bridges
        in general, not of any one target app, so the spec lives here -- one
        label, one vocabulary, one tooltip across every bridge and both DCCs.
        The vocabulary is pythontk's :data:`~pythontk.core_utils.handoff.app_handoff.CARRIER_EXTENSIONS`
        verbatim: the engine refuses any other spelling before it exports, so
        the panel offers exactly what the engine accepts. A bridge whose target
        reads only FBX simply does not register the spec (its engine declares
        ``carriers = ("fbx",)``) -- the panel shows no choice rather than a
        choice the send would refuse.

        Default ``fbx``: the shipped route on every bridge. USD is the opt-in
        parallel -- materials travel natively as UsdPreviewSurface and the
        scene graph arrives typed, but the format has no equivalent of Maya's
        shared-shape / Blender's linked-duplicate instancing, so a structural
        hand-off refuses an instanced selection on it rather than silently
        flattening the scene (the regression that reverted a USD default
        once). Order is append-only: combos persist by INDEX.

        Like :meth:`shader_type_spec`, *section* defaults to EMPTY so the spec
        can drop into an unsectioned registry without re-labelling its
        neighbours. Returns a FRESH spec per call (the ``choices`` list is
        mutable).
        """
        import pythontk as ptk

        return AttributeSpec(
            key=ptk.CARRIER_PARAM,
            label="Format",
            kind="choice",
            default=default,
            choices=[
                ("FBX", "fbx"),
                ("USD", "usd"),
            ],
            section=section,
            tooltip=(
                "Which interchange format the selection leaves as:\n"
                "• FBX — the shipped default; carries instancing natively.\n"
                "• USD — opt-in. Materials travel as UsdPreviewSurface (no\n"
                "  texture-manifest rebuild needed), groups/locators arrive as\n"
                "  typed Xform prims. Instanced / linked-duplicate selections\n"
                "  are REFUSED on a scene hand-off rather than flattened —\n"
                "  send those via FBX."
            ),
        )

    @staticmethod
    def rig_mode_spec(default: str = "auto", section: str = "") -> AttributeSpec:
        """The shared **Rig** parameter: how a hand-off treats the rig logic that
        drives what it carries -- constraints, IK, drivers, expressions, which
        neither carrier has a form for.

        A property of hand-off bridges in general, like the carrier, so the spec
        lives here: one label, one vocabulary, one tooltip across every bridge
        and both DCCs. The vocabulary is pythontk's
        :data:`~pythontk.core_utils.handoff.app_handoff.RIG_MODES` verbatim, and the
        engine is what enforces it. Order is append-only: combos persist by
        INDEX, and ``auto`` leads because it is what an undecided request gets.

        Like :meth:`carrier_spec`, *section* defaults to EMPTY so the spec can
        drop into an unsectioned registry, and a FRESH spec is returned per
        call (the ``choices`` list is mutable).
        """
        import pythontk as ptk

        labels = {
            "auto": "Auto",
            "bake": "Bake to keys",
            "rig": "Transfer rig",
            "raw": "Raw",
        }
        return AttributeSpec(
            key=ptk.RIG_MODE_PARAM,
            label="Rig",
            kind="choice",
            default=default,
            choices=[(labels.get(mode, mode), mode) for mode in ptk.RIG_MODES],
            section=section,
            tooltip=(
                "How the rig logic driving the selection travels. "
                "Auto: bake driven animation to keys only when the scene has some (constraints, IK, driven keys), else import raw. "
                "Bake to keys: always bake every driven channel. "
                "Transfer rig: rebuild each rig (a control chain down to what it deforms) as editable relationships when the target can build and verify ALL of it; a rig it cannot complete is baked exactly as Bake would, and the log names the link that stopped it. "
                "Raw: touch nothing; driven animation is lost. "
                "Whenever a rig is baked, its apparatus is left out of the import -- constraint nodes, IK handles, control curves, up-vector locators, the groups holding only those, and joints nothing is skinned to -- because the motion now lives on what renders; the log counts what was dropped, and nothing renderable is ever touched. Raw keeps it, along with everything else."
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
    def affix_parts(value: Any, *, default: str = "prefix"):
        """``(prefix, suffix)`` for a collected ``affix``-kind parameter value.

        Re-exported here (it delegates to :meth:`KindFactory.affix_parts`) so a
        bridge engine reads an affix param through the same ``parameters``
        module it reads everything else through, instead of importing the
        widget factory into a headless code path.
        """
        return KindFactory.affix_parts(value, default=default)

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
            if spec is None:
                out[key] = str(val)
                continue
            # A composite kind (``affix``) collapses to its scalar stand-in
            # first, so a token never renders as a dict repr; scalars are
            # returned unchanged by ``to_literal``.
            out[key] = formatter(spec, KindFactory.to_literal(spec, val))
        return out


class ParamRegistry(object):
    """A bridge's parameter registry, declared as data: subclass it, set :attr:`PARAMS`.

    What every bridge's ``parameters.py`` used to hand-write -- the
    ``referenced_keys`` / ``defaults`` / ``render_context`` wrappers binding the
    :class:`Parameters` helpers to its own dict -- is inherited instead::

        class Parameters(ParamRegistry):
            PARAMS = PARAMS
            FORMATTER = Formatters.lua_literal  # optional: python_literal by default
            SUPERSESSIONS = SUPERSESSIONS  # optional

    The subclass IS what :class:`~uitk.bridge.slots.BridgeSlotsBase` expects as
    its ``params_module`` (``PARAMS`` / ``referenced_keys`` / ``SUPERSESSIONS``)
    and the namespace a headless engine calls (``Parameters.defaults()``,
    ``Parameters.render_context(values)``). A registry whose rule differs
    overrides the method (an include-expanding ``referenced_keys``, a run-mode
    relevance, a derived token) and reaches the default through ``super()``.
    Called on the class: it holds no state.
    """

    #: ``{key: AttributeSpec}``; display order = iteration order.
    PARAMS: Dict[str, AttributeSpec] = {}

    #: Renders one registered value for substitution: a :class:`Formatters`
    #: staticmethod, ``(spec, value) -> str``.
    FORMATTER: Callable[[AttributeSpec, Any], str] = staticmethod(
        Formatters.python_literal
    )

    #: ``(trigger, governed keys, reason)`` triples the panel greys rows by, or
    #: ``None`` to leave them to the panel's own ``PARAM_SUPERSESSIONS``.
    SUPERSESSIONS: Optional[Tuple[Tuple[str, Tuple[str, ...], str], ...]] = None

    @classmethod
    def referenced_keys(cls, script_text: str) -> Set[str]:
        """Registered keys whose ``__KEY__`` token appears in *script_text*.

        Parameters:
            script_text: A template body (pre-substitution).

        Returns:
            (set) The keys of :attr:`PARAMS` it references.
        """
        return Parameters.referenced_keys(script_text, cls.PARAMS)

    @classmethod
    def defaults(cls) -> Dict[str, Any]:
        """``{key: default}`` for every registered parameter."""
        return Parameters.defaults(cls.PARAMS)

    @classmethod
    def render_context(
        cls,
        values: Dict[str, Any],
        formatter: Optional[Callable[[AttributeSpec, Any], str]] = None,
    ) -> Dict[str, str]:
        """Format *values* for ``StrUtils.replace_delimited``.

        Parameters:
            values: ``{key: value}``; unregistered keys fall through to ``str()``.
            formatter: A one-off renderer in place of :attr:`FORMATTER` (a
                second target language for the same values).

        Returns:
            (dict) ``{key: literal text}``.
        """
        return Parameters.render_context(
            values, cls.PARAMS, formatter=formatter or cls.FORMATTER
        )

    @staticmethod
    def affix_parts(value: Any, *, default: str = "prefix") -> Tuple[str, str]:
        """``(prefix, suffix)`` for an ``affix``-kind value (:meth:`Parameters.affix_parts`)."""
        return Parameters.affix_parts(value, default=default)
