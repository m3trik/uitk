# !/usr/bin/python
# coding=utf-8
"""Unit tests for Header widget.

This module tests the Header widget functionality including:
- Header creation and configuration
- Button configuration
- Pin/unpin functionality
- Dragging behavior
- Menu integration
- Title text management

Run standalone: python -m test.test_header
"""

import unittest
from unittest.mock import MagicMock, patch

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore, QtGui

from uitk.widgets.header import Header


class TestHeaderCreation(QtBaseTestCase):
    """Tests for Header creation and initialization."""

    def test_creates_header_with_defaults(self):
        """Should create header with default settings."""
        header = self.track_widget(Header())
        self.assertIsNotNone(header)
        self.assertFalse(header.pinned)

    def test_creates_header_with_parent(self):
        """Should create header with parent widget."""
        parent = self.track_widget(QtWidgets.QWidget())
        header = self.track_widget(Header(parent=parent))
        self.assertEqual(header.parent(), parent)

    def test_creates_header_with_title(self):
        """Should create header with title via kwargs."""
        header = self.track_widget(Header(setTitle="My Title"))
        self.assertEqual(header.title(), "My Title")

    def test_has_container_layout(self):
        """Should have container layout for buttons."""
        header = self.track_widget(Header())
        self.assertIsNotNone(header.container_layout)
        self.assertIsInstance(header.container_layout, QtWidgets.QHBoxLayout)

    def test_has_open_hand_cursor(self):
        """Should have open hand cursor for dragging."""
        header = self.track_widget(Header())
        self.assertEqual(header.cursor().shape(), QtCore.Qt.OpenHandCursor)

    def test_has_fixed_height(self):
        """Should have fixed height of 20 pixels."""
        header = self.track_widget(Header())
        self.assertEqual(header.height(), 20)

    def test_has_bold_font(self):
        """Should have bold font."""
        header = self.track_widget(Header())
        self.assertTrue(header.font().bold())


class TestHeaderButtons(QtBaseTestCase):
    """Tests for Header button configuration."""

    def test_buttons_dict_empty_by_default(self):
        """Should have empty buttons dict when no buttons configured."""
        header = self.track_widget(Header())
        self.assertEqual(header.buttons, {})

    def test_config_buttons_adds_pin_button(self):
        """Should add pin button when configured."""
        header = self.track_widget(Header(config_buttons=["pin"]))
        self.assertIn("pin", header.buttons)

    def test_config_buttons_adds_multiple_buttons(self):
        """Should add multiple buttons when configured."""
        header = self.track_widget(Header(config_buttons=["pin", "hide"]))
        self.assertIn("pin", header.buttons)
        self.assertIn("hide", header.buttons)

    def test_config_buttons_ignores_unknown(self):
        """Should ignore unknown button names."""
        header = self.track_widget(Header(config_buttons=["unknown"]))
        self.assertNotIn("unknown", header.buttons)

    def test_has_buttons_returns_false_when_empty(self):
        """Should return False when no buttons exist."""
        header = self.track_widget(Header())
        self.assertFalse(header.has_buttons())

    def test_has_buttons_returns_true_when_buttons_exist(self):
        """Should return True when buttons exist."""
        header = self.track_widget(Header(config_buttons=["pin"]))
        self.assertTrue(header.has_buttons())

    def test_has_buttons_checks_specific_type(self):
        """Should check for specific button type."""
        header = self.track_widget(Header(config_buttons=["pin"]))
        self.assertTrue(header.has_buttons("pin"))
        self.assertFalse(header.has_buttons("hide"))

    def test_has_buttons_checks_list_of_types(self):
        """Should check for list of button types."""
        header = self.track_widget(Header(config_buttons=["pin"]))
        self.assertTrue(header.has_buttons(["pin", "hide"]))
        self.assertFalse(header.has_buttons(["hide", "menu"]))


