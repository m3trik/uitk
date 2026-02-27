# !/usr/bin/python
# coding=utf-8
import inspect
import functools
from typing import Dict, List, Tuple, Union, Callable, Optional, Any
from qtpy import QtWidgets, QtGui, QtCore


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
                if isinstance(widget, QtWidgets.QWidget) and widget.objectName() in [
                    "MayaWindow",
                    "3dsMaxWindow",
                ]:
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


class ShortcutManager:
    """Centralized shortcut management with clear separation of concerns"""

    def __init__(self, widget: QtWidgets.QWidget):
        self.widget = widget
        self.shortcuts: Dict[str, Dict] = {}

    def add_shortcut(
        self,
        key_sequence: Union[str, QtGui.QKeySequence],
        action: Callable,
        description: str = "",
        context: QtCore.Qt.ShortcutContext = QtCore.Qt.WidgetShortcut,
    ) -> QtWidgets.QShortcut:
        """Add a keyboard shortcut with optional description and context

        Parameters:
            key_sequence: Key combination (e.g., "Ctrl+C" or QtGui.QKeySequence.Copy)
            action: Function to call when shortcut is activated
            description: Optional description for documentation
            context: Shortcut context (Widget, Window, Application)

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
        self.shortcuts[shortcut_key] = {
            "shortcut": shortcut,
            "action": action,
            "description": description,
            "context": context,
        }

        return shortcut

    def add_shortcuts_batch(
        self,
        shortcuts_config: List[Tuple[Union[str, QtGui.QKeySequence], Callable, str]],
    ) -> List[QtWidgets.QShortcut]:
        """Add multiple shortcuts from a configuration list

        Parameters:
            shortcuts_config: List of tuples (key_sequence, action, description)

        Returns:
            List of created QShortcut objects
        """
        created_shortcuts = []
        for config in shortcuts_config:
            if len(config) == 3:
                key_seq, action, description = config
                shortcut = self.add_shortcut(key_seq, action, description)
                created_shortcuts.append(shortcut)
            elif len(config) == 2:
                key_seq, action = config
                shortcut = self.add_shortcut(key_seq, action)
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
        self.shortcuts[shortcut_key] = {
            "shortcut": shortcut,
            "description": description,
            "type": "global",
        }
        return shortcut

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
            shortcut_data = self.shortcuts[key]
            # Handle GlobalShortcut explicit cleanup if needed, though deleteLater works for QObject
            if isinstance(shortcut_data["shortcut"], GlobalShortcut):
                # Remove from static set if we kept it there, but we didn't implement remove method there.
                # Just rely on GC and deleteLater.
                pass

            shortcut_data["shortcut"].deleteLater()
            del self.shortcuts[key]
            return True
        return False

    def clear_all(self) -> None:
        """Remove all shortcuts"""
        for shortcut_data in self.shortcuts.values():
            shortcut_data["shortcut"].deleteLater()
        self.shortcuts.clear()

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


class ShortcutMixin:
    """Mixin class that provides easy shortcut management for any Qt widget

    Usage:
        class MyWidget(QtWidgets.QWidget, ShortcutMixin):
            def __init__(self):
                super().__init__()
                self.setup_shortcuts()

            def setup_shortcuts(self):
                self.add_shortcut("Ctrl+S", self.save, "Save file")
                self.add_shortcuts_from_config([
                    ("Ctrl+O", self.open_file, "Open file"),
                    ("Ctrl+N", self.new_file, "New file"),
                ])
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._shortcut_manager: Optional[ShortcutManager] = None

    @property
    def shortcut_manager(self) -> ShortcutManager:
        """Lazy initialization of shortcut manager"""
        if self._shortcut_manager is None:
            self._shortcut_manager = ShortcutManager(self)
        return self._shortcut_manager

    def add_shortcut(
        self,
        key_sequence: Union[str, QtGui.QKeySequence],
        action: Callable,
        description: str = "",
        context: QtCore.Qt.ShortcutContext = QtCore.Qt.WidgetShortcut,
    ) -> QtWidgets.QShortcut:
        """Add a keyboard shortcut

        Parameters:
            key_sequence: Key combination
            action: Function to call
            description: Optional description
            context: Shortcut context

        Returns:
            The created QShortcut object
        """
        return self.shortcut_manager.add_shortcut(
            key_sequence, action, description, context
        )

    def add_shortcuts_from_config(
        self,
        shortcuts_config: List[Tuple[Union[str, QtGui.QKeySequence], Callable, str]],
    ) -> List[QtWidgets.QShortcut]:
        """Add multiple shortcuts from configuration

        Parameters:
            shortcuts_config: List of (key_sequence, action, description) tuples

        Returns:
            List of created shortcuts
        """
        return self.shortcut_manager.add_shortcuts_batch(shortcuts_config)

    def remove_shortcut(self, key_sequence: Union[str, QtGui.QKeySequence]) -> bool:
        """Remove a shortcut"""
        return self.shortcut_manager.remove_shortcut(key_sequence)

    def clear_all_shortcuts(self) -> None:
        """Clear all shortcuts"""
        if self._shortcut_manager:
            self._shortcut_manager.clear_all()

    def get_shortcuts_info(self) -> Dict[str, str]:
        """Get all shortcuts information"""
        if self._shortcut_manager:
            return self._shortcut_manager.get_shortcuts_info()
        return {}

    def add_shortcuts_to_context_menu(
        self, menu: QtWidgets.QMenu, submenu_title: str = "Keyboard Shortcuts"
    ) -> QtWidgets.QMenu:
        """Add shortcuts information to a context menu

        Parameters:
            menu: The menu to add shortcuts info to
            submenu_title: Title for the shortcuts submenu

        Returns:
            The created shortcuts submenu
        """
        shortcuts_menu = menu.addMenu(submenu_title)
        shortcuts_info = self.get_shortcuts_info()

        if shortcuts_info:
            for shortcut, description in shortcuts_info.items():
                action = shortcuts_menu.addAction(f"{shortcut}: {description}")
                action.setEnabled(False)  # Make it non-clickable, just informational
        else:
            action = shortcuts_menu.addAction("No shortcuts registered")
            action.setEnabled(False)

        return shortcuts_menu

    def add_menu_actions_with_shortcuts(
        self,
        menu: Optional[QtWidgets.QMenu] = None,
        actions_config: Optional[
            List[Tuple[str, Callable, Optional[Union[str, QtGui.QKeySequence]]]]
        ] = None,
        auto_match_shortcuts: bool = True,
    ) -> QtWidgets.QMenu:
        """Add menu actions with inline shortcut display

        This single method can:
        1. Create a new menu with actions (if menu=None)
        2. Add actions to an existing menu (if menu provided)
        3. Auto-match registered shortcuts with callbacks
        4. Use provided shortcut hints

        Parameters:
            menu: Existing menu to add to, or None to create new menu
            actions_config: List of tuples (text, callback, [shortcut_key])
            auto_match_shortcuts: Whether to auto-match registered shortcuts with callbacks

        Returns:
            The menu (created or provided)
        """
        if menu is None:
            menu = QtWidgets.QMenu()

        if not actions_config:
            return menu

        shortcuts_info = self.get_shortcuts_info() if auto_match_shortcuts else {}

        for config in actions_config:
            if len(config) >= 2:
                text = config[0]
                callback = config[1]
                shortcut_key = config[2] if len(config) > 2 else None

                # Auto-match shortcut if none provided and auto-match is enabled
                if shortcut_key is None and auto_match_shortcuts:
                    for key, info in self.shortcut_manager.shortcuts.items():
                        if info["action"] == callback:
                            shortcut_key = key
                            break

                # Create the action
                action = menu.addAction(text)
                action.triggered.connect(callback)

                # Set shortcut for inline display if available
                if shortcut_key:
                    if isinstance(shortcut_key, str):
                        key_sequence = QtGui.QKeySequence(shortcut_key)
                    else:
                        key_sequence = QtGui.QKeySequence(shortcut_key)
                    action.setShortcut(key_sequence)

        return menu

    # Convenience methods for common use cases
    def create_context_menu(self, actions_config, **kwargs):
        """Convenience method to create a new context menu with shortcuts"""
        return self.add_menu_actions_with_shortcuts(None, actions_config, **kwargs)

    def add_actions_to_menu(self, menu, actions_config, **kwargs):
        """Convenience method to add actions to an existing menu"""
        return self.add_menu_actions_with_shortcuts(menu, actions_config, **kwargs)


