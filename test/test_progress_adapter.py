# !/usr/bin/python
# coding=utf-8
"""Unit tests for SwitchboardUtilsMixin.progress_adapter.

The adapter bridges the footer's ``update(value, text)`` signature to the
two common downstream ``progress_callback`` shapes used across mayatk and
pythontk: ``(current, total, message)`` and ``(percent)``.

Run standalone: python -m test.test_progress_adapter
"""

import unittest

from conftest import BaseTestCase

from uitk.switchboard.utils import SwitchboardUtilsMixin


class TestProgressAdapter(BaseTestCase):
    """Tests for the progress_adapter static helper."""

    def setUp(self):
        super().setUp()
        # Records each call the wrapped update receives so we can assert
        # the exact args coming through after adaptation.
        self.calls = []

        def update(value=None, text=None):
            self.calls.append((value, text))
            return True

        self.update = update

    def test_three_arg_shape_forwards_current_and_message(self):
        """``cb(current, total, message)`` should pass current + message."""
        cb = SwitchboardUtilsMixin.progress_adapter(self.update)
        result = cb(25, 100, "Analyzing foo")
        self.assertTrue(result)
        self.assertEqual(self.calls, [(25, "Analyzing foo")])

    def test_single_arg_percent_shape_forwards_value_only(self):
        """``cb(percent)`` should pass the value, leaving text None."""
        cb = SwitchboardUtilsMixin.progress_adapter(self.update)
        cb(42.7)  # percent floats truncate via int() like a 0..100 bar tick
        self.assertEqual(self.calls, [(42, None)])

    def test_two_arg_shape_forwards_value_only(self):
        """``cb(current, total)`` should ignore total, pass current."""
        cb = SwitchboardUtilsMixin.progress_adapter(self.update)
        cb(3, 10)
        self.assertEqual(self.calls, [(3, None)])

    def test_none_value_passes_through(self):
        """``cb(None, ...)`` should hand None to update (marquee tick)."""
        cb = SwitchboardUtilsMixin.progress_adapter(self.update)
        cb(None, 100, "Working")
        self.assertEqual(self.calls, [(None, "Working")])

    def test_propagates_cancel_signal(self):
        """If update returns False, the adapter returns False (cancel)."""

        def cancelling_update(value=None, text=None):
            return False

        cb = SwitchboardUtilsMixin.progress_adapter(cancelling_update)
        self.assertFalse(cb(5, 10, "Working"))

    def test_non_numeric_value_falls_back_to_none(self):
        """Garbage first arg should not raise — value falls back to None."""
        cb = SwitchboardUtilsMixin.progress_adapter(self.update)
        cb("not-a-number", 10, "msg")
        self.assertEqual(self.calls, [(None, "msg")])


class _StubFooter:
    """Minimal footer-like object exposing ``set_progress_total``.

    The adapter reaches the footer via ``update.__self__`` — so to
    exercise the auto-sync path we need ``update`` to be a bound method
    of an object that has ``set_progress_total``.
    """

    def __init__(self):
        self.totals_set = []
        self.calls = []

    def set_progress_total(self, total):
        self.totals_set.append(total)

    def update(self, value=None, text=None):
        self.calls.append((value, text))
        return True


class TestProgressAdapterAutoSync(BaseTestCase):
    """The adapter auto-syncs the bar's max from the callback's total.

    Slots can therefore use ``sb.progress(text=...)`` with no upfront
    ``total`` — the first non-zero ``total`` argument from a downstream
    callback retotals the bar.
    """

    def setUp(self):
        super().setUp()
        self.footer = _StubFooter()

    def test_first_tick_with_total_syncs_bar(self):
        cb = SwitchboardUtilsMixin.progress_adapter(self.footer.update)
        cb(0, 130, "Updating: mat_0")
        # Bar's max should be retotalled to 130 on the first tick.
        self.assertEqual(self.footer.totals_set, [130])
        self.assertEqual(self.footer.calls, [(0, "Updating: mat_0")])

    def test_repeated_ticks_keep_calling_set_total(self):
        """``set_progress_total`` itself short-circuits when in-sync —
        the adapter just calls it every time and trusts the footer."""
        cb = SwitchboardUtilsMixin.progress_adapter(self.footer.update)
        cb(0, 130, "msg0")
        cb(65, 130, "msg65")
        cb(130, 130, "Done")
        self.assertEqual(self.footer.totals_set, [130, 130, 130])

    def test_zero_total_skips_sync(self):
        """``find_texture_files`` passes ``total=0`` (unknown count) —
        the adapter must not retotal the bar in that case."""
        cb = SwitchboardUtilsMixin.progress_adapter(self.footer.update)
        cb(5, 0, "Scanning: /some/dir")
        self.assertEqual(self.footer.totals_set, [])

    def test_single_arg_percent_skips_sync(self):
        """``MapCompositor`` passes a bare ``percent`` — no total
        argument means no retotalling."""
        cb = SwitchboardUtilsMixin.progress_adapter(self.footer.update)
        cb(42.5)
        self.assertEqual(self.footer.totals_set, [])
        self.assertEqual(self.footer.calls, [(42, None)])

    def test_unbound_update_does_not_crash(self):
        """``_NoOpProgressContext._noop`` is unbound — adapter must
        skip the sync path silently."""
        calls = []

        def update(value=None, text=None):
            calls.append((value, text))
            return True

        cb = SwitchboardUtilsMixin.progress_adapter(update)
        cb(50, 100, "msg")  # would crash if adapter assumed __self__
        self.assertEqual(calls, [(50, "msg")])


if __name__ == "__main__":
    unittest.main()
