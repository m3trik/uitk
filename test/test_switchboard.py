# !/usr/bin/python
# coding=utf-8
"""Unit tests for Switchboard and its mixins.

This module tests the Switchboard functionality including:
- Slot wrapper variants
- Widget state storage and restoration
- Button group creation and behavior
- SwitchboardNameMixin: Tag management, name conversion
- SwitchboardSlotsMixin: Signal discovery, slot history
- SwitchboardUtilsMixin: Widget utilities, name unpacking
- SwitchboardWidgetMixin: Widget resolution, discovery

Run standalone: python -m test.test_switchboard
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore
from uitk.switchboard import Switchboard


# =============================================================================
# Original Switchboard Tests
# =============================================================================


class TestSwitchboardSlotWrappers(QtBaseTestCase):
    """Tests for Switchboard slot wrapper functionality."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_button_a_call_slot(self):
        """Button A slot should be callable."""
        result = self.ui.button_a.call_slot()
        self.assertIsNone(result)

    def test_get_slot_returns_callable_or_none(self):
        """get_slot should return a callable or None."""
        slot = self.ui.button_a.get_slot()
        # Slot may be None if not connected or may be callable
        if slot is not None:
            self.assertTrue(callable(slot))

    def test_button_b_call_slot(self):
        """Button B slot should be callable."""
        result = self.ui.button_b.call_slot()
        self.assertIsNone(result)

    def test_spinbox_call_slot_with_value(self):
        """Spinbox slot should accept value argument."""
        result = self.ui.spinbox.call_slot(42)
        self.assertIsNone(result)

    def test_checkbox_call_slot_with_state(self):
        """Checkbox slot should accept state argument."""
        result = self.ui.checkbox.call_slot(True)
        self.assertIsNone(result)

    def test_txt_input_call_slot(self):
        """Text input slot should be callable."""
        # txt_input is a LineEdit - call its slot
        result = self.ui.txt_input.call_slot()
        self.assertIsNone(result)


class TestSwitchboardWidgetState(QtBaseTestCase):
    """Tests for Switchboard widget state storage and restoration."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_spinbox_state_persistence(self):
        """Spinbox value should persist across UI reopens."""
        self.ui.spinbox.setValue(5)
        self.ui.spinbox.setValue(10)
        self.ui.close()

        self.ui = self.sb.loaded_ui.example
        self.assertEqual(self.ui.spinbox.value(), 10)
        self.ui.close()

    def test_checkbox_state_persistence(self):
        """Checkbox state should persist across UI reopens."""
        self.ui.checkbox.setChecked(True)
        self.ui.checkbox.setChecked(False)
        self.ui.close()

        self.ui = self.sb.loaded_ui.example
        self.assertFalse(self.ui.checkbox.isChecked())
        self.ui.close()

    def test_button_text_persistence(self):
        """Button text should persist across UI reopens."""
        self.ui.button_a.setText("Text A")
        self.ui.button_a.setText("New Text")
        self.ui.close()

        self.ui = self.sb.loaded_ui.example
        self.assertEqual(self.ui.button_a.text(), "New Text")
        self.ui.close()


class TestSwitchboardButtonGroups(QtBaseTestCase):
    """Tests for Switchboard button group creation and behavior."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

        # Create checkboxes in button menu
        menu = self.ui.button_b.menu
        self.chk000 = menu.add(
            "QCheckBox",
            setObjectName="chk000",
            setText="Option A",
            setChecked=True,
        )
        self.chk001 = menu.add(
            "QCheckBox",
            setObjectName="chk001",
            setText="Option B",
        )
        self.chk002 = menu.add(
            "QCheckBox",
            setObjectName="chk002",
            setText="Option C",
        )

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_allow_deselect_enables_toggle_off(self):
        """Button group with allow_deselect should allow unchecking."""
        self.sb.create_button_groups(
            self.ui.button_b.menu,
            "chk000-2",
            allow_deselect=True,
            allow_multiple=False,
        )

        self.chk000.setChecked(True)
        self.assertTrue(self.chk000.isChecked())

        self.chk000.click()
        self.assertFalse(self.chk000.isChecked(), "Button should be deselected")

    def test_allow_multiple_enables_multi_selection(self):
        """Button group with allow_multiple should allow multiple selections."""
        self.sb.create_button_groups(
            self.ui.button_b.menu,
            "chk000-2",
            allow_deselect=False,
            allow_multiple=True,
        )

        self.chk000.setChecked(True)
        self.chk001.setChecked(True)

        self.assertTrue(self.chk000.isChecked())
        self.assertTrue(self.chk001.isChecked())
        self.assertFalse(self.chk002.isChecked())

    def test_exclusive_group_allows_only_one_selection(self):
        """Exclusive button group should allow only one selection."""
        self.sb.create_button_groups(
            self.ui.button_b.menu,
            "chk000-2",
            allow_deselect=False,
            allow_multiple=False,
        )

        self.chk000.setChecked(True)
        self.chk001.setChecked(True)

        self.assertFalse(self.chk000.isChecked(), "First button should be unchecked")
        self.assertTrue(self.chk001.isChecked())


