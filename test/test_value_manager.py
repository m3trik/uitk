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
from uitk.managers.value_manager import ValueManager


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

    def test_noncheckable_pushbutton_label_is_not_state(self):
        # A plain (non-checkable) push button is an action/launcher: its label is
        # static .ui content (or derived from other state on init), never a
        # persistable value of its own. set_value must NOT overwrite the label —
        # else a stale stored value (e.g. a launcher renamed in the .ui, whose old
        # label was persisted) would clobber it on restore — and get_value reports
        # no value (only a *checkable* button carries one).
        b = QtWidgets.QPushButton("More..")
        self.track_widget(b)
        ValueManager.set_value(b, "Transform")
        self.assertEqual(
            b.text(), "More..", "plain button label must not be overwritten by state"
        )
        self.assertIsNone(
            ValueManager.get_value(b), "plain button has no persistable value"
        )


class TestSetValueNumeric(QtBaseTestCase):
    """set_value on numeric widgets."""

    def test_bad_value_leaves_widget_unchanged(self):
        """Regression: the direct set_value path reset the widget to
        minimum() on an unparseable value (42 -> 5); it must leave the
        current value untouched, matching _set_numeric_value."""
        sb = QtWidgets.QSpinBox()
        self.track_widget(sb)
        sb.setRange(5, 100)
        sb.setValue(42)
        ValueManager.set_value(sb, "not-a-number")
        self.assertEqual(sb.value(), 42)

    def test_string_numbers_accepted(self):
        """The direct path goes through _set_numeric_value, which handles
        string numbers like '7.0'."""
        sb = QtWidgets.QSpinBox()
        self.track_widget(sb)
        sb.setRange(0, 100)
        ValueManager.set_value(sb, "7.0")
        self.assertEqual(sb.value(), 7)


class TestTextChangedOnTextEdit(QtBaseTestCase):
    """``textChanged`` value ops must work for ``QTextEdit``.

    ``QTextEdit`` maps to ``textChanged`` in the default-signal table, but it
    has no ``text()`` — the signal-based getter returned ``None``, so a
    registered QTextEdit's state was never saved. The getter/setter must fall
    back to ``toPlainText()`` / ``setPlainText()``.
    """

    def test_get_value_by_signal_reads_plain_text(self):
        te = self.track_widget(QtWidgets.QTextEdit())
        te.setPlainText("session notes")
        self.assertEqual(
            ValueManager.get_value_by_signal(te, "textChanged"),
            "session notes",
        )

    def test_set_value_by_signal_writes_plain_text(self):
        te = self.track_widget(QtWidgets.QTextEdit())
        ValueManager.set_value_by_signal(te, "restored", "textChanged")
        self.assertEqual(te.toPlainText(), "restored")

    def test_round_trip_preserves_markup_ish_text(self):
        # setText() would interpret this as rich text and toPlainText() would
        # strip the tags — the plain-text setter must round-trip it verbatim.
        te = self.track_widget(QtWidgets.QTextEdit())
        literal = "<b>not markup</b>"
        ValueManager.set_value_by_signal(te, literal, "textChanged")
        self.assertEqual(te.toPlainText(), literal)

    def test_lineedit_path_unchanged(self):
        le = self.track_widget(QtWidgets.QLineEdit())
        ValueManager.set_value_by_signal(le, "abc", "textChanged")
        self.assertEqual(
            ValueManager.get_value_by_signal(le, "textChanged"), "abc"
        )


class TestStateManagerPersistence(QtBaseTestCase):
    """StateManager.save type gate + widget-default lifetime."""

    class _SpySettings:
        def __init__(self):
            self.stored = {}

        def setValue(self, key, value):
            self.stored[key] = value

        def sync(self):
            pass

    def test_checkstate_enum_persists(self):
        """Regression: PySide6's Qt.CheckState is not an int subclass, so
        the primitive-type gate silently dropped tri-state checkbox state.
        Enums must be coerced to their value and stored."""
        from qtpy import QtCore
        from uitk.managers.state_manager import StateManager

        settings = self._SpySettings()
        sm = StateManager(settings)

        cb = QtWidgets.QCheckBox()
        self.track_widget(cb)
        cb.setObjectName("triState")
        cb.setTristate(True)
        cb.restore_state = True
        cb.derived_type = QtWidgets.QCheckBox
        cb.default_signals = lambda: "stateChanged"
        cb.setCheckState(QtCore.Qt.CheckState.PartiallyChecked)

        sm.save(cb)
        self.assertEqual(
            settings.stored.get("triState/stateChanged"),
            QtCore.Qt.CheckState.PartiallyChecked.value,
        )

    def test_defaults_do_not_pin_widgets(self):
        """_defaults uses weak keys: a garbage-collected widget's entry
        must disappear instead of leaking (and later crashing reset_all)."""
        import gc
        from uitk.managers.state_manager import StateManager

        sm = StateManager(self._SpySettings())
        w = QtWidgets.QSpinBox()
        sm.set_default(w, 3)
        self.assertTrue(sm.has_default(w))
        del w
        gc.collect()
        self.assertEqual(len(sm._defaults), 0)


if __name__ == "__main__":
    unittest.main()
