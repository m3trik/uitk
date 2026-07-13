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
        combo.item_spacing = 0  # isolate uniform-height from the spacing gap
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


class TestWidgetComboBoxItemSpacing(QtBaseTestCase):
    """The vertical gap between embedded-widget rows is a tight per-widget
    height plus the exposed ``item_spacing`` (default 1px). Regression: a
    stale add-time height (e.g. a checkbox measuring 17px pre-theme, 14px
    after) left rows taller than their widget, rendering as a ~3px gap."""

    def test_default_item_spacing_is_one(self):
        from uitk.widgets.widgetComboBox import WidgetComboBox

        self.assertEqual(self.track_widget(WidgetComboBox()).item_spacing, 1)

    def test_item_spacing_adds_to_row_height(self):
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        combo.add(QtWidgets.QPushButton("x"))
        combo._recompute_uniform_heights()
        base = combo._uniform_item_height

        combo.item_spacing = 0
        self.assertEqual(combo._model.item(0).sizeHint().height(), base)
        combo.item_spacing = 4
        self.assertEqual(combo._model.item(0).sizeHint().height(), base + 4)

    def test_recompute_corrects_stale_uniform_height(self):
        """``_recompute_uniform_heights`` re-derives the row height from the
        widget's *current* sizeHint, shrinking rows that were sized to a
        stale (larger) add-time height."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        combo.item_spacing = 0
        widget = QtWidgets.QPushButton("x")
        combo.add(widget)
        real_h = widget.sizeHint().height()

        # Simulate a stale, too-tall height captured before the widget shrank.
        combo._uniform_item_height = real_h + 5
        combo._resync_uniform_heights()
        self.assertEqual(combo._model.item(0).sizeHint().height(), real_h + 5)

        combo._recompute_uniform_heights()
        self.assertEqual(combo._uniform_item_height, real_h)
        self.assertEqual(combo._model.item(0).sizeHint().height(), real_h)


class TestWidgetComboBoxActionsSection(QtBaseTestCase):
    """The persistent actions section: grid layout, separator sizing, and
    button↔action enabled-state mirroring."""

    @staticmethod
    def _action_buttons(combo):
        """Return the QPushButtons in the actions container (last row)."""
        last = combo._model.rowCount() - 1
        container = combo._row_containers.get(last)
        inner = container.property("_embedded_widget")
        lay = inner.layout()
        return [lay.itemAt(i).widget() for i in range(lay.count())]

    def test_action_columns_grid_row_major(self):
        """``action_columns = 2`` packs actions row-major into a 2-col grid."""
        from uitk.widgets.widgetComboBox import WidgetComboBox
        from qtpy import QtWidgets as QW

        combo = self.track_widget(WidgetComboBox())
        combo.action_columns = 2
        combo.actions.add(
            {"A": lambda: None, "B": lambda: None,
             "C": lambda: None, "D": lambda: None}
        )

        last = combo._model.rowCount() - 1
        lay = combo._row_containers.get(last).property("_embedded_widget").layout()
        self.assertIsInstance(lay, QW.QGridLayout)
        pos = {
            lay.itemAt(i).widget().text(): lay.getItemPosition(i)[:2]
            for i in range(lay.count())
        }
        self.assertEqual(pos["A"], (0, 0))
        self.assertEqual(pos["B"], (0, 1))
        self.assertEqual(pos["C"], (1, 0))
        self.assertEqual(pos["D"], (1, 1))

    def test_separator_row_height_pinned_to_separator(self):
        """Regression: the separator row must be sized to the separator widget,
        not the delegate's (font-based) default — otherwise the surplus renders
        as dead space between the separator and the action buttons."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        combo.actions.add("Only", lambda: None)

        sep_row = combo._model.rowCount() - 2  # separator precedes the buttons
        sep_item = combo._model.item(sep_row)
        sep_widget = combo._row_containers.get(sep_row).property("_embedded_widget")

        self.assertTrue(
            sep_item.sizeHint().isValid(),
            "separator row left with an invalid sizeHint (the dead-space bug)",
        )
        self.assertEqual(
            sep_item.sizeHint().height(), sep_widget.minimumHeight(),
            "separator row height must match the separator widget's own height",
        )

    def test_button_mirrors_action_enabled_state(self):
        """Toggling ``action.setEnabled`` greys out / restores its button."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        action = combo.actions.add("Toggle", lambda: None)

        (btn,) = self._action_buttons(combo)
        self.assertTrue(btn.isEnabled())

        action.setEnabled(False)
        self.assertFalse(btn.isEnabled(), "button did not follow action.setEnabled(False)")

        action.setEnabled(True)
        self.assertTrue(btn.isEnabled(), "button did not follow action.setEnabled(True)")

    def test_rebuild_does_not_accumulate_action_connections(self):
        """Repeated rebuilds (e.g. preset refresh) must not leave dangling
        action.changed→button bindings connected to deleted buttons."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        combo.actions.add("X", lambda: None)
        for _ in range(5):
            combo._rebuild_actions_section()
        # One live binding per action after the latest rebuild.
        self.assertEqual(len(combo._action_button_conns), 1)

    def test_icon_only_no_separator_single_row(self):
        """icon-only + no-separator -> a single container row of textless,
        accessible-named buttons (toolbar style)."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        combo.action_icon_only = True
        combo.show_action_separator = False
        combo.actions.add(
            {"A": lambda: None, "B": lambda: None, "C": lambda: None}
        )
        combo.action_columns = 3

        # No separator -> only the button container row is added.
        self.assertEqual(combo._action_row_count, 1)
        btns = self._action_buttons(combo)
        self.assertEqual(len(btns), 3)
        for b in btns:
            self.assertEqual(b.text(), "", "icon-only buttons carry no text")
            self.assertTrue(
                b.accessibleName(), "icon-only buttons keep an accessible name"
            )

    def test_separator_drawn_by_default(self):
        """Default keeps the separator (two action rows: separator + buttons)."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        combo.actions.add("Only", lambda: None)
        self.assertEqual(combo._action_row_count, 2)


