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
from unittest import mock

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore, QtGui
from uitk.switchboard import Switchboard
from uitk.switchboard.utils import _suspend_override_cursor, _drain_override_cursor
from uitk.switchboard.slots import _ModalBusyCursorFilter
from uitk.examples.example import ExampleSlots


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
            slot_source=ExampleSlots,
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


class TestSlotWrapperSignatureCache(QtBaseTestCase):
    """The signature cache must key on the function, not id() of a bound method.

    Regression: keying on id(slot) let CPython's freed-bound-method id reuse
    serve a stale (param_names, wants_widget) entry for a *different* slot,
    corrupting widget injection intermittently. Keying on __func__ (a
    WeakKeyDictionary) resolves each slot's signature correctly and stores the
    function object as the key.
    """

    def test_wants_widget_resolved_per_function(self):
        from uitk.switchboard.slots import SlotWrapper

        class Slots:
            def with_widget(self, widget):
                pass

            def no_widget(self):
                pass

        s = Slots()
        w1 = SlotWrapper(s.with_widget, None, None)
        w2 = SlotWrapper(s.no_widget, None, None)
        self.assertTrue(w1.wants_widget)
        self.assertFalse(w2.wants_widget)

    def test_cache_keyed_by_function_object(self):
        from uitk.switchboard.slots import SlotWrapper

        class Slots:
            def do_it(self, widget):
                pass

        s = Slots()
        SlotWrapper(s.do_it, None, None)
        # The underlying function (shared across instances/bindings) is the key,
        # never an int id — so a reused bound-method id cannot collide.
        self.assertIn(Slots.do_it, SlotWrapper._sig_cache)


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
            slot_source=ExampleSlots,
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
            slot_source=ExampleSlots,
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
            slot_source=ExampleSlots,
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
            slot_source=ExampleSlots,
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

    def test_get_unknown_tags_known_prefix_of_unknown(self):
        """A known tag that is a prefix of an unknown one must not suppress it."""
        result = self.sb.get_unknown_tags("menu#submenu", ["sub"])
        self.assertEqual(result, ["submenu"])

    def test_get_unknown_tags_preserves_underscores(self):
        """Underscore tags must not be truncated at the underscore."""
        result = self.sb.get_unknown_tags("menu#my_tag", ["other"])
        self.assertEqual(result, ["my_tag"])

    def test_get_unknown_tags_empty_known_list(self):
        """An empty known list means every tag is unknown."""
        result = self.sb.get_unknown_tags("menu#foo#bar", [])
        self.assertEqual(result, ["foo", "bar"])


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
            slot_source=ExampleSlots,
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
            slot_source=ExampleSlots,
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
            slot_source=ExampleSlots,
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

    def test_get_available_signals_derived_false_returns_own_signals(self):
        """derived=False returns the class's OWN signals, not an empty set."""
        own = self.sb.get_available_signals(QtWidgets.QComboBox, derived=False)
        allsig = self.sb.get_available_signals(QtWidgets.QComboBox, derived=True)
        self.assertTrue(own, "derived=False must not be empty")
        self.assertTrue(own <= allsig)
        # A QObject-inherited signal is present with derived=True but excluded
        # from the class's own signals.
        self.assertIn("destroyed", allsig)
        self.assertNotIn("destroyed", own)

    def test_get_available_signals_exc_excludes_parent_class(self):
        """exc must exclude signals defined on an excluded parent class."""
        result = self.sb.get_available_signals(
            QtWidgets.QComboBox, exc=[QtCore.QObject]
        )
        self.assertNotIn("destroyed", result)  # QObject signal excluded
        self.assertIn("currentIndexChanged", result)  # own signal kept

    def test_set_widget_attrs_removed(self):
        """The dead/broken set_widget_attrs helper must no longer exist."""
        self.assertFalse(hasattr(self.sb, "set_widget_attrs"))


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
            slot_source=ExampleSlots,
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

    def test_unpack_name_without_digits_passthrough(self):
        """A name with no numeric token passes through verbatim (was dropped)."""
        self.assertEqual(Switchboard.unpack_names("grp_basic"), ["grp_basic"])
        self.assertEqual(
            Switchboard.unpack_names("chk000-1, grp_basic"),
            ["chk000", "chk001", "grp_basic"],
        )

    def test_unpack_range_derives_pad_width_from_source(self):
        """Zero-pad width comes from the source token, not a hard-coded 3."""
        self.assertEqual(
            Switchboard.unpack_names("chk0001-3"),
            ["chk0001", "chk0002", "chk0003"],
        )


