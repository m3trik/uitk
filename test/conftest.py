# !/usr/bin/python
# coding=utf-8
"""Base test configuration and utilities for UITK test suite.

This module provides common test infrastructure, fixtures, and utilities
used across all UITK test modules.
"""

import sys
import atexit
import shutil
import logging
import tempfile
from pathlib import Path
from typing import Optional
from unittest import TestCase

# Add package root and test directory to path for imports
PACKAGE_ROOT = Path(__file__).parent.parent.absolute()
TEST_DIR = Path(__file__).parent.absolute()
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))


def _sandbox_qsettings() -> str:
    """Keep the whole test process off the real ``QSettings`` store.

    uitk's *production* settings live in the real per-user store
    (``HKCU\\Software\\uitk\\shared`` on Windows, ``~/.config/uitk`` on
    Linux). Many tests construct ``SettingsManager()`` / ``QSettings(org,
    app)`` with production-ish names and then ``setValue`` / ``clear`` them —
    so without isolation a single ``pytest`` run reads, writes, and (worst of
    all) wipes the developer's live marking-menu bindings, widget state, and
    theme. Closing and relaunching the host DCC then "mysteriously" restores
    defaults: the suite emptied the store on its way out.

    The catch on Windows: ``QSettings(org, app)`` and ``QSettings(scope, org,
    app)`` *always* use ``NativeFormat`` (the registry). They ignore
    ``setDefaultFormat`` (which only governs the no-arg / parent-only
    constructors), and ``setPath`` is a documented no-op for ``NativeFormat``.
    The only reliable redirect is to rewrite those registry-bound overloads to
    the explicit ``IniFormat`` constructor — done here by swapping
    ``QtCore.QSettings`` for a thin subclass. ``setPath`` then steers the
    resulting ini files into a throwaway temp dir.

    Pass-through is deliberate for every other overload (explicit-format,
    ``QSettings(path, IniFormat)``, no-arg): those don't touch the shared
    native store. Subclassing (not a factory function) preserves
    ``QSettings.IniFormat`` enum access and ``isinstance(x, QSettings)``.

    Activated at *import* time (below) rather than via a pytest fixture so it
    protects direct ``unittest`` / ``mayapy`` runs too — every test module
    imports this conftest before defining its cases, and this must run before
    the first ``QSettings`` is constructed.
    """
    from qtpy import QtCore

    tmp = tempfile.mkdtemp(prefix="uitk_test_qsettings_")
    real = QtCore.QSettings
    ini, user = real.IniFormat, real.UserScope

    # IniFormat files for both scopes land in the temp dir.
    for scope in (real.UserScope, real.SystemScope):
        real.setPath(ini, scope, tmp)
    # Load-bearing for the no-arg / QObject-parent constructors (which the
    # subclass below forwards verbatim): they pick up IniFormat from here.
    real.setDefaultFormat(ini)

    class _SandboxedQSettings(real):
        """Force the NativeFormat (registry-bound) overloads onto temp ini.

        Two Qt constructor overloads silently bind to the real native store
        and ignore ``setDefaultFormat`` / ``setPath``:
        ``QSettings(org, app[, parent])`` and ``QSettings(scope, org,
        app[, parent])``. Both are rewritten to the explicit ``IniFormat``
        constructor so no test can reach the real ``HKCU\\Software\\uitk``
        hive. Every other overload (explicit-format, ``QSettings(path,
        IniFormat)``, and the no-arg / parent-only forms already steered by
        ``setDefaultFormat`` above) passes through unchanged.
        """

        def __init__(self, *args, **kwargs):
            if (
                len(args) >= 2
                and isinstance(args[0], str)
                and isinstance(args[1], str)
            ):
                # (org, app[, parent]) -> (Ini, UserScope, org, app[, parent])
                super().__init__(ini, user, *args, **kwargs)
            elif (
                len(args) >= 3
                and isinstance(args[1], str)
                and isinstance(args[2], str)
            ):
                # (scope, org, app[, parent]) -> (Ini, scope, org, app[, parent])
                super().__init__(ini, *args, **kwargs)
            else:
                super().__init__(*args, **kwargs)

    QtCore.QSettings = _SandboxedQSettings
    atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))
    return tmp


