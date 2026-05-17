"""Register, install-on-demand, and launch external Python tools as subprocesses.

Each tool is a pip-installable Python package whose UI is exposed via a
class (entry point). Tools run in a fresh interpreter so they don't share
the host process's Qt event loop or block Maya / Blender / Max on errors.

Typical usage::

    sb.handlers.external_tool.register(
        "map_compositor",
        module="map_compositor",
        entry="MapCompositorUI",
        install_spec="map_compositor",
    )
    sb.handlers.external_tool.launch("map_compositor")
"""
import os
import shutil
import subprocess
import sys
from typing import Dict, Optional

import pythontk as ptk

from uitk.switchboard import Switchboard


# Host executables whose `-c` flag does NOT mean "run Python code" —
# routing a Python snippet through them invokes MEL / MaxScript / etc.
# When detected as sys.executable, we substitute the sibling python binary.
_DCC_HOST_SIBLINGS = {
    "maya.exe": "mayapy.exe",
    "maya": "mayapy",
    "3dsmax.exe": "3dsmaxpy.exe",
    "blender.exe": "python.exe",  # Blender ships python in <install>/<ver>/python/bin
    "blender": "python",
}


def _default_python() -> str:
    """Best-effort pick of a standalone Python interpreter.

    Order:
      1. ``python`` / ``python3`` on PATH (a real CPython, ideal for pip).
      2. Sibling pythonised binary if ``sys.executable`` is a DCC host
         (e.g. maya.exe -> mayapy.exe in the same bin/).
      3. ``sys.executable`` (last resort).
    """
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            return found

    exe = sys.executable or ""
    base = os.path.basename(exe).lower()
    sibling = _DCC_HOST_SIBLINGS.get(base)
    if sibling:
        candidate = os.path.join(os.path.dirname(exe), sibling)
        if os.path.isfile(candidate):
            return candidate

    return exe


