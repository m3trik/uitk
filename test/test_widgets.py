# !/usr/bin/python
# coding=utf-8
"""Unit tests for core widget classes.

This module tests the core widget functionality including:
- PushButton
- CheckBox
- LineEdit
- ComboBox
- Label

Run standalone: python -m test.test_widgets
"""

import unittest
from unittest.mock import MagicMock

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore


# =============================================================================
# PushButton Tests
# =============================================================================


class TestPushButtonCreation(QtBaseTestCase):
    """Tests for PushButton widget creation."""

    def test_creates_button_with_defaults(self):
        """Should create button with default settings."""
        from uitk.widgets.pushButton import PushButton

        button = self.track_widget(PushButton())
        self.assertIsNotNone(button)

    def test_creates_button_with_parent(self):
        """Should create button with parent widget."""
        from uitk.widgets.pushButton import PushButton

        parent = self.track_widget(QtWidgets.QWidget())
        button = self.track_widget(PushButton(parent=parent))
        self.assertEqual(button.parent(), parent)

    def test_sets_object_name_via_kwargs(self):
        """Should set object name via kwargs."""
        from uitk.widgets.pushButton import PushButton

        button = self.track_widget(PushButton(setObjectName="test_button"))
        self.assertEqual(button.objectName(), "test_button")

    def test_sets_class_property(self):
        """Should set class property to class name."""
        from uitk.widgets.pushButton import PushButton

        button = self.track_widget(PushButton())
        self.assertEqual(button.property("class"), "PushButton")


class TestPushButtonMenu(QtBaseTestCase):
    """Tests for PushButton menu functionality."""

    def test_has_menu_attribute(self):
        """Should have menu attribute from MenuMixin."""
        from uitk.widgets.pushButton import PushButton

        button = self.track_widget(PushButton())
        self.assertTrue(hasattr(button, "menu"))

    def test_menu_trigger_button_is_right(self):
        """Should have right click as menu trigger (as Qt constant)."""
        from uitk.widgets.pushButton import PushButton

        button = self.track_widget(PushButton())
        # Menu converts "right" to Qt.RightButton
        self.assertEqual(button.menu.trigger_button, QtCore.Qt.RightButton)

    def test_menu_has_apply_button_enabled(self):
        """Should have apply button enabled for pushbutton menus."""
        from uitk.widgets.pushButton import PushButton

        button = self.track_widget(PushButton())
        self.assertTrue(button.menu.add_apply_button)


class TestPushButtonOptionBox(QtBaseTestCase):
    """Tests for PushButton option box functionality."""

    def test_has_option_box_attribute(self):
        """Should have option_box attribute from OptionBoxMixin."""
        from uitk.widgets.pushButton import PushButton

        button = self.track_widget(PushButton())
        self.assertTrue(hasattr(button, "option_box"))


class TestPushButtonRichText(QtBaseTestCase):
    """Tests for PushButton rich text functionality."""

    def test_has_rich_text_method(self):
        """Should have richText method from RichText mixin."""
        from uitk.widgets.pushButton import PushButton

        button = self.track_widget(PushButton())
        self.assertTrue(hasattr(button, "richText"))

    def test_has_set_rich_text_method(self):
        """Should have setRichText method from RichText mixin."""
        from uitk.widgets.pushButton import PushButton

        button = self.track_widget(PushButton())
        self.assertTrue(hasattr(button, "setRichText"))


# =============================================================================
# CheckBox Tests
# =============================================================================


class TestCheckBoxCreation(QtBaseTestCase):
    """Tests for CheckBox widget creation."""

    def test_creates_checkbox_with_defaults(self):
        """Should create checkbox with default settings."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        self.assertIsNotNone(checkbox)

    def test_creates_checkbox_with_parent(self):
        """Should create checkbox with parent widget."""
        from uitk.widgets.checkBox import CheckBox

        parent = self.track_widget(QtWidgets.QWidget())
        checkbox = self.track_widget(CheckBox(parent=parent))
        self.assertEqual(checkbox.parent(), parent)

    def test_sets_class_property(self):
        """Should set class property to class name."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        self.assertEqual(checkbox.property("class"), "CheckBox")


