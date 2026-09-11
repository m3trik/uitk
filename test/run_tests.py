# !/usr/bin/python
# coding=utf-8
"""UITK Test Suite Runner

This module discovers and runs all tests in the UITK test suite,
collecting results and outputting to a log file.

Usage:
    python run_all_tests.py              # Run all tests with console output
    python run_all_tests.py --log        # Run all tests and save to log file
    python run_all_tests.py --verbose    # Run with verbose output
    python run_all_tests.py --quiet      # Run with minimal output
    python run_all_tests.py --no-badge   # Skip updating the README badge
"""

import sys
import os
import unittest
import logging
import argparse
import faulthandler
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Optional, Sequence

import pythontk as ptk

# Dump a native traceback if Qt segfaults (e.g. during teardown) — otherwise
# a crash surfaces only as an unexplained 0xC0000005 exit code on Windows.
faulthandler.enable()

# Windows consoles default to cp1252, which can't encode characters test
# docstrings legitimately use ("→"); unittest's printErrors then raises
# UnicodeEncodeError MID-REPORT, eating the failure list and the summary.
# errors="replace" keeps the report flowing no matter the console codepage.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(errors="replace")
        except (ValueError, OSError):
            pass  # detached/duplicated stream — leave it be

# Add package root to path
PACKAGE_ROOT = Path(__file__).parent.parent.absolute()
TEST_DIR = Path(__file__).parent
LOG_DIR = TEST_DIR / "logs"
# uitk keeps two front doors (the repo landing page and the packaged docs one);
# both carry the badge row, so both get stamped.
README_PATHS = (PACKAGE_ROOT / "README.md", PACKAGE_ROOT / "docs" / "README.md")

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

# AFTER the sys.path setup above, not with the stdlib imports: conftest
# lives in TEST_DIR, so importing it earlier only works by the accident
# of Python putting a script's own directory on sys.path -- which does
# not hold when this module is imported by path (test_run_tests.py does
# exactly that). QtWait.FLAKY_MARKER lets _print_summary count
# deliberately-gated tests apart from ordinary environment skips.
from conftest import QtWait  # noqa: E402


class TestResult:
    """Container for test result data."""

    def __init__(
        self,
        name: str,
        status: str,
        duration: float = 0.0,
        message: Optional[str] = None,
    ):
        self.name = name
        self.status = status  # 'passed', 'failed', 'error', 'skipped'
        self.duration = duration
        self.message = message

    def __repr__(self):
        return f"TestResult({self.name!r}, {self.status!r})"


