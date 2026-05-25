# !/usr/bin/python
# coding=utf-8
import re
import os
import sys
import inspect
from typing import List, Union, Optional, Iterable
from xml.etree.ElementTree import ElementTree, Element, SubElement
import xml.etree.ElementTree as ET
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk

# Composition pieces — private to this package:
from uitk.switchboard.slots import SwitchboardSlotsMixin
from uitk.switchboard.shortcuts import SwitchboardShortcutMixin
from uitk.switchboard.widgets import SwitchboardWidgetMixin
from uitk.switchboard.utils import SwitchboardUtilsMixin
from uitk.switchboard.names import SwitchboardNameMixin
from uitk.switchboard.editors import SwitchboardEditorsMixin
from uitk.switchboard.style import SwitchboardStyleMixin

# Generic infrastructure (shared with non-Switchboard widgets):
from uitk.file_manager import FileManager
from uitk.widgets.mixins.convert import ConvertMixin
from uitk.widgets.mixins.settings_manager import SettingsManager
from uitk.loaders import CompiledLoader, RuntimeLoader


class Switchboard(
    QtCore.QObject,
    ptk.HelpMixin,
    ptk.LoggingMixin,
    SwitchboardSlotsMixin,
    SwitchboardShortcutMixin,
    SwitchboardWidgetMixin,
    SwitchboardUtilsMixin,
    SwitchboardNameMixin,
    SwitchboardEditorsMixin,
    SwitchboardStyleMixin,
):
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
                    ui = sb.my_project
                    ui.set_attributes(WA_TranslucentBackground=True)
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

    # Use the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

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
    ) -> None:
        super().__init__(parent)
        """ """
        self.logger.setLevel(log_level)

        # Ensure plain QtWidgets (e.g. unpromoted QLineEdit in .ui files) expose
        # `widget.option_box`. patch_widget_class is idempotent (no-op if the
        # class already has the property), so repeated Switchboard inits are safe.
        from uitk.widgets.optionBox.utils import patch_common_widgets

        patch_common_widgets()

        self._loader = self._build_loader(loader)

        self.tag_delimiter = tag_delimiter or self.TAG_DELIMITER
        self.ui_name_delimiters = ui_name_delimiters or self.UI_NAME_DELIMITER
        self.registry = FileManager()
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
            resolver=self._resolve_widget,
            use_weakref=True,
        )  # All registered widgets.
        self.registered_icons = ptk.NamespaceHandler(
            self,
            "registered_icons",
            resolver=self._resolve_icon,
            use_weakref=True,
        )  # All registered icons.

        self.slot_instances = ptk.NamespaceHandler(
            self,
            "slot_instances",
            resolver=self.get_slots_instance,
        )  # All slot instances.

        self.settings = SettingsManager(namespace="switchboard")
        self.configurable = self.settings.branch("configurable")  # Persistent config

        self._current_ui = None
        self._ui_history = []  # Ordered ui history.
        self._slot_history = []  # Previously called slots.
        self._synced_pairs = set()  # Hashed values representing synced widgets.
        self.convert = ConvertMixin()

        # Register any handlers passed during construction (after configurable is ready)
        if self._pending_handlers:
            for name, obj in self._pending_handlers.items():
                if getattr(self.handlers, name, None):
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
          - ``"compiled"`` (default) — :class:`CompiledLoader`. pyside6-uic
            produces a hashed _ui.py per .ui; loads through Python imports.
          - ``"runtime"`` — :class:`RuntimeLoader`. ``QtUiTools.QUiLoader``
            reads .ui XML directly each time. No on-disk artifact.
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
        missing = [m for m in self._LOADER_CONTRACT if not callable(getattr(instance, m, None))]
        if missing:
            raise TypeError(
                f"Loader {type(instance).__name__} is missing required "
                f"method(s): {missing}. The loader contract is "
                f"{list(self._LOADER_CONTRACT)}."
            )
        return instance

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
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
        self._ui_history.append(ui)

    @property
    def prev_ui(self) -> QtWidgets.QWidget:
        """Get the previous UI from history.

        Returns:
            (obj)
        """
        return self.ui_history(-1)

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
        """Resolver for dynamically loading UIs when accessed via NamespaceHandler."""
        self.logger.debug(f"[{attr_name}] Resolving UI")

        actual_ui_name = self.find_ui_filename(attr_name, unique_match=True)
        if not actual_ui_name:
            return self._resolve_ui_using_slots(attr_name)

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
            self.logger.debug(
                f"[on_ui_loaded] emit failed for {name!r}", exc_info=True
            )
        return ui

    def _resolve_ui_using_slots(self, attr_name) -> QtWidgets.QWidget:
        if getattr(self, "_resolving_ui", None) == attr_name:
            raise RuntimeError(f"Recursive resolution detected for key: '{attr_name}'")
        self._resolving_ui = attr_name
        try:
            found_slots = self._find_slots_class(attr_name)
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
        """Return the configuration for the Switchboard registries."""
        return {
            "ui_registry": {
                "objects": ui_source,
                "inc_files": "*.ui",
            },
            "slot_registry": {
                "objects": slot_source,
                "fields": ["classname", "classobj", "filename", "filepath"],
                "inc_files": "*.py",
                "exc_files": "*_ui.py",
            },
            "widget_registry": {
                "objects": widget_source,
                "fields": ["classname", "classobj", "filename", "filepath"],
                "inc_files": "*.py",
                "exc_files": "*_ui.py",
            },
            "icon_registry": {
                "objects": icon_source,
                "inc_files": ["*.svg", "*.png", "*.jpg", "*.jpeg", "*.bmp", "*.ico"],
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
        validate=0,
        tags=None,
    ):
        """Add new locations to the Switchboard registries.

        Args:
            ui_location: Path(s) or module(s) containing .ui files.
            slot_location: Path(s) or module(s) containing slot classes.
            widget_location: Path(s) or module(s) containing custom widgets.
            icon_location: Path(s) or module(s) containing icons.
            base_dir: Base directory for relative paths. Defaults to caller's directory.
            recursive: If True, directory locations are scanned recursively.
            validate: Validation level for paths (0=None, 1=Warn, 2=Raise).
            tags: Optional set/list of tags to apply to UIs loaded from ui_location.
                  When a UI file from this location is loaded via add_ui(), these
                  tags are automatically merged into its tag set.
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
            # Note: FileContainer.extend handles duplicates if configured,
            # but we can do a quick check here if it's a single path string.
            # However, since location can be a list or module, simple string check isn't enough.
            # We rely on FileContainer/FileManager to resolve and handle it.

            # Helper to validate a single path item if validation is requested
            def _validate_item(item):
                path_to_check = item
                if inspect.ismodule(item):
                    path_to_check = (
                        os.path.dirname(item.__file__)
                        if hasattr(item, "__file__")
                        else None
                    )
                elif inspect.isclass(item):
                    path_to_check = inspect.getfile(item)

                if path_to_check:
                    self.registry.resolve_path(
                        path_to_check,
                        base_dir=base_dir,
                        validate=validate,
                        path_type=type_name,
                    )

            if validate > 0:
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

            registry.extend(location, base_dir=base_dir, recursive=recursive)
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
        """Load a UI from the given .ui path via its compiled _ui.py module."""
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
                if norm_path.startswith(src_dir + os.sep) or norm_path == src_dir:
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
            settings=self.settings.branch(name),
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
        pattern = re.sub(r"_", r"[^0-9a-zA-Z]", legal_name)
        filenames = self.registry.ui_registry.get("filename")
        matches = [name for name in filenames if re.fullmatch(pattern, name)]

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
        """Get the UI history."""
        self._ui_history = self._ui_history[-200:]
        if not allow_duplicates:
            self._ui_history = list(dict.fromkeys(self._ui_history[::-1]))[::-1]

        history = self._ui_history
        if inc or exc:
            history = ptk.filter_list(history, inc, exc, lambda u: u.objectName())

        if index is None:
            self.logger.debug("[ui_history] Returning full UI history list")
            return history
        else:
            try:
                result = history[index]
                if isinstance(result, list):
                    self.logger.debug(
                        f"[ui_history] Returning history slice: {[u.objectName() for u in result]}"
                    )
                else:
                    self.logger.debug(
                        f"[ui_history] Returning UI: {result.objectName()}"
                    )
                return result
            except IndexError:
                self.logger.debug(f"[ui_history] Index out of range: {index}")
                return [] if isinstance(index, int) else None


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
