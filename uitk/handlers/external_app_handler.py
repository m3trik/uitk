"""Register, install-on-demand, and launch external Python apps as subprocesses.

Each app is a pip-installable Python package whose UI is exposed via a
class (entry point). Apps run in a fresh interpreter so they don't share
the host process's Qt event loop or block Maya / Blender / Max on errors.

Apps self-describe via ``uitk.external_apps[.in_process]`` entry points,
so a host normally registers nothing — :meth:`ExternalAppHandler.discover`
(run on construction) picks them up and derives each app's ``install_spec``
from its distribution automatically. A host only needs to point at the
*provider* package when it might not be installed yet::

    sb.handlers.external_app.add_provider("extapps")   # install-on-demand
    sb.handlers.external_app.launch("compositor")      # installs + launches

Direct registration is still available for ad-hoc / out-of-band apps::

    sb.handlers.external_app.register(
        "compositor",
        module="extapps.texture_maps.compositor",
        entry="CompositorUI",
        install_spec="extapps",
    )
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

    # Entry-point group hosts use to advertise *provider packages* — a
    # package that ships discoverable apps but may not be installed yet.
    # ``name = install_spec`` (e.g. ``extapps = "extapps"``). Read by
    # :meth:`discover`; absent providers self-install on first launch
    # of any of their apps (see :meth:`_bootstrap_providers`).
    PROVIDER_GROUP: str = "uitk.external_app_providers"

    # Entry-point extras beginning with this prefix are host-visibility
    # gates (``hide_maya`` -> hidden in the ``maya`` context) rather than
    # semantic browser tags. See :meth:`_partition_extras`.
    HIDE_PREFIX: str = "hide_"

    def __init__(
        self,
        switchboard: Switchboard,
        log_level: str = "WARNING",
        auto_discover: bool = True,
        **kwargs,
    ):
        super().__init__(switchboard=switchboard, log_level=log_level)
        self._apps: Dict[str, dict] = {}
        # Provider packages that ship discoverable apps but may not be
        # installed yet. Keyed by install_spec; consulted on a launch miss.
        self._providers: Dict[str, dict] = {}
        # install_specs already attempted this session, so a launch miss
        # doesn't reinstall a provider on every click.
        self._bootstrapped: Set[str] = set()
        # Cache of widgets returned in in-process mode, keyed by app name.
        # Re-launching by name returns the cached widget so close-and-reopen
        # via the same button doesn't create duplicate windows.
        self._in_process_widgets: Dict[str, object] = {}
        # Cache of Popen handles for subprocess-mode launches so
        # ``is_visible`` can report "running" without re-polling the OS
        # process table.
        self._subprocesses: Dict[str, "subprocess.Popen"] = {}
        if auto_discover:
            self._discover_providers()
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
        scan = dict(self.DISCOVERY_GROUPS) if groups is None else {
            g: self.DISCOVERY_GROUPS.get(g, "subprocess") for g in groups
        }
        count = 0
        for group, mode in scan.items():
            for ep in self._entry_points(group):
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
                # Split extras: ``hide_<host>`` extras are host-visibility
                # gates (exclusion semantics, never displayed); everything
                # else is a plain semantic tag for the browser filter.
                tags, hidden_in = self._partition_extras(extras)
                # The app's distribution name *is* its install spec — read
                # it straight off the entry point so a missing package can
                # self-install on first launch with zero host bookkeeping.
                # ``ep.dist`` is Python 3.10+; older runtimes (and the test
                # fakes) simply yield no spec and fall back to the provider
                # mechanism / a manual ``install_spec``.
                spec = getattr(getattr(ep, "dist", None), "name", None)
                self.register(
                    ep.name,
                    module=module,
                    entry=attr,
                    install_spec=spec,
                    tags=tags or None,
                    hidden_in=hidden_in or None,
                    mode=mode,
                )
                count += 1
        if count:
            self.logger.debug(
                f"[discover] registered {count} app(s) "
                f"from groups {list(scan)}"
            )
        return count

    @staticmethod
    def _entry_points(group: str) -> list:
        """Return the entry points in *group*, across importlib versions.

        Centralises the Python 3.10+ ``entry_points(group=...)`` selector
        vs the 3.8/3.9 ``entry_points().get(group, [])`` mapping form so
        both :meth:`discover` and :meth:`_discover_providers` share one path.
        """
        try:
            from importlib.metadata import entry_points
        except ImportError:  # pragma: no cover — present on all 3.8+ runtimes
            return []
        try:
            return list(entry_points(group=group))
        except TypeError:  # pragma: no cover — Python 3.8/3.9 selector signature
            return list(entry_points().get(group, []))

    @classmethod
    def _partition_extras(cls, extras: Iterable[str]) -> "tuple[set, set]":
        """Split entry-point *extras* into (semantic tags, host gates).

        ``hide_<host>`` extras become the host-visibility gate set (with
        the prefix stripped); all other extras are plain semantic tags.
        Keeping the two apart means a domain tag like ``photogrammetry``
        can never gate an app out of a host whose ``context_tags`` happens
        not to contain it.
        """
        tags: Set[str] = set()
        hidden_in: Set[str] = set()
        for extra in extras:
            if extra.startswith(cls.HIDE_PREFIX):
                gate = extra[len(cls.HIDE_PREFIX):].strip()
                if gate:
                    hidden_in.add(gate)
            else:
                tags.add(extra)
        return tags, hidden_in

    # ── Provider packages (install-on-demand) ────────────────────────────

    @staticmethod
    def _base_pkg_name(install_spec: str) -> str:
        """Best-effort import name for a pip *install_spec*.

        Strips version pins / extras / URL fragments so the spec can be
        probed for importability before installing. Works for the common
        ``name``/``name==1.0``/``name[extra]`` forms; for anything exotic
        (VCS URLs) the caller should pass an explicit ``probe_module``.
        """
        spec = install_spec.strip()
        for sep in ("[", "==", ">=", "<=", "~=", ">", "<", "@", " "):
            spec = spec.split(sep, 1)[0]
        return spec.strip()

    def add_provider(
        self,
        install_spec: str,
        *,
        probe_module: Optional[str] = None,
        group: Optional[str] = None,
        python: Optional[str] = None,
    ) -> None:
        """Register a provider package that ships discoverable apps.

        A provider is a pip-installable package whose apps self-describe
        via the discovery entry-point groups but which may not be
        installed in the target interpreter yet. When an app name fails
        to resolve at :meth:`launch` time, the handler installs each
        not-yet-importable provider and re-runs :meth:`discover` before
        giving up — so a host needs to know only *which package* provides
        apps, never the per-app module/entry table.

        Parameters:
            install_spec: ``pip install`` target (PyPI name, ``name[extra]``,
                ``git+https://...`` URL, ...).
            probe_module: Import name used to check whether the provider is
                already present (avoids a needless reinstall). Defaults to
                the spec's base package name.
            group: Discovery entry-point group the provider feeds; picks the
                install interpreter (in-process groups install into the
                current interpreter, others into a standalone Python).
                Defaults to the in-process group.
            python: Explicit interpreter to install into; overrides *group*.
        """
        self._providers[install_spec] = {
            "install_spec": install_spec,
            "probe_module": probe_module or self._base_pkg_name(install_spec),
            "group": group,
            "python": python,
        }

    def _discover_providers(self) -> int:
        """Register providers advertised under :attr:`PROVIDER_GROUP`.

        Lets a host declare its providers declaratively in its own
        ``pyproject.toml`` (``extapps = "extapps"``) instead of in code.
        The entry-point name is the probe/import name; its value is the
        install spec. Returns the count registered.
        """
        count = 0
        for ep in self._entry_points(self.PROVIDER_GROUP):
            try:
                spec = ep.value  # raw RHS string — the install spec
            except Exception:
                continue
            self.add_provider(spec, probe_module=ep.name, group=None)
            count += 1
        return count

    def _bootstrap_providers(self, python: Optional[str] = None) -> bool:
        """Make untried providers' apps resolvable, then re-discover.

        Called on a launch miss. Each provider is attempted at most once
        per session (tracked in ``self._bootstrapped``) so a wrong app
        name doesn't reinstall on every click. A provider that's already
        importable is left alone (no install) but discovery still re-runs,
        in case its apps weren't registered when the handler was built.

        Returns True if any provider was attempted this call (so the
        caller should re-resolve the app); False if there was nothing
        new to try.
        """
        pending = [s for s in self._providers if s not in self._bootstrapped]
        if not pending:
            return False
        for spec in pending:
            self._bootstrapped.add(spec)
            prov = self._providers[spec]
            group = prov.get("group")
            mode = self.DISCOVERY_GROUPS.get(group) if group else "in_process"
            py = python or prov.get("python") or (
                sys.executable if mode == "in_process" else _default_python()
            )
            if self._is_importable(prov["probe_module"], py):
                continue  # already present — re-discovery below surfaces it
            if os.path.basename(py).lower() in _DCC_HOST_SIBLINGS:
                # Can't pip into a live DCC interpreter (maya.exe / blender.exe)
                # — the install would hang. Rely on the package being present in
                # the host's env; the launch raises a clean error if it isn't.
                self.logger.warning(
                    f"[provider] {spec!r} not importable but {py!r} is a DCC "
                    f"host — skipping install (provision it into the host env)."
                )
                continue
            self.logger.info(f"[provider] installing {spec!r} into {py}")
            try:
                ptk.PackageManager(python_path=py).install(spec)
            except Exception:
                self.logger.warning(
                    f"[provider] install of {spec!r} failed", exc_info=True
                )
        try:
            self.discover()
        except Exception:
            self.logger.debug(
                "[provider] post-bootstrap discover failed", exc_info=True
            )
        return True

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
        hidden_in: Optional[Iterable[str]] = None,
    ) -> None:
        """Pre-register an app so it can be launched by name.

        Parameters:
            name: Unique identifier used with :meth:`launch`.
            module: Importable module name (e.g. ``"extapps.texture_maps.compositor"``).
            entry: Class/callable inside *module* that returns a uitk
                MainWindow when invoked. Required for ``mode="in_process"``.
                In ``mode="subprocess"`` it's optional — if omitted the
                app is launched via ``python -m <module>``.
            install_spec: ``pip install`` target used when *module* is
                not importable. PyPI name, ``git+https://...`` URL, or
                any value pip accepts. If *None*, a missing module
                raises ``RuntimeError`` at launch time. Usually left to
                :meth:`discover`, which derives it automatically from the
                app's distribution (``entry_point.dist.name``).
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
                filter just like .ui-backed tags. Purely semantic — tags
                never affect *visibility* (see *hidden_in*).
            hidden_in: Optional iterable of host context tags this app
                should be hidden in. A host whose switchboard
                ``context_tags`` intersects this set won't list the app
                (it stays launchable by name). Exclusion semantics —
                an empty set (the default) means "visible everywhere".
                Kept separate from *tags* so a semantic tag can never
                accidentally gate an app out of a host. Maya, for
                instance, hides the Substance/Marmoset panels
                (``hidden_in={"maya"}``) because it ships native bridges.
        """
        self._apps[name] = {
            "module": module,
            "entry": entry,
            "install_spec": install_spec,
            "python": python,
            "show_kwargs": show_kwargs,
            "mode": mode,
            "tags": frozenset(tags or ()),
            "hidden_in": frozenset(hidden_in or ()),
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
        # Host curation: a non-empty switchboard context hides any app
        # gated against one of its tags (``hidden_in``). Mirrors the
        # widget-level ``apply_visibility_policy`` — an empty context
        # disables filtering, so standalone hosts list everything.
        context = frozenset(getattr(self.sb, "context_tags", None) or ())
        for name, cfg in self._apps.items():
            if context and (cfg.get("hidden_in") or frozenset()) & context:
                continue
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
        overrides = (
            ("module", module),
            ("entry", entry),
            ("install_spec", install_spec),
            ("python", python),
            ("show_kwargs", show_kwargs),
            ("mode", mode),
        )

        def _resolve():
            c = dict(self._apps.get(name, {})) if name else {}
            for k, v in overrides:
                if v is not None:
                    c[k] = v
            return c

        cfg = _resolve()

        # Bootstrap miss: a name the host never registered (because its
        # provider package isn't installed yet). Install the provider(s)
        # and re-discover, then re-resolve before giving up.
        if name and not cfg.get("module") and self._providers:
            if self._bootstrap_providers():
                cfg = _resolve()

        if not cfg.get("module"):
            raise ValueError(
                "launch() requires a registered name or module= kwarg."
            )

        run_mode = cfg.get("mode", "subprocess")
        py = sys.executable if run_mode == "in_process" else (
            cfg.get("python") or _default_python()
        )

        importable = self._is_importable(cfg["module"], py)
        if not importable and name and module is None:
            # Self-heal a stale cached registration. An app's entry-point
            # module path can change on disk after discovery was cached — a
            # package move (``foo`` -> ``foo.sub``) or a version bump in an
            # editable install that rewrites the entry-point metadata. The
            # in-memory ``self._apps`` still points at the old path, so the
            # import fails. When the module came from the registry (no explicit
            # ``module=`` kwarg), re-discover once and retry with the refreshed
            # path before assuming the package is missing and (re)installing it
            # — cheaper than a pip install and it spares the user a host restart.
            before = dict(self._apps.get(name, {}))
            try:
                self.discover()
            except Exception:  # noqa: BLE001 — best-effort; fall through to install
                self.logger.debug("[launch] re-discovery failed", exc_info=True)
            refreshed = self._apps.get(name)
            if refreshed is not None:
                # discover() rebuilds the registration from entry-point metadata
                # alone; restore launch-augmentation fields a manual register()
                # added (install_spec / python / show_kwargs) so re-discovery
                # corrects the module path without degrading the registration.
                for k in ("install_spec", "python", "show_kwargs"):
                    if not refreshed.get(k) and before.get(k):
                        refreshed[k] = before[k]
            refreshed = refreshed or {}
            if refreshed.get("module") and refreshed["module"] != before.get("module"):
                self.logger.info(
                    f"[launch] {name!r} re-discovered: "
                    f"{before.get('module')!r} -> {refreshed['module']!r}"
                )
                cfg["module"] = refreshed["module"]
                if entry is None and refreshed.get("entry"):
                    cfg["entry"] = refreshed["entry"]
                importable = self._is_importable(cfg["module"], py)

        if not importable:
            spec = cfg.get("install_spec")
            if not spec:
                # No per-app spec — a registered provider may still own this
                # module. Install providers and retry once before failing.
                if self._providers and self._bootstrap_providers(python=py):
                    importable = self._is_importable(cfg["module"], py)
                if not importable:
                    raise RuntimeError(
                        f"Module {cfg['module']!r} is not available in "
                        f"{py} and no install_spec was provided."
                    )
            else:
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
            import qtpy  # noqa: F401 -- availability probe (headless callers)
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
