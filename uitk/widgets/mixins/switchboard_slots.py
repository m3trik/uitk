# !/usr/bin/python
# coding=utf-8
import inspect
import traceback
from typing import Optional, Union, Type, Callable
from qtpy import QtWidgets, QtCore
import pythontk as ptk


class SwitchboardSlotsMixin:
    """Mixin for managing slot connections and signal-slot handling in the Switchboard."""

    default_signals = {
        QtWidgets.QAction: "triggered",
        QtWidgets.QCheckBox: "stateChanged",
        QtWidgets.QComboBox: "currentIndexChanged",
        QtWidgets.QDateEdit: "dateChanged",
        QtWidgets.QDateTimeEdit: "dateTimeChanged",
        QtWidgets.QDial: "valueChanged",
        QtWidgets.QDoubleSpinBox: "valueChanged",
        QtWidgets.QLabel: "released",
        QtWidgets.QLineEdit: "textChanged",
        QtWidgets.QListWidget: "itemClicked",
        QtWidgets.QMenu: "triggered",
        QtWidgets.QMenuBar: "triggered",
        QtWidgets.QProgressBar: "valueChanged",
        QtWidgets.QPushButton: "clicked",
        QtWidgets.QRadioButton: "toggled",
        QtWidgets.QScrollBar: "valueChanged",
        QtWidgets.QSlider: "valueChanged",
        QtWidgets.QSpinBox: "valueChanged",
        QtWidgets.QStackedWidget: "currentChanged",
        QtWidgets.QTabBar: "currentChanged",
        QtWidgets.QTabWidget: "currentChanged",
        QtWidgets.QTableWidget: "cellChanged",
        QtWidgets.QTextEdit: "textChanged",
        QtWidgets.QTimeEdit: "timeChanged",
        QtWidgets.QToolBox: "currentChanged",
        QtWidgets.QTreeWidget: "itemClicked",
    }

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
                self.logger.warning(f"[_find_slot_class] No 'objectName' found: {ui}.")
                return None
        else:
            name = ui

        # Extract the name without tags
        name_no_tags = self.get_base_name(name)
        if not name_no_tags:
            self.logger.warning(f"[_find_slot_class] No base name found for: {name}.")
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

    def resolve_slot_class(self, ui) -> Optional[Type]:
        """Resolves a slot class type for the given UI (does not assign)."""
        name = ui.objectName()
        if not name:
            return None

        name_no_tags = self.get_base_name(name)
        try_names = [self.convert_to_legal_name(name_no_tags).title().replace("_", "")]
        try_names = [f"{n}Slots" for n in try_names] + try_names

        for class_name in try_names:
            found = self.registry.slot_registry.get(
                classname=class_name, return_field="classobj"
            )
            if found:
                return found

        for relative_name in self.get_ui_relatives(ui, upstream=True, reverse=True):
            rel = self.get_ui(relative_name)
            if rel:
                try:
                    return self.resolve_slot_class(rel)
                except Exception:
                    self.logger.info(traceback.format_exc())

        return None

    def get_slot_class(self, ui) -> Optional[object]:
        """Returns an assigned slot instance or tries to resolve and assign one."""
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Expected QWidget, got {type(ui)}")

        if hasattr(ui, "_slots"):
            return ui._slots

        resolved_class = self.resolve_slot_class(ui)
        if resolved_class:
            return self.set_slot_class(ui, resolved_class)

        return None

    def set_slot_class(
        self, ui: QtWidgets.QWidget, clss: Union[Type, object], overwrite: bool = False
    ):
        """Assigns or replaces a slot instance on a UI. Accepts either a class or an instance."""
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Expected QWidget, got {type(ui)}")

        current = getattr(ui, "_slots", None)

        if not overwrite:
            if isinstance(clss, type) and isinstance(current, clss):
                return current
            if not isinstance(clss, type) and current is clss:
                return current

        if not isinstance(clss, type):
            ui._slots = clss
            return clss

        def accepts_switchboard(cls):
            params = inspect.signature(cls.__init__).parameters
            return "switchboard" in params or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
            )

        kwargs = {"switchboard": self} if accepts_switchboard(clss) else {}

        try:
            instance = clss(**kwargs)
            ui._slots = instance
            return instance
        except Exception:
            self.logger.error(
                f"Failed to instantiate slot class '{clss.__name__}' for UI '{ui.objectName()}':\n{traceback.format_exc()}"
            )
            return None

    def get_slot(
        self,
        slot_class: object,
        slot_name: str,
        wrap: bool = False,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> Optional[Callable]:
        """Get the slot from the slot class.

        Parameters:
            slot_class (object): Slot class instance.
            slot_name (str): Name of the slot (method or attribute).
            wrap (bool): If True, return a wrapped callable with widget context.
            widget (QWidget, optional): Required if wrap is True.

        Returns:
            object or None: The slot or wrapped slot, or None if not found.
        """
        try:
            slot = getattr(slot_class, slot_name)
        except AttributeError:
            self.logger.debug(
                f"Slot '{slot_name}' not found in '{slot_class.__class__.__name__}'"
            )
            return None
        except Exception:
            self.logger.error(
                f"Exception occurred while accessing slot '{slot_name}' in "
                f"'{slot_class.__class__.__name__}':\n{traceback.format_exc()}"
            )
            return None

        if wrap and widget:
            return self._create_slot_wrapper(slot, widget)

        return slot

    def get_slot_from_widget(
        self, widget: QtWidgets.QWidget, wrap: bool = False
    ) -> Optional[Callable]:
        """Get the corresponding slot from a given widget.

        Parameters:
            widget (QWidget): The widget whose slot to retrieve.
            wrap (bool): If True, returns the wrapped slot with widget context.

        Returns:
            Callable or None: The slot (or wrapped slot) of the same name.
        """
        self.logger.debug(f"Getting slot from widget: {widget}")

        slot_class = self.get_slot_class(widget.ui)
        return self.get_slot(slot_class, widget.objectName(), wrap=wrap, widget=widget)

    def init_slot(self, widget, force=False):
        """Initialize a slot for a widget.
        If force is True or widget is not initialized, calls the initialization method for the slot.
        """
        if not isinstance(widget, QtWidgets.QWidget):
            self.logger.warning(
                f"Expected a widget object, but received {type(widget)}"
            )
            return

        slots = self.get_slot_class(widget.ui)
        slot_init = getattr(slots, f"{widget.objectName()}_init", None)

        # Always run if force=True, otherwise only on first initialization
        if force or not getattr(widget, "is_initialized", False):
            if slot_init:
                slot_init(widget)

    def call_slot(self, widget, *args, **kwargs):
        """Call a slot method for a widget.
        Retrieves the slot associated with the widget's UI and calls it with the provided arguments.
        """
        if not isinstance(widget, QtWidgets.QWidget):
            self.logger.warning(
                f"Expected a widget object, but received {type(widget)}"
            )
            return

        slot = self.get_slot(
            self.get_slot_class(widget.ui),
            widget.objectName(),
            wrap=True,
            widget=widget,
        )
        if slot:
            slot(*args, **kwargs)

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
            if getattr(ui, "is_connected", False):
                return
            widgets = ui.widgets

        # Make snapshot to avoid mutation during iteration
        for widget in ptk.make_iterable(widgets, snapshot=True):
            self.connect_slot(widget)

        ui.is_connected = True

    def connect_slot(self, widget, slot=None):
        """Connects a slot to the default signals of a widget."""
        self.logger.debug(
            f"Connecting slot for '{widget.ui.objectName()}.{widget.objectName()}'"
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
                    f"Invalid signal for '{widget.ui.objectName()}.{widget.objectName()}' {widget.derived_type}. "
                    f"Expected str, got '{type(signal_name)}'"
                )

            signal = getattr(widget, signal_name, None)
            if not signal:
                self.logger.warning(
                    f"No valid signal found for '{widget.ui.objectName()}.{widget.objectName()}' {widget.derived_type}. "
                    f"Expected str, got '{type(signal_name)}'"
                )
                continue

            if (
                widget in widget.ui.connected_slots
                and signal_name in widget.ui.connected_slots[widget]
            ):
                continue

            slot_wrapper = self._create_slot_wrapper(slot, widget)
            signal.connect(slot_wrapper)

            widget.ui.connected_slots.setdefault(widget, {})[signal_name] = slot_wrapper

            self.logger.debug(
                f"Slot connected for '{widget.ui.objectName()}.{widget.objectName()}' {widget.derived_type}"
            )

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
                    signal = getattr(widget, signal_name, None)
                    if signal:
                        signal.disconnect(slot)
                widget.ui.connected_slots[widget] = {}
            else:
                signals = getattr(slot, "signals", self.get_default_signals(widget))
                for signal_name in signals:
                    if signal_name in self.connected_slots.get(widget, {}):
                        signal = getattr(widget, signal_name, None)
                        if signal:
                            signal.disconnect(slot)
                # Ensure the slot is removed from the connected_slots
                widget.ui.connected_slots[widget] = {
                    signal_name: slot
                    for signal_name, slot in widget.ui.connected_slots[widget].items()
                    if signal_name not in signals
                }

        ui.is_connected = False
        self.logger.debug(f"Slots disconnected for '{ui}'")


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    ...

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
