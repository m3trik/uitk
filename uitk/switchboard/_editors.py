# !/usr/bin/python
# coding=utf-8
"""Mixin that exposes the bundled editor windows on the Switchboard.

The Switchboard ships three top-level editor windows that operate on its
state — :class:`StyleEditor`, :class:`HotkeyEditor`, and
:class:`SwitchboardBrowser`. Without a central exposure point each caller
re-implements the same five-line pattern of "cache, probe for deletion,
recreate if dead, show, raise". This mixin centralizes that:

    self.sb.editors.show("style")          # opens / focuses by name
    self.sb.editors.browser                # property access
    self.sb.editors.show("browser").raise_()

Editor instances are cached on the registry — re-showing the same window
across invocations rather than spawning a new one — and auto-recover when
the underlying Qt object has been deleted (e.g. the user clicked the OS
close button and Qt destroyed the C++ side).

Mirrors the spirit of :class:`mayatk.MayaUiHandler`'s "use what's given,
otherwise stand one up" pattern; the mixin doesn't need a host instance
because the Switchboard itself is the ambient host.
"""
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List

if TYPE_CHECKING:  # pragma: no cover
    from qtpy import QtWidgets


class _EditorRegistry:
    """Lazy, auto-recovering cache of singleton editors bound to a Switchboard.

    The registry hands out one instance per editor name and rebuilds the
    instance if a stale C++ pointer is detected. Parent resolution prefers
    the switchboard's marking-menu handler (so editors land in the same
    window tree as other floating tools) and falls back to the
    switchboard's QObject parent.
    """

    # Editor names → factory specs. Each spec is a (module_path, class_name,
    # needs_switchboard) triple resolved lazily so importing the mixin
    # doesn't drag every editor module into memory.
    _EDITORS: Dict[str, tuple] = {
        "style": ("uitk.widgets.editors.style_editor", "StyleEditor", False),
        "hotkey": ("uitk.widgets.editors.hotkey_editor", "HotkeyEditor", True),
        "browser": (
            "uitk.widgets.editors.switchboard_browser",
            "SwitchboardBrowser",
            True,
        ),
    }

    def __init__(self, sb):
        self._sb = sb
        self._cache: Dict[str, Any] = {}
        # Hooks run once, immediately after each editor is built. Lets
        # host packages (tentacle/mayatk) wire DCC-specific configuration
        # (e.g. Maya collision checkers) without coupling uitk to them.
        self._post_build_hooks: Dict[str, List[Callable]] = {}

    # ── Public API ──────────────────────────────────────────────────────────

    def names(self) -> Iterable[str]:
        """Return the editor names this registry knows how to build."""
        return tuple(self._EDITORS.keys())

    def add_post_build_hook(self, name: str, hook: Callable) -> None:
        """Register a callable to run when *name* editor is first built.

        The hook receives the editor instance:
        ``hook(editor) -> None``. Hooks fire once per build (which means
        again after the editor is destroyed and recreated). Registration
        is idempotent — adding the same hook twice has no effect.

        Args:
            name: Editor name (one of :meth:`names`).
            hook: ``Callable[[editor], None]``.
        """
        if name not in self._EDITORS:
            raise KeyError(
                f"Unknown editor {name!r}. Available: {', '.join(self.names())}"
            )
        bucket = self._post_build_hooks.setdefault(name, [])
        if hook not in bucket:
            bucket.append(hook)

    def get(self, name: str) -> "QtWidgets.QWidget":
        """Return a live editor instance for *name*.

        Constructs on first access; subsequent accesses return the cached
        instance unless the Qt object has been destroyed, in which case
        the registry rebuilds transparently.
        """
        if name not in self._EDITORS:
            raise KeyError(
                f"Unknown editor {name!r}. Available: {', '.join(self.names())}"
            )
        cached = self._cache.get(name)
        if cached is not None and self._is_alive(cached):
            return cached
        instance = self._build(name)
        self._cache[name] = instance
        return instance

    def show(self, name: str, *, raise_window: bool = True) -> "QtWidgets.QWidget":
        """Show, optionally raise / activate, and return the named editor.

        Folds the four-step pattern from every caller (cache check,
        deletion probe, show, raise) into one call.

        Popup-context recovery
        ----------------------
        When this is called from inside a ``QMenu`` action slot (i.e. the
        user clicked a menu item which fired our slot), the menu's
        ``hideEvent`` runs *after* the slot returns and explicitly
        ``raise_()`` / ``activateWindow()``-s the previously-active
        window — which buries our just-shown editor. To survive that,
        we detect the active-popup case via :meth:`_is_in_popup_context`
        and schedule a deferred re-raise on the next event-loop tick,
        after the menu has finished closing. The synchronous show +
        raise still happens first so callers and tests see the window
        become visible immediately.
        """
        from qtpy import QtCore

        editor = self.get(name)
        editor.show()
        if raise_window:
            editor.raise_()
            editor.activateWindow()
            if self._is_in_popup_context(editor):
                QtCore.QTimer.singleShot(
                    0,
                    lambda e=editor: (e.raise_(), e.activateWindow()),
                )
        return editor

    @staticmethod
    def _is_in_popup_context(editor) -> bool:
        """True when an active popup will steal focus back from *editor*.

        Returns True iff there is currently an active popup widget that
        is *not* the editor itself — meaning the popup's own hide flow
        will run after our caller returns and re-raise its
        previously-active window. The editor needs a deferred re-raise
        to survive that.
        """
        from qtpy import QtWidgets

        active_popup = QtWidgets.QApplication.activePopupWidget()
        return active_popup is not None and active_popup is not editor

    # ── Property shortcuts ──────────────────────────────────────────────────

    @property
    def style(self) -> "QtWidgets.QWidget":
        return self.get("style")

    @property
    def hotkey(self) -> "QtWidgets.QWidget":
        return self.get("hotkey")

    @property
    def browser(self) -> "QtWidgets.QWidget":
        return self.get("browser")

    # ── Internal ────────────────────────────────────────────────────────────

    def _resolve_parent(self):
        """Pick the most appropriate parent for a freshly-built editor.

        Prefers ``sb.handlers.marking_menu`` so editors join the same
        floating-window tree as the marking-menu-launched UIs. Falls back
        to the switchboard's QObject parent (which always exists since
        Switchboard inherits from QObject) — typically the host DCC's
        main window.
        """
        handlers = getattr(self._sb, "handlers", None)
        marking_menu = getattr(handlers, "marking_menu", None) if handlers else None
        if marking_menu is not None:
            return marking_menu
        return self._sb.parent()

    @staticmethod
    def _is_alive(instance) -> bool:
        """Probe a Qt object to detect a deleted C++ underlying.

        Catches both ``RuntimeError`` (the standard PySide signal that
        the wrapped C++ object has been deleted) and ``AttributeError``
        (which some shiboken builds raise for partially-disposed
        wrappers). Anything else is unexpected and we let it propagate.
        """
        try:
            instance.objectName()
            return True
        except (RuntimeError, AttributeError):
            return False

    def _build(self, name: str):
        """Instantiate the editor by name, importing its module on demand."""
        module_path, class_name, needs_switchboard = self._EDITORS[name]
        import importlib

        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        parent = self._resolve_parent()
        if needs_switchboard:
            instance = cls(switchboard=self._sb, parent=parent)
        else:
            instance = cls(parent=parent)

        for hook in self._post_build_hooks.get(name, ()):
            try:
                hook(instance)
            except Exception as exc:  # noqa: BLE001
                logger = getattr(self._sb, "logger", None)
                if logger is not None:
                    logger.warning(
                        f"[editors] Post-build hook {hook} raised for {name!r}: {exc}"
                    )
        return instance


class SwitchboardEditorsMixin:
    """Adds an ``editors`` property to Switchboard exposing the bundled editors.

    Lazy: the registry isn't created until the first ``sb.editors`` access,
    so applications that never open an editor pay nothing for the import.
    """

    @property
    def editors(self) -> _EditorRegistry:
        """Cached editor registry — see :class:`_EditorRegistry`."""
        if not hasattr(self, "_editors_registry"):
            self._editors_registry = _EditorRegistry(self)
        return self._editors_registry
