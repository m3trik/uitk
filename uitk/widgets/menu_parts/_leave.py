# !/usr/bin/python
# coding=utf-8
"""Hide on leave: dismiss the menu once the pointer has left it and its popups.

A 100 ms poll (armed on show) tests whether the pointer is still over the menu
or any *transient* child popup it adopted (an option-menu dropdown, a context
menu, a value popup -- ``adopt_transient``), with a grace for crossing the gap
to a child and a longer one for a menu that opened away from the cursor. An
in-progress text edit inside the menu holds it open.

One part of :class:`~uitk.widgets.menu.Menu`, which inherits it; it holds no
state of its own (``Menu.__init__`` declares every attribute used here) and
is never instantiated alone.
"""

import os
import weakref
from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

# Opt-in live diagnostic for hide_on_leave. Set UITK_MENU_LEAVE_DEBUG=1 (e.g.
# via Maya.env so it is present before uitk imports) to have every leave-poll
# tick log why a menu stays open or hides — the only reliable way to pin down a
# real-platform "won't hide" symptom that does not reproduce offscreen. See
# Menu._check_cursor_position.
_LEAVE_DEBUG = bool(os.environ.get("UITK_MENU_LEAVE_DEBUG"))


class _MenuLeaveMixin:
    """Hide on leave: dismiss the menu once the pointer has left it and its popups."""

    @property
    def hide_on_leave(self) -> bool:
        """Get whether menu auto-hides when mouse leaves.

        Returns:
            bool: True if menu auto-hides on leave, False otherwise
        """
        return self._hide_on_leave

    @hide_on_leave.setter
    def hide_on_leave(self, value: bool) -> None:
        """Set whether menu auto-hides when mouse leaves.

        Parameters:
            value: True to enable auto-hide on leave, False to disable
        """
        self._hide_on_leave = bool(value)

        if self._hide_on_leave:
            if self._leave_timer is None:
                self._setup_leave_timer()
        else:
            if self._leave_timer is not None:
                self._leave_timer.stop()
                self._leave_timer.deleteLater()
                self._leave_timer = None

    def _ensure_timer_created(self):
        """Ensure timer is created if hide_on_leave is enabled (called on first show)."""
        if self.hide_on_leave and self._leave_timer is None:
            self._setup_leave_timer()
            self.logger.debug(
                "Menu._ensure_timer_created: Timer created for hide_on_leave"
            )

    def _setup_leave_timer(self):
        """Set up timer for auto-hide on mouse leave."""
        self._leave_timer = QtCore.QTimer(self)
        self._leave_timer.setInterval(100)  # Check every 100ms
        self._leave_timer.timeout.connect(self._check_cursor_position)

    def _arm_leave_timer(self):
        """Start the leave-poll timer after showEvent's initial grace period."""
        if self._leave_timer:
            self._leave_timer.start()

    def _widget_in_subtree(self, widget: Optional[QtWidgets.QWidget]) -> bool:
        """True when *widget* is this menu or any descendant of it.

        Walks the QObject parent chain (not the visual-ancestor test) so it
        also matches widgets living in a *separate top-level popup* opened from
        inside the menu — a ComboBox dropdown, an option-box ⋯ menu — whose
        chain crosses the window boundary back to ``self``. ``isAncestorOf``
        is same-window-only and misses those.
        """
        w = widget
        while w is not None:
            if w is self:
                return True
            w = w.parent()
        return False

    # ------------------------------------------------------------------
    # Transient popup family (hover-coordinated child popups)
    # ------------------------------------------------------------------

    def adopt_transient(self, child: QtWidgets.QWidget) -> None:
        """Keep this menu open while the pointer is over *child*.

        Registers a child popup — an option-menu dropdown, a context menu, a
        value popup, a nested ``Menu`` — as part of this menu's *transient
        family*. While any adopted child is visible, ``hide_on_leave`` treats
        the pointer being over that child (by window geometry OR by QObject
        subtree) as "still inside", and hiding this menu cascades to the child.

        Ownership here is logical, not a QObject relationship: child popups are
        frequently parented to the wrapped widget (a sibling of this menu) for
        lifetime/positioning reasons, which puts them outside this menu's
        subtree. Adoption re-establishes the relationship so the existing
        subtree check (:meth:`_widget_in_subtree`) becomes one special case of
        a broader "is the pointer in my family?" test.

        Children are held weakly and pruned lazily, so one destroyed or hidden
        without notice is cleaned up on next access — a child that dies can
        never wedge this menu open. Adoption is idempotent. The first adoption
        raises :attr:`leave_grace_samples` so a brief gap-crossing toward the
        child does not dismiss this menu.

        Parameters:
            child: The top-level popup widget to adopt. ``self`` and
                non-widgets are ignored.
        """
        if not isinstance(child, QtWidgets.QWidget) or child is self:
            return
        for ref in self._transient_children:
            if ref() is child:
                return  # already adopted
        self._transient_children.append(weakref.ref(child))
        # Prompt pruning when the child reports it hid (optional — lazy pruning
        # in _living_transients is the correctness guarantee; this just keeps
        # the list tidy). Menu exposes on_hidden; plain popups may not.
        on_hidden = getattr(child, "on_hidden", None)
        if on_hidden is not None and hasattr(on_hidden, "connect"):
            try:
                on_hidden.connect(self._prune_transients)
            except (RuntimeError, TypeError):
                pass
        # A newly adopted child means the user is heading toward it: clear any
        # in-flight leave count and give this menu the gap-crossing grace.
        self._outside_samples = 0
        self.leave_grace_samples = max(self.leave_grace_samples, 3)
        self.logger.debug(f"adopt_transient: adopted {child!r}")

    def _living_transients(self):
        """Yield adopted children still alive (valid C++ object), pruning the rest."""
        survivors = []
        for ref in self._transient_children:
            child = ref()
            if child is None:
                continue
            try:
                child.isVisible()  # cheap touch — raises if the C++ object is gone
            except RuntimeError:
                continue
            survivors.append(ref)
            yield child
        self._transient_children = survivors

    def _prune_transients(self) -> None:
        """Drop dead/deleted children from the registry."""
        list(self._living_transients())

    def _iter_transient_family(self, _seen: Optional[set] = None):
        """Yield this menu and every living adopted descendant, recursively.

        Guarded against cycles (``_seen``) so an accidental mutual adoption
        can't spin the 100 ms leave-poll into an infinite loop.
        """
        if _seen is None:
            _seen = set()
        if id(self) in _seen:
            return
        _seen.add(id(self))
        yield self
        for child in self._living_transients():
            sub = getattr(child, "_iter_transient_family", None)
            if callable(sub):
                yield from sub(_seen)
            elif id(child) not in _seen:
                _seen.add(id(child))
                yield child

    def _pointer_in_family(self, global_pos: Optional[QtCore.QPoint] = None) -> bool:
        """True when the pointer is over this menu or any adopted transient.

        Generalizes the rect + subtree test in :meth:`_check_cursor_position`
        to the whole popup family: a hit on any visible family member's window
        geometry, or on any widget whose QObject parent chain leads back into a
        family member, keeps the menu open.
        """
        if global_pos is None:
            global_pos = QtGui.QCursor.pos()
        widget_at = QtWidgets.QApplication.widgetAt(global_pos)
        for member in self._iter_transient_family():
            try:
                if not member.isVisible():
                    continue
                # Map global → member-local and test the local rect. This is
                # coordinate-system agnostic: it is correct whether the member
                # is a top-level Tool window OR a child widget (e.g. a menu
                # parented into the fullscreen marking-menu overlay), and across
                # multi-monitor offsets. frameGeometry() would only be global
                # for top-levels and could otherwise falsely report "inside",
                # wedging hide_on_leave permanently open.
                if member.rect().contains(member.mapFromGlobal(global_pos)):
                    return True
            except RuntimeError:
                continue
            in_subtree = getattr(member, "_widget_in_subtree", None)
            if callable(in_subtree) and in_subtree(widget_at):
                return True
        return False

    def _hide_transient_children(self) -> None:
        """Hide every adopted child (cascade) and clear the registry."""
        if not self._transient_children:
            return
        for child in list(self._living_transients()):
            try:
                child.hide()
            except RuntimeError:
                pass
        self._transient_children = []

    # Widget types whose focus means the user is actively entering a value, so
    # a stray mouse-leave must not tear the menu down mid-edit. The inline
    # preset Save/Rename field is a ``QLineEdit`` (an editable ComboBox focuses
    # its internal ``QLineEdit``); spin boxes edit through ``QAbstractSpinBox``.
    # Non-text widgets (buttons, plain combos, checkboxes) are intentionally
    # excluded — a click that merely parks focus on one of them must still let
    # the fast hide-on-leave fire when the cursor leaves.
    _EDIT_FOCUS_TYPES = (
        QtWidgets.QLineEdit,
        QtWidgets.QTextEdit,
        QtWidgets.QPlainTextEdit,
        QtWidgets.QAbstractSpinBox,
    )

    def _text_edit_in_progress(self) -> bool:
        """True when a *text-entry* widget inside this menu's subtree has focus.

        Used to suppress ``hide_on_leave`` while the user is actively editing
        one of the menu's widgets — e.g. typing a new name into the preset
        combo's inline Save/Rename line edit. Without this guard a transient
        mouse-leave hid the popup mid-edit, ending the edit prematurely and (on
        a Save seeded with the active preset's own name) silently overwriting
        that template with its unchanged name before the user could retype it.
        """
        app = QtWidgets.QApplication.instance()
        if app is None:
            return False
        focus = app.focusWidget()
        return isinstance(focus, self._EDIT_FOCUS_TYPES) and self._widget_in_subtree(
            focus
        )

    def _demote_editor_autofocus(self) -> None:
        """Stop editor items from passively auto-grabbing keyboard focus.

        A spin box / line edit added to a ``hide_on_leave`` menu defaults to a
        focus policy that includes Tab/activation focus, so it grabs keyboard
        focus the instant the menu is shown and activated — even though the user
        never engaged it. That makes :meth:`_text_edit_in_progress` read True and
        wedges the menu open against ``hide_on_leave`` (the field bug where a
        spin-box option menu — e.g. *Merge* — "never hides" while a checkbox-only
        one — e.g. *Separate* — does). Demoting such editors to ``ClickFocus``
        drops only the *passive* auto-focus: click-to-edit and an explicit
        ``setFocus`` still work, so deliberate editing (the preset inline rename)
        stays protected. Idempotent; only touches ``hide_on_leave`` menus.
        """
        if not self.hide_on_leave:
            return
        # Policies that already don't passively auto-focus. Everything else
        # (TabFocus / StrongFocus / WheelFocus) is demoted. Equality membership
        # rather than a bitwise `& TabFocus` so it's safe across PySide2 and
        # PySide6's stricter enums (Maya 2025 ships 6.5.3).
        no_autofocus = (QtCore.Qt.NoFocus, QtCore.Qt.ClickFocus)
        for item in self.get_items():
            try:
                if (
                    isinstance(item, self._EDIT_FOCUS_TYPES)
                    and item.focusPolicy() not in no_autofocus
                ):
                    item.setFocusPolicy(QtCore.Qt.ClickFocus)
            except RuntimeError:
                pass

    def _check_cursor_position(self):
        """Check if cursor is outside menu bounds and hide if so.

        Only hides if the mouse has entered the menu at least once.
        This prevents immediate hiding when menu is positioned away from cursor.
        Also respects the pinned state — won't hide if pinned — and never hides
        while keyboard focus is on one of the menu's widgets (an in-progress
        edit), so a stray mouse-leave can't dismiss the popup mid-interaction.
        """
        if not self.isVisible():
            self._leave_timer.stop()
            return

        if _LEAVE_DEBUG:
            self._log_leave_state()

        # Don't hide if menu is pinned
        if self.is_pinned:
            self._outside_samples = 0
            return

        # Check the whole popup family, not just this window: the pointer counts
        # as "inside" when it is over this menu OR any adopted transient child
        # (an option-menu dropdown, a context menu, a value popup) — by window
        # geometry or by the QObject subtree walk that catches separate
        # top-level popups parented back under a family member. See
        # _pointer_in_family / adopt_transient.
        if self._pointer_in_family():
            if not self._mouse_has_entered:
                self.logger.debug("_check_cursor_position: Pointer entered menu family")
            self._mouse_has_entered = True
            self._outside_samples = 0
            return

        # Outside the whole family. Before hiding, honor active text entry: if a
        # line edit / spin box inside the menu has focus the user is mid-edit —
        # tearing the menu down here is what produced the accidental preset
        # overwrite. The menu still hides normally once the edit ends.
        if self._text_edit_in_progress():
            self._outside_samples = 0
            return

        # The pointer is outside the whole family. Count consecutive outside
        # samples and hide once they exceed the grace. Two graces apply:
        #   * entered → a deliberate leave: hide after ``leave_grace_samples``
        #     (default 1 = immediate; raised once a child is adopted to bridge
        #     the gap the pointer crosses between this menu and a child popup).
        #   * never entered → the menu opened away from the cursor and the user
        #     hasn't reached it: hide after the longer ``unentered_grace_samples``
        #     (time to reach it) so an opened-but-ignored hide_on_leave menu
        #     still auto-dismisses instead of lingering forever.
        self._outside_samples += 1
        threshold = (
            max(1, self.leave_grace_samples)
            if self._mouse_has_entered
            else max(1, self.unentered_grace_samples)
        )
        if self._outside_samples >= threshold:
            self.logger.debug(
                "_check_cursor_position: Pointer outside family (entered=%s), hiding",
                self._mouse_has_entered,
            )
            self.hide()
            self._leave_timer.stop()

    def _log_leave_state(self) -> None:
        """Log the hide_on_leave decision state for the current poll tick.

        Active only when ``UITK_MENU_LEAVE_DEBUG`` is set. Names exactly which
        gate is keeping the menu open so a real-session capture can pinpoint a
        "won't hide" symptom that does not reproduce offscreen. Read it as:

        * ``hol=False``           → hide_on_leave is off (nothing to do).
        * ``timer=False``         → the leave poll isn't running.
        * ``pinned=True``         → is_pinned (prevent_hide or header pin) blocks it.
        * ``entered=False``       → cursor never entered; the menu won't hide
                                    until it has (it opened away from the cursor).
        * ``in_family=True`` with ``self_rect=False`` and ``children=0`` → kept
          open by the QObject-subtree walk; ``widgetAt`` names the offending
          widget (a stale/unexpected hit, e.g. under the marking menu's grab).
        """
        try:
            gpos = QtGui.QCursor.pos()
            wa = QtWidgets.QApplication.widgetAt(gpos)
            self_hit = self.rect().contains(self.mapFromGlobal(gpos))
            in_family = self._pointer_in_family(gpos)
            wa_name = f"{type(wa).__name__}({wa.objectName() or '-'})" if wa else "None"
            wa_win = wa.window().objectName() or "-" if wa is not None else "-"
            children = sum(1 for _ in self._living_transients())
            timer_on = bool(self._leave_timer and self._leave_timer.isActive())
            self.logger.warning(
                "[leave] name=%s hol=%s pinned=%s entered=%s timer=%s self_rect=%s "
                "in_family=%s children=%d grace=%s outside=%s widgetAt=%s win=%s",
                self.objectName() or "-",
                self.hide_on_leave,
                self.is_pinned,
                self._mouse_has_entered,
                timer_on,
                self_hit,
                in_family,
                children,
                self.leave_grace_samples,
                self._outside_samples,
                wa_name,
                wa_win,
            )
        except Exception as e:  # diagnostics must never break the poll
            self.logger.warning(f"[leave] diagnostic error: {e}")