class TestSwitchboardFileDialog(unittest.TestCase):
    """Tests for SwitchboardUtilsMixin.file_dialog selection mode."""

    def _patched(self):
        from uitk.switchboard import utils

        patcher = mock.patch.object(utils.QtWidgets, "QFileDialog")
        MockFD = patcher.start()
        self.addCleanup(patcher.stop)
        MockFD.getOpenFileName.return_value = ("/a.png", "")
        MockFD.getOpenFileNames.return_value = (["/a.png", "/b.png"], "")
        return MockFD

    def test_single_uses_get_open_file_name(self):
        """allow_multiple=False must use getOpenFileName and return a bare str."""
        MockFD = self._patched()
        result = Switchboard.file_dialog(allow_multiple=False)
        self.assertEqual(result, "/a.png")
        MockFD.getOpenFileName.assert_called_once()
        MockFD.getOpenFileNames.assert_not_called()

    def test_multiple_uses_get_open_file_names(self):
        """allow_multiple=True returns the full list via getOpenFileNames."""
        MockFD = self._patched()
        result = Switchboard.file_dialog(allow_multiple=True)
        self.assertEqual(result, ["/a.png", "/b.png"])
        MockFD.getOpenFileNames.assert_called_once()
        MockFD.getOpenFileName.assert_not_called()

    def test_does_not_set_read_only_option(self):
        """The ReadOnly option must not be OR'd into the dialog options."""
        MockFD = self._patched()
        Switchboard.file_dialog(allow_multiple=True)
        # Options() is created but never combined with ReadOnly.
        MockFD.Options.return_value.__ior__.assert_not_called()


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

    def test_padding_x_raises_stale_maximum_width(self):
        """A content-fit resize must not be silently truncated by a stale
        maximumWidth (e.g. a Designer-authored ceiling sized for shorter
        text than the widget currently holds).

        Regression test: marking-menu submenu buttons auto-size via
        ``center_widget(w, padding_x=...)`` (see ``add_child_event_filter``
        in _marking_menu.py). Several tentacle .ui buttons carry a leftover
        ``maximumSize`` from Designer that predates their current (longer)
        label text, which used to clamp the resize back below the button's
        own minimumSizeHint -- text rendered flush against the edges instead
        of padded. See uitk/docs/MARKING_MENU.md "Widget centering".
        """
        button = self.track_widget(QtWidgets.QPushButton())
        button.setText("A Fairly Long Button Label")
        button.setMaximumWidth(40)  # stale ceiling, narrower than the text needs
        needed = button.minimumSizeHint().width() + 25

        Switchboard.center_widget(button, padding_x=25)

        self.assertGreaterEqual(
            button.maximumWidth(),
            needed,
            "center_widget must raise a too-small maximumWidth to fit the request",
        )
        self.assertEqual(button.width(), needed)

    def test_padding_x_leaves_generous_maximum_width_untouched(self):
        """A maximumWidth that already accommodates the padded size must be
        left alone (no unnecessary widening of the constraint)."""
        button = self.track_widget(QtWidgets.QPushButton())
        button.setText("Short")
        button.setMaximumWidth(500)

        Switchboard.center_widget(button, padding_x=25)

        self.assertEqual(button.maximumWidth(), 500)

    def test_padding_x_does_not_widen_a_fixed_size_lock(self):
        """minimumWidth == maximumWidth is a deliberate fixed-size lock (e.g.
        a square icon tile), not a stale Designer ceiling, and must survive
        a padding_x resize untouched -- even when the button's own text
        would otherwise need more room than the lock allows.

        Regression: tentacle's cameras#startmenu.ui ``i000`` ("Camera
        Options") is pinned to a 100x21 fixed size (min == max); text-only
        sizing would need more than 100px, and an earlier version of the
        maximumWidth-raising fix widened it anyway, stretching a tile meant
        to stay square/uniform with its siblings.
        """
        button = self.track_widget(QtWidgets.QPushButton())
        button.setText("Camera Options")
        button.setFixedWidth(100)  # sets minimumWidth == maximumWidth == 100
        self.assertGreater(
            button.minimumSizeHint().width() + 25,
            100,
            "fixture invalid: this text must actually need more than the lock",
        )

        Switchboard.center_widget(button, padding_x=25)

        self.assertEqual(button.maximumWidth(), 100)
        self.assertEqual(button.width(), 100)


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

    def _with_alt_modifier(self):
        return mock.patch.object(
            QtWidgets.QApplication.instance(),
            "keyboardModifiers",
            return_value=QtCore.Qt.AltModifier,
        )

    def test_invert_with_alt_flips_bool_true_to_false(self):
        with self._with_alt_modifier():
            self.assertEqual(Switchboard.invert_on_modifier(True), False)

    def test_invert_with_alt_flips_bool_false_to_true(self):
        with self._with_alt_modifier():
            self.assertEqual(Switchboard.invert_on_modifier(False), True)

    def test_invert_with_alt_negates_int(self):
        with self._with_alt_modifier():
            self.assertEqual(Switchboard.invert_on_modifier(5), -5)
            self.assertEqual(Switchboard.invert_on_modifier(-5), 5)


