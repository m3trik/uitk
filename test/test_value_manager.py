# !/usr/bin/python
# coding=utf-8
"""Regression coverage for ValueManager.set_value.

Guards the bug where a checkable button (QCheckBox / QRadioButton /
checkable QPushButton) routed through the fallback ``set_value`` path had
its *label* set to the value instead of its *checked state* — because every
``QAbstractButton`` inherits ``setText`` and the ``setText`` branch used to
precede the ``setChecked`` branch. The uitk ``CheckBox`` made this worse: it
overrides ``setText`` with a rich-text setter, so ``set_value(chk, True)``
wrote the string ``"True"`` into the label and left the box unchecked.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets

from uitk.widgets.checkBox import CheckBox
from uitk.widgets.mixins.value_manager import ValueManager


class TestSetValueCheckableButtons(QtBaseTestCase):
    def _check(self, widget):
        self.track_widget(widget)
        widget.setChecked(False)
        ValueManager.set_value(widget, True)
        self.assertTrue(
            widget.isChecked(),
            f"{type(widget).__name__} not checked by set_value(True)",
        )
        ValueManager.set_value(widget, False)
        self.assertFalse(
            widget.isChecked(),
            f"{type(widget).__name__} not unchecked by set_value(False)",
        )

    def test_plain_qcheckbox(self):
        self._check(QtWidgets.QCheckBox())

    def test_qradiobutton(self):
        # autoExclusive radios can't be unchecked via setChecked(False) (Qt
        # keeps one checked in the group), so only assert the check direction.
        rb = QtWidgets.QRadioButton()
        rb.setAutoExclusive(False)
        self._check(rb)

    def test_checkable_qpushbutton(self):
        b = QtWidgets.QPushButton()
        b.setCheckable(True)
        self._check(b)

    def test_uitk_checkbox_sets_state_not_text(self):
        chk = CheckBox()
        self.track_widget(chk)
        chk.setChecked(False)
        ValueManager.set_value(chk, True)
        self.assertTrue(chk.isChecked(), "uitk CheckBox not checked by set_value")
        # The value must NOT have leaked into the rich-text label.
        self.assertNotIn("True", chk.text())

    def test_string_truthy_values(self):
        chk = QtWidgets.QCheckBox()
        self.track_widget(chk)
        for s in ("true", "1", "yes", "on"):
            chk.setChecked(False)
            ValueManager.set_value(chk, s)
            self.assertTrue(chk.isChecked(), f"set_value({s!r}) should check")
        for s in ("false", "0", "no", "off"):
            chk.setChecked(True)
            ValueManager.set_value(chk, s)
            self.assertFalse(chk.isChecked(), f"set_value({s!r}) should uncheck")

    def test_checkable_qgroupbox(self):
        # QGroupBox is not a QAbstractButton (no setText to shadow it); it must
        # still route through the later setChecked branch.
        g = QtWidgets.QGroupBox()
        g.setCheckable(True)
        self.track_widget(g)
        g.setChecked(False)
        ValueManager.set_value(g, True)
        self.assertTrue(g.isChecked())
        ValueManager.set_value(g, False)
        self.assertFalse(g.isChecked())

    def test_noncheckable_pushbutton_still_takes_text(self):
        # Plain (non-checkable) push buttons must keep their text behavior.
        b = QtWidgets.QPushButton()
        self.track_widget(b)
        ValueManager.set_value(b, "Hello")
        self.assertEqual(b.text(), "Hello")


if __name__ == "__main__":
    unittest.main()
