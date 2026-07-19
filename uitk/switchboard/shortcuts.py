# !/usr/bin/python
# coding=utf-8
"""Switchboard-side keyboard shortcut machinery.

This module is paired with :mod:`uitk.managers.shortcut_manager`:

* The generic primitives (``GlobalShortcut``, ``ShortcutManager``,
  ``ShortcutMixin``, scope-name <-> ``Qt.ShortcutContext`` helpers)
  live in ``uitk.managers.shortcut_manager`` and can be used by any
  widget independent of Switchboard.

* The Switchboard-only pieces (the ``@Shortcut`` slot-decorator and
  ``SwitchboardShortcutMixin`` which scans Slot classes for decorated
  methods, applies user overrides from ``ui.settings``, and live-binds
  ``QShortcut`` objects on the main window) live here.

Public surface re-exported from :mod:`uitk.switchboard`:
    Shortcut — slot-method decorator, e.g. ``@Shortcut("Ctrl+S")``.
"""
import inspect
from typing import Any, Callable, Dict, List, Optional
from qtpy import QtCore, QtGui, QtWidgets

from uitk.managers.shortcut_manager import (
    GlobalShortcut,
    SCOPE_NAME_TO_CONTEXT,
    context_to_scope_name,
    host_namespace_suffix,
    resolve_application_host,
    scope_name_to_context,
)


def _as_bool(value: Any) -> bool:
    """Coerce a persisted settings value to ``bool``.

    The QSettings backend may round-trip a bool as a real ``bool`` or as a
    ``"true"``/``"false"`` / ``"1"``/``"0"`` string depending on platform, so a
    bare ``bool(value)`` would read the string ``"false"`` as ``True``. Normalize
    both forms here.
    """
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


class Shortcut:
    """Decorator to assign a keyboard shortcut to a slot method.

    This decorator attaches metadata to the function that the Switchboard uses
    to automatically register QShortcuts when the slots class is instantiated.

    Args:
        sequence (str): Key sequence (e.g., "Ctrl+S", "Alt+F4").
        context (QtCore.Qt.ShortcutContext, optional): The context for the shortcut.
            Defaults to Qt.WindowShortcut (Available when parent window is focused).
            Use Qt.WidgetShortcut for widget-specific scope.
        name (str, optional): A human-readable name for the action (for Settings/UI).
            Defaults to the function name.
        doc (str, optional): A description of the action. Defaults to function docstring.
        robust (bool, optional): If True, uses GlobalShortcut with event filtering,
            which is more reliable in complex hosts (like Maya) and supports release events.
            Defaults to False (standard QShortcut).
        hidden (bool, optional): If True, the binding is omitted from the shortcut
            editor's default view (still listed under the editor's "Show hidden"
            toggle, so it remains discoverable and collision-checked). Use for
            conventional/functional keys that should not clutter the list.
            Defaults to False. May be overridden per-binding at runtime via
            :meth:`SwitchboardShortcutMixin.set_binding_hidden`.
        editable (bool, optional): If False, the binding is shown in the editor
            but cannot be rebound by the user (a fixed, semantic key). Defaults
            to True.
    """

    def __init__(
        self,
        sequence: str,
        context: QtCore.Qt.ShortcutContext = QtCore.Qt.WindowShortcut,
        name: Optional[str] = None,
        doc: Optional[str] = None,
        robust: bool = False,
        hidden: bool = False,
        editable: bool = True,
    ):
        self.sequence = sequence
        self.context = context
        self.name = name
        self.doc = doc
        self.robust = robust
        self.hidden = hidden
        self.editable = editable

    def __call__(self, func: Callable) -> Callable:
        func._shortcut_meta = {
            "sequence": self.sequence,
            "context": self.context,
            "name": self.name,
            "doc": self.doc,
            "robust": self.robust,
            "hidden": self.hidden,
            "editable": self.editable,
        }
        return func


