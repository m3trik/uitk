# !/usr/bin/python
# coding=utf-8
"""Unit tests for the ColorSwatch widget.

Tests cover:
- Swatch creation and default color initialization
- Color property getter/setter
- Single click selects (checks) the swatch without opening color dialog
- Double click opens color dialog
- keep_square aspect lock
- Settings save/load round-trip

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
        self.settings.remove("colorSwatch/test_alpha")
        self.settings.remove("colorSwatch/test_ext_initial")
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
        """Should use the constructor color when no saved color exists in settings."""
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

    def test_external_initial_color_applied_when_no_saved_settings(self):
        """_initialColor set AFTER construction seeds the no-settings default.

        Regression: mayatk/blendertk Color ID build swatches from a .ui (no
        `color=` kwarg), then assign `button._initialColor = <pastel>` and
        `button.settings = <store>`. With nothing persisted the swatch must
        show that pastel — not the __init__ white fallback.
        """
        from uitk.widgets.colorSwatch import ColorSwatch

        swatch = self.track_widget(ColorSwatch(setObjectName="test_ext_initial"))
        # Mirror the downstream order: seed _initialColor, then attach settings
        # (assigning .settings schedules the deferred initializeColor()).
        swatch._initialColor = QtGui.QColor(180, 120, 60)
        swatch.settings = self.settings
        app.processEvents()
        app.processEvents()
        self.assertEqual(swatch.color.red(), 180)
        self.assertEqual(swatch.color.green(), 120)
        self.assertEqual(swatch.color.blue(), 60)

    def test_saved_color_wins_over_external_initial_color(self):
        """A persisted value overrides an externally-set _initialColor."""
        from uitk.widgets.colorSwatch import ColorSwatch

        self.settings.setValue("colorSwatch/test_ext_initial/color", "#0A141E")
        self.settings.sync()

        swatch = self.track_widget(ColorSwatch(setObjectName="test_ext_initial"))
        swatch._initialColor = QtGui.QColor(180, 120, 60)
        swatch.settings = self.settings
        app.processEvents()
        app.processEvents()
        self.assertEqual(swatch.color.red(), 0x0A)
        self.assertEqual(swatch.color.green(), 0x14)
        self.assertEqual(swatch.color.blue(), 0x1E)

    def test_color_readable_before_event_loop(self):
        """`.color` must be valid immediately, before the deferred init runs.

        Regression: _color was only created inside the deferred singleShot, so
        reading `.color` (or any repaint) before the event loop spun raised
        AttributeError.
        """
        from uitk.widgets.colorSwatch import ColorSwatch

        # No processEvents() — read synchronously right after construction.
        swatch = self.track_widget(ColorSwatch(color=QtGui.QColor(10, 20, 30)))
        color = swatch.color  # must not raise
        self.assertIsInstance(color, QtGui.QColor)
        self.assertTrue(color.isValid())
        swatch.updateBackgroundColor()  # also touches _color; must not raise

    def test_alpha_persists_across_save_load(self):
        """A color with alpha must round-trip through settings (HexArgb)."""
        from uitk.widgets.colorSwatch import ColorSwatch

        self.settings.remove("colorSwatch/test_alpha")
        swatch = self.track_widget(
            ColorSwatch(settings=self.settings, setObjectName="test_alpha")
        )
        app.processEvents()
        app.processEvents()
        swatch.color = QtGui.QColor(200, 100, 50, 128)  # 50% alpha
        self.settings.sync()

        swatch2 = self.track_widget(
            ColorSwatch(settings=self.settings, setObjectName="test_alpha")
        )
        app.processEvents()
        app.processEvents()
        self.assertEqual(swatch2.color.alpha(), 128)
        self.assertEqual(
            (swatch2.color.red(), swatch2.color.green(), swatch2.color.blue()),
            (200, 100, 50),
        )


# =============================================================================
# NOTE: The default swatch palette (ColorId.DEFAULT_SWATCH_COLORS) and
# ColorUtils.get_color_difference live in mayatk (display_utils/color_id.py),
# a *downstream* package. Their tests belong there (mayatk/test/
# test_display_extras.py) — not here — so uitk's CI never depends on a mayatk
# symbol that hasn't published yet. The ColorSwatch widget itself is
# palette-agnostic; callers pass colors in.
# =============================================================================

if __name__ == "__main__":
    unittest.main()
