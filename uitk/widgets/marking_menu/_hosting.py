# !/usr/bin/python
# coding=utf-8
"""The pages the overlay hosts: stacking, theming, and warm-up.

Start/submenu UIs are stacked as non-window pages of the fullscreen
overlay and centred on the gesture anchor; standalone windows are handed
to the UI handler. Also the two persisted hosted-window themes and the
scoped preload that makes the first activation behave like every later
one.

One part of :class:`~uitk.widgets.marking_menu._marking_menu.MarkingMenu`,
which inherits it; it holds no state of its own beyond the class-level
defaults it declares, and is never instantiated alone.
"""

from contextlib import contextmanager
from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

from uitk.managers.shortcut_manager import ShortcutManager
from uitk.themes.style_sheet import StyleSheet
from ._resolver import _MARKING_MENU_TAGS


class _HostingMixin:
    """The pages the overlay hosts: stacking, theming, and warm-up."""

    _current_widget: Optional[QtWidgets.QWidget] = None

    # Remaining UI names of an in-flight scoped preload (see preload_menus);
    # None when no warm-up is running.
    _preload_queue: Optional[list] = None

    # ── Hosted-window themes ────────────────────────────────────────────
    # The two window styles this menu hosts were historically hard-pinned to
    # "dark": the radial startmenu/submenu pages (menu_theme) and the standalone
    # tool windows (window_theme). Now user-selectable and persisted per host
    # (Maya/Blender share the QSettings backend — see _binding_store_key for the
    # namespacing rationale). tentacle's preferences exposes both.
    DEFAULT_MENU_THEME = "dark"
    DEFAULT_WINDOW_THEME = "dark"

    def _theme_store(self, kind: str):
        """The persisted ``SettingItem`` for a hosted style ("menu"/"window")."""
        suffix = ShortcutManager.host_namespace_suffix(
            getattr(self.sb, "context_tags", None)
        )
        return getattr(self.sb.configurable, f"marking_menu_{kind}_theme{suffix}")

    @property
    def menu_theme(self) -> str:
        """Theme applied to the radial startmenu / submenu pages."""
        return self._theme_store("menu").get(self.DEFAULT_MENU_THEME)

    @menu_theme.setter
    def menu_theme(self, theme: str):
        self._set_hosted_theme("menu", theme)

    @property
    def window_theme(self) -> str:
        """Theme applied to standalone tool windows."""
        return self._theme_store("window").get(self.DEFAULT_WINDOW_THEME)

    @window_theme.setter
    def window_theme(self, theme: str):
        self._set_hosted_theme("window", theme)

    def resolve_hosted_theme(self, ui) -> str:
        """Theme for *ui* by hosted style — menu page vs standalone window.

        The single source ``UiHandler.apply_styles`` reads, so both styling
        entry points (this menu's ``_host_stacked`` and the handler) agree on
        which of the two configured themes a UI wears.
        """
        try:
            is_menu = ui.has_tags(_MARKING_MENU_TAGS)
        except AttributeError:
            is_menu = False
        return self.menu_theme if is_menu else self.window_theme

    def _set_hosted_theme(self, kind: str, theme: str):
        """Persist *theme* for a hosted style and re-theme its live windows.

        Future loads read the stored value at style time; already-loaded UIs of
        the matching style are re-themed per-widget, so the other style and
        every unrelated window stay untouched.
        """
        if theme not in StyleSheet.themes:
            raise ValueError(
                f"Unknown theme {theme!r}. Available: {list(StyleSheet.themes)}"
            )
        self._theme_store(kind).set(theme)
        want_menu = kind == "menu"
        for ui in list(getattr(self.sb, "loaded_ui", {}).values()):
            try:
                if ui.has_tags(_MARKING_MENU_TAGS) != want_menu:
                    continue
                StyleSheet.set_theme(theme, widget=ui)
            except (AttributeError, RuntimeError):
                continue

    def hosts_ui(self, name: str) -> bool:
        """True when *name* is a stacked page (startmenu/submenu) this menu hosts.

        The hosting claim consumed by ``UiHandler.hosting_handler`` /
        ``launch`` (duck-typed ``hosts_ui``/``show`` contract): a standalone
        launcher (e.g. the SwitchboardBrowser's Launch button) must route
        these pages through :meth:`show` — re-hosting one as a top-level
        window strips the stacked invariants (child-of-overlay parenting,
        borderless style, geometry-persistence opt-out) and, since
        ``is_initialized`` gates ``_init_ui`` to a single run, the page
        never recovers (the "browser-launched startmenu breaks the marking
        menu" bug).

        Registry-level and load-free: a loaded page answers from its live
        tags; an unloaded one from its name-derived plus on-disk XML tags —
        the same tag set :meth:`show`'s stacked-vs-standalone dispatch reads
        once the page is loaded, so the claim and the dispatch can't
        disagree.
        """
        if not name:
            return False
        loaded = getattr(self.sb, "loaded_ui", None)
        ui = loaded.peek(name) if loaded is not None else None
        if ui is not None and getattr(ui, "has_tags", None):
            return bool(ui.has_tags(_MARKING_MENU_TAGS))
        tags = set(self.sb.get_tags_from_name(name) or ())
        get_file_tags = getattr(self.sb, "_get_ui_tags", None)
        if callable(get_file_tags):
            try:
                tags |= set(get_file_tags(name) or ())
            except Exception:  # unresolvable path / bad XML — name tags decide
                pass
        return not tags.isdisjoint(_MARKING_MENU_TAGS)

    def addWidget(self, widget: QtWidgets.QWidget) -> None:
        """Add a widget to the MarkingMenu window.

        Parameters:
            widget (QWidget): The widget to add.
        """
        widget.setParent(self)

    def currentWidget(self) -> Optional[QtWidgets.QWidget]:
        """Get the currently active widget.

        Returns:
            QWidget: The currently active widget, or None if no widget is active.
        """
        return self._current_widget

    def setCurrentWidget(
        self,
        widget: QtWidgets.QWidget,
        *,
        anchor: Optional[QtCore.QPoint] = None,
    ) -> None:
        """Set the current widget and position its center at the given anchor.

        Parameters:
            widget (QWidget): The widget to set as current.
            anchor (QPoint, optional): Global position to align widget's
                center to. Defaults to the current cursor position.
        """
        if self._current_widget:
            self._current_widget.hide()

        self._current_widget = widget
        widget.show()
        widget.raise_()

        # QMainWindow may collapse to 0x0 when reparented as a child widget;
        # use central widget size as a fallback.
        if widget.width() <= 0 or widget.height() <= 0:
            cw = widget.centralWidget() if hasattr(widget, "centralWidget") else None
            if cw and (cw.width() > 0 or cw.height() > 0):
                widget.resize(cw.size())
            else:
                widget.resize(600, 600)

        self._position_current_widget(anchor)

        # Update mouse tracking cache for the new widget
        self.mouse_tracking.update_child_widgets()

    def _position_current_widget(self, anchor: Optional[QtCore.QPoint] = None) -> None:
        """Center the current page on ``anchor`` (global; defaults to the
        cursor). Split from ``setCurrentWidget`` so a cold page can be
        re-centered against its settled geometry after the present delivers
        its first showEvent (see ``_show_marking_menu``) without re-running
        the page swap."""
        widget = self._current_widget
        if widget is None:
            return
        if anchor is None:
            anchor = QtGui.QCursor.pos()
        # Center the widget on the anchor. Marking-menu navigation windows
        # (startmenu/submenu) MUST keep their center pinned to the gesture
        # origin: the directional flick that drives the menu is measured
        # relative to that point, so an on-screen clamp that nudges the menu
        # away from the cursor desyncs the gesture and "breaks the overlay
        # starting position". Those windows opt out via ensure_on_screen=False
        # (set in _init_ui) — and are the only widgets that reach this method
        # today, so in practice the clamp below is skipped. It is kept (not
        # deleted) and gated on the same ensure_on_screen flag MainWindow's
        # _ensure_on_screen honors, so setCurrentWidget stays a correct
        # positioning primitive for any opted-in widget, guarding the case
        # where centering near a screen/monitor edge would spill it off the
        # display.
        global_top_left = anchor - widget.rect().center()
        if getattr(widget, "ensure_on_screen", True):
            screen = (
                QtWidgets.QApplication.screenAt(anchor)
                or QtWidgets.QApplication.primaryScreen()
            )
            if screen is not None:
                ag = screen.availableGeometry()
                # max(ag.left(), ...) guards the degenerate case of a widget
                # wider or taller than the screen (clamp to the top-left corner).
                x = min(global_top_left.x(), ag.right() - widget.width() + 1)
                x = max(ag.left(), x)
                y = min(global_top_left.y(), ag.bottom() - widget.height() + 1)
                y = max(ag.top(), y)
                global_top_left = QtCore.QPoint(x, y)
        widget.move(self.mapFromGlobal(global_top_left))

    def setCurrentIndex(self, index: int) -> None:
        """Set the current widget index (compatibility method).

        Parameters:
            index (int): The index to set. If -1, hides the current widget.
        """
        if index == -1 and self._current_widget:
            self._current_widget.hide()
            self._current_widget = None

    def _host_stacked(self, ui) -> None:
        """(Re)establish the hosting invariants for a stacked page.

        Everything a startmenu/submenu needs to live as a child of this
        overlay: borderless translucent styling, screen-clamp opt-out (the
        centering must stay pinned to the gesture origin — see
        ``_position_current_widget``), geometry persistence off, and
        parenting into the overlay (a plain ``setParent`` also resets any
        window flags a previous host set).

        Called from :meth:`_init_ui` on first load, and from :meth:`show`'s
        heal path when an initialized page comes back detached — e.g. a
        standalone launcher re-hosted it as a top-level window. First-load
        concerns (child event filters, ``on_child_registered`` wiring) stay
        in ``_init_ui``: re-running them here would stack connections.
        """
        ui.style.set(theme=self.menu_theme, style_class="translucentBgNoBorder")
        ui.ensure_on_screen = False
        # Stacked menus are transient — they hide on every transition
        # and reshow on the next gesture. Persisting their geometry via
        # MainWindow's save-on-hide / restore-on-show creates a feedback
        # loop: a transient size saved during a hide gets restored on
        # the next show, which is then re-saved, locking the menu to a
        # tiny restored size (visible as the upper-section-cropped bug).
        # Disable the persistence and discard any previously-saved value.
        ui.restore_window_size = False
        try:
            ui.settings.clear("window_geometry")
        except Exception:
            pass
        self.addWidget(ui)  # add the UI to the stackedLayout.
        # Resize after addWidget (setParent can reset geometry)
        w = max(ui.width(), 600)
        h = max(ui.height(), 600)
        ui.resize(w, h)

    def _init_ui(self, ui) -> None:
        """Initialize the given UI.

        Parameters:
            ui (QWidget): The UI to initialize.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: {type(ui)}, expected QWidget.")

        ui_name = ui.objectName()
        self.logger.debug(
            f"[{ui_name}] _init_ui called, tags={getattr(ui, 'tags', None)}, "
            f"has_header={hasattr(ui, 'header')}"
        )

        if ui.has_tags(_MARKING_MENU_TAGS):  # StackedWidget
            self._host_stacked(ui)
            self.add_child_event_filter(ui.widgets)
            ui.on_child_registered.connect(lambda w: self.add_child_event_filter(w))
            # Stacked menus: No explicit lifecycle setup needed (they hide with parent)

        else:  # Standalone MainWindow
            ui.setParent(self.parent(), QtCore.Qt.Window)

            # Delegate all window setup to UiHandler (styling + lifecycle)
            self.ui_handler.apply_styles(ui)
            self.ui_handler.setup_lifecycle(ui, hide_signal=self.key_show_release)

            # No automatic slot timeout — every slot used to be wrapped in
            # ExecutionMonitor (thread spawn + Esc-cancel listener) which
            # paid that cost for every UI interaction even though the vast
            # majority of slots finish in milliseconds. Heavy operations
            # now opt in explicitly with the ``@Cancelable(timeout=N)``
            # decorator on the slot method, or set ``widget.slot_timeout``
            # at runtime.

    def preload_menus(self, names=None, *, defer: bool = True) -> None:
        """Warm the menus the bindings can reach so the FIRST activation
        behaves exactly like every later one.

        A cold page pays its entire initialization inside the first gesture:
        the .ui load, slot-class instantiation and signal wiring
        (``register_children``), QSS polish, and the content fit — and since
        ``_show_marking_menu`` presents LAST, that first-show work lands
        *after* the page was already centered on the gesture anchor, so the
        menu visibly settles ("the first press feels uninitialized"). This
        runs the same initialization up front through the real show path
        (:meth:`_flush_first_show`), scoped to the distinct binding targets —
        never the whole UI registry, whose standalone tool windows stay lazy.

        Parameters:
            names: Iterable of UI names to warm. Defaults to the distinct
                targets of the current bindings.
            defer: Warm one UI per event-loop tick (default) so a busy host
                stays responsive during startup; ``False`` warms
                synchronously (tests, or hosts preloading behind a splash).

        Idempotent — initialized pages are skipped — so it's safe to re-run
        after a bindings change to warm only the new targets. A live gesture
        owns the overlay: the deferred run waits and retries rather than
        hiding/re-showing it out from under the user.
        """
        if self._retired:
            return
        if names is None:
            names = dict.fromkeys(self._bindings.values())
        queue = [n for n in names if n]
        if not queue:
            return
        merging = self._preload_queue is not None
        if merging:
            self._preload_queue.extend(queue)  # merge into the in-flight run
        else:
            self._preload_queue = queue
        if defer:
            if not merging:  # an in-flight run already has a timer servicing it
                QtCore.QTimer.singleShot(0, self._preload_next)
            return
        # Synchronous drain — including anything an in-flight deferred run
        # still had queued (idempotent, so no double work; its stale timer
        # later finds an empty queue and no-ops).
        try:
            while self._preload_queue:
                self._warm_menu(self._preload_queue.pop(0))
        finally:
            self._preload_queue = None

    def _preload_next(self) -> None:
        """Timer tick of a deferred :meth:`preload_menus` run — warm one UI,
        then yield the event loop before the next."""
        if self._retired or not self._preload_queue:
            self._preload_queue = None
            return
        try:
            busy = self._activation_key_held or self.isVisible()
        except RuntimeError:
            # C++ overlay destroyed without retire() (host teardown / dev
            # reload) while a retry was pending — end the chain quietly
            # instead of raising into the DCC event loop.
            self._preload_queue = None
            return
        if busy:
            # Mid-gesture: the overlay is the user's. Retry once it's idle.
            QtCore.QTimer.singleShot(1000, self._preload_next)
            return
        try:
            self._warm_menu(self._preload_queue.pop(0))
        finally:
            # Continue the chain even if a warm-up raised something
            # _warm_menu didn't swallow — a single bad page must not strand
            # the queue non-None (which would dead-end every later
            # preload_menus call into a chain no timer services).
            if self._preload_queue:
                QtCore.QTimer.singleShot(0, self._preload_next)
            else:
                self._preload_queue = None

    def _warm_menu(self, name: str) -> None:
        """Warm a single stacked menu: resolve, ``_init_ui``, and flush its
        first-show initialization while nothing paints. Failures are logged
        and swallowed — preloading is an optimization and must never break
        the host's startup (an unresolvable target simply stays lazy)."""
        try:
            ui = self.sb.get_ui(name)
        except Exception as e:
            self.logger.debug(f"[preload] {name!r} did not resolve: {e}")
            return
        if ui is None or getattr(ui, "is_initialized", False):
            return
        if not (getattr(ui, "has_tags", None) and ui.has_tags(_MARKING_MENU_TAGS)):
            # Standalone windows (and anything without a tag surface) stay
            # lazy: their show is user-driven and positioned by the
            # ui_handler at launch time.
            return
        if not self.isHidden():
            # A live gesture owns the overlay (synchronous callers only — the
            # deferred path already waits and retries). Warming now would
            # half-run: _flush_first_show no-ops, is_initialized stays False,
            # and the later real show() re-runs _init_ui, stacking a
            # duplicate on_child_registered connection.
            self.logger.debug(f"[preload] overlay visible; {name!r} stays lazy.")
            return
        try:
            self._init_ui(ui)
            self._flush_first_show(ui)
        except Exception as e:
            self.logger.warning(f"[preload] warming {name!r} failed: {e}")

    @contextmanager
    def _suppressed_present(self):
        """Present the overlay under ``WA_DontShowOnScreen`` for the duration
        of the block, then end hidden with the attribute cleared.

        The shared mechanic behind construction's realize-without-presenting
        and :meth:`_flush_first_show`'s warm-up: the native window (and its
        screen bind) is realized, children shown inside the block receive
        genuine show events, and nothing ever maps on screen. The teardown is
        unconditional (``finally``) — a body that raises must not leave the
        overlay shown-but-unmapped (``isHidden()`` False would skip the next
        activation's present) or leak the suppression into a real show. Hide
        is the BASE-class hide: the ``hide()`` override ends by raising/
        activating the host parent — a focus steal when nothing was ever on
        screen; its gesture cleanup is all no-op here, and ``hideEvent``'s
        safety net still runs either way.

        The teardown must also drop ``WindowFullScreen`` from the window
        state — but keep the fullscreen *geometry*. ``hide()`` keeps the
        state, and on Qt 6.10 the next real ``showFullScreen()`` then sees
        "already fullscreen" — no state transition, no fullscreen geometry —
        and maps the overlay at its ~100x30 "normal" geometry at the screen
        origin (live: Blender/PySide6 6.10.1, "the key steals focus but no
        menu appears"; Maya's 6.5.3 happened to re-apply the geometry).
        Clearing the state alone restores that stale normal geometry on the
        hidden overlay, which desyncs the pre-present anchor mapping — the
        present-last path centers pages against the hidden overlay's
        geometry (``setCurrentWidget`` → ``mapFromGlobal``) *before* the
        present applies the fullscreen rect — so the screen rect is re-pinned
        immediately after (:meth:`_move_hidden_overlay` — the pin must reach
        the NATIVE window). Both run while hidden; nothing paints. Pinned by
        ``test_construction_leaves_no_stale_fullscreen_state`` and
        ``test_preloaded_page_first_activation_centers``.
        """
        self.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
        try:
            self.showFullScreen()
            yield
        finally:
            QtWidgets.QWidget.hide(self)
            self.setAttribute(QtCore.Qt.WA_DontShowOnScreen, False)
            self.setWindowState(self.windowState() & ~QtCore.Qt.WindowFullScreen)
            handle = self.windowHandle()
            screen = handle.screen() if handle is not None else self.screen()
            if screen is not None:
                self._move_hidden_overlay(screen.geometry())

    def _move_hidden_overlay(self, rect: QtCore.QRect) -> None:
        """Move the hidden overlay to ``rect`` at BOTH layers — widget and
        native window.

        On Qt 6.10, ``QWidget.setGeometry`` on a hidden top-level does not
        reach the platform window at all (never-mapped windows sit at the
        platform's creation-default position; a fullscreen-state clear on a
        previously-mapped one silently restores its stale "normal" position)
        — while ``mapFromGlobal`` reads the NATIVE position. The present-last
        activation path centers pages against the hidden overlay
        (``setCurrentWidget`` → ``mapFromGlobal``) *before* the present, so
        the two layers must agree or every pre-present anchor mapping is off
        by the (native-pos − rect-origin) delta. ``QWindow.setGeometry``
        verifiably moves the hidden native window in both cases (probed on
        PySide6 6.10.1; on 6.5 the widget call alone propagates and the
        handle write is simply redundant).
        """
        self.setGeometry(rect)
        handle = self.windowHandle()
        if handle is not None:
            handle.setGeometry(rect)

    def _flush_first_show(self, page) -> None:
        """Run a stacked page's REAL first-show initialization (child
        registration / slot wiring, QSS polish, content fit) while nothing
        paints, so a later activation positions against settled geometry.

        Children shown inside a :meth:`_suppressed_present` block receive
        genuine show events without anything mapping on screen. No-op unless
        the overlay is hidden and the page still uninitialized, so it can
        never fight a live gesture.
        """
        if getattr(page, "is_initialized", False) or not self.isHidden():
            return
        with self._suppressed_present():
            page.setVisible(True)
            page.setVisible(False)

    def _prepare_ui(self, ui, *, anchor=None) -> QtWidgets.QWidget:
        """Initialize and set the UI without showing it.

        Stacked menus (startmenu/submenu) are managed directly by MarkingMenu.
        Standalone windows are delegated to the window manager for styling.

        Parameters:
            anchor (QPoint, optional): Global position to align a stacked
                widget's center to. ``None`` defers to ``setCurrentWidget``'s
                default (current cursor).
        """
        if not isinstance(ui, (str, QtWidgets.QWidget)):
            raise ValueError(f"Invalid datatype for ui: {type(ui)}")

        # Resolve UI using the appropriate manager
        if isinstance(ui, str):
            # Use our get() which routes stacked vs standalone correctly
            found_ui = self.get(ui)
        else:
            found_ui = ui

        if not found_ui:
            raise ValueError(f"UI not found: {ui}")

        is_stacked = found_ui.has_tags(_MARKING_MENU_TAGS)

        # Apply appropriate initialization based on UI type
        if not found_ui.is_initialized:
            self._init_ui(found_ui)

        if is_stacked:
            # Stacked menus: managed by MarkingMenu
            self.setCurrentWidget(found_ui, anchor=anchor)
        else:
            # Standalone windows: hide the marking menu overlay only if NOT parented to it
            if found_ui.parent() != self:
                self.hide()

        self.sb.current_ui = found_ui
        return found_ui
