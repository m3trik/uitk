# !/usr/bin/python
# coding=utf-8
import sys
import os
import time
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


# Crash diagnostic (opt-in via TENTACLE_MM_CRASH_DIAG=1).
# Writes line-buffered log so the last entry survives a hard segfault.
_CRASH_DIAG_FH = None
_CRASH_DIAG_INIT_TRIED = False

# Cache the validity probe at import time (hot path during gestures).
_IS_VALID = None
try:
    from shiboken6 import isValid as _IS_VALID  # type: ignore
except Exception:
    try:
        from shiboken2 import isValid as _IS_VALID  # type: ignore
    except Exception:
        _IS_VALID = None


def _diag(tag, **kw):
    """Append one diagnostic record. Lazy-initializes file handle on first call,
    so the env var can be set after import (e.g. from Maya's Script Editor).
    Never raises.
    """
    global _CRASH_DIAG_FH, _CRASH_DIAG_INIT_TRIED
    if _CRASH_DIAG_FH is None:
        if _CRASH_DIAG_INIT_TRIED and not os.environ.get("TENTACLE_MM_CRASH_DIAG"):
            return
        _CRASH_DIAG_INIT_TRIED = True
        if not os.environ.get("TENTACLE_MM_CRASH_DIAG"):
            return
        try:
            path = os.path.expanduser("~/tentacle_marking_menu_crash.log")
            _CRASH_DIAG_FH = open(path, "a", buffering=1, encoding="utf-8")
            _CRASH_DIAG_FH.write(
                f"\n===== session start pid={os.getpid()} "
                f"t={time.time():.3f} =====\n"
            )
        except Exception:
            _CRASH_DIAG_FH = None
            return
    try:
        parts = [f"{time.time():.6f}", tag]
        for k, v in kw.items():
            parts.append(f"{k}={v!r}")
        _CRASH_DIAG_FH.write(" | ".join(parts) + "\n")
    except Exception:
        pass


def _diag_enabled() -> bool:
    """True iff the diag file handle is open. Cheap check — use this to
    gate the construction of expensive diag payloads (e.g. comprehensions
    over the overlay path) so we don't pay the build cost when the env
    var is off."""
    return _CRASH_DIAG_FH is not None


def _safe_int(v):
    """Coerce Qt enum/flag/int to int without raising. Returns -1 on failure."""
    try:
        if isinstance(v, int):
            return v
        return int(v)
    except Exception:
        try:
            return int(v.value)
        except Exception:
            return -1


