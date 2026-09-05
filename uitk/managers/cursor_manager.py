# !/usr/bin/python
# coding=utf-8
"""One owner for every cursor change in uitk.

Qt has two cursor systems, and this module is the only place uitk drives
either of them directly.

**The application override cursor** (``QApplication.setOverrideCursor`` /
``restoreOverrideCursor``) is a process-wide stack that beats every widget
cursor. It is a balanced pair with no notion of ownership: ``restore`` pops
the TOP of the stack, whoever pushed it. So a caller that misses its pop (a
release delivered elsewhere, a destroyed owner, an exception) strands a
cursor over the whole application, and a caller whose entry got buried pops
a stranger's entry instead of its own. Nothing in uitk calls the raw pair
any more; there are two owned forms and two stack primitives:

* :meth:`CursorManager.busy` — a bounded ``with`` scope (the slot
  dispatcher's wait cursor). On exit it removes the top-most entry of ITS
  shape, wherever that sits, and it yields to native modal dialogs while it
  is held.
* :class:`OverrideCursorGuard` — an interaction with no bounded end (the
  marking menu's gesture cursor): a watchdog removes the override as soon as
  the owner's ``is_live`` predicate turns false, so no event has to arrive.
* :meth:`CursorManager.suspend` / :meth:`CursorManager.drain` — for the
  dialogs that must show natural cursors while an override is active: a
  modal suspends the stack for its event loop and restores it after; a
  non-modal viewer cancels it outright.

**Per-widget cursors** (``QWidget.setCursor`` / ``QGraphicsItem.setCursor``)
are the affordance layer — the open hand on a draggable header, the
horizontal arrow on a resize edge. A gesture that changes one for its
duration has to put back exactly what was there, which is either an explicit
cursor or NONE, and ``target.cursor()`` cannot tell the two apart (it reports
the inherited arrow either way), so restoring it pins an explicit arrow on a
widget that used to inherit. :meth:`CursorManager.push` /
:meth:`CursorManager.pop` keep the distinction, for widgets and graphics
items alike. :meth:`CursorManager.heal_hover` covers the case where a
widget's cursor never applies at all because Qt's own hover bookkeeping has
gone stale.

Nothing here imports widgets or the switchboard: the manager sits below both.
"""

import contextlib
import weakref
from typing import Callable, List, Optional

from qtpy import QtCore, QtGui, QtWidgets