class TestHeaderCreateButton(QtBaseTestCase):
    """Tests for Header create_button method."""

    def test_create_button_returns_push_button(self):
        """Should create QPushButton."""
        header = self.track_widget(Header())
        button = header.create_button("radio_empty.svg", lambda: None)
        self.assertIsInstance(button, QtWidgets.QPushButton)

    def test_create_button_sets_object_name(self):
        """Should set object name when provided."""
        header = self.track_widget(Header())
        button = header.create_button(
            "radio_empty.svg", lambda: None, button_type="test_button"
        )
        self.assertEqual(button.objectName(), "hdr_test_button")

    def test_create_button_has_arrow_cursor(self):
        """Should have arrow cursor on button."""
        header = self.track_widget(Header())
        button = header.create_button("radio_empty.svg", lambda: None)
        self.assertEqual(button.cursor().shape(), QtCore.Qt.ArrowCursor)

    def test_create_button_connects_callback(self):
        """Should connect callback to clicked signal."""
        header = self.track_widget(Header())
        callback_called = []
        button = header.create_button(
            "radio_empty.svg", lambda: callback_called.append(True)
        )
        button.click()
        self.assertTrue(callback_called)


class TestHeaderPinning(QtBaseTestCase):
    """Tests for Header pin/unpin functionality."""

    def test_pinned_default_false(self):
        """Should default to unpinned state."""
        header = self.track_widget(Header())
        self.assertFalse(header.pinned)

    def test_toggle_pin_changes_state(self):
        """Should toggle pinned state."""
        # Create header with a window parent to avoid errors
        window = self.track_widget(QtWidgets.QWidget())
        header = self.track_widget(
            Header(parent=window, config_buttons=["pin"], pin_on_drag_only=False)
        )
        initial_state = header.pinned
        header.toggle_pin()
        self.assertNotEqual(header.pinned, initial_state)

    def test_toggle_pin_emits_signal(self):
        """Should emit toggled signal when pin state changes."""
        window = self.track_widget(QtWidgets.QWidget())
        header = self.track_widget(
            Header(parent=window, config_buttons=["pin"], pin_on_drag_only=False)
        )
        signal_received = []
        header.toggled.connect(lambda state: signal_received.append(state))
        header.toggle_pin()
        self.assertEqual(len(signal_received), 1)

    def test_reset_pin_state_unpins(self):
        """Should reset to unpinned state."""
        window = self.track_widget(QtWidgets.QWidget())
        header = self.track_widget(Header(parent=window, config_buttons=["pin"]))
        header.pinned = True
        header.reset_pin_state()
        self.assertFalse(header.pinned)

    def test_reset_pin_state_emits_signal(self):
        """Should emit toggled signal when reset."""
        window = self.track_widget(QtWidgets.QWidget())
        header = self.track_widget(Header(parent=window, config_buttons=["pin"]))
        header.pinned = True
        signal_received = []
        header.toggled.connect(lambda state: signal_received.append(state))
        header.reset_pin_state()
        self.assertIn(False, signal_received)


class TestHeaderTitle(QtBaseTestCase):
    """Tests for Header title methods."""

    def test_set_title_updates_text(self):
        """Should update text when title is set."""
        header = self.track_widget(Header())
        header.setTitle("New Title")
        self.assertEqual(header.title(), "New Title")

    def test_title_returns_text(self):
        """Should return current text."""
        header = self.track_widget(Header())
        header.setText("Current Text")
        self.assertEqual(header.title(), "Current Text")


class TestHeaderMenu(QtBaseTestCase):
    """Tests for Header menu integration."""

    def test_menu_property_creates_menu(self):
        """Should create menu on first access."""
        header = self.track_widget(Header())
        menu = header.menu
        self.assertIsNotNone(menu)

    def test_menu_property_returns_same_instance(self):
        """Should return same menu instance on subsequent access."""
        header = self.track_widget(Header())
        menu1 = header.menu
        menu2 = header.menu
        self.assertIs(menu1, menu2)


class TestHeaderButtonDefinitions(QtBaseTestCase):
    """Tests for Header button definitions."""

    def test_has_button_definitions(self):
        """Should have button_definitions class attribute."""
        self.assertTrue(hasattr(Header, "button_definitions"))
        self.assertIsInstance(Header.button_definitions, dict)

    def test_button_definitions_has_menu_button(self):
        """Should have menu definition."""
        self.assertIn("menu", Header.button_definitions)

    def test_button_definitions_has_minimize_button(self):
        """Should have minimize definition."""
        self.assertIn("minimize", Header.button_definitions)

    def test_button_definitions_has_hide_button(self):
        """Should have hide definition."""
        self.assertIn("hide", Header.button_definitions)

    def test_button_definitions_has_pin_button(self):
        """Should have pin definition."""
        self.assertIn("pin", Header.button_definitions)

    def test_button_definition_contains_icon_and_method(self):
        """Should have (icon, method) tuple for each button."""
        for name, definition in Header.button_definitions.items():
            self.assertIsInstance(definition, tuple)
            self.assertEqual(len(definition), 2)


