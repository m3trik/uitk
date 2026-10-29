# !/usr/bin/python
# coding=utf-8
import os
import sys
import inspect
from typing import Any, Callable, Dict, List, Union, Optional, Iterable, Type
from xml.etree.ElementTree import ElementTree, Element, SubElement
import xml.etree.ElementTree as ET
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk

from uitk._bootstrap import Bootstrap

# Collaborators — private to this package; the Switchboard delegates to them:
from uitk.switchboard.slots import _Slots
from uitk.switchboard.shortcuts import _Shortcuts
from uitk.switchboard.widgets import _Gates, _Widgets
from uitk.switchboard.rules import _Rules
from uitk.switchboard.widget_values import _WidgetValues
from uitk.switchboard.control_groups import (
    _ControlGroups,
    _LOCK_ACTIVE_COLOR,
    _LOCK_INACTIVE_COLOR,
)
from uitk.switchboard.dialogs import _Dialogs
from uitk.switchboard.placement import _Placement
from uitk.switchboard.event_loop import _EventLoop
from uitk.switchboard.names import _Names
from uitk.switchboard.editors import _EditorRegistry
from uitk.switchboard.namespace import _UitkNamespace

# Generic infrastructure (shared with non-Switchboard widgets):
from uitk.switchboard.history import History
from uitk.managers.registry_manager import RegistryManager
from uitk.widgets.mixins.convert import ConvertMixin
from uitk.widgets.mixins.tooltip_mixin import TooltipNamespace
from uitk.managers.settings_manager import SettingsManager
from uitk.loaders import CompiledLoader, RuntimeLoader


class _Forward:
    """A Switchboard name that forwards to one of its collaborators' attributes.

    Keeps the private names that code outside the switchboard reads, and that one
    collaborator reads of another's (``sb._find_slots_class``, ``sb._commands``),
    on the collaborator that owns them. Reads, writes and deletes all forward, so
    ``mock.patch.object(sb, name)`` reaches the collaborator's own calls too.
    """

    def __init__(self, collaborator: str, name: str):
        self.collaborator, self.name = collaborator, name

    def __get__(self, sb, owner=None):
        if sb is None:
            return self
        return getattr(getattr(sb, self.collaborator), self.name)

    def __set__(self, sb, value):
        setattr(getattr(sb, self.collaborator), self.name, value)

    def __delete__(self, sb):
        delattr(getattr(sb, self.collaborator), self.name)