class OverrideCursorGuard(QtCore.QObject):
    """Owns one application override cursor and guarantees its removal.

    ``QApplication.setOverrideCursor`` / ``restoreOverrideCursor`` are a
    balanced pair, so an override is only ever as reliable as the event that is
    supposed to pop it. A cursor pushed for the duration of an interaction —
    the marking menu's gesture ``CrossCursor`` — strands itself over the whole
    application whenever that pop is missed, and nothing notices:

      * the release lands somewhere else (a child widget holding the mouse
        grab, the host DCC, another window), so the pushing widget never sees
        the event that ends the interaction;
      * the widget is *destroyed* rather than hidden — Qt sends no hide event
        to a child in that case (only a parent ``hide()`` while visible does);
      * a third party snapshots the stack and restores it afterwards
        (:meth:`CursorManager.suspend`, the modal suspension inside
        :meth:`CursorManager.busy`). If the owner released its cursor while
        the stack was suspended, the restore re-pushes an entry that now has
        no owner at all.

    This guard replaces balanced-call bookkeeping with an INVARIANT — *an
    override of ``shape`` exists only while ``is_live()`` says it should* —
    enforced from three sides:

      * :meth:`apply` / :meth:`clear` — the ordinary, immediate path.
      * a watchdog timer, running ONLY while the guard holds the override,
        that clears it as soon as ``is_live()`` turns False. This is what
        covers the missed events: no event has to arrive for the cursor to
        come back. A predicate that raises (the owner's C++ object is gone)
        counts as not-live, and the class keeps the guard — and therefore its
        timer — alive while it holds a push, so even a destroyed owner is
        cleaned up.
      * :meth:`reconcile` — drops any stack entry whose shape a guard claims
        but no guard holds (the snapshot/restore case). Run before every
        apply, and applied as a filter inside :meth:`CursorManager.push_stack`
        so a stale entry is never re-pushed in the first place.

    The claimed shape must be EXCLUSIVE to the guard: nothing else in the
    process may push it, or reconcile would drop a stranger's cursor. (This
    is why the dispatcher's ``WaitCursor`` is a :meth:`CursorManager.busy`
    scope and not a guard — the host DCC pushes wait cursors of its own.)

    Parameters:
        shape (Qt.CursorShape): The cursor this guard owns, exclusively.
        is_live (callable): Zero-arg predicate — True while the override is
            legitimate (e.g. ``widget.isVisible``). Raising counts as False.
        interval_ms (int): Watchdog period while the override is held.
    """

    #: Shapes any guard has ever claimed — the set :meth:`is_stale` filters on.
    _CLAIMED_SHAPES = set()
    #: Guards currently holding a push. A strong ref, so a guard whose owner
    #: was destroyed still gets ticked (and cleaned up) by its own timer.
    _HOLDERS = set()

    def __init__(self, shape, is_live: Callable[[], bool], interval_ms: int = 250):
        super().__init__()
        self._shape = shape
        self._is_live = is_live
        self._holding = False
        # Explicitly the base class's registries: they are process-global by
        # design (any subclass shares them), and mutating through ``type(self)``
        # would read as per-subclass state.
        OverrideCursorGuard._CLAIMED_SHAPES.add(shape)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._on_tick)

    @property
    def shape(self):
        """The cursor shape this guard owns."""
        return self._shape

    @property
    def holding(self) -> bool:
        """True while this guard holds an application override cursor."""
        return self._holding

    def apply(self) -> None:
        """Push the override (idempotent) and start the watchdog."""
        app = QtWidgets.QApplication.instance()
        if app is None or self._holding:
            return
        # Anything of our shape still on the stack is by definition stale —
        # we hold nothing. Clear it so a leak can never accumulate a second
        # entry that would outlive this interaction too.
        self.reconcile()
        app.setOverrideCursor(QtGui.QCursor(self._shape))
        self._holding = True
        OverrideCursorGuard._HOLDERS.add(self)
        self._timer.start()

    def clear(self) -> None:
        """Remove the override (idempotent) and stop the watchdog."""
        if not self._holding:
            return
        # Order matters: dropping ownership FIRST is what lets the removal
        # below reuse the generic stale-entry filter for the buried case.
        self._holding = False
        OverrideCursorGuard._HOLDERS.discard(self)
        self._timer.stop()

        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        top = app.overrideCursor()
        if top is None:
            # Nothing to remove — the stack is currently suspended by someone
            # else (their restore now drops our entry via is_stale).
            return
        if top.shape() == self._shape:
            app.restoreOverrideCursor()
        else:
            # Buried under a later push (e.g. a slot's busy cursor): rebuild
            # the stack without our entry rather than popping theirs.
            self.reconcile()

    def _on_tick(self) -> None:
        """Watchdog: enforce the invariant without needing any event."""
        if self._live():
            return
        self.clear()

    def _live(self) -> bool:
        """``is_live()``, fail-safe. Any failure — including a deleted C++
        owner (``RuntimeError``) — means *not* live: an override that cannot
        prove it is still wanted must go."""
        try:
            return bool(self._is_live())
        except Exception:
            return False

    @classmethod
    def holds(cls, shape) -> bool:
        """True if any live guard currently holds ``shape``.

        Snapshots the holder set: a guard released mid-iteration (a watchdog
        tick landing inside a stack rebuild) mutates it.
        """
        return any(g.holding and g.shape == shape for g in tuple(cls._HOLDERS))

    @classmethod
    def is_stale(cls, cursor) -> bool:
        """True if ``cursor`` is a guard-owned shape that no guard holds —
        an orphan that must not be (re-)pushed onto the stack."""
        shape = cursor.shape()
        return shape in cls._CLAIMED_SHAPES and not cls.holds(shape)

    @classmethod
    def notify_stack_drained(cls) -> None:
        """Drop every guard's ownership because the whole stack was dropped
        out from under them (see :meth:`CursorManager.drain`).

        Without this a guard keeps claiming an entry that no longer exists:
        ``holds`` then reports True for an orphaned shape, and — the visible
        part — :meth:`apply` short-circuits, so the interaction runs out its
        life with no cursor instead of re-asserting one. Only the ownership
        flag is cleared; there is nothing left to pop.
        """
        for guard in tuple(cls._HOLDERS):
            guard._holding = False
            guard._timer.stop()
        cls._HOLDERS.clear()

    @classmethod
    def reconcile(cls) -> None:
        """Drop every orphaned guard cursor from the application stack,
        wherever it sits, leaving all other entries in their original order.
        No-op when no override is active."""
        app = QtWidgets.QApplication.instance()
        if app is None or app.overrideCursor() is None:
            return
        saved = CursorManager.pop_stack(app)
        # The re-push drops stale entries (see CursorManager.push_stack).
        CursorManager.push_stack(saved, app)


