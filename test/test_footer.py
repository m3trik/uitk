# !/usr/bin/python
# coding=utf-8
"""Unit tests for Footer widget.

This module tests the Footer widget functionality including:
- Footer creation and configuration
- Status text management
- Size grip functionality
- Font size updates
- Attach to widget functionality
- FooterStatusController

Run standalone: python -m test.test_footer
"""

import unittest
from unittest.mock import MagicMock, patch

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore

from uitk.widgets.footer import Footer, FooterStatusController


class TestFooterCreation(QtBaseTestCase):
    """Tests for Footer creation and initialization."""

    def test_creates_footer_with_defaults(self):
        """Should create footer with default settings."""
        footer = self.track_widget(Footer())
        self.assertIsNotNone(footer)

    def test_creates_footer_with_parent(self):
        """Should create footer with parent widget."""
        parent = self.track_widget(QtWidgets.QWidget())
        footer = self.track_widget(Footer(parent=parent))
        self.assertEqual(footer.parent(), parent)

    def test_creates_footer_with_size_grip(self):
        """Should create footer with size grip by default."""
        footer = self.track_widget(Footer(add_size_grip=True))
        self.assertIsNotNone(footer._size_grip)

    def test_creates_footer_without_size_grip(self):
        """Should create footer without size grip when disabled."""
        footer = self.track_widget(Footer(add_size_grip=False))
        self.assertIsNone(footer._size_grip)

    def test_has_container_layout(self):
        """Should have container layout."""
        footer = self.track_widget(Footer())
        self.assertIsNotNone(footer.container_layout)
        self.assertIsInstance(footer.container_layout, QtWidgets.QHBoxLayout)

    def test_has_fixed_height(self):
        """Should have fixed height of 20 pixels."""
        footer = self.track_widget(Footer())
        self.assertEqual(footer.height(), 20)

    def test_has_left_alignment(self):
        """Should have left alignment for text."""
        footer = self.track_widget(Footer())
        alignment = footer.alignment()
        self.assertTrue(alignment & QtCore.Qt.AlignLeft)

    def test_has_vertical_center_alignment(self):
        """Should have vertical center alignment."""
        footer = self.track_widget(Footer())
        alignment = footer.alignment()
        self.assertTrue(alignment & QtCore.Qt.AlignVCenter)


class TestFooterStatusText(QtBaseTestCase):
    """Tests for Footer status text methods."""

    def test_set_status_text_updates_text(self):
        """Should update text when status text is set."""
        footer = self.track_widget(Footer())
        footer.setStatusText("Ready")
        self.assertEqual(footer.text(), "Ready")

    def test_status_text_returns_current_status(self):
        """Should return current status text."""
        footer = self.track_widget(Footer())
        footer.setStatusText("Processing")
        self.assertEqual(footer.statusText(), "Processing")

    def test_set_status_text_with_none(self):
        """Should handle None status text."""
        footer = self.track_widget(Footer())
        footer.setStatusText(None)
        self.assertEqual(footer.statusText(), "")

    def test_set_status_text_with_empty_string(self):
        """Should handle empty string status text."""
        footer = self.track_widget(Footer())
        footer.setStatusText("")
        self.assertEqual(footer.statusText(), "")


class TestFooterDefaultStatusText(QtBaseTestCase):
    """Tests for Footer default status text."""

    def test_set_default_status_text(self):
        """Should set default status text."""
        footer = self.track_widget(Footer())
        footer.setDefaultStatusText("Default Text")
        self.assertEqual(footer._default_status_text, "Default Text")

    def test_default_status_shown_when_no_status(self):
        """Should show default text when no status set."""
        footer = self.track_widget(Footer())
        footer.setDefaultStatusText("Default")
        # When status text is empty, default should be shown
        self.assertEqual(footer.text(), "Default")

    def test_status_text_overrides_default(self):
        """Should show status text over default."""
        footer = self.track_widget(Footer())
        footer.setDefaultStatusText("Default")
        footer.setStatusText("Custom Status")
        self.assertEqual(footer.text(), "Custom Status")