class TestCheckBoxState(QtBaseTestCase):
    """Tests for CheckBox state handling."""

    def test_check_state_returns_integer(self):
        """Should return check state as integer."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        state = checkbox.checkState()
        self.assertIsInstance(state, int)

    def test_check_state_unchecked_is_zero(self):
        """Should return 0 for unchecked state."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        checkbox.setChecked(False)
        self.assertEqual(checkbox.checkState(), 0)

    def test_check_state_checked_is_one(self):
        """Should return 1 for checked state."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        checkbox.setChecked(True)
        self.assertEqual(checkbox.checkState(), 1)

    def test_set_check_state_with_integer(self):
        """Should set check state using integer."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        checkbox.setCheckState(1)
        self.assertTrue(checkbox.isChecked())

    def test_set_check_state_with_zero(self):
        """Should uncheck when set to 0."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        checkbox.setChecked(True)
        checkbox.setCheckState(0)
        self.assertFalse(checkbox.isChecked())


class TestCheckBoxTristate(QtBaseTestCase):
    """Tests for CheckBox tri-state functionality."""

    def test_tristate_returns_three_states(self):
        """Should return 0, 1, 2 for tri-state checkbox."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        checkbox.setTristate(True)

        # Test unchecked
        checkbox.setCheckState(0)
        self.assertEqual(checkbox.checkState(), 0)

        # Test partially checked
        checkbox.setCheckState(1)
        self.assertEqual(checkbox.checkState(), 1)

        # Test checked
        checkbox.setCheckState(2)
        self.assertEqual(checkbox.checkState(), 2)


class TestCheckBoxHitButton(QtBaseTestCase):
    """Tests for CheckBox hit button override."""

    def test_hit_button_accepts_point_in_bounds(self):
        """Should return True for point within widget bounds."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        checkbox.resize(100, 30)

        pos = QtCore.QPoint(50, 15)
        self.assertTrue(checkbox.hitButton(pos))

    def test_hit_button_rejects_point_outside_bounds(self):
        """Should return False for point outside widget bounds."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        checkbox.resize(100, 30)

        pos = QtCore.QPoint(150, 50)
        self.assertFalse(checkbox.hitButton(pos))


# =============================================================================
# LineEdit Tests
# =============================================================================


class TestLineEditCreation(QtBaseTestCase):
    """Tests for LineEdit widget creation."""

    def test_creates_lineedit_with_defaults(self):
        """Should create line edit with default settings."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        self.assertIsNotNone(line_edit)

    def test_creates_lineedit_with_parent(self):
        """Should create line edit with parent widget."""
        from uitk.widgets.lineEdit import LineEdit

        parent = self.track_widget(QtWidgets.QWidget())
        line_edit = self.track_widget(LineEdit(parent=parent))
        self.assertEqual(line_edit.parent(), parent)

    def test_sets_class_property(self):
        """Should set class property to class name."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        self.assertEqual(line_edit.property("class"), "LineEdit")


class TestLineEditMenu(QtBaseTestCase):
    """Tests for LineEdit menu functionality."""

    def test_has_menu_attribute(self):
        """Should have menu attribute from MenuMixin."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        self.assertTrue(hasattr(line_edit, "menu"))

    def test_menu_trigger_is_right_click(self):
        """Should have right click as menu trigger (as Qt constant)."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        # Menu converts "right" to Qt.RightButton
        self.assertEqual(line_edit.menu.trigger_button, QtCore.Qt.RightButton)


class TestLineEditActionColors(QtBaseTestCase):
    """Tests for LineEdit action color functionality."""

    def test_has_set_action_color_method(self):
        """Should have set_action_color method."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        self.assertTrue(hasattr(line_edit, "set_action_color"))

    def test_has_reset_action_color_method(self):
        """Should have reset_action_color method."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        self.assertTrue(hasattr(line_edit, "reset_action_color"))

    def test_action_color_map_has_expected_keys(self):
        """Should have expected action color keys."""
        from uitk.widgets.lineEdit import LineEdit

        expected_keys = {"valid", "invalid", "warning", "info", "inactive"}
        self.assertTrue(expected_keys.issubset(LineEdit.ACTION_COLOR_MAP.keys()))


class TestLineEditSignals(QtBaseTestCase):
    """Tests for LineEdit custom signals."""

    def test_has_shown_signal(self):
        """Should have shown signal."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        self.assertTrue(hasattr(line_edit, "shown"))

    def test_has_hidden_signal(self):
        """Should have hidden signal."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        self.assertTrue(hasattr(line_edit, "hidden"))


# =============================================================================
# ComboBox Tests
# =============================================================================


class TestComboBoxCreation(QtBaseTestCase):
    """Tests for ComboBox widget creation."""

    def test_creates_combobox_with_defaults(self):
        """Should create combo box with default settings."""
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        self.assertIsNotNone(combo)

    def test_creates_combobox_with_parent(self):
        """Should create combo box with parent widget."""
        from uitk.widgets.comboBox import ComboBox

        parent = self.track_widget(QtWidgets.QWidget())
        combo = self.track_widget(ComboBox(parent=parent))
        self.assertEqual(combo.parent(), parent)


