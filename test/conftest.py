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
from typing import Optional
from unittest import TestCase

# Add package root to path for imports
PACKAGE_ROOT = Path(__file__).parent.parent.absolute()
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))


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

    def tearDown(self):
        """Clean up widgets created during the test."""
        super().tearDown()
        if self._widgets_to_cleanup:
            for widget in self._widgets_to_cleanup:
                try:
                    widget.deleteLater()
                except RuntimeError:
                    # Widget may already be deleted
                    pass
            self._widgets_to_cleanup.clear()

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


# Test data paths
TEST_DIR = Path(__file__).parent
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
