"""Reusable benchmark for the option_box menu initialization lifecycle.

Designed to run inside any live ``QApplication`` host — a DCC, an IDE,
or plain Python.  uitk deliberately stays host-agnostic: this module
imports nothing from ``maya``, ``max``, etc.  Project-specific consumers
(e.g. tentacle's option_box bench) subclass :class:`OptionBoxInitBench`,
implement :meth:`setup_switchboard`, and decide how to *drive* the bench
(launch a fresh DCC, run inline, …); the rest of the lifecycle timing
is shared.

The bench is strictly **one-shot per host process**.  The lifecycle we
care about (cold slot init, first option_box show) is by definition a
once-per-DCC-session event, and re-running it inside the same Qt
session diverges from the real path.  Aggregate across multiple host
launches if you need noise reduction — that's the driver's job.

Phases timed (sub-millisecond resolution, ``time.perf_counter``):

  ``02_switchboard_construct``
      Construct the :class:`Switchboard` with the project's UI / slot
      sources.  Cost is dominated by registry scans and module imports.

  ``03_load_ui_file``
      Resolve and load the requested ``.ui`` file via :class:`QUiLoader`.

  ``04_register_children_sync``
      Walk the loaded UI and call ``register_widget`` on every widget,
      which in turn invokes each slot's ``<name>_init`` method.  This is
      the synchronous body of every ``tbXXX_init`` /
      ``widget.option_box.menu.add(...)`` call.

  ``05_drain_deferred_timers``
      Pump the Qt event loop so the ``QTimer.singleShot(0, ...)`` retries
      scheduled by ``Menu.add`` and ``OptionBoxManager`` complete.  This
      is where the visible flicker originates.

  ``06_first_show_option_box_menu``
      First time we click an option_box's dropdown — exercises the
      ``Menu.showEvent`` lazy-init pile-up.
"""

from __future__ import annotations

import gc
import time
from contextlib import contextmanager
from typing import Any, Optional


class _PhaseTimer:
    """Records ordered (name, ms) entries via :meth:`measure`."""

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


