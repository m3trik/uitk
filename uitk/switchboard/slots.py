# !/usr/bin/python
# coding=utf-8
import inspect
import traceback
from functools import wraps
from typing import Optional, Union, Type, Callable, Any
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk


class Signals:
    """Decorator to specify which signals a slot should connect to.

    This class takes one or more signal names as strings during initialization
    and assigns them as attributes to the decorated function. The signals can be
    later retrieved for connecting the slot method to the respective signals.

    Attributes:
        signals (tuple of str): Signal names as strings.

    Example:
        @Signals("clicked", "pressed")
        def my_button(self, widget=None):
            print("Button interacted")

        @Signals.blockSignals
        def update_widget(self):
            self.spinbox.setValue(10)  # Won't trigger valueChanged
    """

    def __init__(self, *signals):
        if len(signals) == 0:
            raise ValueError("At least one signal must be specified")
        for signal in signals:
            if not isinstance(signal, str):
                raise TypeError(f"Signal must be a string, not {type(signal)}")
        self.signals = signals

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper.signals = self.signals
        return wrapper

    @classmethod
    def blockSignals(cls, func):
        """Decorator that blocks widget signals during method execution."""

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self.blockSignals(True)
            try:
                return func(self, *args, **kwargs)
            finally:
                self.blockSignals(False)

        return wrapper


class Cancelable:
    """Decorator: enable cancel-with-Esc + warning dialog for a heavy slot.

    Apply to slot methods that do bulk synchronous work the user might
    want to abort mid-flight. The Switchboard dispatcher wraps decorated
    slots in :func:`pythontk.ExecutionMonitor.execution_monitor`, which:

    * shows a "still running…" dialog (Keep Waiting / Cancel) after
      ``timeout`` seconds,
    * lets the user press-and-hold Esc at any time to abort,
    * spawns a near-cursor spinner subprocess (separate process,
      animates regardless of the main-thread event loop) after the
      threshold lapses.

    Plain (undecorated) slots run without any of this — the dispatcher's
    universal wait cursor is the only feedback. Restricting the
    monitor to opt-in slots avoids the per-invocation cost of spawning
    the monitor thread for every UI interaction.

    Example::

        @Cancelable(60)
        def tb016(self, widget):
            # Heavy: scan every animated transform in the scene.
            # User can hold Esc to abort if they picked the wrong scope.
            mtk.SegmentKeys.format_scene_info_html(...)

        @Cancelable(300, message="Texture optimization")
        def tb022(self, widget):
            mtk.MapOptimizer.batch_optimize_maps(...)

    Args:
        timeout: Seconds before the warning dialog appears. Must be > 0.
        message: Optional human-readable description used in the dialog
            and logger output. Defaults to a generic message built from
            the slot name.
    """

    def __init__(self, timeout: float, *, message: Optional[str] = None):
        if not (isinstance(timeout, (int, float)) and timeout > 0):
            raise ValueError(
                f"Cancelable(timeout=...): timeout must be a positive number, "
                f"got {timeout!r}"
            )
        self.timeout = float(timeout)
        self.message = message

    def __call__(self, func: Callable) -> Callable:
        func._cancelable_meta = {
            "timeout": self.timeout,
            "message": self.message,
        }
        return func


def _slot_busy_opt_out(widget, sb) -> bool:
    """True when the slot dispatcher should skip the busy-cursor change.

    Rapid-fire signals (sliders, text-changed) set
    ``widget.no_busy_indicator = True`` to avoid flashing the cursor on
    every event. The UI may also set ``ui.no_busy_indicator`` to
    suppress for an entire window. Defensive: a misbehaving ``@property``
    must not propagate into slot dispatch.
    """
    try:
        if getattr(widget, "no_busy_indicator", False):
            return True
    except Exception:
        pass
    ui = getattr(sb, "active_ui", None)
    if ui is None:
        ui = getattr(sb, "_current_ui", None)
    try:
        if ui is not None and getattr(ui, "no_busy_indicator", False):
            return True
    except Exception:
        pass
    return False


