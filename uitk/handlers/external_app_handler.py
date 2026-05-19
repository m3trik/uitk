"""Register, install-on-demand, and launch external Python apps as subprocesses.

Each app is a pip-installable Python package whose UI is exposed via a
class (entry point). Apps run in a fresh interpreter so they don't share
the host process's Qt event loop or block Maya / Blender / Max on errors.

Typical usage::

    sb.handlers.external_app.register(
        "map_compositor",
        module="extapps.map_compositor",
        entry="MapCompositorUI",
        install_spec="extapps",
    )
    sb.handlers.external_app.launch("map_compositor")
"""
import os
import shutil
import subprocess
import sys
from typing import Dict, Iterable, Optional, Set

import pythontk as ptk

from uitk.switchboard import Switchboard
from uitk.handlers.base_handler import BaseHandler
from uitk.handlers.handler_entry import HandlerEntry


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


class _VisibilityForwarder:
    """Event filter that forwards a widget's Show/Hide events to a handler.

    Lives as a child of the watched widget — Qt owns its lifetime; when
    the widget is destroyed, this object goes with it. Holds only a
    weak reference to the handler to avoid keeping the Switchboard
    alive past its natural lifetime.

    Qt's QEvent.Show / QEvent.Hide fire on every QWidget regardless of
    inheritance, so this works for uitk MainWindows, plain QWidgets,
    and anything in between — important because external apps can
    return arbitrary widget classes.
    """

    def __new__(cls, handler, name, parent=None):
        # Defer the QObject base class binding until first use to avoid
        # importing qtpy at module-load time (this file is imported
        # before qtpy is guaranteed to be on sys.path in some headless
        # test setups).
        from qtpy import QtCore
        import weakref

        # Build a one-off subclass that mixes our forwarder logic into
        # QObject. Cached on the class so we don't rebuild per widget.
        if not hasattr(cls, "_qt_class"):

            class _Forwarder(QtCore.QObject):
                def __init__(self, handler, entry_name, parent=None):
                    super().__init__(parent)
                    self._handler_ref = weakref.ref(handler)
                    self._name = entry_name

                def eventFilter(self, obj, event):
                    t = event.type()
                    if t in (QtCore.QEvent.Show, QtCore.QEvent.Hide):
                        handler = self._handler_ref()
                        if handler is not None:
                            try:
                                handler._notify_entries_changed(self._name)
                            except Exception:
                                pass
                    return False  # never consume — let the widget handle normally

            cls._qt_class = _Forwarder
        return cls._qt_class(handler, name, parent)


