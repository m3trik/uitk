import os
import copy
from typing import Optional, Dict, Any, Union, List, Tuple, Iterable
from uitk import Switchboard
from uitk.handlers.base_handler import BaseHandler
from uitk.handlers.handler_entry import HandlerEntry
from qtpy import QtWidgets, QtCore, QtGui


class UiHandler(BaseHandler):
    """
    A generic, dynamic UI Handler that supports recursive discovery of UI and Slot files.
    Allows for a "convention over configuration" approach while supporting overrides.

    Implements the launchable contract (:class:`LaunchableHandlerProtocol`)
    so registered .ui files show up alongside other handlers' entries in
    the unified launcher surface.
    """

    CONFIG_BRANCH = "ui"

    # Can be overridden by subclasses to provide manual mappings
    # Format: {"ui_name": {"ui": "path/to/file.ui", "slot": "path/to/slots.py"}}
    UI_REGISTRY: Dict[str, Dict[str, str]] = {}

    # Header button sets keyed by window "persistence" mode. The pin set is
    # transient chrome — it participates in the marking-menu key_show_release
    # auto-hide lifecycle (via MainWindow.request_hide / _has_pin_button) and
    # is user-pinnable. The hide set is sticky chrome — request_hide refuses,
    # so the window stays open until an explicit dismiss.
    TRANSIENT_HEADER = ("menu", "collapse", "pin")
    STICKY_HEADER = ("menu", "collapse", "hide")

    # Window persistence — the user-facing name for the chrome choice above.
    # ``"transient"`` -> pin chrome, ``"sticky"`` -> hide chrome. ``"context"``
    # is not a chrome: it means "no user choice, use :meth:`default_persistence`"
    # (the per-window default a subclass declares — e.g. mayatk's tool panels
    # are sticky). This handler is the SOLE owner of the resolution; the UI
    # Browser is only its front end (a global default plus per-window
    # overrides, both persisted in this handler's config branch).
    PERSISTENCE_TRANSIENT = "transient"
    PERSISTENCE_STICKY = "sticky"
    PERSISTENCE_CONTEXT = "context"
    PERSISTENCE_MODES = (PERSISTENCE_TRANSIENT, PERSISTENCE_STICKY)
    WINDOW_PERSISTENCE_KEY = "window_persistence"
    WINDOW_PERSISTENCE_DEFAULT = PERSISTENCE_CONTEXT
    PERSISTENCE_OVERRIDE_PREFIX = "persistence_override"

    # Pin-button click behavior for every window this handler styles:
    #   True  → one-click dismiss (``Header.pin_on_drag_only``): clicking the
    #           pin button hides the window and hovering it shows the red hide
    #           affordance; the window is pinned by dragging its header.
    #   False → classic toggle: click to pin, click again to unpin and hide.
    # Persisted under the handler's config branch; the UI Browser's "Pin
    # button hides (1-click)" checkbox is the user-facing switch.
    PIN_CLICK_HIDES_KEY = "pin_click_hides"
    PIN_CLICK_HIDES_DEFAULT = True

    # Default styling configuration
    DEFAULT_STYLE: Dict[str, Any] = {
        "attributes": {"WA_TranslucentBackground": True},
        "flags": {"FramelessWindowHint": True},
        "theme": "dark",
        "style_class": "translucentBgWithBorder",
        "header_buttons": TRANSIENT_HEADER,
    }

    # Configuration defaults exposed to Switchboard
    DEFAULTS = {
        "default_position": None,  # "cursor", "screen", "last", or (x,y)
        "remember_position": True,
        "remember_size": True,
        "style": DEFAULT_STYLE,
        PIN_CLICK_HIDES_KEY: PIN_CLICK_HIDES_DEFAULT,
        WINDOW_PERSISTENCE_KEY: WINDOW_PERSISTENCE_DEFAULT,
    }

    def __init__(
        self,
        switchboard: Switchboard,
        ui_root: Union[str, List[str]] = None,
        slot_root: Union[str, List[str]] = None,
        discover_slots: bool = False,
        recursive: bool = True,
        log_level: str = "WARNING",
        source_tags=None,
        **kwargs,
    ):
        """
        Initialize the UiHandler.

        Args:
            switchboard: The Switchboard instance this handler belongs to. Required.
            ui_root: Root directory or directories to scan for .ui files.
            slot_root: Root directory or directories to scan for slot classes.
                       If None, defaults to ui_root.
            discover_slots: If True, also scans for slots recursively (can be slow).
            recursive: Whether to scan directories recursively.
            log_level: Logging level.
            source_tags: Optional tags to apply to UIs loaded from ui_root.
            **kwargs: Additional arguments.
        """
        super().__init__(switchboard=switchboard, log_level=log_level)
        self.recursive = recursive

        # Seed the process-wide pin-click default from the persisted
        # preference. This is what carries the preference to headers this
        # handler never styles — Menu chrome (option-box menus, persistent
        # mode) and .ui-embedded headers all follow Header's class default.
        self._seed_pin_click_default()

        # 1. Register properties from the manual registry (Overrides)
        self._register_manual_overrides()

        # 2. Dynamic Discovery
        if ui_root:
            self.sb.register(
                ui_location=ui_root, recursive=self.recursive, tags=source_tags
            )
            if discover_slots and (slot_root or ui_root):
                self.sb.register(
                    slot_location=(slot_root or ui_root), recursive=self.recursive
                )

        # 3. Wire visibility tracking for every UI as it loads — not
        # just ones launched via this handler. Without this, a UI shown
        # by a marking menu or direct ``loaded_ui[name].show()`` call
        # never gets its on_show/on_hide piped into the entries-changed
        # signal, so the browser's row stays stuck on its old icon
        # (the bug the user keeps hitting: "after the UI closes the
        # action button still shows the focus icon"). Wiring is
        # idempotent — see ``_wire_visibility``'s flag check.
        loaded_signal = getattr(self.sb, "on_ui_loaded", None)
        if loaded_signal is not None:
            loaded_signal.connect(self._on_ui_loaded)

    def _on_ui_loaded(self, name: str) -> None:
        """Hook for ``Switchboard.on_ui_loaded`` — wire visibility tracking.

        Fires once per UI when it first materialises in ``loaded_ui``.
        We grab the just-loaded widget and connect its ``on_show`` /
        ``on_hide`` to ``_notify_entries_changed`` so the browser
        receives row-refresh signals regardless of who triggered the
        load (browser launch button, marking menu, plain
        ``sb.loaded_ui.<name>``, …).
        """
        ui = self.sb.loaded_ui.peek(name)
        if ui is None:
            return
        self._wire_visibility(name, ui)

    @property
    def editors(self):
        """Shortcut to the bound switchboard's editor registry.

        Equivalent to ``self.sb.editors`` — exists so shelf scripts and
        other handler callers can launch a bundled editor in one line
        without threading through ``.sb``::

            handler.editors.show("browser")

        See :class:`uitk.switchboard.editors._EditorRegistry`
        for the available editor names and methods.
        """
        return self.sb.editors

    def _register_manual_overrides(self):
        """Register items explicitly defined in UI_REGISTRY."""
        for name, data in self.UI_REGISTRY.items():
            try:
                self.sb.register(
                    ui_location=data.get("ui"),
                    slot_location=data.get("slot"),
                )
            except Exception as e:
                self.logger.error(f"Failed to register override '{name}': {e}")

    def can_resolve(self, name: str) -> bool:
        """True if :meth:`get` would resolve *name* to a UI — without building it.

        Hook for the switchboard's :meth:`SwitchboardWidgetMixin.ui_name_resolves`
        so destination resolution (nav-button click + auto-hide) can recognise UIs
        this handler produces. Base = a registered file stem; subclasses extend it
        for non-file sources (``MayaUiHandler`` adds its native-menu names).
        """
        if not name:
            return False
        base = name.split("#")[0] if "#" in name else name
        return self.sb.is_registered_ui(base)

    def get(self, name: str, **kwargs):
        """Retrieve a standalone UI by name and apply default styling.

        Parameters:
            name: The name of the UI to retrieve.
            **kwargs: Accepted and ignored for call-site compatibility. The
                underlying :meth:`Switchboard.get_ui` takes only ``name`` and no
                UI-reload path exists, but existing consumers pass extra
                keywords (e.g. tentacle's ``get(name, header=True)`` and the
                marking menu's ``get(name, **kwargs)``); tolerating them here
                keeps those call sites working rather than raising ``TypeError``.

        Returns:
            The UI widget with styles applied, or None if not found.
        """
        # Strip tags/sub-names if present (e.g. "polygons#component" -> "polygons")
        if "#" in name:
            name = name.split("#")[0]

        ui = self.sb.get_ui(name)
        if ui:
            self.apply_styles(ui)

        return ui

    def show(
        self,
        ui,
        pos: Union[str, Tuple[int, int], QtCore.QPoint, None] = None,
        force: bool = False,
        **kwargs,
    ):
        """Show a UI by name or widget reference.

        param pos: Position override. If None, checks self.config.default_position.
        """
        if isinstance(ui, str):
            ui = self.get(ui)

        if not ui:
            return None

        # Resolve position: explicit arg > config default > None (let Qt decide)
        if pos is None:
            pos = self.config.get("default_position", None)

        if force or not ui.isVisible():
            ui.show()
            self._restore_collapsed_header(ui)
            self._position_window(ui, pos)
            ui.raise_()
            ui.activateWindow()

        return ui

    @staticmethod
    def _restore_collapsed_header(ui) -> None:
        """Present the FULL window: undo a header collapse/minimize left on it.

        A header-collapsed window is still visible (a bare title strip), so
        Qt's ``show()`` no-ops on it and ``Header.showEvent`` — which resets
        collapse state on a hidden→shown transition — never fires. Restore
        before positioning so cursor-centering measures the real size.
        """
        header = getattr(ui, "header", None)
        if header is None:
            return
        try:
            header.restore_window()  # no-op unless header-minimized
            header.expand_window()  # no-op unless collapsed
        except (AttributeError, RuntimeError):
            pass  # not a uitk Header, or its window is already gone

    def _position_window(
        self,
        ui: QtWidgets.QWidget,
        pos: Union[str, Tuple[int, int], QtCore.QPoint, None],
    ) -> None:
        """Position a window based on the given pos specification."""
        if pos is None:
            return

        # Activate layout so geometry is accurate without flushing the
        # full event queue (which would fire deferred CollapsableGroup
        # timers and fight with restored window geometry).
        cw = ui.centralWidget() if hasattr(ui, "centralWidget") else None
        layout = (cw or ui).layout() if (cw or ui) else None
        if layout:
            layout.activate()

        target_global = None

        if pos == "cursor":
            cursor_pos = QtGui.QCursor.pos()
            # Ensure the window has a valid size before positioning
            if ui.width() <= 0 or ui.height() <= 0:
                ui.adjustSize()
            # Calculate window center offset
            half_width = ui.width() // 2
            half_height = ui.height() // 2
            # Offset slightly down so title bar is accessible
            vertical_offset = int(ui.height() * 0.25)
            target_global = QtCore.QPoint(
                cursor_pos.x() - half_width,
                cursor_pos.y() - half_height + vertical_offset,
            )
        elif pos == "screen":
            screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                screen_geo = screen.availableGeometry()
                # availableGeometry() is already in global coords, so its center
                # yields the correct global top-left after subtracting the window
                # half-extent. Adding topLeft() again would double-count the
                # screen's available origin (e.g. a top/left-docked taskbar),
                # off-centering the window. Matches utils.center_widget.
                target_global = screen_geo.center() - ui.rect().center()
        elif isinstance(pos, QtCore.QPoint):
            target_global = pos
        elif isinstance(pos, (tuple, list)) and len(pos) >= 2:
            target_global = QtCore.QPoint(int(pos[0]), int(pos[1]))
        else:
            self.logger.warning(f"Unknown position specification: {pos}")
            return

        if target_global:
            parent = ui.parentWidget()
            if parent and not ui.isWindow():
                # Non-window child: move() uses parent-relative coords
                target_local = parent.mapFromGlobal(target_global)
                ui.move(target_local)
            else:
                # Top-level or Qt.Window child: move() uses screen coords
                ui.move(target_global)

            # Clamp to screen after final positioning
            if getattr(ui, "ensure_on_screen", False) and hasattr(
                ui, "_ensure_on_screen"
            ):
                ui._ensure_on_screen()

    def setup_lifecycle(self, ui, hide_signal=None):
        """Connect a window to a hide signal, respecting its pin state.

        Idempotent — both canonical init paths (``MarkingMenu._init_ui``
        and :meth:`launch`) run this on the same shared window; the per-UI
        flag keeps relaunches from stacking connections (N ``request_hide``
        calls per key release).

        Parameters:
            ui: The MainWindow to configure
            hide_signal: Signal to connect for auto-hide (e.g., marking_menu.key_show_release)
        """
        if hide_signal is not None and hasattr(ui, "request_hide"):
            if getattr(ui, "_uitk_lifecycle_wired", False):
                return
            hide_signal.connect(ui.request_hide)
            ui._uitk_lifecycle_wired = True
            self.logger.debug(
                f"[{ui.objectName()}] Connected hide_signal -> request_hide"
            )

    # ── Pin-button click mode ─────────────────────────────────────────────

    @property
    def pin_click_hides(self) -> bool:
        """Whether a pin-button click dismisses the window (see the class constants).

        Persisted preference; takes effect through ``Header``'s process-wide
        default (:meth:`_seed_pin_click_default`), which every header built
        without an explicit ``pin_on_drag_only`` follows — including Menu
        chrome this handler never styles.
        """
        return bool(
            self.config.value(self.PIN_CLICK_HIDES_KEY, self.PIN_CLICK_HIDES_DEFAULT)
        )

    @pin_click_hides.setter
    def pin_click_hides(self, value) -> None:
        value = bool(value)
        self.config.setValue(self.PIN_CLICK_HIDES_KEY, value)
        # Publishing the class default IS the live-apply: headers resolve
        # their mode through it at click/hover/show time, so open windows and
        # menu chrome adopt the flip immediately. A header with an explicitly
        # assigned ``pin_on_drag_only`` (a slot's deliberate per-tool choice)
        # keeps it — the preference must not clobber intent.
        self._seed_pin_click_default(value)

    def _seed_pin_click_default(self, value: Optional[bool] = None) -> None:
        """Publish the preference as ``Header``'s process-wide default.

        Lazy import keeps handler import free of widget modules.
        """
        from uitk.widgets.header import Header

        Header.set_default_pin_on_drag_only(
            self.pin_click_hides if value is None else value
        )

    # ── Window persistence (pin vs hide chrome) ──────────────────────────

    def default_persistence(self, ui) -> str:
        """The per-window default for *ui* — what it does with no user override.

        This is the "context" in the UI Browser's ``Default (context)``: the
        behavior a window has always had, expressed as a persistence mode
        instead of hardcoded header buttons. Subclasses override it to declare
        their own defaults (mayatk / blendertk make their tool panels sticky);
        overriding ``apply_styles`` to swap ``header_buttons`` is the wrong
        home, because a user override then has nothing to override.

        Returns one of :attr:`PERSISTENCE_MODES` (never ``"context"``).
        """
        return self.PERSISTENCE_TRANSIENT

    @property
    def window_persistence(self) -> str:
        """Global default persistence: a mode, or ``"context"`` for per-window.

        Persisted preference; the UI Browser's "Window persistence" combo is
        the user-facing switch. ``"context"`` (the default) defers to
        :meth:`default_persistence` per window.
        """
        value = self.config.value(
            self.WINDOW_PERSISTENCE_KEY, self.WINDOW_PERSISTENCE_DEFAULT
        )
        return (
            value
            if value in self.PERSISTENCE_MODES or value == self.PERSISTENCE_CONTEXT
            else self.WINDOW_PERSISTENCE_DEFAULT
        )

    @window_persistence.setter
    def window_persistence(self, value) -> None:
        if value not in self.PERSISTENCE_MODES:
            value = self.PERSISTENCE_CONTEXT
        self.config.setValue(self.WINDOW_PERSISTENCE_KEY, value)
        self.reapply_persistence()

    def _persistence_key(self, name: str) -> str:
        """Per-window override key, host-namespaced.

        QSettings is shared across processes by (org, app), so a bare UI name
        would let a Maya and a Blender session collide on a same-named entry.
        Reuse the Switchboard's host-namespacing SSoT (the same one behind
        per-UI ``ui.settings``) so ``mirror`` -> ``mirror_maya`` /
        ``mirror_blender``.
        """
        ns = getattr(self.sb, "_host_namespaced_branch", None)
        leaf = ns(name) if callable(ns) else name
        return f"{self.PERSISTENCE_OVERRIDE_PREFIX}/{leaf}"

    def persistence_override(self, name: str) -> Optional[str]:
        """The stored per-window override, or ``None`` if it follows the default."""
        if not name:
            return None
        value = self.config.value(self._persistence_key(name), None)
        return value if value in self.PERSISTENCE_MODES else None

    def set_persistence_override(self, name: str, mode: Optional[str]) -> None:
        """Set (a mode) or clear (``None``) a per-window override, and re-chrome
        the window if it is already loaded."""
        if not name:
            return
        key = self._persistence_key(name)
        if mode in self.PERSISTENCE_MODES:
            self.config.setValue(key, mode)
        else:
            self.config.remove(key)
        self.reapply_persistence(name)

    @staticmethod
    def _ui_name(ui, name: Optional[str] = None) -> str:
        """The registry name for *ui* — the ``loaded_ui`` key, which
        ``Switchboard.add_ui`` also stamps as the window's objectName."""
        if name:
            return name
        try:
            return ui.objectName() or ""
        except AttributeError:
            return ""

    def resolve_persistence(
        self, ui, name: Optional[str] = None, context_default: Optional[str] = None
    ) -> str:
        """The effective persistence mode for *ui*: a concrete member of
        :attr:`PERSISTENCE_MODES`, never ``"context"``.

        Precedence: per-window override -> global default (when not
        ``"context"``) -> *context_default* (a caller's launch-path default)
        -> :meth:`default_persistence`.
        """
        override = self.persistence_override(self._ui_name(ui, name))
        if override is not None:
            return override
        global_mode = self.window_persistence
        if global_mode in self.PERSISTENCE_MODES:
            return global_mode
        return self._default_mode(ui, context_default)

    def _default_mode(self, ui, context_default: Optional[str] = None) -> str:
        """The mode for *ui* with no user choice in play — the tail of
        :meth:`resolve_persistence`, and what clearing a choice falls back to."""
        if context_default in self.PERSISTENCE_MODES:
            return context_default
        return self.default_persistence(ui)

    def is_persistence_explicit(self, ui, name: Optional[str] = None) -> bool:
        """Whether a *user* choice (per-window override or a non-context global)
        drives *ui*'s chrome — as opposed to a per-window default.

        An explicit choice outranks even a header a ``.ui`` file configured by
        hand; a default must not.
        """
        if self.persistence_override(self._ui_name(ui, name)) is not None:
            return True
        return self.window_persistence in self.PERSISTENCE_MODES

    def reapply_persistence(self, name: Optional[str] = None) -> None:
        """Re-chrome loaded windows after a persistence preference change.

        Live-apply is what makes the preference a *setting* rather than a
        launch argument — the same contract ``pin_click_hides`` has. Limited to
        *name* when given, otherwise every loaded UI.
        """
        loaded = getattr(self.sb, "loaded_ui", None)
        if loaded is None:
            return
        if name:
            items = [(name, loaded.peek(name))]
        else:
            try:
                items = list(loaded.items())
            except AttributeError:
                return
        for ui_name, ui in items:
            if ui is None:
                continue
            try:
                self._sync_persistence(ui, ui_name)
            except RuntimeError:  # window deleted since it was loaded
                continue

    def _sync_persistence(
        self,
        ui,
        name: Optional[str] = None,
        override: Optional[str] = None,
        context_default: Optional[str] = None,
        header=None,
    ) -> None:
        """Bring *ui*'s header in line with its persistence mode.

        A *default* and a *choice* have different rights over the header:

        * **Unconfigured header** — install the mode's whole default set
          (:meth:`_persistence_header`). This is the first-load path.
        * **Already configured + an explicit user choice** — swap only the
          dismissal button (:meth:`_persistence_buttons`). Panels configure
          their own chrome in ``header_init`` (``"refresh", "menu", "collapse",
          "hide"``); replacing that wholesale to honor a pin/hide choice would
          silently delete the refresh button.
        * **Already configured, no explicit choice** — restore the baseline
          (below), which is a no-op unless a choice had previously swapped it.
          The panel's own call IS its default.

        The **baseline** is what makes *clearing* a choice work: it's the chrome
        as the panel last configured it, remembered on the header before the
        first forced swap. Without it, clearing an override left the swapped
        button in place until the next load — the row menu would say ``Default``
        while the window still showed the override. It can't be recomputed
        instead, because a panel that declares a pin button in ``header_init``
        (the gesture-scoped exception) has a default the handler's own
        resolution would get wrong. It is refreshed whenever the panel's chrome
        differs from what this method last wrote, so a re-run ``header_init``
        re-establishes it.

        *override* is a per-call mode (the browser's per-launch value), treated
        as an explicit choice.
        """
        header = header if header is not None else self._ui_header(ui)
        if header is None:
            return
        explicit = override in self.PERSISTENCE_MODES or self.is_persistence_explicit(
            ui, name
        )
        mode = (
            override
            if override in self.PERSISTENCE_MODES
            else self.resolve_persistence(ui, name, context_default)
        )
        current = self._header_chrome(header)
        if not current:
            buttons = self._persistence_header(mode)
            # Baseline for a handler-installed header is the same set built
            # from the mode it would have had with no user choice in play.
            baseline = self._persistence_header(self._default_mode(ui, context_default))
        else:
            baseline = getattr(header, self._BASELINE_ATTR, None)
            if baseline is None or current != getattr(header, self._WRITTEN_ATTR, None):
                baseline = current  # the panel (re)configured its own chrome
            buttons = self._persistence_buttons(current, mode) if explicit else baseline
        if override in self.PERSISTENCE_MODES:
            # A per-launch override lives only in this call — nothing persisted
            # it, so it has to BE the baseline or the on-show pass would read
            # the stored preference and immediately undo it.
            baseline = buttons
        setattr(header, self._BASELINE_ATTR, tuple(baseline))
        self._write_header_buttons(header, buttons)
        setattr(header, self._WRITTEN_ATTR, tuple(buttons))

    def _resolve_hosted_theme(self, ui) -> Optional[str]:
        """The configured theme for *ui*'s hosted style, or ``None``.

        Delegates to the marking menu, the owner of the menu-page vs
        standalone-window theme preferences, so both styling entry points
        (``MarkingMenu._host_stacked`` and this handler) agree. Returns ``None``
        when no marking menu is present (plain Switchboard usage), leaving the
        caller's ``DEFAULT_STYLE`` theme in place.
        """
        mm = getattr(getattr(self.sb, "handlers", None), "marking_menu", None)
        resolve = getattr(mm, "resolve_hosted_theme", None)
        if resolve is None:
            return None
        try:
            return resolve(ui)
        except (AttributeError, RuntimeError):
            return None

    def apply_styles(self, ui, style: Dict = None, theme: str = None):
        """Apply default styles to the UI instance.

        ``theme`` overrides the theme for this call. When omitted, a style still
        carrying ``DEFAULT_STYLE``'s theme is treated as "no deliberate choice"
        and the theme is resolved from the marking menu's per-style setting
        (menu pages vs standalone windows), so the two hosted window themes are
        user-configurable rather than hard-pinned. Subclass overrides that
        pre-build a style from ``DEFAULT_STYLE`` (mayatk / blendertk swap header
        buttons) therefore still participate; a caller that deliberately set a
        different theme keeps it.
        """
        # Always use the class-level DEFAULT_STYLE as the authoritative source.
        # Persisted config may contain stale values from previous code versions.
        # When style is provided by a subclass override, trust it as pre-built.
        # Otherwise deepcopy from DEFAULT_STYLE so mutations stay local.
        if style is None:
            style = copy.deepcopy(self.DEFAULT_STYLE)

        if not style:
            return

        # Tag-based overrides
        try:
            if ui.has_tags(["startmenu", "submenu"]):
                style["style_class"] = "translucentBgNoBorder"
        except AttributeError:
            pass

        # Theme: explicit arg wins; otherwise the marking menu's per-style
        # setting drives any style that hasn't deliberately picked a theme.
        if theme:
            style["theme"] = theme
        elif style.get("theme") == self.DEFAULT_STYLE.get("theme"):
            resolved = self._resolve_hosted_theme(ui)
            if resolved:
                style["theme"] = resolved

        # Apply generic ptk/qt styles
        if "attributes" in style:
            try:
                ui.set_attributes(**style["attributes"])
            except AttributeError:
                pass

        if "flags" in style:
            try:
                ui.set_flags(**style["flags"])
            except AttributeError:
                pass

        try:
            ui.style
            theme = style.get("theme")
            style_class = style.get("style_class")
            if theme or style_class:
                ui.style.set(theme=theme, style_class=style_class)
        except AttributeError:
            pass

        # Header chrome. A style still carrying ``DEFAULT_STYLE``'s buttons is
        # "no deliberate choice" (same rule as the theme above), so the chrome
        # is resolved from the window's persistence mode — the single place pin
        # vs hide is decided, for EVERY init path. Without this the marking
        # menu's canonical path baked in its own chrome and the UI Browser's
        # setting reached browser-launched windows only.
        buttons = style.get("header_buttons")
        header = self._ui_header(ui) if buttons else None
        if header is not None:
            if tuple(buttons) == tuple(self.DEFAULT_STYLE["header_buttons"]):
                self._sync_persistence(ui, header=header)
            elif not self._header_chrome(header):
                # A caller-named set is still only a DEFAULT: it fills an
                # unconfigured header but never overwrites chrome a slot's
                # ``header_init`` already chose. Only an explicit user choice
                # outranks that — see :meth:`_sync_persistence`.
                self._write_header_buttons(header, buttons)

    # ── Launchable contract ──────────────────────────────────────────────

    def entries(self) -> Iterable[HandlerEntry]:
        """Yield one :class:`HandlerEntry` per .ui registered with the Switchboard.

        Tags are split into inherited (filename + source-directory) and
        file-backed (``<uitk_tags>`` XML) so the browser can render them
        with the existing inherited-vs-file UX. Only file tags are
        editable; that's signalled by passing ``file_tags`` (vs ``None``).
        """
        ui_registry = getattr(self.sb.registry, "ui_registry", None)
        if ui_registry is None:
            return
        for name in ui_registry.get("filename") or []:
            filepath = ui_registry.get(filename=name, return_field="filepath")
            yield HandlerEntry(
                name=name,
                kind="ui_file",
                handler=self,
                inherited_tags=frozenset(self._inherited_tags_for(name, filepath)),
                file_tags=frozenset(self.sb._get_ui_tags(name)),
                filepath=filepath,
            )

    def _inherited_tags_for(self, name: str, filepath: Optional[str]) -> set:
        """Filename-derived + source-directory inherited tags.

        Mirrors the same computation the browser model used to perform
        directly; lifted here so handler entries are the source of truth.
        """
        tags = set(self.sb.get_tags_from_name(name) or set())
        if filepath and self.sb._source_tags:
            norm = os.path.normpath(os.path.abspath(filepath))
            for src_dir, src_tags in self.sb._source_tags.items():
                if norm.startswith(src_dir + os.sep) or norm == src_dir:
                    tags.update(src_tags)
                    break
        return tags

    def hosting_handler(self, name: str):
        """Return the registered handler that claims windowing ownership of *name*.

        Duck-typed hosting contract — a handler that manages how a UI is
        parented and shown (rather than leaving it a standalone window)
        exposes::

            hosts_ui(name: str) -> bool   # cheap claim; must not load the UI
            show(name: str) -> QWidget    # the owner's presentation path

        :meth:`launch` consults the claim before applying its standalone
        setup, so a launcher surface (e.g. the SwitchboardBrowser) stays
        owner-agnostic — the marking menu claims its stacked startmenu /
        submenu pages this way. Returns None when no handler claims the
        name (the common case); standalone hosting is then legitimate,
        including for marking-menu-tagged UIs on a switchboard with no
        marking menu registered.
        """
        handlers = getattr(self.sb, "handlers", None)
        if handlers is None:
            return None
        for handler in vars(handlers).values():
            if handler is self:
                continue
            hosts_ui = getattr(handler, "hosts_ui", None)
            if not callable(hosts_ui) or not callable(getattr(handler, "show", None)):
                continue
            try:
                if hosts_ui(name):
                    return handler
            except Exception:
                # A dead or misbehaving claimant must not block launching —
                # fall through to the remaining handlers / standalone path.
                self.logger.debug(
                    f"hosts_ui probe failed on {type(handler).__name__}",
                    exc_info=True,
                )
        return None

    def launch(self, name: str, **options):
        """Launch the named UI applying the browser's per-launch style options.

        Recognized keys in ``options`` (all optional):
            frameless, translucent, restore_geometry, on_top, theme,
            parent_to_sb (default True — parent to the sb's own parent
            for DCC embedding; only honored on switchboards WITHOUT a
            marking menu — the canonical init below owns parenting
            otherwise),
            persistence ("transient" | "sticky" | None) — selects the
            header button set: "transient" gives the pin button (auto-hides
            with the marking menu, user-pinnable); "sticky" gives the hide
            button (stays open). ``None`` keeps the default (canonical/
            marking-menu windows -> pin, standalone launches -> hide).

        Any unrecognized keys are ignored — keeps the contract stable
        when callers pass options targeted at other handler kinds.

        A UI claimed by a hosting handler (see :meth:`hosting_handler`) is
        delegated to that handler's ``show`` instead: the standalone setup
        below (reparent to a top-level Qt.Window, Tool/on-top flags,
        launched-header buttons) would strip the owner's hosting invariants
        — e.g. a marking-menu startmenu page is a stacked child of the
        overlay, and since ``is_initialized`` gates the menu's ``_init_ui``
        to one run, a page re-hosted here never inits correctly again. The
        style options are discarded in that case; the owner controls
        presentation.
        """
        host = self.hosting_handler(name)
        if host is not None:
            ui = host.show(name)
            self._notify_entries_changed(name)
            return ui

        frameless = options.get("frameless", True)
        translucent = options.get("translucent", True)
        on_top = options.get("on_top", True)
        restore_geometry = options.get("restore_geometry", True)
        theme = options.get("theme")
        persistence = options.get("persistence")  # None | "transient" | "sticky"

        # Standalone windows on a marking-menu switchboard are the SAME
        # singleton the menu manages — route window init through the menu's
        # canonical path (``mm.get`` → parenting to the host app window,
        # apply_styles' pin chrome, hide-with-menu lifecycle) so launch
        # order can't fork the window's behavior. Without this, whichever
        # path touched the window first won forever: a browser-launched
        # tool got the launcher's hide button (and was parented to the
        # menu overlay, dying with it) instead of the intended pin button
        # that hides when the marking menu hides.
        mm = getattr(getattr(self.sb, "handlers", None), "marking_menu", None)
        canonical = mm is not None and callable(getattr(mm, "get", None))
        if canonical:
            ui = mm.get(name) or self.sb.loaded_ui[name]
        else:
            ui = self.sb.loaded_ui[name]
            if options.get("parent_to_sb", True):
                sb_parent = self.sb.parent() if hasattr(self.sb, "parent") else None
                if sb_parent is not None:
                    ui.setParent(sb_parent, QtCore.Qt.Window)

        ui.set_flags(
            FramelessWindowHint=frameless,
            Tool=frameless,
            WindowStaysOnTopHint=on_top,
        )
        ui.setAttribute(QtCore.Qt.WA_TranslucentBackground, translucent)

        if theme and hasattr(ui, "style"):
            try:
                ui.style.set(theme=theme)
            except Exception:
                pass

        # Chrome. A caller-supplied ``persistence`` is a per-launch override;
        # otherwise resolve the stored preference exactly as apply_styles does,
        # so a window's pin/hide behavior is identical however it was opened.
        # A launcher-opened window with no stored choice keeps the standalone
        # default (hide chrome — nothing auto-hides it out here); the canonical
        # marking-menu path defers to the UI's own default instead.
        self._sync_persistence(
            ui,
            name,
            override=persistence,
            context_default=None if canonical else self.PERSISTENCE_STICKY,
        )

        if not restore_geometry and hasattr(ui, "clear_saved_geometry"):
            ui.clear_saved_geometry()

        ui.show(pos="screen")
        ui.raise_()
        ui.activateWindow()

        # Wire visibility tracking so on_show/on_hide refresh the row.
        self._wire_visibility(name, ui)
        self._notify_entries_changed(name)
        return ui

    @classmethod
    def _persistence_header(cls, persistence) -> tuple:
        """Header button set for a launch ``persistence`` mode.

        ``"transient"`` -> pin chrome (auto-hides with the marking menu,
        user-pinnable). Anything else (incl. ``None`` / ``"sticky"``) ->
        hide chrome (stays open) — so ``None`` preserves the standalone
        default this method has always applied.
        """
        return cls.TRANSIENT_HEADER if persistence == "transient" else cls.STICKY_HEADER

    @staticmethod
    def _ui_header(ui, attr: str = "config_buttons"):
        """Resolve a UI's header widget exposing *attr*, or None.

        ``ui.header`` may not be registered yet (``register_children`` runs later
        in ``showEvent``), so fall back to ``findChild`` by objectName. *attr* is
        the capability the caller needs (e.g. ``config_buttons`` for chrome,
        ``hide_window`` for dismissal) — a header lacking it resolves to None.
        """
        header = getattr(ui, "header", None)
        if header is not None and hasattr(header, attr):
            return header
        header = (
            ui.findChild(QtWidgets.QWidget, "header")
            if hasattr(ui, "findChild")
            else None
        )
        if header is not None and hasattr(header, attr):
            return header
        return None

    @classmethod
    def _persistence_buttons(cls, buttons, persistence) -> tuple:
        """*buttons* with its dismissal button swapped to match *persistence*.

        Order and every other button are preserved — the mode owns pin-vs-hide,
        not the rest of a panel's chrome. A set carrying neither button gains
        the wanted one at the end.
        """
        want = "pin" if persistence == cls.PERSISTENCE_TRANSIENT else "hide"
        drop = "hide" if want == "pin" else "pin"
        out, placed = [], False
        for name in buttons:
            if name in (want, drop):
                if not placed:
                    out.append(want)
                    placed = True
            else:
                out.append(name)
        if not placed:
            out.append(want)
        return tuple(out)

    # Per-header bookkeeping for _sync_persistence: the chrome it last wrote,
    # and the pre-swap baseline to put back when a user choice is cleared.
    _WRITTEN_ATTR = "_uitk_persistence_written"
    _BASELINE_ATTR = "_uitk_persistence_baseline"

    @staticmethod
    def _header_chrome(header) -> tuple:
        """*header*'s configured buttons in layout order, help excluded.

        The help button never counts as configuration: ``Header.set_help_text``
        installs it additively (typically from a slot's ``header_init``) and
        ``config_buttons`` re-appends it across rebuilds. Empty means the header
        has made no chrome choice — a help-only header once suppressed the
        default menu / collapse / dismiss buttons, which is the bug this
        exclusion exists for.
        """
        return tuple(b for b in (getattr(header, "buttons", None) or ()) if b != "help")

    @classmethod
    def _write_header_buttons(cls, header, buttons) -> None:
        """Install *buttons* on *header* — the single chrome write path.

        A no-op when the chrome is already correct: ``apply_styles`` runs on
        every ``get`` and ``config_buttons`` replaces the button widgets, so an
        unguarded write would churn the chrome for no visible change. Compared
        in ORDER — ``Header.buttons`` is insertion-ordered and that order is the
        layout order, so the same names in a different arrangement is a real
        change. The help button is excluded: ``Header.set_help_text`` adds it
        additively and ``config_buttons`` re-appends it across rebuilds.
        """
        if cls._header_chrome(header) == tuple(buttons):
            return
        try:
            header.config_buttons(*buttons)
        except Exception:
            pass

    def close(self, name: str) -> None:
        """Hide the named UI via its header (matches the in-window hide button).

        Routes through ``Header.hide_window`` when present so collapse /
        minimize state is reset cleanly. Falls back to a direct
        ``ui.hide()`` for UIs without a uitk Header.
        """
        ui = self.sb.loaded_ui.peek(name)
        if not isinstance(ui, QtWidgets.QWidget):
            return
        header = self._ui_header(ui, attr="hide_window")
        hidden = False
        if header is not None:
            try:
                header.hide_window()
                hidden = True
            except Exception:
                pass
        if not hidden:
            ui.hide()
        self._notify_entries_changed(name)

    def is_visible(self, name: str) -> bool:
        ui = self.sb.loaded_ui.peek(name)
        try:
            return bool(ui and ui.isVisible())
        except Exception:
            return False

    def save_tags(self, name: str, tags: Iterable[str]) -> None:
        """Persist ``<uitk_tags>`` XML for the named UI. Optional contract method."""
        filepath = self.sb.registry.ui_registry.get(
            filename=name, return_field="filepath"
        )
        if not filepath:
            raise ValueError(f"No filepath registered for UI {name!r}.")
        self.sb.save_ui_tags(filepath, tags)
        # save_ui_tags already emits on_ui_tags_changed, which is
        # forwarded into on_handler_entry_changed.

    # ── Visibility hookup ────────────────────────────────────────────────

    def _wire_visibility(self, name: str, ui) -> None:
        """Connect ``ui.on_show``/``on_hide`` so row visibility refreshes, and
        re-assert the window's persistence chrome on every show.

        The chrome half is an ordering fix: ``register_children`` (which runs a
        slot's ``header_init``, where panels call ``config_buttons``) happens
        earlier in ``showEvent`` than ``on_show``, so a panel's own chrome would
        otherwise be the last word and a user's UI Browser override would never
        stick. ``_sync_persistence`` leaves the panel's set alone unless the
        user made an explicit choice, so this is inert by default.

        Idempotent — uses a per-UI flag attribute so re-launching the
        same UI doesn't stack connections.
        """
        if getattr(ui, "_uitk_handler_visibility_wired", False):
            return
        on_show = getattr(ui, "on_show", None)
        on_hide = getattr(ui, "on_hide", None)
        if on_show is None or on_hide is None:
            return
        try:
            on_show.connect(lambda _n=name: self._notify_entries_changed(_n))
            on_hide.connect(lambda _n=name: self._notify_entries_changed(_n))
            # By NAME, not by captured widget: this connection is owned by the
            # window it fires on, so capturing the widget would make it hold a
            # reference to itself. ``reapply_persistence`` already does the
            # by-name lookup (and tolerates an evicted / deleted window).
            on_show.connect(lambda _n=name: self.reapply_persistence(_n))
            ui._uitk_handler_visibility_wired = True
        except Exception:
            pass
