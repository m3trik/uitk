# !/usr/bin/python
# coding=utf-8
import inspect
import traceback
from typing import Optional, Union, Type, Callable, Any
from qtpy import QtWidgets, QtCore
import pythontk as ptk


class SlotWrapper:
    """Wrapper class for slots to handle argument injection, history tracking, and timeout monitoring."""

    def __init__(self, slot, widget, switchboard):
        self.slot = slot
        self.widget = widget
        self.sb = switchboard

        # Pre-calculate signature info
        self.sig = inspect.signature(slot)
        self.param_names = set(self.sig.parameters.keys())
        self.wants_widget = "widget" in self.param_names

    def _get_timeout(self):
        """Resolve the timeout value dynamically."""
        # Check widget first
        timeout = getattr(self.widget, "slot_timeout", None)

        # Fallback to UI (MainWindow) setting if not on widget
        if (
            timeout is None
            and hasattr(self.widget, "ui")
            and hasattr(self.widget.ui, "default_slot_timeout")
        ):
            timeout = self.widget.ui.default_slot_timeout

        if timeout:
            self.sb.logger.debug(
                f"Resolved timeout for {self.widget.objectName()}: {timeout}"
            )

        return timeout

    def __call__(self, *args, **kwargs):
        """The method called by the Qt Signal."""

        # Argument Injection Logic
        if self.wants_widget and "widget" not in kwargs:
            kwargs["widget"] = self.widget

        # Filter kwargs to match signature (prevents TypeErrors)
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in self.param_names}

        # History Tracking
        self.sb.slot_history(add=self.slot)

        # Execution Strategy
        timeout = self._get_timeout()
        if timeout and timeout > 0:
            msg = f"Slot '{self.slot.__name__}' on '{self.widget.objectName()}'"
            monitored_slot = ptk.ExecutionMonitor.execution_monitor(
                threshold=timeout,
                message=msg,
                logger=self.sb.logger,
                allow_escape_cancel=True,
            )(self.slot)

            try:
                return monitored_slot(*args, **filtered_kwargs)
            except KeyboardInterrupt:
                self.sb.logger.warning(
                    f"Execution of {self.slot.__name__} aborted by user."
                )
                return None
        else:
            return self.slot(*args, **filtered_kwargs)


