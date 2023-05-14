# !/usr/bin/python
# coding=utf-8
import os, sys
import re
import importlib
import inspect
import logging, traceback
from functools import wraps
from collections import defaultdict
from typing import List, Union
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtUiTools import QUiLoader
from pythontk import (
    File,
    Str,
    Iter,
    getDerivedType,
    setAttributes,
    formatReturn,
)


import functools
from functools import wraps


def signals(*signals):
    """Decorator to specify the signals that a slot should be connected to.

    Args:
        *signals (str): One or more signal names as strings.

    Returns:
        decorator: A decorator that can be applied to a slot method.

    Usage:
        @signals('clicked', 'released')
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
        delimiters (tuple, optional): A tuple of two delimiter strings, where the first delimiter is used to split the hierarchy and the second delimiter is used to split hierarchy levels. Defaults to (".", "#").
        preload (bool): Load all UI immediately. Otherwise UI will be loaded as required.
        persist (bool): Do not assign the UI's slots attribute a None value when a class is not found.
        set_legal_name_no_tags_attr (bool): If True, sets the legal name without tags attribute for the object (provinding there are no conflicts). Defaults to False.
        suppress_warnings (bool): Suppress legal name warning messages if True.

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
        "QAction": "triggered",
        "QLabel": "released",
        "QPushButton": "clicked",
        "QListWidget": "itemClicked",
        "QTreeWidget": "itemClicked",
        "QComboBox": "currentIndexChanged",
        "QSpinBox": "valueChanged",
        "QDoubleSpinBox": "valueChanged",
        "QCheckBox": "stateChanged",
        "QRadioButton": "toggled",
        "QLineEdit": "textChanged",
        "QTextEdit": "textChanged",
        "QSlider": "valueChanged",
        "QProgressBar": "valueChanged",
        "QDial": "valueChanged",
        "QScrollBar": "valueChanged",
        "QDateEdit": "dateChanged",
        "QDateTimeEdit": "dateTimeChanged",
        "QTimeEdit": "timeChanged",
        "QMenu": "triggered",
        "QMenuBar": "triggered",
        "QTabBar": "currentChanged",
        "QTabWidget": "currentChanged",
        "QToolBox": "currentChanged",
        "QStackedWidget": "currentChanged",
    }

    def __init__(
        self,
        parent=None,
        ui_location="",
        widgets_location="",
        slots_location="",
        delimiters=(".", "#"),
        preload=False,
        persist=False,
        set_legal_name_no_tags_attr=False,
        suppress_warnings=False,
    ):
        super().__init__(parent)
        """
        """
        self.suppress_warnings = suppress_warnings

        calling_frame = inspect.currentframe().f_back
        self.default_dir = self.get_module_dir_from_frame(
            calling_frame
        )  # calling mod dir.
        self.module_dir = File.getFilepath(__file__)  # the directory of this module.

        # initialize the files dicts before the location dicts (dependancies).
        self.ui_files = {}  # UI paths.
        self.widget_files = {}  # widget paths.
        self.slots_files = {}  # slot class paths.

        # use the relative filepath of this module if None is given.
        self.ui_location = ui_location or f"{self.module_dir}/ui"
        self.widgets_location = widgets_location or f"{self.module_dir}/widgets"
        self.slots_location = slots_location or f"{self.module_dir}/slots"

        self.delimiters = delimiters
        self.persist = persist
        self.set_legal_name_no_tags_attr = set_legal_name_no_tags_attr

        self._loadedUi = {}  # all loaded ui.
        self._ui_history = []  # ordered ui history.
        self._wgtHistory = []  # previously used widgets.
        self._registeredWidgets = {}  # all registered custom widgets.
        self._slot_instances = {}  # slot classes that have been instantiated.
        self._connected_slots = defaultdict(list)  # currently connected slots.
        self._synced_pairs = set()  # hashed values representing synced widgets.
        self._gcProtect = set()  # objects protected from garbage collection.

        if preload:
            self.load_all_ui()

    def __getattr__(self, attr_name):
        """If an unknown attribute matches the name of a UI in the current UI directory; load and return it.
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
        found_widget = self.widget_files.get(Str.setCase(attr_name, "camel"), None)
        if found_widget:
            widget = self.register_widgets(found_widget)
            # check if any of the widgets in the list has a name that matches the attribute name in a case-insensitive manner.
            if isinstance(widget, list):
                widget = next(
                    iter(w for w in widget if w.__name__.lower() == attr_name.lower()),
                    None,
                )
            # If the widget's name matches the attribute name, the widget is returned.
            if widget and widget.__name__.lower() == attr_name.lower():
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

        except AttributeError as error:
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
            # use getFilepath to get the full path to the module.
            self._ui_location = File.getFilepath(x)
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

        except AttributeError as error:
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
            # use getFilepath to get the full path to the module.
            self._widgets_location = File.getFilepath(x)
        elif isinstance(x, (list, tuple, set, QtWidgets.QWidget)):
            self._widgets_location = Iter.makeList(x)
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

        except AttributeError as error:
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
            # use getFilepath to get the full path to the module.
            self._slots_location = File.getFilepath(x)
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
            raise ValueError(f"Incorrect datatype: {type(ui)}, expected QWidget.")

        self.set_current_ui(ui)

    @property
    def prev_ui(self) -> QtWidgets.QWidget:
        """Get the previous ui from history.

        Returns:
            (obj)
        """
        return self.get_prev_ui()

    @property
    def prev_command(self) -> object:
        """Get the last called slot method.

        Returns:
            (obj) method.
        """
        try:
            return self.prev_commands[-1]

        except IndexError as error:
            return None

    @property
    def prev_commands(self) -> tuple:
        """Get a list of previously called slot methods.

        Returns:
            (tuple) list of methods.
        """
        # limit to last 10 elements and get methods from widget history.
        cmds = [w.get_slot() for w in self._wgtHistory[-10:]]
        # remove any duplicates (keeping the last element). [hist.remove(l) for l in hist[:] if hist.count(l)>1] #
        hist = tuple(dict.fromkeys(cmds[::-1]))[::-1]
        return hist

    def _construct_ui_files_dict(self) -> dict:
        """Build and return a dictionary of UI paths, where the keys are the UI file names and the values
        are the corresponding file paths.

        Returns:
            dict: A dictionary of UI file paths with UI file names as keys.
        """
        if not isinstance(self.ui_location, str):
            raise ValueError(
                f"Invalid datatype for _construct_ui_files_dict: {type(ui_dir)}, expected str."
            )

        ui_filepaths = File.getDirContents(
            self.ui_location, "filepaths", incFiles="*.ui"
        )
        ui_files = File.getFileInfo(ui_filepaths, "filename|filepath")
        return dict(ui_files)

    def _construct_widget_files_dict(self) -> dict:
        """Build and return a dictionary of widget paths, where the keys are the widget file names and the
        values are the corresponding file paths or widget objects.

        Returns:
            dict: A dictionary of widget file paths or widget objects with widget file names as keys.
        """
        if isinstance(self.widgets_location, str):
            widget_filepaths = File.getDirContents(
                self.widgets_location, "filepaths", incFiles="*.py"
            )
            widget_files = File.getFileInfo(widget_filepaths, "filename|filepath")
            return dict(widget_files)
        elif isinstance(self.widgets_location, (list, tuple, set)):
            widget_dict = {}
            for widget in self.widgets_location:
                widget_name = widget.__name__
                widget_file = inspect.getfile(widget)
                widget_dict[widget_name] = widget_file
            return widget_dict
        else:
            raise ValueError(
                f"Invalid datatype for _construct_widget_files_dict: {type(ui_dir)}, expected str, list, tuple, or set."
            )

    def _construct_slots_files_dict(self) -> dict:
        """Build and return a dictionary of slot class paths, where the keys are the slot class file names
        and the values are the corresponding file paths. The method supports two types of input for
        slots_location: a directory path (str) or a class object.

        Returns:
            dict: A dictionary of slot class file paths with slot class file names as keys.
        """
        if isinstance(self.slots_location, str):
            slots_filepaths = File.getDirContents(
                self.slots_location, "filepaths", incFiles="*.py"
            )
            slots_files = File.getFileInfo(slots_filepaths, "filename|filepath")
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
                f"Invalid datatype for _construct_slots_files_dict: {type(ui_dir)}, expected str or class."
            )

    def init_widgets(
        self, ui, widgets, recursive=True, return_all_widgets=False, **kwargs
    ) -> set:
        """Add widgets as attributes of the ui while giving additional attributes to the widgets themselves.

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
            widgets (obj/list): A widget or list of widgets to be added.
            recursive (bool): Whether to recursively add child widgets (default=True).
            kwargs (): Keyword arguments to set additional widget attributes.

        Returns:
            (set) The added widgets.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Incorrect datatype: {type(ui)}")

        added_widgets = set()
        for w in Iter.makeList(widgets):
            if w in ui._widgets or w in added_widgets or not self.is_widget(w):
                continue

            w.ui = ui
            w.name = w.objectName()
            w.type = w.__class__.__name__
            w.derived_type = getDerivedType(w, module="QtWidgets", return_name=True)
            # get the default widget signals as list. ie. [<widget.valueChanged>]
            w.signals = self.get_default_signals(w)
            # get a string stripped of trailing non-letter chars. ie. 'cmb' from 'cmb015'
            w.base_name = self.get_base_name(w.name)
            w.get_slot = lambda w=w, u=ui: getattr(self.get_slots(u), w.name, None)

            setAttributes(w, **kwargs)
            setattr(ui, w.name, w)
            added_widgets.add(w)
            # print('initWidgts:', w.ui.name.ljust(26), w.base_name.ljust(25), (w.name or type(w).__name__).ljust(25), w.type.ljust(15), w.derived_type.ljust(15), id(w)) #debug

            if recursive:
                child_widgets = w.findChildren(QtWidgets.QWidget)
                self.init_widgets(ui, child_widgets, **kwargs)

        ui._widgets.update(added_widgets)
        return added_widgets if not return_all_widgets else ui._widgets

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
                [('class', 'DraggableHeader'), ('extends', 'QPushButton'), ('header', 'widgets.pushbuttondraggable.h')]
        from:
            <customwidget>
                    <class>DraggableHeader</class>
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
        # logging.info(f.read()) #debug
        content = list(f.readlines())

        result = []
        actual_prop_text = ""
        for i, l in enumerate(content):
            if l.strip() == "<{}>".format(prop):
                actual_prop_text = l
                start = i + 1
            elif l == Str.insert(actual_prop_text, "/", "<"):
                end = i

                delimiters = (
                    "</",
                    "<",
                    ">",
                    "\n",
                    " ",
                )
                regex_pattern = "|".join(map(re.escape, delimiters))

                lst = [
                    tuple(dict.fromkeys([i for i in re.split(regex_pattern, s) if i]))
                    for s in content[start:end]
                ]  # use dict to remove any duplicates.
                result.append(lst)

        f.close()
        return result

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
        import re

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
            raise ValueError(f"Incorrect datatype: {type(ui)}")

        dct = {
            c: c.objectName()
            for c in ui.findChildren(QtWidgets.QWidget, None)
            if (not object_names_only or c.objectName())
        }

        return Iter.filterDict(dct, inc, exc, keys=True, values=True)

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
            raise ValueError(f"Incorrect datatype: {type(ui)}")

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
        mod_name = File.formatPath(path, "name")
        if mod_name:
            wgt_name = Str.setCase(mod_name, "pascal")
            if wgt_name in self._registeredWidgets:
                return {}

            if not File.isValid(path):
                path = os.path.join(self.widgets_location, f"{mod_name}.py")

            try:
                spec = importlib.util.spec_from_file_location(mod_name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except ModuleNotFoundError:
                logging.info(traceback.format_exc())
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
                logging.info(traceback.format_exc())
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
            raise ValueError(f"Incorrect datatype: {type(ui)}")

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

        self.init_widgets(ui, ui.findChildren(QtWidgets.QWidget))
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
            raise ValueError(f"Incorrect datatype: {type(ui)}")

        if hasattr(ui, "_slots"):
            return ui._slots

        if inspect.isclass(self.slots_location):
            clss = self.slots_location
            return self.set_slots(ui, clss)

        try:
            found_path = self._find_slots_class_module(ui)
        except ValueError:
            logging.info(traceback.format_exc())
            found_path = None

        if not found_path:
            for relative_name in self.get_ui_relatives(ui, upstream=True, reverse=True):
                relative_ui = self.get_ui(relative_name)
                if relative_ui:
                    try:
                        found_path = self._find_slots_class_module(relative_ui)
                        break
                    except ValueError:
                        logging.info(traceback.format_exc())

        if found_path:
            slots_instance = self.set_slots(ui, found_path)
            return slots_instance
        else:
            if not self.persist:
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
        slots_dir = File.formatPath(self.slots_location, "dir")
        suffix = slots_dir if isinstance(slots_dir, str) else ""

        legal_name_camel = Str.setCase(ui.legal_name, case="camel")
        legal_name_notags_camel = Str.setCase(ui.legal_name_no_tags, case="camel")

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

        cls_name = Str.setCase(name, case="pascal")
        clss = getattr(mod, cls_name, None)

        if clss is None:
            clss = inspect.getmembers(mod, inspect.isclass)[0][1]
            if not self.suppress_warnings:
                if clss:
                    logging.warning(
                        f"Slot class '{cls_name}' not found for '{ui.name}'. Using '{clss}' instead."
                    )
                else:
                    logging.warning(
                        f"Slot class '{cls_name}' not found for '{ui.name}'."
                    )

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
        for w in Iter.makeList(widgets):  # assure widgets is a list.
            if isinstance(w, str):
                widgets_ = self._get_widgets_from_dir(w)
                for w_ in widgets_.values():
                    rw = self.register_widgets(w_)
                    result.append(rw)
                continue

            elif w.__name__ in self._registeredWidgets:
                continue

            try:
                self.registerCustomWidget(w)
                self._registeredWidgets[w.__name__] = w
                setattr(self, w.__name__, w)
                result.append(w)

            except Exception:
                logging.info(traceback.format_exc())

        # if 'widgets' is given as a list; return a list.
        return formatReturn(result, widgets)

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
        name = File.formatPath(file, "name")
        path = File.formatPath(file, "path")

        # register custom widgets
        if widgets is None and not isinstance(
            self.widgets_location, str
        ):  # widget objects defined in widgets.
            widgets = self.widgets_location
        if widgets is not None:  # widgets given explicitly or defined in widgets.
            self.register_widgets(widgets)
        else:  # search for and attempt to load any widget dependancies using the path defined in widgets.
            lst = self.get_property_from_ui_file(file, "customwidget")
            for l in lst:  # get any custom widgets from the ui file.
                try:
                    className = l[0][1]
                    # ie. 'DraggableHeader' from ('class', 'DraggableHeader')
                    derived_type = l[1][1]
                    # ie. 'QPushButton' from ('extends', 'QPushButton')
                except IndexError as error:
                    continue

                mod_name = Str.setCase(className, "camel")
                fullpath = os.path.join(self.widgets_location, mod_name + ".py")
                self.register_widgets(fullpath)

        ui = self.MainWindow(
            self,
            file,
            set_legal_name_no_tags_attr=self.set_legal_name_no_tags_attr,
            suppress_warnings=self.suppress_warnings,
        )
        self._loadedUi[ui.name] = ui
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
            return getattr(self, ui)

        if isinstance(ui, QtWidgets.QWidget):
            return ui

        elif not ui:
            return self.ui

        else:
            raise ValueError(f"Incorrect datatype for ui: {type(ui)}")

    def show_and_connect(self, ui, connect_on_show=True):
        """Register the uiName in history as current,
        set slot connections, and show the given ui.
        An override for the built-in show method.

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
            connect_on_show (bool): The the ui as connected.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Incorrect datatype: {type(ui)}")

        if connect_on_show:
            ui.connected = True
        ui.__class__.show(ui)

    def get_current_ui(self) -> QtWidgets.QWidget:
        """Get the current ui.

        Returns:
            (obj): A previously loaded dynamic ui object.
        """
        try:
            return self._current_ui

        except AttributeError as error:
            # if only one ui is loaded set that ui as current.
            if len(self._loadedUi) == 1:
                ui = next(iter(self._loadedUi.values()))
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
            raise ValueError(f"Incorrect datatype: {type(ui)}")

        current_ui = getattr(self, "_current_ui", None)
        if current_ui == ui:
            return

        self._current_ui = ui
        self._ui_history.append(ui)
        # logging.info(f"_ui_history: {u.name for u in self._ui_history}")  # debug

    def get_prev_ui(
        self,
        allow_duplicates=False,
        allow_current=False,
        as_list=False,
        inc=[],
        exc=[],
    ):
        """Get ui from history.
        ex. _ui_history list: ['previousName2', 'previousName1', 'currentName']

        Parameters:
            allow_duplicates (bool): Applicable when returning as_list. Allows for duplicate names in the returned list.
            allow_current (bool): Allow the currentName. Default is off.
            as_list (bool): Returns the full list of previously called names. By default duplicates are removed.
            inc (str)(int)(obj/list): The objects(s) to include.
                            supports using the '*' operator: startswith*, *endswith, *contains*
                            Will include all items that satisfy ANY of the given search terms.
                            meaning: '*.png' and '*Normal*' returns all strings ending in '.png' AND all
                            strings containing 'Normal'. NOT strings satisfying both terms.
            exc (str)(int)(obj/list): The objects(s) to exclude. Similar to include.
                            exlude take precidence over include.
        Returns:
            (str/list) if 'as_list': returns [list of string names]
        """
        # keep original list length restricted to last 200 elements
        self._ui_history = self._ui_history[-200:]
        # work on a copy of the list, keeping the original intact
        hist = self._ui_history.copy()

        if not allow_current:  # remove the last index. (currentName)
            hist = hist[:-1]

        # remove any previous duplicates if they exist; keeping the last added element.
        if not allow_duplicates:
            [hist.remove(u) for u in hist[:] if hist.count(u) > 1]

        filtered = Iter.filterWithMappedValues(
            hist, Iter.filterList, lambda u: u.name, inc, exc
        )

        if as_list:
            return filtered  # return entire list after being modified by any flags such as 'allow_duplicates'.
        else:
            try:
                return filtered[-1]  # return the previous ui name if one exists.
            except:
                return None

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
        ui_name = ui if isinstance(ui, str) else ui.name

        relatives = Str.getMatchingHierarchyItems(
            self.ui_files.keys(),
            ui_name,
            upstream,
            exact,
            downstream,
            reverse,
            self.delimiters,
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

    def get_widgets_by_type(self, types, ui=None, derived_type=False):
        """Get widgets of the given types.

        Parameters:
            types (str/list): A widget class name, or list of widget class names. ie. 'QPushbutton' or ['QPushbutton', 'QComboBox']
            ui (str/obj): Parent ui name, or ui object. ie. 'polygons' or <polygons>
                                            If no name is given, the current ui will be used.
            derived_type (bool): Get by using the parent class of custom widgets.

        Returns:
            (list)
        """
        if ui is None or isinstance(ui, str):
            ui = self.get_ui(ui)

        typ = "derived_type" if derived_type else "type"
        return [w for w in ui.widgets if getattr(w, typ) in Iter.makeList(types)]

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
                for u in self._loadedUi.values()
                for w in u.widgets
                if w.get_slot() == method
            ),
            None,
        )

    def get_method(self, ui, widget=None):
        """Get the method(s) associated with the given ui / widget.

        Parameters:
            ui (str/obj): The ui name, or ui object. ie. 'polygons' or <polygons>
            widget (str/obj): widget, widget's objectName, or method name.

        Returns:
            if widget: corresponding method object to given widget.
            else: all of the methods associated to the given ui name as a list.

        Example:
            sb.get_slot('polygons', <b022>)() #call method <b022> of the 'polygons' class
        """
        if ui is None or isinstance(ui, str):
            ui = self.get_ui(ui)

        if widget is None:  # get all methods for the given ui name.
            return [w.get_slot() for w in ui.widgets]

        elif isinstance(widget, str):
            return next(
                iter(
                    w.get_slot() for w in ui.widgets if w.get_slot().__name__ == widget
                ),
                None,
            )

        elif not widget in ui._widgets:
            self.init_widgets(ui, widget)

        return next(
            iter(w.get_slot() for w in ui.widgets if w.get_slot() == widget.get_slot()),
            None,
        )

    def get_signals(self, widget, d=True, exc=[]):
        """Get all signals for a given widget.

        Parameters:
            widget (str/obj): The widget to get signals for.
            d (bool): Return signals from all derived classes instead of just the given widget class.
                    ex. get: QObject, QWidget, QAbstractButton, QPushButton signals from 'QPushButton'
            exc (list): Exclude any classes in this list. ex. exc=[QtCore.QObject, 'QWidget']

        Returns:
            (list)

        Example: get_signals(QtWidgets.QPushButton)
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
        signals = []
        clss = source if isinstance(source, type) else type(source)
        signal = type(QtCore.Signal())
        for subcls in clss.mro():
            clsname = f"{subcls.__module__}.{subcls.__name__}"
            for k, v in sorted(vars(subcls).items()):
                if isinstance(v, signal):
                    if (not d and clsname != clss.__name__) or (
                        exc and (clss in exc or clss.__name__ in exc)
                    ):  # if signal is from parent class QAbstractButton and given widget is QPushButton:
                        continue
                    signals.append(k)
        return signals

    def get_default_signals(self, widget):
        """Get the default signals for a given widget type.

        Parameters:
            widgetType (str): Widget class name. ie. 'QPushButton'

        Returns:
            (str) signal ie. 'released'
        """
        signals = []
        try:  # if the widget type has a default signal assigned in the signals dict; get the signal.
            signalTypes = self.default_signals[widget.derived_type]
            for s in Iter.makeList(signalTypes):  # assure 'signalTypes' is a list.
                signal = getattr(widget, s, None)
                signals.append(signal)

        except KeyError:
            pass
        return signals

    def connect_slots(self, ui, widgets=None):
        """Connects the signals to their respective slots for the widgets of the given ui.

        This function ensures that existing signal-slot connections are not repeated.
        If a connection already exists, it is not made again.

        Parameters:
            ui (QWidget): The dynamic UI object containing widgets.
            widgets (Iterable[QtWidgets.QWidget], optional): A specific set of widgets for which
                to connect slots. If not provided, all widgets from the ui are used.

        Raises:
            ValueError: If ui is not an instance of QWidget.

        Side effect:
            If successful, sets `ui.is_connected` to True indicating that
            the slots for the UI's widgets are connected.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Incorrect datatype: {type(ui)}")

        if widgets is None:
            if ui.is_connected:
                return
            widgets = ui.widgets

        for widget in Iter.makeList(widgets):
            slot = widget.get_slot()
            if slot:
                # Get signals from slot decorator, or default signals if not present
                signals = getattr(
                    slot, "signals", [self.default_signals.get(widget.derived_type)]
                )
                for signal_name in signals:
                    signal = getattr(widget, signal_name, None)
                    if signal:
                        if slot not in self._connected_slots[signal]:
                            signal.connect(slot)
                            self._connected_slots[signal].append(slot)
                    elif signal_name in self.default_signals:
                        signal = getattr(
                            widget, self.default_signals[signal_name], None
                        )
                        if signal:
                            signal.connect(
                                lambda *args, w=widget: self._wgtHistory.append(w)
                            )
        ui.is_connected = True

    def disconnect_slots(self, ui, widgets=None):
        """Disconnects the signals from their respective slots for the widgets of the given ui.

        Only disconnects the slots that are connected via `connect_slots`.

        Parameters:
            ui (QWidget): The dynamic UI object containing widgets.
            widgets (Iterable[QWidget], optional): A specific set of widgets for which
                to disconnect slots. If not provided, all widgets from the ui are used.

        Raises:
            ValueError: If ui is not an instance of QWidget.

        Side effect:
            If successful, sets `ui.is_connected` to False indicating that
            the slots for the UI's widgets are disconnected.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Incorrect datatype: {type(ui)}")

        if widgets is None:
            if not ui.is_connected:
                return
            widgets = ui.widgets

        for widget in Iter.makeList(widgets):
            slot = widget.get_slot()
            if slot:
                signals = [signal for signal in widget.signals if signal is not None]
                for signal in signals:
                    if slot in self._connected_slots[signal]:
                        signal.disconnect(slot)
                        self._connected_slots[signal].remove(slot)
        ui.is_connected = False

    def connect_multi(self, widgets, signals, slots, clss=None):
        """Connect multiple signals to multiple slots at once.

        Parameters:
            widgets (str/obj/list): ie. 'chk000-2' or [tb.ctxMenu.chk000, tb.ctxMenu.chk001]
            signals (str/list): ie. 'toggled' or ['toggled']
            slots (obj/list): ie. self.cmb002 or [self.cmb002]
            clss (obj/list): if the widgets arg is given as a string, then the class it belongs to can be explicitly given.
                    else, the current ui will be used.
        Example:
            connect_('chk000-2', 'toggled', self.cmb002, tb.ctxMenu)
            connect_([tb.ctxMenu.chk000, tb.ctxMenu.chk001], 'toggled', self.cmb002)
            connect_(tb.ctxMenu.chk015, 'toggled',
            [lambda state: self.rigging.tb004.setText('Unlock Transforms' if state else 'Lock Transforms'),
            lambda state: self.rigging_submenu.tb004.setText('Unlock Transforms' if state else 'Lock Transforms')])
        """
        if isinstance(widgets, (str)):
            try:
                widgets = self.get_widgets_from_str(
                    clss, widgets, suppress_error=True
                )  # get_widgets_from_str returns a widget list from a string of object_names.
            except Exception as error:
                widgets = self.get_widgets_from_str(
                    self.get_current_ui(), widgets, suppress_error=True
                )

        # if the variables are not of a list type; convert them.
        widgets = Iter.makeList(widgets)
        signals = Iter.makeList(signals)
        slots = Iter.makeList(slots)

        for widget in widgets:
            for signal in signals:
                signal = getattr(widget, signal)
                for slot in slots:
                    signal.connect(slot)

    def sync_all_widgets(self, *uis, **kwargs):
        """Set sync connections for all widgets of the given UI objects.

        Parameters:
            *uis: A tuple of previously loaded dynamic UI objects to sync widgets among.
        """
        for i, ui1 in enumerate(uis):
            for ui2 in uis[i + 1 :]:
                for w1 in ui1.widgets:
                    try:
                        w2 = self.get_widget(w1.name, ui2)
                    except AttributeError:
                        continue

                    pair_id = hash((w1, w2))
                    if pair_id in self._synced_pairs:
                        continue

                    self.sync_widgets(w1, w2, **kwargs)

    def sync_widgets(self, w1, w2, **kwargs):
        """Set the initial signal connections that will call the _sync_attributes function on state changes.

        Parameters:
            w1 (obj): The first widget to sync.
            w2 (obj): The second widget to sync.
            kwargs: The attribute(s) to sync as keyword arguments.
        """
        try:  # get the default signal for the given widget.
            signals1 = self.get_default_signals(w1)
            signals2 = self.get_default_signals(w2)

            # set sync connections for each of the widgets signals.
            for s1, s2 in zip(signals1, signals2):
                s1.connect(lambda: self._sync_attributes(w1, w2, **kwargs))
                s2.connect(lambda: self._sync_attributes(w2, w1, **kwargs))

            pair_id = hash((w1, w2))
            self._synced_pairs.add(pair_id)

        except (AttributeError, KeyError) as error:
            return

    attributesGetSet = {
        "value": "setValue",
        "text": "setText",
        "icon": "setIcon",
        "checkState": "setCheckState",
        "isChecked": "setChecked",
        "isDisabled": "setDisabled",
    }

    def _sync_attributes(self, frm, to, attributes=[]):
        """Sync the given attributes between the two given widgets.
        If a widget does not have an attribute it will be silently skipped.

        Parameters:
            frm (obj): The widget to transfer attribute values from.
            to (obj): The widget to transfer attribute values to.
            attributes (str/list)(dict): The attribute(s) to sync. ie. a setter attribute 'setChecked' or a dict containing getter:setter pairs. ie. {'isChecked':'setChecked'}
        """
        if not attributes:
            attributes = self.attributesGetSet

        elif not isinstance(attributes, dict):
            attributes = {
                next(
                    (k for k, v in self.attributesGetSet.items() if v == i), None
                ): i  # construct a gettr setter pair dict using only the given setter values.
                for i in Iter.makeList(attributes)
            }

        _attributes = {}
        for gettr, settr in attributes.items():
            try:
                _attributes[settr] = getattr(frm, gettr)()
            except AttributeError:
                pass

        for (
            attr,
            value,
        ) in _attributes.items():  # set the second widget's attributes from the first.
            try:
                getattr(to, attr)(value)
            except AttributeError:
                pass

    def set_widget_attrs(self, *args, **kwargs):
        """Set multiple properties, for multiple widgets, on multiple ui's at once.

        Parameters:
            *args = arg [0] (str) String of object_names. - object_names separated by ',' ie. 'b000-12,b022'
                            arg [1:] dynamic ui object/s.  If no ui's are given, then the parent and child uis will be used.
            *kwargs = keyword: - the property to modify. ex. setText, setValue, setEnabled, setDisabled, setVisible, setHidden
                            value: - intended value.
        Example:
            set_widget_attrs('chk003', <ui1>, <ui2>, setText='Un-Crease')
        """
        if not args[1:]:
            relatives = self.get_ui_relatives(self.get_current_ui())
            args = args + relatives

        for ui in args[1:]:
            widgets = self.get_widgets_from_str(
                ui, args[0]
            )  # get_widgets_from_str returns a widget list from a string of object_names.
            for property_, value in kwargs.items():
                [
                    getattr(w, property_)(value) for w in widgets
                ]  # set the property state for each widget in the list.

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

    @classmethod
    def get_widgets_from_str(cls, ui, name_string, suppress_error=True):
        """Get a list of corresponding widgets from a single shorthand formatted string.
        ie. 's000,b002,cmb011-15' would return object list: [<s000>, <b002>, <cmb011>, <cmb012>, <cmb013>, <cmb014>, <cmb015>]

        Parameters:
            ui (QWidget): A previously loaded dynamic ui object.
            name_string (str): Widget object names separated by ','. ie. 's000,b004-7'. b004-7 specifies buttons b004-b007.
            suppress_error (bool): Print an error message to the console if a widget is not found.

        Returns:
            (list)

        Example:
            get_widgets_from_str(<ui>, 's000,b002,cmb011-15')
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Incorrect datatype: {type(ui)}")

        widgets = []
        for n in cls.unpack_names(name_string):
            try:
                w = getattr(ui, n)
                widgets.append(w)
            except AttributeError:
                if not suppress_error:
                    logging.info(traceback.format_exc())

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
    def resize_and_center_widget(widget, padding_x=30, padding_y=6):
        """Adjust the given widget's size to fit contents and re-center.

        Parameters:
            widget (obj): The widget to resize.
            padding_x (int): Any additional width to be applied.
            padding_y (int): Any additional height to be applied.
        """
        p1 = widget.rect().center()
        widget.resize(
            widget.sizeHint().width() + padding_x,
            widget.sizeHint().height() + padding_y,
        )
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

    def toggle_widgets(self, *args, **kwargs):
        """Set multiple boolean properties, for multiple widgets, on multiple ui's at once.

        Parameters:
            *args = dynamic ui object/s. If no ui's are given, then the current UI will be used.
            *kwargs = keyword: - the property to modify. ex. setChecked, setUnChecked, setEnabled, setDisabled, setVisible, setHidden
                                    value: string of object_names - object_names separated by ',' ie. 'b000-12,b022'
        Example:
            toggle_widgets(<ui1>, <ui2>, setDisabled='b000', setUnChecked='chk009-12', setVisible='b015,b017')
        """
        if not args:
            relatives = self.get_ui_relatives(self.get_current_ui())
            args = relatives

        for ui in args:
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
            checkboxes = self.get_widgets_from_str(ui, checkboxes, suppress_error=True)

        prefix = axis = ""
        for chk in checkboxes:
            if chk.isChecked():
                if chk.text() == "-":
                    prefix = "-"
                else:
                    axis = chk.text()
        # logging.info(f"prefix: {prefix} axis: {axis}") #debug
        return prefix + axis  # ie. '-X'

    def gc_protect(self, obj=None, clear=False):
        """Protect the given object from garbage collection.

        Parameters:
            obj (obj/list): The obj(s) to add to the protected list.
            clear (bool): Clear the set before adding any given object(s).

        Returns:
            (list) protected objects.
        """
        if clear:
            self._gcProtect.clear()

        for o in Iter.makeList(obj):
            self._gcProtect.add(o)

        return self._gcProtect

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

    @staticmethod
    def get_top_level_parent(widget, index=-1):
        """Get the parent widget at the top of the hierarchy for the given widget.

        Parameters:
            widget (obj): QWidget
            index (int): Last index is top level.

        Returns:
            (QWidget)
        """
        return self.get_parent_widgets()[index]

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

    def message_box(self, string, message_type="", location="topMiddle", timeout=1):
        """Spawns a message box with the given text.
        Supports HTML formatting.
        Prints a formatted version of the given string to console, stripped of html tags, to the console.

        Parameters:
            message_type (str): The message context type. ex. 'Error', 'Warning', 'Note', 'Result'
            location (str)(point) = move the messagebox to the specified location. Can be given as a qpoint or string value. default is: 'topMiddle'
            timeout (int): time in seconds before the messagebox auto closes.
        """
        if message_type:
            string = f"{message_type.capitalize()}: {string}"

        try:
            self._messageBox.location = location
        except AttributeError:
            self._messageBox = self.MessageBox(self.parent())
            self._messageBox.location = location
        self._messageBox.timeout = timeout

        from re import sub

        # strip everything between '<' and '>' (html tags)
        logging.info(f"# {sub('<.*?>', '', string)}")

        self._messageBox.setText(string)
        self._messageBox.exec_()

    # @classmethod
    # def progress(cls, fn):
    #   '''A decorator for progress_bar.
    #   Does not work with staticmethods.
    #   '''
    #   def wrapper(self, *args, **kwargs):
    #       self.progress_bar(fn(self, *args, **kwargs))
    #   return wrapper

    def progress_bar(self):
        """ """
        try:
            return self._progress_bar

        except AttributeError:
            from widgets.progress_bar import progress_bar

            self._progress_bar = progress_bar(self.parent())

            try:
                self.ui.progress_bar.step1
            except AttributeError:
                pass

            return self._progress_bar

    @staticmethod
    def invert_on_modifier(value):
        """Invert a numerical or boolean value if the alt key is pressed.

        Parameters:
            value (int, float, bool) = The value to invert.

        Returns:
            (int, float, bool)
        """
        modifiers = QtWidgets.QApplication.instance().keyboardModifiers()
        if not modifiers in (
            QtCore.Qt.AltModifier,
            QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier,
        ):
            return value

        if type(value) in (int, float):
            result = abs(value) if value < 0 else -value
        elif type(value) == bool:
            result = True if value else False

        return result


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":

    class MyProject:
        ...

    class MyProjectSlots(MyProject):
        def __init__(self):
            self.sb = self.switchboard()

        @signals("released")
        def MyButtonsObjectName(self):
            print("Button released!")

    sb = Switchboard(slots_location=MyProjectSlots)
    ui = sb.example
    ui.connect_slots()

    print("ui:".ljust(20), ui)
    print("ui name:".ljust(20), ui.name)
    print("ui path:".ljust(20), ui.path)  # The directory path containing the UI file
    print("is current ui:".ljust(20), ui.is_current)
    print("is initialized:".ljust(20), ui.is_initialized)
    print("is connected:".ljust(20), ui.is_connected)
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
            w.type.ljust(15),
            w.derived_type.ljust(15),
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


# def setConnections(self, ui):
#     """Replace any signal connections of a previous ui with the set for the ui of the given name.

#     Parameters:
#         ui (QWidget): A previously loaded dynamic ui object.
#     """
#     if not isinstance(ui, QtWidgets.QWidget):
#         raise ValueError(f"Incorrect datatype: {type(ui)}")

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
# def getDerivedType(
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
#     ui_dir = File.formatPath(filePath, "dir")
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

# def setAttributes(self, obj=None, order=['setVisible'], **kwargs):
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
#           pass; # logging.info(__name__+':','setAttributes:', obj, order, kwargs, error)