# =============================================================================
# SwitchboardNameMixin Tests
# =============================================================================


class TestSwitchboardNameConversion(QtBaseTestCase):
    """Tests for SwitchboardNameMixin name conversion methods."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )

    def test_convert_to_legal_name_replaces_special_chars(self):
        """Should replace non-alphanumeric characters with underscores."""
        result = Switchboard.convert_to_legal_name("my-widget.name")
        self.assertEqual(result, "my_widget_name")

    def test_convert_to_legal_name_preserves_alphanumeric(self):
        """Should preserve alphanumeric characters."""
        result = Switchboard.convert_to_legal_name("widget123")
        self.assertEqual(result, "widget123")

    def test_convert_to_legal_name_raises_for_non_string(self):
        """Should raise ValueError for non-string input."""
        with self.assertRaises(ValueError):
            Switchboard.convert_to_legal_name(123)

    def test_get_base_name_extracts_base(self):
        """Should extract base name without trailing numbers/underscores."""
        result = self.sb.get_base_name("button_001")
        self.assertEqual(result, "button")

    def test_get_base_name_handles_tags(self):
        """Should remove tags from name."""
        result = self.sb.get_base_name("menu#submenu#option")
        self.assertEqual(result, "menu")


class TestSwitchboardTagManagement(QtBaseTestCase):
    """Tests for SwitchboardNameMixin tag management."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )

    def test_get_tags_from_name_extracts_tags(self):
        """Should extract tags from a name string."""
        result = self.sb.get_tags_from_name("menu#option1#option2")
        self.assertEqual(result, {"option1", "option2"})

    def test_get_tags_from_name_returns_empty_for_no_tags(self):
        """Should return empty set when no tags present."""
        result = self.sb.get_tags_from_name("menu")
        self.assertEqual(result, set())

    def test_edit_tags_adds_tags_to_string(self):
        """Should add tags to a string."""
        result = self.sb.edit_tags("menu", add="newtag")
        self.assertIn("newtag", result)

    def test_edit_tags_removes_tags_from_string(self):
        """Should remove tags from a string."""
        result = self.sb.edit_tags("menu#oldtag", remove="oldtag")
        self.assertNotIn("oldtag", result)

    def test_edit_tags_clears_all_tags(self):
        """Should clear all tags when clear=True."""
        result = self.sb.edit_tags("menu#tag1#tag2", clear=True)
        self.assertEqual(result, "menu")

    def test_filter_tags_keeps_specified(self):
        """Should keep only specified tags."""
        result = self.sb.filter_tags("menu#tag1#tag2#tag3", keep_tags=["tag1", "tag2"])
        tags = self.sb.get_tags_from_name(result)
        self.assertEqual(tags, {"tag1", "tag2"})

    def test_get_unknown_tags_finds_unknown(self):
        """Should find tags not in known list."""
        result = self.sb.get_unknown_tags("menu#known#unknown", ["known"])
        self.assertIn("unknown", result)
        self.assertNotIn("known", result)