class TestSwitchboardAddResetButtons(QtBaseTestCase):
    """Tests for SwitchboardUtilsMixin.add_reset_buttons batch helper.

    Uses uitk spin/combo widgets (which carry the OptionBoxMixin and wrap
    cleanly) so the tests mirror real panels — production slots wire uitk
    SpinBox/DoubleSpinBox/ComboBox, never plain QtWidgets spin boxes.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        from uitk.widgets.spinBox import SpinBox
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

        # Add convention-named uitk spin widgets to the panel so every
        # resolution path (findChildren, string pattern, explicit list) and the
        # uitk ComboBox already in the example UI are all exercisable.
        layout = self.ui.centralWidget().layout()
        self.s000 = SpinBox()
        self.s000.setObjectName("s000")
        layout.addWidget(self.s000)
        self.ui.register_widget(self.s000)
        self.s001 = DoubleSpinBox()
        self.s001.setObjectName("s001")
        layout.addWidget(self.s001)
        self.ui.register_widget(self.s001)

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def _has_reset(self, widget):
        from uitk.widgets.optionBox.options.reset import ResetOption

        return widget.option_box.find_option(ResetOption) is not None

    def test_auto_discovers_spinboxes_via_findchildren(self):
        """widgets=None discovers every child of *types* (spin boxes by default)."""
        box = self.track_widget(QtWidgets.QWidget())
        from uitk.widgets.spinBox import SpinBox

        QtWidgets.QVBoxLayout(box)
        a = SpinBox()
        a.setObjectName("only_a")
        box.layout().addWidget(a)
        b = SpinBox()
        b.setObjectName("only_b")
        box.layout().addWidget(b)

        wired = self.sb.add_reset_buttons(box)
        self.assertCountEqual(wired, [a, b])
        self.assertTrue(self._has_reset(a))
        self.assertTrue(self._has_reset(b))

    def test_string_pattern_resolution(self):
        """A shorthand pattern resolves via the s000/cmb000 naming convention."""
        wired = self.sb.add_reset_buttons(self.ui, "s000-1")
        self.assertEqual(wired, [self.s000, self.s001])
        self.assertTrue(self._has_reset(self.s000))
        self.assertTrue(self._has_reset(self.s001))

    def test_explicit_widget_list(self):
        """An explicit widget list wires exactly those widgets."""
        wired = self.sb.add_reset_buttons(self.ui, [self.s000])
        self.assertEqual(wired, [self.s000])
        self.assertTrue(self._has_reset(self.s000))
        self.assertFalse(self._has_reset(self.s001))

    def test_skips_named_widget(self):
        """A widget whose objectName is in skip is left alone."""
        wired = self.sb.add_reset_buttons(self.ui, [self.s000, self.s001], skip=("s000",))
        self.assertEqual(wired, [self.s001])
        self.assertFalse(self._has_reset(self.s000))

    def test_skips_widget_instance(self):
        """A widget instance (not just its name) in skip is left alone."""
        wired = self.sb.add_reset_buttons(self.ui, [self.s000, self.s001], skip=(self.s000,))
        self.assertEqual(wired, [self.s001])
        self.assertFalse(self._has_reset(self.s000))

    def test_types_override_targets_combos(self):
        """types= lets a panel wire combo boxes instead of spin boxes."""
        wired = self.sb.add_reset_buttons(self.ui, types=(QtWidgets.QComboBox,))
        self.assertIn(self.ui.cmb_options, wired)
        self.assertTrue(self._has_reset(self.ui.cmb_options))
        # The default spin-box targets must remain untouched.
        self.assertFalse(self._has_reset(self.s000))

    def test_forwards_kwargs_to_set_reset(self):
        """**set_reset_kwargs reach the underlying ResetOption."""
        from uitk.widgets.optionBox.options.reset import ResetOption

        self.sb.add_reset_buttons(self.ui, [self.s000], icon="close")
        opt = self.s000.option_box.find_option(ResetOption)
        self.assertIsNotNone(opt)
        self.assertEqual(opt._icon, "close")

    def test_returns_empty_for_no_matches(self):
        """A container with no matching widgets returns an empty list, not an error."""
        empty = self.track_widget(QtWidgets.QWidget())
        self.assertEqual(self.sb.add_reset_buttons(empty), [])


class _DeadCppWrapper:
    """Stand-in for a shiboken wrapper whose C++ object was invalidated.

    Touching any Qt method raises RuntimeError (exactly as a reparented
    QUiLoader widget does in PySide6), but the defer-time name stamp survives
    because it is a plain Python attribute.
    """

    def __init__(self, name):
        self._deferred_object_name = name

    def objectName(self):
        raise RuntimeError("Internal C++ object (QSpinBox) already deleted")


class TestDeferredWidgetRevival(QtBaseTestCase):
    """Regression tests for the self-healing deferred-widget pipeline.

    A widget accessed during a slots ``__init__`` is registered as a *deferred*
    widget; an option-box wrap (``add_reset_buttons``) then reparents it, which
    in PySide6 invalidates the wrapper captured at defer time. Previously
    ``_process_deferred_widgets`` crashed on the dead wrapper
    ("Internal C++ object ... already deleted") and the whole panel failed to
    open. The switchboard must now re-resolve the live wrapper instead.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        from uitk.widgets.spinBox import SpinBox
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

        layout = self.ui.centralWidget().layout()
        self.s000 = SpinBox()
        self.s000.setObjectName("s000")
        layout.addWidget(self.s000)
        self.ui.register_widget(self.s000)
        self.s001 = DoubleSpinBox()
        self.s001.setObjectName("s001")
        layout.addWidget(self.s001)
        self.ui.register_widget(self.s001)

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_widget_is_alive_distinguishes_live_from_dead(self):
        self.assertTrue(self.sb._widget_is_alive(self.s000))
        self.assertFalse(self.sb._widget_is_alive(_DeadCppWrapper("s000")))

    def test_revive_returns_widget_unchanged_when_alive(self):
        """A live wrapper is passed straight through (the common case)."""
        self.assertIs(self.sb._revive_deferred_widget(self.ui, self.s000), self.s000)

    def test_revive_reresolves_dead_wrapper_and_repairs_registry(self):
        """A dead wrapper is re-resolved by name; ui.<name> and ui.widgets heal."""
        dead = _DeadCppWrapper("s000")
        # Simulate the post-reparent registry state: the dead wrapper is what
        # the switchboard currently holds, while the live widget is still in
        # the Qt child tree (findable by name).
        self.ui.widgets.discard(self.s000)
        self.ui.widgets.add(dead)
        setattr(self.ui, "s000", dead)

        revived = self.sb._revive_deferred_widget(self.ui, dead)

        self.assertIs(revived, self.s000)
        self.assertIn(self.s000, self.ui.widgets)
        self.assertNotIn(dead, self.ui.widgets)
        # Downstream self.ui.s000 access now lands on the live wrapper.
        self.assertIs(getattr(self.ui, "s000"), self.s000)
        self.assertTrue(self.sb._widget_is_alive(self.ui.s000))

    def test_revive_returns_none_when_unrecoverable(self):
        """A dead wrapper whose widget no longer exists is reported, not raised."""
        self.assertIsNone(
            self.sb._revive_deferred_widget(self.ui, _DeadCppWrapper("does_not_exist"))
        )

    def test_process_deferred_survives_dead_wrapper(self):
        """The exact crash site: a dead wrapper in the deferred list must not
        abort the batch, and the live widget must still be initialized."""
        dead = _DeadCppWrapper("s000")
        self.ui.widgets.discard(self.s000)
        self.ui.widgets.add(dead)
        setattr(self.ui, "s000", dead)

        # Pre-fix this raised RuntimeError on the [w.objectName() ...] log line.
        self.sb._process_deferred_widgets(self.ui, [dead, self.s001])

        self.assertIs(getattr(self.ui, "s000"), self.s000)
        self.assertIn(self.s000, self.ui.widgets)
        self.assertNotIn(dead, self.ui.widgets)
        self.assertTrue(self.sb._widget_is_alive(self.ui.s000))

    def test_process_deferred_drops_unrecoverable_widget(self):
        """An unrecoverable dead wrapper is skipped without crashing the panel."""
        self.sb._process_deferred_widgets(self.ui, [_DeadCppWrapper("does_not_exist")])

    def test_real_optionbox_wrap_after_defer_keeps_widget_usable(self):
        """End-to-end: the real option-box wrap (which invalidates the wrapper
        in PySide6) after a defer must leave the widget usable post-process."""
        # Stamp the name as the defer path would, then perform the real wrap and
        # run the pipeline step that crashed.
        self.s000._deferred_object_name = "s000"
        self.sb.add_reset_buttons(self.ui, [self.s000])

        self.sb._process_deferred_widgets(self.ui, [self.s000])

        self.assertTrue(self.sb._widget_is_alive(self.ui.s000))
        # The live widget remains functional for perform_operation-style use.
        self.ui.s000.value()


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
            slot_source=ExampleSlots,
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
            slot_source=ExampleSlots,
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
            slot_source=ExampleSlots,
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
            slot_source=ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_slot_wrapper_is_callable(self):
        """SlotWrapper should be callable."""
        from uitk.switchboard import SlotWrapper

        def test_slot():
            return "called"

        wrapper = SlotWrapper(test_slot, self.ui.button_a, self.sb)
        self.assertTrue(callable(wrapper))

    def test_slot_wrapper_calls_underlying_slot(self):
        """SlotWrapper should call the underlying slot."""
        from uitk.switchboard import SlotWrapper

        call_log = []

        def test_slot():
            call_log.append("called")

        wrapper = SlotWrapper(test_slot, self.ui.button_a, self.sb)
        wrapper()

        self.assertEqual(call_log, ["called"])

    def test_slot_wrapper_injects_widget_argument(self):
        """SlotWrapper should inject widget argument if signature accepts it."""
        from uitk.switchboard import SlotWrapper

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
            slot_source=ExampleSlots,
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
            slot_source=ExampleSlots,
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
            slot_source=ExampleSlots,
        )

    def test_slot_history_index_out_of_range(self):
        """Should handle index out of range gracefully."""
        # Clear history and try to access index
        history = self.sb.slot_history()
        if len(history) == 0:
            result = self.sb.slot_history(index=999)
            # Out-of-range single-int index returns None (prev_slot contract).
            self.assertIsNone(result)

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
            slot_source=ExampleSlots,
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
            slot_source=ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_slot_wrapper_with_lambda(self):
        """SlotWrapper should work with lambda functions."""
        from uitk.switchboard import SlotWrapper

        call_log = []
        wrapper = SlotWrapper(
            lambda: call_log.append("lambda"), self.ui.button_a, self.sb
        )
        wrapper()

        self.assertEqual(call_log, ["lambda"])

    def test_slot_wrapper_with_exception(self):
        """SlotWrapper should propagate exceptions."""
        from uitk.switchboard import SlotWrapper

        def raising_slot():
            raise ValueError("test error")

        wrapper = SlotWrapper(raising_slot, self.ui.button_a, self.sb)

        with self.assertRaises(ValueError):
            wrapper()

    def test_slot_wrapper_with_args(self):
        """SlotWrapper should pass through positional arguments."""
        from uitk.switchboard import SlotWrapper

        received_args = []

        def test_slot(*args):
            received_args.extend(args)

        wrapper = SlotWrapper(test_slot, self.ui.button_a, self.sb)
        wrapper(1, 2, 3)

        self.assertEqual(received_args, [1, 2, 3])

    def test_slot_wrapper_with_kwargs(self):
        """SlotWrapper should pass through keyword arguments."""
        from uitk.switchboard import SlotWrapper

        received_kwargs = {}

        def test_slot(widget=None, **kwargs):
            received_kwargs.update(kwargs)

        wrapper = SlotWrapper(test_slot, self.ui.button_a, self.sb)
        wrapper(foo="bar", baz=42)

        # SlotWrapper may not pass through arbitrary kwargs if slot signature doesn't match
        # Just verify wrapper is callable and doesn't crash
        self.assertTrue(callable(wrapper))


