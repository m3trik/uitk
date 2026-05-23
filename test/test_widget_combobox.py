# !/usr/bin/python
# coding=utf-8
"""Tests for WidgetComboBox widget.

Run standalone: python -m test.test_widget_combobox
"""
import unittest
from unittest.mock import MagicMock

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore


class TestWidgetComboBoxAdd(QtBaseTestCase):
    """Tests for WidgetComboBox.add() method."""

    def test_add_widget_instance(self):
        """Should add a widget instance."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        checkbox = QtWidgets.QCheckBox("Test")
        result = combo.add(checkbox)

        self.assertEqual(result, checkbox)
        self.assertEqual(combo.count(), 1)

    def test_add_widget_class(self):
        """Should instantiate and add a widget class."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        result = combo.add(QtWidgets.QCheckBox)

        self.assertIsInstance(result, QtWidgets.QCheckBox)
        self.assertEqual(combo.count(), 1)

    def test_add_widget_class_with_kwargs(self):
        """Should instantiate widget class and apply kwargs to the widget."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        result = combo.add(QtWidgets.QCheckBox, setText="My Checkbox", setChecked=True)

        self.assertIsInstance(result, QtWidgets.QCheckBox)
        self.assertEqual(result.text(), "My Checkbox")
        self.assertTrue(result.isChecked())
        self.assertEqual(combo.count(), 1)

    def test_add_widget_tuple(self):
        """Should add widget with label from tuple."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        checkbox = QtWidgets.QCheckBox("Test")
        result = combo.add([(checkbox, "Label")])

        # Single item in list returns the widget directly, not a list
        self.assertEqual(result, checkbox)
        self.assertEqual(combo.count(), 1)

    def test_add_multiple_widgets(self):
        """Should add multiple widgets from list."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        cb1 = QtWidgets.QCheckBox("One")
        cb2 = QtWidgets.QCheckBox("Two")
        result = combo.add([cb1, cb2])

        self.assertEqual(len(result), 2)
        self.assertEqual(combo.count(), 2)

    def test_add_with_header(self):
        """Should set header text when provided."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        combo.add(QtWidgets.QCheckBox, header="OPTIONS")

        self.assertEqual(combo.header_text, "OPTIONS")

    def test_add_with_clear_false(self):
        """Should not clear existing items when clear=False."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        combo.add(QtWidgets.QCheckBox("First"))
        combo.add(QtWidgets.QCheckBox("Second"), clear=False)

        self.assertEqual(combo.count(), 2)

    def test_add_string_items(self):
        """Should add string items."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        combo.add(["Item 1", "Item 2", "Item 3"])

        self.assertEqual(combo.count(), 3)

    def test_add_mixed_content(self):
        """Should handle mixed widget and string content."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        checkbox = QtWidgets.QCheckBox("Check")
        combo.add([checkbox, "Text Item"])

        self.assertEqual(combo.count(), 2)


class TestWidgetComboBoxWidgetAccess(QtBaseTestCase):
    """Tests for accessing widgets in WidgetComboBox."""

    def test_widget_at_returns_widget(self):
        """Should return widget at specified row."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        checkbox = QtWidgets.QCheckBox("Test")
        combo.add(checkbox)

        self.assertEqual(combo.widgetAt(0), checkbox)

    def test_widget_at_returns_none_for_invalid_row(self):
        """Should return None for invalid row."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        self.assertIsNone(combo.widgetAt(99))


class TestWidgetComboBoxUniformHeight(QtBaseTestCase):
    """Rows must be uniform height so mixed-widget popups look like a
    standard combobox dropdown rather than a ragged stack."""

    def test_rows_resize_to_max_widget_height(self):
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        # Add a short widget first, then a taller one. The first row must
        # grow to match the taller sizeHint.
        checkbox = QtWidgets.QCheckBox("c")
        combo.add(checkbox)
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        combo.add(slider, clear=False)

        target = max(checkbox.sizeHint().height(), slider.sizeHint().height())
        heights = [
            combo._model.item(r).sizeHint().height()
            for r in range(combo._model.rowCount())
        ]
        self.assertEqual(
            heights, [target, target],
            f"All rows must use uniform height {target}; got {heights}",
        )

    def test_actions_section_does_not_inflate_uniform_height(self):
        """The actions container is multi-button and tall; it must not push
        uniform-height for the selectable rows above it."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        checkbox = QtWidgets.QCheckBox("c")
        combo.add(checkbox)
        baseline = combo._model.item(0).sizeHint().height()

        combo.actions.add("Tall Action Button", lambda: None)
        # The original (selectable) row's height must be unchanged.
        self.assertEqual(
            combo._model.item(0).sizeHint().height(), baseline,
            "Selectable rows must not grow when an actions section is added",
        )


if __name__ == "__main__":
    unittest.main()
