# !/usr/bin/python
# coding=utf-8
"""Common infrastructure for Switchboard handlers.

Centralises the boilerplate that every handler used to duplicate:

* the ``switchboard`` guard,
* the ``instance()`` singleton classmethod keyed by ``(cls, id(sb))``
  (a bare ``id(sb)`` key collides with sibling handlers — see the test
  ``test_singleton_key_does_not_collide_with_other_handlers``),
* ``self.config`` mapped onto ``sb.configurable.branch(...)``,
* a unified ``_notify_entries_changed`` helper that routes through the
  Switchboard's signals so subscribers (e.g. the browser) connect once,
* Show/Hide row-refresh wiring for a handler's windows
  (``_wire_widget_visibility``),
* the rendering helpers behind the optional ``launch_code`` contract method
  (``_launch_script`` / ``_import_code`` / ``_path_code``).

Handlers that want their items in the unified launcher surface (browser)
additionally implement the four-method launchable contract documented on
:class:`LaunchableHandlerProtocol` (validated at register time —
inheriting the protocol is optional, duck-typing is sufficient).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import (
    TYPE_CHECKING,
    Iterable,
    List,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

import pythontk as ptk

if TYPE_CHECKING:  # pragma: no cover
    from uitk.handlers.handler_entry import HandlerEntry
    from uitk.switchboard import Switchboard


class _VisibilityForwarder:
    """Event filter that forwards a widget's Show/Hide events to a handler.

    Lives as a child of the watched widget — Qt owns its lifetime; when
    the widget is destroyed, this object goes with it. Holds only a
    weak reference to the handler to avoid keeping the Switchboard
    alive past its natural lifetime.

    Qt's QEvent.Show / QEvent.Hide fire on every QWidget regardless of
    inheritance, so this works for uitk MainWindows, plain QWidgets,
    and anything in between — important because external apps can
    return arbitrary widget classes, and the bundled editors carry no
    ``on_show`` / ``on_hide`` signals.

    The relay is queued to the next event-loop turn, never run inside the
    event: Qt also sends a window its Hide from inside ``~QWidget``, and a
    listener there (the browser's own model, emitting into its own view)
    touches children mid-destruction -- an access violation. It carries the
    handler weakref and the name, not this filter, so it still arrives when
    the window is gone by then.
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

            def relay(handler_ref, entry_name):
                handler = handler_ref()
                if handler is not None:
                    try:
                        handler._notify_entries_changed(entry_name)
                    except Exception:
                        pass

            class _Forwarder(QtCore.QObject):
                def __init__(self, handler, entry_name, parent=None):
                    super().__init__(parent)
                    self._handler_ref = weakref.ref(handler)
                    self._name = entry_name

                def eventFilter(self, obj, event):
                    shown_or_hidden = event.type() in (
                        QtCore.QEvent.Show,
                        QtCore.QEvent.Hide,
                    )
                    if shown_or_hidden and QtCore.QCoreApplication.instance():
                        ref, name = self._handler_ref, self._name
                        QtCore.QTimer.singleShot(0, lambda: relay(ref, name))
                    return False  # never consume — let the widget handle normally

            cls._qt_class = _Forwarder
        return cls._qt_class(handler, name, parent)


class BaseHandler(ptk.SingletonMixin, ptk.LoggingMixin):
    """Common base for Switchboard handlers.

    Subclasses set :attr:`CONFIG_BRANCH` (the name passed to
    ``sb.configurable.branch(...)``) and optionally :attr:`DEFAULTS`;
    ``Switchboard.register_handler`` seeds the branch with those values.

    Singleton key is ``(cls, id(sb))`` so two distinct handler classes
    bound to the same Switchboard don't collide.
    """

    CONFIG_BRANCH: Optional[str] = None
    DEFAULTS: dict = {}

    def __init__(
        self,
        switchboard: "Switchboard",
        log_level: str = "WARNING",
        **_kwargs,
    ):
        if switchboard is None:
            raise ValueError(f"{type(self).__name__} requires a Switchboard instance.")
        self.sb = switchboard
        self.logger.setLevel(log_level)

    @classmethod
    def instance(cls, switchboard: "Switchboard" = None, **kwargs):
        kwargs.setdefault("switchboard", switchboard)
        kwargs["singleton_key"] = (cls, id(switchboard))
        return super().instance(**kwargs)

    @property
    def config(self):
        branch = self.CONFIG_BRANCH or type(self).__name__
        return self.sb.configurable.branch(branch)

    # ── launchable-contract helpers ───────────────────────────────────

    def _notify_entries_changed(self, entry_name: Optional[str] = None) -> None:
        """Fan-out an entry-state-changed event through the Switchboard.

        Two-tier granularity:
          * ``entry_name=None`` → coarse "this handler's entry set may
            have changed" (registration / unregistration of an item).
          * ``entry_name=<name>`` → fine "one entry's live state changed"
            (visibility, status, …).

        Routes through ``sb.on_handler_entries_changed`` and
        ``sb.on_handler_entry_changed`` respectively. Subscribers connect
        to the sb-level signals once and receive events for every handler
        — matching the existing ``on_ui_registered`` pattern.
        """
        handler_name = self._sb_handler_name() or type(self).__name__
        if entry_name is None:
            sig = getattr(self.sb, "on_handler_entries_changed", None)
            if sig is not None:
                sig.emit(handler_name)
        else:
            sig = getattr(self.sb, "on_handler_entry_changed", None)
            if sig is not None:
                sig.emit(handler_name, entry_name)

    def _sb_handler_name(self) -> Optional[str]:
        """Look up the attribute name this handler is bound to on ``sb.handlers``.

        Returns ``None`` during init (handler being constructed before
        ``register_handler`` finishes) or if the handler has been detached.
        Callers fall back to the class name in that case — good enough
        for signal routing without forcing handlers to know their own
        binding.
        """
        handlers = getattr(self.sb, "handlers", None)
        if handlers is None:
            return None
        for name, value in vars(handlers).items():
            if value is self:
                return name
        return None

    def _wire_widget_visibility(self, widget, name: str) -> None:
        """Install a Show/Hide event filter so the row refreshes on any hide path.

        Idempotent — guarded by a per-widget flag attribute. The filter
        is kept alive by being a child of the widget itself, so it stays
        in scope as long as the widget does.

        Event filter is preferred over signal hookup because a handler's
        windows may or may not be uitk MainWindows; ``QEvent.Show``/
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

    # ── Standalone launch code (the optional ``launch_code`` method) ────

    @staticmethod
    def _launch_script(
        name: str,
        imports: Iterable[str],
        body: Iterable[str],
        app: Optional[str] = None,
    ) -> str:
        """Assemble a ``launch_code`` snippet: header, imports, *body*, loop tail.

        Parameters:
            name: The launched entry, named in the header comment.
            imports: Import lines *body* needs; duplicates collapse.
            body: Statements that stand up the host objects and launch.
            app: Expression naming the QApplication once *body* ran. Given
                it, the snippet runs Qt's event loop only when it created that
                application itself -- a plain ``python`` process. Inside a host
                that already has one (Maya, a Qt-hosting Blender) the loop is
                the host's and the window just opens. ``None`` for a launch
                whose window lives in another process.

        Returns:
            The snippet, newline-terminated.
        """
        imports = list(imports)
        if app:
            imports.append("from qtpy import QtWidgets")
        # isort's order: plain ``import x`` first, then ``from x import y``.
        imports = sorted(
            dict.fromkeys(imports), key=lambda line: (line.startswith("from "), line)
        )
        lines = [f"# Launch {name!r} standalone (generated by uitk's launch_code)."]
        lines += imports + [""]
        if app:
            lines.append("owns_loop = QtWidgets.QApplication.instance() is None")
        lines += list(body)
        if app:
            lines += [
                "if owns_loop:  # plain Python: no host app is running Qt's loop",
                f"    {app}.exec_()",
            ]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _import_code(obj) -> Optional[Tuple[str, str]]:
        """``(import_line, name)`` re-importing class *obj* in a fresh session.

        Prefers the package root's public name (``from mayatk import
        MayaUiHandler``) -- the stable contract -- over the defining module.

        Returns:
            None for anything a fresh interpreter cannot import by name:
            ``__main__``, a nested class, a registry's synthetic
            ``*_ptk_loader_*`` module.
        """
        module = getattr(obj, "__module__", None) or ""
        name = getattr(obj, "__qualname__", "") or ""
        if (
            not name
            or "." in name
            or module in ("", "__main__")
            or "_ptk_loader_" in module
        ):
            return None
        root = module.split(".")[0]
        try:
            if getattr(sys.modules.get(root), name, None) is obj:
                return f"from {root} import {name}", name
        except Exception:  # a lazy package root may raise on an unknown name
            pass
        if getattr(sys.modules.get(module), name, None) is obj:
            return f"from {module} import {name}", name
        return None

    @staticmethod
    def _path_code(path: str) -> Tuple[List[str], str]:
        """``(imports, expr)`` spelling *path* (a file or a directory) from its
        importable package.

        The top-most ``__init__.py`` directory at or above *path* names the
        package. When this process imports that package from the same place,
        *path* becomes ``os.path.join(os.path.dirname(<pkg>.__file__), ...)``
        -- it follows the package through a reinstall or a Python upgrade.
        Anything else is spelled as its absolute path.
        """
        path = os.path.abspath(path)
        top = None
        cur = path if os.path.isdir(path) else os.path.dirname(path)
        while True:
            if os.path.isfile(os.path.join(cur, "__init__.py")):
                top = cur
            elif top is not None:
                break
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        if top is not None:
            pkg = os.path.basename(top)
            try:
                spec = importlib.util.find_spec(pkg)
            except (ImportError, ValueError):
                spec = None

            def _key(p: str) -> str:
                return os.path.normcase(os.path.realpath(p))

            locations = getattr(spec, "submodule_search_locations", None) or ()
            if pkg.isidentifier() and any(_key(p) == _key(top) for p in locations):
                expr = f"os.path.dirname({pkg}.__file__)"
                rel = os.path.relpath(path, top)
                if rel != os.curdir:
                    args = ", ".join(repr(p) for p in rel.split(os.sep))
                    expr = f"os.path.join({expr}, {args})"
                return ["import os", f"import {pkg}"], expr
        if os.sep == "\\":
            path = path.replace("\\", "/")  # Windows takes '/' too, and it reads
        return [], repr(path)


@runtime_checkable
class LaunchableHandlerProtocol(Protocol):
    """Structural type for handlers that participate in the launcher surface.

    Inheritance is optional — the Switchboard validates the contract by
    duck-typing at ``register_handler`` time (mirrors ``_LOADER_CONTRACT``).
    Use this protocol for type hints and ``isinstance`` checks; for the
    runtime source of truth see ``Switchboard._LAUNCHABLE_CONTRACT``.

    Optional methods, probed by the browser with ``getattr``:

    * ``save_tags(name, tags)`` — for handlers whose entries report
      ``editable_tags=True``. The browser only calls it for those entries.
    * ``focus(name)`` — raise an already-visible entry (the row's Focus
      button). Without it, Focus is a no-op for the handler's rows.
    * ``launch_code(name, **options) -> Optional[str]`` — Python that
      launches the entry standalone, in a fresh interpreter or a DCC shelf
      button, with its dependencies re-established; *options* are the
      launch options ``launch`` would get. ``None`` when no importable
      spelling exists. Backs the browser's *Copy launch code* row action.
    """

    def entries(self) -> Iterable["HandlerEntry"]: ...
    def launch(self, name: str, **options): ...
    def close(self, name: str) -> None: ...
    def is_visible(self, name: str) -> bool: ...