# Sandbox QSettings storage for the entire test process. See the docstring
# for why this is import-time and not a fixture.
QSETTINGS_SANDBOX_DIR = _sandbox_qsettings()


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


# ---------------------------------------------------------------------------
# First-paint stability harness
#
# uitk's anti-flash doctrine: all visual state must be FINAL by the time a
# window's show() returns — anything corrected on a later event-loop tick
# painted the un-final state first (the init "flash"). These helpers snapshot
# a widget tree at show-return and assert nothing visible mutates while the
# deferred-timer backlog drains.
#
# The deterministic flash reproducer (style-independent, offscreen-safe) is a
# PROPERTY-SELECTOR stylesheet: dynamic-property rules ([class="tight"]) do
# NOT re-evaluate when the property is set after the QSS is installed — the
# widget keeps the un-matched metrics until an unpolish/polish cycle (which
# show performs implicitly, hence the visible correction). Type-selector
# rules re-resolve immediately on modern Qt and CANNOT reproduce the bug.
# ---------------------------------------------------------------------------

# Two-rule reproducer: the type rule is the "floor" every button gets; the
# property rule is the collapsed final state that only applies post-repolish.
FIRST_PAINT_QSS = (
    "QPushButton { min-width: 80px; }\n"
    'QPushButton[class="tight"] { min-width: 8px; padding: 0px; font-size: 6pt; }'
)


def _widget_path(w, root):
    """Stable-ish identity for a widget within *root*'s tree."""
    parts = []
    cur = w
    while cur is not None and cur is not root:
        parent = cur.parentWidget()
        name = cur.objectName()
        if not name:
            # Disambiguate unnamed siblings by class + index within parent.
            sibs = (
                [c for c in parent.children() if type(c) is type(cur)]
                if parent is not None
                else [cur]
            )
            try:
                name = f"{type(cur).__name__}#{sibs.index(cur)}"
            except ValueError:
                name = type(cur).__name__
        parts.append(name)
        cur = parent
    parts.append(root.objectName() or type(root).__name__)
    return "/".join(reversed(parts))


def visual_state_snapshot(root, ignore=()):
    """Snapshot (visibility, geometry, icon) for every widget under *root*.

    ``ignore`` is an iterable of substrings — any widget whose path contains
    one is skipped (throwaway internals).
    """
    from qtpy import QtWidgets

    state = {}
    for w in [root] + root.findChildren(QtWidgets.QWidget):
        try:
            path = _widget_path(w, root)
            if any(s in path for s in ignore):
                continue
            geo = w.geometry()
            icon_key = None
            if isinstance(w, QtWidgets.QAbstractButton) and not w.icon().isNull():
                icon_key = w.icon().cacheKey()
            state[path] = (
                w.isVisible(),
                (geo.x(), geo.y(), geo.width(), geo.height()),
                icon_key,
            )
        except RuntimeError:
            pass  # C++ side died mid-walk
    return state


def diff_visual_state(before, after):
    """Human-readable per-widget deltas between two snapshots."""
    lines = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            lines.append(f"  {key}: {before.get(key)} -> {after.get(key)}")
    return lines


def assert_stable_after_show(testcase, window, pumps=20, settle_ms=12, ignore=()):
    """Show *window*; assert no visible state mutates once show() returns.

    The snapshot taken synchronously at show-return is the state the first
    paint renders (uitk's contract); draining ``pumps`` event-loop passes
    then flushes every ``singleShot(0, ...)`` correction — any diff is a
    user-visible init flash.
    """
    from qtpy import QtCore, QtWidgets

    window.show()
    # Qt processes posted LayoutRequests BEFORE the first paint — flush them
    # so snapshot A is what the first paint actually renders. Without this,
    # a hand-built window's layout-assigned geometry (which lands pre-paint)
    # would read as a post-show "mutation" on styles with large native hints.
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.LayoutRequest)
    before = visual_state_snapshot(window, ignore=ignore)
    for _ in range(pumps):
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, settle_ms)
    after = visual_state_snapshot(window, ignore=ignore)
    delta = diff_visual_state(before, after)
    if delta:
        testcase.fail(
            "visible state mutated after show() returned (init flash):\n"
            + "\n".join(delta)
        )


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
