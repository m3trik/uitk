# !/usr/bin/python
# coding=utf-8
"""Deferred wrapping for :class:`OptionBoxManager`: options queue until the
widget has a parent, then the widget is wrapped in its container once."""

from qtpy import QtCore


class _OptionBoxWrapMixin:
    """Queue options until the widget is parented, then wrap it in an
    :class:`OptionBoxContainer` exactly once (a partial of
    :class:`OptionBoxManager`)."""

    def _schedule_wrap_if_needed(self):
        """Schedule a wrap attempt once the widget is laid out.

        The option box needs to wrap the underlying widget to display buttons.
        Strategy:

        - **Fast path (parent already attached)**: perform the wrap
          synchronously.  The vast majority of slot-init calls happen with
          the widget already inserted into a layout, so this is the common
          case.  Running the wrap synchronously means the
          ``parent.layout().replaceWidget(...)`` reparent completes before
          ``MainWindow.showEvent`` returns control to the event loop —
          eliminating the visible flicker between ``super().showEvent()``
          and the deferred-timer-driven wrap firing on the next tick.

        - **Slow path (parent missing)**: fall back to the
          ``_schedule_wrap_retry`` / ``_attempt_wrap_when_ready`` retry loop
          so widgets parented late (e.g. via ``setParent`` after
          construction) still get wrapped once their parent attaches.

        Re-entrancy: ``_perform_wrap`` reparents *this* widget into a new
        ``OptionBoxContainer``.  ``register_children`` walks via a
        ``findChildren`` snapshot, so reparenting mid-walk is safe.
        Menu-item registration (Contract 2) remains deferred via the
        coalesced drain in :class:`Menu`.

        **Observable consequence for slot authors**: when called from
        inside a ``<name>_init(widget)`` body (which is the normal entry
        point), ``widget.parent()`` changes *during* the slot body — from
        the original layout parent (e.g. the central widget) to the new
        ``OptionBoxContainer``.  Code in the slot body that reads
        ``widget.parent()`` *after* wiring an option must account for
        this; reading it *before* the option_box call sees the original
        parent.  No tentacle / mayatk slot in the current monorepo
        relies on the post-wiring parent (verified by grep).
        """

        if self._is_wrapped or not self._pending_options:
            return  # Nothing to do or already wrapped

        if self._wrap_retry_scheduled:
            return  # A retry is already pending

        widget = getattr(self, "_widget", None)
        if widget is not None and widget.parent() is not None:
            # Fast path: synchronous wrap — completes before showEvent paints.
            self._perform_wrap()
            return

        self._wrap_retry_scheduled = True
        self._schedule_wrap_retry(0)

    def _schedule_wrap_retry(self, delay_ms: int) -> None:
        """Arm the retry-until-parented timer, parented to the wrapped widget
        (not a bare ``QTimer.singleShot``) so it is destroyed along with the
        widget instead of firing ``_attempt_wrap_when_ready`` into a deleted
        ``self._widget`` (observed live: ``RuntimeError: Internal C++ object
        ... already deleted`` from ``widget.parent()`` when a widget is torn
        down mid-retry, e.g. test teardown right after construction)."""
        widget = getattr(self, "_widget", None)
        if widget is None:
            return
        if self._wrap_retry_timer is None:
            self._wrap_retry_timer = QtCore.QTimer(widget)
            self._wrap_retry_timer.setSingleShot(True)
            self._wrap_retry_timer.timeout.connect(self._attempt_wrap_when_ready)
        self._wrap_retry_timer.start(delay_ms)

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
            self._schedule_wrap_retry(15)
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
        # If we have pending options and haven't wrapped yet, do it now
        if self._pending_options and not self._is_wrapped:
            self.logger.debug(
                f"OptionBoxManager.container: Triggering lazy wrap for {len(self._pending_options)} pending options"
            )
            self._perform_wrap()

        # If we don't have a container yet, but widget has a menu with items,
        # try to get the container from the menu's option box. Use the
        # non-creating ``has_menu`` check — ``hasattr(widget, "menu")`` would
        # materialize a context menu via the lazy MenuMixin descriptor.
        if not self._container and getattr(self._widget, "has_menu", False):
            menu = self._widget.menu
            if (
                hasattr(menu, "option_box")
                and menu.option_box
                and hasattr(menu.option_box, "container")
            ):
                self._container = menu.option_box.container
                self._option_box = menu.option_box
                # The adopted box already wraps the widget; mark wrapped so a
                # later add_option routes through the direct-add branch instead
                # of building a SECOND OptionBox and re-wrapping the widget
                # (which corrupts the layout). Mirrors the two sibling adoption
                # sites (add_option reuse branch and _update_option_box).
                self._is_wrapped = True

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

        from ._optionBox import OptionBox

        _log_step("import_OptionBox")

        # Create option box with ALL pending options at once
        self._option_box = OptionBox(
            show_clear=self._clear_enabled,
            option_order=self._option_order,
            options=self._pending_options,
        )
        _log_step("OptionBox_created")

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
        """Update option box based on current settings."""
        # If we already have an option box, just update it
        if self._option_box:
            self._option_box.set_clear_button_visible(self._clear_enabled)
            return

        # Check if widget already has a menu with an option box
        existing_option_box = self._find_existing_option_box()

        if existing_option_box:
            # Use the existing option box from menu
            self._option_box = existing_option_box
            self._container = existing_option_box.container
            self._is_wrapped = True
            # Migrate already-queued options into the adopted box so they aren't
            # dropped once _is_wrapped short-circuits the deferred wrap path.
            for pending in self._pending_options:
                self._option_box.add_option(pending)
            self._pending_options = []
            if self._clear_enabled:
                self._option_box.set_clear_button_visible(True)
        elif self._clear_enabled:
            # Create and wrap immediately if clear is enabled
            self._create_option_box()

    def _find_existing_option_box(self):
        """Find existing option box created by menu or other systems.

        Uses the non-creating ``has_menu`` check instead of touching
        ``widget.menu`` directly: the MenuMixin ``.menu`` descriptor lazily
        *creates* a standalone context menu on first access, so probing it
        here would materialize an otherwise-unused menu for every wrapped
        widget at register time.
        """
        if not getattr(self._widget, "has_menu", False):
            return None

        menu = self._widget.menu
        if hasattr(menu, "option_box"):
            menu_option_box = menu.option_box
            if menu_option_box and hasattr(menu_option_box, "container"):
                return menu_option_box

        return None

    def _create_option_box(self):
        """Create and wrap the option box."""
        from ._optionBox import OptionBox

        # Include any pending plugins
        pending = self._pending_options or None

        self._option_box = OptionBox(
            show_clear=self._clear_enabled,
            option_order=self._option_order,
            options=pending,
        )
        self._container = self._option_box.wrap(self._widget)
        self._is_wrapped = True

        # Clear pending options
        self._pending_options = []
        self._wrap_retry_scheduled = False

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
            self._menu = None
            self._is_wrapped = False
            self._pending_options = []
