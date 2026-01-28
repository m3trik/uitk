import os
import copy
import logging
from typing import Optional, Dict, Any, Union, List, Tuple
import pythontk as ptk
from uitk import Switchboard
from qtpy import QtWidgets, QtCore, QtGui


class WindowController(ptk.SingletonMixin, ptk.LoggingMixin):
    """
    A generic, dynamic UI Manager that supports recursive discovery of UI and Slot files.
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

    def __init__(
        self,
        ui_root: Union[str, List[str]] = None,
        slot_root: Union[str, List[str]] = None,
        switchboard: Optional[Switchboard] = None,
        discover_slots: bool = False,
        recursive: bool = True,
        log_level: str = "WARNING",
        **kwargs,
    ):
        """
        Initialize the WindowController.

        Args:
            ui_root: Root directory or directories to scan for .ui files.
            slot_root: Root directory or directories to scan for slot classes.
                       If None, defaults to ui_root.
            switchboard: Existing Switchboard instance to use.
            discover_slots: If True, also scans for slots recursively (can be slow).
            recursive: Whether to scan directories recursively.
            log_level: Logging level.
            **kwargs: Additional arguments passed to Switchboard.
        """
        self.logger.setLevel(log_level)
        self.recursive = recursive

        # Initialize or use existing Switchboard
        sb_kwargs = {k: v for k, v in kwargs.items() if k != "singleton_key"}
        self.sb = switchboard or Switchboard(**sb_kwargs)

        # 1. Register properties from the manual registry (Overrides)
        self._register_manual_overrides()

        # 2. Dynamic Discovery
        if ui_root:
            self.sb.register(ui_location=ui_root, recursive=self.recursive)
            if discover_slots and (slot_root or ui_root):
                self.sb.register(
                    slot_location=(slot_root or ui_root), recursive=self.recursive
                )

    def _register_manual_overrides(self):
        """Register items explicitly defined in UI_REGISTRY."""
        for name, data in self.UI_REGISTRY.items():
            try:
                self.sb.register(
                    ui_location=data.get("ui"),
                    slot_location=data.get("slot"),
                    # We rely on Switchboard/UiLoader determining the name from the file
                    # unless we want to map it explicitly in the future.
                    # Currently Switchboard.register doesn't take a 'name' map for files easily
                    # without loading them.
                )
                # If the registry implies a specific name for a specific file,
                # Switchboard resolves name via ptk.format_path(path, "name").
                # If we want to support aliasing, we might need a lookup map in get().
            except Exception as e:
                self.logger.error(f"Failed to register override '{name}': {e}")

    def _discover_and_register(self, ui_roots, slot_roots):
        """Recursively find and register UI and Slot files."""
        # Deprecated: Handled directly by Switchboard.register now
        pass

    @classmethod
    def instance(cls, switchboard: Switchboard = None, **kwargs) -> "WindowController":
        kwargs.setdefault("switchboard", switchboard)
        kwargs["singleton_key"] = id(switchboard)
        return super().instance(**kwargs)

    def get(self, name: str, reload: bool = False, **kwargs):
        """Retrieve a standalone UI by name and apply default styling.

        This method is intended for standalone windows (not stacked menus).
        Stacked menus should be retrieved directly from Switchboard.

        Parameters:
            name: The name of the UI to retrieve.
            reload: If True, forces a reload of the UI.
            **kwargs: Additional arguments.

        Returns:
            The UI widget with styles applied, or None if not found.
        """
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

        Parameters:
            ui: The name of the UI to show or a QWidget instance.
            pos: Position to show the window. Can be:
                - "cursor": Center on cursor position
                - "screen": Center on screen
                - (x, y) tuple or QPoint: Absolute position
                - None: Use default Qt positioning
            force: If True, forces the UI to show even if already visible.
            **kwargs: Additional arguments passed to get().

        Returns:
            The UI widget if found and shown, None otherwise.
        """
        if isinstance(ui, str):
            ui = self.get(ui, **kwargs)

        if not ui:
            return None

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
        """Position a window based on the given pos specification.

        Parameters:
            ui: The widget to position.
            pos: Position specification (see show() for details).
        """
        if pos is None:
            return

        # Ensure layout is processed so geometry is accurate
        ui.adjustSize()
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
            # If the window has a parent, move() uses local coordinates.
            # We must map our global target to the parent's local space.
            parent = ui.parentWidget()
            if parent:
                # If parent is a high-level controller (like StackedController), ensure we map correctly
                target_local = parent.mapFromGlobal(target_global)
                ui.move(target_local)
            else:
                ui.move(target_global)

    def apply_styles(self, ui, style: Dict = None):
        """
        Apply default styles to the UI instance.
        Can be overridden by subclasses or configured via DEFAULT_STYLE.
        """
        # Create a working copy of the style to modify based on logic
        style = copy.deepcopy(style or self.DEFAULT_STYLE)
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
