# !/usr/bin/python
# coding=utf-8
import sys
import re
import logging
from functools import partial
from PySide2 import QtCore, QtGui, QtWidgets
from pythontk import File
from uitk.widgets.stateManager import StateManager
from uitk.widgets.attributes import Attributes
from uitk.widgets.docking import Docking
from uitk.widgets.styleSheet import StyleSheet


class MainWindow(QtWidgets.QMainWindow, StateManager, Attributes, StyleSheet):
    on_show = QtCore.Signal()

    def __init__(
        self,
        switchboard_instance,
        ui_filepath,
        connect_on_show=True,
        set_name_attr=True,
        set_legal_name_attr=True,
        set_legal_name_no_tags_attr=False,
        suppress_warnings=False,
        **kwargs,
    ):
        """Represents a main window in a GUI application.
        Inherits from QtWidgets.QMainWindow class, providing additional functionality for
        managing user interface (UI) elements.

        Parameters:
            switchboard_instance (obj): An instance of the switchboard class.
            ui_filepath (str): The full path to a UI file.
            connect_on_show (bool): While True, the UI will be set as current and connections established when it becomes visible.
            set_name_attr (bool): If True, sets the name attribute for the object. Defaults to True.
            set_legal_name_attr (bool): If True, sets the legal name attribute for the object (provinding there are no conflicts). Defaults to True.
            set_legal_name_no_tags_attr (bool): If True, sets the legal name without tags attribute for the object (provinding there are no conflicts). Defaults to False.
            suppress_warnings (bool): Suppress legal name warning messages if True.
            **kwargs: Additional keyword arguments to pass to the MainWindow. ie. setVisible=False

        Attributes:
            on_show: A signal that is emitted when the window is shown.
            sb: An instance of the switchboard class.

        Properties:
            <UI>.name (str): The UI filename.
            <UI>.path (str): The directory path containing the UI file.
            <UI>.is_current_ui (bool): True if the UI is set as current.
            <UI>.is_initialized (bool): True after the UI is first shown.
            <UI>.is_connected (bool): True if the UI is connected to its slots.
            <UI>.connect_on_show: Establish connections when the UI becomes visible.
            <UI>.prevent_hide (bool): While True, the hide method is disabled.
            <UI>.widgets (list): All the widgets of the UI.
            <UI>.slots (obj): The slots class instance.
            <UI>._widgets: All the widgets of the UI.
            <UI>._deferred: A dictionary of deferred methods.
        """
        super().__init__()

        self.suppress_warnings = suppress_warnings

        self.sb = switchboard_instance
        self.name = self._set_name_attr(ui_filepath, set_name_attr)
        self.legal_name = self._set_legal_name_attr(self.name, set_legal_name_attr)
        self.legal_name_no_tags = self._set_legal_name_no_tags_attr(
            self.name, set_legal_name_no_tags_attr
        )
        self.path = File.formatPath(ui_filepath, "path")
        self.tags = self._parse_tags(self.name)
        self.is_initialized = False
        self.is_connected = False
        self.prevent_hide = False
        self.connect_on_show = connect_on_show
        self._widgets = set()
        self._deferred = {}

        ui = self.sb.load(ui_filepath)

        self.setCentralWidget(ui.centralWidget())
        self.transfer_properties(ui, self)

        flags = QtCore.Qt.CustomizeWindowHint
        flags &= ~QtCore.Qt.WindowTitleHint
        flags &= ~QtCore.Qt.WindowSystemMenuHint
        flags &= ~QtCore.Qt.WindowMinMaxButtonsHint
        flags |= ui.windowFlags()
        self.setWindowFlags(flags)

        self.set_legal_attribute(self.sb, self.name, self, also_set_original=True)
        self.setAttribute(QtCore.Qt.WA_NoChildEventsForParent, True)
        self.set_attributes(**kwargs)

        self.docking = Docking(self)
        self.docking.docking_enabled = True

        self.set_style()  # Set the stylesheet
        self.load_widget_states()  # Load widget states

        self.on_show.connect(self._connect_on_show)

    def __getattr__(self, attr_name):
        """Looks for the widget in the parent class.
        If found, the widget is initialized and returned, else an AttributeError is raised.

        Parameters:
            attr_name (str): the name of the attribute being accessed.

        Returns:
            () The value of the widget attribute if it exists, or raises an AttributeError
            if the attribute cannot be found.

        Raises:
            AttributeError: if the attribute does not exist in the current instance
            or the parent class.
        """
        found_widget = self.sb._get_widget_from_ui(self, attr_name)
        if found_widget:
            self.sb.init_widgets(self, found_widget)
            return found_widget

        raise AttributeError(
            f"{self.__class__.__name__} has no attribute `{attr_name}`"
        )

    @property
    def widgets(self):
        """Returns a list of the widgets in the widget's widget dictionary or initializes the widget dictionary and returns all the widgets found in the widget's children.

        Returns:
            set: A set of the widgets in the widget's widget dictionary or all the widgets found in the widget's children.
        """
        return self._widgets or self.sb.init_widgets(
            self, self.findChildren(QtWidgets.QWidget), return_all_widgets=True
        )

    @property
    def slots(self):
        """Returns a list of the slots connected to the widget's signals.

        Returns:
            list: A list of the slots connected to the widget's signals.
        """
        return self.sb.get_slots(self)

    @property
    def is_stacked_widget(self):
        """ """
        return isinstance(self.parent(), QtWidgets.QStackedWidget)

    @property
    def is_current_ui(self):
        """Returns True if the widget is the currently active UI, False otherwise."""
        return self == self.sb.get_current_ui()

    def set_as_current(self):
        """Sets the widget as the currently active UI."""
        self.sb.set_current_ui(self)

    def _set_name_attr(self, file, set_attr=False) -> str:
        """Sets name attribute for the object.

        Parameters:
            file (str): The file path.
            set_attr (bool): If True, sets the name attribute. Defaults to False.

        Returns:
            str: The name attribute.
        """
        name = File.formatPath(file, "name")
        if set_attr:
            setattr(self.sb, name, self)
        return name

    def _set_legal_name_attr(self, name, set_attr=False) -> str:
        """Sets legal name attribute for the object.

        Parameters:
            name (str): The name to generate the legal name from.
            set_attr (bool): If True, sets the legal name attribute. Defaults to False.

        Returns:
            str: The legal name attribute.
        """
        legal_name = self.sb.convert_to_legal_name(name)

        if set_attr:
            if legal_name and name != legal_name:
                if legal_name in self.sb.ui_files:
                    if not self.suppress_warnings:
                        logging.warning(
                            f"Legal name '{legal_name}' already exists. Attribute not set."
                        )
                else:
                    setattr(self.sb, legal_name, self)
        return legal_name

    def _set_legal_name_no_tags_attr(self, name, set_attr=False) -> str:
        """Sets legal name without tags attribute for the object.

        Parameters:
            name (str): The name to generate the legal name without tags from.
            set_attr (bool): If True, sets the legal name without tags attribute. Defaults to False.

        Returns:
            str: The legal name without tags attribute.
        """
        name_without_tags = "".join(name.split("#")[0])
        legal_name_notags = self.sb.convert_to_legal_name(name_without_tags)

        if set_attr:
            if legal_name_notags and name != legal_name_notags:
                if legal_name_notags in self.sb.ui_files:
                    if not self.suppress_warnings:
                        logging.warning(
                            f"Legal name without tags '{legal_name_notags}' already exists. Attribute not set."
                        )
                else:
                    setattr(self.sb, legal_name_notags, self)
        return legal_name_notags

    @staticmethod
    def _parse_tags(name):
        """Parse tags from the file name and return a set of tags."""
        parts = name.split("#")
        return set(parts[1:]) if len(parts) > 1 else set()

    def has_tag(self, tag_str):
        """Check if any of the given tags, separated by '|', are present in the tags set."""
        tags_to_check = tag_str.split("|")
        return any(tag in self.tags for tag in tags_to_check)

    def connect_slots(self):
        """Connects the widget's signals to their respective slots."""
        if not self.is_connected:
            self.sb.connect_slots(self)

    def _connect_on_show(self):
        """Connects the widget's signals to their respective slots when the widget becomes visible."""
        if self.connect_on_show:
            self.connect_slots()

    def on_child_polished(self, w):
        """Called after a child widget is polished. Initializes the widget dictionary with the child widget and connects its signals to their respective slots if the widget is connected.

        Parameters:
            w (QWidget): The polished child widget.
        """
        if w not in self._widgets:
            self.sb.init_widgets(self, w)
            self.trigger_deferred()
            if self.is_connected:
                self.sb.connect_slots(self, w)

    def trigger_deferred(self):
        """Executes all deferred methods, in priority order. Any arguments passed to the deferred functions
        will be applied at this point. Once all deferred methods have executed, the dictionary is cleared.
        """
        for priority in sorted(self._deferred):
            for method in self._deferred[priority]:
                method()
        self._deferred.clear()

    def defer(self, func, *args, priority=0):
        """Defer execution of a function until later. The function is added to a dictionary of deferred
        methods, with a specified priority. Lower priority values will be executed before higher ones.

        Parameters:
            func (function): The function to defer.
            *args: Any arguments to be passed to the function.
            priority (int, optional): The priority of the deferred method. Lower values will be executed
                            first. Defaults to 0.
        """
        method = partial(func, *args)
        if priority in self._deferred:
            self._deferred[priority] += (method,)
        else:
            self._deferred[priority] = (method,)

    def event(self, event):
        """Handles events that are sent to the widget.

        Parameters:
            event (QtCore.QEvent): The event that was sent to the widget.

        Returns:
            bool: True if the event was handled, otherwise False.

        Notes:
            This method is called automatically by Qt when an event is sent to the widget.
            If the event is a `QEvent.ChildPolished` event, it calls the `on_child_polished`
            method with the child widget as an argument. Otherwise, it calls the superclass
            implementation of `event`.
        """
        if event.type() == QtCore.QEvent.ChildPolished:
            child = event.child()
            self.on_child_polished(child)
        return super().event(event)

    def setVisible(self, state):
        """Called every time the widget is shown or hidden on screen. If the widget is set to be prevented from hiding, it will not be hidden when state is False.

        Parameters:
            state (bool): Whether the widget is being shown or hidden.
        """
        if state:  # visible
            self.activateWindow()
            self.setWindowFlags(self.windowFlags())
            super().setVisible(True)
            self.on_show.emit()
            self.is_initialized = True

        elif not self.prevent_hide:  # invisible
            super().setVisible(False)

    def show(self, app_exec=False):
        """Show the MainWindow.

        Parameters:
            app_exec (bool, optional): Execute the given PySide2 application, display its window, wait for user input,
                and then terminate the program with a status code returned from the application.
                Defaults to False.
        Raises:
            SystemExit: Raised if the exit code returned from the PySide2 application is not -1.
        """
        super().show()
        if app_exec:
            exit_code = self.sb.app.exec_()
            if exit_code != -1:
                sys.exit(exit_code)


# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from uitk import Switchboard

    class MyProject:
        ...

    class MySlots(MyProject):
        def __init__(self):
            self.sb = self.switchboard()

        def MyButtonsObjectName(self):
            print("Button clicked!")

    sb = Switchboard(slots_location=MySlots)
    mainwindow = MainWindow(sb, sb.ui_files["example"])
    print("sb.example:", mainwindow.sb.example)
    mainwindow.show(app_exec=True)

# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
Promoting a widget in designer to use a custom class:
>   In Qt Designer, select all the widgets you want to replace, 
        then right-click them and select 'Promote to...'. 

>   In the dialog:
        Base Class:     Class from which you inherit. ie. QWidget
        Promoted Class: Name of the class. ie. "MyWidget"
        Header File:    Path of the file (changing the extension .py to .h)  ie. myfolder.mymodule.mywidget.h

>   Then click "Add", "Promote", 
        and you will see the class change from "QWidget" to "MyWidget" in the Object Inspector pane.
"""

# deprecated ---------------------
