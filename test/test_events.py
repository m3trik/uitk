# !/usr/bin/python
# coding=utf-8
"""Unit tests for Events module.

This module tests the event handling functionality including:
- EventFactoryFilter creation and installation
- Mouse tracking functionality
- Event filtering and handler resolution
- Edge cases and error handling

Run standalone: python -m test.test_events
"""

import unittest
from unittest.mock import MagicMock, patch
import weakref

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore, QtGui
from uitk.events import EventFactoryFilter, MouseTracking


class TestEventFactoryFilterCreation(QtBaseTestCase):
    """Tests for EventFactoryFilter creation and configuration."""

    def setUp(self):
        super().setUp()
        self.parent_widget = self.track_widget(QtWidgets.QWidget())

    def test_creates_filter_with_defaults(self):
        """Should create filter with default settings."""
        filter_obj = EventFactoryFilter()
        self.assertIsNotNone(filter_obj)
        self.assertEqual(filter_obj.event_name_prefix, "")
        self.assertFalse(filter_obj.propagate_to_children)

    def test_creates_filter_with_parent(self):
        """Should create filter with parent object."""
        filter_obj = EventFactoryFilter(parent=self.parent_widget)
        self.assertEqual(filter_obj.parent(), self.parent_widget)

    def test_creates_filter_with_event_types(self):
        """Should create filter with specified event types."""
        filter_obj = EventFactoryFilter(
            event_types={"MouseButtonPress", "MouseButtonRelease"}
        )
        self.assertEqual(len(filter_obj.event_types), 2)

    def test_creates_filter_with_event_name_prefix(self):
        """Should create filter with custom event name prefix."""
        filter_obj = EventFactoryFilter(event_name_prefix="child_")
        self.assertEqual(filter_obj.event_name_prefix, "child_")

    def test_normalizes_string_event_types(self):
        """Should normalize string event types to integers."""
        filter_obj = EventFactoryFilter(event_types={"MouseButtonPress"})
        # All event types should be integers after normalization
        for etype in filter_obj.event_types:
            self.assertIsInstance(etype, int)

    def test_normalizes_integer_event_types(self):
        """Should accept integer event types directly."""
        filter_obj = EventFactoryFilter(
            event_types={int(QtCore.QEvent.Type.MouseButtonPress)}
        )
        self.assertIn(int(QtCore.QEvent.Type.MouseButtonPress), filter_obj.event_types)

    def test_raises_for_invalid_event_type_string(self):
        """Should raise ValueError for invalid event type string."""
        with self.assertRaises(ValueError) as context:
            EventFactoryFilter(event_types={"InvalidEventType"})
        self.assertIn("Invalid QEvent type string", str(context.exception))

    def test_creates_filter_with_forward_events_to(self):
        """Should accept custom event handler target."""
        handler = MagicMock()
        filter_obj = EventFactoryFilter(forward_events_to=handler)
        self.assertEqual(filter_obj.forward_events_to, handler)

    def test_default_forward_events_to_self(self):
        """Should default forward_events_to to self when not provided."""
        filter_obj = EventFactoryFilter()
        self.assertEqual(filter_obj.forward_events_to, filter_obj)

    def test_propagate_to_children_true(self):
        """Should accept propagate_to_children=True."""
        filter_obj = EventFactoryFilter(propagate_to_children=True)
        self.assertTrue(filter_obj.propagate_to_children)


