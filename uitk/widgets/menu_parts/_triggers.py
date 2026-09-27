# !/usr/bin/python
# coding=utf-8
"""How the menu is opened and dismissed by what it is attached to.

The trigger hook -- a ``clicked`` / ``pressed`` signal on the anchor for
left-click menus, an event filter on it otherwise -- toggles the menu on the
configured ``trigger_button``; ``trigger_from_widget`` is the same toggle for a
programmatic caller. ``hide_on_trigger`` dismisses the menu once one of its
items is released on (per-item overrides via ``set_hide_on_trigger``).

One part of :class:`~uitk.widgets.menu.Menu`, which inherits it; it holds no
state of its own (``Menu.__init__`` declares every attribute used here) and
is never instantiated alone.
"""

import warnings
from typing import Optional, Union

from qtpy import QtCore, QtWidgets

from uitk.widgets.mixins.convert import ConvertMixin
from uitk.widgets.separator import Separator


class _MenuTriggersMixin:
    """How the menu is opened and dismissed by what it is attached to."""

    def _should_trigger(self, button: QtCore.Qt.MouseButton) -> bool:
        """Check if the given button should trigger the menu.

        This centralizes all button-checking logic in one place.

        Parameters:
            button: The mouse button that was pressed

        Returns:
            True if this button should trigger the menu, False otherwise
        """
        # False sentinel = no auto-trigger (menu must be shown manually)
        if self.trigger_button is False:
            return False

        # No trigger button restriction - allow any button
        if self.trigger_button is None:
            return True

        # Single button restriction
        if isinstance(self.trigger_button, QtCore.Qt.MouseButton):
            return button == self.trigger_button

        # Multiple buttons allowed (tuple)
        if isinstance(self.trigger_button, (tuple, list)):
            return button in self.trigger_button

        return False

    @property
    def trigger_button(self) -> Union[QtCore.Qt.MouseButton, tuple, None, bool]:
        """Get the current trigger button(s).

        Returns:
            QtCore.Qt.MouseButton: Single button constant
            tuple: Multiple button constants
            None: Any button triggers
            False: No auto-trigger (manual show only)
        """
        return self._trigger_button

    @trigger_button.setter
    def trigger_button(
        self, value: Union[QtCore.Qt.MouseButton, str, tuple, list, None]
    ) -> None:
        """Set the trigger button(s).

        Accepts Qt constants, strings ("left", "right", "middle", "any", "none"), or tuples/lists.

        Parameters:
            value: Single button (Qt constant or string), tuple/list of buttons,
                  "any" for any button, or "none" to disable auto-triggering
        """
        # Use ConvertMixin to normalize the value
        try:
            self._trigger_button = ConvertMixin.to_qmousebutton(value)
        except ValueError as e:
            self.logger.warning(f"{e}. Defaulting to LeftButton.")
            self._trigger_button = QtCore.Qt.LeftButton

        # Left-click menus act like instant-action menus:
        # - No apply button (actions execute immediately)
        # - Auto-hide when mouse leaves (like standard menus)
        if self._trigger_button == QtCore.Qt.LeftButton:
            self.add_apply_button = False
            self.hide_on_leave = True

        # Keep trigger event filters in sync with the trigger_button setting
        if self._trigger_button is False:
            self._uninstall_event_filters()
        else:
            # Install filters immediately if we already have content/parent
            if self.contains_items and not (
                self._event_filters_installed or self._parent_signal_source
            ):
                self._ensure_trigger_hook()

    # ------------------------------------------------------------------
    # Hide on trigger (dismiss the menu after an item is interacted with)
    # ------------------------------------------------------------------

    def set_hide_on_trigger(
        self, widget: QtWidgets.QWidget, hide: Optional[bool]
    ) -> None:
        """Include/exclude one item from the menu-level :attr:`hide_on_trigger`.

        Parameters:
            widget: A menu item (as returned by :meth:`add`).
            hide: ``True`` — this item always hides the menu when triggered;
                ``False`` — this item never hides it; ``None`` — clear the
                override and follow the menu-level setting again.
        """
        widget.setProperty("hide_on_trigger", hide)

    def _resolve_hide_on_trigger(self, widget: QtWidgets.QWidget) -> bool:
        """Effective hide-on-trigger for *widget*: its override, else the menu's."""
        override = widget.property("hide_on_trigger")
        if override is not None:
            return bool(override)
        # Separators are non-interactive: a release on a titled section row is
        # not a trigger, so it must not dismiss the menu. (An explicit
        # per-widget include above still wins.)
        if isinstance(widget, Separator):
            return False
        return bool(self.hide_on_trigger)

    def _is_wrapped_item(self, widget, items) -> bool:
        """True when *widget* is an added item now nested under a grid cell.

        An option-box wrap replaces the item with its container in the grid
        layout; the event filter installed at ``add()`` time still reports the
        original widget, so resolve through its parent chain (up to this menu).
        """
        if not isinstance(widget, QtWidgets.QWidget):
            return False
        parent = widget.parentWidget()
        while parent is not None and parent is not self:
            if parent in items:
                return True
            parent = parent.parentWidget()
        return False

    def _handle_nested_trigger(self, container, item) -> None:
        """Hide-on-trigger for interactions nested inside a container item.

        Connected at ``add()`` time to a container's ``on_item_interacted``
        (e.g. an ``ExpandableList`` menu row, whose internal releases the menu's
        own release filter never sees). Only a LEAF interaction is a trigger —
        an item with a populated sublist is navigation. The hide resolves
        against the *container* row, so ``set_hide_on_trigger`` overrides apply
        to it like any other item.
        """
        sub = getattr(item, "sublist", None)
        if sub is not None and sub.get_items():
            return
        if self._resolve_hide_on_trigger(container):
            self._schedule_hide_on_trigger()

    def _schedule_hide_on_trigger(self) -> None:
        """Hide on the next event-loop tick.

        Deferred so the triggering mouse-release finishes delivery to the item
        first — hiding synchronously from inside the event filter would tear
        the item down before its own clicked/released signals fire.
        """
        if self._trigger_hide_timer is None:
            self._trigger_hide_timer = QtCore.QTimer(self)
            self._trigger_hide_timer.setSingleShot(True)
            self._trigger_hide_timer.timeout.connect(self.hide)
        self._trigger_hide_timer.start(0)

    def _get_anchor_widget(self) -> Optional[QtWidgets.QWidget]:
        """Get the effective anchor widget (parent or filter target)."""
        return self.parent() or self._filter_target

    def _get_parent_signal_slot(self, signal_name: str):
        """Get the appropriate slot for a parent signal name."""
        if signal_name in ("clicked", "pressed"):
            return self._on_parent_triggered
        return None

    def _disconnect_parent_signal(self) -> None:
        if not self._parent_signal_source:
            return

        parent, signal_name = self._parent_signal_source
        slot = self._get_parent_signal_slot(signal_name)
        if parent and slot:
            # Use warnings filter to suppress PyQt's RuntimeWarning when slot wasn't connected
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    getattr(parent, signal_name).disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
        self.logger.debug(
            f"Menu._disconnect_parent_signal: Disconnected {signal_name} from {parent}"
        )
        self._parent_signal_source = None

    def _connect_parent_signal(self, parent: QtWidgets.QWidget) -> bool:
        """Attempt to hook into the parent's Qt signal for triggering."""
        # Always disconnect any previous connection before wiring a new one
        self._disconnect_parent_signal()

        # Try to find a suitable signal
        signal_name = None
        if hasattr(parent, "clicked"):
            signal_name = "clicked"
        elif hasattr(parent, "pressed"):
            signal_name = "pressed"
        else:
            return False

        slot = self._on_parent_triggered
        signal = getattr(parent, signal_name)

        # Disconnect any existing connection and connect the slot
        # Use warnings filter to suppress PyQt's RuntimeWarning when slot wasn't connected
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

        try:
            signal.connect(slot)
        except (TypeError, RuntimeError):
            return False

        self._parent_signal_source = (parent, signal_name)
        self.logger.debug(
            f"Menu._connect_parent_signal: Connected {signal_name} signal on {parent}"
        )
        return True

    def _remove_parent_event_filter(self) -> None:
        if self._event_filters_installed:
            try:
                self.removeEventFilter(self)
            except Exception:
                pass

        if self._filter_target:
            try:
                self._filter_target.removeEventFilter(self)
            except Exception:
                pass
            self._filter_target = None

        self._event_filters_installed = False
        self._pending_event_filter_install = False

    def _ensure_trigger_hook(self) -> None:
        """Ensure the menu connects to its trigger source (signal or event filter)."""
        if self._trigger_button is False:
            self._disconnect_parent_signal()
            if self._event_filters_installed or self._filter_target:
                self._remove_parent_event_filter()
            self._pending_trigger_hook = False
            self._pending_event_filter_install = False
            return

        parent = self._get_anchor_widget()
        if parent is None:
            self._pending_trigger_hook = True
            self._pending_event_filter_install = True
            self.logger.debug(
                "Menu._ensure_trigger_hook: Parent unavailable, deferring"
            )
            return

        # Prefer signal-based triggering for left-button clicks
        if self._trigger_button == QtCore.Qt.LeftButton and self._connect_parent_signal(
            parent
        ):
            if self._event_filters_installed or self._filter_target:
                self._remove_parent_event_filter()
            self._pending_trigger_hook = False
            self._pending_event_filter_install = False
            return

        # Fallback to event filters when signals aren't available or for non-left triggers
        self._disconnect_parent_signal()

        if not self._event_filters_installed:
            self.installEventFilter(self)
            parent.installEventFilter(self)
            self._filter_target = parent
            self._event_filters_installed = True
            self.logger.debug(
                f"Menu._ensure_trigger_hook: Installed event filter on {parent}"
            )
        elif self._filter_target is not parent:
            if self._filter_target:
                try:
                    self._filter_target.removeEventFilter(self)
                except Exception:
                    pass
            parent.installEventFilter(self)
            self._filter_target = parent
            self.logger.debug(
                f"Menu._ensure_trigger_hook: Updated event filter target to {parent}"
            )

        self._pending_trigger_hook = False
        self._pending_event_filter_install = False

    def _uninstall_event_filters(self):
        """Remove any trigger hooks (signals or event filters)."""
        if not self._event_filters_installed and not self._parent_signal_source:
            self._pending_event_filter_install = False
            self._pending_trigger_hook = False
            return

        self._disconnect_parent_signal()
        if self._event_filters_installed or self._filter_target:
            self._remove_parent_event_filter()

        self._pending_event_filter_install = False
        self._pending_trigger_hook = False
        self.logger.debug("Menu._uninstall_event_filters: Trigger hooks removed")

    def _on_parent_triggered(self, checked: bool = False) -> None:  # type: ignore[override]
        """Handle parent widget signal (clicked or pressed)."""
        if self.is_pinned:
            return
        self.trigger_from_widget(self._get_anchor_widget(), button=QtCore.Qt.LeftButton)

    # Alias for backward compatibility
    _install_event_filters = _ensure_trigger_hook

    def eventFilter(self, widget, event):
        """Handle events for the menu and its children.

        This filter handles:
        - Parent widget clicks to toggle menu visibility
        - Parent hide events to auto-hide menu
        - Item interactions to emit signals
        """
        event_type = event.type()
        parent_widget = self._get_anchor_widget()

        if event_type == QtCore.QEvent.MouseButtonPress and widget is parent_widget:
            # Use centralized trigger logic
            if self._should_trigger(event.button()):
                new_state = not self.isVisible()
                # Don't hide if pinned (but allow showing)
                if not new_state and self.is_pinned:
                    self.logger.debug(
                        "eventFilter: Menu is pinned, ignoring hide request"
                    )
                else:
                    self.logger.debug(
                        f"eventFilter: Parent clicked, toggling menu visibility to {new_state}"
                    )
                    self.setVisible(new_state)

        elif event_type == QtCore.QEvent.Hide and widget is parent_widget:
            # Hide menu when parent is hidden (unless pinned)
            if self.isVisible() and not self.is_pinned:
                self.hide()

        elif event_type == QtCore.QEvent.MouseButtonRelease:
            items = self.get_items()
            is_item = widget in items
            if is_item:
                self.logger.debug(
                    f"eventFilter: Item interacted: {widget.objectName() or type(widget).__name__}"
                )
                self.on_item_interacted.emit(widget)
            # Dismissal also resolves through an option-box wrap (the wrap
            # replaces the item with its container in the grid, so the direct
            # membership test misses it). on_item_interacted keeps its
            # historical direct-item scope — external consumers depend on it.
            if (
                is_item or self._is_wrapped_item(widget, items)
            ) and self._resolve_hide_on_trigger(widget):
                self._schedule_hide_on_trigger()

        return super().eventFilter(widget, event)

    def trigger_from_widget(
        self,
        widget: Optional[QtWidgets.QWidget] = None,
        *,
        button: QtCore.Qt.MouseButton = QtCore.Qt.LeftButton,
    ) -> None:
        """Toggle visibility using the same rules as the parent click event.

        This method allows programmatic triggering of the menu without
        requiring a parent widget or event filter. It respects the same
        trigger button constraints as interactive clicks.

        Parameters:
            widget: Optional anchor widget to position the menu relative to
            button: The mouse button to simulate (default: LeftButton)
        """
        # Don't allow hiding if menu is pinned
        if self.is_pinned:
            return

        # Use centralized trigger logic
        if not self._should_trigger(button):
            return

        # Toggle visibility
        if not self.isVisible():
            # Show using popup method if we have an anchor widget
            if widget:
                self.show_as_popup(
                    anchor_widget=widget, position=self.position or "bottom"
                )
            else:
                self.setVisible(True)
                self.raise_()
                self.activateWindow()
        else:
            self.hide()
