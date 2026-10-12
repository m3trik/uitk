"""Reusable benchmark for the MarkingMenu RUNTIME hot paths.

:mod:`bench.marking_menu_init` times the once-per-session lifecycle (cold
load, first ``_init_ui``, first show). This bench times what the user feels
on EVERY gesture after that: the activation press, chord switches between
start menus, the drag trail, hover navigation into submenus and back, and
the release. Each phase is timed as *operation + event-loop drain*, so the
paint and backing-store flush the operation schedules are included — a
cheap Python call that dirties a full-screen translucent window is not
cheap.

Like the init bench it is host-agnostic (imports no DCC SDK) and one-shot
per host process. A consumer subclasses :class:`MarkingMenuRuntimeBench`,
implements :meth:`setup_marking_menu`, and decides how to drive it (a fresh
DCC, an offscreen ``QApplication``, ...).

The bench never touches the real pointer. ``QCursor.pos`` is patched to a
synthetic position for the duration (every anchor, hit-test and transition
check reads that), activation is driven through the menu's own press /
release methods rather than the OS key, and :class:`MouseTracking`'s grab
hand-off is stubbed so a drag sample never captures the real mouse. What it
cannot exercise is OS input delivery itself.

Cycle layout::

    press (default page) -> each chord binding -> drag samples on the
    drag page -> hover-nav into each nav button's submenu and back ->
    release

Cycle 0 is the first gesture after preload: its samples are reported under
``first`` (lists, one entry per occurrence — a cold submenu pays its load in
``hover_enter`` and its first show in ``hover_transition``). The next
:attr:`CYCLES` are steady state, aggregated into ``phases_ms_*`` (keys
follow the init bench so ``run_in_maya``'s aggregation and ``--diff`` work
unchanged). Timing and profiling never share a cycle: cProfile's per-call
overhead would inflate every number, and most for exactly the call-heavy
paths a fix removes. :attr:`PROFILE_CYCLES` further cycles, untimed, feed
``profile_by_phase`` and the overall ``profile_cumulative`` /
``profile_tottime``. Cycle 0 can be profiled instead of timed
(``profile_first``) — it runs once per process, so it is one or the other.
"""

from __future__ import annotations

import cProfile
import io
import os
import pstats
import statistics
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

_BUTTON_BITS = {"LeftButton": 0x1, "RightButton": 0x2, "MiddleButton": 0x4}