class SwitchboardShortcutMixin:
    """Mixin for managing keyboard shortcuts for Switchboard Slots."""

    # ─────────────────────────────────────────────────────────────────
    # Host-namespaced persistence
    #
    # QSettings is shared across processes by ``(org, app)``, so a Maya and a
    # Blender session would otherwise read/write the SAME ``shortcuts.*``
    # overrides — a shortcut assigned in one host silently appears (or, worse,
    # collides) in the other. The key prefix is namespaced by the host's
    # ``context_tags`` (``shortcuts_maya.`` / ``shortcuts_blender.`` / plain
    # ``shortcuts.`` for standalone), mirroring
    # ``MarkingMenu._binding_store_key`` so BOTH binding systems key off the same
    # host identity and can't drift apart.
    # ─────────────────────────────────────────────────────────────────

    def _host_suffix(self) -> str:
        """Host-context suffix: ``"_maya"`` / ``"_blender"`` / ``""`` (standalone).
        Delegates to the shared :func:`host_namespace_suffix` so it stays identical
        to the marking-menu binding store's scheme (drift would re-introduce
        cross-host collisions). Underpins both :meth:`_shortcut_ns` (shortcut/command
        keys) and :meth:`_host_namespaced_branch` (per-panel widget-state branches)."""
        return host_namespace_suffix(getattr(self, "context_tags", None))

    def _shortcut_ns(self) -> str:
        """Settings-key prefix for every slot/command override, host-namespaced
        (e.g. ``"shortcuts_maya."``). Single source of truth for the prefix so the
        write path, the read/registry path, and the deferred-bind scan can't
        drift apart — drift would re-introduce the cross-host collision."""
        return f"shortcuts{self._host_suffix()}."

    def _host_namespaced_branch(self, name: str) -> str:
        """Host-namespace a per-panel settings BRANCH name (e.g. ``"mirror"`` ->
        ``"mirror_maya"``), the widget-state analog of :meth:`_shortcut_ns`.

        Single source of truth for ``Switchboard.add_ui`` (the branch a loaded
        UI's ``ui.settings``/``ui.state`` actually uses),
        ``MainWindow._relative_state`` (the not-loaded sibling fallback), and
        ``get_shortcut_registry`` (reads overrides from that same branch without
        force-loading the UI) — drift between them would re-introduce the
        cross-host collision this namespacing exists to prevent.
        """
        return name + self._host_suffix()

    def _migrate_shortcuts_to_host_namespace(self) -> None:
        """One-shot: copy legacy un-suffixed ``shortcuts.*`` overrides into this
        host's namespaced keys, so existing customizations survive the move to
        host-namespaced persistence.

        Before namespacing, Maya and Blender shared one ``shortcuts.*`` set. On
        first run each host *copies* that shared set into its own namespace and
        then diverges; the legacy keys are deliberately left orphaned so the
        *other* host can still seed from them (re-running clears nothing). A
        host that already has a namespaced key wins — a value the user changed
        post-migration is never clobbered. Standalone (no suffix) keeps the
        legacy keys as-is. Idempotent via a per-host marker.

        Writes TWO twins per legacy key: one under the legacy key's own branch
        (``head``, for a global bucket like ``commands``/``configurable`` that
        ``Switchboard.add_ui`` never renames) and one under ``head + suffix``
        (for a per-panel branch — ``add_ui`` now host-namespaces the branch
        itself, so a window/widget-scope override must land where the loaded
        UI's ``ui.settings`` will actually look for it). The extra twin under a
        global bucket is simply unused dead data — nothing ever branches
        ``"commands" + suffix`` — so writing both unconditionally is safe
        without needing to know which ``head`` values are panel names.
        """
        suffix = self._host_suffix()
        if not suffix:
            return  # standalone keeps the legacy un-suffixed keys (no collision)
        marker = f"shortcuts_migrated{suffix}"
        if self.configurable.value(marker):
            return
        legacy_prefix = "shortcuts."
        host_prefix = f"shortcuts{suffix}."
        for key in self.settings.keys():
            head, sep, tail = key.partition("/")
            if not sep or not tail.startswith(legacy_prefix):
                continue
            leaf = tail[len(legacy_prefix):]
            for twin_head in (head, self._host_namespaced_branch(head)):
                twin = f"{twin_head}/{host_prefix}{leaf}"
                if self.settings.value(twin) is None:
                    self.settings.setValue(twin, self.settings.value(key))
        self.configurable.setValue(marker, True)

    def register_slots_shortcuts(
        self, ui: QtWidgets.QWidget, slots_instance: object
    ) -> None:
        """Scan a Slots instance and register shortcuts for decorated methods.

        This method:
        1. Iterates over all methods in the slots instance.
        2. checks for `_shortcut_meta` (from @shortcut decorator) OR `shortcut` attribute.
        3. Checks `ui.settings` for user overrides.
        4. Creates a QShortcut attached to the main window (or specific context).
        5. Connects the shortcut to the slot, handling argument injection gracefully.

        Args:
            ui (QtWidgets.QWidget): The UI instance (MainWindow) owning the slots.
            slots_instance (object): The instantiated Slots class.
        """
        slots_cls_name = slots_instance.__class__.__name__
        self.logger.debug(
            f"[register_slots_shortcuts] Scanning {slots_cls_name} for shortcuts..."
        )

        # Collect property names from the MRO so we can skip them.
        # inspect.getmembers calls getattr() on every attribute, which
        # triggers @property getters.  If a getter has side-effects (e.g.
        # lazy init that validates external state) it can raise and crash
        # the entire registration.  Skipping properties is safe here
        # because shortcut metadata lives on regular methods, never on
        # properties.
        _property_names: set = set()
        for _cls in type(slots_instance).__mro__:
            for _k, _v in vars(_cls).items():
                if isinstance(_v, property):
                    _property_names.add(_k)

        for name in sorted(dir(slots_instance)):
            if name in _property_names:
                continue
            try:
                method = getattr(slots_instance, name)
            except Exception:
                continue
            if not inspect.ismethod(method):
                continue
            # 1. Check for metadata from decorator
            meta = getattr(method, "_shortcut_meta", {})

            # 2. Check for attribute-style definition (dynamic assignment in __init__)
            # Support func.shortcut = "Ctrl+S"
            attr_seq = getattr(method, "shortcut", None)
            if attr_seq and not meta.get("sequence"):
                meta["sequence"] = attr_seq
                meta["context"] = getattr(
                    method, "shortcut_context", QtCore.Qt.WindowShortcut
                )

            # 3. Resolve the effective binding: decorator default + user
            # override (sequence + scope). The override is read BEFORE the
            # empty-check below, so a shortcut the user assigned via the editor to
            # an UNDECORATED slot (no @Shortcut default) is still re-created on
            # the next session. The previous `if not default_sequence: continue`
            # bailed first, silently dropping every editor-assigned binding on a
            # plain widget slot until the user reassigned it.
            default_sequence = meta.get("sequence")  # None for undecorated slots
            final_sequence = default_sequence
            default_context = meta.get("context", QtCore.Qt.WindowShortcut)
            final_context = default_context
            settings_key = f"{self._shortcut_ns()}{slots_cls_name}.{name}"
            scope_settings_key = f"{settings_key}.scope"

            if hasattr(ui, "settings"):
                user_override = ui.settings.value(settings_key)
                # A *present* override wins, including an empty string — that is
                # an explicit "no shortcut" (the user cleared a binding that has
                # a non-empty decorator default). Only a *missing* override
                # (``None``) falls through to the default. ``if user_override:``
                # would wrongly resurrect the default for a cleared binding.
                if user_override is not None:
                    final_sequence = user_override
                scope_override = ui.settings.value(scope_settings_key)
                # Validate against known scopes so legacy/garbage values
                # silently fall back to the decorator default.
                if scope_override in SCOPE_NAME_TO_CONTEXT:
                    final_context = scope_name_to_context(scope_override)

            # Nothing to bind: no decorator default AND no (non-empty) override.
            if not final_sequence:
                continue

            # 4. Register
            self._create_switchboard_shortcut(
                ui,
                slots_instance,
                method,
                name,
                final_sequence,
                final_context,
                meta.get("robust", False),
            )

        # The UI is now built, so its real (UI-context) shortcuts above own
        # their keys. Drop any cold-start standins for this UI — a leftover
        # standin on the same app-scoped key would make Qt's activation
        # ambiguous (neither fires). No-op when there were none.
        self._dispose_deferred_slot_shortcuts(ui.objectName())

    @staticmethod
    def _adapt_shortcut_callback(callback: Callable) -> Callable:
        """Return a zero-arg callable for a shortcut trigger.

        A shortcut/GlobalShortcut trigger passes no arguments, but slots/commands
        often expect ``widget``; inject ``widget=None`` for those. Shared by the
        slot (:meth:`_create_switchboard_shortcut`) and command
        (:meth:`_bind_command`) binders.
        """
        try:
            wants_widget = "widget" in inspect.signature(callback).parameters
        except (TypeError, ValueError):
            wants_widget = False  # builtins / C funcs without an introspectable sig
        return (lambda: callback(widget=None)) if wants_widget else callback

    def _create_switchboard_shortcut(
        self,
        ui: QtWidgets.QWidget,
        slots_instance: object,
        method: callable,
        method_name: str,
        sequence: str,
        context: int = QtCore.Qt.WindowShortcut,
        robust: bool = False,
    ):
        """Internal helper to create and connect the QShortcut object."""
        parent = ui  # Default parent is the Main Window
        if context == QtCore.Qt.ApplicationShortcut:
            # Application scope must fire even when this slot's window is hidden
            # (that's the whole point of "anywhere in the host app"). A QShortcut
            # is disabled while its owner widget is hidden — regardless of scope —
            # so own it by an always-visible host window instead of the slot UI,
            # which is hidden whenever the tool isn't open. See
            # resolve_application_host for the Qt rationale.
            parent = resolve_application_host(ui)
        elif context == QtCore.Qt.WidgetShortcut:
            # If strictly widget scoped, we might need a specific widget provided.
            # But normally Switchboard shortcuts are Window scoped (Global implementations).
            pass

        key_seq = QtGui.QKeySequence(sequence)

        if robust:
            # robust=True uses GlobalShortcut with event filter (e.g. for Maya)
            shortcut = GlobalShortcut(key_seq, parent, context=context)
        else:
            shortcut = QtWidgets.QShortcut(key_seq, parent)
            shortcut.setContext(context)

        # Adapt the call: a shortcut trigger sends no arguments, so inject
        # widget=None for slots that expect a widget.
        wrapper = self._adapt_shortcut_callback(method)
        if robust:
            shortcut.pressed.connect(wrapper)
        else:
            shortcut.activated.connect(wrapper)

        # Store to prevent GC and enable Live Re-binding
        if not hasattr(slots_instance, "_connected_shortcuts"):
            # Map: method_name -> QShortcut
            slots_instance._connected_shortcuts = {}

        slots_instance._connected_shortcuts[method_name] = shortcut

        self.logger.debug(
            f"[shortcut] Bound '{sequence}' -> {slots_instance.__class__.__name__}.{method_name}"
        )

    def get_shortcut_registry(self, ui: QtWidgets.QWidget) -> List[Dict[str, Any]]:
        """Get a registry of all assignable slots and their shortcut status.

        Identifies slots by finding widget objectNames that have matching methods
        in the slots class. Also includes any methods with explicit @shortcut
        decorator (for non-widget-bound actions).

        Returns:
            List[Dict]: [
                {
                    "class": "MainSlots",
                    "method": "save_file",
                    "name": "Save File",
                    "current": "Ctrl+S",
                    "default": "Ctrl+S",
                    "doc": "Saves the current file."
                }, ...
            ]
        """
        # Get the slots instance for this UI
        slots_instance = self.get_slots_instance(ui)
        if not slots_instance:
            return []

        slots_cls_name = slots_instance.__class__.__name__

        # Candidate slots: widget objectNames in the live UI tree that have a
        # matching public slot method, plus any @shortcut-decorated method.
        widget_names = {
            w.objectName()
            for w in ui.findChildren(QtWidgets.QWidget)
            if w.objectName() and not w.objectName().startswith("qt_")
        }
        slot_method_names = {
            name
            for name in widget_names
            if callable(getattr(slots_instance, name, None))
            and not name.endswith("_init")
            and not name.startswith("_")
        }
        for name, method in inspect.getmembers(
            slots_instance, predicate=inspect.ismethod
        ):
            if getattr(method, "_shortcut_meta", {}).get("sequence"):
                slot_method_names.add(name)

        # Override reader: the live UI's per-UI QSettings, or a no-op when the
        # UI carries no settings store.
        settings_value = (
            ui.settings.value if hasattr(ui, "settings") else (lambda _k: None)
        )
        return self._build_shortcut_entries(
            slots_cls_name,
            slot_method_names,
            lambda n: getattr(slots_instance, n, None),
            settings_value,
        )

    def _build_shortcut_entries(
        self,
        slots_cls_name: str,
        slot_method_names,
        resolve_method,
        settings_value,
    ) -> List[Dict[str, Any]]:
        """Build shortcut-registry entries from resolved inputs.

        The single source of truth for an entry's shape and its default /
        current (override) resolution, shared by the live
        :meth:`get_shortcut_registry` (instance + live widget tree) and the
        static, no-instantiation path that lists every UI at once.

        Parameters:
            slots_cls_name: Slots class name — the QSettings key namespace.
            slot_method_names: Candidate method names to emit entries for.
            resolve_method: ``name -> method/function`` (a bound method for the
                live path, an unbound function for the static path) or ``None``.
            settings_value: ``key -> value`` reader for user overrides (the same
                ``{_shortcut_ns}{cls}.{method}`` keys the live UI writes — the
                prefix is host-namespaced, see :meth:`_shortcut_ns`), or a no-op
                returning ``None`` when no store is available.
        """
        registry: List[Dict[str, Any]] = []
        for name in sorted(slot_method_names):
            method = resolve_method(name)
            if not method or not callable(method):
                continue

            meta = getattr(method, "_shortcut_meta", {})
            attr_seq = getattr(method, "shortcut", None)

            default = meta.get("sequence", attr_seq)
            doc = meta.get("doc") or method.__doc__ or ""

            default_context = meta.get("context", QtCore.Qt.WindowShortcut)
            default_scope = context_to_scope_name(default_context)

            # Current = user override when present. Present-but-empty ("") is an
            # explicit clear (no shortcut); only a missing override (None)
            # reverts to the default. See the note in ``_register_shortcuts``.
            current = default
            current_scope = default_scope
            settings_key = f"{self._shortcut_ns()}{slots_cls_name}.{name}"
            override = settings_value(settings_key)
            if override is not None:
                current = override
            scope_override = settings_value(f"{settings_key}.scope")
            # Only honour overrides that map to a known scope. Anything else
            # (legacy bad data, manual edits, mis-typed values) is ignored so
            # the user falls back to the decorator default rather than a
            # stuck/garbage scope label.
            if scope_override in SCOPE_NAME_TO_CONTEXT:
                current_scope = scope_override

            # Visibility / editability: the declarative decorator (or command
            # spec) default, overridable per-binding at runtime via the
            # ``.hidden`` / ``.editable`` settings twins (written by
            # :meth:`set_binding_hidden` / :meth:`set_binding_editable`). A
            # *missing* override (None) keeps the declared default; a present
            # value wins. Read through the same ``settings_value`` reader the
            # sequence/scope overrides use, so slots and commands share one
            # mechanism (DRY).
            hidden = bool(meta.get("hidden", False))
            editable = bool(meta.get("editable", True))
            hidden_override = settings_value(f"{settings_key}.hidden")
            if hidden_override is not None:
                hidden = _as_bool(hidden_override)
            editable_override = settings_value(f"{settings_key}.editable")
            if editable_override is not None:
                editable = _as_bool(editable_override)

            registry.append(
                {
                    "class": slots_cls_name,
                    "method": name,
                    "name": meta.get("name", name),
                    "current": current,
                    "default": default,
                    "current_scope": current_scope,
                    "default_scope": default_scope,
                    "doc": inspect.cleandoc(doc).split("\n")[0] if doc else "",
                    "hidden": hidden,
                    "editable": editable,
                    "clearable": bool(meta.get("clearable", True)),
                }
            )

        return registry

    def get_static_shortcut_registry(self, ui_name: str) -> List[Dict[str, Any]]:
        """Build a UI's shortcut registry WITHOUT instantiating the UI.

        Resolves the slots class and widget objectNames from the registry and
        the ``.ui`` file on disk (not a live widget tree), reads user overrides
        from the same per-UI ``QSettings`` the live UI writes, and feeds them
        through the shared :meth:`_build_shortcut_entries`. This lets a caller
        (e.g. the shortcut editor's "show all" view) list every registered UI's
        slots at once without force-building them all — the cause of the
        host-shutdown crash; a UI is only instantiated when its binding is
        actually edited.

        Fidelity note: widget names come from the static ``.ui`` XML, so slots
        bound to widgets *created in code at runtime* (not declared in the
        ``.ui``) are not listed until that UI is actually loaded.
        ``@shortcut``-decorated methods are always included (read from the
        class). For an already-loaded UI prefer :meth:`get_shortcut_registry`,
        which sees the real widget tree.

        Returns an empty list when no slots class resolves for ``ui_name``.
        """
        slots_cls = self._find_slots_class(
            self.get_base_name(ui_name), allow_sole_fallback=True
        )
        if slots_cls is None:
            return []

        # Public slot methods whose names match a declared widget, plus any
        # @shortcut-decorated method (read from the class — unbound functions).
        widget_names = self._ui_widget_names(ui_name)
        slot_method_names = {
            name
            for name in widget_names
            if callable(getattr(slots_cls, name, None))
            and not name.endswith("_init")
            and not name.startswith("_")
        }
        for name, func in inspect.getmembers(
            slots_cls, predicate=inspect.isfunction
        ):
            if getattr(func, "_shortcut_meta", {}).get("sequence"):
                slot_method_names.add(name)

        # Read overrides from the SAME per-UI, host-namespaced settings branch
        # the loaded UI uses (see ``Switchboard.add_ui`` /
        # ``_host_namespaced_branch``), so a binding persisted while the UI was
        # open is reflected here without rebuilding.
        settings = self.settings.branch(self._host_namespaced_branch(ui_name))
        return self._build_shortcut_entries(
            slots_cls.__name__,
            slot_method_names,
            lambda n: getattr(slots_cls, n, None),
            settings.value,
        )

    def _ui_widget_names(self, ui_name: str) -> set:
        """Widget objectNames declared in a UI's ``.ui`` file (no instantiation).

        Mirrors what :meth:`get_shortcut_registry` reads from a live tree via
        ``findChildren(QWidget)``: every ``<widget>`` name except the top-level
        window itself (which ``findChildren`` also excludes) and Qt-internal
        ``qt_*`` names. Returns an empty set if the file can't be resolved/read.
        """
        import xml.etree.ElementTree as ET

        actual = self.find_ui_filename(ui_name, unique_match=True)
        filepath = (
            self.registry.ui_registry.get(filename=actual, return_field="filepath")
            if actual
            else None
        )
        if not filepath:
            return set()
        try:
            root = ET.parse(filepath).getroot()
        except (ET.ParseError, OSError):
            return set()

        top = root.find("widget")  # the main window element itself
        top_name = top.get("name") if top is not None else None
        return {
            name
            for w in root.iter("widget")
            if (name := w.get("name"))
            and name != top_name
            and not name.startswith("qt_")
        }

    def set_user_shortcut(
        self,
        ui: QtWidgets.QWidget,
        slot_name: str,
        sequence: str,
        scope: Optional[str] = None,
    ) -> None:
        """Update a shortcut setting dynamically and live-update the active QShortcut.

        Args:
            ui (QtWidgets.QWidget): The main window/UI.
            slot_name (str): The name of the method (e.g., "save_file").
            sequence (str): The new key sequence (e.g., "Ctrl+Alt+S").
            scope (str, optional): Persisted scope name ("window", "application",
                "widget", "widget_children"). When None, the existing scope
                override (if any) is preserved; otherwise the decorator default
                applies.
        """
        slots_instance = self.get_slots_instance(ui)
        if not slots_instance:
            return

        cls_name = slots_instance.__class__.__name__
        key = f"{self._shortcut_ns()}{cls_name}.{slot_name}"
        scope_key = f"{key}.scope"

        # 1. Update Persistent Settings. Treat empty scope the same as
        # None — don't write garbage that the registry would have to
        # filter on read.
        if hasattr(ui, "settings"):
            ui.settings.setValue(key, sequence)
            if scope:
                ui.settings.setValue(scope_key, scope)

        # 2. Resolve target context for live rebind
        method = getattr(slots_instance, slot_name, None)
        meta = getattr(method, "_shortcut_meta", {}) if method else {}
        default_context = meta.get("context", QtCore.Qt.WindowShortcut)

        # Empty/None scope is treated identically: fall through to the
        # existing override (if any) or the decorator default. This keeps
        # the read and write paths aligned — neither persists nor honours
        # a "" scope. Stored overrides are also validated against the
        # known scope set so legacy bad data can't sneak through.
        if scope and scope in SCOPE_NAME_TO_CONTEXT:
            target_context = scope_name_to_context(scope)
        elif hasattr(ui, "settings"):
            existing_scope = ui.settings.value(scope_key)
            target_context = (
                scope_name_to_context(existing_scope)
                if existing_scope in SCOPE_NAME_TO_CONTEXT
                else default_context
            )
        else:
            target_context = default_context

        # 3. Live re-bind — recreate rather than mutate in place.
        #
        # A scope change can require a *different owner widget* than the live
        # shortcut has: switching to application scope must re-own the shortcut
        # by an always-visible host window (a hidden owner disables it even at
        # ApplicationShortcut scope), and switching back to window scope must
        # re-own it by this UI. QShortcut.setContext alone can't do that, so
        # tear the old one down and rebuild it with the correct owner for the
        # target context. Recreation is cheap (one QShortcut) and keeps the
        # creation logic in a single place.
        existing_shortcuts = getattr(slots_instance, "_connected_shortcuts", {})
        old = existing_shortcuts.pop(slot_name, None)
        if old is not None:
            self._dispose_shortcut(old)

        if sequence and method:
            self._create_switchboard_shortcut(
                ui,
                slots_instance,
                method,
                slot_name,
                sequence,
                target_context,
                meta.get("robust", False),
            )
            self.logger.info(
                f"[set_user_shortcut] Rebound {slot_name} to {sequence} "
                f"({context_to_scope_name(target_context)})"
            )

    @staticmethod
    def _dispose_shortcut(shortcut) -> None:
        """Tear down a QShortcut/GlobalShortcut created by this mixin.

        Disable first so the outgoing shortcut is inert immediately — its
        replacement is created right after, and a still-live old shortcut on
        the same sequence could otherwise fire (or fire ambiguously) in the
        window before ``deleteLater`` is processed. GlobalShortcut also needs
        its static self-reference dropped, which ``dispose`` handles.
        """
        try:
            if isinstance(shortcut, GlobalShortcut):
                shortcut.dispose()
            else:
                shortcut.setEnabled(False)
                shortcut.deleteLater()
        except RuntimeError:
            pass  # underlying C++ object already gone

    # ─────────────────────────────────────────────────────────────────
    # Programmatic, UI-less commands
    #
    # A *command* is a shortcut-bindable action with no owning UI, widget, or
    # slots class — e.g. the Switchboard's own navigation verbs
    # (``show_prev_ui``, ``repeat_last``). Registered in code via
    # :meth:`register_command`, they surface in the shortcut editor exactly
    # like slot shortcuts (the editor lists them under a "Commands"
    # pseudo-UI with a colour-coded "no UI" tag) and persist their overrides
    # under the Switchboard's own settings, namespaced ``shortcuts.Commands.*``
    # — the same key shape a UI uses, just rooted at ``self.settings``
    # instead of a per-UI branch. This is the registry path that lets a
    # command appear in the editor even when it ships *unbound* (the
    # ``@Shortcut`` decorator path required a non-empty default sequence).
    # ─────────────────────────────────────────────────────────────────

    #: Settings namespace / pseudo-class name for commands. Shared by the
    #: entry builder, the binder, and ``set_command_shortcut`` so the read
    #: and write keys can't drift.
    _COMMAND_NS = "Commands"

    def _command_settings(self):
        """The store holding command overrides (``shortcuts.Commands.*``)."""
        return self.settings.branch("commands")

    def _command_key(self, name: str) -> str:
        """The settings key for command *name* (mirrors the slot key shape,
        host-namespaced via :meth:`_shortcut_ns`)."""
        return f"{self._shortcut_ns()}{self._COMMAND_NS}.{name}"

    def register_command(
        self,
        name: str,
        callback: Optional[Callable] = None,
        *,
        label: Optional[str] = None,
        sequence: str = "",
        scope: str = "application",
        doc: str = "",
        hidden: bool = False,
        editable: bool = True,
        bind: bool = True,
        clearable: bool = True,
        on_rebind: Optional[Callable[[str, str], None]] = None,
        value_getter: Optional[Callable[[], str]] = None,
    ) -> str:
        """Register a UI-less, shortcut-bindable command.

        The command appears in the shortcut editor's "Commands" pseudo-UI and can
        be (re)bound there like any slot shortcut. It also live-binds a plain
        host-owned ``QShortcut`` (see :meth:`_make_host_shortcut`) as soon as an
        always-visible host window is available (deferred to the first
        ``on_ui_loaded`` when none exists yet).

        Parameters:
            name: Stable identifier and settings key (e.g. ``"reopen_last_ui"``).
            callback: Zero-arg callable (or one accepting ``widget=None``) run on
                trigger — typically a bound Switchboard verb.
            label: Display name in the editor. Defaults to a title-cased *name*.
            sequence: Default key sequence. ``""`` ships the command **unbound**
                (it still lists in the editor for the user to assign).
            scope: Default scope name (``"application"`` / ``"window"``).
            doc: Description shown in the editor. Defaults to ``callback.__doc__``.
            hidden: When True, omit from the editor's default view (still listed
                under "Show hidden"). Overridable at runtime via
                :meth:`set_binding_hidden`.
            editable: When False, show the command but disallow rebinding (a
                fixed, semantic key).
            clearable: When False, the editor never offers to *clear* this
                command's key to resolve a collision (it reports the conflict as
                coexisting, non-breaking). For an externally-owned binding whose
                ``on_rebind`` cannot honour an empty sequence — e.g. the marking
                menu's activation key, which must always stay bound — so the
                "Clear conflicting" path doesn't silently no-op.
            bind: When False the register does **not** create a host ``QShortcut``
                for this command — the real key is owned externally (e.g. the
                marking menu's own activation ``GlobalShortcut``) or the entry is
                display-only. Prevents a second, colliding shortcut on the same
                key. Pair with ``value_getter`` / ``on_rebind`` to keep the editor
                row live + editable without that duplicate.
            on_rebind: ``(sequence, scope) -> None`` invoked when the user edits
                (or resets) this command in the editor, **instead of** the default
                persist-and-rebind. For a binding whose owner must perform a
                cross-cutting update — e.g. the marking menu rewriting every chord
                when its activation key changes.
            value_getter: ``() -> str`` returning the command's live current
                sequence, read from the external owner rather than command
                settings (which are never written for a ``bind=False`` entry). So
                the editor shows + colours the real, externally-held state.

        Returns:
            The command *name*.
        """
        spec = {
            "name": name,
            "callback": callback,
            "label": label or name.replace("_", " ").title(),
            "sequence": sequence,
            "scope": scope,
            "doc": doc or ((callback.__doc__ if callback else "") or ""),
            "hidden": hidden,
            "editable": editable,
            "clearable": clearable,
            # Externally-owned / display-only binding support (see the docstring):
            # ``bind=False`` skips the register-created QShortcut; ``value_getter``
            # supplies the live current value; ``on_rebind`` receives editor edits.
            "bind": bind,
            "on_rebind": on_rebind,
            "value_getter": value_getter,
        }
        spec["_carrier"] = self._make_command_carrier(spec)
        self._commands[name] = spec
        self._bind_command(name)
        return name

    def unregister_command(self, name: str) -> None:
        """Remove a command and tear down its live shortcut, if any."""
        self._commands.pop(name, None)
        shortcut = self._command_shortcuts.pop(name, None)
        if shortcut is not None:
            self._dispose_shortcut(shortcut)

    def _make_command_carrier(self, spec: dict) -> Callable:
        """Wrap a command spec as a callable carrying ``_shortcut_meta``.

        Lets :meth:`get_command_registry` reuse :meth:`_build_shortcut_entries`
        verbatim — that builder reads default sequence / scope / name / doc off
        ``_shortcut_meta``, exactly what a ``@Shortcut``-decorated method exposes.
        """

        def carrier(*args, **kwargs):
            cb = spec["callback"]
            return cb(*args, **kwargs) if cb else None

        carrier._shortcut_meta = {
            "sequence": spec["sequence"],
            "context": scope_name_to_context(spec["scope"]),
            "name": spec["label"],
            "doc": spec["doc"],
            "hidden": spec.get("hidden", False),
            "editable": spec.get("editable", True),
            "clearable": spec.get("clearable", True),
        }
        carrier.__doc__ = spec["doc"]
        return carrier

    def get_command_registry(self) -> List[Dict[str, Any]]:
        """Registry entries for every command, in the slot-shortcut entry shape.

        Each entry carries ``"command": True`` so the editor renders it under the
        "Commands" pseudo-UI with a colour-coded tag and routes edits through
        :meth:`set_command_shortcut`. Reuses :meth:`_build_shortcut_entries` for
        identical default/override resolution.
        """
        commands = getattr(self, "_commands", None)
        if not commands:
            return []
        entries = self._build_shortcut_entries(
            self._COMMAND_NS,
            set(commands),
            lambda n: commands.get(n, {}).get("_carrier"),
            self._command_settings().value,
        )
        for entry in entries:
            entry["command"] = True
            # An externally-owned binding (bind=False) reads its live current
            # value from the owner, not command settings (never written for it),
            # so the editor shows + colours the real state (e.g. the marking
            # menu's current activation key).
            getter = commands.get(entry["method"], {}).get("value_getter")
            if getter is not None:
                try:
                    entry["current"] = getter() or ""
                except Exception:  # a flaky getter must not break the whole list
                    self.logger.debug(
                        f"[command] value_getter for {entry['method']!r} raised",
                        exc_info=True,
                    )
        return entries

    def set_command_shortcut(
        self, name: str, sequence: str, scope: Optional[str] = None
    ) -> None:
        """Persist a command's override and live-rebind it (the command twin of
        :meth:`set_user_shortcut`).

        An empty *sequence* clears the binding (the command stays listed, just
        unbound). A *scope* of ``None`` preserves the existing override.

        Externally-owned bindings (registered ``on_rebind=…``) delegate the edit
        to their owner instead of touching command settings / the register's
        shortcut — the owner is the source of truth its ``value_getter`` reads
        back (e.g. the marking menu rewriting every chord for a new activation
        key). The reset path routes here too, so a reset also delegates.
        """
        if name not in getattr(self, "_commands", {}):
            return
        spec = self._commands[name]
        on_rebind = spec.get("on_rebind")
        if on_rebind is not None:
            on_rebind(sequence, scope or spec.get("scope", "application"))
            return
        store = self._command_settings()
        key = self._command_key(name)
        store.setValue(key, sequence)
        if scope:
            store.setValue(f"{key}.scope", scope)
        self._bind_command(name)

    def _set_command_flag(self, name: str, flag: str, value: bool) -> None:
        """Persist + live-apply a command's ``hidden``/``editable`` flag override.

        Writes the ``.{flag}`` settings twin read back by
        :meth:`_build_shortcut_entries` (the same path slot/command entries use
        for sequence/scope) and updates the in-memory spec + carrier meta so an
        entry built from the live command reflects the change immediately. A
        no-op for an unknown command. Shared by the two public mutators.
        """
        spec = getattr(self, "_commands", {}).get(name)
        if spec is None:
            return
        value = bool(value)
        spec[flag] = value
        spec["_carrier"]._shortcut_meta[flag] = value
        self._command_settings().setValue(f"{self._command_key(name)}.{flag}", value)

    def set_binding_hidden(self, name: str, hidden: bool = True) -> None:
        """Hide/show command *name* in the shortcut editor's default view.

        The post-hoc twin of the ``hidden=`` registration kwarg. A no-op for an
        unknown command.
        """
        self._set_command_flag(name, "hidden", hidden)

    def set_binding_editable(self, name: str, editable: bool = True) -> None:
        """Allow/forbid the user rebinding command *name* in the editor.

        The post-hoc twin of the ``editable=`` registration kwarg. A no-op for an
        unknown command.
        """
        self._set_command_flag(name, "editable", editable)

    def _resolve_command_binding(self, name: str):
        """Return the effective ``(sequence, scope_name)`` for command *name*.

        Override (present, incl. empty = explicit clear) wins over the spec
        default; a garbage/legacy scope override falls back to the default.
        """
        spec = self._commands[name]
        store = self._command_settings()
        key = self._command_key(name)
        seq = store.value(key)
        if seq is None:
            seq = spec["sequence"]
        scope = store.value(f"{key}.scope")
        if scope not in SCOPE_NAME_TO_CONTEXT:
            scope = spec["scope"]
        return seq, scope

    def _command_host(self) -> Optional[QtWidgets.QWidget]:
        """A live starting widget to own command shortcuts, or None.

        Resolution defers to :func:`resolve_application_host` (called by
        :meth:`_bind_command`) for the final DCC-host upgrade; this just needs a
        good *starting* widget.

        A persistent, visible Switchboard UI is preferred over
        ``app.activeWindow()`` — and that ordering is the fix for a real bug:
        commands are (re)bound the moment the user assigns a key in the shortcut
        editor, at which point the active window *is* that editor, an ephemeral
        tool window. Qt disables an application-scoped shortcut whose owner
        window is hidden, so owning the command by the editor made it silently
        inert as soon as the editor closed (it "never worked"). The shortcut
        editor is not a registered Switchboard UI, so preferring ``loaded_ui``
        skips it for the host's real, lasting windows.

        The marking menu's transient surfaces (``startmenu``/``submenu``) are
        skipped: they're visible only mid-gesture and vanish on release, so
        owning a command by one would make it inert again — the same skip
        :meth:`show_prev_ui` applies when reopening a window.

        When no Switchboard UI is visible it falls back to an always-visible
        *application* host via :func:`resolve_application_host` (the DCC main
        window, else any visible non-transient top-level) — **not**
        ``app.activeWindow()``. That was a real persistence bug: at next-session
        startup ``on_ui_loaded`` fires while the just-loaded UI is still hidden
        and nothing is the active window, so the old fallback returned ``None``,
        ``_bind_command`` bailed, and the persisted command silently never bound
        (it "didn't persist"). The DCC host is up at that point, so binding to it
        succeeds. Returns ``None`` only when nothing is on screen at all —
        binding is retried on the next ``on_ui_loaded`` / current-UI change.
        """
        for ui in self.loaded_ui.values():
            try:
                if ui.has_tags(["startmenu", "submenu"]):
                    continue
                if ui.isVisible():
                    return ui
            except RuntimeError:
                continue
        # An always-visible application host (DCC window / visible top-level).
        host = resolve_application_host(None)
        if host is None:
            return None
        try:
            if hasattr(host, "has_tags") and host.has_tags(["startmenu", "submenu"]):
                return None  # never own a command by a transient surface
        except RuntimeError:
            return None
        return host

    def _bind_command(self, name: str) -> None:
        """(Re)create the live shortcut for command *name* from its current
        sequence/scope. Disposes any prior shortcut first; a no-op when the
        command is unbound or no host window exists yet."""
        spec = self._commands.get(name)
        if spec is None:
            return
        if not spec.get("bind", True):
            return  # externally-owned / display-only: the register creates no shortcut

        old = self._command_shortcuts.pop(name, None)
        if old is not None:
            self._dispose_shortcut(old)

        sequence, scope = self._resolve_command_binding(name)
        if not sequence:
            return  # unbound

        host = self._command_host()
        if host is None:
            return  # defer until a window exists (on_ui_loaded)

        shortcut = self._make_host_shortcut(
            sequence,
            host,
            self._adapt_shortcut_callback(spec["callback"]),
            scope_name_to_context(scope),
        )
        self._command_shortcuts[name] = shortcut
        self.logger.debug(
            f"[command] Bound '{sequence}' ({scope}) -> command '{name}'"
        )

    @staticmethod
    def _make_host_shortcut(
        sequence: str,
        host: QtWidgets.QWidget,
        on_press: Callable,
        context: QtCore.Qt.ShortcutContext = QtCore.Qt.ApplicationShortcut,
    ) -> QtWidgets.QShortcut:
        """Create a host-owned plain ``QShortcut`` wired to *on_press*.

        Shared by the command binder and the cold-start deferred-slot binder.
        Both are *fire-on-press* actions that never use key release, so this
        deliberately uses a plain ``QShortcut`` (``activated``) rather than
        :class:`GlobalShortcut`.

        Why this matters — a real bug, found live in Maya: ``GlobalShortcut``
        only re-emits ``pressed`` after its application-level event filter sees a
        matching ``KeyRelease`` reset an internal ``_is_down`` latch. In a DCC
        host that release is routinely *missed* — the native viewport has focus,
        or focus shifts while the action runs — so the latch sticks ``True`` and
        every subsequent press is silently swallowed: the command fires once,
        then goes dead for the session (reported as "the global commands don't
        persist / stop working"). A plain ``QShortcut.activated`` fires on every
        press with no such latch, and is exactly what
        :meth:`register_slots_shortcuts` uses for ordinary (non-robust) slot
        shortcuts — so commands and cold-start slot standins now behave identically
        to the slot shortcuts that already persist reliably.

        Application scope must be owned by an always-visible window (a
        ``QShortcut`` whose owner is hidden is inert even at
        ``ApplicationShortcut`` scope — see :func:`resolve_application_host`);
        window/widget scopes keep the given *host* as the owner.
        """
        parent = (
            resolve_application_host(host)
            if context == QtCore.Qt.ApplicationShortcut
            else host
        )
        shortcut = QtWidgets.QShortcut(QtGui.QKeySequence(sequence), parent)
        shortcut.setContext(context)
        # Match the prior GlobalShortcut behaviour: one fire per physical press,
        # never auto-repeat while the chord is held (a held "repeat last" would
        # otherwise machine-gun the action).
        shortcut.setAutoRepeat(False)
        shortcut.activated.connect(on_press)
        return shortcut

    def _bind_pending_commands(self, *args) -> None:
        """Bind every command whose live shortcut is missing OR stale.

        Wired to ``on_ui_loaded``. Two jobs:

        * **Pending** — a command registered before any host window existed has
          no live shortcut yet; bind it now that one does.
        * **Stale (self-heal)** — a command is *eagerly* bound during
          :meth:`register_command`, which runs in ``Switchboard.__init__``. If
          the host assigns ``context_tags`` only *after* construction (the
          ``MarkingMenu(switchboard=…)`` reuse path) — or the resolved value
          otherwise changes — that eager bind resolved its sequence under the
          wrong, un-suffixed settings namespace and latched a stale key (e.g.
          the legacy ``shortcuts.Commands.repeat_last_command`` default instead
          of the host-namespaced ``shortcuts_maya.…`` value the user actually
          set). The old pass bound only *missing* commands, so that stale
          binding was never corrected and the user's real key silently never
          bound — the proven "repeat-last doesn't persist across sessions"
          report (a dead ``Ctrl+Shift+R`` was bound, never the assigned ``M``).
          Rebinding whenever the live key no longer matches the
          currently-resolved sequence lets the binding self-correct on the first
          UI load, independent of how the drift arose (late tags, settings
          edit, in-process module reload).

        Both the key *and* the scope are compared: a binding can drift in scope
        alone (e.g. the legacy namespace had it window-scoped, the host
        namespace application-scoped), and a stale ``WindowShortcut`` owned by an
        always-visible host is inert exactly when an app-scoped binding should
        fire — so a key-only check would silently leave it mis-scoped.
        """
        for name in list(getattr(self, "_commands", {})):
            if not self._commands[name].get("bind", True):
                continue  # externally-owned / display-only: nothing to (re)bind
            live = self._command_shortcuts.get(name)
            if live is None:
                self._bind_command(name)  # pending: never bound yet
                continue
            sequence, scope = self._resolve_command_binding(name)
            try:
                in_sync = live.key().toString() == (sequence or "") and (
                    live.context() == scope_name_to_context(scope)
                )
            except RuntimeError:
                in_sync = False  # underlying C++ shortcut gone -> rebind
            if not in_sync:
                self._bind_command(name)  # stale: persisted binding drifted

    # ─────────────────────────────────────────────────────────────────
    # Cold-start application-scoped slot shortcuts
    #
    # An application-scoped shortcut assigned to a *slot* (via the editor) is
    # normally created by :meth:`register_slots_shortcuts` when its UI is built.
    # But tool UIs are lazy, so on a fresh session — before the tool is ever
    # opened — the binding has no live shortcut and the shortcut is dead even
    # though the editor still lists it as assigned. These standins close that
    # gap: at the first ``on_ui_loaded`` we read the persisted *application*-
    # scoped overrides straight from settings (no UI build), and own a
    # host-window ``QShortcut`` per binding that builds-then-invokes the
    # slot on press. The standin is disposed the instant its UI is actually
    # built (see :meth:`register_slots_shortcuts`), handing the key to the real
    # UI-context shortcut. Window-scoped shortcuts need no standin — they only
    # fire while their window is focused, which already requires it to be open.
    # ─────────────────────────────────────────────────────────────────

    def _ui_names_with_shortcut_overrides(self) -> set:
        """UI names that have any persisted shortcut override for THIS host.

        Reads the host-namespaced prefix (see :meth:`_shortcut_ns`) so a Maya
        session's deferred-bind scan ignores Blender's overrides. One settings
        scan, so the (per-UI, XML-parsing) :meth:`get_static_shortcut_registry`
        is only paid for UIs the user has actually customised — not every
        registered UI. The ``commands`` branch is skipped: it's the command
        store, not a UI.
        """
        prefix = self._shortcut_ns()
        suffix = self._host_suffix()
        names = set()
        for key in self.settings.keys():
            head, sep, tail = key.partition("/")
            if sep and head != "commands" and tail.startswith(prefix):
                # ``head`` is the per-panel settings BRANCH, host-namespaced via
                # ``_host_namespaced_branch`` (``mirror`` -> ``mirror_maya``).
                # Invert it so the real UI name reaches ``get_static_shortcut_registry``
                # / ``loaded_ui.peek`` — else the branch name resolves no slot
                # class and the app-scoped standin never binds. Dedupes cleanly
                # with any migrated-user plain twin (``mirror`` and ``mirror_maya``
                # both collapse to ``mirror``).
                if suffix and head.endswith(suffix):
                    head = head[: -len(suffix)]
                names.add(head)
        return names

    def _bind_deferred_slot_shortcuts(self, *args) -> None:
        """Eagerly bind application-scoped slot shortcuts for UIs not yet built.

        Wired to ``on_ui_loaded``; runs the scan once, the first time a visible
        host window is available (so the standins have a valid owner). Skips
        already-built UIs — their real shortcuts own the keys — and is a no-op
        when nothing is customised.
        """
        if self._deferred_slots_scanned:
            return
        host = self._command_host()
        if host is None:
            return  # no visible owner yet; retry on the next on_ui_loaded

        for ui_name in self._ui_names_with_shortcut_overrides():
            if self.loaded_ui.peek(ui_name) is not None:
                continue  # built -> register_slots_shortcuts owns its shortcuts
            try:
                registry = self.get_static_shortcut_registry(ui_name)
            except Exception:
                self.logger.debug(
                    f"[deferred-slot] static registry failed for {ui_name!r}",
                    exc_info=True,
                )
                continue
            for entry in registry:
                if entry.get("current_scope") != "application":
                    continue
                sequence = entry.get("current") or ""
                if sequence:
                    self._create_deferred_slot_shortcut(
                        ui_name, entry["method"], sequence, host
                    )
        self._deferred_slots_scanned = True

    def _create_deferred_slot_shortcut(
        self, ui_name: str, method: str, sequence: str, host
    ) -> None:
        """Own a host-window standin shortcut that builds-then-invokes a slot."""
        key = (ui_name, method)
        if key in self._deferred_slot_shortcuts:
            return
        self._deferred_slot_shortcuts[key] = self._make_host_shortcut(
            sequence, host, self._make_deferred_slot_callback(ui_name, method)
        )
        self.logger.debug(
            f"[deferred-slot] Bound '{sequence}' -> {ui_name}.{method} (until built)"
        )

    def _make_deferred_slot_callback(self, ui_name: str, method: str) -> Callable:
        """Build the UI (if needed), resolve the slot, and invoke it.

        Building the UI runs :meth:`register_slots_shortcuts`, which disposes
        this standin and creates the real host-owned shortcut for subsequent
        presses. The slot runs without the window being shown — an app-wide
        shortcut fires the action, it doesn't pop the tool open.
        """

        def fire():
            ui = self.get_ui(ui_name)
            if ui is None:
                return
            instance = self.get_slots_instance(ui)
            slot = getattr(instance, method, None) if instance else None
            if slot is None:
                self.logger.debug(
                    f"[deferred-slot] {ui_name}.{method} not found after build"
                )
                return
            self._adapt_shortcut_callback(slot)()

        return fire

    def _dispose_deferred_slot_shortcuts(self, ui_name: str) -> None:
        """Tear down every standin for *ui_name* — its real shortcuts now own
        the keys (a leftover standin would make Qt's activation ambiguous)."""
        store = getattr(self, "_deferred_slot_shortcuts", None)
        if not store:
            return
        for key in [k for k in store if k[0] == ui_name]:
            self._dispose_shortcut(store.pop(key))
