# !/usr/bin/python
# coding=utf-8
"""Tests for ``conftest.QtWait`` — the shared bounded wait-then-FAIL helper.

Why this module exists: a Qt test that ends in a runtime ``self.skipTest(...)``
when a popup/menu/table "did not materialise" cannot tell a *busy machine* from
a *broken feature* — both produce a green run with zero failures, which is
precisely the case the test was written for. ``QtWait`` replaces those sites
with a wall-clock-bounded wait that FAILS on timeout, plus one explicit,
greppable marker for the rare site that genuinely cannot be made deterministic.
"""

import re
import time
import unittest
from unittest import mock
from pathlib import Path

from qtpy import QtCore
from conftest import QtBaseTestCase, QtWait, TEST_DIR


class TestQtWaitUntil(QtBaseTestCase):
    """``QtWait.until`` — pump until true, fail (never skip) on timeout."""

    def test_already_true_predicate_returns_its_value(self):
        """The truthy value is handed back, so a site can bind it directly."""
        self.assertEqual(QtWait.until(lambda: [1, 2], "never"), [1, 2])

    def test_already_true_predicate_does_not_pump(self):
        """The common case costs nothing: no event-loop passes are spent."""
        QtWait.until(lambda: True, "never")
        self.assertEqual(QtWait.last_pumps, 0)

    def test_deferred_condition_is_reached_by_pumping(self):
        """A condition satisfied only by a queued timer is reached — proving
        the wait pumps the event loop rather than merely polling."""
        flag = []
        QtCore.QTimer.singleShot(30, lambda: flag.append(1))
        self.assertTrue(QtWait.until(lambda: bool(flag), "timer never fired"))
        self.assertGreater(QtWait.last_pumps, 0, "must have pumped to get there")

    def test_timeout_raises_assertion_error_not_skip(self):
        """The whole point: an unmet condition is a FAILURE, never a skip."""
        with self.assertRaises(AssertionError) as ctx:
            QtWait.until(lambda: False, "popup never appeared", timeout_ms=50)
        self.assertNotIsInstance(
            ctx.exception, unittest.SkipTest, "a timeout must fail, not skip"
        )

    def test_timeout_message_names_the_condition_and_the_budget(self):
        """The failure has to be diagnosable without re-running under a debugger."""
        with self.assertRaises(AssertionError) as ctx:
            QtWait.until(lambda: False, "popup never appeared", timeout_ms=50)
        text = str(ctx.exception)
        self.assertIn("popup never appeared", text)
        self.assertIn("50", text, "the budget spent belongs in the message")

    def test_timeout_spends_the_whole_wall_clock_budget(self):
        """Bounded by wall clock (so a loaded machine gets more passes), not by
        a fixed pump count (which shrinks exactly when the machine is busy)."""
        start = time.monotonic()
        with self.assertRaises(AssertionError):
            QtWait.until(lambda: False, "never", timeout_ms=120)
        elapsed_ms = (time.monotonic() - start) * 1000
        self.assertGreaterEqual(elapsed_ms, 100, "must not give up early")

    def test_predicate_exception_propagates(self):
        """A broken predicate is a bug in the test, not a condition to wait on."""
        with self.assertRaises(ZeroDivisionError):
            QtWait.until(lambda: 1 / 0, "never", timeout_ms=50)


class TestQtWaitReached(QtBaseTestCase):
    """``QtWait.reached`` — the non-failing probe used to choose a policy."""

    def test_reached_returns_true_when_condition_holds(self):
        self.assertTrue(QtWait.reached(lambda: True))

    def test_reached_returns_false_instead_of_failing(self):
        self.assertFalse(QtWait.reached(lambda: False, timeout_ms=50))


class TestQtWaitFlakyMarker(QtBaseTestCase):
    """The last-resort escape hatch is explicit and countable."""

    def test_flaky_skips_with_a_greppable_marker(self):
        with self.assertRaises(unittest.SkipTest) as ctx:
            QtWait.flaky(self, "OS clipboard held by another process")
        text = str(ctx.exception)
        self.assertIn(QtWait.FLAKY_MARKER, text)
        self.assertIn("OS clipboard held by another process", text)

    def test_marker_is_a_stable_greppable_token(self):
        """A runner (or a human) counts these separately from real skips."""
        self.assertEqual(QtWait.FLAKY_MARKER, "FLAKY-GATED:")


