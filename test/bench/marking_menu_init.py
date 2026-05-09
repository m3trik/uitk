"""Reusable benchmark for the MarkingMenu lazy-load + init lifecycle.

Designed to run inside any live ``QApplication`` host — a DCC, an IDE,
or plain Python.  uitk deliberately stays host-agnostic: this module
imports nothing from ``maya``, ``max``, etc.  Project-specific consumers
(e.g. tentacle's marking_menu bench) subclass
:class:`MarkingMenuInitBench`, implement :meth:`setup_switchboard` and
:meth:`setup_marking_menu`, and decide how to *drive* the bench (launch
a fresh DCC, run inline, …); the rest of the lifecycle timing is shared.

The bench is strictly **one-shot per host process**.  The lifecycle we
care about (cold compile of ``_ui.py``, first ``_init_ui``, first show)
is by definition a once-per-DCC-session event, and re-running it inside
the same Qt session diverges from the real path.  Aggregate across
multiple host launches if you need noise reduction — that's the
driver's job.

Phases timed (sub-millisecond resolution, ``time.perf_counter``):

  ``01_imports``
      Import :class:`uitk.Switchboard` and :class:`uitk.MarkingMenu`.

  ``02_switchboard_construct``
      Construct the :class:`Switchboard` with the project's UI / slot
      sources.  Cost is dominated by registry scans and module imports.
      Subclasses whose marking menu builds its own switchboard
      internally (e.g. tentacle's ``TclMaya``) may return ``None``
      here — phase 03 then absorbs the bundled cost.

  ``03_marking_menu_construct``
      Construct the :class:`MarkingMenu` (or subclass).  Includes
      handler registration, binding parse, and global-shortcut wiring.

  ``04_lazy_load_startmenu``
      First ``sb.get_ui(STARTMENU_UI)``.  Triggers the full
      :class:`uitk.loaders.compiled.CompiledLoader` path: hash check
      against the ``.ui``, compile to ``_ui.py`` if missing/stale,
      ``importlib`` exec, ``setupUi`` of the widget tree, and finally
      :meth:`Switchboard.add_ui` wrap-in-MainWindow.

  ``05_init_startmenu``
      ``MarkingMenu._init_ui`` on the loaded UI: stylesheet apply,
      ``setParent`` into the marking-menu's stacked layout, and
      :meth:`add_child_event_filter` walk over every child widget.

  ``06_first_show_startmenu``
      ``MarkingMenu._show_marking_menu``: ``setCurrentWidget`` (hide
      previous, show new), reposition at cursor, raise + activate.

  ``07_drain_after_startmenu``
      Pump the Qt event loop so ``QTimer.singleShot(0, ...)`` retries
      and any deferred init scheduled during the show complete.

  ``08_lazy_load_submenu``
      Same as 04, but for a submenu UI — either the explicit
      :attr:`SUBMENU_UI` or the autodetected first ``i#submenu``
      reachable from the startmenu.

  ``09_init_submenu``
      Same as 05, but for the submenu.

  ``10_drain_after_submenu``
      Same as 07, scoped to the submenu.

  ``11_warm_show_startmenu``
      Second ``mm.show(STARTMENU_UI, force=True)``.  Should be
      near-zero on the warm path: the widget is cached in
      ``loaded_ui`` (via Qt parent chain) and ``is_initialized`` is
      already ``True``.  A non-zero result here means the warm path
      is doing more work than necessary (typically a phantom re-load
      caused by weakref drop, or per-show style/init that should
      have been gated).

  ``12_warm_load_via_loader``
      Direct second call to ``sb._loader.load(filepath)`` — isolates
      the per-call cost of the loader itself (``ensure_compiled``
      hash check + ``_import_compiled_module`` re-exec + ``setupUi``)
      from the ``add_ui`` / ``_init_ui`` cost measured in 04+05.
      Useful diagnostic for evaluating module-cache strategies.
"""

from __future__ import annotations

import gc
import time
from contextlib import contextmanager
from typing import Any, Optional


