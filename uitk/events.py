# !/usr/bin/python
# coding=utf-8
"""Event handling utilities for Qt applications.

This module provides event filters and mouse tracking utilities for
enhanced widget interaction and event management.

Classes:
    EventFactoryFilter: Dynamic event filter with lazy handler resolution
        and scoped widget control. Allows forwarding events to custom handlers.
    MouseTracking: QObject subclass providing mouse enter/leave events for
        QWidget child widgets, useful for hover detection.

Example:
    Using EventFactoryFilter to handle child widget events::

        class MyHandler:
            def child_mousePressEvent(self, event, widget):
                print(f"Clicked on {widget.objectName()}")

        handler = MyHandler()
        filter = EventFactoryFilter(
            forward_events_to=handler,
            event_name_prefix="child_",
            event_types={"MouseButtonPress"}
        )
        filter.install(my_widget)

    Using MouseTracking for hover effects::

        tracker = MouseTracking(parent_widget)
        tracker.enter.connect(lambda w: w.setStyleSheet("background: blue"))
        tracker.leave.connect(lambda w: w.setStyleSheet(""))
"""
import weakref
from typing import Iterable
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk


class EventFactoryFilter(QtCore.QObject):
    """Efficient dynamic event filter with lazy handler resolution and scoped widget control.

    Parameters:
        parent (QObject): Optional parent object.
        forward_events_to (object): Target object that defines the event handler methods.
        event_name_prefix (str): Prefix prepended to handler method names. Example: 'child_' → 'child_mousePressEvent'.
        event_types (set[str | int]): Event types to watch, given as QEvent.Type enums or their string names.
        propagate_to_children (bool): If False (default), only calls handlers for widgets explicitly passed to `install()`.
    """

    def __init__(
        self,
        parent: QtCore.QObject = None,
        forward_events_to: object = None,
        event_name_prefix: str = "",
        event_types: set[str | int] = None,
        propagate_to_children: bool = False,
    ):
        super().__init__(parent)
        self.forward_events_to = forward_events_to or self
        self.event_name_prefix = event_name_prefix
        self.event_types: set[int] = {
            self._normalize_event_type(e) for e in (event_types or set())
        }
        self.propagate_to_children = propagate_to_children
        self._handler_cache: dict[tuple[int, int], callable | None] = {}
        self._installed_widgets: "weakref.WeakSet[QtCore.QObject]" = weakref.WeakSet()

    def install(self, widgets: QtCore.QObject | Iterable[QtCore.QObject]):
        """Install this event filter on one or more widgets."""

        for w in ptk.make_iterable(widgets):
            w.installEventFilter(self)
            if not self.propagate_to_children:
                self._installed_widgets.add(w)
                self._track_widget_lifecycle(w)

    def _track_widget_lifecycle(self, widget: QtCore.QObject):
        """Connect destroyed signal so we can auto-uninstall tracked widgets."""

        wr = weakref.ref(widget)

        def _on_destroyed(obj=None, wr=wr):
            dead_widget = wr()
            if dead_widget:
                self.uninstall(dead_widget)

        widget.destroyed.connect(_on_destroyed)

    def uninstall(self, widgets: QtCore.QObject | Iterable[QtCore.QObject]):
        """Uninstall this event filter from one or more widgets."""
        for w in ptk.make_iterable(widgets):
            w.removeEventFilter(self)
            self._installed_widgets.discard(w)

    def is_installed(self, widget: QtCore.QObject) -> bool:
        """Return whether a widget is being tracked (only valid if propagate_to_children=False)."""
        return widget in self._installed_widgets

    def eventFilter(self, widget: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Event filter method that processes events and calls the appropriate handler."""
        try:
            if widget is None:
                return False
        except RuntimeError:
            return False

        etype = event.type()

        if etype not in self.event_types:
            return False

        if not self.propagate_to_children and widget not in self._installed_widgets:
            return False

        cache_key = (id(self.forward_events_to), etype)
        handler = self._handler_cache.get(cache_key)
        if handler is None:
            method_name = self._format_event_name(etype)
            handler = getattr(self.forward_events_to, method_name, None)
            self._handler_cache[cache_key] = handler

        if handler:
            try:
                return bool(handler(widget, event))
            except RuntimeError:
                return False

        return False

    def _normalize_event_type(self, etype: str | int) -> int:
        """Normalize event type to an integer value."""
        if isinstance(etype, int):
            return etype
        try:
            return getattr(QtCore.QEvent.Type, etype)
        except AttributeError:
            raise ValueError(f"Invalid QEvent type string: '{etype}'")

    def _default_event_name(self, event_type: int) -> str:
        """Return a default event name based on the event type."""
        try:  # Try to get name via QEvent.Type, fallback to int
            enum_member = QtCore.QEvent.Type(event_type)
            name = enum_member.name  # PySide6>=6.2
        except Exception:  # Fallback: manually map or just use the integer value
            name = f"Type{int(event_type)}"
        return (
            name[0].lower() + name[1:] + "Event" if name else f"type{event_type}Event"
        )

    def _format_event_name(self, event_type: int) -> str:
        return f"{self.event_name_prefix}{self._default_event_name(event_type)}"


class MouseTracking(QtCore.QObject, ptk.LoggingMixin):
    """MouseTracking is a QObject subclass that provides mouse enter and leave events for QWidget child widgets.
    It uses event filtering to track the mouse movement and send enter and leave events to the child widgets.

    Attributes:
        _prev_mouse_over (list): List of widgets that were previously under the mouse cursor.
        _mouse_over (list): List of widgets that are currently under the mouse cursor.
        _widgets (set): Set of child widgets of the parent.
        _filtered_widgets (set): Set of widgets that have been processed for special handling (widgets with a viewport).
        logger (Logger): Instance of a logger that logs mouse tracking events.

    Methods:
        eventFilter(self, widget, event): Filters events to track mouse move events and button press/release events.
        should_capture_mouse(self, widget): Checks if a widget should capture the mouse.
        track(self): Updates tracking data and sends enter, leave, and release events to widgets.

    Parameters:
        parent (QWidget): Parent widget for the MouseTracking object.
        track_on_drag_only (bool, optional): If True, tracks mouse movement only when dragging. Defaults to True.
        log_level (int, optional): Logging level. Defaults to logging.WARNING.

    Raises:
        TypeError: If parent is not a QWidget derived type.
    """

    def __init__(
        self,
        parent,
        track_on_drag_only: bool = True,
        log_level="WARNING",
        auto_update: bool = True,
    ):
        super().__init__(parent)

        if not isinstance(parent, QtWidgets.QWidget):
            raise TypeError("Parent must be a QWidget derived type")

        self.logger.setLevel(log_level)

        self.track_on_drag_only = track_on_drag_only
        self.auto_update = auto_update
        self._prev_mouse_over: set[QtWidgets.QWidget] = set()
        self._mouse_over: set[QtWidgets.QWidget] = set()
        self._filtered_widgets: "weakref.WeakSet[QtWidgets.QWidget]" = weakref.WeakSet()
        self._mouse_owner: QtWidgets.QWidget | None = None

        parent.installEventFilter(self)

    def should_capture_mouse(self, widget):
        """Checks if a widget should capture the mouse."""
        widget_conditions = [
            # (QtWidgets.QPushButton, lambda widget: not widget.isDown()),
            (QtWidgets.QComboBox, lambda widget: not widget.view().isVisible()),
            (QtWidgets.QSlider, lambda widget: not widget.isSliderDown()),
            (QtWidgets.QScrollBar, lambda widget: not widget.isSliderDown()),
        ]
        for widget_type, condition in widget_conditions:
            if isinstance(widget, widget_type) and condition(widget):
                self.logger.debug(
                    f"Not capturing mouse for {widget_type.__name__} under specified condition"
                )
                return False
        return True

    def _update_widgets_under_cursor(self, top_widget: QtWidgets.QWidget):
        """Updates the list of widgets currently under the cursor."""
        self.update_child_widgets()
        self._mouse_over = {top_widget} if top_widget in self._widgets else set()
        self.logger.debug(
            f"Widgets under cursor: {[f'{w.objectName()}, {type(w).__name__}' for w in self._mouse_over]}"
        )

    def update_child_widgets(self):
        """Updates the set of child widgets of the parent."""
        parent = self.parent()
        if hasattr(parent, "currentWidget") and callable(parent.currentWidget):
            current = parent.currentWidget()
            widgets = current.findChildren(QtWidgets.QWidget) if current else []
        else:
            widgets = parent.findChildren(QtWidgets.QWidget)
        self._widgets: set[QtWidgets.QWidget] = set(widgets)

    def track(self):
        """Efficiently updates tracking data and sends enter and leave events to widgets."""
        cursor_pos = QtGui.QCursor.pos()
        top_widget = QtWidgets.QApplication.widgetAt(cursor_pos)

        self._release_mouse_for_widgets(self._mouse_over)
        if self.auto_update:
            self.update_child_widgets()

        self._mouse_over = {top_widget} if top_widget in self._widgets else set()

        for widget in self._prev_mouse_over - self._mouse_over:
            if self.is_widget_valid(widget):
                self._send_leave_event(widget)

        for widget in self._mouse_over - self._prev_mouse_over:
            if self.is_widget_valid(widget):
                self._send_enter_event(widget)

        if self.is_widget_valid(top_widget):
            self._handle_mouse_grab(top_widget)

        self._prev_mouse_over = set(self._mouse_over)
        self._filter_viewport_widgets()

    @staticmethod
    def is_widget_valid(widget):
        """Return True if the Qt widget and its C++ object still exist."""
        if widget is None:
            return False
        try:  # This will throw if the C++ object is deleted
            widget.objectName()
        except RuntimeError:
            return False
        return True

    def _release_mouse_for_widgets(self, widgets):
        """Releases mouse for given widgets if still valid."""
        for widget in widgets:
            if self.is_widget_valid(widget):
                try:
                    widget.releaseMouse()
                except RuntimeError:
                    continue
                if widget is self._mouse_owner:
                    self._mouse_owner = None

    def _send_enter_event(self, widget):
        """Sends an enter event to a widget."""
        try:
            pos = QtGui.QCursor.pos()
            local_pos = widget.mapFromGlobal(pos)
            event = QtGui.QEnterEvent(
                QtCore.QPointF(local_pos),
                QtCore.QPointF(local_pos),
                QtCore.QPointF(pos),
            )
            QtWidgets.QApplication.sendEvent(widget, event)
        except RuntimeError:
            self.logger.debug("Widget deleted before enter event could be sent.")

    def _send_leave_event(self, widget):
        """Sends a leave event to a widget."""
        try:
            event = QtCore.QEvent(QtCore.QEvent.Type.Leave)
            QtWidgets.QApplication.sendEvent(widget, event)
        except RuntimeError:
            self.logger.debug("Widget deleted before leave event could be sent.")

    def _send_release_event(self, widget, button):
        """Sends a release event to a widget."""
        try:
            global_pos = QtGui.QCursor.pos()
            local_pos = widget.mapFromGlobal(global_pos)
            event = QtGui.QMouseEvent(
                QtCore.QEvent.Type.MouseButtonRelease,
                local_pos,
                global_pos,
                button,
                QtCore.Qt.MouseButtons(QtCore.Qt.NoButton),
                QtCore.Qt.KeyboardModifiers(QtCore.Qt.NoModifier),
            )
            QtWidgets.QApplication.postEvent(widget, event)
        except RuntimeError:
            self.logger.debug("Widget deleted before release event could be sent.")

    def _handle_mouse_grab(self, top_widget: QtWidgets.QWidget):
        """Handles mouse grabbing depending on the widget currently under the cursor."""
        try:
            if (
                top_widget
                and top_widget.isVisible()
                and self.should_capture_mouse(top_widget)
            ):
                self.logger.info(
                    f"Grabbing mouse for widget: {top_widget.objectName()}"
                )
                self._grab_widget(top_widget)
            elif self._mouse_owner and QtWidgets.QApplication.mouseButtons():
                # Keep the current owner if dragging
                pass
            else:
                self._release_mouse_owner()
        except RuntimeError:
            self.logger.debug("Could not grab mouse: widget may have been deleted.")

    def _grab_widget(self, widget: QtWidgets.QWidget):
        """Grab the mouse for a widget only when ownership changes."""

        if widget is self._mouse_owner or not self.is_widget_valid(widget):
            return

        self._release_mouse_owner()
        widget.grabMouse()
        self._mouse_owner = widget

    def _release_mouse_owner(self):
        """Release the currently grabbed widget, if any."""

        if self._mouse_owner and self.is_widget_valid(self._mouse_owner):
            try:
                self._mouse_owner.releaseMouse()
            except RuntimeError:
                pass
        self._mouse_owner = None

    def _filter_viewport_widgets(self):
        """Adds special handling for widgets with a viewport."""
        for widget in self._widgets:
            if hasattr(widget, "viewport") and widget not in self._filtered_widgets:
                self._filtered_widgets.add(widget)
                self._handle_viewport_widget(widget)

    def _handle_viewport_widget(self, widget):
        """Adds event filter to viewport instead of overwriting mouseMoveEvent."""
        if hasattr(widget, "viewport"):
            viewport = widget.viewport()
            if viewport:
                viewport.installEventFilter(self)
                self._filtered_widgets.add(viewport)

    def eventFilter(self, widget, event):
        """Filter mouse move and release events."""
        etype = event.type()

        if etype == QtCore.QEvent.Type.MouseMove:
            if self.track_on_drag_only and not QtWidgets.QApplication.mouseButtons():
                self._flush_hover_state()
                return False
            self.track()

        elif etype == QtCore.QEvent.Type.MouseButtonRelease:
            top_widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
            if (
                isinstance(top_widget, QtWidgets.QAbstractButton)
                and not top_widget.isDown()
            ):
                self._send_release_event(top_widget, event.button())

        elif etype in (
            QtCore.QEvent.Type.Hide,
            QtCore.QEvent.Type.FocusOut,
            QtCore.QEvent.Type.WindowDeactivate,
        ):
            self._release_mouse_owner()
            self._flush_hover_state()

        elif etype in (
            QtCore.QEvent.Type.WindowActivate,
            QtCore.QEvent.Type.FocusIn,
        ):
            # Reinitialize widget cache when window regains focus
            self._reinitialize_tracking()

        return super().eventFilter(widget, event)

    def _flush_hover_state(self):
        """Release grabbed widgets and emit leave events when tracking pauses."""

        if not (self._mouse_over or self._prev_mouse_over):
            return

        stale_widgets = self._mouse_over | self._prev_mouse_over
        self._release_mouse_for_widgets(stale_widgets)

        for widget in stale_widgets:
            if self.is_widget_valid(widget):
                self._send_leave_event(widget)

        self._mouse_over.clear()
        self._prev_mouse_over.clear()

    def _reinitialize_tracking(self):
        """Reinitialize tracking state when window regains focus.

        This ensures hover events work correctly after the user returns
        from working in another application or window.
        """
        # Refresh the widget cache to pick up any new/removed widgets
        self.update_child_widgets()

        # Clear stale state from before deactivation
        self._prev_mouse_over.clear()
        self._mouse_over.clear()

        # Re-filter viewport widgets in case any were added
        self._filter_viewport_widgets()

        self.logger.debug("Tracking reinitialized after window activation")


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    pass

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