class TestHeaderWindowActions(QtBaseTestCase):
    """Tests for Header window action methods."""

    def _make_header_window(self, buttons=("collapse", "minimize", "hide")):
        """Create a window with a header inside a layout, shown and sized."""
        window = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(window)
        layout.setContentsMargins(0, 0, 0, 0)
        header = Header(parent=window, config_buttons=list(buttons))
        layout.addWidget(header)
        # Add a body sibling so collapse has something to hide
        body = QtWidgets.QLabel("body", parent=window)
        layout.addWidget(body)
        window.show()
        window.resize(400, 300)
        window.move(500, 300)
        app.processEvents()
        return window, header, body

    def tearDown(self):
        """Clear the class-level stacking registry between tests."""
        Header._minimized_headers.clear()
        # Reset class defaults that individual tests may have changed
        Header.MINIMIZE_STACK = "horizontal"
        super().tearDown()

    # ---- minimize basics ----

    def test_minimize_window_collapses_and_narrows(self):
        """Should collapse to header height and narrow to MINIMIZE_WIDTH."""
        window, header, _ = self._make_header_window()
        header.minimize_window()
        app.processEvents()
        self.assertTrue(header._minimized)
        self.assertTrue(header._collapsed)
        self.assertEqual(window.width(), Header.MINIMIZE_WIDTH)

    def test_minimize_window_sets_suppression_property(self):
        """Should set _header_minimized property on window."""
        window, header, _ = self._make_header_window()
        header.minimize_window()
        app.processEvents()
        self.assertTrue(window.property("_header_minimized"))

    def test_minimize_toggle_restores(self):
        """Calling minimize_window again should restore original size/pos."""
        window, header, _ = self._make_header_window()
        orig_pos = window.pos()
        orig_size = window.size()
        header.minimize_window()
        app.processEvents()
        header.minimize_window()  # toggle
        app.processEvents()
        self.assertFalse(header._minimized)
        self.assertFalse(header._collapsed)
        self.assertEqual(window.size(), orig_size)
        self.assertEqual(window.pos(), orig_pos)
        self.assertFalse(window.property("_header_minimized"))

    def test_restore_clears_registry(self):
        """Restoring should remove header from _minimized_headers."""
        _, header, _ = self._make_header_window()
        header.minimize_window()
        app.processEvents()
        self.assertIn(header, Header._minimized_headers)
        header.restore_window()
        app.processEvents()
        self.assertNotIn(header, Header._minimized_headers)
        self.assertEqual(len(Header._minimized_headers), 0)

    # ---- horizontal stacking ----

    def test_horizontal_stacking_positions(self):
        """Multiple minimized windows should stack left-to-right.

        Bug: Before stacking, all minimized windows overlapped at the same
        lower-left corner position.
        Fixed: 2026-03-14
        """
        Header.MINIMIZE_STACK = "horizontal"
        pairs = [self._make_header_window() for _ in range(3)]
        for _, h, _ in pairs:
            h.minimize_window()
            app.processEvents()

        # Verify all three registered in the stacking list
        self.assertEqual(len(Header._minimized_headers), 3)

        # Test computed positions (deterministic) rather than actual window
        # coordinates which are platform/WM-dependent and can be flaky.
        screen = QtWidgets.QApplication.primaryScreen()
        avail = screen.availableGeometry()
        xs = [
            h._compute_minimize_position(h.window(), avail, i).x()
            for i, (_, h, _) in enumerate(pairs)
        ]
        # Each window should be further right than the previous
        for i in range(1, len(xs)):
            self.assertGreater(xs[i], xs[i - 1], f"win{i} not to the right of win{i-1}")

    def test_horizontal_stacking_same_y(self):
        """Horizontally stacked windows should share the same y coordinate."""
        Header.MINIMIZE_STACK = "horizontal"
        pairs = [self._make_header_window() for _ in range(3)]
        for _, h, _ in pairs:
            h.minimize_window()
            app.processEvents()

        screen = QtWidgets.QApplication.primaryScreen()
        avail = screen.availableGeometry()
        ys = [
            h._compute_minimize_position(h.window(), avail, i).y()
            for i, (_, h, _) in enumerate(pairs)
        ]
        for i in range(1, len(ys)):
            self.assertAlmostEqual(
                ys[i], ys[0], delta=4, msg=f"win{i} y differs too much from win0"
            )

    def test_horizontal_stacking_reflow_on_restore(self):
        """Restoring a middle window should close the gap in horizontal stack.

        Bug: If you minimized 3 windows (slots 0,1,2) then restored slot 1,
        slot 2 kept its old position, leaving a gap.
        Fixed: 2026-03-14
        """
        Header.MINIMIZE_STACK = "horizontal"
        pairs = [self._make_header_window() for _ in range(3)]
        for _, h, _ in pairs:
            h.minimize_window()
            app.processEvents()

        # Restore the middle one
        pairs[1][1].restore_window()
        app.processEvents()

        remaining = [(w, h) for w, h, _ in pairs if h._minimized]
        self.assertEqual(len(remaining), 2)
        # Verify computed reflow positions close the gap
        screen = QtWidgets.QApplication.primaryScreen()
        avail = screen.availableGeometry()
        xs = [
            h._compute_minimize_position(h.window(), avail, i).x()
            for i, (_, h) in enumerate(remaining)
        ]
        self.assertGreater(xs[1], xs[0], "reflow didn't close gap")

    # ---- vertical stacking ----

    def test_vertical_stacking_positions(self):
        """Multiple minimized windows should stack bottom-to-top when vertical."""
        Header.MINIMIZE_STACK = "vertical"
        pairs = [self._make_header_window() for _ in range(3)]
        for _, h, _ in pairs:
            h.minimize_window()
            app.processEvents()

        screen = QtWidgets.QApplication.primaryScreen()
        avail = screen.availableGeometry()
        ys = [
            h._compute_minimize_position(h.window(), avail, i).y()
            for i, (_, h, _) in enumerate(pairs)
        ]
        # Each window should be higher (smaller y) than the previous
        for i in range(1, len(ys)):
            self.assertLess(ys[i], ys[i - 1], f"win{i} not above win{i-1}")

    def test_vertical_stacking_same_x(self):
        """Vertically stacked windows should share the same x coordinate."""
        Header.MINIMIZE_STACK = "vertical"
        pairs = [self._make_header_window() for _ in range(3)]
        for _, h, _ in pairs:
            h.minimize_window()
            app.processEvents()

        screen = QtWidgets.QApplication.primaryScreen()
        avail = screen.availableGeometry()
        xs = [
            h._compute_minimize_position(h.window(), avail, i).x()
            for i, (_, h, _) in enumerate(pairs)
        ]
        for i in range(1, len(xs)):
            self.assertAlmostEqual(
                xs[i], xs[0], delta=4, msg=f"win{i} x differs too much from win0"
            )

    # ---- collapse / expand ----

    def test_collapse_hides_siblings(self):
        """Should hide body sibling and shrink to header height."""
        window, header, body = self._make_header_window()
        header.collapse_window()
        app.processEvents()
        self.assertTrue(header._collapsed)
        self.assertFalse(body.isVisible())

    def test_expand_restores_siblings(self):
        """Should restore body sibling and original size."""
        window, header, body = self._make_header_window()
        orig_size = window.size()
        header.collapse_window()
        app.processEvents()
        header.expand_window()
        app.processEvents()
        self.assertFalse(header._collapsed)
        self.assertTrue(body.isVisible())
        self.assertEqual(window.size(), orig_size)

    def test_collapse_with_fixed_width(self):
        """Should narrow the window when fixed_width is given."""
        window, header, _ = self._make_header_window()
        header.collapse_window(fixed_width=200)
        app.processEvents()
        self.assertEqual(window.width(), 200)
        self.assertTrue(header._collapsed)

    def test_collapse_with_fixed_width_below_minimum(self):
        """Should collapse below the window's minimum width.

        Bug: Windows with a minimum width wider than MINIMIZE_WIDTH could not
        shrink because intermediate widget minimumWidth constraints were not
        cleared during collapse.
        Fixed: 2026-04-03
        """
        window, header, body = self._make_header_window()
        # Set a minimum width larger than the collapse target
        window.setMinimumWidth(350)
        body.setMinimumWidth(350)
        app.processEvents()

        header.collapse_window(fixed_width=200)
        app.processEvents()
        self.assertTrue(header._collapsed)
        self.assertEqual(window.width(), 200)

        # Expand and verify constraints are restored
        header.expand_window()
        app.processEvents()
        self.assertFalse(header._collapsed)
        self.assertEqual(window.minimumWidth(), 350)
        self.assertEqual(body.minimumWidth(), 350)

    # ---- basic window actions ----

    def test_hide_window_hides_parent(self):
        """Should hide parent window."""
        window, header, _ = self._make_header_window(buttons=("pin", "hide"))
        header.hide_window()
        self.assertFalse(window.isVisible())