class SwitchboardSlotsMixin:
    """Mixin for managing slot connections and signal-slot handling in the Switchboard."""

    default_signals = {
        QtWidgets.QAction: "triggered",
        QtWidgets.QCheckBox: "toggled",
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

    def get_default_signals(self, widget: QtWidgets.QWidget) -> set:
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
        try_names = self.get_slot_class_names(base_name)

        self.logger.debug(f"[_find_slots_class] Looking for: {try_names}")

        for name in try_names:
            cls = self.registry.slot_registry.get(
                classname=name, return_field="classobj"
            )
            if cls:
                self.logger.debug(f"[_find_slots_class] Resolved '{name}' to {cls}")
                return cls
        return None

    def slots_instantiated(self, key: str) -> bool:
        return key in self.slot_instances and not isinstance(
            self.slot_instances.raw(key), self.slot_instances.Placeholder
        )

    def get_slots_instance(self, ui: Union[str, QtWidgets.QWidget]) -> Optional[object]:
        """Get or create a slots instance for the given UI."""
        if isinstance(ui, str):
            ui = self.get_ui(ui)

        key = self.get_base_name(ui.objectName())

        # Check if already instantiated
        if self.slots_instantiated(key):
            return self.slot_instances[key]

        # Check if creation is in progress using placeholder metadata
        placeholder = self.slot_instances.get_placeholder(key)
        if placeholder and placeholder.meta.get("creation_in_progress", False):
            self.logger.debug(
                f"[get_slots_instance] [{ui.objectName()}] Slots creation already in progress"
            )
            return None

        # Find and create the slots instance
        slots_cls = self._find_slots_class(key)
        if slots_cls:
            try:
                # Set creation in progress flag
                if not placeholder:
                    placeholder = self.slot_instances.Placeholder(
                        slots_cls, meta={"creation_in_progress": True}
                    )
                    self.slot_instances.set_placeholder(key, placeholder)
                else:
                    placeholder.meta["creation_in_progress"] = True

                self.logger.debug(
                    f"[get_slots_instance] [{ui.objectName()}] Creating slots instance"
                )
                instance = self._create_slots_instance(ui, slots_cls)
                return instance
            finally:
                # Clear flag in case the placeholder still exists
                placeholder = self.slot_instances.get_placeholder(key)
                if placeholder and "creation_in_progress" in placeholder.meta:
                    placeholder.meta["creation_in_progress"] = False

        return None

    def _get_deferred_widgets(self, key: str) -> list:
        """Helper method to extract deferred widgets from a placeholder."""
        placeholder = self.slot_instances.get_placeholder(key)
        if placeholder and "deferred_widgets" in placeholder.meta:
            return placeholder.meta.get("deferred_widgets", [])
        return []

    def _create_slots_instance(
        self, ui: QtWidgets.QWidget, slots_cls: Type
    ) -> Optional[object]:
        """Create and initialize a new slots instance."""
        key = self.get_base_name(ui.objectName())
        self.logger.debug(f"[{ui.objectName()}] Creating slots instance: {slots_cls}")

        try:
            # Get deferred widgets BEFORE creating the instance
            deferred_widgets = self._get_deferred_widgets(key)

            instance = slots_cls(switchboard=self)

            # Update storage
            self.slot_instances[key] = instance
            ui.connected_slots["default"] = instance

            # Process deferred widgets AFTER instance is created
            self._process_deferred_widgets(ui, deferred_widgets)

            return instance
        except Exception as e:
            # Use logger's built-in spam prevention with a custom cache key
            cache_key = (
                f"{slots_cls.__name__ if slots_cls else 'Unknown'}_{type(e).__name__}"
            )
            deferred_count = (
                len(deferred_widgets) if "deferred_widgets" in locals() else 0
            )
            deferred_names = (
                [w.objectName() for w in deferred_widgets]
                if "deferred_widgets" in locals() and deferred_widgets
                else []
            )
            error_message = (
                f"[_create_slots_instance] [{ui.objectName()}] Failed to create slots instance for '{key}':\n"
                f"  Error: {type(e).__name__}: {e}\n"
                f"  Slots Class: {slots_cls.__name__ if slots_cls else 'Unknown'} "
                f"(from {getattr(slots_cls, '__module__', 'Unknown') if slots_cls else 'Unknown'})\n"
                f"  Deferred Widgets: {deferred_count} widgets - {deferred_names}\n"
                f"  Traceback:\n{traceback.format_exc()}"
            )
            self.logger.error_once(error_message, cache_key=cache_key)
            return None

    def _perform_slot_init(self, ui: QtWidgets.QWidget, widget: QtWidgets.QWidget):
        """Initialize a slot for a widget."""
        # Only skip if already initialized AND not refreshing
        if getattr(widget, "is_initialized", False) and not getattr(
            widget, "refresh_on_show", False
        ):
            self.logger.debug(
                f"[_perform_slot_init] [{ui.objectName()}.{widget.objectName()}] Already initialized, skipping"
            )
            return

        slots = self.get_slots_instance(ui)
        if not slots:
            self.logger.debug(
                f"[_perform_slot_init] [{ui.objectName()}.{widget.objectName()}] No slots instance found"
            )
            return

        # Check for and call the widget-specific init method
        slot_func = getattr(slots, f"{widget.objectName()}{self.INIT_SUFFIX}", None)
        if slot_func:
            try:
                slot_func(widget)
                self.logger.debug(
                    f"[_perform_slot_init] [{ui.objectName()}.{widget.objectName()}] Init method executed"
                )
            except Exception as e:
                self.logger.error(
                    f"[_perform_slot_init] [{ui.objectName()}.{widget.objectName()}] Error in init method: {e}"
                )
        else:
            self.logger.debug(
                f"[_perform_slot_init] [{ui.objectName()}.{widget.objectName()}] No init method found"
            )

        try:  # Restore widget state
            widget.perform_restore_state()
        except Exception as e:
            self.logger.error(
                f"[_perform_slot_init] [{ui.objectName()}.{widget.objectName()}] Error restoring state: {e}"
            )

        try:  # Connect widget signals to slots
            widget.connect_slot()
        except Exception as e:
            self.logger.error(
                f"[_perform_slot_init] [{ui.objectName()}.{widget.objectName()}] Error connecting slot: {e}"
            )

        # Mark widget as initialized
        widget.is_initialized = True

        try:  # Register child widgets
            self.logger.debug(
                f"[_perform_slot_init] [{ui.objectName()}.{widget.objectName()}] Calling register_children .."
            )
            widget.register_children()
            self.logger.debug(
                f"[_perform_slot_init] [{ui.objectName()}.{widget.objectName()}] Finished registering children from slot init"
            )
        except Exception as e:
            self.logger.error(
                f"[_perform_slot_init] [{ui.objectName()}.{widget.objectName()}] Error registering children: {e}"
            )

        self.logger.debug(
            f"[_perform_slot_init] [{ui.objectName()}.{widget.objectName()}] Slot initialization complete"
        )

    def _process_deferred_widgets(
        self, ui: QtWidgets.QWidget, deferred_widgets: list
    ) -> None:
        """Process deferred widgets for initialization."""
        if not deferred_widgets:
            self.logger.debug(
                f"[_process_deferred_widgets] [{ui.objectName()}] No deferred widgets to process"
            )
            return

        self.logger.debug(
            f"[_process_deferred_widgets] [{ui.objectName()}] Processing deferred widgets: {[w.objectName() for w in deferred_widgets]}"
        )

        # Process all deferred widgets
        for widget in deferred_widgets:
            try:
                self._perform_slot_init(ui, widget)
            except Exception as e:
                self.logger.error(
                    f"[_process_deferred_widgets] [{ui.objectName()}.{widget.objectName()}] Failed to initialize deferred widget: {e}"
                )

        # Clear the deferred widgets from the placeholder
        key = self.get_base_name(ui.objectName())
        placeholder = self.slot_instances.get_placeholder(key)
        if placeholder and "deferred_widgets" in placeholder.meta:
            placeholder.meta["deferred_widgets"] = []
            self.logger.debug(
                f"[_process_deferred_widgets] [{ui.objectName()}] Cleared deferred widgets list"
            )

    def _add_to_placeholder(self, key: str, widget: QtWidgets.QWidget) -> None:
        """Add a widget to a placeholder's deferred_widgets metadata."""
        placeholder = self.slot_instances.get_placeholder(key)
        if placeholder:
            # Add widget to existing placeholder's metadata
            placeholder.meta.setdefault("deferred_widgets", []).append(widget)
            self.logger.debug(
                f"[_add_to_placeholder] [{widget.ui.objectName()}.{widget.objectName()}] Added to placeholder metadata"
            )
        else:
            # Create new placeholder with widget in metadata
            slots_cls = self._find_slots_class(key)
            if slots_cls:
                placeholder = self.slot_instances.Placeholder(
                    slots_cls, meta={"deferred_widgets": [widget]}
                )
                self.slot_instances.set_placeholder(key, placeholder)
                self.logger.debug(
                    f"[_add_to_placeholder] [{widget.ui.objectName()}.{widget.objectName()}] Created placeholder with metadata"
                )
        self.logger.debug(
            f"[_add_to_placeholder] [{widget.ui.objectName()}.{widget.objectName()}] Added to placeholder '{key}'"
        )

    def init_slot(self, widget: QtWidgets.QWidget) -> None:
        if not isinstance(widget, QtWidgets.QWidget):
            return

        ui = widget.ui
        key = self.get_base_name(ui.objectName())

        # Always add to placeholder first, in case slot isn't ready
        self._add_to_placeholder(key, widget)

        # Then try to get or create the slots instance
        slots = self.get_slots_instance(ui)

        # If it succeeded, process it immediately
        if slots:
            self._perform_slot_init(ui, widget)

    def call_slot(self, widget: QtWidgets.QWidget, *args, **kwargs):
        """Call a slot method for a widget.
        Retrieves the slot associated with the widget's UI and calls it with the provided arguments.
        """
        if not isinstance(widget, QtWidgets.QWidget):
            self.logger.debug(f"[call_slot] Expected QWidget, got {type(widget)}")
            return

        ui_name = (
            widget.ui.objectName()
            if hasattr(widget, "ui") and widget.ui
            else "UnknownUI"
        )
        widget_name = widget.objectName()
        self.logger.debug(f"[call_slot] [{ui_name}.{widget_name}] Calling slot")

        slot = self.get_slot(
            self.get_slots_instance(widget.ui),
            widget_name,
            wrap=True,
            widget=widget,
        )
        if slot:
            slot(*args, **kwargs)
        else:
            self.logger.debug(
                f"[call_slot] [{ui_name}.{widget_name}] No callable slot found"
            )

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
                    f"[get_slot] [{widget.ui.objectName()}.{slot_name}] Slot not found in '{slot_class.__class__.__name__}'"
                )
            else:
                self.logger.debug(
                    f"[get_slot] [{slot_name}] Slot not found in '{slot_class.__class__.__name__}'"
                )
            return None
        except Exception:
            if widget:
                self.logger.error(
                    f"[get_slot] [{widget.ui.objectName()}.{slot_name}] Error accessing slot in '{slot_class.__name__}':\n{traceback.format_exc()}"
                )
            else:
                self.logger.error(
                    f"[get_slot] [{slot_name}] Error accessing slot in '{slot_class.__name__}':\n{traceback.format_exc()}"
                )
            return None

        if wrap and widget:
            return self._create_slot_wrapper(slot, widget)

        return slot

    def get_slot_from_widget(
        self, widget: QtWidgets.QWidget, wrap: bool = False
    ) -> Optional[Callable]:
        self.logger.debug(
            f"[get_slot_from_widget] [{widget.ui.objectName()}.{widget.objectName()}] Getting slot from widget"
        )

        slot_class = self.get_slots_instance(widget.ui)
        return self.get_slot(slot_class, widget.objectName(), wrap=wrap, widget=widget)

    def connect_slot(self, widget, slot=None):
        """Connect a widget's signals to its slot."""
        ui_name = widget.ui.objectName()
        widget_name = widget.objectName()

        if not slot:
            slot = self.get_slot_from_widget(widget)
            if not slot:
                self.logger.debug(
                    f"[connect_slot] [{ui_name}.{widget_name}] No slot found for widget"
                )
                return

        signals = getattr(
            slot,
            "signals",
            ptk.make_iterable(self.default_signals.get(widget.derived_type)),
        )

        for signal_name in signals:
            if not isinstance(signal_name, str):
                self.logger.error(
                    f"[connect_slot] [{ui_name}.{widget_name}] Invalid signal type: {type(signal_name)}"
                )
                continue

            signal = getattr(widget, signal_name, None)
            if not signal:
                self.logger.debug(
                    f"[connect_slot] [{ui_name}.{widget_name}] Signal '{signal_name}' not found"
                )
                continue

            # Skip if already connected
            if (
                widget in widget.ui.connected_slots
                and signal_name in widget.ui.connected_slots[widget]
            ):
                continue

            try:
                slot_wrapper = self._create_slot_wrapper(slot, widget)
                signal.connect(slot_wrapper)
                widget.ui.connected_slots.setdefault(widget, {})[
                    signal_name
                ] = slot_wrapper
                self.logger.debug(
                    f"[connect_slot] [{ui_name}.{widget_name}] Connected to signal '{signal_name}'"
                )
            except Exception as e:
                self.logger.error(
                    f"[connect_slot] [{ui_name}.{widget_name}] Error connecting to signal '{signal_name}': {e}"
                )

    def _create_slot_wrapper(self, slot, widget):
        """Creates a wrapper object for a slot that includes the widget as a parameter if possible.

        Parameters:
            slot (callable): The slot function to be wrapped.
            widget (QWidget): The widget that the slot is connected to.

        Returns:
            SlotWrapper: The slot wrapper object.
        """
        return SlotWrapper(slot, widget, self)

    def disconnect_slot(self, widget, slot=None):
        """Disconnects a slot from a widget.

        Parameters:
            widget (QWidget): The widget to disconnect the slot from.
            slot (callable, optional): The specific slot to disconnect. If not provided, all slots will be disconnected.
        """
        if not isinstance(widget, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(widget)}")

        if slot is None:
            # Disconnect all slots for the widget
            for signal_name, slot in self.connected_slots.get(widget, {}).items():
                signal = getattr(widget, signal_name, None)
                if signal:
                    signal.disconnect(slot)
            widget.ui.connected_slots[widget] = {}
        else:  # Disconnect a specific slot
            for signal_name, connected_slot in self.connected_slots.get(
                widget, {}
            ).items():
                if connected_slot == slot:
                    signal = getattr(widget, signal_name, None)
                    if signal:
                        signal.disconnect(slot)
                    break

    def slot_history(
        self,
        index=None,
        allow_duplicates=False,
        inc=[],
        exc=[],
        add=[],
        remove=[],
        length=200,
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
            length (int): Maximum length of the slot history. If the history exceeds this length, it will be truncated.

        Returns:
            (object/list): Slot method(s) based on index or slice.
        """
        # Keep original list length restricted to last 'length' elements
        self._slot_history = self._slot_history[-length:]
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


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    ...

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