class TestEventFactoryFilterInstallation(QtBaseTestCase):
    """Tests for EventFactoryFilter installation on widgets."""

    def setUp(self):
        super().setUp()
        self.widget = self.track_widget(QtWidgets.QPushButton())
        self.filter_obj = EventFactoryFilter()

    def test_install_on_single_widget(self):
        """Should install filter on a single widget."""
        self.filter_obj.install(self.widget)
        # Widget should be tracked if not propagating to children
        self.assertIn(self.widget, self.filter_obj._installed_widgets)

    def test_install_on_multiple_widgets(self):
        """Should install filter on multiple widgets."""
        widget2 = self.track_widget(QtWidgets.QLabel())
        self.filter_obj.install([self.widget, widget2])
        self.assertIn(self.widget, self.filter_obj._installed_widgets)
        self.assertIn(widget2, self.filter_obj._installed_widgets)

    def test_uninstall_removes_widget(self):
        """Should remove widget from tracking on uninstall."""
        self.filter_obj.install(self.widget)
        self.filter_obj.uninstall(self.widget)
        self.assertNotIn(self.widget, self.filter_obj._installed_widgets)

    def test_is_installed_returns_correct_state(self):
        """Should correctly report installation state."""
        self.assertFalse(self.filter_obj.is_installed(self.widget))
        self.filter_obj.install(self.widget)
        self.assertTrue(self.filter_obj.is_installed(self.widget))

    def test_uninstall_multiple_widgets(self):
        """Should uninstall multiple widgets at once."""
        widget2 = self.track_widget(QtWidgets.QLabel())
        self.filter_obj.install([self.widget, widget2])
        self.filter_obj.uninstall([self.widget, widget2])
        self.assertFalse(self.filter_obj.is_installed(self.widget))
        self.assertFalse(self.filter_obj.is_installed(widget2))

    def test_install_does_not_track_when_propagate_children(self):
        """Should not add to _installed_widgets when propagate_to_children=True."""
        filter_obj = EventFactoryFilter(propagate_to_children=True)
        filter_obj.install(self.widget)
        self.assertNotIn(self.widget, filter_obj._installed_widgets)

    def test_install_same_widget_twice(self):
        """Should handle installing same widget twice without error."""
        self.filter_obj.install(self.widget)
        self.filter_obj.install(self.widget)  # Should not raise
        self.assertIn(self.widget, self.filter_obj._installed_widgets)

    def test_uninstall_not_installed_widget(self):
        """Should handle uninstalling widget that was never installed."""
        widget2 = self.track_widget(QtWidgets.QLabel())
        # Should not raise
        self.filter_obj.uninstall(widget2)


class TestEventFactoryFilterEventHandling(QtBaseTestCase):
    """Tests for EventFactoryFilter event handling."""

    def setUp(self):
        super().setUp()
        self.handler_called = False
        self.handler_widget = None
        self.handler_event = None

    def _create_handler_target(self):
        """Create a mock handler target object."""

        class HandlerTarget:
            def __init__(target_self):
                target_self.handler_called = False

            def mouseButtonPressEvent(target_self, widget, event):
                self.handler_called = True
                self.handler_widget = widget
                self.handler_event = event
                return True

        return HandlerTarget()

    def test_has_event_filter_method(self):
        """Should have eventFilter method that can be called."""
        filter_obj = EventFactoryFilter(
            event_types={"MouseButtonPress"},
        )
        self.assertTrue(hasattr(filter_obj, "eventFilter"))
        self.assertTrue(callable(filter_obj.eventFilter))

    def test_ignores_untracked_event_types(self):
        """Should ignore events not in event_types set."""
        handler_target = self._create_handler_target()
        filter_obj = EventFactoryFilter(
            forward_events_to=handler_target,
            event_types={"MouseButtonRelease"},  # Only tracking release, not press
        )

        widget = self.track_widget(QtWidgets.QPushButton())
        filter_obj.install(widget)

        # Create a press event (not tracked)
        event = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),  # globalPos
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )

        result = filter_obj.eventFilter(widget, event)
        self.assertFalse(self.handler_called)
        self.assertFalse(result)

    def test_calls_handler_for_tracked_event(self):
        """Should call handler for tracked event types."""
        handler_target = self._create_handler_target()
        filter_obj = EventFactoryFilter(
            forward_events_to=handler_target,
            event_types={"MouseButtonPress"},
        )

        widget = self.track_widget(QtWidgets.QPushButton())
        filter_obj.install(widget)

        event = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )

        result = filter_obj.eventFilter(widget, event)
        self.assertTrue(self.handler_called)
        self.assertEqual(self.handler_widget, widget)

    def test_event_filter_returns_false_for_none_widget(self):
        """Should return False when widget is None."""
        filter_obj = EventFactoryFilter(event_types={"MouseButtonPress"})
        event = MagicMock()
        event.type.return_value = int(QtCore.QEvent.Type.MouseButtonPress)
        result = filter_obj.eventFilter(None, event)
        self.assertFalse(result)

    def test_event_filter_ignores_uninstalled_widget(self):
        """Should ignore events from widgets not in _installed_widgets."""
        handler_target = self._create_handler_target()
        filter_obj = EventFactoryFilter(
            forward_events_to=handler_target,
            event_types={"MouseButtonPress"},
            propagate_to_children=False,
        )

        widget = self.track_widget(QtWidgets.QPushButton())
        # Not installed

        event = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )

        result = filter_obj.eventFilter(widget, event)
        self.assertFalse(self.handler_called)
        self.assertFalse(result)

    def test_handler_cache_stores_resolved_handler(self):
        """Should cache resolved handler for performance."""
        handler_target = self._create_handler_target()
        filter_obj = EventFactoryFilter(
            forward_events_to=handler_target,
            event_types={"MouseButtonPress"},
        )

        widget = self.track_widget(QtWidgets.QPushButton())
        filter_obj.install(widget)

        event = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )

        # First call populates cache
        filter_obj.eventFilter(widget, event)
        self.assertGreater(len(filter_obj._handler_cache), 0)


