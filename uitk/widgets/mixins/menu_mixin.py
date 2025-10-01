#!/usr/bin/env python
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
    """Descriptor that provides a uitk Menu object regardless of base Qt class collisions."""

    def __get__(self, instance: Any, owner: type):
        if instance is None:
            return self

        # First: check for existing instance attribute (highest priority)
        inst_attr = instance.__dict__.get("menu")
        MenuCls = _get_menu_class()
        if MenuCls is not None and isinstance(inst_attr, MenuCls):
            return inst_attr

        # Second: prefer OptionBox-backed menu (single source of truth)
        try:
            mgr = getattr(instance, "option_box", None)
            if mgr is not None and hasattr(mgr, "get_option_menu"):
                menu = mgr.get_option_menu(create=False)  # Don't auto-create
                if MenuCls is not None and isinstance(menu, MenuCls):
                    # Cache for future access
                    instance.__dict__["menu"] = menu
                    return menu
        except Exception:
            pass

        # Third: fallback to local menu only if no OptionBox manager exists
        try:
            mgr = getattr(instance, "option_box", None)
            if mgr is None:  # Only create fallback if no OptionBox manager
                menu = self._fallback(instance)
                instance.__dict__["menu"] = menu
                return menu
        except Exception:
            pass

        # If OptionBox manager exists but no menu yet, return None
        # This prevents conflicts and lets OptionBox manage the menu lifecycle
        return None

    def _fallback(self, instance: Any):
        MenuCls = _get_menu_class()
        if MenuCls is None:
            return None

        m = getattr(instance, "_menu", None)
        if not isinstance(m, MenuCls):
            # Create fallback menu with clear parent relationship
            m = MenuCls(
                parent=instance,  # Explicit parent
                mode="popup",
                position="cursorPos",
                fixed_item_height=20,
            )
            setattr(instance, "_menu", m)
        return m

    # Optional explicit setter to allow reassignment if needed
    def __set__(self, instance: Any, value: Any) -> None:  # type: ignore[override]
        MenuCls = _get_menu_class()
        if MenuCls is not None and isinstance(value, MenuCls):
            setattr(instance, "_menu", value)
            return
        # Fallback duck-typing: must have callable add
        if callable(getattr(value, "add", None)):
            setattr(instance, "_menu", value)
            return
        raise TypeError(
            "Assigned menu must be a uitk Menu or provide a callable 'add'."
        )


class MenuMixin:
    """Attach descriptor-based `menu` to consuming widgets.

    Strategy revision:
        The descriptor alone is insufficient in some cases (notably `QPushButton`),
        where the bound C++ method `menu()` can still be returned or cached before
        Python-level attribute resolution re-checks the descriptor. To guarantee
        a Python object with `.add` is always available, we *also* create an instance
        attribute `self.menu` during `__init__` if accessing `self.menu` would return
        a callable lacking `.add`.

    Order of resolution now:
        1. Instance attribute (installed below) — always preferred by Python.
        2. Descriptor fallback (still present for legacy or subclass overrides).
    """

    # Descriptor installed at class definition time (kept for fallback / subclasses)
    menu = _MenuDescriptor()

    def __init_subclass__(cls, **kwargs):  # type: ignore[override]
        super().__init_subclass__(**kwargs)  # type: ignore[misc]
        if not isinstance(cls.__dict__.get("menu"), _MenuDescriptor):
            cls.menu = _MenuDescriptor()  # type: ignore[assignment]

    def __init__(self, *args, **kwargs):  # type: ignore[override]
        # Some consuming widgets have multiple inheritance chains; ensure all bases init.
        super_init = getattr(super(), "__init__", None)
        if callable(super_init):
            super_init(*args, **kwargs)

        # Only set up fallback menu if no OptionBox manager will be created
        # This prevents conflicts between MenuMixin and OptionBox menus
        MenuCls = _get_menu_class()
        if MenuCls is None:
            return

        # Check if this widget will likely use OptionBox
        # (heuristic: has certain mixin classes or attributes)
        likely_option_box = (
            hasattr(self, "option_box")
            or "OptionBoxMixin" in [cls.__name__ for cls in type(self).__mro__]
            or hasattr(type(self), "_option_box_manager")
        )

        if likely_option_box:
            return  # Let OptionBox handle menu creation

        # Set up fallback menu for widgets that won't use OptionBox
        existing = self.__dict__.get("menu")
        if not isinstance(existing, MenuCls):
            candidate = object.__getattribute__(self, "menu")
            if not isinstance(candidate, MenuCls):
                m = MenuCls(
                    parent=self,
                    mode="popup",
                    position="cursorPos",
                    fixed_item_height=20,
                )
                self.menu = m
