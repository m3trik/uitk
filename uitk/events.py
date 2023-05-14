# !/usr/bin/python
# coding=utf-8
import os, sys
import re
from functools import partial
from PySide2 import QtCore, QtGui, QtWidgets


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


class MouseTracking(QtCore.QObject):
    """MouseTracking is a QObject subclass that provides mouse enter and leave events
    for QWidget child widgets. It uses event filtering to track the mouse movement
    and send enter and leave events to the child widgets.

    The class also handles special cases for widgets with a viewport or those requiring
    specific behavior by processing them in the __handle_viewport_widget method.
    This method can be customized to implement the desired behavior for such widgets.

    Usage:
        mouse_tracking = MouseTracking(parent_widget)
        where parent_widget is the widget whose child widgets you want to track.

    Attributes:
        _prev_mouse_over (list): Previous list of widgets under the mouse cursor.
        _mouse_over (list): Current list of widgets under the mouse cursor.
        _filtered_widgets (set): Set of widgets that have been processed for special handling (eg. widgets with a viewport).
    """

    def __init__(self, parent):
        super().__init__(parent)

        if not isinstance(parent, QtWidgets.QWidget):
            raise TypeError("Parent must be a QWidget derived type")

        self._prev_mouse_over = []
        self._mouse_over = []
        parent.installEventFilter(self)
        self._filtered_widgets = set()

    def track(self, widgets):
        self.__update_widgets_under_cursor(widgets)

        self.__send_leave_events()
        self.__send_enter_events()

        top_widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
        if top_widget:
            top_widget.grabMouse()
        else:
            QtWidgets.QApplication.activeWindow().grabMouse()

        self._prev_mouse_over = self._mouse_over.copy()

        for widget in widgets:
            if hasattr(widget, "viewport") and widget not in self._filtered_widgets:
                self._filtered_widgets.add(widget)
                self.__handle_viewport_widget(widget)

    def __handle_viewport_widget(self, widget):
        """Implement any special handling for widgets with viewports here
        For example, you can make the widget ignore mouse move events like this:
        """
        original_mouse_move_event = widget.mouseMoveEvent

        def new_mouse_move_event(event):
            original_mouse_move_event(event)
            event.ignore()

        widget.mouseMoveEvent = partial(new_mouse_move_event)

    def __update_widgets_under_cursor(self, widgets):
        top_widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
        self._mouse_over = []

        if top_widget and top_widget in widgets:
            self._mouse_over.append(top_widget)

    def __send_leave_events(self):
        for w in self._prev_mouse_over:
            if w not in self._mouse_over:
                w.releaseMouse()
                QtGui.QGuiApplication.sendEvent(w, QtCore.QEvent(QtCore.QEvent.Leave))

    def __send_enter_events(self):
        for w in self._mouse_over:
            if w not in self._prev_mouse_over:
                QtGui.QGuiApplication.sendEvent(w, QtCore.QEvent(QtCore.QEvent.Enter))

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.MouseMove:
            try:
                parent = self.parent()

                if isinstance(parent, QtWidgets.QStackedWidget):
                    current_widget = parent.currentWidget()
                    widgets = current_widget.findChildren(QtWidgets.QWidget)
                else:
                    widgets = parent.findChildren(QtWidgets.QWidget)

                self.track(widgets)
            except AttributeError:
                pass
            except TypeError:
                pass

        return super().eventFilter(watched, event)


# --------------------------------------------------------------------------------------------


# module name
print(__name__)
# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------


# deprecated: ------------------------------


# class MouseTracking(QtCore.QObject):
#   '''
#   '''
#   app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv) #return the existing QApplication object, or create a new one if none exists.

#   _prev_mouse_over=[] #list of widgets currently under the mouse cursor. (Limited to those widgets set as mouse tracked)

#   def mouseOverFilter(self, widgets):
#       '''Get the widget(s) currently under the mouse cursor, and manage mouse grab and event handling for those widgets.
#       Primarily used to trigger widget events while moving the cursor in the mouse button down state.

#       Parameters:
#           widgets (list): The widgets to filter for those currently under the mouse cursor.

#       Returns:
#           (list) widgets currently under mouse.
#       '''
#       mouseOver=[]
#       for w in widgets: #get all widgets currently under mouse cursor and send enter|leave events accordingly.
#           try:
#               if w.rect().contains(w.mapFromGlobal(QtGui.QCursor.pos())):
#                   mouseOver.append(w)

#           except AttributeError as error:
#               pass

#       return mouseOver


#   def track(self, widgets):
#       '''Get the widget(s) currently under the mouse cursor, and manage mouse grab and event handling for those widgets.
#       Primarily used to trigger widget events while moving the cursor in the mouse button down state.

#       Parameters:
#           widgets (list): The widgets to track.
#       '''
#       mouseOver = self.mouseOverFilter(widgets)

#       #send leave events for widgets no longer in mouseOver.
#       for w in self._prev_mouse_over:
#           if not w in mouseOver:
#               w.releaseMouse() # release mouse grab here
#               self.app.sendEvent(w, QtCore.QEvent(QtCore.QEvent.Leave))
#               # print ('releaseMouse:', w) #debug

#       #send enter events for any new widgets in mouseOver.
#       for w in mouseOver:
#           if not w in self._prev_mouse_over:
#               self.app.sendEvent(w, QtCore.QEvent(QtCore.QEvent.Enter))

#       try:
#           topWidget = self.app.widgetAt(QtGui.QCursor.pos())
#           topWidget.releaseMouse()  # release the mouse before grabbing it
#           topWidget.grabMouse() #set widget to receive mouse events.
#           # print ('grabMouse:', topWidget) #debug
#           # topWidget.setFocus() #set widget to receive keyboard events.
#           # print ('focusWidget:', self.app.focusWidget())

#       except AttributeError as error:
#           self.app.activeWindow().grabMouse()

#       self._prev_mouse_over = mouseOver


# w = self.app.widgetAt(QtGui.QCursor.pos())

#       if not w==self._prev_mouse_over:
#           try:
#               self._prev_mouse_over.releaseMouse()
#               self.app.sendEvent(self._prev_mouse_over, self.leaveEvent_)
#           except (TypeError, AttributeError) as error:
#               pass

#           w.grabMouse() #set widget to receive mouse events.
#           print ('grab:', w.objectName())
#           self.app.sendEvent(w, self.enterEvent_)
#           self._prev_mouse_over = w
