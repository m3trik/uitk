# !/usr/bin/python
# coding=utf-8
import os, sys
from functools import partial

from PySide2 import QtCore, QtGui, QtWidgets


class EventFactoryFilter(QtCore.QObject):
	"""Event filter for dynamic UI objects.
	Forwards events to event handlers dynamically based on the event type.

	Parameters:
		parent (QWidget, optional): The parent widget for the event filter. Defaults to None.
		eventNamePrefix (str, optional): A prefix for the event method names. Defaults to an empty string.
		forwardEventsTo (QWidget, optional): The widget to forward events to. Defaults to None.
		events (tuple, optional): The types of events to be handled. Defaults to a predefined set of event names.
	"""
	events=( #the types of events to be handled here.
		'showEvent',
		'hideEvent',
		'enterEvent',
		'leaveEvent',
		'mousePressEvent',
		'mouseMoveEvent',
		'mouseReleaseEvent',
		'keyPressEvent',
		'keyReleaseEvent',
	)

	def __init__(self, parent=None, eventNamePrefix='', forwardEventsTo=None, events=events):
		super().__init__(parent)

		self.eventNamePrefix = eventNamePrefix
		self.forwardEventsTo = forwardEventsTo


	def createEventName(self, event):
		"""Get an event method name string from a given event.
		Example: 'enterEvent' from QtCore.QEvent.Type.Enter
		Example: 'mousePressEvent' from QtCore.QEvent.Type.MouseButtonPress

		Parameters:
			event (QEvent): The event whose method name needs to be generated.
		
		Returns:
			str: The formatted method name.
		"""
		s1 = str(event.type()).split('.')[-1] #get the event name ie. 'Enter' from QtCore.QEvent.Type.Enter
		s2 = s1[0].lower() + s1[1:] #lowercase the first letter.
		s3 = s2.replace('Button', '') #remove 'Button' if it exists.
		return s3 + 'Event' #add trailing 'Event'


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
		if self.forwardEventsTo is None:
			self.forwardEventsTo = self

		eventName = self.createEventName(event) #get 'mousePressEvent' from <QEvent>

		if eventName in self.events: #handle only events listed in 'eventTypes'
			try:
				getattr(self.forwardEventsTo, self.eventNamePrefix+eventName)(widget, event) #handle the event (in subclass. #ie. self.enterEvent(<widget>, <event>)
				return True

			except AttributeError as error:
				pass #print (__file__, error)

		return False #event not handled



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
		_prevMouseOver (list): Previous list of widgets under the mouse cursor.
		_mouseOver (list): Current list of widgets under the mouse cursor.
		_filtered_widgets (set): Set of widgets that have been processed for special handling (e.g., widgets with a viewport).
	"""
	def __init__(self, parent):
		super().__init__(parent)
		self._prevMouseOver = []
		self._mouseOver = []
		parent.installEventFilter(self)
		self._filtered_widgets = set()


	def eventFilter(self, watched, event):
		if event.type() == QtCore.QEvent.MouseMove:
			if isinstance(self.parent(), QtWidgets.QStackedWidget):
				current_widget = self.parent().currentWidget()
				self.track(current_widget.findChildren(QtWidgets.QWidget))
			else:
				self.track(self.parent().findChildren(QtWidgets.QWidget))

		return super().eventFilter(watched, event)


	def track(self, widgets):
		self.__update_widgets_under_cursor(widgets)

		self.__send_leave_events()
		self.__send_enter_events()

		top_widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
		if top_widget:
			top_widget.grabMouse()
		else:
			QtWidgets.QApplication.activeWindow().grabMouse()

		self._prevMouseOver = self._mouseOver.copy()

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
		self._mouseOver = []
		
		if top_widget and top_widget in widgets:
			self._mouseOver.append(top_widget)


	def __send_leave_events(self):
		for w in self._prevMouseOver:
			if w not in self._mouseOver:
				w.releaseMouse()
				QtGui.QGuiApplication.sendEvent(w, QtCore.QEvent(QtCore.QEvent.Leave))


	def __send_enter_events(self):
		for w in self._mouseOver:
			if w not in self._prevMouseOver:
				QtGui.QGuiApplication.sendEvent(w, QtCore.QEvent(QtCore.QEvent.Enter))







# --------------------------------------------------------------------------------------------







#module name
print (__name__)
# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------


#deprecated: ------------------------------



# class MouseTracking(QtCore.QObject):
# 	'''
# 	'''
# 	app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv) #return the existing QApplication object, or create a new one if none exists.

# 	_prevMouseOver=[] #list of widgets currently under the mouse cursor. (Limited to those widgets set as mouse tracked)

# 	def mouseOverFilter(self, widgets):
# 		'''Get the widget(s) currently under the mouse cursor, and manage mouse grab and event handling for those widgets.
# 		Primarily used to trigger widget events while moving the cursor in the mouse button down state.

# 		Parameters:
# 			widgets (list): The widgets to filter for those currently under the mouse cursor.

# 		Return:
# 			(list) widgets currently under mouse.
# 		'''
# 		mouseOver=[]
# 		for w in widgets: #get all widgets currently under mouse cursor and send enter|leave events accordingly.
# 			try:
# 				if w.rect().contains(w.mapFromGlobal(QtGui.QCursor.pos())):
# 					mouseOver.append(w)

# 			except AttributeError as error:
# 				pass

# 		return mouseOver


# 	def track(self, widgets):
# 		'''Get the widget(s) currently under the mouse cursor, and manage mouse grab and event handling for those widgets.
# 		Primarily used to trigger widget events while moving the cursor in the mouse button down state.

# 		Parameters:
# 			widgets (list): The widgets to track.
# 		'''
# 		mouseOver = self.mouseOverFilter(widgets)

# 		#send leave events for widgets no longer in mouseOver.
# 		for w in self._prevMouseOver:
# 			if not w in mouseOver:
# 				w.releaseMouse() # release mouse grab here
# 				self.app.sendEvent(w, QtCore.QEvent(QtCore.QEvent.Leave))
# 				# print ('releaseMouse:', w) #debug

# 		#send enter events for any new widgets in mouseOver.
# 		for w in mouseOver:
# 			if not w in self._prevMouseOver:
# 				self.app.sendEvent(w, QtCore.QEvent(QtCore.QEvent.Enter))

# 		try:
# 			topWidget = self.app.widgetAt(QtGui.QCursor.pos())
# 			topWidget.releaseMouse()  # release the mouse before grabbing it
# 			topWidget.grabMouse() #set widget to receive mouse events.
# 			# print ('grabMouse:', topWidget) #debug
# 			# topWidget.setFocus() #set widget to receive keyboard events.
# 			# print ('focusWidget:', self.app.focusWidget())

# 		except AttributeError as error:
# 			self.app.activeWindow().grabMouse()

# 		self._prevMouseOver = mouseOver


# w = self.app.widgetAt(QtGui.QCursor.pos())

# 		if not w==self._prevMouseOver:
# 			try:
# 				self._prevMouseOver.releaseMouse()
# 				self.app.sendEvent(self._prevMouseOver, self.leaveEvent_)
# 			except (TypeError, AttributeError) as error:
# 				pass

# 			w.grabMouse() #set widget to receive mouse events.
# 			print ('grab:', w.objectName())
# 			self.app.sendEvent(w, self.enterEvent_)
# 			self._prevMouseOver = w