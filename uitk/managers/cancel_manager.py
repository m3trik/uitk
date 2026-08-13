# !/usr/bin/python
# coding=utf-8
"""Host strategy for cancelling long-running slots.

uitk owns the *affordance* (Esc, a progress bar, a warning dialog); the host
owns what cancellation actually costs. Maya can peek the input queue mid-crunch
and wrap the work in an undo chunk; a standalone Qt app can do neither but has a
live event loop. :class:`CancelProvider` is the seam between them, and
:class:`CancelManager` is the registry a DCC package registers into at startup.

Every provider answers four questions for one operation:

* **sources** — what, polled from the operation's own thread, means "the user
  asked to stop?" (:class:`~pythontk.CancelScope` pull sources).
* **transaction** — what brackets the work, and can a cancelled run be rolled
  back to where it started?
* **feedback** — where does progress show when uitk's own footer is not on
  screen (a marking-menu slot often outlives the window that launched it)?
* **pump policy** — how to keep the UI repainting between work chunks without
  letting queued input dispatch a *second* slot into half-mutated state.

The default provider implements the standalone-Qt answers, so uitk works with
no host registration at all.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

import pythontk as ptk
from qtpy import QtCore, QtWidgets


class CancelProvider:
    """Standalone-Qt cancellation strategy; base class for host providers.

    Subclass in a DCC package (mayatk, blendertk) and register the instance via
    :meth:`CancelManager.register`. Every hook is optional — override only what
    the host can actually do, and never let a hook raise: a failure in the
    cancel plumbing must degrade the affordance, never break the slot.
    """

    name = "qt"

    #: Exclude queued input while pumping. False here because a standalone app
    #: has no other way to deliver the progress bar's Esc shortcut; hosts with a
    #: pump-independent source (Maya) set True to close the reentrancy hole.
    exclude_user_input = False

    #: Sustained Esc hold (seconds) before the key-state fallback source fires.
    escape_hold_seconds = 0.5

    #: Whether ``rollback=True`` can actually be honoured. Declared rather than
    #: attempted: a *partial* rollback leaves the document in an arbitrary
    #: intermediate state, which is worse than not rolling back at all, so a
    #: host that cannot undo cleanly must say so and let the dispatcher report
    #: it instead of half-doing it.
    supports_rollback = False

    def __init__(self):
        self._brackets: List[Any] = []

    # ------------------------------------------------------------------
    # Subclass helpers — bracket bookkeeping and reporting
    # ------------------------------------------------------------------
    # Every host provider tracks in-flight operations the same way (push on
    # begin, pop on end, consult the innermost from a tick or a source), so
    # that balance lives here rather than being re-derived per host, where the
    # twins would drift.
    @classmethod
    def install(cls) -> Optional["CancelProvider"]:
        """Register an instance of this provider with :class:`CancelManager`.

        Returns the provider, or ``None`` if registration failed — installation
        must never take down whatever host startup called it.
        """
        try:
            return CancelManager.register(cls())
        except Exception as e:
            cls.report_warning(f"Could not install {cls.__name__}: {e}")
            return None

    @classmethod
    def report_warning(cls, message: str) -> None:
        """Surface a warning to the user. Hosts override to use native output.

        Logs under the *concrete* provider's module, so a message from a DCC
        twin is attributed to that package rather than to uitk.
        """
        logging.getLogger(cls.__module__).warning(message)

    @classmethod
    def report_info(cls, message: str) -> None:
        """Surface an informational message. Hosts override for native output."""
        logging.getLogger(cls.__module__).info(message)

    def open_bracket(self, bracket: Any) -> Any:
        """Track *bracket* as the innermost in-flight operation; returns it."""
        self._brackets.append(bracket)
        return bracket

    def close_bracket(self, token: Any) -> Optional[Any]:
        """Stop tracking *token*; returns it, or ``None`` if it wasn't open.

        ``None`` covers both a junk token and a double close, so callers can
        use it as the guard for host teardown that must happen exactly once.

        Matched by **identity**, not equality: a host is free to make its
        bracket a dataclass, and two nested operations with equal field values
        would then let ``list.remove`` drop the wrong one — silently unbalancing
        the stack rather than failing.
        """
        for index, bracket in enumerate(self._brackets):
            if bracket is token:
                del self._brackets[index]
                return token
        return None

    @property
    def current_bracket(self) -> Optional[Any]:
        """The innermost in-flight operation, or ``None``."""
        return self._brackets[-1] if self._brackets else None

    def create_sources(self, scope, label: str = "") -> List[Callable[[], bool]]:
        """Pull sources for *scope*, polled on the operation's own thread.

        The base source is a key-state Esc-hold probe. Unlike a Qt shortcut it
        needs no event loop, so it still works while a slot blocks the main
        thread — which is exactly when the user reaches for Esc.
        """
        return [
            ptk.ExecutionMonitor.escape_hold_source(
                hold_seconds=self.escape_hold_seconds
            )
        ]

    def begin(self, scope, label: str = "", rollback: bool = False) -> Any:
        """Open the host bracket for an operation; returns an opaque token.

        *rollback* is passed at open time, not just at close: a host that can
        undo (Maya's undo chunk) has to start recording before the work runs.
        """
        return None

    def tick(
        self,
        value: Optional[int] = None,
        total: Optional[int] = None,
        text: Optional[str] = None,
    ) -> None:
        """Mirror one progress step into host-native UI (no-op by default).

        Takes no token: the provider knows its own active bracket from
        :meth:`begin`. Callers on the tick path (a progress bar deep in a
        widget tree) should not have to carry host state around.
        """

    def end(self, token: Any, cancelled: bool = False, rollback: bool = False) -> None:
        """Close the host bracket, optionally undoing a cancelled operation."""

    def pump(self) -> None:
        """Keep the UI responsive between work chunks.

        ``ExcludeUserInputEvents`` is the difference between "repaint the bar"
        and "dispatch whatever the user clicked while the scene was half
        mutated" — a nested slot on partially mutated state is a corruption
        bug, not a responsiveness feature.
        """
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        if self.exclude_user_input:
            app.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
        else:
            app.processEvents()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"


class CancelManager:
    """Process-wide registry for the active :class:`CancelProvider`.

    One provider per process: it describes the host uitk is running inside, and
    a process is only ever inside one host. Hosts register at startup::

        uitk.CancelManager.register(MayaCancelProvider())
    """

    _provider: Optional[CancelProvider] = None
    _default: Optional[CancelProvider] = None

    @classmethod
    def register(cls, provider: CancelProvider) -> CancelProvider:
        """Install the host provider; returns it for chaining."""
        if not isinstance(provider, CancelProvider):
            raise TypeError(
                f"provider must be a CancelProvider, got {type(provider).__name__}"
            )
        cls._provider = provider
        return provider

    @classmethod
    def provider(cls) -> CancelProvider:
        """The registered provider, or a shared standalone-Qt default."""
        if cls._provider is not None:
            return cls._provider
        if cls._default is None:
            cls._default = CancelProvider()
        return cls._default

    @classmethod
    def reset(cls) -> None:
        """Drop the registered provider (tests, host teardown)."""
        cls._provider = None

    @classmethod
    def new_scope(cls, label: str = "", **kwargs) -> ptk.CancelScope:
        """Build a :class:`~pythontk.CancelScope` wired to the host provider.

        The single place a scope is constructed in uitk, so every entry point —
        a ``@Cancelable`` slot, a bare progress bar — gets the same sources and
        therefore the same Esc behaviour.
        """
        scope = ptk.CancelScope(label or "operation", **kwargs)
        provider = cls.provider()
        try:
            for source in provider.create_sources(scope, label) or ():
                scope.add_source(source)
        except Exception:
            # A provider that can't build sources still yields a usable scope —
            # cancellable by dialog and by any pull source added later.
            pass
        return scope