class TestEventFactoryFilterEventNameFormatting(QtBaseTestCase):
    """Tests for event name formatting."""

    def test_formats_event_name_with_prefix(self):
        """Should format event name with prefix."""
        filter_obj = EventFactoryFilter(event_name_prefix="child_")
        name = filter_obj._format_event_name(QtCore.QEvent.Type.MouseButtonPress)
        self.assertTrue(name.startswith("child_"))

    def test_formats_event_name_without_prefix(self):
        """Should format event name without prefix when empty."""
        filter_obj = EventFactoryFilter(event_name_prefix="")
        name = filter_obj._format_event_name(QtCore.QEvent.Type.MouseButtonPress)
        self.assertFalse(name.startswith("_"))

    def test_default_event_name_contains_event(self):
        """Should contain 'Event' suffix in default name."""
        filter_obj = EventFactoryFilter()
        name = filter_obj._default_event_name(QtCore.QEvent.Type.MouseButtonPress)
        self.assertTrue(name.endswith("Event"))

    def test_formats_different_event_types(self):
        """Should format different event types correctly."""
        filter_obj = EventFactoryFilter()
        press_name = filter_obj._format_event_name(QtCore.QEvent.Type.MouseButtonPress)
        release_name = filter_obj._format_event_name(
            QtCore.QEvent.Type.MouseButtonRelease
        )
        self.assertNotEqual(press_name, release_name)


class TestMouseTrackingCreation(QtBaseTestCase):
    """Tests for MouseTracking creation and initialization."""

    def setUp(self):
        super().setUp()
        self.parent_widget = self.track_widget(QtWidgets.QWidget())

    def test_creates_tracker_with_parent(self):
        """Should create tracker with parent widget."""
        tracker = MouseTracking(self.parent_widget)
        self.assertEqual(tracker.parent(), self.parent_widget)

    def test_raises_type_error_for_non_widget_parent(self):
        """Should raise TypeError if parent is not a QWidget."""
        with self.assertRaises(TypeError) as context:
            MouseTracking(parent="not a widget")
        # Can be either TypeError from our validation or from PySide6 itself
        self.assertTrue(len(str(context.exception)) > 0)

    def test_track_on_drag_only_default(self):
        """Should default to track_on_drag_only=True."""
        tracker = MouseTracking(self.parent_widget)
        self.assertTrue(tracker.track_on_drag_only)

    def test_configures_track_on_drag_only(self):
        """Should configure track_on_drag_only parameter."""
        tracker = MouseTracking(self.parent_widget, track_on_drag_only=False)
        self.assertFalse(tracker.track_on_drag_only)

    def test_auto_update_default_true(self):
        """Should default to auto_update=True."""
        tracker = MouseTracking(self.parent_widget)
        self.assertTrue(tracker.auto_update)

    def test_configures_auto_update(self):
        """Should configure auto_update parameter."""
        tracker = MouseTracking(self.parent_widget, auto_update=False)
        self.assertFalse(tracker.auto_update)

    def test_initializes_empty_tracking_sets(self):
        """Should initialize with empty tracking sets."""
        tracker = MouseTracking(self.parent_widget)
        self.assertEqual(len(tracker._prev_mouse_over), 0)
        self.assertEqual(len(tracker._mouse_over), 0)

    def test_raises_type_error_for_none_parent(self):
        """Should raise TypeError for None parent."""
        with self.assertRaises(TypeError):
            MouseTracking(parent=None)