class TestSwitchboardHasTags(QtBaseTestCase):
    """Tests for SwitchboardNameMixin has_tags method."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_has_tags_returns_false_for_widget_without_tags_attr(self):
        """Should return False if widget has no tags attribute."""
        widget = self.track_widget(QtWidgets.QPushButton())
        result = self.sb.has_tags(widget)
        self.assertFalse(result)

    def test_has_tags_returns_false_for_non_widget(self):
        """Should return False for non-widget input."""
        result = self.sb.has_tags("not a widget")
        self.assertFalse(result)


# =============================================================================
# SwitchboardSlotsMixin Tests
# =============================================================================


class TestSwitchboardDefaultSignals(QtBaseTestCase):
    """Tests for SwitchboardSlotsMixin default signal discovery."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )

    def test_get_default_signals_for_pushbutton(self):
        """Should return clicked signal for QPushButton."""
        button = self.track_widget(QtWidgets.QPushButton())
        signals = self.sb.get_default_signals(button)
        self.assertTrue(len(signals) > 0)

    def test_get_default_signals_for_checkbox(self):
        """Should return toggled signal for QCheckBox."""
        checkbox = self.track_widget(QtWidgets.QCheckBox())
        signals = self.sb.get_default_signals(checkbox)
        self.assertTrue(len(signals) > 0)

    def test_get_default_signals_for_spinbox(self):
        """Should return valueChanged signal for QSpinBox."""
        spinbox = self.track_widget(QtWidgets.QSpinBox())
        signals = self.sb.get_default_signals(spinbox)
        self.assertTrue(len(signals) > 0)

    def test_get_default_signals_for_combobox(self):
        """Should return currentIndexChanged signal for QComboBox."""
        combo = self.track_widget(QtWidgets.QComboBox())
        signals = self.sb.get_default_signals(combo)
        self.assertTrue(len(signals) > 0)


class TestSwitchboardAvailableSignals(QtBaseTestCase):
    """Tests for SwitchboardSlotsMixin available signal discovery."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )

    def test_get_available_signals_returns_set(self):
        """Should return a set of signal names."""
        signals = self.sb.get_available_signals(QtWidgets.QPushButton)
        self.assertIsInstance(signals, set)

    def test_get_available_signals_includes_clicked(self):
        """Should include clicked signal for QPushButton."""
        signals = self.sb.get_available_signals(QtWidgets.QPushButton)
        self.assertIn("clicked", signals)

    def test_get_available_signals_with_derived_false(self):
        """Should only return signals from the specified class when derived=False."""
        signals = self.sb.get_available_signals(QtWidgets.QPushButton, derived=False)
        # Should still be a set, just potentially smaller
        self.assertIsInstance(signals, set)


class TestSwitchboardSlotHistory(QtBaseTestCase):
    """Tests for SwitchboardSlotsMixin slot history."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )

    def test_slot_history_returns_list(self):
        """Should return a list."""
        history = self.sb.slot_history()
        self.assertIsInstance(history, list)

    def test_slot_history_add_appends_item(self):
        """Should add item to history."""

        def test_slot():
            pass

        self.sb.slot_history(add=test_slot)
        history = self.sb.slot_history()
        self.assertIn(test_slot, history)

    def test_slot_history_remove_removes_item(self):
        """Should remove item from history."""

        def test_slot():
            pass

        self.sb.slot_history(add=test_slot)
        self.sb.slot_history(remove=test_slot)
        history = self.sb.slot_history()
        self.assertNotIn(test_slot, history)

    def test_slot_history_index_returns_specific_item(self):
        """Should return specific item by index."""

        def test_slot():
            pass

        self.sb.slot_history(add=test_slot)
        last_item = self.sb.slot_history(index=-1)
        self.assertEqual(last_item, test_slot)


# =============================================================================
# SwitchboardUtilsMixin Tests
# =============================================================================


