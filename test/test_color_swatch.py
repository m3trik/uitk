# !/usr/bin/python
# coding=utf-8
"""Unit tests for ColorSwatch widget and ColorId default swatch colors.

Tests cover:
- Swatch creation and default color initialization
- Color property getter/setter
- Single click selects (checks) the swatch without opening color dialog
- Double click opens color dialog
- Settings save/load round-trip
- Default swatch color palette from ColorId
- get_color_difference pure logic

Run standalone: python -m test.test_color_swatch
"""

import unittest
from unittest.mock import patch, MagicMock

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtGui, QtCore


# =============================================================================
# ColorSwatch Creation
# =============================================================================


class TestColorSwatchCreation(QtBaseTestCase):
    """Tests for ColorSwatch widget creation."""

    def test_creates_swatch_with_defaults(self):
        """Should create a swatch with default white color when no args given."""
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch = self.track_widget(ColorSwatch())
        app.processEvents()
        self.assertIsNotNone(swatch)
        self.assertIsInstance(swatch.color, QtGui.QColor)

    def test_creates_swatch_with_initial_color(self):
        """Should create a swatch with the specified initial color."""
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch = self.track_widget(
            ColorSwatch(color=QtGui.QColor(255, 0, 0), setObjectName="test_red")
        )
        app.processEvents()
        self.assertEqual(swatch.color.red(), 255)
        self.assertEqual(swatch.color.green(), 0)
        self.assertEqual(swatch.color.blue(), 0)

    def test_creates_swatch_checkable(self):
        """Should support checkable mode for selection."""
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch = self.track_widget(ColorSwatch(setCheckable=True))
        app.processEvents()
        self.assertTrue(swatch.isCheckable())


# =============================================================================
# Color Property
# =============================================================================


class TestColorSwatchColorProperty(QtBaseTestCase):
    """Tests for the color property getter/setter."""

    def test_set_color_with_qcolor(self):
        """Should accept a QColor directly."""
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch = self.track_widget(ColorSwatch(setObjectName="test_qcolor"))
        app.processEvents()
        new_color = QtGui.QColor(0, 128, 255)
        swatch.color = new_color
        self.assertEqual(swatch.color.red(), 0)
        self.assertEqual(swatch.color.green(), 128)
        self.assertEqual(swatch.color.blue(), 255)

    def test_set_color_with_tuple(self):
        """Should accept an RGB tuple and convert to QColor."""
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch = self.track_widget(ColorSwatch(setObjectName="test_tuple"))
        app.processEvents()
        swatch.color = (100, 150, 200)
        self.assertEqual(swatch.color.red(), 100)
        self.assertEqual(swatch.color.green(), 150)
        self.assertEqual(swatch.color.blue(), 200)

    def test_set_color_with_string(self):
        """Should accept a color name string."""
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch = self.track_widget(ColorSwatch(setObjectName="test_string"))
        app.processEvents()
        swatch.color = "#ff0000"
        self.assertEqual(swatch.color.red(), 255)
        self.assertEqual(swatch.color.green(), 0)
        self.assertEqual(swatch.color.blue(), 0)

    def test_color_changed_signal_emitted(self):
        """Should emit colorChanged signal when color is set."""
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch = self.track_widget(ColorSwatch(setObjectName="test_signal"))
        app.processEvents()
        received = []
        swatch.colorChanged.connect(lambda c: received.append(c))
        swatch.color = QtGui.QColor(10, 20, 30)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].red(), 10)


# =============================================================================
# Click Behavior
# =============================================================================


class TestColorSwatchClickBehavior(QtBaseTestCase):
    """Tests for single vs double click behavior."""

    def test_single_click_toggles_checked_state(self):
        """Single click should toggle the checked state without opening the color dialog."""
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch = self.track_widget(
            ColorSwatch(
                color=QtGui.QColor(100, 100, 100),
                setObjectName="test_click",
                setCheckable=True,
            )
        )
        app.processEvents()
        self.assertFalse(swatch.isChecked())

        # Simulate single click
        swatch.click()
        self.assertTrue(swatch.isChecked())

        # Click again to uncheck
        swatch.click()
        self.assertFalse(swatch.isChecked())

    @patch("uitk.widgets.colorSwatch.QtWidgets.QColorDialog")
    def test_single_click_does_not_open_dialog(self, mock_dialog_cls):
        """Single click must NOT open the color dialog."""
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch = self.track_widget(
            ColorSwatch(
                color=QtGui.QColor(100, 100, 100),
                setObjectName="test_no_dialog",
                setCheckable=True,
            )
        )
        app.processEvents()
        swatch.click()
        mock_dialog_cls.assert_not_called()

    @patch("uitk.widgets.colorSwatch.QtWidgets.QColorDialog")
    def test_double_click_opens_color_dialog(self, mock_dialog_cls):
        """Double click should open the color dialog."""
        from uitk.widgets.colorSwatch import ColorSwatch

        mock_dialog = MagicMock()
        mock_dialog.exec_.return_value = False
        mock_dialog_cls.return_value = mock_dialog

        swatch = self.track_widget(
            ColorSwatch(
                color=QtGui.QColor(100, 100, 100),
                setObjectName="test_dblclick",
                setCheckable=True,
            )
        )
        app.processEvents()

        # Simulate double click event
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonDblClick,
            QtCore.QPointF(5, 5),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        swatch.mouseDoubleClickEvent(event)
        mock_dialog_cls.assert_called_once()
        mock_dialog.exec_.assert_called_once()


