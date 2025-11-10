# !/usr/bin/python
# coding=utf-8
"""Utilities and helper functions for OptionBox."""

from qtpy import QtWidgets, QtCore
from typing import Optional, Union
import pythontk as ptk


class OptionBoxManager(ptk.LoggingMixin):
    """Elegant manager for option box functionality accessible as widget.option_box"""

    def __init__(self, widget, log_level: Optional[Union[int, str]] = "WARNING"):
        self.logger.setLevel(log_level)
        self.logger.debug(
            f"OptionBoxManager.__init__: Creating for widget={type(widget).__name__}"
        )
        self._widget = widget
        self._option_box = None
        self._container = None
        self._clear_enabled = False
        self._action_handler = None
        self._menu = None
        self._option_order = [
            "clear",
            "action",
        ]  # Default order: clear button first, then action button
        self._pending_options = []  # Store options until wrapping is needed
        self._wrap_retry_scheduled = False  # Prevent duplicate timer scheduling
        self._wrap_retry_count = 0  # Track retries while waiting for parent assignment
        self._is_wrapped = False  # Track if wrap() has been called

    @property
    def clear_option(self):
        """Get/set clear option state"""
        return self._clear_enabled

    @clear_option.setter
    def clear_option(self, enabled):
        """Enable/disable clear option"""
        self._clear_enabled = enabled
        self._update_option_box()

    @property
    def option_order(self):
        """Get/set option ordering: ['clear', 'action'] or ['action', 'clear']"""
        return self._option_order

    @option_order.setter
    def option_order(self, order):
        """Set option ordering

        Args:
            order: List like ['clear', 'action'] or ['action', 'clear']
        """
        if not isinstance(order, (list, tuple)):
            raise ValueError("Option order must be a list or tuple")

        valid_options = {"clear", "action"}
        if not all(opt in valid_options for opt in order):
            raise ValueError(
                f"Invalid options in order. Valid options: {valid_options}"
            )

        self._option_order = list(order)
        if self._option_box:
            # Recreate with new order
            self._recreate_option_box()

    def enable_clear(self):
        """Enable clear option (fluent interface)"""
        self.clear_option = True
        return self

    def disable_clear(self):
        """Disable clear option (fluent interface)"""
        self.clear_option = False
        return self

    def set_action(self, action_handler):
        """Set action handler (fluent interface)"""
        self._action_handler = action_handler
        self._update_option_box()
        return self

    def set_menu(self, menu):
        """Set menu (fluent interface)"""
        self._menu = menu
        self._action_handler = menu
        self._update_option_box()
        return self

    def set_order(self, order):
        """Set option order (fluent interface)

        Args:
            order: List like ['clear', 'action'] or ['action', 'clear']
        """
        self.option_order = order
        return self

    def clear_first(self):
        """Set clear button to appear first (fluent interface)"""
        return self.set_order(["clear", "action"])

    def action_first(self):
        """Set action button to appear first (fluent interface)"""
        return self.set_order(["action", "clear"])

    @property
    def enabled(self):
        """Check if option box is enabled"""
        return self._option_box is not None

    @property
    def widget(self):
        """Get the actual option box widget"""
        self._update_option_box()  # Ensure option box is created if needed
        return self._option_box

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
        """Set an existing menu instance.

        Args:
            value: A Menu instance to use
        """
        self._menu = value
        # Don't set _action_handler - menu uses plugin system (MenuOption)
        # which creates its own button. Setting _action_handler would create
        # a duplicate button.
        # self._action_handler = value  # REMOVED - causes duplicate buttons
        # Don't call _update_option_box() - the menu is managed via plugins

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
            # PERFORMANCE OPTIMIZATION: Check for existing menu to avoid duplication
            from uitk.widgets.menu import Menu

            _log_step("import_Menu")

            existing_menu = None

            # Priority 1: Check MenuMixin's _menu_instance (most common case)
            # This is a direct dict access - very fast
            if "_menu_instance" in self._widget.__dict__:
                candidate = self._widget.__dict__.get("_menu_instance")
                if isinstance(candidate, Menu):
                    existing_menu = candidate
                    self.logger.debug(
                        "OptionBoxManager.enable_menu: Found existing menu via _menu_instance"
                    )
            _log_step("check_menu_instance")

            # Priority 2: Check if menu was explicitly passed
            if existing_menu is None and menu is not None:
                if isinstance(menu, Menu):
                    existing_menu = menu
                    self.logger.debug(
                        "OptionBoxManager.enable_menu: Using explicitly passed menu"
                    )

            # Priority 3: Try getting menu from widget's menu attribute
            # (Some widgets like TextEdit set menu directly)
            if existing_menu is None and hasattr(self._widget, "menu"):
                try:
                    # Access __dict__ directly to avoid triggering MenuMixin descriptor
                    # which could cause unwanted side effects
                    widget_menu = self._widget.__dict__.get("menu")
                    if isinstance(widget_menu, Menu):
                        existing_menu = widget_menu
                except Exception:
                    pass
            _log_step("check_passed_menu")

            # Use existing menu or create new one
            if existing_menu is not None:
                self.logger.debug(
                    "OptionBoxManager.enable_menu: Reusing existing menu instance"
                )
                self._menu = existing_menu
                # Update MenuMixin cache to point to this menu for consistency
                self._widget.__dict__["_menu_instance"] = existing_menu
                _log_step("reuse_menu")
            else:
                # Create a new Menu with appropriate defaults
                # Merge defaults with user-provided kwargs
                default_kwargs = {
                    "parent": self._widget,
                    "trigger_button": "none",  # OptionBox button handles triggering
                    "match_parent_width": False,  # Don't constrain width to prevent cropping
                    "add_apply_button": True,  # Enable apply button for option box menus
                }
                default_kwargs.update(menu_kwargs)

                self.logger.debug(
                    f"OptionBoxManager.enable_menu: Creating NEW menu with kwargs={list(default_kwargs.keys())}"
                )

                self._menu = Menu(**default_kwargs)
                _log_step("Menu_creation")

                # Cache it in MenuMixin for fast access
                self._widget.__dict__["_menu_instance"] = self._menu

                self.logger.debug(
                    f"OptionBoxManager.enable_menu: Menu created and cached"
                )
                _log_step("cache_menu")

            # Create and add the MenuOption plugin
            # MenuOption is a plugin that creates its own button, so we don't need
            # to set _action_handler - that would create a duplicate button
            from ..optionBox.options import MenuOption

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

    def disable_menu(self):
        """Disable menu option (fluent interface).

        Returns:
            self: For fluent interface chaining
        """
        # TODO: Implement menu option removal
        self._menu = None
        return self

    def add_option(self, option):
        """Add an option plugin to this option box.

        This is the central method for adding any option plugin,
        maintaining consistency across all option types.

        LAZY LOADING: Options are stored in _pending_options and only
        wrapped when the container is actually accessed via .container property.

        Args:
            option: An option plugin instance to add

        Returns:
            self: For fluent interface chaining
        """
        # PERFORMANCE: Only enable timing if logger level is DEBUG (10) or lower
        timing_enabled = self.logger.level <= 10

        if timing_enabled:
            import time

            add_option_start = time.perf_counter()
            _step_time = add_option_start

            def _log_step(step_name):
                nonlocal _step_time
                now = time.perf_counter()
                duration_ms = (now - _step_time) * 1000
                total_ms = (now - add_option_start) * 1000
                self.logger.debug(
                    f"OptionBoxManager.add_option [{step_name}]: {duration_ms:.3f}ms (total: {total_ms:.3f}ms)"
                )
                _step_time = now

        else:

            def _log_step(step_name):
                pass

        # If already wrapped, add option directly to option box
        if self._is_wrapped and self._option_box:
            self._option_box.add_option(option)
            _log_step("direct_add_to_wrapped")
            if timing_enabled:
                total_duration = (time.perf_counter() - add_option_start) * 1000
                self.logger.debug(
                    f"OptionBoxManager.add_option: TOTAL (already wrapped) in {total_duration:.3f}ms"
                )
            return self

        # Check for existing option box (from menu or other systems)
        if not self._option_box:
            existing_option_box = self._find_existing_option_box()
            _log_step("find_existing")

            if existing_option_box:
                # Reuse existing option box - it's already wrapped
                self._option_box = existing_option_box
                self._container = existing_option_box.container
                self._is_wrapped = True
                self._option_box.add_option(option)
                _log_step("reuse_and_add")
                if timing_enabled:
                    total_duration = (time.perf_counter() - add_option_start) * 1000
                    self.logger.debug(
                        f"OptionBoxManager.add_option: TOTAL (reused existing) in {total_duration:.3f}ms"
                    )
                return self

        # LAZY LOADING: Store option for later, don't wrap yet!
        self._pending_options.append(option)
        _log_step("store_pending")

        # Ensure the widget gets wrapped once it's part of a layout
        self._schedule_wrap_if_needed()

        if timing_enabled:
            total_duration = (time.perf_counter() - add_option_start) * 1000
            self.logger.debug(
                f"OptionBoxManager.add_option: TOTAL (deferred wrapping) in {total_duration:.3f}ms"
            )
        return self

    def _schedule_wrap_if_needed(self):
        """Schedule a wrap attempt once the widget is laid out.

        The option box needs to wrap the underlying widget to display buttons.
        When options are added before the widget has a parent/layout, we defer
        wrapping and retry once Qt has finished parenting operations.
        """

        if self._is_wrapped or not self._pending_options:
            return  # Nothing to do or already wrapped

        if self._wrap_retry_scheduled:
            return  # A retry is already pending

        self._wrap_retry_scheduled = True
        QtCore.QTimer.singleShot(0, self._attempt_wrap_when_ready)

    def _attempt_wrap_when_ready(self):
        """Attempt to wrap the widget, retrying until a parent exists."""

        self._wrap_retry_scheduled = False

        if self._is_wrapped or not self._pending_options:
            self._wrap_retry_count = 0
            return

        widget = getattr(self, "_widget", None)
        if widget is None:
            return

        parent = widget.parent()
        if parent is None:
            # Parent not assigned yet; retry with a small delay (up to a limit)
            if self._wrap_retry_count >= 50:
                self.logger.warning(
                    "OptionBoxManager: Unable to wrap option box - widget has no parent"
                )
                return

            self._wrap_retry_count += 1
            self._wrap_retry_scheduled = True
            QtCore.QTimer.singleShot(15, self._attempt_wrap_when_ready)
            return

        # Parent exists - perform the wrap now
        try:
            self._perform_wrap()
        finally:
            self._wrap_retry_count = 0

    @property
    def container(self):
        """Get the container widget (for layout management).

        LAZY LOADING TRIGGER: Accessing this property will trigger wrapping
        if there are pending options that haven't been wrapped yet.
        """
        import time

        container_start = time.perf_counter()

        # If we have pending options and haven't wrapped yet, do it now
        if self._pending_options and not self._is_wrapped:
            self.logger.debug(
                f"OptionBoxManager.container: Triggering lazy wrap for {len(self._pending_options)} pending options"
            )
            self._perform_wrap()
            duration_ms = (time.perf_counter() - container_start) * 1000
            self.logger.debug(
                f"OptionBoxManager.container: Lazy wrap completed in {duration_ms:.3f}ms"
            )

        # If we don't have a container yet, but widget has a menu with items,
        # try to get the container from the menu's option box
        if not self._container and hasattr(self._widget, "menu"):
            menu = self._widget.menu
            if (
                hasattr(menu, "option_box")
                and menu.option_box
                and hasattr(menu.option_box, "container")
            ):
                self._container = menu.option_box.container
                self._option_box = menu.option_box

        return self._container

    def _perform_wrap(self):
        """Perform the actual wrapping of pending options.

        This is called lazily when container is first accessed.
        Wraps the widget with all pending options at once for efficiency.
        """
        # PERFORMANCE: Only enable timing if logger level is DEBUG (10) or lower
        timing_enabled = self.logger.level <= 10

        if timing_enabled:
            import time

            wrap_start = time.perf_counter()
            _step_time = wrap_start

            def _log_step(step_name):
                nonlocal _step_time
                now = time.perf_counter()
                duration_ms = (now - _step_time) * 1000
                total_ms = (now - wrap_start) * 1000
                self.logger.debug(
                    f"OptionBoxManager._perform_wrap [{step_name}]: {duration_ms:.3f}ms (total: {total_ms:.3f}ms)"
                )
                _step_time = now

        else:

            def _log_step(step_name):
                pass

        if not self._pending_options:
            return  # Nothing to wrap

        from ._optionBox import OptionBoxWithOrdering

        _log_step("import_OptionBoxWithOrdering")

        # Create option box with ALL pending options at once
        self._option_box = OptionBoxWithOrdering(
            action_handler=None,  # Let plugins create buttons
            show_clear=self._clear_enabled,
            option_order=self._option_order,
            options=self._pending_options,  # Pass all pending options
        )
        _log_step("OptionBoxWithOrdering_created")

        # Perform the wrap (expensive operation - but only done once)
        self._container = self._option_box.wrap(self._widget)
        _log_step("wrap_widget")

        # Mark as wrapped and clear pending options
        self._is_wrapped = True
        self._pending_options = []
        _log_step("cleanup")

        if timing_enabled:
            total_duration = (time.perf_counter() - wrap_start) * 1000
            self.logger.debug(
                f"OptionBoxManager._perform_wrap: TOTAL wrap completed in {total_duration:.3f}ms"
            )

    def _update_option_box(self):
        """Update or create option box based on current settings.

        Note: With lazy loading, this won't trigger wrapping immediately.
        Wrapping only happens when .container is accessed.
        """
        from ._optionBox import OptionBox, OptionBoxWithOrdering

        # If we already have an option box, just update it
        if self._option_box:
            self._option_box.set_clear_button_visible(self._clear_enabled)
            if self._action_handler:
                self._option_box.set_action_handler(self._action_handler)
            return

        # Check if widget already has a menu with an option box
        existing_option_box = self._find_existing_option_box()

        if existing_option_box:
            # Use the existing option box from menu
            self._option_box = existing_option_box
            self._container = existing_option_box.container
            self._is_wrapped = True  # Mark as wrapped if using existing
            # Update its settings
            if self._clear_enabled:
                self._option_box.set_clear_button_visible(True)
        elif self._clear_enabled or self._action_handler:
            # Legacy path: Create and wrap immediately (for backward compatibility)
            # New code should use add_option() which defers wrapping
            self._create_option_box()

    def _find_existing_option_box(self):
        """Find existing option box created by menu or other systems"""
        from ._optionBox import OptionBox

        # Check if widget has a menu with an option box
        if hasattr(self._widget, "menu") and hasattr(self._widget.menu, "option_box"):
            menu_option_box = self._widget.menu.option_box
            if menu_option_box and hasattr(menu_option_box, "container"):
                return menu_option_box

        # Check if widget is already wrapped in an option box container
        parent = self._widget.parent()
        if (
            parent
            and hasattr(parent, "objectName")
            and parent.objectName() == "optionBoxContainer"
        ):
            # Find the option box widget in the container
            for child in parent.children():
                if isinstance(child, OptionBox):
                    return child

        return None

    def _create_option_box(self):
        """Create and wrap the option box (legacy immediate wrapping).

        This is kept for backward compatibility with old code paths.
        New code using add_option() will defer wrapping until container access.
        """
        from ._optionBox import OptionBoxWithOrdering

        self._option_box = OptionBoxWithOrdering(
            action_handler=self._action_handler,
            show_clear=self._clear_enabled,
            option_order=self._option_order,
        )
        self._container = self._option_box.wrap(self._widget)
        self._is_wrapped = True  # Mark as wrapped

    def _recreate_option_box(self):
        """Recreate option box with new settings"""
        if self._option_box and self._container:
            # Store current settings
            action_handler = self._action_handler
            clear_enabled = self._clear_enabled

            # Remove existing
            self.remove()

            # Recreate with new order
            self._action_handler = action_handler
            self._clear_enabled = clear_enabled
            self._create_option_box()

    def remove(self):
        """Remove option box completely"""
        if self._option_box and self._container:
            # Restore widget to original state
            parent = self._container.parent()
            if parent and parent.layout():
                parent.layout().replaceWidget(self._container, self._widget)
            else:
                self._widget.setParent(parent)
                self._widget.move(self._container.pos())

            self._container.deleteLater()
            self._option_box = None
            self._container = None
            self._clear_enabled = False
            self._action_handler = None
            self._menu = None
            self._is_wrapped = False
            self._pending_options = []  # Clear any pending options