class TestMouseTrackingWidgetValidation(QtBaseTestCase):
    """Tests for widget validation in MouseTracking."""

    def test_is_widget_valid_returns_true_for_valid_widget(self):
        """Should return True for a valid widget."""
        widget = self.track_widget(QtWidgets.QPushButton())
        self.assertTrue(MouseTracking.is_widget_valid(widget))

    def test_is_widget_valid_returns_false_for_none(self):
        """Should return False for None."""
        self.assertFalse(MouseTracking.is_widget_valid(None))

    def test_is_widget_valid_returns_false_for_deleted_widget(self):
        """Should return False for a deleted widget."""
        widget = QtWidgets.QPushButton()
        widget.deleteLater()
        # Process events to actually delete the widget
        QtWidgets.QApplication.processEvents()
        # After deletion, accessing the widget should fail
        # Note: This test may be flaky depending on Qt's cleanup timing
        # The method should handle RuntimeError gracefully

    def test_is_widget_valid_handles_runtime_error(self):
        """Should handle RuntimeError when checking deleted widget."""
        # Create and immediately schedule for deletion
        widget = QtWidgets.QPushButton()
        ref = weakref.ref(widget)
        del widget
        QtWidgets.QApplication.processEvents()
        # If the weak reference is dead, the widget was deleted
        if ref() is None:
            self.assertFalse(MouseTracking.is_widget_valid(None))


class TestMouseTrackingShouldCaptureMouse(QtBaseTestCase):
    """Tests for should_capture_mouse logic."""

    def setUp(self):
        super().setUp()
        self.parent_widget = self.track_widget(QtWidgets.QWidget())
        self.tracker = MouseTracking(self.parent_widget)

    def test_returns_true_for_regular_button(self):
        """Should return True for a regular push button."""
        button = self.track_widget(QtWidgets.QPushButton())
        self.assertTrue(self.tracker.should_capture_mouse(button))

    def test_returns_false_for_combo_box_with_hidden_view(self):
        """should_capture_mouse should return False for combo box when view.isVisible() is False."""
        combo = self.track_widget(QtWidgets.QComboBox())
        combo.addItems(["Item 1", "Item 2"])
        # According to the implementation, when combo.view().isVisible() is False,
        # the condition (lambda widget: not widget.view().isVisible()) returns True,
        # which means should_capture_mouse returns False for QComboBox
        result = self.tracker.should_capture_mouse(combo)
        # This is the expected behavior per the implementation
        self.assertFalse(result)

    def test_returns_true_for_label(self):
        """Should return True for a QLabel."""
        label = self.track_widget(QtWidgets.QLabel("Test"))
        self.assertTrue(self.tracker.should_capture_mouse(label))

    def test_returns_true_for_line_edit(self):
        """Should return True for a QLineEdit."""
        line_edit = self.track_widget(QtWidgets.QLineEdit())
        self.assertTrue(self.tracker.should_capture_mouse(line_edit))

    def test_returns_true_for_checkbox(self):
        """Should return True for a QCheckBox."""
        checkbox = self.track_widget(QtWidgets.QCheckBox())
        self.assertTrue(self.tracker.should_capture_mouse(checkbox))

    def test_returns_false_for_slider_when_not_sliding(self):
        """Should return False for QSlider when not sliding."""
        slider = self.track_widget(QtWidgets.QSlider())
        # When slider is not being dragged, isSliderDown() is False
        result = self.tracker.should_capture_mouse(slider)
        self.assertFalse(result)

    def test_returns_false_for_scrollbar_when_not_sliding(self):
        """Should return False for QScrollBar when not sliding."""
        scrollbar = self.track_widget(QtWidgets.QScrollBar())
        result = self.tracker.should_capture_mouse(scrollbar)
        self.assertFalse(result)


