# !/usr/bin/python
# coding=utf-8
import re
import traceback
from typing import List, Union
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

        # Hide all groupboxes that do not match the unknown tags
        for groupbox in groupboxes:
            if unknown_tags and groupbox.objectName() not in unknown_tags:
                groupbox.hide()
            else:
                groupbox.show()

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

        if type(value) in (int, float):
            result = abs(value) if value < 0 else -value
        elif type(value) == bool:
            result = True if value else False

        return result

    def message_box(self, string, *buttons, location="topMiddle", timeout=3):
        """Spawns a message box with the given text and optionally sets buttons."""
        # Log text without HTML tags
        self.logger.info(f"# {re.sub('<.*?>', '', string)}")

        # Use a new instance for modal (exec) boxes to avoid reentrancy bugs
        if buttons:
            msg_box = self.registered_widgets.MessageBox(self.parent())
            msg_box.location = location
            msg_box.timeout = timeout
            msg_box.setStandardButtons(*buttons)
            msg_box.setText(string)
            return msg_box.exec_()
        else:
            # Safe to reuse for passive popups
            if not hasattr(self, "_messageBox"):
                self._messageBox = self.registered_widgets.MessageBox(self.parent())

            self._messageBox.location = location
            self._messageBox.timeout = timeout
            self._messageBox.setText(string)
            self._messageBox.show()
            return None

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
    def input_dialog(
        title: str = "Input", label: str = "Enter value:", text: str = ""
    ) -> str:
        """Open an input dialog to get a string from the user.

        Parameters:
            title (str): Title of the dialog.
            label (str): Label text.
            text (str): Default text.

        Returns:
            str: The entered text, or None if cancelled.
        """
        text, ok = QtWidgets.QInputDialog.getText(None, title, label, text=text)
        if ok:
            return text
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


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    ...

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
