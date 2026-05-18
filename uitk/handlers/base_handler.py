# !/usr/bin/python
# coding=utf-8
"""Common infrastructure for Switchboard handlers.

Centralises the boilerplate that every handler used to duplicate:

* the ``switchboard`` guard,
* the ``instance()`` singleton classmethod keyed by ``(cls, id(sb))``
  (a bare ``id(sb)`` key collides with sibling handlers — see the test
  ``test_singleton_key_does_not_collide_with_other_handlers``),
* ``self.config`` mapped onto ``sb.configurable.branch(...)``,
* a unified ``_notify_entries_changed`` helper that routes through the
  Switchboard's signals so subscribers (e.g. the browser) connect once.

Handlers that want their items in the unified launcher surface (browser)
additionally implement the four-method launchable contract documented on
:class:`LaunchableHandlerProtocol` (validated at register time —
inheriting the protocol is optional, duck-typing is sufficient).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional, Protocol, runtime_checkable

import pythontk as ptk

if TYPE_CHECKING:  # pragma: no cover
    from uitk.handlers.handler_entry import HandlerEntry
    from uitk.switchboard import Switchboard


class BaseHandler(ptk.SingletonMixin, ptk.LoggingMixin):
    """Common base for Switchboard handlers.

    Subclasses set :attr:`CONFIG_BRANCH` (the name passed to
    ``sb.configurable.branch(...)``) and optionally :attr:`DEFAULTS`;
    ``Switchboard.register_handler`` seeds the branch with those values.

    Singleton key is ``(cls, id(sb))`` so two distinct handler classes
    bound to the same Switchboard don't collide.
    """

    CONFIG_BRANCH: Optional[str] = None
    DEFAULTS: dict = {}

    def __init__(
        self,
        switchboard: "Switchboard",
        log_level: str = "WARNING",
        **_kwargs,
    ):
        if switchboard is None:
            raise ValueError(
                f"{type(self).__name__} requires a Switchboard instance."
            )
        self.sb = switchboard
        self.logger.setLevel(log_level)

    @classmethod
    def instance(cls, switchboard: "Switchboard" = None, **kwargs):
        kwargs.setdefault("switchboard", switchboard)
        kwargs["singleton_key"] = (cls, id(switchboard))
        return super().instance(**kwargs)

    @property
    def config(self):
        branch = self.CONFIG_BRANCH or type(self).__name__
        return self.sb.configurable.branch(branch)

    # ── launchable-contract helpers ───────────────────────────────────

    def _notify_entries_changed(self, entry_name: Optional[str] = None) -> None:
        """Fan-out an entry-state-changed event through the Switchboard.

        Two-tier granularity:
          * ``entry_name=None`` → coarse "this handler's entry set may
            have changed" (registration / unregistration of an item).
          * ``entry_name=<name>`` → fine "one entry's live state changed"
            (visibility, status, …).

        Routes through ``sb.on_handler_entries_changed`` and
        ``sb.on_handler_entry_changed`` respectively. Subscribers connect
        to the sb-level signals once and receive events for every handler
        — matching the existing ``on_ui_registered`` pattern.
        """
        handler_name = self._sb_handler_name() or type(self).__name__
        if entry_name is None:
            sig = getattr(self.sb, "on_handler_entries_changed", None)
            if sig is not None:
                sig.emit(handler_name)
        else:
            sig = getattr(self.sb, "on_handler_entry_changed", None)
            if sig is not None:
                sig.emit(handler_name, entry_name)

    def _sb_handler_name(self) -> Optional[str]:
        """Look up the attribute name this handler is bound to on ``sb.handlers``.

        Returns ``None`` during init (handler being constructed before
        ``register_handler`` finishes) or if the handler has been detached.
        Callers fall back to the class name in that case — good enough
        for signal routing without forcing handlers to know their own
        binding.
        """
        handlers = getattr(self.sb, "handlers", None)
        if handlers is None:
            return None
        for name, value in vars(handlers).items():
            if value is self:
                return name
        return None


@runtime_checkable
class LaunchableHandlerProtocol(Protocol):
    """Structural type for handlers that participate in the launcher surface.

    Inheritance is optional — the Switchboard validates the contract by
    duck-typing at ``register_handler`` time (mirrors ``_LOADER_CONTRACT``).
    Use this protocol for type hints and ``isinstance`` checks; for the
    runtime source of truth see ``Switchboard._LAUNCHABLE_CONTRACT``.

    A fifth, *optional* method — ``save_tags(name, tags)`` — should be
    implemented by handlers whose entries report ``editable_tags=True``.
    The browser only calls it for those entries.
    """

    def entries(self) -> Iterable["HandlerEntry"]: ...
    def launch(self, name: str, **options): ...
    def close(self, name: str) -> None: ...
    def is_visible(self, name: str) -> bool: ...