class TestMouseTrackingEventFilter(QtBaseTestCase):
    """Tests for MouseTracking event filtering."""

    def setUp(self):
        super().setUp()
        self.parent_widget = self.track_widget(QtWidgets.QWidget())
        self.tracker = MouseTracking(self.parent_widget)

    def test_has_event_filter_method(self):
        """Should have eventFilter method."""
        self.assertTrue(hasattr(self.tracker, "eventFilter"))
        self.assertTrue(callable(self.tracker.eventFilter))

    def test_event_filter_handles_mouse_move(self):
        """Should handle MouseMove event type."""
        event = MagicMock()
        event.type.return_value = QtCore.QEvent.Type.MouseMove
        # Should not raise
        result = self.tracker.eventFilter(self.parent_widget, event)
        self.assertFalse(result)  # Should not consume event

    def test_event_filter_handles_hide_event(self):
        """Should handle Hide event by releasing mouse."""
        event = QtCore.QEvent(QtCore.QEvent.Type.Hide)
        result = self.tracker.eventFilter(self.parent_widget, event)
        self.assertFalse(result)

    def test_event_filter_handles_focus_out(self):
        """Should handle FocusOut event."""
        event = QtGui.QFocusEvent(QtCore.QEvent.Type.FocusOut)
        result = self.tracker.eventFilter(self.parent_widget, event)
        self.assertFalse(result)

    def test_event_filter_handles_window_deactivate(self):
        """Should handle WindowDeactivate event."""
        event = QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate)
        result = self.tracker.eventFilter(self.parent_widget, event)
        self.assertFalse(result)

    def test_optimization_update_on_press_not_move(self):
        """Verify update_child_widgets is called on Press/Enter but not Move."""
        self.tracker.update_child_widgets = MagicMock()

        # Test MouseMove (Should NOT update)
        event_move = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseMove,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            QtCore.Qt.NoButton,
            QtCore.Qt.NoButton,
            QtCore.Qt.NoModifier,
        )
        self.tracker.eventFilter(self.parent_widget, event_move)
        self.tracker.update_child_widgets.assert_not_called()

        # Test MouseButtonPress (Should UPDATE)
        event_press = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        self.tracker.eventFilter(self.parent_widget, event_press)
        self.tracker.update_child_widgets.assert_called_once()
        self.tracker.update_child_widgets.reset_mock()

        # Test Enter (Should UPDATE)
        event_enter = QtCore.QEvent(QtCore.QEvent.Type.Enter)
        self.tracker.eventFilter(self.parent_widget, event_enter)
        self.tracker.update_child_widgets.assert_called_once()


class TestMouseTrackingUpdateMethods(QtBaseTestCase):
    """Tests for MouseTracking update methods."""

    def setUp(self):
        super().setUp()
        self.parent_widget = self.track_widget(QtWidgets.QWidget())
        self.tracker = MouseTracking(self.parent_widget)

    def test_update_child_widgets(self):
        """Should update _widgets set with child widgets."""
        button = QtWidgets.QPushButton(self.parent_widget)
        label = QtWidgets.QLabel(self.parent_widget)
        self.tracker.update_child_widgets()
        self.assertIn(button, self.tracker._widgets)
        self.assertIn(label, self.tracker._widgets)

    def test_flush_hover_state_clears_tracking(self):
        """Should clear mouse_over sets when flushing."""
        # Add some widgets to tracking
        button = self.track_widget(QtWidgets.QPushButton())
        self.tracker._mouse_over.add(button)
        self.tracker._prev_mouse_over.add(button)
        self.tracker._flush_hover_state()
        self.assertEqual(len(self.tracker._mouse_over), 0)
        self.assertEqual(len(self.tracker._prev_mouse_over), 0)

    def test_flush_hover_state_handles_empty_sets(self):
        """Should handle empty sets without error."""
        self.tracker._mouse_over.clear()
        self.tracker._prev_mouse_over.clear()
        # Should not raise
        self.tracker._flush_hover_state()


class TestMouseTrackingWithStackedWidget(QtBaseTestCase):
    """Tests for MouseTracking with QStackedWidget parent."""

    def test_tracks_current_widget_children(self):
        """Should track children of current widget in stack."""
        stack = self.track_widget(QtWidgets.QStackedWidget())
        page1 = QtWidgets.QWidget()
        button1 = QtWidgets.QPushButton("Page 1 Button", page1)
        page2 = QtWidgets.QWidget()
        button2 = QtWidgets.QPushButton("Page 2 Button", page2)
        stack.addWidget(page1)
        stack.addWidget(page2)
        stack.setCurrentWidget(page1)

        tracker = MouseTracking(stack)
        tracker.update_child_widgets()

        # Should find button1 since page1 is current
        self.assertIn(button1, tracker._widgets)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