# -------------------------------------------------------------------------
# Convenience functions for easy integration
# -------------------------------------------------------------------------


def add_option_box(widget, action=None, menu=None, show_clear=False, **kwargs):
    """Add an option box to any widget with one function call.

    Args:
        widget: The widget to wrap
        action: Action function to call when clicked
        menu: Menu object to show when clicked
        show_clear: Whether to show clear button for text widgets
        **kwargs: Additional options

    Returns:
        The container widget that should be added to layouts

    Example:
        line_edit = QtWidgets.QLineEdit()
        container = add_option_box(line_edit, show_clear=True)
        layout.addWidget(container)
    """
    from ._optionBox import OptionBox

    option_box = OptionBox(action=action, menu=menu, show_clear=show_clear, **kwargs)
    return option_box.wrap(widget)


def add_clear_option(widget, **kwargs):
    """Add just a clear button to a text widget.

    Args:
        widget: The text widget to add clear button to
        **kwargs: Additional options

    Returns:
        The container widget that should be added to layouts
    """
    return add_option_box(widget, show_clear=True, **kwargs)


def add_menu_option(widget, menu, **kwargs):
    """Add a menu option to any widget.

    Args:
        widget: The widget to wrap
        menu: Menu object to show
        **kwargs: Additional options

    Returns:
        The container widget that should be added to layouts
    """
    return add_option_box(widget, menu=menu, **kwargs)


# -------------------------------------------------------------------------
# Widget patching for elegant usage
# -------------------------------------------------------------------------


def patch_widget_class(widget_class):
    """Add option_box attribute to a widget class."""

    def get_option_box(self):
        """Get or create option box manager"""
        if not hasattr(self, "_option_box_manager"):
            self._option_box_manager = OptionBoxManager(self)
        return self._option_box_manager

    # Only add if not already present
    if not hasattr(widget_class, "option_box"):
        widget_class.option_box = property(get_option_box)
    return widget_class


def patch_common_widgets():
    """Patch common Qt widgets with option box support."""
    common_widgets = [
        QtWidgets.QLineEdit,
        QtWidgets.QTextEdit,
        QtWidgets.QPlainTextEdit,
        QtWidgets.QPushButton,
        QtWidgets.QComboBox,
        QtWidgets.QSpinBox,
        QtWidgets.QDoubleSpinBox,
    ]

    for widget_class in common_widgets:
        patch_widget_class(widget_class)
