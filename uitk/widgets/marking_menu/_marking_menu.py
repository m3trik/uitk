# !/usr/bin/python
# coding=utf-8
import sys
import os
from typing import Optional
from qtpy import QtCore, QtWidgets, QtGui
import pythontk as ptk

# From this package:
from uitk.switchboard import Switchboard
from uitk.events import EventFactoryFilter, MouseTracking
from .overlay import Overlay
from uitk.handlers.ui_handler import UiHandler


class ShortcutHandler(QtCore.QObject):
    """Application-wide shortcut that toggles the MarkingMenu overlay."""

    _instance: Optional["ShortcutHandler"] = None

    def __init__(
        self,
        owner: "MarkingMenu",
        shortcut_parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(owner)
        self._owner = owner
        self._target = self._resolve_target(shortcut_parent)
        sequence = self._build_sequence(owner.key_show)
        self._shortcut = QtWidgets.QShortcut(sequence, self._target)
        self._shortcut.setContext(QtCore.Qt.ApplicationShortcut)
        self._shortcut.setAutoRepeat(False)
        self._shortcut.activated.connect(self._on_key_press)
        self._key_is_down = False
        self._event_source = self._install_release_filter()

    @classmethod
    def create(
        cls,
        owner: "MarkingMenu",
        shortcut_parent: Optional[QtWidgets.QWidget] = None,
    ) -> "ShortcutHandler":
        """Install or update the global shortcut binding."""
        if cls._instance:
            cls._instance.deleteLater()
        cls._instance = cls(owner, shortcut_parent)
        return cls._instance

    def _install_release_filter(self):
        app = QtWidgets.QApplication.instance()
        source = app if app else self._target
        if source:
            source.installEventFilter(self)
        return source

    def _resolve_target(self, explicit_parent):
        if isinstance(explicit_parent, QtWidgets.QWidget):
            return explicit_parent

        app = getattr(self._owner.sb, "app", None) or QtWidgets.QApplication.instance()
        if app:
            active = app.activeWindow()
            if isinstance(active, QtWidgets.QWidget):
                return active

            for widget in app.topLevelWidgets():
                if (
                    isinstance(widget, QtWidgets.QWidget)
                    and widget.objectName() == "MayaWindow"
                ):
                    return widget

        parent_widget = self._owner.parentWidget()
        if isinstance(parent_widget, QtWidgets.QWidget):
            return parent_widget

        logical_parent = self._owner.parent()
        if isinstance(logical_parent, QtWidgets.QWidget):
            return logical_parent

        return self._owner

    def _build_sequence(self, key_value):
        if key_value is None:
            self._owner.logger.warning(
                "key_show is invalid; defaulting to F12 shortcut"
            )
            key_value = QtCore.Qt.Key_F12
            self._owner.key_show = key_value

        if isinstance(key_value, QtGui.QKeySequence):
            return key_value

        return QtGui.QKeySequence(key_value)

    def eventFilter(self, obj, event):
        if (
            self._key_is_down
            and event.type() == QtCore.QEvent.KeyRelease
            and event.key() == self._owner.key_show
            and not event.isAutoRepeat()
        ):
            self._on_key_release()
            return True
        return super().eventFilter(obj, event)

    def _on_key_press(self):
        if self._key_is_down:
            return

        try:
            self._key_is_down = True
            self._owner._activation_key_held = True
            self._owner.key_show_press.emit()

            # Capture state once
            buttons = QtWidgets.QApplication.mouseButtons()

            # Track buttons held at activation for chord release detection
            self._owner._chord_buttons_at_press = self._owner._to_int(buttons)

            # Clean external UIs, passing current state to avoid race/re-query
            self._owner._dismiss_external_popups(buttons)

            # Build lookup string from current state
            lookup = self._owner._build_lookup_key(buttons)
            ui_target = self._owner._bindings.get(lookup)

            self._owner.logger.debug(
                f"_on_key_press: buttons={buttons}, lookup='{lookup}', ui_target={ui_target}"
            )

            self._owner.show(ui_target, force=True)

            # Handover
            active_btn = self._owner._get_priority_button(buttons)
            if active_btn != QtCore.Qt.NoButton:
                self._owner._transfer_mouse_control(active_btn, buttons)

            QtCore.QTimer.singleShot(0, self._owner.dim_other_windows)

        except Exception as e:
            self._owner.logger.error(f"Error in _on_key_press: {e}")
            # Ensure we reset state if something exploded
            self._key_is_down = False
            self._owner._activation_key_held = False

    def _on_key_release(self):
        if not self._key_is_down:
            return
        self._key_is_down = False
        self._owner._activation_key_held = False
        self._owner.key_show_release.emit()
        self._owner.hide()
        QtCore.QTimer.singleShot(0, self._owner.restore_other_windows)


class MarkingMenu(
    QtWidgets.QWidget, ptk.SingletonMixin, ptk.LoggingMixin, ptk.HelpMixin
):
    """MarkingMenu is a marking menu based on a QWidget.
    The various UI's are set by calling 'show' with the intended UI name string. ex. MarkingMenu().show('polygons')

    Parameters:
        parent (QWidget): The parent application's top level window instance. ie. the Maya main window.
        key_show (str): The name of the key which, when pressed, will trigger the display of the marking menu. This should be one of the key names defined in QtCore.Qt. Defaults to 'Key_F12'.
        ui_source (str): The directory path or the module where the UI files are located.
                If the given dir is not a full path, it will be treated as relative to the default path.
                If a module is given, the path to that module will be used.
        slot_source (str): The directory path where the slot classes are located or a class object.
                If the given dir is a string and not a full path, it will be treated as relative to the default path.
                If a module is given, the path to that module will be used.
        switchboard (Switchboard): An optional existing Switchboard instance to use.
        log_level (int): Determines the level of logging messages. Defaults to logging.WARNING. Accepts standard Python logging module levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.
    """

    left_mouse_double_click = QtCore.Signal()
    left_mouse_double_click_ctrl = QtCore.Signal()
    middle_mouse_double_click = QtCore.Signal()
    right_mouse_double_click = QtCore.Signal()
    right_mouse_double_click_ctrl = QtCore.Signal()
    key_show_press = QtCore.Signal()
    key_show_release = QtCore.Signal()

    # Default Handler Configuration
    HANDLERS = {"ui": UiHandler}

    _in_transition: bool = False
    _instances: dict = {}
    _submenu_cache: dict = {}
    _last_ui_history_check: QtWidgets.QWidget = None
    _pending_show_timer: QtCore.QTimer = None
    _shortcut_instance: Optional["ShortcutHandler"] = None
    _current_widget: Optional[QtWidgets.QWidget] = None

    # Chord release detection: tracks multi-button states for simultaneous release handling
    _chord_release_timer: QtCore.QTimer = None
    _chord_pending_widget: Optional[QtWidgets.QWidget] = None
    _chord_pending_buttons: Optional[QtCore.Qt.MouseButtons] = None
    _chord_pending_modifiers: Optional[QtCore.Qt.KeyboardModifiers] = None
    _chord_buttons_at_press: int = 0  # Buttons held when menu was activated

    def __init__(
        self,
        parent=None,
        ui_source=None,
        slot_source=None,
        widget_source=None,
        bindings: dict = None,
        handlers: dict = None,
        switchboard: Optional[Switchboard] = None,
        log_level: str = "DEBUG",
        **kwargs,
    ):
        """ """
        super().__init__(parent=parent)
        self.logger.setLevel(log_level)
        self._bindings = {}
        self._activation_key = None
        self._activation_key_held = False
        self._initial_bindings = bindings  # Store for after sb is set up

        # Merge class-level HANDLERS with instance-level handlers param
        self._handlers_config = getattr(self, "HANDLERS", {}).copy()
        if handlers:
            self._handlers_config.update(handlers)

        # ... (path resolution logic) ...

        # Resolve paths relative to the subclass module (e.g. TclMaya in tentacle)
        # instead of relative to this base class file in uitk.
        base_dir = 1
        module = sys.modules.get(self.__module__)
        if module and hasattr(module, "__file__"):
            base_dir = os.path.dirname(module.__file__)

        if switchboard:
            self.sb = switchboard
            # If sources are provided, register them to the existing switchboard
            if any([ui_source, slot_source, widget_source]):
                self.sb.register(
                    ui_location=ui_source,
                    slot_location=slot_source,
                    widget_location=widget_source,
                    base_dir=base_dir,
                )
        else:
            self.sb = Switchboard(
                self,
                ui_source=ui_source,
                slot_source=slot_source,
                widget_source=widget_source,
                handlers=self._handlers_config,
                base_dir=base_dir,
            )

        # Initialize the Handler Ecosystem
        self._setup_registry()

        # Initialize bindings: explicit arg > stored > empty
        if self._initial_bindings:
            # Only apply initial bindings if no bindings are currently stored (first run)
            if self.sb.configurable.marking_menu_bindings.get(None) is None:
                self.sb.configurable.marking_menu_bindings.set(self._initial_bindings)

        # Register callback to rebuild bindings when they change
        self.sb.configurable.marking_menu_bindings.changed.connect(self._build_bindings)
        self._build_bindings()

        self.child_event_filter = EventFactoryFilter(
            parent=self,
            forward_events_to=self,
            event_name_prefix="child_",
            event_types={
                "Enter",
                "Leave",
                "MouseMove",
                "MouseButtonPress",
                "MouseButtonRelease",
            },
        )

        self.overlay = Overlay(self, antialiasing=True)
        self.mouse_tracking = MouseTracking(self, auto_update=False)

        self.key_show = self._activation_key
        self.key_close = QtCore.Qt.Key_Escape
        self._windows_to_restore = set()

        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_NoMousePropagation, False)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.showFullScreen()

        # Initialize smooth transition timer
        self._pending_show_timer = QtCore.QTimer()
        self._pending_show_timer.setSingleShot(True)
        self._pending_show_timer.timeout.connect(self._perform_transition)
        self._setup_complete = True
        self._pending_ui = None

        # Initialize chord release detection timer
        self._chord_release_timer = QtCore.QTimer()
        self._chord_release_timer.setSingleShot(True)
        self._chord_release_timer.timeout.connect(self._chord_timeout_transition)
        self._chord_pending_widget = None
        self._chord_pending_buttons = None
        self._chord_pending_modifiers = None
        self._chord_buttons_at_press = 0

        # Auto-install shortcut if parent is provided
        if parent:
            ShortcutHandler.create(self, parent)

    def _setup_registry(self):
        """Initialize and register the application's handlers."""
        # 1. Register Self (The Marking Menu)
        self.sb.handlers.marking_menu = self

        # 2. Register Configured Handlers (e.g. UiHandler)
        # Uses _handlers_config which merges HANDLERS class attr + handlers param
        handlers = getattr(self, "_handlers_config", {}) or getattr(
            self, "HANDLERS", {}
        )

        for name, obj in handlers.items():
            # Skip if already registered (allows for manual dependency injection)
            if getattr(self.sb.handlers, name, None):
                continue

            # Instantiate if class, use directly if instance
            if isinstance(obj, type):
                if hasattr(obj, "instance"):
                    instance = obj.instance(switchboard=self.sb)
                else:
                    instance = obj(switchboard=self.sb)
                defaults = getattr(obj, "DEFAULTS", {})
            else:
                instance = obj
                defaults = getattr(instance, "DEFAULTS", {})

            self.sb.register_handler(name, instance, defaults)
            self.logger.debug(f"Registered Handler: {name} -> {instance}")

    @classmethod
    def instance(
        cls, switchboard: Optional[Switchboard] = None, **kwargs
    ) -> "MarkingMenu":
        kwargs.setdefault("switchboard", switchboard)
        kwargs["singleton_key"] = id(switchboard)
        return super().instance(**kwargs)

    @property
    def bindings(self) -> dict:
        """Get bindings from persistent storage."""
        return self.sb.configurable.marking_menu_bindings.get({})

    @bindings.setter
    def bindings(self, value: dict):
        """Set bindings (auto-persists and triggers rebuild via callback)."""
        self.sb.configurable.marking_menu_bindings.set(value)

    @property
    def ui_handler(self):
        """Accessor for the UI handler."""
        return self.sb.handlers.ui

    def get(self, name: str, **kwargs) -> QtWidgets.QWidget:
        """Get a UI widget by name.

        For standalone windows, delegates to the window manager.
        For stacked menus (startmenu/submenu), retrieves directly from Switchboard but ensures styling is applied.

        Parameters:
            name: The name of the UI to retrieve.
            **kwargs: Additional arguments.

        Returns:
            The UI widget.
        """
        # First check if it's a stacked menu
        ui = self.sb.get_ui(name)
        if ui and ui.has_tags(["startmenu", "submenu"]):
            # Ensure proper styling is applied (WindowManager owns the styling logic)
            self.ui_handler.apply_styles(ui)
            return ui

        # For standalone windows (or if not yet loaded), delegate to WindowManager
        ui = self.ui_handler.get(name, **kwargs)

        if ui and not getattr(ui, "is_initialized", False):
            self._init_ui(ui)

        return ui

    def _to_int(self, val) -> int:
        """Safely convert a Qt Enum or Flag to an integer."""
        if isinstance(val, int):
            return val
        try:
            return int(val)
        except (TypeError, ValueError):
            if hasattr(val, "value"):
                return val.value
            self.logger.warning(f"Could not convert {val} (type: {type(val)}) to int.")
            return 0

    def _normalize_binding_key(self, parts: list) -> str:
        """Normalize binding parts into a consistent string key.

        Sorts parts alphabetically to ensure order-independence:
        'LeftButton|Key_F12' == 'Key_F12|LeftButton'
        """
        return "|".join(sorted(p.strip() for p in parts if p.strip()))

    # Pre-built reverse lookup for key values -> names (built lazily on first use)
    _key_name_cache: dict = None

    def _get_key_name(self, key_value) -> Optional[str]:
        """Get the string name for a Qt key value using cached reverse lookup."""
        if MarkingMenu._key_name_cache is None:
            MarkingMenu._key_name_cache = {
                getattr(QtCore.Qt, name): name
                for name in dir(QtCore.Qt)
                if name.startswith("Key_")
            }
        return MarkingMenu._key_name_cache.get(key_value)

    def _build_lookup_key(self, buttons=None, modifiers=None, key=None) -> str:
        """Build a normalized lookup key from current input state.

        Parameters:
            buttons: Qt MouseButtons flags (e.g., LeftButton | RightButton)
            modifiers: Qt KeyboardModifiers flags
            key: Qt Key value (for non-activation key presses)

        Returns:
            Normalized string key for binding lookup
        """
        parts = []

        # Add activation key if held
        if self._activation_key_held and self._activation_key_str:
            parts.append(self._activation_key_str)

        # Add explicit key if provided (using cached lookup)
        if key is not None:
            key_name = self._get_key_name(key)
            if key_name:
                parts.append(key_name)

        # Add modifiers
        if modifiers:
            modifiers_int = self._to_int(modifiers)
            if modifiers_int & self._to_int(QtCore.Qt.ShiftModifier):
                parts.append("ShiftModifier")
            if modifiers_int & self._to_int(QtCore.Qt.ControlModifier):
                parts.append("ControlModifier")
            if modifiers_int & self._to_int(QtCore.Qt.AltModifier):
                parts.append("AltModifier")
            if modifiers_int & self._to_int(QtCore.Qt.MetaModifier):
                parts.append("MetaModifier")

        # Add buttons
        if buttons:
            buttons_int = self._to_int(buttons)
            if buttons_int & self._to_int(QtCore.Qt.LeftButton):
                parts.append("LeftButton")
            if buttons_int & self._to_int(QtCore.Qt.RightButton):
                parts.append("RightButton")
            if buttons_int & self._to_int(QtCore.Qt.MiddleButton):
                parts.append("MiddleButton")

        return self._normalize_binding_key(parts)

    def _build_bindings(self, _value=None):
        """Parse and organize the input bindings into a unified lookup dict.

        Args:
            _value: Ignored. Accepts callback arg from on_change.
        """
        self._bindings.clear()
        self._activation_key = None
        self._activation_key_str = None

        if not isinstance(self.bindings, dict):
            self.logger.warning("Bindings not configured correctly or invalid.")
            return

        for key, ui_in in self.bindings.items():
            if not isinstance(key, str):
                continue

            # Parse and normalize the binding string
            parts = key.split("|")
            normalized = self._normalize_binding_key(parts)

            # Extract activation key from any binding (first Key_* found)
            for part in parts:
                part = part.strip()
                if part.startswith("Key_") and self._activation_key_str is None:
                    self._activation_key_str = part
                    if hasattr(QtCore.Qt, part):
                        self._activation_key = self._to_int(getattr(QtCore.Qt, part))

            self._bindings[normalized] = ui_in
            self.logger.debug(f"Binding: '{key}' -> '{normalized}' -> '{ui_in}'")

        self.logger.debug(
            f"Activation key: {self._activation_key_str} ({self._activation_key})"
        )
        self.logger.debug(f"All bindings: {self._bindings}")

        if self._activation_key is None:
            if not self._bindings and self._initial_bindings:
                self.logger.warning("No bindings found. reverting to default bindings.")
                self.bindings = self._initial_bindings
                return

            self.logger.warning(
                "No activation key found in bindings. Include Key_* in at least one binding."
            )

    def addWidget(self, widget: QtWidgets.QWidget) -> None:
        """Add a widget to the MarkingMenu window.

        Parameters:
            widget (QWidget): The widget to add.
        """
        widget.setParent(self)

    def currentWidget(self) -> Optional[QtWidgets.QWidget]:
        """Get the currently active widget.

        Returns:
            QWidget: The currently active widget, or None if no widget is active.
        """
        return self._current_widget

    def setCurrentWidget(self, widget: QtWidgets.QWidget) -> None:
        """Set the current widget and position it at the cursor.

        Parameters:
            widget (QWidget): The widget to set as current.
        """
        if self._current_widget:
            self._current_widget.hide()

        self._current_widget = widget
        widget.show()
        widget.raise_()

        # Position the widget at the cursor
        cursor_pos = QtGui.QCursor.pos()
        local_pos = self.mapFromGlobal(cursor_pos)
        widget.move(local_pos - widget.rect().center())

        # Update mouse tracking cache for the new widget
        self.mouse_tracking.update_child_widgets()

    def setCurrentIndex(self, index: int) -> None:
        """Set the current widget index (compatibility method).

        Parameters:
            index (int): The index to set. If -1, hides the current widget.
        """
        if index == -1 and self._current_widget:
            self._current_widget.hide()
            self._current_widget = None

    def _init_ui(self, ui) -> None:
        """Initialize the given UI.

        Parameters:
            ui (QWidget): The UI to initialize.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: {type(ui)}, expected QWidget.")

        if ui.has_tags(["startmenu", "submenu"]):  # StackedWidget
            ui.style.set(theme="dark", style_class="translucentBgNoBorder")
            ui.resize(600, 600)
            ui.ensure_on_screen = False
            self.addWidget(ui)  # add the UI to the stackedLayout.
            self.add_child_event_filter(ui.widgets)
            ui.on_child_registered.connect(lambda w: self.add_child_event_filter(w))

        else:  # Standalone MainWindow
            # Parent normal windows to the MarkingMenu to ensure lifecycle coupling.
            # EXCEPTION: 'mayatk' windows (wrapped native menus) should remain parented to the host app.
            if not ui.has_tags(["mayatk", "maya"]):
                ui.setParent(self.parent(), QtCore.Qt.Window)

            # Delegate styling to the window manager
            self.ui_handler.apply_styles(ui)

            # Ensure lifecycle coupling
            self.key_show_release.connect(ui.hide)

            ui.default_slot_timeout = 360.0

    def _prepare_ui(self, ui) -> QtWidgets.QWidget:
        """Initialize and set the UI without showing it.

        Stacked menus (startmenu/submenu) are managed directly by MarkingMenu.
        Standalone windows are delegated to the window manager for styling.
        """
        if not isinstance(ui, (str, QtWidgets.QWidget)):
            raise ValueError(f"Invalid datatype for ui: {type(ui)}")

        # Resolve UI using the appropriate manager
        if isinstance(ui, str):
            # Use our get() which routes stacked vs standalone correctly
            found_ui = self.get(ui)
        else:
            found_ui = ui

        if not found_ui:
            raise ValueError(f"UI not found: {ui}")

        is_stacked = found_ui.has_tags(["startmenu", "submenu"])

        # Apply appropriate initialization based on UI type
        if not found_ui.is_initialized:
            self._init_ui(found_ui)

        if is_stacked:
            # Stacked menus: managed by MarkingMenu
            self.setCurrentWidget(found_ui)
        else:
            # Standalone windows: hide the marking menu overlay only if NOT parented to it
            if found_ui.parent() != self:
                self.hide()

        self.sb.current_ui = found_ui
        return found_ui

    def _debounce_transition(self, clear_pending: bool = False) -> None:
        """Cancel any pending transition to allow a new one to take precedence."""
        if self._pending_show_timer.isActive():
            self._pending_show_timer.stop()
        self._in_transition = False
        if clear_pending:
            self._pending_transition_ui = None
            self._pending_transition_widget = None

    def _set_submenu(self, ui, w) -> None:
        """Set the submenu for the given UI and widget."""
        self._debounce_transition()
        self._in_transition = True

        # Store transition data and schedule execution
        self._pending_transition_ui = ui
        self._pending_transition_widget = w
        self._pending_show_timer.start(8)  # ~120fps timing for very smooth transitions

    def _perform_transition(self) -> None:
        """Execute the scheduled submenu transition."""
        ui = getattr(self, "_pending_transition_ui", None)
        w = getattr(self, "_pending_transition_widget", None)

        # Clear pending references
        self._pending_transition_ui = None
        self._pending_transition_widget = None

        if not ui or not w:
            self._clear_transition_flag()
            return

        # VALIDATION: Abort if user has moved cursor away from the triggering widget
        try:
            cursor_pos = QtGui.QCursor.pos()
            w_rect = QtCore.QRect(w.mapToGlobal(QtCore.QPoint(0, 0)), w.size())
            # Allow a small margin of error (e.g. 5 pixels) for fast movements
            if not w_rect.adjusted(-5, -5, 5, 5).contains(cursor_pos):
                self._clear_transition_flag()
                return
        except RuntimeError:
            self._clear_transition_flag()
            return

        try:
            # Preserve overlay path order by adding to path first
            self.overlay.path.add(ui, w)

            # Batch UI initialization and preparation
            if not ui.is_initialized:
                self._init_ui(ui)
            self._prepare_ui(ui)

            # Position submenu smoothly without forcing immediate updates
            self._position_submenu_smooth(ui, w)

            # Switch active widget without repositioning (preserving smooth calculations)
            if self._current_widget and self._current_widget != ui:
                self._current_widget.hide()
            self._current_widget = ui
            ui.show()
            ui.raise_()
            self.sb.current_ui = ui

            # Optimize history check and overlay cloning
            self._handle_overlay_cloning(ui)

            # Update mouse tracking to include newly cloned widgets
            self.mouse_tracking.update_child_widgets()

        finally:
            # Clear transition flag after a brief delay to allow smooth completion
            QtCore.QTimer.singleShot(16, self._clear_transition_flag)  # ~60fps timing

    def _position_submenu_smooth(self, ui, w) -> None:
        """Handle submenu positioning with smooth visual transitions."""
        try:
            # Cache widget centers to avoid repeated calculations
            w_center = w.rect().center()
            p1 = w.mapToGlobal(w_center)

            w2 = self.sb.get_widget(w.objectName(), ui)
            if w2:
                w2.resize(w.size())
                w2_center = w2.rect().center()
                p2 = w2.mapToGlobal(w2_center)

                # Calculate new position
                diff = p1 - p2

                # Move to position smoothly - let Qt handle the timing naturally
                ui.move(ui.pos() + diff)

        except Exception as e:
            self.logger.warning(f"Submenu positioning failed: {e}")

    def _handle_overlay_cloning(self, ui) -> None:
        """Handle overlay cloning with optimized history checking."""
        if ui != self._last_ui_history_check:
            ui_history_slice = self.sb.ui_history(slice(0, -1), allow_duplicates=True)
            if ui not in ui_history_slice:
                self.overlay.clone_widgets_along_path(ui, self._return_to_startmenu)
            self._last_ui_history_check = ui

    def _delayed_show_ui(self) -> None:
        """Show the UI after smooth positioning delay."""
        if self._pending_ui:
            current_ui = self.sb.current_ui
            if current_ui == self._pending_ui:
                if self._current_widget and self._current_widget != current_ui:
                    self._current_widget.hide()
                self._current_widget = current_ui
                current_ui.show()
                current_ui.raise_()
            self._pending_ui = None

    def _clear_transition_flag(self):
        """Clear the transition flag to allow new transitions."""
        self._in_transition = False

    def _return_to_startmenu(self) -> None:
        """Return to the start menu by moving the overlay path back to the start position."""
        self._debounce_transition(clear_pending=True)

        start_pos = self.overlay.path.start_pos
        if not isinstance(start_pos, QtCore.QPoint):
            self.logger.warning("_return_to_startmenu called with no valid start_pos.")
            return

        startmenu = self.sb.ui_history(-1, inc="*#startmenu*")
        self._prepare_ui(startmenu)

        local_pos = self.mapFromGlobal(start_pos)
        startmenu.move(local_pos - startmenu.rect().center())

        # Switch active widget
        if self._current_widget and self._current_widget != startmenu:
            self._current_widget.hide()
        self._current_widget = startmenu
        startmenu.show()
        startmenu.raise_()
        self.sb.current_ui = startmenu

    # ---------------------------------------------------------------------------------------------
    #   Menu Navigation Helpers:

    def _dismiss_external_popups(self, buttons_mask=None) -> None:
        """Dismiss any active popup widgets that are not children of MarkingMenu."""
        if buttons_mask is None:
            buttons_mask = QtWidgets.QApplication.mouseButtons()

        # 1. Simulate Mouse Release to clear Maya's MM or other grabbers
        if buttons_mask != QtCore.Qt.NoButton:
            btn = self._get_priority_button(buttons_mask)
            if btn != QtCore.Qt.NoButton:
                # Find target
                target = QtWidgets.QWidget.mouseGrabber()
                if not target:
                    target = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())

                # Should not send to self or children if we are somehow active (unlikely at this stage)
                if target and not self.isAncestorOf(target):
                    local_pos = target.mapFromGlobal(QtGui.QCursor.pos())
                    # QMouseEvent(type, localPos, globalPos, button, buttons, modifiers)
                    event = QtGui.QMouseEvent(
                        QtCore.QEvent.MouseButtonRelease,
                        QtCore.QPointF(local_pos),
                        QtCore.QPointF(QtGui.QCursor.pos()),
                        btn,
                        QtCore.Qt.NoButton,
                        QtCore.Qt.KeyboardModifier(),
                    )
                    QtWidgets.QApplication.sendEvent(target, event)

        # 2. Close active popup chain
        popup = QtWidgets.QApplication.activePopupWidget()
        attempts = 0
        while popup is not None and attempts < 10:
            # Don't close our own popups
            if self.isAncestorOf(popup):
                break
            popup.hide()
            popup.close()
            popup = QtWidgets.QApplication.activePopupWidget()
            attempts += 1

        # 3. Additional sweep for any visible QMenu that might not be 'activePopupWidget'
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(widget, QtWidgets.QMenu) and widget.isVisible():
                if not self.isAncestorOf(widget):
                    widget.hide()
                    widget.close()

    def _get_priority_button(self, buttons_mask) -> QtCore.Qt.MouseButton:
        """Resolve the primary button from a combination of held buttons."""
        if buttons_mask & QtCore.Qt.RightButton:
            return QtCore.Qt.RightButton
        if buttons_mask & QtCore.Qt.MiddleButton:
            return QtCore.Qt.MiddleButton
        if buttons_mask & QtCore.Qt.LeftButton:
            return QtCore.Qt.LeftButton
        return QtCore.Qt.NoButton

    def _count_buttons(self, buttons_mask) -> int:
        """Count how many mouse buttons are in the given button mask."""
        count = 0
        buttons_int = self._to_int(buttons_mask)
        if buttons_int & self._to_int(QtCore.Qt.LeftButton):
            count += 1
        if buttons_int & self._to_int(QtCore.Qt.RightButton):
            count += 1
        if buttons_int & self._to_int(QtCore.Qt.MiddleButton):
            count += 1
        return count

    def _was_multi_button_press(self) -> bool:
        """Check if the menu was activated with multiple buttons held."""
        return self._count_buttons(self._chord_buttons_at_press) > 1

    def _cancel_chord_timer(self) -> None:
        """Cancel any pending chord detection."""
        if self._chord_release_timer.isActive():
            self._chord_release_timer.stop()
        self._chord_pending_widget = None
        self._chord_pending_buttons = None
        self._chord_pending_modifiers = None

    def _chord_timeout_transition(self) -> None:
        """Called when chord detection window expires - perform the menu transition."""
        self.logger.debug("Chord Release: Timer expired - performing transition")
        if self._chord_pending_buttons is not None:
            self._transition_to_state(
                self._chord_pending_buttons, self._chord_pending_modifiers
            )
        self._cancel_chord_timer()

    def _transition_to_state(self, buttons, modifiers=None) -> None:
        """Transition menu to state matching the given button/modifier combination."""
        lookup = self._build_lookup_key(buttons=buttons, modifiers=modifiers)
        next_ui = self._bindings.get(lookup)

        # Fallback: if modifiers are held but no specific binding exists, try without modifiers
        if not next_ui and modifiers and modifiers != QtCore.Qt.NoModifier:
            base_lookup = self._build_lookup_key(
                buttons=buttons, modifiers=QtCore.Qt.NoModifier
            )
            if base_lookup != lookup:
                next_ui = self._bindings.get(base_lookup)

        if next_ui:
            self.show(next_ui, force=True)

    def _handle_widget_action(self, widget) -> bool:
        """Execute action for a widget (button click or menu navigation).

        Returns:
            bool: True if action was executed, False if widget is non-interactive.
        """
        # Resolve container to actual child widget
        if hasattr(widget, "derived_type") and widget.derived_type == QtWidgets.QWidget:
            child = widget.childAt(widget.mapFromGlobal(QtGui.QCursor.pos()))
            if child:
                widget = child

        # Handle 'i' button clicks (menu/submenu launchers)
        if isinstance(widget, QtWidgets.QPushButton):
            if hasattr(widget, "base_name") and widget.base_name() == "i":
                menu = self._resolve_button_menu(widget)
                if menu:
                    is_standalone = not menu.has_tags(["startmenu", "submenu"])
                    self.show(menu, force=is_standalone)
                    return True

        # Emit clicked signal for standard buttons
        if hasattr(widget, "clicked"):
            ui = getattr(widget, "ui", None)
            base_name = getattr(widget, "base_name", lambda: None)()
            self.hide()
            if ui and ui.has_tags(["startmenu", "submenu"]) and base_name != "chk":
                widget.clicked.emit()
                return True

        return False

    def _transfer_mouse_control(self, button, buttons_mask) -> None:
        """Transfer mouse control to this widget by grabbing and synthesizing a press."""
        self.logger.debug(
            f"_transfer_mouse_control: button={button}, buttons_mask={buttons_mask}"
        )

        # Force grab mouse to ensure MarkingMenu receives subsequent move events
        self.grabMouse()

        local_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(local_pos),
            QtCore.QPointF(QtGui.QCursor.pos()),
            button,
            buttons_mask,
            QtCore.Qt.KeyboardModifier(),
        )
        QtWidgets.QApplication.sendEvent(self, event)

    # ---------------------------------------------------------------------------------------------
    #   Stacked Widget Event handling:

    def mousePressEvent(self, event) -> None:
        """Handle mouse press to switch menus based on full input state."""
        self.logger.debug(f"mousePressEvent: {event.buttons()} {event.modifiers()}")
        if self.sb.current_ui.has_tags(["startmenu", "submenu"]):
            lookup = self._build_lookup_key(
                buttons=event.buttons(), modifiers=event.modifiers()
            )
            ui_name = self._bindings.get(lookup)
            self.logger.debug(f"mousePressEvent lookup: {lookup} -> {ui_name}")

            if ui_name:
                self.overlay.start_gesture(event.globalPos())
                self.show(ui_name)

        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        """Handle key press for non-activation key bindings."""
        if event.key() == self._activation_key:
            super().keyPressEvent(event)
            return

        lookup = self._build_lookup_key(modifiers=event.modifiers(), key=event.key())
        ui_name = self._bindings.get(lookup)

        if ui_name:
            self.overlay.start_gesture(QtGui.QCursor.pos())
            self.show(ui_name)
        else:
            super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """ """
        if self.sb.current_ui.has_tags(["startmenu", "submenu"]):
            if event.button() == QtCore.Qt.LeftButton:
                if event.modifiers() == QtCore.Qt.ControlModifier:
                    self.left_mouse_double_click_ctrl.emit()
                else:
                    self.left_mouse_double_click.emit()

            elif event.button() == QtCore.Qt.MiddleButton:
                self.middle_mouse_double_click.emit()

            elif event.button() == QtCore.Qt.RightButton:
                if event.modifiers() == QtCore.Qt.ControlModifier:
                    self.right_mouse_double_click_ctrl.emit()
                else:
                    self.right_mouse_double_click.emit()

        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse release to transition menus based on remaining buttons."""
        current_ui = self.sb.current_ui

        # For stacked UIs, check if we're releasing over a widget
        if current_ui and current_ui.has_tags(["startmenu", "submenu"]):
            widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())

            if widget and widget is not self and widget is not current_ui:
                # When mouse is grabbed, child event filter is bypassed - handle clicks here
                if current_ui.isAncestorOf(widget):
                    if self._handle_widget_action(widget):
                        self.releaseMouse()
                        super().mouseReleaseEvent(event)
                        return
                    # If not handled (e.g. background/label), fall through to transition logic
                else:
                    # Widget is outside current_ui - don't transition
                    super().mouseReleaseEvent(event)
                    return

        # Transition to the appropriate UI based on remaining state
        remaining_buttons = event.buttons()
        chord_tolerance = 75 if self._was_multi_button_press() else 40

        if remaining_buttons == QtCore.Qt.NoButton:
            # All buttons released - transition immediately
            self._cancel_chord_timer()
            self._transition_to_state(remaining_buttons, event.modifiers())
        else:
            # Buttons remain - start chord timer to allow simultaneous release
            self._chord_pending_buttons = remaining_buttons
            self._chord_pending_modifiers = event.modifiers()
            self._chord_release_timer.start(chord_tolerance)

        super().mouseReleaseEvent(event)

    def _resolve_button_menu(self, widget) -> Optional[QtWidgets.QWidget]:
        """Resolve menu for an 'i' button, handling cache and tag cleanup."""
        menu_name = widget.accessibleName()
        if not menu_name:
            return None

        unknown_tags = self.sb.get_unknown_tags(
            menu_name, known_tags=["submenu", "startmenu"]
        )
        new_menu_name = self.sb.edit_tags(menu_name, remove=unknown_tags)

        menu = self._submenu_cache.get(new_menu_name)
        if menu is None:
            menu = self.sb.get_ui(new_menu_name)
            if menu:
                self._submenu_cache[new_menu_name] = menu

        if menu:
            self.sb.hide_unmatched_groupboxes(menu, unknown_tags)

        return menu

    def show(
        self, ui: Optional[str] = None, pos=None, force: bool = False, **kwargs
    ) -> QtWidgets.QWidget:
        """Central hub for showing any UI component.

        Args:
            ui (str, optional): The name of the UI to show.
            pos: Position argument passed to windows.
            force (bool): Force the UI to show.
            **kwargs: Additional arguments.

        Returns:
            QtWidgets.QWidget: The displayed widget.
        """
        # Cancel any pending chord transitions to avoid race conditions
        self._cancel_chord_timer()

        # If no UI is specified, show the Main Startup Menu (default behavior)
        if ui is None:
            ui = self._bindings.get(self._activation_key_str)

        # If still None, we can't show anything
        if ui is None:
            # If we are just toggling the overlay visibility
            if not self.isVisible():
                super().show()
            return self

        # Resolve the UI object
        found_ui = self.sb.get_ui(ui)
        if not found_ui:
            # Fallback: check submenu cache
            found_ui = self._submenu_cache.get(ui)

        if not found_ui:
            self.logger.error(f"UI '{ui}' not found.")
            return None

        # Initialize if needed
        if not found_ui.is_initialized:
            self._init_ui(found_ui)

        # Determine Type: Marking Menu or Standalone Window?
        is_marking_menu = found_ui.has_tags(["startmenu", "submenu"])

        if is_marking_menu:
            return self._show_marking_menu(found_ui, **kwargs)
        else:
            return self._show_window(found_ui, pos=pos, force=force, **kwargs)

    def _show_marking_menu(self, widget, **kwargs):
        """Internal handler for showing marking menus."""
        self.setCurrentWidget(widget)

        if widget.has_tags("startmenu"):
            self.overlay.start_gesture(QtGui.QCursor.pos())

        if self.isHidden():
            super().show()
            self.raise_()
            self.activateWindow()

        self.sb.current_ui = widget
        return widget

    def _show_window(self, widget, pos=None, force=False, **kwargs):
        """Internal handler for showing standalone windows."""
        if widget.parent() != self:
            self.hide()

        self.restore_other_windows()

        self.ui_handler.apply_styles(widget)
        self.ui_handler.show(widget, pos=pos or "cursor", force=force)
        return widget

    def hide(self):
        """Override hide to properly reset stacked widget state."""
        self._cancel_chord_timer()
        self._chord_buttons_at_press = 0

        if self.currentWidget():
            self.setCurrentIndex(-1)

        current_ui = self.sb.current_ui
        if current_ui:
            try:
                if current_ui.has_tags(["startmenu", "submenu"]):
                    header = current_ui.header
                    if header:
                        try:
                            header.reset_pin_state()
                        except AttributeError:
                            try:
                                if header.pinned:
                                    header.pinned = False
                                    if current_ui.prevent_hide:
                                        current_ui.prevent_hide = False
                            except AttributeError:
                                pass
            except AttributeError:
                pass

        super().hide()

        parent = self.parentWidget()
        if parent:
            parent.raise_()
            parent.activateWindow()

    def hideEvent(self, event):
        """ """
        self._clear_optimization_caches()
        super().hideEvent(event)

    def _clear_optimization_caches(self):
        """Clear optimization caches to prevent memory accumulation."""
        if self._pending_show_timer and self._pending_show_timer.isActive():
            self._pending_show_timer.stop()

        self._cancel_chord_timer()
        self._in_transition = False
        self._pending_ui = None

        if len(self._submenu_cache) > 50:
            self._submenu_cache.clear()
        self._last_ui_history_check = None

    def dim_other_windows(self) -> None:
        """Dim all visible windows except the current one."""
        if not self.isVisible():
            return

        for win in self.sb.visible_windows:
            if win is not self and not win.has_tags(["startmenu", "submenu"]):
                self._windows_to_restore.add(win)
                win.setWindowOpacity(0.15)
                win.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        if self._windows_to_restore:
            self.logger.debug(f"Dimming other windows: {self._windows_to_restore}")

    def restore_other_windows(self) -> None:
        """Restore all previously dimmed windows."""
        if not self._windows_to_restore:
            return

        for win in self._windows_to_restore:
            win.setWindowOpacity(1.0)
            win.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self._windows_to_restore.clear()
        self.logger.debug("Restored previously dimmed windows.")

    # ---------------------------------------------------------------------------------------------

    def add_child_event_filter(self, widgets) -> None:
        """Initialize child widgets with an event filter.

        Parameters:
            widgets (str/list): The widget(s) to initialize.
        """
        filtered_types = [
            QtWidgets.QMainWindow,
            QtWidgets.QWidget,
            QtWidgets.QAction,
            QtWidgets.QLabel,
            QtWidgets.QPushButton,
            QtWidgets.QCheckBox,
            QtWidgets.QRadioButton,
        ]

        for w in ptk.make_iterable(widgets):
            try:
                if (w.derived_type not in filtered_types) or (
                    not w.ui.has_tags(["startmenu", "submenu"])
                ):
                    continue
            except AttributeError:
                continue

            if w.derived_type in (
                QtWidgets.QPushButton,
                QtWidgets.QLabel,
                QtWidgets.QCheckBox,
                QtWidgets.QRadioButton,
            ):
                self.sb.center_widget(w, padding_x=25)
                if w.base_name() == "i":
                    w.ui.style.set(widget=w)

            if w.type == self.sb.registered_widgets.Region:
                w.visible_on_mouse_over = True

            self.child_event_filter.install(w)

    def child_enterEvent(self, w, event) -> None:
        """Handle the enter event for child widgets."""
        if w.derived_type == QtWidgets.QPushButton:
            if w.base_name() == "i":
                acc_name = w.accessibleName()
                if not acc_name:
                    return

                submenu_name = f"{acc_name}#submenu"
                if submenu_name != w.ui.objectName():
                    submenu = self._submenu_cache.get(submenu_name)
                    if submenu is None:
                        submenu = self.sb.get_ui(submenu_name)
                        if submenu:
                            self._submenu_cache[submenu_name] = submenu

                    if submenu:
                        self._set_submenu(submenu, w)

        if w.base_name() == "chk" and w.ui.has_tags("submenu") and self.isVisible():
            if isinstance(w, QtWidgets.QAbstractButton):
                w.toggle()

        super_event = getattr(super(type(w), w), "enterEvent", None)
        if callable(super_event):
            super_event(event)

    def child_leaveEvent(self, w, event) -> None:
        """Handle the leave event for child widgets."""
        if w.derived_type == QtWidgets.QPushButton:
            self._debounce_transition(clear_pending=True)

        super_event = getattr(super(type(w), w), "leaveEvent", None)
        if callable(super_event):
            super_event(event)

    def child_mouseButtonReleaseEvent(self, w, event) -> bool:
        """Handle mouse button release events on child widgets."""
        if not w.underMouse():
            w.mouseReleaseEvent(event)
            return False

        remaining_buttons = event.buttons()
        all_released = remaining_buttons == QtCore.Qt.NoButton

        # Chord release detected: all buttons released while timer was active
        if self._chord_release_timer.isActive() and all_released:
            pending = self._chord_pending_widget
            self._cancel_chord_timer()

            # Execute pending widget action, or transition to base state
            if pending and self._handle_widget_action(pending):
                return True

            self._transition_to_state(QtCore.Qt.NoButton, event.modifiers())
            return True

        # Timer still running and buttons still held - wait for more releases
        if self._chord_release_timer.isActive():
            self.logger.debug(
                f"Chord logic: Waiting for more releases on {w.objectName()}"
            )
            return True

        return False