class TestWidgetComboBoxArrowAffordance(QtBaseTestCase):
    """The optional dropdown affordance: off by default, opt-in triangle,
    custom icon override, and alpha."""

    def test_arrow_off_by_default(self):
        """Default draws no affordance — matches the base ComboBox."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        self.assertIsNone(combo.arrow_direction)
        self.assertIsNone(combo.arrow_icon)
        self.assertEqual(combo.arrow_alpha, 1.0)

    def test_arrow_direction_validation(self):
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        combo.arrow_direction = "down"
        self.assertEqual(combo.arrow_direction, "down")
        with self.assertRaises(ValueError):
            combo.arrow_direction = "sideways"

    def test_arrow_icon_type_guard(self):
        from uitk.widgets.widgetComboBox import WidgetComboBox
        from qtpy import QtGui

        combo = self.track_widget(WidgetComboBox())
        icon = QtGui.QIcon()
        combo.arrow_icon = icon
        self.assertIs(combo.arrow_icon, icon)
        combo.arrow_icon = None
        self.assertIsNone(combo.arrow_icon)
        with self.assertRaises(TypeError):
            combo.arrow_icon = "not an icon"

    def test_arrow_alpha_clamped(self):
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = self.track_widget(WidgetComboBox())
        combo.arrow_alpha = 2.5
        self.assertEqual(combo.arrow_alpha, 1.0)
        combo.arrow_alpha = -1.0
        self.assertEqual(combo.arrow_alpha, 0.0)
        combo.arrow_alpha = 0.5
        self.assertEqual(combo.arrow_alpha, 0.5)

    def test_paint_paths_do_not_crash(self):
        """Every affordance path (none / triangle / icon / alpha) paints
        without error offscreen."""
        from uitk.widgets.widgetComboBox import WidgetComboBox
        from qtpy import QtGui, QtCore

        combo = self.track_widget(WidgetComboBox())
        combo.add(["Alpha", "Beta"])
        combo.resize(120, 24)

        def _render():
            pm = QtGui.QPixmap(combo.size())
            pm.fill(QtCore.Qt.transparent)
            combo.render(pm)

        _render()  # default: nothing
        combo.arrow_direction = "down"
        _render()  # triangle
        combo.arrow_icon = QtGui.QIcon()  # null icon → falls back to triangle cleanly
        _render()
        # A real (non-null) icon exercises the drawPixmap path.
        pm = QtGui.QPixmap(16, 16)
        pm.fill(QtCore.Qt.red)
        combo.arrow_icon = QtGui.QIcon(pm)
        _render()
        combo.arrow_alpha = 0.3
        _render()


if __name__ == "__main__":
    unittest.main()
