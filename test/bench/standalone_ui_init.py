"""Reusable benchmark for standalone-window UI lazy-load + first-show.

Suits tools that open as their own ``QMainWindow`` rather than as a
stacked page inside a :class:`MarkingMenu` — e.g. mayatk's
``hierarchy_sync``, ``color_id``, ``naming``.  The lifecycle is
distinct from the marking-menu bench:

* **Standalone** — first ``ui.show()`` triggers ``MainWindow.showEvent``
  which fires ``register_children``, walking every wrapped widget and
  invoking its ``<widget>_init`` slot method (combo population, tree
  builds, Maya scene queries, …).  This is usually the dominant cost.

* **Stacked menu** — ``MarkingMenu._init_ui`` re-parents the UI under
  the menu's stacked layout and applies styling; ``register_children``
  also fires during the eventual ``setCurrentWidget`` show, but the
  visual cost is hidden behind the gesture animation.

Subclass and override :meth:`setup_switchboard` to wire your project.
Optionally override :meth:`setup_marking_menu` if your project's real
path constructs a marking menu first (so its cost is bundled into
phase 02 the same way :class:`MarkingMenuInitBench` does it).

Phases timed (sub-millisecond resolution, ``time.perf_counter``):

  ``01_imports``
      Import :class:`uitk.Switchboard`.

  ``02_construct``
      Construct whatever the project needs before a UI can be loaded:
      a bare ``Switchboard``, a ``TclMaya`` that builds its own
      switchboard internally, etc.  Subclasses decide.

  ``03_lazy_load_ui``
      First ``sb.get_ui(UI_NAME)``.  Triggers the
      :class:`uitk.loaders.compiled.CompiledLoader` path (hash check,
      ``importlib`` exec of ``_ui.py``, ``setupUi``) and
      :meth:`Switchboard.add_ui` (wrap in ``MainWindow``,
      :class:`SettingsManager` branch, tag merge).

  ``04_register_children``
      ``ui.register_children()`` walks every wrapped widget and fires
      its ``<widget>_init`` slot method.  This is where heavy
      per-widget setup lives — combo population, tree builds, Maya
      scene queries, etc.  Calling it explicitly here isolates that
      cost from the visual ``show()`` cost.

  ``05_first_show``
      ``ui.show()``.  ``register_children`` already ran so this is
      the pure visual show + first paint.

  ``06_drain_after_show``
      Pump deferred ``QTimer.singleShot(0, ...)`` retries scheduled
      during register / show so they're attributed to this UI.

  ``07_warm_show``
      Second ``ui.show()`` after a ``hide()``.  Should be near-zero.
      A non-trivial result here means something on the warm-show path
      is doing work that should have been gated to first-show only.

  ``08_warm_load_via_loader``
      Direct second call to ``sb._loader.load(filepath)`` — isolates
      the per-call cost of the loader (``ensure_compiled`` hash check
      + ``_import_compiled_module`` re-exec + ``setupUi``) from the
      ``add_ui`` / ``register_children`` cost in phases 03+04.
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


class StandaloneUiInitBench:
    """Reusable bench for standalone ``QMainWindow`` UIs.

    Subclass and override :meth:`setup_switchboard`.  The default
    :meth:`setup_marking_menu` is a no-op; override only if your
    project's real path constructs a marking menu before opening these
    UIs (e.g. tentacle's ``TclMaya``, which registers mayatk UIs onto
    its switchboard via ``MayaUiHandler``).
    """

    #: Default UI to load.  Override per subclass or pass via ``ui_name``.
    UI_NAME = "ui"

    def __init__(
        self,
        ui_name: Optional[str] = None,
        label: str = "run",
    ) -> None:
        self.ui_name = ui_name or self.UI_NAME
        self.label = label

    # ------------------------------------------------------------------
    # Subclass extension points
    # ------------------------------------------------------------------

    def setup_switchboard(self):
        """Return the :class:`Switchboard` the bench will load through.

        Subclasses that bundle construction (e.g. tentacle's ``TclMaya``
        builds its own switchboard internally) should construct the
        bundle here and return ``mm.sb`` — phase 02 will absorb the
        full bundled cost.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.setup_switchboard() must be overridden"
        )

    # ------------------------------------------------------------------
    # Bench body
    # ------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Run the bench end-to-end and return a result dict."""
        from qtpy import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is None:
            raise RuntimeError(
                "StandaloneUiInitBench requires an existing QApplication "
                "in the active Python process."
            )

        def _ck(msg: str) -> None:
            print(f"[bench] {msg}", flush=True)

        timer = _PhaseTimer()

        _ck("01 imports")
        with timer.measure("01_imports"):
            from uitk import Switchboard  # noqa: F401

        _ck("02 construct")
        with timer.measure("02_construct"):
            sb = self.setup_switchboard()

        _ck(f"03 lazy load ui {self.ui_name!r}")
        with timer.measure("03_lazy_load_ui"):
            ui = sb.get_ui(self.ui_name)
        if ui is None:
            raise RuntimeError(
                f"UI {self.ui_name!r} resolved to None — check registry"
            )
        widget_count = len(ui.findChildren(QtWidgets.QWidget))
        _ck(f"03 done; widgets={widget_count}")

        _ck("04 register_children")
        with timer.measure("04_register_children"):
            # ``register_children`` is idempotent — re-running it is a
            # no-op once children have been wrapped.  Calling it
            # explicitly here means we attribute the cost to this phase
            # rather than to ``show()`` where it would otherwise fire
            # via ``MainWindow.showEvent``.
            if hasattr(ui, "register_children"):
                ui.register_children()

        _ck("05 first show")
        with timer.measure("05_first_show"):
            ui.show()

        _ck("06 drain after show")
        with timer.measure("06_drain_after_show"):
            for _ in range(20):
                app.processEvents(QtCore.QEventLoop.AllEvents, 12)

        _ck("07 warm show (after hide)")
        ui.hide()
        for _ in range(5):
            app.processEvents(QtCore.QEventLoop.AllEvents, 4)
        with timer.measure("07_warm_show"):
            ui.show()
            for _ in range(5):
                app.processEvents(QtCore.QEventLoop.AllEvents, 4)

        _ck("08 warm load via loader")
        ui_path = sb.registry.ui_registry.get(
            filename=self.ui_name, return_field="filepath"
        )
        if ui_path:
            with timer.measure("08_warm_load_via_loader"):
                # Build a fresh widget tree directly via the loader.
                # No add_ui / register_children — pure per-call loader
                # cost.  The orphan tree is discarded.
                _ = sb._loader.load(ui_path)
        else:
            timer.entries.append(("08_warm_load_via_loader", float("nan")))

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
            "widget_count": widget_count,
            "phases_ms_best": phases,
            "first_load_total_ms_best": _sum(
                "03_lazy_load_ui",
                "04_register_children",
                "05_first_show",
            ),
            "warm_show_ms_best": phases.get("07_warm_show"),
            "warm_load_ms_best": phases.get("08_warm_load_via_loader"),
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
            f"widgets={result.get('widget_count')}"
        )
        lines.append(f"{'phase':<48} {'ms':>10}")
        lines.append("-" * 60)
        for k, ms in (result.get("phases_ms_best") or {}).items():
            ms_str = "nan" if ms != ms else f"{ms:.2f}"
            lines.append(f"{k:<48} {ms_str:>10}")
        lines.append("-" * 60)
        lines.append(
            f"{'first load total (03+04+05)':<48} "
            f"{result.get('first_load_total_ms_best', 0):>10.2f}"
        )
        warm_show = result.get("warm_show_ms_best")
        warm_show_str = (
            "n/a"
            if warm_show is None or warm_show != warm_show
            else f"{warm_show:.2f}"
        )
        lines.append(f"{'warm show (07)':<48} {warm_show_str:>10}")
        warm_load = result.get("warm_load_ms_best")
        warm_load_str = (
            "n/a"
            if warm_load is None or warm_load != warm_load
            else f"{warm_load:.2f}"
        )
        lines.append(f"{'warm load via loader (08)':<48} {warm_load_str:>10}")
        return "\n".join(lines)
