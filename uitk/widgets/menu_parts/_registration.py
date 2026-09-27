# !/usr/bin/python
# coding=utf-8
"""Registering the menu's items with the window that owns it.

Items added to a menu are registered with the owning ``MainWindow`` (slot
wiring, state persistence) one event-loop tick after ``add`` returns, coalesced
into one drain per menu -- and flushed early by ``MainWindow.register_children``
so it lands before the window's first paint. The owning window is captured
while the menu still sits under it, because showing the menu reparents it to a
top-level popup.

One part of :class:`~uitk.widgets.menu.Menu`, which inherits it; it holds no
state of its own (``Menu.__init__`` declares every attribute used here) and
is never instantiated alone.
"""

import logging
import weakref
from typing import Optional

from qtpy import QtCore, QtWidgets

_logger = logging.getLogger("uitk.widgets.menu")


class _MenuRegistrationMixin:
    """Registering the menu's items with the window that owns it."""

    # Every Menu with a non-empty deferred-registration queue (see
    # Menu._schedule_registration). Weak so a menu destroyed before its drain
    # simply drops out. Consumed by _flush_pending_registrations, which
    # MainWindow.register_children calls to complete all menu-item registration
    # inside the pre-paint window instead of on the post-paint tick-0 timer (the
    # init-flash "drain" phase).
    _awaiting_registration: "weakref.WeakSet" = weakref.WeakSet()

    @staticmethod
    def _flush_pending_registrations(window=None) -> int:
        """Synchronously drain every menu's deferred item registrations.

        ``Menu.add`` defers each item's ``register_widget`` to a coalesced
        ``QTimer.singleShot(0, ...)`` — deliberately, to escape *mid-add*
        recursion (a synchronous ``init_slot`` during ``add()`` can re-enter menu
        population; see ``Menu.add``). That deferral was never meant to escape
        the pre-paint window, yet on first show the timer fires only AFTER the
        window painted — item state-restore and nested option-box wraps then
        mutate on screen (the init flash).

        Called at the end of ``MainWindow.register_children`` (all ``add()``
        frames unwound, window not yet painted). Only menus outside an ``add()``
        frame (``_add_depth == 0``) and belonging to *window* (when given) are
        drained — the recursion contract is preserved exactly. Loops to fixpoint
        (a drained ``init_slot`` may populate nested menus, scheduling more) with
        a safety cap. The already-armed tick-0 timers later find empty queues
        and no-op.

        Returns the number of menus drained.
        """
        drained = 0
        for _ in range(10):  # fixpoint cap — see warning below
            # Snapshot: draining mutates the set (menus discard themselves).
            batch = [
                m
                for m in list(_MenuRegistrationMixin._awaiting_registration)
                # Plain Python attrs — safe even on a dead C++ wrapper.
                if m._pending_registrations and m._add_depth == 0
            ]
            if window is not None:
                alive = []
                for m in batch:
                    try:
                        # C++ access (walks parent()): a deleteLater'd menu's
                        # wrapper lingers in the WeakSet until GC and raises
                        # RuntimeError here — it must be dropped, not allowed to
                        # crash the flush inside MainWindow.showEvent.
                        if m._resolve_registration_window() is window:
                            alive.append(m)
                    except RuntimeError:
                        _MenuRegistrationMixin._awaiting_registration.discard(m)
                batch = alive
            if not batch:
                return drained
            for menu in batch:
                try:
                    menu._drain_pending_registrations()
                    drained += 1
                except RuntimeError:
                    continue  # menu died mid-flush
        _logger.warning(
            "Menu._flush_pending_registrations: fixpoint cap reached — menu "
            "registrations still pending after 10 rounds (recursive add loop?)."
        )
        return drained

    def owner_window(self) -> Optional[QtWidgets.QWidget]:
        """Public alias for the owning ``MainWindow``, or ``None``.

        Thin wrapper over :meth:`_resolve_registration_window` so collaborators
        (e.g. a window-scoped :class:`PresetManager`) can reach the host window
        through the same reparent-race-robust resolver used for dynamic-widget
        registration, without depending on a private method.
        """
        return self._resolve_registration_window()

    def _resolve_registration_window(self) -> Optional[QtWidgets.QWidget]:
        """Return the owning MainWindow for dynamic-widget registration.

        Registration is *deferred* (see :meth:`_schedule_registration`); by the
        time the drain runs the menu may have reparented itself to a top-level
        popup / Tool window on show, severing the parent chain back to the
        MainWindow. A plain ``self.parent()`` walk then finds nothing and
        registration is silently skipped — the widget never gets
        ``restore_state``, so its value is neither saved nor restored. This was
        the prime suspect behind menu-hosted options resetting only in live
        interactive DCC sessions (where show/reparent races the drain).

        To stay robust we (1) prefer a live parent-chain walk — correct and
        cheap in the common, un-reparented case — and (2) fall back to the
        MainWindow captured weakly while the chain was still intact. The cache
        is refreshed on every successful live walk.
        """
        curr = self.parent()
        while curr is not None:
            if hasattr(curr, "register_widget") and hasattr(curr, "widgets"):
                self._registration_window_ref = weakref.ref(curr)
                return curr
            curr = curr.parent()

        ref = self._registration_window_ref
        window = ref() if ref is not None else None
        if window is not None:
            try:
                window.objectName()  # dead C++ wrapper -> RuntimeError
                return window
            except RuntimeError:
                self._registration_window_ref = None
        return None

    def _register_with_main_window(self, widget: QtWidgets.QWidget) -> None:
        """Find the owning MainWindow and register *widget* with it.

        This enables signal wiring, slot discovery, and QSettings-based
        state persistence for widgets added dynamically via :meth:`add`.
        Resolution goes through :meth:`_resolve_registration_window` so a menu
        that has already reparented to a popup still resolves its MainWindow.
        """
        window = self._resolve_registration_window()
        if window is None:
            self.logger.debug(
                "_register_with_main_window: no MainWindow reachable for "
                f"{widget.objectName()!r}; its state will not persist"
            )
            return
        try:
            window.register_widget(widget)
        except Exception:
            pass

    def _schedule_registration(self, widget: QtWidgets.QWidget) -> None:
        """Queue *widget* for deferred registration with the main window.

        Coalesces N per-item ``QTimer.singleShot`` calls into a single
        drain pass.  Registration order (FIFO) and the deferred-not-sync
        contract from :meth:`Menu.add` are preserved.
        """
        # Capture the owning MainWindow once, while the menu is still nested
        # under its host and the parent chain is intact. By drain time the menu
        # may have reparented to a popup, breaking the walk; the cache set here
        # lets _resolve_registration_window recover it. A later legitimate
        # reparent is still honored — drain-time resolution re-walks live first.
        if self._registration_window_ref is None:
            self._resolve_registration_window()
        self._pending_registrations.append(widget)
        # Track for the pre-paint flush (_flush_pending_registrations) so
        # register_children can complete registration before first paint;
        # the timer below stays as the fallback for post-show dynamic adds.
        _MenuRegistrationMixin._awaiting_registration.add(self)
        if not self._registration_drain_scheduled:
            self._registration_drain_scheduled = True
            QtCore.QTimer.singleShot(0, self._drain_pending_registrations)

    def _drain_pending_registrations(self) -> None:
        """Process every queued registration in insertion order.

        Anything appended *during* the drain (e.g. a registration that
        ends up calling ``Menu.add`` again on a sibling menu) lands in a
        fresh queue and triggers its own next-tick drain — matching the
        per-item-timer behavior this replaced.

        Exception handling: with one timer per item (the prior
        implementation), each fired independently — a failure in one
        registration didn't drop the rest.  We preserve that property by
        catching all exceptions per-iteration.  ``RuntimeError`` (the
        common case: widget destroyed between schedule and drain) is
        swallowed silently; any other exception is logged so latent bugs
        don't go unnoticed but the drain still completes.
        """
        pending, self._pending_registrations = self._pending_registrations, []
        self._registration_drain_scheduled = False
        # Registrations appended DURING the drain land in the fresh queue and
        # re-add this menu; discarding here keeps the awaiting-set accurate.
        _MenuRegistrationMixin._awaiting_registration.discard(self)
        for widget in pending:
            try:
                self._register_with_main_window(widget)
            except RuntimeError:
                # Widget destroyed between schedule and drain; skip silently.
                continue
            except Exception as exc:  # noqa: BLE001 — preserve per-timer isolation
                self.logger.error(
                    f"_drain_pending_registrations: {type(exc).__name__} during "
                    f"_register_with_main_window: {exc}",
                )
                continue
