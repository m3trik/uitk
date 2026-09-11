#!/usr/bin/python
# coding=utf-8
"""Unit tests for the uitk test runner's README-badge guard.

A partial run must not stamp the badge -- whether it was scoped by argument or
by environment (no Qt binding installed, so whole modules never import). See
m3trik/docs/TEST_BADGE_STANDARD.md.

Covers:
- discover_module_names: the expected module set is derived from disk, never
  recorded, so it cannot go stale.
- module_of / is_import_standin: unittest's synthetic stand-ins
  (ModuleImportFailure / ModuleSkipped) are attributed to the module that
  failed, and never counted as a run.
- ``StatusBadge.gate``: refuses the stamp (with a printable reason) when a discovered
  module did not run, or when nothing ran at all.
- _DetailedTestResult: end-to-end module coverage over a real discovery of a
  short, purpose-built module set.
"""

import importlib.util
import logging
import sys
import unittest
from conftest import QtWait
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest import mock

import pythontk as ptk

TEST_DIR = Path(__file__).resolve().parent


class RunnerTestCase(unittest.TestCase):
    """Base: loads ``run_tests.py`` by path (it is a script, not a package)."""

    RUNNER_PATH = TEST_DIR / "run_tests.py"
    MODULE_NAME = "_uitk_run_tests_under_test"

    @classmethod
    def load_runner(cls):
        """Import the runner module from its file path."""
        spec = importlib.util.spec_from_file_location(cls.MODULE_NAME, cls.RUNNER_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @classmethod
    def setUpClass(cls):
        cls.runner = cls.load_runner()


class TestModuleDiscovery(RunnerTestCase):
    """The expected module set comes off disk, matching unittest discovery."""

    def setUp(self):
        self.artifacts = ptk.TempArtifacts(
            "run_tests_probe", dir=str(TEST_DIR / "temp_tests"), policy="scoped"
        )
        self.probe_dir = Path(self.artifacts.dir_path())

    def tearDown(self):
        self.artifacts.cleanup()

    def test_matches_test_star_py_only(self):
        for name in ("test_alpha.py", "test_beta.py", "conftest.py", "helpers.py"):
            (self.probe_dir / name).write_text("", encoding="utf-8")

        self.assertEqual(
            ptk.StatusBadge.discover_module_names(self.probe_dir),
            {"test_alpha", "test_beta"},
        )

    def test_empty_dir_yields_empty_set(self):
        self.assertEqual(ptk.StatusBadge.discover_module_names(self.probe_dir), set())

    def test_real_test_dir_is_non_trivial(self):
        """The live test tree must resolve to a real module set, not nothing."""
        found = ptk.StatusBadge.discover_module_names(TEST_DIR)
        self.assertIn(Path(__file__).stem, found)
        self.assertGreater(len(found), 1)


class TestBadgeGate(RunnerTestCase):
    """The gate refuses a stamp on any run that fell short of the module set."""

    def gate(self, expected, ran, passed=5, failed=0):
        return ptk.StatusBadge.gate(expected, ran, passed, failed)

    def test_allows_a_complete_run(self):
        allowed, reason = self.gate({"test_a", "test_b"}, {"test_a", "test_b"})
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_allows_a_complete_run_with_failures(self):
        """A red run still stamps -- the badge exists to report the failures."""
        allowed, _ = self.gate({"test_a"}, {"test_a"}, passed=0, failed=3)
        self.assertTrue(allowed)

    def test_refuses_when_a_module_did_not_run(self):
        allowed, reason = self.gate({"test_a", "test_mainwindow"}, {"test_a"})
        self.assertFalse(allowed)
        self.assertIn("test_mainwindow", reason)
        self.assertIn("1 of 2", reason)

    def test_reason_truncates_a_long_missing_list(self):
        expected = {f"test_{i}" for i in range(12)}
        allowed, reason = self.gate(expected, set())
        self.assertFalse(allowed)
        self.assertIn("+6 more", reason)
        self.assertLess(len(reason), 200)

    def test_refuses_when_nothing_ran(self):
        allowed, reason = self.gate({"test_a"}, {"test_a"}, passed=0, failed=0)
        self.assertFalse(allowed)
        self.assertIn("no test cases ran", reason)

    def test_extra_ran_modules_do_not_block(self):
        allowed, _ = self.gate({"test_a"}, {"test_a", "test_b"})
        self.assertTrue(allowed)


class TestModuleCoverage(RunnerTestCase):
    """End-to-end: a short module set run through real unittest discovery."""

    MODULES = {
        # Imports fine, one passing case.
        "test_probe_ok.py": (
            "import unittest\n"
            "class TestOk(unittest.TestCase):\n"
            "    def test_passes(self):\n"
            "        self.assertTrue(True)\n"
        ),
        # The missing-Qt case: a hard module-level import that is unavailable.
        "test_probe_broken.py": (
            "import _probe_missing_dependency_xyz  # noqa: F401\n"
            "import unittest\n"
            "class TestBroken(unittest.TestCase):\n"
            "    def test_never_runs(self):\n"
            "        pass\n"
        ),
        # The other idiom: a guarded import that skips the module wholesale.
        "test_probe_module_skip.py": (
            "import unittest\nraise unittest.SkipTest('no Qt binding')\n"
        ),
        # Imported and run, but every case is environment-gated.
        "test_probe_all_skipped.py": (
            "import unittest\n"
            "@unittest.skipUnless(False, 'no display')\n"
            "class TestGated(unittest.TestCase):\n"
            "    def test_gated(self):\n"
            "        pass\n"
        ),
    }

    def setUp(self):
        self.artifacts = ptk.TempArtifacts(
            "run_tests_probe", dir=str(TEST_DIR / "temp_tests"), policy="scoped"
        )
        self.probe_dir = Path(self.artifacts.dir_path())
        self._sys_path = list(sys.path)
        self._sys_modules = set(sys.modules)

    def tearDown(self):
        for name in set(sys.modules) - self._sys_modules:
            sys.modules.pop(name, None)
        sys.path[:] = self._sys_path
        self.artifacts.cleanup()

    def write_modules(self, *names):
        for name in names:
            (self.probe_dir / name).write_text(self.MODULES[name], encoding="utf-8")

    def run_probe(self):
        """Discover + run the probe dir, returning the runner's result object."""
        suite = unittest.TestLoader().discover(
            start_dir=str(self.probe_dir),
            pattern="test_*.py",
            top_level_dir=str(self.probe_dir),
        )
        return unittest.TextTestRunner(
            stream=StringIO(), verbosity=0, resultclass=self.runner._DetailedTestResult
        ).run(suite)

    def test_import_failure_and_module_skip_are_not_runs(self):
        self.write_modules(*self.MODULES)
        result = self.run_probe()

        self.assertEqual(
            result.modules_ran, {"test_probe_ok", "test_probe_all_skipped"}
        )
        self.assertEqual(result.modules_executed, {"test_probe_ok"})

    def test_gate_refuses_the_environment_scoped_run(self):
        self.write_modules(*self.MODULES)
        result = self.run_probe()
        expected = ptk.StatusBadge.discover_module_names(self.probe_dir)

        allowed, reason = ptk.StatusBadge.gate(
            expected, result.modules_ran, passed=1, failed=1
        )
        self.assertFalse(allowed)
        self.assertIn("test_probe_broken", reason)
        self.assertIn("test_probe_module_skip", reason)

    def test_gate_allows_a_run_where_every_module_ran(self):
        self.write_modules("test_probe_ok.py", "test_probe_all_skipped.py")
        result = self.run_probe()
        expected = ptk.StatusBadge.discover_module_names(self.probe_dir)

        allowed, reason = ptk.StatusBadge.gate(
            expected, result.modules_ran, passed=1, failed=0
        )
        self.assertTrue(allowed, reason)
        # A fully skipped module still counts as run (skips stay green), but the
        # runner names it -- it is the difference the warning reports.
        self.assertEqual(
            result.modules_ran - result.modules_executed, {"test_probe_all_skipped"}
        )


class TestRunLogFidelity(RunnerTestCase):
    """The log file has to carry the part of a failure that explains it.

    Two ways it did not: a message was truncated to its first 200 characters --
    which for a traceback is the "Traceback (most recent call last):" header and
    a frame or two, never the assertion at the end -- and anything the run
    PRINTED went to the console only, so a swallowed exception's
    traceback.print_exc() left no trace in the artifact that outlives the run.
    """

    LONG_TRACE = (
        "Traceback (most recent call last):\n"
        + '  File "widget.py", line 12, in build\n    layout.addWidget(w)\n' * 12
        + "AssertionError: PROBE-THE-ASSERTION-THAT-FAILED\n"
    )

    def setUp(self):
        # Deliberately NOT dir=test/temp_tests: that directory is on the
        # cloud-synced O: drive, where the sync client can still hold a file the
        # next line reads back -- measured here as a PermissionError under a
        # concurrent full suite. TempArtifacts defaults to the unsynced system
        # TEMP, which is the discriminator the 2026-08-10 backlog entry
        # measured, and it leaves this test measuring the writer rather than
        # the environment.
        self.artifacts = ptk.TempArtifacts("uitk_run_log", policy="scoped")
        self.log_path = Path(self.artifacts.path())

    def tearDown(self):
        self.artifacts.cleanup()

    def write_summary(self, printed="", failed=True):
        """Drive `_write_log_summary` alone, returning what it wrote.

        Built with `__new__`: the writer reads four attributes, and a real
        constructor would install logging handlers this test has no use for.
        """
        runner = self.runner.TestSuiteRunner.__new__(self.runner.TestSuiteRunner)
        runner.log_file_path = self.log_path
        runner.end_time = datetime.now()
        runner._console = StringIO(printed)
        runner.results = [
            self.runner.TestResult(
                name="test_probe", status="failed", message=self.LONG_TRACE
            ),
            self.runner.TestResult(
                name="test_skipped", status="skipped", message="x" * 500
            ),
        ]
        result = unittest.TestResult()
        if failed:
            result.failures = [("test_probe", self.LONG_TRACE)]
        runner._write_log_summary(result, 1.0)
        return self.log_path.read_text(encoding="utf-8")

    def test_the_assertion_survives_into_the_log(self):
        self.assertIn("PROBE-THE-ASSERTION-THAT-FAILED", self.write_summary())

    def test_a_skip_reason_is_still_capped(self):
        """The counterweight: writing everything whole is not the fix -- a skip
        reason is one line, and its cap keeps a pathological one from filling
        the log."""
        text = self.write_summary()
        self.assertIn("x" * 200 + "...", text)
        self.assertNotIn("x" * 300, text)

    def test_printed_output_reaches_the_log_on_failure(self):
        text = self.write_summary(printed="PROBE-PRINTED-EXPLANATION\n")
        self.assertIn("PROBE-PRINTED-EXPLANATION", text)

    def test_printed_output_is_left_out_of_a_clean_run(self):
        """A passing run's chatter would bury the report."""
        text = self.write_summary(printed="PROBE-PRINTED-EXPLANATION\n", failed=False)
        self.assertNotIn("PROBE-PRINTED-EXPLANATION", text)


class TestBadgeWiring(RunnerTestCase):
    """The gate is wired into the badge write, not merely importable."""

    def setUp(self):
        # Constructing a runner attaches a console handler to a module-level
        # logger; restore the original set so the rest of the suite is unchanged.
        self.logger = logging.getLogger("UITK.TestRunner")
        self._handlers = list(self.logger.handlers)

    def tearDown(self):
        self.logger.handlers[:] = self._handlers

    def make_result(self, modules_ran, tests_run=5):
        result = unittest.TestResult()
        result.testsRun = tests_run
        result.modules_ran = set(modules_ran)
        result.modules_executed = set(modules_ran)
        return result

    def make_runner(self):
        return self.runner.TestSuiteRunner(
            verbosity=0, log_to_file=False, update_badge=True
        )

    def test_partial_run_never_writes_the_badge(self):
        """Both front doors stay untouched when a module did not run."""
        with mock.patch.object(ptk.StatusBadge, "update_test_badge") as writer:
            self.make_runner()._update_readme_badge(
                self.make_result({"test_run_tests"})  # one module of many
            )
        writer.assert_not_called()

    def test_complete_run_writes_the_badge(self):
        modules = ptk.StatusBadge.discover_module_names(TEST_DIR)
        with mock.patch.object(ptk.StatusBadge, "update_test_badge") as writer:
            self.make_runner()._update_readme_badge(self.make_result(modules))

        self.assertEqual(writer.call_count, len(self.runner.README_PATHS))
        self.assertEqual(writer.call_args[0][1:3], (5, 0))  # passed, failed


class TestFlakyGatedReporting(RunnerTestCase):
    """A deliberately gated test must be countable, not buried in the skips.

    The suite's whole defect was that a broken feature and a busy machine
    looked identical in a green run. Most self-skips became bounded waits that
    FAIL, but a few genuinely depend on a resource this process does not own
    (the machine-global OS clipboard). Those stay skips -- and are stamped with
    ``QtWait.FLAKY_MARKER`` so a RISE in them is visible rather than silent.
    """

    def _summarise(self, skipped):
        """Drive the real ``_print_summary`` and capture what it logged."""
        import io as _io
        import logging

        result = unittest.TestResult()
        result.testsRun = len(skipped) + 1
        result.skipped = list(skipped)

        runner = self.runner.TestSuiteRunner()
        buffer = _io.StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setLevel(logging.INFO)
        runner.logger.addHandler(handler)
        self.addCleanup(runner.logger.removeHandler, handler)

        runner._print_summary(result, 1.0)
        return buffer.getvalue()

    def test_a_gated_skip_is_counted_apart_from_an_ordinary_one(self):
        output = self._summarise(
            [
                ("test_a", "no display available"),
                ("test_b", QtWait.FLAKY_MARKER + " OS clipboard held"),
            ]
        )
        self.assertIn("Flaky-gated: 1", output)
        self.assertIn("Skipped: 2", output, "a gate is still a skip in the total")
        self.assertIn("test_b", output, "the gated test must be named")

    def test_ordinary_skips_alone_report_no_gate_line(self):
        """No marker, no noise -- the line only appears when it means something."""
        output = self._summarise([("test_a", "no display available")])
        self.assertNotIn("Flaky-gated", output)


class TestModuleScoping(RunnerTestCase):
    """``--modules`` selects by module, including one that will not import.

    The scoping exists to bisect a cross-module interaction, so the two things
    that must not happen are selecting the wrong module and silently selecting
    NOTHING.
    """

    def _stem(self, test):
        return self.runner.TestSuiteRunner._module_stem(test)

    def test_a_normal_test_resolves_to_its_module_stem(self):
        class Sample(unittest.TestCase):
            def test_x(self):
                pass

        Sample.__module__ = "test_sequencer"
        self.assertEqual(self._stem(Sample("test_x")), "sequencer")

    def test_an_unimportable_module_is_still_matched_by_name(self):
        """Regression: a module that fails to IMPORT must stay selectable.

        ``unittest`` represents it as a synthetic ``_FailedTest`` whose
        ``__module__`` is ``unittest.loader``; the module's own name lives in
        the METHOD name. Reading the leading segment of ``id()`` instead yields
        ``"unittest"``, so the scoped run drops the import error and reports
        the module as having no failures -- silently green on a module that
        never loaded.
        """
        from unittest.loader import _make_failed_import_test

        made = _make_failed_import_test("test_broken_module", unittest.TestSuite)
        suite = made[0] if isinstance(made, tuple) else made
        failed = list(suite)[0]

        self.assertEqual(type(failed).__module__, "unittest.loader")
        self.assertEqual(self._stem(failed), "broken_module")

    def test_the_test_prefix_is_optional(self):
        runner = self.runner.TestSuiteRunner(modules=["sequencer", "test_widgets"])
        self.assertEqual(runner.modules, {"sequencer", "widgets"})

    def test_no_modules_means_the_whole_suite(self):
        self.assertIsNone(self.runner.TestSuiteRunner().modules)
        self.assertIsNone(self.runner.TestSuiteRunner(modules=[]).modules)

    def test_an_unknown_module_name_is_a_hard_error(self):
        """A typo must not read as "those tests all passed"."""
        runner = self.runner.TestSuiteRunner(modules=["definitely_not_a_module"])
        with self.assertRaises(SystemExit) as caught:
            runner.discover_tests()
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