# =============================================================================
# keep_square aspect lock
# =============================================================================


class TestColorSwatchKeepSquare(QtBaseTestCase):
    """Tests for the opt-in keep_square aspect lock."""

    def test_keep_square_off_by_default(self):
        """Swatches should not constrain their aspect unless asked to."""
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch = self.track_widget(ColorSwatch(setObjectName="test_square_off"))
        app.processEvents()
        self.assertFalse(swatch.keep_square)

    def test_keep_square_makes_swatch_square_in_grid(self):
        """A keep_square swatch should track its column width and stay square."""
        from uitk.widgets.colorSwatch import ColorSwatch

        container = self.track_widget(QtWidgets.QWidget())
        grid = QtWidgets.QGridLayout(container)
        grid.setSpacing(2)
        grid.setContentsMargins(0, 0, 0, 0)
        swatches = []
        for i in range(6):
            sw = ColorSwatch(setObjectName=f"test_square_{i}")
            sw.keep_square = True
            grid.addWidget(sw, 0, i)
            swatches.append(sw)

        for width in (200, 300):
            container.resize(width, 80)
            container.show()
            for _ in range(5):
                app.processEvents()
            for sw in swatches:
                self.assertEqual(
                    sw.height(),
                    sw.width(),
                    f"swatch not square at container width {width}: "
                    f"{sw.width()}x{sw.height()}",
                )

    def test_keep_square_settable_via_kwargs(self):
        """keep_square should be settable through the set_attributes kwargs path."""
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch = self.track_widget(
            ColorSwatch(setObjectName="test_square_kwarg", keep_square=True)
        )
        app.processEvents()
        self.assertTrue(swatch.keep_square)


# =============================================================================
# Settings Save/Load
# =============================================================================


class TestColorSwatchSettings(QtBaseTestCase):
    """Tests for settings persistence."""

    def setUp(self):
        super().setUp()
        self.settings = QtCore.QSettings("uitk_test", "color_swatch_test")
        # Clear test keys before each test
        self.settings.remove("colorSwatch/test_persist")
        self.settings.remove("colorSwatch/test_initial")
        self.settings.remove("colorSwatch/test_initial_hex")
        self.settings.sync()

    def test_save_and_load_color(self):
        """Should persist color via QSettings and restore it."""
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch1 = self.track_widget(
            ColorSwatch(
                color=QtGui.QColor(200, 100, 50),
                settings=self.settings,
                setObjectName="test_persist",
            )
        )
        # Process deferred singleShot timers
        app.processEvents()
        app.processEvents()
        swatch1.color = QtGui.QColor(42, 84, 168)
        self.settings.sync()

        # Verify the color was saved in settings
        saved = self.settings.value("colorSwatch/test_persist/color")
        self.assertIsNotNone(saved, "Color was not saved to settings")

        # Create a new swatch with same objectName and settings — should load saved color
        swatch2 = self.track_widget(
            ColorSwatch(
                settings=self.settings,
                setObjectName="test_persist",
            )
        )
        # Process deferred singleShot timers for loadColor
        app.processEvents()
        app.processEvents()
        self.assertEqual(swatch2.color.red(), 42)
        self.assertEqual(swatch2.color.green(), 84)
        self.assertEqual(swatch2.color.blue(), 168)

    def test_initial_color_used_when_no_saved_settings(self):
        """Should use _initialColor when no saved color exists in settings."""
        from uitk.widgets.colorSwatch import ColorSwatch

        self.settings.remove("colorSwatch/test_initial")
        swatch = self.track_widget(
            ColorSwatch(
                color=QtGui.QColor(180, 120, 120),
                settings=self.settings,
                setObjectName="test_initial",
            )
        )
        # Drain the deferred initializeRequested QTimer.singleShot.
        app.processEvents()
        app.processEvents()
        self.assertEqual(swatch.color.red(), 180)
        self.assertEqual(swatch.color.green(), 120)
        self.assertEqual(swatch.color.blue(), 120)

    def test_initial_color_from_hex_string_when_no_saved_settings(self):
        """Should accept a hex string as initial color and not fall back to white."""
        from uitk.widgets.colorSwatch import ColorSwatch

        self.settings.remove("colorSwatch/test_initial_hex")
        swatch = self.track_widget(
            ColorSwatch(
                color="#88B8D0",
                settings=self.settings,
                setObjectName="test_initial_hex",
            )
        )
        app.processEvents()
        app.processEvents()
        self.assertEqual(swatch.color.red(), 0x88)
        self.assertEqual(swatch.color.green(), 0xB8)
        self.assertEqual(swatch.color.blue(), 0xD0)


