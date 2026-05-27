# !/usr/bin/python
# coding=utf-8
"""Unit tests for ``TableWidget`` wheel-scrub axis-swap + modifier signal.

Pins the two recent fixes:

1. **Axis-swap fallback** — when Alt is held the wheel ``angleDelta`` may
   arrive on ``.x()`` instead of ``.y()`` on some Qt builds; the table
   widget must read whichever axis carries the delta or Alt-held wheels
   silently no-op (the channels-cell symptom).

2. **Modifiers passed via signal** — the receiver shouldn't have to
   poll ``QApplication.keyboardModifiers()`` (which can race against
   the wheel event); the table emits the event's own modifier mask via
   the ``cellWheelScrolled`` signal.

Run standalone: python -m pytest test/test_table_widget_wheel.py -v
"""
import unittest
from unittest.mock import MagicMock

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore


class _WheelScrubFixture(QtBaseTestCase):
    """Shared fixture: a TableWidget with wheel-scrub enabled on column 0."""

    def _make_table(self):
        from uitk.widgets.tableWidget import TableWidget

        tbl = self.track_widget(TableWidget())
        tbl.setRowCount(1)
        tbl.setColumnCount(1)
        tbl.set_wheel_scrub_columns([0])
        return tbl

    def _make_index(self, row=0, col=0):
        # Real QModelIndex so the signal payload types are realistic.
        from qtpy import QtCore as _C

        idx = MagicMock(spec=_C.QModelIndex)
        idx.row.return_value = row
        idx.column.return_value = col
        idx.isValid.return_value = True
        return idx

    def _make_wheel_event(self, delta=120, axis="y", modifiers=None):
        event = MagicMock()
        if axis == "x":
            event.angleDelta.return_value.x.return_value = delta
            event.angleDelta.return_value.y.return_value = 0
        else:
            event.angleDelta.return_value.x.return_value = 0
            event.angleDelta.return_value.y.return_value = delta
        event.modifiers.return_value = (
            modifiers if modifiers is not None else QtCore.Qt.NoModifier
        )
        return event


class TestCellWheelScrubbedAxisSwap(_WheelScrubFixture):
    """Axis-swap fallback: Alt-transposed wheel events must still fire."""

    def test_y_axis_emits_signal(self):
        tbl = self._make_table()
        captured = []
        tbl.cellWheelScrolled.connect(lambda *args: captured.append(args))

        idx = self._make_index()
        event = self._make_wheel_event(delta=120, axis="y")
        tbl._emit_wheel_scrub(idx, event)

        self.assertEqual(len(captured), 1)
        row, col, steps, _mods = captured[0]
        self.assertEqual((row, col, steps), (0, 0, 1))

    def test_x_axis_alt_transposed_emits_signal(self):
        """Regression: Alt-held wheels transpose ``angleDelta`` from ``.y()``
        onto ``.x()`` on some Qt builds; the previous y-only check missed
        them entirely. The fallback must pick up the x-axis delta.
        """
        tbl = self._make_table()
        captured = []
        tbl.cellWheelScrolled.connect(lambda *args: captured.append(args))

        idx = self._make_index()
        event = self._make_wheel_event(
            delta=120, axis="x", modifiers=QtCore.Qt.AltModifier
        )
        tbl._emit_wheel_scrub(idx, event)

        self.assertEqual(len(captured), 1)
        row, col, steps, _mods = captured[0]
        self.assertEqual((row, col, steps), (0, 0, 1))

    def test_negative_delta_emits_negative_steps(self):
        tbl = self._make_table()
        captured = []
        tbl.cellWheelScrolled.connect(lambda *args: captured.append(args))

        idx = self._make_index()
        event = self._make_wheel_event(delta=-120, axis="y")
        tbl._emit_wheel_scrub(idx, event)

        self.assertEqual(len(captured), 1)
        _r, _c, steps, _mods = captured[0]
        self.assertEqual(steps, -1)

    def test_zero_delta_does_not_emit(self):
        tbl = self._make_table()
        captured = []
        tbl.cellWheelScrolled.connect(lambda *args: captured.append(args))

        idx = self._make_index()
        event = self._make_wheel_event(delta=0, axis="y")
        # Zero on x as well -- emulates a stale wheel event with no real delta.
        event.angleDelta.return_value.x.return_value = 0
        tbl._emit_wheel_scrub(idx, event)

        self.assertEqual(captured, [])


class TestCellWheelScrubbedModifiers(_WheelScrubFixture):
    """Modifiers passed via the signal -- receivers don't race-poll
    ``QApplication.keyboardModifiers()``.
    """

    def test_modifiers_payload_is_the_event_modifiers(self):
        tbl = self._make_table()
        captured = []
        tbl.cellWheelScrolled.connect(lambda *args: captured.append(args))

        idx = self._make_index()
        event = self._make_wheel_event(
            delta=120,
            modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier,
        )
        tbl._emit_wheel_scrub(idx, event)

        self.assertEqual(len(captured), 1)
        _r, _c, _steps, mods = captured[0]
        self.assertTrue(bool(mods & QtCore.Qt.ControlModifier))
        self.assertTrue(bool(mods & QtCore.Qt.ShiftModifier))
        self.assertFalse(bool(mods & QtCore.Qt.AltModifier))


if __name__ == "__main__":
    unittest.main()
