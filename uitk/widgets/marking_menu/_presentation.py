# !/usr/bin/python
# coding=utf-8
"""Showing and hiding: the overlay, standalone windows, and the fade.

``show`` routes a UI name to the overlay (a stacked page) or to a
standalone window; ``hide`` and ``hideEvent`` own every teardown (grab
release, un-dim) so a hide by any path cleans up; and the dim pass fades
the other windows for as long as the overlay is up.

One part of :class:`~uitk.widgets.marking_menu._marking_menu.MarkingMenu`,
which inherits it; it holds no state of its own beyond the class-level
defaults it declares, and is never instantiated alone.
"""

from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

from uitk._bootstrap import Bootstrap
from ._resolver import _MARKING_MENU_TAGS


class _PresentationMixin:
    """Showing and hiding: the overlay, standalone windows, and the fade."""

    def show(
        self, ui: Optional[str] = None, pos=None, force: bool = False, **kwargs
    ) -> QtWidgets.QWidget:
        """Central hub for showing any UI component.

        Args:
            ui (str, optional): The name of the UI to show.
            pos: Position argument passed to windows.
            force (bool): Force the UI to show.
            **kwargs: Additional arguments.

        Returns:
            QtWidgets.QWidget: The displayed widget.
        """
        # If no UI is specified, show the Main Startup Menu (default behavior)
        if ui is None:
            ui = self._bindings.get(self._activation_key_str)

        # If still None, we can't show anything
        if ui is None:
            # If we are just toggling the overlay visibility
            if not self.isVisible():
                super().show()
            return self

        # Resolve the UI object
        try:
            found_ui = self.sb.get_ui(ui)
        except AttributeError as e:
            # get_ui resolves an unknown name through the slot resolver, which
            # raises AttributeError ("Slot class '<name>' not found") for a
            # stale binding target. Degrade to the submenu-cache fallback +
            # logged None return below (mirrors _cached_ui) rather than
            # escaping into the Qt event loop. The lazy load means this can
            # also swallow a real defect in a valid name's module — log the
            # text so that stays diagnosable.
            self.logger.debug(f"get_ui('{ui}') raised AttributeError: {e}")
            found_ui = None
        if not found_ui:
            # Fallback: check submenu cache
            found_ui = self._submenu_cache.get(ui)

        if not found_ui:
            self.logger.error(f"UI '{ui}' not found.")
            return None

        # Initialize if needed
        if not found_ui.is_initialized:
            self._init_ui(found_ui)

        # Determine Type: Marking Menu or Standalone Window?
        is_marking_menu = found_ui.has_tags(_MARKING_MENU_TAGS)

        if is_marking_menu:
            # Heal: an initialized stacked page can come back detached —
            # re-hosted elsewhere as a top-level window (e.g. a standalone
            # launcher that bypassed the hosts_ui claim). is_initialized
            # gates _init_ui to a single run, so without this the page
            # would stay outside the overlay forever: positioned via
            # mapFromGlobal against a window it no longer lives in, wrong
            # chrome, geometry persistence re-engaged.
            if found_ui.parent() is not self:
                self._host_stacked(found_ui)
            return self._show_marking_menu(found_ui, **kwargs)
        else:
            return self._show_window(found_ui, pos=pos, force=force, **kwargs)

    def _do_pending_hide(self) -> None:
        """Execute the deferred hide scheduled by suppress_default_on_reentry.

        Skipped when ``_show_marking_menu`` (or another sync) cleared the
        pending widget — i.e. the user pressed a new button before the
        timer fired and we shouldn't yank the new menu away.

        After hiding, re-establishes the mouse grab and window focus.
        Hiding the child widget can cause Maya / the OS to transfer focus
        to the parent application, which routes the next mouse press to
        the wrong window — symptoms: "press a button, nothing shows;
        press again, then it shows".
        """
        widget = self._pending_hide_widget
        self._pending_hide_widget = None
        if widget is not None and widget is self._current_widget and widget.isVisible():
            widget.hide()
            self._current_widget = None
            if self.isVisible() and self._activation_key_held:
                self.raise_()
                self.activateWindow()
                if self.mouseGrabber() is not self:
                    self.grabMouse()

    def _ensure_fullscreen_on_active_screen(
        self, anchor: Optional[QtCore.QPoint] = None
    ) -> None:
        """Pin the full-screen overlay's GEOMETRY to the screen the menu will
        land on. Geometry only — presenting a hidden overlay is the caller's
        job (``_show_marking_menu`` presents LAST, after the target page is
        current; see the comment there for why the order matters).

        The overlay is a single frameless full-screen window and every menu is
        positioned inside it via ``self.mapFromGlobal(...)``. Qt's
        ``showFullScreen()`` binds the window to whichever screen it currently
        occupies — set once at construction to the parent (Maya) window's
        screen. When Maya is dragged to another monitor the overlay stays
        pinned to the original screen, so a menu anchored on the new monitor
        maps to local coordinates outside the overlay's bounds and silently
        never appears ("shows once, then subsequent shows fail without error").

        Relocate the overlay to the screen containing ``anchor`` (the same
        point ``setCurrentWidget`` positions the menu against, defaulting
        to the cursor) *before* the menu is positioned, so the coordinate
        mapping resolves against the correct window origin.

        Parameters:
            anchor (QPoint, optional): Global point the menu will be anchored
                to. Defaults to the current cursor position.
        """
        if anchor is None:
            anchor = QtGui.QCursor.pos()
        target = (
            QtWidgets.QApplication.screenAt(anchor)
            or QtWidgets.QApplication.primaryScreen()
        )
        handle = self.windowHandle()
        current = handle.screen() if handle is not None else None

        # Relocate only when the overlay is *confirmed* to be on a different
        # screen than the active one. Single-monitor and indeterminate cases
        # (no window handle / no screens) are a strict no-op.
        # (current is not None already implies handle is not None.)
        if target is not None and current is not None and current is not target:
            # Drop the full-screen state so the geometry can move across
            # screens, relocate, then re-assert full-screen on the target —
            # but re-present here only when already visible (the mid-gesture
            # monitor hop). A hidden overlay is presented by the caller after
            # the page swap — and its move must reach the NATIVE window
            # (_move_hidden_overlay): the caller's pre-present centering maps
            # the anchor via mapFromGlobal, which on Qt 6.10 reads a native
            # position a hidden QWidget.setGeometry never updates.
            self.setWindowState(self.windowState() & ~QtCore.Qt.WindowFullScreen)
            handle.setScreen(target)
            if self.isHidden():
                self._move_hidden_overlay(target.geometry())
            else:
                self.setGeometry(target.geometry())
                self.showFullScreen()

    def _show_marking_menu(self, widget, **kwargs):
        """Internal handler for showing marking menus."""
        # Cancel any pending suppress-hide so we don't pull the new menu away.
        self._pending_hide_widget = None

        # Startmenus shown mid-gesture (chord transitions like F12 → F12+LMB
        # → F12) anchor to the gesture's origin so the menu doesn't follow
        # cursor jitter between presses. The first show of each activation
        # cycle anchors at the cursor and becomes that gesture's origin.
        is_startmenu = widget.has_tags("startmenu")
        new_gesture = is_startmenu and self.overlay.path.is_empty
        # Resolve the anchor ONCE so every consumer — screen selection, the
        # centering, a new gesture's origin, and the cold-show re-center
        # below — reads the same point (a fresh cursor re-read at each step
        # can drift a few px between them).
        anchor = (
            self.overlay.path.start_pos
            if is_startmenu and not new_gesture
            else QtGui.QCursor.pos()
        )

        # Multi-monitor: assign the overlay's screen/geometry for the anchor's
        # screen before positioning the menu (see method docstring). Must run
        # before setCurrentWidget, which maps the global anchor into the
        # overlay's local space — same anchor, so both resolve to the same
        # screen. Geometry only; a hidden overlay is presented last, below.
        self._ensure_fullscreen_on_active_screen(anchor)

        # A cold page's first-show init (register_children slot wiring, QSS
        # polish, content fit) is delivered by the PRESENT below — after the
        # centering — so its geometry still settles afterwards; remember and
        # re-center then. Preloaded pages (preload_menus) never hit this.
        first_show = not getattr(widget, "is_initialized", True)

        self.setCurrentWidget(widget, anchor=anchor)

        if new_gesture:
            self.overlay.start_gesture(anchor)

        if (
            self._suppress_default_on_reentry
            and self._activation_key_held
            and self._activation_key_str is not None
            and widget.objectName() != self._bindings.get(self._activation_key_str)
        ):
            self._non_default_shown = True

        # Present LAST — a hidden overlay becomes visible only after the
        # target page is current. The overlay is a translucent (layered)
        # window: when re-shown, the OS re-presents its last composed frame
        # and Qt only replaces it on the first repaint after the show.
        # Presenting before the page swap therefore flashed the PREVIOUS
        # gesture's surface on every reopen — e.g. the submenu a standalone
        # tool was launched from — until the new page painted. (The
        # mid-gesture monitor hop re-presents inside
        # _ensure_fullscreen_on_active_screen: already visible, no reopen
        # seam. Guarded by test_marking_menu_present_order.py.)
        if self.isHidden():
            self.showFullScreen()
            if first_show and getattr(widget, "is_initialized", False):
                # The present just delivered the page's first showEvent, so
                # its settled geometry differs from what the centering above
                # measured ("first press feels uninitialized": mis-centered,
                # then visibly snaps). Re-center on the SAME anchor and
                # refresh the tracking cache for the just-registered
                # children. Once per page ever — and never for preloaded
                # pages, whose first show was flushed at warm-up.
                self._position_current_widget(anchor)
                self.mouse_tracking.update_child_widgets()
            # Push the freshly-composed frame NOW. The show presents the
            # retained buffer (cleared by hide()'s flush — invisible, not
            # stale), and without this forced repaint the real menu waits on
            # the HOST's next paint cycle — a user-visible gap under a busy
            # DCC event loop.
            self.repaint()

        self.raise_()
        self.activateWindow()

        self.sb.current_ui = widget
        return widget

    def _show_window(self, widget, pos=None, force=False, **kwargs):
        """Internal handler for showing standalone windows."""
        if self._input_logging_on:
            self.logger.debug(
                f"[handoff] _show_window START target={widget.objectName()!r} "
                f"force={force} | {self._input_state()}"
            )
        # Ensure the widget won't be hidden alongside the MarkingMenu.
        if widget.parent() is self:
            widget.setParent(self.parent(), QtCore.Qt.Window)

        # When launched from another visible standalone window, reparent the
        # target to it so Qt window-group management keeps the new window
        # above the launching window.  Without this they are siblings and the
        # OS can freely reorder them.
        invoker = self.sb.active_ui
        if (
            invoker is not None
            and invoker is not self
            and invoker is not widget
            and invoker.isVisible()
            and not invoker.has_tags(_MARKING_MENU_TAGS)
            and widget.parent() is not invoker
        ):
            widget.setParent(invoker, QtCore.Qt.Window)

        # Clear activation state so _sync_menu_to_state won't resolve to
        # an activation-keyed binding (e.g. "Key_F12" → startmenu).
        self._activation_key_held = False
        self._standalone_suppress = True
        self._transitioning_to_window = True
        # hideEvent restores the dim here, before the target window is shown —
        # so the window being launched is never one of the faded ones.
        self.hide()
        self._transitioning_to_window = False

        self.ui_handler.apply_styles(widget)
        self.ui_handler.show(widget, pos=pos or "cursor", force=force)

        # Deferred raise: when super().hide() fires on the MarkingMenu, the
        # OS implicitly gives focus back to the parent (sequencer) before
        # ui_handler.show() can activate the target.  A zero-delay timer runs
        # after all pending events settle, ensuring the target ends up on top.
        QtCore.QTimer.singleShot(0, lambda w=widget: (w.raise_(), w.activateWindow()))
        # Same-delay follow-up (FIFO: runs after the raise above) — captures the
        # post-activation grab/active state, the moment a launched window would
        # be input-dead if a grab survived the handoff. Only scheduled while a
        # repro is being recorded, so no idle timer is queued otherwise.
        if self._input_logging_on:
            QtCore.QTimer.singleShot(
                0,
                lambda w=widget: self.logger.debug(
                    f"[handoff] _show_window POST-RAISE target={w.objectName()!r} | "
                    f"{self._input_state()}"
                ),
            )

        return widget

    def _reset_stacked_pin(self, ui) -> None:
        """Clear a stacked page's pin / prevent-hide so ``hide()`` isn't vetoed.

        ``MainWindow.setVisible`` is pin-gated (a pinned window silently
        refuses ``hide()``), so this must run BEFORE any attempt to hide the
        page — the old hide-then-unpin order left a pinned page in shown-state
        with its pin cleared, and a shown-state child re-shows with the
        overlay on the next present (the "submenu that launched the window
        shows again on the next activation" ghost). No-op for non-stacked
        UIs and for test doubles without the pin surface.
        """
        if not (getattr(ui, "has_tags", None) and ui.has_tags(_MARKING_MENU_TAGS)):
            return
        header = getattr(ui, "header", None)
        if header is not None:
            try:
                header.reset_pin_state()
            except AttributeError:
                # Fallback for headers without reset_pin_state
                if getattr(header, "pinned", False):
                    header.pinned = False
        # Window-level flags, with or without a header. setVisible consults
        # the WINDOW's pin, and Header.reset_pin_state no-ops unless the
        # HEADER believes it's pinned — a desynced (or absent) header would
        # otherwise leave the window pin set and the hide vetoed anyway.
        # Menu-style surfaces use prevent_hide; MainWindow uses set_pinned.
        if getattr(ui, "pinned", False) and hasattr(ui, "set_pinned"):
            ui.set_pinned(False)
        if getattr(ui, "prevent_hide", False):
            ui.prevent_hide = False

    def _hide_stacked_leftovers(self) -> None:
        """Unpin + explicitly hide every stacked page still in SHOWN-state.

        A page that dodged its hide (a pin veto — see :meth:`_reset_stacked_pin`)
        keeps its shown-state and re-shows with the overlay on the next
        present: the stale-menu ghost. The predicate is ``not isHidden()``
        (the child's own state), NOT ``isVisible()`` — under a hidden parent
        every child reports invisible, which would blind the sweep exactly
        when the overlay is already down. Direct children only (pages are
        parented to the overlay by ``addWidget``) — no switchboard
        dependency. Idempotent; called from both :meth:`hide` and
        :meth:`hideEvent` so bypassed hides (a parent ``setVisible(False)``)
        are covered too.
        """
        for child in self.children():
            if (
                isinstance(child, QtWidgets.QWidget)
                and not child.isHidden()
                and getattr(child, "has_tags", None)
                and child.has_tags(_MARKING_MENU_TAGS)
            ):
                self._reset_stacked_pin(child)
                child.hide()

    def dismiss_for_action(self) -> None:
        """End the gesture NOW, because a user action is about to run.

        Not every action a hosted page produces is dispatched by this class. An
        ``ExpandableList`` sublist item is no registered switchboard widget, so
        its release is consumed by the list's own event filter and never reaches
        :meth:`_handle_widget_action` — which is where the hide before a leaf
        fires lives. This is that same hide, reachable by a widget that
        dispatches its OWN input through duck-typed ancestor lookup
        (``ExpandableList._find_host_with``), so one dispatch route cannot end
        the gesture while another silently leaves it live.

        Dismissal cannot be left to the activation key's release. A slot
        routinely opens a blocking, focus-stealing window — a NATIVE file
        dialog, a DCC's own browser — and the keyboard goes with it, so Qt never
        sees the ``KeyRelease`` at all: :meth:`_on_activation_release` does not
        run, and the overlay is stranded on screen (live: Maya, *scene* ▸ Import
        ▸ "Import Blender Scene", the menu sitting under the file dialog until
        the next activation). Whatever ends the gesture therefore has to be the
        DISPATCH, which is synchronous and cannot be swallowed.

        :meth:`hide` is the whole teardown — ``_relinquish_input_control`` drops
        the hold and any mouse grab, ``hideEvent`` restores the dimmed host
        windows — and is a no-op on an already-hidden menu, so this is safe to
        call from every dispatch path, including ones that overlap.

        It exists as a name of its own rather than letting callers probe for
        ``hide`` precisely BECAUSE the lookup is duck-typed: every QWidget has a
        ``hide``, so an ancestor walk searching for it would match the first
        container it met and close some arbitrary parent. This name means one
        thing — *I am a transient surface that a dispatched action dismisses* —
        and only a surface that is one answers to it.
        """
        self.hide()

    def hide(self):
        """Override hide to properly reset stacked widget state."""
        self.logger.debug("MarkingMenu.hide() called")

        # Unpin BEFORE hiding — see _reset_stacked_pin for why the order
        # matters (a pinned page vetoes its own hide()).
        current_ui = self.sb.active_ui
        if current_ui is not None:
            self.logger.debug(
                f"MarkingMenu.hide(): current_ui={current_ui.objectName()}, "
                f"tags={getattr(current_ui, 'tags', None)}"
            )
            self._reset_stacked_pin(current_ui)

        if self.currentWidget():
            self.setCurrentIndex(-1)

        # Sweep any stacked page that dodged its hide (e.g. pinned during a
        # transition). Also run from hideEvent, but a hide() on an ALREADY
        # hidden overlay (retire()) sends no QHideEvent — so this call is
        # what clears a ghost manufactured while hidden.
        self._hide_stacked_leftovers()

        # Flush a CLEARED frame into the window's retained buffer before
        # hiding. The overlay is a layered (translucent) window: the OS
        # re-presents its last composed frame when the window is next shown,
        # and Qt repaints only AFTER that present — so pixels left in the
        # buffer here (the menu just hidden + the gesture trail) flash
        # momentarily on every reopen even though the correct page is
        # already current (the page swap happens while hidden, and hidden
        # windows never repaint). With the pages down and the trail cleared,
        # this synchronous repaint composes an empty translucent frame: the
        # retained buffer becomes invisible instead of stale.
        if self.isVisible():
            self.overlay.clear_paint_events()
            self.repaint()

        # CRITICAL: end the gesture and fully relinquish mouse control before
        # hiding (see _relinquish_input_control). The leaf-click launch path calls
        # hide() then opens a tool window via its slot WITHOUT going through
        # _show_window (the only other place _activation_key_held is cleared), so
        # without this the flag stayed set, the hidden menu's re-grab guards
        # (mousePressEvent / _do_pending_hide) kept/re-acquired the mouse, and the
        # launched window was input-dead (every click went to the hidden menu)
        # until the user tapped the activation key again — which ran this same
        # cleanup via _on_activation_release.
        self._relinquish_input_control()

        super().hide()

        parent = self.parentWidget()
        if parent and not self._transitioning_to_window:
            # Order matters: raise_() first brings window to front, then activateWindow()
            # gives it focus. Reversing this can cause the parent to go behind other apps.
            # Skip when transitioning to a standalone window — the target window
            # will raise itself via ui_handler.show(), and raising the parent here
            # would steal z-order from it.
            parent.raise_()
            parent.activateWindow()

    #: Without a compositor (X11), the screen this overlay covers, snapshotted
    #: as it shows and painted behind the page -- else the whole screen goes
    #: black while the menu is held. None where translucency composites.
    _backdrop = None

    def showEvent(self, event):
        self._backdrop = Bootstrap.screen_backdrop(self)
        super().showEvent(event)

    def paintEvent(self, event):
        if self._backdrop is not None:
            painter = QtGui.QPainter(self)
            painter.drawPixmap(0, 0, self._backdrop)
            painter.end()
        super().paintEvent(event)

    def hideEvent(self, event):
        """Clean up on hide - relinquishes input control even if hide() was bypassed."""
        self._backdrop = None
        # Safety net for a hide that bypassed hide() (e.g. a parent hide /
        # setVisible(False)): run the same full relinquish so the gesture can't
        # stay "live" with a dangling grab — releasing the grab alone left
        # _activation_key_held set, so a re-grab guard could still re-acquire.
        self._relinquish_input_control()
        # The dim only ever runs while this window is visible, so hiding is its
        # symmetric end — whatever the reason for the hide. Keyed to the
        # key_show *release* instead, the fade stuck whenever that release never
        # arrived (see restore_other_windows).
        self.restore_other_windows()
        # Same safety net for shown-state page ghosts: a bypassed hide skips
        # hide()'s sweep, and a pinned page left in shown-state re-shows with
        # the overlay on the next present. isHidden-based, so it works here
        # even though every child already reports isVisible()==False.
        self._hide_stacked_leftovers()
        self._clear_optimization_caches()
        super().hideEvent(event)

    def _clear_optimization_caches(self):
        """Clear optimization caches to prevent memory accumulation."""
        if self._pending_show_timer and self._pending_show_timer.isActive():
            self._pending_show_timer.stop()

        self._in_transition = False

        if len(self._submenu_cache) > 50:
            self._submenu_cache.clear()
        self._last_ui_history_check = None

    def _set_dimmed(self, w, dimmed: bool) -> None:
        """Fade (or restore) a single window/menu, guarded against deletion.

        One primitive for both dimmed targets — top-level MainWindows and
        their open Menus (which are separate Tool windows and so don't inherit
        a parent's composited opacity). The try/except absorbs the case where
        a target's C++ object was destroyed mid-hold (more likely now that
        short-lived menus join the set).

        Where the window system cannot show the fade (native Wayland, X11
        without a compositor) nothing is dimmed: a window that looks untouched
        but ignores clicks is worse than no fade. Restoring always runs.
        """
        if dimmed and not Bootstrap.fades_windows():
            return
        try:
            w.setWindowOpacity(0.15 if dimmed else 1.0)
            w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, dimmed)
        except RuntimeError:
            pass

    def _dim_targets(self):
        """Yield each background window/menu to fade for the current hold.

        Two independent axes:

        * **Windows** — every *visible* loaded window backgrounds, except the
          marking menu's own radial surfaces (``startmenu``/``submenu``), which
          are the active gesture surface and stay bright.
        * **Menus** — the open menus of *every* loaded window, surface-tagged or
          not. A ``Menu`` is a separate top-level Tool window and is never part
          of the radial gesture, so an option-box popup backgrounds whether it
          was launched from a standalone window or hosted on a submenu surface
          (its owner is the surface window, so gating menus on the surface tag
          would wrongly spare it). Menus also outlive their parent's visibility
          (orphaned menus are intentional — hide the window, keep a small tool
          menu open), so iterating ``loaded_ui`` rather than ``visible_windows``
          reaches both the orphaned and the surface-hosted cases.

        ``menus(visible=True)`` reads the registration-time association (the
        WeakSet the menu joined on show); it never triggers lazy menu creation
        and never re-resolves a reparented menu's owner. ``self`` is skipped
        whole — the marking menu dims nothing of its own.
        """
        for win in self.sb.loaded_ui.values():
            if win is self:
                continue
            # The radial surfaces are the active gesture surface — never dim the
            # *window*. But a popup hosted on one (an option-box menu) is not
            # part of the gesture, so its menus still background below.
            if win.isVisible() and not win.has_tags(_MARKING_MENU_TAGS):
                yield win
            yield from win.menus(visible=True)

    def dim_other_windows(self) -> None:
        """Fade every background window and menu, once per hold.

        Once-per-hold snapshot (see ``_dim_snapshot_taken``): only windows and
        menus already open at key_show press are faded; ``self`` and anything
        opened during the hold stay bright. See :meth:`_dim_targets` for what is
        selected and why it spans the menus of hidden parents.
        """
        if not self.isVisible() or self._dim_snapshot_taken:
            return
        self._dim_snapshot_taken = True

        for target in self._dim_targets():
            self._windows_to_restore.add(target)
            self._set_dimmed(target, True)

        if self._windows_to_restore:
            self.logger.debug(f"Dimming other windows: {self._windows_to_restore}")

    def restore_other_windows(self) -> None:
        """Restore everything dimmed by the last :meth:`dim_other_windows`.

        Called from :meth:`hideEvent` — the single owner of the un-dim, so the
        fade can't outlive the overlay no matter how the gesture ended (key
        release, leaf-click launch, standalone-window handoff, a bypassed hide).
        Idempotent: the set is empty after the first pass.

        Why not the key_show release (the bug this replaced): a leaf that
        launches a task hides the menu with the key still held, and in a DCC
        host that key-up is routinely never seen by Qt — the native viewport
        takes focus (see :meth:`GlobalShortcut._on_press`). Every other window
        then stayed at 0.15 opacity AND ``WA_TransparentForMouseEvents`` until
        the user tapped key_show again.
        """
        # Guarded rather than an unconditional sweep: this now runs on EVERY
        # hide, and the no-op case must stay free of both work and log noise
        # (an unconditional line would bury the input-handoff traces).
        if self._windows_to_restore:
            for win in self._windows_to_restore:
                self._set_dimmed(win, False)
            self._windows_to_restore.clear()
            self.logger.debug("Restored previously dimmed windows.")
        self._dim_snapshot_taken = False