class TestSuiteRunner:
    """Runs the complete UITK test suite and collects results."""

    def __init__(
        self,
        verbosity: int = 2,
        log_to_file: bool = False,
        update_badge: bool = True,
        modules: Optional[Sequence[str]] = None,
    ):
        self.verbosity = verbosity
        self.log_to_file = log_to_file
        self.update_badge = update_badge
        # Bare stems, `test_` prefix optional: {"sequencer", "test_sequencer"}
        # both select `test_sequencer.py`.
        self.modules = (
            {m[5:] if m.startswith("test_") else m for m in modules}
            if modules
            else None
        )
        self.results: list[TestResult] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging for the test runner."""
        self.logger = logging.getLogger("UITK.TestRunner")
        self.logger.setLevel(logging.DEBUG)
        # `getLogger` hands back the SAME logger to every instance, so handlers
        # installed by a previous construction are still attached and each one
        # re-emits the line. `test_run_tests` constructs the runner twice, which
        # left the real run printing its whole report THREE times (measured in a
        # full run: every summary line tripled). Own the list rather than
        # appending to whatever is on it.
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
            handler.close()

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if self.verbosity > 1 else logging.INFO)
        console_format = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)

        # File handler (if enabled)
        if self.log_to_file:
            LOG_DIR.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = LOG_DIR / f"test_run_{timestamp}.log"

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
            )
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)

            self.log_file_path = log_file
        else:
            self.log_file_path = None

    def discover_tests(self) -> unittest.TestSuite:
        """Discover all test modules in the test directory.

        With ``modules`` set, the discovered suite is FILTERED rather than
        re-discovered: keeping ``loader.discover``'s own module order is the
        whole point of a scoped run here, since the runs worth scoping are the
        ones chasing a cross-module interaction, and re-ordering the survivors
        would change the very thing under investigation. The badge is refused
        for such a run by ``StatusBadge.gate``, which compares the modules that
        ran against the ``test_*.py`` files on disk -- so no extra gating is
        needed here.
        """
        self.logger.info(f"Discovering tests in: {TEST_DIR}")

        loader = unittest.TestLoader()
        suite = loader.discover(
            start_dir=str(TEST_DIR),
            pattern="test_*.py",
            top_level_dir=str(TEST_DIR),
        )

        if self.modules:
            # One walk, one stem per test: validate the names BEFORE building
            # the filtered suite, so a typo costs nothing and reports fully.
            stems = [(self._module_stem(t), t) for t in self._iter_tests(suite)]
            found = {s for s, _ in stems}
            missing = sorted(self.modules - found)
            if missing:
                # Loud, because a typo would otherwise read as "those tests all
                # pass" -- the failure mode a scoped run can least afford.
                self.logger.error(
                    f"--modules named {len(missing)} unknown module(s): "
                    f"{', '.join(missing)}. Known: {', '.join(sorted(found))}"
                )
                raise SystemExit(2)
            suite = unittest.TestSuite(t for s, t in stems if s in self.modules)
            self.logger.info(f"Scoped to: {', '.join(sorted(self.modules))}")

        test_count = sum(1 for _ in self._iter_tests(suite))
        self.logger.info(f"Discovered {test_count} tests")

        return suite

    @staticmethod
    def _module_stem(test) -> str:
        """``test_sequencer.TestX.test_y`` -> ``sequencer``.

        Reads the class's ``__module__``, with one special case that matters: a
        module that fails to IMPORT is represented by a synthetic
        ``unittest.loader._FailedTest`` whose ``__module__`` is therefore
        ``unittest.loader``, and whose id is
        ``unittest.loader._FailedTest.<module>`` -- so the module name lives in
        the METHOD name, not the leading segment. Get this wrong and a scoped
        run silently drops the very import error it was called to look at,
        reporting "0 failures" for a module that never loaded.
        """
        mod = type(test).__module__
        if mod == "unittest.loader":  # _FailedTest: the module did not import
            mod = getattr(test, "_testMethodName", "") or test.id()
        mod = mod.rsplit(".", 1)[-1]
        return mod[5:] if mod.startswith("test_") else mod

    def _iter_tests(self, suite):
        """Iterate over all tests in a suite recursively."""
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                yield from self._iter_tests(item)
            else:
                yield item

    def run(self) -> bool:
        """Run the complete test suite.

        Returns:
            bool: True if all tests passed, False otherwise.
        """
        self.start_time = datetime.now()
        self.logger.info("=" * 70)
        self.logger.info("UITK Test Suite")
        self.logger.info(f"Started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 70)

        # Discover and run tests
        suite = self.discover_tests()

        # Create a custom result collector
        stream = StringIO() if self.verbosity == 0 else sys.stdout
        runner = unittest.TextTestRunner(
            stream=stream,
            verbosity=self.verbosity,
            resultclass=_DetailedTestResult,
        )

        # unittest reports through `stream`, but product code does not: a bare
        # print(), or the traceback.print_exc() of an exception the product
        # swallowed, goes to the REAL stdout/stderr and was absent from the log
        # file -- so a failure whose only explanation was printed reached the
        # reader as a bare assertion diff. Tee both for the run; `stream` above
        # holds the ORIGINAL stdout object, so nothing is doubled.
        self._console = StringIO()
        real_out, real_err = sys.stdout, sys.stderr
        sys.stdout = ptk.TeeStream(real_out, self._console)
        sys.stderr = ptk.TeeStream(real_err, self._console)
        try:
            result = runner.run(suite)
        finally:
            # In a finally so a runner crash cannot leave the process writing
            # into a buffer nobody reads.
            sys.stdout, sys.stderr = real_out, real_err

        # Collect results
        self._collect_results(result)

        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()

        # Print summary
        self._print_summary(result, duration)

        # Update README badge
        if self.update_badge:
            self._update_readme_badge(result)

        # Write log file summary
        if self.log_to_file and self.log_file_path:
            self._write_log_summary(result, duration)

        return result.wasSuccessful()

    def _collect_results(self, result: unittest.TestResult):
        """Collect results from the test run."""
        # Successful tests
        for test in getattr(result, "successes", []):
            self.results.append(
                TestResult(
                    name=str(test),
                    status="passed",
                )
            )

        # Failed tests
        for test, traceback in result.failures:
            self.results.append(
                TestResult(
                    name=str(test),
                    status="failed",
                    message=traceback,
                )
            )

        # Errors
        for test, traceback in result.errors:
            self.results.append(
                TestResult(
                    name=str(test),
                    status="error",
                    message=traceback,
                )
            )

        # Skipped tests
        for test, reason in result.skipped:
            self.results.append(
                TestResult(
                    name=str(test),
                    status="skipped",
                    message=reason,
                )
            )

    def _print_summary(self, result: unittest.TestResult, duration: float):
        """Print a summary of the test run."""
        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info("TEST SUMMARY")
        self.logger.info("=" * 70)

        total = result.testsRun
        passed = total - len(result.failures) - len(result.errors) - len(result.skipped)
        failed = len(result.failures)
        errors = len(result.errors)
        skipped = len(result.skipped)

        self.logger.info(f"Total:   {total}")
        self.logger.info(f"Passed:  {passed}")
        self.logger.info(f"Failed:  {failed}")
        self.logger.info(f"Errors:  {errors}")
        self.logger.info(f"Skipped: {skipped}")

        # A DELIBERATELY GATED test is not an ordinary skip: it is a test that
        # could not run because a resource this process does not own was
        # unavailable (the machine-global OS clipboard, say). Rolled into the
        # skip count it is invisible, which is the whole failure mode this
        # suite was fixed for -- a broken feature and a busy machine must not
        # look alike. QtWait.flaky stamps the reason so it can be counted here.
        gated = [
            (test, reason)
            for test, reason in result.skipped
            if QtWait.FLAKY_MARKER in str(reason)
        ]
        if gated:
            self.logger.warning(
                f"Flaky-gated: {len(gated)} (of the {skipped} skipped) -- a rise "
                "here means the environment is degrading, not the code"
            )
            for test, reason in gated:
                self.logger.info(f"  - {test}: {reason}")

        self.logger.info(f"Duration: {duration:.2f}s")

        # A module that imported but produced only skips still counts as run
        # (the standard keeps environment-gated skips green) -- but say so.
        skipped_only = sorted(
            set(getattr(result, "modules_ran", ()))
            - set(getattr(result, "modules_executed", ()))
        )
        if skipped_only:
            self.logger.warning(
                f"{len(skipped_only)} module(s) contributed only skips: "
                + ", ".join(skipped_only)
            )
        self.logger.info("")

        if result.wasSuccessful():
            self.logger.info("✓ All tests passed!")
        else:
            self.logger.warning("✗ Some tests failed")

            # Repeat the platform caveat HERE, next to the failures it explains.
            # __main__ already warns before the run, but that line is hundreds
            # of lines of dots away from the summary a reader actually acts on,
            # and a redirected run is usually read by tailing the end. Measured
            # 2026-09-10: a native-platform run reported
            # `test_the_card_stays_translucent_under_the_theme` as failing and
            # it was taken for a real defect, logged, and bisected across the
            # suite before the unset variable was noticed -- the startup warning
            # was present in both logs and read by nobody.
            if not os.environ.get("QT_QPA_PLATFORM"):
                self.logger.warning(
                    "   NOTE: QT_QPA_PLATFORM is unset, so this ran on the "
                    "NATIVE platform style. The rendering tests expect "
                    "'offscreen' (Fusion + light palette) and report failures "
                    "that are NOT in the code. Re-run with "
                    "QT_QPA_PLATFORM=offscreen before believing the list below."
                )

            if result.failures:
                self.logger.info("")
                self.logger.info("FAILURES:")
                for test, _ in result.failures:
                    self.logger.info(f"  - {test}")

            if result.errors:
                self.logger.info("")
                self.logger.info("ERRORS:")
                for test, _ in result.errors:
                    self.logger.info(f"  - {test}")

        self.logger.info("=" * 70)

        if self.log_file_path:
            self.logger.info(f"Log file: {self.log_file_path}")

    def _update_readme_badge(self, result: unittest.TestResult):
        """Update the test badge in the README file.

        Delegates to the ecosystem-wide SSoT (``ptk.StatusBadge``) so the count
        means the same thing here as in every sibling package: individual test
        cases, skips excluded. See m3trik/docs/TEST_BADGE_STANDARD.md.

        A partial run must not stamp the badge, whether it was scoped by argument
        or by environment (no Qt binding available, so those modules never
        import), so the write is gated on ``ptk.StatusBadge.gate``. The expected
        module set is *derived* from the ``test_*.py`` files on disk rather than
        recorded anywhere, so it can never go stale, and a refused stamp always
        names its reason -- mirroring mayatk's runner, which prints
        ``[INFO] Badge not updated (some modules did not run).`` The rule lives
        on ``StatusBadge`` rather than here because six runners stamp this badge:
        completeness has to be one implementation, not one per runner.
        """
        total = result.testsRun
        passed = total - len(result.failures) - len(result.errors) - len(result.skipped)
        failed = len(result.failures) + len(result.errors)

        # Never stamp a run the environment scoped down (see above).
        allowed, reason = ptk.StatusBadge.gate(
            ptk.StatusBadge.discover_module_names(TEST_DIR),
            getattr(result, "modules_ran", ()),
            passed,
            failed,
        )
        if not allowed:
            self.logger.warning(f"Badge not updated ({reason}).")
            return

        try:
            stamped = [
                p
                for p in README_PATHS
                if ptk.StatusBadge.update_test_badge(
                    p, passed, failed, test_dir=PACKAGE_ROOT / "test"
                )
            ]
            if not stamped:
                paths = ", ".join(str(p) for p in README_PATHS)
                self.logger.warning(
                    f"README badge not updated (missing or unwritable): {paths}"
                )
                return
            self.logger.info(
                f"Updated test badge in {len(stamped)} README(s): "
                f"{passed}/{total} tests passed"
            )
        except Exception as e:
            self.logger.warning(f"Failed to update README badge: {e}")

    def _write_log_summary(self, result: unittest.TestResult, duration: float):
        """Write a detailed summary to the log file."""
        if not self.log_file_path:
            return

        with open(self.log_file_path, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 70 + "\n")
            f.write("DETAILED RESULTS\n")
            f.write("=" * 70 + "\n\n")

            # Write all results by status
            for status in ["passed", "failed", "error", "skipped"]:
                status_results = [r for r in self.results if r.status == status]
                if status_results:
                    f.write(f"\n{status.upper()} ({len(status_results)}):\n")
                    f.write("-" * 40 + "\n")
                    for r in status_results:
                        f.write(f"  {r.name}\n")
                        if not r.message:
                            continue
                        # A traceback's payload -- the assertion that actually
                        # failed -- is its LAST lines, so truncating to the
                        # first 200 characters kept the "Traceback (most recent
                        # call last):" header and cut off the answer. Failures
                        # and errors are written whole; a skip reason is one
                        # line, so keeping its cap costs nothing.
                        message = r.message
                        if status == "skipped" and len(message) > 200:
                            message = message[:200] + "..."
                        for line in message.rstrip().splitlines():
                            f.write(f"    {line}\n")

            # What the run PRINTED, on failure only: a passing run's chatter
            # would bury the report, while a failing one's is often the only
            # record of why (see the tee in `run`).
            console = getattr(self, "_console", None)
            printed = console.getvalue().strip() if console else ""
            if printed and (result.failures or result.errors):
                f.write("\n" + "=" * 70 + "\n")
                f.write("CAPTURED CONSOLE OUTPUT (tail)\n")
                f.write("=" * 70 + "\n")
                for line in printed.splitlines()[-200:]:
                    f.write(f"  {line}\n")

            f.write("\n" + "=" * 70 + "\n")
            f.write(f"Completed at: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total duration: {duration:.2f}s\n")


class _DetailedTestResult(unittest.TextTestResult):
    """Extended TestResult that tracks successful tests.

    Also records which test modules actually ran, so a run the environment
    scoped down can be refused the README badge (see
    :meth:`TestSuiteRunner._update_readme_badge`).
    """

    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.successes = []  # test NAMES -- see addSuccess
        self.modules_ran = set()  # imported, and its cases were run
        self.modules_executed = set()  # produced at least one non-skipped case

    def _note_module(self, test, executed: bool):
        """Credit *test*'s module; a loader stand-in means it never ran."""
        if ptk.StatusBadge.is_import_standin(test):
            return
        name = ptk.StatusBadge.module_of(test)
        if not name:
            return
        self.modules_ran.add(name)
        if executed:
            self.modules_executed.add(name)

    def addSuccess(self, test):
        super().addSuccess(test)
        # The NAME, not the instance. unittest drops each case from the suite
        # as it runs (``TestSuite._removeTestAtIndex``) precisely so a finished
        # test -- and every widget it holds in an attribute -- can be collected;
        # appending the instance here defeated that and pinned all ~4k of them,
        # plus their widgets, for the whole run. Measured over 537 tests:
        # 263 live QWidget wrappers pinned vs 39 unpinned. `_collect_results`
        # only ever reads ``str(test)``, so this is behaviour-identical.
        self.successes.append(str(test))
        self._note_module(test, True)

    def addError(self, test, err):
        super().addError(test, err)
        self._note_module(test, True)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._note_module(test, True)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._note_module(test, True)

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._note_module(test, True)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._note_module(test, False)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="UITK Test Suite Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--log",
        action="store_true",
        help="Save results to a log file",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Minimal output",
    )
    parser.add_argument(
        "--no-badge",
        action="store_true",
        help="Skip updating the README badge",
    )
    parser.add_argument(
        "--modules",
        nargs="+",
        metavar="NAME",
        help=(
            "Run only these test modules, in the suite's own discovery order "
            "(bare stem or test_ prefix: 'sequencer' == 'test_sequencer'). "
            "For bisecting a cross-module interaction; the badge is refused "
            "for a partial run."
        ),
    )
    return parser.parse_args()


