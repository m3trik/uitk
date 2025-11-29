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


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