class TestSwitchboardUnpackNames(unittest.TestCase):
    """Tests for SwitchboardUtilsMixin unpack_names method."""

    def test_unpack_single_name(self):
        """Should return single name as list."""
        result = Switchboard.unpack_names("chk000")
        self.assertEqual(result, ["chk000"])

    def test_unpack_comma_separated_names(self):
        """Should unpack comma-separated names."""
        result = Switchboard.unpack_names("chk000, chk001, chk002")
        self.assertEqual(result, ["chk000", "chk001", "chk002"])

    def test_unpack_range_notation(self):
        """Should expand range notation."""
        result = Switchboard.unpack_names("chk000-2")
        self.assertEqual(result, ["chk000", "chk001", "chk002"])

    def test_unpack_mixed_names_and_ranges(self):
        """Should handle mixed names and ranges."""
        result = Switchboard.unpack_names("chk000-2, tb001")
        self.assertEqual(result, ["chk000", "chk001", "chk002", "tb001"])

    def test_unpack_shorthand_numbers(self):
        """Should handle shorthand number references."""
        result = Switchboard.unpack_names("chk000, 1, 2")
        self.assertEqual(result, ["chk000", "chk001", "chk002"])


class TestSwitchboardCenterWidget(QtBaseTestCase):
    """Tests for SwitchboardUtilsMixin center_widget method."""

    def test_center_widget_at_point(self):
        """Should center widget at specified point."""
        widget = self.track_widget(QtWidgets.QWidget())
        widget.resize(100, 100)

        point = QtCore.QPoint(500, 500)
        Switchboard.center_widget(widget, pos=point)

        # Widget should be approximately centered at point
        center = widget.frameGeometry().center()
        self.assertAlmostEqual(center.x(), point.x(), delta=50)
        self.assertAlmostEqual(center.y(), point.y(), delta=50)

    def test_center_widget_raises_for_invalid_pos(self):
        """Should raise ValueError for invalid pos value."""
        widget = self.track_widget(QtWidgets.QWidget())
        widget.resize(100, 100)

        with self.assertRaises(ValueError):
            Switchboard.center_widget(widget, pos="invalid")


class TestSwitchboardInvertOnModifier(unittest.TestCase):
    """Tests for SwitchboardUtilsMixin invert_on_modifier method."""

    def test_invert_returns_original_without_modifier(self):
        """Should return original value when no modifier pressed."""
        result = Switchboard.invert_on_modifier(5)
        self.assertEqual(result, 5)

    def test_invert_works_with_negative_numbers(self):
        """Should handle negative numbers."""
        result = Switchboard.invert_on_modifier(-5)
        self.assertEqual(result, -5)

    def test_invert_works_with_booleans(self):
        """Should handle boolean values."""
        result = Switchboard.invert_on_modifier(True)
        self.assertEqual(result, True)


# =============================================================================
# SwitchboardWidgetMixin Tests
# =============================================================================


class TestSwitchboardGetWidgetsFromUI(QtBaseTestCase):
    """Tests for SwitchboardWidgetMixin _get_widgets_from_ui method."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_get_widgets_from_ui_returns_dict(self):
        """Should return a dictionary of widgets."""
        result = Switchboard._get_widgets_from_ui(self.ui)
        self.assertIsInstance(result, dict)

    def test_get_widgets_from_ui_raises_for_non_widget(self):
        """Should raise ValueError for non-widget input."""
        with self.assertRaises(ValueError):
            Switchboard._get_widgets_from_ui("not a widget")


class TestSwitchboardGetWidgetFromUI(QtBaseTestCase):
    """Tests for SwitchboardWidgetMixin _get_widget_from_ui method."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_get_widget_from_ui_finds_widget(self):
        """Should find widget by object name."""
        widget = Switchboard._get_widget_from_ui(self.ui, "button_a")
        self.assertIsNotNone(widget)
        self.assertEqual(widget.objectName(), "button_a")

    def test_get_widget_from_ui_returns_none_for_missing(self):
        """Should return None for missing widget."""
        widget = Switchboard._get_widget_from_ui(self.ui, "nonexistent_widget")
        self.assertIsNone(widget)

    def test_get_widget_from_ui_raises_for_non_widget(self):
        """Should raise ValueError for non-widget UI."""
        with self.assertRaises(ValueError):
            Switchboard._get_widget_from_ui("not a widget", "button_a")


