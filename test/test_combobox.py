# !/usr/bin/python
# coding=utf-8
"""Regression tests for the base uitk ComboBox widget."""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()


class SetEditableNoneSafety(QtBaseTestCase):
    """``setEditable(False)`` on a non-editable combo must not AttributeError.

    Background: pyside6-uic-generated setupUi calls setEditable(False)
    explicitly when a .ui declares ``<property name="editable"><bool>false</bool></property>``.
    QComboBox.lineEdit() returns None when the combo is not editable, so the
    previous code raised on ``lineEdit.text()``. See
    [comboBox.py](uitk/uitk/widgets/comboBox.py).
    """

    def test_set_editable_false_on_default_combo_does_not_raise(self):
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        # Default state: editable is False, lineEdit() is None. The call
        # must be a no-op rather than crash.
        combo.setEditable(False)

    def test_set_editable_true_then_false_round_trip(self):
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        combo.addItem("alpha")
        combo.setEditable(True)
        # Now lineEdit() returns a real QLineEdit
        self.assertIsNotNone(combo.lineEdit())
        combo.setEditable(False)
        # And we can flip again without issue
        combo.setEditable(False)


if __name__ == "__main__":
    unittest.main()
