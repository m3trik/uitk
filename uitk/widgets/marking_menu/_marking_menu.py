# !/usr/bin/python
# coding=utf-8
import sys
import os
import weakref
from typing import Optional

from qtpy import QtCore, QtWidgets
import pythontk as ptk

from uitk.compile import UiCompiler
from uitk.events import EventFactoryFilter, MouseTracking
from uitk.handlers.ui_handler import UiHandler
from uitk.loaders import CompiledLoader
from uitk.switchboard import Switchboard
from ._resolver import MenuResolver, _MARKING_MENU_TAGS
from .overlay import Overlay
from ._bindings import _BindingsMixin
from ._hosting import _HostingMixin
from ._input import _InputMixin
from ._navigation import _NavigationMixin
from ._presentation import _PresentationMixin


class MarkingMenu(
    # The concept parts come BEFORE QWidget: several override QWidget virtuals
    # (show/hide, the mouse/key/show/hide events), and a base listed after
    # QWidget would lose those names to it. Their names are disjoint, so their
    # own order is immaterial.
    _BindingsMixin,
    _HostingMixin,
    _NavigationMixin,
    _InputMixin,
    _PresentationMixin,
    QtWidgets.QWidget,
    ptk.SingletonMixin,
    ptk.LoggingMixin,
    ptk.HelpMixin,
):
    """MarkingMenu is a marking menu based on a QWidget.
    The various UI's are set by calling 'show' with the intended UI name string. ex. MarkingMenu().show('polygons')

    Parameters:
        parent (QWidget): The parent application's top level window instance. ie. the Maya main window.
        bindings (dict): Chord string -> UI name, e.g. ``{"Key_Z": "main", "Key_Z|LeftButton": "cameras"}``.
                This is also where the **activation key** comes from: there is no ``key_show``
                parameter — the first ``Key_*`` part found while parsing these bindings becomes it
                (see ``_build_bindings`` / ``MenuResolver.parse_binding_keys``), and the parsed
                result is published on the ``key_show`` *attribute*. A caller wanting to choose the
                key by name generates the bindings from it (tentacle's ``Tcl.chord_bindings`` does
                exactly that). Persisted per host context and forward-merged with these defaults on
                each construction.
        ui_source (str): The directory path or the module where the UI files are located.
                If the given dir is not a full path, it will be treated as relative to the default path.
                If a module is given, the path to that module will be used.
        slot_source (str): The directory path where the slot classes are located or a class object.
                If the given dir is a string and not a full path, it will be treated as relative to the default path.
                If a module is given, the path to that module will be used.
        switchboard (Switchboard): An optional existing Switchboard instance to use.
        log_level (int): Determines the level of logging messages. Defaults to logging.WARNING. Accepts standard Python logging module levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.

    The class is assembled from one part per concept, each a mixin module in
    this package: ``_bindings`` (chord table, activation key, routes),
    ``_hosting`` (stacked pages, hosted themes, preload), ``_navigation``
    (submenu transitions, child hooks), ``_input`` (hit-testing, press/release
    dispatch, the grab) and ``_presentation`` (show/hide, the fade). This
    module keeps construction, the process-wide instance registry and the
    activation press/release that drive the rest.
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
    # Fallback registry for a process with no QApplication yet (test fixtures
    # that bypass __init__). Production instances go through _live_registry().
    _live_instances: "weakref.WeakSet" = weakref.WeakSet()
    # Attribute under which the process-wide registry lives on the QApplication.
    # A plain constant, so both class generations across a reload agree on it.
    _LIVE_REGISTRY_ATTR = "_uitk_marking_menu_live_instances"
    _retired: bool = False

    # Shell-style name patterns matching the gesture pages this menu hosts
    # (the same tag set hosts_ui claims). Applied as the SwitchboardBrowser's
    # structural exclude filter via an editors post-build hook (see
    # _register_browser_entry_filter): gesture pages aren't standalone tools,
    # and their show/hide traffic during gestures would churn an open
    # browser. Subclasses opt out (or extend) by overriding.
    HOSTED_PAGE_PATTERNS = tuple(f"*#{t}*" for t in _MARKING_MENU_TAGS)

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
        preload: bool = False,
        context_tags=None,
        **kwargs,
    ):
        """ """
        super().__init__(parent=parent)
        self.logger.setLevel(log_level)
        self._bindings = {}
        self._submenu_cache = {}  # per-instance; see the class-attr note
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
                UiCompiler.precompile_async(*ui_paths)

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
        # The dim pass is a once-per-hold snapshot: it runs on key_show press
        # and must NOT re-run while the key is held (a QShortcut auto-repeats by
        # default). Re-running would re-snapshot and dim windows/menus opened
        # *during* the hold — which are the current operation and must stay
        # bright. A separate bool (not `bool(_windows_to_restore)`) is required
        # so an empty snapshot still blocks a re-run.
        self._dim_snapshot_taken = False

        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_NoMousePropagation, False)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        # Realize the native window and bind the fullscreen state/screen
        # WITHOUT presenting. A bare showFullScreen() here left the
        # (translucent) overlay on screen from DCC startup until the first
        # gesture ended, so the FIRST activation ran
        # _ensure_fullscreen_on_active_screen's cross-screen relocate on a
        # VISIBLE window — dropping the fullscreen state restores Qt's
        # ~100x30 pre-fullscreen "normal" geometry on screen and paints every
        # intermediate step (the init-time "components flash before the menu
        # shows"). The suppressed present keeps the handle and screen bind,
        # ends construction hidden, and makes the first activation take the
        # same present-last path as every reopen (_show_marking_menu).
        with self._suppressed_present():
            pass

        # Initialize smooth transition timer
        self._pending_show_timer = QtCore.QTimer()
        self._pending_show_timer.setSingleShot(True)
        self._pending_show_timer.timeout.connect(self._perform_transition)

        # Auto-install the activation shortcut if a parent is provided. Extracted
        # to _install_activation_shortcut so set_activation_key can re-create it on
        # the new key; the host is remembered for that re-install.
        self._activation_parent = parent
        if parent:
            self._install_activation_shortcut()

        # A process hosts at most ONE input-owning marking menu. A second
        # instance (a dev reload constructs a new TclMaya/TclBlender in the
        # same DCC session) must RETIRE the previous one: its still-live
        # activation GlobalShortcut otherwise keeps servicing the gesture with
        # stale caches — wrappers whose native-menu content this instance's
        # builds re-wrap — so a chord release is consumed but launches nothing.
        registry = self._live_registry()
        for _other in list(registry):
            if _other is not self:
                _other.retire()
        registry.add(self)

        # Optional scoped preloading: warm the binding-target menus once the
        # host's event loop spins, so the FIRST activation behaves exactly
        # like every later one (see preload_menus). Deferred + staggered —
        # construction stays fast and the host keeps painting between
        # warm-ups. Off by default for the same reason as ``precompile``.
        if preload:
            self.preload_menus()

    @classmethod
    def _live_registry(cls) -> "weakref.WeakSet":
        """Every not-yet-retired instance in this PROCESS.

        Anchored on the ``QApplication`` rather than on the class, because a
        class attribute does not survive a module reload: ``importlib.reload``
        re-executes the class body, so the post-reload generation would start
        with an EMPTY registry and never retire the instance built before it —
        two armed activation shortcuts on the same host widget, which Qt
        resolves as ambiguous, so the menu stops opening until the DCC is
        restarted. That is the ``Settings > Reload Scripts`` path in tentacle.
        The QApplication outlives every reload, so both generations resolve the
        same set (the same reason tentacle's Blender event pump caches its
        generation token there).

        Falls back to the class-level set only when there is no QApplication —
        test fixtures that bypass ``__init__``; a production instance is a
        QWidget and so always has one.
        """
        app = QtWidgets.QApplication.instance()
        if app is None:
            return cls._live_instances
        registry = getattr(app, cls._LIVE_REGISTRY_ATTR, None)
        if registry is None:
            registry = weakref.WeakSet()
            setattr(app, cls._LIVE_REGISTRY_ATTR, registry)
        return registry

    @classmethod
    def retire_all(cls) -> list:
        """Retire every live instance in the process; returns those instances.

        The teardown hook a host calls BEFORE reloading the ecosystem packages,
        so no pre-reload instance is left servicing the activation gesture with
        caches the reload has invalidated. Reaches instances of any class
        generation — see :meth:`_live_registry`.

        Returning the instances rather than a count is what lets the caller
        dispose of them once their replacement is up (tentacle's
        ``Tcl.dispose_retired``) without reaching into the private registry.
        """
        instances = list(cls._live_registry())
        for instance in instances:
            try:
                instance.retire()
            except Exception:  # a dead C++ side is already inert — keep going
                pass
        return instances

    def retire(self) -> None:
        """Deactivate this instance because a newer MarkingMenu now owns
        activation input (re-instantiation in the same process — the dev-reload
        situation).

        Disposes the activation ``GlobalShortcut`` AND every shortcut this
        instance's Switchboard registered, cancels pending timers, and ends any
        live gesture (``hide`` releases grabs); the activation callbacks become
        no-ops. Irreversible by design — construct a new instance rather than
        reviving a retired one.

        The Switchboard sweep is what keeps a rebuild from stacking bindings:
        application-scoped shortcuts are parented to the HOST window, so Qt keeps
        them armed after this instance is gone, and the replacement's copies then
        ambiguate with them until the host restarts (see
        ``Switchboard.dispose_shortcuts``). Retiring is the moment this instance
        stops owning input — all of it, not just the activation key.
        """
        if self._retired:
            return
        self._retired = True
        self._live_registry().discard(self)
        self._dispose_activation_shortcut()
        try:
            self.sb.dispose_shortcuts()
        except Exception:  # a skewed/absent switchboard must not block retiring
            self.logger.debug("retire: shortcut disposal failed", exc_info=True)
        self._cancel_chord_release_timer()
        if self._pending_show_timer is not None:
            self._pending_show_timer.stop()
        try:
            self.hide()
        except Exception:
            self.logger.debug("retire: hide failed", exc_info=True)

    def _on_activation_press(self, buttons=None):
        """Handle the global shortcut press event.

        Parameters:
            buttons: Optional pre-resolved Qt mouse-button mask. Hosts whose
                native event loop owns the mouse (e.g. Blender's GHOST) pass the
                physically held buttons here — ``QApplication.mouseButtons()``
                only reflects events Qt itself has seen. ``None`` (the Qt
                shortcut path) falls back to the Qt query.
        """
        if self._retired:
            return
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

        target = MenuResolver.resolve_target_menu(
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
        if self._retired:
            return
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
            if win is not self and not win.has_tags(_MARKING_MENU_TAGS):
                if hasattr(win, "request_hide"):
                    win.request_hide()

        # Un-dims on the way down — hideEvent owns the restore (single owner:
        # the fade exists only while the overlay is up).
        self.hide()

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

        # 3. Launcher-surface policy for the pages this menu hosts.
        self._register_browser_entry_filter()

    def _register_browser_entry_filter(self) -> None:
        """Hide this menu's gesture pages from the launcher surface.

        Registers an editors post-build hook that applies
        :attr:`HOSTED_PAGE_PATTERNS` as the SwitchboardBrowser's structural
        exclude filter — every build of the browser on this switchboard
        carries the policy. Two reasons the pages don't belong in the list:

        * They're gesture surfaces this menu hosts, not standalone tools —
          launching one from a list is out of context (and pre-hosts_ui,
          re-hosted it destructively).
        * They emit entry-changed traffic on every show/hide during a
          gesture; structural exclusion short-circuits that in the model,
          so an open browser can't make the menu sluggish.

        Overridable policy: subclasses opt out with
        ``HOSTED_PAGE_PATTERNS = ()``; a user can clear it at runtime via
        the browser's public ``set_entry_filter()``. Degrades to a no-op on
        switchboards without an editors registry (test stubs, minimal
        hosts).
        """
        if not self.HOSTED_PAGE_PATTERNS:
            return
        editors = getattr(self.sb, "editors", None)
        add_hook = getattr(editors, "add_post_build_hook", None)
        if not callable(add_hook):
            return
        patterns = list(self.HOSTED_PAGE_PATTERNS)
        add_hook(
            "browser",
            lambda browser: browser.set_entry_filter(exc=patterns),
        )

    @classmethod
    def instance(
        cls, switchboard: Optional[Switchboard] = None, **kwargs
    ) -> "MarkingMenu":
        kwargs.setdefault("switchboard", switchboard)
        kwargs["singleton_key"] = id(switchboard)
        return super().instance(**kwargs)

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
        try:
            ui = self.sb.get_ui(name)
        except AttributeError as e:
            # An unresolvable name raises AttributeError out of the slot
            # resolver ("Slot class '<name>' not found"); degrade to None so a
            # stale target falls through to WindowManager delegation / None
            # return instead of raising (mirrors _cached_ui). get_ui lazily
            # LOADS the UI though, so this can also swallow a real defect in a
            # valid name's module — log the text so that stays diagnosable.
            self.logger.debug(f"get_ui('{name}') raised AttributeError: {e}")
            ui = None
        if ui and ui.has_tags(_MARKING_MENU_TAGS):
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
