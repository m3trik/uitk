# !/usr/bin/python
# coding=utf-8
"""Moving between menus: hover submenus, transitions, and the child hooks.

A hovered ``MenuButton`` stacks its submenu by moving the whole overlay so
the new page's anchor lands under the cursor (the identity-gated
transition that stops synthetic-enter ping-pong), plus the breadcrumb
clone, the start-menu return, and the event hooks installed on every
child of a hosted page.

One part of :class:`~uitk.widgets.marking_menu._marking_menu.MarkingMenu`,
which inherits it; it holds no state of its own beyond the class-level
defaults it declares, and is never instantiated alone.
"""

from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets
import pythontk as ptk

from uitk.themes.style_sheet import StyleSheet
from uitk.widgets.menuButton import MenuButton
from ._resolver import _MARKING_MENU_TAGS


class _NavigationMixin:
    """Moving between menus: hover submenus, transitions, and the child hooks."""

    _in_transition: bool = False
    # The (from, to) ui names of the hover-nav transition currently executing —
    # the synthetic-enter gate (see child_enterEvent). Class-level default for
    # test fixtures that bypass __init__.
    _transition_swap: tuple = ()
    # Per-instance cache, rebound in __init__. The class-level default exists
    # ONLY as a fallback for test fixtures that bypass __init__ — production
    # instances must never share it: a second instance (dev reload) resolving
    # nav targets through a shared cache dispatches into the old instance's
    # hollowed native-menu wrappers ("MenuButtons stop launching").
    _submenu_cache: dict = {}
    _last_ui_history_check: QtWidgets.QWidget = None
    _pending_show_timer: QtCore.QTimer = None

    # Smooth submenu-transition state: set by _set_submenu, consumed by the
    # _pending_show_timer's _perform_transition, cleared by _debounce_transition.
    _pending_transition_ui: Optional[QtWidgets.QWidget] = None
    _pending_transition_widget: Optional[QtWidgets.QWidget] = None
    _transitioning_to_window: bool = False

    def _debounce_transition(self, clear_pending: bool = False) -> None:
        """Cancel any pending transition to allow a new one to take precedence."""
        if self._pending_show_timer.isActive():
            self._pending_show_timer.stop()
        self._in_transition = False
        if clear_pending:
            self._pending_transition_ui = None
            self._pending_transition_widget = None

    def _set_submenu(self, ui, w) -> None:
        """Set the submenu for the given UI and widget."""
        self._debounce_transition()
        self._in_transition = True

        # Store transition data and schedule execution
        self._pending_transition_ui = ui
        self._pending_transition_widget = w
        self._pending_show_timer.start(8)  # ~120fps timing for very smooth transitions

    def _perform_transition(self) -> None:
        """Execute the scheduled submenu transition."""
        ui = self._pending_transition_ui
        w = self._pending_transition_widget

        # Clear pending references
        self._pending_transition_ui = None
        self._pending_transition_widget = None

        if not ui or not w:
            self._clear_transition_flag()
            return

        # VALIDATION: Abort if user has moved cursor away from the triggering widget
        try:
            cursor_pos = QtGui.QCursor.pos()
            w_rect = QtCore.QRect(w.mapToGlobal(QtCore.QPoint(0, 0)), w.size())
            # Allow a small margin of error (e.g. 5 pixels) for fast movements
            if not w_rect.adjusted(-5, -5, 5, 5).contains(cursor_pos):
                self._clear_transition_flag()
                return
        except RuntimeError:
            self._clear_transition_flag()
            return

        try:
            # The pair being swapped, for the synthetic-enter gate in
            # child_enterEvent: repositioning slides both the departing menu's
            # breadcrumb and the arriving menu's anchor under the cursor, and Qt
            # delivers enter events for them as if the user hovered — navigating
            # on those ping-pongs the two menus forever. Recorded BEFORE the
            # reposition; cleared with the transition flag.
            departing = self.sb.current_ui
            self._transition_swap = (
                departing.objectName() if departing is not None else None,
                ui.objectName(),
            )

            # Preserve overlay path order by adding to path first. ``add``'s
            # return value is the single source of truth for "where was the
            # trigger widget when the user crossed it" — every downstream
            # consumer (smooth positioning, clone placement) reads THIS
            # value rather than re-querying ``w.mapToGlobal`` later, so any
            # intermediate widget-state change (layout-on-hide, style
            # reapply, etc.) can't silently drift the menu out from under
            # the cursor. ``None`` means add was skipped (widget invisible
            # or missing) — smooth positioning falls back to a live read.
            anchor_global = self.overlay.path.add(ui, w)

            # Batch UI initialization and preparation
            if not ui.is_initialized:
                self._init_ui(ui)
            self._prepare_ui(ui)

            # Position submenu smoothly without forcing immediate updates.
            # Pass the path-saved anchor so smooth positioning uses the
            # single source of truth, not a stale re-read of ``w``.
            self._position_submenu_smooth(ui, w, anchor_global=anchor_global)

            # Switch active widget without repositioning (preserving smooth calculations)
            if self._current_widget and self._current_widget != ui:
                self._current_widget.hide()
            self._current_widget = ui
            ui.show()
            ui.raise_()
            self.sb.current_ui = ui
            # Hover-nav committed: this submenu is now current_ui going into the
            # release.

            # Optimize history check and overlay cloning
            self._handle_overlay_cloning(ui)

            # Update mouse tracking to include newly cloned widgets
            self.mouse_tracking.update_child_widgets()

        finally:
            # Clear transition flag after a brief delay to allow smooth completion
            QtCore.QTimer.singleShot(16, self._clear_transition_flag)  # ~60fps timing

    def _position_submenu_smooth(self, ui, w, *, anchor_global=None) -> None:
        """Align ``ui`` so the trigger's pair widget lands at the trigger's
        screen position (pairing: :meth:`_find_pair_widget`).

        ``anchor_global`` is the path-captured global center of the trigger
        widget — the single source of truth for *where the cursor crossed
        the button*. The caller threads this value through from ``path.add``
        so positioning is independent of any widget-state changes that
        happen between path-capture and this call (layout-on-hide, style
        reapply, deferred geometry). When omitted, falls back to a live
        re-read of ``w.mapToGlobal`` — preserves back-compat for callers
        that don't yet know about the path entry.

        Resizes the destination widget to match the launcher's size so the
        button doesn't visually pop to a different size during the
        transition. This is especially important when the launcher lives in
        a layout (e.g. main#startmenu's QVBoxLayout) and the destination
        widget is at fixed geometry — without the resize, the two would
        have different widths and the cursor would land on a visually
        different button.
        """
        try:
            if anchor_global is not None:
                p1 = anchor_global
            else:
                p1 = w.mapToGlobal(w.rect().center())

            w2 = self._find_pair_widget(ui, w)
            if w2:
                self._align_widget_to_global_center(ui, w2, w.size(), p1)

        except Exception as e:
            self.logger.warning(f"Submenu positioning failed: {e}")

    def _find_pair_widget(self, ui, w):
        """Locate the widget in ``ui`` that represents the same node as ``w``.

        ``MenuButton`` pairs are identified by ``target``: the launcher in the
        departing menu and the arriving menu's self-anchor both point at the
        same node, so the target IS the pair identity — the same property
        hover-nav (``submenu_name``) and release-resolution already key on.
        When several candidates share the bare target (a shared submenu
        reached through different filter tags), the full ``submenu_name()``
        disambiguates.

        objectName matching remains only as a fallback for targetless
        widgets: the historical scheme paired launcher and anchor by a
        hand-maintained cross-file numbering convention (every button
        pointing at node X named ``iNNN``), which nothing enforces — menu
        sets that named buttons freely silently lost anchor alignment.
        """
        target = w.target if isinstance(w, MenuButton) else ""
        if target:
            candidates = [b for b in ui.findChildren(MenuButton) if b.target == target]
            if len(candidates) > 1:
                wanted = w.submenu_name()
                candidates = [
                    b for b in candidates if b.submenu_name() == wanted
                ] or candidates
            if candidates:
                return candidates[0]
        return self.sb.get_widget(w.objectName(), ui)

    @staticmethod
    def _align_widget_to_global_center(ui, w2, source_size, target_global_center):
        """Resize ``w2`` to ``source_size`` and move ``ui`` so ``w2``'s global
        center lands at ``target_global_center``.

        The resize preserves ``w2``'s *local* center: ``w2.resize`` keeps
        the top-left fixed and would otherwise shift the local center by
        half the size delta, which then propagates into the ui-move and
        slides every neighboring widget in ``ui`` off its layout position.
        We compensate with an in-place ``w2.move`` so the resize affects
        only ``w2``'s extent, not its position relative to its siblings.

        Returns the ``QPoint`` delta applied to ``ui``.
        """
        old_local_center = w2.rect().center()
        w2.resize(source_size)
        new_local_center = w2.rect().center()
        w2.move(w2.pos() + old_local_center - new_local_center)

        p2 = w2.mapToGlobal(w2.rect().center())
        diff = target_global_center - p2
        ui.move(ui.pos() + diff)
        return diff

    def _handle_overlay_cloning(self, ui) -> None:
        """Handle overlay cloning with optimized history checking."""
        if ui == self._last_ui_history_check:
            return
        ui_history_slice = self.sb.ui_history(slice(0, -1), allow_duplicates=True)
        if ui in ui_history_slice:
            self._last_ui_history_check = ui
            return

        self.overlay.clone_widgets_along_path(ui, self._return_to_startmenu)
        self._last_ui_history_check = ui

    def _clear_transition_flag(self):
        """Clear the transition flag (and the swap pair) to allow new transitions."""
        self._in_transition = False
        self._transition_swap = ()

    def _return_to_startmenu(self) -> None:
        """Return to the start menu, anchoring it at the gesture origin."""
        self._debounce_transition(clear_pending=True)

        start_pos = self.overlay.path.start_pos
        if not isinstance(start_pos, QtCore.QPoint):
            self.logger.warning("_return_to_startmenu called with no valid start_pos.")
            return

        startmenu = self.sb.ui_history(-1, inc="*#startmenu*")
        self._prepare_ui(startmenu, anchor=start_pos)

    def _cached_ui(self, name: str) -> Optional[QtWidgets.QWidget]:
        """Return the UI for *name*, populating the submenu cache on first hit.

        Returns ``None`` for an unresolvable name rather than raising: ``get_ui`` resolves
        an unknown name through the slot resolver, which raises ``AttributeError`` ("Slot
        class '<name>' not found"). Callers (``child_enterEvent``, ``_resolve_button_menu``)
        guard on a falsy result, so honouring the ``Optional`` contract is what lets a nav
        launcher whose target doesn't resolve degrade gracefully instead of crashing the
        hover/click that triggered it. (Catching the resolver's miss — rather than gating on
        ``is_registered_ui`` — keeps programmatically-registered UIs that ``get_ui`` can load
        but that aren't in the *file* registry resolvable.)
        """
        ui = self._submenu_cache.get(name)
        if ui is None:
            try:
                ui = self.sb.get_ui(name)
            except AttributeError:
                return None
            if ui:
                self._submenu_cache[name] = ui
        return ui

    def _resolve_button_menu(self, widget: MenuButton) -> Optional[QtWidgets.QWidget]:
        """Resolve the menu a ``MenuButton`` navigates to (click path).

        Delegates destination resolution to the shared
        ``Switchboard.menu_button_target_name`` SSoT so a click, a hover
        (``child_enterEvent``) and the auto-hide check
        (``menu_button_target_resolves``) all agree. A bare-target nav launcher
        (``target="cameras"``, ``filterTags="lower"``) opens its composed submenu
        ``"cameras#lower#submenu"``; a fully-qualified ``target`` opens directly.
        Previously this resolved the *bare* ``target`` only, so clicking an upper/lower
        nav region raised ``AttributeError`` ("Slot class 'cameras' not found") instead of
        opening the submenu — the "submenus don't launch" report. Matching groupboxes are
        revealed via the filter tags.
        """
        name = self.sb.menu_button_target_name(widget)
        if not name:
            return None
        menu = self._cached_ui(name)
        if menu:
            self.sb.hide_unmatched_groupboxes(menu, widget.filter_tag_list())
        return menu

    # ---------------------------------------------------------------------------------------------

    def add_child_event_filter(self, widgets) -> None:
        """Initialize child widgets with an event filter.

        Parameters:
            widgets (str/list): The widget(s) to initialize.
        """
        filtered_types = [
            QtWidgets.QMainWindow,
            QtWidgets.QWidget,
            QtWidgets.QAction,
            QtWidgets.QLabel,
            QtWidgets.QPushButton,
            QtWidgets.QCheckBox,
            QtWidgets.QRadioButton,
        ]

        for w in ptk.make_iterable(widgets):
            try:
                if (w.derived_type not in filtered_types) or (
                    not w.ui.has_tags(_MARKING_MENU_TAGS)
                ):
                    continue
            except AttributeError:
                continue

            # Fit-to-content resize is NAV-ONLY by default: a MenuButton's label
            # is code/Designer-authored and must never clip, so it is re-fit
            # (center-preserving) to its content hint. Regular slot buttons,
            # labels and checkboxes keep their Designer geometry — an
            # option-box-wrapped widget is instead fitted by its
            # OptionBoxContainer (``_adjust_to_content``), which sizes the
            # whole container (widget + option buttons) around the same center.
            if isinstance(w, MenuButton):
                # Style BEFORE the content-fit measurement — the old order
                # (measure, then style) sized the button from pre-style
                # metrics, freezing an inflated width on hosts whose base
                # style reports a large un-styled button floor (the Blender
                # ~80px CT_PushButton inflation). repolish_tree re-evaluates
                # property-selector QSS stamped after the widget's first
                # polish (stale until an unpolish/polish cycle), so the fit
                # below measures final metrics.
                w.ui.style.set(widget=w)
                StyleSheet.repolish_tree(w)
                self.sb.center_widget(w, padding_x=35)

            if w.type == self.sb.registered_widgets.Region:
                w.visible_on_mouse_over = True

            self.child_event_filter.install(w)

    def _is_popup_menu_child(self, w) -> bool:
        """True if *w* is displayed inside an interactive ``Menu`` popup (e.g. an
        option-box dropdown) rather than directly on this marking menu.

        Option-box controls are real start/submenu slot widgets (their ``.ui`` is
        the submenu) merely *shown* in a popup ``Menu``, so they carry this menu's
        ``child_event_filter``. But that popup owns its own input: running the
        gesture child-handlers on it routes its releases through
        :meth:`_handle_menu_item_release` — whose ``_action_dispatched`` latch,
        left stuck ``True`` by the launching click (a popup press never resets it),
        then SWALLOWS the release so the checkbox never toggles / the combobox
        never selects — and hover-toggles its checkboxes. Such widgets must be
        left to normal Qt input. Gated on the top-level window being a ``Menu`` so
        ExpandableList sublist ToolTips (gesture surfaces, not ``Menu`` windows)
        are unaffected.
        """
        from uitk.widgets.menu import Menu

        try:
            return isinstance(w.window(), Menu)
        except RuntimeError:
            return False

    def child_enterEvent(self, w, event) -> None:
        """Handle the enter event for child widgets."""
        # Skip the gesture behaviour (submenu-open, chk hover-toggle) for a widget
        # shown inside an interactive Menu popup — it owns its own input.
        if not self._is_popup_menu_child(w):
            if isinstance(w, MenuButton) and w.target:
                # Hover opens the button's own submenu — component-specific when the
                # button carries filter tags (the polygons Edge button →
                # "polygons#edge#submenu", not the base "polygons#submenu").
                # Identity gates (no timing heuristics): never re-open the menu the
                # button lives in, the menu that is already current, or either side
                # of the transition currently executing. A transition repositions
                # the window under the cursor and Qt delivers enter events for
                # whatever lands there — the departing menu's breadcrumb, then the
                # arriving menu's own anchor — and navigating on those ping-pongs
                # A->B->A forever (the live "Rigging is unreachable" report). A
                # genuine hover mid-transition targets a THIRD menu and still
                # resolves, as does a real breadcrumb back-hover afterwards.
                submenu_name = w.submenu_name()
                current = self.sb.current_ui
                current_name = current.objectName() if current is not None else None
                blocked = (w.ui.objectName(), current_name, *self._transition_swap)
                submenu = (
                    self._cached_ui(submenu_name)
                    if submenu_name not in blocked
                    else None
                )
                if submenu:
                    self._set_submenu(submenu, w)

            if w.base_name() == "chk" and w.ui.has_tags("submenu") and self.isVisible():
                if isinstance(w, QtWidgets.QAbstractButton):
                    w.toggle()

        super_event = getattr(super(type(w), w), "enterEvent", None)
        if callable(super_event):
            super_event(event)

    def child_leaveEvent(self, w, event) -> None:
        """Handle the leave event for child widgets."""
        if not self._is_popup_menu_child(w) and w.derived_type == QtWidgets.QPushButton:
            self._debounce_transition(clear_pending=True)

        super_event = getattr(super(type(w), w), "leaveEvent", None)
        if callable(super_event):
            super_event(event)

    def child_mouseButtonReleaseEvent(self, w, event) -> bool:
        """Dispatch (or forward) a release delivered to a *grabbed* child.

        During a drag the mouse grab migrates from the MarkingMenu to the
        child button under the cursor (``MouseTracking._handle_mouse_grab``
        captures QPushButtons), so the release lands HERE — on the child's
        event filter — not on :meth:`mouseReleaseEvent`. The grabbed button
        never received a *press* (the chord press went to the overlay), so it
        is not ``down`` and Qt emits no native click: without help, the release
        is a dead click.

        When the child is an interactive item of the current start/submenu, the
        release is routed through the SAME :meth:`_handle_menu_item_release` the
        menu-grab path uses, in the SAME order: the owned item fires IMMEDIATELY
        on the first release, with NO wait for any other held button (the chord
        tolerance governs navigation only — see :meth:`mouseReleaseEvent`), and
        the ``_action_dispatched`` latch swallows the trailing release of the
        pair. Sharing that core keeps the gesture giving the SAME result no matter
        which object holds the grab — and fixes the dead click that regressed when
        the ``_chord_release_timer`` machinery was replaced by
        ``_sync_menu_to_state`` (commit 3b7213e), which left this path a no-op
        pass-through. The two sites are mutually exclusive (menu-grab →
        mouseReleaseEvent; child-grab → here), so there is no double dispatch.

        The target is resolved via :meth:`_resolve_release_target` (event position
        then live cursor), so the click lands on the right item whether the cursor
        drifted off ``w`` under a pumped host loop (Blender) or the chord release's
        event position missed the item the pointer is over (Maya).
        """
        # A control shown inside an interactive Menu popup (option-box dropdown)
        # owns its own input — never route its release through the gesture
        # dispatch. The launching click leaves _action_dispatched stuck True (a
        # popup press never resets it), so _handle_menu_item_release would SWALLOW
        # this release and the checkbox/combobox would never actuate. Returning
        # False lets the release reach the widget's own handler. See
        # _is_popup_menu_child.
        if self._is_popup_menu_child(w):
            return False
        current_ui = self.sb.active_ui
        if self._input_logging_on:
            self.logger.debug(
                f"[handoff] child_mouseButtonReleaseEvent w={self._w_repr(w)} "
                f"widgetAt={self._w_repr(QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos()))} "
                f"current_ui={current_ui.objectName() if current_ui else None!r} | "
                f"{self._input_state()}"
            )
        if current_ui and current_ui.has_tags(_MARKING_MENU_TAGS):
            # Owned item → dispatch the click IMMEDIATELY on the first release,
            # regardless of any other held button (same order as the menu-grab
            # path; the chord tolerance governs navigation only, never an
            # owned-item select). The _action_dispatched latch makes the trailing
            # release of a both-button pair a no-op, so the click fires once.
            widget, pos = self._resolve_release_target(event, current_ui)
            if widget is not None:
                if self._handle_menu_item_release(pos, widget):
                    # Fired — drop the child's grab and consume. The grabbed
                    # child may be a different button than the resolved target
                    # (cursor drift), so clear ITS pass-through-press down
                    # state here as well.
                    self._clear_button_down(w)
                    try:
                        w.releaseMouse()
                    except RuntimeError:
                        pass
                    return True
                return False  # owned but non-interactive — let it fall through

        # Not over an owned item: chord NAVIGATION. A partial release (other
        # button still held) is deferred by the tolerance window; returning True
        # keeps the child's grab so the final release still reaches here.
        if self._defer_partial_or_settle(event, current_ui):
            self._clear_button_down(w)
            return True

        # Not over an owned menu item — forward to the child's own handler when
        # the grab was bypassed (cursor moved off it), as before.
        if not w.underMouse():
            w.mouseReleaseEvent(event)
        return False
