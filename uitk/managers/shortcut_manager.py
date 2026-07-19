# !/usr/bin/python
# coding=utf-8
"""Generic keyboard-shortcut primitives, usable by any Qt widget.

This module is paired with :mod:`uitk.switchboard.shortcuts`, which
holds the Switchboard-specific glue (the ``@Shortcut`` slot decorator
and ``SwitchboardShortcutMixin``). Anything in this file is intended
for direct use by widgets without involving Switchboard:

* :class:`GlobalShortcut` — robust press/release detection via event filter.
* :class:`ShortcutManager` — per-widget registry of shortcuts.
* Scope-name helpers (string ↔ ``Qt.ShortcutContext``) used by both layers.

This is the lower layer: it has no Switchboard dependency, so the split
is by layer (primitives vs. orchestration), not duplication — merging the
two would force the widget layer to import :mod:`uitk.switchboard`.
"""
from typing import Callable, Dict, List, Optional, Tuple, Union
from qtpy import QtCore, QtGui, QtWidgets


# Scope name <-> Qt.ShortcutContext mapping. Used for persistence (string form
# survives JSON/QSettings) and editor UX. The two end-user-facing scopes are
# "window" and "application"; the widget-scoped variants are decorator-only.
SCOPE_NAME_TO_CONTEXT: Dict[str, QtCore.Qt.ShortcutContext] = {
    "widget": QtCore.Qt.WidgetShortcut,
    "widget_children": QtCore.Qt.WidgetWithChildrenShortcut,
    "window": QtCore.Qt.WindowShortcut,
    "application": QtCore.Qt.ApplicationShortcut,
}
SCOPE_CONTEXT_TO_NAME: Dict[QtCore.Qt.ShortcutContext, str] = {
    v: k for k, v in SCOPE_NAME_TO_CONTEXT.items()
}


def context_to_scope_name(context: QtCore.Qt.ShortcutContext) -> str:
    """Convert a Qt.ShortcutContext to its persistence string."""
    return SCOPE_CONTEXT_TO_NAME.get(context, "window")


def scope_name_to_context(name: str) -> QtCore.Qt.ShortcutContext:
    """Convert a persisted scope string to a Qt.ShortcutContext."""
    return SCOPE_NAME_TO_CONTEXT.get(name, QtCore.Qt.WindowShortcut)


def host_namespace_suffix(context_tags) -> str:
    """Settings-key suffix namespacing persisted state by host context.

    QSettings is shared across processes by ``(org, app)``, so without a per-host
    suffix a Maya and a Blender session read/write the SAME keys and their
    bindings collide. Returns ``"_maya"`` / ``"_blender"`` (tags sorted + joined)
    for a non-empty ``context_tags``, or ``""`` for standalone.

    Single source of the convention, shared by the marking-menu binding store
    (``MarkingMenu._binding_store_key``) and the shortcut/command store
    (``SwitchboardShortcutMixin._shortcut_ns``) so the two can't drift — drift
    would re-introduce the cross-host collision both are guarding against.
    """
    tags = sorted(context_tags or ())
    return ("_" + "_".join(tags)) if tags else ""


# Known DCC host top-level window object names, searched when resolving an
# always-visible owner for application-scoped shortcuts.
_HOST_WINDOW_NAMES = ("MayaWindow", "3dsMaxWindow")


