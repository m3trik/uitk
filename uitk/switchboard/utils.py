# !/usr/bin/python
# coding=utf-8
import re
import traceback
from typing import Callable, List, Optional, Union
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk


class SwitchboardUtilsMixin:
    """Utility methods for widget positioning, centering, and screen geometry."""

    @staticmethod
    def get_cursor_offset_from_center(widget):
        """Get the relative position of the cursor with respect to the center of a given widget.

        Parameters:
            widget (QWidget): The widget to query.

        Returns:
            (obj) QPoint
        """
        return QtGui.QCursor.pos() - widget.rect().center()

    @staticmethod
    def center_widget(
        widget,
        pos=None,
        offset_x=0,
        offset_y=0,
        padding_x=None,
        padding_y=None,
        relative: QtWidgets.QWidget = None,
    ):
        """Adjust the widget's size to fit contents and center it at the given point, on the screen, at cursor, or at the widget's current position if no point is given.

        Parameters:
            widget (QWidget): The widget to move and resize.
            pos (QPoint/str, optional): A point to move to, or 'screen' to center on screen, or 'cursor' to center at cursor position. Defaults to None.
            offset_x (int, optional): The desired offset percentage on the x axis. Defaults to 0.
            offset_y (int, optional): The desired offset percentage on the y axis. Defaults to 0.
            padding_x (int, optional): Additional width from the widget's minimum size or relative widget. If not specified, the widget's current width is used.
            padding_y (int, optional): Additional height from the widget's minimum size or relative widget. If not specified, the widget's current height is used.
            relative (QWidget, optional): If given, use this widget's current size as the base size for resizing.
        """
        # Resize the widget if padding values are provided
        if padding_x is not None or padding_y is not None:
            p1 = widget.rect().center()

            w = widget if not relative else relative
            x = w.minimumSizeHint().width() if padding_x is not None else w.width()
            y = w.minimumSizeHint().height() if padding_y is not None else w.height()

            widget.resize(
                x + (padding_x if padding_x is not None else 0),
                y + (padding_y if padding_y is not None else 0),
            )
            p2 = widget.rect().center()
            diff = p1 - p2
            widget.move(widget.pos() + diff)

        # Determine the center point based on the provided pos value
        if pos == "screen":
            rect = QtWidgets.QApplication.primaryScreen().availableGeometry()
            centerPoint = rect.center()
        elif pos == "cursor":
            centerPoint = QtGui.QCursor.pos()
        elif pos is None:
            centerPoint = widget.frameGeometry().center()
        elif isinstance(pos, QtCore.QPoint):
            centerPoint = pos
        else:
            raise ValueError(
                "Invalid value for pos. It should be either 'screen', 'cursor', a QPoint instance or None."
            )

        # Compute the offset
        offset = QtCore.QPoint(
            widget.width() * offset_x / 100, widget.height() * offset_y / 100
        )
        # Center the widget considering the offset
        widget.move(centerPoint - widget.rect().center() + offset)

    @classmethod
    def unpack_names(cls, name_string):
        """Unpacks a comma-separated string of names and returns a list of individual names.

        Parameters:
            name_string (str): A string consisting of widget names separated by commas.
                    Names may include ranges with hyphens, e.g., 'chk021-23, 25, tb001'.
        Returns:
            list: A list of unpacked names, e.g., ['chk021', 'chk022', 'chk023', 'chk025', 'tb001'].
        """

        def expand_name_range(prefix, start, stop):
            """Generate a list of names with a given prefix and a range of numbers."""
            return [prefix + str(num).zfill(3) for num in range(start, stop + 1)]

        def extract_parts(name):
            """Extract alphabetic and numeric parts from a given name using regular expressions."""
            return re.findall(r"([a-zA-Z]+)|(\d+)", name)

        names = re.split(r",\s*", name_string)
        unpacked_names = []
        last_prefix = None

        for name in names:
            parts = extract_parts(name)
            digits = [int(p[1]) for p in parts if p[1]]

            if len(digits) == 1:
                if not parts[0][0]:
                    unpacked_names.append(last_prefix + str(digits[0]).zfill(3))
                else:
                    last_prefix = parts[0][0]
                    unpacked_names.append(name)
            elif len(digits) == 2:
                prefix = parts[0][0]
                start, stop = digits
                unpacked_names.extend(expand_name_range(prefix, start, stop))
                last_prefix = prefix

        return unpacked_names

    def get_widgets_by_string_pattern(self, ui, name_string):
        """Get a list of corresponding widgets from a single shorthand formatted string.
        ie. 's000,b002,cmb011-15' would return object list: [<s000>, <b002>, <cmb011>, <cmb012>, <cmb013>, <cmb014>, <cmb015>]

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            name_string (str): Widget object names separated by ','. ie. 's000,b004-7'. b004-7 specifies buttons b004 though b007.

        Returns:
            (list) QWidget(s)

        Example:
            get_widgets_by_string_pattern(<ui>, 's000,b002,cmb011-15')
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")

        widgets = []
        for n in self.unpack_names(name_string):
            try:
                w = getattr(ui, n)
                widgets.append(w)
            except AttributeError:
                self.logger.info(traceback.format_exc())

        return widgets

    def get_methods_by_string_pattern(self, clss, name_string):
        """Get a list of corresponding methods from a single shorthand formatted string.
        ie. 's000,b002,cmb011-15' would return methods: [<s000>, <b002>, <cmb011>, <cmb012>, <cmb013>, <cmb014>, <cmb015>]

        Parameters:
            clss (class): The class containing the methods.
            name_string (str): Slot names separated by ','. ie. 's000,b004-7'. b004-7 specifies methods b004 through b007.

        Returns:
            (list) class methods.

        Example:
            get_methods_by_string_pattern(<ui>, 'slot1,slot2,slot3')
        """
        if not isinstance(clss, object):
            raise ValueError(f"Invalid datatype: Expected class, got {type(clss)}")

        result = []
        for method_name in self.unpack_names(name_string):
            method = getattr(clss, method_name, None)
            if method is not None:
                result.append(method)

        return result

    def create_button_groups(
        self,
        ui: QtWidgets.QWidget,
        *args: str,
        allow_deselect: bool = False,
        allow_multiple: bool = False,
    ) -> List[QtWidgets.QButtonGroup]:
        """Create button groups for a set of widgets.

        Parameters:
            ui (QtWidgets.QWidget): A previously loaded dynamic UI object.
            args (str): The widgets to group. Object_names separated by ',' ie. 'b000-12,b022'
            allow_deselect (bool): Whether to allow none of the checkboxes to be selected.
            allow_multiple (bool): Whether to allow multiple checkboxes to be selected.
        """
        button_groups = []

        def button_toggled(w: QtWidgets.QAbstractButton, grp: QtWidgets.QButtonGroup):
            """Handle button toggle event."""
            w.blockSignals(True)  # Block signals to prevent recursive calls

            if not allow_multiple and w.isChecked():
                # Uncheck all other buttons in the group
                for btn in grp.buttons():
                    if btn != w:
                        btn.setChecked(False)
            elif not allow_deselect and not any(
                btn.isChecked() for btn in grp.buttons()
            ):
                # Re-check the button if deselect is not allowed
                w.setChecked(True)

            w.blockSignals(False)  # Unblock signals after state change

        for buttons in args:
            # Get widgets by the string pattern
            widgets = self.get_widgets_by_string_pattern(ui, buttons)
            if not widgets:
                continue

            # Validation checks
            widget_type = type(widgets[0])
            if allow_multiple and issubclass(widget_type, QtWidgets.QRadioButton):
                raise ValueError("Allow_multiple is not applicable to QRadioButton")
            if any(type(w) != widget_type for w in widgets):
                raise TypeError("All widgets in a group must be of the same type")

            # Create button group
            grp = QtWidgets.QButtonGroup()
            grp.setExclusive(False)  # Set to False to manually handle exclusivity

            # Add each widget to the button group
            for w in widgets:
                w.button_group = grp
                grp.addButton(w)
                # Temporarily block signals to prevent the toggled slot from being triggered
                w.blockSignals(True)
                w.setChecked(False)
                w.blockSignals(False)
                w.toggled.connect(lambda checked, w=w, grp=grp: button_toggled(w, grp))

            button_groups.append(grp)

        return ptk.format_return(button_groups)

    def toggle_multi(self, ui, trigger=None, signal=None, **kwargs):
        """Set multiple boolean properties for multiple widgets at once, or connect a trigger to do so automatically.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            trigger (str/QWidget, optional): If provided, connects this widget's signal to toggle the others.
                                             If None, toggles immediately.
            signal (str, optional): Signal name to connect (only used when trigger is provided). Default: 'toggled'.
            **kwargs: The properties to modify. Can be:
                     - Direct properties (immediate mode): setChecked, setUnChecked, setEnabled, setDisabled, etc.
                       Value: string of object_names separated by ',' ie. 'b000-12,b022'
                     - State mapping (trigger mode): on_<state>={...}, on_default={...}
                       Value: dict of toggle_multi kwargs to apply for that state

        Examples:
            # Immediate toggle (original behavior)
            toggle_multi(<ui>, setDisabled='b000', setUnChecked='chk009-12')

            # Auto-connect with boolean states (True/False)
            toggle_multi(<ui>, trigger='chk027', signal='toggled',
                        on_True={'setDisabled': 's005,s006'},
                        on_False={'setEnabled': 's005,s006'})

            # Auto-connect with any value states (e.g., combobox index)
            toggle_multi(<ui>, trigger='cmb001', signal='currentIndexChanged',
                        on_0={'setVisible': 'grp_basic'},
                        on_1={'setVisible': 'grp_advanced'},
                        on_2={'setVisible': 'grp_expert'},
                        on_default={'setHidden': 'grp_basic,grp_advanced,grp_expert'})

            # String states (e.g., from text changed)
            toggle_multi(<ui>, trigger='line_edit', signal='textChanged',
                        on_auto={'setEnabled': 's001'},
                        on_manual={'setDisabled': 's001'})
        """
        # Extract state mapping kwargs (those starting with 'on_')
        state_map = {}
        immediate_kwargs = {}

        for key, value in list(kwargs.items()):
            if key.startswith(self.STATE_PREFIX):
                state_value = key[len(self.STATE_PREFIX) :]  # Remove 'on_' prefix
                # Store the string representation as key - will match against actual signal values
                state_map[state_value] = value
            else:
                immediate_kwargs[key] = value

        # If trigger provided, set up connection
        if trigger is not None:
            # Default signal to 'toggled' if not specified
            if signal is None:
                signal = "toggled"

            # Get the trigger widget if string provided
            if isinstance(trigger, str):
                trigger_widget = getattr(ui, trigger, None)
                if not trigger_widget:
                    self.logger.warning(
                        f"Widget '{trigger}' not found in UI, cannot connect toggle."
                    )
                    return
            else:
                trigger_widget = trigger

            # Get default state mapping if provided
            default_map = state_map.pop("default", None)

            # Create the callback function
            def toggle_callback(state):
                # Convert state to string for lookup (to match parameter names)
                state_key = str(state)

                # Look up the state in the mapping
                toggle_kwargs = state_map.get(state_key)

                # Fall back to default if state not found
                if toggle_kwargs is None and default_map is not None:
                    toggle_kwargs = default_map

                if toggle_kwargs:
                    self.toggle_multi(ui, **toggle_kwargs)

            # Connect the signal
            try:
                signal_obj = getattr(trigger_widget, signal, None)
                if signal_obj and callable(getattr(signal_obj, "connect", None)):
                    signal_obj.connect(toggle_callback)
                else:
                    self.logger.warning(
                        f"Signal '{signal}' not found on widget '{trigger_widget}'"
                    )
            except Exception as e:
                self.logger.error(f"Failed to connect toggle: {e}")
            return

        # Original immediate toggle behavior
        for k in immediate_kwargs:  # property_ ie. setUnChecked
            # get_widgets_by_string_pattern returns a widget list from a string of object_names.
            widgets = self.get_widgets_by_string_pattern(ui, immediate_kwargs[k])

            state = True
            # strips 'Un' and sets the state from True to False. ie. 'setUnChecked' becomes 'setChecked' (False)
            if "Un" in k:
                k = k.replace("Un", "")
                state = False

            # set the property state for each widget in the list.
            for w in widgets:
                getattr(w, k)(state)

    def connect_multi(self, ui, widgets, signals, slots):
        """Connect multiple signals to multiple slots at once.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            widgets (str/list): 'chk000-2' or [tb.menu.chk000, tb.menu.chk001]
            signals (str/list): 'toggled' or ['toggled']
            slots (obj/list): self.cmb002 or [self.cmb002]

        Example:
            connect_multi(tb.menu, 'chk000-2', 'toggled', self.cmb002)
        """
        if isinstance(widgets, str):
            widgets = self.get_widgets_by_string_pattern(ui, widgets)
        else:
            widgets = ptk.make_iterable(widgets)

        # Ensure the other arguments are iterable
        signals = ptk.make_iterable(signals)
        slots = ptk.make_iterable(slots)

        self.logger.debug(
            f"[connect_multi] Connecting: {widgets} to {signals} -> {slots}"
        )

        for widget in widgets:
            if not widget:
                self.logger.warning(f"Skipped: Invalid widget '{widget}'")
                continue

            for signal_name in signals:
                try:
                    signal = getattr(widget, signal_name, None)
                    if not signal:
                        self.logger.warning(
                            f"Skipped: Widget '{widget}' has no signal '{signal_name}'"
                        )
                        continue

                    for slot in slots:
                        if not callable(slot):
                            self.logger.warning(
                                f"Skipped: Slot '{slot}' is not callable"
                            )
                            continue

                        signal.connect(slot)

                except Exception as e:
                    self.logger.error(
                        f"Failed to connect signal '{signal_name}' on '{widget}' to '{slot}': {e}"
                    )

    def add_reset_buttons(
        self,
        ui,
        widgets=None,
        *,
        types=(QtWidgets.QAbstractSpinBox,),
        skip=(),
        **set_reset_kwargs,
    ):
        """Give each matching value widget a per-field *reset-to-default* button.

        A thin batch wrapper over the option-box ``ResetOption`` (see
        ``widget.option_box.set_reset``): for every resolved widget it adds a
        small icon button beside the field that resets it to its registry
        default on click, or *bypasses* it to default (greyed, restorable) on
        Alt/Ctrl+click. The default is resolved from the UI's ``StateManager``
        at click time, so no per-field wiring is needed. Bypass is
        non-persistent — each session starts with every field active.

        Widget resolution mirrors :meth:`connect_multi`.

        Note:
            Prefer calling this *before* ``connect_multi`` (or anything that
            registers the same widgets as deferred) inside a slots ``__init__``.
            Wrapping a widget in its option-box reparents it, which invalidates
            the QUiLoader-built Python wrapper captured at defer time. The
            switchboard self-heals — ``_process_deferred_widgets`` re-resolves
            such widgets to their live wrapper — so a late wrap no longer crashes
            the panel ("Internal C++ object ... already deleted"); wrapping first
            simply avoids the extra re-resolution.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            widgets (str/list/None): Widgets to wire. A shorthand pattern
                (``'s000-4'``), an explicit widget list, or ``None`` to
                auto-discover every child of *types*.
            types (tuple): Widget class(es) auto-discovered when *widgets* is
                ``None`` (default: spin boxes). Pass e.g. ``(ComboBox,)`` for a
                panel whose parameters are combos.
            skip (str/iterable): objectName(s) and/or widget instance(s) to
                leave alone (e.g. fields sharing a tight row with a button).
            **set_reset_kwargs: Forwarded verbatim to ``option_box.set_reset``
                (e.g. ``reset=``, ``icon=``, ``tooltip=``, ``on_toggled=``).

        Returns:
            list: The widgets that received a reset button.

        Example:
            sb.add_reset_buttons(ui)                      # every spin box
            sb.add_reset_buttons(ui, skip=("s025", "s026", "s027"))
            sb.add_reset_buttons(ui, "cmb000-1")          # specific combos
        """
        if widgets is None:
            widgets = []
            for t in ptk.make_iterable(types):
                widgets.extend(ui.findChildren(t))
        elif isinstance(widgets, str):
            widgets = self.get_widgets_by_string_pattern(ui, widgets)
        else:
            widgets = ptk.make_iterable(widgets)

        # Split skip into names and widget identities so callers can pass either.
        skip = ptk.make_iterable(skip)
        skip_names = {s for s in skip if isinstance(s, str)}
        skip_ids = {id(s) for s in skip if not isinstance(s, str)}

        wired = []
        for widget in widgets:
            if not widget:
                continue
            name = widget.objectName()
            if name in skip_names or id(widget) in skip_ids:
                continue
            try:
                widget.option_box.set_reset(**set_reset_kwargs)
                wired.append(widget)
            except Exception as e:
                # Use the name captured above rather than re-reading the widget:
                # if set_reset failed because the underlying C++ object was torn
                # down mid-wrap, calling back into it here would raise again and
                # abort the whole batch.
                self.logger.debug(f"[add_reset_buttons] skipped '{name}': {e}")
        return wired

    def set_axis_for_checkboxes(self, checkboxes, axis, ui=None):
        """Set the given checkbox's check states to reflect the specified axis.

        Parameters:
            checkboxes (str/list): 3 or 4 (or six with explicit negative values) checkboxes.
            axis (str): Axis to set. Valid text: '-','X','Y','Z','-X','-Y','-Z' ('-' indicates a negative axis in a four checkbox setup)

        Example:
            set_axis_for_checkboxes('chk000-3', '-X') # Optional `ui` arg for the checkboxes.
        """
        if isinstance(checkboxes, (str)):
            if ui is None:
                ui = self.current_ui
            checkboxes = self.get_widgets_by_string_pattern(ui, checkboxes)

        prefix = "-" if "-" in axis else ""  # separate the prefix and axis
        coord = axis.strip("-")

        for chk in checkboxes:
            if any(
                [
                    chk.text() == prefix,
                    chk.text() == coord,
                    chk.text() == prefix + coord,
                ]
            ):
                chk.setChecked(True)

    def get_axis_from_checkboxes(self, checkboxes, ui=None, return_type="str"):
        """Get the intended axis value as a string or integer by reading the multiple checkbox's check states.

        Parameters:
            checkboxes (str/list): 3 or 4 (or six with explicit negative values) checkboxes.
                Valid: '-','X','Y','Z','-X','-Y','-Z' ('-' indicates a negative axis in a four checkbox setup)
            ui: The user interface context if required.
            return_type (str): The type of the return value, 'str' for string or 'int' for integer representation.

        Returns:
            (str or int) The axis value in lower case (e.g., '-x') or as an integer index (e.g., 0 for 'x', 1 for '-x').

        Example:
            get_axis_from_checkboxes('chk000-3', return_type='int')  # Could output 0, 1, 2, 3, 4, or 5
        """
        if isinstance(checkboxes, str):
            if ui is None:
                ui = self.current_ui
            checkboxes = self.get_widgets_by_string_pattern(ui, checkboxes)

        prefix = ""
        axis = ""
        for chk in checkboxes:
            if chk.isChecked():
                text = chk.text()
                if re.search("[^a-zA-Z]", text):  # Check for any non-alphabet character
                    prefix = "-"  # Assuming negative prefix if any non-alphabet character is present
                else:
                    axis = text.lower()

        # Mapping for axis strings to integers
        axis_map = {"x": 0, "-x": 1, "y": 2, "-y": 3, "z": 4, "-z": 5}

        # Construct the axis string with potential prefix
        axis_string = prefix + axis

        # Convert to integer index if needed
        if return_type == "int":
            return axis_map.get(axis_string, None)  # Return the corresponding integer

        # Return as string by default
        return axis_string

    def hide_unmatched_groupboxes(self, ui, unknown_tags) -> None:
        """Hides all QGroupBox widgets in the provided UI that do not match the unknown tags extracted
        from the provided tag string.

        Parameters:
            ui (QObject): The UI object in which to hide unmatched QGroupBox widgets.
            unknown_tags (list): A list of tags that should not be hidden. If empty, all groupboxes will be hidden.
        """
        # Find all QGroupBox widgets in the UI
        groupboxes = ui.findChildren(QtWidgets.QGroupBox)

        # Get the window
        window = ui.window() if isinstance(ui, QtWidgets.QWidget) else None

        visibility_changed = False
        # Hide all groupboxes that do not match the unknown tags
        for groupbox in groupboxes:
            should_hide = unknown_tags and groupbox.objectName() not in unknown_tags

            if should_hide and not groupbox.isHidden():
                groupbox.hide()
                visibility_changed = True
            elif not should_hide and groupbox.isHidden():
                groupbox.show()
                visibility_changed = True

        # Adjust window size
        if window and visibility_changed:
            QtCore.QTimer.singleShot(
                0, lambda: (window.adjustSize(), window.updateGeometry())
            )

    @staticmethod
    def invert_on_modifier(value):
        """Invert a numerical or boolean value if the alt key is pressed.

        Parameters:
            value (int, float, bool) = The value to invert.

        Returns:
            (int, float, bool)
        """
        modifiers = QtWidgets.QApplication.instance().keyboardModifiers()
        if modifiers not in (
            QtCore.Qt.AltModifier,
            QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier,
        ):
            return value

        if isinstance(value, bool):
            result = not value
        elif isinstance(value, (int, float)):
            result = abs(value) if value < 0 else -value
        else:
            result = value

        return result

    def progress(
        self,
        ui=None,
        total: Optional[int] = None,
        text: str = "",
    ):
        """Context manager for cooperative progress / task feedback.

        Routes to the active UI's :meth:`Footer.progress` when a footer
        is available; otherwise returns a no-op so callers run unchanged
        on UIs without one.

        Two modes from one entry point:

        * Pass ``total=N`` for a determinate progress bar (known step
          count). Tick with ``update(i + 1)``.
        * Omit *total* (the default) for an indeterminate "task
          indicator" marquee. Tick with bare ``update()`` calls between
          work chunks to drive the animation.

        Adapter-driven slots can omit *total* even for determinate
        progress: :func:`progress_adapter` auto-syncs the bar's max
        from the callback's ``total`` argument on the first tick, so
        the slot doesn't need to pre-compute the loop size.

        The slot dispatcher already shows a system wait cursor for the
        duration of every slot — this is for slots that want *richer*
        feedback in the footer.

        Parameters:
            ui: UI hosting the footer. Defaults to ``active_ui``.
            total: Step count for determinate mode; ``None`` (default)
                selects indeterminate / task-indicator mode.
            text: Optional status text shown alongside the bar.

        Yields:
            ``update(value=None, text=None) -> bool`` — returns ``False``
            if the user cancelled (Esc-hold). In task-indicator mode,
            call with no arguments to advance the marquee.

        Determinate example::

            with self.sb.progress(total=len(items), text="Copying") as update:
                for i, item in enumerate(items):
                    process(item)
                    if not update(i + 1):
                        break  # user cancelled

        Task-indicator example::

            with self.sb.progress(text="Working: Get Scene Info") as tick:
                step_one()
                tick()       # pumps the event loop, advances the bar
                step_two()
                tick()
        """
        if ui is None:
            ui = getattr(self, "active_ui", None) or getattr(self, "current_ui", None)
        footer = getattr(ui, "footer", None) if ui is not None else None
        if footer is not None and hasattr(footer, "progress"):
            return footer.progress(total=total, text=text)
        return _NoOpProgressContext()

    @staticmethod
    def progress_adapter(
        update: Callable[..., bool],
    ) -> Callable[..., bool]:
        """Adapt the footer ``update`` callable to the shape downstream
        ``progress_callback`` parameters typically expect.

        Handles both ecosystem shapes with one adapter:

        * ``cb(current, total, message)`` — mayatk pattern
          (``SceneAnalyzer.analyze``, ``MatUtils.get_mat_info``…).
        * ``cb(percent)`` — pythontk pattern
          (``MapCompositor``; expects ``0..100``).

        **Auto-syncs the bar's max from the callback's ``total``** so
        slots don't have to pre-declare the loop size:

            with self.sb.progress(text="Analyzing") as update:
                analyzer.analyze(
                    progress_callback=self.sb.progress_adapter(update),
                )

        On the first tick where ``total > 0``, the bar's maximum is
        retotalled to that value (and the bar switches out of
        indeterminate mode if it was pulsing). Subsequent ticks
        re-sync only when ``total`` actually changes — so a single
        adapter handles fixed-percent callbacks (``total=100``),
        per-item count callbacks (``total=N``), and indeterminate
        ones (``total=0``).

        The returned callable forwards the bool from ``update``, so
        downstreams that read it for cooperative cancellation get it
        for free.
        """
        # The bound ``update`` carries a reference to the host footer,
        # which exposes :meth:`set_progress_total`. Falls back to a
        # no-op for unbound callables (``_NoOpProgressContext._noop``).
        footer = getattr(update, "__self__", None)
        set_total = getattr(footer, "set_progress_total", None)

        def adapted(*args, **kwargs) -> bool:
            value = None
            text = None
            if args and args[0] is not None:
                try:
                    value = int(args[0])
                except (TypeError, ValueError):
                    value = None
            if len(args) >= 3 and args[2] is not None:
                text = str(args[2])
            # Sync bar max from callback's ``total``. ``set_progress_total``
            # short-circuits on matching state, so the per-tick cost is
            # one int comparison once the bar is in sync.
            if set_total is not None and len(args) >= 2 and args[1] is not None:
                try:
                    cb_total = int(args[1])
                except (TypeError, ValueError):
                    cb_total = 0
                if cb_total > 0:
                    set_total(cb_total)
            return bool(update(value, text))

        return adapted

    def message_box(
        self,
        string,
        *buttons,
        location="topMiddle",
        timeout=3,
        background=0.75,
    ):
        """Spawns a message box with the given text and optionally sets buttons.

        Parameters:
            string: HTML text to display.
            *buttons: Optional standard-button flags.  When provided the
                box is modal (``exec_``); otherwise a passive popup.
            location: Placement hint (default ``"topMiddle"``).
            timeout: Auto-dismiss seconds (default 3).
            background (bool/float/str): Controls the label background.
                ``True`` uses default dark grey at 50% opacity,
                ``False`` disables the background,
                a ``float`` 0–1 sets opacity (default 0.5),
                a CSS color ``str`` is used verbatim.
        """
        # Log text without HTML tags
        self.logger.info(f"# {re.sub('<.*?>', '', string)}")

        # Use a new instance for modal (exec) boxes to avoid reentrancy bugs
        if buttons:
            msg_box = self.registered_widgets.MessageBox(self.parent())
            msg_box.location = location
            msg_box.timeout = timeout
            msg_box.setStandardButtons(*buttons)
            msg_box.setText(string, background=background)
            return msg_box.exec_()
        else:
            # Safe to reuse for passive popups
            if not hasattr(self, "_messageBox"):
                self._messageBox = self.registered_widgets.MessageBox(self.parent())

            self._messageBox.location = location
            self._messageBox.timeout = timeout
            self._messageBox.setText(string, background=background)
            self._messageBox.show()
            return None

    def text_view_dialog(
        self,
        text: str = "",
        *buttons,
        title: str = "",
        size=(640, 400),
        monospace: bool = False,
        word_wrap: bool = True,
        background=False,
        parent=None,
    ):
        """Spawn a scrollable text-viewer window with optional buttons.

        Sibling to :meth:`message_box` for content too long or too
        structured for a passive popup (reports, log output, formatted
        result dumps). The viewer is a uitk :class:`WindowPanel`
        subclass with its own header, footer, and busy-indicator
        integration — same theming and chrome as the rest of the
        ecosystem's tool windows.

        Always non-modal: the viewer coexists with the host application
        (Maya, etc.) so the user can keep working while reading. The
        viewer's footer participates in the slot dispatcher's
        busy-indicator broadcast, so its own footer shows the
        "Working:" indicator if a slot is dispatched while it's open.

        Parameters:
            text: HTML or plain text to display. May be empty when the
                caller plans to populate via :meth:`TextViewBox.setText`
                / :meth:`append_text` after the call.
            *buttons: Standard-button name strings (``"Ok"``,
                ``"Cancel"``, etc. — same vocabulary as
                :meth:`message_box`). Buttons in the Accept / Reject /
                Destructive roles close the window; Apply / Reset /
                Help leave it open and surface their clicked name via
                ``TextViewBox.clicked_button``.
            title: Window title (shown in the header).
            size: Initial ``(width, height)``. Default ``(640, 400)``.
            monospace: Use a monospace body font. Default ``False``.
            word_wrap: Wrap long lines. ``False`` enables horizontal
                scrolling for tabular content. Default ``True``.
            background: Body background colour. Same semantics as
                :meth:`message_box`. Default ``False`` (widget default).
            parent: Anchor widget. Defaults to ``self.parent()``. The
                viewer reparents to ``parent.window()`` so it survives
                a transient invoker hiding.

        Returns:
            The :class:`TextViewBox` instance — the caller can stream
            more content via :meth:`TextViewBox.append_text` or close
            it later via :meth:`close`.
        """
        # Log a stripped, length-capped preview so reports don't flood
        # the log file the way an uncapped echo would.
        preview = re.sub("<.*?>", "", text or "")
        if len(preview) > 500:
            preview = preview[:500] + "…"
        if preview:
            self.logger.info(f"# {preview}")

        dlg = self.registered_widgets.TextViewBox(
            parent=parent if parent is not None else self.parent(),
            title=title,
            monospace=monospace,
            word_wrap=word_wrap,
        )
        if size:
            dlg.resize(*size)
        if text:
            dlg.setText(text, background=background)
        if buttons:
            dlg.setStandardButtons(*buttons)

        # Keep alive via the existing gc_protect helper so the caller
        # can return without the window being collected.
        self.gc_protect(dlg)
        dlg.show()
        return dlg

    @staticmethod
    def file_dialog(
        file_types: Union[str, List[str]] = ["*.*"],
        title: str = "Select files to open",
        start_dir: str = "/home",
        filter_description: str = "All Files",
        allow_multiple: bool = True,
    ) -> Union[str, List[str]]:
        """Open a file dialog to select files of the given type(s) using qtpy.

        Parameters:
            file_types (Union[str, List[str]]): Extensions of file types to include. Can be a string or a list of strings.
                Default is ["*.*"], which includes all files.
            title (str): Title of the file dialog. Default is "Select files to open."
            start_dir (str): Initial directory to display in the file dialog. Default is "/home."
            filter_description (str): Description for the filter applied to the file types. Default is "All Files."
            allow_multiple (bool): Whether to allow multiple file selection. Default is True.

        Returns:
            Union[str, List[str]]: A string if a single file is selected, or a list of strings if multiple files are selected.

        Example:
            files = file_dialog(file_types=["*.png", "*.jpg"], title="Select images", filter_description="Images")
        """
        options = QtWidgets.QFileDialog.Options()
        if allow_multiple:
            options |= QtWidgets.QFileDialog.ReadOnly

        file_types_string = f"{filter_description} ({' '.join(file_types)})"

        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            None, title, start_dir, file_types_string, options=options
        )

        return files if allow_multiple else files[0] if files else None

    @staticmethod
    def dir_dialog(title: str = "Select a directory", start_dir: str = "/home") -> str:
        """Open a directory dialog to select a directory using qtpy.

        Parameters:
            title (str): Title of the directory dialog. Default is "Select a directory."
            start_dir (str): Initial directory to display in the dialog. Default is "/home."

        Returns:
            str: Selected directory path.

        Example:
            directory_path = dir_dialog(title="Select a project folder")
        """
        options = QtWidgets.QFileDialog.Options()
        directory_path = QtWidgets.QFileDialog.getExistingDirectory(
            None, title, start_dir, options=options
        )

        return directory_path

    @staticmethod
    def save_file_dialog(
        file_types: Union[str, List[str]] = ["*.*"],
        title: str = "Save file",
        start_dir: str = "/home",
        filter_description: str = "All Files",
    ) -> Optional[str]:
        """Open a save-file dialog to choose a destination path.

        Parameters:
            file_types: Extensions to include (e.g. ``["*.wav"]``).
                Default is ``["*.*"]``.
            title: Dialog window title.
            start_dir: Initial directory / suggested file path.
            filter_description: Label for the file-type filter.

        Returns:
            The chosen file path, or *None* if the dialog was cancelled.

        Example:
            path = save_file_dialog(
                file_types=["*.wav"],
                title="Export audio",
                filter_description="WAV Files",
            )
        """
        if isinstance(file_types, str):
            file_types = [file_types]

        file_types_string = f"{filter_description} ({' '.join(file_types)})"

        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            None, title, start_dir, file_types_string
        )

        return path or None

    @staticmethod
    def input_dialog(
        title: str = "Input",
        label: str = "Enter value:",
        text: str = "",
        parent: QtWidgets.QWidget = None,
        placeholder: str = "",
        validate: callable = None,
        error_text: str = "Invalid input.",
    ) -> str:
        """Show a modal text-input dialog and return the entered string.

        Builds a small custom ``QDialog`` so it can be properly parented,
        styled to match the host application, and extended with inline
        validation feedback.  Falls back gracefully when no parent is
        supplied.

        Parameters:
            title: Window title.
            label: Descriptive label above the text field.
            text: Pre-filled text (e.g. the current value for rename).
            parent: Optional parent widget for correct modality and
                positioning.  Accepts any ``QWidget``.
            placeholder: Greyed-out hint shown when the field is empty.
            validate: Optional ``callable(text) -> bool``.  While it
                returns ``False`` the OK button stays disabled and a
                brief *error_text* is shown beneath the field.
            error_text: Message displayed when *validate* returns
                ``False``.

        Returns:
            str: The stripped text the user entered, or ``None`` if the
            dialog was cancelled or closed.
        """
        dlg = QtWidgets.QDialog(parent)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(280)

        layout = QtWidgets.QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(6)

        lbl = QtWidgets.QLabel(label)
        layout.addWidget(lbl)

        line = QtWidgets.QLineEdit(text)
        if placeholder:
            line.setPlaceholderText(placeholder)
        line.selectAll()
        layout.addWidget(line)

        err_lbl = QtWidgets.QLabel("")
        err_lbl.setStyleSheet("color: #e05555; font-size: 11px;")
        err_lbl.setVisible(False)
        layout.addWidget(err_lbl)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        layout.addWidget(btn_box)

        ok_btn = btn_box.button(QtWidgets.QDialogButtonBox.Ok)

        def _validate_text(t=None):
            if t is None:
                t = line.text()
            if validate is not None:
                valid = validate(t)
                ok_btn.setEnabled(valid)
                err_lbl.setText("" if valid else error_text)
                err_lbl.setVisible(not valid)
            else:
                ok_btn.setEnabled(bool(t.strip()))

        line.textChanged.connect(_validate_text)
        _validate_text(text)

        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)

        # Inherit parent stylesheet so the dialog matches the host theme.
        if parent is not None:
            ss = parent.styleSheet()
            if ss:
                dlg.setStyleSheet(ss)

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            result = line.text().strip()
            return result if result else None
        return None

    @staticmethod
    def simulate_key_press(
        ui, key=QtCore.Qt.Key_F12, modifiers=QtCore.Qt.NoModifier, release=False
    ):
        """Simulate a key press event for the given UI and optionally release the keyboard.

        Parameters:
            ui (QtWidgets.QWidget): The UI widget to simulate the key press for.
            key (QtCore.Qt.Key): The key to simulate. Defaults to QtCore.Qt.Key_F12.
            modifiers (QtCore.Qt.KeyboardModifiers): The keyboard modifiers to apply. Defaults to QtCore.Qt.NoModifier.
            release (bool): Whether to simulate a key release event.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError("The 'ui' parameter must be a QWidget or a subclass.")

        # Create and post the key press event
        press_event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, modifiers)
        QtWidgets.QApplication.postEvent(ui, press_event)

        # Optionally create and post the key release event
        if release:
            release_event = QtGui.QKeyEvent(QtCore.QEvent.KeyRelease, key, modifiers)
            QtWidgets.QApplication.postEvent(ui, release_event)

    def defer_with_timer(self, func: callable, *args, ms: int = 300, **kwargs) -> None:
        """Defer execution of any callable with arguments after a delay.

        Parameters:
            func (callable): The function to be called after the delay.
            *args: Positional arguments for the function.
            ms (int, optional): Delay in milliseconds before execution. Default is 300.
            **kwargs: Keyword arguments for the function.

        Raises:
            ValueError: If func is not callable.
            TypeError: If ms is not an integer.
        """
        if not callable(func):
            raise ValueError(
                f"[defer_with_timer] Expected a callable, got {type(func).__name__}"
            )

        if not isinstance(ms, int):
            raise TypeError(
                f"[defer_with_timer] ms must be an integer, got {type(ms).__name__}"
            )

        def safe_call():
            """Executes the function safely and logs any exceptions."""
            try:
                func(*args, **kwargs)
            except Exception as e:
                self.logger.error(
                    f"[defer_with_timer] Exception in deferred call to {func.__name__}: {e}"
                )
                self.logger.debug(traceback.format_exc())
                if args and "ms" not in kwargs and isinstance(args[0], int):
                    raise TypeError(
                        "[defer_with_timer] Did you mean to pass ms as a keyword argument?"
                    )

        # Schedule the deferred execution
        QtCore.QTimer.singleShot(ms, safe_call)

    def gc_protect(self, obj=None, clear=False):
        """
        Protect the given object(s) from garbage collection by holding a strong reference.
        Parameters:
            obj (obj/list): The obj(s) to add to the protected dict.
            clear (bool): Clear the dict before adding any given object(s).
        Returns:
            dict: The protected objects.
        """
        if not hasattr(self, "_gc_protect"):
            self._gc_protect = {}

        if clear:
            self._gc_protect.clear()

        for o in ptk.make_iterable(obj):
            key = o.objectName() or id(o)
            self._gc_protect[key] = o

            # Remove from dict when destroyed
            def _cleanup(key=key):
                self._gc_protect.pop(key, None)

            try:
                o.destroyed.connect(_cleanup)
            except AttributeError:
                self.logger.debug(
                    f"Object {o} does not have a 'destroyed' signal. Cannot connect to it."
                )

        return self._gc_protect

    @staticmethod
    def modal_menu(content_fn, parent=None, **kwargs):
        """Show a themed modal Menu popup, block until dismissed.

        Convenience wrapper around :meth:`Menu.run_modal`.  See that method
        for full parameter documentation.

        Parameters:
            content_fn (callable): ``content_fn(menu, state)`` — populate the
                menu with widgets and store result data in *state*.
            parent (QWidget, optional): Parent widget.
            **kwargs: Forwarded to :meth:`Menu.run_modal` (``title``,
                ``buttons``, ``size``, ``min_size``, ``center``, etc.).

        Returns:
            dict or None: The *state* dict on accept, ``None`` on reject.
        """
        from uitk.widgets.menu import Menu

        return Menu.run_modal(content_fn, parent=parent, **kwargs)


class _NoOpProgressContext:
    """Fallback context for SwitchboardUtilsMixin.progress() when no footer
    is available. Yields a no-op update callable so caller code runs
    unmodified — just without visible progress feedback.
    """

    def __enter__(self):
        return self._noop

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    @staticmethod
    def _noop(value=None, text=None):
        return True


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    ...

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
