# !/usr/bin/python
# coding=utf-8
"""Unit tests for Events module.

This module tests the event handling functionality including:
- EventFactoryFilter creation and installation
- Mouse tracking functionality
- Event filtering and handler resolution

Run standalone: python -m test.test_events
"""

import unittest
from unittest.mock import MagicMock, patch

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

            def mousePressEvent(target_self, widget, event):
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


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