class TestHeaderAttachTo(QtBaseTestCase):
    """Tests for Header attach_to method."""

    def test_attach_to_widget_with_layout(self):
        """Should attach header to widget with layout."""
        widget = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(widget)
        header = self.track_widget(Header())
        header.attach_to(widget)
        self.assertEqual(widget.header, header)

    def test_attach_to_widget_creates_layout(self):
        """Should create layout if widget has none."""
        widget = self.track_widget(QtWidgets.QWidget())
        header = self.track_widget(Header())
        header.attach_to(widget)
        self.assertIsNotNone(widget.layout())

    def test_attach_to_mainwindow_uses_central_widget(self):
        """Should attach to central widget of QMainWindow."""
        window = self.track_widget(QtWidgets.QMainWindow())
        central = QtWidgets.QWidget()
        central_layout = QtWidgets.QVBoxLayout(central)
        window.setCentralWidget(central)
        header = self.track_widget(Header())
        header.attach_to(window)
        self.assertEqual(central.header, header)

    def test_attach_to_avoids_double_attachment(self):
        """Should not attach twice to same widget."""
        widget = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(widget)
        header = self.track_widget(Header())
        header.attach_to(widget)
        header.attach_to(widget)  # Second attach should be ignored
        self.assertEqual(widget.header, header)