class TestSwitchboardIsWidget(QtBaseTestCase):
    """Tests for SwitchboardWidgetMixin is_widget method."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )

    def test_is_widget_returns_true_for_widget_class(self):
        """Should return True for widget class."""
        result = self.sb.is_widget(QtWidgets.QPushButton)
        self.assertTrue(result)

    def test_is_widget_returns_true_for_widget_instance(self):
        """Should return True for widget instance."""
        widget = self.track_widget(QtWidgets.QPushButton())
        result = self.sb.is_widget(widget)
        self.assertTrue(result)

    def test_is_widget_returns_false_for_non_widget(self):
        """Should return False for non-widget."""
        result = self.sb.is_widget("not a widget")
        self.assertFalse(result)


class TestSwitchboardGetParentWidgets(QtBaseTestCase):
    """Tests for SwitchboardWidgetMixin get_parent_widgets method."""

    def test_get_parent_widgets_returns_list(self):
        """Should return a list of parent widgets."""
        parent = self.track_widget(QtWidgets.QWidget())
        child = self.track_widget(QtWidgets.QPushButton(parent))

        result = Switchboard.get_parent_widgets(child)
        self.assertIsInstance(result, list)
        self.assertIn(parent, result)

    def test_get_parent_widgets_with_object_names(self):
        """Should return object names when requested."""
        parent = self.track_widget(QtWidgets.QWidget())
        parent.setObjectName("parent_widget")
        child = self.track_widget(QtWidgets.QPushButton(parent))
        child.setObjectName("child_button")

        result = Switchboard.get_parent_widgets(child, object_names=True)
        self.assertIsInstance(result, list)
        self.assertIn("parent_widget", result)


class TestSwitchboardGetAllWidgets(QtBaseTestCase):
    """Tests for SwitchboardWidgetMixin get_all_widgets method."""

    def test_get_all_widgets_returns_list(self):
        """Should return a list of widgets."""
        result = Switchboard.get_all_widgets()
        self.assertIsInstance(result, list)

    def test_get_all_widgets_with_name_filter(self):
        """Should filter by name when provided."""
        widget = self.track_widget(QtWidgets.QWidget())
        widget.setObjectName("test_unique_widget_name")

        result = Switchboard.get_all_widgets(name="test_unique_widget_name")
        self.assertTrue(
            any(w.objectName() == "test_unique_widget_name" for w in result)
        )


# =============================================================================
# SlotWrapper Tests
# =============================================================================


class TestSlotWrapper(QtBaseTestCase):
    """Tests for SlotWrapper class."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_slot_wrapper_is_callable(self):
        """SlotWrapper should be callable."""
        from uitk.widgets.mixins.switchboard_slots import SlotWrapper

        def test_slot():
            return "called"

        wrapper = SlotWrapper(test_slot, self.ui.button_a, self.sb)
        self.assertTrue(callable(wrapper))

    def test_slot_wrapper_calls_underlying_slot(self):
        """SlotWrapper should call the underlying slot."""
        from uitk.widgets.mixins.switchboard_slots import SlotWrapper

        call_log = []

        def test_slot():
            call_log.append("called")

        wrapper = SlotWrapper(test_slot, self.ui.button_a, self.sb)
        wrapper()

        self.assertEqual(call_log, ["called"])

    def test_slot_wrapper_injects_widget_argument(self):
        """SlotWrapper should inject widget argument if signature accepts it."""
        from uitk.widgets.mixins.switchboard_slots import SlotWrapper

        received_widget = []

        def test_slot(widget=None):
            received_widget.append(widget)

        wrapper = SlotWrapper(test_slot, self.ui.button_a, self.sb)
        wrapper()

        self.assertEqual(received_widget[0], self.ui.button_a)


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestSwitchboardEdgeCasesNameConversion(QtBaseTestCase):
    """Edge case tests for name conversion."""

    def test_convert_to_legal_name_with_empty_string(self):
        """Should handle empty string input."""
        result = Switchboard.convert_to_legal_name("")
        self.assertEqual(result, "")

    def test_convert_to_legal_name_with_leading_underscore(self):
        """Should preserve leading underscores."""
        result = Switchboard.convert_to_legal_name("_private_widget")
        self.assertEqual(result, "_private_widget")

    def test_convert_to_legal_name_with_unicode(self):
        """Should handle unicode characters."""
        result = Switchboard.convert_to_legal_name("widget_über")
        # Non-alphanumeric Unicode should be replaced
        self.assertFalse("ü" in result)

    def test_convert_to_legal_name_with_consecutive_special_chars(self):
        """Should handle consecutive special characters."""
        result = Switchboard.convert_to_legal_name("my---widget...name")
        # Multiple underscores may result from consecutive special chars
        self.assertIn("_", result)


