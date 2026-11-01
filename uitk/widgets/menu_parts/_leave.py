# !/usr/bin/python
# coding=utf-8
"""Hide on leave: dismiss the menu once the pointer has left it and its popups.

A 100 ms poll (armed on show) tests whether the pointer is still over the menu
or any *transient* child popup it adopted (an option-menu dropdown, a context
menu, a value popup -- ``adopt_transient``), with a grace for crossing the gap
to a child and a longer one for a menu that opened away from the cursor. An
in-progress text edit inside the menu holds it open.

One part of :class:`~uitk.widgets.menu.Menu` (see ``menu_parts``).
"""

import os
import weakref
from typing import TYPE_CHECKING, Optional

from qtpy import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from uitk.widgets.menu import Menu

# Opt-in live diagnostic for hide_on_leave. Set UITK_MENU_LEAVE_DEBUG=1 (e.g.
# via Maya.env so it is present before uitk imports) to have every leave-poll
# tick log why a menu stays open or hides — the only reliable way to pin down a
# real-platform "won't hide" symptom that does not reproduce offscreen. See
# _MenuLeave.check_cursor_position.
_LEAVE_DEBUG = bool(os.environ.get("UITK_MENU_LEAVE_DEBUG"))


class _MenuLeave:
    """A :class:`Menu`'s hide on leave and its transient popup family.

    Owns the switch, the poll timers, the entered / outside-sample state and
    the adopted children (held weakly). The two grace knobs
    (``leave_grace_samples``, ``unentered_grace_samples``) stay public
    attributes of the menu; the timers fire the menu's own slots.
    """

    # Widget types whose focus means the user is actively entering a value, so
    # a stray mouse-leave must not tear the menu down mid-edit. The inline
    # preset Save/Rename field is a ``QLineEdit`` (an editable ComboBox focuses
    # its internal ``QLineEdit``); spin boxes edit through ``QAbstractSpinBox``.
    # Non-text widgets (buttons, plain combos, checkboxes) are intentionally
    # excluded — a click that merely parks focus on one of them must still let
    # the fast hide-on-leave fire when the cursor leaves.
    EDIT_FOCUS_TYPES = (
        QtWidgets.QLineEdit,
        QtWidgets.QTextEdit,
        QtWidgets.QPlainTextEdit,
        QtWidgets.QAbstractSpinBox,
    )

    def __init__(self, menu: "Menu") -> None:
        self._menu = menu
        # The value behind ``Menu.hide_on_leave`` (see set_enabled).
        self.enabled = False
        self.leave_timer: Optional[QtCore.QTimer] = None
        self.leave_start_timer: Optional[QtCore.QTimer] = None
        self.mouse_has_entered = False
        self.outside_samples: int = 0
        # Transient popup family: child popups (option-menu dropdowns, context
        # menus, value popups) opened from within this menu that should keep it
        # alive while the pointer is over them and be torn down with it. Held
        # weakly and pruned lazily, so a child destroyed/hidden without notice
        # is cleaned up on next access. See adopt_transient / pointer_in_family.
        self.transient_children: list = []  # list[weakref.ref[QWidget]]

    def set_enabled(self, value: bool) -> None:
        self.enabled = bool(value)

        if self.enabled:
            if self.leave_timer is None:
                self.setup_leave_timer()
        else:
            if self.leave_timer is not None:
                self.leave_timer.stop()
                self.leave_timer.deleteLater()
                self.leave_timer = None

    def ensure_timer_created(self):
        """Ensure timer is created if hide_on_leave is enabled (called on first show)."""
        if self._menu.hide_on_leave and self.leave_timer is None:
            self.setup_leave_timer()
            self._menu.logger.debug(
                "Menu._ensure_timer_created: Timer created for hide_on_leave"
            )

    def setup_leave_timer(self):
        """Set up timer for auto-hide on mouse leave."""
        menu = self._menu
        self.leave_timer = QtCore.QTimer(menu)
        self.leave_timer.setInterval(100)  # Check every 100ms
        self.leave_timer.timeout.connect(menu._check_cursor_position)

    def arm_on_show(self) -> None:
        """Start the leave poll after a grace period (from ``showEvent``).

        The grace keeps a menu that appears at the cursor from hiding before
        the cursor reaches its bounds. A QTimer parented to the menu (not a bare
        singleShot) so the deferred call is destroyed along with the menu
        instead of firing into an already-deleted leave timer (singleShot has
        no owner to cancel it).
        """
        if not self.leave_timer:
            return
        if self.leave_start_timer is None:
            menu = self._menu
            self.leave_start_timer = QtCore.QTimer(menu)
            self.leave_start_timer.setSingleShot(True)
            self.leave_start_timer.timeout.connect(menu._arm_leave_timer)
        self.leave_start_timer.start(200)

    def arm_leave_timer(self):
        """Start the leave-poll timer after showEvent's initial grace period."""
        if self.leave_timer:
            self.leave_timer.start()

    def note_shown(self) -> None:
        """Reset the leave state for a fresh show: has the cursor entered yet?"""
        menu = self._menu
        # Check if cursor is already inside menu when it appears
        # This prevents immediate hide-on-leave when menu pops up under cursor
        self.outside_samples = 0
        cursor_pos = menu.mapFromGlobal(QtGui.QCursor.pos())
        if menu.rect().contains(cursor_pos):
            self.mouse_has_entered = True
            menu.logger.debug(
                "showEvent: Cursor already inside menu, marking as entered"
            )
        else:
            # Reset to False when cursor is outside - menu must wait for cursor to enter
            self.mouse_has_entered = False
            menu.logger.debug("showEvent: Cursor outside menu, waiting for entry")

    def stop(self) -> None:
        """Stop the leave poll (the menu hid)."""
        if self.leave_timer and self.leave_timer.isActive():
            self.leave_timer.stop()
            self._menu.logger.debug("hideEvent: Leave timer stopped")

    def widget_in_subtree(self, widget: Optional[QtWidgets.QWidget]) -> bool:
        """True when *widget* is this menu or any descendant of it.

        Walks the QObject parent chain (not the visual-ancestor test) so it
        also matches widgets living in a *separate top-level popup* opened from
        inside the menu — a ComboBox dropdown, an option-box ⋯ menu — whose
        chain crosses the window boundary back to the menu. ``isAncestorOf``
        is same-window-only and misses those.
        """
        menu = self._menu
        w = widget
        while w is not None:
            if w is menu:
                return True
            w = w.parent()
        return False

    # ------------------------------------------------------------------
    # Transient popup family (hover-coordinated child popups)
    # ------------------------------------------------------------------

    def adopt_transient(self, child: QtWidgets.QWidget) -> None:
        menu = self._menu
        if not isinstance(child, QtWidgets.QWidget) or child is menu:
            return
        for ref in self.transient_children:
            if ref() is child:
                return  # already adopted
        self.transient_children.append(weakref.ref(child))
        # Prompt pruning when the child reports it hid (optional — lazy pruning
        # in living_transients is the correctness guarantee; this just keeps
        # the list tidy). Menu exposes on_hidden; plain popups may not. The
        # menu's own slot is connected, so the connection dies with the menu.
        on_hidden = getattr(child, "on_hidden", None)
        if on_hidden is not None and hasattr(on_hidden, "connect"):
            try:
                on_hidden.connect(menu._prune_transients)
            except (RuntimeError, TypeError):
                pass
        # A newly adopted child means the user is heading toward it: clear any
        # in-flight leave count and give this menu the gap-crossing grace.
        self.outside_samples = 0
        menu.leave_grace_samples = max(menu.leave_grace_samples, 3)
        menu.logger.debug(f"adopt_transient: adopted {child!r}")

    def living_transients(self):
        """Yield adopted children still alive (valid C++ object), pruning the rest."""
        survivors = []
        for ref in self.transient_children:
            child = ref()
            if child is None:
                continue
            try:
                child.isVisible()  # cheap touch — raises if the C++ object is gone
            except RuntimeError:
                continue
            survivors.append(ref)
            yield child
        self.transient_children = survivors

    def prune_transients(self) -> None:
        """Drop dead/deleted children from the registry."""
        list(self.living_transients())

    def iter_transient_family(self, _seen: Optional[set] = None):
        """Yield this menu and every living adopted descendant, recursively.

        Guarded against cycles (``_seen``) so an accidental mutual adoption
        can't spin the 100 ms leave-poll into an infinite loop. A child menu is
        walked through its own ``_iter_transient_family``.
        """
        menu = self._menu
        if _seen is None:
            _seen = set()
        if id(menu) in _seen:
            return
        _seen.add(id(menu))
        yield menu
        for child in self.living_transients():
            sub = getattr(child, "_iter_transient_family", None)
            if callable(sub):
                yield from sub(_seen)
            elif id(child) not in _seen:
                _seen.add(id(child))
                yield child

    def pointer_in_family(self, global_pos: Optional[QtCore.QPoint] = None) -> bool:
        """True when the pointer is over this menu or any adopted transient.

        Generalizes the rect + subtree test in :meth:`check_cursor_position`
        to the whole popup family: a hit on any visible family member's window
        geometry, or on any widget whose QObject parent chain leads back into a
        family member, keeps the menu open.
        """
        if global_pos is None:
            global_pos = QtGui.QCursor.pos()
        widget_at = QtWidgets.QApplication.widgetAt(global_pos)
        for member in self.iter_transient_family():
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

    def hide_transient_children(self) -> None:
        """Hide every adopted child (cascade) and clear the registry."""
        if not self.transient_children:
            return
        for child in list(self.living_transients()):
            try:
                child.hide()
            except RuntimeError:
                pass
        self.transient_children = []

    def text_edit_in_progress(self) -> bool:
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
        return isinstance(focus, self.EDIT_FOCUS_TYPES) and self.widget_in_subtree(
            focus
        )

    def demote_editor_autofocus(self) -> None:
        """Stop editor items from passively auto-grabbing keyboard focus.

        A spin box / line edit added to a ``hide_on_leave`` menu defaults to a
        focus policy that includes Tab/activation focus, so it grabs keyboard
        focus the instant the menu is shown and activated — even though the user
        never engaged it. That makes :meth:`text_edit_in_progress` read True and
        wedges the menu open against ``hide_on_leave`` (the field bug where a
        spin-box option menu — e.g. *Merge* — "never hides" while a checkbox-only
        one — e.g. *Separate* — does). Demoting such editors to ``ClickFocus``
        drops only the *passive* auto-focus: click-to-edit and an explicit
        ``setFocus`` still work, so deliberate editing (the preset inline rename)
        stays protected. Idempotent; only touches ``hide_on_leave`` menus.
        """
        if not self._menu.hide_on_leave:
            return
        # Policies that already don't passively auto-focus. Everything else
        # (TabFocus / StrongFocus / WheelFocus) is demoted. Equality membership
        # rather than a bitwise `& TabFocus` so it's safe across PySide2 and
        # PySide6's stricter enums (Maya 2025 ships 6.5.3).
        no_autofocus = (QtCore.Qt.NoFocus, QtCore.Qt.ClickFocus)
        for item in self._menu.get_items():
            try:
                if (
                    isinstance(item, self.EDIT_FOCUS_TYPES)
                    and item.focusPolicy() not in no_autofocus
                ):
                    item.setFocusPolicy(QtCore.Qt.ClickFocus)
            except RuntimeError:
                pass

    def check_cursor_position(self):
        """Check if cursor is outside menu bounds and hide if so.

        Only hides if the mouse has entered the menu at least once.
        This prevents immediate hiding when menu is positioned away from cursor.
        Also respects the pinned state — won't hide if pinned — and never hides
        while keyboard focus is on one of the menu's widgets (an in-progress
        edit), so a stray mouse-leave can't dismiss the popup mid-interaction.
        """
        menu = self._menu
        if not menu.isVisible():
            self.leave_timer.stop()
            return

        if _LEAVE_DEBUG:
            self.log_leave_state()

        # Don't hide if menu is pinned
        if menu.is_pinned:
            self.outside_samples = 0
            return

        # Check the whole popup family, not just this window: the pointer counts
        # as "inside" when it is over this menu OR any adopted transient child
        # (an option-menu dropdown, a context menu, a value popup) — by window
        # geometry or by the QObject subtree walk that catches separate
        # top-level popups parented back under a family member. See
        # pointer_in_family / adopt_transient.
        if self.pointer_in_family():
            if not self.mouse_has_entered:
                menu.logger.debug("_check_cursor_position: Pointer entered menu family")
            self.mouse_has_entered = True
            self.outside_samples = 0
            return

        # Outside the whole family. Before hiding, honor active text entry: if a
        # line edit / spin box inside the menu has focus the user is mid-edit —
        # tearing the menu down here is what produced the accidental preset
        # overwrite. The menu still hides normally once the edit ends.
        if self.text_edit_in_progress():
            self.outside_samples = 0
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
        self.outside_samples += 1
        threshold = (
            max(1, menu.leave_grace_samples)
            if self.mouse_has_entered
            else max(1, menu.unentered_grace_samples)
        )
        if self.outside_samples >= threshold:
            menu.logger.debug(
                "_check_cursor_position: Pointer outside family (entered=%s), hiding",
                self.mouse_has_entered,
            )
            menu.hide()
            self.leave_timer.stop()

    def log_leave_state(self) -> None:
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
        menu = self._menu
        try:
            gpos = QtGui.QCursor.pos()
            wa = QtWidgets.QApplication.widgetAt(gpos)
            self_hit = menu.rect().contains(menu.mapFromGlobal(gpos))
            in_family = self.pointer_in_family(gpos)
            wa_name = f"{type(wa).__name__}({wa.objectName() or '-'})" if wa else "None"
            wa_win = wa.window().objectName() or "-" if wa is not None else "-"
            children = sum(1 for _ in self.living_transients())
            timer_on = bool(self.leave_timer and self.leave_timer.isActive())
            menu.logger.warning(
                "[leave] name=%s hol=%s pinned=%s entered=%s timer=%s self_rect=%s "
                "in_family=%s children=%d grace=%s outside=%s widgetAt=%s win=%s",
                menu.objectName() or "-",
                menu.hide_on_leave,
                menu.is_pinned,
                self.mouse_has_entered,
                timer_on,
                self_hit,
                in_family,
                children,
                menu.leave_grace_samples,
                self.outside_samples,
                wa_name,
                wa_win,
            )
        except Exception as e:  # diagnostics must never break the poll
            menu.logger.warning(f"[leave] diagnostic error: {e}")
