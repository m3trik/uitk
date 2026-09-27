# !/usr/bin/python
# coding=utf-8
"""A shortcut collision a checker reports -- Qt-free.

Host packages build these in their own collision checkers (a DCC's native
hotkey map) without importing Qt; the shortcut editor
(:class:`~uitk.widgets.editors.shortcut_editor.registry_editor.ShortcutEditor`)
renders them and offers whatever each one says it can do.
"""

from typing import Callable, Optional


class CollisionConflict:
    """A single conflict reported by a collision checker.

    Attributes:
        source: Where the conflict came from: ``"uitk"`` for the editor's own
            registry; a host checker names itself.
        description: Human-readable explanation.
        breaks_binding: True when accepting the new binding will leave both
            sides in an undefined / unreliable state (e.g. two same-scope same-
            sequence shortcuts that Qt cannot disambiguate). When True the
            editor offers to auto-clear the conflicting binding.
        clear_action: Optional callable that clears the conflicting binding
            when the user accepts the auto-clear path. Required when
            ``breaks_binding`` is True for the conflict to be resolvable. On a
            coexisting conflict (``breaks_binding`` False) it earns an
            *Assign & free <label> binding* option.
        label: Display name of the conflicting binding's owner in that option
            (``"Assign & free <label> binding"``). Defaults to *source*.
        clear_blocked: Why the owner cannot clear its binding right now. Given
            on a coexisting conflict with no ``clear_action``, the editor shows
            the free option DISABLED with this as its tooltip rather than
            leaving the user to wonder why it is missing.
    """

    def __init__(
        self,
        source: str,
        description: str,
        breaks_binding: bool = False,
        clear_action: Optional[Callable[[], None]] = None,
        label: Optional[str] = None,
        clear_blocked: str = "",
    ):
        self.source = source
        self.description = description
        self.breaks_binding = breaks_binding
        self.clear_action = clear_action
        self.label = label
        self.clear_blocked = clear_blocked

    @property
    def display_label(self) -> str:
        """The owner's name as the conflict dialog shows it."""
        return self.label or self.source

    def __repr__(self) -> str:
        return (
            f"CollisionConflict(source={self.source!r}, "
            f"description={self.description!r}, "
            f"breaks_binding={self.breaks_binding}, "
            f"clear_action={'set' if self.clear_action else 'None'})"
        )