class _PhaseTimer:
    """Records ordered ``(name, ms)`` entries via :meth:`measure`."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, float]] = []

    @contextmanager
    def measure(self, name: str):
        gc.collect()
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.entries.append((name, (time.perf_counter() - t0) * 1000))


class MarkingMenuInitBench:
    """Reusable marking-menu init benchmark.

    Subclass and override :meth:`setup_switchboard` and
    :meth:`setup_marking_menu` to wire your project.  Optionally set
    :attr:`STARTMENU_UI` and :attr:`SUBMENU_UI` (or rely on
    :meth:`find_submenu_name` to autodetect a submenu from an ``i``
    button in the loaded startmenu).
    """

    #: Default startmenu UI to load.  Override per subclass or pass via
    #: ``ui_name``.
    STARTMENU_UI = "startmenu"

    #: Optional explicit submenu UI name.  When ``None``, the bench
    #: walks the loaded startmenu for the first ``i`` button and uses
    #: ``f"{accessibleName}#submenu"``.
    SUBMENU_UI: Optional[str] = None

    def __init__(
        self,
        ui_name: Optional[str] = None,
        label: str = "run",
    ) -> None:
        self.ui_name = ui_name or self.STARTMENU_UI
        self.label = label

    # ------------------------------------------------------------------
    # Subclass extension points
    # ------------------------------------------------------------------

    def setup_switchboard(self):
        """Construct and return a configured :class:`uitk.Switchboard`.

        Subclasses whose marking menu builds its own switchboard
        internally (e.g. tentacle's ``TclMaya``) may return ``None``;
        :meth:`run` will then read ``mm.sb`` after marking-menu
        construction and the ``02_switchboard_construct`` phase will
        report ~0 ms.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.setup_switchboard() must be overridden"
        )

    def setup_marking_menu(self, sb):
        """Construct and return the :class:`MarkingMenu` (or subclass).

        Receives the ``Switchboard`` returned from
        :meth:`setup_switchboard` (``None`` if the subclass bundles
        construction).
        """
        raise NotImplementedError(
            f"{type(self).__name__}.setup_marking_menu() must be overridden"
        )

    def find_submenu_name(self, ui) -> Optional[str]:
        """Autodetect the first reachable submenu name from ``ui``.

        Walks the loaded startmenu for ``QPushButton`` widgets whose
        ``base_name() == "i"`` and returns ``f"{accessibleName}#submenu"``
        for the first match.  Override to point at a specific known
        submenu instead.
        """
        from qtpy import QtWidgets

        for w in ui.findChildren(QtWidgets.QPushButton):
            base_name = getattr(w, "base_name", None)
            if not callable(base_name):
                continue
            if base_name() != "i":
                continue
            acc = w.accessibleName()
            if acc:
                return f"{acc}#submenu"
        return None

    # ------------------------------------------------------------------
    # Bench body
    # ------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Run the bench end-to-end and return a result dict.

        One-shot: construct the switchboard + marking menu, lazy-load
        the startmenu and a submenu, time the lifecycle phases, emit
        numbers.  No teardown — Qt cleans up when the host process
        exits.  This matches the only path that has ever been stable
        inside a real DCC session.
        """
        from qtpy import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is None:
            raise RuntimeError(
                "MarkingMenuInitBench requires an existing QApplication "
                "in the active Python process."
            )

        def _ck(msg: str) -> None:
            print(f"[bench] {msg}", flush=True)

        timer = _PhaseTimer()

        _ck("01 imports")
        with timer.measure("01_imports"):
            from uitk import Switchboard  # noqa: F401
            from uitk import MarkingMenu  # noqa: F401

        _ck("02 switchboard construct")
        with timer.measure("02_switchboard_construct"):
            sb = self.setup_switchboard()

        _ck("03 marking_menu construct")
        with timer.measure("03_marking_menu_construct"):
            mm = self.setup_marking_menu(sb)
            if sb is None:
                sb = mm.sb  # subclass that bundles construction

        _ck(f"04 lazy load startmenu {self.ui_name!r}")
        with timer.measure("04_lazy_load_startmenu"):
            ui = sb.get_ui(self.ui_name)
        if ui is None:
            raise RuntimeError(
                f"Startmenu UI {self.ui_name!r} resolved to None"
            )
        widget_count = len(ui.findChildren(QtWidgets.QWidget))
        _ck(f"04 done; widgets={widget_count}")

        _ck("05 init startmenu")
        with timer.measure("05_init_startmenu"):
            if not getattr(ui, "is_initialized", False):
                mm._init_ui(ui)

        _ck("06 first show startmenu")
        with timer.measure("06_first_show_startmenu"):
            mm._show_marking_menu(ui)

        _ck("07 drain after startmenu")
        with timer.measure("07_drain_after_startmenu"):
            for _ in range(20):
                app.processEvents(QtCore.QEventLoop.AllEvents, 12)

        sub_name = self.SUBMENU_UI or self.find_submenu_name(ui)
        sub_widget_count: Optional[int] = None
        if sub_name:
            _ck(f"08 lazy load submenu {sub_name!r}")
            with timer.measure("08_lazy_load_submenu"):
                submenu = sb.get_ui(sub_name)
            if submenu is None:
                _ck(f"08 submenu {sub_name!r} resolved to None")
                for k in (
                    "09_init_submenu",
                    "10_drain_after_submenu",
                ):
                    timer.entries.append((k, float("nan")))
            else:
                sub_widget_count = len(submenu.findChildren(QtWidgets.QWidget))
                _ck(f"08 done; sub_widgets={sub_widget_count}")

                _ck("09 init submenu")
                with timer.measure("09_init_submenu"):
                    if not getattr(submenu, "is_initialized", False):
                        mm._init_ui(submenu)

                _ck("10 drain after submenu")
                with timer.measure("10_drain_after_submenu"):
                    for _ in range(20):
                        app.processEvents(QtCore.QEventLoop.AllEvents, 12)
        else:
            _ck("08 no submenu found; skipping 08-10")
            for k in (
                "08_lazy_load_submenu",
                "09_init_submenu",
                "10_drain_after_submenu",
            ):
                timer.entries.append((k, float("nan")))

        _ck("11 warm show startmenu")
        with timer.measure("11_warm_show_startmenu"):
            mm.show(self.ui_name, force=True)

        _ck("12 warm load via loader")
        ui_path = sb.registry.ui_registry.get(
            filename=self.ui_name, return_field="filepath"
        )
        if ui_path:
            with timer.measure("12_warm_load_via_loader"):
                # Build a fresh widget tree directly via the loader.  No
                # add_ui / _init_ui — pure per-call loader cost.
                _ = sb._loader.load(ui_path)
        else:
            timer.entries.append(("12_warm_load_via_loader", float("nan")))

        phases = {n: round(ms, 3) for n, ms in timer.entries}

        def _sum(*keys: str) -> float:
            return round(
                sum(
                    ms
                    for n, ms in timer.entries
                    if n in keys and ms == ms  # NaN-safe
                ),
                3,
            )

        return {
            "label": self.label,
            "ui": self.ui_name,
            "submenu": sub_name,
            "widget_count": widget_count,
            "submenu_widget_count": sub_widget_count,
            "phases_ms_best": phases,
            "first_load_total_ms_best": _sum(
                "04_lazy_load_startmenu",
                "05_init_startmenu",
                "06_first_show_startmenu",
            ),
            "submenu_load_total_ms_best": _sum(
                "08_lazy_load_submenu",
                "09_init_submenu",
            ),
            "warm_show_ms_best": phases.get("11_warm_show_startmenu"),
            "warm_load_ms_best": phases.get("12_warm_load_via_loader"),
        }

    # ------------------------------------------------------------------
    # Pretty-printing
    # ------------------------------------------------------------------

    @staticmethod
    def format_report(result: dict[str, Any]) -> str:
        """Human-readable table for the result of :meth:`run`."""
        lines = []
        lines.append(
            f"# {result.get('label', 'run')}  ui={result.get('ui')}  "
            f"submenu={result.get('submenu')}  "
            f"widgets={result.get('widget_count')}  "
            f"sub_widgets={result.get('submenu_widget_count')}"
        )
        lines.append(f"{'phase':<48} {'ms':>10}")
        lines.append("-" * 60)
        for k, ms in (result.get("phases_ms_best") or {}).items():
            ms_str = "nan" if ms != ms else f"{ms:.2f}"
            lines.append(f"{k:<48} {ms_str:>10}")
        lines.append("-" * 60)
        lines.append(
            f"{'first load total (04+05+06)':<48} "
            f"{result.get('first_load_total_ms_best', 0):>10.2f}"
        )
        lines.append(
            f"{'submenu load total (08+09)':<48} "
            f"{result.get('submenu_load_total_ms_best', 0):>10.2f}"
        )
        warm_show = result.get("warm_show_ms_best")
        warm_show_str = (
            "n/a"
            if warm_show is None or warm_show != warm_show
            else f"{warm_show:.2f}"
        )
        lines.append(f"{'warm show (11)':<48} {warm_show_str:>10}")
        warm_load = result.get("warm_load_ms_best")
        warm_load_str = (
            "n/a"
            if warm_load is None or warm_load != warm_load
            else f"{warm_load:.2f}"
        )
        lines.append(f"{'warm load via loader (12)':<48} {warm_load_str:>10}")
        return "\n".join(lines)