class TestFooterKwargsInitialization(QtBaseTestCase):
    """Tests for Footer initialization with kwargs."""

    def test_accepts_set_status_text_kwarg(self):
        """Should accept setStatusText as kwarg."""
        footer = self.track_widget(Footer(setStatusText="Initial Status"))
        self.assertEqual(footer.statusText(), "Initial Status")


class TestFooterAttachTo(QtBaseTestCase):
    """Tests for Footer attach_to method."""

    def test_attach_to_widget_with_layout(self):
        """Should attach footer to widget with layout."""
        widget = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(widget)
        footer = self.track_widget(Footer())
        footer.attach_to(widget)
        self.assertEqual(widget.footer, footer)

    def test_attach_to_widget_creates_layout(self):
        """Should create layout if widget has none."""
        widget = self.track_widget(QtWidgets.QWidget())
        footer = self.track_widget(Footer())
        footer.attach_to(widget)
        self.assertIsNotNone(widget.layout())

    def test_attach_to_mainwindow_uses_central_widget(self):
        """Should attach to central widget of QMainWindow."""
        window = self.track_widget(QtWidgets.QMainWindow())
        central = QtWidgets.QWidget()
        central_layout = QtWidgets.QVBoxLayout(central)
        window.setCentralWidget(central)
        footer = self.track_widget(Footer())
        footer.attach_to(window)
        self.assertEqual(central.footer, footer)

    def test_attach_to_avoids_double_attachment(self):
        """Should not attach twice to same widget."""
        widget = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(widget)
        footer = self.track_widget(Footer())
        footer.attach_to(widget)
        footer.attach_to(widget)  # Second attach should be ignored
        self.assertEqual(widget.footer, footer)


class TestFooterSizeGrip(QtBaseTestCase):
    """Tests for Footer size grip functionality."""

    def test_size_grip_is_qsizegrip(self):
        """Should have QSizeGrip widget."""
        footer = self.track_widget(Footer(add_size_grip=True))
        self.assertIsInstance(footer._size_grip, QtWidgets.QSizeGrip)

    def test_size_grip_none_when_disabled(self):
        """Should not have size grip when disabled."""
        footer = self.track_widget(Footer(add_size_grip=False))
        self.assertIsNone(footer._size_grip)


class TestFooterFontSize(QtBaseTestCase):
    """Tests for Footer font size updates."""

    def test_update_font_size_method_exists(self):
        """Should have update_font_size method."""
        footer = self.track_widget(Footer())
        self.assertTrue(hasattr(footer, "update_font_size"))
        self.assertTrue(callable(footer.update_font_size))

    def test_update_font_size_sets_font(self):
        """Should update font when called."""
        footer = self.track_widget(Footer())
        initial_font = footer.font()
        footer.update_font_size()
        # Font should be updated (may be same size if height unchanged)
        self.assertIsNotNone(footer.font())


class TestFooterResizeEvent(QtBaseTestCase):
    """Tests for Footer resize event handling."""

    def test_resize_event_updates_font(self):
        """Should update font on resize event."""
        footer = self.track_widget(Footer())
        # Resize the footer
        footer.resize(200, 30)
        # Font size should be recalculated
        font_size = footer.font().pointSizeF()
        self.assertGreater(font_size, 0)


class TestFooterStatusController(QtBaseTestCase):
    """Tests for FooterStatusController class."""

    def test_creates_controller_with_footer(self):
        """Should create controller with footer."""
        footer = self.track_widget(Footer())
        controller = FooterStatusController(footer)
        self.assertIsNotNone(controller)

    def test_controller_updates_footer(self):
        """Should update footer when update is called."""
        footer = self.track_widget(Footer())
        controller = FooterStatusController(footer, resolver=lambda: "Updated")
        controller.update()
        self.assertEqual(footer.statusText(), "Updated")

    def test_controller_with_resolver(self):
        """Should use resolver function to get status."""
        footer = self.track_widget(Footer())
        controller = FooterStatusController(footer, resolver=lambda: "From Resolver")
        self.assertEqual(footer.statusText(), "From Resolver")

    def test_controller_set_resolver(self):
        """Should allow changing resolver."""
        footer = self.track_widget(Footer())
        controller = FooterStatusController(footer, resolver=lambda: "Initial")
        controller.set_resolver(lambda: "Changed")
        self.assertEqual(footer.statusText(), "Changed")

    def test_controller_with_default_text(self):
        """Should set default text on footer."""
        footer = self.track_widget(Footer())
        controller = FooterStatusController(footer, default_text="Default")
        self.assertEqual(footer._default_status_text, "Default")