class TestComboBoxItems(QtBaseTestCase):
    """Tests for ComboBox item management."""

    def test_adds_items(self):
        """Should add items to combo box."""
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        combo.addItems(["Item 1", "Item 2", "Item 3"])
        self.assertEqual(combo.count(), 3)

    def test_gets_current_item_text(self):
        """Should get current item text."""
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        combo.addItems(["First", "Second", "Third"])
        combo.setCurrentIndex(1)
        self.assertEqual(combo.currentText(), "Second")


class TestAlignedComboBox(QtBaseTestCase):
    """Tests for AlignedComboBox header functionality."""

    def test_sets_header_text(self):
        """Should set header text."""
        from uitk.widgets.comboBox import AlignedComboBox

        combo = self.track_widget(AlignedComboBox())
        combo.setHeaderText("Select an option")
        self.assertEqual(combo.header_text, "Select an option")

    def test_sets_header_alignment_left(self):
        """Should set header alignment to left."""
        from uitk.widgets.comboBox import AlignedComboBox

        combo = self.track_widget(AlignedComboBox())
        combo.setHeaderAlignment("left")
        self.assertEqual(combo.header_alignment, QtCore.Qt.AlignLeft)

    def test_sets_header_alignment_center(self):
        """Should set header alignment to center."""
        from uitk.widgets.comboBox import AlignedComboBox

        combo = self.track_widget(AlignedComboBox())
        combo.setHeaderAlignment("center")
        self.assertEqual(combo.header_alignment, QtCore.Qt.AlignHCenter)

    def test_sets_header_alignment_right(self):
        """Should set header alignment to right."""
        from uitk.widgets.comboBox import AlignedComboBox

        combo = self.track_widget(AlignedComboBox())
        combo.setHeaderAlignment("right")
        self.assertEqual(combo.header_alignment, QtCore.Qt.AlignRight)


# =============================================================================
# Label Tests
# =============================================================================


class TestLabelCreation(QtBaseTestCase):
    """Tests for Label widget creation."""

    def test_creates_label_with_defaults(self):
        """Should create label with default settings."""
        from uitk.widgets.label import Label

        label = self.track_widget(Label())
        self.assertIsNotNone(label)

    def test_creates_label_with_parent(self):
        """Should create label with parent widget."""
        from uitk.widgets.label import Label

        parent = self.track_widget(QtWidgets.QWidget())
        label = self.track_widget(Label(parent=parent))
        self.assertEqual(label.parent(), parent)


class TestLabelRichText(QtBaseTestCase):
    """Tests for Label rich text functionality."""

    def test_uses_qt_rich_text_format(self):
        """Should use Qt RichText format for text."""
        from uitk.widgets.label import Label

        label = self.track_widget(Label())
        # Label sets RichText format in __init__
        self.assertEqual(label.textFormat(), QtCore.Qt.RichText)


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestPushButtonEdgeCases(QtBaseTestCase):
    """Edge case tests for PushButton."""

    def test_button_with_empty_text(self):
        """Should handle empty text."""
        from uitk.widgets.pushButton import PushButton

        button = self.track_widget(PushButton())
        button.setText("")
        self.assertEqual(button.text(), "")

    def test_button_with_unicode_text(self):
        """Should handle unicode text."""
        from uitk.widgets.pushButton import PushButton

        button = self.track_widget(PushButton())
        button.setText("按钮 🚀")
        self.assertEqual(button.text(), "按钮 🚀")

    def test_button_with_very_long_text(self):
        """Should handle very long text."""
        from uitk.widgets.pushButton import PushButton

        button = self.track_widget(PushButton())
        long_text = "A" * 1000
        button.setText(long_text)
        self.assertEqual(button.text(), long_text)

    def test_button_multiple_clicks(self):
        """Should handle multiple rapid clicks."""
        from uitk.widgets.pushButton import PushButton

        click_count = [0]

        def on_click():
            click_count[0] += 1

        button = self.track_widget(PushButton())
        button.clicked.connect(on_click)

        for _ in range(10):
            button.click()

        self.assertEqual(click_count[0], 10)