class TestQtWaitPlatformProbe(QtBaseTestCase):
    """``is_offscreen`` picks the policy at the one site that still gates."""

    def test_reports_the_live_qpa_not_the_environment_guess(self):
        """Reads the QApplication's actual platform, so it stays correct when
        the QPA was chosen by an argument rather than ``QT_QPA_PLATFORM``."""
        from qtpy import QtWidgets

        app = QtWidgets.QApplication.instance()
        self.assertEqual(
            QtWait.is_offscreen(), app.platformName().lower() == "offscreen"
        )


class TestQtWaitPump(QtBaseTestCase):
    """``QtWait.pump`` — the calibrated replacement for hand-rolled loops."""

    def test_pump_delivers_queued_work(self):
        flag = []
        QtCore.QTimer.singleShot(0, lambda: flag.append(1))
        QtWait.pump()
        self.assertEqual(flag, [1])


class TestConvertedModulesDoNotSelfSkip(unittest.TestCase):
    """Regression guard for the 2026-08-03 backlog entry.

    These four modules carried 25 runtime ``self.skipTest(...)`` calls that
    downgraded themselves under CPU load (measured: 3244 passed idle vs 3236
    under load, 0 failures either way). Every one is now a bounded wait that
    fails. Re-introducing a bare runtime skip here is invisible in a green run,
    so it is pinned mechanically: the only permitted route to a skip is
    ``QtWait.flaky``, which stamps a countable marker.
    """

    CONVERTED = (
        "test_combobox.py",
        "test_menu.py",
        "test_shortcut_editor.py",
        "test_script_output.py",
    )
    _SKIP_CALL = re.compile(r"\.skipTest\s*\(")

    def test_no_runtime_self_skip_calls(self):
        offenders = []
        for name in self.CONVERTED:
            path = Path(TEST_DIR) / name
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if self._SKIP_CALL.search(line):
                    offenders.append(f"{name}:{lineno}: {line.strip()}")
        self.assertEqual(
            offenders,
            [],
            "runtime self-skips are indistinguishable from a broken feature — "
            "use QtWait.until (fails on timeout) or QtWait.flaky (countable "
            "marker):\n" + "\n".join(offenders),
        )


class TestRequireClipboard(QtBaseTestCase):
    """The shared OS-resource probe, on both sides of its one decision.

    Neither branch runs in a normal offscreen suite -- the clipboard round-trips,
    so the probe returns before either is reached. They are the whole point of
    the helper, so they are driven directly here: unified from two divergent
    copies, the one that was NOT maintained had degraded to a bare skipTest,
    which is what let a broken copy path read as an unavailable OS resource.
    """

    class _Case(unittest.TestCase):
        def runTest(self):  # pragma: no cover - a stand-in to fail/gate
            pass

    def _probe_with_dead_clipboard(self, offscreen):
        """Run the probe with the round-trip forced to fail."""
        # patch.object restores the DESCRIPTOR. Plain setattr put the bound
        # method back, silently turning `reached` from a classmethod into a
        # method (and `is_offscreen` into a function) for every later test
        # in the process.
        patcher = mock.patch.object(
            QtWait, "reached", classmethod(lambda cls, *a, **k: False)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        offscreen_patcher = mock.patch.object(
            QtWait, "is_offscreen", staticmethod(lambda: offscreen)
        )
        offscreen_patcher.start()
        self.addCleanup(offscreen_patcher.stop)
        QtWait.require_clipboard(self._Case())

    def test_offscreen_a_dead_clipboard_is_a_failure(self):
        """Offscreen QPA has an in-memory clipboard: a dead one is a regression."""
        with self.assertRaises(AssertionError) as caught:
            self._probe_with_dead_clipboard(offscreen=True)
        self.assertIn("regression", str(caught.exception))
        self.assertNotIn(
            QtWait.FLAKY_MARKER,
            str(caught.exception),
            "offscreen must never gate -- there is no OS resource to blame",
        )

    def test_on_a_real_platform_it_gates_and_is_countable(self):
        """The clipboard is machine-global there, so a holder is not our bug."""
        with self.assertRaises(unittest.SkipTest) as caught:
            self._probe_with_dead_clipboard(offscreen=False)
        self.assertIn(QtWait.FLAKY_MARKER, str(caught.exception))

    def test_a_working_clipboard_just_returns(self):
        """The ordinary path costs nothing and raises nothing."""
        self.assertIsNone(QtWait.require_clipboard(self._Case()))


if __name__ == "__main__":
    unittest.main()