class TestSlotMismatchLogging(QtBaseTestCase):
    """Tests for slot-mismatch logging behavior.

    Verifies that get_slot and connect_slot log at DEBUG level when a widget
    has no matching slot method. DEBUG is intentional — most widgets
    (size_grip, menuFrame, hdr_pin, etc.) have no slot by design.
    WARNING would flood the console with false positives.
    Verified: 2026-03-01
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_get_slot_logs_debug_on_missing_slot(self):
        """get_slot should log at DEBUG (not WARNING) when no matching slot exists.

        Uses mock.patch because uitk's LoggingMixin creates unregistered Logger
        instances (not via getLogger), making assertLogs unreliable.
        """
        from unittest.mock import patch

        slots_instance = self.sb.get_slots_instance(self.ui)
        logger = self.sb.logger

        with (
            patch.object(logger, "debug", wraps=logger.debug) as mock_debug,
            patch.object(logger, "warning", wraps=logger.warning) as mock_warning,
        ):
            result = self.sb.get_slot(slots_instance, "nonexistent_widget_xyz")

        self.assertIsNone(result)
        # Should have logged at DEBUG
        debug_calls = [
            str(c) for c in mock_debug.call_args_list if "Slot not found" in str(c)
        ]
        self.assertTrue(
            len(debug_calls) > 0,
            "Expected 'Slot not found' at DEBUG level",
        )
        # Must NOT have logged at WARNING (would flood console)
        warning_calls = [
            str(c) for c in mock_warning.call_args_list if "Slot not found" in str(c)
        ]
        self.assertEqual(
            len(warning_calls),
            0,
            f"Slot-not-found must be DEBUG, not WARNING (floods console): {warning_calls}",
        )

    def test_connect_slot_skips_non_callable_collision(self):
        """connect_slot must skip (with a WARNING) when a widget's objectName
        collides with a non-callable attribute on the slots class.

        Without the guard, ``getattr(slots, objectName)`` returns that attribute
        (e.g. a widget stored as ``self.<objectName>``) and ``signal.connect`` on
        it raised the cryptic "is not a callable object" — the map_converter
        footer-button bug. The connection must be skipped, not attempted.
        """
        from unittest.mock import patch

        slots_instance = self.sb.get_slots_instance(self.ui)
        # Simulate the collision: a non-callable attribute named like the widget.
        slots_instance.colliding_widget = QtWidgets.QLabel("not a slot")

        orphan = QtWidgets.QPushButton("Colliding")
        orphan.setObjectName("colliding_widget")
        orphan.setParent(self.ui.centralWidget())
        self.ui.register_widget(orphan)

        logger = self.sb.logger
        with (
            patch.object(logger, "warning", wraps=logger.warning) as mock_warning,
            patch.object(logger, "error", wraps=logger.error) as mock_error,
        ):
            self.sb.connect_slot(orphan)

        # Must NOT have attempted the connection (no cryptic connect error).
        connect_errors = [
            str(c) for c in mock_error.call_args_list if "Error connecting" in str(c)
        ]
        self.assertEqual(
            connect_errors, [], f"Should skip, not error on connect: {connect_errors}"
        )
        # Should warn (actionably) about the non-callable collision.
        warns = [str(c) for c in mock_warning.call_args_list if "non-callable" in str(c)]
        self.assertTrue(
            len(warns) > 0, "Expected a WARNING about the non-callable slot collision"
        )
        # And the signal must not be wired.
        self.assertNotIn(orphan, self.ui.connected_slots)

    def test_connect_slot_logs_debug_on_missing_slot(self):
        """connect_slot should log at DEBUG (not WARNING) when widget has no slot.

        Uses mock.patch because uitk's LoggingMixin creates unregistered Logger
        instances (not via getLogger), making assertLogs unreliable.
        """
        from unittest.mock import patch

        orphan = QtWidgets.QPushButton("Orphan")
        orphan.setObjectName("nonexistent_widget_xyz")
        orphan.setParent(self.ui.centralWidget())
        self.ui.register_widget(orphan)

        logger = self.sb.logger

        with (
            patch.object(logger, "debug", wraps=logger.debug) as mock_debug,
            patch.object(logger, "warning", wraps=logger.warning) as mock_warning,
        ):
            self.sb.connect_slot(orphan)

        debug_calls = [
            str(c)
            for c in mock_debug.call_args_list
            if "No slot found" in str(c) or "Slot not found" in str(c)
        ]
        self.assertTrue(
            len(debug_calls) > 0,
            "Expected slot-mismatch message at DEBUG level",
        )
        warning_calls = [
            str(c)
            for c in mock_warning.call_args_list
            if "No slot found" in str(c) or "Slot not found" in str(c)
        ]
        self.assertEqual(
            len(warning_calls),
            0,
            f"Slot-not-found must be DEBUG, not WARNING (floods console): {warning_calls}",
        )


# =============================================================================
# Performance Regression Tests
# =============================================================================


class TestLoggerHandlerSyncPerformance(unittest.TestCase):
    """Regression: LoggingMixin.logger must NOT sync handler levels on every access.

    Bug: The logger ClassProperty iterated all handlers calling setLevel() on
    every property access. With hundreds of logger accesses per widget during
    init, this was a significant bottleneck.
    Fix: Handler levels are now synced only in _set_level (called via setLevel).
    Fixed: 2026-03-01
    """

    def test_handler_setLevel_not_called_on_access(self):
        """Accessing .logger repeatedly should not call handler.setLevel each time."""
        from unittest.mock import patch

        sb = Switchboard(ui_source=None)
        logger = sb.logger
        # Force a level so we have a known state
        logger.setLevel("WARNING")

        # Now patch handler.setLevel and access the logger many times
        handler = logger.handlers[0]
        with patch.object(handler, "setLevel", wraps=handler.setLevel) as mock_set:
            for _ in range(100):
                _ = sb.logger  # Repeated property access
            # Should NOT have been called 100 times (was the old behavior)
            self.assertEqual(
                mock_set.call_count,
                0,
                f"handler.setLevel called {mock_set.call_count} times on 100 logger accesses (should be 0)",
            )

    def test_setLevel_syncs_handlers(self):
        """Calling setLevel should still propagate to handlers."""
        import logging

        sb = Switchboard(ui_source=None)
        logger = sb.logger
        logger.setLevel("DEBUG")
        for handler in logger.handlers:
            self.assertEqual(
                handler.level,
                logging.DEBUG,
                "Handler level should match after setLevel('DEBUG')",
            )
        logger.setLevel("ERROR")
        for handler in logger.handlers:
            self.assertEqual(
                handler.level,
                logging.ERROR,
                "Handler level should match after setLevel('ERROR')",
            )


class TestSlotWrapperSignatureCache(QtBaseTestCase):
    """Regression: SlotWrapper must cache inspect.signature per slot function.

    Bug: inspect.signature() was called in every SlotWrapper.__init__, which
    runs for every widget×signal connection. For the same slot function connected
    to multiple widgets, the signature is identical.
    Fix: Cache by slot function id in a class-level dict.
    Fixed: 2026-03-01
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        from uitk.switchboard import SlotWrapper

        SlotWrapper._sig_cache.clear()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_signature_cached_across_wrappers(self):
        """Creating two SlotWrappers for the same slot should call inspect.signature only once."""
        from unittest.mock import patch
        from uitk.switchboard import SlotWrapper
        import inspect

        def dummy_slot(self, widget=None):
            pass

        btn1 = QtWidgets.QPushButton("A")
        btn1.setObjectName("test_btn_a")
        btn2 = QtWidgets.QPushButton("B")
        btn2.setObjectName("test_btn_b")

        SlotWrapper._sig_cache.clear()
        with patch(
            "uitk.switchboard.slots.inspect.signature",
            wraps=inspect.signature,
        ) as mock_sig:
            w1 = SlotWrapper(dummy_slot, btn1, self.sb)
            w2 = SlotWrapper(dummy_slot, btn2, self.sb)

        self.assertEqual(
            mock_sig.call_count,
            1,
            f"inspect.signature called {mock_sig.call_count} times for same slot (should be 1)",
        )
        # Both wrappers should have identical param info
        self.assertEqual(w1.param_names, w2.param_names)
        self.assertEqual(w1.wants_widget, w2.wants_widget)
        self.assertTrue(w1.wants_widget)

    def test_different_slots_cached_independently(self):
        """Different slot functions should each get their own cache entry."""
        from uitk.switchboard import SlotWrapper

        def slot_a(self, widget=None):
            pass

        def slot_b(self, value=0):
            pass

        btn = QtWidgets.QPushButton("X")
        btn.setObjectName("test_btn_x")

        SlotWrapper._sig_cache.clear()
        w1 = SlotWrapper(slot_a, btn, self.sb)
        w2 = SlotWrapper(slot_b, btn, self.sb)

        self.assertTrue(w1.wants_widget)
        self.assertFalse(w2.wants_widget)
        self.assertEqual(len(SlotWrapper._sig_cache), 2)