class TestFooterStatusControllerTruncation(QtBaseTestCase):
    """Tests for FooterStatusController truncation functionality."""

    def test_truncation_with_length(self):
        """Should truncate text when length specified."""
        footer = self.track_widget(Footer())
        controller = FooterStatusController(
            footer,
            resolver=lambda: "This is a very long status text",
            truncate_kwargs={"length": 10, "mode": "end"},
        )
        # Text should be truncated
        self.assertLessEqual(len(footer.statusText()), 15)  # length + insert

    def test_truncation_with_invalid_length(self):
        """Should not truncate when length is invalid."""
        footer = self.track_widget(Footer())
        controller = FooterStatusController(
            footer,
            resolver=lambda: "Short",
            truncate_kwargs={"length": -1},
        )
        # Text should not be modified
        self.assertEqual(footer.statusText(), "Short")

    def test_set_truncation_method(self):
        """Should allow changing truncation settings."""
        footer = self.track_widget(Footer())
        controller = FooterStatusController(footer, resolver=lambda: "Long text here")
        controller.set_truncation(length=5, mode="end")
        controller.update()
        # Text should be truncated
        self.assertLessEqual(len(footer.statusText()), 10)


class TestFooterStatusControllerFallbackTruncate(QtBaseTestCase):
    """Tests for FooterStatusController fallback truncation."""

    def test_fallback_truncate_end_mode(self):
        """Should truncate at end in end mode."""
        footer = self.track_widget(Footer())
        controller = FooterStatusController(footer)
        result = controller._fallback_truncate(
            "Hello World",
            {"length": 5, "mode": "end", "insert": ".."},
        )
        self.assertTrue(result.startswith("Hello"))
        self.assertTrue(result.endswith(".."))

    def test_fallback_truncate_start_mode(self):
        """Should truncate at start in start mode."""
        footer = self.track_widget(Footer())
        controller = FooterStatusController(footer)
        result = controller._fallback_truncate(
            "Hello World",
            {"length": 5, "mode": "start", "insert": ".."},
        )
        self.assertTrue(result.startswith(".."))

    def test_fallback_truncate_middle_mode(self):
        """Should truncate in middle in middle mode."""
        footer = self.track_widget(Footer())
        controller = FooterStatusController(footer)
        result = controller._fallback_truncate(
            "Hello World",
            {"length": 8, "mode": "middle", "insert": ".."},
        )
        self.assertIn("..", result)


class TestFooterStatusControllerSanitize(QtBaseTestCase):
    """Tests for FooterStatusController _sanitize_truncate_kwargs."""

    def test_sanitize_returns_none_for_none(self):
        """Should return None when input is None."""
        result = FooterStatusController._sanitize_truncate_kwargs(None)
        self.assertIsNone(result)

    def test_sanitize_returns_none_for_invalid_length(self):
        """Should return None when length is invalid."""
        result = FooterStatusController._sanitize_truncate_kwargs({"length": -5})
        self.assertIsNone(result)

    def test_sanitize_returns_dict_for_valid_input(self):
        """Should return dict when input is valid."""
        result = FooterStatusController._sanitize_truncate_kwargs({"length": 10})
        self.assertIsNotNone(result)
        self.assertEqual(result["length"], 10)


class TestFooterClass(QtBaseTestCase):
    """Tests for Footer class property."""

    def test_has_class_property(self):
        """Should have 'class' property set to class name."""
        footer = self.track_widget(Footer())
        class_prop = footer.property("class")
        self.assertEqual(class_prop, "Footer")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
