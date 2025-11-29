# !/usr/bin/python
# coding=utf-8
"""Unit tests for MainWindow widget.

This module tests the MainWindow widget functionality including:
- MainWindow creation and initialization
- Widget registration and management
- Signal handling (on_show, on_hide, on_close, on_focus, on_child_changed)
- Window geometry save/restore
- State management integration
- Tag editing
- Style sheet locking
- Event filter behavior

Run standalone: python -m test.test_mainwindow
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore


class MockSwitchboard:
    """Mock switchboard for testing MainWindow without full Switchboard dependency."""

    def __init__(self):
        self.current_ui = None
        self.app = QtWidgets.QApplication.instance()
        # default_signals must be a dict, not a method
        self.default_signals = {
            "QPushButton": "clicked",
            "QCheckBox": "stateChanged",
            "QLineEdit": "textChanged",
        }

    def convert_to_legal_name(self, name):
        """Convert name to a legal Python identifier."""
        return name.replace(" ", "_").replace("-", "_")

    def get_base_name(self, name):
        """Get base name without tags."""
        if "#" in name:
            return name.split("#")[0]
        return name

    def has_tags(self, widget, tags=None):
        """Check if widget has specified tags."""
        widget_tags = getattr(widget, "tags", set())
        if tags is None:
            return bool(widget_tags)
        if isinstance(tags, str):
            tags = {tags}
        return bool(widget_tags & set(tags))

    def edit_tags(self, target, add=None, remove=None, clear=False, reset=False):
        """Edit tags on a widget."""
        if isinstance(target, str):
            return target
        return None

    def _get_widget_from_ui(self, ui, attr_name):
        """Get widget by object name."""
        return ui.findChild(QtWidgets.QWidget, attr_name)

    def get_slots_instance(self, widget):
        """Get slots instance for widget."""
        return MagicMock()

    def get_ui_relatives(self, ui, upstream=False, downstream=False):
        """Get related UIs."""
        return []

    def get_widget(self, name, ui):
        """Get widget from UI by name."""
        return None

    def center_widget(self, widget, pos=None):
        """Center widget at position."""
        pass

    def init_slot(self, widget):
        """Initialize slot for widget."""
        pass

    def call_slot(self, widget, *args, **kwargs):
        """Call slot for widget."""
        pass

    def connect_slot(self, widget, slot=None):
        """Connect slot to widget."""
        pass


class TestMainWindowCreation(QtBaseTestCase):
    """Tests for MainWindow creation and initialization."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_creates_mainwindow_with_name(self):
        """Should create MainWindow with specified name."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertEqual(window.objectName(), "TestWindow")

    def test_creates_mainwindow_with_parent(self):
        """Should create MainWindow with parent widget."""
        from uitk.widgets.mainWindow import MainWindow

        parent = self.track_widget(QtWidgets.QWidget())
        window = self.track_widget(MainWindow("TestWindow", self.sb, parent=parent))
        self.assertEqual(window.parent(), parent)

    def test_creates_mainwindow_with_central_widget(self):
        """Should create MainWindow with central widget."""
        from uitk.widgets.mainWindow import MainWindow

        central = QtWidgets.QWidget()
        window = self.track_widget(
            MainWindow("TestWindow", self.sb, central_widget=central)
        )
        self.assertEqual(window.centralWidget(), central)

    def test_creates_mainwindow_with_tags(self):
        """Should create MainWindow with specified tags."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(
            MainWindow("TestWindow", self.sb, tags={"tag1", "tag2"})
        )
        self.assertIn("tag1", window.tags)
        self.assertIn("tag2", window.tags)

    def test_stores_switchboard_reference(self):
        """Should store reference to switchboard instance."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertEqual(window.sb, self.sb)

    def test_initializes_settings_manager(self):
        """Should initialize settings manager."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertIsNotNone(window.settings)

    def test_initializes_state_manager(self):
        """Should initialize state manager."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertIsNotNone(window.state)

    def test_default_is_not_initialized(self):
        """Should start with is_initialized=False."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertFalse(window.is_initialized)


class TestMainWindowSignals(QtBaseTestCase):
    """Tests for MainWindow signal emissions."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_has_on_show_signal(self):
        """Should have on_show signal."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertTrue(hasattr(window, "on_show"))

    def test_has_on_hide_signal(self):
        """Should have on_hide signal."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertTrue(hasattr(window, "on_hide"))

    def test_has_on_close_signal(self):
        """Should have on_close signal."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertTrue(hasattr(window, "on_close"))

    def test_has_on_focus_in_signal(self):
        """Should have on_focus_in signal."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertTrue(hasattr(window, "on_focus_in"))

    def test_has_on_focus_out_signal(self):
        """Should have on_focus_out signal."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertTrue(hasattr(window, "on_focus_out"))

    def test_has_on_child_registered_signal(self):
        """Should have on_child_registered signal."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertTrue(hasattr(window, "on_child_registered"))

    def test_has_on_child_changed_signal(self):
        """Should have on_child_changed signal."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertTrue(hasattr(window, "on_child_changed"))

    def test_emits_on_show_when_shown(self):
        """Should emit on_show signal when window is shown."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        signal_received = []
        window.on_show.connect(lambda: signal_received.append(True))
        window.show()
        self.assertTrue(signal_received)

    def test_emits_on_hide_when_hidden(self):
        """Should emit on_hide signal when window is hidden."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        window.show()
        signal_received = []
        window.on_hide.connect(lambda: signal_received.append(True))
        window.hide()
        self.assertTrue(signal_received)


