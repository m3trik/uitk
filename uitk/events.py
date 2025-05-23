# !/usr/bin/python
# coding=utf-8
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
        self._handler_cache: dict[int, callable | None] = {}
        self._installed_widgets: "weakref.WeakSet[QtCore.QObject]" = weakref.WeakSet()

    def install(self, widgets: QtCore.QObject | Iterable[QtCore.QObject]):
        """Install this event filter on one or more widgets."""
        import weakref

        for w in ptk.make_iterable(widgets):
            w.installEventFilter(self)
            if not self.propagate_to_children:
                self._installed_widgets.add(w)
            wr = weakref.ref(w)

            def _on_destroyed(obj, wr=wr):
                widget = wr()
                if widget:
                    self.uninstall(widget)

            w.destroyed.connect(_on_destroyed)

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

        handler = self._handler_cache.get(etype)
        if handler is None:
            method_name = self._format_event_name(etype)
            handler = getattr(self.forward_events_to, method_name, None)
            self._handler_cache[etype] = handler

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

    def __init__(self, parent, track_on_drag_only: bool = True, log_level="WARNING"):
        super().__init__(parent)

        if not isinstance(parent, QtWidgets.QWidget):
            raise TypeError("Parent must be a QWidget derived type")

        self.logger.setLevel(log_level)

        self.track_on_drag_only = track_on_drag_only
        self._prev_mouse_over: set[QtWidgets.QWidget] = set()
        self._mouse_over: set[QtWidgets.QWidget] = set()
        self._filtered_widgets: set[QtWidgets.QWidget] = set()

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
        self._get_child_widgets()
        self._mouse_over = {top_widget} if top_widget in self._widgets else set()
        self.logger.debug(
            f"Widgets under cursor: {[f'{w.objectName()}, {type(w).__name__}' for w in self._mouse_over]}"
        )

    def _get_child_widgets(self):
        """Updates the set of child widgets of the parent."""
        parent = self.parent()
        widgets = (
            parent.currentWidget().findChildren(QtWidgets.QWidget)
            if isinstance(parent, QtWidgets.QStackedWidget)
            else parent.findChildren(QtWidgets.QWidget)
        )
        self._widgets: set[QtWidgets.QWidget] = set(widgets)

    def track(self):
        """Efficiently updates tracking data and sends enter and leave events to widgets."""
        cursor_pos = QtGui.QCursor.pos()
        top_widget = QtWidgets.QApplication.widgetAt(cursor_pos)

        self._release_mouse_for_widgets(self._mouse_over)
        self._get_child_widgets()

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
                top_widget.grabMouse()
            else:
                active_window = QtWidgets.QApplication.activeWindow()
                if active_window and active_window.isVisible():
                    self.logger.info(
                        f"Grabbing mouse for active window: {active_window.objectName()}"
                    )
                    active_window.grabMouse()
        except RuntimeError:
            self.logger.debug("Could not grab mouse: widget may have been deleted.")

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
                return False
            self.track()

        elif etype == QtCore.QEvent.Type.MouseButtonRelease:
            top_widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
            if (
                isinstance(top_widget, QtWidgets.QAbstractButton)
                and not top_widget.isDown()
            ):
                self._send_release_event(top_widget, event.button())

        return super().eventFilter(widget, event)


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    pass

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
