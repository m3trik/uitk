import os
import copy
import logging
from typing import Optional, Dict, Any, Union, List, Tuple
import pythontk as ptk
from uitk import Switchboard
from qtpy import QtWidgets, QtCore, QtGui


class UiHandler(ptk.SingletonMixin, ptk.LoggingMixin):
    """
    A generic, dynamic UI Handler that supports recursive discovery of UI and Slot files.
    Allows for a "convention over configuration" approach while supporting overrides.
    """

    # Can be overridden by subclasses to provide manual mappings
    # Format: {"ui_name": {"ui": "path/to/file.ui", "slot": "path/to/slots.py"}}
    UI_REGISTRY: Dict[str, Dict[str, str]] = {}

    # Default styling configuration
    DEFAULT_STYLE: Dict[str, Any] = {
        "attributes": {"WA_TranslucentBackground": True},
        "flags": {"FramelessWindowHint": True},
        "theme": "dark",
        "style_class": "translucentBgWithBorder",
        "header_buttons": ("menu", "collapse", "hide"),
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
            **kwargs: Additional arguments.
        """
        self.logger.setLevel(log_level)
        self.recursive = recursive

        # Handlers always receive an existing Switchboard - never create one
        if switchboard is None:
            raise ValueError(
                f"{self.__class__.__name__} requires a Switchboard instance. "
                "Handlers must be registered to an existing Switchboard."
            )
        self.sb = switchboard

        # 1. Register properties from the manual registry (Overrides)
        self._register_manual_overrides()

        # 2. Dynamic Discovery
        if ui_root:
            self.sb.register(ui_location=ui_root, recursive=self.recursive)
            if discover_slots and (slot_root or ui_root):
                self.sb.register(
                    slot_location=(slot_root or ui_root), recursive=self.recursive
                )

    @property
    def config(self):
        """Access configuration branch for this handler."""
        return self.sb.configurable.branch("ui")

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

    @classmethod
    def instance(cls, switchboard: Switchboard = None, **kwargs) -> "UiHandler":
        kwargs.setdefault("switchboard", switchboard)
        kwargs["singleton_key"] = id(switchboard)
        return super().instance(**kwargs)

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

        # Ensure layout is processed so geometry is accurate
        QtWidgets.QApplication.processEvents()

        target_global = None

        if pos == "cursor":
            cursor_pos = QtGui.QCursor.pos()
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
            if parent:
                target_local = parent.mapFromGlobal(target_global)
                ui.move(target_local)
            else:
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
        # Load style from arg > config > default class var
        config_style = self.config.value("style", self.DEFAULT_STYLE)
        style = copy.deepcopy(style or config_style)

        if not style:
            return

        # Tag-based overrides
        try:
            if ui.has_tags(["mayatk", "maya"]):
                style["header_buttons"] = ("menu", "collapse", "pin")

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
            try:
                if ui.header and ui.header.config_buttons:
                    ui.header.config_buttons(*style["header_buttons"])
            except AttributeError:
                pass