class TestMainWindowWidgetRegistration(QtBaseTestCase):
    """Tests for MainWindow widget registration."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_widgets_set_starts_empty(self):
        """Should start with empty widgets set."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertEqual(len(window.widgets), 0)

    def test_register_widget_adds_to_set(self):
        """Should add widget to widgets set when registered."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        central = QtWidgets.QWidget()
        window.setCentralWidget(central)

        widget = QtWidgets.QPushButton("Test")
        widget.setObjectName("testButton")
        widget.setParent(central)

        window.register_widget(widget)
        self.assertIn(widget, window.widgets)

    def test_register_widget_sets_ui_reference(self):
        """Should set ui reference on registered widget."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        central = QtWidgets.QWidget()
        window.setCentralWidget(central)

        widget = QtWidgets.QPushButton("Test")
        widget.setObjectName("testButton")
        widget.setParent(central)

        window.register_widget(widget)
        self.assertEqual(widget.ui, window)

    def test_register_widget_skips_no_object_name(self):
        """Should skip widget without object name."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        central = QtWidgets.QWidget()
        window.setCentralWidget(central)

        widget = QtWidgets.QPushButton("Test")
        # No object name set
        widget.setParent(central)

        window.register_widget(widget)
        self.assertNotIn(widget, window.widgets)

    def test_register_widget_emits_signal(self):
        """Should emit on_child_registered signal when widget is registered."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        central = QtWidgets.QWidget()
        window.setCentralWidget(central)

        widget = QtWidgets.QPushButton("Test")
        widget.setObjectName("testButton")
        widget.setParent(central)

        signal_received = []
        window.on_child_registered.connect(lambda w: signal_received.append(w))
        window.register_widget(widget)
        self.assertIn(widget, signal_received)

    def test_register_widget_skips_duplicate(self):
        """Should not register widget twice."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        central = QtWidgets.QWidget()
        window.setCentralWidget(central)

        widget = QtWidgets.QPushButton("Test")
        widget.setObjectName("testButton")
        widget.setParent(central)

        window.register_widget(widget)
        window.register_widget(widget)  # Try to register again
        # Should still only be in set once
        count = sum(1 for w in window.widgets if w == widget)
        self.assertEqual(count, 1)


class TestMainWindowPinned(QtBaseTestCase):
    """Tests for MainWindow pinned state."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_is_pinned_default_false(self):
        """Should default to not pinned."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertFalse(window.is_pinned)

    def test_is_pinned_true_when_prevent_hide(self):
        """Should be pinned when prevent_hide is True."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        window.prevent_hide = True
        self.assertTrue(window.is_pinned)

    def test_set_visible_respects_pinned(self):
        """Should not hide when pinned."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        window.show()
        window.prevent_hide = True
        window.setVisible(False)
        # Should still be visible when pinned
        self.assertTrue(window.isVisible())


class TestMainWindowGeometry(QtBaseTestCase):
    """Tests for MainWindow geometry save/restore."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_restore_window_size_default_true(self):
        """Should default to restore_window_size=True."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertTrue(window.restore_window_size)

    def test_restore_window_size_can_be_disabled(self):
        """Should be able to disable restore_window_size."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(
            MainWindow("TestWindow", self.sb, restore_window_size=False)
        )
        self.assertFalse(window.restore_window_size)

    def test_save_window_geometry_requires_restore_enabled(self):
        """Should not save geometry when restore is disabled."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(
            MainWindow("TestWindow", self.sb, restore_window_size=False)
        )
        # Should not raise, but should do nothing
        window.save_window_geometry()

    def test_clear_saved_geometry(self):
        """Should clear saved geometry from settings."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        # Should not raise
        window.clear_saved_geometry()


