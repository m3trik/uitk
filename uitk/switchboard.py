# !/usr/bin/python
# coding=utf-8
import re
import sys
import inspect
from typing import List, Union, Optional
from xml.etree.ElementTree import ElementTree
from qtpy import QtWidgets, QtCore, QtGui, QtUiTools
import pythontk as ptk

# From this package:
from uitk.file_manager import FileManager
from uitk.widgets.mixins import ConvertMixin
from uitk.widgets.mixins import SwitchboardSlotsMixin
from uitk.widgets.mixins import SwitchboardWidgetMixin
from uitk.widgets.mixins import SwitchboardUtilsMixin


class Switchboard(
    QtUiTools.QUiLoader,
    ptk.HelpMixin,
    ptk.LoggingMixin,
    SwitchboardSlotsMixin,
    SwitchboardWidgetMixin,
    SwitchboardUtilsMixin,
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
    QtUiTools = QtUiTools

    # Use the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    def __init__(
        self,
        parent=None,
        ui_source=None,
        slot_source=None,
        widget_source=None,
        ui_name_delimiters=".",
        log_level: str = "DEBUG",
    ) -> None:
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
            use_weakref=True,
        )  # All loaded ui.
        self.registered_widgets = ptk.NamespaceHandler(
            self,
            "registered_widgets",
            resolver=self._resolve_widget,
            use_weakref=True,
        )  # All registered widgets.

        self.slot_instances = ptk.NamespaceHandler(
            self,
            "slot_instances",
            resolver=self._resolve_slots_instance,
        )  # All slot instances.

        self._current_ui = None
        self._ui_history = []  # Ordered ui history.
        self._slot_history = []  # Previously called slots.
        self._pending_slot_init = {}  # Slots that are pending initialization.
        self._synced_pairs = set()  # Hashed values representing synced widgets.

        self.convert = ConvertMixin()

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        return instance

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

    @staticmethod
    def convert_to_legal_name(name: str) -> str:
        """Convert a name to a legal format by replacing non-alphanumeric characters with underscores.

        Parameters:
            name (str): The name to convert.

        Returns:
            str: The converted name with only alphanumeric characters and underscores.
        """
        if not isinstance(name, str):
            raise ValueError(f"Expected a string, got {type(name)}")

        return re.sub(r"[^0-9a-zA-Z]", "_", name)

    @staticmethod
    def get_base_name(name: str) -> str:
        """Extract a robust, human-readable base name without suffixes or tags.

        Parameters:
            name (str): The name to process.

        Returns:
            str: The base name extracted from the input name.
        """
        if not isinstance(name, str):
            raise ValueError(f"Expected a string, got {type(name)}")

        if not name:
            return ""

        # Remove tags (e.g., myWidget#001 -> myWidget)
        name = name.split("#")[0]

        # Remove trailing digits or underscores (e.g., myWidget_02 -> myWidget)
        name = re.sub(r"[_\d]+$", "", name)

        # Extract leading alphanumeric base with at least one letter
        match = re.search(r"\b[a-zA-Z]\w*", name)
        return match.group() if match else name

    def has_tags(self, ui, tags=None) -> bool:
        """Check if any of the given tag(s) are present in the UI's tags set.
        If no tags are provided, it checks if the UI has any tags at all.

        Parameters:
            ui (QWidget): The UI object to check.
            tags (str/list): The tag(s) to check.

        Returns:
            bool: True if any of the given tags are present in the tags set, False otherwise.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            self.logger.debug(f"Invalid UI type: {type(ui)}. Expected QWidget.")
            return False

        if not hasattr(ui, "tags"):
            self.logger.debug(f"UI '{ui.objectName()}' has no 'tags' attribute.")
            return False

        if tags is None:
            return bool(ui.tags)

        tags_to_check = ptk.make_iterable(tags)
        return any(tag in ui.tags for tag in tags_to_check)

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
    def get_unknown_tags(tag_string, known_tags=["submenu", "startmenu"]):
        """Extracts all tags from a given string that are not known tags.

        Parameters:
            tag_string (str/list): The known tags in which to derive any unknown tags from.

        Returns:
            list: A list of unknown tags extracted from the tag_string.

        Note:
            Known tags are defined for example 'submenu' and 'startmenu'. Any other tag found in the string
            is considered unknown. Tags are expected to be prefixed by a '#' symbol.
        """
        # Join known_tags into a pattern string
        known_tags_list = ptk.make_iterable(known_tags)
        known_tags_pattern = "|".join(known_tags_list)
        unknown_tags = re.findall(f"#(?!{known_tags_pattern})[a-zA-Z0-9]*", tag_string)
        # Remove leading '#' from all tags
        unknown_tags = [tag[1:] for tag in unknown_tags if tag != "#"]
        return unknown_tags

    def clean_tag_string(self, tag_string):
        """Cleans a given tag string by removing unknown tags.

        Parameters:
            tag_string (str): The string from which to remove unknown tags.

        Returns:
            str: The cleaned tag string with unknown tags removed.

        Note:
            This function utilizes the get_unknown_tags function to identify and subsequently
            remove unknown tags from the provided string.
        """
        unknown_tags = self.get_unknown_tags(tag_string)
        # Remove unknown tags from the string
        cleaned_tag_string = re.sub("#" + "|#".join(unknown_tags), "", tag_string)
        return cleaned_tag_string

    @property
    def visible_windows(self) -> set:
        """Return all currently visible MainWindow instances."""
        return {ui for ui in self.loaded_ui.values() if ui.isVisible()}.copy()

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
        ui = self.add_ui(name, widget=loaded_ui, path=ui_filepath)

        self.logger.debug(f"UI '{name}' loaded successfully.")
        return ui

    def _resolve_ui_using_slots(self, attr_name) -> QtWidgets.QWidget:
        if getattr(self, "_resolving_ui", None) == attr_name:
            raise RuntimeError(f"Recursive resolution detected for key: '{attr_name}'")
        self._resolving_ui = attr_name
        try:
            found_slots = self._find_slots_class(attr_name)
            if not found_slots:
                raise AttributeError(f"Slot class '{attr_name}' not found.")

            ui = self.add_ui(name=attr_name)

            # Use slot cache and instance logic
            self.get_slots_instance(ui)

            return ui
        finally:
            self._resolving_ui = None

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

    def _add_existing_wrapped_ui(
        self, window: QtWidgets.QMainWindow, name: Optional[str] = None
    ) -> QtWidgets.QMainWindow:
        """Add an existing MainWindow (already wrapped) to this Switchboard.

        Parameters:
            window (QMainWindow): The existing MainWindow to add.
            name (str, optional): Override name for the UI. Updates window.objectName() if provided.

        Returns:
            QMainWindow: The added window.
        """
        if name:
            window.setObjectName(name)

        if window.objectName() in self.loaded_ui:
            self.logger.warning(
                f"UI '{window.objectName()}' already exists in this Switchboard."
            )
            return self.loaded_ui[window.objectName()]

        self.loaded_ui[window.objectName()] = window

        if not hasattr(window, "_slots"):
            try:
                self.get_slots_instance(window)  # Uses cached or resolves if needed
            except Exception as e:
                self.logger.debug(
                    f"Failed to set slot class for UI '{window.objectName()}': {e}"
                )

        self.logger.debug(f"Added existing wrapped window '{window.objectName()}'.")
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
        """Adds a given QWidget or QMainWindow to the Switchboard wrapped in MainWindow.

        Parameters:
            name (str): Name of the UI. If not given, derived from widget or file path.
            widget (QWidget or QMainWindow, optional): Central widget or MainWindow instance.
            parent (QWidget, optional): Parent widget for the new MainWindow.
            tags (set, optional): Tags for the UI.
            path (str, optional): Associated path.
            overwrite (bool, optional): If True, overwrite existing UI. Defaults to False.
            **kwargs: Additional keyword arguments for MainWindow.

        Returns:
            QMainWindow: Wrapped UI instance.
        """
        if name in self.loaded_ui:
            if not overwrite:
                self.logger.debug(f"UI '{name}' already exists. Returning existing.")
                return self.loaded_ui[name]

            self.logger.debug(f"Overwriting existing UI '{name}'.")
            del self.loaded_ui[name]

        if isinstance(widget, self.registered_widgets.MainWindow):
            return self._add_existing_wrapped_ui(widget, name=name)

        # continue normal wrapping logic
        central_widget = (
            widget.centralWidget()
            if isinstance(widget, QtWidgets.QMainWindow) and widget.centralWidget()
            else widget
        )

        tags = tags or (self._parse_tags(name) if name else None)
        path = ptk.format_path(path, "path") if path else None

        # Parent to the swtichboard parent if not given.
        parent = parent or (
            self.parent() if isinstance(self.parent(), QtWidgets.QMainWindow) else None
        )

        main_window = self.registered_widgets.MainWindow(
            name=name,
            switchboard_instance=self,
            central_widget=central_widget,
            parent=parent,
            tags=tags,
            path=path,
            log_level=self.logger.level,
            **kwargs,
        )
        self.loaded_ui[name] = main_window

        self.logger.debug(
            f"MainWindow Added: Name={main_window.objectName()}, Tags={main_window.tags}, Path={main_window.path}"
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
            history = ptk.filter_list(history, inc, exc, lambda u: u.objectName())

        if index is None:
            return history  # Return entire list if index is None
        else:
            try:
                return history[index]  # Return UI(s) based on the index
            except IndexError:
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
