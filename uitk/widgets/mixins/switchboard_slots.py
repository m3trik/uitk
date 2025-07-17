# !/usr/bin/python
# coding=utf-8
import inspect
import traceback
from typing import Optional, Union, Type, Callable, Any
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

    def _find_slots_class(self, base_name: str) -> Optional[Type]:
        legal_name = self.convert_to_legal_name(base_name)
        capitalized = "".join(part.title() for part in legal_name.split("_"))
        try_names = [f"{capitalized}Slots", capitalized]

        self.logger.debug(f"[_find_slots_class] Looking for: {try_names}")

        for name in try_names:
            cls = self.registry.slot_registry.get(
                classname=name, return_field="classobj"
            )
            if cls:
                self.logger.debug(f"[SlotResolver] Resolved '{name}' to {cls}")
                return cls
        return None

    def _resolve_slots_instance(
        self, widget: Union[str, QtWidgets.QWidget]
    ) -> Optional[object]:
        if isinstance(widget, str):
            ui = self.get_ui(widget)
        else:
            ui = getattr(widget, "ui", None) or widget.parent()

        if not ui or not ui.objectName():
            self.logger.debug(
                f"[_resolve_slots_instance] Could not resolve UI: {widget}"
            )
            return None

        return self.get_slots_instance(ui)

    def slots_instanciated(self, key: str) -> bool:
        raw = self.slot_instances.raw(key)
        if isinstance(raw, self.slot_instances.Placeholder):
            return raw.meta.get("ready", False)
        return getattr(raw, "_is_ready", False)

    def mark_slots_instanciated(self, key: str, slots: object) -> None:
        setattr(slots, "_is_ready", True)
        if self.slot_instances.has_placeholder(key):
            self.slot_instances.placeholders[key].meta["ready"] = True

    def get_slots_instance(self, ui: QtWidgets.QWidget) -> Optional[object]:
        if not hasattr(ui, "connected_slots"):
            self.logger.debug(f"[{ui.objectName()}] UI has no 'connected_slots'")
            return None

        if "default" in ui.connected_slots:
            return ui.connected_slots["default"]

        key = self.get_base_name(ui.objectName())

        if self.slot_instances.is_resolving(key):
            self.logger.debug(
                f"[{ui.objectName()}] Preventing recursion for key '{key}'"
            )
            return None

        existing = self.slot_instances.raw(key)
        if existing:
            return existing

        slots_cls = self._find_slots_class(key)
        if not slots_cls:
            self.logger.debug(
                f"[{ui.objectName()}] No slots class found for key '{key}'"
            )
            return None

        token = object()
        ui.connected_slots["default"] = token

        try:
            self.logger.debug(
                f"[{ui.objectName()}] Creating slot instance: {slots_cls}"
            )
            slots = slots_cls(ui=ui, switchboard=self)

            if ui.connected_slots.get("default") is token:
                self.slot_instances[key] = slots
                self.set_slots_instance(ui, slots)
                self.mark_slots_instanciated(key, slots)

                pending = self._pending_slot_init.pop(key, [])
                if pending:
                    self.logger.debug(
                        f"[{ui.objectName()}] Initializing {len(pending)} deferred widgets"
                    )
                for pending_widget in pending:
                    self.init_slot(pending_widget)

            else:
                slots = ui.connected_slots["default"]

            return slots

        except Exception as e:
            if ui.connected_slots.get("default") is token:
                del ui.connected_slots["default"]
            self.logger.error(
                f"[{ui.objectName()}] Error initializing slots for '{key}': {e}"
            )
            return None

    def set_slots_instance(self, ui: QtWidgets.QWidget, instance: object):
        if not hasattr(ui, "connected_slots"):
            self.logger.debug(f"[{ui.objectName()}] UI has no 'connected_slots'")
            return
        ui.connected_slots["default"] = instance

    def init_slot(self, widget: QtWidgets.QWidget) -> None:
        if not isinstance(widget, QtWidgets.QWidget):
            return

        ui = getattr(widget, "ui", None)
        if not ui or not ui.objectName():
            self.logger.debug(
                f"[UnknownUI.{widget.objectName()}] Widget missing valid UI or object name"
            )
            return

        self.logger.debug(
            f"[{ui.objectName()}.{widget.objectName()}] Initializing slot"
        )

        slots = self.get_slots_instance(ui)
        if not slots:
            self.logger.debug(
                f"[{ui.objectName()}.{widget.objectName()}] No slot instance resolved"
            )
            return

        slot_func = getattr(slots, f"{widget.objectName()}_init", None)
        if callable(slot_func):
            slot_func(widget)
            self.logger.debug(
                f"[{ui.objectName()}.{widget.objectName()}] Init method called successfully"
            )
        else:
            self.logger.debug(
                f"[{ui.objectName()}.{widget.objectName()}] No init method found in {slots.__class__.__name__}"
            )

        widget.ui.restore_widget_state(widget)
        widget.is_initialized = True

    def call_slot(self, widget: QtWidgets.QWidget, *args, **kwargs):
        """Call a slot method for a widget.
        Retrieves the slot associated with the widget's UI and calls it with the provided arguments.
        """
        if not isinstance(widget, QtWidgets.QWidget):
            self.logger.debug(f"[InvalidWidget] Expected QWidget, got {type(widget)}")
            return

        ui_name = (
            widget.ui.objectName()
            if hasattr(widget, "ui") and widget.ui
            else "UnknownUI"
        )
        widget_name = widget.objectName()
        self.logger.debug(f"[{ui_name}.{widget_name}] Calling slot")

        slot = self.get_slot(
            self.get_slots_instance(widget.ui),
            widget_name,
            wrap=True,
            widget=widget,
        )
        if slot:
            slot(*args, **kwargs)
        else:
            self.logger.debug(f"[{ui_name}.{widget_name}] No callable slot found")

    def get_slot(
        self,
        slot_class: object,
        slot_name: str,
        wrap: bool = False,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> Optional[Callable]:
        try:
            slot = getattr(slot_class, slot_name)
        except AttributeError:
            if widget:
                self.logger.debug(
                    f"[{widget.ui.objectName()}.{slot_name}] Slot not found in '{slot_class.__class__.__name__}'"
                )
            else:
                self.logger.debug(
                    f"[{slot_name}] Slot not found in '{slot_class.__class__.__name__}'"
                )
            return None
        except Exception:
            if widget:
                self.logger.error(
                    f"[{widget.ui.objectName()}.{slot_name}] Error accessing slot in '{slot_class.__name__}':\n{traceback.format_exc()}"
                )
            else:
                self.logger.error(
                    f"[{slot_name}] Error accessing slot in '{slot_class.__name__}':\n{traceback.format_exc()}"
                )
            return None

        if wrap and widget:
            return self._create_slot_wrapper(slot, widget)

        return slot

    def get_slot_from_widget(
        self, widget: QtWidgets.QWidget, wrap: bool = False
    ) -> Optional[Callable]:
        self.logger.debug(
            f"[{widget.ui.objectName()}.{widget.objectName()}] Getting slot from widget"
        )

        slot_class = self.get_slots_instance(widget.ui)
        return self.get_slot(slot_class, widget.objectName(), wrap=wrap, widget=widget)

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
                    self.logger.debug(f"Item '{item}' not found in slot history.")
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
        ui_name = widget.ui.objectName()
        widget_name = widget.objectName()
        self.logger.debug(f"[{ui_name}.{widget_name}] Connecting slot")

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
                    f"[{ui_name}.{widget_name}] Invalid signal for {widget.derived_type}. Expected str, got {type(signal_name)}"
                )

            signal = getattr(widget, signal_name, None)
            if not signal:
                self.logger.debug(
                    f"[{ui_name}.{widget_name}] No signal '{signal_name}' found on {widget.derived_type}"
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

            self.logger.debug(f"[{ui_name}.{widget_name}] Connected to '{signal_name}'")

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
        self.logger.debug(f"[{ui.objectName()}] Disconnecting slots")

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
                widget.ui.connected_slots[widget] = {
                    signal_name: slot
                    for signal_name, slot in widget.ui.connected_slots[widget].items()
                    if signal_name not in signals
                }

        ui.is_connected = False
        self.logger.debug(f"[{ui.objectName()}] Slots disconnected")


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    ...

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