def _widget_id(w):
    """Safe widget identity string — survives deleted C++ underneath."""
    if w is None:
        return "None"
    try:
        if _IS_VALID is not None and not _IS_VALID(w):
            return f"<DELETED {type(w).__name__} id={id(w):#x}>"
        cls = type(w).__name__
        try:
            name = w.objectName() or "<noname>"
        except Exception:
            name = "<err>"
        try:
            is_win = w.isWindow()
        except Exception:
            is_win = "?"
        try:
            visible = w.isVisible()
        except Exception:
            visible = "?"
        try:
            wflags = _safe_int(w.windowFlags())
        except Exception:
            wflags = "?"
        return (
            f"<{cls} name={name!r} id={id(w):#x} "
            f"win={is_win} vis={visible} flags={wflags}>"
        )
    except Exception as e:
        return f"<id-err {e!r}>"


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
        _diag(
            "ACT_PRESS_ENTER",
            held=self._activation_key_held,
            suppress=self._standalone_suppress,
            non_default=self._non_default_shown,
            self_visible=self.isVisible(),
            self_grabber=(QtWidgets.QWidget.mouseGrabber() is self),
            grabber=_widget_id(QtWidgets.QWidget.mouseGrabber()),
            current_widget=_widget_id(self._current_widget),
            buttons=_safe_int(buttons),
        )
        try:
            # If a standalone window was opened during this key-hold cycle,
            # ignore re-press until the key is genuinely released and pressed again.
            if self._standalone_suppress:
                _diag("ACT_PRESS_SUPPRESSED")
                return

            self._activation_key_held = True
            self._non_default_shown = False
            self.key_show_press.emit()

            _diag("ACT_PRESS_BEFORE_DISMISS", buttons=_safe_int(buttons))
            # Clean external UIs, passing current state to avoid race/re-query
            self._dismiss_external_popups(buttons)
            _diag("ACT_PRESS_AFTER_DISMISS")

            # Single source of truth: pick a menu from the current input state.
            self._sync_menu_to_state(
                buttons=self._to_int(buttons),
                modifiers=self._to_int(QtWidgets.QApplication.keyboardModifiers()),
            )
            _diag(
                "ACT_PRESS_AFTER_SYNC",
                self_visible=self.isVisible(),
                current_widget=_widget_id(self._current_widget),
            )

            # Hand over mouse control if a button is already held at activation.
            active_btn = self._get_priority_button(buttons)
            if active_btn != QtCore.Qt.NoButton:
                self._transfer_mouse_control(active_btn, buttons)

            QtCore.QTimer.singleShot(0, self.dim_other_windows)

        except Exception as e:
            _diag("ACT_PRESS_EXC", err=repr(e))
            self.logger.error(f"Error in _on_activation_press: {e}")
            self._activation_key_held = False
        _diag("ACT_PRESS_EXIT")

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
        _diag(
            "ACT_RELEASE_ENTER",
            held=self._activation_key_held,
            self_visible=self.isVisible(),
            self_grabber=(QtWidgets.QWidget.mouseGrabber() is self),
            grabber=_widget_id(QtWidgets.QWidget.mouseGrabber()),
            current_widget=_widget_id(self._current_widget),
        )
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
            _diag(
                "POS_SMOOTH_ENTER",
                ui=ui.objectName(),
                w=w.objectName() if hasattr(w, "objectName") else "?",
                w_size=(w.width(), w.height()),
                w_pos_in_parent=(w.pos().x(), w.pos().y()),
                p1=(p1.x(), p1.y()),
                anchor_source="path" if anchor_global is not None else "live",
                w2_found=w2 is not None,
                w2_size_before=(w2.width(), w2.height()) if w2 else None,
                ui_pos_before=(ui.pos().x(), ui.pos().y()),
            )
            if w2:
                diff = self._align_widget_to_global_center(
                    ui, w2, w.size(), p1
                )
                _diag(
                    "POS_SMOOTH_EXIT",
                    w2_size_after=(w2.width(), w2.height()),
                    w2_local_center=(
                        w2.rect().center().x(),
                        w2.rect().center().y(),
                    ),
                    diff=(diff.x(), diff.y()),
                    ui_pos_after=(ui.pos().x(), ui.pos().y()),
                )

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

        Returns the ``QPoint`` delta applied to ``ui`` (for diagnostics).
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

        # Diag payload is only built when the crash log is open — keeps the
        # mapToGlobal calls out of the hot path under normal runs.
        if _diag_enabled():
            _diag(
                "CLONE_BEFORE",
                ui=ui.objectName(),
                ui_pos=(ui.pos().x(), ui.pos().y()),
                path_entries=[
                    self._path_entry_snapshot(w, pos)
                    for w, pos, _ in self.overlay.path._path
                ],
            )

        clones = self.overlay.clone_widgets_along_path(
            ui, self._return_to_startmenu
        )

        if _diag_enabled():
            _diag(
                "CLONE_AFTER",
                ui=ui.objectName(),
                clones=[self._clone_snapshot(c) for c in clones],
            )

        self._last_ui_history_check = ui

    @staticmethod
    def _path_entry_snapshot(widget, saved_pos):
        """One row of the path table for CLONE_BEFORE — captures saved vs
        live center so the two can be diffed when investigating drift."""
        if widget is None:
            return {"name": None, "saved_pos": None, "current_center": None, "size": None}
        try:
            current = widget.mapToGlobal(widget.rect().center())
            current_center = (current.x(), current.y())
        except Exception:
            current_center = None
        return {
            "name": widget.objectName() if hasattr(widget, "objectName") else None,
            "saved_pos": (saved_pos.x(), saved_pos.y()) if saved_pos else None,
            "current_center": current_center,
            "size": (widget.width(), widget.height()),
        }

    @staticmethod
    def _clone_snapshot(clone):
        """One row of the clones table for CLONE_AFTER."""
        gc = clone.mapToGlobal(clone.rect().center())
        return {
            "name": clone.objectName(),
            "pos_in_parent": (clone.pos().x(), clone.pos().y()),
            "size": (clone.width(), clone.height()),
            "global_center": (gc.x(), gc.y()),
        }

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
        """Return to the start menu, anchoring it at the gesture origin."""
        self._debounce_transition(clear_pending=True)

        start_pos = self.overlay.path.start_pos
        if not isinstance(start_pos, QtCore.QPoint):
            self.logger.warning("_return_to_startmenu called with no valid start_pos.")
            return

        startmenu = self.sb.ui_history(-1, inc="*#startmenu*")
        _diag(
            "RETURN_BEFORE",
            startmenu=startmenu.objectName() if startmenu else None,
            start_pos=(start_pos.x(), start_pos.y()),
            startmenu_pos_before=(startmenu.pos().x(), startmenu.pos().y()) if startmenu else None,
        )
        self._prepare_ui(startmenu, anchor=start_pos)
        _diag(
            "RETURN_AFTER",
            startmenu_pos_after=(startmenu.pos().x(), startmenu.pos().y()),
            startmenu_size=(startmenu.width(), startmenu.height()),
        )

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
                target_src = "grabber"
                if not target:
                    target = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
                    target_src = "widgetAt"

                _diag(
                    "DISMISS_TARGET",
                    src=target_src,
                    target=_widget_id(target),
                    is_ancestor=(self.isAncestorOf(target) if target else None),
                    btn=_safe_int(btn),
                )

                # Should not send to self or children if we are somehow active (unlikely at this stage)
                if target and not self.isAncestorOf(target):
                    try:
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
                        _diag("DISMISS_BEFORE_SENDEVENT", target=_widget_id(target))
                        QtWidgets.QApplication.sendEvent(target, event)
                        _diag("DISMISS_AFTER_SENDEVENT")
                    except Exception as e:
                        _diag("DISMISS_SENDEVENT_EXC", err=repr(e))
                        raise

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
                is_standalone = not menu.has_tags(["startmenu", "submenu"])
                _diag("MM_DISPATCH_NAV", widget=_widget_id(widget), menu=_widget_id(menu))
                self.show(menu, force=is_standalone)
                return True

        # Emit clicked signal for standard buttons
        if hasattr(widget, "clicked"):
            ui = getattr(widget, "ui", None)
            base_name = getattr(widget, "base_name", lambda: None)()
            ui_is_menu = bool(ui and ui.has_tags(["startmenu", "submenu"]))
            if ui_is_menu and base_name != "chk":
                # Marks the leaf's slot actually firing — the proof a click ran
                # vs was silently dropped (a release hitting a leaf whose owning
                # ``ui`` isn't a live menu logs MM_DISPATCH_SKIP and just hides).
                _diag(
                    "MM_DISPATCH_CLICK",
                    widget=_widget_id(widget),
                    ui=_widget_id(ui),
                    base_name=base_name,
                )
                self.hide()
                widget.clicked.emit()
                return True
            else:
                _diag(
                    "MM_DISPATCH_SKIP",
                    widget=_widget_id(widget),
                    ui=_widget_id(ui),
                    base_name=base_name,
                    ui_is_menu=ui_is_menu,
                )
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

        _diag("MM_DISPATCH_NONINTERACTIVE", widget=_widget_id(widget))
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
        _diag(
            "XFER_ENTER",
            button=_safe_int(button),
            buttons_mask=_safe_int(buttons_mask),
            self_visible=self.isVisible(),
            self_grabber=(QtWidgets.QWidget.mouseGrabber() is self),
            grabber=_widget_id(QtWidgets.QWidget.mouseGrabber()),
        )

        # Force grab mouse to ensure MarkingMenu receives subsequent move events
        _diag("XFER_BEFORE_GRAB")
        self.grabMouse()
        _diag("XFER_AFTER_GRAB", grabber=_widget_id(QtWidgets.QWidget.mouseGrabber()))

        local_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(local_pos),
            QtCore.QPointF(QtGui.QCursor.pos()),
            button,
            buttons_mask,
            QtCore.Qt.KeyboardModifier(),
        )
        _diag("XFER_BEFORE_SENDEVENT")
        QtWidgets.QApplication.sendEvent(self, event)
        _diag("XFER_AFTER_SENDEVENT")

    def _is_menu_item_press(self, event) -> bool:
        """True if *event* is a lone-button press over an interactive item
        (a button) of the current start/submenu — i.e. a click to dispatch on
        release, not a chord to resolve.

        Uses the event's own global position (not the live cursor) so it is
        immune to cursor drift under a pumped host event loop (Blender), and
        hit-tests against ``current_ui`` so only presses on *this menu's* items
        count — a press on empty overlay (the chord gesture) returns False.
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
        target = QtWidgets.QApplication.widgetAt(event.globalPos())
        if target is None or target is self:
            return False
        if not isinstance(target, QtWidgets.QAbstractButton):
            return False
        return self._ui_owns_widget(current_ui, target)

    # ---------------------------------------------------------------------------------------------
    #   Stacked Widget Event handling:

    def mousePressEvent(self, event) -> None:
        """Handle mouse press: route through the central state-sync."""
        self.logger.debug(f"mousePressEvent: {event.buttons()} {event.modifiers()}")
        _diag(
            "MM_PRESS_ENTER",
            held=self._activation_key_held,
            self_visible=self.isVisible(),
            self_grabber=(QtWidgets.QWidget.mouseGrabber() is self),
            buttons=_safe_int(event.buttons()),
            current_widget=_widget_id(self._current_widget),
        )

        # Cancel any pending suppress-hide so we don't yank the menu away
        # right after showing it.
        self._pending_hide_widget = None

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
            _diag("MM_PRESS_MENU_ITEM", held=self._activation_key_held)
            event.accept()
            return

        # Defensive: re-establish mouse grab if it was lost (e.g. after a
        # deferred child-hide caused the host app to claim focus).
        if self._activation_key_held and self.mouseGrabber() is not self:
            _diag("MM_PRESS_REGRAB", self_visible=self.isVisible())
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

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse release: dispatch click action or sync menu state."""
        current_ui = self.sb.active_ui
        _diag(
            "MM_RELEASE_ENTER",
            held=self._activation_key_held,
            self_grabber=(QtWidgets.QWidget.mouseGrabber() is self),
            current_ui=_widget_id(current_ui),
            button=_safe_int(event.button()),
            buttons=_safe_int(event.buttons()),
        )

        if current_ui and current_ui.has_tags(["startmenu", "submenu"]):
            # Resolve the click target at the *release event's* position, not the
            # live cursor: the dispatch must act on where the button was released.
            # Under a host that pumps Qt from its own loop (Blender), the cursor
            # can move between the physical release and when this handler runs, so
            # QCursor.pos() drifts off the leaf and the click is silently dropped
            # (the intermittent "dead click"). event.globalPos() carries the OS
            # release position and equals the cursor under a native Qt loop (Maya).
            widget = QtWidgets.QApplication.widgetAt(event.globalPos())
            _diag("MM_RELEASE_WIDGETAT", widget=_widget_id(widget))

            self.logger.debug(
                f"[mouseReleaseEvent] current_ui={current_ui.objectName()}, "
                f"widgetAt={widget.objectName() if widget and hasattr(widget, 'objectName') else widget}, "
                f"grabber={self.mouseGrabber() is self}"
            )

            if widget and widget is not self and widget is not current_ui:
                if self._ui_owns_widget(current_ui, widget):
                    if self._handle_widget_action(widget, event.globalPos()):
                        self.releaseMouse()
                        event.accept()
                        return
                    # Non-interactive widget — fall through to normal sync.
                else:
                    # Cursor over an unrelated widget — leave menu state alone.
                    _diag(
                        "MM_RELEASE_UNRELATED_RETURN",
                        self_grabber=(QtWidgets.QWidget.mouseGrabber() is self),
                    )
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
        _diag(
            "PENDING_HIDE_ENTER",
            widget=_widget_id(widget),
            current_widget=_widget_id(self._current_widget),
            held=self._activation_key_held,
            self_visible=self.isVisible(),
        )
        if widget is not None and widget is self._current_widget and widget.isVisible():
            widget.hide()
            self._current_widget = None
            if self.isVisible() and self._activation_key_held:
                self.raise_()
                self.activateWindow()
                if self.mouseGrabber() is not self:
                    _diag("PENDING_HIDE_BEFORE_GRAB", self_visible=self.isVisible())
                    self.grabMouse()
                    _diag("PENDING_HIDE_AFTER_GRAB")

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
                if isinstance(w, MenuButton):
                    w.ui.style.set(widget=w)

            if w.type == self.sb.registered_widgets.Region:
                w.visible_on_mouse_over = True

            self.child_event_filter.install(w)

    def child_enterEvent(self, w, event) -> None:
        """Handle the enter event for child widgets."""
        if isinstance(w, MenuButton) and w.target:
            # Hover opens the button's own submenu — component-specific when the
            # button carries filter tags (the polygons Edge button →
            # "polygons#edge#submenu", not the base "polygons#submenu").
            submenu_name = w.submenu_name()
            if submenu_name != w.ui.objectName():
                submenu = self._cached_ui(submenu_name)
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
