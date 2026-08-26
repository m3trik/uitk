# !/usr/bin/python
# coding=utf-8
"""Unit tests for ``uitk.widgets.windowPanel.WindowPanel``'s build idiom.

``WindowPanel`` is built the way a ``Menu`` is built: ``add(x, **kwargs)``
takes a widget-class name / instance / class, routes the kwargs through
``AttributesMixin.set_attributes`` (setters and signal connections alike),
places the widget as a form row with an optional caption to its LEFT, and
exposes it as ``panel.<objectName>``. These tests pin that the vocabulary IS
Menu's — same resolution, same kwargs, same exposure rule — so building a
window and building a menu are one skill.

Run standalone: python -m test.test_window_panel
"""

import logging
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets

from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.windowPanel import WindowPanel


class WindowPanelTestCase(QtBaseTestCase):
    def _panel(self, **kwargs):
        panel = WindowPanel(title=kwargs.pop("title", "Probe"), **kwargs)
        self.addCleanup(panel.deleteLater)
        self.addCleanup(panel.close)
        return panel

    @staticmethod
    def _label_of(panel, row):
        item = panel.rows_layout.itemAt(row, QtWidgets.QFormLayout.LabelRole)
        return item.widget() if item is not None else None

    @staticmethod
    def _field_of(panel, row):
        item = panel.rows_layout.itemAt(row, QtWidgets.QFormLayout.FieldRole)
        if item.widget() is not None:
            return [item.widget()]
        cell = item.layout()
        return [cell.itemAt(i).widget() for i in range(cell.count())]


class TestResolution(WindowPanelTestCase):
    """What ``add`` accepts, and what a string turns into."""

    def test_a_uitk_widget_name_resolves_to_the_uitk_class(self):
        """The root registry is asked FIRST: "CheckBox" is uitk's, not Qt's."""
        from uitk.widgets.checkBox import CheckBox

        widget = self._panel().add("CheckBox")
        self.assertIsInstance(widget, CheckBox)

    def test_a_qt_widget_name_resolves_to_qt(self):
        widget = self._panel().add("QPushButton")
        self.assertIs(type(widget), QtWidgets.QPushButton)

    def test_a_separator_resolves_for_free(self):
        """Registered in the root registry, so the header-menu idiom
        ``add("Separator", setTitle=...)`` works on a window unchanged."""
        from uitk.widgets.separator import Separator

        self.assertIsInstance(self._panel().add("Separator"), Separator)

    def test_an_instance_is_used_as_is(self):
        instance = QtWidgets.QSpinBox()
        self.assertIs(self._panel().add(instance), instance)

    def test_a_class_is_instantiated(self):
        self.assertIsInstance(self._panel().add(QtWidgets.QSpinBox), QtWidgets.QSpinBox)

    def test_an_unresolvable_string_becomes_a_caption(self):
        """Menu's affordance: ``add("Output:")`` is a section caption."""
        widget = self._panel().add("Output:")
        self.assertIsInstance(widget, QtWidgets.QLabel)
        self.assertEqual(widget.text(), "Output:")
        self.assertTrue(widget.property("caption"))

    def test_a_registry_name_that_is_not_a_widget_does_not_instantiate(self):
        """The root registry resolves managers and mixins too; a hit is
        type-checked before anything is built."""
        widget = self._panel().add("SettingsManager")
        self.assertIsInstance(widget, QtWidgets.QLabel)

    def test_a_typo_that_looks_like_a_class_name_is_logged(self):
        """The label fallthrough is Menu's known typo trap — surfaced here."""
        with self.assertLogs("uitk.widgets.windowPanel", level=logging.DEBUG) as logs:
            self._panel().add("PushButtn")
        self.assertTrue(any("PushButtn" in line for line in logs.output))

    def test_a_list_adds_each_and_returns_them_in_order(self):
        widgets = self._panel().add(["QPushButton", "QLineEdit"])
        self.assertEqual(
            [type(w) for w in widgets], [QtWidgets.QPushButton, QtWidgets.QLineEdit]
        )

    def test_anything_else_is_refused(self):
        with self.assertRaises(TypeError):
            self._panel().add(42)


class TestKwargs(WindowPanelTestCase):
    """The kwargs dialect is literally ``set_attributes`` — Menu's."""

    def test_the_panel_is_an_attributes_mixin(self):
        self.assertIsInstance(self._panel(), AttributesMixin)

    def test_setter_kwargs_are_applied(self):
        widget = self._panel().add("QLineEdit", setText="hello", setEnabled=False)
        self.assertEqual(widget.text(), "hello")
        self.assertFalse(widget.isEnabled())

    def test_a_signal_name_connects(self):
        seen = []
        widget = self._panel().add("QPushButton", clicked=lambda *_: seen.append(1))
        widget.click()
        self.assertEqual(seen, [1])

    def test_kwargs_are_applied_before_the_row_is_placed(self):
        """The caption mirrors the control's enabled state AT ADD TIME, so a
        ``setEnabled=False`` kwarg must land before the caption reads it."""
        panel = self._panel()
        panel.add("QLineEdit", label="Path", setEnabled=False)
        self.assertFalse(self._label_of(panel, 0).isEnabled())


