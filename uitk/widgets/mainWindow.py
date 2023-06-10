# !/usr/bin/python
# coding=utf-8
import sys
import logging
from functools import partial
from PySide2 import QtCore, QtWidgets
from pythontk import File, listify, get_derived_type, set_attributes
from uitk.widgets.mixins.state_manager import StateManagerMixin
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.style_sheet import StyleSheet


class MainWindow(
    QtWidgets.QMainWindow,
    StateManagerMixin,
    AttributesMixin,
    StyleSheet,
):
    on_show = QtCore.Signal()
    on_widget_added = QtCore.Signal(object)
    on_widget_changed = QtCore.Signal(object, object)

    def __init__(
        self,
        switchboard_instance,
        ui_filepath,
        connect_on_show=True,
        set_name_attr=True,
        set_legal_name_attr=True,
        set_legal_name_no_tags_attr=False,
        log_level=logging.WARNING,
        **kwargs,
    ):
        """Represents a main window in a GUI application.
        Inherits from QtWidgets.QMainWindow class, providing additional functionality for
        managing user interface (UI) elements.

        Parameters:
            switchboard_instance (QUiLoader): An instance of the switchboard class.
            ui_filepath (str): The full path to a UI file.
            connect_on_show (bool): While True, the UI will be set as current and connections established when it becomes visible.
            set_name_attr (bool): If True, sets a switchboard attribute using the UI name. Defaults to True.
            set_legal_name_attr (bool): If True, sets a switchboard attribute using the UI legal name (provinding there are no conflicts). Defaults to True.
            set_legal_name_no_tags_attr (bool): If True, sets a switchboard attribute using the UI legal name without tags (provinding there are no conflicts). Defaults to False.
            log_level (int): Determines the level of logging messages to print. Defaults to logging.WARNING. Accepts standard Python logging module levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.
            **kwargs: Additional keyword arguments to pass to the MainWindow. ie. setVisible=False

        AttributesMixin:
            on_show: A signal that is emitted when the window is shown.
            sb: An instance of the switchboard class.

        Properties:
            <UI>.name (str): The UI filename.
            <UI>.path (str): The directory path containing the UI file.
            <UI>.is_current (bool): True if the UI is set as current.
            <UI>.is_initialized (bool): True after the UI is first shown.
            <UI>.is_connected (bool): True if the UI is connected to its slots.
            <UI>.connect_on_show: Establish connections immediately before the UI becomes visible.
            <UI>.prevent_hide (bool): While True, the hide method is disabled.
            <UI>.widgets (list): All the widgets of the UI.
            <UI>.slots (obj): The slots class instance.
            <UI>._deferred: A dictionary of deferred methods.
        """
        super().__init__()

        self._init_logger(log_level)

        self.sb = switchboard_instance
        self.name = self._set_name(ui_filepath, set_name_attr)
        self.legal_name = self._set_legal_name(self.name, set_legal_name_attr)
        self.legal_name_no_tags = self._set_legal_name_no_tags(
            self.name, set_legal_name_no_tags_attr
        )
        self.path = File.format_path(ui_filepath, "path")
        self.tags = self._parse_tags(self.name)
        self.is_initialized = False
        self.is_connected = False
        self.prevent_hide = False
        self.connect_on_show = connect_on_show
        self.widgets = set()
        self._deferred = {}

        # Install event filter before setting central widget to init children
        self.installEventFilter(self)

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

        # self.load_widget_states()  # Load widget states

        self.on_show.connect(
            lambda: self.connect_slots() if self.connect_on_show else None
        )

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
        if found_widget:  # This is likely never used
            self.init_child(found_widget)
            return found_widget

        raise AttributeError(
            f"{self.__class__.__name__} has no attribute `{attr_name}`"
        )

    def init_child(self, widget, **kwargs):
        """Assign additional attributes to the widget for easier access and better management.

        Parameters:
            widget (obj): A widget that will be added as attributes.
            kwargs (dict): Additional widget attributes as keyword arguments.

        """
        if widget in self.widgets:
            self.logger.info(f"Widget {widget} is already in self.widgets")
            return
        if not isinstance(widget, QtWidgets.QWidget):
            self.logger.info(f"Widget {widget} is not an instance of QtWidgets.QWidget")
            return

        widget.ui = self
        widget.name = widget.objectName()
        widget.type = widget.__class__.__name__
        widget.derived_type = get_derived_type(
            widget, module="QtWidgets", return_name=True
        )
        widget.base_name = self.sb.get_base_name(widget.name)
        widget.get_slot = lambda w=widget: self.sb.get_method_by_name(self, widget.name)
        widget.get_slot_init = lambda w=widget: self.sb.get_method_by_name(
            self, widget.name + "_init"
        )
        widget.refresh = True
        widget.installEventFilter(self)

        set_attributes(widget, **kwargs)
        setattr(self, widget.name, widget)
        self.widgets.add(widget)

        self.init_widget_changed_signal(widget)
        self.on_widget_added.emit(widget)

        if self.is_connected:
            self.sb.connect_slot(widget)

        # Initialize the widgets children
        for child in widget.findChildren(QtWidgets.QWidget):
            self.init_child(child)

    def init_widget_changed_signal(self, widget):
        # Connect the appropriate signal for each type of widget
        if isinstance(widget, QtWidgets.QCheckBox):
            widget.stateChanged.connect(
                lambda state: self.on_widget_changed.emit(widget, state)
            )
            print("emit_widget_changed:", widget)
        elif isinstance(widget, QtWidgets.QRadioButton):
            widget.toggled.connect(
                lambda state: self.on_widget_changed.emit(widget, state)
            )
            print("emit_widget_changed:", widget)
        elif (
            isinstance(widget, QtWidgets.QAbstractSlider)
            or isinstance(widget, QtWidgets.QSpinBox)
            or isinstance(widget, QtWidgets.QDoubleSpinBox)
        ):
            widget.valueChanged.connect(
                lambda value: self.on_widget_changed.emit(widget, value)
            )
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.textChanged.connect(
                lambda text: self.on_widget_changed.emit(widget, text)
            )
        elif isinstance(widget, QtWidgets.QComboBox):
            widget.currentIndexChanged.connect(
                lambda index: self.on_widget_changed.emit(widget, index)
            )
            print("emit_widget_changed:", widget)

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
    def is_current(self):
        """Returns True if the widget is the currently active UI, False otherwise."""
        return self == self.sb.get_current_ui()

    def set_as_current(self):
        """Sets the widget as the currently active UI."""
        self.sb.set_current_ui(self)

    def _set_name(self, file, set_attr=False) -> str:
        """Sets name attribute for the object.

        Parameters:
            file (str): The file path.
            set_attr (bool): If True, sets a switchboard attribute using the name. Defaults to False.

        Returns:
            str: The name attribute.
        """
        name = File.format_path(file, "name")
        if set_attr:
            setattr(self.sb, name, self)
        return name

    def _set_legal_name(self, name, set_attr=False) -> str:
        """Sets legal name attribute for the object.

        Parameters:
            name (str): The name to generate the legal name from.
            set_attr (bool): If True, sets a switchboard attribute using the legal name. Defaults to False.

        Returns:
            str: The legal name attribute.
        """
        legal_name = self.sb.convert_to_legal_name(name)

        if set_attr:
            if legal_name and name != legal_name:
                if legal_name in self.sb.ui_files:
                    self.logger.warning(
                        f"Legal name '{legal_name}' already exists. Attribute not set."
                    )
                else:
                    setattr(self.sb, legal_name, self)
        return legal_name

    def _set_legal_name_no_tags(self, name, set_attr=False) -> str:
        """Sets legal name without tags attribute for the object.

        Parameters:
            name (str): The name to generate the legal name without tags from.
            set_attr (bool): If True, sets a switchboard attribute using the legal name without tags. Defaults to False.

        Returns:
            str: The legal name without tags attribute.
        """
        name_no_tags = "".join(name.split("#")[0])
        legal_name_no_tags = self.sb.convert_to_legal_name(name_no_tags)

        if set_attr:
            if legal_name_no_tags and name != legal_name_no_tags:
                if legal_name_no_tags in self.sb.ui_files:
                    self.logger.warning(
                        f"Legal name without tags '{legal_name_no_tags}' already exists. Attribute not set."
                    )
                else:
                    setattr(self.sb, legal_name_no_tags, self)
        return legal_name_no_tags

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
        self.sb.connect_slots(self)

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

    def eventFilter(self, widget, event):
        """Filter out specific events related to the widget."""
        if event.type() == QtCore.QEvent.ChildPolished:
            child = event.child()
            if isinstance(child, QtWidgets.QWidget):
                self.init_child(child)

        elif event.type() == QtCore.QEvent.Show:
            if widget is not self:
                slot_init = widget.get_slot_init()
                if slot_init and widget.refresh:
                    widget.refresh = False  # Default to False before calling init where you can choose to set refresh to True.
                    slot_init(widget)

        return super().eventFilter(widget, event)

    def setVisible(self, state):
        """Called every time the widget is shown or hidden on screen.
        If the widget is set to be prevented from hiding, it will not be hidden when state is False.

        Parameters:
            state (bool): Whether the widget is being shown or hidden.
        """
        if state:  # visible
            self.activateWindow()
            self.setWindowFlags(self.windowFlags())
            self.on_show.emit()
            self.is_initialized = True
            super().setVisible(True)

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

if __name__ == "__main__":
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
    print("sb.example.widgets:", mainwindow.sb.example.widgets)
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