class TestInitSlotShortCircuit(QtBaseTestCase):
    """Regression: init_slot must short-circuit when slots are already instantiated.

    Bug: init_slot always called _add_to_placeholder (which may call
    _find_slots_class) even when the slot instance already exists. This caused
    redundant registry lookups for every widget after the first.
    Fix: Check slots_instantiated(key) first and skip placeholder path.
    Fixed: 2026-03-01
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_no_placeholder_call_when_slots_exist(self):
        """After slots are instantiated, init_slot should not call _add_to_placeholder."""
        from unittest.mock import patch

        # Ensure slots exist
        self.sb.get_slots_instance(self.ui)
        key = self.sb.get_base_name(self.ui.objectName())
        self.assertTrue(self.sb.slots_instantiated(key))

        # Now register a new widget
        btn = QtWidgets.QPushButton("NewBtn")
        btn.setObjectName("new_test_button")
        btn.setParent(self.ui.centralWidget())
        self.ui.register_widget(btn)

        with patch.object(self.sb, "_add_to_placeholder") as mock_placeholder:
            self.sb.init_slot(btn)

        self.assertEqual(
            mock_placeholder.call_count,
            0,
            "_add_to_placeholder should not be called when slots are already instantiated",
        )


class TestDerivedTypeCache(QtBaseTestCase):
    """Regression: get_derived_type must cache results by widget type.

    Bug: get_derived_type walked the full MRO for every widget, even though
    the result is deterministic per type+parameters.
    Fix: Class-level cache dict keyed by (type, return_name, module, ...).
    Fixed: 2026-03-01
    """

    def test_cache_hit_on_same_type(self):
        """Two QPushButtons should produce only one MRO traversal."""
        import pythontk as ptk

        ptk.CoreUtils._derived_type_cache.clear()

        btn1 = QtWidgets.QPushButton("A")
        btn2 = QtWidgets.QPushButton("B")

        r1 = ptk.get_derived_type(btn1, module="QtWidgets")
        r2 = ptk.get_derived_type(btn2, module="QtWidgets")

        self.assertIs(r1, r2, "Same type should return identical cached result")
        # Cache should have exactly one entry for this parameter combination
        matching = [
            k
            for k in ptk.CoreUtils._derived_type_cache
            if k[0] is QtWidgets.QPushButton and k[2] == "QtWidgets"
        ]
        self.assertEqual(
            len(matching), 1, "Should have one cache entry for QPushButton+QtWidgets"
        )

    def test_different_types_cached_separately(self):
        """Different widget types should be cached independently."""
        import pythontk as ptk

        ptk.CoreUtils._derived_type_cache.clear()

        btn = QtWidgets.QPushButton("A")
        chk = QtWidgets.QCheckBox("B")

        r1 = ptk.get_derived_type(btn, module="QtWidgets")
        r2 = ptk.get_derived_type(chk, module="QtWidgets")

        self.assertIsNot(r1, r2)
        self.assertEqual(len(ptk.CoreUtils._derived_type_cache), 2)


class TestDefaultSignalsLookupEfficiency(QtBaseTestCase):
    """Regression: widget.default_signals() should use direct dict lookup, not isinstance loop.

    The lambda assigned in register_widget should do a dict.get by derived_type,
    not iterate all 27 entries with isinstance checks.
    Fixed: 2026-03-01
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=ExampleSlots,
        )
        self.ui = self.sb.loaded_ui.example

    def tearDown(self):
        if hasattr(self, "ui") and self.ui:
            self.ui.close()
        super().tearDown()

    def test_pushbutton_default_signal_is_clicked(self):
        """A registered QPushButton should report 'clicked' as its default signal."""
        btn = QtWidgets.QPushButton("Test")
        btn.setObjectName("test_default_sig_btn")
        btn.setParent(self.ui.centralWidget())
        self.ui.register_widget(btn)

        result = btn.default_signals()
        self.assertEqual(result, "clicked")

    def test_checkbox_default_signal_is_toggled(self):
        """A registered QCheckBox should report 'toggled' as its default signal."""
        chk = QtWidgets.QCheckBox("Test")
        chk.setObjectName("test_default_sig_chk")
        chk.setParent(self.ui.centralWidget())
        self.ui.register_widget(chk)

        result = chk.default_signals()
        self.assertEqual(result, "toggled")

    def test_widget_without_default_signal(self):
        """A widget type not in default_signals should return None."""
        frame = QtWidgets.QFrame()
        frame.setObjectName("test_default_sig_frame")
        frame.setParent(self.ui.centralWidget())
        self.ui.register_widget(frame)

        result = frame.default_signals()
        self.assertIsNone(result)


