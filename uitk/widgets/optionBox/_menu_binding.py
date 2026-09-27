# !/usr/bin/python
# coding=utf-8
"""Menu binding for :class:`OptionBoxManager`: the ``widget.option_box.menu``
surface and the action / option-menu buttons it wires."""

from typing import Optional


class _OptionBoxMenuMixin:
    """The option box's menu: lazy creation, adoption, and the menu /
    option-menu buttons (a partial of :class:`OptionBoxManager`)."""

    @property
    def menu(self):
        """Get or create a Menu instance for this option box.

        For backward compatibility, this property auto-creates the menu if needed.
        This maintains existing API behavior where `widget.option_box.menu.add()`
        always works.

        The performance impact is minimal because:
        1. Menu creation is lazy (doesn't build UI until items added)
        2. MenuMixin descriptor caches the result
        3. This is only called when explicitly accessing option_box.menu

        Returns:
            Menu: The menu instance (created if necessary)
        """
        if self._menu is None:
            self.enable_menu()
        return self._menu

    def get_menu(self, create=False):
        """Get menu, optionally creating if it doesn't exist.

        This method provides explicit control over menu creation.
        The .menu property auto-creates for backward compatibility.

        Args:
            create: If True and menu doesn't exist, creates one via enable_menu()

        Returns:
            Menu: The menu instance, or None if it doesn't exist and create=False
        """
        if self._menu is None and create:
            self.enable_menu()
        return self._menu

    @menu.setter
    def menu(self, value):
        """Set (or clear) the option-box menu.

        Assigning a :class:`Menu` produces exactly one menu button via
        :meth:`enable_menu`; reassigning first tears down any prior button
        (:meth:`disable_menu`) so buttons never duplicate. Assigning ``None``
        disables the menu entirely.

        Previously this only stored ``self._menu`` and never produced a button
        — so ``widget.option_box.menu = my_menu`` was a dead-end, and a
        subsequent ``enable_menu`` short-circuited on the already-set ``_menu``.

        Args:
            value: A Menu instance to use, or None to disable.
        """
        from uitk.widgets.menu import Menu

        # Tear down any existing menu + its button first (idempotent).
        self.disable_menu()
        if value is None:
            return
        if isinstance(value, Menu):
            self.enable_menu(menu=value)
        else:
            # Non-Menu value: legacy passthrough — stored without a button.
            self._menu = value

    def enable_menu(self, menu=None, **menu_kwargs):
        """Enable menu option using the MenuOption plugin.

        This follows the same pattern as enable_clear() - it creates
        the appropriate option plugin and adds it to the option box.

        Coordinates with MenuMixin to avoid duplicate menu creation:
        - Checks for existing menu via MenuMixin's _menu_instance
        - Reuses existing menu if found
        - Creates new menu only if needed

        Args:
            menu: Optional existing Menu instance. If None, will check for
                  existing menu or create a new one.
            **menu_kwargs: Additional kwargs passed to Menu() constructor if
                          creating a new menu (e.g., position, add_header, etc.)

        Returns:
            self: For fluent interface chaining
        """
        # PERFORMANCE: Only enable timing if logger level is DEBUG (10) or lower
        # In production with INFO (20) or higher, this adds 50-100ms overhead
        timing_enabled = self.logger.level <= 10

        if timing_enabled:
            import time

            enable_menu_start = time.perf_counter()
            _step_time = enable_menu_start

            def _log_step(step_name):
                nonlocal _step_time
                now = time.perf_counter()
                duration_ms = (now - _step_time) * 1000
                total_ms = (now - enable_menu_start) * 1000
                self.logger.debug(
                    f"OptionBoxManager.enable_menu [{step_name}]: {duration_ms:.3f}ms (total: {total_ms:.3f}ms)"
                )
                _step_time = now

        else:
            # No-op function when timing disabled
            def _log_step(step_name):
                pass

        self.logger.debug(
            f"OptionBoxManager.enable_menu: Called with menu={menu}, "
            f"menu_kwargs={list(menu_kwargs.keys())}"
        )

        if self._menu is None:
            from uitk.widgets.menu import Menu

            _log_step("import_Menu")

            # Only use explicitly passed menu - do NOT reuse widget's context menu
            # The option box menu should be completely separate from the widget's
            # right-click context menu (which is managed by MenuMixin)
            if menu is not None and isinstance(menu, Menu):
                self.logger.debug(
                    "OptionBoxManager.enable_menu: Using explicitly passed menu"
                )
                self._menu = menu
                _log_step("use_passed_menu")
            else:
                # Create a new Menu with appropriate defaults
                # Merge defaults with user-provided kwargs
                default_kwargs = {
                    "parent": self._widget,
                    "trigger_button": "none",  # OptionBox button handles triggering
                    "match_parent_width": False,  # Don't constrain width to prevent cropping
                    "add_apply_button": True,  # Enable apply button for option box menus
                    "add_defaults_button": True,  # Show restore defaults for option box menus
                    "hide_on_leave": True,  # Auto-hide when mouse leaves
                }
                default_kwargs.update(menu_kwargs)

                # Auto-name the menu based on the parent widget if not provided
                if (
                    "name" not in default_kwargs
                    and self._widget
                    and self._widget.objectName()
                ):
                    default_kwargs["name"] = f"{self._widget.objectName()}_option_menu"

                self.logger.debug(
                    f"OptionBoxManager.enable_menu: Creating NEW menu with kwargs={list(default_kwargs.keys())}"
                )

                self._menu = Menu(**default_kwargs)
                _log_step("Menu_creation")

                self.logger.debug(
                    "OptionBoxManager.enable_menu: Menu created (separate from widget context menu)"
                )
                _log_step("menu_created")

            # Create and add the MenuOption plugin
            # MenuOption is a plugin that creates its own button, so we don't need
            # to set _action_handler - that would create a duplicate button
            from ..optionBox.options.action import MenuOption

            _log_step("import_MenuOption")

            menu_option = MenuOption(wrapped_widget=self._widget, menu=self._menu)
            _log_step("MenuOption_creation")

            self.add_option(menu_option)
            _log_step("add_option")

        if timing_enabled:
            total_duration = (time.perf_counter() - enable_menu_start) * 1000
            self.logger.debug(
                f"OptionBoxManager.enable_menu: TOTAL completed in {total_duration:.3f}ms"
            )
        return self

    def enable_option_menu(
        self,
        *,
        title: Optional[str] = None,
        items=None,
        build_menu=None,
        position: str = "cursorPos",
        add_header: bool = True,
        tooltip: str = "Options",
        menu=None,
    ):
        """Add a dropdown *option menu* button (fluent interface).

        Builds an :class:`OptionMenuOption` — a button that pops a ``Menu`` of
        command rows — and adds it to the option box. Backs the
        ``widget.options.option_menu(...)`` fluent wrapper (which previously
        called this nonexistent method and raised ``AttributeError``).

        Args:
            title: Optional dropdown-menu title.
            items: Iterable of ``(label, callback)`` rows; each becomes a real
                clickable button wired to its callback.
            build_menu: Optional ``callable(menu)`` for custom population, run
                after ``items``.
            position: Menu popup position (default ``"cursorPos"``).
            add_header: Whether the dropdown ``Menu`` shows a draggable header.
            tooltip: Button tooltip.
            menu: Optional pre-built :class:`Menu` used verbatim.

        Returns:
            self: For fluent interface chaining.
        """
        from uitk.widgets.optionBox.options.option_menu import OptionMenuOption

        item_list = list(items) if items else None
        option = OptionMenuOption(
            wrapped_widget=self._widget,
            menu_items=item_list,
            tooltip=tooltip,
            position=position,
            add_header=add_header,
        )
        # A caller-supplied Menu is used verbatim (bypasses lazy creation), so
        # its rows must be added explicitly — _ensure_menu only populates
        # menu_items when it builds the menu itself.
        if menu is not None:
            option._menu = menu
            for item in item_list or []:
                option._add_menu_item(item)
        self.add_option(option)

        # Force the (otherwise lazy) menu build only when there is something to
        # apply beyond the static items the option already carries.
        if title is not None or build_menu is not None:
            built = option.menu
            if title is not None:
                built.setTitle(title)
            if build_menu is not None:
                build_menu(built)
        return self

    def disable_menu(self):
        """Disable the menu option (fluent interface).

        Removes the MenuOption button — from both the pending list and an
        already-wrapped option box — and drops the menu reference, so a later
        :meth:`enable_menu` (or the ``menu`` setter) rebuilds a *single* fresh
        button instead of stacking a duplicate on top of an orphaned one.

        Returns:
            self: For fluent interface chaining
        """
        from ..optionBox.options.action import MenuOption

        self._remove_options(lambda o: isinstance(o, MenuOption))
        self._menu = None
        return self
