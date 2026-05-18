# !/usr/bin/python
# coding=utf-8
"""Unified launchable-entry data class shared by all Switchboard handlers.

Any handler that wants its registered items to appear in the unified
launcher surface (e.g. :class:`uitk.widgets.editors.SwitchboardBrowser`)
yields :class:`HandlerEntry` instances from its ``entries()`` method.

The entry is a frozen value object: identity (``name``, ``kind``) and
static metadata (``tags``, ``filepath``) are baked in at construction.
Live state (``is_visible``) is queried back through the owning handler
at use time so an entry never goes stale.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, FrozenSet, Optional

if TYPE_CHECKING:  # pragma: no cover
    from uitk.handlers.base_handler import BaseHandler


@dataclass(frozen=True)
class HandlerEntry:
    """One launchable item exposed by a Switchboard handler.

    Parameters:
        name: Identifier within the handler. Used as the key for
            launch/close/visibility lookups on the back-ref handler.
            Should also be unique across handlers in the same
            Switchboard; collisions are tolerated (last-write wins
            in the browser model) but the browser warns.
        kind: Short categorical label (e.g. ``"ui_file"``,
            ``"external_subprocess"``, ``"external_in_process"``).
            Rendered as a chip in the browser so users can tell
            launchables apart at a glance.
        handler: The handler that owns this entry. Browser dispatches
            launch/close/focus through it without knowing the kind.
        inherited_tags: Tags sourced from outside the entry's backing
            file — filename conventions, source-directory tags from
            ``Switchboard.register()``. Rendered as read-only chips.
        file_tags: Tags persisted in the entry's own backing file
            (e.g. ``<uitk_tags>`` in .ui XML). ``None`` signals
            "no on-disk tag storage" — browser disables inline tag
            editing. An empty frozenset means "editable but empty".
        filepath: On-disk path of the backing file when one exists.
            ``None`` for purely synthetic entries like external tools.
    """

    name: str
    kind: str
    handler: "BaseHandler"
    inherited_tags: FrozenSet[str] = frozenset()
    file_tags: Optional[FrozenSet[str]] = None
    filepath: Optional[str] = None

    @property
    def all_tags(self) -> FrozenSet[str]:
        return self.inherited_tags | (self.file_tags or frozenset())

    @property
    def editable_tags(self) -> bool:
        return self.file_tags is not None and self.filepath is not None
