# !/usr/bin/python
# coding=utf-8
"""Dynamic UI loader and event handler for PyQt/PySide applications.

The Switchboard is the core of UITK, providing automatic loading of Qt Designer
UI files, dynamic signal-slot connections based on naming conventions, and
integration of custom widget classes.

Classes:
    Switchboard: Main class for loading UIs and connecting slots.

Key Features:
    - Load .ui files and access them as attributes (sb.my_ui)
    - Automatic slot connection via naming convention (widget 'btn_save' -> method 'btn_save')
    - Support for _init suffix methods for widget initialization
    - Custom widget class registration and promotion
    - Theme and style management

Example:
    Basic usage::

        from uitk import Switchboard

        class MySlots:
            def __init__(self, switchboard):
                self.sb = switchboard

            def btn_save(self, widget=None):
                print("Save clicked")

            def btn_save_init(self, widget):
                widget.setText("Save File")

        sb = Switchboard(ui_source="app.ui", slot_source=MySlots)
        ui = sb.app
        ui.show(app_exec=True)
"""
import re
import sys
import inspect
from typing import List, Union, Optional
from xml.etree.ElementTree import ElementTree
from qtpy import QtWidgets, QtCore, QtGui, QtUiTools
import pythontk as ptk

# From this package:
from uitk.widgets.mixins import SwitchboardSlotsMixin
from uitk.widgets.mixins import SwitchboardWidgetMixin
from uitk.widgets.mixins import SwitchboardUtilsMixin
from uitk.widgets.mixins import SwitchboardNameMixin
from uitk.file_manager import FileManager
from uitk.widgets.mixins import ConvertMixin


class Switchboard(
    QtUiTools.QUiLoader,
    ptk.HelpMixin,
    ptk.LoggingMixin,
    SwitchboardSlotsMixin,
    SwitchboardWidgetMixin,
    SwitchboardUtilsMixin,
    SwitchboardNameMixin,
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
        icon_source=None,
        tag_delimiter: str = None,
        ui_name_delimiters: str = None,
        log_level: str = "warning",
    ) -> None:
        super().__init__(parent)
        """ """
        self.logger.setLevel(log_level)

        self.tag_delimiter = tag_delimiter or self.TAG_DELIMITER
        self.ui_name_delimiters = ui_name_delimiters or self.UI_NAME_DELIMITER
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
            exc_files="*_ui.py",
            base_dir=base_dir,
        )
        self.registry.create(
            "widget_registry",
            widget_source,
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
            exc_files="*_ui.py",
            base_dir=base_dir,
        )
        self.registry.create(
            "icon_registry",
            icon_source,
            inc_files=["*.svg", "*.png", "*.jpg", "*.jpeg", "*.bmp", "*.ico"],
            base_dir=base_dir,
        )

        # Include this package's widgets
        self.registry.widget_registry.extend("widgets", base_dir=self)

        # Include this package's default icons
        self.registry.icon_registry.extend("icons", base_dir=self)

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

        self._current_ui = None
        self._ui_history = []  # Ordered ui history.
        self._slot_history = []  # Previously called slots.
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

    def register(
        self,
        ui_location=None,
        slot_location=None,
        widget_location=None,
        base_dir=1,
        validate=0,
    ):
        """Add new locations to the Switchboard."""
        if ui_location and not self.registry.contains_location(
            ui_location, "ui_registry"
        ):
            if self.registry.resolve_path(
                ui_location, base_dir=base_dir, validate=validate, path_type="UI"
            ):
                self.registry.ui_registry.extend(ui_location, base_dir=base_dir)
                self.logger.debug(f"[register] UI location added: {ui_location}")

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
                self.logger.debug(f"[register] Slot location added: {slot_path}")

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
                self.logger.debug(
                    f"[register] Widget location added: {widget_location}"
                )

    def load_all_ui(self) -> list:
        """Extends the 'load_ui' method to load all UI from a given path.

        Returns:
            (list) QWidget(s).
        """
        filepaths = self.registry.ui_registry.get("filepath")
        return [self.load_ui(f) for f in filepaths]

    def load_ui(self, file: str) -> QtWidgets.QMainWindow:
        """Loads a UI from the given path to the UI file and adds it to the switchboard."""
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

        loaded_ui = self.load(file)
        name = ptk.format_path(file, "name")
        self.logger.debug(f"[{name}] UI loaded via QUiLoader from {file}")
        return loaded_ui

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

        tags = tags or (self.get_tags_from_name(name) if name else None)
        path = ptk.format_path(path, "path") if path else None

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
        """Get UIs related to the given UI, based on hierarchical name matching.

        Parameters:
            ui (str or QWidget): Target UI name or object.
            upstream (bool): Include higher-level ancestors.
            exact (bool): Include only exact matches.
            downstream (bool): Include children/submenus.
            reverse (bool): Reverse order of matches.

        Returns:
            list[str] or list[QWidget]: Matching UI names or loaded QWidget objects,
                                        depending on input type.
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

        # --- Step 2: Normalize all UI filenames into canonical names ---
        ui_filenames = self.registry.ui_registry.get("filename") or []

        # --- Step 3: Match based on hierarchy ---
        matched_names = ptk.get_matching_hierarchy_items(
            hierarchy_items=ui_filenames,
            target=target_name,
            upstream=upstream,
            exact=exact,
            downstream=downstream,
            reverse=reverse,
            delimiters=[self.ui_name_delimiters, self.tag_delimiter],
        )

        # --- Step 4: Return matching names or UI instances ---
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