# Convenience function for standard shortcuts
def create_standard_shortcuts_config() -> List[Tuple[QtGui.QKeySequence, str, str]]:
    """Create a standard set of shortcut configurations

    Returns:
        List of (key_sequence, method_name, description) tuples for common actions
    """
    return [
        (QtGui.QKeySequence.Copy, "copy", "Copy"),
        (QtGui.QKeySequence.Cut, "cut", "Cut"),
        (QtGui.QKeySequence.Paste, "paste", "Paste"),
        (QtGui.QKeySequence.SelectAll, "selectAll", "Select All"),
        (QtGui.QKeySequence.Undo, "undo", "Undo"),
        (QtGui.QKeySequence.Redo, "redo", "Redo"),
        (QtGui.QKeySequence.Find, "find", "Find"),
        (QtGui.QKeySequence.Save, "save", "Save"),
        (QtGui.QKeySequence.Open, "open", "Open"),
        (QtGui.QKeySequence.New, "new", "New"),
        (QtGui.QKeySequence.Close, "close", "Close"),
        (QtGui.QKeySequence.Quit, "quit", "Quit"),
        (QtGui.QKeySequence.Refresh, "refresh", "Refresh"),
    ]


def apply_standard_shortcuts(widget, shortcuts_to_apply: Optional[List[str]] = None):
    """Apply standard shortcuts to a widget that has corresponding methods

    Parameters:
        widget: Widget that implements ShortcutMixin
        shortcuts_to_apply: List of method names to apply shortcuts for.
                          If None, applies all available standard shortcuts.
    """
    if not hasattr(widget, "add_shortcut"):
        raise TypeError(
            "Widget must implement ShortcutMixin to use apply_standard_shortcuts"
        )

    standard_config = create_standard_shortcuts_config()

    for key_seq, method_name, description in standard_config:
        if shortcuts_to_apply is None or method_name in shortcuts_to_apply:
            if hasattr(widget, method_name):
                method = getattr(widget, method_name)
                widget.add_shortcut(key_seq, method, description)


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

            # 3. Check Settings for Override
            final_sequence = default_sequence
            settings_key = f"shortcuts.{slots_cls_name}.{name}"

            if hasattr(ui, "settings"):
                # If the key doesn't exist, settings might return None. using .get() with default.
                # Assuming SettingsManager Proxy object.
                user_override = ui.settings.value(settings_key)
                if user_override:
                    final_sequence = user_override

            if not final_sequence:
                continue

            # 4. Register
            self._create_switchboard_shortcut(
                ui,
                slots_instance,
                method,
                name,
                final_sequence,
                meta.get("context"),
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

            # Get Current (check for user override)
            current = default
            if hasattr(ui, "settings"):
                settings_key = f"shortcuts.{slots_cls_name}.{name}"
                override = ui.settings.value(settings_key)
                if override:
                    current = override

            registry.append(
                {
                    "class": slots_cls_name,
                    "method": name,
                    "name": meta.get("name", name),
                    "current": current,
                    "default": default,
                    "doc": inspect.cleandoc(doc).split("\n")[0] if doc else "",
                }
            )

        return registry

    def set_user_shortcut(
        self, ui: QtWidgets.QWidget, slot_name: str, sequence: str
    ) -> None:
        """Update a shortcut setting dynamically and live-update the active QShortcut.

        Args:
            ui (QtWidgets.QWidget): The main window/UI.
            slot_name (str): The name of the method (e.g., "save_file").
            sequence (str): The new key sequence (e.g., "Ctrl+Alt+S").
        """
        slots_instance = self.get_slots_instance(ui)
        if not slots_instance:
            return

        # 1. Update Persistent Settings
        if hasattr(ui, "settings"):
            cls_name = slots_instance.__class__.__name__
            key = f"shortcuts.{cls_name}.{slot_name}"
            ui.settings.setValue(key, sequence)

        # 2. Live Re-bind
        # Check if we already have a shortcut for this slot
        existing_shortcuts = getattr(slots_instance, "_connected_shortcuts", {})
        shortcut = existing_shortcuts.get(slot_name)

        if shortcut:
            # Update existing
            shortcut.setKey(QtGui.QKeySequence(sequence))
            self.logger.info(f"[set_user_shortcut] Rebound {slot_name} to {sequence}")
        else:
            # Create new if it didn't exist (e.g. was previously unset)
            method = getattr(slots_instance, slot_name, None)
            if method:
                # Need to infer context or default to WindowShortcut
                # Try to get from meta, else Window
                meta = getattr(method, "_shortcut_meta", {})
                context = meta.get("context", QtCore.Qt.WindowShortcut)

                self._create_switchboard_shortcut(
                    ui, slots_instance, method, slot_name, sequence, context
                )


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
Usage Examples:

1. Basic usage with mixin:
    class MyTextEdit(QtWidgets.QTextEdit, ShortcutMixin):
        def __init__(self):
            super().__init__()
            self.setup_shortcuts()
            
        def setup_shortcuts(self):
            self.add_shortcut("Ctrl+S", self.save_file, "Save file")
            self.add_shortcut("F5", self.refresh, "Refresh content")

2. Batch shortcut setup:
    shortcuts_config = [
        ("Ctrl+C", self.copy, "Copy text"),
        ("Ctrl+V", self.paste, "Paste text"),
        ("Del", self.clear, "Clear content"),
    ]
    self.add_shortcuts_from_config(shortcuts_config)

3. Standard shortcuts:
    apply_standard_shortcuts(self, ["copy", "paste", "selectAll"])

4. Context menu integration:
    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Some Action", self.some_action)
        self.add_shortcuts_to_context_menu(menu)
        menu.exec(event.globalPos())
"""