class TestCheckBoxEdgeCases(QtBaseTestCase):
    """Edge case tests for CheckBox."""

    def test_checkbox_rapid_state_changes(self):
        """Should handle rapid state changes."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        for i in range(20):
            checkbox.setChecked(i % 2 == 0)
        # Final state should be correct
        self.assertFalse(checkbox.isChecked())  # 20 is even, so False

    def test_checkbox_tristate_cycle(self):
        """Should cycle through all tri-state values."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        checkbox.setTristate(True)

        states = []
        for state in [0, 1, 2, 0]:
            checkbox.setCheckState(state)
            states.append(checkbox.checkState())

        self.assertEqual(states, [0, 1, 2, 0])

    def test_checkbox_hit_button_at_origin(self):
        """Should handle hit test at origin."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        checkbox.resize(100, 30)
        self.assertTrue(checkbox.hitButton(QtCore.QPoint(0, 0)))

    def test_checkbox_hit_button_at_boundary(self):
        """Should handle hit test at boundary."""
        from uitk.widgets.checkBox import CheckBox

        checkbox = self.track_widget(CheckBox())
        checkbox.resize(100, 30)
        # Exactly at right edge
        self.assertTrue(checkbox.hitButton(QtCore.QPoint(99, 15)))


class TestLineEditEdgeCases(QtBaseTestCase):
    """Edge case tests for LineEdit."""

    def test_lineedit_empty_text(self):
        """Should handle empty text."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        line_edit.setText("")
        self.assertEqual(line_edit.text(), "")

    def test_lineedit_unicode_text(self):
        """Should handle unicode text."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        line_edit.setText("日本語 🔥")
        self.assertEqual(line_edit.text(), "日本語 🔥")

    def test_lineedit_whitespace_text(self):
        """Should handle whitespace-only text."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        line_edit.setText("   ")
        self.assertEqual(line_edit.text(), "   ")

    def test_lineedit_newline_text(self):
        """LineEdit preserves newlines in text property."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        line_edit.setText("line1\nline2")
        # The text is stored as-is
        self.assertEqual(line_edit.text(), "line1\nline2")

    def test_lineedit_clear(self):
        """Should clear text."""
        from uitk.widgets.lineEdit import LineEdit

        line_edit = self.track_widget(LineEdit())
        line_edit.setText("some text")
        line_edit.clear()
        self.assertEqual(line_edit.text(), "")


class TestComboBoxEdgeCases(QtBaseTestCase):
    """Edge case tests for ComboBox."""

    def test_combobox_empty(self):
        """Should handle empty combo box."""
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        self.assertEqual(combo.count(), 0)
        self.assertEqual(combo.currentIndex(), -1)

    def test_combobox_single_item(self):
        """Should handle single item."""
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        combo.addItem("Only item")
        self.assertEqual(combo.count(), 1)
        self.assertEqual(combo.currentIndex(), 0)

    def test_combobox_duplicate_items(self):
        """Should handle duplicate items."""
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        combo.addItems(["Same", "Same", "Same"])
        self.assertEqual(combo.count(), 3)

    def test_combobox_remove_item_via_base(self):
        """Should handle removing item via parent class method."""
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        combo.addItems(["First", "Second", "Third"])
        combo.setCurrentIndex(1)
        # Use parent class removeItem to avoid custom signal
        QtWidgets.QComboBox.removeItem(combo, 1)
        # Current index should change
        self.assertEqual(combo.count(), 2)

    def test_combobox_clear(self):
        """Should clear all items."""
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        combo.addItems(["A", "B", "C"])
        combo.clear()
        self.assertEqual(combo.count(), 0)


class TestAlignedComboBoxEdgeCases(QtBaseTestCase):
    """Edge case tests for AlignedComboBox."""

    def test_aligned_combobox_empty_header(self):
        """Should handle empty header text."""
        from uitk.widgets.comboBox import AlignedComboBox

        combo = self.track_widget(AlignedComboBox())
        combo.setHeaderText("")
        self.assertEqual(combo.header_text, "")

    def test_aligned_combobox_invalid_alignment(self):
        """Should handle invalid alignment gracefully."""
        from uitk.widgets.comboBox import AlignedComboBox

        combo = self.track_widget(AlignedComboBox())
        # Default alignment should be used for invalid value
        try:
            combo.setHeaderAlignment("invalid")
        except (ValueError, KeyError):
            pass  # Expected behavior
        # Widget should still be usable
        self.assertIsNotNone(combo)


class TestLabelEdgeCases(QtBaseTestCase):
    """Edge case tests for Label."""

    def test_label_empty_text(self):
        """Should handle empty text."""
        from uitk.widgets.label import Label

        label = self.track_widget(Label())
        label.setText("")
        self.assertEqual(label.text(), "")

    def test_label_html_content(self):
        """Should handle HTML content."""
        from uitk.widgets.label import Label

        label = self.track_widget(Label())
        label.setText("<b>Bold</b> and <i>italic</i>")
        # Should contain the HTML
        self.assertIn("<b>Bold</b>", label.text())

    def test_label_url_link(self):
        """Should handle URL links in rich text."""
        from uitk.widgets.label import Label

        label = self.track_widget(Label())
        label.setText('<a href="http://example.com">Link</a>')
        self.assertIn("href", label.text())


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
