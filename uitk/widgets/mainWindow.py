# !/usr/bin/python
# coding=utf-8
import sys
import logging
from typing import Any
from functools import partial
from PySide2 import QtCore, QtWidgets
import pythontk as ptk
from uitk import __package__
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.style_sheet import StyleSheet


class MainWindow(
    QtWidgets.QMainWindow,
    AttributesMixin,
    StyleSheet,
):
    on_show = QtCore.Signal()
    on_hide = QtCore.Signal()
    on_focus_in = QtCore.Signal()
    on_focus_out = QtCore.Signal()
    on_child_added = QtCore.Signal(object)
    on_child_changed = QtCore.Signal(object, object)

    def __init__(
        self,
        switchboard_instance,
        ui_filepath,
        log_level=logging.WARNING,
        **kwargs,
    ):
        """Represents a main window in a GUI application.
        Inherits from QtWidgets.QMainWindow class, providing additional functionality for
        managing user interface (UI) elements.

        Parameters:
            switchboard_instance (QUiLoader): An instance of the switchboard class.
            ui_filepath (str): The full path to a UI file.
            log_level (int): Determines the level of logging messages to print. Defaults to logging.WARNING. Accepts standard Python logging module levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.
            **kwargs: Additional keyword arguments to pass to the MainWindow. ie. setVisible=False

        Signals:
            on_show: Signal that is emitted before the window is shown.
            on_hide: Signal that is emitted before the window is hidden.
            on_child_added: Signal that is emitted when a child widget is added. Provides the added widget as a parameter.
            on_child_changed: Signal that is emitted when a child widget changes. Provides the value and widget as parameters.

        AttributesMixin:
            sb: An instance of the switchboard class.

        Properties:
            <UI>.name (str): The UI filename.
            <UI>.path (str): The directory path containing the UI file.
            <UI>.is_current (bool): True if the UI is set as current.
            <UI>.is_initialized (bool): True after the UI is first shown.
            <UI>.is_connected (bool): True if the UI is connected to its slots.
            <UI>.prevent_hide (bool): While True, the hide method is disabled.
            <UI>.widgets (list): All the widgets of the UI.
            <UI>.slots (obj): The slots class instance.
            <UI>._deferred: A dictionary of deferred methods.
        """
        super().__init__()

        self._init_logger(log_level)

        self.sb = switchboard_instance
        self.name = self._set_name(ui_filepath, True)
        self.legal_name = self._set_legal_name(self.name, True)
        self.legal_name_no_tags = self._set_legal_name_no_tags(self.name, True)
        self.path = ptk.format_path(ui_filepath, "path")
        self.tags = self._parse_tags(self.name)
        self.is_initialized = False
        self.is_connected = False
        self.prevent_hide = False
        self.widgets = set()
        self._deferred = {}

        # Install event filter before setting central widget to init children
        self.installEventFilter(self)

        ui = self.sb.load(ui_filepath)
        self.setCentralWidget(ui.centralWidget())
        self.transfer_widget_properties(ui, self)
        self.setWindowFlags(ui.windowFlags())

        self.settings = QtCore.QSettings(__package__, self.name)

        self.set_legal_attribute(self.sb, self.name, self, also_set_original=True)
        self.set_attributes(WA_NoChildEventsForParent=True, **kwargs)
        self.setFocusPolicy(QtCore.Qt.ClickFocus)

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

    def init_child(self, widget: QtWidgets.QWidget, **kwargs: Any) -> None:
        """Assign additional attributes to the widget for easier access and better management.

        Parameters:
            widget: A widget to be initialized and added as an attribute.
            kwargs: Additional widget attributes as keyword arguments.
        """
        if widget in self.widgets:
            self.logger.info(f"Widget {widget} is already initialized.")
            return

        if not isinstance(widget, QtWidgets.QWidget):
            self.logger.warning(f"Attempted to initialize a non-widget: {widget}.")
            return

        # Initialize widget attributes
        widget.ui = self
        widget.name = widget.objectName()
        widget.base_name = self.sb.get_base_name(widget.name)
        widget.type = type(widget)
        widget.derived_type = ptk.get_derived_type(widget, module="QtWidgets")

        # Lambda functions for widget operations
        widget.get_slot = lambda w=widget: getattr(
            self.sb.get_slot_class(w.ui), w.name, None
        )
        widget.init_slot = lambda *args, w=widget: self.init_slot(w)
        widget.call_slot = lambda *args, w=widget, **kwargs: self.call_slot(
            w, *args, **kwargs
        )
        widget.connect_slot = lambda w=widget, s=None: self.sb.connect_slot(s)

        # Additional widget setup
        widget.refresh = True
        widget.is_initialized = False
        widget.installEventFilter(self)

        # Apply additional attributes from kwargs
        ptk.set_attributes(widget, **kwargs)

        # Register the widget
        setattr(self, widget.name, widget)
        self.widgets.add(widget)

        # Post-initialization actions
        self.on_child_added.emit(widget)
        self.sb.restore_widget_state(widget)
        self.init_child_changed_signal(widget)

        if self.is_connected:
            self.sb.connect_slot(widget)

        # Recursively initialize child widgets
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
    def slots(self):
        """Returns a list of the slots connected to the widget's signals.

        Returns:
            list: A list of the slots connected to the widget's signals.
        """
        return self.sb.get_slot_class(self)

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
                if self.sb.registry.ui_registry.get(filename=legal_name):
                    pass
                    # self.logger.warning(
                    #     f"Legal name '{legal_name}' already exists. Attribute not set."
                    # )
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
                if self.sb.registry.ui_registry.get(filename=legal_name_no_tags):
                    pass
                    # self.logger.warning(
                    #     f"Legal name without tags '{legal_name_no_tags}' already exists. Attribute not set."
                    # )
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

    def has_tags(self, tags):
        """Check if any of the given tag(s) are present in the UI's tags set.

        Parameters:
            tags (str/list): The tag(s) to check.

        Returns:
            bool: True if any of the given tags are present in the tags set, False otherwise.
        """
        tags_to_check = ptk.make_iterable(tags)
        return any(tag in self.tags for tag in tags_to_check)

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
        if not isinstance(widget, QtWidgets.QWidget):
            self.logger.warning(
                f"Expected a widget object, but received {type(widget)}"
            )
            return

        slots = self.sb.get_slot_class(self)
        slot_init = getattr(slots, f"{widget.name}_init", None)

        if slot_init and widget.refresh:
            widget.refresh = False  # Default to False before calling init where you can choose to set refresh to True.
            slot_init(widget)

    def call_slot(self, widget, *args, **kwargs):
        """Executes the associated slot for a given widget.

        This method retrieves the slot corresponding to the widget's name and executes it,
        passing along any additional arguments and keyword arguments. It also re-initializes the slot
        if the widget's `refresh` attribute is set to True.

        Parameters:
            widget (QWidget): The widget whose associated slot is to be called.
            *args: Variable-length argument list to pass to the slot.
            **kwargs: Arbitrary keyword arguments to pass to the slot.
        """
        if not isinstance(widget, QtWidgets.QWidget):
            self.logger.warning(
                f"Expected a widget object, but received {type(widget)}"
            )
            return

        slots = self.sb.get_slot_class(self)
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
                        if isinstance(rel_widget, QtWidgets.QWidget):
                            rel_widget.init_slot()

                if not widget.is_initialized:
                    widget.is_initialized = True

        return super().eventFilter(widget, event)

    def setVisible(self, visible):
        """Reimplement setVisible to prevent window from being hidden when prevent_hide is True."""
        if self.prevent_hide and not visible:
            return
        super().setVisible(visible)

    def show(self, pos=None, app_exec=False):
        """Show the MainWindow.

        Parameters:
            pos (QPoint/str, optional): A point to move to, or 'screen' to center on screen, or 'cursor' to center at cursor position. Defaults to None.
            app_exec (bool, optional): Execute the given PySide2 application, display its window, wait for user input,
                    and then terminate the program with a status code returned from the application. Defaults to False.
        Raises:
            SystemExit: Raised if the exit code returned from the PySide2 application is not -1.
        """
        super().show()
        self.sb.center_widget(self, pos)
        self.trigger_deferred()

        if app_exec:
            exit_code = self.sb.app.exec_()
            if exit_code != -1:
                sys.exit(exit_code)

    def showEvent(self, event):
        """Reimplement showEvent to emit custom signal when window is shown."""
        self.sb.connect_slots(self)
        self.activateWindow()
        self.on_show.emit()

        super().showEvent(event)
        self.is_initialized = True

    def focusInEvent(self, event):
        """Override the focus event to set the current UI when this window gains focus."""
        self.sb.set_current_ui(self)
        super().focusInEvent(event)
        self.on_focus_in.emit()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.on_focus_out.emit()

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
    from uitk import Switchboard

    class MyProject:
        ...

    class MySlots(MyProject):
        def __init__(self):
            self.sb = self.switchboard()

        def MyButtonsObjectName(self):
            print("Button clicked!")

    # Use the package to define the ui_location and slot_location.
    sb = Switchboard(
        ui_location="../example",
        slot_location=MySlots,
    )
    sb.example.show(app_exec=True)


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