class OptionBoxInitBench:
    """Reusable option_box init benchmark.

    Subclass and override :meth:`setup_switchboard` to wire your project.
    """

    #: Default UI to load.  Override per subclass or pass via ``ui_name``.
    DEFAULT_UI = "edit"

    def __init__(
        self,
        ui_name: Optional[str] = None,
        label: str = "run",
    ) -> None:
        self.ui_name = ui_name or self.DEFAULT_UI
        self.label = label

    # ------------------------------------------------------------------
    # Subclass extension points
    # ------------------------------------------------------------------

    def setup_switchboard(self):
        """Construct and return a configured :class:`uitk.Switchboard`.

        Subclasses must override.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.setup_switchboard() must be overridden"
        )

    def post_switchboard(self, sb) -> None:
        """Hook for subclasses to do any patching after construction.

        For example, tentacle wires ``sb.handlers.marking_menu`` so its
        slot constructors don't AttributeError.  Default: no-op.
        """
        return None

    # ------------------------------------------------------------------
    # Bench body
    # ------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Run the bench end-to-end and return a result dict.

        One-shot: construct the switchboard, load the UI, time the
        lifecycle phases, emit numbers.  No teardown — Qt cleans up when
        the host process exits.  This matches the only path that has
        ever been stable inside a real DCC session.
        """
        from qtpy import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is None:
            raise RuntimeError(
                "OptionBoxInitBench requires an existing QApplication "
                "in the active Python process."
            )

        def _ck(msg: str) -> None:
            print(f"[bench] {msg}", flush=True)

        timer = _PhaseTimer()

        _ck("01 begin imports")
        with timer.measure("01_imports"):
            from uitk import Switchboard  # noqa: F401
            from uitk.widgets.optionBox.utils import patch_common_widgets

            patch_common_widgets()

        _ck("02 begin switchboard ctor")
        with timer.measure("02_switchboard_construct"):
            sb = self.setup_switchboard()
            self.post_switchboard(sb)

        _ck(f"03 begin load ui {self.ui_name!r}")
        with timer.measure("03_load_ui_file"):
            ui = getattr(sb.loaded_ui, self.ui_name)

        widget_count = len(ui.findChildren(QtWidgets.QWidget))
        _ck(f"03 done; widgets={widget_count}")

        _ck("04 begin register_children")
        with timer.measure("04_register_children_sync"):
            ui.register_children()
        _ck("04 done")

        _ck("05 begin drain")
        with timer.measure("05_drain_deferred_timers"):
            for _ in range(20):
                app.processEvents(QtCore.QEventLoop.AllEvents, 12)
        _ck("05 done")

        sample_btn = self._find_sample_option_box_button(ui)
        _ck(f"06 sample btn = {sample_btn.objectName() if sample_btn else None}")

        if sample_btn is not None:
            _ck("06 begin show_as_popup")
            with timer.measure("06_first_show_option_box_menu"):
                sample_btn.option_box.menu.show_as_popup(
                    anchor_widget=sample_btn, position="bottom"
                )
                for _ in range(20):
                    app.processEvents(QtCore.QEventLoop.AllEvents, 12)
            _ck("06 hide menu")
            sample_btn.option_box.menu.hide()
            _ck("06 done")
        else:
            timer.entries.append(("06_first_show_option_box_menu", float("nan")))

        wrapped_menus, total_items = self._inventory_option_boxes(ui)
        _ck(f"done (menus={wrapped_menus} items={total_items})")

        phases = {n: round(ms, 3) for n, ms in timer.entries}
        return {
            "label": self.label,
            "ui": self.ui_name,
            "widget_count": widget_count,
            "wrapped_menus": wrapped_menus,
            "total_menu_items": total_items,
            "sample_widget": sample_btn.objectName() if sample_btn else None,
            "phases_ms_best": phases,
            "init_total_ms_best": round(
                sum(
                    ms
                    for n, ms in timer.entries
                    if n in ("04_register_children_sync", "05_drain_deferred_timers")
                ),
                3,
            ),
            "first_show_ms_best": next(
                (
                    round(ms, 3)
                    for n, ms in timer.entries
                    if n == "06_first_show_option_box_menu"
                ),
                None,
            ),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_sample_option_box_button(ui):
        """Return the first ``tbXXX`` widget whose option_box menu has items."""
        from qtpy import QtWidgets

        for w in ui.findChildren(QtWidgets.QWidget):
            name = w.objectName() or ""
            if not name.startswith("tb"):
                continue
            mgr = getattr(w, "option_box", None)
            if mgr is None:
                continue
            menu = getattr(mgr, "_menu", None)
            if menu is None:
                continue
            if hasattr(menu, "contains_items") and not menu.contains_items:
                continue
            return w
        return None

    @staticmethod
    def _inventory_option_boxes(ui):
        from qtpy import QtWidgets

        wrapped, items = 0, 0
        for w in ui.findChildren(QtWidgets.QWidget):
            mgr = getattr(w, "option_box", None) if hasattr(w, "option_box") else None
            if mgr is None:
                continue
            menu = getattr(mgr, "_menu", None)
            if menu is None:
                continue
            if hasattr(menu, "contains_items") and menu.contains_items:
                wrapped += 1
                if hasattr(menu, "get_items"):
                    items += sum(1 for _ in menu.get_items())
        return wrapped, items

    # ------------------------------------------------------------------
    # Pretty-printing
    # ------------------------------------------------------------------

    @staticmethod
    def format_report(result: dict[str, Any]) -> str:
        """Human-readable table for the result of :meth:`run`."""
        lines = []
        lines.append(
            f"# {result.get('label', 'run')}  ui={result.get('ui')}  "
            f"widgets={result.get('widget_count')}  "
            f"menus={result.get('wrapped_menus')}  "
            f"items={result.get('total_menu_items')}"
        )
        lines.append(f"{'phase':<48} {'ms':>10}")
        lines.append("-" * 60)
        for k, ms in (result.get("phases_ms_best") or {}).items():
            lines.append(f"{k:<48} {ms:>10.2f}")
        lines.append("-" * 60)
        lines.append(f"{'init total (04+05)':<48} {result.get('init_total_ms_best', 0):>10.2f}")
        lines.append(
            f"{'first show (06)':<48} "
            f"{(result.get('first_show_ms_best') or 0):>10.2f}"
        )
        return "\n".join(lines)
