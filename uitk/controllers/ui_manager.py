import os
import logging
from typing import Optional, Dict, Any, Union, List
import pythontk as ptk
from uitk import Switchboard


class UiManager(ptk.SingletonMixin, ptk.LoggingMixin):
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
        Initialize the UiManager.

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
    def instance(cls, switchboard: Switchboard = None, **kwargs) -> "UiManager":
        kwargs.setdefault("switchboard", switchboard)
        kwargs["singleton_key"] = id(switchboard)
        return super().instance(**kwargs)

    def get(self, name: str, reload: bool = False, **kwargs):
        """
        Retrieve a UI by name.
        """
        ui = self.sb.get_ui(name)
        if ui:
            self.apply_styles(ui)

        return ui

    def apply_styles(self, ui, style: Dict = None):
        """
        Apply default styles to the UI instance.
        Can be overridden by subclasses or configured via DEFAULT_STYLE.
        """
        style = style or self.DEFAULT_STYLE
        if not style:
            return

        # Apply generic ptk/qt styles if methods exist
        if "attributes" in style and hasattr(ui, "set_attributes"):
            ui.set_attributes(**style["attributes"])

        if "flags" in style and hasattr(ui, "set_flags"):
            ui.set_flags(**style["flags"])

        if hasattr(ui, "style"):
            theme = style.get("theme")
            style_class = style.get("style_class")
            if theme or style_class:
                ui.style.set(theme=theme, style_class=style_class)

        if "header_buttons" in style and hasattr(ui, "header") and ui.header:
            if hasattr(ui.header, "config_buttons"):
                ui.header.config_buttons(*style["header_buttons"])
