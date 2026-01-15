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
import re
import unittest
import logging
import argparse
from datetime import datetime
from pathlib import Path
from io import StringIO
from typing import Optional

# Add package root to path
PACKAGE_ROOT = Path(__file__).parent.parent.absolute()
TEST_DIR = Path(__file__).parent
LOG_DIR = TEST_DIR / "logs"
README_PATH = PACKAGE_ROOT / "docs" / "README.md"

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
        """Update the test badge in the README file."""
        if not README_PATH.exists():
            self.logger.warning(
                f"README not found at {README_PATH}, skipping badge update"
            )
            return

        total = result.testsRun
        passed = total - len(result.failures) - len(result.errors) - len(result.skipped)
        failed = len(result.failures) + len(result.errors)

        # Determine badge color and status text
        if result.wasSuccessful():
            color = "brightgreen"
            status = f"{passed}%20passed"
        elif failed > 0:
            color = "red"
            status = f"{passed}%20passed%2C%20{failed}%20failed"
        else:
            color = "yellow"
            status = f"{passed}%20passed%2C%20{len(result.skipped)}%20skipped"

        # Create badge URL (shields.io format)
        badge_url = f"https://img.shields.io/badge/tests-{status}-{color}.svg"
        badge_markdown = f"[![Tests]({badge_url})](test/)"

        try:
            content = README_PATH.read_text(encoding="utf-8")

            # Pattern to match existing test badge or the position after version badge
            test_badge_pattern = r"\[!\[Tests\]\([^\)]+\)\]\([^\)]*\)\n?"

            if re.search(test_badge_pattern, content):
                # Replace existing test badge
                new_content = re.sub(test_badge_pattern, badge_markdown + "\n", content)
            else:
                # Insert after the Version badge line (or License badge if Version not found)
                version_pattern = r"(\[!\[Version\]\([^\)]+\)\]\([^\)]+\))\n"
                license_pattern = r"(\[!\[License[^\]]*\]\([^\)]+\)\]\([^\)]+\))\n"

                if re.search(version_pattern, content):
                    new_content = re.sub(
                        version_pattern,
                        r"\1\n" + badge_markdown + "\n",
                        content,
                    )
                elif re.search(license_pattern, content):
                    new_content = re.sub(
                        license_pattern,
                        r"\1\n" + badge_markdown + "\n",
                        content,
                    )
                else:
                    # Add at the very beginning
                    new_content = badge_markdown + "\n" + content

            README_PATH.write_text(new_content, encoding="utf-8")
            self.logger.info(
                f"Updated test badge in README: {passed}/{total} tests passed"
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

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