class ExternalAppHandler(BaseHandler):
    """Switchboard handler for launching external Python apps.

    Resolves the app's importability in a target Python interpreter,
    installs the package via :class:`pythontk.PackageManager` when
    missing, and launches the UI in a detached subprocess via
    :class:`pythontk.AppLauncher`.

    Implements the launchable contract so registered apps appear
    alongside .ui-backed UIs in the unified launcher (e.g. browser).
    """

    CONFIG_BRANCH = "external_app"
    DEFAULTS: dict = {}

    # Entry-point groups consulted by :meth:`discover` to find
    # self-describing apps installed in the current environment.
    # Mapping is group -> default mode. The app's pyproject.toml
    # declares which group it belongs to; hosts don't need to know.
    DISCOVERY_GROUPS: Dict[str, str] = {
        "uitk.external_apps": "subprocess",
        "uitk.external_apps.in_process": "in_process",
    }

    def __init__(
        self,
        switchboard: Switchboard,
        log_level: str = "WARNING",
        auto_discover: bool = True,
        **kwargs,
    ):
        super().__init__(switchboard=switchboard, log_level=log_level)
        self._apps: Dict[str, dict] = {}
        # Cache of widgets returned in in-process mode, keyed by app name.
        # Re-launching by name returns the cached widget so close-and-reopen
        # via the same button doesn't create duplicate windows.
        self._in_process_widgets: Dict[str, object] = {}
        # Cache of Popen handles for subprocess-mode launches so
        # ``is_visible`` can report "running" without re-polling the OS
        # process table.
        self._subprocesses: Dict[str, "subprocess.Popen"] = {}
        if auto_discover:
            self.discover()

    def discover(self, groups: Optional[Iterable[str]] = None) -> int:
        """Auto-register every app advertised under a uitk entry-point group.

        Apps opt in by declaring an entry point in their own package
        metadata — no host edits required to surface a new app. Two
        groups are recognised by default:

        * ``uitk.external_apps`` — launched in a subprocess (safe default).
        * ``uitk.external_apps.in_process`` — launched in the current
          interpreter (for Qt-clean apps that want to be parented under
          a DCC host like Maya).

        Example (in an app's ``pyproject.toml``)::

            [project.entry-points."uitk.external_apps.in_process"]
            metashape_workflow = "metashape_workflow:MetashapeWorkflowUI [photogrammetry,materials]"

        ``name = module:Class [tag1,tag2,...]`` — name becomes the
        registration key, ``module:Class`` becomes module + entry,
        bracketed extras become tags.

        Returns the count of apps newly registered. Re-registers
        existing entries on each call (idempotent).
        """
        try:
            from importlib.metadata import entry_points
        except ImportError:  # pragma: no cover — covered by all 3.8+ runtimes
            return 0
        scan = dict(self.DISCOVERY_GROUPS) if groups is None else {
            g: self.DISCOVERY_GROUPS.get(g, "subprocess") for g in groups
        }
        count = 0
        for group, mode in scan.items():
            try:
                # Python 3.10+: entry_points(group=...) selector.
                eps = entry_points(group=group)
            except TypeError:  # pragma: no cover — Python 3.8/3.9 path
                eps = entry_points().get(group, [])
            for ep in eps:
                try:
                    module = ep.module  # left of ':' — never imports
                    attr = ep.attr      # right of ':'
                    extras = list(ep.extras) if getattr(ep, "extras", None) else []
                except Exception:
                    self.logger.warning(
                        f"[discover] could not parse entry point {ep!r}",
                        exc_info=True,
                    )
                    continue
                self.register(
                    ep.name,
                    module=module,
                    entry=attr,
                    tags=set(extras) if extras else None,
                    mode=mode,
                )
                count += 1
        if count:
            self.logger.debug(
                f"[discover] registered {count} app(s) "
                f"from groups {list(scan)}"
            )
        return count

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
        tags: Optional[Iterable[str]] = None,
    ) -> None:
        """Pre-register an app so it can be launched by name.

        Parameters:
            name: Unique identifier used with :meth:`launch`.
            module: Importable module name (e.g. ``"extapps.map_compositor"``).
            entry: Class/callable inside *module* that returns a uitk
                MainWindow when invoked. Required for ``mode="in_process"``.
                In ``mode="subprocess"`` it's optional — if omitted the
                app is launched via ``python -m <module>``.
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
            tags: Optional iterable of tags applied to this app's
                :class:`HandlerEntry`. Surfaces in the browser's tag
                filter just like .ui-backed tags.
        """
        self._apps[name] = {
            "module": module,
            "entry": entry,
            "install_spec": install_spec,
            "python": python,
            "show_kwargs": show_kwargs,
            "mode": mode,
            "tags": frozenset(tags or ()),
        }
        self._notify_entries_changed()

    def is_registered(self, name: str) -> bool:
        return name in self._apps

    def unregister(self, name: str) -> None:
        """Remove an app. No-op if not registered."""
        if self._apps.pop(name, None) is not None:
            self._in_process_widgets.pop(name, None)
            self._subprocesses.pop(name, None)
            self._notify_entries_changed()

    # ── Launchable contract ──────────────────────────────────────────────

    def entries(self) -> Iterable[HandlerEntry]:
        """Yield one :class:`HandlerEntry` per registered app.

        Kind reflects the launch mode so the browser can render a
        distinguishing chip.

        Two tag stores, mirroring the .ui semantic:
          * ``inherited_tags`` — declared at registration (manual
            ``register(tags=...)``) or in the entry-point's bracketed
            ``[extras]``. Read-only; surfaces as the same dimmed chips
            .ui filename/source-directory tags use.
          * ``file_tags`` — user-curated tags persisted in the handler's
            config branch via :meth:`save_tags`. Editable inline (the
            browser's QLineEdit delegate calls back into us). Always a
            (possibly empty) frozenset — never ``None`` — so every
            external-app row is editable, just like .ui rows.
        """
        user_tags = self._user_tags()
        for name, cfg in self._apps.items():
            mode = cfg.get("mode", "subprocess")
            kind = (
                "external_in_process"
                if mode == "in_process"
                else "external_subprocess"
            )
            yield HandlerEntry(
                name=name,
                kind=kind,
                handler=self,
                inherited_tags=frozenset(cfg.get("tags") or ()),
                file_tags=frozenset(user_tags.get(name, ())),
                # No on-disk file — the editable_tags property checks
                # ``filepath is not None``, so we expose a synthetic
                # config:// URI to mark "editable, but not file-backed".
                filepath=f"config://external_app/{name}",
            )

    # ── Editable tags via the handler's config branch ────────────────────

    _USER_TAGS_KEY = "user_tags"

    def _user_tags(self) -> Dict[str, list]:
        """Return the persisted {app_name: [tag, …]} dict.

        Stored under a single key so the whole mapping round-trips
        through QSettings as one value (avoids per-key fan-out and the
        delete-keys-not-in-dict bookkeeping that comes with that).

        Strips any leading "#" from stored values on read so existing
        data with a leftover prefix (from a pre-fix session) heals
        itself the first time it's rendered — no migration step
        required.
        """
        raw = self.config.value(self._USER_TAGS_KEY, {}) or {}
        if not isinstance(raw, dict):
            return {}
        cleaned: Dict[str, list] = {}
        for app_name, tags in raw.items():
            if not isinstance(tags, (list, tuple)):
                continue
            kept = sorted({
                stripped
                for t in tags
                if isinstance(t, str)
                and (stripped := t.strip().lstrip("#").strip())
            })
            if kept:
                cleaned[app_name] = kept
        return cleaned

    def save_tags(self, name: str, tags: Iterable[str]) -> None:
        """Persist *tags* for *name* in the handler's config branch.

        This is the launchable contract's optional ``save_tags`` method —
        the browser's inline editor calls it on commit. Tags persist
        across sessions via :class:`SettingsManager` so the user's
        curation isn't lost on app restart.
        """
        if name not in self._apps:
            raise ValueError(f"No such external app: {name!r}")
        # Strip leading "#" too — that prefix is display formatting,
        # not part of the tag identity. Stored values stay "clean" so
        # filtering / set-comparison works without double-hashing.
        clean = sorted({
            stripped
            for t in tags
            if (stripped := t.strip().lstrip("#").strip())
        })
        store = dict(self._user_tags())
        if clean:
            store[name] = clean
        else:
            store.pop(name, None)
        self.config.setValue(self._USER_TAGS_KEY, store)
        self._notify_entries_changed(name)

    def close(self, name: str) -> None:
        """Hide an in-process widget; terminate a subprocess.

        ``close`` is best-effort for subprocesses — sends ``terminate``
        and clears the handle. The OS does the rest.
        """
        widget = self._in_process_widgets.get(name)
        if widget is not None:
            try:
                if hasattr(widget, "hide"):
                    widget.hide()
            except RuntimeError:
                # C++ object already deleted.
                pass
            self._notify_entries_changed(name)
            return
        proc = self._subprocesses.get(name)
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
            self._subprocesses.pop(name, None)
            self._notify_entries_changed(name)

    def is_visible(self, name: str) -> bool:
        widget = self._in_process_widgets.get(name)
        if widget is not None:
            try:
                return bool(widget.isVisible())
            except RuntimeError:
                return False
        proc = self._subprocesses.get(name)
        if proc is not None:
            still_running = proc.poll() is None
            if not still_running:
                # Process has exited; drop the stale handle so the row
                # reverts to "launchable" on the next refresh.
                self._subprocesses.pop(name, None)
            return still_running
        return False

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
        show: bool = True,
        **_options,
    ):
        """Launch a registered app, or an ad-hoc app from kwargs.

        Kwargs override any value supplied at :meth:`register` time. The
        combined config must at minimum provide *module*.

        ``show=False`` (in-process mode only) returns the widget after
        install + import + reparent + visibility wiring, but does NOT
        call ``show()/raise_()/activateWindow()``. Use this when the
        caller wants to inject host context (e.g. set
        ``ui.slots.texture_provider``) and then route the widget through
        a custom show path (such as the marking menu's cursor-relative
        positioning). Ignored in subprocess mode — the launch always
        starts the process.

        Returns:
            ``subprocess.Popen`` in ``mode="subprocess"``, or the UI
            widget in ``mode="in_process"`` (already parented under
            the Switchboard's parent — typically the host DCC's main
            window — and shown/raised/activated when ``show=True``).
            Caller may re-parent or re-show but no longer has to.
        """
        cfg = dict(self._apps.get(name, {})) if name else {}
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
            try:
                ptk.PackageManager(python_path=py).install(spec)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to install {spec!r} into {py}: {e}"
                ) from e
            if not self._is_importable(cfg["module"], py):
                raise RuntimeError(
                    f"Install of {spec!r} completed but {cfg['module']!r} "
                    f"is still not importable in {py}."
                )

        if run_mode == "in_process":
            cached = self._in_process_widgets.get(name) if name else None
            if cached is not None and self._widget_alive(cached):
                widget = cached
            else:
                widget = self._import_entry(cfg["module"], cfg.get("entry"))
                if name:
                    self._in_process_widgets[name] = widget
            if show:
                self._show_in_process(widget, name=name)
            else:
                self._prepare_in_process(widget, name=name)
            if name:
                self._notify_entries_changed(name)
            return widget

        proc = self._spawn(
            python=py,
            module=cfg["module"],
            entry=cfg.get("entry"),
            show_kwargs=cfg.get("show_kwargs"),
        )
        if name and proc is not None:
            self._subprocesses[name] = proc
            self._notify_entries_changed(name)
        return proc

    # ------------------------------------------------------------------

    def _prepare_in_process(self, widget, name: Optional[str] = None) -> None:
        """Reparent under the host and wire visibility tracking, but do NOT show.

        Use this when the caller plans to route the widget through a
        custom show path (e.g. ``marking_menu.show()`` for cursor-
        relative positioning) and just needs the widget primed.

        Re-parenting preserves the widget's own ``windowFlags`` (external
        apps come fully-styled — frameless, translucent, etc.); passing
        a bare ``Qt.Window`` to ``setParent`` would replace flags wholesale
        and break the look. The ``| Qt.Window`` is required because Qt
        only treats a child as a top-level window when that flag is set;
        without it, the app would dock as an inline child of the host.

        Also installs a visibility-tracking event filter on the widget
        (idempotent) so the row-state refresh signal fires when the user
        hides the app by any path — its own header X, ALT+F4, a
        programmatic ``widget.hide()``. Without this, the browser's row
        icon stays stuck on "Focus" because no entries-changed signal
        ever fires on hide.
        """
        try:
            from qtpy import QtCore as _QtCore

            host_parent = self.sb.parent() if hasattr(self.sb, "parent") else None
            if host_parent is not None and widget.parent() is not host_parent:
                widget.setParent(host_parent, widget.windowFlags() | _QtCore.Qt.Window)
            if name is not None:
                self._wire_widget_visibility(widget, name)
        except Exception:
            # Best-effort. If the widget is a non-Qt object (mock in tests,
            # custom launcher returning a plain Python object), the caller
            # still gets the instance back and can handle display itself.
            self.logger.debug(
                f"[_prepare_in_process] could not prepare widget {widget!r}",
                exc_info=True,
            )

    def _show_in_process(self, widget, name: Optional[str] = None) -> None:
        """Prepare the widget then show + raise + activate.

        Centralised so every launch path produces a visible window —
        the browser, a slot's launch button, an ``instance.launch(...)``
        call from a Python console all behave the same.
        """
        self._prepare_in_process(widget, name=name)
        try:
            widget.show()
            widget.raise_()
            widget.activateWindow()
        except Exception:
            self.logger.debug(
                f"[_show_in_process] could not display widget {widget!r}",
                exc_info=True,
            )

    def _wire_widget_visibility(self, widget, name: str) -> None:
        """Install a Show/Hide event filter so the row refreshes on any hide path.

        Idempotent — guarded by a per-widget flag attribute. The filter
        is kept alive by being a child of the widget itself, so it stays
        in scope as long as the widget does.

        Event filter is preferred over signal hookup because external
        apps may or may not be uitk MainWindows; ``QEvent.Show``/
        ``QEvent.Hide`` fire on every QWidget regardless of inheritance.
        """
        if getattr(widget, "_uitk_external_visibility_wired", False):
            return
        try:
            from qtpy import QtCore as _QtCore
        except ImportError:
            return
        filt = _VisibilityForwarder(self, name, parent=widget)
        widget.installEventFilter(filt)
        widget._uitk_external_visibility_wired = True

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
