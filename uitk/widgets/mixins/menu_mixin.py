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
    """Descriptor that provides a uitk Menu object with smart coordination.

    Resolution order (optimized for performance):
    1. Existing instance menu (cached) - FAST PATH
    2. OptionBox menu (if OptionBox exists and has menu) - MEDIUM PATH
    3. Create new menu (if no OptionBox) - SLOW PATH
    """

    def __get__(self, instance: Any, owner: type):
        if instance is None:
            return self

        # FAST PATH: Check cache first (single dict lookup)
        # This is the most common case (99% of calls) - extremely fast
        inst_menu = instance.__dict__.get("_menu_instance")
        if inst_menu is not None:
            MenuCls = _get_menu_class()
            if MenuCls is not None and isinstance(inst_menu, MenuCls):
                return inst_menu

        # MEDIUM PATH: Check if OptionBox has an existing menu (without triggering creation)
        # We directly access _menu attribute to avoid calling the auto-creating property
        if "_option_box_manager" in instance.__dict__:
            try:
                mgr = instance.__dict__.get("_option_box_manager")
                # Access _menu directly to avoid property auto-creation
                # This keeps performance while still coordinating with OptionBox
                if mgr and hasattr(mgr, "_menu") and mgr._menu is not None:
                    MenuCls = _get_menu_class()
                    if MenuCls is not None and isinstance(mgr._menu, MenuCls):
                        # Cache it for future fast-path access
                        instance.__dict__["_menu_instance"] = mgr._menu
                        return mgr._menu
            except Exception:
                pass

        # SLOW PATH: Create standalone menu (option_box doesn't exist or has no menu)
        menu = self._create_menu(instance)
        if menu is not None:
            instance.__dict__["_menu_instance"] = menu
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
    The descriptor handles coordination with OptionBox if present.

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

    def __init_subclass__(cls, **kwargs):  # type: ignore[override]
        """Ensure descriptor is present on all subclasses."""
        super().__init_subclass__(**kwargs)  # type: ignore[misc]
        if not isinstance(cls.__dict__.get("menu"), _MenuDescriptor):
            cls.menu = _MenuDescriptor()  # type: ignore[assignment]
