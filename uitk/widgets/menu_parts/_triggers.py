# !/usr/bin/python
# coding=utf-8
"""How the menu is opened and dismissed by what it is attached to.

The trigger hook -- a ``clicked`` / ``pressed`` signal on the anchor for
left-click menus, an event filter on it otherwise -- toggles the menu on the
configured ``trigger_button``; ``trigger_from_widget`` is the same toggle for a
programmatic caller. ``hide_on_trigger`` dismisses the menu once one of its
items is released on (per-item overrides via ``set_hide_on_trigger``).

One part of :class:`~uitk.widgets.menu.Menu` (see ``menu_parts``).
"""

import warnings
from typing import TYPE_CHECKING, Optional, Tuple, Union

from qtpy import QtCore, QtWidgets

from uitk.widgets.mixins.convert import ConvertMixin
from uitk.widgets.separator import Separator

if TYPE_CHECKING:
    from uitk.widgets.menu import Menu


class _MenuTrigger:
    """How a :class:`Menu` is opened and dismissed by what it is attached to.

    Owns the normalized trigger button and the hook state: the anchor signal
    it connected, or the anchor it filters. Signal connections and the
    filters themselves go to the menu (a QObject), so they die with it.
    """

    def __init__(self, menu: "Menu") -> None:
        self._menu = menu
        # The normalized value behind ``Menu.trigger_button`` (see set_button).
        self.button: Union[QtCore.Qt.MouseButton, tuple, None, bool] = None
        self.event_filters_installed = False
        self.filter_target: Optional[QtWidgets.QWidget] = None
        self.pending_event_filter_install = False
        self.parent_signal_source: Optional[Tuple[QtWidgets.QWidget, str]] = None
        self.pending_trigger_hook = False
        # Deferred hide used by hide_on_trigger (parented to the menu so it
        # dies with it instead of firing into a deleted widget).
        self.hide_timer: Optional[QtCore.QTimer] = None

    def should_trigger(self, button: QtCore.Qt.MouseButton) -> bool:
        """Check if the given button should trigger the menu.

        This centralizes all button-checking logic in one place.

        Parameters:
            button: The mouse button that was pressed

        Returns:
            True if this button should trigger the menu, False otherwise
        """
        trigger_button = self.button
        # False sentinel = no auto-trigger (menu must be shown manually)
        if trigger_button is False:
            return False

        # No trigger button restriction - allow any button
        if trigger_button is None:
            return True

        # Single button restriction
        if isinstance(trigger_button, QtCore.Qt.MouseButton):
            return button == trigger_button

        # Multiple buttons allowed (tuple)
        if isinstance(trigger_button, (tuple, list)):
            return button in trigger_button

        return False

    def set_button(
        self, value: Union[QtCore.Qt.MouseButton, str, tuple, list, None]
    ) -> None:
        """Normalize and apply a ``trigger_button`` value (see :attr:`Menu.trigger_button`)."""
        menu = self._menu
        # Use ConvertMixin to normalize the value
        try:
            self.button = ConvertMixin.to_qmousebutton(value)
        except ValueError as e:
            menu.logger.warning(f"{e}. Defaulting to LeftButton.")
            self.button = QtCore.Qt.LeftButton

        # Left-click menus act like instant-action menus:
        # - No apply button (actions execute immediately)
        # - Auto-hide when mouse leaves (like standard menus)
        if self.button == QtCore.Qt.LeftButton:
            menu.add_apply_button = False
            menu.hide_on_leave = True

        # Keep trigger event filters in sync with the trigger_button setting
        if self.button is False:
            self.uninstall_event_filters()
        else:
            # Install filters immediately if we already have content/parent
            if menu.contains_items and not (
                self.event_filters_installed or self.parent_signal_source
            ):
                menu._ensure_trigger_hook()

    # ------------------------------------------------------------------
    # Hide on trigger (dismiss the menu after an item is interacted with)
    # ------------------------------------------------------------------

    def resolve_hide_on_trigger(self, widget: QtWidgets.QWidget) -> bool:
        """Effective hide-on-trigger for *widget*: its override, else the menu's."""
        override = widget.property("hide_on_trigger")
        if override is not None:
            return bool(override)
        # Separators are non-interactive: a release on a titled section row is
        # not a trigger, so it must not dismiss the menu. (An explicit
        # per-widget include above still wins.)
        if isinstance(widget, Separator):
            return False
        return bool(self._menu.hide_on_trigger)

    def is_wrapped_item(self, widget, items) -> bool:
        """True when *widget* is an added item now nested under a grid cell.

        An option-box wrap replaces the item with its container in the grid
        layout; the event filter installed at ``add()`` time still reports the
        original widget, so resolve through its parent chain (up to this menu).
        """
        if not isinstance(widget, QtWidgets.QWidget):
            return False
        menu = self._menu
        parent = widget.parentWidget()
        while parent is not None and parent is not menu:
            if parent in items:
                return True
            parent = parent.parentWidget()
        return False

    def handle_nested_trigger(self, container, item) -> None:
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
        if self.resolve_hide_on_trigger(container):
            self.schedule_hide_on_trigger()

    def schedule_hide_on_trigger(self) -> None:
        """Hide on the next event-loop tick.

        Deferred so the triggering mouse-release finishes delivery to the item
        first — hiding synchronously from inside the event filter would tear
        the item down before its own clicked/released signals fire.
        """
        if self.hide_timer is None:
            menu = self._menu
            self.hide_timer = QtCore.QTimer(menu)
            self.hide_timer.setSingleShot(True)
            self.hide_timer.timeout.connect(menu.hide)
        self.hide_timer.start(0)

    # ------------------------------------------------------------------
    # The trigger hook
    # ------------------------------------------------------------------

    def get_anchor_widget(self) -> Optional[QtWidgets.QWidget]:
        """Get the effective anchor widget (parent or filter target)."""
        return self._menu.parent() or self.filter_target

    def get_parent_signal_slot(self, signal_name: str):
        """Get the appropriate slot for a parent signal name."""
        if signal_name in ("clicked", "pressed"):
            return self._menu._on_parent_triggered
        return None

    def disconnect_parent_signal(self) -> None:
        if not self.parent_signal_source:
            return

        parent, signal_name = self.parent_signal_source
        slot = self.get_parent_signal_slot(signal_name)
        if parent and slot:
            # Use warnings filter to suppress PyQt's RuntimeWarning when slot wasn't connected
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    getattr(parent, signal_name).disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
        self._menu.logger.debug(
            f"Menu._disconnect_parent_signal: Disconnected {signal_name} from {parent}"
        )
        self.parent_signal_source = None

    def connect_parent_signal(self, parent: QtWidgets.QWidget) -> bool:
        """Attempt to hook into the parent's Qt signal for triggering."""
        # Always disconnect any previous connection before wiring a new one
        self.disconnect_parent_signal()

        # Try to find a suitable signal
        signal_name = None
        if hasattr(parent, "clicked"):
            signal_name = "clicked"
        elif hasattr(parent, "pressed"):
            signal_name = "pressed"
        else:
            return False

        # The menu's own slot (not this part's): a QObject receiver, so the
        # connection drops when the menu is destroyed.
        slot = self._menu._on_parent_triggered
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

        self.parent_signal_source = (parent, signal_name)
        self._menu.logger.debug(
            f"Menu._connect_parent_signal: Connected {signal_name} signal on {parent}"
        )
        return True

    def remove_parent_event_filter(self) -> None:
        menu = self._menu
        if self.event_filters_installed:
            try:
                menu.removeEventFilter(menu)
            except Exception:
                pass

        if self.filter_target:
            try:
                self.filter_target.removeEventFilter(menu)
            except Exception:
                pass
            self.filter_target = None

        self.event_filters_installed = False
        self.pending_event_filter_install = False

    def ensure_trigger_hook(self) -> None:
        """Ensure the menu connects to its trigger source (signal or event filter)."""
        menu = self._menu
        if self.button is False:
            self.disconnect_parent_signal()
            if self.event_filters_installed or self.filter_target:
                self.remove_parent_event_filter()
            self.pending_trigger_hook = False
            self.pending_event_filter_install = False
            return

        parent = self.get_anchor_widget()
        if parent is None:
            self.pending_trigger_hook = True
            self.pending_event_filter_install = True
            menu.logger.debug(
                "Menu._ensure_trigger_hook: Parent unavailable, deferring"
            )
            return

        # Prefer signal-based triggering for left-button clicks
        if self.button == QtCore.Qt.LeftButton and self.connect_parent_signal(parent):
            if self.event_filters_installed or self.filter_target:
                self.remove_parent_event_filter()
            self.pending_trigger_hook = False
            self.pending_event_filter_install = False
            return

        # Fallback to event filters when signals aren't available or for non-left triggers
        self.disconnect_parent_signal()

        if not self.event_filters_installed:
            menu.installEventFilter(menu)
            parent.installEventFilter(menu)
            self.filter_target = parent
            self.event_filters_installed = True
            menu.logger.debug(
                f"Menu._ensure_trigger_hook: Installed event filter on {parent}"
            )
        elif self.filter_target is not parent:
            if self.filter_target:
                try:
                    self.filter_target.removeEventFilter(menu)
                except Exception:
                    pass
            parent.installEventFilter(menu)
            self.filter_target = parent
            menu.logger.debug(
                f"Menu._ensure_trigger_hook: Updated event filter target to {parent}"
            )

        self.pending_trigger_hook = False
        self.pending_event_filter_install = False

    def uninstall_event_filters(self):
        """Remove any trigger hooks (signals or event filters)."""
        if not self.event_filters_installed and not self.parent_signal_source:
            self.pending_event_filter_install = False
            self.pending_trigger_hook = False
            return

        self.disconnect_parent_signal()
        if self.event_filters_installed or self.filter_target:
            self.remove_parent_event_filter()

        self.pending_event_filter_install = False
        self.pending_trigger_hook = False
        self._menu.logger.debug("Menu._uninstall_event_filters: Trigger hooks removed")

    def on_parent_triggered(self) -> None:
        """Handle parent widget signal (clicked or pressed)."""
        menu = self._menu
        if menu.is_pinned:
            return
        menu.trigger_from_widget(self.get_anchor_widget(), button=QtCore.Qt.LeftButton)

    def filter(self, widget, event) -> None:
        """The menu's share of :meth:`Menu.eventFilter` (which then defers to Qt)."""
        menu = self._menu
        event_type = event.type()
        parent_widget = self.get_anchor_widget()

        if event_type == QtCore.QEvent.MouseButtonPress and widget is parent_widget:
            # Use centralized trigger logic
            if self.should_trigger(event.button()):
                new_state = not menu.isVisible()
                # Don't hide if pinned (but allow showing)
                if not new_state and menu.is_pinned:
                    menu.logger.debug(
                        "eventFilter: Menu is pinned, ignoring hide request"
                    )
                else:
                    menu.logger.debug(
                        f"eventFilter: Parent clicked, toggling menu visibility to {new_state}"
                    )
                    menu.setVisible(new_state)

        elif event_type == QtCore.QEvent.Hide and widget is parent_widget:
            # Hide menu when parent is hidden (unless pinned)
            if menu.isVisible() and not menu.is_pinned:
                menu.hide()

        elif event_type == QtCore.QEvent.MouseButtonRelease:
            items = menu.get_items()
            is_item = widget in items
            if is_item:
                menu.logger.debug(
                    f"eventFilter: Item interacted: {widget.objectName() or type(widget).__name__}"
                )
                menu.on_item_interacted.emit(widget)
            # Dismissal also resolves through an option-box wrap (the wrap
            # replaces the item with its container in the grid, so the direct
            # membership test misses it). on_item_interacted keeps its
            # historical direct-item scope — external consumers depend on it.
            if (
                is_item or self.is_wrapped_item(widget, items)
            ) and self.resolve_hide_on_trigger(widget):
                self.schedule_hide_on_trigger()

    def trigger_from_widget(
        self,
        widget: Optional[QtWidgets.QWidget] = None,
        button: QtCore.Qt.MouseButton = QtCore.Qt.LeftButton,
    ) -> None:
        menu = self._menu
        # Don't allow hiding if menu is pinned
        if menu.is_pinned:
            return

        # Use centralized trigger logic
        if not self.should_trigger(button):
            return

        # Toggle visibility
        if not menu.isVisible():
            # Show using popup method if we have an anchor widget
            if widget:
                menu.show_as_popup(
                    anchor_widget=widget, position=menu.position or "bottom"
                )
            else:
                menu.setVisible(True)
                menu.raise_()
                menu.activateWindow()
        else:
            menu.hide()
