# !/usr/bin/python
# coding=utf-8
"""Base test configuration and utilities for UITK test suite.

This module provides common test infrastructure, fixtures, and utilities
used across all UITK test modules.
"""

import sys
import os
import logging
from pathlib import Path
from typing import Optional, Union
from unittest import TestCase

# Add package root and test directory to path for imports
PACKAGE_ROOT = Path(__file__).parent.parent.absolute()
TEST_DIR = Path(__file__).parent.absolute()
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))


def setup_qt_application():
    """Ensure a QApplication instance exists for Qt-based tests.

    Returns:
        QApplication: The existing or newly created QApplication instance.
    """
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


class BaseTestCase(TestCase):
    """Base test case with common setup and utilities for UITK tests."""

    # Class-level logger
    logger: Optional[logging.Logger] = None

    @classmethod
    def setUpClass(cls):
        """Set up class-level resources."""
        cls.logger = logging.getLogger(cls.__name__)
        cls.logger.setLevel(logging.DEBUG)

    @classmethod
    def tearDownClass(cls):
        """Clean up class-level resources."""
        pass

    def setUp(self):
        """Set up test fixtures."""
        self.test_name = self._testMethodName
        if self.logger:
            self.logger.debug(f"Starting test: {self.test_name}")

    def tearDown(self):
        """Tear down test fixtures."""
        if self.logger:
            self.logger.debug(f"Completed test: {self.test_name}")


