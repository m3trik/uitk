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
from ._resolver import parse_binding_keys, resolve_target_menu
from uitk.handlers.ui_handler import UiHandler
from uitk.widgets.mixins.shortcuts import GlobalShortcut
from uitk.compile import precompile_async
from uitk.loaders import CompiledLoader


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
    _shortcut_instance: Optional["GlobalShortcut"] = None
    _current_widget: Optional[QtWidgets.QWidget] = None

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
        suppress_default_on_reentry: bool = False,
        precompile: bool = False,
        **kwargs,
    ):
        """ """
        super().__init__(parent=parent)
        self.logger.setLevel(log_level)
        self._bindings = {}
        self._activation_key = None
        self._activation_key_held = False
        self._initial_bindings = bindings  # Store for after sb is set up
        self._default_bindings = bindings  # Public-facing copy of the original defaults
        self._standalone_suppress = (
            False  # Prevents reshow after standalone window opened
        )
        self._suppress_default_on_reentry = suppress_default_on_reentry
        self._non_default_shown = False
        self._pending_hide_widget = None

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

        # Optional background pre-compile of any stale/missing _ui.py files
        # so the first marking-menu activation doesn't pay per-UI uic
        # subprocess costs. Daemon thread; lazy ensure_compiled remains the
        # fallback if the user beats it to a particular UI.
        # Off by default to keep test environments clean (no daemon threads
        # leaking across MarkingMenu construction in test suites). Production
        # consumers (e.g. tentacle.tcl_maya) opt in with ``precompile=True``.
        # Gated on the active loader: only the CompiledLoader actually
        # consumes _ui.py artifacts, so under the (default) RuntimeLoader
        # there's nothing to precompile and the call would be wasted uic
        # work writing artifacts no one reads.
        if precompile and isinstance(self.sb._loader, CompiledLoader):
            ui_paths = [
                entry.filepath for entry in self.sb.registry.ui_registry.named_tuples
            ]
            if ui_paths:
                precompile_async(*ui_paths)

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

        # Auto-install shortcut if parent is provided
        if parent:
            if not self.key_show:
                self.logger.warning("key_show is invalid; defaulting to F12 shortcut")
                self.key_show = QtCore.Qt.Key_F12

            self._shortcut_instance = GlobalShortcut(
                self.key_show, parent, context=QtCore.Qt.ApplicationShortcut
            )
            self._shortcut_instance.pressed.connect(self._on_activation_press)
            self._shortcut_instance.released.connect(self._on_activation_release)

    def _on_activation_press(self):
        """Handle the global shortcut press event."""
        try:
            # If a standalone window was opened during this key-hold cycle,
            # ignore re-press until the key is genuinely released and pressed again.
            if self._standalone_suppress:
                return

            self._activation_key_held = True
            self._non_default_shown = False
            self.key_show_press.emit()

            buttons = QtWidgets.QApplication.mouseButtons()

            # Clean external UIs, passing current state to avoid race/re-query
            self._dismiss_external_popups(buttons)

            # Single source of truth: pick a menu from the current input state.
            self._sync_menu_to_state(
                buttons=self._to_int(buttons),
                modifiers=self._to_int(QtWidgets.QApplication.keyboardModifiers()),
            )

            # Hand over mouse control if a button is already held at activation.
            active_btn = self._get_priority_button(buttons)
            if active_btn != QtCore.Qt.NoButton:
                self._transfer_mouse_control(active_btn, buttons)

            QtCore.QTimer.singleShot(0, self.dim_other_windows)

        except Exception as e:
            self.logger.error(f"Error in _on_activation_press: {e}")
            self._activation_key_held = False

    def _sync_menu_to_state(self, *, buttons=None, modifiers=None, extra_key=None):
        """Single source of truth — make the visible menu match input state.

        Called from every event handler that can change the input state
        (activation press, mouse press, mouse release, key press). The
        resolver decides which UI matches; this method handles the rest:
        suppress-on-reentry, default-vs-non-default tracking, and avoiding
        no-op reshows.
        """
        if buttons is None:
            buttons = self._to_int(QtWidgets.QApplication.mouseButtons())
        if modifiers is None:
            modifiers = self._to_int(QtWidgets.QApplication.keyboardModifiers())

        target = resolve_target_menu(
            activation_held=self._activation_key_held,
            activation_key_str=self._activation_key_str,
            buttons=buttons,
            modifiers=modifiers,
            bindings=self._bindings,
            extra_key=extra_key,
        )

        self.logger.debug(
            f"_sync_menu_to_state: buttons={buttons:#x}, modifiers={modifiers:#x}, "
            f"extra_key={extra_key} -> target={target}"
        )

        if target is None:
            return

        default_name = self._bindings.get(self._activation_key_str)

        # Suppress bouncing back to default once a non-default menu was shown.
        # The hide is deferred — synchronously hiding the current widget during
        # mouseReleaseEvent can break delivery of the next mouseButtonPress.
        # _show_marking_menu cancels the pending hide if a new press lands first.
        if (
            self._suppress_default_on_reentry
            and self._non_default_shown
            and target == default_name
        ):
            if self._current_widget and self._current_widget.isVisible():
                self._pending_hide_widget = self._current_widget
                QtCore.QTimer.singleShot(0, self._do_pending_hide)
            return

        if target != default_name:
            self._non_default_shown = True

        # Skip re-showing the same UI. Use active_ui (no-warn peek) — None
        # is a valid state on first activation; current_ui would warn.
        current = self.sb.active_ui
        if (
            current is self._current_widget
            and current is not None
            and current.objectName() == target
            and current.isVisible()
        ):
            return

        self.show(target, force=True)

    def _on_activation_release(self):
        """Handle the global shortcut release event."""
        self._activation_key_held = False
        self._standalone_suppress = False
        self._non_default_shown = False

        self.logger.debug("_on_activation_release: Emitting key_show_release signal")
        self.key_show_release.emit()

        # Hide any visible standalone windows that aren't pinned.
        for win in list(self.sb.visible_windows):
            if win is not self and not win.has_tags(["startmenu", "submenu"]):
                if hasattr(win, "request_hide"):
                    win.request_hide()

        self.hide()
        QtCore.QTimer.singleShot(0, self.restore_other_windows)

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
    def default_bindings(self) -> dict:
        """The original bindings passed at construction time."""
        return dict(self._default_bindings or {})

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

    def _build_bindings(self, _value=None):
        """Parse and organize the input bindings into a unified lookup dict.

        Args:
            _value: Ignored. Accepts callback arg from on_change.
        """
        if not isinstance(self.bindings, dict):
            self.logger.warning("Bindings not configured correctly or invalid.")
            self._bindings = {}
            self._activation_key = None
            self._activation_key_str = None
            return

        normalized, activation_key_str = parse_binding_keys(self.bindings)
        self._bindings = normalized
        self._activation_key_str = activation_key_str

        if activation_key_str and hasattr(QtCore.Qt, activation_key_str):
            self._activation_key = self._to_int(getattr(QtCore.Qt, activation_key_str))
        else:
            self._activation_key = None

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

        # QMainWindow may collapse to 0x0 when reparented as a child widget;
        # use central widget size as a fallback.
        if widget.width() <= 0 or widget.height() <= 0:
            cw = widget.centralWidget() if hasattr(widget, "centralWidget") else None
            if cw and (cw.width() > 0 or cw.height() > 0):
                widget.resize(cw.size())
            else:
                widget.resize(600, 600)

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

        ui_name = ui.objectName()
        self.logger.debug(
            f"[{ui_name}] _init_ui called, tags={getattr(ui, 'tags', None)}, "
            f"has_header={hasattr(ui, 'header')}"
        )

        if ui.has_tags(["startmenu", "submenu"]):  # StackedWidget
            ui.style.set(theme="dark", style_class="translucentBgNoBorder")
            ui.ensure_on_screen = False
            # Stacked menus are transient — they hide on every transition
            # and reshow on the next gesture. Persisting their geometry via
            # MainWindow's save-on-hide / restore-on-show creates a feedback
            # loop: a transient size saved during a hide gets restored on
            # the next show, which is then re-saved, locking the menu to a
            # tiny restored size (visible as the upper-section-cropped bug).
            # Disable the persistence and discard any previously-saved value.
            ui.restore_window_size = False
            try:
                ui.settings.clear("window_geometry")
            except Exception:
                pass
            self.addWidget(ui)  # add the UI to the stackedLayout.
            # Resize after addWidget (setParent can reset geometry)
            w = max(ui.width(), 600)
            h = max(ui.height(), 600)
            ui.resize(w, h)
            self.add_child_event_filter(ui.widgets)
            ui.on_child_registered.connect(lambda w: self.add_child_event_filter(w))
            # Stacked menus: No explicit lifecycle setup needed (they hide with parent)

        else:  # Standalone MainWindow
            ui.setParent(self.parent(), QtCore.Qt.Window)

            # Delegate all window setup to UiHandler (styling + lifecycle)
            self.ui_handler.apply_styles(ui)
            self.ui_handler.setup_lifecycle(ui, hide_signal=self.key_show_release)

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
            current_ui = self.sb.active_ui
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

    def _is_logical_descendant(self, ancestor_widget, widget) -> bool:
        """Check if *widget* is a logical descendant of *ancestor_widget*.

        Top-level ToolTip windows (e.g. ExpandableList sublists) set a
        ``_logical_ancestor`` attribute pointing to the root widget that
        lives inside the normal widget hierarchy.  This method walks up
        the widget's parent chain looking for that marker.

        Parameters:
            ancestor_widget: The prospective ancestor (e.g. ``current_ui``).
            widget: The widget found under the cursor.

        Returns:
            bool: True if *widget* (or one of its Qt parents) has a
            ``_logical_ancestor`` that *ancestor_widget* is an ancestor of.
        """
        w = widget
        while w is not None:
            logical_root = getattr(w, "_logical_ancestor", None)
            if logical_root is not None:
                return (
                    ancestor_widget.isAncestorOf(logical_root)
                    or logical_root is ancestor_widget
                )
            w = w.parent()
        return False

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
            if ui and ui.has_tags(["startmenu", "submenu"]) and base_name != "chk":
                self.hide()
                widget.clicked.emit()
                return True
            else:
                self.logger.debug(
                    f"[_handle_widget_action] Click skipped for "
                    f"'{widget.objectName()}': ui={ui}, "
                    f"has_tags={ui.has_tags(['startmenu', 'submenu']) if ui else 'N/A'}, "
                    f"base_name='{base_name}'"
                )

        # Handle ExpandableList items (widgets with item_text set by ExpandableList)
        if hasattr(widget, "item_text"):
            parent = widget.parent()
            while parent:
                if hasattr(parent, "on_item_interacted"):
                    self.hide()
                    parent.on_item_interacted.emit(widget)
                    return True
                parent = parent.parent()

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
        """Handle mouse press: route through the central state-sync."""
        self.logger.debug(f"mousePressEvent: {event.buttons()} {event.modifiers()}")

        # Cancel any pending suppress-hide so we don't yank the menu away
        # right after showing it.
        self._pending_hide_widget = None

        # Defensive: re-establish mouse grab if it was lost (e.g. after a
        # deferred child-hide caused the host app to claim focus).
        if self._activation_key_held and self.mouseGrabber() is not self:
            self.grabMouse()

        current_ui = self.sb.active_ui
        if current_ui and current_ui.has_tags(["startmenu", "submenu"]):
            self.overlay.start_gesture(event.globalPos())

        self._sync_menu_to_state(
            buttons=self._to_int(event.buttons()),
            modifiers=self._to_int(event.modifiers()),
        )
        event.accept()

    def keyPressEvent(self, event) -> None:
        """Handle key press for non-activation key bindings."""
        if event.key() == self._activation_key:
            super().keyPressEvent(event)
            return

        key_name = self._get_key_name(event.key())
        if key_name:
            target = resolve_target_menu(
                activation_held=self._activation_key_held,
                activation_key_str=self._activation_key_str,
                buttons=self._to_int(QtWidgets.QApplication.mouseButtons()),
                modifiers=self._to_int(event.modifiers()),
                bindings=self._bindings,
                extra_key=key_name,
            )
            default_name = self._bindings.get(self._activation_key_str)
            if target and target != default_name:
                self.overlay.start_gesture(QtGui.QCursor.pos())
                self.show(target, force=True)
                return

        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """ """
        current_ui = self.sb.active_ui
        if current_ui and current_ui.has_tags(["startmenu", "submenu"]):
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
        """Handle mouse release: dispatch click action or sync menu state."""
        current_ui = self.sb.active_ui

        if current_ui and current_ui.has_tags(["startmenu", "submenu"]):
            widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())

            self.logger.debug(
                f"[mouseReleaseEvent] current_ui={current_ui.objectName()}, "
                f"widgetAt={widget.objectName() if widget and hasattr(widget, 'objectName') else widget}, "
                f"grabber={self.mouseGrabber() is self}"
            )

            if widget and widget is not self and widget is not current_ui:
                if current_ui.isAncestorOf(widget) or self._is_logical_descendant(
                    current_ui, widget
                ):
                    if self._handle_widget_action(widget):
                        self.releaseMouse()
                        event.accept()
                        return
                    # Non-interactive widget — fall through to normal sync.
                else:
                    # Cursor over an unrelated widget — leave menu state alone.
                    event.accept()
                    return

        self._sync_menu_to_state(
            buttons=self._to_int(event.buttons()),
            modifiers=self._to_int(event.modifiers()),
        )
        event.accept()

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

    def _do_pending_hide(self) -> None:
        """Execute the deferred hide scheduled by suppress_default_on_reentry.

        Skipped when ``_show_marking_menu`` (or another sync) cleared the
        pending widget — i.e. the user pressed a new button before the
        timer fired and we shouldn't yank the new menu away.

        After hiding, re-establishes the mouse grab and window focus.
        Hiding the child widget can cause Maya / the OS to transfer focus
        to the parent application, which routes the next mouse press to
        the wrong window — symptoms: "press a button, nothing shows;
        press again, then it shows".
        """
        widget = self._pending_hide_widget
        self._pending_hide_widget = None
        if widget is not None and widget is self._current_widget and widget.isVisible():
            widget.hide()
            self._current_widget = None
            if self.isVisible() and self._activation_key_held:
                self.raise_()
                self.activateWindow()
                if self.mouseGrabber() is not self:
                    self.grabMouse()

    def _show_marking_menu(self, widget, **kwargs):
        """Internal handler for showing marking menus."""
        # Cancel any pending suppress-hide so we don't pull the new menu away.
        self._pending_hide_widget = None
        self.setCurrentWidget(widget)

        if widget.has_tags("startmenu"):
            self.overlay.start_gesture(QtGui.QCursor.pos())

        if (
            self._suppress_default_on_reentry
            and self._activation_key_held
            and self._activation_key_str is not None
            and widget.objectName() != self._bindings.get(self._activation_key_str)
        ):
            self._non_default_shown = True

        if self.isHidden():
            self.showFullScreen()

        self.raise_()
        self.activateWindow()

        self.sb.current_ui = widget
        return widget

    def _show_window(self, widget, pos=None, force=False, **kwargs):
        """Internal handler for showing standalone windows."""
        # Ensure the widget won't be hidden alongside the MarkingMenu.
        if widget.parent() is self:
            widget.setParent(self.parent(), QtCore.Qt.Window)

        # When launched from another visible standalone window, reparent the
        # target to it so Qt window-group management keeps the new window
        # above the launching window.  Without this they are siblings and the
        # OS can freely reorder them.
        invoker = self.sb.active_ui
        if (
            invoker is not None
            and invoker is not self
            and invoker is not widget
            and invoker.isVisible()
            and not invoker.has_tags(["startmenu", "submenu"])
            and widget.parent() is not invoker
        ):
            widget.setParent(invoker, QtCore.Qt.Window)

        # Clear activation state so _sync_menu_to_state won't resolve to
        # an activation-keyed binding (e.g. "Key_F12" → startmenu).
        self._activation_key_held = False
        self._standalone_suppress = True
        self._transitioning_to_window = True
        self.hide()
        self._transitioning_to_window = False

        self.restore_other_windows()

        self.ui_handler.apply_styles(widget)
        self.ui_handler.show(widget, pos=pos or "cursor", force=force)

        # Deferred raise: when super().hide() fires on the MarkingMenu, the
        # OS implicitly gives focus back to the parent (sequencer) before
        # ui_handler.show() can activate the target.  A zero-delay timer runs
        # after all pending events settle, ensuring the target ends up on top.
        QtCore.QTimer.singleShot(0, lambda w=widget: (w.raise_(), w.activateWindow()))

        return widget

    def hide(self):
        """Override hide to properly reset stacked widget state."""
        self.logger.debug("MarkingMenu.hide() called")

        if self.currentWidget():
            self.setCurrentIndex(-1)

        current_ui = self.sb.active_ui
        if current_ui:
            self.logger.debug(
                f"MarkingMenu.hide(): current_ui={current_ui.objectName()}, "
                f"tags={getattr(current_ui, 'tags', None)}"
            )
            try:
                if current_ui.has_tags(["startmenu", "submenu"]):
                    header = current_ui.header
                    if header:
                        try:
                            header.reset_pin_state()
                        except AttributeError:
                            # Fallback for widgets without reset_pin_state
                            if getattr(header, "pinned", False):
                                header.pinned = False
                            # Menu uses prevent_hide; MainWindow uses set_pinned
                            if hasattr(current_ui, "set_pinned"):
                                current_ui.set_pinned(False)
                            elif hasattr(current_ui, "prevent_hide"):
                                current_ui.prevent_hide = False
            except AttributeError:
                pass

        # CRITICAL: Release mouse grab before hiding to prevent zombie grabs.
        # If the MarkingMenu grabbed the mouse (see _transfer_mouse_control) and we
        # hide without releasing, the OS may leave mouse input in a broken state.
        if self.mouseGrabber() is self:
            self.releaseMouse()

        super().hide()

        parent = self.parentWidget()
        if parent and not getattr(self, "_transitioning_to_window", False):
            # Order matters: raise_() first brings window to front, then activateWindow()
            # gives it focus. Reversing this can cause the parent to go behind other apps.
            # Skip when transitioning to a standalone window — the target window
            # will raise itself via ui_handler.show(), and raising the parent here
            # would steal z-order from it.
            parent.raise_()
            parent.activateWindow()

    def hideEvent(self, event):
        """Clean up on hide - ensures mouse grab is released even if hide() was bypassed."""
        # Safety net: release mouse grab if we still have it
        if self.mouseGrabber() is self:
            self.releaseMouse()
        self._clear_optimization_caches()
        super().hideEvent(event)

    def _clear_optimization_caches(self):
        """Clear optimization caches to prevent memory accumulation."""
        if self._pending_show_timer and self._pending_show_timer.isActive():
            self._pending_show_timer.stop()

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
        """Forward release events to the child's normal handler.

        With the mouse grabbed by MarkingMenu, releases come through
        ``mouseReleaseEvent`` directly. This filter only fires when the
        grab is bypassed (e.g. cursor over a non-grab-target child),
        in which case we just delegate to the child.
        """
        if not w.underMouse():
            w.mouseReleaseEvent(event)
        return False
