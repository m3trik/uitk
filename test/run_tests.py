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
from pathlib import Path
from io import StringIO
from typing import Optional

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
    ):
        self.verbosity = verbosity
        self.log_to_file = log_to_file
        self.update_badge = update_badge
        self.results: list[TestResult] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging for the test runner."""
        self.logger = logging.getLogger("UITK.TestRunner")
        self.logger.setLevel(logging.DEBUG)

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
        """Discover all test modules in the test directory."""
        self.logger.info(f"Discovering tests in: {TEST_DIR}")

        loader = unittest.TestLoader()
        suite = loader.discover(
            start_dir=str(TEST_DIR),
            pattern="test_*.py",
            top_level_dir=str(TEST_DIR),
        )

        # Count tests
        test_count = sum(1 for _ in self._iter_tests(suite))
        self.logger.info(f"Discovered {test_count} tests")

        return suite

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

        result = runner.run(suite)

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
        self.logger.info(f"Duration: {duration:.2f}s")
        self.logger.info("")

        if result.wasSuccessful():
            self.logger.info("✓ All tests passed!")
        else:
            self.logger.warning("✗ Some tests failed")

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
        """
        from pythontk.core_utils.status_badge import StatusBadge

        total = result.testsRun
        passed = total - len(result.failures) - len(result.errors) - len(result.skipped)
        failed = len(result.failures) + len(result.errors)

        try:
            stamped = [
                p
                for p in README_PATHS
                if StatusBadge.update_test_badge(
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
                        if r.message:
                            f.write(
                                f"    {r.message[:200]}...\n"
                                if len(r.message) > 200
                                else f"    {r.message}\n"
                            )

            f.write("\n" + "=" * 70 + "\n")
            f.write(f"Completed at: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total duration: {duration:.2f}s\n")


class _DetailedTestResult(unittest.TextTestResult):
    """Extended TestResult that tracks successful tests."""

    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.successes = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes.append(test)


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

    _hard_exit(0 if success else 1)


def _hard_exit(code: int) -> None:
    """Exit immediately, preserving *code* as the process exit status.

    Plain interpreter shutdown — and even ``os._exit`` on Windows (which still
    runs ``DLL_PROCESS_DETACH``, executing Qt's static destructors) — can
    segfault tearing down leaked Qt objects, replacing the exit code with
    0xC0000005. ``TerminateProcess`` skips detach callbacks entirely.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":
        import ctypes

        # HANDLE must be typed: ctypes' default c_int restype truncates
        # GetCurrentProcess()'s 64-bit pseudo-handle (-1) to 32 bits, and the
        # untyped round-trip handed TerminateProcess 0x00000000FFFFFFFF — an
        # invalid handle, so the kill failed DETERMINISTICALLY (returned 0 on
        # every probe run) and every run fell through to os._exit's
        # DLL_PROCESS_DETACH, the exact segfault surface this function exists
        # to skip. That's why green runs kept exiting 5 (0xC0000005's low
        # byte) despite both earlier parking fixes: the park was unreachable.
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.TerminateProcess.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        kernel32.TerminateProcess.restype = ctypes.c_int
        kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        kernel32.WaitForSingleObject.restype = ctypes.c_uint
        if kernel32.TerminateProcess(kernel32.GetCurrentProcess(), code):
            # TerminateProcess is asynchronous — it can return to this
            # thread while the kill is still in flight. Falling through to
            # os._exit here re-enters DLL_PROCESS_DETACH (the exact segfault
            # this function exists to skip) and clobbers the exit code with
            # 0xC0000005 (observed live: a green run reported as failed).
            # Park until the kill lands — with a SINGLE never-returning wait,
            # not a Sleep loop: the loop re-entered Python bytecode + ctypes
            # marshalling once per second inside the dying process, and that
            # execution surface is where an access violation clobbered a
            # green run's exit code with 0xC0000005 (shell-reported as 5)
            # despite this parking (observed live 2026-07-25).
            INFINITE = 0xFFFFFFFF
            while True:
                # Looped only against a spurious return (e.g. WAIT_FAILED):
                # falling through to os._exit would re-enter the detach
                # callbacks this function exists to skip.
                kernel32.WaitForSingleObject(kernel32.GetCurrentProcess(), INFINITE)
        # Only reachable when TerminateProcess reported failure (the park
        # never returns). Announce it — the untyped-handle bug hid behind
        # this silent fallback for two fix cycles.
        print(
            f"_hard_exit: TerminateProcess failed "
            f"(WinError {ctypes.get_last_error()}); falling back to os._exit — "
            "the exit code may be clobbered by DLL_PROCESS_DETACH teardown.",
            flush=True,
        )
    os._exit(code)


if __name__ == "__main__":
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
