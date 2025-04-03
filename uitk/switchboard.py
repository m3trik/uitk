# !/usr/bin/python
# coding=utf-8
import re
import sys
import json
import inspect
import traceback
from typing import List, Union, Optional
from xml.etree.ElementTree import ElementTree
from qtpy import QtCore, QtGui, QtWidgets, QtUiTools
import pythontk as ptk

# From this package:
from uitk.file_manager import FileManager
from uitk.widgets.mixins import ConvertMixin


class Switchboard(QtUiTools.QUiLoader, ptk.HelpMixin, ptk.LoggingMixin):
    """Switchboard is a dynamic UI loader and event handler for PyQt/PySide applications.
    It facilitates the loading of UI files, dynamic assignment of properties, and
    management of signal-slot connections in a modular and organized manner.

    This class streamlines the process of integrating UI files created with Qt Designer,
    custom widget classes, and Python slot classes into your application. It adds convenience
    methods and properties to each slot class instance, enabling easy access to the Switchboard's
    functionality within the slots class.

    Attributes:
        default_signals (dict): Default signals to be connected per widget type when no specific signals are defined.
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
                    ui.set_style(theme="dark", style_class="translucentBgWithBorder")
                    return ui

        - Instantiating and displaying the UI:
            ui = MyProjectUi(parent)
            ui.show(pos="screen", app_exec=True)
    """

    QtCore = QtCore
    QtGui = QtGui
    QtWidgets = QtWidgets
    QtUiTools = QtUiTools

    # Use the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    default_signals = {  # the signals to be connected per widget type should no signals be specified using the slot decorator.
        QtWidgets.QAction: "triggered",
        QtWidgets.QLabel: "released",
        QtWidgets.QPushButton: "clicked",
        QtWidgets.QListWidget: "itemClicked",
        QtWidgets.QTreeWidget: "itemClicked",
        QtWidgets.QComboBox: "currentIndexChanged",
        QtWidgets.QSpinBox: "valueChanged",
        QtWidgets.QDoubleSpinBox: "valueChanged",
        QtWidgets.QCheckBox: "stateChanged",
        QtWidgets.QRadioButton: "toggled",
        QtWidgets.QLineEdit: "textChanged",
        QtWidgets.QTextEdit: "textChanged",
        QtWidgets.QSlider: "valueChanged",
        QtWidgets.QProgressBar: "valueChanged",
        QtWidgets.QDial: "valueChanged",
        QtWidgets.QScrollBar: "valueChanged",
        QtWidgets.QDateEdit: "dateChanged",
        QtWidgets.QDateTimeEdit: "dateTimeChanged",
        QtWidgets.QTimeEdit: "timeChanged",
        QtWidgets.QMenu: "triggered",
        QtWidgets.QMenuBar: "triggered",
        QtWidgets.QTabBar: "currentChanged",
        QtWidgets.QTabWidget: "currentChanged",
        QtWidgets.QToolBox: "currentChanged",
        QtWidgets.QStackedWidget: "currentChanged",
    }

    def __init__(
        self,
        parent=None,
        ui_source=None,
        slot_source=None,
        widget_source=None,
        ui_name_delimiters=[".", "#"],
        log_level: str = "WARNING",
    ):
        super().__init__(parent)
        """ """
        self.logger.setLevel(log_level)

        self.ui_name_delimiters = ui_name_delimiters

        self.registry = FileManager()
        base_dir = 1 if not __name__ == "__main__" else 0

        # Initialize registries directly
        self.registry.create(
            "ui_registry",
            ui_source,
            inc_files="*.ui",
            base_dir=base_dir,
        )
        self.registry.create(
            "slot_registry",
            slot_source,
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
            base_dir=base_dir,
        )
        self.registry.create(
            "widget_registry",
            widget_source,
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
            base_dir=base_dir,
        )

        # Include this package's widgets
        self.registry.widget_registry.extend("widgets", base_dir=0)

        self.loaded_ui = ptk.NamespaceHandler(
            self,
            "loaded_ui",
            resolver=self._resolve_ui,
        )  # All loaded ui.
        self.registered_widgets = ptk.NamespaceHandler(
            self,
            "registered_widgets",
            resolver=self._resolve_widget,
        )  # All registered custom widgets.
        self._current_ui = None
        self._ui_history = []  # Ordered ui history.
        self._slot_history = []  # Previously called slots.
        self._synced_pairs = set()  # Hashed values representing synced widgets.
        self._gc_protect = set()  # Objects protected from garbage collection.

        self.convert = ConvertMixin()

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
            name = self.format_ui_name(ui_filepath)
            ui = self.add_ui(widget=newly_loaded_ui, name=name, path=ui_filepath)
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

    def _resolve_ui(self, attr_name):
        """Resolver for dynamically loading UIs when accessed via NamespaceHandler.

        Parameters:
            attr_name (str): The name of the UI to load.

        Returns:
            (obj) The loaded UI object.
        """
        self.logger.debug(f"Resolving UI: {attr_name}")

        # Check if the attribute matches a UI file
        actual_ui_name = self.find_ui_filename(attr_name, unique_match=True)
        if not actual_ui_name:  # Check if the attribute matches a slot class
            return self._resolve_ui_using_slots(attr_name)

        ui_filepath = self.registry.ui_registry.get(
            filename=actual_ui_name, return_field="filepath"
        )
        if not ui_filepath:
            raise AttributeError(f"Unable to resolve filepath for '{attr_name}'.")

        loaded_ui = self.load_ui(ui_filepath)
        name = ptk.format_path(ui_filepath, "name")
        ui = self.add_ui(widget=loaded_ui, name=name, path=ui_filepath)

        self.logger.debug(f"UI '{name}' loaded successfully.")
        return ui

    def _resolve_ui_using_slots(self, attr_name) -> QtWidgets.QWidget:
        """Resolve a UI using a slot class if no UI file is found.
        Accounts for scenarios where the UI is registered during slot class instantiation.

        Parameters:
            attr_name (str): The name of the UI to load.

        Returns:
            (obj) The loaded UI object.
        """
        # Check if it matches a slot class
        found_slots = self._find_slot_class(attr_name)
        if not found_slots:
            raise AttributeError(f"Slot class '{attr_name}' not found.")

        try:  # Ensure UI does not exist before adding a new one
            added_ui = self.loaded_ui[attr_name]
        except KeyError:
            added_ui = self.add_ui(name=attr_name)
            self.loaded_ui[attr_name] = added_ui

        self.set_slot_class(added_ui, found_slots)
        return added_ui

    def _resolve_widget(self, attr_name):
        """Resolver for dynamically loading registered widgets when accessed.

        Parameters:
            attr_name (str): The name of the widget to resolve.

        Returns:
            object: The widget object if it's found, or None if it's not found.
        """
        self.logger.debug(f"Resolving widget: {attr_name}")

        # Check if the attribute matches a widget file
        widget_class = self.registry.widget_registry.get(
            classname=attr_name, return_field="classobj"
        )
        if not widget_class:
            raise AttributeError(f"Unable to resolve widget class for '{attr_name}'.")

        widget = self.register_widget(widget_class)
        self.logger.debug(
            f"Widget class '{widget_class.__name__}' loaded successfully."
        )
        return widget

    def register(
        self,
        ui_location=None,
        slot_location=None,
        widget_location=None,
        base_dir=1,
        validate=0,
    ):
        """Add new locations to the Switchboard.

        Parameters:
            ui_location (optional): Path to the UI file.
            slot_location (optional): Slot class.
            widget_location (optional): Path to widget files.
            base_dir (optional): Base directory for relative paths. Derived from the call stack.
                0 for this modules dir, 1 for the caller module, etc.
            validate (int): Validation level:
                0: No validation
                1: Warn on invalid path
                2: Raise on invalid path
        """
        # UI path
        if ui_location and not self.registry.contains_location(
            ui_location, "ui_registry"
        ):
            if self.registry.resolve_path(
                ui_location, base_dir=base_dir, validate=validate, path_type="UI"
            ):
                self.registry.ui_registry.extend(ui_location, base_dir=base_dir)

        # Slot path
        if slot_location and not self.registry.contains_location(
            slot_location, "slot_registry"
        ):
            slot_path = (
                inspect.getfile(slot_location)
                if inspect.isclass(slot_location)
                else slot_location
            )
            if self.registry.resolve_path(
                slot_path, base_dir=base_dir, validate=validate, path_type="Slot"
            ):
                self.registry.slot_registry.extend(slot_location, base_dir=base_dir)

        # Widget path
        if widget_location and not self.registry.contains_location(
            widget_location, "widget_registry"
        ):
            if self.registry.resolve_path(
                widget_location,
                base_dir=base_dir,
                validate=validate,
                path_type="Widget",
            ):
                self.registry.widget_registry.extend(widget_location, base_dir=base_dir)

    def load_all_ui(self) -> list:
        """Extends the 'load_ui' method to load all UI from a given path.

        Returns:
            (list) QWidget(s).
        """
        filepaths = self.registry.ui_registry.get("filepath")
        return [self.load_ui(f) for f in filepaths]

    def load_ui(self, file: str) -> QtWidgets.QMainWindow:
        """Loads a UI from the given path to the UI file and adds it to the switchboard.

        Parameters:
            file (str): The full file path to the UI file.

        Returns:
            MainWindow: The UI wrapped in the MainWindow class.
        """
        # Register any custom widgets found in the UI file.
        custom_widgets = self.get_property_from_ui_file(file, "customwidget")
        for widget in custom_widgets:
            try:
                class_name = widget[0][1]
            except IndexError:
                continue

            if class_name not in self.registered_widgets.keys():
                widget_class_info = self.registry.widget_registry.get(
                    classname=class_name, return_field="classobj"
                )
                if widget_class_info:
                    self.register_widget(widget_class_info)

        # Load the UI file using QUiLoader.
        loaded_ui = self.load(file)
        return loaded_ui

    def _add_existing_wrapped_window(
        self, window: QtWidgets.QMainWindow, name: Optional[str] = None
    ) -> QtWidgets.QMainWindow:
        """Add an existing MainWindow (already wrapped) to this Switchboard.

        Parameters:
            window (QMainWindow): The existing MainWindow to add.
            name (str, optional): Override name for the UI. Updates window.name if provided.

        Returns:
            QMainWindow: The added window.
        """
        if name:
            window.name = name

        name = window.name
        if name in self.loaded_ui:
            self.logger.warning(f"UI '{name}' already exists in this Switchboard.")
            return self.loaded_ui[name]

        self.loaded_ui[name] = window

        if not hasattr(window, "_slots"):
            try:
                slot_class = self._find_slot_class(window)
                if slot_class:
                    self.set_slot_class(window, slot_class)
            except Exception as e:
                self.logger.warning(f"Failed to set slot class for UI '{name}': {e}")

        self.logger.debug(f"Added existing wrapped window '{name}'.")
        return window

    def add_ui(
        self,
        widget: Optional[QtWidgets.QWidget] = None,
        name: str = None,
        tags: set = None,
        path: str = None,
        overwrite: bool = False,
        **kwargs,
    ) -> QtWidgets.QMainWindow:
        """Adds a given QWidget or QMainWindow to the Switchboard wrapped in MainWindow.

        Parameters:
            widget (QWidget or QMainWindow, optional): Central widget or MainWindow instance.
            name (str, optional): Custom UI name.
            tags (set, optional): Tags for the UI.
            path (str, optional): Associated path.
            overwrite (bool, optional): If True, overwrite existing UI. Defaults to False.
            **kwargs: Additional keyword arguments for MainWindow.

        Returns:
            QMainWindow: Wrapped UI instance.
        """
        derived_name = name or (
            widget.objectName() if widget and widget.objectName() else None
        )

        if derived_name in self.loaded_ui:
            if not overwrite:
                self.logger.debug(
                    f"UI '{derived_name}' already exists. Returning existing."
                )
                return self.loaded_ui[derived_name]

            self.logger.debug(f"Overwriting existing UI '{derived_name}'.")
            del self.loaded_ui[derived_name]

        if isinstance(widget, self.registered_widgets.MainWindow):
            return self._add_existing_wrapped_window(widget, name=derived_name)

        # continue normal wrapping logic
        central_widget = (
            widget.centralWidget()
            if isinstance(widget, QtWidgets.QMainWindow) and widget.centralWidget()
            else widget
        )

        tags = tags or (self._parse_tags(derived_name) if derived_name else None)
        path = ptk.format_path(path, "path") if path else None

        main_window = self.registered_widgets.MainWindow(
            switchboard_instance=self,
            central_widget=central_widget,
            name=derived_name,
            tags=tags,
            path=path,
            **kwargs,
        )
        self.loaded_ui[derived_name] = main_window

        self.logger.debug(
            f"MainWindow Added: Name={main_window.name}, Tags={main_window.tags}, Path={main_window.path}"
        )
        return main_window

    def get_ui(self, ui=None) -> QtWidgets.QWidget:
        """Get a dynamic UI using its string name, or if no argument is given, return the current UI.

        Parameters:
            ui (str/list/QWidget): The UI or name(s) of the UI.

        Raises:
            ValueError: If the given UI is of an incorrect datatype.

        Returns:
            (obj/list): If a list is given, a list is returned. Otherwise, a QWidget object is returned.
        """
        if isinstance(ui, QtWidgets.QWidget):
            return ui

        elif isinstance(ui, str):
            return getattr(self.loaded_ui, ui)

        elif isinstance(ui, (list, set, tuple)):
            return [self.get_ui(u) for u in ui]

        elif ui is None:
            return self.current_ui

        else:
            raise ValueError(
                f"Invalid datatype for ui: Expected str or QWidget, got {type(ui)}"
            )

    def set_slot_class(self, ui, clss):
        """This method sets the slot class instance for a loaded dynamic UI object."""
        self.logger.debug(f"Setting slot class for UI: {ui}")

        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")

        def accepts_switchboard(clss):
            """Check if the class accepts the switchboard as an argument."""
            init_params = inspect.signature(clss.__init__).parameters
            return "switchboard" in init_params or any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in init_params.values()
            )

        kwargs = {"switchboard": self} if accepts_switchboard(clss) else {}

        try:
            instance = clss(**kwargs)
        except Exception:
            self.logger.error(
                f"Failed to instantiate slot class '{clss.__name__}' for UI '{ui.name}':\n{traceback.format_exc()}"
            )
            return None

        ui._slots = instance
        self.logger.debug(f"Slot class {ui._slots} set for UI: {ui.name}")
        return instance

    def get_slot_class(self, ui):
        """This function tries to get a class instance of the slots module from a dynamic UI object.
        If it doesn't exist, it tries to import it from a specified location or from the parent menu.
        If it's found, it's set and returned, otherwise None is returned.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.

        Returns:
            object: A class instance.
        """
        self.logger.debug(f"Getting slot class for UI: {ui}")

        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")

        if hasattr(ui, "_slots"):  # Return the existing slot class
            self.logger.debug(f"Returning existing slot class {ui._slots}.")
            return ui._slots

        try:  # If no slots are set, attempt to find the slot class
            found_class = self._find_slot_class(ui)
        except ValueError:
            self.logger.info(traceback.format_exc())
            found_class = None

        # If slot class is not found, search for relatives' slot classes
        if not found_class:
            self.logger.debug(
                f"Slot class not found for '{ui}'. Searching for relatives."
            )
            for relative_name in self.get_ui_relatives(ui, upstream=True, reverse=True):
                relative_ui = self.get_ui(relative_name)
                if relative_ui:
                    self.logger.debug(
                        f"Searching for slot class in relative '{relative_ui}'."
                    )
                    try:
                        found_class = self._find_slot_class(relative_ui)
                        self.logger.debug(
                            f"Slot class found for '{relative_ui}': {found_class}"
                        )
                        break
                    except ValueError:
                        self.logger.info(traceback.format_exc())

        # If a class is found, set it as the slot class for the UI
        if found_class:
            slots_instance = self.set_slot_class(ui, found_class)
            return slots_instance

        # If no slot class is found, return None
        return None

    def _find_slot_class(self, ui: Union[str, QtWidgets.QWidget]) -> Optional[object]:
        """Find the slot class associated with the given UI by following a specific naming convention.

        This method takes a UI object or a UI name (string) and retrieves the associated slot class based on
        the legal name without tags. It constructs possible class names by capitalizing each word, removing underscores,
        and considering both the original name and a version with the 'Slots' suffix.

        Parameters:
            ui (Union[str, QWidget]): A UI object or a string representing the UI name.

        Returns:
            object: The matched slot class, if found. If no corresponding slot class is found, returns None.
        """
        # Get the UI name
        if isinstance(ui, QtWidgets.QWidget):
            name = ui.objectName()
            if not name:
                self.logger.warning(
                    f"Failed to extract a valid name from '{ui}'. No 'name' attribute found."
                )
                return None
        else:
            name = ui

        # Extract the name without tags
        name_no_tags = "".join(name.split("#")[0])
        # Log a warning if the name_no_tags is empty and return None
        if not name_no_tags:
            self.logger.warning(f"Failed to extract a valid name from '{name}'.")
            return None

        # Convert the name to its legal form
        legal_name_no_tags = self.convert_to_legal_name(name_no_tags)
        # Construct possible class names based on the legal name
        possible_class_name = legal_name_no_tags.title().replace("_", "")
        try_names = [f"{possible_class_name}Slots", possible_class_name]

        # Search for the class in the slot registry
        for name in try_names:
            found_class = self.registry.slot_registry.get(
                classname=name, return_field="classobj"
            )
            if found_class:
                return found_class

        return None

    def get_available_signals(self, widget, derived=True, exc=[]):
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
        signals = set()
        clss = widget if isinstance(widget, type) else type(widget)
        signal_type = type(QtCore.Signal())
        for subcls in clss.mro():
            clsname = f"{subcls.__module__}.{subcls.__name__}"
            for k, v in sorted(vars(subcls).items()):
                if isinstance(v, signal_type):
                    if (not derived and clsname != clss.__name__) or (
                        exc and (clss in exc or clss.__name__ in exc)
                    ):  # if signal is from parent class QAbstractButton and given widget is QPushButton:
                        continue
                    signals.add(k)
        return signals

    def get_default_signals(self, widget):
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
        signals = set()
        for widget_type, signal_name in self.default_signals.items():
            if isinstance(widget, widget_type):
                signal = getattr(widget, signal_name, None)
                if signal is not None:
                    signals.add(signal)
        return signals

    def connect_slots(self, ui, widgets=None):
        """Connects the default slots to their corresponding signals for all widgets of a given UI.

        This method iterates over all widgets of the UI, and for each widget, it calls the `connect_slot` method
        to connect the widget's default slot to its corresponding signal.

        If a specific set of widgets is provided, the method only connects the slots for these widgets.

        After all slots are connected, the method sets the `is_connected` attribute of the UI to True.

        Parameters:
            ui (QtWidgets.QWidget): The UI to connect the slots for.
            widgets (Iterable[QtWidgets.QWidget], optional): A specific set of widgets to connect the slots for.
                If not provided, all widgets of the UI are used.

        Raises:
            ValueError: If the UI is not an instance of QtWidgets.QWidget.

        Side effect:
            If successful, sets `<ui>.is_connected` to True, indicating that the slots for the UI's widgets are connected.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: {type(ui)}")

        if widgets is None:
            if ui.is_connected:
                return
            widgets = ui.widgets

        for widget in ptk.make_iterable(widgets):
            self.connect_slot(widget)

        ui.is_connected = True

    def _create_slot_wrapper(self, slot, widget):
        """Creates a wrapper function for a slot that includes the widget as a parameter if possible.

        Parameters:
            slot (callable): The slot function to be wrapped.
            widget (QWidget): The widget that the slot is connected to.

        Returns:
            callable: The slot wrapper function.
        """
        sig = inspect.signature(slot)
        param_names = [
            name
            for name, param in sig.parameters.items()
            if param.kind
            in [inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY]
        ]

        def wrapper(*args, **kwargs):
            # Check if the only parameter is 'widget'
            if len(param_names) == 1 and "widget" in param_names:
                # Call the slot with only the 'widget' argument
                return slot(widget)

            # Otherwise, prepare arguments normally
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in param_names}
            if "widget" in param_names and "widget" not in kwargs:
                filtered_kwargs["widget"] = widget

            self.slot_history(add=slot)
            return slot(*args, **filtered_kwargs)

        return wrapper

    def connect_slot(self, widget, slot=None):
        """Connects a slot to its associated signals for a widget."""
        self.logger.debug(
            f"Connecting slot for '{widget.ui.name}.{widget.name or widget}'"
        )
        if not slot:
            slot = self.get_slot_from_widget(widget)
            if not slot:
                return

        signals = getattr(
            slot,
            "signals",
            ptk.make_iterable(self.default_signals.get(widget.derived_type)),
        )

        for signal_name in signals:
            if not isinstance(signal_name, str):
                raise TypeError(
                    f"Invalid signal for '{widget.ui.name}.{widget.name or widget}' {widget.derived_type}. "
                    f"Expected str, got '{type(signal_name)}'"
                )
            signal = getattr(widget, signal_name, None)
            if not signal:
                self.logger.warning(
                    f"No valid signal found for '{widget.ui.name}.{widget.name}' {widget.derived_type}. "
                    f"Expected str, got '{type(signal_name)}'"
                )
                continue
            slot_wrapper = self._create_slot_wrapper(slot, widget)
            signal.connect(slot_wrapper)

            # Store the connection directly in the slot instance's connections attribute
            widget.ui.connected_slots.setdefault(widget, {})[signal_name] = slot_wrapper

            self.logger.debug(
                f"Slot connected for '{widget.ui.name}.{widget.name or widget}' {widget.derived_type}"
            )

    def disconnect_slots(self, ui, widgets=None, disconnect_all=False):
        """Disconnects the signals from their respective slots for the widgets of the given UI.

        Only disconnects the slots that are connected via `connect_slots` unless disconnect_all is True.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            widgets (Iterable[QWidget], optional): A specific set of widgets for which
                to disconnect slots. If not provided, all widgets from the UI are used.
            disconnect_all (bool, optional): If True, disconnects all slots regardless of their connection source.

        Raises:
            ValueError: If `ui` is not an instance of QWidget.

        Side effect:
            If successful, sets `<ui>.is_connected` to False indicating that
            the slots for the UI's widgets are disconnected.
        """
        self.logger.debug(f"Disconnecting slots for '{ui}'")

        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")

        if widgets is None:
            if not ui.is_connected:
                return
            widgets = ui.widgets

        for widget in ptk.make_iterable(widgets):
            slot = self.get_slot_from_widget(widget)
            if not slot:
                continue
            if disconnect_all:
                for signal_name, slot in self.connected_slots.get(widget, {}).items():
                    getattr(widget, signal_name).disconnect(slot)
            else:
                signals = getattr(slot, "signals", self.get_default_signals(widget))
                for signal_name in signals:
                    if signal_name in self.connected_slots.get(widget, {}):
                        getattr(widget, signal_name).disconnect(slot)

        ui.is_connected = False
        self.logger.debug(f"Slots disconnected for '{ui}'")

    def ui_history(self, index=None, allow_duplicates=False, inc=[], exc=[]):
        """Get the UI history.

        Parameters:
            index (int/slice, optional): Index or slice to return from the history. If not provided, returns the full list.
            allow_duplicates (bool): When returning a list, allows for duplicate names in the returned list.
            inc (str/list): The objects(s) to include.
                    supports using the '*' operator: startswith*, *endswith, *contains*
                    Will include all items that satisfy ANY of the given search terms.
                    meaning: '*.png' and '*Normal*' returns all strings ending in '.png' AND all
                    strings containing 'Normal'. NOT strings satisfying both terms.
            exc (str/list): The objects(s) to exclude. Similar to include.
                    exclude take precedence over include.
        Returns:
            (str/list): String of a single UI name or list of UI names based on the index or slice.

        Examples:
            ui_history() -> ['previousName4', 'previousName3', 'previousName2', 'previousName1', 'currentName']
            ui_history(-2) -> 'previousName1'
            ui_history(slice(-3, None)) -> ['previousName2', 'previousName1', 'currentName']
        """
        # Keep original list length restricted to last 200 elements
        self._ui_history = self._ui_history[-200:]
        # Remove any previous duplicates if they exist; keeping the last added element.
        if not allow_duplicates:
            self._ui_history = list(dict.fromkeys(self._ui_history[::-1]))[::-1]

        history = self._ui_history
        if inc or exc:
            history = ptk.filter_list(history, inc, exc, lambda u: u.name)

        if index is None:
            return history  # Return entire list if index is None
        else:
            try:
                return history[index]  # Return UI(s) based on the index
            except IndexError:
                return [] if isinstance(index, int) else None

    def slot_history(
        self, index=None, allow_duplicates=False, inc=[], exc=[], add=[], remove=[]
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

        Returns:
            (object/list): Slot method(s) based on index or slice.
        """
        # Keep original list length restricted to last 200 elements
        self._slot_history = self._slot_history[-200:]
        # Append new entries to the history
        if add:
            self._slot_history.extend(ptk.make_iterable(add))
        # Remove entries from the history
        if remove:
            remove_items = ptk.make_iterable(remove)
            for item in remove_items:
                try:
                    self._slot_history.remove(item)
                except ValueError:
                    self.logger.warning(f"Item '{item}' not found in slot history.")
        # Remove any previous duplicates if they exist; keeping the last added element.
        if not allow_duplicates:
            self._slot_history = list(dict.fromkeys(self._slot_history[::-1]))[::-1]

        history = self._slot_history
        if inc or exc:
            history = ptk.filter_list(
                history, inc, exc, lambda m: m.__name__, check_unmapped=True
            )

        if index is None:
            return history  # Return entire list if index is None
        else:
            try:
                return history[index]  # Return slot(s) based on the index
            except IndexError:
                return [] if isinstance(index, int) else None

    def get_ui_relatives(
        self, ui, upstream=False, exact=False, downstream=False, reverse=False
    ):
        """Get the UI relatives based on the hierarchy matching.

        Parameters:
            ui (str or obj): A dynamic UI object or its name for which relatives are to be found.
            upstream (bool, optional): If True, return the relatives that are upstream of the target UI. Defaults to False.
            exact (bool, optional): If True, return only the relatives that exactly match the target UI. Defaults to False.
            downstream (bool, optional): If True, return the relatives that are downstream of the target UI. Defaults to False.
            reverse (bool, optional): If True, search for relatives in the reverse direction. Defaults to False.

        Returns:
            list: A list of UI relative names (if ui is given as a string) or UI relative objects (if ui is given as an object) found based on the hierarchy matching.
        """
        ui_name = str(ui)
        ui_filenames = self.registry.ui_registry.get(
            "filename"
        )  # Get the filenames from the named tuple

        relatives = ptk.get_matching_hierarchy_items(
            ui_filenames,
            ui_name,
            upstream,
            exact,
            downstream,
            reverse,
            self.ui_name_delimiters,
        )
        # Return strings if ui given as a string, else UI objects.
        return relatives if ui_name == ui else self.get_ui(relatives)

    @staticmethod
    def get_base_name(widget) -> str:
        """Return the base name of a widget's object name.
        A base name is defined as a character sequence at the beginning of the widget's object name,
        ending at the last letter character.

        Parameters:
            widget (str/obj): The widget or its object name as a string.

        Returns:
            (str) The base name of the widget's object name as a string.

        Example:
            get_base_name('some_name') #returns: 'some_name'
            get_base_name('some_name_') #returns: 'some_name'
            get_base_name('some_name_03') #returns: 'some_name'
        """
        if not isinstance(widget, str):
            widget = widget.objectName()

        match = re.search(r"^\w*[a-zA-Z]", widget)
        return match.group() if match else widget

    def convert_to_legal_name(self, name: str) -> str:
        """Convert the given name to its legal representation, replacing any non-alphanumeric characters with underscores.

        Parameters:
            name (str): The name to convert.

        Returns:
            str: The legal name with non-alphanumeric characters replaced by underscores.
        """
        return re.sub(r"[^0-9a-zA-Z]", "_", name)

    def find_ui_filename(
        self, legal_name: str, unique_match: bool = False
    ) -> Union[str, List[str], None]:
        """Convert the given legal name to its original name(s) by searching the UI files.

        Parameters:
            legal_name (str): The legal name to convert back to the original name.
            unique_match (bool, optional): If True, return None when there is more than one possible match, otherwise, return all possible matches. Defaults to False.

        Returns:
            Union[str, List[str], None]: The original name(s) or None if unique_match is True and multiple matches are found.
        """
        # Replace underscores with a regex pattern to match any non-alphanumeric character
        pattern = re.sub(r"_", r"[^0-9a-zA-Z]", legal_name)

        # Retrieve all filenames from the ui_registry container
        filenames = self.registry.ui_registry.get("filename")
        # Find matches using the regex pattern
        matches = [name for name in filenames if re.fullmatch(pattern, name)]

        if unique_match:
            return None if len(matches) != 1 else matches[0]
        else:
            return matches

    @staticmethod
    def get_property_from_ui_file(file, prop):
        """Retrieves a specified property from a given UI or XML file.

        This method parses the given file, expecting it to be in either .ui or .xml format,
        and searches for all elements with the specified property. It then returns a list
        of these elements, where each element is represented as a list of tuples containing
        the tag and text of its sub-elements.

        Parameters:
            file (str): The path to the UI or XML file to be parsed. The file must have a .ui or .xml extension.
            prop (str): The property to search for within the file.

        Returns:
            list: A list of lists containing tuples with the tag and text of the sub-elements of each element found with the specified property.

        Raises:
            ValueError: If the file extension is not .ui or .xml, or if there is an error in parsing the file.

        Example:
            get_property_from_ui_file('example.ui', 'customwidget')
            # Output: [[('class', 'CustomWidget'), ('extends', 'QWidget')], ...]
        """
        if not (file.endswith(".ui") or file.endswith(".xml")):
            raise ValueError(
                f"Invalid file extension. Expected a .ui or .xml file, got: {file}"
            )

        tree = ElementTree()
        tree.parse(file)

        # Find all elements with the given property
        elements = tree.findall(".//{}".format(prop))

        result = []
        for elem in elements:
            prop_list = []
            for subelem in elem:
                prop_list.append((subelem.tag, subelem.text))
            result.append(prop_list)

        return result

    def _parse_tags(self, name: str) -> set:
        """Parse tags from the given name.

        Parameters:
            name (str): The name to parse tags from.

        Returns:
            set: A set of tags parsed from the name.
        """
        parts = name.split("#")
        return set(parts[1:]) if len(parts) > 1 else set()

    @staticmethod
    def _get_widgets_from_ui(
        ui: QtWidgets.QWidget, inc=[], exc="_*", object_names_only=False
    ) -> dict:
        """Find widgets in a qtpy UI object.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            inc (str)(tuple): Widget names to include.
            exc (str)(tuple): Widget names to exclude.
            object_names_only (bool): Only include widgets with object names.

        Returns:
            (dict) {<widget>:'objectName'}
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: {type(ui)}")

        dct = {
            c: c.objectName()
            for c in ui.findChildren(QtWidgets.QWidget, None)
            if (not object_names_only or c.objectName())
        }

        return ptk.filter_dict(dct, inc, exc, keys=True, values=True)

    @staticmethod
    def _get_widget_from_ui(
        ui: QtWidgets.QWidget, object_name: str
    ) -> QtWidgets.QWidget:
        """Find a widget in a qtpy UI object by its object name.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            object_name (str): The object name of the widget to find.

        Returns:
            (QWidget)(None) The widget object if it's found, or None if it's not found.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: {type(ui)}")

        return ui.findChild(QtWidgets.QWidget, object_name)

    def register_widget(self, widget):
        """Register any custom widgets using the module names.
        Registered widgets can be accessed as properties. ex. sb.registered_widgets.PushButton()

        Parameters:
            widget (obj): The widget to register.

        Returns:
            (obj): The registered widget
        """
        if widget.__name__ not in self.registered_widgets.keys():
            self.registerCustomWidget(widget)
            self.registered_widgets[widget.__name__] = widget
            return widget

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
        if ui is None or isinstance(ui, str):
            ui = self.get_ui(ui)

        return next((w for w in ui.widgets if w.name == name), None)

    def get_slot(self, slot_class, slot_name):
        """Get the slot from the slot class.

        Parameters:
            slot_class (object): Slot class instance.
            slot_name (str): Name of the slot (method or attribute).

        Returns:
            object or None: The slot, or None if not found.
        """
        try:
            return getattr(slot_class, slot_name)
        except AttributeError:
            self.logger.debug(
                f"Slot '{slot_name}' not found in '{slot_class.__class__.__name__}'"
            )
            return None
        except Exception:
            self.logger.error(
                f"Exception occurred while accessing slot '{slot_name}' in '{slot_class.__class__.__name__}':\n"
                f"{traceback.format_exc()}"
            )
            return None

    def get_slot_from_widget(self, widget):
        """Get the corresponding slot from a given widget.

        Parameters:
            widget (obj): The widget in which to get the slot of.

        Returns:
            (obj) The slot of the same name. ie. <b000 slot> from <b000 widget>.
        """
        self.logger.debug(f"Getting slot from widget: {widget}")

        slot_clss = self.get_slot_class(widget.ui)
        return self.get_slot(slot_clss, widget.name)

    def get_widget_from_slot(self, method):
        """Get the corresponding widget from a given method.

        Parameters:
            method (obj): The method in which to get the widget of.

        Returns:
            (obj) The widget of the same name. ie. <b000 widget> from <b000 method>.
        """
        if not method:
            return None

        return next(
            iter(
                w
                for u in self.loaded_ui.values()
                for w in u.widgets
                if w.get_slot() == method
            ),
            None,
        )

    def sync_widget_values(self, value, widget):
        """Synchronizes the value of a given widget with all its relative widgets.

        This method first retrieves all the relative UIs of the given widget, including both upstream and downstream relatives.
        It then iterates over these relatives, and for each relative, it tries to get a widget with the same name as the given widget.

        If such a widget exists in the relative UI, the method checks the type of the widget and uses the appropriate method to set the widget's value.
        The appropriate method is determined based on the signal that the widget emits when its state changes.

        The signal names and corresponding methods are stored in the `default_signals` dictionary, which maps widget types to signal names.

        Parameters:
            value (any): The value to set the widget's relatives to.
            widget (QWidget): The widget to synchronize the value for.
        """
        relatives = self.get_ui_relatives(widget.ui, upstream=True, downstream=True)
        for relative in relatives:
            # self.logger.debug("name:      ", widget.name)
            relative_widget = self.get_widget(widget.name, relative)
            # self.logger.debug("get widget:", relative_widget)
            if relative_widget is not None and relative_widget is not widget:
                signal_name = self.default_signals.get(widget.derived_type)
                if signal_name:
                    self._apply_state_to_widget(relative_widget, signal_name, value)
                    self.store_widget_state(relative_widget, signal_name, value)

        # Store the state of the original widget regardless of whether it has relatives
        original_signal_name = self.default_signals.get(widget.derived_type)
        if original_signal_name:
            self.store_widget_state(widget, original_signal_name, value)

    def store_widget_state(
        self, widget: QtWidgets.QWidget, signal_name: str, value: any
    ) -> None:
        """Stores the current state of a widget in the application settings.
        Serializes complex objects into JSON for storable formats.

        Parameters:
            widget (QWidget): The widget whose state is to be stored.
            signal_name (str): The name of the signal indicating a state change in the widget.
            value (any): The current state of the widget, to be serialized if complex.
        """
        # Serialize complex objects into a storable format (e.g., JSON string)
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value)
        elif not isinstance(value, (int, float, str, bool)):
            # Log or handle non-serializable objects here
            return

        widget.ui.settings.setValue(f"{widget.objectName()}/{signal_name}", value)

    def restore_widget_state(self, widget: QtWidgets.QWidget) -> None:
        """Restores the state of a given widget using QSettings.
        Deserializes stored JSON strings back into Python objects.

        Parameters:
            widget (QWidget): The widget whose state is to be restored.
        """
        widget_name = widget.objectName()
        if not widget_name:
            return  # Exit if widget does not have a name

        signal_name = self.default_signals.get(widget.derived_type)
        if signal_name:
            try:
                value = widget.ui.settings.value(f"{widget_name}/{signal_name}")
                if value is not None:
                    # Attempt to parse the value assuming it might be JSON
                    try:
                        parsed_value = json.loads(value)
                    except (TypeError, json.JSONDecodeError):
                        parsed_value = value  # Use the original value if parsing fails
                    self._apply_state_to_widget(widget, signal_name, parsed_value)
            except EOFError:
                return

    def clear_widget_state(self, widget):
        """Clears the stored state of a given widget from the application settings.

        Parameters:
            widget (QWidget): The widget whose state is to be cleared.
        """
        signal_name = self.default_signals.get(widget.derived_type)
        if signal_name:
            key = f"{widget.name}/{signal_name}"
            widget.ui.settings.remove(key)

    def _apply_state_to_widget(self, widget, signal_name, value):
        """Applies the stored state to a widget based on the given signal name.

        Parameters:
            widget (QWidget): The widget whose state is to be updated.
            signal_name (str): The name of the signal that triggered the state change.
            value (Union[str, float, int]): The value to set the widget's state to.
        """
        # Define a dictionary that maps signal names to lambda functions
        action_map = {
            "textChanged": lambda w, v: (
                w.setText(str(v)) if hasattr(w, "setText") else None
            ),
            "valueChanged": lambda w, v: (
                self._set_numeric_value(w, v) if hasattr(w, "setValue") else None
            ),
            "currentIndexChanged": lambda w, v: (
                self._set_index_value(w, v) if hasattr(w, "setCurrentIndex") else None
            ),
            "toggled": lambda w, v: (
                self._set_boolean_value(w, v) if hasattr(w, "setChecked") else None
            ),
            "stateChanged": lambda w, v: (
                self._set_check_state(w, v) if hasattr(w, "setCheckState") else None
            ),
        }

        # Call the appropriate lambda function if the signal_name exists in action_map
        action = action_map.get(signal_name)
        if action:
            action(widget, value)

    def _set_numeric_value(self, widget, value):
        try:
            widget.setValue(float(value))
        except (ValueError, TypeError):
            pass  # Optionally log this error

    def _set_index_value(self, widget, value):
        try:
            widget.setCurrentIndex(int(value))
        except (ValueError, TypeError):
            pass  # Optionally log this error

    def _set_boolean_value(self, widget, value):
        widget.setChecked(value in ["true", "True", 1, "1"])

    def _set_check_state(self, widget, value):
        try:
            widget.setCheckState(QtCore.Qt.CheckState(int(value)))
        except (ValueError, TypeError):
            pass  # Optionally log this error

    def set_widget_attrs(self, ui, widget_names, **kwargs):
        """Set multiple properties, for multiple widgets, on multiple UI's at once.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            widget_names (str): String of object_names. - object_names separated by ',' ie. 'b000-12,b022'
            *kwargs = keyword: - the property to modify. ex. setText, setValue, setEnabled, setDisabled, setVisible, setHidden
                        value: - intended value.
        Example:
            set_widget_attrs(<ui>, 'chk003-6', setText='Un-Crease')
        """
        # Get_widgets_from_str returns a widget list from a string of object_names.
        widgets = self.get_widgets_by_string_pattern(ui, widget_names)
        # Set the property state for each widget in the list.
        for attr, value in kwargs.items():
            for w in widgets:
                try:
                    setattr(w, attr, value)
                except AttributeError:
                    pass

    def is_widget(self, obj):
        """Returns True if the given obj is a valid widget.

        Parameters:
            obj (obj): An object to query.

        Returns:
            (bool)
        """
        try:
            return issubclass(obj, QtWidgets.QWidget)
        except TypeError:
            return issubclass(obj.__class__, QtWidgets.QWidget)

    @staticmethod
    def get_parent_widgets(widget, object_names=False):
        """Get the all parent widgets of the given widget.

        Parameters:
            widget (QWidget): The widget to get parents of.
            object_names (bool): Return as object_names.

        Returns:
            (list) Object(s) or objectName(s)
        """
        parentWidgets = []
        w = widget
        while w:
            parentWidgets.append(w)
            w = w.parentWidget()
        if object_names:
            return [w.objectName() for w in parentWidgets]
        return parentWidgets

    @classmethod
    def get_top_level_parent(cls, widget, index=-1):
        """Get the parent widget at the top of the hierarchy for the given widget.

        Parameters:
            widget (QWidget): The widget to get top level parent of.
            index (int): Last index is top level.

        Returns:
            (QWidget)
        """
        return cls.get_parent_widgets()[index]

    @staticmethod
    def get_all_windows(name=None):
        """Get Qt windows.

        Parameters:
            name (str): Return only windows having the given object name.

        Returns:
            (list) windows.
        """
        return [
            w
            for w in QtWidgets.QApplication.allWindows()
            if (name is None) or (w.objectName() == name)
        ]

    @staticmethod
    def get_all_widgets(name=None):
        """Get Qt widgets.

        Parameters:
            name (str): Return only widgets having the given object name.

        Returns:
            (list) widgets.
        """
        return [
            w
            for w in QtWidgets.QApplication.allWidgets()
            if (name is None) or (w.objectName() == name)
        ]

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
        w = QtWidgets.QApplication.widgetAt(pos)
        if top_widget_only:
            return w

        widgets = []
        while w:
            widgets.append(w)

            w.setAttribute(
                QtCore.Qt.WA_TransparentForMouseEvents
            )  # make widget invisible to further enquiries.
            w = QtWidgets.QApplication.widgetAt(pos)

        for w in widgets:  # restore attribute.
            w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)

        return widgets

    @staticmethod
    def get_cursor_offset_from_center(widget):
        """Get the relative position of the cursor with respect to the center of a given widget.

        Parameters:
            widget (QWidget): The widget to query.

        Returns:
            (obj) QPoint
        """
        return QtGui.QCursor.pos() - widget.rect().center()

    @staticmethod
    def center_widget(
        widget, pos=None, offset_x=0, offset_y=0, padding_x=None, padding_y=None
    ):
        """Adjust the widget's size to fit contents and center it at the given point, on the screen, at cursor, or at the widget's current position if no point is given.

        Parameters:
            widget (QWidget): The widget to move and resize.
            pos (QPoint/str, optional): A point to move to, or 'screen' to center on screen, or 'cursor' to center at cursor position. Defaults to None.
            offset_x (int, optional): The desired offset percentage on the x axis. Defaults to 0.
            offset_y (int, optional): The desired offset percentage on the y axis. Defaults to 0.
            padding_x (int, optional): Additional width from the widget's minimum size. If not specified, the widget's current width is used.
            padding_y (int, optional): Additional height from the widget's minimum size. If not specified, the widget's current height is used.
        """
        # Resize the widget if padding values are provided
        if padding_x is not None or padding_y is not None:
            p1 = widget.rect().center()
            x = (
                widget.minimumSizeHint().width()
                if padding_x is not None
                else widget.width()
            )
            y = (
                widget.minimumSizeHint().height()
                if padding_y is not None
                else widget.height()
            )
            widget.resize(
                x + (padding_x if padding_x is not None else 0),
                y + (padding_y if padding_y is not None else 0),
            )
            p2 = widget.rect().center()
            diff = p1 - p2
            widget.move(widget.pos() + diff)

        # Determine the center point based on the provided pos value
        if pos == "screen":
            rect = QtWidgets.QApplication.desktop().availableGeometry(widget)
            centerPoint = rect.center()
        elif pos == "cursor":
            centerPoint = QtGui.QCursor.pos()
        elif pos is None:
            centerPoint = widget.frameGeometry().center()
        elif isinstance(pos, QtCore.QPoint):
            centerPoint = pos
        else:
            raise ValueError(
                "Invalid value for pos. It should be either 'screen', 'cursor', a QPoint instance or None."
            )

        # Compute the offset
        offset = QtCore.QPoint(
            widget.width() * offset_x / 100, widget.height() * offset_y / 100
        )
        # Center the widget considering the offset
        widget.move(centerPoint - widget.rect().center() + offset)

    @staticmethod
    def unpack_names(name_string):
        """Unpacks a comma-separated string of names and returns a list of individual names.

        Parameters:
            name_string (str): A string consisting of widget names separated by commas.
                    Names may include ranges with hyphens, e.g., 'chk021-23, 25, tb001'.
        Returns:
            list: A list of unpacked names, e.g., ['chk021', 'chk022', 'chk023', 'chk025', 'tb001'].
        """

        def expand_name_range(prefix, start, stop):
            """Generate a list of names with a given prefix and a range of numbers."""
            return [prefix + str(num).zfill(3) for num in range(start, stop + 1)]

        def extract_parts(name):
            """Extract alphabetic and numeric parts from a given name using regular expressions."""
            return re.findall(r"([a-zA-Z]+)|(\d+)", name)

        names = re.split(r",\s*", name_string)
        unpacked_names = []
        last_prefix = None

        for name in names:
            parts = extract_parts(name)
            digits = [int(p[1]) for p in parts if p[1]]

            if len(digits) == 1:
                if not parts[0][0]:
                    unpacked_names.append(last_prefix + str(digits[0]).zfill(3))
                else:
                    last_prefix = parts[0][0]
                    unpacked_names.append(name)
            elif len(digits) == 2:
                prefix = parts[0][0]
                start, stop = digits
                unpacked_names.extend(expand_name_range(prefix, start, stop))
                last_prefix = prefix

        return unpacked_names

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
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")

        widgets = []
        for n in Switchboard.unpack_names(name_string):
            try:
                w = getattr(ui, n)
                widgets.append(w)
            except AttributeError:
                self.logger.info(traceback.format_exc())

        return widgets

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
        if not isinstance(clss, object):
            raise ValueError(f"Invalid datatype: Expected class, got {type(clss)}")

        result = []
        for method_name in Switchboard.unpack_names(name_string):
            method = getattr(clss, method_name, None)
            if method is not None:
                result.append(method)

        return result

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
        button_groups = []

        def button_toggled(w: QtWidgets.QAbstractButton, grp: QtWidgets.QButtonGroup):
            """Handle button toggle event."""
            w.blockSignals(True)  # Block signals to prevent recursive calls

            if not allow_multiple and w.isChecked():
                # Uncheck all other buttons in the group
                for btn in grp.buttons():
                    if btn != w:
                        btn.setChecked(False)
            elif not allow_deselect and not any(
                btn.isChecked() for btn in grp.buttons()
            ):
                # Re-check the button if deselect is not allowed
                w.setChecked(True)

            w.blockSignals(False)  # Unblock signals after state change

        for buttons in args:
            # Get widgets by the string pattern
            widgets = self.get_widgets_by_string_pattern(ui, buttons)
            if not widgets:
                continue

            # Validation checks
            widget_type = type(widgets[0])
            if allow_multiple and issubclass(widget_type, QtWidgets.QRadioButton):
                raise ValueError("Allow_multiple is not applicable to QRadioButton")
            if any(type(w) != widget_type for w in widgets):
                raise TypeError("All widgets in a group must be of the same type")

            # Create button group
            grp = QtWidgets.QButtonGroup()
            grp.setExclusive(False)  # Set to False to manually handle exclusivity

            # Add each widget to the button group
            for w in widgets:
                w.button_group = grp
                grp.addButton(w)
                # Temporarily block signals to prevent the toggled slot from being triggered
                w.blockSignals(True)
                w.setChecked(False)
                w.blockSignals(False)
                w.toggled.connect(lambda checked, w=w, grp=grp: button_toggled(w, grp))

            button_groups.append(grp)

        return ptk.format_return(button_groups)

    def toggle_multi(self, ui, **kwargs):
        """Set multiple boolean properties, for multiple widgets at once.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            *kwargs: The property to modify. ex. setChecked, setUnChecked, setEnabled, setDisabled, setVisible, setHidden
                        value: string of object_names - object_names separated by ',' ie. 'b000-12,b022'
        Example:
            toggle_multi(<ui>, setDisabled='b000', setUnChecked='chk009-12', setVisible='b015,b017')
        """
        for k in kwargs:  # property_ ie. setUnChecked
            # get_widgets_by_string_pattern returns a widget list from a string of object_names.
            widgets = self.get_widgets_by_string_pattern(ui, kwargs[k])

            state = True
            # strips 'Un' and sets the state from True to False. ie. 'setUnChecked' becomes 'setChecked' (False)
            if "Un" in k:
                k = k.replace("Un", "")
                state = False

            # set the property state for each widget in the list.
            for w in widgets:
                getattr(w, k)(state)

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
        if isinstance(widgets, str):
            widgets = self.get_widgets_by_string_pattern(ui, widgets)
        else:
            widgets = ptk.make_iterable(widgets)

        # Ensure the other arguments are iterable
        signals = ptk.make_iterable(signals)
        slots = ptk.make_iterable(slots)

        self.logger.debug(
            f"[connect_multi] Connecting: {widgets} to {signals} -> {slots}"
        )

        for widget in widgets:
            if not widget:
                self.logger.warning(f"Skipped: Invalid widget '{widget}'")
                continue

            for signal_name in signals:
                try:
                    signal = getattr(widget, signal_name, None)
                    if not signal:
                        self.logger.warning(
                            f"Skipped: Widget '{widget}' has no signal '{signal_name}'"
                        )
                        continue

                    for slot in slots:
                        if not callable(slot):
                            self.logger.warning(
                                f"Skipped: Slot '{slot}' is not callable"
                            )
                            continue

                        signal.connect(slot)

                except Exception as e:
                    self.logger.error(
                        f"Failed to connect signal '{signal_name}' on '{widget}' to '{slot}': {e}"
                    )

    def set_axis_for_checkboxes(self, checkboxes, axis, ui=None):
        """Set the given checkbox's check states to reflect the specified axis.

        Parameters:
            checkboxes (str/list): 3 or 4 (or six with explicit negative values) checkboxes.
            axis (str): Axis to set. Valid text: '-','X','Y','Z','-X','-Y','-Z' ('-' indicates a negative axis in a four checkbox setup)

        Example:
            set_axis_for_checkboxes('chk000-3', '-X') # Optional `ui` arg for the checkboxes.
        """
        if isinstance(checkboxes, (str)):
            if ui is None:
                ui = self.current_ui
            checkboxes = self.get_widgets_by_string_pattern(ui, checkboxes)

        prefix = "-" if "-" in axis else ""  # separate the prefix and axis
        coord = axis.strip("-")

        for chk in checkboxes:
            if any(
                [
                    chk.text() == prefix,
                    chk.text() == coord,
                    chk.text() == prefix + coord,
                ]
            ):
                chk.setChecked(True)

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
        if isinstance(checkboxes, str):
            if ui is None:
                ui = self.current_ui
            checkboxes = self.get_widgets_by_string_pattern(ui, checkboxes)

        prefix = ""
        axis = ""
        for chk in checkboxes:
            if chk.isChecked():
                text = chk.text()
                if re.search("[^a-zA-Z]", text):  # Check for any non-alphabet character
                    prefix = "-"  # Assuming negative prefix if any non-alphabet character is present
                else:
                    axis = text.lower()

        # Mapping for axis strings to integers
        axis_map = {"x": 0, "-x": 1, "y": 2, "-y": 3, "z": 4, "-z": 5}

        # Construct the axis string with potential prefix
        axis_string = prefix + axis

        # Convert to integer index if needed
        if return_type == "int":
            return axis_map.get(axis_string, None)  # Return the corresponding integer

        # Return as string by default
        return axis_string

    @staticmethod
    def invert_on_modifier(value):
        """Invert a numerical or boolean value if the alt key is pressed.

        Parameters:
            value (int, float, bool) = The value to invert.

        Returns:
            (int, float, bool)
        """
        modifiers = QtWidgets.QApplication.instance().keyboardModifiers()
        if modifiers not in (
            QtCore.Qt.AltModifier,
            QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier,
        ):
            return value

        if type(value) in (int, float):
            result = abs(value) if value < 0 else -value
        elif type(value) == bool:
            result = True if value else False

        return result

    def message_box(self, string, *buttons, location="topMiddle", timeout=3):
        """Spawns a message box with the given text and optionally sets buttons.

        Parameters:
            string (str): The message to display.
            *buttons (str): Variable length argument list of buttons to display.
            location (str/QPoint, optional): The location to move the messagebox to. Default is 'topMiddle'.
            timeout (int, optional): Time in seconds before the messagebox auto closes. Default is 3.

        Returns:
            The result of the message box interaction if buttons are provided, None otherwise.
        """
        if not hasattr(self, "_messageBox"):
            self._messageBox = self.registered_widgets.MessageBox(self.parent())

        self._messageBox.location = location
        self._messageBox.timeout = timeout

        self._messageBox.setStandardButtons(*buttons)

        # Log text without HTML tags
        self.logger.info(f"# {re.sub('<.*?>', '', string)}")

        self._messageBox.setText(string)

        if buttons:  # If buttons are provided, use exec_() and return the result
            return self._messageBox.exec_()
        else:  # If no buttons, use show() and do not wait for a result
            self._messageBox.show()
            return None

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
        options = QtWidgets.QFileDialog.Options()
        if allow_multiple:
            options |= QtWidgets.QFileDialog.ReadOnly

        file_types_string = f"{filter_description} ({' '.join(file_types)})"

        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            None, title, start_dir, file_types_string, options=options
        )

        return files if allow_multiple else files[0] if files else None

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
        options = QtWidgets.QFileDialog.Options()
        directory_path = QtWidgets.QFileDialog.getExistingDirectory(
            None, title, start_dir, options=options
        )

        return directory_path

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
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError("The 'ui' parameter must be a QWidget or a subclass.")

        # Create and post the key press event
        press_event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, modifiers)
        QtWidgets.QApplication.postEvent(ui, press_event)

        # Optionally create and post the key release event
        if release:
            release_event = QtGui.QKeyEvent(QtCore.QEvent.KeyRelease, key, modifiers)
            QtWidgets.QApplication.postEvent(ui, release_event)

    def defer(self, method: callable, *args, delay_ms: int = 300, **kwargs) -> None:
        """Defer execution of any callable with arguments after a delay.

        Parameters:
            method (callable): The method to be called after the delay.
            *args: Positional arguments for the method.
            delay_ms (int, optional): Delay in milliseconds before execution. Default is 300.
            **kwargs: Keyword arguments for the method.

        Raises:
            ValueError: If method is not callable.
            TypeError: If delay_ms is not an integer.
        """
        if not callable(method):
            raise ValueError(f"defer: Expected a callable, got {type(method).__name__}")

        if not isinstance(delay_ms, int):
            raise TypeError(
                f"defer: delay_ms must be an integer, got {type(delay_ms).__name__}"
            )

        def safe_call():
            """Executes the method safely and logs any exceptions."""
            try:
                method(*args, **kwargs)
            except Exception as e:
                self.logger.error(
                    f"defer: Exception in deferred call to {method.__name__}: {e}"
                )
                self.logger.debug(traceback.format_exc())

        # Schedule the deferred execution
        QtCore.QTimer.singleShot(delay_ms, safe_call)

    def gc_protect(self, obj=None, clear=False):
        """Protect the given object from garbage collection.

        Parameters:
            obj (obj/list): The obj(s) to add to the protected list.
            clear (bool): Clear the set before adding any given object(s).

        Returns:
            (list) protected objects.
        """
        if clear:
            self._gc_protect.clear()

        for o in ptk.make_iterable(obj):
            self._gc_protect.add(o)

        return self._gc_protect


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    from uitk import example

    sb = Switchboard(ui_source=example, slot_source=example.example_slots)
    ui = sb.example
    # ui.set_attributes(WA_TranslucentBackground=True)
    # ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)
    # ui.set_style(theme="dark", style_class="translucentBgWithBorder")

    # print(repr(ui))
    # print(sb.QWidget)
    # ui.show(pos="screen", app_exec=True)

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
