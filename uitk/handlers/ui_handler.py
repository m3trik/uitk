import os
import copy
import logging
from typing import Optional, Dict, Any, Union, List, Tuple, Iterable
import pythontk as ptk
from uitk import Switchboard
from uitk.handlers.base_handler import BaseHandler, LaunchableHandlerProtocol
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

    # Default styling configuration
    DEFAULT_STYLE: Dict[str, Any] = {
        "attributes": {"WA_TranslucentBackground": True},
        "flags": {"FramelessWindowHint": True},
        "theme": "dark",
        "style_class": "translucentBgWithBorder",
        "header_buttons": ("menu", "collapse", "pin"),
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

    def get(self, name: str, reload: bool = False, **kwargs):
        """Retrieve a standalone UI by name and apply default styling.

        Parameters:
            name: The name of the UI to retrieve.
            reload: If True, forces a reload of the UI.
            **kwargs: Additional arguments.

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
            ui = self.get(ui, **kwargs)

        if not ui:
            return None

        # Resolve position: explicit arg > config default > None (let Qt decide)
        if pos is None:
            pos = self.config.get("default_position", None)

        if force or not ui.isVisible():
            ui.show()
            self._position_window(ui, pos)
            ui.raise_()
            ui.activateWindow()

        return ui

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
                center = screen_geo.center() - ui.rect().center()
                target_global = screen_geo.topLeft() + center
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

        Parameters:
            ui: The MainWindow to configure
            hide_signal: Signal to connect for auto-hide (e.g., marking_menu.key_show_release)
        """
        if hide_signal is not None and hasattr(ui, "request_hide"):
            hide_signal.connect(ui.request_hide)
            self.logger.debug(
                f"[{ui.objectName()}] Connected hide_signal -> request_hide"
            )

    def apply_styles(self, ui, style: Dict = None):
        """
        Apply default styles to the UI instance.
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
            # ui.header may not be registered yet (register_children runs
            # later in showEvent), so fall back to findChild by objectName.
            header = getattr(ui, "header", None)
            if not hasattr(header, "config_buttons"):
                header = (
                    ui.findChild(QtWidgets.QWidget, "header")
                    if hasattr(ui, "findChild")
                    else None
                )
            if header is not None and hasattr(header, "config_buttons"):
                current = tuple(getattr(header, "buttons", {}).keys())
                if not current:
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

    def launch(self, name: str, **options):
        """Launch the named UI applying the browser's per-launch style options.

        Recognized keys in ``options`` (all optional):
            frameless, translucent, restore_geometry, on_top, theme,
            parent_to_sb (default True — parent to the sb's own parent
            for DCC embedding, matching the existing browser behavior).

        Any unrecognized keys are ignored — keeps the contract stable
        when callers pass options targeted at other handler kinds.
        """
        ui = self.sb.loaded_ui[name]
        parent_to_sb = options.get("parent_to_sb", True)
        frameless = options.get("frameless", True)
        translucent = options.get("translucent", True)
        on_top = options.get("on_top", True)
        restore_geometry = options.get("restore_geometry", True)
        theme = options.get("theme")

        if parent_to_sb:
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

        self._configure_launched_header(ui)

        if not restore_geometry and hasattr(ui, "clear_saved_geometry"):
            ui.clear_saved_geometry()

        ui.show(pos="screen")
        ui.raise_()
        ui.activateWindow()

        # Wire visibility tracking so on_show/on_hide refresh the row.
        self._wire_visibility(name, ui)
        self._notify_entries_changed(name)
        return ui

    @staticmethod
    def _configure_launched_header(ui) -> None:
        """Add hide/collapse/menu buttons to a launched UI's header.

        Skips if the header already has buttons (deliberate custom set
        should be preserved). Lifted from SwitchboardBrowser so launch
        styling lives on the handler.
        """
        header = getattr(ui, "header", None)
        if header is None or not hasattr(header, "config_buttons"):
            header = (
                ui.findChild(QtWidgets.QWidget, "header")
                if hasattr(ui, "findChild")
                else None
            )
        if header is None or not hasattr(header, "config_buttons"):
            return
        if getattr(header, "buttons", None):
            return
        try:
            header.config_buttons("menu", "collapse", "hide")
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
        header = getattr(ui, "header", None)
        if header is None or not hasattr(header, "hide_window"):
            header = (
                ui.findChild(QtWidgets.QWidget, "header")
                if hasattr(ui, "findChild")
                else None
            )
        hidden = False
        if header is not None and hasattr(header, "hide_window"):
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