class Switchboard(QtCore.QObject, ptk.HelpMixin, ptk.LoggingMixin):
    """Switchboard is a dynamic UI loader and event handler for PyQt/PySide applications.
    It facilitates the loading of UI files, dynamic assignment of properties, and
    management of signal-slot connections in a modular and organized manner.

    This class streamlines the process of integrating UI files created with Qt Designer,
    custom widget classes, and Python slot classes into your application. It adds convenience
    methods and properties to each slot class instance, enabling easy access to the Switchboard's
    functionality within the slots class.

    Attributes:
        default_signals (dict): Which widgets are tracked, and default signals to be connected if no signals are overridden.
        module_dir (str): Directory of this module.
        default_dir (str): Default directory used for relative path resolution.

    Example:
        - Creating a subclass of Switchboard to load project UI and connect slots:
            class MyProjectUi:
                def __new__(cls, *args, **kwargs):
                    sb = Switchboard(*args, ui_source="my_project.ui", **kwargs)
                    ui = sb.loaded_ui.my_project
                    Bootstrap.set_translucent(ui)  # opaque where nothing composites
                    ui.set_flags(Tool=True, FramelessWindowHint=True, WindowStaysOnTopHint=True)
                    ui.style.set(theme="dark", style_class="translucentBgWithBorder")
                    return ui

        - Instantiating and displaying the UI:
            ui = MyProjectUi(parent)
            ui.show(pos="screen", app_exec=True)
    """

    QtCore = QtCore
    QtGui = QtGui
    QtWidgets = QtWidgets

    # The name vocabulary. The collaborators read it off the Switchboard at
    # call time, so a subclass that overrides one is honored everywhere.
    TAG_DELIMITER = "#"
    _UI_NAME_DELIMITER = "."
    #: Never read: nothing splits a UI name on it. Reading it warns.
    UI_NAME_DELIMITER = ptk.Deprecation.class_attribute(
        _UI_NAME_DELIMITER,
        "nothing -- no UI name is split on it",
        remove_in="1.10.0",
        since="2026-10-28",
    )
    SLOT_SUFFIX = "Slots"
    INIT_SUFFIX = "_init"
    STATE_PREFIX = "on_"

    # Lazy QApplication accessor. Previously this ran in the class body,
    # which constructed a QApplication as a side effect of merely importing
    # or referencing Switchboard — violating the package's no-side-effects-
    # on-import rule. Resolved on first access instead; works on both the
    # class (Switchboard.app) and instances (sb.app).
    @staticmethod
    def _new_app():
        """This process's own QApplication, with the standalone platform policy
        applied first (:meth:`Bootstrap.configure_platform`: X11 on a Wayland
        session, where the marking menu and popups can be placed)."""
        Bootstrap.configure_platform()
        return QtWidgets.QApplication(sys.argv)

    app = ptk.ClassProperty(
        lambda cls: QtWidgets.QApplication.instance() or cls._new_app()
    )

    # Emitted when a new UI enters ui_registry via register().
    on_ui_registered = QtCore.Signal(str)
    # Emitted after save_ui_tags() persists XML tags for an existing UI.
    on_ui_tags_changed = QtCore.Signal(str)
    # Emitted from ``_resolve_ui`` after a UI has been loaded and added
    # to ``loaded_ui``. Distinct from ``on_ui_registered`` (registry
    # population) — this one fires once per UI when it actually
    # materialises, regardless of which code path triggered the load
    # (browser launch button, marking menu, direct loaded_ui access).
    # UiHandler uses it to wire visibility-change tracking centrally,
    # so a UI shown via *any* path participates in row-state refresh.
    on_ui_loaded = QtCore.Signal(str)
    # Emitted when a launchable handler's full entry set may have changed
    # (registration / unregistration). Payload: handler attr name on
    # ``self.handlers``. Subscribers should re-pull entries for that handler.
    on_handler_entries_changed = QtCore.Signal(str)
    # Emitted when one entry's live state changed (visibility, status).
    # Payload: (handler_attr_name, entry_name). Lets subscribers refresh
    # a single row instead of rebuilding the handler's full entry list.
    on_handler_entry_changed = QtCore.Signal(str, str)

    @ptk.Deprecation.parameter(
        "ui_name_delimiters", drop=True, remove_in="1.10.0", since="2026-10-28"
    )
    def __init__(
        self,
        parent=None,
        ui_source=None,
        slot_source=None,
        widget_source=None,
        icon_source=None,
        handlers: dict = None,
        tag_delimiter: str = None,
        ui_name_delimiters: str = None,
        log_level: str = "warning",
        base_dir=None,
        loader="runtime",
        context_tags=None,
        on_missing_slot=None,
    ) -> None:
        """Initialize a Switchboard and populate its source registries.

        Parameters:
            parent (QObject): Optional Qt parent for this QObject.
            ui_source: Source of ``.ui`` files — a module, directory, or file
                path (or list thereof). Loaded lazily via ``loaded_ui``.
            slot_source: Source of slot classes (module/dir/file/class) whose
                methods are wired to matching widgets.
            widget_source: Source of custom widget classes to register in
                addition to this package's built-ins.
            icon_source: Source of icon files to register.
            handlers (dict): Optional ``{attr_name: handler}`` mapping to
                register on ``self.handlers`` after initialization. A ``None``
                value registers nothing; ``{"editor": None}`` opts out of the
                default :class:`EditorHandler` (the bundled editors' rows in
                the UI Browser).
            tag_delimiter (str): Override for the name tag delimiter
                (defaults to ``TAG_DELIMITER``, ``'#'``).
            ui_name_delimiters (str): Deprecated, removed in 1.10.0: nothing
                reads it. Passing it by keyword warns and is ignored.
            log_level (str): Logging level for this instance. Default ``"warning"``.
            base_dir: Base directory for resolving relative source paths. When
                ``None``, resolves relative to the caller's module.
            loader (str): UI loader strategy — ``"runtime"`` (default) or
                ``"compiled"``.
            context_tags: Feature tags this host satisfies (e.g. ``{"maya"}``).
                Widgets whose ``requires`` property matches none of these are
                hidden at registration. Empty disables filtering.
            on_missing_slot: ``callable(widget)`` invoked when ``connect_slot``
                finds no slot for a signal-bearing widget. ``None`` is silent
                (production default); set ``UITK_MARK_MISSING_SLOTS`` to install
                the built-in grey-out marker.
        """
        super().__init__(parent)
        self.logger.setLevel(log_level)
        # Collaborators: each subsystem's own state and behavior, behind the
        # public methods below. Each is handed what it needs -- this facade only
        # where it reads facade state that changes after construction. One that
        # holds the facade calls the public methods through it, so an override or
        # patch of ``sb.<method>`` reaches every caller, as it did with mixins.
        # A collaborator not handed the facade gets getters, never a captured value,
        # so ``sb.use_logger()`` or a reassigned ``default_signals`` reaches it too.
        self._event_loop = _EventLoop(lambda: self.logger)
        self._names = _Names(self)
        # The rules and control groups read values the one way _WidgetValues does.
        self._values = _WidgetValues(lambda: self.logger, lambda: self.default_signals)
        self._rules = _Rules(lambda: self.logger, self._names, self._values)
        self._dialogs = _Dialogs(self)
        self._gates = _Gates(self)
        self._widgets = _Widgets(self)
        self._shortcuts = _Shortcuts(self)
        self._slots = _Slots(self)
        self._groups = _ControlGroups(self, self._values)

        # Visibility-policy context: the feature tags this host satisfies (e.g. {"maya"}).
        # Widgets carrying a `requires` Designer property are hidden at registration when
        # none of their tags match (see apply_visibility_policy). Empty = no filtering,
        # so a standalone/dev session shows everything.
        self.context_tags = set(context_tags) if context_tags else set()

        # Missing-slot policy hook: callable(widget) invoked when connect_slot finds no
        # slot for a signal-bearing widget. None = silent (production default). Setting
        # UITK_MARK_MISSING_SLOTS in the environment installs the built-in grey-out
        # marker (a live "not-yet-built" map for development).
        if on_missing_slot is None and os.getenv("UITK_MARK_MISSING_SLOTS"):
            on_missing_slot = self.mark_missing_slot
        self.on_missing_slot = on_missing_slot

        # Ensure a QApplication exists before any UI work. The lazy ``app``
        # class property creates one on first access; touching it here keeps
        # the old guarantee (an app always exists once a Switchboard does)
        # without the old import-time side effect.
        _ = self.app

        # A host that owns the application (Maya) quits without finalizing
        # Python; the guard keeps that exit out of shiboken's teardown fault.
        from uitk.managers.host_exit_guard import HostExitGuard

        HostExitGuard.arm()

        # Ensure plain QtWidgets (e.g. unpromoted QLineEdit in .ui files) expose
        # `widget.option_box`. patch_widget_class is idempotent (no-op if the
        # class already has the property), so repeated Switchboard inits are safe.
        from uitk.widgets.optionBox.option_box_manager import OptionBoxManager

        OptionBoxManager.patch_common_widgets()

        self._loader = self._build_loader(loader)

        self.tag_delimiter = tag_delimiter or self.TAG_DELIMITER
        self.ui_name_delimiters = ui_name_delimiters or self._UI_NAME_DELIMITER
        self.registry = RegistryManager()
        if base_dir is None:
            base_dir = 1 if not __name__ == "__main__" else 0

        # Initialize handlers namespace
        self.handlers = type("Handlers", (), {})()
        # Subset of handlers exposing the launchable contract; populated
        # by ``register_handler`` and consumed by ``iter_handler_entries``.
        self._launchable_handlers: dict = {}

        # Forward the pre-existing UI-specific signals into the new
        # unified ones so subscribers can listen on the unified pair
        # alone. The UI-specific signals remain emitted for backward
        # compat with code already wired to them.
        self.on_ui_registered.connect(
            lambda n: self.on_handler_entry_changed.emit("ui", n)
        )
        self.on_ui_tags_changed.connect(
            lambda n: self.on_handler_entry_changed.emit("ui", n)
        )

        # Store handlers for registration after configurable is initialized
        self._pending_handlers = handlers

        # Tag overlays must exist before any registry population.
        self._source_tags = {}  # {normalized_dir_path: set_of_tags}
        # {ui_name: set_of_tags} parsed from the .ui's <uitk_tags> property.
        # Populated lazily on first access via ``_get_ui_tags`` to avoid
        # paying an N×ET.parse cost at init for UIs that may never load.
        self._ui_tags: dict = {}

        # Define source configuration
        sources = self._get_registry_config(
            ui_source, slot_source, widget_source, icon_source
        )

        # Initialize registries
        for descriptor, config in sources.items():
            objects = config.pop("objects")
            self.registry.create(
                descriptor,
                objects,
                base_dir=base_dir,
                **config,
            )

        # Include this package's widgets (and subpackages like sequencer/) and
        # default icons. ``base_dir=self`` would resolve to this module's
        # directory (``uitk/switchboard/``); the assets live one level up at
        # the ``uitk/`` package root, so anchor on the package directory.
        _UITK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.registry.widget_registry.extend(
            "widgets", base_dir=_UITK_DIR, recursive=True
        )
        self.registry.icon_registry.extend("icons", base_dir=_UITK_DIR)

        self.loaded_ui = ptk.NamespaceHandler(
            self,
            "loaded_ui",
            resolver=self._resolve_ui,
            use_weakref=True,
        )  # All loaded ui.
        self.registered_widgets = ptk.NamespaceHandler(
            self,
            "registered_widgets",
            resolver=self._widgets.resolve_widget,
            use_weakref=True,
        )  # All registered widgets.
        self.registered_icons = ptk.NamespaceHandler(
            self,
            "registered_icons",
            resolver=self._widgets.resolve_icon,
            use_weakref=True,
        )  # All registered icons.

        self.slot_instances = ptk.NamespaceHandler(
            self,
            "slot_instances",
            resolver=self.get_slots_instance,
        )  # All slot instances.

        self.settings = SettingsManager(namespace="switchboard")
        self.configurable = self.settings.branch("configurable")  # Persistent config

        # Rich-text tooltip surface: the DSL (fmt/kbd/hl/placeholder_preview) plus
        # bind(), including the batch form that resolves a "chk000-2" range — which
        # only the Switchboard can do. ``MainWindow.register_widget`` stamps the
        # per-widget convenience (``widget.tooltip``) that delegates back here, the
        # same split as call_slot/init_slot. Also spares consumers an import of a
        # uitk mixin module, like the Qt passthroughs above.
        self.tooltip = TooltipNamespace(self)

        self._current_ui = None
        # Ordered UI history. Weak refs so a closed UI is freed (the prior list
        # held strong refs, pinning up to maxlen windows alive and defeating the
        # weakref design of loaded_ui).
        self._ui_history = History(maxlen=200, key=lambda u: u.objectName(), weak=True)
        # Commands and the cold-start slot standins bind once a host window
        # exists (see _Shortcuts), so registration order is free.
        self.on_ui_loaded.connect(self._shortcuts.bind_pending_commands)
        self.on_ui_loaded.connect(self._shortcuts.bind_deferred_slot_shortcuts)
        self.convert = ConvertMixin()

        # Register any handlers passed during construction (after configurable is ready)
        if self._pending_handlers:
            for name, obj in self._pending_handlers.items():
                if obj is None or getattr(self.handlers, name, None):
                    continue
                # Instantiate if class, use directly if instance
                if isinstance(obj, type):
                    if hasattr(obj, "instance"):
                        instance = obj.instance(switchboard=self)
                    else:
                        instance = obj(switchboard=self)
                    defaults = getattr(obj, "DEFAULTS", {})
                else:
                    instance = obj
                    defaults = getattr(instance, "DEFAULTS", {})
                self.register_handler(name, instance, defaults)
            self._pending_handlers = None

        # Auto-register a default UiHandler so any code that consumes the
        # unified launcher surface (``iter_handler_entries``) sees the
        # ui_registry without forcing every caller to wire UiHandler
        # themselves. Subclasses passed via ``handlers={"ui": MyUiHandler}``
        # already populate this slot and are preserved. Lazy-imported here
        # to avoid an import cycle (UiHandler imports Switchboard).
        if not getattr(self.handlers, "ui", None):
            from uitk.handlers.ui_handler import UiHandler

            self.register_handler(
                "ui",
                UiHandler.instance(switchboard=self),
                getattr(UiHandler, "DEFAULTS", {}),
            )

        # Likewise the bundled editors, so the launcher lists them -- the UI
        # Browser included. ``handlers={"editor": None}`` opts out.
        if "editor" not in (handlers or {}) and not getattr(
            self.handlers, "editor", None
        ):
            from uitk.handlers.editor_handler import EditorHandler

            self.register_handler(
                "editor",
                EditorHandler.instance(switchboard=self),
                EditorHandler.DEFAULTS,
            )

        # Shortcut/command overrides are persisted host-namespaced (Maya and
        # Blender share one QSettings backend). Fold any legacy un-suffixed
        # overrides into this host's namespace BEFORE commands register/bind, so
        # a persisted binding from a pre-namespacing session still applies.
        # Best-effort: a settings-store hiccup must degrade to "no migration",
        # never crash the whole UI at construction.
        try:
            self._shortcuts.migrate_shortcuts_to_host_namespace()
        except Exception:
            self.logger.warning(
                "[shortcuts] host-namespace migration failed", exc_info=True
            )

        # Built-in navigation commands — UI-less, shortcut-bindable actions that
        # surface in the shortcut editor for every host. Both ship **unbound**:
        # the user assigns a key in the editor (no surprise default binding).
        # Host packages add their own via register_command().
        self.register_command(
            "reopen_last_ui",
            self.show_prev_ui,
            label="Reopen Last UI",
            doc="Re-show the last non-transient UI.",
        )
        self.register_command(
            "repeat_last_command",
            self.repeat_last,
            label="Repeat Last Command",
            doc="Re-invoke the last slot.",
        )

    # Methods every launchable handler must expose. Validated by
    # ``register_handler`` (duck-typed; subclassing
    # ``LaunchableHandlerProtocol`` is optional). Mirrors
    # ``_LOADER_CONTRACT`` so the same enforcement pattern shows up in
    # one place for both extension points.
    _LAUNCHABLE_CONTRACT = ("entries", "launch", "close", "is_visible")

    def register_handler(self, name: str, instance, defaults: dict = None):
        """Register a handler instance and apply defaults to its config.

        If *instance* implements the launchable contract
        (:attr:`_LAUNCHABLE_CONTRACT`) it's also added to the unified
        entry surface — :meth:`iter_handler_entries` will yield from it
        and the browser will list its entries.
        """
        setattr(self.handlers, name, instance)
        if defaults:
            # Apply defaults to the configuration branch matching the handler name
            self.configurable.branch(name).set_defaults(defaults)
        if self._is_launchable(instance):
            self._launchable_handlers[name] = instance
            # Coarse re-read so any browser already wired to the signal
            # picks up the new handler's entries without manual refresh.
            self.on_handler_entries_changed.emit(name)

    @classmethod
    def _is_launchable(cls, instance) -> bool:
        """Return True iff *instance* exposes the full launchable contract.

        Each contract method must exist and be callable on the instance.
        A partial implementation is rejected: a handler that ships
        ``entries()`` but not ``close()`` would crash the browser when
        the user tried to dismiss a row.
        """
        return all(
            callable(getattr(instance, m, None)) for m in cls._LAUNCHABLE_CONTRACT
        )

    def iter_handler_entries(self):
        """Yield every :class:`HandlerEntry` from every launchable handler.

        Single iteration point for clients (browser, marking menu, …)
        that need a unified view across handler boundaries. Errors from
        an individual handler are logged and skipped so one broken
        handler doesn't blank the launcher.
        """
        for handler_name, handler in self._launchable_handlers.items():
            try:
                yield from handler.entries()
            except Exception:
                self.logger.warning(
                    f"[iter_handler_entries] {handler_name}.entries() failed",
                    exc_info=True,
                )

    _LOADER_CLASSES = {
        "compiled": CompiledLoader,
        "runtime": RuntimeLoader,
    }
    _LOADER_CONTRACT = ("load", "read_ui_tags", "on_tags_written")

    def _build_loader(self, loader):
        """Resolve the ``loader`` kwarg to a delegate instance.

        Accepts:
          - ``"runtime"`` (default) — :class:`RuntimeLoader`. ``QtUiTools.QUiLoader``
            reads .ui XML directly each time. No on-disk artifact.
          - ``"compiled"`` — :class:`CompiledLoader`. The active binding's uic
            produces a hash-stamped _ui.py per .ui; loads through Python imports.
          - A class implementing the loader contract (instantiated with
            ``self``) — for custom delegates.
          - An already-constructed delegate instance — used as-is.

        Both built-ins implement the same three-method contract:
        ``load(file)``, ``read_ui_tags(path)``, ``on_tags_written(path)``.
        Custom delegates passed in are validated upfront against this
        contract so a typo'd class fails here, not at first UI load.
        """
        if isinstance(loader, str):
            cls = self._LOADER_CLASSES.get(loader)
            if cls is None:
                raise ValueError(
                    f"Unknown loader {loader!r}; expected one of "
                    f"{sorted(self._LOADER_CLASSES)}"
                )
            instance = cls(self)
        elif isinstance(loader, type):
            instance = loader(self)
        else:
            # Caller passed a constructed instance.
            instance = loader
        missing = [
            m for m in self._LOADER_CONTRACT if not callable(getattr(instance, m, None))
        ]
        if missing:
            raise TypeError(
                f"Loader {type(instance).__name__} is missing required "
                f"method(s): {missing}. The loader contract is "
                f"{list(self._LOADER_CONTRACT)}."
            )
        return instance

    @property
    def active_ui(self) -> Optional[QtWidgets.QWidget]:
        """Return the currently set UI, or None — no auto-load, no warning.

        Use this when None is a valid state the caller will handle (e.g. the
        marking menu probing whether anything is shown yet). ``current_ui``
        is for callers that semantically require a UI and benefit from the
        auto-load + warning when one isn't set.
        """
        return self._current_ui

    @property
    def current_ui(self) -> QtWidgets.QWidget:
        """Get or load the current UI if not already set."""
        if self._current_ui is not None:
            return self._current_ui

        # If only one UI is loaded, set that UI as current.
        if len(self.loaded_ui.keys()) == 1:
            ui = next(iter(self.loaded_ui.values()))
            self.current_ui = ui
            return ui

        # If only one UI file exists but hasn't been loaded yet, load and set it.
        filepaths = self.registry.ui_registry.get("filepath")
        if filepaths and len(filepaths) == 1:
            ui_filepath = filepaths[0]
            newly_loaded_ui = self.load_ui(ui_filepath)
            name = ptk.format_path(ui_filepath, "name")
            ui = self.add_ui(name, widget=newly_loaded_ui, path=ui_filepath)
            self.current_ui = ui
            return ui

        self.logger.warning("No current UI set.")
        return None

    @current_ui.setter
    def current_ui(self, ui: QtWidgets.QWidget) -> None:
        """Set the current UI and record it in UI history."""
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")

        # Avoid re-registering the same UI
        if self._current_ui is ui:
            return

        self._current_ui = ui
        self._ui_history.add(ui)  # History caps + holds weakly

        # A UI becoming current means a window is now on screen — a reliable
        # moment to bind any command / cold-start slot standin that deferred
        # for lack of a visible host. ``on_ui_loaded`` fires while a UI is still
        # hidden, so a persisted app-scoped binding can otherwise miss its only
        # bind chance on a host that shows no window until after load. Both
        # methods are cheap no-ops once everything is bound.
        self._shortcuts.bind_pending_commands()
        self._shortcuts.bind_deferred_slot_shortcuts()

    @property
    def prev_ui(self) -> Optional[QtWidgets.QWidget]:
        """Get the previous UI from history — the one before the current UI.

        The ``current_ui`` setter appends the now-current UI to history, so the
        last deduped entry is always the *current* UI; the previous one is the
        second-most-recent distinct entry.

        Returns:
            (obj) The previous UI, or ``None`` when history holds fewer than
            two distinct UIs.
        """
        hist = self.ui_history(allow_duplicates=False)
        return hist[-2] if len(hist) > 1 else None

    @property
    def prev_slot(self) -> object:
        """Get the last called slot.

        Returns:
            (obj) method.
        """
        try:
            return self.slot_history(-1)

        except IndexError:
            return None

    @property
    def visible_windows(self) -> set:
        """Return all currently visible MainWindow instances."""
        visible = {ui for ui in self.loaded_ui.values() if ui.isVisible()}
        self.logger.debug(
            f"[visible_windows] {len(visible)} visible window(s): {[u.objectName() for u in visible]}"
        )
        return visible.copy()

    def _resolve_ui(self, attr_name):
        """Resolver for dynamically loading UIs when accessed via NamespaceHandler.

        A name resolves to its ``.ui`` file, else to its Slots class (a UI built
        in code), else to the UI the active UI handler builds on demand (a name
        :meth:`ui_name_resolves` reports through the handler's ``can_resolve``,
        e.g. mayatk's native Maya menus). A UI with no Slots class is the normal
        case: such a name needs none to resolve. A claimed name the handler fails
        to build raises an ``AttributeError`` naming the handler, not the Slots
        miss.
        """
        self.logger.debug(f"[{attr_name}] Resolving UI")

        actual_ui_name = self.find_ui_filename(attr_name, unique_match=True)
        if not actual_ui_name:
            try:
                return self._resolve_ui_using_slots(attr_name)
            except AttributeError:
                ui = self._widgets.resolve_handler_ui(attr_name)
                if ui is None:
                    raise
                return ui

        ui_filepath = self.registry.ui_registry.get(
            filename=actual_ui_name, return_field="filepath"
        )
        if not ui_filepath:
            raise AttributeError(f"Unable to resolve filepath for '{attr_name}'.")

        loaded_ui = self.load_ui(ui_filepath)
        name = ptk.format_path(ui_filepath, "name")
        ui = self.add_ui(name, widget=loaded_ui, path=ui_filepath)

        self.logger.debug(f"[{name}] UI loaded successfully from {ui_filepath}")
        try:
            self.on_ui_loaded.emit(name)
        except Exception:
            # Signal emission must not block the load — log and move on.
            self.logger.debug(f"[on_ui_loaded] emit failed for {name!r}", exc_info=True)
        return ui

    def _resolve_ui_using_slots(self, attr_name) -> QtWidgets.QWidget:
        if getattr(self, "_resolving_ui", None) == attr_name:
            raise RuntimeError(f"Recursive resolution detected for key: '{attr_name}'")
        self._resolving_ui = attr_name
        try:
            found_slots = self._slots.find_slots_class(attr_name)
            if not found_slots:
                self.logger.debug(
                    f"[{attr_name}] No slot class found during resolution"
                )
                raise AttributeError(f"Slot class '{attr_name}' not found.")

            ui = self.add_ui(name=attr_name)
            self.get_slots_instance(ui)
            return ui
        finally:
            self._resolving_ui = None

    def _get_registry_config(
        self, ui_source, slot_source, widget_source, icon_source
    ) -> dict:
        """Return the configuration for the Switchboard registries.

        ``validate``/``path_type`` are stored on each registry's metadata so they reach
        ``RegistryManager.resolve_path`` on every collection — including the ones driven by
        ``FileRegistry.extend``, which merges the registry's stored metadata. Without them the
        registries collected at ``validate=0`` and a source directory that didn't exist was
        reported (fatally, for the class-scanning registries) from several frames deep instead of
        being named where the caller could act on it.
        """
        return {
            "ui_registry": {
                "objects": ui_source,
                "inc_files": "*.ui",
                "validate": 1,
                "path_type": "UI",
            },
            "slot_registry": {
                "objects": slot_source,
                "fields": ["classname", "classobj", "filename", "filepath"],
                "inc_files": "*.py",
                "exc_files": "*_ui.py",
                "validate": 1,
                "path_type": "Slot",
            },
            "widget_registry": {
                "objects": widget_source,
                "fields": ["classname", "classobj", "filename", "filepath"],
                "inc_files": "*.py",
                "exc_files": "*_ui.py",
                "validate": 1,
                "path_type": "Widget",
            },
            "icon_registry": {
                "objects": icon_source,
                "inc_files": ["*.svg", "*.png", "*.jpg", "*.jpeg", "*.bmp", "*.ico"],
                "validate": 1,
                "path_type": "Icon",
            },
        }

    def register(
        self,
        ui_location=None,
        slot_location=None,
        widget_location=None,
        icon_location=None,
        base_dir=1,
        recursive: bool = False,
        validate=1,
        tags=None,
        exclude=None,
    ):
        """Add new locations to the Switchboard registries.

        Args:
            ui_location: Path(s) or module(s) containing .ui files.
            slot_location: Path(s) or module(s) containing slot classes.
            widget_location: Path(s) or module(s) containing custom widgets.
            icon_location: Path(s) or module(s) containing icons.
            base_dir: Base directory for relative paths. Defaults to caller's directory.
            recursive: If True, directory locations are scanned recursively.
            validate: How loudly an unusable location is reported — 0=silent, 1=warn (default),
                2=raise ``FileNotFoundError``. It does NOT decide whether a missing location is
                survivable: one is always skipped rather than registered, at every level.
            tags: Optional set/list of tags to apply to UIs loaded from ui_location.
                  When a UI file from this location is loaded via add_ui(), these
                  tags are automatically merged into its tag set.
            exclude: File-name pattern(s) (shell wildcards) this call leaves out of
                  every location it registers, on top of each registry's own
                  exclusions: a host registering a shared folder minus the files it
                  does not serve (``"light_rig.*"`` drops ``light_rig.ui`` from
                  ui_location and ``light_rig.py`` from slot_location).
        """
        source_tags_changed = False
        if tags and ui_location:
            tag_set = set(ptk.make_iterable(tags))
            for loc in ptk.make_iterable(ui_location):
                if inspect.ismodule(loc) and hasattr(loc, "__file__"):
                    loc = os.path.dirname(loc.__file__)
                if isinstance(loc, str):
                    resolved = os.path.normpath(os.path.abspath(loc))
                    if self._source_tags.get(resolved) != tag_set:
                        self._source_tags[resolved] = tag_set
                        source_tags_changed = True
        locations = {
            "ui_registry": (ui_location, "UI"),
            "slot_registry": (slot_location, "Slot"),
            "widget_registry": (widget_location, "Widget"),
            "icon_registry": (icon_location, "Icon"),
        }

        for registry_name, (location, type_name) in locations.items():
            if not location:
                continue

            # Check if we should add this location
            # Note: FileRegistry.extend handles duplicates if configured,
            # but we can do a quick check here if it's a single path string.
            # However, since location can be a list or module, simple string check isn't enough.
            # We rely on FileRegistry/RegistryManager to resolve and handle it.

            # Strict mode only. ``extend`` below now resolves at this same ``validate`` level, so
            # for the warn level this pre-pass would emit a SECOND identical warning for one bad
            # source — undercutting the point of a precise message. It is kept for ``2`` so a
            # strict register fails before the lazy registry creation below mutates any state.
            # (It is also the weaker check of the two: a module with no ``__file__`` yields None
            # here and is skipped silently, where ``resolve_path``'s own object branch reports it.)
            def _validate_item(item):
                path_to_check = item
                if inspect.ismodule(item):
                    path_to_check = (
                        os.path.dirname(item.__file__)
                        if hasattr(item, "__file__")
                        else None
                    )
                elif inspect.isclass(item):
                    # A class in a module gone from sys.modules (pythontk's
                    # loose-file loader) has no file: skipped, like a
                    # file-less module above.
                    try:
                        path_to_check = inspect.getfile(item)
                    except (TypeError, OSError):
                        path_to_check = None

                if path_to_check:
                    self.registry.resolve_path(
                        path_to_check,
                        base_dir=base_dir,
                        validate=validate,
                        path_type=type_name,
                    )

            if validate > 1:
                for item in ptk.make_iterable(location):
                    _validate_item(item)

            # Perform the extension
            registry = getattr(self.registry, registry_name, None)
            if registry is None:
                # Lazily create the registry if it doesn't exist
                config = self._get_registry_config(None, None, None, None).get(
                    registry_name, {}
                )
                config.pop("objects", None)
                registry = self.registry.create(registry_name, None, **config)

            # Track UI registry entries before extension so we can emit a
            # signal for newly added entries (and parse their XML tags).
            prev_ui_names = (
                set(self.registry.ui_registry.get("filename") or [])
                if registry_name == "ui_registry"
                else None
            )

            # ``exclude`` adds to the registry's own exclusions: a per-call
            # ``exc_files`` replaces the stored one in ``extend``, so passed bare
            # it would let a slot scan pick up ``*_ui.py``.
            options = {}
            if exclude:
                options["exc_files"] = [
                    *ptk.make_iterable(registry.metadata.get("exc_files") or ()),
                    *ptk.make_iterable(exclude),
                ]

            # Forward validate/path_type: without them ``extend`` merges the registry's stored
            # metadata and re-resolves at whatever that carries, so the level computed above was
            # discarded — ``validate=1`` warned and then raised anyway, leaving only 0 and 2
            # reachable despite all three being documented and unit-tested on ``resolve_path``.
            registry.extend(
                location,
                base_dir=base_dir,
                recursive=recursive,
                validate=validate,
                path_type=type_name,
                **options,
            )
            self.logger.debug(f"[register] {type_name} location added: {location}")

            if registry_name == "ui_registry":
                self._ingest_new_ui_entries(prev_ui_names)
                # Source tags shifted but no new filenames added — the
                # per-entry signal didn't fire for existing rows. Fire
                # the coarse signal so subscribers (browser model) re-pull
                # entries and pick up the updated inherited_tags.
                if source_tags_changed:
                    self.on_handler_entries_changed.emit("ui")

    def load_all_ui(self) -> list:
        """Extends the 'load_ui' method to load all UI from a given path.

        Returns:
            (list) QWidget(s).
        """
        filepaths = self.registry.ui_registry.get("filepath")
        return [self.load_ui(f) for f in filepaths]

    def load_ui(self, file: str) -> QtWidgets.QMainWindow:
        """Load a UI from the given .ui path via the configured loader delegate."""
        return self._loader.load(file)

    def _add_existing_wrapped_ui(
        self, window: QtWidgets.QMainWindow, name: Optional[str] = None
    ) -> QtWidgets.QMainWindow:
        if name:
            window.setObjectName(name)

        if window.objectName() in self.loaded_ui:
            self.logger.warning(
                f"[{window.objectName()}] UI already exists in this Switchboard"
            )
            return self.loaded_ui[window.objectName()]

        self.loaded_ui[window.objectName()] = window

        if not hasattr(window, "_slots"):
            try:
                self.get_slots_instance(window)
            except Exception as e:
                self.logger.debug(
                    f"[{window.objectName()}] Failed to set slot class: {e}"
                )

        self.logger.debug(f"[{window.objectName()}] Existing wrapped window added")
        return window

    def add_ui(
        self,
        name: str,
        widget: Optional[QtWidgets.QWidget] = None,
        parent: Optional[QtWidgets.QWidget] = None,
        tags: set = None,
        path: str = None,
        overwrite: bool = False,
        **kwargs,
    ) -> QtWidgets.QMainWindow:
        if name in self.loaded_ui:
            if not overwrite:
                self.logger.debug(f"[{name}] UI already exists. Returning existing.")
                return self.loaded_ui[name]

            self.logger.debug(f"[{name}] Overwriting existing UI")
            del self.loaded_ui[name]

        if isinstance(widget, self.registered_widgets.MainWindow):
            return self._add_existing_wrapped_ui(widget, name=name)

        central_widget = (
            widget.centralWidget()
            if isinstance(widget, QtWidgets.QMainWindow) and widget.centralWidget()
            else widget
        )

        tags = set(tags or (self.get_tags_from_name(name) if name else set()))
        # Capture the .ui filepath before format_path coerces it to a
        # directory — _get_ui_tags needs the file to read XML tags from.
        ui_file_path = path if (path and os.path.isfile(path)) else None
        path = ptk.format_path(path, "path") if path else None

        # Merge source tags from registered directories
        if path and self._source_tags:
            norm_path = os.path.normpath(os.path.abspath(path))
            for src_dir, src_tags in self._source_tags.items():
                # is_under also normalizes case, so a registered source dir
                # whose casing differs from the resolved path still matches.
                if ptk.FileUtils.is_under(norm_path, src_dir):
                    tags.update(src_tags)
                    break

        # Merge tags parsed from the .ui file's <property name="uitk_tags">
        # (lazy: read on first request, cached thereafter).
        if name:
            tags.update(self._get_ui_tags(name, ui_file_path))

        # Don't add footer to stacked UIs (startmenu/submenu)
        if tags and any(tag in tags for tag in ["startmenu", "submenu"]):
            kwargs.setdefault("add_footer", False)

        main_window = self.registered_widgets.MainWindow(
            name=name,
            switchboard_instance=self,
            central_widget=central_widget,
            parent=parent,
            tags=tags,
            path=path,
            log_level=self.logger.level,
            # Host-namespaced (see _Shortcuts.host_namespaced_branch):
            # QSettings is shared across processes by (org, app), so without this a
            # Maya and a Blender session loading a same-named panel (e.g. "mirror")
            # would read/write the SAME widget-state keys and collide -- mirrors the
            # fix already applied to shortcuts/marking-menu bindings so all three
            # can't drift apart.
            settings=self.settings.branch(self._shortcuts.host_namespaced_branch(name)),
            **kwargs,
        )
        self.loaded_ui[name] = main_window

        self.logger.debug(
            f"[{main_window.objectName()}] MainWindow added with Tags={main_window.tags}, Path={main_window.path}"
        )
        return main_window

    def get_ui(self, ui=None) -> QtWidgets.QWidget:
        """Get a dynamic UI using its string name, or if no argument is given, return the current UI."""
        if isinstance(ui, QtWidgets.QWidget):
            self.logger.debug(f"[{ui.objectName()}] get_ui received QWidget directly")
            return ui

        elif isinstance(ui, str):
            self.logger.debug(f"[{ui}] Resolving get_ui by name")
            return getattr(self.loaded_ui, ui)

        elif isinstance(ui, (list, set, tuple)):
            return [self.get_ui(u) for u in ui]

        elif ui is None:
            if self._current_ui:
                self.logger.debug(
                    f"[{self._current_ui.objectName()}] Returning current_ui"
                )
            else:
                self.logger.debug("[get_ui] No current_ui set")
            return self.current_ui

        else:
            raise ValueError(
                f"Invalid datatype for ui: Expected str or QWidget, got {type(ui)}"
            )

    def get_ui_relatives(
        self, ui, upstream=False, exact=False, downstream=False, reverse=False
    ):
        """Get UIs related to the given UI via shared base name.

        Two UIs are "related" when they share the same base name (the portion
        before the first tag delimiter ``#``).  Direction filters control which
        relatives are returned based on tag depth:

        * **upstream** – relatives with *fewer* tag segments (ancestors).
        * **downstream** – relatives with *more* tag segments (children/submenus).
        * **exact** – relatives with the *same number* of tag segments.

        Parameters:
            ui (str or QWidget): Target UI name or object.
            upstream (bool): Include higher-level ancestors.
            exact (bool): Include only exact-depth matches.
            downstream (bool): Include children/submenus.
            reverse (bool): Reverse order of matches.

        Returns:
            list[str] or list[QWidget]: Matching UI names or loaded QWidget
                objects, depending on input type.
        """
        # --- Step 1: Resolve target name ---
        if isinstance(ui, QtWidgets.QWidget):
            target_name = ui.objectName()
            return_type = "object"
        elif isinstance(ui, str):
            target_name = ui
            return_type = "string"
        else:
            raise TypeError(f"Invalid type for 'ui': {type(ui)}")

        if not target_name:
            return []

        # --- Step 2: Find all UIs sharing the same base name ---
        target_base = self.get_base_name(target_name)
        ui_filenames = self.registry.ui_registry.get("filename") or []

        target_depth = target_name.count(self.tag_delimiter)
        matched_names = []

        for fn in ui_filenames:
            if fn == target_name:
                continue  # Skip self
            if self.get_base_name(fn) != target_base:
                continue  # Different base name

            depth = fn.count(self.tag_delimiter)
            if upstream and depth < target_depth:
                matched_names.append(fn)
            elif downstream and depth > target_depth:
                matched_names.append(fn)
            elif exact and depth == target_depth:
                matched_names.append(fn)

        # Sort by depth (ascending) then reverse if requested
        matched_names.sort(key=lambda x: x.count(self.tag_delimiter), reverse=reverse)

        # --- Step 3: Return matching names or UI instances ---
        if return_type == "string":
            return matched_names
        return self.get_ui(matched_names)

    def find_ui_filename(
        self, legal_name: str, unique_match: bool = False
    ) -> Union[str, List[str], None]:
        """Convert the given legal name to its original name(s) by searching the UI files."""
        # The inverse of convert_to_legal_name, from the rule's owner: each
        # ``_`` may have been any non-alphanumeric character.
        pattern = ptk.StrUtils.legal_name_matcher(legal_name)
        filenames = self.registry.ui_registry.get("filename")
        matches = [name for name in filenames if pattern.fullmatch(name)]

        if unique_match:
            if len(matches) != 1:
                self.logger.debug(
                    f"[find_ui_filename] Ambiguous or no match for '{legal_name}': {matches}"
                )
                return None
            self.logger.debug(
                f"[find_ui_filename] Unique match for '{legal_name}': {matches[0]}"
            )
            return matches[0]
        else:
            self.logger.debug(
                f"[find_ui_filename] Matches for '{legal_name}': {matches}"
            )
            return matches

    # ── Tag persistence ──────────────────────────────────────────────

    UITK_TAGS_PROPERTY = "uitk_tags"

    def _ingest_new_ui_entries(self, prev_ui_names, emit=True):
        """Emit ``on_ui_registered`` for UI entries newly added to the registry.

        Called after each registry extension. Tag XML is *not* parsed here —
        ``_ui_tags[name]`` is populated lazily by :meth:`_get_ui_tags` on
        first access. Eager parsing at init was an N×ET.parse cost paid for
        every UI in the registry whether it ever loaded or not; under the
        runtime loader that cost dominated startup.

        Listeners (e.g. the switchboard browser model) only need the
        notification — they query tags themselves when the user inspects
        a row. Pass emit=False during __init__ where no listener exists.
        """
        if not emit:
            return

        if prev_ui_names is None:
            prev_ui_names = set()

        ui_registry = getattr(self.registry, "ui_registry", None)
        if ui_registry is None:
            return

        for entry in list(ui_registry.named_tuples):
            name = getattr(entry, "filename", None)
            if not name or name in prev_ui_names:
                continue
            try:
                self.on_ui_registered.emit(name)
            except Exception:
                # Signal emission shouldn't block registration on Qt errors.
                self.logger.debug(
                    f"[on_ui_registered] emit failed for '{name}'", exc_info=True
                )

    def _get_ui_tags(self, name: str, path: str = None) -> set:
        """Return uitk_tags for a UI, lazy-loading from the .ui file on miss.

        Looks up ``path`` from the registry if not provided. Returns an empty
        set if neither cache nor registry can resolve a file. Result is
        cached in ``_ui_tags`` so subsequent calls are O(1).
        """
        if name in self._ui_tags:
            return self._ui_tags[name]
        if not path:
            ui_registry = getattr(self.registry, "ui_registry", None)
            if ui_registry is not None:
                path = ui_registry.get(filename=name, return_field="filepath")
        if not path:
            return set()
        tags = self._loader.read_ui_tags(path)
        self._ui_tags[name] = tags
        return tags

    def save_ui_tags(self, path: str, tags: Iterable[str]) -> None:
        """Persist tags into a .ui file as a Designer-safe dynamic property.

        Writes ``<property name="uitk_tags" stdset="0"><string>tag1,tag2</string></property>``
        as the first <property> child of the root widget. Uses an atomic
        write (temp file + os.replace) so cloud-sync clients never observe a
        partial write.

        If ``tags`` is empty, removes the property entirely.

        Updates the cached XML tag set, the live MainWindow.tags if the UI
        is currently loaded, and emits ``on_ui_tags_changed``.
        """
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(f"UI file not found: {path}")

        # Strip leading "#" — the prefix is display-only formatting added
        # by the browser's delegate. Storing "#foo" would round-trip to
        # "##foo" the next time the row renders.
        tag_set = set()
        for t in tags:
            cleaned = t.strip().lstrip("#").strip() if t else ""
            if cleaned:
                tag_set.add(cleaned)

        tree = ElementTree()
        tree.parse(path)
        root = tree.getroot()
        widget = root.find("widget") if root is not None else None
        if widget is None:
            raise ValueError(f"Root <widget> not found in: {path}")

        # Locate any existing uitk_tags property
        existing = None
        for prop in widget.findall("property"):
            if prop.get("name") == self.UITK_TAGS_PROPERTY:
                existing = prop
                break

        if not tag_set:
            if existing is not None:
                widget.remove(existing)
        else:
            if existing is None:
                existing = Element("property")
                existing.set("name", self.UITK_TAGS_PROPERTY)
                # Insert as the first <property> child of the root widget
                # so it appears prominently in Designer's Property Editor.
                insert_idx = 0
                for i, child in enumerate(list(widget)):
                    if child.tag == "property":
                        insert_idx = i
                        break
                    insert_idx = i + 1
                widget.insert(insert_idx, existing)
            existing.set("stdset", "0")
            # Replace any children with a fresh <string>
            for child in list(existing):
                existing.remove(child)
            string_el = SubElement(existing, "string")
            string_el.text = ",".join(sorted(tag_set))

        # Pretty-print for clean diffs (Python 3.9+)
        try:
            ET.indent(tree, space=" ")
        except AttributeError:
            pass

        serialized = ET.tostring(root, encoding="unicode")
        if not serialized.startswith("<?xml"):
            serialized = '<?xml version="1.0" encoding="UTF-8"?>\n' + serialized
        ptk.FileUtils.atomic_write_text(path, serialized)

        # Regenerate the compiled artifact so runtime sees the new tags.
        # Failure here means the next load_ui will detect drift and re-try.
        try:
            self._loader.on_tags_written(path)
        except Exception:
            self.logger.warning(
                f"[save_ui_tags] failed to regenerate _ui.py for '{path}' — "
                f"will retry on next load",
                exc_info=True,
            )

        # Update caches and live state
        ui_name = ptk.format_path(path, "name")
        self._ui_tags[ui_name] = set(tag_set)

        if ui_name in self.loaded_ui:
            ui = self.loaded_ui[ui_name]
            try:
                ui.edit_tags(reset=True, add=list(tag_set))
            except Exception:
                self.logger.debug(
                    f"[save_ui_tags] failed to update live tags on '{ui_name}'",
                    exc_info=True,
                )

        try:
            self.on_ui_tags_changed.emit(ui_name)
        except Exception:
            self.logger.debug(
                f"[on_ui_tags_changed] emit failed for '{ui_name}'", exc_info=True
            )

    def ui_history(self, index=None, allow_duplicates=False, inc=None, exc=None):
        """Get the UI history.

        Read-only: deduplication and filtering produce a view; the stored
        history is only mutated by the ``current_ui`` setter. Dead (closed)
        UIs are pruned from the underlying weak store on access.
        """
        return self._ui_history.get(
            index, allow_duplicates=allow_duplicates, inc=inc, exc=exc
        )

    def show_prev_ui(self) -> Optional[QtWidgets.QWidget]:
        """Re-show the most-recent non-transient UI that isn't already on screen.

        Walks UI history newest-first and shows the first window that is hidden
        (so "reopen last UI" brings back a just-closed tool) and isn't a marking-
        menu surface (``startmenu``/``submenu``). A window already visible is
        skipped — there's nothing to reopen — so repeated presses step back
        through hidden windows instead of re-showing the one on screen.

        Note it deliberately does *not* skip ``_current_ui``: a reopened window
        gains focus and becomes the current UI, so the old "skip the current
        one" rule left it unreopenable once closed — pressing the shortcut worked
        once and then did nothing (the reported bug). Visibility, not currency,
        is the right gate. Returns the UI shown, or ``None`` when every history
        entry is already visible or transient.
        """
        for ui in reversed(self.ui_history(allow_duplicates=False)):
            try:
                if ui.has_tags(["startmenu", "submenu"]) or ui.isVisible():
                    continue
                ui.show()
            except RuntimeError:
                # Live Python wrapper over a deleted C++ window (DCC teardown /
                # module reload). The weak store only prunes GC'd wrappers, so
                # skip this stale entry and try the next.
                continue
            self.logger.debug(f"[show_prev_ui] Re-showing {ui.objectName()}")
            return ui
        self.logger.debug("[show_prev_ui] No previous UI to re-show")
        return None

    def repeat_last(self):
        """Re-invoke the last slot with the exact args it last ran with.

        ``prev_slot`` only yields the bound method — calling it bare loses both
        the injected ``widget`` and any signal payload the slot took as a
        required positional (e.g. a list slot's clicked ``item``), so a repeat
        would raise ``TypeError``. The live ``SlotWrapper`` snapshots its last
        invocation's args/kwargs; this replays them through the normal dispatch
        path (wait cursor, timeout, history). Returns the slot's return value,
        or ``None`` if no slot has run yet or its widget has since been
        deleted. The slot's own exceptions propagate, as on its first run.
        """
        return self._slots.repeat_last()

    @property
    def style(self):
        """The :class:`StyleSheet` class (imported lazily on first access).

        Returns the class — not an instance — so the standard set of
        classmethods (``set_theme``, ``reload``, ``set_variable``,
        ``get_variable``, ``get_icon_color``) are reachable from a single
        ``sb.style.<method>`` call.
        """
        from uitk.themes.style_sheet import StyleSheet

        return StyleSheet

    @property
    def editors(self) -> _EditorRegistry:
        """Cached editor registry — see :class:`_EditorRegistry`."""
        # Lazy where it costs: the registry is a small name table (the default
        # ``EditorHandler`` reads it to list the editors as launcher rows), and
        # an editor's module is imported only when that editor is first built.
        if not hasattr(self, "_editors_registry"):
            self._editors_registry = _EditorRegistry(self)
        return self._editors_registry

    def __getattr__(self, name):
        """Fall back to the ``uitk`` namespace for a name normal lookup missed
        (``sb.IconManager``): see :mod:`uitk.switchboard.namespace`."""
        return _UitkNamespace.resolve(self, name)

    # ── Placement (placement.py) ──────────────────────────────────────────────

    @staticmethod
    def get_cursor_offset_from_center(widget):
        """Get the relative position of the cursor with respect to the center of a given widget.

        Parameters:
            widget (QWidget): The widget to query.

        Returns:
            (obj) QPoint
        """
        return _Placement.get_cursor_offset_from_center(widget)

    @staticmethod
    def center_widget(
        widget,
        pos=None,
        offset_x=0,
        offset_y=0,
        padding_x=None,
        padding_y=None,
        relative: QtWidgets.QWidget = None,
    ):
        """Adjust the widget's size to fit contents and center it at the given point, on the screen, at cursor, or at the widget's current position if no point is given.

        Parameters:
            widget (QWidget): The widget to move and resize.
            pos (QPoint/str, optional): A point to move to, or 'screen' to center on screen, or 'cursor' to center at cursor position. Defaults to None.
            offset_x (int, optional): The desired offset percentage on the x axis. Defaults to 0.
            offset_y (int, optional): The desired offset percentage on the y axis. Defaults to 0.
            padding_x (int, optional): Additional width from the widget's minimum size or relative widget. If not specified, the widget's current width is used. A maximumWidth too small to fit the result is raised to fit, unless minimumWidth == maximumWidth (a deliberate fixed-size lock, left untouched).
            padding_y (int, optional): Additional height from the widget's minimum size or relative widget. If not specified, the widget's current height is used. Same maximumHeight handling as padding_x.
            relative (QWidget, optional): If given, use this widget's current size as the base size for resizing.
        """
        return _Placement.center_widget(
            widget, pos, offset_x, offset_y, padding_x, padding_y, relative
        )

    # ── Event loop (event_loop.py) ────────────────────────────────────────────

    @staticmethod
    def invert_on_modifier(value):
        """Invert a numerical or boolean value if the alt key is pressed.

        Parameters:
            value (int, float, bool) = The value to invert.

        Returns:
            (int, float, bool)
        """
        return _EventLoop.invert_on_modifier(value)

    @staticmethod
    def simulate_key_press(
        ui, key=QtCore.Qt.Key_F12, modifiers=QtCore.Qt.NoModifier, release=False
    ):
        """Simulate a key press event for the given UI and optionally release the keyboard.

        Parameters:
            ui (QtWidgets.QWidget): The UI widget to simulate the key press for.
            key (QtCore.Qt.Key): The key to simulate. Defaults to QtCore.Qt.Key_F12.
            modifiers (QtCore.Qt.KeyboardModifiers): The keyboard modifiers to apply. Defaults to QtCore.Qt.NoModifier.
            release (bool): Whether to simulate a key release event.
        """
        return _EventLoop.simulate_key_press(ui, key, modifiers, release)

    def defer_with_timer(self, func: callable, *args, ms: int = 300, **kwargs) -> None:
        """Defer execution of any callable with arguments after a delay.

        Parameters:
            func (callable): The function to be called after the delay.
            *args: Positional arguments for the function.
            ms (int, optional): Delay in milliseconds before execution. Default is 300.
            **kwargs: Keyword arguments for the function.

        Raises:
            ValueError: If func is not callable.
            TypeError: If ms is not an integer.
        """
        return self._event_loop.defer_with_timer(func, *args, ms=ms, **kwargs)

    def gc_protect(self, obj=None, clear=False):
        """
        Protect the given object(s) from garbage collection by holding a strong reference.
        Parameters:
            obj (obj/list): The obj(s) to add to the protected dict.
            clear (bool): Clear the dict before adding any given object(s).
        Returns:
            dict: The protected objects.
        """
        return self._event_loop.gc_protect(obj, clear)

    # ── Names and tags (names.py) ─────────────────────────────────────────────

    @staticmethod
    def convert_to_legal_name(name: str) -> str:
        """Convert a name to a legal format by replacing non-alphanumeric characters with underscores.

        Parameters:
            name (str): The name to convert.

        Returns:
            str: The converted name with only alphanumeric characters and underscores.
        """
        return _Names.convert_to_legal_name(name)

    def get_slot_class_names(self, base_name: str) -> List[str]:
        """Generate potential slot class names from a base name.

        Parameters:
            base_name (str): The base name to generate slot class names from.

        Returns:
            List[str]: A list of potential slot class names.
        """
        return self._names.get_slot_class_names(base_name)

    def get_slot_file_names(self, base_name: str) -> List[str]:
        """Generate potential slot file names from a base name.

        Parameters:
            base_name (str): The base name to generate slot file names from.

        Returns:
            List[str]: A list of potential slot file names WITHOUT extension.
        """
        return self._names.get_slot_file_names(base_name)

    def get_base_name(self, name: str) -> str:
        return self._names.get_base_name(name)

    def get_tags_from_name(self, name: str) -> set[str]:
        """Extract tags from a UI name string.

        Parameters:
            name (str): The name to parse (e.g. "menu#submenu").

        Returns:
            set[str]: A set of tags extracted from the name.
        """
        return self._names.get_tags_from_name(name)

    def has_tags(self, ui, tags=None) -> bool:
        """Check if any of the given tag(s) are present in the UI's tags set.
        If no tags are provided, it checks if the UI has any tags at all.

        Parameters:
            ui (QWidget): The UI object to check.
            tags (str/list): The tag(s) to check.

        Returns:
            bool: True if any of the given tags are present in the tags set, False otherwise.
        """
        return self._names.has_tags(ui, tags)

    def edit_tags(
        self,
        target: Union[str, QtWidgets.QWidget],
        add: Union[str, List[str]] = None,
        remove: Union[str, List[str]] = None,
        clear: bool = False,
        reset: bool = False,
    ) -> Union[str, None]:
        """Edit tags on a widget or a tag string.

        Parameters:
            target (str or QWidget): The widget to edit tags on, or a tag string.
            add (str or list[str]): Tags to add.
            remove (str or list[str]): Tags to remove.
            clear (bool): If True, clears all tags.
            reset (bool): If True, resets tags to default (only for widgets).

        Returns:
            str or None: The modified tag string if target is a string, otherwise None.
        """
        return self._names.edit_tags(target, add, remove, clear, reset)

    def filter_tags(
        self,
        tag_string: str,
        keep_tags: list[str] = None,
        remove_tags: list[str] = None,
    ) -> str:
        """Filter tags from a tag string - either keep only specified tags or remove specified tags.

        Parameters:
            tag_string (str): The string containing tags
            keep_tags (list[str], optional): If provided, keep only these tags
            remove_tags (list[str], optional): If provided, remove these tags

        Returns:
            str: The filtered tag string
        """
        return self._names.filter_tags(tag_string, keep_tags, remove_tags)

    def get_unknown_tags(self, tag_string: str, known_tags: list[str]) -> list[str]:
        """Get tags that are not in the known_tags list.

        Parameters:
            tag_string (str): The string containing tags
            known_tags (list[str]): List of known/expected tags

        Returns:
            list[str]: List of unknown tag names (without delimiter prefix)
        """
        return self._names.get_unknown_tags(tag_string, known_tags)

    @classmethod
    def unpack_names(cls, name_string):
        """Unpacks a comma-separated string of names and returns a list of individual names.

        Parameters:
            name_string (str): A string consisting of widget names separated by commas.
                    Names may include ranges with hyphens, e.g., 'chk021-23, 25, tb001'.
        Returns:
            list: A list of unpacked names, e.g., ['chk021', 'chk022', 'chk023', 'chk025', 'tb001'].
        """
        return _Names.unpack_names(name_string)

    def get_widgets_by_string_pattern(self, ui, name_string):
        """Get a list of corresponding widgets from a single shorthand formatted string.
        ie. 's000,b002,cmb011-15' would return object list: [<s000>, <b002>, <cmb011>, <cmb012>, <cmb013>, <cmb014>, <cmb015>]

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            name_string (str): Widget object names separated by ','. ie. 's000,b004-7'. b004-7 specifies buttons b004 though b007.

        Returns:
            (list) QWidget(s)

        Example:
            get_widgets_by_string_pattern(<ui>, 's000,b002,cmb011-15')
        """
        return self._names.get_widgets_by_string_pattern(ui, name_string)

    def get_methods_by_string_pattern(self, clss, name_string):
        """Get a list of corresponding methods from a single shorthand formatted string.
        ie. 's000,b002,cmb011-15' would return methods: [<s000>, <b002>, <cmb011>, <cmb012>, <cmb013>, <cmb014>, <cmb015>]

        Parameters:
            clss (class): The class containing the methods.
            name_string (str): Slot names separated by ','. ie. 's000,b004-7'. b004-7 specifies methods b004 through b007.

        Returns:
            (list) class methods.

        Example:
            get_methods_by_string_pattern(<ui>, 'slot1,slot2,slot3')
        """
        return self._names.get_methods_by_string_pattern(clss, name_string)

    # ── Widget values (widget_values.py) ──────────────────────────────────────

    # Private names read outside the switchboard (its tests included).
    _combo_value = staticmethod(_WidgetValues._combo_value)
    _widget_value_reader = _Forward("_values", "widget_value_reader")

    # ── Control groups (control_groups.py) ────────────────────────────────────

    def create_button_groups(
        self,
        ui: QtWidgets.QWidget,
        *args: str,
        allow_deselect: bool = False,
        allow_multiple: bool = False,
    ) -> List[QtWidgets.QButtonGroup]:
        """Create button groups for a set of widgets.

        Parameters:
            ui (QtWidgets.QWidget): A previously loaded dynamic UI object.
            args (str): The widgets to group. Object_names separated by ',' ie. 'b000-12,b022'
            allow_deselect (bool): Whether to allow none of the checkboxes to be selected.
            allow_multiple (bool): Whether to allow multiple checkboxes to be selected.
        """
        return self._groups.create_button_groups(
            ui, *args, allow_deselect=allow_deselect, allow_multiple=allow_multiple
        )

    def toggle_multi(self, ui, trigger=None, signal=None, apply_now=True, **kwargs):
        """Set multiple boolean properties for multiple widgets at once, or connect a trigger to do so automatically.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            trigger (str/QWidget, optional): If provided, connects this widget's signal to toggle the others.
                                             If None, toggles immediately.
            signal (str, optional): Signal name to connect (only used when trigger is provided).
                                    Default: the widget's natural change signal (``toggled`` for
                                    buttons, ``currentIndexChanged`` for combos, …; ``toggled`` if unknown).
            apply_now (bool): Trigger mode only. Also apply the mapping for the trigger's
                              CURRENT value at wire time (default True) — a widget restored
                              from session state before the connection exists would otherwise
                              leave its dependants in the wrong state until the user touches it.
            **kwargs: The properties to modify. Can be:
                     - Direct properties (immediate mode): setChecked, setUnChecked, setEnabled, setDisabled, etc.
                       Value: string of object_names separated by ',' ie. 'b000-12,b022'
                     - State mapping (trigger mode): on_<state>={...}, on_default={...}
                       Value: dict of toggle_multi kwargs to apply for that state

        For the common "enable X while Y says so" dependency prefer :meth:`enable_when` —
        one predicate instead of a mirrored ``on_True`` / ``on_False`` pair.

        Examples:
            # Immediate toggle (original behavior)
            toggle_multi(<ui>, setDisabled='b000', setUnChecked='chk009-12')

            # Auto-connect with boolean states (True/False)
            toggle_multi(<ui>, trigger='chk027', signal='toggled',
                        on_True={'setDisabled': 's005,s006'},
                        on_False={'setEnabled': 's005,s006'})

            # Auto-connect with any value states (e.g., combobox index)
            toggle_multi(<ui>, trigger='cmb001', signal='currentIndexChanged',
                        on_0={'setVisible': 'grp_basic'},
                        on_1={'setVisible': 'grp_advanced'},
                        on_2={'setVisible': 'grp_expert'},
                        on_default={'setHidden': 'grp_basic,grp_advanced,grp_expert'})

            # String states (e.g., from text changed)
            toggle_multi(<ui>, trigger='line_edit', signal='textChanged',
                        on_auto={'setEnabled': 's001'},
                        on_manual={'setDisabled': 's001'})
        """
        return self._groups.toggle_multi(ui, trigger, signal, apply_now, **kwargs)

    def connect_multi(self, ui, widgets, signals, slots):
        """Connect multiple signals to multiple slots at once.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            widgets (str/list): 'chk000-2' or [tb.menu.chk000, tb.menu.chk001]
            signals (str/list): 'toggled' or ['toggled']
            slots (obj/list): self.cmb002 or [self.cmb002]

        Example:
            connect_multi(tb.menu, 'chk000-2', 'toggled', self.cmb002)
        """
        return self._groups.connect_multi(ui, widgets, signals, slots)

    def add_reset_buttons(
        self,
        ui,
        widgets=None,
        *,
        types=(QtWidgets.QAbstractSpinBox,),
        skip=(),
        **set_reset_kwargs,
    ):
        """Give each matching value widget a per-field *reset-to-default* button.

        A thin batch wrapper over the option-box ``ResetOption`` (see
        ``widget.option_box.set_reset``): for every resolved widget it adds a
        small icon button beside the field that resets it to its registry
        default on click, or *bypasses* it to default (greyed, restorable) on
        Alt/Ctrl+click. The default is resolved from the UI's ``StateManager``
        at click time, so no per-field wiring is needed. Bypass is
        non-persistent — each session starts with every field active.

        Widget resolution mirrors :meth:`connect_multi`.

        Note:
            Prefer calling this *before* ``connect_multi`` (or anything that
            registers the same widgets as deferred) inside a slots ``__init__``.
            Wrapping a widget in its option-box reparents it, which invalidates
            the QUiLoader-built Python wrapper captured at defer time. The
            switchboard self-heals — ``_process_deferred_widgets`` re-resolves
            such widgets to their live wrapper — so a late wrap no longer crashes
            the panel ("Internal C++ object ... already deleted"); wrapping first
            simply avoids the extra re-resolution.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            widgets (str/list/None): Widgets to wire. A shorthand pattern
                (``'s000-4'``), an explicit widget list, or ``None`` to
                auto-discover every child of *types*.
            types (tuple): Widget class(es) auto-discovered when *widgets* is
                ``None`` (default: spin boxes). Pass e.g. ``(ComboBox,)`` for a
                panel whose parameters are combos.
            skip (str/iterable): objectName(s) and/or widget instance(s) to
                leave alone (e.g. fields sharing a tight row with a button).
            **set_reset_kwargs: Forwarded verbatim to ``option_box.set_reset``
                (e.g. ``reset=``, ``icon=``, ``tooltip=``, ``on_toggled=``).

        Returns:
            list: The widgets that received a reset button.

        Example:
            sb.add_reset_buttons(ui)                      # every spin box
            sb.add_reset_buttons(ui, skip=("s025", "s026", "s027"))
            sb.add_reset_buttons(ui, "cmb000-1")          # specific combos
        """
        return self._groups.add_reset_buttons(
            ui, widgets, types=types, skip=skip, **set_reset_kwargs
        )

    def link_spinboxes(
        self,
        ui,
        widgets=None,
        *,
        types=(QtWidgets.QAbstractSpinBox,),
        skip=(),
        icon: str = "lock",
        icon_off: str = "unlock",
        tooltip_on: str = "Linked. Changing this shifts the other linked fields by the same amount. Click to unlink.",
        tooltip_off: str = "Unlinked. Click to link this field so it moves with the others.",
        initial: bool = False,
        active_color: str = _LOCK_ACTIVE_COLOR,
        disabled_color: str = _LOCK_INACTIVE_COLOR,
        **set_toggle_kwargs,
    ):
        """Give each spin box a *lock* toggle that links locked boxes by an equal delta.

        A batch companion to :meth:`add_reset_buttons`: each resolved widget gets
        an option-box lock toggle (a persisted :class:`ToggleOption`). When a
        **locked** box's value changes, every *other* **locked** box is shifted by
        the same delta; unlocked boxes are independent. Each field opts in on its
        own, so the user can link any subset (e.g. X+Y but not Z).

        The lock state persists per widget (via the ToggleOption's own settings),
        so a session reopens with the same fields linked. Composes with
        :meth:`add_reset_buttons` — a field can carry both a reset and a lock
        button (option ordering keeps ``reset`` before ``toggle``).

        Widget resolution mirrors :meth:`connect_multi` / :meth:`add_reset_buttons`.
        Call it in the same place (before ``connect_multi``) for the same
        wrap-before-defer reason.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            widgets (str/list/None): Widgets to wire — a shorthand pattern
                (``'s003-5'``), an explicit list, or ``None`` to auto-discover
                every child of *types*.
            types (tuple): Widget class(es) auto-discovered when *widgets* is
                ``None`` (default: spin boxes).
            skip (str/iterable): objectName(s) and/or widget instance(s) to leave
                alone.
            icon / icon_off: Toggle icons for the linked / unlinked states.
            tooltip_on / tooltip_off: Toggle tooltips.
            initial (bool): Starting lock state (default unlinked). Overridden by
                any persisted per-field value.
            active_color / disabled_color: Icon tints for the locked / unlocked
                states — the channel-box lock convention (see the module
                constants). Overrides ``ToggleOption``'s error-red default,
                which would misread an unlocked field as a fault.
            **set_toggle_kwargs: Forwarded verbatim to ``option_box.set_toggle``.

        Returns:
            list: The widgets that received a lock toggle.
        """
        return self._groups.link_spinboxes(
            ui,
            widgets,
            types=types,
            skip=skip,
            icon=icon,
            icon_off=icon_off,
            tooltip_on=tooltip_on,
            tooltip_off=tooltip_off,
            initial=initial,
            active_color=active_color,
            disabled_color=disabled_color,
            **set_toggle_kwargs,
        )

    def set_axis_for_checkboxes(self, checkboxes, axis, ui=None):
        """Set the given checkbox's check states to reflect the specified axis.

        Parameters:
            checkboxes (str/list): 3 or 4 (or six with explicit negative values) checkboxes.
            axis (str): Axis to set. Valid text: '-','X','Y','Z','-X','-Y','-Z' ('-' indicates a negative axis in a four checkbox setup)

        Example:
            set_axis_for_checkboxes('chk000-3', '-X') # Optional `ui` arg for the checkboxes.
        """
        return self._groups.set_axis_for_checkboxes(checkboxes, axis, ui)

    def get_axis_from_checkboxes(self, checkboxes, ui=None, return_type="str"):
        """Get the intended axis value as a string or integer by reading the multiple checkbox's check states.

        Parameters:
            checkboxes (str/list): 3 or 4 (or six with explicit negative values) checkboxes.
                Valid: '-','X','Y','Z','-X','-Y','-Z' ('-' indicates a negative axis in a four checkbox setup)
            ui: The user interface context if required.
            return_type (str): The type of the return value, 'str' for string or 'int' for integer representation.

        Returns:
            (str or int) The axis value in lower case (e.g., '-x') or as an integer index (e.g., 0 for 'x', 1 for '-x').

        Example:
            get_axis_from_checkboxes('chk000-3', return_type='int')  # Could output 0, 1, 2, 3, 4, or 5
        """
        return self._groups.get_axis_from_checkboxes(checkboxes, ui, return_type)

    def hide_unmatched_groupboxes(self, ui, unknown_tags) -> None:
        """Hides all QGroupBox widgets in the provided UI that do not match the unknown tags extracted
        from the provided tag string.

        Parameters:
            ui (QObject): The UI object in which to hide unmatched QGroupBox widgets.
            unknown_tags (list): A list of tags that should not be hidden. If empty, all groupboxes will be hidden.
        """
        return self._groups.hide_unmatched_groupboxes(ui, unknown_tags)

    # ── Rules (rules.py) ──────────────────────────────────────────────────────

    def enable_when(
        self,
        ui,
        targets,
        trigger,
        condition=True,
        signal=None,
        value=None,
        invert=False,
    ):
        """Keep *targets* enabled exactly while *trigger*'s value satisfies
        *condition* — a declarative dependency, wired once.

        The one-line answer to "grey this out when it can't apply": a lower-level
        choice (output format, a master checkbox, a mode combo) makes some other
        control irrelevant, and the panel should say so instead of leaving a
        live dial the export ignores. Replaces the pattern of a per-trigger slot
        + a ``_sync_*`` helper + a mirrored ``toggle_multi`` ``on_True`` /
        ``on_False`` pair with one rule that reads as the sentence it encodes::

            sb.enable_when(ui, "cmb006", "cmb004", lambda fmt: fmt != "fbx")
            sb.enable_when(ui, "texture_max_size", "optimize_textures")
            sb.enable_when(ui, "s001,chk002", "cmb035", 0)           # index / data == 0
            sb.enable_when(ui, "d000", "cmb035", 0, invert=True)     # the other branch
            sb.enable_when(ui, "texture_write_back",
                           ["optimize_textures", "cmb005"], lambda opt, tpl: opt or tpl)

        Parameters:
            ui: The loaded UI (widgets resolve by objectName on it).
            targets: Widget(s) to enable/disable — an objectName pattern string
                (``'s000,b004-7'``), a widget, or a list of either.
            trigger: The controlling widget(s) — objectName / widget, or a list
                (the condition then receives one value per trigger, in order).
            condition: What "on" means for the trigger's value: a callable
                ``(value, …) -> bool``; a plain value (equality); a set / list /
                tuple of values (membership); or ``True`` (default: truthiness —
                the master-checkbox case). With MULTIPLE triggers every
                non-callable form is **all-of**: equality, membership and
                truthiness each have to hold for every trigger. A callable is
                handed one value per trigger and decides for itself, which is
                where any-of lives.
            signal: Change signal name (single trigger). Default: the widget's
                natural signal from the value table.
            value: Reader override — a callable ``(widget) -> value`` used for
                every trigger, or a ``{objectName: callable}`` mapping for a
                mixed set (unlisted triggers keep the default reader, which
                reads a combo's ``currentData`` when items carry data, else
                ``currentIndex``; buttons ``isChecked``; …).
            invert: Enable when the condition is NOT met.

        A rule that resolves nothing against a container that HAS no
        ``on_child_registered`` is reported (see :meth:`_Rules._warn_if_rule_is_dead`):
        nothing further can arrive there, so it is not waiting — the names are on
        another container.

        Order-independent by design: a target (or trigger) that isn't
        registered on *ui* yet — a ``WidgetComboBox`` row, an option-box menu
        item — is picked up when ``ui.on_child_registered`` announces it, and
        the rule is (re)applied then and once more after the current event
        (registration restores session state with signals blocked, so the
        first read can be pre-restore). Every rule is also re-applied by
        :meth:`refresh_dependencies` for bulk state changes made with signals
        blocked (a preset load). Wiring the same targets to the same triggers
        twice is a no-op, so an ``_init`` slot that re-runs can't stack rules.

        Returns:
            The rule's ``apply`` callable (handy as an ``on_loaded`` hook).
        """
        return self._rules.enable_when(
            ui, targets, trigger, condition, signal, value, invert
        )

    def show_when(
        self,
        ui,
        targets,
        trigger,
        condition=True,
        signal=None,
        value=None,
        invert=False,
    ):
        """Keep *targets* on screen exactly while *trigger*'s value satisfies
        *condition* -- :meth:`enable_when`'s visibility twin.

        Greying out says "this exists but does not apply"; hiding says "this
        does not exist for what you chose". A KTX2 encoder dial with PNG
        selected, a GLB-only optimisation with no GLB being written, an FBX
        preset on a USD export: the panel is smaller and reads truer without
        them. Same rule grammar, same order-independence, same bulk refresh
        (:meth:`refresh_dependencies`), same conflict report::

            sb.show_when(ui, "uastc_rdo", "texture_file_type", "ktx2")
            sb.show_when(ui, "secondary_max_size,glb_key_tolerance", "cmb004",
                         {"glb", "fbx_glb"})

        A plain widget hides itself. A row of a :class:`WidgetComboBox` (an
        option menu) goes through the combo's own
        :class:`~uitk.managers.field_visibility.FieldVisibility` instead, so
        the model row leaves the popup and the titled separator over a section
        whose every row is hidden stands down with them. Either way the
        widget's VALUE is untouched: a hidden field still saves, restores and
        reads -- the run reads what the panel holds, so a hidden dial must be
        one the run ignores (or one the caller resolves as off).

        Parameters and return value as :meth:`enable_when`.
        """
        return self._rules.show_when(
            ui, targets, trigger, condition, signal, value, invert
        )

    def text_from(
        self,
        ui,
        targets: Union[str, Any, List[Any]],
        sources: Union[str, Any, List[Any]],
        formatter: Callable[..., str],
        signal: Optional[str] = None,
        value: Optional[
            Union[Callable[[Any], Any], Dict[str, Callable[[Any], Any]]]
        ] = None,
    ) -> Callable[[], None]:
        """Keep *targets*' text derived from *sources* — a self-labelling widget,
        wired once.

        The text counterpart of :meth:`enable_when`: that one answers "grey this out
        when it can't apply", this one answers "say what this will do". A control
        whose behaviour is configured elsewhere — an option box, a mode combo —
        reads as a mystery until it names its own outcome, and on a marking menu
        there is no dialog to read first::

            sb.text_from(menu, widget, "s003", "Crease {}".format)
            sb.text_from(menu, widget, "chk024-26",
                         lambda *on: f"Constrain: {'ON' if any(on) else 'OFF'}")
            sb.text_from(menu, widget, ["cmb_scope", "cmb_save", "cmb_format"],
                         self._export_button_text,
                         value={"cmb_format": lambda w: w.currentText()})

        Hand-wiring this is three steps — read, format, ``setText`` — plus a fourth
        that is easy to forget: applying it at WIRE TIME. A rule that is only
        connected leaves whatever text the ``.ui`` shipped standing until the user
        touches something, which is already wrong whenever a source starts
        non-default or was restored from session state.

        Parameters:
            ui: The loaded UI, or whatever the names resolve against — an option
                box's ``menu`` is the common one.
            targets: Widget(s) to relabel — an objectName pattern string
                (``'tb003'``, ``'b004-7'``), a widget, or a list of either. Every
                resolved target gets the same text.
            sources: The widget(s) the text is derived from — objectName / pattern
                / widget, or a list of those. Patterns UNPACK here (unlike
                :meth:`enable_when`'s trigger), so ``'chk024-26'`` feeds the
                formatter three values.
            formatter: ``callable(*values) -> str``, one value per resolved source
                in order. ``"Crease {}".format`` is a formatter.
            signal: Change signal name (single source). Default: the widget's
                natural signal from the value table.
            value: Reader override — a callable ``(widget) -> value`` used for every
                source, or a ``{objectName: callable}`` mapping for a mixed set
                (unlisted sources keep the default reader). The default reads a
                combo's ``currentData`` when its items carry data, else
                ``currentIndex``; pass ``currentText`` when the item's LABEL is what
                the text should say.

        Order-independent, idempotent and bulk-refreshable exactly as
        :meth:`enable_when` — they share the machinery and the notes there apply,
        including the report when a rule can never fire. A source named EXACTLY that
        hasn't been registered yet holds the whole rule rather than formatting a
        partial reading; a pattern contributes whatever it matches so far, and is
        re-applied when the rest arrive.

        A target that is also a source is safe: the write-back cannot re-enter the
        rule. A formatter that raises leaves the current text standing rather than
        blanking it, so a half-built source costs nothing.

        Returns:
            The rule's ``apply`` callable (handy as an ``on_loaded`` hook).
        """
        return self._rules.text_from(ui, targets, sources, formatter, signal, value)

    def value_from(
        self,
        ui,
        targets: Union[str, Any, List[Any]],
        sources: Union[str, Any, List[Any]],
        resolver: Callable[..., Any],
        signal: Optional[str] = None,
        value: Optional[
            Union[Callable[[Any], Any], Dict[str, Callable[[Any], Any]]]
        ] = None,
    ) -> Callable[[], None]:
        """Keep *targets*' VALUE derived from *sources* — a control that follows
        the dials it stands for, wired once.

        The third of the declarative family: :meth:`enable_when` answers "grey
        this out when it can't apply", :meth:`text_from` "say what this will
        do", and this one "say WHICH of my presets you are on". The case it
        exists for is a summary control the user can also drive around: a
        Quality combo that fills Resolution / Samples has to fall back to
        *Custom* the moment either dial stops matching a preset, or it keeps
        naming a tier the bake is no longer using::

            sb.value_from(ui, "cmb000", ["cmb_resolution", "spn_samples"],
                          self._preset_for_dials)      # -> "mobile" | "Custom"

            sb.value_from(m, "cmb_mode", "chk_advanced",
                          lambda on: "advanced" if on else "basic")

        Hand-wiring this is the same four steps as :meth:`text_from` — read,
        resolve, write, and apply at WIRE TIME — plus a fifth that only bites
        here: a naive write-back re-enters through the target's own change
        signal. The write is fenced, so a target may be its own source.

        Parameters:
            ui: The loaded UI, or whatever the names resolve against — an option
                box's ``menu`` is the common one.
            targets: Widget(s) to drive — an objectName pattern string
                (``'cmb000'``, ``'s004-7'``), a widget, or a list of either.
                Every resolved target gets the same value.
            sources: The widget(s) the value is derived from — objectName /
                pattern / widget, or a list of those. Patterns UNPACK (as in
                :meth:`text_from`), so ``'chk024-26'`` feeds three values.
            resolver: ``callable(*values) -> value``, one value per resolved
                source in order. Returning ``None`` DECLINES — the target is
                left exactly as the user left it — so "I have no opinion about
                this combination" needs no sentinel.
            signal: Change signal name (single source). Default: the widget's
                natural signal from the value table.
            value: Reader override for the SOURCES — a callable ``(widget) ->
                value`` for every one, or a ``{objectName: callable}`` mapping
                for a mixed set. (Writes are dispatched by widget type; see
                :meth:`_WidgetValues.widget_value_writer`.)

        The write is the mirror of the read: a combo takes the item whose DATA,
        then whose LABEL, then whose ROW matches (a value matching none of the
        three is reported and skipped, never coerced to row 0); every other type
        goes to ``ValueManager.set_value``, which coerces where that is
        unambiguous (``"8"`` into a spin box) and leaves the widget alone where
        it is not. Writes are NOT signal-blocked — a derived value is a real
        change and the target's own slot is entitled to see it (that is what
        lets a preset combo re-apply the rest of its preset).

        Order-independent, idempotent and bulk-refreshable exactly as
        :meth:`enable_when` and :meth:`text_from` — they share the machinery
        (:meth:`_Rules._wire_rule`) and the notes there apply, including the report
        when a rule can never fire.

        Returns:
            The rule's ``apply`` callable (handy as an ``on_loaded`` hook).
        """
        return self._rules.value_from(ui, targets, sources, resolver, signal, value)

    def refresh_dependencies(self, ui) -> None:
        """Re-apply every declarative rule on *ui* — :meth:`enable_when`'s,
        :meth:`show_when`'s, :meth:`text_from`'s and :meth:`value_from`'s — for bulk value changes
        made with signals blocked (a preset load, a programmatic restore) that
        no trigger signal announced."""
        return self._rules.refresh_dependencies(ui)

    # ── Dialogs and progress (dialogs.py) ─────────────────────────────────────

    @staticmethod
    def busy_cursor(shape=QtCore.Qt.WaitCursor):
        """Application busy cursor for the duration of a ``with`` block.

        :meth:`CursorManager.busy` reached through the switchboard, for slot
        code that runs OUTSIDE dispatch (a worker callback, a method called
        directly). Every dispatched slot is already bracketed in one, so a
        slot body never needs it — and never touches
        ``QApplication.setOverrideCursor`` directly: the raw pair pops the top
        of the stack rather than its own entry.
        """
        return _Dialogs.busy_cursor(shape)

    def progress(
        self,
        ui=None,
        total: Optional[int] = None,
        text: str = "",
        busy: Optional[bool] = None,
    ):
        """Context manager for cooperative progress / task feedback.

        Routes to the active UI's :meth:`Footer.progress` when a footer
        is available; otherwise returns a no-op so callers run unchanged
        on UIs without one.

        Two modes from one entry point:

        * Pass ``total=N`` for a determinate progress bar (known step
          count). Tick with ``update(i + 1)``.
        * Omit *total* (the default) for an indeterminate "task
          indicator" marquee. Tick with bare ``update()`` calls between
          work chunks to drive the animation.

        Adapter-driven slots can omit *total* even for determinate
        progress: :func:`progress_adapter` auto-syncs the bar's max
        from the callback's ``total`` argument on the first tick, so
        the slot doesn't need to pre-compute the loop size.

        The slot dispatcher already shows a system wait cursor for the
        duration of every slot — this is for slots that want *richer*
        feedback in the footer.

        Parameters:
            ui: UI hosting the footer. Defaults to ``active_ui``.
            total: Step count for determinate mode; ``None`` (default)
                selects indeterminate / task-indicator mode.
            text: Optional status text shown alongside the bar.
            busy: Show the footer's busy spinner beside the text. ``None``
                (default) shows it for indeterminate work only; ``True``
                keeps it on a determinate bar whose single steps are long
                (see ``Footer.set_busy``); ``False`` never shows it.

        Yields:
            ``update(value=None, text=None) -> bool`` — returns ``False``
            if the user cancelled (Esc-hold). In task-indicator mode,
            call with no arguments to advance the marquee.

        Determinate example::

            with self.sb.progress(total=len(items), text="Copying") as update:
                for i, item in enumerate(items):
                    process(item)
                    if not update(i + 1):
                        break  # user cancelled

        Task-indicator example::

            with self.sb.progress(text="Working: Get Scene Info") as tick:
                step_one()
                tick()       # pumps the event loop, advances the bar
                step_two()
                tick()
        """
        return self._dialogs.progress(ui, total, text, busy)

    @staticmethod
    def progress_adapter(
        update: Callable[..., bool],
    ) -> Callable[..., bool]:
        """Adapt the footer ``update`` callable to the shape downstream
        ``progress_callback`` parameters typically expect.

        Handles both ecosystem shapes with one adapter:

        * ``cb(current, total, message)`` — mayatk pattern
          (``SceneAnalyzer.analyze``, ``MatUtils.get_mat_info``…).
        * ``cb(percent)`` — pythontk pattern
          (``MapCompositor``; expects ``0..100``).

        **Auto-syncs the bar's max from the callback's ``total``** so
        slots don't have to pre-declare the loop size:

            with self.sb.progress(text="Analyzing") as update:
                analyzer.analyze(
                    progress_callback=self.sb.progress_adapter(update),
                )

        On the first tick where ``total > 0``, the bar's maximum is
        retotalled to that value (and the bar switches out of
        indeterminate mode if it was pulsing). Subsequent ticks
        re-sync only when ``total`` actually changes — so a single
        adapter handles fixed-percent callbacks (``total=100``),
        per-item count callbacks (``total=N``), and indeterminate
        ones (``total=0``).

        The returned callable forwards the bool from ``update``, so
        downstreams that read it for cooperative cancellation get it
        for free.
        """
        return _Dialogs.progress_adapter(update)

    def confirm(self, question, yes="Yes", no="No") -> bool:
        """Ask *question* in a modal :meth:`message_box` and answer True when
        the user chose *yes* -- the consent callable a tool's install offer
        takes (``ptk.ImgUtils.settle_ktx2_encoder(prompt=sb.confirm)``), so
        no panel re-spells "message_box(q, 'Yes', 'No') == 'Yes'" itself.
        """
        return self._dialogs.confirm(question, yes, no)

    def message_box(
        self,
        string,
        *buttons,
        location="topMiddle",
        timeout="auto",
        background=0.75,
        default=None,
    ):
        """Spawns a message box with the given text and optionally sets buttons.

        Parameters:
            string: HTML text to display.
            *buttons: Optional buttons: Qt standard-button names (``"Yes"``,
                ``"Cancel"``) or any other label, which becomes a button of
                its own (``"Override All"``). When provided the box is modal
                (``exec_``) and returns the clicked button's name or label;
                otherwise a passive popup.
            default: The button Enter answers, by name or label (modal
                only). ``None`` leaves Qt's choice.
            location: Placement hint (default ``"topMiddle"``).
            timeout: Auto-dismiss seconds for the passive popup. ``"auto"``
                (default) times it to the text -- long enough to read, never
                more than a few seconds (``MessageBox.reading_time``);
                ``None`` or ``0`` keeps it up until dismissed. A box with
                buttons always waits for its answer.
            background (bool/float/str): Controls the label background.
                ``True`` uses default dark grey at 50% opacity,
                ``False`` disables the background,
                a ``float`` 0–1 sets opacity (default 0.5),
                a CSS color ``str`` is used verbatim.
        """
        return self._dialogs.message_box(
            string,
            *buttons,
            location=location,
            timeout=timeout,
            background=background,
            default=default,
        )

    def text_view_dialog(
        self,
        text: str = "",
        *buttons,
        title: str = "",
        size=(640, 400),
        monospace: bool = False,
        word_wrap: bool = True,
        background=False,
        parent=None,
        link_handler=None,
        on_refresh: Optional[Callable[[], Any]] = None,
    ):
        """Spawn a scrollable text-viewer window with optional buttons.

        Sibling to :meth:`message_box` for content too long or too
        structured for a passive popup (reports, log output, formatted
        result dumps). The viewer is a uitk :class:`WindowPanel`
        subclass with its own header, footer, and busy-indicator
        integration — same theming and chrome as the rest of the
        ecosystem's tool windows.

        Always non-modal: the viewer coexists with the host application
        (Maya, etc.) so the user can keep working while reading. The
        viewer's footer participates in the slot dispatcher's
        busy-indicator broadcast, so its own footer shows the
        "Working:" indicator if a slot is dispatched while it's open.

        Parameters:
            text: HTML or plain text to display. May be empty when the
                caller plans to populate via :meth:`TextViewBox.setText`
                / :meth:`append_text` after the call.
            *buttons: Standard-button name strings (``"Ok"``,
                ``"Cancel"``, etc. — same vocabulary as
                :meth:`message_box`). Buttons in the Accept / Reject /
                Destructive roles close the window; Apply / Reset /
                Help leave it open and surface their clicked name via
                ``TextViewBox.clicked_button``.
            title: Window title (shown in the header).
            size: Initial ``(width, height)``. Default ``(640, 400)``.
            monospace: Use a monospace body font. Default ``False``.
            word_wrap: Wrap long lines. ``False`` enables horizontal
                scrolling for tabular content. Default ``True``.
            background: Body background colour. Same semantics as
                :meth:`message_box`. Default ``False`` (widget default).
            parent: Anchor widget. Defaults to ``self.parent()``. The
                viewer reparents to ``parent.window()`` so it survives
                a transient invoker hiding.
            link_handler: ``handler(QUrl) -> bool`` offered each clicked
                link first (see :class:`TextViewBox`) -- pass a DCC's
                ``UiUtils.dispatch_log_link`` so a report's
                ``action://select`` links select what they name.
            on_refresh: Called by the header's refresh button, shown first
                when given -- a report that reads itself again (the caller
                sets the new text). ``None``: no refresh button.

        Returns:
            The :class:`TextViewBox` instance — the caller can stream
            more content via :meth:`TextViewBox.append_text` or close
            it later via :meth:`close`.
        """
        return self._dialogs.text_view_dialog(
            text,
            *buttons,
            title=title,
            size=size,
            monospace=monospace,
            word_wrap=word_wrap,
            background=background,
            parent=parent,
            link_handler=link_handler,
            on_refresh=on_refresh,
        )

    def preview_dialog(
        self,
        render: Callable[[dict], str],
        specs=(),
        *,
        values: Optional[dict] = None,
        on_change: Optional[Callable[[str, Any], None]] = None,
        actions: Optional[dict] = None,
        status: Optional[Callable[[dict, str], str]] = None,
        title: str = "",
        size=(960, 600),
        monospace: bool = True,
        word_wrap: bool = False,
        parent=None,
    ):
        """A live preview of a tool's output: option rows beside the text,
        which renders again on every change, and the verbs that write it.

        :meth:`text_view_dialog`'s viewer (the Get Scene Info report's) made
        a preview by :meth:`TextViewBox.bind_preview`.  Non-modal: the tool
        it previews stays usable, and the caller re-renders it when what it
        shows changes (``refresh_preview``).

        Parameters:
            render: ``render(values) -> str``: the output for the options'
                *values*, shown as plain text.
            specs: The options (``bind_preview``'s: ``AttributeSpec``\\ s or
                dicts of their fields).
            values: The options' values to start from.
            on_change: ``on_change(key, value)`` once an option changed.
            actions: ``{button name: action(viewer)}`` -- each a footer button
                (``"Copy"``, ``"SaveAs"`` ...: :attr:`TextViewBox.BUTTONS`),
                then ``Close``.  A Copy / Save As leaves the preview open.
            status: ``status(values, text) -> str`` for the viewer's footer.
            title, size, monospace, word_wrap, parent: As
                :meth:`text_view_dialog`.

        Returns:
            The :class:`TextViewBox`.

        Raises:
            ValueError: An action named for no button (it would never run).
        """
        return self._dialogs.preview_dialog(
            render,
            specs,
            values=values,
            on_change=on_change,
            actions=actions,
            status=status,
            title=title,
            size=size,
            monospace=monospace,
            word_wrap=word_wrap,
            parent=parent,
        )

    def data_view_dialog(
        self,
        data: Any,
        *,
        title: str = "",
        save_path: Optional[str] = "",
        empty_message: str = "Nothing to show.",
        size=(720, 560),
        parent=None,
    ):
        """Show structured *data* as colour-coded JSON in a text viewer.

        The shared viewer for tool-authored data -- scene metadata, manifests,
        records -- so every caller gets the same look
        (:meth:`TextViewBox.format_data`) and the same Save, and polishing it
        polishes them all.

        Parameters:
            data: Any JSON-serializable value; one json cannot encode is shown
                as its ``str``.
            title: Window title; also names the Save dialog.
            save_path: Suggested file for the Save button (``""`` suggests
                none); ``None`` hides Save.
            empty_message: Shown in a message box instead of an empty viewer
                when *data* holds nothing: an empty container, or a dict whose
                values are all empty containers (a store with no records).
            size: Initial ``(width, height)``.
            parent: Anchor widget, as :meth:`text_view_dialog`.

        Returns:
            The :class:`TextViewBox`, or ``None`` when *data* was empty.
        """
        return self._dialogs.data_view_dialog(
            data,
            title=title,
            save_path=save_path,
            empty_message=empty_message,
            size=size,
            parent=parent,
        )

    def save_data_dialog(
        self, data: Any, title: str = "", path: str = "", parent=None
    ) -> Optional[str]:
        """Write *data* as indented JSON to a ``.json`` file the user picks.

        :meth:`data_view_dialog`'s Save, usable on its own. Written atomically;
        a value json cannot encode is written as its ``str``.

        Returns:
            The written path, or ``None`` when the user cancelled.
        """
        return self._dialogs.save_data_dialog(data, title, path, parent)

    @staticmethod
    def file_dialog(
        file_types: Union[str, List[str]] = ["*.*"],
        title: str = "Select files to open",
        start_dir: str = "/home",
        filter_description: str = "All Files",
        allow_multiple: bool = True,
    ) -> Union[str, List[str]]:
        """Open a file dialog to select files of the given type(s) using qtpy.

        Parameters:
            file_types (Union[str, List[str]]): Extensions of file types to include. Can be a string or a list of strings.
                Default is ["*.*"], which includes all files.
            title (str): Title of the file dialog. Default is "Select files to open."
            start_dir (str): Initial directory to display in the file dialog. Default is "/home."
            filter_description (str): Description for the filter applied to the file types. Default is "All Files."
            allow_multiple (bool): Whether to allow multiple file selection. Default is True.

        Returns:
            Union[str, List[str]]: A string if a single file is selected, or a list of strings if multiple files are selected.

        Example:
            files = file_dialog(file_types=["*.png", "*.jpg"], title="Select images", filter_description="Images")
        """
        return _Dialogs.file_dialog(
            file_types, title, start_dir, filter_description, allow_multiple
        )

    @staticmethod
    def dir_dialog(title: str = "Select a directory", start_dir: str = "/home") -> str:
        """Open a directory dialog to select a directory using qtpy.

        Parameters:
            title (str): Title of the directory dialog. Default is "Select a directory."
            start_dir (str): Initial directory to display in the dialog. Default is "/home."

        Returns:
            str: Selected directory path.

        Example:
            directory_path = dir_dialog(title="Select a project folder")
        """
        return _Dialogs.dir_dialog(title, start_dir)

    @staticmethod
    def save_file_dialog(
        file_types: Union[str, List[str]] = ["*.*"],
        title: str = "Save file",
        start_dir: str = "/home",
        filter_description: str = "All Files",
    ) -> Optional[str]:
        """Open a save-file dialog to choose a destination path.

        Parameters:
            file_types: Extensions to include (e.g. ``["*.wav"]``).
                Default is ``["*.*"]``.
            title: Dialog window title.
            start_dir: Initial directory / suggested file path.
            filter_description: Label for the file-type filter.

        Returns:
            The chosen file path, or *None* if the dialog was cancelled.

        Example:
            path = save_file_dialog(
                file_types=["*.wav"],
                title="Export audio",
                filter_description="WAV Files",
            )
        """
        return _Dialogs.save_file_dialog(
            file_types, title, start_dir, filter_description
        )

    @staticmethod
    def input_dialog(
        title: str = "Input",
        label: str = "Enter value:",
        text: str = "",
        parent: QtWidgets.QWidget = None,
        placeholder: str = "",
        validate: callable = None,
        error_text: str = "Invalid input.",
    ) -> str:
        """Show a modal text-input dialog and return the entered string.

        Builds a small custom ``QDialog`` so it can be properly parented,
        styled to match the host application, and extended with inline
        validation feedback.  Falls back gracefully when no parent is
        supplied.

        Parameters:
            title: Window title.
            label: Descriptive label above the text field.
            text: Pre-filled text (e.g. the current value for rename).
            parent: Optional parent widget for correct modality and
                positioning.  Accepts any ``QWidget``.
            placeholder: Greyed-out hint shown when the field is empty.
            validate: Optional ``callable(text) -> bool``.  While it
                returns ``False`` the OK button stays disabled and a
                brief *error_text* is shown beneath the field.
            error_text: Message displayed when *validate* returns
                ``False``.

        Returns:
            str: The stripped text the user entered, or ``None`` if the
            dialog was cancelled or closed.
        """
        return _Dialogs.input_dialog(
            title, label, text, parent, placeholder, validate, error_text
        )

    @staticmethod
    def list_input_dialog(
        items,
        title: str = "Select",
        label: str = "Select item(s):",
        parent: QtWidgets.QWidget = None,
        multi: bool = True,
        selected=None,
    ) -> list:
        """Show a modal list picker and return the chosen entries.

        The list twin of :meth:`input_dialog` — same parenting, host-theme
        inheritance, and busy-cursor suspension, so a panel needing "pick some
        of these" doesn't hand-roll a ``QDialog`` that misses all three.

        Parameters:
            items: Iterable of entries. Non-strings are rendered with ``str``;
                the returned values are the rendered strings.
            title: Window title.
            label: Descriptive label above the list.
            parent: Optional parent widget for correct modality and position.
            multi: Allow selecting several entries (default). False restricts
                to one.
            selected: Optional iterable of entries to pre-select.

        Returns:
            list[str]: The selected entries, or ``[]`` if the dialog was
                cancelled or nothing was picked.
        """
        return _Dialogs.list_input_dialog(items, title, label, parent, multi, selected)

    @staticmethod
    def form_dialog(
        fields,
        title: str = "Options",
        parent: QtWidgets.QWidget = None,
        ok_text: Union[str, Callable] = "OK",
        validate: Callable = None,
        message: str = "",
    ) -> Optional[dict]:
        """Show a modal form of labelled rows and return ``{name: value}``.

        The multi-field twin of :meth:`input_dialog`, for the case a sequence
        of single-purpose dialogs handles badly: **two or more answers the
        user has to tell apart**. A pair of native folder pickers shown back
        to back are the same widget with different captions, so which one is
        "search here" and which is "write here" lives entirely in a title
        bar — and the answer changes when one of them is skipped. Side by
        side and labelled, there is nothing to confuse and no order to
        remember.

        The window is a :class:`~uitk.widgets.formPanel.FormPanel`, so it
        wears the toolset's own chrome (Header, Footer, theme) rather than a
        bare dialog's host default, and every row's ``hint`` is a formatted
        tooltip. See :meth:`FormPanel.set_fields` for the full field spec.

        Use this when the caller does the work AFTER the answers are in.
        When the work belongs on the form — a verb button, a log to watch,
        a second run with one value changed — use :meth:`form_panel`, which
        stays open and keeps its output pane.

        Parameters:
            fields: Iterable of row specs (dicts). See
                :meth:`FormPanel.set_fields`.
            title: Window title.
            parent: Optional parent for correct modality and position.
            ok_text: Accept-button text. Say what will happen ("Copy 12
                files") — the button is the last thing read before
                committing. A ``callable(values) -> str`` is re-evaluated on
                every edit, so a verb chosen ON the form (a Copy/Move row)
                reaches the button that names the operation.
            validate: Optional ``callable(values: dict) -> str``. Return ""
                (or None) when the form is valid, else the message to show in
                the footer; OK stays disabled while it is non-empty.
            message: Optional line above the rows.

        Returns:
            dict|None: ``{name: value}`` for every row, or None when the
            dialog was cancelled or closed.

        Example:
            paths = sb.form_dialog(
                [
                    {"name": "src", "kind": "dir", "label": "Search in",
                     "hint": "3 unresolved texture(s), searched recursively"},
                    {"name": "dest", "kind": "dir", "label": "Copy into",
                     "value": sourceimages, "hint": "12 file(s) land here"},
                ],
                title="Find & Copy Textures",
                ok_text="Copy 12 files",
                validate=lambda v: (
                    "Destination is the search folder — nothing would move."
                    if v["src"] and v["src"] == v["dest"] else ""
                ),
            )
        """
        return _Dialogs.form_dialog(fields, title, parent, ok_text, validate, message)

    @staticmethod
    def form_panel(
        fields,
        title: str = "Options",
        parent: QtWidgets.QWidget = None,
        ok_text: Union[str, Callable] = "OK",
        cancel_text: str = None,
        validate: Callable = None,
        message: str = "",
        help_text: str = "",
        on_run: Callable = None,
        apply_text: str = "Apply",
        output: bool = True,
        min_width: int = 560,
        settings=None,
        settings_key: str = "window_geometry",
    ):
        """Build a :class:`~uitk.widgets.formPanel.FormPanel` — the modeless twin.

        The same rows as :meth:`form_dialog`, in a window that STAYS OPEN and
        runs the operation itself: the accept button calls ``on_run(values)``
        with the panel still up, the operation's log streams into the single
        output pane at the bottom, and the footer carries the status. That is
        the shape every other tool window in the toolset has, and it is what a
        modal cannot be — a modal that has closed can neither show what it did
        nor be re-run with one value changed.

        Does NOT show the panel: the caller decides, because a caller that
        keeps the panel (to re-seed it from live state on the next invocation
        rather than stacking a second window) needs the reference before the
        first show. Call ``panel.present()``. It is a ``WindowPanel``, so
        anything beyond the field specs is added the way a Menu item is —
        ``panel.add("PushButton", setText=..., clicked=...)``.

        Parameters:
            fields: Iterable of row specs (dicts). See
                :meth:`FormPanel.set_fields`.
            title: Header text.
            parent: Anchor widget; the panel reparents to ``parent.window()``.
            ok_text: Accept-button text, or ``callable(values) -> str``.
            cancel_text: Reject-button text. A run-in-place panel gets no
                reject button by default (the header carries the window's
                close); pass a string to force one.
            validate: ``callable(values: dict) -> str`` — "" when valid.
            message: Optional rich-text line above the rows.
            help_text: Rich text for the header's ``?`` button. Build it with
                ``sb.tooltip.fmt(...)``.
            on_run: ``callable(values: dict)`` run in place by the accept
                button. Return a ``callable()`` to say "this was a preview" —
                the panel arms Apply with it (the naming panel's dry-run
                contract). Omit for a panel the caller drives itself.
            apply_text: Text of the armed-preview button.
            output: Show the collapsable output pane (default True).
            min_width: Minimum window width.
            settings: Optional store (``sb.settings.branch("<tool>")``) the
                window's size and position survive across sessions in.
            settings_key: Settings key holding the serialized geometry.

        Returns:
            FormPanel: the (unshown) panel.

        Example:
            panel = sb.form_panel(
                fields,
                title="Find & Copy Textures",
                parent=self.ui,
                on_run=self._execute_find_and_copy,
                validate=self._validate_find_and_copy,
            )
            panel.present()
        """
        return _Dialogs.form_panel(
            fields,
            title,
            parent,
            ok_text,
            cancel_text,
            validate,
            message,
            help_text,
            on_run,
            apply_text,
            output,
            min_width,
            settings,
            settings_key,
        )

    @staticmethod
    def modal_menu(content_fn, parent=None, **kwargs):
        """Show a themed modal Menu popup, block until dismissed.

        Convenience wrapper around :meth:`Menu.run_modal`.  See that method
        for full parameter documentation.

        Parameters:
            content_fn (callable): ``content_fn(menu, state)`` — populate the
                menu with widgets and store result data in *state*.
            parent (QWidget, optional): Parent widget.
            **kwargs: Forwarded to :meth:`Menu.run_modal` (``title``,
                ``buttons``, ``size``, ``min_size``, ``center``, etc.).

        Returns:
            dict or None: The *state* dict on accept, ``None`` on reject.
        """
        return _Dialogs.modal_menu(content_fn, parent, **kwargs)

    # The reused passive popup (read by tests).
    _messageBox = _Forward("_dialogs", "popup")

    # ── Widgets and gates (widgets.py) ────────────────────────────────────────

    #: How a widget whose requirement is unmet is presented -- owned by
    #: :class:`_Gates` (widgets.py), which documents each policy.
    UNMET_POLICIES = _Gates.UNMET_POLICIES
    UNMET_POLICY_DEFAULT = _Gates.UNMET_POLICY_DEFAULT
    UNMET_POLICY_KEY = _Gates.UNMET_POLICY_KEY

    @property
    def unmet_policy(self) -> str:
        """How tools whose requirement is unmet are presented (persisted).

        A user preference, so it lives in the shared ``configurable`` branch
        rather than on the instance -- a dev reload that builds a second
        Switchboard must not silently revert the user's choice. An unrecognized
        stored value degrades to :attr:`UNMET_POLICY_DEFAULT` rather than raising:
        a settings file written by a newer version must not break an older one.
        """
        return self._gates.unmet_policy

    @unmet_policy.setter
    def unmet_policy(self, value) -> None:
        self._gates.unmet_policy = value

    def gate(self, widget, available, reason: str = "") -> bool:
        """Present *widget* according to whether its requirement is met.

        The explicit counterpart to :meth:`apply_visibility_policy`: a slot calls
        this from its ``*_init`` with a plain bool it computed however it likes --
        ``mtk.MarmosetBridge.APP.available``, ``cmds.pluginInfo(..., loaded=True)``,
        ``OptionalPackageManager.available("unitytk>=0.0.8")``. Nothing here knows
        about apps, plugins, or packages; the caller owns the question and this
        owns the answer's *presentation*, per :attr:`unmet_policy`.

        Called from ``*_init``, which re-fires on every panel show, so it must be
        idempotent and must fully restore -- both are covered: the pre-gate
        presentation is stashed on first gate and put back when *available* turns
        true, so repeated calls neither stack tooltips nor lose the widget's real
        state. That re-fire is what makes a policy change take effect on the next
        panel build; :meth:`recheck_gates` is the same thing on demand, for the
        case the re-fire cannot serve -- the user installing the missing app
        DURING the session, with the panel already open.

        Parameters:
            widget: The widget to gate. ``None`` is tolerated (a slot may gate an
                optional widget without a guard) and returns *available*.
            available: Whether the requirement is satisfied -- a bool, or a
                zero-arg callable returning one. Pass the CALLABLE when the
                answer can change while the session runs (an app the user may
                install): it is what :meth:`recheck_gates` re-evaluates, where a
                bare bool can only be re-applied as recorded.
            reason (str): User-facing explanation shown in the disabled tooltip,
                e.g. ``AppSpec.not_found_message``. Optional -- a generic line is
                used when omitted.

        Returns:
            bool: *available*, so a slot can ``if not self.sb.gate(...): return``.
        """
        return self._gates.gate(widget, available, reason)

    def recheck_gates(self) -> int:
        """Re-apply every live gate; return how many widgets were re-presented.

        The on-demand twin of the ``*_init`` re-fire, for the two things that
        re-fire cannot reach: a user who installs a missing app WHILE a panel is
        open, and a change to :attr:`unmet_policy` that should land on the panel
        already in front of them.

        A gate registered with a CALLABLE is re-evaluated, so a newly-installed
        app is discovered here; one registered with a plain bool is re-applied as
        recorded, which still picks up a policy change. Callers holding a cached
        probe (``ptk.AppSpec.path`` memoizes, deliberately) must invalidate it
        first -- ``AppSpec.refresh()`` -- or the callable will report the same
        answer it did before; ``Slots.recheck_app_gates`` does exactly that pair.

        Entries whose widget has been garbage-collected or whose underlying C++
        object is gone are pruned as they are found, so the registry cannot grow
        across panel rebuilds.
        """
        return self._gates.recheck_gates()

    def is_registered_ui(self, name: str) -> bool:
        """True if *name* matches a known UI file stem in the registry (no load is triggered)."""
        return self._widgets.is_registered_ui(name)

    def ui_name_resolves(self, name: str) -> bool:
        """True if *name* resolves to a UI, without triggering a load.

        Broader than :meth:`is_registered_ui`: a name resolves if it is a
        registered file stem OR a name the active UI handler can build on demand
        — e.g. a mayatk native Maya menu (``"key"``), which is not a ``.ui`` file
        but is produced by ``MayaUiHandler`` from ``MayaNativeMenus.MENU_MAPPING``.
        The file-stem-only ``is_registered_ui`` missed those handler-backed,
        lazily-built UIs, which is why a nav button whose ``target`` is a native
        menu fell back to its ``#submenu`` overlay on release (instead of opening
        the menu). Resolvability is queried via the handler's ``can_resolve`` hook
        (default = file stem), so no menu is actually built here; :meth:`get_ui`
        builds it, through the handler's ``get``, the first time it is asked.
        """
        return self._widgets.ui_name_resolves(name)

    def menu_button_target_name(self, widget) -> Optional[str]:
        """The registered UI name a ``MenuButton`` navigates to, or ``None``.

        Single source of truth for nav-button destination resolution, shared by the
        visibility auto-hide (:meth:`menu_button_target_resolves`) and the marking menu's
        click path (``MarkingMenu._resolve_button_menu``) so they can't drift — divergence
        here is what let a click resolve a different (or dead) target than the auto-hide saw.
        Two candidates, the registered base ``target`` preferred:

        * **Base-panel launcher** — a ``target`` that itself resolves to a UI (e.g. the
          polygons component buttons → the ``"polygons"`` panel; or a category button like
          ``"key"`` → the native Maya ``key`` menu the mayatk handler builds on demand).
          This is the original click behavior; preferred so a button that has both a base
          panel and a submenu still opens the base panel on click. Resolvability uses
          :meth:`ui_name_resolves` (file stem OR handler-backed) — not the file-stem-only
          :meth:`is_registered_ui`, which missed lazily-built native menus and made ``key``
          fall back to its overlay submenu on release ("the standalone menu never opened").
        * **Submenu launcher** — a bare ``target`` like ``"cameras"`` that does *not*
          resolve composes ``submenu_name()`` (``"cameras#lower#submenu"``), matching the
          hover path (``child_enterEvent``), which always opens the submenu.
        """
        return self._widgets.menu_button_target_name(widget)

    def menu_button_target_resolves(self, widget) -> bool:
        """True if a ``MenuButton``'s ``target`` resolves to a registered UI.

        See :meth:`menu_button_target_name` for the resolution rules — the visibility
        policy never hides a button that *does* go somewhere (a click would reach it).
        """
        return self._widgets.menu_button_target_resolves(widget)

    def apply_visibility_policy(self, widget) -> bool:
        """Hide a freshly-registered widget the current context can't serve.

        Two policies, applied at widget registration (``MainWindow.register_widget``):

        1. **``requires`` tag** — a Designer dynamic string property naming the feature
           tag(s) the widget needs (``"maya"``, ``"maya|blender"``; ``|``/comma/space
           separated alternatives). Hidden when the switchboard's ``context_tags`` is
           non-empty and shares no tag. An empty ``context_tags`` disables filtering.
        2. **Nav auto-hide** — a ``MenuButton`` whose ``target`` does not resolve against
           the UI registry navigates nowhere in this context and hides itself (no manual
           tags needed; an unported submenu disappears from every nav path that points
           at it). Resolution mirrors the live nav paths — see
           :meth:`menu_button_target_resolves`.

        Returns True when the widget was hidden; the reason is recorded on
        ``widget.hidden_by_policy`` for tooling/coverage reports.
        """
        return self._widgets.apply_visibility_policy(widget)

    def resolve_widget_class(
        self, class_name: str
    ) -> Optional[Type[QtWidgets.QWidget]]:
        """Return the widget class registered under the given name."""
        return self._widgets.resolve_widget_class(class_name)

    def get_icon(self, icon_name: str) -> QtGui.QIcon:
        """Get a registered icon by name.

        Parameters:
            icon_name (str): The name of the icon (without file extension).

        Returns:
            QIcon: The icon if found, or a null icon if not found.
        """
        return self._widgets.get_icon(icon_name)

    def register_widget(self, widget):
        """Register any custom widgets using the module names.
        Registered widgets can be accessed as properties. ex. sb.registered_widgets.PushButton()

        Parameters:
            widget (obj): The widget to register.

        Returns:
            (obj): The registered widget
        """
        return self._widgets.register_widget(widget)

    def get_widget(self, name, ui=None):
        """Case insensitive. Get the widget object/s from the given UI and name.

        Parameters:
            name (str): The object name of the widget. ie. 'b000'
            ui (str/obj): UI, or name of UI. ie. 'polygons'. If no nothing is given, the current UI will be used.
                    A UI object can be passed into this parameter, which will be used to get it's corresponding name.
        Returns:
            (obj) if name:  widget object with the given name from the current UI.
                    if ui and name: widget object with the given name from the given UI name.
            (list) if ui: all widgets for the given UI.
        """
        return self._widgets.get_widget(name, ui)

    def get_widget_from_slot(self, method):
        """Get the corresponding widget from a given method.

        Parameters:
            method (obj): The method in which to get the widget of.

        Returns:
            (obj) The widget of the same name. ie. <b000 widget> from <b000 method>.
        """
        return self._widgets.get_widget_from_slot(method)

    def is_widget(self, obj):
        """Returns True if the given obj is a valid widget.

        Parameters:
            obj (obj): An object to query.

        Returns:
            (bool)
        """
        return self._widgets.is_widget(obj)

    @staticmethod
    def get_parent_widgets(widget, object_names=False):
        """Get the all parent widgets of the given widget.

        Parameters:
            widget (QWidget): The widget to get parents of.
            object_names (bool): Return as object_names.

        Returns:
            (list) Object(s) or objectName(s)
        """
        return _Widgets.get_parent_widgets(widget, object_names)

    @staticmethod
    def get_all_windows(name=None):
        """Get Qt windows.

        Parameters:
            name (str): Return only windows having the given object name.

        Returns:
            (list) windows.
        """
        return _Widgets.get_all_windows(name)

    @staticmethod
    def get_all_widgets(name=None):
        """Get Qt widgets.

        Parameters:
            name (str): Return only widgets having the given object name.

        Returns:
            (list) widgets.
        """
        return _Widgets.get_all_widgets(name)

    @staticmethod
    def get_widget_at(pos, top_widget_only=True):
        """Get visible and enabled widget(s) located at the given position.
        As written, this will disable `TransparentForMouseEvents` on each widget queried.

        Parameters:
            pos (QPoint) = The global position at which to query.
            top_widget_only (bool): Return only the top-most widget,
                    otherwise widgets are returned in the order in which they overlap.
                    Disabling this option will cause overlapping windows to flash as
                    their attribute is changed and restored.
        Returns:
            (obj/list) list if not top_widget_only.

        Example:
            get_widget_at(QtGui.QCursor.pos())
        """
        return _Widgets.get_widget_at(pos, top_widget_only)

    # Private names read outside the switchboard and by _Slots / _EditorRegistry.
    _gate_registry = _Forward("_gates", "registry")
    _widget_is_alive = staticmethod(_Widgets.widget_is_alive)
    _get_widget_from_ui = staticmethod(_Widgets.get_widget_from_ui)
    _get_widgets_from_ui = _Widgets.get_widgets_from_ui

    # ── Shortcuts and commands (shortcuts.py) ─────────────────────────────────

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
        return self._shortcuts.register_slots_shortcuts(ui, slots_instance)

    def widget_has_shortcut(self, widget: QtWidgets.QWidget) -> bool:
        """Whether *widget*'s slot currently holds a bound keyboard shortcut.

        The live binding map answers this: ``_connected_shortcuts`` is keyed by
        slot method name and holds only what is bound right now, so a cleared
        binding drops out of it. Cheaper than :meth:`get_shortcut_registry`,
        which rebuilds every entry for the UI — this runs per item as a menu
        opens (``Menu._apply_shortcut_item_filter``).

        Parameters:
            widget (QtWidgets.QWidget): A registered widget; its objectName
                names the slot, and its ``ui`` says which Slots instance owns it.

        Returns:
            bool: ``True`` when a key is bound to that slot.
        """
        return self._shortcuts.widget_has_shortcut(widget)

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
        return self._shortcuts.get_shortcut_registry(ui)

    def get_static_shortcut_registry(self, ui_name: str) -> List[Dict[str, Any]]:
        """Build a UI's shortcut registry WITHOUT instantiating the UI.

        Resolves the slots class and widget objectNames from the registry and
        the ``.ui`` file on disk (not a live widget tree), reads user overrides
        from the same per-UI ``QSettings`` the live UI writes, and feeds them
        through the shared :meth:`_Shortcuts._build_shortcut_entries`. This lets a caller
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
        return self._shortcuts.get_static_shortcut_registry(ui_name)

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
        return self._shortcuts.set_user_shortcut(ui, slot_name, sequence, scope)

    def dispose_shortcuts(self) -> int:
        """Destroy every shortcut this Switchboard registered; returns the count.

        Application-scoped shortcuts are parented to the HOST window rather than
        to the tool's own UI (see :meth:`_Shortcuts._create_switchboard_shortcut`) so they
        keep firing while the tool is hidden. The consequence is that Qt, not
        this Switchboard, owns their lifetime: dropping the Switchboard and its
        slot instances leaves them armed on that host forever, because a
        parented QObject does not die with the Python wrapper that made it.

        That is only a leak until the UI is rebuilt in the same session — the
        dev-reload path (tentacle's ``Settings > Reload Scripts``). Then the
        rebuild arms a SECOND shortcut on the same sequence and the same parent,
        which Qt reports as an ambiguous overload and answers by firing NEITHER.
        The binding dies silently and stays dead until the host restarts.
        Measured in a live Maya: one reload took two user hotkeys from one armed
        shortcut each to three each.

        So a host tearing down a Switchboard has to say so, and this is that
        call — see ``MarkingMenu.retire``, which makes it part of retiring an
        instance. Idempotent: a second call finds nothing left and returns 0.
        """
        return self._shortcuts.dispose_shortcuts()

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
        return self._shortcuts.register_command(
            name,
            callback,
            label=label,
            sequence=sequence,
            scope=scope,
            doc=doc,
            hidden=hidden,
            editable=editable,
            bind=bind,
            clearable=clearable,
            on_rebind=on_rebind,
            value_getter=value_getter,
        )

    def unregister_command(self, name: str) -> None:
        """Remove a command and tear down its live shortcut, if any."""
        return self._shortcuts.unregister_command(name)

    def get_command_registry(self) -> List[Dict[str, Any]]:
        """Registry entries for every command, in the slot-shortcut entry shape.

        Each entry carries ``"command": True`` so the editor renders it under the
        "Commands" pseudo-UI with a colour-coded tag and routes edits through
        :meth:`set_command_shortcut`. Reuses :meth:`_Shortcuts._build_shortcut_entries` for
        identical default/override resolution.
        """
        return self._shortcuts.get_command_registry()

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
        return self._shortcuts.set_command_shortcut(name, sequence, scope)

    def set_binding_hidden(self, name: str, hidden: bool = True) -> None:
        """Hide/show command *name* in the shortcut editor's default view.

        The post-hoc twin of the ``hidden=`` registration kwarg. A no-op for an
        unknown command.
        """
        return self._shortcuts.set_binding_hidden(name, hidden)

    def set_binding_editable(self, name: str, editable: bool = True) -> None:
        """Allow/forbid the user rebinding command *name* in the editor.

        The post-hoc twin of the ``editable=`` registration kwarg. A no-op for an
        unknown command.
        """
        return self._shortcuts.set_binding_editable(name, editable)

    # Private names read outside the switchboard (its tests included).
    _commands = _Forward("_shortcuts", "commands")
    _command_shortcuts = _Forward("_shortcuts", "command_shortcuts")
    _deferred_slot_shortcuts = _Forward("_shortcuts", "deferred_slot_shortcuts")
    _deferred_slots_scanned = _Forward("_shortcuts", "deferred_slots_scanned")
    _host_suffix = _Forward("_shortcuts", "host_suffix")
    _shortcut_ns = _Forward("_shortcuts", "shortcut_ns")
    _host_namespaced_branch = _Forward("_shortcuts", "host_namespaced_branch")
    _slot_shortcut_key = _Forward("_shortcuts", "slot_shortcut_key")
    _command_settings = _Forward("_shortcuts", "command_settings")
    _command_key = _Forward("_shortcuts", "command_key")
    _command_host = _Forward("_shortcuts", "command_host")
    _bind_command = _Forward("_shortcuts", "bind_command")
    _bind_pending_commands = _Forward("_shortcuts", "bind_pending_commands")
    _ui_names_with_shortcut_overrides = _Forward(
        "_shortcuts", "ui_names_with_shortcut_overrides"
    )
    _bind_deferred_slot_shortcuts = _Forward(
        "_shortcuts", "bind_deferred_slot_shortcuts"
    )
    _make_deferred_slot_callback = _Forward("_shortcuts", "make_deferred_slot_callback")
    _dispose_deferred_slot_shortcuts = _Forward(
        "_shortcuts", "dispose_deferred_slot_shortcuts"
    )
    _dispose_shortcut = staticmethod(_Shortcuts.dispose_shortcut)
    _make_host_shortcut = staticmethod(_Shortcuts.make_host_shortcut)

    # ── Slots (slots.py) ──────────────────────────────────────────────────────

    #: Which widgets are tracked, and the signal a slot connects to when it
    #: names none -- owned by :class:`_Slots` (slots.py).
    default_signals = _Slots.default_signals

    def get_default_signals(self, widget: QtWidgets.QWidget) -> set:
        """Retrieves the default signals for a given widget type.

        This method iterates over a dictionary of default signals, which maps widget types to signal names.
        If the widget is an instance of a type in the dictionary, the method checks if the widget has a signal
        with the corresponding name. If it does, the signal is added to a set of signals.

        The method returns this set of signals, which represents all the default signals that the widget has.

        Parameters:
            widget (QWidget): The widget to get the default signals for.

        Returns:
            set: A set of signals that the widget has, according to the default signals dictionary.
        """
        return self._slots.get_default_signals(widget)

    def get_available_signals(self, widget, derived=True, exc=None):
        """Get all available signals for a type of widget.

        Parameters:
            widget (str/obj): The widget to get signals for.
            derived (bool): Return signals from all derived classes instead of just the given widget class.
                    ex. get: QObject, QWidget, QAbstractButton, QPushButton signals from 'QPushButton'
            exc (list): Exclude any classes in this list. ex. exc=[QtCore.QObject, 'QWidget']

        Returns:
            (set)

        Example: get_available_signals(QtWidgets.QPushButton)
            would return:
                clicked (QAbstractButton)
                pressed (QAbstractButton)
                released (QAbstractButton)
                toggled (QAbstractButton)
                customContextMenuRequested (QWidget)
                windowIconChanged (QWidget)
                windowIconTextChanged (QWidget)
                windowTitleChanged (QWidget)
                destroyed (QObject)
                objectNameChanged (QObject)
        """
        return self._slots.get_available_signals(widget, derived, exc)

    def slots_instantiated(self, key: str) -> bool:
        return self._slots.slots_instantiated(key)

    def get_slots_instance(self, ui: Union[str, QtWidgets.QWidget]) -> Optional[object]:
        """Get or create a slots instance for the given UI."""
        return self._slots.get_slots_instance(ui)

    def init_slot(self, widget: QtWidgets.QWidget, block_signals: bool = True) -> None:
        return self._slots.init_slot(widget, block_signals)

    def call_slot(self, widget: QtWidgets.QWidget, *args, **kwargs):
        """Call a slot method for a widget.
        Retrieves the slot associated with the widget's UI and calls it with the provided arguments.
        """
        return self._slots.call_slot(widget, *args, **kwargs)

    def get_slot(
        self,
        slot_class: object,
        slot_name: str,
        wrap: bool = False,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> Optional[Callable]:
        return self._slots.get_slot(slot_class, slot_name, wrap, widget)

    def get_slot_from_widget(
        self, widget: QtWidgets.QWidget, wrap: bool = False
    ) -> Optional[Callable]:
        return self._slots.get_slot_from_widget(widget, wrap)

    def mark_missing_slot(self, widget):
        """Built-in ``on_missing_slot`` hook: grey the widget + explain in its tooltip.

        Gives a live "not-yet-built" map during development (installed by setting
        ``UITK_MARK_MISSING_SLOTS`` in the environment, or passed explicitly as the
        switchboard's ``on_missing_slot``). Never the production default — it would
        repaint every unwired widget at init.
        """
        return self._slots.mark_missing_slot(widget)

    def notify_missing_slot(self, widget):
        """Invoke the missing-slot policy hook for a widget ``connect_slot`` couldn't wire.

        Only fires for widgets the switchboard *would* have connected (one with a
        :meth:`_Slots._slot_signal`), and never for nav ``MenuButton``s (they own navigation, not a
        slot). No-op when no ``on_missing_slot`` hook is set — the production default.
        """
        return self._slots.notify_missing_slot(widget)

    def connect_slot(self, widget, slot=None):
        """Connect a widget's signals to its slot."""
        return self._slots.connect_slot(widget, slot)

    def slot_history(
        self,
        index=None,
        allow_duplicates=False,
        inc=None,
        exc=None,
        add=None,
        remove=None,
        length=200,
    ):
        """Get the slot history.

        Parameters:
            index (int/slice, optional): Index or slice to return from the history. If not provided, returns the full list.
            allow_duplicates (bool): When returning a list, allows for duplicate names in the returned list.
            inc (str/int/list): The objects(s) to include.
                            supports using the '*' operator: startswith*, *endswith, *contains*
                            Will include all items that satisfy ANY of the given search terms.
                            meaning: '*.png' and '*Normal*' returns all strings ending in '.png' AND all
                            strings containing 'Normal'. NOT strings satisfying both terms.
            exc (str/int/list): The objects(s) to exclude. Similar to include.
                            exclude take precedence over include.
            add (object/list, optional): New entrie(s) to append to the slot history.
            remove (object/list, optional): Entry/entries to remove from the slot history.
            length (int): Maximum length of the slot history. If the history exceeds this length, it will be truncated.

        Returns:
            (object/list): Slot method(s) based on index or slice.
        """
        return self._slots.slot_history(
            index, allow_duplicates, inc, exc, add, remove, length
        )

    # Private names read outside the switchboard and by _Shortcuts (slot lookup).
    _find_slots_class = _Forward("_slots", "find_slots_class")
    _perform_slot_init = _Forward("_slots", "perform_slot_init")
    _process_deferred_widgets = _Forward("_slots", "process_deferred_widgets")
    _revive_deferred_widget = _Forward("_slots", "revive_deferred_widget")
    _add_to_placeholder = _Forward("_slots", "add_to_placeholder")
    _last_slot_wrapper = _Forward("_slots", "last_wrapper")
    _suppress_slot_capture = _Forward("_slots", "suppress_capture")


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    from uitk import example

    sb = Switchboard(ui_source=example, slot_source=example.example_slots)
    ui = sb.example
    # ui.set_attributes(WA_TranslucentBackground=True)
    # ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)
    # ui.style.set(theme="dark", style_class="translucentBgWithBorder")

    # print(repr(ui))
    # print(sb.QWidget)
    # ui.show(pos="screen", app_exec=True)

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
