# !/usr/bin/python
# coding=utf-8
import sys
import os
import tempfile
from typing import Optional
from qtpy import QtCore, QtWidgets, QtGui
import pythontk as ptk

# From this package:
from uitk.switchboard import Switchboard
from uitk.events import EventFactoryFilter, MouseTracking
from .overlay import Overlay
from ._resolver import parse_binding_keys, resolve_target_menu, count_buttons
from uitk.handlers.ui_handler import UiHandler
from uitk.widgets.menuButton import MenuButton
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
    # Single-shot latch: a chord release arrives as TWO release events a few ms
    # apart (one per button). Without coalescing, each one dispatches — the
    # trailing release fires a SECOND action (e.g. clicks a leaf of a submenu a
    # nav-button release just opened). v1.0.66's removed _chord_release_timer
    # coalesced the pair into one decision; this latch restores "one dispatch per
    # gesture". Set when an action fires, re-armed on the next press / activation.
    _action_dispatched: bool = False

    # Chord-release tolerance — governs NAVIGATION only, never item selection.
    # A release OVER AN OWNED ITEM always dispatches the click immediately on the
    # first release (see mouseReleaseEvent); this timer is consulted only for a
    # release over EMPTY overlay (the "switch menus by releasing a button"
    # gesture). There, a real-world both-buttons release is imperfect — the two
    # buttons lift a few ms apart, so the first release arrives with the other
    # still held (a "partial"). Acting on that partial immediately would flicker
    # the menu to the one-button menu before the second button lifts. v1.0.66
    # deferred it by a tolerance window (this timer): if the other button also
    # releases within the window it was a both-buttons release (settle on the
    # final all-up release); if it is still held when the window expires it was
    # an intentional switch (→ navigate to the remaining-button menu). Putting
    # this deferral AHEAD of the owned-item dispatch was the regression — it
    # navigated the menu away before the click could land. Tunable; 75 ms matches
    # the proven v1.0.66 value.
    CHORD_RELEASE_TOLERANCE_MS: int = 75
    _chord_release_timer: Optional[QtCore.QTimer] = None
    _chord_pending_buttons: int = 0
    _chord_pending_modifiers: int = 0

    # Smooth submenu-transition state: set by _set_submenu, consumed by the
    # _pending_show_timer's _perform_transition, cleared by _debounce_transition.
    _pending_transition_ui: Optional[QtWidgets.QWidget] = None
    _pending_transition_widget: Optional[QtWidgets.QWidget] = None
    _transitioning_to_window: bool = False
    # Explicit on/off for the input-handoff diagnostics (see enable_input_logging).
    # Gates capture that touches Qt hit-testing, so it never runs on the hot event
    # path unless a repro is actively being recorded. NOT the log level: the class
    # logger sits at NOTSET, which makes isEnabledFor(DEBUG) unreliable as a gate.
    _input_logging_on: bool = False

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
        context_tags=None,
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
            if context_tags:
                self.sb.context_tags = set(context_tags)
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
                context_tags=context_tags,
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

        # Initialize bindings: explicit arg > stored > empty. The store is
        # namespaced per host context (see _bindings_store) so Maya/Blender don't
        # clobber each other's chords in the shared QSettings backend.
        if self._initial_bindings:
            to_persist = self._reconcile_bindings(
                self._initial_bindings,
                self._bindings_store.get(None),
            )
            if to_persist is not None:
                self._bindings_store.set(to_persist)

        # Register callback to rebuild bindings when they change
        self._bindings_store.changed.connect(self._build_bindings)
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
        self.mouse_tracking = MouseTracking(
            self, auto_update=False, buttons_provider=self._host_mouse_buttons
        )
        # Opt-in input-handoff diagnostics: set UITK_INPUT_LOG=<path> before
        # launch to tee DEBUG grab/launch/release records (this menu + its
        # MouseTracking) to a file. Zero cost unless the env var is set.
        if os.environ.get("UITK_INPUT_LOG"):
            try:
                self.enable_input_logging(os.environ["UITK_INPUT_LOG"])
            except Exception as _e:  # never let diagnostics break construction
                self.logger.warning(f"UITK_INPUT_LOG enable failed: {_e}")

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

    def _on_activation_press(self, buttons=None):
        """Handle the global shortcut press event.

        Parameters:
            buttons: Optional pre-resolved Qt mouse-button mask. Hosts whose
                native event loop owns the mouse (e.g. Blender's GHOST) pass the
                physically held buttons here — ``QApplication.mouseButtons()``
                only reflects events Qt itself has seen. ``None`` (the Qt
                shortcut path) falls back to the Qt query.
        """
        if buttons is None:
            buttons = QtWidgets.QApplication.mouseButtons()
        try:
            # If a standalone window was opened during this key-hold cycle,
            # ignore re-press until the key is genuinely released and pressed again.
            if self._standalone_suppress:
                return

            self._activation_key_held = True
            self._non_default_shown = False
            self._action_dispatched = False  # fresh marking-menu session
            self.key_show_press.emit()

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
        # The resolved navigation target. When a release falls through to here
        # instead of dispatching a click, this is the menu the gesture switches
        # to — i.e. the "menu stays open and shifts" the user sees.
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

        # The re-show — this is the visible "shift" when a release reaches here.
        self.show(target, force=True)

    def _on_activation_release(self):
        """Handle the global shortcut release event."""
        if self._input_logging_on:
            self.logger.debug(
                f"[handoff] _on_activation_release (the 'tap key_show again' fix path) "
                f"| {self._input_state()}"
            )
        self._activation_key_held = False
        self._standalone_suppress = False
        self._non_default_shown = False
        # The gesture is over — drop any pending chord-release decision so a
        # deferred partial can't fire a menu switch after the key is released.
        self._cancel_chord_release_timer()

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

    @staticmethod
    def _reconcile_bindings(defaults: dict, stored: Optional[dict]) -> Optional[dict]:
        """Decide what binding dict (if any) to persist at construction.

        Returns the dict to write to persistent storage, or ``None`` when no
        write is needed:

        * ``stored is None`` (first run) → seed with ``defaults``.
        * ``stored`` present → ``{**defaults, **stored}`` so newly-shipped default
          keys are added while the user's customizations of existing keys win on
          overlap. Returns ``None`` when that merge equals ``stored`` (already
          current — avoid a redundant write + ``changed`` signal).

        Without the forward-merge a user who ran an older version keeps a frozen
        binding set and never receives new defaults — the symptom that a newly
        added chord (e.g. ``F12+L+R``) silently falls through to a sibling menu
        because its binding was never present in the resolver's lookup.

        A ``None`` or non-dict ``stored`` (unset, or corrupt/legacy QSettings) is
        treated as first run and re-seeded with ``defaults`` — never spread into
        a dict literal, which would raise at construction.
        """
        if not defaults:
            return None
        if not isinstance(stored, dict):
            return dict(defaults)
        merged = {**defaults, **stored}
        return merged if merged != stored else None

    @staticmethod
    def _binding_store_key(context_tags) -> str:
        """QSettings key for persisted bindings, namespaced by host context.

        The QSettings backend is shared across processes by ``(org, app)``, so a
        Maya and a Blender session would otherwise read/write the SAME
        ``marking_menu_bindings`` key — and their chords collide: ``F12+L+R`` maps
        to ``maya#startmenu`` in one host and ``blender#startmenu`` in the other,
        so whichever persisted last hijacks the key and the other host's chord
        resolves to a UI it doesn't even have. Namespacing by ``context_tags``
        (``..._maya`` / ``..._blender``) keeps each DCC's binding set independent;
        an empty/absent context (standalone) keeps the legacy un-suffixed key.
        """
        tags = sorted(context_tags or ())
        return "marking_menu_bindings" + ("_" + "_".join(tags) if tags else "")

    @property
    def _bindings_store(self):
        """The persisted-bindings ``SettingItem`` for this menu's host context.

        See :meth:`_binding_store_key` for why the key is host-namespaced. The
        pre-namespace key is intentionally left orphaned — re-seeding each host
        from its own current defaults is the correct recovery from the prior
        shared-key collision (so a Blender session no longer inherits Maya's
        ``F12+L+R`` target, or vice versa).
        """
        key = self._binding_store_key(getattr(self.sb, "context_tags", None))
        return getattr(self.sb.configurable, key)

    @property
    def default_bindings(self) -> dict:
        """The original bindings passed at construction time."""
        return dict(self._default_bindings or {})

    @property
    def bindings(self) -> dict:
        """Get bindings from persistent storage."""
        return self._bindings_store.get({})

    @bindings.setter
    def bindings(self, value: dict):
        """Set bindings (auto-persists and triggers rebuild via callback)."""
        self._bindings_store.set(value)

    def on_bindings_changed(self, callback) -> None:
        """Subscribe to binding changes on this menu's persistent store.

        Public hook for the binding editor (tentacle's settings panel): it must
        listen on — and write to — the SAME host-namespaced store the menu reads
        (see :meth:`_binding_store_key`), or its combos desync from the live menu.
        Routing through ``bindings`` / this hook keeps that storage key an
        internal detail rather than something every editor reimplements.
        """
        self._bindings_store.changed.connect(callback)

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

    def setCurrentWidget(
        self,
        widget: QtWidgets.QWidget,
        *,
        anchor: Optional[QtCore.QPoint] = None,
    ) -> None:
        """Set the current widget and position its center at the given anchor.

        Parameters:
            widget (QWidget): The widget to set as current.
            anchor (QPoint, optional): Global position to align widget's
                center to. Defaults to the current cursor position.
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

        if anchor is None:
            anchor = QtGui.QCursor.pos()
        # Center the widget on the anchor. Marking-menu navigation windows
        # (startmenu/submenu) MUST keep their center pinned to the gesture
        # origin: the directional flick that drives the menu is measured
        # relative to that point, so an on-screen clamp that nudges the menu
        # away from the cursor desyncs the gesture and "breaks the overlay
        # starting position". Those windows opt out via ensure_on_screen=False
        # (set in _init_ui) — and are the only widgets that reach this method
        # today, so in practice the clamp below is skipped. It is kept (not
        # deleted) and gated on the same ensure_on_screen flag MainWindow's
        # _ensure_on_screen honors, so setCurrentWidget stays a correct
        # positioning primitive for any opted-in widget, guarding the case
        # where centering near a screen/monitor edge would spill it off the
        # display.
        global_top_left = anchor - widget.rect().center()
        if getattr(widget, "ensure_on_screen", True):
            screen = QtWidgets.QApplication.screenAt(
                anchor
            ) or QtWidgets.QApplication.primaryScreen()
            if screen is not None:
                ag = screen.availableGeometry()
                # max(ag.left(), ...) guards the degenerate case of a widget
                # wider or taller than the screen (clamp to the top-left corner).
                x = min(global_top_left.x(), ag.right() - widget.width() + 1)
                x = max(ag.left(), x)
                y = min(global_top_left.y(), ag.bottom() - widget.height() + 1)
                y = max(ag.top(), y)
                global_top_left = QtCore.QPoint(x, y)
        widget.move(self.mapFromGlobal(global_top_left))

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

            # No automatic slot timeout — every slot used to be wrapped in
            # ExecutionMonitor (thread spawn + Esc-cancel listener) which
            # paid that cost for every UI interaction even though the vast
            # majority of slots finish in milliseconds. Heavy operations
            # now opt in explicitly with the ``@Cancelable(timeout=N)``
            # decorator on the slot method, or set ``widget.slot_timeout``
            # at runtime.

    def _prepare_ui(self, ui, *, anchor=None) -> QtWidgets.QWidget:
        """Initialize and set the UI without showing it.

        Stacked menus (startmenu/submenu) are managed directly by MarkingMenu.
        Standalone windows are delegated to the window manager for styling.

        Parameters:
            anchor (QPoint, optional): Global position to align a stacked
                widget's center to. ``None`` defers to ``setCurrentWidget``'s
                default (current cursor).
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
            self.setCurrentWidget(found_ui, anchor=anchor)
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
        ui = self._pending_transition_ui
        w = self._pending_transition_widget

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
            # Preserve overlay path order by adding to path first. ``add``'s
            # return value is the single source of truth for "where was the
            # trigger widget when the user crossed it" — every downstream
            # consumer (smooth positioning, clone placement) reads THIS
            # value rather than re-querying ``w.mapToGlobal`` later, so any
            # intermediate widget-state change (layout-on-hide, style
            # reapply, etc.) can't silently drift the menu out from under
            # the cursor. ``None`` means add was skipped (widget invisible
            # or missing) — smooth positioning falls back to a live read.
            anchor_global = self.overlay.path.add(ui, w)

            # Batch UI initialization and preparation
            if not ui.is_initialized:
                self._init_ui(ui)
            self._prepare_ui(ui)

            # Position submenu smoothly without forcing immediate updates.
            # Pass the path-saved anchor so smooth positioning uses the
            # single source of truth, not a stale re-read of ``w``.
            self._position_submenu_smooth(ui, w, anchor_global=anchor_global)

            # Switch active widget without repositioning (preserving smooth calculations)
            if self._current_widget and self._current_widget != ui:
                self._current_widget.hide()
            self._current_widget = ui
            ui.show()
            ui.raise_()
            self.sb.current_ui = ui
            # Hover-nav committed: this submenu is now current_ui going into the
            # release.

            # Optimize history check and overlay cloning
            self._handle_overlay_cloning(ui)

            # Update mouse tracking to include newly cloned widgets
            self.mouse_tracking.update_child_widgets()

        finally:
            # Clear transition flag after a brief delay to allow smooth completion
            QtCore.QTimer.singleShot(16, self._clear_transition_flag)  # ~60fps timing

    def _position_submenu_smooth(self, ui, w, *, anchor_global=None) -> None:
        """Align ui so a same-named widget lands at the trigger's screen position.

        ``anchor_global`` is the path-captured global center of the trigger
        widget — the single source of truth for *where the cursor crossed
        the button*. The caller threads this value through from ``path.add``
        so positioning is independent of any widget-state changes that
        happen between path-capture and this call (layout-on-hide, style
        reapply, deferred geometry). When omitted, falls back to a live
        re-read of ``w.mapToGlobal`` — preserves back-compat for callers
        that don't yet know about the path entry.

        Resizes the destination widget to match the launcher's size so the
        button doesn't visually pop to a different size during the
        transition. This is especially important when the launcher lives in
        a layout (e.g. main#startmenu's QVBoxLayout) and the destination
        widget is at fixed geometry — without the resize, the two would
        have different widths and the cursor would land on a visually
        different button.
        """
        try:
            if anchor_global is not None:
                p1 = anchor_global
            else:
                p1 = w.mapToGlobal(w.rect().center())

            w2 = self.sb.get_widget(w.objectName(), ui)
            if w2:
                self._align_widget_to_global_center(ui, w2, w.size(), p1)

        except Exception as e:
            self.logger.warning(f"Submenu positioning failed: {e}")

    @staticmethod
    def _align_widget_to_global_center(ui, w2, source_size, target_global_center):
        """Resize ``w2`` to ``source_size`` and move ``ui`` so ``w2``'s global
        center lands at ``target_global_center``.

        The resize preserves ``w2``'s *local* center: ``w2.resize`` keeps
        the top-left fixed and would otherwise shift the local center by
        half the size delta, which then propagates into the ui-move and
        slides every neighboring widget in ``ui`` off its layout position.
        We compensate with an in-place ``w2.move`` so the resize affects
        only ``w2``'s extent, not its position relative to its siblings.

        Returns the ``QPoint`` delta applied to ``ui``.
        """
        old_local_center = w2.rect().center()
        w2.resize(source_size)
        new_local_center = w2.rect().center()
        w2.move(w2.pos() + old_local_center - new_local_center)

        p2 = w2.mapToGlobal(w2.rect().center())
        diff = target_global_center - p2
        ui.move(ui.pos() + diff)
        return diff

    def _handle_overlay_cloning(self, ui) -> None:
        """Handle overlay cloning with optimized history checking."""
        if ui == self._last_ui_history_check:
            return
        ui_history_slice = self.sb.ui_history(slice(0, -1), allow_duplicates=True)
        if ui in ui_history_slice:
            self._last_ui_history_check = ui
            return

        self.overlay.clone_widgets_along_path(ui, self._return_to_startmenu)
        self._last_ui_history_check = ui

    def _clear_transition_flag(self):
        """Clear the transition flag to allow new transitions."""
        self._in_transition = False

    def _return_to_startmenu(self) -> None:
        """Return to the start menu, anchoring it at the gesture origin."""
        self._debounce_transition(clear_pending=True)

        start_pos = self.overlay.path.start_pos
        if not isinstance(start_pos, QtCore.QPoint):
            self.logger.warning("_return_to_startmenu called with no valid start_pos.")
            return

        startmenu = self.sb.ui_history(-1, inc="*#startmenu*")
        self._prepare_ui(startmenu, anchor=start_pos)

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

    def _ui_owns_widget(self, ui, widget) -> bool:
        """True if *widget* belongs to menu *ui* — a direct Qt descendant, or a
        logical descendant (a top-level sublist marked with ``_logical_ancestor``).
        The "is this widget part of the current menu?" test shared by the press
        click-vs-chord classification and the release click dispatch."""
        return ui.isAncestorOf(widget) or self._is_logical_descendant(ui, widget)

    def _owned_item_at(self, pos, current_ui):
        """The owned item of *current_ui* at global *pos*, or ``None``.

        Tries the OS-level :func:`QApplication.widgetAt` first — the only probe
        that can resolve a *logical* descendant (a top-level ExpandableList
        sublist marked with ``_logical_ancestor``) — then a geometric
        ``current_ui.childAt`` fallback.

        The geometric fallback is the fix for the marking menu's central live
        bug: over the menu's ``WA_TranslucentBackground`` overlay, ``widgetAt``'s
        OS ``WindowFromPoint`` falls through the layered window's transparent
        pixels and returns ``None`` even though the cursor is squarely over a
        button. So BOTH the release hit-test (:meth:`_resolve_release_target`) and
        the press click-vs-chord classification (:meth:`_is_menu_item_press`)
        missed, and the gesture fell through to ``_sync_menu_to_state`` and
        navigated away instead of clicking — the intermittent "the menu item under
        the cursor never registers a click, the menu just shifts/switches". It is
        pixel/alpha-dependent (hence "needs several clicks"). ``childAt`` walks the
        widget tree by geometry with no OS window query, so it finds the item
        ``widgetAt`` couldn't. Confirmed live: at a cursor squarely inside a
        button's rect, ``widgetAt`` returned ``None`` while ``childAt`` returned
        the button.
        """
        widget = QtWidgets.QApplication.widgetAt(pos)
        if (
            widget is not None
            and widget is not self
            and widget is not current_ui
            and self._ui_owns_widget(current_ui, widget)
        ):
            return widget
        child = current_ui.childAt(current_ui.mapFromGlobal(pos))
        if (
            child is not None
            and child is not current_ui
            and self._ui_owns_widget(current_ui, child)
        ):
            return child
        return None

    def _handle_widget_action(self, widget, global_pos=None) -> bool:
        """Execute action for a widget (button click or menu navigation).

        Args:
            widget: The widget resolved under the release/click position.
            global_pos: The dispatch position in global coords. Used to resolve a
                container's child at the *event* position rather than the live
                ``QCursor.pos()`` — under a host that pumps Qt from its own loop
                (Blender) the cursor drifts between the physical release and when
                this runs, so the live cursor can land on the wrong child (the
                same drift the release-path hit-test guards against). Falls back to
                the live cursor when not supplied.

        Returns:
            bool: True if action was executed, False if widget is non-interactive.
        """
        # Resolve container to actual child widget
        if hasattr(widget, "derived_type") and widget.derived_type == QtWidgets.QWidget:
            pos = global_pos if global_pos is not None else QtGui.QCursor.pos()
            child = widget.childAt(widget.mapFromGlobal(pos))
            if child:
                widget = child

        # Navigation-button clicks (menu/submenu launchers). Click opens the
        # button's target as a standalone window or a stacked submenu depending
        # on the target UI's own tags.
        if isinstance(widget, MenuButton):
            menu = self._resolve_button_menu(widget)
            if menu:
                # A nav button opens its target as a standalone window or a
                # stacked submenu depending on the target UI's own tags. A
                # category button like 'key' resolves (on release) to the native
                # Maya 'key' menu — an untagged window — so this opens it
                # standalone; a bare submenu target opens in the overlay.
                is_standalone = not menu.has_tags(["startmenu", "submenu"])
                self.show(menu, force=is_standalone)
                return True

        # Emit clicked signal for standard buttons
        if hasattr(widget, "clicked"):
            ui = getattr(widget, "ui", None)
            base_name = getattr(widget, "base_name", lambda: None)()
            ui_is_menu = bool(ui and ui.has_tags(["startmenu", "submenu"]))
            if ui_is_menu and base_name != "chk":
                # The leaf's slot actually fires here — a release hitting a leaf
                # whose owning ``ui`` isn't a live menu falls through to the
                # skip-log below instead.
                self.hide()
                widget.clicked.emit()
                return True
            else:
                self.logger.debug(
                    f"[_handle_widget_action] Click skipped for "
                    f"'{widget.objectName()}': ui={ui}, "
                    f"has_tags={ui_is_menu}, base_name='{base_name}'"
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

    def _host_mouse_buttons(self):
        """Current mouse-button mask for hover/drag tracking — overridable per host.

        Defaults to Qt's own query. A host whose native event loop owns the mouse
        (Blender's GHOST) overrides this to read the real (physical) button state,
        so ``MouseTracking``'s drag-gated ``track()`` — which reveals the marking
        menu's ``visible_on_mouse_over`` Regions during a grabbed chord gesture —
        still fires when ``QApplication.mouseButtons()`` is blind to GHOST events.
        """
        return QtWidgets.QApplication.mouseButtons()

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

    def _is_menu_item_press(self, event) -> bool:
        """True if *event* is a lone-button press over an interactive item
        (a button) of the current start/submenu — i.e. a click to dispatch on
        release, not a chord to resolve.

        Uses the event's own global position (not the live cursor) so it is
        immune to cursor drift under a pumped host event loop (Blender), and
        hit-tests against ``current_ui`` so only presses on *this menu's* items
        count — a press on empty overlay (the chord gesture) returns False. The
        hit-test goes through :meth:`_owned_item_at` (widgetAt + geometric childAt
        fallback): widgetAt alone returns None over the translucent overlay, so a
        single click on a menu item was mis-classified as a chord and navigated
        away instead of clicking — the same bug the release path had.
        """
        # A menu item is left-clicked; Middle/Right are chord selectors, never an
        # item click. Requiring a lone LeftButton keeps every chord (incl. a second
        # concurrent button → count > 1, and bare M/R presses) resolving as a chord.
        if event.button() != QtCore.Qt.LeftButton:
            return False
        if count_buttons(self._to_int(event.buttons())) != 1:
            return False
        current_ui = self.sb.active_ui
        if not (current_ui and current_ui.has_tags(["startmenu", "submenu"])):
            return False
        target = self._owned_item_at(event.globalPos(), current_ui)
        return isinstance(target, QtWidgets.QAbstractButton)

    # ---------------------------------------------------------------------------------------------
    #   Stacked Widget Event handling:

    def mousePressEvent(self, event) -> None:
        """Handle mouse press: route through the central state-sync."""
        if self._input_logging_on:
            self.logger.debug(
                f"[handoff] mousePressEvent buttons={self._to_int(event.buttons()):#04x} "
                f"widgetAt={self._w_repr(QtWidgets.QApplication.widgetAt(event.globalPos()))} "
                f"| {self._input_state()}"
            )

        # Cancel any pending suppress-hide so we don't yank the menu away
        # right after showing it.
        self._pending_hide_widget = None

        # Re-arm the single-shot dispatch latch: a press is a fresh click intent.
        # (The chord's own L-then-R presses both land before any release, so this
        # never re-arms mid-release-pair.) NOT re-armed on show() — a nav release
        # shows a submenu mid-gesture and must stay latched against the trailing
        # release.
        self._action_dispatched = False
        # A new press supersedes any pending chord-release decision.
        self._cancel_chord_release_timer()

        # A press that lands on an interactive menu item (a leaf or nav button of
        # the current start/submenu) is a CLICK — dispatch it on release; it must
        # never be re-resolved as the F12|Button chord. In Maya the button itself
        # consumes the press so the menu never sees it; over Blender the menu can
        # hold the mouse grab (a chord reach, or a stray re-grab), which routes the
        # press to the menu instead — where the sync below would read
        # buttons=LeftButton (while the key is held) as the chord and navigate away
        # before the leaf can fire (the "dead click", reproduced live in
        # tentacle/test/blender/normals_multiclick_check.py). Skipping the re-grab +
        # sync here lets the release reach _handle_widget_action. This must apply
        # even mid-chord: _is_menu_item_press already excludes a real chord (it
        # requires a lone button over an interactive item of the current menu, so a
        # second concurrent button or a press on empty overlay still resolves as a
        # chord) — the discriminator is position + button count, not a flag.
        if self._is_menu_item_press(event):
            event.accept()
            return

        # Defensive: re-establish mouse grab if it was lost (e.g. after a
        # deferred child-hide caused the host app to claim focus).
        if self._activation_key_held and self.mouseGrabber() is not self:
            self.grabMouse()

        current_ui = self.sb.active_ui
        if current_ui and current_ui.has_tags(["startmenu", "submenu"]):
            # Only start a new gesture if there isn't one already — otherwise
            # chord transitions (e.g. holding F12, tapping LMB) would rebind
            # start_pos to the cursor on every press, drifting the menu with
            # hand jitter.
            if self.overlay.path.is_empty:
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
                if self.overlay.path.is_empty:
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

    def _ensure_chord_release_timer(self) -> QtCore.QTimer:
        """Lazily create the single-shot chord-release tolerance timer.

        Lazy (not built in ``__init__``) so subclasses that bypass ``__init__``
        for event-handler-only testing still get it on first use.
        """
        timer = self._chord_release_timer
        if timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._on_chord_release_timeout)
            self._chord_release_timer = timer
        return timer

    def _defer_chord_release(self, event) -> None:
        """Hold a partial NAVIGATION release (one button up, other(s) still held,
        and NOT over an owned item) for the tolerance window instead of navigating
        now.

        The final all-up release within the window cancels this and settles to the
        no-button menu (``_sync_menu_to_state``); if the window expires with a
        button still held it was an intentional switch and
        :meth:`_on_chord_release_timeout` navigates to the remaining-button menu.
        """
        self._chord_pending_buttons = self._to_int(event.buttons())
        self._chord_pending_modifiers = self._to_int(event.modifiers())
        self._ensure_chord_release_timer().start(self.CHORD_RELEASE_TOLERANCE_MS)

    def _cancel_chord_release_timer(self) -> None:
        """Cancel a pending chord-release decision (the gesture resolved)."""
        timer = self._chord_release_timer
        if timer is not None and timer.isActive():
            timer.stop()
        self._chord_pending_buttons = 0

    def _on_chord_release_timeout(self) -> None:
        """The remaining chord button(s) were held past the tolerance — the user
        meant to SWITCH menus, not release both. Navigate to the menu the still-
        held buttons resolve to (the deferred sync the partial release skipped)."""
        pending = self._chord_pending_buttons
        self._chord_pending_buttons = 0
        if pending:
            self._sync_menu_to_state(
                buttons=pending, modifiers=self._chord_pending_modifiers
            )

    def _defer_partial_or_settle(self, event, current_ui) -> bool:
        """Classify a NAVIGATION release as a *partial* chord release (defer) or
        the final release (settle). Both release handlers call this ONLY after
        ruling out a release over an owned item (which dispatches immediately) —
        so this governs the "switch menus by releasing a button" gesture, never
        item selection.

        Returns True when the release left a button still held over a
        start/submenu: it is deferred by the tolerance window and the caller must
        consume the event. Returns False for the final all-up release (or a plain
        single-button release), having cancelled any pending decision first, so
        the caller proceeds to navigate (``_sync_menu_to_state``).
        """
        if (
            self._to_int(event.buttons()) != 0
            and current_ui
            and current_ui.has_tags(["startmenu", "submenu"])
        ):
            self._defer_chord_release(event)
            return True
        self._cancel_chord_release_timer()
        return False

    def _resolve_release_target(self, event, current_ui):
        """Resolve the owned menu item under a release, returning ``(widget, pos)``.

        Probes the release EVENT position first (the OS release point, immune to
        cursor drift under a host that pumps Qt from its own loop — Blender), then
        the LIVE cursor (:func:`QtGui.QCursor.pos`). Each position is resolved via
        :meth:`_owned_item_at` (widgetAt + the geometric childAt fallback that
        fixes the translucent-overlay miss).

        Returns ``(None, None)`` when no position is over an owned item.
        """
        for source, pos in (
            ("event", event.globalPos()),
            ("cursor", QtGui.QCursor.pos()),
        ):
            widget = self._owned_item_at(pos, current_ui)
            if widget is not None:
                return widget, pos
        return None, None

    def _handle_menu_item_release(self, pos, widget) -> bool:
        """Dispatch a release that landed on an owned interactive item of the
        current start/submenu — the shared core of :meth:`mouseReleaseEvent`
        (the menu holds the grab) and :meth:`child_mouseButtonReleaseEvent` (the
        grab migrated to the child). Routing both through here keeps the SAME
        gesture giving the SAME result no matter which object holds the grab.

        The item fires IMMEDIATELY on the release, exactly as the proven v1.0.66
        path did (``mouseReleaseEvent`` dispatched ``_handle_widget_action`` on
        the *first* release over an owned widget, with no wait for the other
        chord button). So a *both-buttons-held* release registers the click on
        whichever button lifts first and hides the menu; the trailing release of
        the pair lands on the now-hidden menu and is a harmless no-op.

        Chord *navigation* — releasing a button over empty overlay to drop to
        another menu — is unaffected: that path never reaches here (no owned
        interactive widget under the release), so the caller falls through to
        :meth:`_sync_menu_to_state` and navigates as before.

        ``pos`` is the resolved hit-test position from :meth:`_resolve_release_target`
        (event point or live cursor — whichever found the item), passed to
        ``_handle_widget_action`` so a container resolves its child at the same
        point the item was found.

        Returns True when the release is fully handled and the caller should
        consume it + drop the grab — whether it FIRED the item or SWALLOWED the
        trailing release of an already-dispatched chord. Returns False only when
        the widget is non-interactive, so the caller falls through to its own
        default handling (``_sync_menu_to_state`` / forward).

        A chord release fires this once: the per-gesture ``_action_dispatched``
        latch SWALLOWS the trailing release of the pair (returns True without
        acting) so it cannot dispatch a second action — the nav-button case,
        where the first release opened a submenu without hiding, and the trailing
        release would otherwise click into it OR fall through to sync and hide the
        just-opened submenu. The latch is re-armed on the next press / activation.
        """
        if self._action_dispatched:
            # Trailing release of the chord — swallow it (consume; no second
            # action, and crucially do NOT fall through to sync, which would
            # navigate/hide the menu the first release just settled on).
            return True
        # Set BEFORE dispatching so a re-entrant release during _handle_widget_action
        # (e.g. nav-show pumping events) can't slip a second action through.
        self._action_dispatched = True
        if self._handle_widget_action(widget, pos):
            return True
        # Non-interactive widget — nothing fired, so un-latch and let the caller
        # fall through to its default handling (and a later real action still fires).
        self._action_dispatched = False
        return False

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse release: dispatch click action or sync menu state."""
        current_ui = self.sb.active_ui
        if self._input_logging_on:
            self.logger.debug(
                f"[handoff] mouseReleaseEvent button={self._to_int(event.button()):#04x} "
                f"widgetAt={self._w_repr(QtWidgets.QApplication.widgetAt(event.globalPos()))} "
                f"current_ui={current_ui.objectName() if current_ui else None!r} | "
                f"{self._input_state()}"
            )

        if current_ui and current_ui.has_tags(["startmenu", "submenu"]):
            # Release over an owned interactive item dispatches the click
            # IMMEDIATELY — on the FIRST release of a chord, with NO wait for any
            # other held button. This is the proven v1.0.66 order: it resolved
            # and fired the owned item BEFORE consulting the chord-release timer,
            # and the timer only ever governed the *navigation* case (a release
            # over empty overlay). The regression was deferring this owned-item
            # release through the tolerance window first — the timer then
            # navigated the menu to the remaining-button menu (the "stays open
            # and shifts") before the click could land, so the MenuButton under
            # the cursor never registered. The _action_dispatched latch inside
            # _handle_menu_item_release swallows the trailing release of the
            # pair, so the click fires exactly once.
            #
            # The hit-test resolves at the event position first, then the live
            # cursor — a Maya chord release's globalPos can miss the item the
            # pointer is over (see _resolve_release_target).
            widget, pos = self._resolve_release_target(event, current_ui)

            self.logger.debug(
                f"[mouseReleaseEvent] current_ui={current_ui.objectName()}, "
                f"target={widget.objectName() if widget and hasattr(widget, 'objectName') else widget}, "
                f"grabber={self.mouseGrabber() is self}"
            )

            if widget is not None:
                if self._handle_menu_item_release(pos, widget):
                    self.releaseMouse()
                    event.accept()
                    return
                # owned but non-interactive — fall through to chord handling
            else:
                # Nothing owned under the release. If the pointer is over an
                # unrelated (non-menu) widget, leave the menu state alone; over
                # empty overlay / the menu background, fall through to the chord
                # sync (release-to-navigate).
                probe = QtWidgets.QApplication.widgetAt(event.globalPos())
                if probe is not None and probe is not self and probe is not current_ui:
                    event.accept()
                    return

        # Not over an owned item: this is chord NAVIGATION (release over empty
        # overlay to switch menus). ONLY here does the chord-release tolerance
        # apply — a partial release (a button still held) is deferred so a
        # near-simultaneous both-buttons release doesn't flicker to the
        # one-button menu; the final all-up release navigates below.
        if self._defer_partial_or_settle(event, current_ui):
            event.accept()
            return

        self._sync_menu_to_state(
            buttons=self._to_int(event.buttons()),
            modifiers=self._to_int(event.modifiers()),
        )
        event.accept()

    def _cached_ui(self, name: str) -> Optional[QtWidgets.QWidget]:
        """Return the UI for *name*, populating the submenu cache on first hit.

        Returns ``None`` for an unresolvable name rather than raising: ``get_ui`` resolves
        an unknown name through the slot resolver, which raises ``AttributeError`` ("Slot
        class '<name>' not found"). Callers (``child_enterEvent``, ``_resolve_button_menu``)
        guard on a falsy result, so honouring the ``Optional`` contract is what lets a nav
        launcher whose target doesn't resolve degrade gracefully instead of crashing the
        hover/click that triggered it. (Catching the resolver's miss — rather than gating on
        ``is_registered_ui`` — keeps programmatically-registered UIs that ``get_ui`` can load
        but that aren't in the *file* registry resolvable.)
        """
        ui = self._submenu_cache.get(name)
        if ui is None:
            try:
                ui = self.sb.get_ui(name)
            except AttributeError:
                return None
            if ui:
                self._submenu_cache[name] = ui
        return ui

    def _resolve_button_menu(self, widget: MenuButton) -> Optional[QtWidgets.QWidget]:
        """Resolve the menu a ``MenuButton`` navigates to (click path).

        Delegates destination resolution to the shared
        ``Switchboard.menu_button_target_name`` SSoT so a click, a hover
        (``child_enterEvent``) and the auto-hide check
        (``menu_button_target_resolves``) all agree. A bare-target nav launcher
        (``target="cameras"``, ``filterTags="lower"``) opens its composed submenu
        ``"cameras#lower#submenu"``; a fully-qualified ``target`` opens directly.
        Previously this resolved the *bare* ``target`` only, so clicking an upper/lower
        nav region raised ``AttributeError`` ("Slot class 'cameras' not found") instead of
        opening the submenu — the "submenus don't launch" report. Matching groupboxes are
        revealed via the filter tags.
        """
        name = self.sb.menu_button_target_name(widget)
        if not name:
            return None
        menu = self._cached_ui(name)
        if menu:
            self.sb.hide_unmatched_groupboxes(menu, widget.filter_tag_list())
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

    def _ensure_fullscreen_on_active_screen(
        self, anchor: Optional[QtCore.QPoint] = None
    ) -> None:
        """Pin the full-screen overlay to the screen the menu will land on.

        The overlay is a single frameless full-screen window and every menu is
        positioned inside it via ``self.mapFromGlobal(...)``. Qt's
        ``showFullScreen()`` binds the window to whichever screen it currently
        occupies — set once at construction to the parent (Maya) window's
        screen. When Maya is dragged to another monitor the overlay stays
        pinned to the original screen, so a menu anchored on the new monitor
        maps to local coordinates outside the overlay's bounds and silently
        never appears ("shows once, then subsequent shows fail without error").

        Relocate the overlay to the screen containing ``anchor`` (the same
        point ``setCurrentWidget`` positions the menu against, defaulting
        to the cursor) *before* the menu is positioned, so the coordinate
        mapping resolves against the correct window origin.

        Parameters:
            anchor (QPoint, optional): Global point the menu will be anchored
                to. Defaults to the current cursor position.
        """
        if anchor is None:
            anchor = QtGui.QCursor.pos()
        target = (
            QtWidgets.QApplication.screenAt(anchor)
            or QtWidgets.QApplication.primaryScreen()
        )
        handle = self.windowHandle()
        current = handle.screen() if handle is not None else None

        # Relocate only when the overlay is *confirmed* to be on a different
        # screen than the active one. Single-monitor and indeterminate cases
        # (no window handle / no screens) fall through to the original
        # show-if-hidden behaviour, so this is a strict no-op there.
        # (current is not None already implies handle is not None.)
        if target is not None and current is not None and current is not target:
            # Drop the full-screen state so the geometry can move across
            # screens, relocate, then re-assert full-screen on the target.
            self.setWindowState(self.windowState() & ~QtCore.Qt.WindowFullScreen)
            handle.setScreen(target)
            self.setGeometry(target.geometry())
            self.showFullScreen()
            return

        if self.isHidden():
            self.showFullScreen()

    def _show_marking_menu(self, widget, **kwargs):
        """Internal handler for showing marking menus."""
        # Cancel any pending suppress-hide so we don't pull the new menu away.
        self._pending_hide_widget = None

        # Startmenus shown mid-gesture (chord transitions like F12 → F12+LMB
        # → F12) anchor to the gesture's origin so the menu doesn't follow
        # cursor jitter between presses. The first show of each activation
        # cycle anchors at the cursor and becomes that gesture's origin.
        is_startmenu = widget.has_tags("startmenu")
        new_gesture = is_startmenu and self.overlay.path.is_empty
        anchor = self.overlay.path.start_pos if is_startmenu and not new_gesture else None

        # Multi-monitor: relocate the full-screen overlay to the anchor's screen
        # before positioning the menu (see method docstring). Must run before
        # setCurrentWidget, which maps the global anchor into the overlay's
        # local space — same anchor, so both resolve to the same screen.
        self._ensure_fullscreen_on_active_screen(anchor)

        self.setCurrentWidget(widget, anchor=anchor)

        if new_gesture:
            self.overlay.start_gesture(QtGui.QCursor.pos())

        if (
            self._suppress_default_on_reentry
            and self._activation_key_held
            and self._activation_key_str is not None
            and widget.objectName() != self._bindings.get(self._activation_key_str)
        ):
            self._non_default_shown = True

        # The overlay is already shown full-screen on the active monitor by
        # _ensure_fullscreen_on_active_screen() above.
        self.raise_()
        self.activateWindow()

        self.sb.current_ui = widget
        return widget

    def _show_window(self, widget, pos=None, force=False, **kwargs):
        """Internal handler for showing standalone windows."""
        if self._input_logging_on:
            self.logger.debug(
                f"[handoff] _show_window START target={widget.objectName()!r} "
                f"force={force} | {self._input_state()}"
            )
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
        # Same-delay follow-up (FIFO: runs after the raise above) — captures the
        # post-activation grab/active state, the moment a launched window would
        # be input-dead if a grab survived the handoff. Only scheduled while a
        # repro is being recorded, so no idle timer is queued otherwise.
        if self._input_logging_on:
            QtCore.QTimer.singleShot(
                0,
                lambda w=widget: self.logger.debug(
                    f"[handoff] _show_window POST-RAISE target={w.objectName()!r} | "
                    f"{self._input_state()}"
                ),
            )

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

        # CRITICAL: end the gesture and fully relinquish mouse control before
        # hiding (see _relinquish_input_control). The leaf-click launch path calls
        # hide() then opens a tool window via its slot WITHOUT going through
        # _show_window (the only other place _activation_key_held is cleared), so
        # without this the flag stayed set, the hidden menu's re-grab guards
        # (mousePressEvent / _do_pending_hide) kept/re-acquired the mouse, and the
        # launched window was input-dead (every click went to the hidden menu)
        # until the user tapped the activation key again — which ran this same
        # cleanup via _on_activation_release.
        self._relinquish_input_control()

        super().hide()

        parent = self.parentWidget()
        if parent and not self._transitioning_to_window:
            # Order matters: raise_() first brings window to front, then activateWindow()
            # gives it focus. Reversing this can cause the parent to go behind other apps.
            # Skip when transitioning to a standalone window — the target window
            # will raise itself via ui_handler.show(), and raising the parent here
            # would steal z-order from it.
            parent.raise_()
            parent.activateWindow()

    def hideEvent(self, event):
        """Clean up on hide - relinquishes input control even if hide() was bypassed."""
        # Safety net for a hide that bypassed hide() (e.g. a parent hide /
        # setVisible(False)): run the same full relinquish so the gesture can't
        # stay "live" with a dangling grab — releasing the grab alone left
        # _activation_key_held set, so a re-grab guard could still re-acquire.
        self._relinquish_input_control()
        self._clear_optimization_caches()
        super().hideEvent(event)

    def _relinquish_input_control(self):
        """End the gesture and release any grab — the full hand-off cleanup run on
        every hide, whether deliberate (:meth:`hide`) or bypassed (:meth:`hideEvent`).

        Clearing ``_activation_key_held`` stops the re-grab guards
        (``mousePressEvent`` / ``_do_pending_hide``) from re-acquiring the mouse
        once the menu is hidden; :meth:`_release_input_grab` drops a grab the menu
        or one of its child buttons still holds.
        """
        if self._input_logging_on:
            self.logger.debug(
                f"[handoff] _relinquish_input_control | {self._input_state()}"
            )
        self._activation_key_held = False
        self._release_input_grab()

    def _release_input_grab(self):
        """Release a mouse grab held by the menu OR one of its child buttons.

        ``hide()`` historically released only a grab held by ``self``, but
        ``MouseTracking`` migrates the grab onto the leaf button under the cursor
        during a drag (``_grab_widget`` → ``widget.grabMouse()``), so a chord that
        ends over a child left that child holding the global grab after the menu
        hid. Checking ``isAncestorOf`` covers both owners.
        """
        grabber = QtWidgets.QWidget.mouseGrabber()
        owned = grabber is not None and (grabber is self or self.isAncestorOf(grabber))
        if self._input_logging_on:
            self.logger.debug(
                "[handoff] _release_input_grab: "
                + (
                    f"releasing {self._w_repr(grabber)}"
                    if owned
                    else f"nothing owned to release (grabber={self._w_repr(grabber)})"
                )
            )
        if owned:
            grabber.releaseMouse()

    # ---------------------------------------------------------------------------------------------
    #   Input-handoff diagnostics
    #
    #   The "standalone window launched from the menu is input-dead until you tap
    #   key_show again" report is an input-handoff race: a mouse grab held by the
    #   menu (or a child button MouseTracking migrated it to) routes the new
    #   window's clicks back to the hidden menu. These read-only helpers expose
    #   the grab/activation state so a live repro pinpoints *which* object holds
    #   the grab (or rules a grab out) instead of guessing.

    def _w_repr(self, w) -> str:
        """Compact, delete-safe identifier for a widget in input-state logs."""
        try:
            if w is None:
                return "None"
            win = w.window()
            return (
                f"{type(w).__name__}('{w.objectName()}')"
                f"@{type(win).__name__}('{win.objectName()}')"
            )
        except RuntimeError:
            return "<deleted>"

    def _input_state(self) -> str:
        """One-line snapshot of the mouse-grab / activation state, shared by the
        handoff-diagnostic logs (read-only; safe to call from any log site).

        Reports who holds the global mouse grab and where it sits relative to the
        menu (``self`` / ``child`` / ``other`` / ``none``), the live button mask,
        the active window, the ``MouseTracking`` owner, and the menu's re-grab
        flags — the variables that decide whether a launched window takes clicks.
        """
        grab = QtWidgets.QWidget.mouseGrabber()
        mt = getattr(self, "mouse_tracking", None)
        owner = getattr(mt, "_mouse_owner", None) if mt is not None else None
        if grab is self:
            where = "self"
        elif grab is not None and self.isAncestorOf(grab):
            where = "child"
        elif grab is not None:
            where = "other"
        else:
            where = "none"
        return (
            f"grab={self._w_repr(grab)}[{where}] "
            f"buttons={self._to_int(QtWidgets.QApplication.mouseButtons()):#04x} "
            f"active={self._w_repr(QtWidgets.QApplication.activeWindow())} "
            f"mt_owner={self._w_repr(owner)} "
            f"key_held={getattr(self, '_activation_key_held', None)} "
            f"suppress={getattr(self, '_standalone_suppress', None)} "
            f"menu_visible={self.isVisible()}"
        )

    def enable_input_logging(self, path: Optional[str] = None, level="DEBUG") -> str:
        """Tee DEBUG input-handoff logs (this menu + its ``MouseTracking``) to a file.

        The menu and ``MouseTracking`` use separate class-scoped loggers, so this
        raises the level and attaches a file handler on BOTH — otherwise the grab
        migration records emitted by ``MouseTracking`` are missed. Returns the log
        path; stop with :meth:`disable_input_logging`. Reproduce the issue, then
        read the file. Auto-enabled at construction when the ``UITK_INPUT_LOG``
        environment variable names a path.
        """
        if path is None:
            path = os.path.join(tempfile.gettempdir(), "uitk_input_handoff.log")
        for cls in {type(self), type(self.mouse_tracking)}:
            cls.set_log_level(level)
            cls.set_log_file(path, level)
        self._input_logging_on = True
        self.mouse_tracking._input_logging_on = True
        self.logger.debug(f"[input-log] enabled -> {path} | {self._input_state()}")
        return path

    def disable_input_logging(self) -> None:
        """Stop the file logging started by :meth:`enable_input_logging`."""
        self._input_logging_on = False
        self.mouse_tracking._input_logging_on = False
        for cls in {type(self), type(self.mouse_tracking)}:
            cls.set_log_file(None)

    def _clear_optimization_caches(self):
        """Clear optimization caches to prevent memory accumulation."""
        if self._pending_show_timer and self._pending_show_timer.isActive():
            self._pending_show_timer.stop()

        self._in_transition = False

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
                if isinstance(w, MenuButton):
                    w.ui.style.set(widget=w)

            if w.type == self.sb.registered_widgets.Region:
                w.visible_on_mouse_over = True

            self.child_event_filter.install(w)

    def _is_popup_menu_child(self, w) -> bool:
        """True if *w* is displayed inside an interactive ``Menu`` popup (e.g. an
        option-box dropdown) rather than directly on this marking menu.

        Option-box controls are real start/submenu slot widgets (their ``.ui`` is
        the submenu) merely *shown* in a popup ``Menu``, so they carry this menu's
        ``child_event_filter``. But that popup owns its own input: running the
        gesture child-handlers on it routes its releases through
        :meth:`_handle_menu_item_release` — whose ``_action_dispatched`` latch,
        left stuck ``True`` by the launching click (a popup press never resets it),
        then SWALLOWS the release so the checkbox never toggles / the combobox
        never selects — and hover-toggles its checkboxes. Such widgets must be
        left to normal Qt input. Gated on the top-level window being a ``Menu`` so
        ExpandableList sublist ToolTips (gesture surfaces, not ``Menu`` windows)
        are unaffected.
        """
        from uitk.widgets.menu import Menu

        try:
            return isinstance(w.window(), Menu)
        except RuntimeError:
            return False

    def child_enterEvent(self, w, event) -> None:
        """Handle the enter event for child widgets."""
        # Skip the gesture behaviour (submenu-open, chk hover-toggle) for a widget
        # shown inside an interactive Menu popup — it owns its own input.
        if not self._is_popup_menu_child(w):
            if isinstance(w, MenuButton) and w.target:
                # Hover opens the button's own submenu — component-specific when the
                # button carries filter tags (the polygons Edge button →
                # "polygons#edge#submenu", not the base "polygons#submenu").
                submenu_name = w.submenu_name()
                submenu = self._cached_ui(submenu_name) if submenu_name != w.ui.objectName() else None
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
        if not self._is_popup_menu_child(w) and w.derived_type == QtWidgets.QPushButton:
            self._debounce_transition(clear_pending=True)

        super_event = getattr(super(type(w), w), "leaveEvent", None)
        if callable(super_event):
            super_event(event)

    def child_mouseButtonReleaseEvent(self, w, event) -> bool:
        """Dispatch (or forward) a release delivered to a *grabbed* child.

        During a drag the mouse grab migrates from the MarkingMenu to the
        child button under the cursor (``MouseTracking._handle_mouse_grab``
        captures QPushButtons), so the release lands HERE — on the child's
        event filter — not on :meth:`mouseReleaseEvent`. The grabbed button
        never received a *press* (the chord press went to the overlay), so it
        is not ``down`` and Qt emits no native click: without help, the release
        is a dead click.

        When the child is an interactive item of the current start/submenu, the
        release is routed through the SAME :meth:`_handle_menu_item_release` the
        menu-grab path uses, in the SAME order: the owned item fires IMMEDIATELY
        on the first release, with NO wait for any other held button (the chord
        tolerance governs navigation only — see :meth:`mouseReleaseEvent`), and
        the ``_action_dispatched`` latch swallows the trailing release of the
        pair. Sharing that core keeps the gesture giving the SAME result no matter
        which object holds the grab — and fixes the dead click that regressed when
        the ``_chord_release_timer`` machinery was replaced by
        ``_sync_menu_to_state`` (commit 3b7213e), which left this path a no-op
        pass-through. The two sites are mutually exclusive (menu-grab →
        mouseReleaseEvent; child-grab → here), so there is no double dispatch.

        The target is resolved via :meth:`_resolve_release_target` (event position
        then live cursor), so the click lands on the right item whether the cursor
        drifted off ``w`` under a pumped host loop (Blender) or the chord release's
        event position missed the item the pointer is over (Maya).
        """
        # A control shown inside an interactive Menu popup (option-box dropdown)
        # owns its own input — never route its release through the gesture
        # dispatch. The launching click leaves _action_dispatched stuck True (a
        # popup press never resets it), so _handle_menu_item_release would SWALLOW
        # this release and the checkbox/combobox would never actuate. Returning
        # False lets the release reach the widget's own handler. See
        # _is_popup_menu_child.
        if self._is_popup_menu_child(w):
            return False
        current_ui = self.sb.active_ui
        if self._input_logging_on:
            self.logger.debug(
                f"[handoff] child_mouseButtonReleaseEvent w={self._w_repr(w)} "
                f"widgetAt={self._w_repr(QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos()))} "
                f"current_ui={current_ui.objectName() if current_ui else None!r} | "
                f"{self._input_state()}"
            )
        if current_ui and current_ui.has_tags(["startmenu", "submenu"]):
            # Owned item → dispatch the click IMMEDIATELY on the first release,
            # regardless of any other held button (same order as the menu-grab
            # path; the chord tolerance governs navigation only, never an
            # owned-item select). The _action_dispatched latch makes the trailing
            # release of a both-button pair a no-op, so the click fires once.
            widget, pos = self._resolve_release_target(event, current_ui)
            if widget is not None:
                if self._handle_menu_item_release(pos, widget):
                    # Fired — drop the child's grab and consume.
                    try:
                        w.releaseMouse()
                    except RuntimeError:
                        pass
                    return True
                return False  # owned but non-interactive — let it fall through

        # Not over an owned item: chord NAVIGATION. A partial release (other
        # button still held) is deferred by the tolerance window; returning True
        # keeps the child's grab so the final release still reaches here.
        if self._defer_partial_or_settle(event, current_ui):
            return True

        # Not over an owned menu item — forward to the child's own handler when
        # the grab was bypassed (cursor moved off it), as before.
        if not w.underMouse():
            w.mouseReleaseEvent(event)
        return False
