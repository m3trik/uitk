# !/usr/bin/python
# coding=utf-8
"""Pointer and keyboard dispatch: hit-testing, chord releases, the grab.

Resolves what is under the pointer (the logical, not the OS, hit-test),
dispatches a release over an owned item exactly once per gesture, defers
an empty-overlay partial chord release by ``CHORD_RELEASE_TOLERANCE_MS``,
hands the mouse to the page and takes it back, and carries the opt-in
input-handoff diagnostics.

One part of :class:`~uitk.widgets.marking_menu._marking_menu.MarkingMenu`,
which inherits it; it holds no state of its own beyond the class-level
defaults it declares, and is never instantiated alone.
"""

import os
import tempfile
from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

from uitk.widgets.menuButton import MenuButton
from ._resolver import MenuResolver, _MARKING_MENU_TAGS


class _InputMixin:
    """Pointer and keyboard dispatch: hit-testing, chord releases, the grab."""

    # Single-shot latch: a chord release arrives as TWO release events a few ms
    # apart (one per button). Without coalescing, each one dispatches — the
    # trailing release fires a SECOND action (e.g. clicks a leaf of a submenu a
    # nav-button release just opened). v1.0.66's removed _chord_release_timer
    # coalesced the pair into one decision; this latch restores "one dispatch per
    # gesture". Set when an action fires, re-armed on the next press / activation.
    _action_dispatched: bool = False

    # Chord-release tolerance — governs NAVIGATION only, never item selection.
    # A release OVER AN OWNED ITEM always dispatches the click immediately on the
    # first release (see mouseReleaseEvent); this timer is consulted only for a
    # release over EMPTY overlay (the "switch menus by releasing a button"
    # gesture). There, a real-world both-buttons release is imperfect — the two
    # buttons lift a few ms apart, so the first release arrives with the other
    # still held (a "partial"). Acting on that partial immediately would flicker
    # the menu to the one-button menu before the second button lifts. v1.0.66
    # deferred it by a tolerance window (this timer): if the other button also
    # releases within the window it was a both-buttons release (settle on the
    # final all-up release); if it is still held when the window expires it was
    # an intentional switch (→ navigate to the remaining-button menu). Putting
    # this deferral AHEAD of the owned-item dispatch was the regression — it
    # navigated the menu away before the click could land. Tunable; 75 ms matches
    # the proven v1.0.66 value.
    CHORD_RELEASE_TOLERANCE_MS: int = 75
    _chord_release_timer: Optional[QtCore.QTimer] = None
    _chord_pending_buttons: int = 0
    _chord_pending_modifiers: int = 0
    # Explicit on/off for the input-handoff diagnostics (see enable_input_logging).
    # Gates capture that touches Qt hit-testing, so it never runs on the hot event
    # path unless a repro is actively being recorded. NOT the log level: the class
    # logger sits at NOTSET, which makes isEnabledFor(DEBUG) unreliable as a gate.
    _input_logging_on: bool = False

    # ---------------------------------------------------------------------------------------------
    #   Menu Navigation Helpers:

    def _dismiss_external_popups(self, buttons_mask=None) -> None:
        """Dismiss any active popup widgets that are not children of MarkingMenu."""
        if buttons_mask is None:
            buttons_mask = QtWidgets.QApplication.mouseButtons()

        # 1. Simulate Mouse Release to clear Maya's MM or other grabbers
        if buttons_mask != QtCore.Qt.NoButton:
            btn = self._get_priority_button(buttons_mask)
            if btn != QtCore.Qt.NoButton:
                # Find target
                target = QtWidgets.QWidget.mouseGrabber()
                if not target:
                    target = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())

                # Should not send to self or children if we are somehow active (unlikely at this stage)
                if target and not self.isAncestorOf(target):
                    local_pos = target.mapFromGlobal(QtGui.QCursor.pos())
                    # QMouseEvent(type, localPos, globalPos, button, buttons, modifiers)
                    event = QtGui.QMouseEvent(
                        QtCore.QEvent.MouseButtonRelease,
                        QtCore.QPointF(local_pos),
                        QtCore.QPointF(QtGui.QCursor.pos()),
                        btn,
                        QtCore.Qt.NoButton,
                        QtCore.Qt.KeyboardModifier(),
                    )
                    QtWidgets.QApplication.sendEvent(target, event)

        # 2. Close active popup chain
        popup = QtWidgets.QApplication.activePopupWidget()
        attempts = 0
        while popup is not None and attempts < 10:
            # Don't close our own popups
            if self.isAncestorOf(popup):
                break
            popup.hide()
            popup.close()
            popup = QtWidgets.QApplication.activePopupWidget()
            attempts += 1

        # 3. Additional sweep for any visible QMenu that might not be 'activePopupWidget'
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(widget, QtWidgets.QMenu) and widget.isVisible():
                if not self.isAncestorOf(widget):
                    widget.hide()
                    widget.close()

    def _get_priority_button(self, buttons_mask) -> QtCore.Qt.MouseButton:
        """Resolve the primary button from a combination of held buttons."""
        if buttons_mask & QtCore.Qt.RightButton:
            return QtCore.Qt.RightButton
        if buttons_mask & QtCore.Qt.MiddleButton:
            return QtCore.Qt.MiddleButton
        if buttons_mask & QtCore.Qt.LeftButton:
            return QtCore.Qt.LeftButton
        return QtCore.Qt.NoButton

    def _is_logical_descendant(self, ancestor_widget, widget) -> bool:
        """Check if *widget* is a logical descendant of *ancestor_widget*.

        Widgets reparented outside the UI subtree (e.g. ExpandableList
        sublists, window-children to avoid clipping) set a
        ``_logical_ancestor`` attribute pointing to the root widget that
        lives inside the normal widget hierarchy.  This method walks up
        the widget's parent chain looking for that marker.

        Parameters:
            ancestor_widget: The prospective ancestor (e.g. ``current_ui``).
            widget: The widget found under the cursor.

        Returns:
            bool: True if *widget* (or one of its Qt parents) has a
            ``_logical_ancestor`` that *ancestor_widget* is an ancestor of.
        """
        w = widget
        while w is not None:
            logical_root = getattr(w, "_logical_ancestor", None)
            if logical_root is not None:
                return (
                    ancestor_widget.isAncestorOf(logical_root)
                    or logical_root is ancestor_widget
                )
            w = w.parent()
        return False

    def _ui_owns_widget(self, ui, widget) -> bool:
        """True if *widget* belongs to menu *ui* — a direct Qt descendant, or a
        logical descendant (a top-level sublist marked with ``_logical_ancestor``).
        The "is this widget part of the current menu?" test shared by the press
        click-vs-chord classification and the release click dispatch."""
        return ui.isAncestorOf(widget) or self._is_logical_descendant(ui, widget)

    def _owned_item_at(self, pos, current_ui):
        """The owned item of *current_ui* at global *pos*, or ``None``.

        Tries the OS-level :func:`QApplication.widgetAt` first — the only probe
        that can resolve a *logical* descendant (a top-level ExpandableList
        sublist marked with ``_logical_ancestor``) — then a geometric
        ``current_ui.childAt`` fallback.

        The geometric fallback is the fix for the marking menu's central live
        bug: over the menu's ``WA_TranslucentBackground`` overlay, ``widgetAt``'s
        OS ``WindowFromPoint`` falls through the layered window's transparent
        pixels and returns ``None`` even though the cursor is squarely over a
        button. So BOTH the release hit-test (:meth:`_resolve_release_target`) and
        the press click-vs-chord classification (:meth:`_is_menu_item_press`)
        missed, and the gesture fell through to ``_sync_menu_to_state`` and
        navigated away instead of clicking — the intermittent "the menu item under
        the cursor never registers a click, the menu just shifts/switches". It is
        pixel/alpha-dependent (hence "needs several clicks"). ``childAt`` walks the
        widget tree by geometry with no OS window query, so it finds the item
        ``widgetAt`` couldn't. Confirmed live: at a cursor squarely inside a
        button's rect, ``widgetAt`` returned ``None`` while ``childAt`` returned
        the button.
        """
        widget = QtWidgets.QApplication.widgetAt(pos)
        if (
            widget is not None
            and widget is not self
            and widget is not current_ui
            and self._ui_owns_widget(current_ui, widget)
        ):
            return widget
        child = current_ui.childAt(current_ui.mapFromGlobal(pos))
        if (
            child is not None
            and child is not current_ui
            and self._ui_owns_widget(current_ui, child)
        ):
            return child
        return None

    def _handle_widget_action(self, widget, global_pos=None) -> bool:
        """Execute action for a widget (button click or menu navigation).

        Args:
            widget: The widget resolved under the release/click position.
            global_pos: The dispatch position in global coords. Used to resolve a
                container's child at the *event* position rather than the live
                ``QCursor.pos()`` — under a host that pumps Qt from its own loop
                (Blender) the cursor drifts between the physical release and when
                this runs, so the live cursor can land on the wrong child (the
                same drift the release-path hit-test guards against). Falls back to
                the live cursor when not supplied.

        Returns:
            bool: True if action was executed, False if widget is non-interactive.
        """
        # Resolve container to actual child widget
        if hasattr(widget, "derived_type") and widget.derived_type == QtWidgets.QWidget:
            pos = global_pos if global_pos is not None else QtGui.QCursor.pos()
            child = widget.childAt(widget.mapFromGlobal(pos))
            if child:
                widget = child

        # Navigation-button clicks (menu/submenu launchers). Click opens the
        # button's target as a standalone window or a stacked submenu depending
        # on the target UI's own tags.
        if isinstance(widget, MenuButton):
            menu = self._resolve_button_menu(widget)
            if menu:
                # A nav button opens its target as a standalone window or a
                # stacked submenu depending on the target UI's own tags. A
                # category button like 'key' resolves (on release) to the native
                # Maya 'key' menu — an untagged window — so this opens it
                # standalone; a bare submenu target opens in the overlay.
                is_standalone = not menu.has_tags(_MARKING_MENU_TAGS)
                self.show(menu, force=is_standalone)
                return True

        # Emit clicked signal for standard buttons
        if hasattr(widget, "clicked"):
            ui = getattr(widget, "ui", None)
            base_name = getattr(widget, "base_name", lambda: None)()
            ui_is_menu = bool(ui and ui.has_tags(_MARKING_MENU_TAGS))
            if ui_is_menu and base_name != "chk":
                # The leaf's slot actually fires here — a release hitting a leaf
                # whose owning ``ui`` isn't a live menu falls through to the
                # skip-log below instead.
                self.dismiss_for_action()
                widget.clicked.emit()
                return True
            else:
                self.logger.debug(
                    f"[_handle_widget_action] Click skipped for "
                    f"'{widget.objectName()}': ui={ui}, "
                    f"has_tags={ui_is_menu}, base_name='{base_name}'"
                )

        # Handle ExpandableList items (widgets with item_text set by ExpandableList)
        if hasattr(widget, "item_text"):
            parent = widget.parent()
            while parent:
                if hasattr(parent, "on_item_interacted"):
                    self.dismiss_for_action()
                    parent.on_item_interacted.emit(widget)
                    return True
                parent = parent.parent()

        return False

    def _host_mouse_buttons(self):
        """Current mouse-button mask for hover/drag tracking — overridable per host.

        Defaults to Qt's own query. A host whose native event loop owns the mouse
        (Blender's GHOST) overrides this to read the real (physical) button state,
        so ``MouseTracking``'s drag-gated ``track()`` — which reveals the marking
        menu's ``visible_on_mouse_over`` Regions during a grabbed chord gesture —
        still fires when ``QApplication.mouseButtons()`` is blind to GHOST events.
        """
        return QtWidgets.QApplication.mouseButtons()

    def _transfer_mouse_control(self, button, buttons_mask) -> None:
        """Transfer mouse control to this widget by grabbing and synthesizing a press."""
        self.logger.debug(
            f"_transfer_mouse_control: button={button}, buttons_mask={buttons_mask}"
        )

        # Force grab mouse to ensure MarkingMenu receives subsequent move events
        self.grabMouse()

        local_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(local_pos),
            QtCore.QPointF(QtGui.QCursor.pos()),
            button,
            buttons_mask,
            QtCore.Qt.KeyboardModifier(),
        )
        QtWidgets.QApplication.sendEvent(self, event)

    def _is_menu_item_press(self, event) -> bool:
        """True if *event* is a lone-button press over an interactive item
        (a button) of the current start/submenu — i.e. a click to dispatch on
        release, not a chord to resolve.

        Uses the event's own global position (not the live cursor) so it is
        immune to cursor drift under a pumped host event loop (Blender), and
        hit-tests against ``current_ui`` so only presses on *this menu's* items
        count — a press on empty overlay (the chord gesture) returns False. The
        hit-test goes through :meth:`_owned_item_at` (widgetAt + geometric childAt
        fallback): widgetAt alone returns None over the translucent overlay, so a
        single click on a menu item was mis-classified as a chord and navigated
        away instead of clicking — the same bug the release path had.
        """
        # A menu item is left-clicked; Middle/Right are chord selectors, never an
        # item click. Requiring a lone LeftButton keeps every chord (incl. a second
        # concurrent button → count > 1, and bare M/R presses) resolving as a chord.
        if event.button() != QtCore.Qt.LeftButton:
            return False
        if MenuResolver.count_buttons(self._to_int(event.buttons())) != 1:
            return False
        current_ui = self.sb.active_ui
        if not (current_ui and current_ui.has_tags(_MARKING_MENU_TAGS)):
            return False
        target = self._owned_item_at(event.globalPos(), current_ui)
        return isinstance(target, QtWidgets.QAbstractButton)

    # ---------------------------------------------------------------------------------------------
    #   Stacked Widget Event handling:

    def mousePressEvent(self, event) -> None:
        """Handle mouse press: route through the central state-sync."""
        if self._input_logging_on:
            self.logger.debug(
                f"[handoff] mousePressEvent buttons={self._to_int(event.buttons()):#04x} "
                f"widgetAt={self._w_repr(QtWidgets.QApplication.widgetAt(event.globalPos()))} "
                f"| {self._input_state()}"
            )

        # Cancel any pending suppress-hide so we don't yank the menu away
        # right after showing it.
        self._pending_hide_widget = None

        # Re-arm the single-shot dispatch latch: a press is a fresh click intent.
        # (The chord's own L-then-R presses both land before any release, so this
        # never re-arms mid-release-pair.) NOT re-armed on show() — a nav release
        # shows a submenu mid-gesture and must stay latched against the trailing
        # release.
        self._action_dispatched = False
        # A new press supersedes any pending chord-release decision.
        self._cancel_chord_release_timer()

        # A press that lands on an interactive menu item (a leaf or nav button of
        # the current start/submenu) is a CLICK — dispatch it on release; it must
        # never be re-resolved as the F12|Button chord. In Maya the button itself
        # consumes the press so the menu never sees it; over Blender the menu can
        # hold the mouse grab (a chord reach, or a stray re-grab), which routes the
        # press to the menu instead — where the sync below would read
        # buttons=LeftButton (while the key is held) as the chord and navigate away
        # before the leaf can fire (the "dead click", reproduced live in
        # tentacle/test/blender/normals_multiclick_check.py). Skipping the re-grab +
        # sync here lets the release reach _handle_widget_action. This must apply
        # even mid-chord: _is_menu_item_press already excludes a real chord (it
        # requires a lone button over an interactive item of the current menu, so a
        # second concurrent button or a press on empty overlay still resolves as a
        # chord) — the discriminator is position + button count, not a flag.
        if self._is_menu_item_press(event):
            event.accept()
            return

        # Defensive: re-establish mouse grab if it was lost (e.g. after a
        # deferred child-hide caused the host app to claim focus).
        if self._activation_key_held and self.mouseGrabber() is not self:
            self.grabMouse()

        current_ui = self.sb.active_ui
        if current_ui and current_ui.has_tags(_MARKING_MENU_TAGS):
            # Only start a new gesture if there isn't one already — otherwise
            # chord transitions (e.g. holding F12, tapping LMB) would rebind
            # start_pos to the cursor on every press, drifting the menu with
            # hand jitter.
            if self.overlay.path.is_empty:
                self.overlay.start_gesture(event.globalPos())

        self._sync_menu_to_state(
            buttons=self._to_int(event.buttons()),
            modifiers=self._to_int(event.modifiers()),
        )
        event.accept()

    def keyPressEvent(self, event) -> None:
        """Handle key press for non-activation key bindings."""
        if event.key() == self._activation_key:
            super().keyPressEvent(event)
            return

        key_name = self._get_key_name(event.key())
        if key_name:
            target = MenuResolver.resolve_target_menu(
                activation_held=self._activation_key_held,
                activation_key_str=self._activation_key_str,
                buttons=self._to_int(QtWidgets.QApplication.mouseButtons()),
                modifiers=self._to_int(event.modifiers()),
                bindings=self._bindings,
                extra_key=key_name,
            )
            default_name = self._bindings.get(self._activation_key_str)
            if target and target != default_name:
                if self.overlay.path.is_empty:
                    self.overlay.start_gesture(QtGui.QCursor.pos())
                self.show(target, force=True)
                return

        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """ """
        current_ui = self.sb.active_ui
        if current_ui and current_ui.has_tags(_MARKING_MENU_TAGS):
            if event.button() == QtCore.Qt.LeftButton:
                if event.modifiers() == QtCore.Qt.ControlModifier:
                    self.left_mouse_double_click_ctrl.emit()
                else:
                    self.left_mouse_double_click.emit()

            elif event.button() == QtCore.Qt.MiddleButton:
                self.middle_mouse_double_click.emit()

            elif event.button() == QtCore.Qt.RightButton:
                if event.modifiers() == QtCore.Qt.ControlModifier:
                    self.right_mouse_double_click_ctrl.emit()
                else:
                    self.right_mouse_double_click.emit()

        super().mouseDoubleClickEvent(event)

    def _ensure_chord_release_timer(self) -> QtCore.QTimer:
        """Lazily create the single-shot chord-release tolerance timer.

        Lazy (not built in ``__init__``) so subclasses that bypass ``__init__``
        for event-handler-only testing still get it on first use.
        """
        timer = self._chord_release_timer
        if timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._on_chord_release_timeout)
            self._chord_release_timer = timer
        return timer

    def _defer_chord_release(self, event) -> None:
        """Hold a partial NAVIGATION release (one button up, other(s) still held,
        and NOT over an owned item) for the tolerance window instead of navigating
        now.

        The final all-up release within the window cancels this and settles to the
        no-button menu (``_sync_menu_to_state``); if the window expires with a
        button still held it was an intentional switch and
        :meth:`_on_chord_release_timeout` navigates to the remaining-button menu.
        """
        self._chord_pending_buttons = self._to_int(event.buttons())
        self._chord_pending_modifiers = self._to_int(event.modifiers())
        self._ensure_chord_release_timer().start(self.CHORD_RELEASE_TOLERANCE_MS)

    def _cancel_chord_release_timer(self) -> None:
        """Cancel a pending chord-release decision (the gesture resolved)."""
        timer = self._chord_release_timer
        if timer is not None and timer.isActive():
            timer.stop()
        self._chord_pending_buttons = 0

    def _on_chord_release_timeout(self) -> None:
        """The remaining chord button(s) were held past the tolerance — the user
        meant to SWITCH menus, not release both. Navigate to the menu the still-
        held buttons resolve to (the deferred sync the partial release skipped)."""
        pending = self._chord_pending_buttons
        self._chord_pending_buttons = 0
        if pending:
            self._sync_menu_to_state(
                buttons=pending, modifiers=self._chord_pending_modifiers
            )

    def _defer_partial_or_settle(self, event, current_ui) -> bool:
        """Classify a NAVIGATION release as a *partial* chord release (defer) or
        the final release (settle). Both release handlers call this ONLY after
        ruling out a release over an owned item (which dispatches immediately) —
        so this governs the "switch menus by releasing a button" gesture, never
        item selection.

        Returns True when the release left a button still held over a
        start/submenu: it is deferred by the tolerance window and the caller must
        consume the event. Returns False for the final all-up release (or a plain
        single-button release), having cancelled any pending decision first, so
        the caller proceeds to navigate (``_sync_menu_to_state``).
        """
        if (
            self._to_int(event.buttons()) != 0
            and current_ui
            and current_ui.has_tags(_MARKING_MENU_TAGS)
        ):
            self._defer_chord_release(event)
            return True
        self._cancel_chord_release_timer()
        return False

    def _resolve_release_target(self, event, current_ui):
        """Resolve the owned menu item under a release, returning ``(widget, pos)``.

        Probes the release EVENT position first (the OS release point, immune to
        cursor drift under a host that pumps Qt from its own loop — Blender), then
        the LIVE cursor (:func:`QtGui.QCursor.pos`). Each position is resolved via
        :meth:`_owned_item_at` (widgetAt + the geometric childAt fallback that
        fixes the translucent-overlay miss).

        Returns ``(None, None)`` when no position is over an owned item.
        """
        for source, pos in (
            ("event", event.globalPos()),
            ("cursor", QtGui.QCursor.pos()),
        ):
            widget = self._owned_item_at(pos, current_ui)
            if widget is not None:
                return widget, pos
        return None, None

    @staticmethod
    def _clear_button_down(*widgets) -> None:
        """Clear a stuck ``down`` state on any :class:`QAbstractButton` given.

        A press over an owned menu item is deliberately left to the button
        itself (see :meth:`mousePressEvent`'s ``_is_menu_item_press`` early
        return), so Qt sets the button ``down``. The matching release, however,
        is dispatched through :meth:`_handle_menu_item_release` and CONSUMED —
        it never reaches the button's own ``mouseReleaseEvent``, which is the
        only thing that would clear ``down`` again. The button then paints
        ``:pressed`` forever once the cursor leaves it (``:hover`` outranks the
        pressed rule while hovered, which is why the stick only shows on
        hover-leave). Called on every release-consume path with both the
        resolved dispatch target and the grab-holding child, since cursor
        drift can make those two different buttons.
        """
        for w in widgets:
            if isinstance(w, QtWidgets.QAbstractButton):
                try:
                    if w.isDown():
                        w.setDown(False)
                except RuntimeError:
                    continue  # underlying C++ object already deleted

    def _handle_menu_item_release(self, pos, widget) -> bool:
        """Dispatch a release that landed on an owned interactive item of the
        current start/submenu — the shared core of :meth:`mouseReleaseEvent`
        (the menu holds the grab) and :meth:`child_mouseButtonReleaseEvent` (the
        grab migrated to the child). Routing both through here keeps the SAME
        gesture giving the SAME result no matter which object holds the grab.

        The item fires IMMEDIATELY on the release, exactly as the proven v1.0.66
        path did (``mouseReleaseEvent`` dispatched ``_handle_widget_action`` on
        the *first* release over an owned widget, with no wait for the other
        chord button). So a *both-buttons-held* release registers the click on
        whichever button lifts first and hides the menu; the trailing release of
        the pair lands on the now-hidden menu and is a harmless no-op.

        Chord *navigation* — releasing a button over empty overlay to drop to
        another menu — is unaffected: that path never reaches here (no owned
        interactive widget under the release), so the caller falls through to
        :meth:`_sync_menu_to_state` and navigates as before.

        ``pos`` is the resolved hit-test position from :meth:`_resolve_release_target`
        (event point or live cursor — whichever found the item), passed to
        ``_handle_widget_action`` so a container resolves its child at the same
        point the item was found.

        Returns True when the release is fully handled and the caller should
        consume it + drop the grab — whether it FIRED the item or SWALLOWED the
        trailing release of an already-dispatched chord. Returns False only when
        the widget is non-interactive, so the caller falls through to its own
        default handling (``_sync_menu_to_state`` / forward).

        A chord release fires this once: the per-gesture ``_action_dispatched``
        latch SWALLOWS the trailing release of the pair (returns True without
        acting) so it cannot dispatch a second action — the nav-button case,
        where the first release opened a submenu without hiding, and the trailing
        release would otherwise click into it OR fall through to sync and hide the
        just-opened submenu. The latch is re-armed on the next press / activation.
        """
        if self._action_dispatched:
            # Trailing release of the chord — swallow it (consume; no second
            # action, and crucially do NOT fall through to sync, which would
            # navigate/hide the menu the first release just settled on).
            self._clear_button_down(widget)
            return True
        # Set BEFORE dispatching so a re-entrant release during _handle_widget_action
        # (e.g. nav-show pumping events) can't slip a second action through.
        self._action_dispatched = True
        if self._handle_widget_action(widget, pos):
            # Consumed: the button's own mouseReleaseEvent will never run, so
            # clear any down state the pass-through press left behind.
            self._clear_button_down(widget)
            return True
        # Non-interactive widget — nothing fired, so un-latch and let the caller
        # fall through to its default handling (and a later real action still fires).
        self._action_dispatched = False
        return False

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse release: dispatch click action or sync menu state."""
        current_ui = self.sb.active_ui
        if self._input_logging_on:
            self.logger.debug(
                f"[handoff] mouseReleaseEvent button={self._to_int(event.button()):#04x} "
                f"widgetAt={self._w_repr(QtWidgets.QApplication.widgetAt(event.globalPos()))} "
                f"current_ui={current_ui.objectName() if current_ui else None!r} | "
                f"{self._input_state()}"
            )

        if current_ui and current_ui.has_tags(_MARKING_MENU_TAGS):
            # Release over an owned interactive item dispatches the click
            # IMMEDIATELY — on the FIRST release of a chord, with NO wait for any
            # other held button. This is the proven v1.0.66 order: it resolved
            # and fired the owned item BEFORE consulting the chord-release timer,
            # and the timer only ever governed the *navigation* case (a release
            # over empty overlay). The regression was deferring this owned-item
            # release through the tolerance window first — the timer then
            # navigated the menu to the remaining-button menu (the "stays open
            # and shifts") before the click could land, so the MenuButton under
            # the cursor never registered. The _action_dispatched latch inside
            # _handle_menu_item_release swallows the trailing release of the
            # pair, so the click fires exactly once.
            #
            # The hit-test resolves at the event position first, then the live
            # cursor — a Maya chord release's globalPos can miss the item the
            # pointer is over (see _resolve_release_target).
            widget, pos = self._resolve_release_target(event, current_ui)

            self.logger.debug(
                f"[mouseReleaseEvent] current_ui={current_ui.objectName()}, "
                f"target={widget.objectName() if widget and hasattr(widget, 'objectName') else widget}, "
                f"grabber={self.mouseGrabber() is self}"
            )

            if widget is not None:
                if self._handle_menu_item_release(pos, widget):
                    self.releaseMouse()
                    event.accept()
                    return
                # owned but non-interactive — fall through to chord handling
            else:
                # Nothing owned under the release. If the pointer is over an
                # unrelated (non-menu) widget, leave the menu state alone; over
                # empty overlay / the menu background, fall through to the chord
                # sync (release-to-navigate).
                probe = QtWidgets.QApplication.widgetAt(event.globalPos())
                if probe is not None and probe is not self and probe is not current_ui:
                    event.accept()
                    return

        # Not over an owned item: this is chord NAVIGATION (release over empty
        # overlay to switch menus). ONLY here does the chord-release tolerance
        # apply — a partial release (a button still held) is deferred so a
        # near-simultaneous both-buttons release doesn't flicker to the
        # one-button menu; the final all-up release navigates below.
        if self._defer_partial_or_settle(event, current_ui):
            event.accept()
            return

        self._sync_menu_to_state(
            buttons=self._to_int(event.buttons()),
            modifiers=self._to_int(event.modifiers()),
        )
        event.accept()

    def _relinquish_input_control(self):
        """End the gesture and release any grab — the full hand-off cleanup run on
        every hide, whether deliberate (:meth:`hide`) or bypassed (:meth:`hideEvent`).

        Clearing ``_activation_key_held`` stops the re-grab guards
        (``mousePressEvent`` / ``_do_pending_hide``) from re-acquiring the mouse
        once the menu is hidden; :meth:`_release_input_grab` drops a grab the menu
        or one of its child buttons still holds.
        """
        if self._input_logging_on:
            self.logger.debug(
                f"[handoff] _relinquish_input_control | {self._input_state()}"
            )
        self._activation_key_held = False
        self._release_input_grab()
        # End the gesture cursor from the widget that is actually being hidden.
        # The overlay's own hideEvent is NOT a dependable trigger in a live DCC
        # host — Qt delivers hide events to the widget being hidden, not
        # reliably down the child chain (the same asymmetry test_expandable_list
        # documents), and a hide() on an already-hidden menu (retire) sends no
        # hide event at all. Overlay's watchdog still backstops every path this
        # one can't see; this just makes the common path instant.
        self.overlay.end_gesture()

    def _release_input_grab(self):
        """Release a mouse grab held by the menu OR one of its child buttons.

        ``hide()`` historically released only a grab held by ``self``, but
        ``MouseTracking`` migrates the grab onto the leaf button under the cursor
        during a drag (``_grab_widget`` → ``widget.grabMouse()``), so a chord that
        ends over a child left that child holding the global grab after the menu
        hid. Checking ``isAncestorOf`` covers both owners.
        """
        grabber = QtWidgets.QWidget.mouseGrabber()
        owned = grabber is not None and (grabber is self or self.isAncestorOf(grabber))
        if self._input_logging_on:
            self.logger.debug(
                "[handoff] _release_input_grab: "
                + (
                    f"releasing {self._w_repr(grabber)}"
                    if owned
                    else f"nothing owned to release (grabber={self._w_repr(grabber)})"
                )
            )
        if owned:
            grabber.releaseMouse()

    # ---------------------------------------------------------------------------------------------
    #   Input-handoff diagnostics
    #
    #   The "standalone window launched from the menu is input-dead until you tap
    #   key_show again" report is an input-handoff race: a mouse grab held by the
    #   menu (or a child button MouseTracking migrated it to) routes the new
    #   window's clicks back to the hidden menu. These read-only helpers expose
    #   the grab/activation state so a live repro pinpoints *which* object holds
    #   the grab (or rules a grab out) instead of guessing.

    def _w_repr(self, w) -> str:
        """Compact, delete-safe identifier for a widget in input-state logs."""
        try:
            if w is None:
                return "None"
            win = w.window()
            return (
                f"{type(w).__name__}('{w.objectName()}')"
                f"@{type(win).__name__}('{win.objectName()}')"
            )
        except RuntimeError:
            return "<deleted>"

    def _input_state(self) -> str:
        """One-line snapshot of the mouse-grab / activation state, shared by the
        handoff-diagnostic logs (read-only; safe to call from any log site).

        Reports who holds the global mouse grab and where it sits relative to the
        menu (``self`` / ``child`` / ``other`` / ``none``), the live button mask,
        the active window, the ``MouseTracking`` owner, and the menu's re-grab
        flags — the variables that decide whether a launched window takes clicks.
        """
        grab = QtWidgets.QWidget.mouseGrabber()
        mt = getattr(self, "mouse_tracking", None)
        owner = getattr(mt, "_mouse_owner", None) if mt is not None else None
        if grab is self:
            where = "self"
        elif grab is not None and self.isAncestorOf(grab):
            where = "child"
        elif grab is not None:
            where = "other"
        else:
            where = "none"
        return (
            f"grab={self._w_repr(grab)}[{where}] "
            f"buttons={self._to_int(QtWidgets.QApplication.mouseButtons()):#04x} "
            f"active={self._w_repr(QtWidgets.QApplication.activeWindow())} "
            f"mt_owner={self._w_repr(owner)} "
            f"key_held={getattr(self, '_activation_key_held', None)} "
            f"suppress={getattr(self, '_standalone_suppress', None)} "
            f"menu_visible={self.isVisible()}"
        )

    def enable_input_logging(self, path: Optional[str] = None, level="DEBUG") -> str:
        """Tee DEBUG input-handoff logs (this menu + its ``MouseTracking``) to a file.

        The menu and ``MouseTracking`` use separate class-scoped loggers, so this
        raises the level and attaches a file handler on BOTH — otherwise the grab
        migration records emitted by ``MouseTracking`` are missed. Returns the log
        path; stop with :meth:`disable_input_logging`. Reproduce the issue, then
        read the file. Auto-enabled at construction when the ``UITK_INPUT_LOG``
        environment variable names a path.
        """
        if path is None:
            path = os.path.join(tempfile.gettempdir(), "uitk_input_handoff.log")
        for cls in {type(self), type(self.mouse_tracking)}:
            cls.set_log_level(level)
            cls.set_log_file(path, level)
        self._input_logging_on = True
        self.mouse_tracking._input_logging_on = True
        self.logger.debug(f"[input-log] enabled -> {path} | {self._input_state()}")
        return path

    def disable_input_logging(self) -> None:
        """Stop the file logging started by :meth:`enable_input_logging`."""
        self._input_logging_on = False
        self.mouse_tracking._input_logging_on = False
        for cls in {type(self), type(self.mouse_tracking)}:
            cls.set_log_file(None)
