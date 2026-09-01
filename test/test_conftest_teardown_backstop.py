# !/usr/bin/python
# coding=utf-8
"""The Qt widget flush must not be bypassable by a subclass ``tearDown``.

``QtBaseTestCase`` ends every Qt test by destroying tracked widgets and draining
the DeferredDelete queue. Its own comment records why: without it the widgets
survive to process exit, "where Qt's static teardown destroys ~the whole suite's
widgets at once and a single event dispatched into a half-dead Python override
segfaults the runner".

That flush used to live only in ``tearDown``, so a subclass overriding
``tearDown`` without chaining to ``super()`` would silently opt out of it. It is
now ALSO registered with ``addCleanup``, which unittest runs after ``tearDown``
whether or not the chain was intact -- and even where it does not call
``tearDown`` at all (a subclass ``setUp`` that raises), or where ``tearDown``
itself dies partway and strands the drain at the end of it.

**This guards an invariant; it does not repair a live defect.** Measured
2026-09-01: 89 subclasses override ``tearDown`` and all 89 chain via ``super()``,
and none override ``setUp`` without chaining -- so nothing bypasses the flush
today. These tests keep that true without anyone having to remember it, which is
the whole reason the registration is worth its line.

The stand-in cases are built INSIDE each test rather than at module scope: a
module-level ``TestCase`` subclass is collected and run as a test in its own
right by both unittest discovery and pytest, which would add phantom tests to
the suite and let their runs disturb the counters here.
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

setup_qt_application()


class TeardownBackstop(unittest.TestCase):
    """Drive a stand-in case through unittest and inspect what happened."""

    @staticmethod
    def _run(case_cls, name):
        case = case_cls(name)
        result = unittest.TestResult()
        case.run(result)
        return case, result

    def test_flush_runs_even_when_teardown_skips_super(self):
        """The shape no class has today: an override that never calls super()."""

        def tear_down(self):  # deliberately does NOT chain
            pass

        def test_body(self):
            from qtpy import QtWidgets

            self.track_widget(QtWidgets.QWidget())

        case_cls = type(
            "BypassesSuperTearDown",
            (QtBaseTestCase,),
            {"tearDown": tear_down, "test_body": test_body},
        )
        case, result = self._run(case_cls, "test_body")

        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])
        self.assertTrue(
            getattr(case, "_qt_torn_down", False),
            "the flush was bypassed by a tearDown that does not chain to super()",
        )
        self.assertFalse(
            case._widgets_to_cleanup,
            "tracked widgets survived the test that skipped super().tearDown()",
        )

    def test_the_flush_does_its_work_once_when_teardown_chains(self):
        """Both entry points fire; only the first may actually drain.

        Counts EFFECTIVE runs, not calls -- the latch is the thing under test,
        and a call count of 2 is the expected, correct shape.
        """
        effective = []

        def qt_teardown(self):
            already = getattr(self, "_qt_torn_down", False)
            QtBaseTestCase._qt_teardown(self)
            if not already:
                effective.append(1)

        def tear_down(self):
            # Explicit, not ``super(type(self), self)``: that form recurses
            # forever the moment anything subclasses the stand-in.
            QtBaseTestCase.tearDown(self)

        case_cls = type(
            "ChainsToSuperTearDown",
            (QtBaseTestCase,),
            {
                "_qt_teardown": qt_teardown,
                "tearDown": tear_down,
                "test_body": lambda self: None,
            },
        )
        _, result = self._run(case_cls, "test_body")

        self.assertEqual(result.errors, [])
        self.assertEqual(
            len(effective), 1, "the flush drained more than once for one test"
        )


if __name__ == "__main__":
    unittest.main()
