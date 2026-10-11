# !/usr/bin/python
# coding=utf-8
"""The Qt-free half of the parameter-panel contract: :class:`AttributeSpec`.

A spec DESCRIBES one editable attribute / bridge parameter -- key, label, kind,
default, range, choices, tooltip, section. Nothing here builds a widget, so a
registry (a bridge's ``PARAMS`` dict, a headless test, a pure-Python tool) can
declare its parameters without a Qt binding; :mod:`uitk.bridge.spec`'s
:class:`~uitk.bridge.spec.KindFactory` turns a spec into a widget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple, Union


ChoiceItem = Union[Any, Tuple[str, Any]]
ChoicesSeq = Sequence[ChoiceItem]


@dataclass(frozen=True)
class AttributeSpec:
    """Description of one editable attribute / bridge parameter.

    A single dataclass shape covers both AttributeWindow's auto-from-value
    panels and the DCC bridges' explicit registries. The bridges always
    set ``kind`` explicitly (``"int"``, ``"choice"``, ``"path"``,
    ``"file_list"``, ...); AttributeWindow leaves it at ``"auto"`` and
    resolves it from ``type(default)`` via :meth:`KindFactory.infer_kind`.

    Attributes:
        key: Identifier used as the widget's objectName. Required.
        label: Display label. Defaults to *key* if empty.
        kind: One of the registered kinds (``"bool" | "int" | "float" |
            "str" | "choice" | "check_list" | "path" | "file" | "files" |
            "file_list" | "action" | "affix"``) or ``"auto"`` to derive from
            ``type(default)``.
            Custom kinds added via :meth:`KindFactory.register_kind` are
            also accepted.
        default: Initial widget value.
        minimum / maximum / step: Numeric range and step (int/float kinds).
        decimals: Float precision (float kind only).
        choices: For the choice-driven kinds (``"choice"``, ``"check_list"``)
            -- a sequence of values (``["Low", "Medium"]``), of
            ``(label, value)`` pairs, or of ``(label, value, tooltip)``
            triples. The value is what :meth:`KindFactory.read_value` returns
            (``check_list`` returns the list of checked ones). Leave empty and
            call :meth:`KindFactory.set_choices` when the entries are only
            known at runtime. The ``"action"`` kind reads the same shape as
            ``(label, action_id, tooltip)`` and accepts a 4th element -- an
            icon name -- that turns the entry into an option-box icon button
            on the row's primary action rather than a second text button.
        tooltip: Tooltip text. The DCC-bridge slots feed this through
            :meth:`uitk.bridge.tooltip.Tooltip.format_param_tooltip` to build
            a rich-text version with type/range/default rows.
        section: Optional category label. A builder that groups specs (e.g.
            :class:`uitk.bridge.BridgeSlotsBase`) inserts a titled
            :class:`~uitk.widgets.separator.Separator` before the first spec of
            each new section, so related params read as a labelled block.
            Empty (default) = no divider. Sections are expected contiguous in
            iteration order.
        inline: Render this spec to the RIGHT of the preceding spec instead of
            on its own row -- for a compact modifier of the value beside it (an
            "Auto" toggle next to the number it overrides). The builder still
            keeps it a separately addressable row, so visibility and
            :meth:`~uitk.bridge.BridgeSlotsBase.set_param_enabled` work per key.
            It rides the host row's visibility, so an inline spec must be
            referenced by the same templates as the spec it follows. Ignored on
            the first spec of a registry (nothing to attach to) and on the first
            spec of a section (a section's opening row is its own).
        placeholder: Grey text shown while a text field is EMPTY, on the
            line-edit kinds (``"str"``, ``"path"``, ``"file"``, ``"files"``). For what
            happens if it is left that way -- an empty field that prompts on
            use, or one that falls back to a computed default -- which is
            unreadable from the row otherwise: the control looks unset and
            unexplained, and a tooltip only says so once the user suspects
            there is something to ask about. Never restate the label here.
            On an ``"int"`` field, which has no empty state, it is the text
            shown AT the minimum (Qt's special value text): for a minimum that
            means "unset" -- a bridge's "0 uses the preset's value" -- which a
            bare 0 would read as zero. The value read back is still the number.
        preset: False for a live switch rather than a setting -- a control
            that acts the moment it changes, such as a share toggle that opens
            a public link. A preset neither saves nor applies it, and Reset to
            Defaults leaves it as it is, so neither can act on the user's
            behalf.
    """

    key: str
    label: str = ""
    kind: str = "auto"
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: Optional[float] = None
    decimals: int = 0
    choices: Optional[ChoicesSeq] = None
    tooltip: str = ""
    section: str = ""
    inline: bool = False
    # Appended, not inserted beside `tooltip` where it reads best: this is a
    # published dataclass, so every field's POSITION is part of the contract
    # and a new one in the middle silently re-points a positional caller's
    # `section` at it.
    placeholder: str = ""
    preset: bool = True

    def __post_init__(self):
        # An empty key produces a widget with empty objectName that can't be
        # found via `getattr(ui, name)` -- silently breaks lookup downstream.
        if not self.key:
            raise ValueError("AttributeSpec.key must be a non-empty string.")

    @classmethod
    def from_value(cls, key: str, value: Any, *, label: str = "") -> "AttributeSpec":
        """Build a minimal spec from a Python value (AttributeWindow style)."""
        return cls(
            key=key,
            label=label or key,
            kind=cls.infer_kind(value),
            default=value,
        )

    @property
    def display_label(self) -> str:
        return self.label or self.key

    @staticmethod
    def infer_kind(value: Any) -> str:
        """Map a Python value to one of the built-in kinds.

        Order matters: ``bool`` is a subclass of ``int``, so check bool first.
        Lists / tuples deliberately fall through to ``"str"`` -- the
        ``file_list`` kind is a multi-file picker (specific UX), not the
        natural rendering for arbitrary list-valued attributes (vector3
        components, multi-int arrays, etc.). Set ``kind="file_list"``
        explicitly when you actually want a file picker.

        Parameters:
            value: The value a spec is inferred from.

        Returns:
            (str) ``"bool"`` / ``"int"`` / ``"float"`` / ``"str"``.
        """
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        return "str"