class SlotWrapper:
    """Wrapper class for slots to handle argument injection, history tracking, debounce, and timeout monitoring.

    Debounce
    --------
    If ``widget.debounce`` is set to a positive integer (milliseconds),
    the slot call is deferred until that many ms elapse without another
    signal.  Each new signal restarts the timer so rapid changes (e.g.
    spinner increments) coalesce into a single slot invocation.
    """

    # Class-level cache: slot function id -> (param_names frozenset, wants_widget bool)
    _sig_cache: dict = {}

    def __init__(self, slot, widget, switchboard):
        self.slot = slot
        self.widget = widget
        self.sb = switchboard
        self._debounce_timer = None
        self._debounce_args = None
        self._debounce_kwargs = None

        # Cache inspect.signature per slot function to avoid repeated introspection
        slot_id = id(slot)
        cached = SlotWrapper._sig_cache.get(slot_id)
        if cached is not None:
            self.param_names, self.wants_widget = cached
        else:
            sig = inspect.signature(slot)
            self.param_names = frozenset(sig.parameters.keys())
            self.wants_widget = "widget" in self.param_names
            SlotWrapper._sig_cache[slot_id] = (self.param_names, self.wants_widget)

    def _get_timeout(self):
        """Resolve the cancel-timeout for this slot, if any.

        Resolution order (first wins):

        1. ``widget.slot_timeout`` — per-widget runtime override.
        2. :class:`Cancelable` decorator metadata — declared at the slot
           definition site (``@Cancelable(timeout=N)``).
        3. ``ui.default_slot_timeout`` — opt-in UI-wide fallback. No
           longer set automatically by the marking menu; only honoured
           when a UI explicitly sets it.

        Returns ``None`` when no source provides a timeout — that's the
        normal path for plain slots, which run without monitor overhead
        and rely only on the dispatcher's wait cursor for feedback.
        """
        # 1. per-widget runtime override
        timeout = getattr(self.widget, "slot_timeout", None)

        # 2. decorator metadata (``@Cancelable(timeout=N)``)
        if timeout is None:
            meta = getattr(self.slot, "_cancelable_meta", None)
            if isinstance(meta, dict):
                timeout = meta.get("timeout")

        # 3. UI-wide fallback (only when a host has explicitly opted in)
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

        # Debounce: defer the call if the widget requests it
        debounce_ms = getattr(self.widget, "debounce", 0) or 0
        if debounce_ms > 0:
            self._debounce_args = args
            self._debounce_kwargs = filtered_kwargs
            if self._debounce_timer is None:
                from qtpy.QtCore import QTimer

                self._debounce_timer = QTimer(self.widget)
                self._debounce_timer.setSingleShot(True)
                self._debounce_timer.timeout.connect(self._flush_debounce)
            self._debounce_timer.setInterval(int(debounce_ms))
            self._debounce_timer.start()
            return None

        return self._invoke(*args, **filtered_kwargs)

    def _flush_debounce(self):
        """Execute the deferred slot call after the debounce timer fires."""
        args = self._debounce_args or ()
        kwargs = self._debounce_kwargs or {}
        self._debounce_args = None
        self._debounce_kwargs = None
        self._invoke(*args, **kwargs)

    def _invoke(self, *args, **kwargs):
        """Execute the slot with history tracking and optional timeout.

        Universal feedback: switches the application override-cursor to
        :data:`Qt.WaitCursor` for the slot's duration. The cursor is
        OS-managed and animates regardless of whether the slot blocks
        the Qt event loop (Maya ``cmds.*``, Max maxops, etc.) — the one
        feedback affordance that survives a frozen main thread. Slots
        that want richer in-widget feedback (status text, progress bar,
        indeterminate "tick" indicator) opt in cooperatively via
        :meth:`Switchboard.progress` / :meth:`Footer.progress`, which
        drive :meth:`ProgressBar.update_progress` — that method calls
        ``QApplication.processEvents`` per tick to keep the bar
        responsive between work chunks.

        Per-slot opt-out via ``widget.no_busy_indicator = True`` (or on
        the UI) is honoured for rapid-fire signals.
        """

        # History Tracking
        self.sb.slot_history(add=self.slot)

        # Wait cursor for the slot's duration. setOverrideCursor pushes
        # onto Qt's cursor stack; the matching restore in ``finally``
        # pops it. The cursor is OS-driven so it animates even when
        # Maya's cmds.* holds the Qt event loop — the dispatcher-side
        # affordance that previously tried to drive a footer marquee
        # could not, because Qt animations need the event loop to tick.
        # Wrapped defensively: a cursor failure must never block slot
        # dispatch.
        cursor_set = False
        if not _slot_busy_opt_out(self.widget, self.sb):
            try:
                QtWidgets.QApplication.setOverrideCursor(
                    QtGui.QCursor(QtCore.Qt.WaitCursor)
                )
                cursor_set = True
            except Exception:
                pass

        try:
            # Execution Strategy
            timeout = self._get_timeout()
            if timeout and timeout > 0:
                # Honour a custom message from @Cancelable(message=...)
                # when one was supplied; otherwise build a generic one
                # from the slot identity.
                meta = getattr(self.slot, "_cancelable_meta", None)
                custom_msg = (meta or {}).get("message") if isinstance(meta, dict) else None
                msg = custom_msg or (
                    f"Slot '{self.slot.__name__}' on '{self.widget.objectName()}'"
                )
                monitored_slot = ptk.ExecutionMonitor.execution_monitor(
                    threshold=timeout,
                    message=msg,
                    logger=self.sb.logger,
                    allow_escape_cancel=True,
                    indicator=True,
                )(self.slot)

                try:
                    return monitored_slot(*args, **kwargs)
                except KeyboardInterrupt:
                    self.sb.logger.warning(
                        f"Execution of {self.slot.__name__} aborted by user."
                    )
                    return None
            else:
                return self.slot(*args, **kwargs)
        finally:
            if cursor_set:
                try:
                    QtWidgets.QApplication.restoreOverrideCursor()
                except Exception:
                    pass


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

    def get_available_signals(self, widget, derived=True, exc=None):
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
        # 1. Try resolving by class name (Standard convention)
        try_names = self.get_slot_class_names(base_name)

        self.logger.debug(f"[_find_slots_class] Looking for classes: {try_names}")

        for name in try_names:
            cls = self.registry.slot_registry.get(
                classname=name, return_field="classobj"
            )
            if cls:
                self.logger.debug(
                    f"[_find_slots_class] Resolved class '{name}' to {cls}"
                )
                return cls

        # 2. Try resolving by module/file name (Fallback)
        # Look for files like <name>Slots.py or <name>_slots.py and use the first class found in them
        try_files = self.get_slot_file_names(base_name)
        self.logger.debug(f"[_find_slots_class] Looking for files: {try_files}")

        for name in try_files:
            # Check assuming standard .py extension.
            # get() returns the first match unless distinct is specified, which works for us
            # as we want a class from that file.
            cls = self.registry.slot_registry.get(
                filename=f"{name}.py", return_field="classobj"
            )
            if cls:
                self.logger.debug(
                    f"[_find_slots_class] Resolved file '{name}.py' to {cls}"
                )
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

            # Ensure the UI is accessible via loaded_ui during construction.
            # When resolution uses WeakValueDictionary, the entry can be lost
            # before the slots constructor accesses it (e.g. loaded_ui.<name>).
            # Only pre-store when the base name matches the objectName (no tags
            # stripped).  For tagged UIs like "display#submenu", storing under
            # the base name "display" clobbers the resolution path for the
            # standalone "display" UI, causing slots to get the wrong self.ui.
            if key == ui.objectName() and not self.loaded_ui.has(key):
                self.loaded_ui[key] = ui

            instance = slots_cls(switchboard=self)

            # Register shortcuts
            self.register_slots_shortcuts(ui, instance)

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
            # Resolve names defensively: a deferred wrapper may itself be the
            # dead C++ object that triggered this failure, so fall back to the
            # name stamped at defer time rather than re-raising while logging.
            deferred_names = []
            if "deferred_widgets" in locals() and deferred_widgets:
                for w in deferred_widgets:
                    try:
                        deferred_names.append(w.objectName())
                    except (RuntimeError, AttributeError):
                        deferred_names.append(
                            getattr(w, "_deferred_object_name", "<deleted>")
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

    def _perform_state_init(
        self, ui: QtWidgets.QWidget, widget: QtWidgets.QWidget
    ) -> None:
        """Initialize widget state: capture default value then restore persistent state.

        This is separated from _perform_slot_init to allow batch processing:
        all widgets complete their slot initialization (including configuration
        in slots class __init__) before any state operations occur.

        Parameters:
            ui: The parent UI widget.
            widget: The widget to initialize state for.
        """
        # Skip if widget doesn't support state restoration
        if not getattr(widget, "restore_state", False):
            return

        # Capture widget default AFTER init (which may populate/configure widget)
        # but BEFORE restoring persistent state
        try:
            ui.state.capture_default(widget)
            self.logger.debug(
                f"[_perform_state_init] [{ui.objectName()}.{widget.objectName()}] Default captured"
            )
        except Exception as e:
            self.logger.debug(
                f"[_perform_state_init] [{ui.objectName()}.{widget.objectName()}] Error capturing default: {e}"
            )

        # Restore widget state from persistent storage
        try:
            widget.perform_restore_state()
            self.logger.debug(
                f"[_perform_state_init] [{ui.objectName()}.{widget.objectName()}] State restored"
            )
        except Exception as e:
            self.logger.error(
                f"[_perform_state_init] [{ui.objectName()}.{widget.objectName()}] Error restoring state: {e}"
            )

    def _revive_deferred_widget(
        self, ui: QtWidgets.QWidget, widget: QtWidgets.QWidget
    ) -> Optional[QtWidgets.QWidget]:
        """Return a live wrapper for a deferred widget, re-resolving if stale.

        A widget registered/deferred during a slots ``__init__`` can be
        reparented before it is processed — most commonly by an option-box wrap
        (e.g. ``add_reset_buttons``), which moves the widget into a container and
        invalidates the Python wrapper captured at defer time. The underlying
        QWidget still exists, so re-resolve it by the name stamped in
        ``_add_to_placeholder`` and repair the switchboard bookkeeping (the
        ``ui.<name>`` attribute and ``ui.widgets`` set, both of which still hold
        the dead wrapper) so downstream ``self.ui.<name>`` access also lands on
        the live wrapper.

        Returns the live widget, or ``None`` if it can't be recovered — the
        caller then skips it rather than crashing the whole panel open.
        """
        if self._widget_is_alive(widget):
            return widget

        try:
            name = getattr(widget, "_deferred_object_name", None)
        except (RuntimeError, AttributeError):
            name = None
        if not name:
            return None

        fresh = self._get_widget_from_ui(ui, name)
        if fresh is None or not self._widget_is_alive(fresh):
            return None

        # Drop the dead wrapper and (re)register the live one. register_widget
        # re-points the ui.<name> attribute, re-adds to ui.widgets, and runs the
        # widget's init (now that the slots instance exists) — the subsequent
        # init phases below are then idempotent no-ops for it.
        ui.widgets.discard(widget)
        if fresh not in ui.widgets:
            ui.register_widget(fresh)

        self.logger.debug(
            f"[_revive_deferred_widget] [{ui.objectName()}.{name}] "
            "re-resolved a reparented deferred widget"
        )
        return fresh

    def _process_deferred_widgets(
        self, ui: QtWidgets.QWidget, deferred_widgets: list
    ) -> None:
        """Process deferred widgets for initialization."""
        if not deferred_widgets:
            self.logger.debug(
                f"[_process_deferred_widgets] [{ui.objectName()}] No deferred widgets to process"
            )
            return

        # Re-resolve any widget whose wrapper was invalidated by a reparent
        # (e.g. an option-box wrap) after it was deferred, so neither the
        # logging below nor the init phases touch a dead C++ object — that would
        # otherwise abort the entire panel open. Unrecoverable widgets are
        # dropped rather than allowed to crash the batch.
        revived = []
        for widget in deferred_widgets:
            live = self._revive_deferred_widget(ui, widget)
            if live is not None:
                revived.append(live)
        deferred_widgets = revived
        if not deferred_widgets:
            return

        self.logger.debug(
            f"[_process_deferred_widgets] [{ui.objectName()}] Processing deferred widgets: {[w.objectName() for w in deferred_widgets]}"
        )

        # Phase 1: Run slot initialization for ALL deferred widgets first
        # This allows slots class __init__ to complete all widget configuration
        # before any state operations occur
        for widget in deferred_widgets:
            try:
                self._perform_slot_init(ui, widget)
            except Exception as e:
                self.logger.error(
                    f"[_process_deferred_widgets] [{ui.objectName()}.{widget.objectName()}] Failed slot init: {e}"
                )

        # Phase 2: Run state initialization for ALL widgets
        # Now that all widgets are configured, capture defaults and restore state
        for widget in deferred_widgets:
            try:
                self._perform_state_init(ui, widget)
            except Exception as e:
                self.logger.error(
                    f"[_process_deferred_widgets] [{ui.objectName()}.{widget.objectName()}] Failed state init: {e}"
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
        # Stamp the objectName now, while the wrapper is guaranteed live. A
        # deferred widget can be reparented before it is processed (e.g. an
        # option-box wrap via add_reset_buttons), which invalidates this Python
        # wrapper; the stamped name lets _revive_deferred_widget re-resolve a
        # fresh wrapper instead of crashing on the dead one. It is a plain
        # Python attribute, so it stays readable even after the C++ side dies.
        try:
            widget._deferred_object_name = widget.objectName()
        except (RuntimeError, AttributeError):
            pass

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

    def init_slot(self, widget: QtWidgets.QWidget, block_signals: bool = True) -> None:
        if not isinstance(widget, QtWidgets.QWidget):
            return

        ui = widget.ui
        key = self.get_base_name(ui.objectName())

        # Fast path: if slots are already instantiated, skip placeholder/find entirely
        if self.slots_instantiated(key):
            slots = self.slot_instances[key]
        else:
            # Add to placeholder first, in case slot isn't ready
            self._add_to_placeholder(key, widget)
            # Then try to get or create the slots instance
            slots = self.get_slots_instance(ui)

        # If slots instance exists, process immediately (not deferred)
        if slots:
            if block_signals:
                was_blocked = widget.blockSignals(True)
                try:
                    self._perform_slot_init(ui, widget)
                    self._perform_state_init(ui, widget)
                finally:
                    widget.blockSignals(was_blocked)
            else:
                self._perform_slot_init(ui, widget)
                self._perform_state_init(ui, widget)

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

    def slot_history(
        self,
        index=None,
        allow_duplicates=False,
        inc=None,
        exc=None,
        add=None,
        remove=None,
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