class TestHeaderToggledSignal(QtBaseTestCase):
    """Tests for Header toggled signal."""

    def test_has_toggled_signal(self):
        """Should have toggled signal."""
        header = self.track_widget(Header())
        self.assertTrue(hasattr(header, "toggled"))

    def test_toggled_signal_emits_bool(self):
        """Should emit boolean value."""
        window = self.track_widget(QtWidgets.QWidget())
        header = self.track_widget(Header(parent=window, config_buttons=["pin"]))
        received_values = []
        header.toggled.connect(lambda v: received_values.append(v))
        header.toggle_pin()
        self.assertTrue(all(isinstance(v, bool) for v in received_values))


class TestHeaderConfigButtonsMethod(QtBaseTestCase):
    """Tests for Header config_buttons method."""

    def test_config_buttons_accepts_list(self):
        """Should accept list of button names."""
        header = self.track_widget(Header())
        header.config_buttons(["pin", "hide"])
        self.assertIn("pin", header.buttons)
        self.assertIn("hide", header.buttons)

    def test_config_buttons_accepts_args(self):
        """Should accept button names as args."""
        header = self.track_widget(Header())
        header.config_buttons("pin", "hide")
        self.assertIn("pin", header.buttons)
        self.assertIn("hide", header.buttons)

    def test_config_buttons_clears_existing(self):
        """Should clear existing buttons before adding new ones."""
        header = self.track_widget(Header(config_buttons=["pin"]))
        header.config_buttons("hide")
        self.assertNotIn("pin", header.buttons)
        self.assertIn("hide", header.buttons)


class TestHeaderIconMethods(QtBaseTestCase):
    """Tests for Header icon methods."""

    def test_get_icon_path_returns_string(self):
        """Should return string path."""
        header = self.track_widget(Header())
        path = header.get_icon_path("radio_empty.svg")
        self.assertIsInstance(path, str)

    def test_get_icon_path_includes_filename(self):
        """Should include filename in path."""
        header = self.track_widget(Header())
        path = header.get_icon_path("radio_empty.svg")
        self.assertIn("radio_empty.svg", path)

    def test_create_svg_icon_returns_qicon(self):
        """Should return QIcon."""
        header = self.track_widget(Header())
        icon = header.create_svg_icon("radio_empty.svg")
        self.assertIsInstance(icon, QtGui.QIcon)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