class TestExposure(WindowPanelTestCase):
    """``panel.<objectName>`` — Menu's rule, verbatim."""

    def test_a_named_widget_is_exposed(self):
        panel = self._panel()
        widget = panel.add("QCheckBox", setObjectName="chk_dry")
        self.assertIs(panel.chk_dry, widget)

    def test_an_unnamed_widget_is_not(self):
        panel = self._panel()
        before = set(vars(panel))
        panel.add("QCheckBox")
        self.assertEqual(set(vars(panel)) - before, set())

    def test_a_name_colliding_with_the_window_api_is_refused(self):
        """A field named ``header`` must not replace the header."""
        panel = self._panel()
        header = panel.header
        with self.assertLogs("uitk.widgets.windowPanel", level=logging.WARNING):
            panel.add("QCheckBox", setObjectName="header")
        self.assertIs(panel.header, header)

    def test_a_re_added_name_replaces_the_previous_widget(self):
        """A widget may replace a widget (a rebuilt row), never a method."""
        panel = self._panel()
        panel.add("QCheckBox", setObjectName="chk")
        second = panel.add("QCheckBox", setObjectName="chk")
        self.assertIs(panel.chk, second)


class TestRows(WindowPanelTestCase):
    """Caption to the LEFT of its control; no caption spans the row."""

    def test_the_rows_are_a_form_layout(self):
        self.assertIsInstance(self._panel().rows_layout, QtWidgets.QFormLayout)

    def test_a_label_becomes_a_caption_in_the_label_column(self):
        panel = self._panel()
        widget = panel.add("QLineEdit", label="Search in")
        caption = self._label_of(panel, 0)
        self.assertEqual(caption.text(), "Search in")
        self.assertTrue(caption.property("caption"))
        self.assertTrue(caption.font().bold())
        self.assertEqual(self._field_of(panel, 0), [widget])

    def test_no_label_spans_the_row(self):
        panel = self._panel()
        widget = panel.add("QCheckBox", setText="Spanning")
        self.assertIsNone(self._label_of(panel, 0))
        self.assertEqual(self._field_of(panel, 0), [widget])

    def test_rows_keep_add_order(self):
        panel = self._panel()
        first = panel.add("QCheckBox")
        second = panel.add("QLineEdit", label="Second")
        self.assertEqual(self._field_of(panel, 0), [first])
        self.assertEqual(self._field_of(panel, 1), [second])

    def test_companions_share_the_field_cell(self):
        panel = self._panel()
        browse = QtWidgets.QPushButton("Browse…")
        editor = panel.add("QLineEdit", label="Path", companions=[browse])
        self.assertEqual(self._field_of(panel, 0), [editor, browse])

    def test_companions_and_caption_follow_the_control_state(self):
        panel = self._panel()
        browse = QtWidgets.QPushButton("Browse…")
        editor = panel.add(
            "QLineEdit", label="Path", companions=[browse], setEnabled=False
        )
        self.assertFalse(browse.isEnabled())
        self.assertFalse(self._label_of(panel, 0).isEnabled())
        self.assertEqual(panel._row_widgets[editor], [self._label_of(panel, 0), browse])

    def test_the_form_region_sits_first_in_the_body(self):
        """Deterministic placement: content a subclass appends (an output
        pane) lands BELOW the rows however late the first add arrives."""
        panel = self._panel()
        self.assertIs(panel.body_layout.itemAt(0).widget(), panel._rows_host)


class TestHints(WindowPanelTestCase):
    """A hint is a formatted tooltip on the whole row, titled by the caption."""

    def test_a_hint_reaches_caption_and_control_alike(self):
        panel = self._panel()
        widget = panel.add("QLineEdit", label="Search in", hint="Searched recursively.")
        tip = widget.toolTip()
        self.assertIn("Searched recursively.", tip)
        self.assertIn("<b>Search in</b>", tip)
        self.assertEqual(self._label_of(panel, 0).toolTip(), tip)

    def test_a_hint_without_a_caption_is_untitled(self):
        widget = self._panel().add("QCheckBox", setText="Box", hint="Ticks.")
        self.assertIn("Ticks.", widget.toolTip())
        self.assertNotIn("<b>", widget.toolTip())

    def test_an_explicit_tooltip_is_verbatim(self):
        widget = self._panel().add("QLineEdit", hint="ignored", tooltip="<i>mine</i>")
        self.assertEqual(widget.toolTip(), "<i>mine</i>")

    def test_no_hint_sets_no_tooltip(self):
        self.assertEqual(self._panel().add("QLineEdit").toolTip(), "")


class TestClearRows(WindowPanelTestCase):
    def test_clear_rows_empties_the_form(self):
        panel = self._panel()
        panel.add("QLineEdit", label="A")
        panel.add("QCheckBox")
        panel.clear_rows()
        self.assertEqual(panel.rows_layout.count(), 0)
        self.assertEqual(panel._row_widgets, {})

    def test_clear_rows_un_exposes_the_dead_widgets(self):
        """An attribute still pointing at a deleted widget hands back a dead
        C++ wrapper — the name must go with the row."""
        panel = self._panel()
        panel.add("QCheckBox", setObjectName="chk")
        panel.clear_rows()
        self.assertNotIn("chk", vars(panel))

    def test_clear_rows_leaves_the_rest_of_the_body_alone(self):
        panel = self._panel()
        extra = QtWidgets.QLabel("kept")
        panel.body_layout.addWidget(extra)
        panel.add("QLineEdit")
        panel.clear_rows()
        self.assertIs(panel.body_layout.itemAt(1).widget(), extra)


if __name__ == "__main__":
    unittest.main()