def resolve_application_host(
    widget: Optional[QtWidgets.QWidget],
) -> Optional[QtWidgets.QWidget]:
    """Return an always-visible top-level window to own an application shortcut.

    Qt deactivates a ``QShortcut`` whenever its owner widget is hidden — even at
    ``Qt.ApplicationShortcut`` scope, because the visibility check runs *before*
    the context check (see ``QShortcutMap::correctContextWidget``). Tool UIs are
    usually hidden when idle, which is exactly when an application-scoped
    shortcut is meant to fire, so owning the shortcut by the slot window makes it
    silently inert. Owning it by the host's main window (which stays visible)
    makes the shortcut genuinely application-wide.

    Resolution order:
        1. A known DCC host top-level (``MayaWindow`` / ``3dsMaxWindow``).
        2. The nearest visible top-level ancestor of *widget*.
        3. Any visible top-level window.
        4. *widget* itself (last resort — preserves prior behaviour).
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        return widget

    # 1. Known DCC host windows are the canonical application owner.
    for w in app.topLevelWidgets():
        if w.objectName() in _HOST_WINDOW_NAMES and w.isVisible():
            return w

    # 2. Nearest visible top-level ancestor of the widget (DCC-agnostic).
    w = widget
    seen: set = set()
    while w is not None and id(w) not in seen:
        seen.add(id(w))
        win = w.window()
        if win is not None and win.isWindow() and win.isVisible():
            return win
        w = w.parentWidget()

    # 3. Any visible top-level window (e.g. a standalone app's main window).
    for w in app.topLevelWidgets():
        if w.isWindow() and w.isVisible():
            return w

    # 4. Last resort: keep prior behaviour rather than dropping the shortcut.
    return widget


def find_duplicate_application_shortcuts(app=None) -> Dict[str, int]:
    """Return ``{sequence: count}`` for key sequences bound by more than one
    *enabled, application-scoped* ``QShortcut`` in the running application.

    An application-scoped shortcut fires regardless of which window has focus, so
    two enabled ones on the same sequence are ambiguous — Qt logs an "Ambiguous
    shortcut overload" and fires **neither**. That is the exact failure mode that
    silently killed repeat-last in Maya (one app shortcut was created per slot
    instance, so several identical ``Ctrl+Shift+R`` shortcuts stacked up).

    Use it as a diagnostic or a test invariant: a healthy application returns an
    empty dict. Empty key sequences (an unbound ``QShortcut``) are ignored, and
    so are window-/widget-scoped shortcuts (those are disambiguated by focus, so
    the same key is legitimately reusable across windows). Returns ``{}`` when no
    ``QApplication`` exists.
    """
    app = app or QtWidgets.QApplication.instance()
    if app is None:
        return {}
    # QShortcut moved QtWidgets -> QtGui in Qt6; accept whichever the binding has.
    shortcut_types = tuple(
        t
        for t in (getattr(QtWidgets, "QShortcut", None), getattr(QtGui, "QShortcut", None))
        if isinstance(t, type)
    )
    counts: Dict[str, int] = {}
    seen: set = set()
    for w in app.allWidgets():
        for child in w.children():
            if not isinstance(child, shortcut_types) or id(child) in seen:
                continue
            seen.add(id(child))
            if not child.isEnabled():
                continue
            if child.context() != QtCore.Qt.ApplicationShortcut:
                continue
            seq = child.key().toString()
            if seq:
                counts[seq] = counts.get(seq, 0) + 1
    return {seq: n for seq, n in counts.items() if n > 1}


class GlobalShortcut(QtCore.QObject):
    """A robust global shortcut handler that detects both press and release events.

    This class wraps a QShortcut for standard activation (press) but adds an
    application-level event filter to reliably detect key release events, which
    standard QShortcuts do not support. This is particularly useful for
    hold-and-release interactions (like marking menus) in complex host
    environments (like Maya) where key events can be swallowed.

    Signals:
        pressed: Emitted when the shortcut is activated (key down).
        released: Emitted when the shortcut key is released.
    """

    pressed = QtCore.Signal()
    released = QtCore.Signal()

    _instances = set()  # Keep references to prevent GC

    def __init__(
        self,
        key_sequence: Union[str, QtGui.QKeySequence],
        parent: QtWidgets.QWidget,
        context: QtCore.Qt.ShortcutContext = QtCore.Qt.ApplicationShortcut,
    ):
        super().__init__(parent)
        self._parent = parent
        self._key_sequence = (
            key_sequence
            if isinstance(key_sequence, QtGui.QKeySequence)
            else QtGui.QKeySequence(key_sequence)
        )
        self._key_val = self._get_primary_key(self._key_sequence)

        # Internal state
        self._is_down = False

        # 1. Setup QShortcut for robust Press detection (activates on press)
        self._shortcut = QtWidgets.QShortcut(self._key_sequence, parent)
        self._shortcut.setContext(context)
        self._shortcut.setAutoRepeat(False)
        self._shortcut.activated.connect(self._on_press)

        # 2. Setup Event Filter for Release detection
        self._target = self._resolve_target(parent)
        self._filter_source = self._install_event_filter()

        GlobalShortcut._instances.add(self)

    def _get_primary_key(self, sequence: QtGui.QKeySequence) -> int:
        """Extract the primary key from the sequence for raw event checking.

        Removes modifiers to ensure comparison with event.key() which only
        returns the base key code.
        """
        if sequence.isEmpty():
            return 0

        combined = sequence[0]

        # PySide6 returns QKeyCombination, PyQt/older returns int
        if hasattr(combined, "key"):
            # PySide6: QKeyCombination has .key() method
            key_enum = combined.key()
            # key_enum might be a Qt.Key enum, convert to int
            return int(key_enum) if not isinstance(key_enum, int) else key_enum
        else:
            # PyQt5/older: combined is already an int with modifiers baked in
            # Mask out modifiers: 0x01FFFFFF is ~KeyboardModifierMask
            return combined & 0x01FFFFFF

    def _resolve_target(self, explicit_parent):
        """Find the robust target for event filtering (e.g. MayaWindow)."""
        app = QtWidgets.QApplication.instance()
        if app:
            # First try the explicit parent's window
            if explicit_parent:
                window = explicit_parent.window()
                if window:
                    return window

            # Fallback to finding MayaWindow or ActiveWindow
            active = app.activeWindow()
            if isinstance(active, QtWidgets.QWidget):
                return active

            # Search top levels for common host windows
            for widget in app.topLevelWidgets():
                if (
                    isinstance(widget, QtWidgets.QWidget)
                    and widget.objectName() in _HOST_WINDOW_NAMES
                ):
                    return widget

        return explicit_parent

    def _install_event_filter(self):
        """Install event filter on the application or target window."""
        app = QtWidgets.QApplication.instance()
        source = app if app else self._target
        if source:
            source.installEventFilter(self)
        return source

    def eventFilter(self, obj, event):
        """Monitor global events for the specific key release."""
        if (
            self._is_down
            and event.type() == QtCore.QEvent.KeyRelease
            and not event.isAutoRepeat()
        ):
            # Check if the released key matches our shortcut key.
            # event.key() returns the key code without modifiers, so we compare
            # it against the stripped key value stored in _key_val.
            # We avoid using event.matches(self._key_sequence) because it requires
            # a StandardKey enum in PySide6 and throws a TypeError with QKeySequence.
            if event.key() == self._key_val:
                self._on_release()
                # We consume the event? Maybe not, safety first.
                # return True

        return super().eventFilter(obj, event)

    def _on_press(self):
        if self._is_down:
            return
        self._is_down = True
        self.pressed.emit()

    def _on_release(self):
        if not self._is_down:
            return
        self._is_down = False
        self.released.emit()

    def setEnabled(self, enabled: bool):
        self._shortcut.setEnabled(enabled)
        if not enabled:
            # Force release if disabled while held
            self._on_release()

    def setKey(self, key_sequence: Union[str, QtGui.QKeySequence]):
        self._key_sequence = (
            key_sequence
            if isinstance(key_sequence, QtGui.QKeySequence)
            else QtGui.QKeySequence(key_sequence)
        )
        self._key_val = self._get_primary_key(self._key_sequence)
        self._shortcut.setKey(self._key_sequence)

    def setContext(self, context: QtCore.Qt.ShortcutContext):
        """Live-update the underlying QShortcut's context.

        Mirrors QShortcut.setContext so SwitchboardShortcutMixin can rebind
        scope without recreating the shortcut.
        """
        self._shortcut.setContext(context)

    def dispose(self) -> None:
        """Disable, unregister, and schedule deletion of this shortcut.

        Symmetric with ``__init__`` adding ``self`` to the static
        ``_instances`` set: that strong self-reference keeps the wrapper alive,
        so ``deleteLater`` alone can never collect it — every caller that drops
        a ``GlobalShortcut`` must drop the static ref too. Centralised here so
        the lifecycle stays in one place (forgetting the discard was a real
        leak). Disabling first makes the shortcut inert immediately, before the
        deferred deletion is processed.
        """
        self.setEnabled(False)
        GlobalShortcut._instances.discard(self)
        if self._shortcut is not None:
            self._shortcut.deleteLater()
        self.deleteLater()


class ShortcutManager:
    """Centralized shortcut management with clear separation of concerns"""

    def __init__(self, widget: QtWidgets.QWidget):
        self.widget = widget
        self.shortcuts: Dict[str, Dict] = {}
        self._change_callbacks: List[Callable] = []

    def add_shortcut(
        self,
        key_sequence: Union[str, QtGui.QKeySequence],
        action: Callable,
        description: str = "",
        context: QtCore.Qt.ShortcutContext = QtCore.Qt.WidgetShortcut,
        hidden: bool = False,
    ) -> QtWidgets.QShortcut:
        """Add a keyboard shortcut with optional description and context

        Parameters:
            key_sequence: Key combination (e.g., "Ctrl+C" or QtGui.QKeySequence.Copy)
            action: Function to call when shortcut is activated
            description: Optional description for documentation
            context: Shortcut context (Widget, Window, Application)
            hidden: When True, the binding is omitted from the shortcut editor's
                default view (still revealed by its "Show hidden" toggle, and
                still collision-checked). For functional/semantic keys.

        Returns:
            The created QShortcut object
        """
        if isinstance(key_sequence, str):
            sequence = QtGui.QKeySequence(key_sequence)
        else:
            sequence = QtGui.QKeySequence(key_sequence)

        shortcut = QtWidgets.QShortcut(sequence, self.widget)
        shortcut.setContext(context)
        shortcut.activated.connect(action)

        # Store for potential cleanup or reference
        shortcut_key = sequence.toString()
        # Overwriting an existing same-sequence binding must dispose the old
        # QShortcut first; otherwise it stays enabled+parented to self.widget
        # (Qt then logs an ambiguous-overload and fires NEITHER) and is orphaned
        # out of self.shortcuts where it can never be removed/cleared.
        prev = self.shortcuts.get(shortcut_key)
        if prev is not None:
            self._dispose(prev.get("shortcut"))
        self.shortcuts[shortcut_key] = {
            "shortcut": shortcut,
            "action": action,
            "description": description,
            "context": context,
            "default_key": shortcut_key,
            "hidden": hidden,
        }

        self._notify_change()
        return shortcut

    def add_shortcuts_batch(
        self,
        shortcuts_config: List[Tuple[Union[str, QtGui.QKeySequence], Callable, str]],
    ) -> List[QtWidgets.QShortcut]:
        """Add multiple shortcuts from a configuration list

        Parameters:
            shortcuts_config: List of tuples.  Each tuple may be:
                - ``(key_sequence, action)``
                - ``(key_sequence, action, description)``
                - ``(key_sequence, action, description, context)``

        Returns:
            List of created QShortcut objects
        """
        created_shortcuts = []
        for config in shortcuts_config:
            if len(config) == 4:
                key_seq, action, description, context = config
                shortcut = self.add_shortcut(key_seq, action, description, context)
            elif len(config) == 3:
                key_seq, action, description = config
                shortcut = self.add_shortcut(key_seq, action, description)
            elif len(config) == 2:
                key_seq, action = config
                shortcut = self.add_shortcut(key_seq, action)
            else:
                continue
            created_shortcuts.append(shortcut)
        return created_shortcuts

    def add_global_shortcut(
        self,
        key_sequence: Union[str, QtGui.QKeySequence],
        on_press: Callable = None,
        on_release: Callable = None,
        description: str = "",
    ) -> GlobalShortcut:
        """Add a global shortcut (robust press/release detection).

        Parameters:
            key_sequence: Key combination.
            on_press: Function to call when activated.
            on_release: Function to call when released.
            description: Description.

        Returns:
            GlobalShortcut instance.
        """
        shortcut = GlobalShortcut(key_sequence, self.widget)
        if on_press:
            shortcut.pressed.connect(on_press)
        if on_release:
            shortcut.released.connect(on_release)

        shortcut_key = shortcut._key_sequence.toString()
        # Same overwrite discipline as add_shortcut: dispose any prior binding on
        # this sequence (GlobalShortcut._dispose also drops its static _instances
        # ref + event filter) before replacing it, else it leaks and ambiguates.
        prev = self.shortcuts.get(shortcut_key)
        if prev is not None:
            self._dispose(prev.get("shortcut"))
        self.shortcuts[shortcut_key] = {
            "shortcut": shortcut,
            "description": description,
            "type": "global",
            "default_key": shortcut_key,
        }
        return shortcut

    def add_info_entry(
        self,
        key_label: str,
        description: str,
    ) -> None:
        """Register a display-only entry (e.g. mouse actions).

        These appear in the shortcut editor but cannot be rebound.
        """
        self.shortcuts[key_label] = {
            "shortcut": None,
            "action": None,
            "description": description,
            "default_key": key_label,
            "read_only": True,
        }

    def remove_shortcut(self, key_sequence: Union[str, QtGui.QKeySequence]) -> bool:
        """Remove a specific shortcut

        Parameters:
            key_sequence: The key sequence to remove

        Returns:
            True if shortcut was found and removed, False otherwise
        """
        if isinstance(key_sequence, str):
            key = key_sequence
        else:
            key = QtGui.QKeySequence(key_sequence).toString()

        if key in self.shortcuts:
            sc = self.shortcuts[key]["shortcut"]
            self._dispose(sc)
            del self.shortcuts[key]
            # Symmetric with add_shortcut/rebind_shortcut: subscribers (e.g. the
            # sequencer's _sync_shortcut_sequences) must re-read the binding set,
            # else a removed key stays in a downstream cache — a destroyed
            # transport would leave Space/Alt+Space swallowed-but-dead.
            self._notify_change()
            return True
        return False

    @staticmethod
    def _dispose(sc) -> None:
        """Tear down a managed shortcut, disabling it first so it is inert
        immediately. GlobalShortcut also needs its static ``_instances`` ref
        dropped (via ``dispose``) or it can't be collected."""
        if sc is None:
            return
        if isinstance(sc, GlobalShortcut):
            sc.dispose()
        else:
            sc.setEnabled(False)
            sc.deleteLater()

    def clear_all(self) -> None:
        """Remove all shortcuts"""
        for shortcut_data in self.shortcuts.values():
            self._dispose(shortcut_data["shortcut"])
        self.shortcuts.clear()

    # -- change notification -----------------------------------------------

    def on_change(self, callback: Callable) -> None:
        """Register a callback invoked after any shortcut is rebound."""
        self._change_callbacks.append(callback)

    def _notify_change(self) -> None:
        for cb in self._change_callbacks:
            cb()

    # -- rebinding ---------------------------------------------------------

    def rebind_shortcut(self, old_key: str, new_key: str) -> bool:
        """Change the key sequence for an existing shortcut.

        If *new_key* is already occupied by another shortcut the request
        is rejected and ``False`` is returned to prevent silent overwrites.

        Returns ``True`` on success, ``False`` if *old_key* was not found
        or *new_key* collides with an existing binding.
        """
        old_norm = QtGui.QKeySequence(old_key).toString()
        new_norm = QtGui.QKeySequence(new_key).toString()
        if old_norm == new_norm:
            return True
        if old_norm not in self.shortcuts:
            return False
        if new_norm in self.shortcuts:
            return False  # collision — caller should warn the user
        entry = self.shortcuts.pop(old_norm)
        entry["shortcut"].setKey(QtGui.QKeySequence(new_key))
        self.shortcuts[new_norm] = entry
        self._notify_change()
        return True

    # -- editor window -----------------------------------------------------

    def show_editor(self, parent=None, title: str = "Shortcuts") -> None:
        """Open the unified shortcut editor for this manager's bindings.

        Routes through the one :class:`ShortcutEditor` (via
        :class:`ManagerSwitchboardFacade`) so a standalone widget gets the same
        editor — filtering, hidden/editable handling, collision checks — as
        Switchboard slots/commands, instead of a bespoke dialog. Loaded on
        demand so importing this module stays Switchboard-free and lightweight.
        """
        from uitk.widgets.editors.shortcut_editor.manager_facade import (
            ManagerSwitchboardFacade,
        )
        from uitk.widgets.editors.shortcut_editor.registry_editor import ShortcutEditor

        if getattr(self, "_editor", None) is not None:
            try:
                self._editor.show()
                self._editor.raise_()
                return
            except RuntimeError:
                pass  # underlying C++ editor was destroyed — rebuild below
        facade = ManagerSwitchboardFacade(self, ui_name=title)
        self._editor = ShortcutEditor(facade, parent=parent or self.widget)
        # Focused-view column tailoring: a manager binding's description is
        # already its Action-column name (Description would be empty), and its
        # scope is fixed by the owner widget (not per-row editable, so the Scope
        # column's toggles would all be inert) — hide both.
        self._editor.set_columns_hidden(
            (self._editor.COL_DESCRIPTION, self._editor.COL_SCOPE)
        )
        self._editor.setWindowTitle(title)
        self._editor.show()

    def get_shortcuts_info(self) -> Dict[str, str]:
        """Get information about all registered shortcuts

        Returns:
            Dictionary mapping shortcut keys to descriptions
        """
        return {key: data["description"] for key, data in self.shortcuts.items()}

    def has_shortcut(self, key_sequence: Union[str, QtGui.QKeySequence]) -> bool:
        """Check if a shortcut is registered

        Parameters:
            key_sequence: The key sequence to check

        Returns:
            True if shortcut exists, False otherwise
        """
        if isinstance(key_sequence, str):
            key = key_sequence
        else:
            key = QtGui.QKeySequence(key_sequence).toString()
        return key in self.shortcuts

    def get_shortcut(
        self, key_sequence: Union[str, QtGui.QKeySequence]
    ) -> Optional[QtWidgets.QShortcut]:
        """Get a specific shortcut object

        Parameters:
            key_sequence: The key sequence to get

        Returns:
            QShortcut object if found, None otherwise
        """
        if isinstance(key_sequence, str):
            key = key_sequence
        else:
            key = QtGui.QKeySequence(key_sequence).toString()

        if key in self.shortcuts:
            return self.shortcuts[key]["shortcut"]
        return None

    # -- unified shortcut-editor integration -------------------------------

    def get_registry(self) -> List[Dict]:
        """Registry entries for this manager's shortcuts, in the shared editor
        shape (:meth:`SwitchboardShortcutMixin._build_shortcut_entries`).

        Lets the one unified :class:`ShortcutEditor` render + edit a manager's
        bindings exactly like Switchboard slots/commands — the DRY replacement
        for the bespoke :class:`ShortcutEditorDialog`. The entry's ``method`` is
        the current sequence (the manager keys by sequence, which is unique), so
        the editor can route a rebind back through :meth:`rebind_shortcut`
        (old sequence -> new). ``read_only`` info rows surface as ``editable``
        False (shown but locked); ``hidden`` rows obey the editor's Show-hidden
        toggle.
        """
        entries: List[Dict] = []
        for key, data in self.shortcuts.items():
            scope = context_to_scope_name(
                data.get("context", QtCore.Qt.WidgetShortcut)
            )
            entries.append(
                {
                    "class": "",  # a manager has no Slots-class namespace
                    "method": key,  # stable id within a render = current seq
                    "name": data.get("description") or key,
                    "current": key,
                    "default": data.get("default_key", key),
                    "current_scope": scope,
                    "default_scope": scope,
                    # The description is the Action-column name; leave doc empty
                    # so the editor's Description column isn't a duplicate of it.
                    "doc": "",
                    "hidden": bool(data.get("hidden", False)),
                    "editable": not bool(data.get("read_only", False)),
                }
            )
        return entries
