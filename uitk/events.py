# !/usr/bin/python
# coding=utf-8
import re
from qtpy import QtCore, QtGui, QtWidgets
import pythontk as ptk


class EventFactoryFilter(QtCore.QObject):
    """Event filter for dynamic UI objects.
    Forwards events to event handlers dynamically based on the event type.

    Parameters:
        parent (QWidget, optional): The parent widget for the event filter. Defaults to None.
    """

    def __init__(self, parent=None, forward_events_to=None, event_name_prefix=""):
        super().__init__(parent)

        self.forward_events_to = forward_events_to or self
        self.event_name_prefix = event_name_prefix

    @staticmethod
    def format_event_name(event_type, prefix=""):
        """Get a formatted event method name string from a given event type using a regular expression.

        Parameters:
            event_type (QEvent.Type): The event type whose method name needs to be generated.
            prefix (str, optional): A prefix for the event method names. Defaults to an empty string.

        Returns:
            str: The formatted event method name.

        Examples:
            format_event_name(QtCore.QEvent.Type.Enter) returns 'enterEvent'
            format_event_name(QtCore.QEvent.Type.MouseButtonPress) returns 'mousePressEvent'
            format_event_name(QtCore.QEvent.Type.Enter, prefix='ef_') returns 'ef_enterEvent'
            format_event_name(QtCore.QEvent.Type.MouseButtonPress, prefix='ef_') returns 'ef_mousePressEvent'
        """
        event_name = re.sub(
            r"^.*\.([A-Z])([^B]*)(?:Button)?(.*)$",
            lambda m: prefix + m.group(1).lower() + m.group(2) + m.group(3) + "Event",
            str(event_type),
        )
        return event_name

    def eventFilter(self, widget, event):
        """Forward widget events to event handlers.
        For any event type, the eventFilter will try to connect to a corresponding
        method derived from the event type string.

        Parameters:
            widget (QWidget): The widget that the event filter is applied to.
            event (QEvent): The event that needs to be processed.

        Returns:
            bool: True if the event was handled, False otherwise.
        """
        try:
            event_handler = getattr(
                self.forward_events_to,
                self.format_event_name(event.type(), self.event_name_prefix),
            )
            event_handled = event_handler(widget, event)
            if event_handled:
                return True
        except AttributeError:
            pass

        return False


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
        log_level (int, optional): Logging level. Defaults to logging.WARNING.

    Raises:
        TypeError: If parent is not a QWidget derived type.
    """

    def __init__(self, parent, log_level="WARNING"):
        super().__init__(parent)

        if not isinstance(parent, QtWidgets.QWidget):
            raise TypeError("Parent must be a QWidget derived type")

        self.logger.setLevel(log_level)

        self._prev_mouse_over: set[QtWidgets.QWidget] = set()
        self._mouse_over: set[QtWidgets.QWidget] = set()
        self._filtered_widgets: set[QtWidgets.QWidget] = set()

        parent.installEventFilter(self)

    def should_capture_mouse(self, widget):
        """Checks if a widget should capture the mouse."""
        widget_conditions = [
            (QtWidgets.QPushButton, lambda widget: not widget.isDown()),
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

        self.logger.info(f"Previous widgets under cursor: {self._prev_mouse_over}")
        self._release_mouse_for_widgets(self._mouse_over)

        self._update_widgets_under_cursor(top_widget)
        self.logger.info(f"Current widgets under cursor: {self._mouse_over}")

        for widget in self._prev_mouse_over - self._mouse_over:
            if not isinstance(widget, QtWidgets.QWidget) or not widget.parent():
                continue
            self._send_leave_event(widget)

        for widget in self._mouse_over - self._prev_mouse_over:
            if not isinstance(widget, QtWidgets.QWidget) or not widget.parent():
                continue
            self._send_enter_event(widget)

        self._handle_mouse_grab(top_widget)
        self._prev_mouse_over = set(self._mouse_over)
        self._filter_viewport_widgets()

    def _release_mouse_for_widgets(self, widgets):
        """Releases mouse for given widgets."""
        for widget in widgets:
            widget.releaseMouse()

    def _send_leave_event(self, widget):
        """Sends a leave event to a widget."""
        try:
            self.logger.info(
                f"Sending Leave event to: {widget}, Name: {widget.objectName()}, Parent: {widget.parent().objectName()}"
            )
            QtGui.QGuiApplication.sendEvent(widget, QtCore.QEvent(QtCore.QEvent.Leave))
        except RuntimeError:
            self.logger.debug("Widget deleted before leave event could be sent.")

    def _send_enter_event(self, widget):
        """Sends an enter event to a widget."""
        try:
            self.logger.info(
                f"Sending Enter event to: {widget}, Name: {widget.objectName()}, Parent: {widget.parent().objectName()}"
            )
            QtGui.QGuiApplication.sendEvent(widget, QtCore.QEvent(QtCore.QEvent.Enter))
        except RuntimeError:
            self.logger.debug("Widget deleted before enter event could be sent.")

    def _send_release_event(self, widget, button):
        """Sends a release event to a widget."""
        self.logger.info(
            f"Sending Release event to: {widget}, Name: {widget.objectName()}, Parent: {widget.parent().objectName()}"
        )
        release_event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtGui.QCursor.pos(),
            button,
            button,
            QtCore.Qt.NoModifier,
        )
        QtGui.QGuiApplication.postEvent(widget, release_event)

    def _handle_mouse_grab(self, top_widget: QtWidgets.QWidget):
        """Handles mouse grabbing depending on the widget currently under the cursor."""
        try:
            if top_widget and self.should_capture_mouse(top_widget):
                self.logger.info(
                    f"Grabbing mouse for widget: {top_widget.objectName()}"
                )
                top_widget.grabMouse()
            else:
                active_window = QtWidgets.QApplication.activeWindow()
                if active_window:
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
        """Ignores mouse move events for widgets with a viewport."""
        original_mouse_move_event = widget.mouseMoveEvent
        widget.mouseMoveEvent = lambda event: (
            original_mouse_move_event(event),
            event.ignore(),
        )

    def eventFilter(self, widget, event):
        """Calls `track` on each mouse move event and also tracks button press/release for QAbstractButton."""
        etype = event.type()

        if etype == QtCore.QEvent.MouseMove:
            if self.logger.isEnabledFor(self.logging.DEBUG):
                self.logger.debug(
                    f"MouseMove event filter triggered by: {widget} with event: {etype}"
                )
            self.track()

        elif etype == QtCore.QEvent.MouseButtonRelease:
            top_widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
            if (
                isinstance(top_widget, QtWidgets.QAbstractButton)
                and not top_widget.isDown()
            ):
                self.logger.info(
                    f"Mouse button release event detected on: {top_widget}"
                )
                self._send_release_event(top_widget, event.button())

        return super().eventFilter(widget, event)


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    pass

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