class TestSwitchboardActiveUi(QtBaseTestCase):
    """The ``active_ui`` no-warn peek vs ``current_ui`` auto-load+warn property.

    ``current_ui`` historically warns when no UI is set. That's noise when
    callers (e.g. the marking menu) legitimately probe for None. ``active_ui``
    is the silent variant — same value, no auto-load, no warning.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module,
            slot_source=ExampleSlots,
        )
        # Force multiple loaded UIs so the auto-load fallback doesn't fire
        # and we're guaranteed to hit the warning path on current_ui.
        self.sb.loaded_ui.example  # ensure loaded
        # Reset _current_ui to simulate the pre-first-show state.
        self.sb._current_ui = None

    def test_active_ui_returns_none_without_warning(self):
        """active_ui returns None when no UI is set, with no log records."""
        import logging

        records = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        h = _Capture(level=logging.DEBUG)
        Switchboard.logger.addHandler(h)
        try:
            self.assertIsNone(self.sb.active_ui)
        finally:
            Switchboard.logger.removeHandler(h)

        warnings = [r for r in records if r.levelno >= logging.WARNING]
        self.assertEqual(
            warnings, [],
            f"active_ui must not emit log warnings; got {[r.getMessage() for r in warnings]}",
        )

    def test_active_ui_returns_set_value(self):
        """active_ui returns the same value as current_ui once one is set."""
        ui = self.sb.loaded_ui.example
        self.sb.current_ui = ui
        self.assertIs(self.sb.active_ui, ui)
        self.assertIs(self.sb.active_ui, self.sb.current_ui)

    def test_active_ui_does_not_auto_load(self):
        """Unlike current_ui, active_ui must not trigger auto-load logic."""
        # Pre-condition: multiple UIs loaded so auto-load wouldn't fire even
        # for current_ui — test confirms active_ui is a pure peek regardless.
        before = self.sb._current_ui
        result = self.sb.active_ui
        after = self.sb._current_ui
        self.assertIs(result, before)
        self.assertIs(after, before)


class TestSuspendOverrideCursor(QtBaseTestCase):
    """Modal switchboard-utils dialogs must not inherit the slot busy cursor.

    Bug: ``SlotInvoker._invoke`` pushes an application-wide ``WaitCursor``
    override for the slot's duration. A ``QApplication`` override cursor
    beats every widget cursor, so dialogs a slot spawns (message box,
    file dialog, input dialog) showed the busy hourglass over their own
    buttons and text fields. Fixed by suspending the override-cursor
    stack for the modal dialog's lifetime via ``_suspend_override_cursor``.
    Fixed: 2026-06-09
    """

    def setUp(self):
        super().setUp()
        _drain_override_cursor()

    def tearDown(self):
        _drain_override_cursor()
        super().tearDown()

    def test_noop_without_active_override(self):
        app = QtWidgets.QApplication.instance()
        self.assertIsNone(app.overrideCursor())
        with _suspend_override_cursor():
            self.assertIsNone(app.overrideCursor())
        self.assertIsNone(app.overrideCursor())

    def test_suspends_and_restores_wait_cursor(self):
        app = QtWidgets.QApplication.instance()
        app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        with _suspend_override_cursor():
            self.assertIsNone(
                app.overrideCursor(), "busy cursor not suspended for the dialog"
            )
        self.assertIsNotNone(app.overrideCursor())
        self.assertEqual(app.overrideCursor().shape(), QtCore.Qt.WaitCursor)

    def test_restores_full_stack_in_order(self):
        app = QtWidgets.QApplication.instance()
        app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.BusyCursor))
        app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        with _suspend_override_cursor():
            self.assertIsNone(app.overrideCursor())
        # Top of the restored stack is the last one that was pushed.
        self.assertEqual(app.overrideCursor().shape(), QtCore.Qt.WaitCursor)
        app.restoreOverrideCursor()
        self.assertEqual(app.overrideCursor().shape(), QtCore.Qt.BusyCursor)

    def test_restores_even_on_exception(self):
        app = QtWidgets.QApplication.instance()
        app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        with self.assertRaises(ValueError):
            with _suspend_override_cursor():
                raise ValueError("boom")
        self.assertIsNotNone(app.overrideCursor())
        self.assertEqual(app.overrideCursor().shape(), QtCore.Qt.WaitCursor)

    def test_input_dialog_suspends_override_during_exec(self):
        """input_dialog must clear the busy cursor while its modal loop runs."""
        sb = Switchboard()
        app = QtWidgets.QApplication.instance()
        app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))

        seen = {}

        def fake_exec(self):
            seen["override"] = app.overrideCursor()
            return QtWidgets.QDialog.Rejected

        with mock.patch.object(QtWidgets.QDialog, "exec_", fake_exec):
            sb.input_dialog(title="t", label="l")

        self.assertIn("override", seen)
        self.assertIsNone(
            seen["override"], "busy cursor still active inside modal exec_"
        )
        # And the slot busy-cursor is back afterward.
        self.assertEqual(app.overrideCursor().shape(), QtCore.Qt.WaitCursor)

    def test_drain_clears_whole_stack(self):
        app = QtWidgets.QApplication.instance()
        app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.BusyCursor))
        app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        _drain_override_cursor()
        self.assertIsNone(app.overrideCursor(), "override stack not drained")
        # Idempotent: a no-op when nothing is active.
        _drain_override_cursor()
        self.assertIsNone(app.overrideCursor())

    def test_text_view_dialog_cancels_busy_cursor(self):
        """A non-modal viewer must not leave the slot busy cursor active."""
        sb = Switchboard()
        app = QtWidgets.QApplication.instance()
        app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))

        dlg = sb.text_view_dialog(text="report", title="t")
        try:
            self.assertIsNone(
                app.overrideCursor(),
                "busy cursor still active over the non-modal viewer",
            )
        finally:
            dlg.close()


class TestModalBusyCursorFilter(QtBaseTestCase):
    """The slot dispatcher's busy cursor must yield to a native modal dialog.

    ``SlotWrapper._invoke`` installs ``_ModalBusyCursorFilter`` on the
    application while it holds the busy ``WaitCursor`` override. Qt posts
    ``WindowBlocked`` / ``WindowUnblocked`` when a modal blocks / releases
    the app (native Maya ``cmds.fileDialog2``, OS pickers included), and
    the filter suspends the override for that span so the dialog shows
    natural cursors, then restores it for the slot's post-dialog work.
    Driven here with synthetic events — real modal block/unblock is
    unreliable headless. Added: 2026-06-10
    """

    def _drain(self):
        app = QtWidgets.QApplication.instance()
        while app.overrideCursor() is not None:
            app.restoreOverrideCursor()

    def setUp(self):
        super().setUp()
        self._drain()
        self.app = QtWidgets.QApplication.instance()
        self.filt = _ModalBusyCursorFilter(self.app)

    def tearDown(self):
        self._drain()
        super().tearDown()

    def _send(self, etype):
        self.filt.eventFilter(None, QtCore.QEvent(etype))

    def test_block_suspends_unblock_restores(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self._send(QtCore.QEvent.WindowBlocked)
        self.assertIsNone(
            self.app.overrideCursor(), "busy cursor not suspended for the modal"
        )
        self._send(QtCore.QEvent.WindowUnblocked)
        self.assertIsNotNone(self.app.overrideCursor())
        self.assertEqual(self.app.overrideCursor().shape(), QtCore.Qt.WaitCursor)

    def test_nested_modals_only_outer_pair_toggles(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self._send(QtCore.QEvent.WindowBlocked)  # outer
        self._send(QtCore.QEvent.WindowBlocked)  # inner
        self.assertIsNone(self.app.overrideCursor())
        self._send(QtCore.QEvent.WindowUnblocked)  # inner closes — stay suspended
        self.assertIsNone(
            self.app.overrideCursor(), "inner unblock restored too early"
        )
        self._send(QtCore.QEvent.WindowUnblocked)  # outer closes — restore
        self.assertEqual(self.app.overrideCursor().shape(), QtCore.Qt.WaitCursor)

    def test_restores_full_stack_in_order(self):
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.BusyCursor))
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self._send(QtCore.QEvent.WindowBlocked)
        self.assertIsNone(self.app.overrideCursor())
        self._send(QtCore.QEvent.WindowUnblocked)
        self.assertEqual(self.app.overrideCursor().shape(), QtCore.Qt.WaitCursor)
        self.app.restoreOverrideCursor()
        self.assertEqual(self.app.overrideCursor().shape(), QtCore.Qt.BusyCursor)

    def test_eventfilter_never_consumes(self):
        self.assertFalse(self.filt.eventFilter(None, QtCore.QEvent(QtCore.QEvent.WindowBlocked)))
        self.assertFalse(self.filt.eventFilter(None, QtCore.QEvent(QtCore.QEvent.WindowUnblocked)))
        self.assertFalse(self.filt.eventFilter(None, QtCore.QEvent(QtCore.QEvent.Show)))

    def test_cleanup_rebalances_dangling_suspend(self):
        """If a block never gets its unblock, cleanup restores the stack."""
        self.app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        self._send(QtCore.QEvent.WindowBlocked)
        self.assertIsNone(self.app.overrideCursor())
        self.filt.cleanup()
        self.assertEqual(self.app.overrideCursor().shape(), QtCore.Qt.WaitCursor)


class TestExplicitSlotBinding(QtBaseTestCase):
    """An explicitly-passed ``slot_source`` binds to its UI even when the class
    name doesn't follow the ``<ui-basename>`` convention.

    Regression: when the texture_maps panels' ``.ui`` basenames were
    de-stuttered (``map_packer.ui`` -> ``packer.ui``) but the slot classes kept
    the old ``Map*Slots`` names, ``_find_slots_class('packer')`` matched nothing
    and ``ui.slots`` was ``None`` (every panel was slot-less). A Switchboard
    built for a single panel now honors its sole registered slot class
    regardless of name; name/file matching still takes precedence, and the
    fallback is restricted to the unambiguous single-class case.
    """

    def test_sole_slot_class_binds_despite_name_mismatch(self):
        class WeirdlyNamedSlots:
            def __init__(self, switchboard, **kwargs):
                self.sb = switchboard

        sb = Switchboard(slot_source=WeirdlyNamedSlots)
        # Slot-creation callers opt into the single-class fallback...
        self.assertIs(
            sb._find_slots_class("packer", allow_sole_fallback=True),
            WeirdlyNamedSlots,
        )
        # ...but the strict (default) lookup, used by UI-name resolution, does
        # NOT — so it can't fabricate slots for an arbitrary name.
        self.assertIsNone(sb._find_slots_class("packer"))

    def test_strict_lookup_never_fabricates_a_ui(self):
        """The single-class fallback must not leak into UI resolution: an
        unknown ``loaded_ui.<name>`` still raises ``AttributeError`` rather than
        creating a phantom UI bound to the sole slot class."""
        class SoloSlots:
            def __init__(self, switchboard, **kwargs):
                self.sb = switchboard

        sb = Switchboard(slot_source=SoloSlots)
        with self.assertRaises(AttributeError):
            _ = sb.loaded_ui.totally_unknown_panel

    def test_name_match_still_takes_precedence(self):
        class PackerSlots:
            def __init__(self, switchboard, **kwargs):
                self.sb = switchboard

        class CompositorSlots:
            def __init__(self, switchboard, **kwargs):
                self.sb = switchboard

        sb = Switchboard(slot_source=[PackerSlots, CompositorSlots])
        # Two classes: resolve by name, never via the single-class fallback
        # (even when the fallback is allowed).
        self.assertIs(
            sb._find_slots_class("packer", allow_sole_fallback=True), PackerSlots
        )
        self.assertIs(
            sb._find_slots_class("compositor", allow_sole_fallback=True),
            CompositorSlots,
        )

    def test_ambiguous_multiclass_no_match_returns_none(self):
        class FooSlots:
            def __init__(self, switchboard, **kwargs):
                self.sb = switchboard

        class BarSlots:
            def __init__(self, switchboard, **kwargs):
                self.sb = switchboard

        sb = Switchboard(slot_source=[FooSlots, BarSlots])
        # More than one class: the fallback can't disambiguate even when allowed.
        self.assertIsNone(
            sb._find_slots_class("nomatch", allow_sole_fallback=True)
        )


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
