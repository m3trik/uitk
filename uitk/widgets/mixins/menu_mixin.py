#!/usr/bin/env python
"""MenuMixin - provides automatic Menu integration for widgets.

This mixin provides a `menu` property that lazily creates and manages
a Menu instance. The menu is NOT created until first accessed, ensuring
widgets without menu usage have no overhead.

Key features:
- `menu`: Property that creates menu on first access
- `has_menu`: Check if menu exists without triggering creation
- `configure_menu()`: Set properties without triggering creation (instance-level)
- `_menu_defaults`: Class-level dict for widget-type defaults (preferred)

Usage:
    class MyWidget(QtWidgets.QWidget, MenuMixin):
        # Class-level defaults (preferred - no per-instance overhead)
        _menu_defaults = {"hide_on_leave": True, "add_apply_button": True}

        def add_items(self):
            # Menu is created here on first access, with _menu_defaults applied
            self.menu.add("Label A")

        def cleanup(self):
            if self.has_menu:
                self.menu.clear()
"""
from typing import Any, Optional, Type

_CACHED_MENU_CLASS: Optional[Type] = None


def _get_menu_class():
    """Return the uitk Menu class lazily to avoid circular import issues.

    Caches the class after first successful import. If import fails (during
    early module loading), returns None so callers can degrade gracefully.
    """
    global _CACHED_MENU_CLASS
    if _CACHED_MENU_CLASS is not None:
        return _CACHED_MENU_CLASS
    try:  # local import to break cycles
        from uitk.widgets.menu import Menu  # type: ignore

        _CACHED_MENU_CLASS = Menu
    except Exception:
        return None
    return _CACHED_MENU_CLASS


class _MenuDescriptor:
    """Descriptor that provides a uitk Menu object with lazy initialization.

    The menu is ONLY created when first accessed via the `.menu` property.
    Use `has_menu` to check if a menu exists without triggering creation.

    Resolution order (optimized for performance):
    1. Existing instance menu (cached) - FAST PATH
    2. Create new menu on first access - SLOW PATH (applies deferred config)
    """

    def __get__(self, instance: Any, owner: type):
        if instance is None:
            return self

        # FAST PATH: Check cache first (single dict lookup)
        # This is the most common case (99% of calls) - extremely fast
        inst_menu = instance.__dict__.get("_menu_instance")
        if inst_menu is not None:
            return inst_menu

        # SLOW PATH: Create standalone menu on first access
        menu = self._create_menu(instance)
        if menu is not None:
            instance.__dict__["_menu_instance"] = menu
            # Apply any deferred configuration
            self._apply_deferred_config(instance, menu)
        return menu

    def _apply_deferred_config(self, instance: Any, menu: Any) -> None:
        """Apply deferred menu configuration stored on the instance.

        Note: Config is now applied during creation in _create_menu.
        This method handles any edge cases where menu was assigned externally.
        """
        config = instance.__dict__.pop("_menu_config", None)
        if config:
            for attr, value in config.items():
                setattr(menu, attr, value)

    def _create_menu(self, instance: Any):
        """Create a standalone Menu for widgets not using OptionBox.

        Merges configuration from multiple sources (in priority order):
        1. Base defaults (trigger_button="right", etc.)
        2. Class-level _menu_defaults dict (for widget-specific defaults)
        3. Deferred configure_menu() calls (for instance-specific config)
        """
        MenuCls = _get_menu_class()
        if MenuCls is None:
            return None

        # Base defaults
        defaults = {
            "parent": instance,
            "trigger_button": "right",
            "position": "cursorPos",
            "fixed_item_height": 20,
            "add_header": True,
            "match_parent_width": False,
        }

        # Check for class-level menu defaults (avoids per-instance config)
        for cls in type(instance).__mro__:
            if "_menu_defaults" in cls.__dict__:
                defaults.update(cls._menu_defaults)
                break

        # Apply any deferred config from configure_menu() calls
        deferred = instance.__dict__.pop("_menu_config", None)
        if deferred:
            defaults.update(deferred)

        # Use factory method if available, otherwise direct instantiation
        if hasattr(MenuCls, "create_context_menu"):
            parent = defaults.pop("parent")
            return MenuCls.create_context_menu(parent=parent, **defaults)

        return MenuCls(**defaults)

    def __set__(self, instance: Any, value: Any) -> None:  # type: ignore[override]
        """Allow explicit menu assignment."""
        MenuCls = _get_menu_class()
        if MenuCls is not None and isinstance(value, MenuCls):
            instance.__dict__["_menu_instance"] = value
            return
        # Duck-typing: must have callable add
        if callable(getattr(value, "add", None)):
            instance.__dict__["_menu_instance"] = value
            return
        raise TypeError(
            "Assigned menu must be a uitk Menu or provide a callable 'add'."
        )


class MenuMixin:
    """Simple drop-in mixin that provides automatic Menu integration.

    Just inherit from this mixin and `self.menu` will be automatically available.
    The menu is lazily created on first access to `self.menu`.

    Use `self.has_menu` to check if a menu has been created without triggering
    creation (useful for cleanup, iteration, or conditional logic).

    Use `self.configure_menu()` to set menu properties without triggering creation.

    Example:
        class MyWidget(QtWidgets.QWidget, MenuMixin):
            def __init__(self):
                super().__init__()
                # Configure without creating (deferred until first access)
                self.configure_menu(trigger_button="right", hide_on_leave=True)

            def add_menu_items(self):
                # Menu is created here on first access
                self.menu.add("Item 1")

            def cleanup(self):
                # Check without creating
                if self.has_menu:
                    self.menu.clear()
    """

    # Descriptor provides smart menu access
    menu = _MenuDescriptor()

    def configure_menu(self, **config) -> None:
        """Configure menu properties without triggering creation.

        If the menu already exists, applies config immediately.
        Otherwise, stores config to be applied when menu is first accessed.

        Args:
            **config: Menu properties to set (e.g., trigger_button="right").
        """
        if self.has_menu:
            # Menu exists, apply immediately
            for attr, value in config.items():
                setattr(self.menu, attr, value)
        else:
            # Store for deferred application
            existing = self.__dict__.setdefault("_menu_config", {})
            existing.update(config)

    @property
    def has_menu(self) -> bool:
        """Check if a menu has been created without triggering creation.

        Returns:
            True if a menu instance exists, False otherwise.
        """
        return (
            "_menu_instance" in self.__dict__
            and self.__dict__["_menu_instance"] is not None
        )