def main():
    """Main entry point for the test runner."""
    args = parse_args()

    # Determine verbosity
    if args.quiet:
        verbosity = 0
    elif args.verbose:
        verbosity = 2
    else:
        verbosity = 1

    # Run tests
    runner = TestSuiteRunner(
        verbosity=verbosity,
        log_to_file=args.log,
        update_badge=not args.no_badge,
        modules=args.modules,
    )

    success = runner.run()

    # Destroy any still-pending deleteLater() widgets while the interpreter is
    # fully alive. processEvents() never handles DeferredDelete, and test
    # classes that skip super().tearDown() bypass the conftest flush — whatever
    # is left would otherwise be torn down by Qt at process exit, where a
    # single event dispatched into a half-dead Python override segfaults.
    try:
        from qtpy import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is not None:
            # Destroying widgets can queue further deferred deletes (children,
            # buddies); a few passes settle the queue.
            for _ in range(3):
                QtCore.QCoreApplication.sendPostedEvents(
                    None, QtCore.QEvent.DeferredDelete
                )
                app.processEvents()
    except Exception:
        pass

    # Skips DLL_PROCESS_DETACH, where Qt's static destructors tear down leaked
    # objects and replaced a GREEN run's status with 0xC0000005 (observed live
    # 2026-07-25). os._exit does NOT skip it on Windows. The mechanics, and the
    # typed-HANDLE and single-wait lessons this file paid for, now live in the
    # shared primitive so every DCC-hosted runner gets them.
    #
    # Looked up defensively: `import pythontk` at module scope only proves SOME
    # pythontk is importable, and this runner is the release gate -- it
    # routinely runs against whichever build is installed. One predating
    # ProcessExit would raise AttributeError from the last statement of a
    # FINISHED run, reporting a green suite as a crash. Degrade to the old
    # behaviour instead; the exit code still stands, only the detach
    # suppression is lost.
    code = 0 if success else 1
    try:
        hard_exit = ptk.ProcessExit.hard_exit
    except AttributeError:
        os._exit(code)
    hard_exit(code)


if __name__ == "__main__":
    # The suite is written against the OFFSCREEN platform, whose default style
    # is Fusion with a light palette. Run it on a native platform and the
    # pixel-rendering tests are measuring a different widget stack: on Windows
    # that is the `windows11` style under the system's dark palette, where the
    # shortcut-overlay card comes out 344x202 of pale cyan instead of 380x336
    # of translucent dark. Same tree, 0 failures offscreen and 2 native -- and
    # nothing in the output says why, which is a whole debugging session.
    #
    # Warn rather than force it: a deliberate native run is a legitimate way to
    # check how the widgets actually look, and silently overriding the caller's
    # platform would make THAT impossible to ask for.
    if not os.environ.get("QT_QPA_PLATFORM"):
        print(
            "[WARN] QT_QPA_PLATFORM is unset, so this runs on the NATIVE "
            "platform style. The suite's rendering tests expect 'offscreen' "
            "(Fusion + light palette) and will report failures that are not "
            "in the code. Set QT_QPA_PLATFORM=offscreen for a clean run.",
            flush=True,
        )

    # Initialize QApplication global reference to prevent premature GC/teardown
    global_app = None
    try:
        from qtpy import QtWidgets

        global_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
            sys.argv
        )
    except ImportError:
        pass

    main()
