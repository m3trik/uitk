# !/usr/bin/python
# coding=utf-8
import os
import re
import sys
import inspect
import logging
import traceback
import importlib
from functools import wraps
from typing import List, Union
from xml.etree.ElementTree import ElementTree
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtUiTools import QUiLoader
import pythontk as ptk


def signals(*signals):
    """Decorator to specify the signals that a slot should be connected to.

    Parameters:
        *signals (str): One or more signal names as strings.

    Returns:
        decorator: A decorator that can be applied to a slot method.

    Usage:
        @signals('clicked')
        def on_button_click():
            print("Button clicked")
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        if len(signals) == 0:
            raise ValueError("At least one signal must be specified")

        for signal in signals:
            if not isinstance(signal, str):
                raise TypeError(f"Signal must be a string, not {type(signal)}")

        wrapper.signals = signals
        return wrapper

    return decorator


from collections import namedtuple
from typing import List


class FileManager:
    def __init__(self, caller_dir=None):
        self.stack = inspect.stack()
        self.caller_dir = caller_dir or self.get_dir_from_stack(2)
        self.module_dir = self.get_dir_from_stack(0)
        print("caller_dir:", self.caller_dir)
        print("module_dir:", self.module_dir)

        # Initialize the internal dictionaries
        self._files = {}
        self._locations = {}

    def get_dir_from_stack(self, index) -> str:
        """Retrieves the directory path from the stack frame at the given index."""
        # If desired index is out of range, use the highest available one
        if index >= len(self.stack):
            index = len(self.stack) - 1

        frame = self.stack[index][0]
        filename = frame.f_code.co_filename
        return os.path.abspath(os.path.dirname(filename))

    def create_tuple(
        self,
        descriptor,
        objects=None,
        structure="filename|filepath",
        inc_files=[],
        exc_files=[],
        inc_dirs=[],
        exc_dirs=[],
        base_dir=None,
    ):
        objs = ptk.make_iterable(objects)

        # If base_dir is not provided, use self.caller_dir
        if base_dir is None:
            base_dir = self.caller_dir

        all_files = []
        for obj in objs:
            file_info = self._handle_single_obj(
                obj, structure, inc_files, exc_files, inc_dirs, exc_dirs, base_dir
            )
            all_files.extend(file_info)

        # Define the named tuple class based on the structure
        TupleClass = namedtuple(descriptor.capitalize(), structure.split("|"))

        # Convert the files into named tuples
        self._files[descriptor] = [TupleClass(*info) for info in all_files]

        # Convert objs to their corresponding file or directory paths
        paths = [self._get_path_from_obj(obj, base_dir) for obj in objs]
        self._locations[descriptor] = [os.path.abspath(path) for path in paths]

        return self._files[descriptor]

    def _get_path_from_obj(self, obj, base_dir=None):
        """Converts obj to a string representing its file or directory path."""

        if isinstance(base_dir, int):
            base_dir = self.get_dir_from_stack(base_dir)
        else:
            base_dir = base_dir or self.caller_dir

        if inspect.ismodule(obj) or inspect.isclass(obj):
            return inspect.getfile(obj)
        elif isinstance(obj, str):
            if not os.path.isabs(obj):
                return os.path.join(base_dir, obj)
            return obj
        else:
            raise ValueError(
                f"Invalid datatype for object: Expected str, module, or class, got {type(obj)}"
            )

    def _handle_single_obj(
        self,
        obj,
        structure="filename|filepath",
        inc_files=[],
        exc_files=[],
        inc_dirs=[],
        exc_dirs=[],
        base_dir=None,
    ):
        """Handles a single object and returns its corresponding files info."""

        if isinstance(base_dir, int):
            base_dir = self.get_dir_from_stack(base_dir)
        else:
            base_dir = base_dir or self.caller_dir

        class_name = None
        if inspect.ismodule(obj):
            dir_path = inspect.getfile(obj)
        elif inspect.isclass(obj):
            dir_path = inspect.getfile(obj)
            class_name = obj.__name__
        elif isinstance(obj, str):
            if not os.path.isabs(obj):
                obj = os.path.join(base_dir, obj)
            dir_path = os.path.abspath(obj)
        else:
            raise ValueError(
                f"Invalid datatype for object: Expected str, module, or class, got {type(obj)}"
            )

        if os.path.isdir(dir_path):
            # Get all files recursively from the directories and their subdirectories
            all_files = ptk.get_dir_contents(
                dir_path,
                returned_type="filepath",
                inc_files=inc_files,
                exc_files=exc_files,
                inc_dirs=inc_dirs,
                exc_dirs=exc_dirs,
            )
        else:
            all_files = [dir_path]

        returned_type = structure
        if any(item in structure for item in ["classname", "class", "module"]):
            file_info = ptk.get_classes_from_path(
                dir_path,
                returned_type,
                inc=class_name,
                top_level_only=False,
                force_tuples=True,
            )
        else:
            file_info = ptk.get_file_info(all_files, returned_type, force_tuples=True)

        return file_info

    def get_dict(self, descriptor):
        """Returns the dictionary of the given descriptor."""
        return self._files.get(descriptor, {})

    def get_dicts(self):
        """Returns all dictionaries."""
        return self._files


class Switchboard(QUiLoader):
    """Load dynamic UI, assign convenience properties, and handle slot connections.

    The following attributes are added to each slots class instance:
        switchboard (method): This method returns the Switchboard instance that the instance belongs to.
            This allows easy access to the Switchboard's methods and properties from within the slots class.
        signals (method): The `@signals` decorator can be used to specify which signals a slot should be connected to.
            If a slot method is not decorated with `@signals`, it will use the default signals specified in the `default_signals` dictionary.

            For example, to specify that a slot should be connected to the 'clicked' and 'released' signals, you could write:
                @signals('clicked', 'released')
                def on_button_click():
                    print("Button clicked")

    Parameters:
        parent (obj): A QtObject derived class.
        ui_location (str/obj): Set the directory of the dynamic UI, or give the dynamic UI objects.
        widgets_location (str/obj): Set the directory of any custom widgets, or give the widget objects.
        slots_location (str/obj): Set the directory of where the slot classes will be imported, or give the slot class itself.
        ui_name_delimiters (tuple, optional): A tuple of two delimiter strings, where the first delimiter is used to split the hierarchy and the second delimiter is used to split hierarchy levels. Defaults to (".", "#").
        preload_ui (bool): Load all UI immediately. Otherwise UI will be loaded as required.
        set_legal_name_no_tags_attr (bool): If True, sets the legal name without tags attribute for the object (provinding there are no conflicts). Defaults to False.
        log_level (int): Determines the level of logging messages to print. Defaults to logging.WARNING. Accepts standard Python logging module levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.

    Properties:
        sb: The instance of this class holding all properties.
        sb.ui: Returns the current UI.
        sb.<uiFileName>: Accesses the UI loaded from uiFileName.
        sb.<customWidgetClassName>: Accesses the custom widget with the specified class name.
        sb.<slotsClassName>: Accesses the slots class of the specified class name.

    Methods:
        load_ui(uiPath): Load the UI file located at uiPath.
        load_all_ui(): Load all UI files in the UI directory.
        registerWidget(widget): Register the specified widget.
        connect_slots(slotClass, ui=None): Connect the slots in the specified slot class to the specified UI.

    Attributes:
        default_signals: A dictionary of the default signals to be connected per widget type.
        module_dir: The directory of this module.
        default_dir: The default directory is the calling module's directory. If any of the given file paths are not
                                        a full path, they will be treated as relative to the currently set path.
    Example:
        1. Create a subclass of Switchboard to load your project ui and connect slots for the UI events.
            class MyProject():
                ...

            class MyProject_slots(MyProject):
                def __init__(self):
                    super().__init__()
                    self.sb = self.switchboard() #slot classes are given the `switchboard` function when they are initialized.
                    print (self.sb.ui) #access the current ui. if a single ui is loaded that will automatically be assigned as current, else you must set a ui as current using: self.sb.ui = self.sb.get_ui(<ui_name>)

            class MyProject_sb(Switchboard):
                def __init__(self, parent=None, **kwargs):
                    super().__init__(parent)
                    self.ui_location = 'path/to/your/dynamic ui file(s)' #specify the location of your ui.
                    self.slots_location = MyProject_slots #give the slots directory or the class itself.

        2. Instantiate the subclass and show the UI.
            sb = MyProject_sb()
            sb.ui.show(app_exec=True)
    """

    # return the existing QApplication object, or create a new one if none exists.
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
        ui_location="ui",
        widgets_location="widgets",
        slots_location="slots",
        preload_ui=False,
        ui_name_delimiters=[".", "#"],
        set_legal_name_no_tags_attr=False,
        log_level=logging.WARNING,
    ):
        super().__init__(parent)
        """
        """
        self._init_logger(log_level)

        self.ui_location = ui_location
        self.widgets_location = widgets_location
        self.slots_location = slots_location

        self.file_manager = FileManager()
        self.ui_files = self.file_manager.create_tuple(
            "ui_files",
            self.ui_location,
            inc_files="*.ui",
        )
        self.widget_files = self.file_manager.create_tuple(
            "widget_files",
            self.widgets_location,
            structure="classname",
            inc_files="*.py",
            base_dir=0,
        )
        self.slots_files = self.file_manager.create_tuple(
            "slots_files",
            self.slots_location,
            structure="classname|filepath",
            inc_files="*.py",
        )

        print("\nui_files:", self.ui_files)
        print("\nwidget_files:", self.widget_files)
        print("\nslots_files:", self.slots_files)

        self.ui_name_delimiters = ui_name_delimiters
        self.set_legal_name_no_tags_attr = set_legal_name_no_tags_attr

        self._loaded_ui = {}  # All loaded ui.
        self._ui_history = []  # Ordered ui history.
        self._registered_widgets = {}  # All registered custom widgets.
        self._slot_history = []  # Previously called slots.
        self._slot_instances = {}  # Slot classes that have been instantiated.
        self._connected_slots = {}  # Currently connected slots.
        self._synced_pairs = set()  # Hashed values representing synced widgets.
        self._gc_protect = set()  # Objects protected from garbage collection.

        if preload_ui:
            self.load_all_ui()

    def _init_logger(self, log_level):
        """Initializes logger."""
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        self.logger.addHandler(handler)

    def __getattr__(self, attr_name):
        """Lazy load UI and custom widgets.
        If an unknown attribute matches the name of a UI in the current UI directory; load and return it.
        Else, if an unknown attribute matches the name of a custom widget in the widgets directory; register and return it.
        If no match is found raise an attribute error.

        Returns:
            (obj) UI or widget.
        """
        # Check if the attribute matches a UI file
        if ptk.has_attribute(self, "ui_files"):
            actual_ui_name = self.convert_from_legal_name(attr_name, unique_match=True)
            found_ui = self.ui_files.get(actual_ui_name, None)
            if found_ui:
                ui = self.load_ui(found_ui)
                return ui

        # Check if the attribute matches a widget file
        if ptk.has_attribute(self, "widget_files"):
            widget_file_path = self.widget_files.get(attr_name, None)
            if widget_file_path:
                widget_class = self.import_class_from_module(
                    widget_file_path, attr_name
                )
                if widget_class:
                    widget = self.register_widget(widget_class)
                    return widget

        raise AttributeError(
            f"{self.__class__.__name__} has no attribute `{attr_name}`"
        )

    @staticmethod
    def get_module_dir_from_frame(frame) -> str:
        """Retrieves the directory path of the given calling frame.

        This method uses the inspect module to find the frame of the calling module
        and extracts its directory path.

        Parameters:
            frame (frame): The frame object of the module.

        Returns:
            str: The absolute directory path of the module.
        """
        calling_file = frame.f_code.co_filename
        default_dir = os.path.abspath(os.path.dirname(calling_file))
        return default_dir

    @staticmethod
    def import_class_from_module(module_path, class_name):
        """Import a class from a given module.

        Parameters:
            module_path (str): The path to the module.
            class_name (str): The name of the class to import.

        Returns:
            The requested class, or None if the class cannot be found.
        """
        spec = importlib.util.spec_from_file_location(
            os.path.basename(module_path), module_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        return getattr(module, class_name, None)

    @property
    def ui(self) -> QtWidgets.QWidget:
        """Get the current ui.

        Returns:
            (obj) ui
        """
        return self.get_current_ui()

    @ui.setter
    def ui(self, ui) -> None:
        """Register the uiName in history as current and set slot connections.

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")

        self.set_current_ui(ui)

    @property
    def prev_ui(self) -> QtWidgets.QWidget:
        """Get the previous ui from history.

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

    def convert_from_legal_name(
        self, legal_name: str, unique_match: bool = False
    ) -> Union[str, List[str], None]:
        """Convert the given legal name to its original name(s) by searching the `ui_files` dictionary.

        Parameters:
            legal_name (str): The legal name to convert back to the original name.
            unique_match (bool, optional): If True, return None when there is more than one possible match, otherwise, return all possible matches. Defaults to False.

        Returns:
            Union[str, List[str], None]: The original name(s) or None if unique_match is True and multiple matches are found.
        """
        # Replace underscores with a regex pattern to match any non-alphanumeric character
        pattern = re.sub(r"_", r"[^0-9a-zA-Z]", legal_name)
        matches = [name for name in self.ui_files.keys() if re.fullmatch(pattern, name)]

        if unique_match:
            return None if len(matches) != 1 else matches[0]
        else:
            return matches

    @staticmethod
    def get_property_from_ui_file(file, prop):
        """ """
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

    @staticmethod
    def _get_widgets_from_ui(
        ui: QtWidgets.QWidget, inc=[], exc="_*", object_names_only=False
    ) -> dict:
        """Find widgets in a PySide2 UI object.

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
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
        """Find a widget in a PySide2 UI object by its object name.

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
            object_name (str): The object name of the widget to find.

        Returns:
            (QWidget)(None) The widget object if it's found, or None if it's not found.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: {type(ui)}")

        return ui.findChild(QtWidgets.QWidget, object_name)

    def register_widget(self, widget):
        """Register any custom widgets using the module names.
        Registered widgets can be accessed as properties. ex. sb.PushButton()
        """
        if widget.__name__ not in self._registered_widgets:
            self.registerCustomWidget(widget)
            self._registered_widgets[widget.__name__] = widget
            setattr(self, widget.__name__, widget)
            return widget

    def set_slots(self, ui, clss):
        """This method sets the slot class instance for a loaded dynamic UI object. It takes a UI and
        a class and sets the instance as the slots for the given UI. Finally, it
        initializes the widgets and returns the slot class instance.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            clss (str/object): A class or path to a class that will be set as the slots for the given UI.

        Returns:
            object: A class instance.

        Attributes:
            switchboard (method): A method in the slot class that returns the Switchboard instance.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")

        if isinstance(clss, str):
            module_path = clss  # Save the path for future reference
            clss = self._import_slots(clss)
        else:  # Derive path from class object
            module_path = ptk.get_object_path(clss, inc_filename=True)

        if module_path not in self._slot_instances:
            # Set slot class attributes
            clss.switchboard = lambda *args: self
            # Create the class instance and save it
            self._slot_instances[module_path] = clss()

        ui._slots = self._slot_instances[module_path]
        # Set switchboard attributes
        setattr(self, ui._slots.__class__.__name__, ui._slots)

        return ui._slots

    def get_slots(self, ui):
        """This function tries to get a class instance of the slots module from a dynamic UI object.
        If it doesn't exist, it tries to import it from a specified location or from the parent menu.
        If it's found, it's set and returned, otherwise None is returned.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.

        Returns:
            object: A class instance.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")

        if hasattr(ui, "_slots"):
            return ui._slots

        if inspect.isclass(self.slots_location):
            clss = self.slots_location
            return self.set_slots(ui, clss)

        try:
            found_path = self._find_slots_class_module(ui)
        except ValueError:
            self.logger.info(traceback.format_exc())
            found_path = None

        if not found_path:
            for relative_name in self.get_ui_relatives(ui, upstream=True, reverse=True):
                relative_ui = self.get_ui(relative_name)
                if relative_ui:
                    try:
                        found_path = self._find_slots_class_module(relative_ui)
                        break
                    except ValueError:
                        self.logger.info(traceback.format_exc())
        # print("get_slots:", ui.name, found_path)
        if found_path:
            slots_instance = self.set_slots(ui, found_path)
            return slots_instance
        else:
            ui._slots = None
            return None

    def _find_slots_class_module(self, ui):
        """Find the path of the slot class associated with the given UI.
        ie. get the path for <Polygons> class using UI name 'polygons'
        searches possible vaid names in the slots_directory in the following order:
            <legal_name>_<suffix>
            <legal_name_notags>_<suffix>
            <legal_name>
            <legal_name_notags>

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.

        Returns:
            str: The path to the slot class file.

        Raises:
            ValueError: If more than one matching slot class is found for the given UI.
        """
        slots_dir = ptk.format_path(self.slots_location, "dir")
        suffix = slots_dir if isinstance(slots_dir, str) else ""

        legal_name_camel = ptk.set_case(ui.legal_name, case="camel")
        legal_name_notags_camel = ptk.set_case(ui.legal_name_no_tags, case="camel")

        try_names = [
            f"{legal_name_camel}_{suffix}",
            f"{legal_name_notags_camel}_{suffix}",
            legal_name_camel,
            legal_name_notags_camel,
        ]

        found_paths = set()
        for name in try_names:
            found_path = self.slots_files.get(name, None)
            if found_path:
                found_paths.add(found_path)

        if len(found_paths) == 1:
            return found_paths.pop()
        elif not found_paths:
            return None
        else:
            raise ValueError(
                f"Multiple matching slot classes found for '{ui.name}'.\n\t{found_paths}"
            )

    def _import_slots(self, found_path):
        """Import the slot class from the given path.

        Parameters:
            found_path (str): The path to the slot class file.

        Returns:
            object: A class object.
        """
        name = os.path.splitext(os.path.basename(found_path))[0]
        spec = importlib.util.spec_from_file_location("", found_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)

        cls_name = ptk.set_case(name, case="pascal")
        clss = getattr(mod, cls_name, None)

        if clss is None:
            clss = inspect.getmembers(mod, inspect.isclass)[0][1]
            if clss:
                self.logger.warning(
                    f"Slot class '{cls_name}' not found. Using '{clss}' instead."
                )
            else:
                self.logger.warning(f"Slot class '{cls_name}' not found.")

        return clss

    def load_all_ui(self) -> list:
        """Extends the 'load_ui' method to load all ui from a given path.

        Returns:
            (list) QWidget(s).
        """
        return [self.load_ui(f) for f in self.ui_files.values()]

    def load_ui(self, file) -> QtWidgets.QWidget:
        """Loads a ui from the given path to the ui file.

        Parameters:
            file (str): The full file path to the ui file.

        Returns:
            (obj) QWidget.
        """
        # Get any custom widgets from the ui file.
        lst = self.get_property_from_ui_file(file, "customwidget")
        for sublist in lst:
            try:  # Get 'MyCustomWidget' from ('class', 'MyCustomWidget')
                class_name = sublist[0][1]
            except IndexError:
                continue

            if (
                class_name in self.widget_files
                and class_name not in self._registered_widgets
            ):
                widget_file_path = self.widget_files[class_name]
                widget_class = self.import_class_from_module(
                    widget_file_path, class_name
                )
                self.register_widget(widget_class)

        ui = self.MainWindow(
            self,
            file,
            set_legal_name_no_tags_attr=self.set_legal_name_no_tags_attr,
            log_level=self.logger.getEffectiveLevel(),
        )

        self._loaded_ui[ui.name] = ui
        return ui

    def get_ui(self, ui=None) -> QtWidgets.QWidget:
        """Get a dynamic ui using its string name, or if no argument is given, return the current ui.

        Parameters:
            ui (str/list/QWidget): The ui or name(s) of the ui.

        Raises:
            ValueError: If the given ui is of an incorrect datatype.

        Returns:
            (obj/list): If a list is given, a list is returned. Otherwise, a QWidget object is returned.
        """
        if isinstance(ui, (list, set, tuple)):
            return [self.get_ui(u) for u in ui]

        elif isinstance(ui, str):
            return getattr(self, ui, None)

        if isinstance(ui, QtWidgets.QWidget):
            return ui

        elif not ui:
            return self.ui

        else:
            raise ValueError(
                f"Invalid datatype for ui: Expected QWidget, got {type(ui)}"
            )

    def get_current_ui(self) -> QtWidgets.QWidget:
        """Get the current ui.

        Returns:
            (obj): A previously loaded dynamic ui object.
        """
        try:
            return self._current_ui

        except AttributeError:
            # if only one ui is loaded set that ui as current.
            if len(self._loaded_ui) == 1:
                ui = next(iter(self._loaded_ui.values()))
                self.set_current_ui(ui)
                return ui

            # if the ui location is set to a single ui, then load and set that ui as current.
            elif self.ui_location.endswith(".ui"):
                ui = self.load_ui(self.ui_location)
                self.set_current_ui(ui)
                return ui

            return None

    def set_current_ui(self, ui) -> None:
        """Register the specified dynamic UI as the current one in the application's history.
        Once registered, the UI widget can be accessed through the `ui` property while it remains the current UI.
        If the given UI is already the current UI, the method simply returns without making any changes.

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")

        current_ui = getattr(self, "_current_ui", None)
        if current_ui == ui:
            return

        self._current_ui = ui
        self._ui_history.append(ui)
        # self.logger.info(f"_ui_history: {u.name for u in self._ui_history}")  # debug

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
                    print(f"Item {item} not found in history.")
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

        relatives = ptk.get_matching_hierarchy_items(
            self.ui_files.keys(),
            ui_name,
            upstream,
            exact,
            downstream,
            reverse,
            self.ui_name_delimiters,
        )
        # return strings if ui given as a string, else ui objects.
        return relatives if ui_name == ui else self.get_ui(relatives)

    def get_widget(self, name, ui=None):
        """Case insensitive. Get the widget object/s from the given ui and name.

        Parameters:
            name (str): The object name of the widget. ie. 'b000'
            ui (str/obj): ui, or name of ui. ie. 'polygons'. If no nothing is given, the current ui will be used.
                                            A ui object can be passed into this parameter, which will be used to get it's corresponding name.
        Returns:
            (obj) if name:  widget object with the given name from the current ui.
                      if ui and name: widget object with the given name from the given ui name.
            (list) if ui: all widgets for the given ui.
        """
        if ui is None or isinstance(ui, str):
            ui = self.get_ui(ui)

        return next((w for w in ui.widgets if w.name == name), None)

    def get_widget_from_method(self, method):
        """Get the corresponding widget from a given method.

        Parameters:
            method (obj): The method in which to get the widget of.

        Returns:
            (obj) widget. ie. <b000 widget> from <b000 method>.
        """
        if not method:
            return None

        return next(
            iter(
                w
                for u in self._loaded_ui.values()
                for w in u.widgets
                if w.get_slot() == method
            ),
            None,
        )

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
            If successful, sets `ui.is_connected` to True, indicating that the slots for the UI's widgets are connected.
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

        The wrapper function is designed to handle different widget-specific signal values as keyword arguments.
        The signal values are passed to the slot function as keyword arguments based on the type of the widget.

        If the slot function does not accept the widget or signal-specific keyword argument, it is called with positional arguments as a fallback.

        Parameters:
            slot (callable): The slot function to be wrapped. This is typically a method of a class.
            widget (QWidget): The widget that the slot is connected to. This widget is passed to the slot function as a keyword argument,
                and its signal value is also passed as a keyword argument.

        Returns:
            callable: The slot wrapper function. This function can be connected to a widget signal and is responsible for calling the original slot function
                with the appropriate arguments.
        """

        def slot_wrapper(*args, **kwargs):
            parameters = inspect.signature(slot).parameters
            has_kwargs = any(p.kind == p.VAR_KEYWORD for p in parameters.values())
            has_widget = "widget" in parameters

            if has_kwargs or has_widget:
                kwargs["widget"] = widget

            if len(args) > 0:  # if there are values, try to call the slot with them
                if "widget" in parameters or has_kwargs:
                    slot(*args, **kwargs)
                else:
                    slot(
                        *args
                    )  # this should fall back to positional arguments if keyword arguments are not accepted
            else:  # no extra arguments, so call the slot with no arguments
                if "widget" in parameters or has_kwargs:
                    slot(**kwargs)
                else:
                    slot()

            self.slot_history(add=slot)  # update slot history after calling the slot

        return slot_wrapper

    def connect_slot(self, widget, slot=None):
        """Connects a slot to its associated signals for a widget.

        The signals to be connected are defined in the slot's 'signals' attribute.
        If the slot doesn't have a 'signals' attribute, the widget's default signals are used instead.
        If a signal name isn't a string or no valid signal is found for the widget, a warning is logged.
        If the slot is not provided, it will attempt to use the default slot associated with the widget.
        If no slot is found, a ValueError is raised.

        Parameters:
            widget (QWidget): The widget to connect the slot to.
            slot (object, optional): The slot to be connected. If not provided, the default slot associated with the widget will be used.

        Raises:
            ValueError: If no slot is found for the widget.
        """
        if not slot:
            slot = widget.get_slot()
            if not slot:
                self.logger.info(
                    f"No slot found for widget {widget.ui.name}.{widget.name}"
                )
                return

        signals = getattr(
            slot,
            "signals",
            ptk.make_iterable(self.default_signals.get(widget.derived_type)),
        )

        for signal_name in signals:
            if not isinstance(signal_name, str):
                raise TypeError(
                    f"Signal name must be a string, not '{type(signal_name)}'"
                )
            signal = getattr(widget, signal_name, None)
            if signal:
                slot_wrapper = self._create_slot_wrapper(slot, widget)
                signal.connect(slot_wrapper)
                if widget not in self._connected_slots:
                    self._connected_slots[widget] = {}
                self._connected_slots[widget][signal_name] = slot_wrapper
            else:
                self.logger.warning(
                    f"No valid signal '{signal_name}' found for {widget.ui.name}.{widget.name}"
                )

    def disconnect_slots(self, ui, widgets=None, disconnect_all=False):
        """Disconnects the signals from their respective slots for the widgets of the given ui.

        Only disconnects the slots that are connected via `connect_slots` unless disconnect_all is True.

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
            widgets (Iterable[QWidget], optional): A specific set of widgets for which
                to disconnect slots. If not provided, all widgets from the ui are used.
            disconnect_all (bool, optional): If True, disconnects all slots regardless of their connection source.

        Raises:
            ValueError: If ui is not an instance of QWidget.

        Side effect:
            If successful, sets `ui.is_connected` to False indicating that
            the slots for the UI's widgets are disconnected.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")
        if widgets is None:
            if not ui.is_connected:
                return
            widgets = ui.widgets
        for widget in ptk.make_iterable(widgets):
            slot = widget.get_slot()
            if not slot:
                continue
            if disconnect_all:
                for signal_name, slot in self._connected_slots.get(widget, {}).items():
                    getattr(widget, signal_name).disconnect(slot)
            else:
                signals = getattr(slot, "signals", self.get_default_signals(widget))
                for signal_name in signals:
                    if signal_name in self._connected_slots.get(widget, {}):
                        getattr(widget, signal_name).disconnect(slot)
        ui.is_connected = False

    def sync_widget_values(self, value, widget):
        """Synchronizes the value of a given widget with all its relative widgets.

        This method first retrieves all the relative UIs of the given widget, including both upstream and downstream relatives.
        It then iterates over these relatives, and for each relative, it tries to get a widget with the same name as the given widget.

        If such a widget exists in the relative UI, the method checks the type of the widget and uses the appropriate method to set the widget's value.
        The appropriate method is determined based on the signal that the widget emits when its state changes.

        The signal names and corresponding methods are stored in the `default_signals` dictionary, which maps widget types to signal names.

        Parameters:
            value (any): The value to set the widget and its relatives to.
            widget (QWidget): The widget to synchronize the value for.
        """
        # Get the relatives of the widget's UI
        relatives = self.get_ui_relatives(
            widget.ui, exact=True, upstream=True, downstream=True
        )
        for relative in relatives:
            # Get the widget of the same name
            relative_widget = getattr(relative, widget.name, None)
            if relative_widget is not None:
                # Check the type of the widget and use the appropriate method to set the value
                signal_name = self.default_signals.get(widget.derived_type)
                if signal_name:
                    # Check if the widget has the signal
                    if relative_widget is not widget:
                        try:
                            if signal_name == "textChanged":
                                relative_widget.setText(value)
                            elif signal_name == "valueChanged":
                                relative_widget.setValue(value)
                            elif signal_name == "currentIndexChanged":
                                relative_widget.setCurrentIndex(value)
                            elif signal_name in {"toggled", "stateChanged"}:
                                relative_widget.setChecked(value)
                        except AttributeError:
                            pass
                    # Save the widget state
                    self.store_widget_state(relative_widget, signal_name, value)

    def store_widget_state(self, widget, signal_name, value):
        """Stores the current state of a widget in the application settings.
        This method uses the QSettings class to store the current state of a widget. The state is stored under a key that is a combination of the widget's object name and the signal name.

        Parameters:
            widget (QWidget): The widget whose state is to be stored.
            signal_name (str): The name of the signal that indicates a state change in the widget.
            value (any): The current state of the widget.
        """
        widget.ui.settings.setValue(f"{widget.name}/{signal_name}", value)

    def restore_widget_state(self, widget):
        """Restores the state of a given widget.
        This method uses the QSettings class to restore the state of a widget. The state is retrieved using a key that is a combination of the widget's object name and the signal name. The method then sets the widget's state based on the retrieved value.

        Parameters:
            widget (QWidget): The widget whose state is to be restored.
        """
        signal_name = self.default_signals.get(widget.derived_type)
        if signal_name:
            value = widget.ui.settings.value(f"{widget.name}/{signal_name}")
            if value is not None:
                # QSettings stores everything as strings, so some conversion might be neccesary
                if signal_name == "textChanged":
                    widget.setText(value)
                elif signal_name == "valueChanged":
                    if isinstance(value, str):
                        value = float(value)
                    widget.setValue(value)
                elif signal_name == "currentIndexChanged":
                    widget.setCurrentIndex(int(value))
                elif signal_name in {"toggled", "stateChanged"}:
                    if isinstance(value, str):
                        value = bool(value.capitalize())
                    widget.setChecked(int(value))

    def set_widget_attrs(self, ui, widget_names, **kwargs):
        """Set multiple properties, for multiple widgets, on multiple ui's at once.

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
            widget_names (str): String of object_names. - object_names separated by ',' ie. 'b000-12,b022'
            *kwargs = keyword: - the property to modify. ex. setText, setValue, setEnabled, setDisabled, setVisible, setHidden
                        value: - intended value.
        Example:
            set_widget_attrs(ui, 'chk003-6', setText='Un-Crease')
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
            ui (QWidget): A previously loaded dynamic ui object.
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

    def create_button_groups(self, ui, *args):
        """Create button groups for a set of widgets.
        The created groups later be accessed through the grouped buttons using the 'button_group' attribute.

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
            args: The widgets to group. Object_names separated by ',' ie. 'b000-12,b022'
        Example:
            grp_a, grp_b = create_button_groups(ui, 'b000-2', 'b003-4')
            grp_a = b000.button_group # access group using the 'button_group' attribute.
            grp_b = b003.button_group
        """
        button_groups = []

        for buttons in args:
            # Create button group
            grp = QtWidgets.QButtonGroup()
            # get_widgets_by_string_pattern returns a widget list from a string of object_names.
            widgets = self.get_widgets_by_string_pattern(ui, buttons)

            # add each widget to the button group
            for w in widgets:
                w.button_group = grp
                grp.addButton(w)

            # Add the group to the list
            button_groups.append(grp)

        # Return a single group if only one was created, otherwise return the tuple of groups
        return ptk.format_return(button_groups)

    def toggle_multi(self, ui, **kwargs):
        """Set multiple boolean properties, for multiple widgets at once.

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
            *kwargs: The property to modify. ex. setChecked, setUnChecked, setEnabled, setDisabled, setVisible, setHidden
                        value: string of object_names - object_names separated by ',' ie. 'b000-12,b022'
        Example:
            toggle_multi(ui, setDisabled='b000', setUnChecked='chk009-12', setVisible='b015,b017')
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
            ui (QWidget): A previously loaded dynamic ui object.
            widgets (str/list): ie. 'chk000-2' or [tb.menu.chk000, tb.menu.chk001]
            signals (str/list): ie. 'toggled' or ['toggled']
            slots (obj/list): ie. self.cmb002 or [self.cmb002]

        Example:
            connect_multi(tb.menu, 'chk000-2', 'toggled', self.cmb002)
        """
        if isinstance(widgets, (str)):
            widgets = self.get_widgets_by_string_pattern(ui, widgets)

        # if the variables are not of a list type; convert them.
        widgets = ptk.make_iterable(widgets)
        signals = ptk.make_iterable(signals)
        slots = ptk.make_iterable(slots)

        for widget in widgets:
            for signal_name in signals:
                signal = getattr(widget, signal_name)
                for slot in slots:
                    try:
                        signal.connect(slot)
                    except TypeError as e:
                        self.logger.error(
                            f"Failed to connect signal {signal_name} to slot {slot}: {e}"
                        )
                        raise

    def set_axis_for_checkboxes(self, checkboxes, axis, ui=None):
        """Set the given checkbox's check states to reflect the specified axis.

        Parameters:
            checkboxes (str/list): 3 or 4 (or six with explicit negative values) checkboxes.
            axis (str): Axis to set. Valid text: '-','X','Y','Z','-X','-Y','-Z' ('-' indicates a negative axis in a four checkbox setup)

        Example:
            set_axis_for_checkboxes('chk000-3', '-X') #optional ui arg for the checkboxes
        """
        if isinstance(checkboxes, (str)):
            if ui is None:
                ui = self.get_current_ui()
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

    def get_axis_from_checkboxes(self, checkboxes, ui=None):
        """Get the intended axis value as a string by reading the multiple checkbox's check states.

        Parameters:
            checkboxes (str/list): 3 or 4 (or six with explicit negative values) checkboxes. Valid text: '-','X','Y','Z','-X','-Y','-Z' ('-' indicates a negative axis in a four checkbox setup)

        Returns:
            (str) axis value. ie. '-X'

        Example:
            get_axis_from_checkboxes('chk000-3')
        """
        if isinstance(checkboxes, (str)):
            if ui is None:
                ui = self.get_current_ui()
            checkboxes = self.get_widgets_by_string_pattern(ui, checkboxes)

        prefix = axis = ""
        for chk in checkboxes:
            if chk.isChecked():
                if chk.text() == "-":
                    prefix = "-"
                else:
                    axis = chk.text()
        # self.logger.info(f"prefix: {prefix} axis: {axis}") #debug
        return prefix + axis  # ie. '-X'

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

    def message_box(self, string, message_type="", location="topMiddle", timeout=3):
        """Spawns a message box with the given text.
        Supports HTML formatting.
        Prints a formatted version of the given string to console, stripped of html tags, to the console.

        Parameters:
            message_type (str/optional): The message context type. ex. 'Error', 'Warning', 'Info', 'Result'
            location (str/QPoint/optional) = move the messagebox to the specified location. default is: 'topMiddle'
            timeout (int/optional): time in seconds before the messagebox auto closes. default is: 3
        """
        if message_type:
            string = f"{message_type.capitalize()}: {string}"

        try:
            self._messageBox.location = location
        except AttributeError:
            self._messageBox = self.MessageBox(self.parent())
            self._messageBox.location = location
        self._messageBox.timeout = timeout

        # strip everything between '<' and '>' (html tags)
        self.logger.info(f"# {re.sub('<.*?>', '', string)}")

        self._messageBox.setText(string)
        self._messageBox.show()  # Use show() instead of exec_()

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

    class MyProject:
        ...

    class MyProjectSlots(MyProject):
        def __init__(self):
            self.sb = self.switchboard()

        @signals("released")
        def MyButtonsObjectName(self):
            self.sb.message_box("Button Pressed")

    sb = Switchboard(
        ui_location="example", widgets_location="widgets", slots_location=MyProjectSlots
    )
    ui = sb.example
    ui.set_style(theme="dark")

    print(repr(ui))
    ui.show(app_exec=True)

logging.info(__name__)  # module name
# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
