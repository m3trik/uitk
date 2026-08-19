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


if __name__ == "__main__":
    unittest.main()
