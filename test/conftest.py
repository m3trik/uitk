# !/usr/bin/python
# coding=utf-8
"""Base test configuration and utilities for UITK test suite.

This module provides common test infrastructure, fixtures, and utilities
used across all UITK test modules.
"""

import os
import sys
import time
import logging
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


# Keep the whole test process off the real QSettings + preset stores. The redirect itself lives in
# the shipped package (``uitk.testing``) because those stores are process-wide and shared by every
# repo in the ecosystem, so tentacle/mayatk/blendertk suites need the identical one — see that
# module for why the Windows NativeFormat overloads have to be rewritten.
#
# Import-time, not a pytest fixture: it must run before the first ``QSettings`` is constructed, and
# it has to protect direct ``unittest`` / ``mayapy`` runs too (every test module imports this
# conftest before defining its cases).
from uitk.testing import TestSandbox  # noqa: E402

QSETTINGS_SANDBOX_DIR, PRESETS_SANDBOX_DIR = TestSandbox.activate()


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


# ---------------------------------------------------------------------------
# Bounded waits — the one primitive every Qt test uses to reach a condition
#
# Two failure modes this replaces, both of which produce a GREEN run:
#
#   1. ``if not popup.isVisible(): self.skipTest("offscreen QPA did not show
#      the popup")`` — a runtime self-skip. Measured 2026-08-02/03 across four
#      full uitk runs: 3244 passed on an idle machine, 3236 on three runs made
#      while other suites competed for the CPU, 0 failures every time. Eight
#      tests quietly downgraded themselves under load — and a genuinely broken
#      popup would downgrade them the same way, with the same green badge. A
#      test that cannot tell "too slow" from "broken" carries no signal in
#      exactly the case it was written for.
#   2. ``for _ in range(20): processEvents()`` — an uncalibrated hand-rolled
#      pump. Too few passes on a loaded machine (flake), too many on an idle
#      one (wall-clock waste), and never a diagnosis when the condition is
#      simply never reached.
#
# ``QtWait.until`` fixes both: it spends a *wall-clock* budget (so a loaded
# machine gets more passes, not fewer) and raises ``AssertionError`` when the
# budget runs out. Slow still passes; broken now fails.
# ---------------------------------------------------------------------------


class _QtWaitInternal:
    """Spin mechanics behind :class:`QtWait`; not part of the test-facing API."""

    @staticmethod
    def _process(slice_ms):
        """One event-loop pass, bounded so a busy queue cannot stall the wait."""
        from qtpy import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents(QtCore.QEventLoop.AllEvents, slice_ms)

    @classmethod
    def _spin(cls, predicate, timeout_ms, poll_ms):
        """Pump until *predicate* is truthy or the wall clock runs out.

        Returns ``(value, elapsed_ms, pumps)``. The predicate is evaluated
        BEFORE the first pump so an already-satisfied condition costs nothing,
        and the loop yields the CPU between passes (``processEvents`` returns
        immediately on an empty queue) — a hot spin would starve the very
        machine whose slowness is being waited out.
        """
        start = time.monotonic()
        deadline = start + timeout_ms / 1000.0
        pumps = 0
        value = predicate()
        while not value and time.monotonic() < deadline:
            cls._process(poll_ms)
            pumps += 1
            value = predicate()
            if not value:
                time.sleep(poll_ms / 1000.0)
        return value, (time.monotonic() - start) * 1000.0, pumps


