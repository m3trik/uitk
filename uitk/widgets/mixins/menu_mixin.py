#!/usr/bin/env python
"""MenuMixin - provides automatic Menu integration for widgets.

This mixin provides a `menu` property that automatically creates and manages
a Menu instance. It's designed to be a simple drop-in that works seamlessly
with both standalone widgets and the OptionBox system.

Usage:
    class MyWidget(QtWidgets.QWidget, MenuMixin):
        def __init__(self):
            super().__init__()
            # Menu is automatically available
            self.menu.add("Label A")

    # Or customize in constructor:
    class MyButton(QtWidgets.QPushButton, MenuMixin):
        def __init__(self):
            super().__init__()
            self.menu.trigger_button = "left"
            self.menu.hide_on_leave = True
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

    Resolution order (optimized for performance):
    1. Existing instance menu (cached) - FAST PATH
    2. Create new menu - SLOW PATH
    """

    def __get__(self, instance: Any, owner: type):
        import time

        get_start = time.perf_counter()

        if instance is None:
            return self

        # FAST PATH: Check cache first (single dict lookup)
        # This is the most common case (99% of calls) - extremely fast
        inst_menu = instance.__dict__.get("_menu_instance")
        if inst_menu is not None:
            MenuCls = _get_menu_class()
            if MenuCls is not None and isinstance(inst_menu, MenuCls):
                duration_ms = (time.perf_counter() - get_start) * 1000
                if hasattr(instance, "logger"):
                    instance.logger.debug(
                        f"_MenuDescriptor.__get__: FAST PATH (cached) in {duration_ms:.3f}ms"
                    )
                return inst_menu

        # SLOW PATH: Create standalone menu (option_box doesn't exist or has no menu)
        menu = self._create_menu(instance)
        if menu is not None:
            instance.__dict__["_menu_instance"] = menu
        duration_ms = (time.perf_counter() - get_start) * 1000
        if hasattr(instance, "logger"):
            instance.logger.debug(
                f"_MenuDescriptor.__get__: SLOW PATH (created new) in {duration_ms:.3f}ms"
            )
        return menu

    def _create_menu(self, instance: Any):
        """Create a standalone Menu for widgets not using OptionBox."""
        MenuCls = _get_menu_class()
        if MenuCls is None:
            return None

        # Use factory method for consistent defaults
        # Widgets can customize after creation via self.menu.property = value
        if hasattr(MenuCls, "create_context_menu"):
            return MenuCls.create_context_menu(parent=instance)

        # Fallback for older Menu class without factory methods
        menu = MenuCls(
            parent=instance,
            trigger_button="right",
            position="cursorPos",
            fixed_item_height=20,
            add_header=True,
            match_parent_width=False,
        )
        return menu

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

    Example:
        class MyWidget(QtWidgets.QWidget, MenuMixin):
            def __init__(self):
                super().__init__()
                # Customize menu if needed
                self.menu.trigger_button = "left"
                self.menu.hide_on_leave = True
                # Add items
                self.menu.add("Item 1")
    """

    # Descriptor provides smart menu access
    menu = _MenuDescriptor()
