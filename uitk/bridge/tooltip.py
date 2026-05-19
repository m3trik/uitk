# !/usr/bin/python
# coding=utf-8
"""Rich-text tooltip + template-description helpers for bridge panels.

Both functions are pluggable hooks on :class:`BridgeSlotsBase`, so
subclasses can override them per-bridge if they need bespoke rendering
-- but the defaults here cover marmoset / substance / rizom and any
shape that follows the same registry conventions.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Optional, Tuple

from uitk.bridge.spec import AttributeSpec
from uitk.widgets.mixins.tooltip_mixin import fmt as _fmt_tooltip


# ---------------------------------------------------------------------------
# Per-parameter tooltips
# ---------------------------------------------------------------------------

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
    if spec.kind == "choice" and spec.choices:
        normalised: List[Tuple[str, object]] = []
        for entry in spec.choices:
            if isinstance(entry, tuple) and len(entry) == 2:
                normalised.append((str(entry[0]), entry[1]))
            else:
                normalised.append((str(entry), entry))
        bullets = [
            f"<b>{label}</b> — <code>{value!r}</code>"
            for label, value in normalised
        ]

    body = spec.tooltip.replace("\n", "<br>") if spec.tooltip else None

    return _fmt_tooltip(
        title=spec.display_label,
        body=body,
        rows=rows,
        bullets=bullets,
    )


# ---------------------------------------------------------------------------
# Per-template leading description
# ---------------------------------------------------------------------------

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
        return _python_module_docstring(template_path)
    if suffix == ".lua":
        return _lua_leading_comment_block(template_path)
    return None


def _python_module_docstring(template_path: Path) -> Optional[str]:
    try:
        tree = ast.parse(template_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    return ast.get_docstring(tree)


def _lua_leading_comment_block(template_path: Path) -> Optional[str]:
    """Return the contiguous ``--`` block at the top of *template_path*."""
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
        out.append(body)
    return "\n".join(out) if out else None