class QtWait:
    """Bounded event-loop waits for Qt tests: reach a condition, or FAIL.

    Usage — in order of preference::

        rows = QtWait.until(lambda: table.rowCount(), "table never populated")
        QtWait.pump()                       # drain queued work, no condition
        QtWait.require_clipboard(self)      # the one shared OS-resource probe
        QtWait.flaky(self, "reason")        # last resort, countable marker

    ``until`` is the default. Reach for ``flaky`` only when the condition
    depends on a resource this process does not own (a machine-global OS
    clipboard, say) — never for "the widget might be slow".
    """

    #: Wall-clock budget for a single wait. Generous by design: the operations
    #: waited on take single-digit milliseconds idle, so this is ~1000x
    #: headroom — it is spent only when something is actually broken.
    TIMEOUT_MS = int(os.environ.get("UITK_TEST_WAIT_TIMEOUT_MS", "5000"))
    #: Event-loop slice per pass, and the CPU yield between passes.
    POLL_MS = 5
    #: Default passes for the conditionless :meth:`pump` drain. ONE, so a bare
    #: ``pump()`` is an exact drop-in for ``processEvents()`` — callers that
    #: genuinely need repeated passes (tearDown's DeferredDelete drain) ask for
    #: them explicitly rather than making every site pay.
    PUMP_PASSES = 1
    #: Slice for :meth:`pump` — long enough to drain a burst in one pass.
    PUMP_SLICE_MS = 50
    #: Stamped into the reason of every deliberately-gated skip, so a runner
    #: (or ``grep``) counts them separately from ordinary environment skips.
    FLAKY_MARKER = "FLAKY-GATED:"

    #: Passes spent by the most recent wait — diagnostics only, never assert
    #: on it outside this helper's own tests.
    last_pumps = 0

    @classmethod
    def until(cls, predicate, message, *, timeout_ms=None, poll_ms=None):
        """Pump the event loop until *predicate* is truthy; fail on timeout.

        Args:
            predicate: Callable re-evaluated between passes. Its truthy value
                is returned, so a site can bind the thing it waited for.
            message: What was expected — quoted verbatim in the failure.
            timeout_ms: Wall-clock budget (default :attr:`TIMEOUT_MS`).
            poll_ms: Event-loop slice per pass (default :attr:`POLL_MS`).

        Returns:
            The predicate's truthy value.

        Raises:
            AssertionError: The condition was not reached inside the budget.
                Deliberately an assertion and never a skip: "the popup never
                appeared" is the failure this test exists to report.
        """
        timeout_ms = cls.TIMEOUT_MS if timeout_ms is None else timeout_ms
        poll_ms = cls.POLL_MS if poll_ms is None else poll_ms
        value, elapsed_ms, pumps = _QtWaitInternal._spin(predicate, timeout_ms, poll_ms)
        cls.last_pumps = pumps
        if not value:
            raise AssertionError(
                f"{message} (waited {elapsed_ms:.0f}ms of a {timeout_ms}ms "
                f"budget over {pumps} event-loop pass(es)). This is a real "
                f"failure, not a slow machine: the budget is ~1000x the idle "
                f"cost of the operation."
            )
        return value

    @classmethod
    def reached(cls, predicate, *, timeout_ms=None, poll_ms=None):
        """Same bounded wait as :meth:`until`, reported as a bool.

        For the rare site that must CHOOSE a policy on the outcome (fail here,
        gate there) rather than simply fail. Prefer :meth:`until`.
        """
        timeout_ms = cls.TIMEOUT_MS if timeout_ms is None else timeout_ms
        poll_ms = cls.POLL_MS if poll_ms is None else poll_ms
        value, _elapsed_ms, pumps = _QtWaitInternal._spin(
            predicate, timeout_ms, poll_ms
        )
        cls.last_pumps = pumps
        return bool(value)

    @classmethod
    def pump(cls, passes=None, slice_ms=None):
        """Drain queued Qt work (posted events, zero-timers) *n* passes.

        The calibrated replacement for hand-rolled ``for _ in range(n):
        processEvents()`` loops. Use it only when there is no condition to wait
        on — when there is one, :meth:`until` is both faster idle and correct
        under load.
        """
        passes = cls.PUMP_PASSES if passes is None else passes
        slice_ms = cls.PUMP_SLICE_MS if slice_ms is None else slice_ms
        for _ in range(passes):
            _QtWaitInternal._process(slice_ms)

    @classmethod
    def require_clipboard(cls, case):
        """Wait for the clipboard to round-trip; FAIL offscreen, gate elsewhere.

        The offscreen QPA carries an in-memory clipboard and always works, so
        CI (which runs offscreen) must never gate here -- a failed round-trip
        there is a real Qt regression and is asserted as one. Under a REAL
        platform the clipboard is a machine-global resource any other process
        can hold open; the set then fails silently and ``text()`` comes back
        empty -- a false failure that says nothing about the copy code.

        The probe retries for a bounded window first, because a holder is
        usually transient; only a clipboard that is still dead after that is
        gated, and the gate is stamped with :attr:`FLAKY_MARKER` so a rise in
        gated tests is countable instead of invisible in a green run.

        The probe does not restore the previous contents: callers overwrite the
        clipboard themselves, so "preserving" it would be false precision --
        and a ``setText`` restore would DESTROY non-text content (an image the
        developer had copied), which ``text()`` cannot capture to begin with.

        Lives here rather than on one test module because two suites need it,
        and the copy that was NOT maintained degraded to a bare ``skipTest``:
        no retry, no offscreen assertion, and no countable marker -- so a
        genuinely broken copy path read as an unavailable OS resource.

        Args:
            case: The ``TestCase`` to fail or gate.
        """
        from qtpy import QtWidgets

        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is None:
            # No QApplication -> clipboard() is None, and the probe would
            # die with an AttributeError several frames deep inside its own
            # predicate. Say what is actually wrong instead.
            case.fail(
                "no QApplication: QApplication.clipboard() returned None. "
                "Derive the test case from QtBaseTestCase (or call "
                "setup_qt_application) before probing the clipboard."
            )
        sentinel = "uitk-clipboard-probe"

        def round_trips():
            clipboard.setText(sentinel)  # re-set: a holder may win a race
            return clipboard.text() == sentinel

        if cls.reached(round_trips, timeout_ms=1000):
            return
        if cls.is_offscreen():
            case.fail(
                "offscreen QPA carries an in-memory clipboard that always "
                "round-trips -- a dead one here is a real regression, not an "
                "unavailable OS resource"
            )
        cls.flaky(
            case,
            "OS clipboard is unavailable in this environment (another process "
            "holds it); run with QT_QPA_PLATFORM=offscreen.",
        )

    @classmethod
    def flaky(cls, testcase, reason):
        """Skip *testcase* with a countable marker — the last resort.

        Legitimate only when the condition depends on a resource outside this
        process (the machine-global OS clipboard). Unlike a bare ``skipTest``
        the reason is stamped, so a rise in gated tests is greppable rather
        than invisible inside a green run.
        """
        testcase.skipTest(f"{cls.FLAKY_MARKER} {reason}")

    @staticmethod
    def is_offscreen():
        """True when running on the offscreen QPA (CI, and the runner default).

        Offscreen carries its own in-memory window/clipboard implementations,
        so anything environment-gated under a real platform is *deterministic*
        here and must be asserted rather than gated.
        """
        from qtpy import QtWidgets

        app = QtWidgets.QApplication.instance()
        name = app.platformName() if app is not None else ""
        return (name or os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen"


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
        self._qt_torn_down = False
        # Registered as a CLEANUP as well as running from tearDown, so the
        # flush cannot be skipped. unittest calls cleanups even where it
        # does NOT call tearDown -- a subclass setUp that raises after this
        # line -- and even when tearDown itself dies partway, which would
        # otherwise strand the DeferredDelete drain at the end of it.
        #
        # This is a GUARD, not a repair of a live defect: measured on this
        # suite, 89 subclasses override tearDown and all 89 chain via
        # ``super()``, and none override setUp without chaining. So nothing
        # bypasses the flush today; this keeps that true without anyone
        # having to remember, and test_conftest_teardown_backstop.py fails
        # if the registration is removed.
        #
        # Latched, so the flush still runs exactly ONCE per test: from
        # tearDown where the chain is intact (unchanged ordering for every
        # class that exists today), from here where it is not. Draining
        # twice would be correct but not free -- each pass is a bounded
        # ``processEvents`` slice, so a busy queue would pay 50ms x3 for the
        # redundant round on every one of ~4k tests.
        self.addCleanup(self._qt_teardown)

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
        QtWait.pump(passes=passes)

    def tearDown(self):
        """Clean up widgets created during the test."""
        super().tearDown()
        self._qt_teardown()

    def _qt_teardown(self):
        """Release grabs, destroy tracked widgets, drain the event queue.

        Runs from BOTH :meth:`tearDown` and the cleanup registered in
        :meth:`setUp`, and latches so the work happens once: whichever
        fires first does it. A subclass that chains to ``super().tearDown()``
        therefore behaves exactly as before this backstop existed.
        """
        if getattr(self, "_qt_torn_down", False):
            return
        self._qt_torn_down = True
        from qtpy import QtWidgets

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

        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

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


def rendered_text_width(text, font):
    """Natural px width *text* occupies when laid out in *font*.

    Unlike ``QFontMetrics.horizontalAdvance`` this resolves **tab stops** the
    way the renderer will, so it is the only honest way to ask whether a string
    containing a tab fits a field (see ``PrefixColumnMixin``).
    """
    from qtpy import QtGui

    layout = QtGui.QTextLayout(text, font)
    layout.beginLayout()
    line = layout.createLine()
    line.setLineWidth(1e6)
    layout.endLayout()
    return line.naturalTextWidth()


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
    from qtpy import QtCore

    window.show()
    # Qt processes posted LayoutRequests BEFORE the first paint — flush them
    # so snapshot A is what the first paint actually renders. Without this,
    # a hand-built window's layout-assigned geometry (which lands pre-paint)
    # would read as a post-show "mutation" on styles with large native hints.
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.LayoutRequest)
    before = visual_state_snapshot(window, ignore=ignore)
    QtWait.pump(passes=pumps, slice_ms=settle_ms)
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
