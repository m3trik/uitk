# !/usr/bin/python
# coding=utf-8
"""Switchboard-side keyboard shortcut machinery.

This module is paired with :mod:`uitk.widgets.mixins.shortcuts`:

* The generic primitives (``GlobalShortcut``, ``ShortcutManager``,
  ``ShortcutMixin``, scope-name <-> ``Qt.ShortcutContext`` helpers)
  live in ``uitk.widgets.mixins.shortcuts`` and can be used by any
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

from uitk.widgets.mixins.shortcuts import (
    GlobalShortcut,
    SCOPE_NAME_TO_CONTEXT,
    context_to_scope_name,
    scope_name_to_context,
)


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
    """

    def __init__(
        self,
        sequence: str,
        context: QtCore.Qt.ShortcutContext = QtCore.Qt.WindowShortcut,
        name: Optional[str] = None,
        doc: Optional[str] = None,
        robust: bool = False,
    ):
        self.sequence = sequence
        self.context = context
        self.name = name
        self.doc = doc
        self.robust = robust

    def __call__(self, func: Callable) -> Callable:
        func._shortcut_meta = {
            "sequence": self.sequence,
            "context": self.context,
            "name": self.name,
            "doc": self.doc,
            "robust": self.robust,
        }
        return func


class SwitchboardShortcutMixin:
    """Mixin for managing keyboard shortcuts for Switchboard Slots."""

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

            default_sequence = meta.get("sequence")
            if not default_sequence:
                continue

            # 3. Check Settings for Override (sequence + scope)
            final_sequence = default_sequence
            default_context = meta.get("context", QtCore.Qt.WindowShortcut)
            final_context = default_context
            settings_key = f"shortcuts.{slots_cls_name}.{name}"
            scope_settings_key = f"{settings_key}.scope"

            if hasattr(ui, "settings"):
                user_override = ui.settings.value(settings_key)
                if user_override:
                    final_sequence = user_override
                scope_override = ui.settings.value(scope_settings_key)
                # Validate against known scopes so legacy/garbage values
                # silently fall back to the decorator default.
                if scope_override in SCOPE_NAME_TO_CONTEXT:
                    final_context = scope_name_to_context(scope_override)

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
        if context == QtCore.Qt.WidgetShortcut:
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

        # 5. Connection wrapper
        # Slots usually expect (self, widget, *args) or just (self).
        # When triggered by QShortcut, no arguments are sent.
        # We need to adapt the call.

        sig = inspect.signature(method)
        wants_widget = "widget" in sig.parameters

        if wants_widget:
            # Pass None as the widget when triggered by hotkey
            # We use a lambda that captures the method
            wrapper = lambda: method(widget=None)
        else:
            wrapper = method

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
        registry = []

        # Get the slots instance for this UI
        slots_instance = self.get_slots_instance(ui)
        if not slots_instance:
            return registry

        slots_cls_name = slots_instance.__class__.__name__

        # Collect all widget objectNames from the UI hierarchy
        widget_names = set()
        for widget in ui.findChildren(QtWidgets.QWidget):
            name = widget.objectName()
            if name and not name.startswith("qt_"):  # Skip Qt internal widgets
                widget_names.add(name)

        # Find which widget names have corresponding slot methods
        slot_method_names = set()
        for name in widget_names:
            method = getattr(slots_instance, name, None)
            if method and callable(method):
                # Exclude _init methods and internal methods
                if not name.endswith("_init") and not name.startswith("_"):
                    slot_method_names.add(name)

        # Also include any methods with explicit @shortcut decorator
        for name, method in inspect.getmembers(
            slots_instance, predicate=inspect.ismethod
        ):
            meta = getattr(method, "_shortcut_meta", {})
            if meta.get("sequence"):
                slot_method_names.add(name)

        # Build registry from slot method names
        for name in sorted(slot_method_names):
            method = getattr(slots_instance, name, None)
            if not method or not callable(method):
                continue

            meta = getattr(method, "_shortcut_meta", {})
            attr_seq = getattr(method, "shortcut", None)

            default = meta.get("sequence", attr_seq)
            doc = meta.get("doc") or method.__doc__ or ""

            default_context = meta.get("context", QtCore.Qt.WindowShortcut)
            default_scope = context_to_scope_name(default_context)

            # Get Current (check for user override)
            current = default
            current_scope = default_scope
            if hasattr(ui, "settings"):
                settings_key = f"shortcuts.{slots_cls_name}.{name}"
                override = ui.settings.value(settings_key)
                if override:
                    current = override
                scope_override = ui.settings.value(f"{settings_key}.scope")
                # Only honour overrides that map to a known scope. Anything
                # else (legacy bad data, manual edits, mis-typed values) is
                # ignored so the user falls back to the decorator default
                # rather than seeing a stuck/garbage scope label.
                if scope_override in SCOPE_NAME_TO_CONTEXT:
                    current_scope = scope_override

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
                }
            )

        return registry

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
        key = f"shortcuts.{cls_name}.{slot_name}"
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

        # 3. Live Re-bind
        existing_shortcuts = getattr(slots_instance, "_connected_shortcuts", {})
        shortcut = existing_shortcuts.get(slot_name)

        if shortcut:
            shortcut.setKey(QtGui.QKeySequence(sequence))
            shortcut.setContext(target_context)
            self.logger.info(
                f"[set_user_shortcut] Rebound {slot_name} to {sequence} "
                f"({context_to_scope_name(target_context)})"
            )
        elif method:
            self._create_switchboard_shortcut(
                ui,
                slots_instance,
                method,
                slot_name,
                sequence,
                target_context,
                meta.get("robust", False),
            )