class _ModalSuspendFilter(QtCore.QObject):
    """Suspend the override stack while a modal dialog blocks the app.

    Installed on the ``QApplication`` by :meth:`CursorManager.busy` for the
    scope's duration. The busy override is application-wide and beats
    *every* widget cursor, so a **native** modal dialog opened inside the
    scope — Maya's ``cmds.fileDialog2`` / ``promptDialog``, a host file
    picker, an OS dialog — would show the busy hourglass over its own
    buttons and fields while waiting for the user. uitk's own dialog helpers
    suspend the override themselves (:meth:`CursorManager.suspend`), but a
    native DCC dialog is not a Qt widget we wrap, so the scope can't bracket
    it.

    Qt posts :data:`QEvent.WindowBlocked` to a window when a modal blocks
    it and :data:`QEvent.WindowUnblocked` when it's released — which fires
    for native Qt-backed dialogs too. This filter pops the whole override
    stack (preserving order) on the first block and restores it on the
    matching unblock, so the dialog shows natural per-widget cursors and
    the hourglass resumes automatically for any blocking work done *after*
    the dialog closes. Nesting is depth-counted so only the outermost
    block/unblock pair touches the cursor.
    """

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._depth = 0
        self._saved = []

    def _restore_all(self):
        CursorManager.push_stack(self._saved, self._app)
        self._saved = []

    def eventFilter(self, obj, event):
        try:
            etype = event.type()
            if etype == QtCore.QEvent.WindowBlocked:
                if self._depth == 0:
                    self._saved = CursorManager.pop_stack(self._app)
                self._depth += 1
            elif etype == QtCore.QEvent.WindowUnblocked:
                if self._depth > 0:
                    self._depth -= 1
                    if self._depth == 0:
                        self._restore_all()
        except Exception:
            pass
        return False  # never consume — purely observational

    def cleanup(self):
        """Re-balance the stack if a block had no matching unblock.

        A modal blocks the scope synchronously, so the unblock normally
        arrives before the scope ends. Defensive: if we exit still
        suspended, put the saved overrides back so the scope's own removal
        finds a balanced stack.
        """
        if self._depth > 0:
            self._restore_all()
        self._depth = 0