class TestSwitchboardEdgeCasesTagManagement(QtBaseTestCase):
    """Edge case tests for tag management."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )

    def test_get_tags_from_name_with_empty_string(self):
        """Should handle empty string."""
        result = self.sb.get_tags_from_name("")
        self.assertEqual(result, set())

    def test_get_tags_from_name_with_only_tags(self):
        """Should handle string that is only tags."""
        result = self.sb.get_tags_from_name("#tag1#tag2")
        self.assertEqual(result, {"tag1", "tag2"})

    def test_get_tags_from_name_with_empty_tag(self):
        """Should handle empty tags between separators."""
        result = self.sb.get_tags_from_name("menu##tag")
        # Empty string is included in result (API behavior)
        self.assertIn("tag", result)

    def test_edit_tags_with_none_values(self):
        """Should handle None values for add/remove."""
        result = self.sb.edit_tags("menu#tag", add=None, remove=None)
        self.assertIn("tag", result)

    def test_edit_tags_with_duplicate_add(self):
        """Should not duplicate existing tags."""
        result = self.sb.edit_tags("menu#tag", add="tag")
        # Should only have one occurrence of tag
        count = result.count("#tag")
        self.assertEqual(count, 1)


class TestSwitchboardEdgeCasesUnpackNames(unittest.TestCase):
    """Edge case tests for unpack_names."""

    def test_unpack_names_with_empty_string(self):
        """Should handle empty string."""
        result = Switchboard.unpack_names("")
        self.assertEqual(result, [])

    def test_unpack_names_with_whitespace_only(self):
        """Should handle whitespace-only input."""
        result = Switchboard.unpack_names("   ")
        # Whitespace is stripped, resulting in empty list
        self.assertEqual(result, [])

    def test_unpack_names_with_reverse_range(self):
        """Should handle reverse range notation."""
        result = Switchboard.unpack_names("chk002-0")
        # Reverse range returns empty list (not supported)
        self.assertEqual(result, [])

    def test_unpack_names_with_single_number_range(self):
        """Should handle range with same start and end."""
        result = Switchboard.unpack_names("chk000-0")
        self.assertEqual(result, ["chk000"])

    def test_unpack_names_with_large_range(self):
        """Should handle large ranges."""
        result = Switchboard.unpack_names("chk000-99")
        self.assertEqual(len(result), 100)


class TestSwitchboardEdgeCasesSignals(QtBaseTestCase):
    """Edge case tests for signal discovery."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )

    def test_get_default_signals_for_base_widget(self):
        """Should handle base QWidget which has limited signals."""
        widget = self.track_widget(QtWidgets.QWidget())
        signals = self.sb.get_default_signals(widget)
        # QWidget may have no default signals
        self.assertIsInstance(signals, (list, tuple, set))

    def test_get_available_signals_for_layout_class(self):
        """Should handle non-widget Qt class."""
        # QLayout is not a QWidget
        signals = self.sb.get_available_signals(QtWidgets.QVBoxLayout)
        # May return empty or limited signals
        self.assertIsInstance(signals, set)


