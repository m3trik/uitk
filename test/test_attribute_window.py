# !/usr/bin/python
# coding=utf-8
"""Unit tests for AttributeWindow (uitk.widgets.attributeWindow).

Covers four regressions:
- Composite (list/set/tuple) attributes are reachable with the DEFAULT
  allow_unsupported_types=False (the plain type gate short-circuited them).
- showEvent with zero rows must not raise (empty max() -> ValueError, which
  the except clause guarded for the wrong type).
- on_label_toggled is wired for checkable labels when single_check=False.
- float_precision is applied to the float spin boxes it builds.

Run standalone: QT_QPA_PLATFORM=offscreen python test_attribute_window.py
"""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets  # noqa: E402
from uitk.widgets.attributeWindow._attributeWindow import AttributeWindow  # noqa: E402


class TestCompositeReachable(QtBaseTestCase):
    """Composite attrs must render with the default allow_unsupported_types=False."""

    def _make(self, attrs):
        w = AttributeWindow(object(), get_attribute_func=lambda: dict(attrs))
        return self.track_widget(w)

    def test_add_attributes_list_default_flag(self):
        w = self._make({})
        # allow_unsupported_types defaults to False.
        self.assertFalse(w.allow_unsupported_types)
        w.add_attributes("Position", [1.0, 2.0, 3.0])
        self.assertIn("Position", w.attribute_to_widgets)
        self.assertEqual(len(w.attribute_to_widgets["Position"]), 3)

    def test_refresh_attributes_list_default_flag(self):
        # Composite arrives via the get_attribute_func -> refresh_attributes gate.
        w = self._make({"Pos": [1.0, 2.0]})
        self.assertIn("Pos", w.attribute_to_widgets)
        self.assertEqual(len(w.attribute_to_widgets["Pos"]), 2)

    def test_scalar_still_added(self):
        w = self._make({"Name": "Cube", "Opacity": 0.5})
        self.assertIn("Name", w.attribute_to_widgets)
        self.assertIn("Opacity", w.attribute_to_widgets)


class TestShowEventEmpty(QtBaseTestCase):
    """Showing a window with zero attributes must not raise."""

    def test_show_with_no_attributes(self):
        w = self.track_widget(AttributeWindow(object(), get_attribute_func=lambda: {}))
        self.assertEqual(w.labels, [])
        # Pre-fix: max() over an empty sequence raised ValueError, which the
        # except (AttributeError) clause did not catch -> propagated out of show().
        w.show()
        QtWidgets.QApplication.processEvents()
        # Reaching here without an exception is the assertion.
        self.assertTrue(True)


class TestLabelToggledWiring(QtBaseTestCase):
    """on_label_toggled must fire labelToggled when single_check=False."""

    def test_checkable_multi_check_emits_labeltoggled(self):
        w = self.track_widget(
            AttributeWindow(
                object(),
                get_attribute_func=lambda: {},
                checkable=True,
                single_check=False,
            )
        )
        w.add_attributes("Flag", True)
        emitted = []
        w.labelToggled.connect(lambda name, state: emitted.append((name, state)))

        label = w.labels[0]
        self.assertEqual(label.text(), "Flag")
        label.setChecked(True)

        self.assertTrue(emitted, "labelToggled never fired for a checkable label")
        self.assertEqual(emitted[-1][0], "Flag")
        self.assertTrue(emitted[-1][1])


class TestFloatPrecision(QtBaseTestCase):
    """float_precision must reach the float spin boxes it builds."""

    def test_float_precision_applied_to_spinbox(self):
        w = self.track_widget(
            AttributeWindow(object(), get_attribute_func=lambda: {}, float_precision=6)
        )
        w.add_attributes("Scale", 1.5)
        widget = w.attribute_to_widgets["Scale"][0]
        self.assertTrue(hasattr(widget, "decimals"))
        self.assertEqual(widget.decimals(), 6)

    def test_float_precision_applied_to_composite(self):
        w = self.track_widget(
            AttributeWindow(object(), get_attribute_func=lambda: {}, float_precision=3)
        )
        w.add_attributes("Vec", [0.1, 0.2])
        for widget in w.attribute_to_widgets["Vec"]:
            self.assertEqual(widget.decimals(), 3)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
