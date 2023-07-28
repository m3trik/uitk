# !/usr/bin/python
# coding=utf-8
import sys
import logging
from functools import partial
from PySide2 import QtCore, QtWidgets
import pythontk as ptk
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.style_sheet import StyleSheet


class MainWindow(
    QtWidgets.QMainWindow,
    AttributesMixin,
    StyleSheet,
):
    on_show = QtCore.Signal()
    on_hide = QtCore.Signal()
    on_child_added = QtCore.Signal(object)
    on_child_changed = QtCore.Signal(object, object)

    def __init__(
        self,
        switchboard_instance,
        ui_filepath,
        connect_on_show=True,
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
            set_legal_name_attr (bool): If True, sets a switchboard attribute using the UI legal name (provinding there are no conflicts). Defaults to True.
            set_legal_name_no_tags_attr (bool): If True, sets a switchboard attribute using the UI legal name without tags (provinding there are no conflicts). Defaults to False.
            log_level (int): Determines the level of logging messages to print. Defaults to logging.WARNING. Accepts standard Python logging module levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.
            **kwargs: Additional keyword arguments to pass to the MainWindow. ie. setVisible=False

        Signals:
            on_show: Signal that is emitted before the window is shown.
            on_hide: Signal that is emitted before the window is hidden.
            on_child_added: Signal that is emitted when a child widget is added. Provides the added widget as a parameter.
            on_child_changed: Signal that is emitted when a child widget changes. Provides the original and new widget as parameters.

        AttributesMixin:
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
            <UI>.stays_on_top (bool): Keep the window on top of other windows.
            <UI>._deferred: A dictionary of deferred methods.
        """
        super().__init__()

        self._init_logger(log_level)

        self.sb = switchboard_instance
        self.name = self._set_name(ui_filepath, True)
        self.legal_name = self._set_legal_name(self.name, set_legal_name_attr)
        self.legal_name_no_tags = self._set_legal_name_no_tags(
            self.name, set_legal_name_no_tags_attr
        )
        self.path = ptk.format_path(ui_filepath, "path")
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

        self.settings = QtCore.QSettings("uitk", self.name)

        self.set_legal_attribute(self.sb, self.name, self, also_set_original=True)
        self.setAttribute(QtCore.Qt.WA_NoChildEventsForParent, True)
        self.set_attributes(**kwargs)

        self.on_show.connect(
            lambda: self.connect_slots() if self.connect_on_show else None
        )
        self.on_child_changed.connect(self.sb.sync_widget_values)

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

    def __repr__(self):
        """Return the type, filename, and path"""
        return f"<MainWindow " f"name={self.name}, " f"path={self.path}>"

    def __str__(self):
        """Return the filename"""
        return self.name

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
        widget.base_name = self.sb.get_base_name(widget.name)
        widget.type = widget.__class__
        widget.derived_type = ptk.get_derived_type(widget, module="QtWidgets")

        widget.get_slot = lambda w=widget: getattr(
            self.sb.get_slots(w.ui), w.name, None
        )

        widget.init_slot = lambda w=widget: self.init_slot(w)
        widget.call_slot = lambda *args, w=widget, **kwargs: self.call_slot(
            w, *args, **kwargs
        )

        widget.connect_slot = lambda w=widget, s=None: self.sb.connect_slot(s)
        widget.refresh = True
        widget.is_initialized = False
        widget.installEventFilter(self)

        ptk.set_attributes(widget, **kwargs)
        setattr(self, widget.name, widget)
        self.widgets.add(widget)

        self.on_child_added.emit(widget)
        # Connect the on_child_changed signal to the sync_widget_values method
        self.init_child_changed_signal(widget)

        if self.is_connected:
            self.sb.connect_slot(widget)

        # Initialize the widgets children
        for child in widget.findChildren(QtWidgets.QWidget):
            self.init_child(child)

    def init_child_changed_signal(self, widget):
        """Initializes the signal for a given widget that will be emitted when the widget's state changes.

        This method iterates over a dictionary of default signals, which maps widget types to signal names.
        If the widget is an instance of a type in the dictionary, the method checks if the widget has a signal
        with the corresponding name. If it does, the method connects the signal to a slot.

        The slot is a lambda function that emits the `on_child_changed` signal of the parent object with the widget
        and the value emitted by the widget's signal as arguments. If the widget's signal does not emit a value,
        the lambda function does nothing.

        The `on_child_changed` signal can then be connected to a method that will be called whenever the widget's state changes.

        Parameters:
            widget (QtWidgets.QWidget): The widget to initialize the signal for.
        """
        signal_name = self.sb.default_signals.get(widget.derived_type)
        if signal_name:
            # Check if the widget has the signal
            if hasattr(widget, signal_name):
                # Get the signal by its name
                signal = getattr(widget, signal_name)
                # Connect the signal to the slot
                signal.connect(
                    lambda v=None, w=widget: self.on_child_changed.emit(v, w)
                    if v is not None
                    else None
                )

    @property
    def stays_on_top(self):
        """Returns if the window stays on top of all others."""
        return self.windowFlags() & QtCore.Qt.WindowStaysOnTopHint

    @stays_on_top.setter
    def stays_on_top(self, value):
        """Sets the window to stay on top of all others.

        Args:
            value (bool): If True, the window will stay on top of all others.
        """
        if value:
            self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowStaysOnTopHint)

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
        """Sets the name attribute for the object based on the filename of the UI file.

        Parameters:
            file (str): The file path of the UI file.
            set_attr (bool): If True, sets a switchboard attribute using the name. Defaults to False.

        Returns:
            str: The name attribute.
        """
        name = ptk.format_path(file, "name")
        if set_attr:
            setattr(self.sb, name, self)
        return name

    def _set_legal_name(self, name, set_attr=False) -> str:
        """Sets the legal name attribute for the object based on the name of the UI file.

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
        """Sets the legal name without tags attribute for the object based on the name of the UI file.

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
        """Parse tags from the file name and return a set of tags.

        Parameters:
            name (str): The name to parse tags from.

        Returns:
            set: A set of tags parsed from the name.
        """
        parts = name.split("#")
        return set(parts[1:]) if len(parts) > 1 else set()

    def has_tag(self, tag_str):
        """Check if any of the given tags, separated by '|', are present in the tags set.

        Parameters:
            tag_str (str): The tags to check, separated by '|'.

        Returns:
            bool: True if any of the given tags are present in the tags set, False otherwise.
        """
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
        """Defer execution of a function until after window is shown. The function is added to a dictionary of deferred
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

    def init_slot(self, widget):
        """Only calls the slot init if widget.refresh is True. widget.refresh defaults to True on first call."""
        slots = self.sb.get_slots(self)
        slot_init = getattr(slots, f"{widget.name}_init", None)

        if slot_init and widget.refresh:
            widget.refresh = False  # Default to False before calling init where you can choose to set refresh to True.
            slot_init(widget)

    def call_slot(self, widget, *args, **kwargs):
        """ """
        slots = self.sb.get_slots(self)
        slot = getattr(slots, widget.name, None)

        if slot:
            if widget.refresh:
                self.init_slot(widget)
            wrapper = self.sb._create_slot_wrapper(slot, widget)
            wrapper(*args, **kwargs)

    def eventFilter(self, widget, event):
        """Filter out specific events related to the widget."""
        if event.type() == QtCore.QEvent.ChildPolished:
            child = event.child()
            if isinstance(child, QtWidgets.QWidget):
                self.init_child(child)

        elif event.type() == QtCore.QEvent.Show:
            if widget is not self:
                for relative in self.sb.get_ui_relatives(
                    widget.ui, exact=True, upstream=True, downstream=True
                ):
                    if widget.name:
                        rel_widget = getattr(relative, widget.name, None)
                        if rel_widget is not None:
                            rel_widget.init_slot()

                if not widget.is_initialized:
                    self.sb.restore_widget_state(widget)
                    widget.is_initialized = True

        return super().eventFilter(widget, event)

    def setVisible(self, visible):
        """Reimplement setVisible to prevent window from being hidden when prevent_hide is True."""
        if self.prevent_hide and not visible:
            return
        super().setVisible(visible)

    def show(self, app_exec=False):
        """Show the MainWindow.

        Parameters:
            app_exec (bool, optional): Execute the given PySide2 application, display its window, wait for user input,
                    and then terminate the program with a status code returned from the application. Defaults to False.
        Raises:
            SystemExit: Raised if the exit code returned from the PySide2 application is not -1.
        """
        super().show()
        self.trigger_deferred()
        if app_exec:
            exit_code = self.sb.app.exec_()
            if exit_code != -1:
                sys.exit(exit_code)

    def showEvent(self, event):
        """Reimplement showEvent to emit custom signal when window is shown."""
        self.activateWindow()
        self.setWindowFlags(self.windowFlags())
        self.on_show.emit()
        super().showEvent(event)
        self.is_initialized = True

    def hideEvent(self, event):
        """Reimplement hideEvent to emit custom signal when window is hidden."""
        self.on_hide.emit()
        super().hideEvent(event)

    def closeEvent(self, event):
        """Reimplement closeEvent to prevent window from being hidden when prevent_hide is True."""
        self.settings.sync()
        super().closeEvent(event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    from uitk import Switchboard, example

    class MyProject:
        ...

    class MySlots(MyProject):
        def __init__(self):
            self.sb = self.switchboard()

        def MyButtonsObjectName(self):
            print("Button clicked!")

    # Use the package to define the ui_location, and explicity pass the slots class.
    sb = Switchboard(ui_location=example, slots_location=MySlots)
    print("sb.ui_location:", sb.ui_location)
    print("sb.ui_files:", sb.ui_files)
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
