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


class TestCellWheelScrubbedSymmetry(_WheelScrubFixture):
    """Sub-notch quantization must be symmetric between up and down.

    Regression: ``steps = signed // 120`` (floor division) dropped a small
    upward scroll (+8 // 120 == 0 -> return) while emitting a full downward
    notch for the mirror-image scroll (-8 // 120 == -1). High-resolution /
    precision wheels and touchpads send such sub-notch angleDelta values, so
    scrolling up slowly did nothing while down slowly jumped a step. The fix
    truncates toward zero (``int(signed / 120)``).
    """

    def _steps_for(self, delta):
        tbl = self._make_table()
        captured = []
        tbl.cellWheelScrolled.connect(lambda *args: captured.append(args))
        tbl._emit_wheel_scrub(self._make_index(), self._make_wheel_event(delta=delta))
        return captured[0][2] if captured else 0

    def test_subnotch_up_and_down_are_symmetric(self):
        # Equal-magnitude sub-notch deltas must both quantize to 0 steps.
        self.assertEqual(self._steps_for(8), 0)
        self.assertEqual(self._steps_for(-8), 0)

    def test_over_one_notch_up_and_down_are_symmetric(self):
        # +121 and -121 must both quantize to a single notch (not 1 vs -2).
        self.assertEqual(self._steps_for(121), 1)
        self.assertEqual(self._steps_for(-121), -1)

    def test_standard_notches_unchanged(self):
        self.assertEqual(self._steps_for(120), 1)
        self.assertEqual(self._steps_for(-120), -1)
        self.assertEqual(self._steps_for(240), 2)
        self.assertEqual(self._steps_for(-240), -2)


class TestCellWheelScrubAccumulation(_WheelScrubFixture):
    """Sub-notch deltas accumulate per cell until a full notch is reached.

    Regression: plain truncation left precision touchpads / free-spin wheels
    that only ever send sub-notch angleDeltas (e.g. +-8) permanently unable
    to scrub — every event quantized to 0 and the remainder was discarded.
    """

    def _scrub(self, tbl, captured, delta, index=None):
        tbl._emit_wheel_scrub(
            index if index is not None else self._make_index(),
            self._make_wheel_event(delta=delta),
        )
        return captured

    def test_repeated_subnotch_deltas_reach_a_notch(self):
        tbl = self._make_table()
        captured = []
        tbl.cellWheelScrolled.connect(lambda *args: captured.append(args))
        # 15 x +8 == 120: exactly one notch, emitted on the 15th event.
        for _ in range(14):
            self._scrub(tbl, captured, 8)
            self.assertEqual(captured, [])
        self._scrub(tbl, captured, 8)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][2], 1)

    def test_residual_carries_between_events(self):
        tbl = self._make_table()
        captured = []
        tbl.cellWheelScrolled.connect(lambda *args: captured.append(args))
        self._scrub(tbl, captured, 100)  # residual 100
        self.assertEqual(captured, [])
        self._scrub(tbl, captured, 100)  # 200 -> one notch, residual 80
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][2], 1)
        self._scrub(tbl, captured, 40)  # 80 + 40 = 120 -> second notch
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[1][2], 1)

    def test_opposite_direction_cancels_residual(self):
        tbl = self._make_table()
        captured = []
        tbl.cellWheelScrolled.connect(lambda *args: captured.append(args))
        self._scrub(tbl, captured, 100)
        self._scrub(tbl, captured, -100)  # residual back to 0, no emit
        self._scrub(tbl, captured, 100)
        self.assertEqual(captured, [])

    def test_cell_change_resets_residual(self):
        tbl = self._make_table()
        captured = []
        tbl.cellWheelScrolled.connect(lambda *args: captured.append(args))
        self._scrub(tbl, captured, 100)  # residual 100 on cell (0, 0)
        # Different cell: residual must NOT carry over (100 + 40 != notch).
        self._scrub(tbl, captured, 40, index=self._make_index(row=1))
        self.assertEqual(captured, [])


if __name__ == "__main__":
    unittest.main()
