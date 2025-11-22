# !/usr/bin/python
# coding=utf-8
from typing import Dict, List, Tuple, Union, Callable, Optional
from qtpy import QtWidgets, QtGui, QtCore


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
            self.shortcuts[key]["shortcut"].deleteLater()
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
