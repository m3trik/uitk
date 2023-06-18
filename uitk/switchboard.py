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
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtUiTools import QUiLoader
from pythontk import (
    File,
    Str,
    Iter,
    format_return,
)


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
        widgets (str/obj): Set the directory of any custom widgets, or give the widget objects.
        slots (str/obj): Set the directory of where the slot classes will be imported, or give the slot class itself.
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
        ui_location="",
        widgets_location="",
        slots_location="",
        preload_ui=False,
        ui_name_delimiters=[".", "#"],
        set_legal_name_no_tags_attr=False,
        log_level=logging.WARNING,
    ):
        super().__init__(parent)
        """
        """
        self._init_logger(log_level)

        calling_frame = inspect.currentframe().f_back
        # Get calling module directory.
        self.default_dir = self.get_module_dir_from_frame(calling_frame)
        self.module_dir = File.get_filepath(__file__)  # the directory of this module.

        # initialize the files dicts before the location dicts (dependancies).
        self.ui_files = {}  # UI paths.
        self.widget_files = {}  # widget paths.
        self.slots_files = {}  # slot class paths.

        # use the relative filepath of this module if None is given.
        self.ui_location = ui_location or f"{self.module_dir}/ui"
        self.widgets_location = widgets_location or f"{self.module_dir}/widgets"
        self.slots_location = slots_location or f"{self.module_dir}/slots"

        self.ui_name_delimiters = ui_name_delimiters
        self.set_legal_name_no_tags_attr = set_legal_name_no_tags_attr

        self._loaded_ui = {}  # all loaded ui.
        self._ui_history = []  # ordered ui history.
        self._registered_widgets = {}  # all registered custom widgets.
        self._slot_history = []  # previously called slots.
        self._slot_instances = {}  # slot classes that have been instantiated.
        self._connected_slots = {}  # currently connected slots.
        self._synced_pairs = set()  # hashed values representing synced widgets.
        self._gc_protect = set()  # objects protected from garbage collection.

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
        actual_ui_name = self.convert_from_legal_name(attr_name, unique_match=True)
        found_ui = self.ui_files.get(actual_ui_name, None)
        if found_ui:
            ui = self.load_ui(found_ui)
            return ui

        # Check if the attribute matches a widget file
        widget_file_path = self.widget_files.get(attr_name, None)
        if widget_file_path:
            spec = importlib.util.spec_from_file_location(attr_name, widget_file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            widget_class = getattr(module, attr_name)

            if widget_class:
                widget = self.register_widgets(widget_class)
                return widget

        raise AttributeError(
            f"{self.__class__.__name__} has no attribute `{attr_name}`"
        )

    @property
    def ui_location(self) -> str:
        """Get the directory where the UI files are located.

        Returns:
            (str) directory path.
        """
        try:
            return self._ui_location

        except AttributeError:
            self._ui_location = self.default_dir
            return self._ui_location

    @ui_location.setter
    def ui_location(self, x) -> None:
        """Set the directory where the UI files are located.

        Parameters:
            x (str/module): The directory path or the module where the UI files are located.
                If the given dir is not a full path, it will be treated as relative to the default path.
                If a module is given, the path to that module will be used.
        Raises:
            ValueError: If the input is not of type 'str' or a module.
        """
        if isinstance(x, str):
            # if the given dir is not a full path, treat it as relative to the default path.
            isAbsPath = os.path.isabs(x)
            self._ui_location = x if isAbsPath else os.path.join(self.default_dir, x)
        elif inspect.ismodule(x):
            # use get_filepath to get the full path to the module.
            self._ui_location = File.get_filepath(x)
        else:
            raise ValueError(
                f"Invalid datatype for ui_location: {type(x)}, expected str or module."
            )
        self.setWorkingDirectory(self._ui_location)  # set QUiLoader working path.
        self.ui_files = self._construct_ui_files_dict()

    @property
    def widgets_location(self) -> str:
        """Get the directory where any custom widgets are stored.

        Returns:
            (str) directory path.
        """
        try:
            return self._widgets_location

        except AttributeError:
            self._widgets_location = self.default_dir
            return self._widgets_location

    @widgets_location.setter
    def widgets_location(self, x) -> None:
        """Set the directory where any custom widgets are stored or the list of custom widgets.

        Parameters:
            x (str/module/QWidget(s)): The directory path where any custom widgets are located or a list of custom widgets.
                If the given dir is not a full path, it will be treated as relative to the default path.
                If a module is given, the path to that module will be used.
        Raises:
            ValueError: If the input is not of type 'str' or QWidget(s).
        """
        if isinstance(x, str):
            # if the given dir is not a full path, treat it as relative to the default path.
            isAbsPath = os.path.isabs(x)
            self._widgets_location = (
                x if isAbsPath else os.path.join(self.default_dir, x)
            )
            self.addPluginPath(self._widgets_location)  # set QUiLoader working path.
        elif inspect.ismodule(x):
            # use get_filepath to get the full path to the module.
            self._widgets_location = File.get_filepath(x)
        elif isinstance(x, (list, tuple, set, QtWidgets.QWidget)):
            self._widgets_location = Iter.make_iterable(x)
        else:
            raise ValueError(
                f"Invalid datatype for widgets_location: {type(x)}, expected str, module, or QWidget(s)."
            )
        self.widget_files = self._construct_widget_files_dict()

    @property
    def slots_location(self) -> str:
        """Get the directory where the slot classes will be imported from.

        Returns:
            (str/obj) slots class directory path or slots class object.
        """
        try:
            return self._slots_location

        except AttributeError:
            self._slots_location = self.default_dir
            return self._slots_location

    @slots_location.setter
    def slots_location(self, x) -> None:
        """Set the directory where the slot classes will be imported from or a class object.

        Parameters:
            x (str/module/class): The directory path where the slot classes are located or a class object.
                If the given dir is a string and not a full path, it will be treated as relative to the default path.
                If a module is given, the path to that module will be used.
        """
        if isinstance(x, str):
            isAbsPath = os.path.isabs(x)
            self._slots_location = (
                x if isAbsPath else os.path.join(self.default_dir, x)
            )  # if the given dir is not a full path, treat it as relative to the default path.
        elif inspect.ismodule(x):
            # use get_filepath to get the full path to the module.
            self._slots_location = File.get_filepath(x)
        elif inspect.isclass(x):
            self._slots_location = x
        else:
            raise ValueError(
                f"Invalid datatype for slots_location: {type(x)}, expected str, module, or class."
            )

        self.slots_files = self._construct_slots_files_dict()

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
            raise ValueError(f"Invalid datatype: {type(ui)}, expected QWidget.")

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

    def _construct_ui_files_dict(self) -> dict:
        """Build and return a dictionary of UI paths, where the keys are the UI file names and the values
        are the corresponding file paths.

        Returns:
            dict: A dictionary of UI file paths with UI file names as keys.
        """
        if not isinstance(self.ui_location, str):
            raise ValueError(
                f"Invalid datatype for _construct_ui_files_dict: {type(self.ui_location)}, expected str."
            )

        ui_filepaths = File.get_dir_contents(
            self.ui_location, "filepaths", inc_files="*.ui"
        )
        ui_files = File.get_file_info(ui_filepaths, "filename|filepath")
        return dict(ui_files)

    @staticmethod
    def _get_classes_in_directory(dir_path) -> dict:
        """Given a directory, return a dictionary with all classes found in .py files in that directory and their respective filepaths.

        Parameters:
            dir_path (str): A directory path containing Python (.py) files.

        Returns:
            dict: A dictionary where keys are class names and values are the paths of the Python files they were found in.
        """
        classes_dict = {}

        for filename in os.listdir(dir_path):
            if filename.endswith(".py"):
                file_path = os.path.join(dir_path, filename)
                spec = importlib.util.spec_from_file_location("module", file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj):
                        classes_dict[name] = file_path

        return classes_dict

    def _construct_widget_files_dict(self) -> dict:
        """Build and return a dictionary of widget paths, where the keys are the widget file names and the
        values are the corresponding file paths or widget objects.

        Returns:
            dict: A dictionary of widget file paths or widget objects with widget file names as keys.
        """
        if isinstance(self.widgets_location, str):
            return self._get_classes_in_directory(self.widgets_location)

        elif isinstance(self.widgets_location, (list, tuple, set)):
            widget_dict = {}
            for widget in self.widgets_location:
                widget_name = widget.__name__
                widget_file = inspect.getfile(widget)
                widget_dict[widget_name] = widget_file
            return widget_dict
        else:
            raise ValueError(
                f"Invalid datatype for _construct_widget_files_dict: {type(self.widgets_location)}, expected str, list, tuple, or set."
            )

    def _construct_slots_files_dict(self) -> dict:
        """Build and return a dictionary of slot class paths, where the keys are the slot class file names
        and the values are the corresponding file paths. The method supports two types of input for
        slots_location: a directory path (str) or a class object.

        Returns:
            dict: A dictionary of slot class file paths with slot class file names as keys.
        """
        if isinstance(self.slots_location, str):
            slots_filepaths = File.get_dir_contents(
                self.slots_location, "filepaths", inc_files="*.py"
            )
            slots_files = File.get_file_info(slots_filepaths, "filename|filepath")
            return dict(slots_files)
        elif inspect.isclass(self.slots_location):
            module_info = inspect.getmodule(self.slots_location)
            if module_info is not None:
                module_path = module_info.__file__
                module_filename = os.path.basename(module_path)
                return {module_filename: module_path}
            else:
                return {}
        else:
            raise ValueError(
                f"Invalid datatype for _construct_slots_files_dict: {type(self.slots_location)}, expected str or class."
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
    def get_property_from_ui_file(file, prop) -> list:
        """Get sub-properties and their values from a given property name.
        Returns all items between the opening and closing statements of the given property.

        So 'customwidget' would return:
                [('class', 'MyCustomWidget'), ('extends', 'QPushButton'), ('header', 'widgets.pushbuttondraggable.h')]
        from:
            <customwidget>
                    <class>MyCustomWidget</class>
                    <extends>QPushButton</extends>
                    <header>widgets.pushbuttondraggable.h</header>
            </customwidget>

        Parameters:
            file (str): The full file path to the ui file.
            prop (str): the property text without its opening and closing brackets.
                                                    ie. 'customwidget' for the property <customwidget>.
        Returns:
            (list) list of tuples (typically one or two element).

        Example: get_property_from_ui_file(file, 'customwidget')
        """
        f = open(file)
        # self.logger.info(f.read()) #debug
        content = list(f.readlines())

        result = []
        actual_prop_text = ""
        for i, l in enumerate(content):
            if l.strip() == "<{}>".format(prop):
                actual_prop_text = l
                start = i + 1
            elif l == Str.insert(actual_prop_text, "/", "<"):
                end = i

                delimiters = ("</", "<", ">", "\n", " ")
                regex_pattern = "|".join(map(re.escape, delimiters))

                lst = [
                    tuple(dict.fromkeys([i for i in re.split(regex_pattern, s) if i]))
                    for s in content[start:end]
                ]  # use dict to remove any duplicates.
                result.append(lst)

        f.close()
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

        return Iter.filter_dict(dct, inc, exc, keys=True, values=True)

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

    def _get_widgets_from_dir(self, path) -> dict:
        """Get all widget class objects from a given directory, module filepath or module name.

        Parameters:
            path (str): A directory, fullpath to a widget module, or the name of a module residing in the 'widgets' directory.
                        For example: - 'path_to/uitk/widgets'
                                                 - 'path_to/uitk/widgets/comboBox.py'
                                                 - 'comboBox'
        Returns:
            (dict) keys are widget names and the values are the widget class objects.
            Returns an empty dictionary if no widgets were found or an error occurred.
        """
        mod_name = File.format_path(path, "name")
        if mod_name:
            wgt_name = Str.set_case(mod_name, "pascal")
            if wgt_name in self._registered_widgets:
                return {}

            if not File.is_valid(path):
                path = os.path.join(self.widgets_location, f"{mod_name}.py")

            try:
                spec = importlib.util.spec_from_file_location(mod_name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except ModuleNotFoundError:
                self.logger.info(traceback.format_exc())
                return {}

            cls_members = inspect.getmembers(
                mod,
                lambda m: inspect.isclass(m)
                and m.__module__ == mod.__name__
                and issubclass(m, QtWidgets.QWidget),
            )  # get only the widget classes that are defined in the module and not any imported classes.
            return dict(cls_members)

        else:  # get all widgets in the given path by recursively calling this fuction.
            try:
                files = os.listdir(path)
            except FileNotFoundError:
                self.logger.info(traceback.format_exc())
                return {}

            widgets = {}
            for file in files:
                if file.endswith(".py") and not file.startswith("_"):
                    mod_path = os.path.join(path, file)
                    widgets.update(self._get_widgets_from_dir(mod_path))
            return widgets

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
            raise ValueError(f"Invalid datatype: {type(ui)}, expected QWidget.")

        if isinstance(clss, str):
            clss_path = clss  # Save the path for future reference
        else:  # Derive path from class object
            module_path = inspect.getfile(clss)
            clss_path = os.path.abspath(module_path)

        if clss_path not in self._slot_instances:
            if isinstance(clss, str):
                clss = self._import_slots(clss)

            clss.switchboard = lambda *args: self

            self._slot_instances[clss_path] = clss()

        ui._slots = self._slot_instances[clss_path]
        setattr(self, ui._slots.__class__.__name__, ui._slots)

        # ui.init_widgets(ui.findChildren(QtWidgets.QWidget))
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
            raise ValueError(f"Invalid datatype: {type(ui)}")

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
        slots_dir = File.format_path(self.slots_location, "dir")
        suffix = slots_dir if isinstance(slots_dir, str) else ""

        legal_name_camel = Str.set_case(ui.legal_name, case="camel")
        legal_name_notags_camel = Str.set_case(ui.legal_name_no_tags, case="camel")

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
        """
        Import the slot class from the given path.

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

        cls_name = Str.set_case(name, case="pascal")
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

    def register_widgets(self, widgets):
        """Register any custom widgets using the module names.
        Registered widgets can be accessed as properties. ex. sb.PushButton()

        Parameters:
            widgets (str/obj/list): A filepath to a dir containing widgets or to the widget itself.
                                    ie. 'O:/Cloud/Code/_scripts/uitk/uitk/ui/widgets' or the widget(s) themselves.

        Returns:
            (obj/list) list if widgets given as a list.

        Example: register_widgets(<class 'widgets.menu.Menu'>) #register using widget class object.
        Example: register_widgets('O:/Cloud/Code/_scripts/uitk/uitk/ui/widgets/menu.py') #register using path to widget module.
        """
        result = []
        for w in Iter.make_iterable(widgets):  # assure widgets is a list.
            if isinstance(w, str):
                widgets_ = self._get_widgets_from_dir(w)
                for w_ in widgets_.values():
                    rw = self.register_widgets(w_)
                    result.append(rw)
                continue

            elif w.__name__ in self._registered_widgets:
                continue

            try:
                self.registerCustomWidget(w)
                self._registered_widgets[w.__name__] = w
                setattr(self, w.__name__, w)
                result.append(w)

            except Exception:
                self.logger.info(traceback.format_exc())

        # if 'widgets' is given as a list; return a list.
        return format_return(result, widgets)

    def load_all_ui(self) -> list:
        """Extends the 'load_ui' method to load all ui from a given path.

        Returns:
            (list) QWidget(s).
        """
        return [self.load_ui(f) for f in self.ui_files.values()]

    def load_ui(self, file, widgets=None) -> QtWidgets.QWidget:
        """Loads a ui from the given path to the ui file.

        Parameters:
            file (str): The full file path to the ui file.
            widgets (str/obj/list): A filepath to a dir containing widgets or the widget(s) itself.
                    ie. 'O:/Cloud/Code/_scripts/uitk/uitk/ui/widgets' or the widget(s) themselves.
        Returns:
            (obj) QWidget.
        """
        # name = File.format_path(file, "name")
        # path = File.format_path(file, "path")

        # register custom widgets
        if widgets is None and not isinstance(
            self.widgets_location, str
        ):  # widget objects defined in widgets.
            widgets = self.widgets_location
        if widgets is not None:  # widgets given explicitly or defined in widgets.
            self.register_widgets(widgets)
        else:  # search for and attempt to load any widget dependancies using the path defined in widgets.
            lst = self.get_property_from_ui_file(file, "customwidget")
            for sublist in lst:  # get any custom widgets from the ui file.
                try:
                    className = sublist[0][1]
                    # ie. 'MyCustomWidget' from ('class', 'MyCustomWidget')
                except IndexError:
                    continue

                mod_name = Str.set_case(className, "camel")
                fullpath = os.path.join(self.widgets_location, mod_name + ".py")
                self.register_widgets(fullpath)

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
            raise ValueError(f"Invalid datatype for ui: {type(ui)}")

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
            raise ValueError(f"Invalid datatype: {type(ui)}")

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
        # keep original list length restricted to last 200 elements
        self._slot_history = self._slot_history[-200:]
        # append new entries to the history
        if add:
            self._slot_history.extend(Iter.make_iterable(add))
        # remove entries from the history
        if remove:
            remove_items = Iter.make_iterable(remove)
            for item in remove_items:
                try:
                    self._slot_history.remove(item)
                except ValueError:
                    print(f"Item {item} not found in history.")
        # remove any previous duplicates if they exist; keeping the last added element.
        if not allow_duplicates:
            self._slot_history = list(dict.fromkeys(self._slot_history[::-1]))[::-1]

        filtered_objs = Iter.filter_list(self._slot_history, inc, exc)

        filtered = Iter.filter_mapped_values(
            filtered_objs, Iter.filter_list, lambda m: m.__name__, inc, exc
        )

        if index is None:
            return filtered  # return entire list if index is None
        else:
            try:
                return filtered[index]  # return slot(s) based on the index
            except IndexError:
                return [] if isinstance(index, int) else None

    def ui_history(
        self,
        index=None,
        allow_duplicates=False,
        inc=[],
        exc=[],
    ):
        """Get the UI history.

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

        Returns:
            (str/list): String of a single UI name or list of UI names based on the index or slice.

        Examples:
            ui_history() -> ['previousName4', 'previousName3', 'previousName2', 'previousName1', 'currentName']
            ui_history(-2) -> 'previousName1'
            ui_history(slice(-3, None)) -> ['previousName2', 'previousName1', 'currentName']
        """
        # keep original list length restricted to last 200 elements
        self._ui_history = self._ui_history[-200:]
        # remove any previous duplicates if they exist; keeping the last added element.
        if not allow_duplicates:
            self._ui_history = list(dict.fromkeys(self._ui_history[::-1]))[::-1]

        filtered = Iter.filter_mapped_values(
            self._ui_history, Iter.filter_list, lambda u: u.name, inc, exc
        )

        if index is None:
            return filtered  # return entire list if index is None
        else:
            try:
                return filtered[index]  # return UI(s) based on the index
            except IndexError:
                return [] if isinstance(index, int) else None

    def get_ui_relatives(
        self,
        ui,
        upstream=False,
        exact=False,
        downstream=False,
        reverse=False,
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

        relatives = Str.get_matching_hierarchy_items(
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
            widget (QtWidgets.QWidget): The widget to get the default signals for.

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

        for widget in Iter.make_iterable(widgets):
            self.connect_slot(widget)

        ui.is_connected = True

    def _create_slot_wrapper(self, slot, widget):
        """Creates a wrapper function for a slot that includes the widget as a parameter if possible.

        The wrapper function is designed to handle different widget-specific signal values as keyword arguments.
        The signal values are passed to the slot function as keyword arguments based on the type of the widget.

        If the slot function does not accept the widget or signal-specific keyword argument, it is called with positional arguments as a fallback.

        Parameters:
            slot (callable): The slot function to be wrapped. This is typically a method of a class.
            widget (QtWidgets.QWidget): The widget that the slot is connected to. This widget is passed to the slot function as a keyword argument,
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

            if len(args) > 0:  # if there is a value, try to call the slot with it
                if "widget" in parameters or has_kwargs:
                    slot(*args, **kwargs)
                else:
                    slot(args[0])
            else:  # no value, so call the slot with no arguments
                if "widget" in parameters or has_kwargs:
                    slot(**kwargs)
                else:
                    slot()

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
            Iter.make_iterable(self.default_signals.get(widget.derived_type)),
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
            raise ValueError(f"Invalid datatype: {type(ui)}")
        if widgets is None:
            if not ui.is_connected:
                return
            widgets = ui.widgets
        for widget in Iter.make_iterable(widgets):
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
            widget (QtWidgets.QWidget): The widget to synchronize the value for.
        """
        # Get the relatives of the widget's UI
        relatives = self.get_ui_relatives(widget.ui, upstream=True, downstream=True)

        for relative in relatives:
            # Get the widget of the same name
            relative_widget = getattr(relative, widget.name, None)
            if relative_widget is not None:
                # Check the type of the widget and use the appropriate method to set the value
                for widget_type, signal_name in self.default_signals.items():
                    if isinstance(relative_widget, widget_type):
                        # Check if the widget has the signal
                        if signal_name == "textChanged":
                            relative_widget.setText(value)
                        elif signal_name == "valueChanged":
                            relative_widget.setValue(value)
                        elif signal_name == "currentIndexChanged":
                            relative_widget.setCurrentIndex(value)
                        elif signal_name in {"toggled", "stateChanged"}:
                            relative_widget.setChecked(value)
                        break  # Stop the loop when the type is found

    def set_widget_attrs(self, *args, **kwargs):
        """Set multiple properties, for multiple widgets, on multiple ui's at once.https://www.tcm.com/watchtcm/titles/69005

        Parameters:
            *args = arg [0] (str) String of object_names. - object_names separated by ',' ie. 'b000-12,b022'
                            arg [1:] dynamic ui object/s.  If no ui's are given, then the parent and child uis will be used.
            *kwargs = keyword: - the property to modify. ex. setText, setValue, setEnabled, setDisabled, setVisible, setHidden
                            value: - intended value.
        Example:
            set_widget_attrs('chk003', <ui1>, <ui2>, setText='Un-Crease')
        """
        if not args[1:]:
            relatives = self.get_ui_relatives(
                self.get_current_ui(), upstream=False, exact=False, downstream=False
            )
            args = args + relatives

        for ui in args[1:]:
            # get_widgets_from_str returns a widget list from a string of object_names.
            widgets = self.get_widgets_from_str(ui, args[0])
            for property_, value in kwargs.items():
                [  # set the property state for each widget in the list.
                    getattr(w, property_)(value) for w in widgets
                ]

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
            widget (obj): QWidget
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
            widget (obj): QWidget
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
    def get_center(widget):
        """Get the center point of a given widget.

        Parameters:
            widget (obj): The widget to query.

        Returns:
            (obj) QPoint
        """
        return QtGui.QCursor.pos() - widget.rect().center()

    @staticmethod
    def resize_and_center_widget(widget, padding_x=25, padding_y=0):
        """Adjust the given widget's size to fit contents and re-center.

        Parameters:
            widget (obj): The widget to resize.
            padding_x (int): Any additional width to be applied.
            padding_y (int): Any additional height to be applied.
        """
        p1 = widget.rect().center()

        x = widget.minimumSizeHint().width() if padding_x else widget.width()
        y = widget.minimumSizeHint().height() if padding_y else widget.height()

        widget.resize(x + padding_x, y + padding_y)

        p2 = widget.rect().center()
        diff = p1 - p2
        widget.move(widget.pos() + diff)

    @staticmethod
    def move_and_center_widget(widget, pos, offset_x=2, offset_y=2):
        """Move and center the given widget on the given point.

        Parameters:
            widget (obj): The widget to resize.
            pos (obj): A point to move to.
            offset_x (int): The desired offset on the x axis. 2 is center.
            offset_y (int): The desired offset on the y axis.
        """
        width = pos.x() - (widget.width() / offset_x)
        height = pos.y() - (widget.height() / offset_y)

        widget.move(
            QtCore.QPoint(width, height)
        )  # center a given widget at a given position.

    @staticmethod
    def center_widget_on_screen(widget):
        """ """
        centerPoint = QtGui.QScreen.availableGeometry(
            QtWidgets.QApplication.primaryScreen()
        ).center()
        widget.move(centerPoint - widget.frameGeometry().center())

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

    def get_widgets_from_str(self, ui, name_string):
        """Get a list of corresponding widgets from a single shorthand formatted string.
        ie. 's000,b002,cmb011-15' would return object list: [<s000>, <b002>, <cmb011>, <cmb012>, <cmb013>, <cmb014>, <cmb015>]

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
            name_string (str): Widget object names separated by ','. ie. 's000,b004-7'. b004-7 specifies buttons b004 though b007.

        Returns:
            (list) QWidget(s)

        Example:
            get_widgets_from_str(<ui>, 's000,b002,cmb011-15')
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: {type(ui)}")

        widgets = []
        for n in Switchboard.unpack_names(name_string):
            try:
                w = getattr(ui, n)
                widgets.append(w)
            except AttributeError:
                self.logger.info(traceback.format_exc())

        return widgets

    def get_slots_from_string(self, slots, name_string):
        """Get a list of corresponding slots from a single shorthand formatted string.
        ie. 's000,b002,cmb011-15' would return methods: [<s000>, <b002>, <cmb011>, <cmb012>, <cmb013>, <cmb014>, <cmb015>]

        Parameters:
            slots (QWidget): The class containing the slots.
            name_string (str): Slot names separated by ','. ie. 's000,b004-7'. b004-7 specifies methods b004 through b007.

        Returns:
            (list) class methods.

        Example:
            get_slots_from_string(<ui>, 'slot1,slot2,slot3')
        """
        if not isinstance(slots, object):
            raise ValueError(f"Invalid datatype: {type(slots)}")

        slots = []
        for n in Switchboard.unpack_names(name_string):
            try:
                s = getattr(slots, n)
                slots.append(s)
            except AttributeError:
                self.logger.info(traceback.format_exc())

        return slots

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
            # get_widgets_from_str returns a widget list from a string of object_names.
            widgets = self.get_widgets_from_str(ui, buttons)

            # add each widget to the button group
            for w in widgets:
                w.button_group = grp
                grp.addButton(w)

            # Add the group to the list
            button_groups.append(grp)

        # Return a single group if only one was created, otherwise return the tuple of groups
        return format_return(button_groups)

    def toggle_widgets(self, ui, **kwargs):
        """Set multiple boolean properties, for multiple widgets, on multiple ui's at once.

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
            *kwargs: The property to modify. ex. setChecked, setUnChecked, setEnabled, setDisabled, setVisible, setHidden
                        value: string of object_names - object_names separated by ',' ie. 'b000-12,b022'
        Example:
            toggle_widgets(ui, setDisabled='b000', setUnChecked='chk009-12', setVisible='b015,b017')
        """
        for k in kwargs:  # property_ ie. setUnChecked
            # get_widgets_from_str returns a widget list from a string of object_names.
            widgets = self.get_widgets_from_str(ui, kwargs[k])

            state = True
            # strips 'Un' and sets the state from True to False. ie. 'setUnChecked' becomes 'setChecked' (False)
            if "Un" in k:
                k = k.replace("Un", "")
                state = False

            # set the property state for each widget in the list.
            for w in widgets:
                getattr(w, k)(state)

    def connect_multi(self, widgets, signals, slots, clss=None):
        """Connect multiple signals to multiple slots at once.

        Parameters:
            widgets (str/obj/list): ie. 'chk000-2' or [tb.ctx_menu.chk000, tb.ctx_menu.chk001]
            signals (str/list): ie. 'toggled' or ['toggled']
            slots (obj/list): ie. self.cmb002 or [self.cmb002]
            clss (obj/list): if the widgets arg is given as a string, then the class it belongs to can be explicitly given.
                    else, the current ui will be used.
        Example:
            connect_('chk000-2', 'toggled', self.cmb002, tb.ctx_menu)
            connect_([tb.ctx_menu.chk000, tb.ctx_menu.chk001], 'toggled', self.cmb002)
            connect_(tb.ctx_menu.chk015, 'toggled',
            [lambda state: self.rigging.tb004.setText('Unlock Transforms' if state else 'Lock Transforms'),
            lambda state: self.rigging_submenu.tb004.setText('Unlock Transforms' if state else 'Lock Transforms')])
        """
        if isinstance(widgets, (str)):
            try:  # get_widgets_from_str returns a widget list from a string of object_names.
                widgets = self.get_widgets_from_str(clss, widgets)
            except Exception:
                widgets = self.get_widgets_from_str(self.get_current_ui(), widgets)

        # if the variables are not of a list type; convert them.
        widgets = Iter.make_iterable(widgets)
        signals = Iter.make_iterable(signals)
        slots = Iter.make_iterable(slots)

        for widget in widgets:
            for signal in signals:
                signal = getattr(widget, signal)
                for slot in slots:
                    signal.connect(slot)

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
            checkboxes = self.get_widgets_from_str(ui, checkboxes)

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
            checkboxes = self.get_widgets_from_str(ui, checkboxes)

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

    def attribute_window(
        self,
        obj,
        window_title="",
        set_attribute_func=None,
        label_toggle_func=None,
        **attrs,
    ):
        """Create an AttributeWindow for the given object and attributes.

        Parameters:
            obj: The object to create the AttributeWindow for.
            window_title: The title of the AttributeWindow.
            set_attribute_func: A function to set the attribute on the object. ex. <your fuction>(obj, name, value)
                        If None, the attribute is set using: setattr(obj, name, value)
            label_toggle_func: A function to handle the label toggled event. ex. <your function>(obj, name, checked)
                        If None, no action is performed when a label is toggled.
            attrs: The attributes to add to the AttributeWindow.
        """
        # Create an AttributeWindow
        window = self.AttributeWindow(self.parent(), checkable=bool(label_toggle_func))
        window.set_style(theme="dark")
        window.setTitle(window_title)
        window.position = "cursorPos"

        for attribute_name, attribute_value in attrs.items():
            window.add_attribute(attribute_name, attribute_value)

        # Connect the valueChanged signal to a slot that sets the attribute on the object
        if set_attribute_func is None:
            window.valueChanged.connect(lambda name, value: setattr(obj, name, value))
        else:
            window.valueChanged.connect(
                lambda name, value: set_attribute_func(obj, name, value)
            )

        # Connect the labelToggled signal to a slot that handles the label toggled event
        if label_toggle_func is not None:
            window.labelToggled.connect(
                lambda name, checked: label_toggle_func(obj, name, checked)
            )

        window.show()

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

        for o in Iter.make_iterable(obj):
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

    sb = Switchboard(slots_location=MyProjectSlots)
    ui = sb.example
    ui.set_style(theme="dark")

    print("ui:".ljust(20), ui)
    print("ui name:".ljust(20), ui.name)
    print("ui path:".ljust(20), ui.path)  # The directory path containing the UI file
    print("is current ui:".ljust(20), ui.is_current)
    print("is connected:".ljust(20), ui.is_connected)
    print("is initialized:".ljust(20), ui.is_initialized)
    print("slots:".ljust(20), ui.slots)  # The associated slots class instance
    print("method:".ljust(20), ui.MyButtonsObjectName.get_slot())
    print(
        "widget from method:".ljust(20),
        sb.get_widget_from_method(ui.MyButtonsObjectName.get_slot()),
    )
    for w in ui.widgets:  # All the widgets of the UI
        print(
            "child widget:".ljust(20),
            (w.name or type(w).__name__).ljust(20),
            w.base_name.ljust(20),
            id(w),
        )

    ui.show(app_exec=True)

logging.info(__name__)  # module name
# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------

# --------------------------------------------------------------------------------------------
# deprecated:
# --------------------------------------------------------------------------------------------


# def _create_slot_wrapper(self, slot, widget):
#     """Creates a wrapper function for a slot that includes the widget as a parameter if possible.

#     The wrapper function is designed to handle different widget-specific signal values as keyword arguments.
#     The signal values are passed to the slot function as keyword arguments based on the type of the widget.

#     If the slot function does not accept the widget or signal-specific keyword argument, it is called with positional arguments as a fallback.

#     Parameters:
#         slot (callable): The slot function to be wrapped. This is typically a method of a class.
#         widget (QtWidgets.QWidget): The widget that the slot is connected to. This widget is passed to the slot function as a keyword argument,
#             and its signal value is also passed as a keyword argument.

#     Returns:
#         callable: The slot wrapper function. This function can be connected to a widget signal and is responsible for calling the original slot function
#             with the appropriate arguments.
#     """

#     def slot_wrapper(*args, **kwargs):
#         parameters = inspect.signature(slot).parameters
#         has_kwargs = any(p.kind == p.VAR_KEYWORD for p in parameters.values())
#         has_widget = "widget" in parameters
#         try:
#             if has_kwargs or has_widget:
#                 kwargs["widget"] = widget
#             slot(*args, **kwargs)
#         except TypeError:  # slot didn't accept widget in kwargs
#             if len(args) > 0:  # if there is a value, try to call the slot with it
#                 slot(args[0])
#             else:  # no value, so call the slot with no arguments
#                 slot()

#     return slot_wrapper


# def sync_all_widgets(self, *uis, **kwargs):
#     """Set sync connections for all widgets of the given UI objects.

#     Parameters:
#         *uis: A tuple of previously loaded dynamic UI objects to sync widgets among.
#     """
#     for i, ui1 in enumerate(uis):
#         for ui2 in uis[i + 1 :]:
#             for w1 in ui1.widgets:
#                 try:
#                     w2 = self.get_widget(w1.name, ui2)
#                 except AttributeError:
#                     continue

#                 pair_id = hash((w1, w2))
#                 if pair_id in self._synced_pairs:
#                     continue

#                 self.sync_widgets(w1, w2, **kwargs)

# def sync_widgets(self, w1, w2, **kwargs):
#     """Set the initial signal connections that will call the _sync_attributes function on state changes.

#     Parameters:
#         w1 (obj): The first widget to sync.
#         w2 (obj): The second widget to sync.
#         kwargs: The attribute(s) to sync as keyword arguments.
#     """
#     try:  # get the default signal for the given widget.
#         signals1 = self.get_default_signals(w1)
#         signals2 = self.get_default_signals(w2)

#         # set sync connections for each of the widgets signals.
#         for s1, s2 in zip(signals1, signals2):
#             s1.connect(lambda: self._sync_attributes(w1, w2, **kwargs))
#             s2.connect(lambda: self._sync_attributes(w2, w1, **kwargs))

#         pair_id = hash((w1, w2))
#         self._synced_pairs.add(pair_id)

#     except (AttributeError, KeyError):
#         return

# attributesGetSet = {
#     "value": "setValue",
#     "text": "setText",
#     "icon": "setIcon",
#     "checkState": "setCheckState",
#     "isChecked": "setChecked",
#     "isDisabled": "setDisabled",
# }

# def _sync_attributes(self, frm, to, attributes=[]):
#     """Sync the given attributes between the two given widgets.
#     If a widget does not have an attribute it will be silently skipped.

#     Parameters:
#         frm (obj): The widget to transfer attribute values from.
#         to (obj): The widget to transfer attribute values to.
#         attributes (str/list)(dict): The attribute(s) to sync. ie. a setter attribute 'setChecked' or a dict containing getter:setter pairs. ie. {'isChecked':'setChecked'}
#     """
#     if not attributes:
#         attributes = self.attributesGetSet

#     elif not isinstance(attributes, dict):
#         attributes = {
#             next(
#                 (k for k, v in self.attributesGetSet.items() if v == i), None
#             ): i  # construct a gettr setter pair dict using only the given setter values.
#             for i in Iter.make_iterable(attributes)
#         }

#     _attributes = {}
#     for gettr, settr in attributes.items():
#         try:
#             _attributes[settr] = getattr(frm, gettr)()
#         except AttributeError:
#             pass

#     for (
#         attr,
#         value,
#     ) in _attributes.items():  # set the second widget's attributes from the first.
#         try:
#             getattr(to, attr)(value)
#         except AttributeError:
#             pass

# def sync_widget_values(self, widget, value):
#     # Get the relatives of the widget's UI
#     relatives = self.get_ui_relatives(widget.ui)

#     # For each relative UI...
#     for relative in relatives:
#         # Get the widget of the same name
#         relative_widget = getattr(relative, widget.name, None)

#         # If the relative widget exists...
#         if relative_widget is not None:
#             # Check the type of the widget and use the appropriate method to set the value
#             if isinstance(relative_widget, QtWidgets.QLabel):
#                 relative_widget.setText(value)
#             elif isinstance(relative_widget, QtWidgets.QSpinBox):
#                 relative_widget.setValue(value)
#             # Add more elif statements for other widget types as needed

# def connect_slot(self, widget, slot):
#     """
#     Connects a slot to its corresponding signals for a given widget.

#     This function attempts to fetch signals from the slot decorator. If it fails to fetch them,
#     it resorts to the default signals based on the widget's derived type. For each fetched signal,
#     the function checks if the signal is a valid attribute of the widget. If it is, it connects
#     the slot to this signal and appends the slot to the connected slots list.

#     Parameters:
#         widget (QtWidgets.QWidget): A widget for which the slot is connected to the signals.
#         slot (method): The slot method to connect to the signals.

#     Raises:
#         TypeError: If the signal name is not a string or if no valid signal was found for the widget.
#     """
#     signals = getattr(
#         slot,
#         "signals",
#         Iter.make_iterable(self.default_signals.get(widget.derived_type)),
#     )

#     def slot_wrapper(*args, **kwargs):
#         self.slot_history(add=slot)  # update slot history before calling the slot
#         slot(*args, **kwargs)

#     for signal_name in signals:
#         if not isinstance(signal_name, str):
#             raise TypeError(
#                 f"Signal name must be a string, not '{type(signal_name)}'"
#             )
#         signal = getattr(widget, signal_name, None)
#         if signal:
#             signal.connect(slot_wrapper)
#             if widget not in self._connected_slots:
#                 self._connected_slots[widget] = {}
#             self._connected_slots[widget][signal_name] = slot_wrapper
#         else:
#             self.logger.warning(
#                 f"No valid signal '{signal_name}' found for {widget.ui.name}.{widget.name}"
#             )

# def connect_slots(self, ui, widgets=None):
#     """Connects the signals to their respective slots for the widgets of the given ui.

#     This function ensures that existing signal-slot connections are not repeated.
#     If a connection already exists, it is not made again.

#     Parameters:
#         ui (QWidget): The dynamic UI object containing widgets.
#         widgets (Iterable[QtWidgets.QWidget], optional): A specific set of widgets for which
#             to connect slots. If not provided, all widgets from the ui are used.

#     Raises:
#         ValueError: If ui is not an instance of QWidget.

#     Side effect:
#         If successful, sets `ui.is_connected` to True indicating that
#         the slots for the UI's widgets are connected.
#     """
#     if not isinstance(ui, QtWidgets.QWidget):
#         raise ValueError(f"Invalid datatype: {type(ui)}")

#     if widgets is None:
#         if ui.is_connected:
#             return
#         widgets = ui.widgets

#     for widget in Iter.make_iterable(widgets):
#         slot = widget.get_slot()
#         self.logger.info(f"Widget: {widget}, Slot: {slot}")
#         if slot:
#             # Get signals from slot decorator, or default signals if not present
#             signals = getattr(
#                 slot, "signals", [self.default_signals.get(widget.derived_type)]
#             )
#             for signal_name in signals:
#                 signal = getattr(widget, signal_name, None)
#                 self.logger.info(f"Signal Name: {signal_name}, Signal: {signal}")
#                 if signal:
#                     if slot not in self._connected_slots[signal]:
#                         signal.connect(slot)
#                         self._connected_slots[signal].append(slot)

#                 elif signal_name in self.default_signals:
#                     signal = getattr(
#                         widget, self.default_signals[signal_name], None
#                     )

#                 try:  # append the slot to _slot_history each time the signal is triggered.
#                     signal.connect(
#                         lambda *args, s=slot: self._slot_history.append(s)
#                     )
#                 except AttributeError:  # signal is NoneType
#                     pass
#     ui.is_connected = True

# def show_and_connect(self, ui, connect_on_show=True):
#     """Register the uiName in history as current,
#     set slot connections, and show the given ui.
#     An override for the built-in show method.

#     Parameters:
#         ui (QWidget): A previously loaded dynamic ui object.
#         connect_on_show (bool): The the ui as connected.
#     """
#     if not isinstance(ui, QtWidgets.QWidget):
#         raise ValueError(f"Invalid datatype: {type(ui)}")

#     if connect_on_show:
#         ui.connected = True
#     ui.__class__.show(ui)

# def setConnections(self, ui):
#     """Replace any signal connections of a previous ui with the set for the ui of the given name.

#     Parameters:
#         ui (QWidget): A previously loaded dynamic ui object.
#     """
#     if not isinstance(ui, QtWidgets.QWidget):
#         raise ValueError(f"Invalid datatype: {type(ui)}")

#     prev_ui = self.get_prev_ui(allow_duplicates=True)
#     if prev_ui:
#         if prev_ui == ui:
#             return
#         elif prev_ui.is_connected and not prev_ui.is_stacked_widget:
#             self.disconnect_slots(prev_ui)

#     if not ui.is_connected:
#         self.connect_slots(ui)

#     # sync all widgets within relative uis.
#     relatives = self.get_ui_relatives(ui)
#     self.sync_all_widgets(relatives)

# def sync_all_widgets(self, frm, to, **kwargs):
#     """Extends setSynConnections method to set sync connections
#     for all widgets of the given pair of ui objects.

#     Parameters:
#             frm (obj): A previously loaded dynamic ui object to sync widgets from.
#             to (obj): A previously loaded dynamic ui object to sync widgets to.
#     """
#     for w1 in frm.widgets:
#         try:
#             w2 = self.get_widget(w1.name, to)
#         except AttributeError:
#             continue

#         pair_id = hash((w1, w2))
#         if pair_id in self._synced_pairs:
#             continue

#         self.sync_widgets(w1, w2, **kwargs)

# def sync_widgets(self, w1, w2, **kwargs):
#     """Set the initial signal connections that will call the _sync_attributes function on state changes.

#     Parameters:
#             w1 (obj): The first widget to sync.
#             w2 (obj): The second widget to sync.
#             kwargs = The attribute(s) to sync as keyword arguments.
#     """
#     try:
#         signals1 = self.get_default_signals(
#             w1
#         )  # get the default signal for the given widget.
#         signals2 = self.get_default_signals(w2)

#         for s1, s2 in zip(
#             signals1, signals2
#         ):  # set sync connections for each of the widgets signals.
#             s1.connect(lambda: self._sync_attributes(w1, w2, **kwargs))
#             s2.connect(lambda: self._sync_attributes(w2, w1, **kwargs))

#         pair_id = hash((w1, w2))
#         self._synced_pairs.add(pair_id)

#     except (AttributeError, KeyError) as error:
#         # if w1 and w2: print ('# {}: {}.sync_widgets({}, {}): {}. args: {}, {} #'.format('KeyError' if type(error)==KeyError else 'AttributeError', __name__, w1.objectName(), w2.objectName(), error, w1, w2)) #debug
#         return

# @staticmethod
# def get_derived_type(
#     widget, name=False, module="QtWidgets", inc=[], exc=[], filterByBaseType=False
# ):
#     """Get the base class of a custom widget.
#     If the type is a standard widget, the derived type will be that widget's type.

#     Parameters:
#             widget (str/obj): QWidget or it's objectName.
#             name (bool): Return the class or the class name.
#             module (str): The name of the base class module to check for.
#             inc (list): Widget types to include. All other will be omitted. Exclude takes dominance over include. Meaning, if the same attribute is in both lists, it will be excluded.
#             exc (list): Widget types to exclude. ie. ['QWidget', 'QAction', 'QLabel', 'QPushButton', 'QListWidget']
#             filterByBaseType (bool): When using `inc`, or `exc`; Filter by base class name, or derived class name. ie. 'QLayout'(base) or 'QGridLayout'(derived)

#     Returns:
#             (obj)(string)(None) class or class name if `name`. ie. 'QPushButton' from a custom widget with class name: 'PushButton'
#     """
#     # logging.info(widget.__class__.__mro__) #debug
#     for c in widget.__class__.__mro__:
#         if (
#             c.__module__ == module or c.__module__.split(".")[-1] == module
#         ):  # check for the first built-in class. ie. 'PySide2.QtWidgets' or 'QtWidgets'
#             typ = c.__class__.__base__.__name__ if filterByBaseType else c
#             if not (typ in exc and (typ in inc if inc else typ not in inc)):
#                 return typ.__name__ if name else typ


# @staticmethod
# def _getUiLevelFromDir(filePath):
#     """Get the UI level by looking for trailing intergers in it's dir name.
#     If none are found a default level of 3 (main menu) is used.

#     Parameters:
#         filePath (str): The directory containing the ui file. ie. 'O:/Cloud/Code/_scripts/uitk/uitk/ui/uiLevel_0/init.ui'

#     Example:
#         menu types:
#             level 1: stackedwidget: base menu
#             level 2: stackedwidget: sub menu
#             level 3: standard menu
#     Returns:
#         (int) If no level is found, a level of 3 (standard menu) will be returned.
#     """
#     ui_dir = File.format_path(filePath, "dir")
#     default_level = 3
#     try:
#         return int(re.findall(r"\d+\s*$", ui_dir)[0])  # get trailing integers.
#     except IndexError:  # int not found.
#         return default_dir

# @staticmethod
# def unpack_names(name_string):
#   '''Get a list of individual names from a single name string.
#   If you are looking to get multiple objects from a name string, call 'get_widgets_from_str' directly instead.

#   Parameters:
#       name_string = string consisting of widget names separated by commas. ie. 'v000, b004-6'

#   Returns:
#       unpacked names. ie. ['v000','b004','b005','b006']

#   Example: unpack_names('chk021-23, 25, tb001')
#   '''
#   packed_names = [n.strip() for n in name_string.split(',') #build list of all widgets passed in containing '-'
#                       if '-' in n or n.strip().isdigit()]

#   otherNames = [n.strip() for n in name_string.split(',') #all widgets passed in not containing '-'
#                       if '-' not in n and not n.strip().isdigit()]

#   unpacked_names=[] #unpack the packed names:
#   for name in packed_names:
#       if '-' in name:
#           name = name.split('-') #ex. split 'b000-8'
#           prefix = name[0].strip('0123456789') #ex. split 'b' from 'b000'
#           start = int(name[0].strip('abcdefghijklmnopqrstuvwxyz') or 0) #start range. #ex. '000' #converting int('000') returns None, if case; assign 0.
#           stop = int(name[1])+1 #end range. #ex. '8' from 'b000-8' becomes 9, for range up to 9 but not including 9.
#           unpacked_names.extend([str(prefix)+'000'[:-len(str(num))]+str(num) for num in range(start,stop)]) #build list of name strings within given range
#           last_name = name
#           last_prefix = prefix
#       else:
#           num = name
#           unpacked_names.extend([str(last_prefix)+'000'[:-len(str(num))]+str(num)])

#   return otherNames+unpacked_names

# def __getattr__(self, attr_name):
#   found_widget = self.sb._get_widget_from_ui(self, attr_name)
#   if found_widget:
#       self.sb.init_widgets(self, found_widget)
#       return found_widget
#   raise AttributeError(f'{self.__class__.__name__} has no attribute `{attr_name}`')

# def get_base_name(widget):
#       '''Query a widgets prefix.
#       A valid prefix is returned when the given widget's objectName startswith an alphanumeric char,
#       followed by at least three integers. ex. i000 (alphanum,int,int,int)

#       Parameters:
#           widget (str/obj): A widget or it's object name.

#       Returns:
#           (str)
#       '''
#       prefix=''
#       if not isinstance(widget, (str)):
#           widget = widget.objectName()
#       for char in widget:
#           if not char.isdigit():
#               prefix = prefix+char
#           else:
#               break

#       i = len(prefix)
#       integers = [c for c in widget[i:i+3] if c.isdigit()]
#       if len(integers)>2 or len(widget)==i:
#           return prefix

# def set_attributes(self, obj=None, order=['setVisible'], **kwargs):
#   '''Set attributes for a given object.

#   Parameters:
#       obj (obj): the child obj, or widgetAction to set attributes for. (default=self)
#       order (list): List of string keywords. ie. ['move', 'setVisible']. attributes in this list will be set last, in order of the list. an example would be setting move positions after setting resize arguments.
#       **kwargs = The keyword arguments to set.
#   '''
#   if not kwargs:
#       return

#   obj = obj if obj else self

#   for k in order:
#       v = kwargs.pop(k, None)
#       if v:
#           from collections import OrderedDict
#           kwargs = OrderedDict(kwargs)
#           kwargs[k] = v

#   for attr, value in kwargs.items():
#       try:
#           getattr(obj, attr)(value)

#       except AttributeError as error:
#           pass; # logging.info(__name__+':','set_attributes:', obj, order, kwargs, error)