class MarkingMenuRuntimeBench:
    """Reusable marking-menu runtime benchmark.

    Subclass and override :meth:`setup_marking_menu`. The chord masks, the
    drag page and the nav buttons are all derived from the live menu's
    bindings and pages, so a subclass rarely needs more.
    """

    #: Steady-state gesture cycles to run after the first (cycle 0).
    CYCLES = 12
    #: Mouse-move samples per drag phase.
    DRAG_SAMPLES = 60
    #: Radius (px) of the circular drag path (beside the page; see _drag_center).
    DRAG_RADIUS = 140
    #: Nav buttons exercised per cycle (bounded so a big page stays quick).
    NAV_BUTTONS = 6
    #: Chord mask whose page carries the drag + hover-nav phases.
    DRAG_BUTTONS = _BUTTON_BITS["RightButton"]
    #: Seconds to wait for a deferred preload to drain after construction.
    PRELOAD_TIMEOUT_S = 60.0
    #: Untimed cycles run under the profiler after the timed ones.
    PROFILE_CYCLES = 4
    #: Rows per phase in ``profile_by_phase``.
    PHASE_PROFILE_ROWS = 14
    #: When set, each phase's raw profile is also dumped here as
    #: ``<phase>.prof`` (for ``pstats`` caller/callee digging). Defaults to the
    #: ``UITK_BENCH_PROFILE_DIR`` environment variable.
    profile_dir: Optional[str] = None

    def __init__(
        self,
        ui_name: Optional[str] = None,
        label: str = "run",
        profile: bool = True,
        profile_first: bool = False,
    ) -> None:
        self.ui_name = ui_name
        self.label = label
        self.profile = profile
        self.profile_first = profile_first or bool(
            os.environ.get("UITK_BENCH_PROFILE_FIRST")
        )
        if self.profile_dir is None:
            self.profile_dir = os.environ.get("UITK_BENCH_PROFILE_DIR") or None
        # Which pass is running: timings are recorded only while _timing, and
        # the profiler runs only while _profiling (see run).
        self._timing = True
        self._profiling = False
        self._samples: dict[str, list[float]] = {}
        self._first: dict[str, list[float]] = {}
        self._profiles: dict[str, cProfile.Profile] = {}
        self._nav_skipped: list[str] = []
        self._first_targets: list[str] = []
        self._cursor = None

    # ------------------------------------------------------------------
    # Subclass extension point
    # ------------------------------------------------------------------

    def setup_marking_menu(self):
        """Construct and return the :class:`MarkingMenu` (or subclass)."""
        raise NotImplementedError(
            f"{type(self).__name__}.setup_marking_menu() must be overridden"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def chord_masks(bindings: dict) -> list[tuple[int, str]]:
        """``(button_mask, target)`` for every button-carrying binding."""
        out = []
        for key, target in bindings.items():
            mask = 0
            for part in str(key).split("|"):
                mask |= _BUTTON_BITS.get(part, 0)
            if mask:
                out.append((mask, target))
        return sorted(out)

    @contextmanager
    def _patched_cursor(self):
        from qtpy import QtCore, QtGui

        self._cursor = QtCore.QPoint(0, 0)
        original = QtGui.QCursor.__dict__.get("pos")
        QtGui.QCursor.pos = staticmethod(lambda *_a: QtCore.QPoint(self._cursor))
        try:
            yield
        finally:
            if original is not None:
                QtGui.QCursor.pos = original
            else:  # pragma: no cover - inherited attribute
                del QtGui.QCursor.pos

    def _drain(self) -> None:
        from qtpy import QtWidgets

        app = QtWidgets.QApplication.instance()
        for _ in range(3):
            app.processEvents()

    @contextmanager
    def _profiled(self, name: str, first: bool):
        """Profile the block under phase *name* during a profiling pass
        (cycle 0, when ``profile_first``, as ``first:<name>``).

        One profiler per phase rather than one around the whole run: Python
        allows a single active profiler, and per-phase tables are what
        attributes a phase's cost. The overall tables sum the steady-state
        phases only; cycle 0's cold work is reported per phase, never mixed in.
        """
        prof = None
        if self._profiling:
            key = f"first:{name}" if first else name
            prof = self._profiles.setdefault(key, cProfile.Profile())
            prof.enable()
        try:
            yield
        finally:
            if prof is not None:
                prof.disable()

    def _record(self, name: str, ms: float, first: bool) -> None:
        if not self._timing:
            return
        bucket = self._first if first else self._samples
        bucket.setdefault(name, []).append(ms)

    def _time(self, name: str, fn: Callable[[], Any], first: bool) -> Any:
        with self._profiled(name, first):
            t0 = time.perf_counter()
            result = fn()
            self._drain()
            ms = (time.perf_counter() - t0) * 1000.0
        self._record(name, ms, first)
        return result

    # ------------------------------------------------------------------
    # Phases
    # ------------------------------------------------------------------

    def _drag_center(self, mm, page, anchor):
        """A drag center on EMPTY overlay beside *page*.

        Dragging across the page would cross its nav buttons, and the drag's
        own hover tracking would then open submenus mid-sample (real
        behaviour, but it folds hover-nav and cold loads into the paint
        timing). Beside the page, the samples time the trail paint and the
        tracking dispatch alone.
        """
        from qtpy import QtCore

        rect = page.geometry().translated(mm.mapToGlobal(QtCore.QPoint(0, 0)))
        screen = mm.screen().geometry()
        offset = rect.width() // 2 + self.DRAG_RADIUS + 30
        for dx in (offset, -offset):
            center = QtCore.QPoint(rect.center().x() + dx, rect.center().y())
            span = QtCore.QRect(0, 0, 2 * self.DRAG_RADIUS, 2 * self.DRAG_RADIUS)
            span.moveCenter(center)
            if screen.contains(span):
                return center
        return anchor  # no room beside the page: drag over it after all

    def _drag(self, mm, page, anchor, first: bool) -> None:
        import math

        from qtpy import QtCore, QtGui, QtWidgets

        mm.overlay.start_gesture(anchor)
        center = self._drag_center(mm, page, anchor)
        buttons = QtCore.Qt.MouseButtons(self.DRAG_BUTTONS)
        with self._profiled("drag_move", first):
            for i in range(self.DRAG_SAMPLES):
                angle = 2 * math.pi * i / self.DRAG_SAMPLES
                g = center + QtCore.QPoint(
                    int(self.DRAG_RADIUS * math.cos(angle)),
                    int(self.DRAG_RADIUS * math.sin(angle)),
                )
                self._cursor = QtCore.QPoint(g)
                event = QtGui.QMouseEvent(
                    QtCore.QEvent.MouseMove,
                    QtCore.QPointF(mm.mapFromGlobal(g)),
                    QtCore.QPointF(g),
                    QtCore.Qt.NoButton,
                    buttons,
                    QtCore.Qt.NoModifier,
                )
                t0 = time.perf_counter()
                QtWidgets.QApplication.sendEvent(mm, event)
                t1 = time.perf_counter()
                self._drain()
                t2 = time.perf_counter()
                self._record("drag_move_dispatch", (t1 - t0) * 1000.0, first)
                self._record("drag_move_paint", (t2 - t1) * 1000.0, first)
                self._record("drag_move_total", (t2 - t0) * 1000.0, first)
        self._cursor = QtCore.QPoint(anchor)

    def _skip_reason(self, mm, button) -> str:
        """Why a hover on *button* scheduled no transition (diagnostics)."""
        name = button.submenu_name()
        try:
            ui = mm.sb.get_ui(name)
        except Exception as e:  # the resolver's miss, or a load defect
            return f"{name}: get_ui raised {type(e).__name__}: {e}"
        if ui is None:
            return f"{name}: get_ui -> None"
        return f"{name}: resolved, but no transition was scheduled"

    def _hover_nav(self, mm, page, first: bool) -> dict[str, int]:
        from qtpy import QtCore, QtGui

        from uitk.widgets.menuButton import MenuButton

        stats = {"nav_attempted": 0, "nav_landed": 0}
        buttons = [
            b for b in page.findChildren(MenuButton) if b.target and b.isVisible()
        ][: self.NAV_BUTTONS]
        for b in buttons:
            center = b.mapToGlobal(b.rect().center())
            self._cursor = QtCore.QPoint(center)
            local = QtCore.QPointF(b.rect().center())
            event = QtGui.QEnterEvent(local, local, QtCore.QPointF(center))
            mm._clear_transition_flag()
            # The enter resolves (and, cold, LOADS) the submenu before the
            # transition timer is armed — part of the hover the user feels.
            # Timed WITHOUT a drain: draining could fire the 8 ms transition
            # timer inside the measurement and fold the transition into it.
            with self._profiled("hover_enter", first):
                t0 = time.perf_counter()
                mm.child_enterEvent(b, event)
                self._record("hover_enter", (time.perf_counter() - t0) * 1e3, first)
            if mm._pending_transition_ui is None:
                self._nav_skipped.append(
                    f"cycle{'0' if first else 'N'} {self._skip_reason(mm, b)}"
                )
                continue
            mm._pending_show_timer.stop()
            stats["nav_attempted"] += 1
            pending = mm._pending_transition_ui
            if first:
                self._first_targets.append(pending.objectName())
            self._time("hover_transition", mm._perform_transition, first)
            if mm.sb.current_ui is pending:
                stats["nav_landed"] += 1
            mm._clear_transition_flag()
            self._time("return_to_startmenu", mm._return_to_startmenu, first)
            mm.overlay.path.clear_to_origin()
        return stats

    def _cycle(self, mm, anchor, chords, first: bool) -> dict[str, int]:
        from qtpy import QtCore

        self._cursor = QtCore.QPoint(anchor)
        self._time(
            "activation_press",
            lambda: mm._on_activation_press(buttons=QtCore.Qt.NoButton),
            first,
        )
        for mask, target in chords:
            self._time(
                f"chord_{target}",
                lambda m=mask: mm._sync_menu_to_state(buttons=m, modifiers=0),
                first,
            )
        # Settle on the drag page for the drag + hover-nav phases.
        mm._sync_menu_to_state(buttons=self.DRAG_BUTTONS, modifiers=0)
        self._drain()
        page = mm.currentWidget()
        stats = {}
        if page is not None:
            self._drag(mm, page, anchor, first)
            stats = self._hover_nav(mm, page, first)
        self._time("activation_release", mm._on_activation_release, first)
        return stats

    def _micro(self, mm) -> dict[str, Any]:
        """Sub-phase costs read straight off the menu (no gesture)."""
        from qtpy import QtCore, QtWidgets

        out: dict[str, Any] = {}
        n = 200
        name = next(iter(mm._bindings.values()), None)
        if name:
            t0 = time.perf_counter()
            for _ in range(n):
                mm.sb.get_ui(name)
            out["get_ui_us"] = round((time.perf_counter() - t0) * 1e6 / n, 2)
        out["top_level_widgets"] = len(QtWidgets.QApplication.topLevelWidgets())
        t0 = time.perf_counter()
        for _ in range(20):
            mm._dismiss_external_popups(QtCore.Qt.NoButton)
        out["dismiss_popups_ms"] = round((time.perf_counter() - t0) * 1000 / 20, 3)
        out["loaded_ui"] = len(list(mm.sb.loaded_ui.values()))
        return out

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _profile_tables(self) -> dict[str, Any]:
        def _text(stats: pstats.Stats, sort: str, limit: int) -> str:
            buf = io.StringIO()
            stats.stream = buf
            stats.sort_stats(sort).print_stats(limit)
            return buf.getvalue()

        if not self._profiles:
            return {}
        if self.profile_dir:
            os.makedirs(self.profile_dir, exist_ok=True)
            for name, prof in self._profiles.items():
                safe = "".join(c if c.isalnum() else "_" for c in name)
                prof.dump_stats(os.path.join(self.profile_dir, f"{safe}.prof"))
        by_phase = {}
        combined = None
        for name, prof in sorted(self._profiles.items()):
            stats = pstats.Stats(prof).strip_dirs()
            by_phase[name] = _text(stats, "tottime", self.PHASE_PROFILE_ROWS)
            if name.startswith("first:"):
                continue
            if combined is None:
                combined = pstats.Stats(prof)
            else:
                combined.add(prof)
        if combined is None:  # only cycle 0 was profiled
            return {"profile_by_phase": by_phase}
        combined.strip_dirs()
        return {
            "profile_by_phase": by_phase,
            "profile_cumulative": _text(combined, "cumulative", 60),
            "profile_tottime": _text(combined, "tottime", 45),
        }

    # ------------------------------------------------------------------
    # Bench body
    # ------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        from qtpy import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is None:
            raise RuntimeError(
                "MarkingMenuRuntimeBench requires an existing QApplication."
            )

        with self._patched_cursor():
            screen = app.primaryScreen().geometry()
            anchor = screen.center()
            self._cursor = QtCore.QPoint(anchor)

            t0 = time.perf_counter()
            mm = self.setup_marking_menu()
            construct_ms = (time.perf_counter() - t0) * 1000.0
            # The bench pumps Qt from Python, which a host-loop-only preload
            # reads as a script pumping events: it would never advance.
            mm.PRELOAD_ONLY_FROM_HOST_LOOP = False

            # Each event-loop pass while the deferred preload drains warms at
            # most one page (or runs work a warmed page deferred): its length
            # is a freeze the warm-up inflicts on an idle host.
            t0 = time.perf_counter()
            deadline = t0 + self.PRELOAD_TIMEOUT_S
            passes = []
            while mm._preload_queue is not None and time.perf_counter() < deadline:
                t_pass = time.perf_counter()
                app.processEvents(QtCore.QEventLoop.AllEvents, 50)
                passes.append(time.perf_counter() - t_pass)
            self._drain()
            preload_ms = (time.perf_counter() - t0) * 1000.0
            # By page name: loaded_ui also keys each page by an alias.
            warmed = sorted(
                {
                    ui.objectName()
                    for ui in mm.sb.loaded_ui.values()
                    if getattr(ui, "is_initialized", False)
                    and mm.hosts_ui(ui.objectName())
                }
            )

            # The grab hand-off would capture the REAL pointer; the bench's
            # drag is synthetic, so record the decision and skip the grab.
            tracking = mm.mouse_tracking
            tracking._grab_widget = lambda _w: None
            tracking._buttons_provider = lambda: self.DRAG_BUTTONS

            chords = self.chord_masks(mm._bindings)
            # Cycle 0: timed, or profiled when asked (once per process).
            self._timing = not self.profile_first
            self._profiling = self.profile and self.profile_first
            nav_first = self._cycle(mm, anchor, chords, first=True)
            # Steady state: timed with the profiler off...
            self._timing, self._profiling = True, False
            nav = {}
            for _ in range(self.CYCLES):
                nav = self._cycle(mm, anchor, chords, first=False)
            # ...then profiled, untimed.
            if self.profile:
                self._timing, self._profiling = False, True
                for _ in range(self.PROFILE_CYCLES):
                    self._cycle(mm, anchor, chords, first=False)
                self._timing, self._profiling = True, False

            micro = self._micro(mm)

        def _agg(fn) -> dict[str, float]:
            return {k: round(fn(v), 3) for k, v in self._samples.items()}

        import uitk

        result = {
            "label": self.label,
            # Which checkout was measured (A/B runs point sys.path at copies).
            "uitk": uitk.__file__,
            "qt": QtCore.qVersion(),
            "screen": [screen.width(), screen.height()],
            "construct_ms": round(construct_ms, 3),
            "preload_drain_ms": round(preload_ms, 3),
            # Every pass of 100 ms or more, longest first: how choppy the host
            # is while the warm-up runs, not just its worst moment.
            "preload_slow_passes_ms": sorted(
                (round(p * 1000.0, 1) for p in passes if p >= 0.1), reverse=True
            ),
            "preload_warmed": warmed,
            "cycles": self.CYCLES,
            "first_profiled": self.profile_first,
            "chords": [t for _, t in chords],
            "nav_first": nav_first,
            "nav": nav,
            "nav_skipped": self._nav_skipped,
            "first_hover_targets": self._first_targets,
            "first": {k: [round(ms, 2) for ms in v] for k, v in self._first.items()},
            "micro": micro,
            "phases_ms_best": _agg(min),
            "phases_ms_median": _agg(statistics.median),
            "phases_ms_p90": _agg(lambda v: sorted(v)[int(0.9 * (len(v) - 1))]),
        }
        result.update(self._profile_tables())
        return result

    @staticmethod
    def format_report(result: dict[str, Any]) -> str:
        """Human-readable table for the result of :meth:`run`."""
        first = result.get("first", {})
        lines = [
            f"# {result.get('label')}  qt={result.get('qt')}  "
            f"screen={result.get('screen')}  cycles={result.get('cycles')}",
            f"construct {result.get('construct_ms')} ms  "
            f"preload drain {result.get('preload_drain_ms')} ms "
            f"(slow passes {result.get('preload_slow_passes_ms', [])[:5]} ms, "
            f"{len(result.get('preload_warmed', []))} pages warm)  "
            f"nav_first={result.get('nav_first')}  nav={result.get('nav')}",
            f"first hover targets: {result.get('first_hover_targets')}",
            f"micro={result.get('micro')}",
        ]
        for line in result.get("nav_skipped", [])[:8]:
            lines.append(f"  skipped: {line}")
        if result.get("first_profiled"):
            lines.append("first gesture (cycle 0): profiled, not timed (first:*)")
        else:
            lines.append("first gesture (cycle 0), ms per occurrence:")
        for k in sorted(first):
            v = first[k]
            if k.startswith("drag_move"):
                v = [round(statistics.median(v), 2)] if v else v
                k = f"{k} (median)"
            lines.append(f"  {k:<42} {v}")
        lines += [
            f"{'steady-state phase':<44} {'best':>9} {'median':>9} {'p90':>9}",
            "-" * 74,
        ]
        best = result.get("phases_ms_best", {})
        median = result.get("phases_ms_median", {})
        p90 = result.get("phases_ms_p90", {})
        for k in sorted(best):
            lines.append(
                f"{k:<44} {best[k]:>9.3f} {median.get(k, 0):>9.3f} "
                f"{p90.get(k, 0):>9.3f}"
            )
        return "\n".join(lines)
