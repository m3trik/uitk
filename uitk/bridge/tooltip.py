# !/usr/bin/python
# coding=utf-8
"""Rich-text tooltip + template-description helpers for bridge panels.

Both :class:`Tooltip` staticmethods are pluggable hooks on
:class:`BridgeSlotsBase`, so subclasses can override them per-bridge if
they need bespoke rendering -- but the defaults here cover marmoset /
substance / rizom and any shape that follows the same registry
conventions.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List, Optional, Tuple

from uitk.bridge.spec import AttributeSpec
from uitk.widgets.mixins.tooltip_mixin import TooltipFormat

# A substitution placeholder (``__SCOPE__``). Matched inside comment prose to
# tell a machine directive from a sentence -- see
# :meth:`_TooltipInternal._lua_leading_comment_block`.
_PLACEHOLDER_RE = re.compile(r"__[A-Z0-9_]+__")


class _TooltipInternal(object):
    """Internal helpers for :class:`Tooltip`."""

    @staticmethod
    def _python_module_docstring(template_path: Path) -> Optional[str]:
        try:
            tree = ast.parse(template_path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            return None
        return ast.get_docstring(tree)

    @staticmethod
    def _lua_leading_comment_block(template_path: Path) -> Optional[str]:
        """Return the leading ``--`` SUMMARY paragraph of *template_path*.

        The first paragraph only, not the whole comment block. These headers
        are read by two audiences at once: the artist picking a preset in the
        panel, and whoever maintains the Lua. Taking everything up to the
        first blank line handed the artist the maintainer's half as well --
        measured-behaviour notes, host-version constraints, why a token is
        spelled without its underscores -- so switching preset dumped a wall
        of text into the log panel where two lines were wanted (live report).

        The split point is an EMPTY ``--`` line, which is how these files
        already separate their paragraphs, so the rationale stays exactly
        where it is and simply stops being user-facing. Empty comment lines
        BEFORE any content are skipped rather than treated as the end, so a
        header that opens with a separator still yields its summary.

        Lines carrying a ``__TOKEN__`` placeholder are dropped wherever they
        appear: those are machine directives aimed at
        ``Parameters.referenced_keys`` -- the ``scope=__SCOPE__`` echo that
        makes the panel show its Scope row -- never prose.
        """
        try:
            text = template_path.read_text(encoding="utf-8")
        except OSError:
            return None
        out: List[str] = []
        for line in text.splitlines():
            stripped = line.lstrip()
            if not stripped:
                break  # blank line ends the leading block
            if not stripped.startswith("--"):
                break  # first non-comment ends the block
            body = stripped[2:]
            # Allow at most one separator space after ``--`` so callers control
            # indentation in the source without introducing leading whitespace.
            if body.startswith(" "):
                body = body[1:]
            if not body.strip():
                if out:
                    break  # paragraph break: the summary is complete
                continue  # leading separator: the summary hasn't started
            if _PLACEHOLDER_RE.search(body):
                continue  # machine directive, not prose
            out.append(body)
        return "\n".join(out) if out else None


class Tooltip(_TooltipInternal):
    """Rich-text tooltip + template-description builders for bridge panels."""

    # -----------------------------------------------------------------------
    # Per-parameter tooltips
    # -----------------------------------------------------------------------

    @staticmethod
    def format_param_tooltip(spec: AttributeSpec) -> str:
        """Build a rich-text tooltip for one :class:`AttributeSpec`.

        Renders title + body + (type / range / step / default) rows + (for
        choice specs) a bullet list of available options. The output is
        HTML produced by :func:`uitk.widgets.mixins.tooltip_mixin.fmt`, so
        Qt's tooltip engine renders it as styled rich text rather than a
        flat string.

        ``\\n`` characters in ``spec.tooltip`` are converted to ``<br>`` so
        multi-line registry strings render with their line breaks preserved
        -- the alternative ``<p>``-collapses-whitespace rule eats
        hand-wrapped registry text.
        """
        rows: List[Tuple[str, str]] = [("Type", spec.kind)]

        if spec.kind in ("int", "float"):
            lo = "—" if spec.minimum is None else str(spec.minimum)
            hi = "—" if spec.maximum is None else str(spec.maximum)
            if spec.minimum is not None or spec.maximum is not None:
                rows.append(("Range", f"{lo} – {hi}"))
            if spec.step is not None:
                rows.append(("Step", str(spec.step)))

        rows.append(("Default", repr(spec.default)))

        bullets = None
        if spec.kind in ("choice", "check_list") and spec.choices:
            normalised: List[Tuple[str, object]] = []
            for entry in spec.choices:
                # (label, value) / (label, value, tooltip) / bare value. A
                # runtime-populated spec has no static choices -- it renders
                # its entries as per-row tooltips instead.
                if isinstance(entry, tuple) and len(entry) in (2, 3):
                    normalised.append((str(entry[0]), entry[1]))
                else:
                    normalised.append((str(entry), entry))
            bullets = [
                f"<b>{label}</b> — <code>{value!r}</code>"
                for label, value in normalised
            ]

        body = spec.tooltip.replace("\n", "<br>") if spec.tooltip else None

        return TooltipFormat.fmt(
            title=spec.display_label,
            body=body,
            rows=rows,
            bullets=bullets,
        )

    # -----------------------------------------------------------------------
    # Per-template leading description
    # -----------------------------------------------------------------------

    @staticmethod
    def template_description(template_path: Path) -> Optional[str]:
        """Return *template_path*'s leading docstring / comment block, or *None*.

        Dispatches on the file extension so the same hook serves Python
        templates (marmoset / substance) and Lua scripts (rizom) without
        each bridge having to override anything:

        * ``.py`` -- :func:`ast.get_docstring` on the parsed module. Templates
          carry ``__KEY__`` substitution tokens that are valid Python NAMEs,
          so ``ast.parse`` succeeds before substitution.
        * ``.lua`` -- the contiguous leading ``--`` comment block, with the
          ``--`` markers stripped and lines joined by newline. Stops at the
          first blank line or non-comment line.
        * anything else -- *None* (silent no-op).
        """
        suffix = template_path.suffix.lower()
        if suffix == ".py":
            return _TooltipInternal._python_module_docstring(template_path)
        if suffix == ".lua":
            return _TooltipInternal._lua_leading_comment_block(template_path)
        return None