# =============================================================================
# Default Swatch Palette
# =============================================================================


def _mock_mayatk_modules():
    """Build a sys.modules patch dict that stubs the mayatk package chain.

    Stubs maya.cmds so color_id can be imported without Maya, while
    using the real mayatk source from the monorepo.
    """
    import sys
    import types
    import os
    from unittest.mock import MagicMock

    # Ensure mayatk source is importable
    mayatk_root = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "mayatk")
    )
    if mayatk_root not in sys.path:
        sys.path.insert(0, mayatk_root)

    mock_maya = types.ModuleType("maya")
    mock_cmds = MagicMock()

    return {
        "maya": mock_maya,
        "maya.cmds": mock_cmds,
    }


class TestDefaultSwatchColors(QtBaseTestCase):
    """Tests for the DEFAULT_SWATCH_COLORS palette on ColorId."""

    def test_palette_has_12_colors(self):
        """Should have exactly 12 default swatch colors."""
        with patch.dict("sys.modules", _mock_mayatk_modules()):
            from mayatk.display_utils.color_id import ColorId

            self.assertEqual(len(ColorId.DEFAULT_SWATCH_COLORS), 12)

    def test_palette_colors_are_valid_rgb_tuples(self):
        """Each default color should be a valid (R, G, B) tuple with values 0-255."""
        with patch.dict("sys.modules", _mock_mayatk_modules()):
            from mayatk.display_utils.color_id import ColorId

            for color in ColorId.DEFAULT_SWATCH_COLORS:
                self.assertIsInstance(color, tuple)
                self.assertEqual(len(color), 3)
                for ch in color:
                    self.assertGreaterEqual(ch, 0)
                    self.assertLessEqual(ch, 255)

    def test_palette_colors_are_all_distinct(self):
        """Each default swatch color should be unique."""
        with patch.dict("sys.modules", _mock_mayatk_modules()):
            from mayatk.display_utils.color_id import ColorId

            colors = ColorId.DEFAULT_SWATCH_COLORS
            self.assertEqual(len(colors), len(set(colors)))

    def test_palette_colors_are_desaturated(self):
        """Default colors should be muted (not fully saturated primary colors)."""
        with patch.dict("sys.modules", _mock_mayatk_modules()):
            from mayatk.display_utils.color_id import ColorId

            for color in ColorId.DEFAULT_SWATCH_COLORS:
                qc = QtGui.QColor(*color)
                # Saturation < 255 means desaturated
                self.assertLess(
                    qc.saturation(),
                    200,
                    f"Color {color} is too saturated ({qc.saturation()})",
                )


# =============================================================================
# ColorUtils.get_color_difference (pure logic, no Maya)
# =============================================================================


class TestGetColorDifference(unittest.TestCase):
    """Tests for get_color_difference static method."""

    def _get_cls(self):
        with patch.dict("sys.modules", _mock_mayatk_modules()):
            from mayatk.display_utils.color_id import ColorUtils

            return ColorUtils

    def test_identical_colors_return_zero(self):
        """get_color_difference of identical colors should be 0."""
        cls = self._get_cls()
        self.assertAlmostEqual(cls.get_color_difference((1, 0, 0), (1, 0, 0)), 0.0)

    def test_opposite_colors_return_one(self):
        """get_color_difference of black vs white (normalized) should be 1.0."""
        cls = self._get_cls()
        self.assertAlmostEqual(cls.get_color_difference((0, 0, 0), (1, 1, 1)), 1.0)

    def test_partial_difference(self):
        """get_color_difference should compute average channel difference."""
        cls = self._get_cls()
        # (0.5, 0.5, 0.5) vs (0.0, 0.0, 0.0) => avg diff = 0.5
        self.assertAlmostEqual(
            cls.get_color_difference((0.5, 0.5, 0.5), (0.0, 0.0, 0.0)), 0.5
        )


# =============================================================================

if __name__ == "__main__":
    unittest.main()