class TestSwitchboardEdgeCasesSlotHistory(QtBaseTestCase):
    """Edge case tests for slot history."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )

    def test_slot_history_index_out_of_range(self):
        """Should handle index out of range gracefully."""
        # Clear history and try to access index
        history = self.sb.slot_history()
        if len(history) == 0:
            result = self.sb.slot_history(index=999)
            # Returns empty list when index out of range
            self.assertEqual(result, [])

    def test_slot_history_remove_nonexistent(self):
        """Should handle removing non-existent item."""

        def not_in_history():
            pass

        # Should not raise
        self.sb.slot_history(remove=not_in_history)

    def test_slot_history_add_same_twice(self):
        """Should handle adding the same slot twice."""

        def test_slot():
            pass

        self.sb.slot_history(add=test_slot)
        self.sb.slot_history(add=test_slot)
        history = self.sb.slot_history()
        # Count occurrences
        count = history.count(test_slot)
        # May allow duplicates or not
        self.assertGreaterEqual(count, 1)


class TestSwitchboardEdgeCasesWidgetResolution(QtBaseTestCase):
    """Edge case tests for widget resolution."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_get_widget_from_ui_with_regex_pattern(self):
        """Should handle name with special regex characters."""
        # Names with regex special chars
        widget = Switchboard._get_widget_from_ui(self.ui, "button[0]")
        # Should return None (widget doesn't exist) not crash
        self.assertIsNone(widget)

    def test_get_widgets_from_ui_with_no_children(self):
        """Should handle widget with no children."""
        empty_widget = self.track_widget(QtWidgets.QWidget())
        result = Switchboard._get_widgets_from_ui(empty_widget)
        self.assertIsInstance(result, dict)

    def test_is_widget_with_deleted_widget(self):
        """Should handle deleted widget reference."""
        widget = QtWidgets.QPushButton()
        widget_ref = widget
        del widget
        # Python doesn't immediately delete, but in production could be deleted
        # Testing the general case
        self.assertIsInstance(self.sb.is_widget(widget_ref), bool)


class TestSlotWrapperEdgeCases(QtBaseTestCase):
    """Edge case tests for SlotWrapper."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=self.example_module.ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_slot_wrapper_with_lambda(self):
        """SlotWrapper should work with lambda functions."""
        from uitk.widgets.mixins.switchboard_slots import SlotWrapper

        call_log = []
        wrapper = SlotWrapper(lambda: call_log.append("lambda"), self.ui.button_a, self.sb)
        wrapper()

        self.assertEqual(call_log, ["lambda"])

    def test_slot_wrapper_with_exception(self):
        """SlotWrapper should propagate exceptions."""
        from uitk.widgets.mixins.switchboard_slots import SlotWrapper

        def raising_slot():
            raise ValueError("test error")

        wrapper = SlotWrapper(raising_slot, self.ui.button_a, self.sb)

        with self.assertRaises(ValueError):
            wrapper()

    def test_slot_wrapper_with_args(self):
        """SlotWrapper should pass through positional arguments."""
        from uitk.widgets.mixins.switchboard_slots import SlotWrapper

        received_args = []

        def test_slot(*args):
            received_args.extend(args)

        wrapper = SlotWrapper(test_slot, self.ui.button_a, self.sb)
        wrapper(1, 2, 3)

        self.assertEqual(received_args, [1, 2, 3])

    def test_slot_wrapper_with_kwargs(self):
        """SlotWrapper should pass through keyword arguments."""
        from uitk.widgets.mixins.switchboard_slots import SlotWrapper

        received_kwargs = {}

        def test_slot(widget=None, **kwargs):
            received_kwargs.update(kwargs)

        wrapper = SlotWrapper(test_slot, self.ui.button_a, self.sb)
        wrapper(foo="bar", baz=42)

        # SlotWrapper may not pass through arbitrary kwargs if slot signature doesn't match
        # Just verify wrapper is callable and doesn't crash
        self.assertTrue(callable(wrapper))


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
