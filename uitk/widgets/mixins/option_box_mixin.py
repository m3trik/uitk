#!/usr/bin/env python
"""OptionBoxMixin - simple drop-in mixin for OptionBox functionality.

This mixin provides automatic OptionBox integration for widgets.
Just inherit from it and `self.option_box` will be available.

Usage:
    class MyWidget(QtWidgets.QWidget, OptionBoxMixin):
        def __init__(self):
            super().__init__()
            # OptionBox is automatically available
            self.option_box.clear_option = True
            self.option_box.menu.add("Item 1")

Example with customization:
    class MyLineEdit(QtWidgets.QLineEdit, OptionBoxMixin, MenuMixin):
        def __init__(self):
            super().__init__()
            # Enable clear button
            self.option_box.clear_option = True
            # Customize the option box menu
            self.option_box.menu.trigger_button = "left"
            self.option_box.menu.add("Copy")
            self.option_box.menu.add("Paste")
"""
from qtpy import QtWidgets
from typing import Optional, TYPE_CHECKING, Callable, Iterable, Tuple

if TYPE_CHECKING:
    from uitk.widgets.optionBox import OptionBoxManager


class OptionBoxMixin:
    """Mixin that provides automatic OptionBox integration for widgets."""

    @staticmethod
    def _resolve_qwidget_option_box_property(self) -> Optional["OptionBoxManager"]:
        """Safely access the autopatched QWidget.option_box property, if present.

        Avoids recursion by calling the property's descriptor directly on QWidget.
        """
        q_prop = getattr(QtWidgets.QWidget, "option_box", None)
        if isinstance(q_prop, property):
            try:
                return q_prop.__get__(self, type(self))  # type: ignore[no-any-return]
            except Exception:
                return None
        return None

    @property
    def option_box(self) -> Optional["OptionBoxManager"]:
        # Fast-path: if we already cached a manager on this instance
        existing = getattr(self, "_option_box_manager", None)
        if existing is not None:
            return existing

        # Try autopatched QWidget property
        mgr = self._resolve_qwidget_option_box_property(self)
        if mgr is not None:
            return mgr

        # Fallback: create and cache manager on this instance
        try:
            from uitk.widgets.optionBox.utils import OptionBoxManager

            mgr = OptionBoxManager(self)  # type: ignore[arg-type]
            setattr(self, "_option_box_manager", mgr)

            return mgr
        except Exception:
            return None

    @property
    def container(self):
        """Return the OptionBox container for this widget if available.

        This mirrors the common convenience seen on some widgets and keeps
        container access DRY across consumers.
        """
        mgr = self.option_box
        return None if mgr is None else mgr.container

    class _OptionsWrapper:
        """Thin, chainable wrapper proxying to OptionBoxManager.

        Methods return self for chaining and operate on the underlying manager.
        """

        def __init__(self, owner: QtWidgets.QWidget):
            self._owner = owner

        @property
        def _mgr(self) -> Optional["OptionBoxManager"]:
            return getattr(self._owner, "option_box", None)  # via mixin property

        # Chainable helpers
        def clear(self) -> "OptionBoxMixin._OptionsWrapper":
            mgr = self._mgr
            if mgr is not None:
                mgr.enable_clear()
            return self

        def pin(
            self,
            settings_key: Optional[str] = None,
            *,
            double_click_to_edit: bool = False,
            single_click_restore: bool = False,
        ) -> "OptionBoxMixin._OptionsWrapper":
            mgr = self._mgr
            if mgr is not None:
                mgr.pin(
                    settings_key=settings_key,
                    double_click_to_edit=double_click_to_edit,
                    single_click_restore=single_click_restore,
                )
            return self

        def recent(
            self,
            settings_key: Optional[str] = None,
            *,
            max_recent: int = 10,
            **kwargs,
        ) -> "OptionBoxMixin._OptionsWrapper":
            mgr = self._mgr
            if mgr is not None:
                mgr.recent(
                    settings_key=settings_key,
                    max_recent=max_recent,
                    **kwargs,
                )
            return self

        def action(self, handler: Callable) -> "OptionBoxMixin._OptionsWrapper":
            mgr = self._mgr
            if mgr is not None:
                mgr.set_action(handler)
            return self

        def disable(self, **kwargs) -> "OptionBoxMixin._OptionsWrapper":
            """Add a universal disable button (see ``OptionBoxManager.set_disable``).

            Toggles the wrapped widget's enabled state while the button stays
            clickable, so it can always be re-enabled.
            """
            mgr = self._mgr
            if mgr is not None:
                mgr.set_disable(**kwargs)
            return self

        def filter(self, **kwargs) -> "OptionBoxMixin._OptionsWrapper":
            """Turn the wrapped text widget into a filter field.

            See ``OptionBoxManager.set_filter`` — adds a filter on/off toggle,
            text persistence, and an optional scope cycle. Skipped with a warning
            on a non-text host (``FilterOption.is_compatible``).
            """
            mgr = self._mgr
            if mgr is not None:
                mgr.set_filter(**kwargs)
            return self

        def option_menu(
            self,
            *,
            title: Optional[str] = None,
            items: Optional[Iterable[Tuple[str, Callable]]] = None,
            build_menu: Optional[Callable] = None,
            position: str = "cursorPos",
            add_header: bool = True,
            tooltip: str = "Options",
            menu=None,
        ) -> "OptionBoxMixin._OptionsWrapper":
            mgr = self._mgr
            if mgr is not None:
                cfg = {
                    "title": title,
                    "items": items,
                    "build_menu": build_menu,
                    "position": position,
                    "add_header": add_header,
                    "tooltip": tooltip,
                }
                # Remove Nones
                cfg = {k: v for k, v in cfg.items() if v is not None}
                if menu is not None:
                    cfg["menu"] = menu
                mgr.enable_option_menu(**cfg)
            return self

        @property
        def container(self):
            mgr = self._mgr
            return None if mgr is None else mgr.container

        @property
        def menu(self):
            mgr = self._mgr
            if mgr is None:
                return None
            return mgr.get_menu(create=True)

    @property
    def options(self) -> "OptionBoxMixin._OptionsWrapper":
        # Always return a fresh thin wrapper bound to this instance
        return OptionBoxMixin._OptionsWrapper(self)