class TestMainWindowStyleSheet(QtBaseTestCase):
    """Tests for MainWindow stylesheet locking."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_lock_style_default_false(self):
        """Should default to lock_style=False."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertFalse(window.lock_style)

    def test_set_stylesheet_when_unlocked(self):
        """Should apply stylesheet when not locked."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        window.setStyleSheet("background: red;")
        self.assertIn("red", window.styleSheet())

    def test_set_stylesheet_blocked_when_locked(self):
        """Should not apply stylesheet when locked."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        window.setStyleSheet("background: blue;")
        window.lock_style = True
        window.setStyleSheet("background: red;")
        # Should still have blue, not red
        self.assertIn("blue", window.styleSheet())

    def test_reset_style_restores_original(self):
        """Should restore original stylesheet on reset."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        original = window.styleSheet()
        window.setStyleSheet("background: green;")
        window.reset_style()
        self.assertEqual(window.styleSheet(), original)


class TestMainWindowFooter(QtBaseTestCase):
    """Tests for MainWindow footer functionality."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_add_footer_default_true(self):
        """Should default to add_footer=True."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertTrue(window.add_footer)

    def test_add_footer_can_be_disabled(self):
        """Should be able to disable footer."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb, add_footer=False))
        self.assertFalse(window.add_footer)

    def test_creates_footer_with_central_widget(self):
        """Should create footer when central widget is set and add_footer=True."""
        from uitk.widgets.mainWindow import MainWindow

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        window = self.track_widget(
            MainWindow("TestWindow", self.sb, central_widget=central, add_footer=True)
        )
        # Footer should be created
        self.assertIsNotNone(window.footer)


class TestMainWindowIsCurrentUI(QtBaseTestCase):
    """Tests for MainWindow is_current_ui property."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_is_current_ui_returns_bool(self):
        """Should return boolean for is_current_ui."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        result = window.is_current_ui
        self.assertIsInstance(result, bool)

    def test_is_current_ui_setter_accepts_true(self):
        """Should accept True for is_current_ui setter."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        window.is_current_ui = True
        # Should set current_ui on switchboard
        self.assertEqual(self.sb.current_ui, window)

    def test_is_current_ui_setter_rejects_non_bool(self):
        """Should reject non-boolean values for is_current_ui setter."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        with self.assertRaises(ValueError):
            window.is_current_ui = "invalid"


class TestMainWindowLegalName(QtBaseTestCase):
    """Tests for MainWindow name conversion methods."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_legal_name_callable(self):
        """Should have legal_name as callable."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertTrue(callable(window.legal_name))

    def test_legal_name_returns_converted_name(self):
        """Should return converted name from switchboard."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("Test Window", self.sb))
        result = window.legal_name()
        self.assertEqual(result, "Test_Window")

    def test_base_name_callable(self):
        """Should have base_name as callable."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        self.assertTrue(callable(window.base_name))

    def test_base_name_returns_base(self):
        """Should return base name without tags."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow#tag", self.sb))
        result = window.base_name()
        self.assertEqual(result, "TestWindow")


class TestMainWindowEditTags(QtBaseTestCase):
    """Tests for MainWindow edit_tags method."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_edit_tags_on_self_when_no_target(self):
        """Should edit tags on self when target is None."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        # Should not raise - edits window's own tags
        window.edit_tags(add="newtag")


class TestMainWindowDeferred(QtBaseTestCase):
    """Tests for MainWindow deferred method execution."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_trigger_deferred_executes_methods(self):
        """Should execute deferred methods when triggered."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        executed = []
        window._deferred[0] = [lambda: executed.append(1)]
        window.trigger_deferred()
        self.assertEqual(executed, [1])

    def test_trigger_deferred_clears_after_execution(self):
        """Should clear deferred methods after execution."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        window._deferred[0] = [lambda: None]
        window.trigger_deferred()
        self.assertEqual(len(window._deferred), 0)

    def test_trigger_deferred_respects_priority(self):
        """Should execute deferred methods in priority order."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        executed = []
        window._deferred[1] = [lambda: executed.append("second")]
        window._deferred[0] = [lambda: executed.append("first")]
        window.trigger_deferred()
        self.assertEqual(executed, ["first", "second"])


class TestMainWindowSlots(QtBaseTestCase):
    """Tests for MainWindow slots property."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_slots_property_returns_from_switchboard(self):
        """Should return slots from switchboard."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        # Should call get_slots_instance on switchboard
        result = window.slots
        self.assertIsNotNone(result)


class TestMainWindowGetattr(QtBaseTestCase):
    """Tests for MainWindow __getattr__ magic method."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()

    def test_getattr_raises_for_unknown_attribute(self):
        """Should raise AttributeError for unknown attribute."""
        from uitk.widgets.mainWindow import MainWindow

        window = self.track_widget(MainWindow("TestWindow", self.sb))
        with self.assertRaises(AttributeError):
            _ = window.nonexistent_widget

    def test_getattr_finds_child_widget(self):
        """Should find child widget by object name."""
        from uitk.widgets.mainWindow import MainWindow

        central = QtWidgets.QWidget()
        window = self.track_widget(
            MainWindow("TestWindow", self.sb, central_widget=central)
        )

        button = QtWidgets.QPushButton("Test", central)
        button.setObjectName("myButton")

        result = window.myButton
        self.assertEqual(result, button)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
