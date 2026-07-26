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

        if "header_buttons" in style:
            header = self._ui_header(ui)
            if header is not None:
                current = tuple(getattr(header, "buttons", {}).keys())
                # The help button is auto-installed by ``Header.set_help_text``
                # (typically from a slot's ``header_init``). It is additive, not
                # a user-explicit button configuration, so don't let its presence
                # suppress the default-button setup. ``config_buttons`` preserves
                # the help button across rebuilds when help text is set.
                non_help_current = tuple(b for b in current if b != "help")
                if not non_help_current:
                    header.config_buttons(*style["header_buttons"])

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

        if not canonical:
            # Launcher-only chrome — the canonical marking-menu init owns the
            # header set otherwise. ``persistence`` picks pin (transient) vs
            # hide (sticky); None -> hide, preserving the standalone default.
            self._configure_launched_header(ui, persistence=persistence)
        elif persistence in ("transient", "sticky"):
            # An EXPLICIT persistence choice (e.g. from the UI Browser) on a
            # marking-menu window: apply_styles already installed the pin
            # chrome, so override it. "sticky" drops the pin button, and
            # MainWindow.request_hide then refuses -> the window survives
            # key_show_release; "transient" re-asserts the pin chrome. Any other
            # value (None, or an unrecognized mode) leaves the canonical chrome.
            self._apply_persistence_chrome(ui, persistence)

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
    def _set_header_chrome(cls, ui, persistence, force: bool) -> None:
        """Apply the persistence button set to a UI's header (single source).

        ``force=False`` preserves a header that already carries a deliberate
        custom button set; ``force=True`` replaces it regardless.
        """
        header = cls._ui_header(ui)
        if header is None:
            return
        if not force and getattr(header, "buttons", None):
            return
        try:
            header.config_buttons(*cls._persistence_header(persistence))
        except Exception:
            pass

    @classmethod
    def _configure_launched_header(cls, ui, persistence=None) -> None:
        """Add menu/collapse plus a pin (transient) or hide (sticky) button to
        a launched UI's header, unless it already has a deliberate custom set.

        Lifted from SwitchboardBrowser so launch styling lives on the handler.
        ``persistence`` selects the button set; ``None`` -> hide.
        """
        cls._set_header_chrome(ui, persistence, force=False)

    @classmethod
    def _apply_persistence_chrome(cls, ui, persistence) -> None:
        """Force the header button set for *persistence*, replacing any existing
        set. Honors an explicit persistence choice on the canonical marking-menu
        path, where apply_styles already installed pin chrome."""
        cls._set_header_chrome(ui, persistence, force=True)

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
        """Connect ``ui.on_show``/``on_hide`` so row visibility refreshes.

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
            ui._uitk_handler_visibility_wired = True
        except Exception:
            pass