class ExternalToolHandler(ptk.SingletonMixin, ptk.LoggingMixin):
    """Switchboard handler for launching external Python tools.

    Resolves the tool's importability in a target Python interpreter,
    installs the package via :class:`pythontk.PackageManager` when
    missing, and launches the UI in a detached subprocess via
    :class:`pythontk.AppLauncher`.
    """

    DEFAULTS: dict = {}

    def __init__(
        self,
        switchboard: Switchboard,
        log_level: str = "WARNING",
        **kwargs,
    ):
        if switchboard is None:
            raise ValueError(
                f"{self.__class__.__name__} requires a Switchboard instance."
            )
        self.sb = switchboard
        self.logger.setLevel(log_level)
        self._tools: Dict[str, dict] = {}
        # Cache of widgets returned in in-process mode, keyed by tool name.
        # Re-launching by name returns the cached widget so close-and-reopen
        # via the same button doesn't create duplicate windows.
        self._in_process_widgets: Dict[str, object] = {}

    @classmethod
    def instance(cls, switchboard: Switchboard = None, **kwargs):
        kwargs.setdefault("switchboard", switchboard)
        kwargs["singleton_key"] = (cls, id(switchboard))
        return super().instance(**kwargs)

    @property
    def config(self):
        return self.sb.configurable.branch("external_tool")

    def register(
        self,
        name: str,
        *,
        module: str,
        entry: Optional[str] = None,
        install_spec: Optional[str] = None,
        python: Optional[str] = None,
        show_kwargs: Optional[dict] = None,
        mode: str = "subprocess",
    ) -> None:
        """Pre-register a tool so it can be launched by name.

        Parameters:
            name: Unique identifier used with :meth:`launch`.
            module: Importable module name (e.g. ``"map_compositor"``).
            entry: Class/callable inside *module* that returns a uitk
                MainWindow when invoked. Required for ``mode="in_process"``.
                In ``mode="subprocess"`` it's optional — if omitted the
                tool is launched via ``python -m <module>``.
            install_spec: ``pip install`` target used when *module* is
                not importable. PyPI name, ``git+https://...`` URL, or
                any value pip accepts. If *None*, a missing module
                raises ``RuntimeError`` at launch time.
            python: Path to the Python interpreter to use for the
                subprocess. Ignored in ``mode="in_process"``. ``None``
                (default) uses :func:`_default_python`.
            show_kwargs: Extra kwargs forwarded to the UI's ``show()``
                call in subprocess mode. Defaults to
                ``{"pos": "screen", "app_exec": True}``. Ignored in
                ``mode="in_process"`` — caller controls show().
            mode: ``"subprocess"`` (default) launches in a fresh
                interpreter; returns ``subprocess.Popen``. ``"in_process"``
                imports into the current interpreter and returns the UI
                widget so the caller can parent / show / dock it
                (e.g. under a Maya main window).
        """
        self._tools[name] = {
            "module": module,
            "entry": entry,
            "install_spec": install_spec,
            "python": python,
            "show_kwargs": show_kwargs,
            "mode": mode,
        }

    def is_registered(self, name: str) -> bool:
        return name in self._tools

    def launch(
        self,
        name: Optional[str] = None,
        *,
        module: Optional[str] = None,
        entry: Optional[str] = None,
        install_spec: Optional[str] = None,
        python: Optional[str] = None,
        show_kwargs: Optional[dict] = None,
        mode: Optional[str] = None,
    ):
        """Launch a registered tool, or an ad-hoc tool from kwargs.

        Kwargs override any value supplied at :meth:`register` time. The
        combined config must at minimum provide *module*.

        Returns:
            ``subprocess.Popen`` in ``mode="subprocess"``, or the UI
            widget in ``mode="in_process"``. Caller is responsible for
            parent/show in the in-process case.
        """
        cfg = dict(self._tools.get(name, {})) if name else {}
        for k, v in (
            ("module", module),
            ("entry", entry),
            ("install_spec", install_spec),
            ("python", python),
            ("show_kwargs", show_kwargs),
            ("mode", mode),
        ):
            if v is not None:
                cfg[k] = v

        if not cfg.get("module"):
            raise ValueError(
                "launch() requires a registered name or module= kwarg."
            )

        run_mode = cfg.get("mode", "subprocess")
        py = sys.executable if run_mode == "in_process" else (
            cfg.get("python") or _default_python()
        )

        if not self._is_importable(cfg["module"], py):
            spec = cfg.get("install_spec")
            if not spec:
                raise RuntimeError(
                    f"Module {cfg['module']!r} is not available in "
                    f"{py} and no install_spec was provided."
                )
            self.logger.info(f"Installing {spec!r} into {py}")
            ptk.PackageManager(python_path=py).install(spec)
            if not self._is_importable(cfg["module"], py):
                raise RuntimeError(
                    f"Install of {spec!r} completed but {cfg['module']!r} "
                    f"is still not importable in {py}."
                )

        if run_mode == "in_process":
            cached = self._in_process_widgets.get(name) if name else None
            if cached is not None and self._widget_alive(cached):
                return cached
            widget = self._import_entry(cfg["module"], cfg.get("entry"))
            if name:
                self._in_process_widgets[name] = widget
            return widget

        return self._spawn(
            python=py,
            module=cfg["module"],
            entry=cfg.get("entry"),
            show_kwargs=cfg.get("show_kwargs"),
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _is_importable(module: str, python: str) -> bool:
        """Return True if *module* can be imported under *python*."""
        if python == sys.executable:
            from importlib.util import find_spec

            try:
                return find_spec(module) is not None
            except (ImportError, ValueError):
                return False

        try:
            result = subprocess.run(
                [python, "-c", f"import {module}"],
                capture_output=True,
                timeout=15,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _widget_alive(widget) -> bool:
        """Return True if the underlying C++ widget hasn't been deleted.

        Qt deletes C++ widgets independently of Python references (e.g. via
        ``WA_DeleteOnClose`` or explicit ``deleteLater``); accessing a
        method on a dead wrapper raises ``RuntimeError``.
        """
        try:
            widget.objectName()
            return True
        except RuntimeError:
            return False

    @staticmethod
    def _import_entry(module: str, entry: Optional[str]):
        """Import *module* in the current interpreter and instantiate *entry*.

        Returns the result of ``getattr(module, entry)()`` — typically a
        UI widget the caller will parent + show. *entry* is required in
        in-process mode (there's no ``-m`` fallback equivalent).
        """
        if not entry:
            raise ValueError(
                "in_process mode requires an `entry` (no `python -m` "
                "equivalent for in-process launch)."
            )
        import importlib

        mod = importlib.import_module(module)
        entry_obj = getattr(mod, entry, None)
        if entry_obj is None:
            raise AttributeError(
                f"Module {module!r} has no attribute {entry!r}."
            )
        return entry_obj()

    @staticmethod
    def _spawn(
        python: str,
        module: str,
        entry: Optional[str],
        show_kwargs: Optional[dict],
    ):
        """Spawn a detached subprocess that opens *module*'s UI."""
        if entry:
            sk = show_kwargs if show_kwargs is not None else {
                "pos": "screen",
                "app_exec": True,
            }
            kwargs_src = ", ".join(f"{k}={v!r}" for k, v in sk.items())
            snippet = (
                f"from {module} import {entry};"
                f"ui = {entry}();"
                f"ui.show({kwargs_src})"
            )
            args = ["-c", snippet]
        else:
            args = ["-m", module]

        return ptk.AppLauncher.launch(python, args=args)