class QtBaseTestCase(BaseTestCase):
    """Base test case for Qt widget tests.

    Provides automatic QApplication setup and widget cleanup.
    """

    app = None
    _widgets_to_cleanup = None

    @classmethod
    def setUpClass(cls):
        """Set up Qt application for the test class."""
        super().setUpClass()
        cls.app = setup_qt_application()

    def setUp(self):
        """Set up test fixtures with widget tracking."""
        super().setUp()
        self._widgets_to_cleanup = []

    # Drain the Qt event queue between tests so DeferredDelete events fire
    # inside tearDown instead of piling up across tests. Without this drain,
    # under PySide6 + offscreen QPA on Linux the backlog eventually SIGSEGVs
    # inside C++ event filters when a later test calls processEvents() and
    # Qt tries to deliver events to mid-destruction widgets. Set False on
    # subclasses that intentionally rely on cross-method Qt state (e.g.
    # input-sequence integration tests).
    _drain_qt_events_in_teardown: bool = True

    @staticmethod
    def _drain_qt_events(passes: int = 3) -> None:
        """Flush the Qt event queue (DeferredDelete, posted, timer events) so
        they fire here rather than leaking into another test. Used by tearDown
        (default), and by input-sequence tests that drain in setUp instead (to
        isolate from a prior test's leftovers without advancing their own
        not-yet-built state)."""
        from qtpy import QtCore, QtWidgets

        for _ in range(passes):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)

    def tearDown(self):
        """Clean up widgets created during the test."""
        from qtpy import QtWidgets

        super().tearDown()
        # Release any lingering mouse grab so it can't leak into the next test.
        # A test (or production code under test) that grabs the mouse and is
        # torn down without releasing leaves a dangling grabber — frequently on
        # a widget that's about to be deleted below — which non-deterministically
        # corrupts grab/hover/handoff assertions in whichever test happens to run
        # next. Releasing here, for every Qt test, fixes that class of
        # order-dependent flake at its root (rather than per-class tearDowns).
        grabber = QtWidgets.QWidget.mouseGrabber()
        if grabber is not None:
            try:
                grabber.releaseMouse()
            except RuntimeError:  # grabber already mid-destruction
                pass
        if self._widgets_to_cleanup:
            for widget in self._widgets_to_cleanup:
                try:
                    widget.deleteLater()
                except RuntimeError:
                    # Widget may already be deleted
                    pass
            self._widgets_to_cleanup.clear()
        if self._drain_qt_events_in_teardown:
            self._drain_qt_events()
        # Actually destroy deleteLater()'d widgets NOW. processEvents() never
        # handles DeferredDelete (Qt processes those only in a real event loop
        # or via an explicit sendPostedEvents call), so without this every
        # widget "deleted" above survives until process exit — where Qt's
        # static teardown destroys ~the whole suite's widgets at once and a
        # single event dispatched into a half-dead Python override segfaults
        # the runner (observed: Sequencer.event AV at exit, 0xC0000005).
        from qtpy import QtCore

        QtCore.QCoreApplication.sendPostedEvents(
            None, QtCore.QEvent.DeferredDelete
        )

    def track_widget(self, widget):
        """Register a widget for automatic cleanup.

        Args:
            widget: A Qt widget to be cleaned up after the test.

        Returns:
            The widget (for chaining).
        """
        if self._widgets_to_cleanup is not None:
            self._widgets_to_cleanup.append(widget)
        return widget

    # --- Visual Regression Helpers ---

    # Override in subclass or per-repo to change locations.
    SNAPSHOT_BASELINE_DIR: Optional[Path] = TEST_DIR / "snapshots"
    SNAPSHOT_OUTPUT_DIR: Optional[Path] = TEST_DIR / "temp_tests" / "snapshots"

    def capture_widget(self, widget, name: str) -> Path:
        """Capture a widget screenshot and save to the output directory.

        Args:
            widget: The Qt widget to capture.
            name: A short identifier (used as filename stem).

        Returns:
            Path to the saved PNG file.
        """
        from qtpy.QtWidgets import QApplication

        # Ensure pending events are processed so the widget is fully painted.
        QApplication.processEvents()

        output_dir = self.SNAPSHOT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{name}.png"
        pixmap = widget.grab()
        pixmap.save(str(path))
        return path

    def assert_visual_match(
        self,
        widget,
        name: str,
        *,
        threshold: float = 0.0,
        update_baseline: bool = False,
    ):
        """Assert that a widget's current appearance matches a stored baseline.

        On the first run (no baseline exists) or when *update_baseline* is True
        the current screenshot is saved as the new baseline and the assertion
        is skipped — so tests pass on the first run and baselines can be
        regenerated by setting the flag.

        Args:
            widget: The Qt widget to capture and compare.
            name: Baseline identifier (also the filename stem).
            threshold: Maximum allowed fraction (0.0–1.0) of pixels that may
                differ before the assertion fails. 0.0 means an exact match.
            update_baseline: If True, overwrite the baseline with the current
                screenshot and skip the comparison.

        Raises:
            AssertionError: If the images differ beyond *threshold*.
        """
        current_path = self.capture_widget(widget, name)

        baseline_dir = self.SNAPSHOT_BASELINE_DIR
        baseline_dir.mkdir(parents=True, exist_ok=True)
        baseline_path = baseline_dir / f"{name}.png"

        if update_baseline or not baseline_path.exists():
            import shutil

            shutil.copy2(current_path, baseline_path)
            return  # Nothing to compare yet.

        from PIL import Image, ImageChops

        baseline_img = Image.open(baseline_path).convert("RGBA")
        current_img = Image.open(current_path).convert("RGBA")

        if baseline_img.size != current_img.size:
            # Save diff artifacts for debugging before failing.
            self.fail(
                f"Visual size mismatch for '{name}': "
                f"baseline {baseline_img.size} vs current {current_img.size}. "
                f"Current screenshot saved at {current_path}"
            )

        diff = ImageChops.difference(baseline_img, current_img)
        # Count pixels where any channel differs.
        diff_pixels = sum(1 for px in diff.getdata() if px != (0, 0, 0, 0))
        total_pixels = baseline_img.size[0] * baseline_img.size[1]
        diff_ratio = diff_pixels / total_pixels if total_pixels else 0.0

        if diff_ratio > threshold:
            # Save the diff image for visual inspection.
            diff_path = self.SNAPSHOT_OUTPUT_DIR / f"{name}_diff.png"
            diff.save(str(diff_path))
            self.fail(
                f"Visual mismatch for '{name}': {diff_ratio:.4%} pixels differ "
                f"(threshold {threshold:.4%}). "
                f"Diff saved at {diff_path}"
            )

    @staticmethod
    def qtest():
        """Return the QTest module for synthetic input simulation.

        Usage::

            QTest = self.qtest()
            QTest.mouseClick(button, Qt.LeftButton)
            QTest.keyClicks(line_edit, "hello")
        """
        from qtpy.QtTest import QTest

        return QTest


# Test data paths (TEST_DIR already defined at top)
UITK_DIR = PACKAGE_ROOT / "uitk"
EXAMPLES_DIR = UITK_DIR / "examples"
WIDGETS_DIR = UITK_DIR / "widgets"


def get_test_resource_path(relative_path: str) -> Path:
    """Get the absolute path to a test resource.

    Args:
        relative_path: Path relative to the test directory.

    Returns:
        Absolute path to the resource.
    """
    return TEST_DIR / relative_path


def get_uitk_path(relative_path: str) -> Path:
    """Get the absolute path to a UITK module or resource.

    Args:
        relative_path: Path relative to the uitk package directory.

    Returns:
        Absolute path to the resource.
    """
    return UITK_DIR / relative_path