class CursorManager:
    """Static service for both of Qt's cursor systems — see the module
    docstring for what each entry point is for and why the raw Qt calls are
    not used directly anywhere else in uitk."""

    # ------------------------------------------------------------------
    # Application override-cursor stack
    # ------------------------------------------------------------------
    @staticmethod
    def _app(app=None):
        return app if app is not None else QtWidgets.QApplication.instance()

    @staticmethod
    def pop_stack(app=None) -> List[QtGui.QCursor]:
        """Pop the whole application override-cursor stack.

        Returns the popped cursors **top-first** so :meth:`push_stack` can
        restore them in the original order. No-op (empty list) when no
        override is active or there is no application.

        Parameters:
            app (QApplication, optional): Defaults to the running instance.

        Returns:
            list[QCursor]: The former stack, top-first.
        """
        app = CursorManager._app(app)
        saved = []
        if app is not None:
            while True:
                current = app.overrideCursor()
                if current is None:
                    break
                saved.append(QtGui.QCursor(current))
                app.restoreOverrideCursor()
        return saved

    @staticmethod
    def push_stack(saved, app=None) -> None:
        """Re-push cursors captured by :meth:`pop_stack`, restoring the
        original stack order.

        An entry belonging to an :class:`OverrideCursorGuard` that has since
        released it is skipped: restoring it would strand a cursor whose owner
        is gone (the pop/push pair brackets an unbounded wait — a modal dialog
        — during which the owning interaction can easily end).

        Parameters:
            saved (list[QCursor]): The top-first list :meth:`pop_stack` returned.
            app (QApplication, optional): Defaults to the running instance.
        """
        app = CursorManager._app(app)
        if app is not None:
            for cursor in reversed(saved):
                if OverrideCursorGuard.is_stale(cursor):
                    continue
                app.setOverrideCursor(cursor)

    @staticmethod
    @contextlib.contextmanager
    def suspend():
        """Clear the application override-cursor stack for a ``with`` block.

        The slot dispatcher holds a :data:`Qt.WaitCursor` override for the
        duration of every slot (:meth:`busy`). An override beats *every*
        widget cursor, so any dialog a slot spawns inherits the busy
        hourglass — even over its buttons, text fields and file lists, where
        the user is expected to interact. A per-widget ``setCursor`` cannot
        win against an active override, so the only correct fix is to
        suspend the override for the dialog's (modal) lifetime, letting each
        widget show its natural cursor, then restore the exact stack
        afterward so the slot's busy feedback resumes.

        No-op when no override is active (dialogs opened outside a slot).
        """
        app = CursorManager._app()
        saved = CursorManager.pop_stack(app)
        try:
            yield
        finally:
            CursorManager.push_stack(saved, app)

    @staticmethod
    def drain() -> None:
        """Pop the entire application override-cursor stack, for good.

        Counterpart to :meth:`suspend` for *non-modal* windows. A modal
        dialog can suspend a busy cursor for the bounded lifetime of its
        event loop and restore it on close. A non-modal viewer outlives the
        slot that spawned it — by the time the user closes it the slot's
        scope has long since ended, so there is nothing to restore *to*, and
        re-pushing a busy cursor on the window's close would strand an
        hourglass with no matching pop. The correct behaviour is therefore
        to *cancel* the busy cursor outright when the window appears: the
        slot's work product is on screen and the user is now meant to
        interact with it. The scope's own removal then finds nothing of its
        shape and removes nothing.

        No-op when no override is active. A drain takes *every* owner's
        entry, guards included — so they are told, or a guard would keep
        claiming an entry that no longer exists
        (:meth:`OverrideCursorGuard.notify_stack_drained`).
        """
        CursorManager.pop_stack(CursorManager._app())
        OverrideCursorGuard.notify_stack_drained()

    @staticmethod
    def release(shape, app=None) -> bool:
        """Remove the top-most override entry of ``shape`` — and nothing else.

        The owner-aware replacement for ``restoreOverrideCursor``, which pops
        whatever is on top. When our entry is on top this is the same one
        pop; when it is buried (a guard's gesture cursor, another scope's
        entry pushed after ours) the stack is rebuilt without our entry and
        the others keep their order. Entries of one shape are fungible, so
        "one entry of my shape" is exact accounting even when several scopes
        of the same shape are live.

        Parameters:
            shape (Qt.CursorShape): The shape the caller pushed.
            app (QApplication, optional): Defaults to the running instance.

        Returns:
            bool: True when an entry was removed; False when none of that
            shape was left (a :meth:`drain` took it — nothing to balance).
        """
        app = CursorManager._app(app)
        if app is None:
            return False
        top = app.overrideCursor()
        if top is None:
            return False
        if top.shape() == shape:
            app.restoreOverrideCursor()
            return True
        saved = CursorManager.pop_stack(app)
        kept = []
        removed = False
        for cursor in saved:  # top-first
            if not removed and cursor.shape() == shape:
                removed = True
                continue
            kept.append(cursor)
        CursorManager.push_stack(kept, app)
        return removed

    @staticmethod
    @contextlib.contextmanager
    def busy(shape=QtCore.Qt.WaitCursor, suspend_for_modals: bool = True):
        """Show ``shape`` application-wide for the duration of a ``with`` block.

        The bounded-scope override: pushed on entry, and on exit the scope's
        OWN entry is removed (:meth:`release`) — never the top of the stack
        blind, so an entry pushed on top of ours by someone else (the marking
        menu's gesture cursor, a host wait cursor) survives our exit exactly
        as it did our entry. While the scope is held the stack yields to any
        native modal dialog that blocks the application
        (:class:`_ModalSuspendFilter`), so the dialog shows natural cursors
        and the busy cursor resumes for the work that follows it.

        The cursor is OS-driven, so it animates even while a DCC command
        holds the Qt event loop. A cursor failure never propagates: the
        scope swallows its own errors, because the caller's work matters and
        the cursor does not.

        Parameters:
            shape (Qt.CursorShape): The busy shape. Default ``WaitCursor``.
            suspend_for_modals (bool): Install the modal suspension for the
                scope's duration. Default True.
        """
        app = CursorManager._app()
        pushed = False
        modal_filter = None
        if app is not None:
            try:
                app.setOverrideCursor(QtGui.QCursor(shape))
                pushed = True
                if suspend_for_modals:
                    modal_filter = _ModalSuspendFilter(app)
                    app.installEventFilter(modal_filter)
            except Exception:
                pass
        try:
            yield
        finally:
            if modal_filter is not None:
                try:
                    app.removeEventFilter(modal_filter)
                    modal_filter.cleanup()
                except Exception:
                    pass
            if pushed:
                try:
                    CursorManager.release(shape, app)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Per-widget / per-item gesture cursors
    # ------------------------------------------------------------------
    #: target -> [(had_explicit_cursor, QCursor), ...] — what :meth:`pop`
    #: restores. Weak, so a target's entries die with it; every Qt wrapper
    #: (QWidget and QGraphicsItem alike) is hashable and weak-referenceable.
    _gesture_cursors = weakref.WeakKeyDictionary()

    @classmethod
    def _gesture_stack(cls, target, create: bool) -> Optional[list]:
        stack = cls._gesture_cursors.get(target)
        if stack is None and create:
            stack = cls._gesture_cursors[target] = []
        return stack

    @staticmethod
    def has_explicit_cursor(target) -> bool:
        """True when ``target`` carries a cursor of its own rather than
        inheriting one. ``QGraphicsItem`` says so through ``hasCursor()``,
        ``QWidget`` through the ``WA_SetCursor`` attribute; ``cursor()``
        alone cannot tell (it reports the inherited arrow either way)."""
        has_cursor = getattr(target, "hasCursor", None)
        if callable(has_cursor):
            return bool(has_cursor())
        return bool(target.testAttribute(QtCore.Qt.WA_SetCursor))

    @classmethod
    def push(cls, target, shape) -> None:
        """Show ``shape`` on ``target`` until :meth:`pop` — a gesture cursor.

        Records whether the target had an explicit cursor (and which) so the
        pop can restore *that*, or restore the target to inheriting. Pushes
        nest. Variations within the gesture (a forbidden cursor while the
        pointer is outside the window, say) are plain ``setCursor`` calls in
        between: the pop restores the pre-gesture state regardless.

        Parameters:
            target (QWidget | QGraphicsItem): Anything with ``setCursor`` /
                ``unsetCursor`` / ``cursor``.
            shape (Qt.CursorShape | QCursor): The gesture cursor.
        """
        cls._gesture_stack(target, create=True).append(
            (cls.has_explicit_cursor(target), QtGui.QCursor(target.cursor()))
        )
        target.setCursor(QtGui.QCursor(shape))

    @classmethod
    def pop(cls, target) -> bool:
        """Undo the most recent :meth:`push` on ``target``.

        Returns:
            bool: True when a pushed cursor was restored; False when nothing
            was pushed (a release with no matching press — a no-op, so a
            cancel path can call it unconditionally).
        """
        stack = cls._gesture_stack(target, create=False)
        if not stack:
            return False
        had_explicit, cursor = stack.pop()
        if had_explicit:
            target.setCursor(cursor)
        else:
            target.unsetCursor()
        return True

    # ------------------------------------------------------------------
    # Hover-state repair
    # ------------------------------------------------------------------
    @staticmethod
    def heal_hover(widget, global_pos) -> bool:
        """Re-run Qt's enter dispatch for ``widget`` when its hover state is
        provably stale.

        A widget's cursor is applied by the Enter that Qt dispatches when the
        pointer moves onto it, and that dispatch is skipped while Qt believes
        a mouse button is still down or a widget still holds the grab. Both
        beliefs are global bookkeeping that a release delivered to another
        window (or swallowed by a popup) can leave stale — and then no widget
        in the process receives Enter: per-widget cursors stop applying and
        QSS ``:hover`` dies with them, until the next real press+release
        resets the state. That is the "header never shows the hand, a click
        elsewhere fixes it" report.

        A ``HoverMove`` is proof the pointer is over the widget (hover events
        are synthesized from the move itself, independent of that
        bookkeeping, and need no mouse tracking). So: call this from a
        widget's ``HoverMove`` (``WA_Hover`` set). If ``underMouse()`` is
        nevertheless False, the state is inconsistent and an Enter is
        re-dispatched through the widget's top-level ``QWindow`` — Qt's own
        path, which sets ``WA_UnderMouse`` up the chain, sends the real
        ``QEnterEvent`` and applies the cursor. Deliberately skipped while a
        button is genuinely held or a grab is live: there the missing Enter
        is Qt's intent, not a fault.

        Parameters:
            widget (QWidget): The hovered widget.
            global_pos (QPoint): The hover event's global position — the
                event's, never a live ``QCursor.pos()`` read.

        Returns:
            bool: True when an Enter was re-dispatched.
        """
        try:
            if widget.underMouse():
                return False
            if QtWidgets.QApplication.mouseButtons() != QtCore.Qt.NoButton:
                return False
            if QtWidgets.QWidget.mouseGrabber() is not None:
                return False
            handle = widget.window().windowHandle()
            if handle is None:
                return False
            local = QtCore.QPointF(handle.mapFromGlobal(global_pos))
            QtCore.QCoreApplication.sendEvent(
                handle, QtGui.QEnterEvent(local, local, QtCore.QPointF(global_pos))
            )
            return True
        except RuntimeError:  # widget or window deleted underneath us
            return False
