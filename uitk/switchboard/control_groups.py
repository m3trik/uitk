# !/usr/bin/python
# coding=utf-8
import re
from typing import List
from qtpy import QtWidgets, QtCore
import pythontk as ptk

# Lock-toggle tints used by :meth:`SwitchboardControlGroupsMixin.link_spinboxes`, taken
# from the channel-box lock column so every lock in the ecosystem reads the
# same: desaturated blue while locked, dim grey while unlocked. Unlocked is a
# perfectly normal state, so it must NOT use ToggleOption's error-red default
# (which is there to flag the control that stopped something working).
_LOCK_ACTIVE_COLOR = "#8A9BB0"
_LOCK_INACTIVE_COLOR = "#555555"


class SwitchboardControlGroupsMixin:
    """Builders that wire a set of controls as one group: button groups,
    multi-toggles, batch connects, reset buttons, linked spin boxes, axis
    check boxes and tag-matched group boxes."""

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
            if any(type(w) is not widget_type for w in widgets):
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

    def toggle_multi(self, ui, trigger=None, signal=None, apply_now=True, **kwargs):
        """Set multiple boolean properties for multiple widgets at once, or connect a trigger to do so automatically.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            trigger (str/QWidget, optional): If provided, connects this widget's signal to toggle the others.
                                             If None, toggles immediately.
            signal (str, optional): Signal name to connect (only used when trigger is provided).
                                    Default: the widget's natural change signal (``toggled`` for
                                    buttons, ``currentIndexChanged`` for combos, …; ``toggled`` if unknown).
            apply_now (bool): Trigger mode only. Also apply the mapping for the trigger's
                              CURRENT value at wire time (default True) — a widget restored
                              from session state before the connection exists would otherwise
                              leave its dependants in the wrong state until the user touches it.
            **kwargs: The properties to modify. Can be:
                     - Direct properties (immediate mode): setChecked, setUnChecked, setEnabled, setDisabled, etc.
                       Value: string of object_names separated by ',' ie. 'b000-12,b022'
                     - State mapping (trigger mode): on_<state>={...}, on_default={...}
                       Value: dict of toggle_multi kwargs to apply for that state

        For the common "enable X while Y says so" dependency prefer :meth:`enable_when` —
        one predicate instead of a mirrored ``on_True`` / ``on_False`` pair.

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
            trigger_widget = self._resolve_ui_widget(ui, trigger)
            if trigger_widget is None:
                self.logger.warning(
                    f"Widget '{trigger}' not found in UI, cannot connect toggle."
                )
                return

            # Default to the widget's natural change signal ('toggled' if unknown).
            if signal is None:
                signal = self._value_change_signal(trigger_widget) or "toggled"

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
                    return
            except Exception as e:
                self.logger.error(f"Failed to connect toggle: {e}", exc_info=True)
                return
            if apply_now:
                toggle_callback(self._read_signal_value(trigger_widget, signal))
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
                    # ``slots``, not the loop's ``slot``: a failure before the
                    # slot loop (the getattr) would leave it unbound, and the
                    # report itself would raise NameError out of the method.
                    self.logger.error(
                        f"Failed to connect signal '{signal_name}' on '{widget}' to {slots}: {e}",
                        exc_info=True,
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
        wired = []
        for widget in self._resolve_option_widgets(ui, widgets, types, skip):
            try:
                widget.option_box.set_reset(**set_reset_kwargs)
                wired.append(widget)
            except Exception as e:
                self.logger.debug(f"[add_reset_buttons] skipped a widget: {e}")
        return wired

    def _resolve_option_widgets(self, ui, widgets, types, skip):
        """Resolve + skip-filter the widget set for the option-box batch helpers.

        Shared by :meth:`add_reset_buttons` and :meth:`link_spinboxes`: *widgets*
        may be a shorthand pattern string, an explicit list, or ``None`` to
        auto-discover every child of *types*; *skip* (objectNames and/or widget
        instances) is removed. Runs before any wrapping, so every resolved
        widget is still live — a dead one is dropped defensively.
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

        out = []
        for w in widgets:
            if not w:
                continue
            try:
                name = w.objectName()
            except RuntimeError:
                continue
            if name in skip_names or id(w) in skip_ids:
                continue
            out.append(w)
        return out

    def link_spinboxes(
        self,
        ui,
        widgets=None,
        *,
        types=(QtWidgets.QAbstractSpinBox,),
        skip=(),
        icon: str = "lock",
        icon_off: str = "unlock",
        tooltip_on: str = "Linked. Changing this shifts the other linked fields by the same amount. Click to unlink.",
        tooltip_off: str = "Unlinked. Click to link this field so it moves with the others.",
        initial: bool = False,
        active_color: str = _LOCK_ACTIVE_COLOR,
        disabled_color: str = _LOCK_INACTIVE_COLOR,
        **set_toggle_kwargs,
    ):
        """Give each spin box a *lock* toggle that links locked boxes by an equal delta.

        A batch companion to :meth:`add_reset_buttons`: each resolved widget gets
        an option-box lock toggle (a persisted :class:`ToggleOption`). When a
        **locked** box's value changes, every *other* **locked** box is shifted by
        the same delta; unlocked boxes are independent. Each field opts in on its
        own, so the user can link any subset (e.g. X+Y but not Z).

        The lock state persists per widget (via the ToggleOption's own settings),
        so a session reopens with the same fields linked. Composes with
        :meth:`add_reset_buttons` — a field can carry both a reset and a lock
        button (option ordering keeps ``reset`` before ``toggle``).

        Widget resolution mirrors :meth:`connect_multi` / :meth:`add_reset_buttons`.
        Call it in the same place (before ``connect_multi``) for the same
        wrap-before-defer reason.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            widgets (str/list/None): Widgets to wire — a shorthand pattern
                (``'s003-5'``), an explicit list, or ``None`` to auto-discover
                every child of *types*.
            types (tuple): Widget class(es) auto-discovered when *widgets* is
                ``None`` (default: spin boxes).
            skip (str/iterable): objectName(s) and/or widget instance(s) to leave
                alone.
            icon / icon_off: Toggle icons for the linked / unlinked states.
            tooltip_on / tooltip_off: Toggle tooltips.
            initial (bool): Starting lock state (default unlinked). Overridden by
                any persisted per-field value.
            active_color / disabled_color: Icon tints for the locked / unlocked
                states — the channel-box lock convention (see the module
                constants). Overrides ``ToggleOption``'s error-red default,
                which would misread an unlocked field as a fault.
            **set_toggle_kwargs: Forwarded verbatim to ``option_box.set_toggle``.

        Returns:
            list: The widgets that received a lock toggle.
        """
        from uitk.widgets.optionBox.options.toggle import ToggleOption

        widgets = self._resolve_option_widgets(ui, widgets, types, skip)
        state = getattr(ui, "state", None)

        # Read the lock state live from each field's ToggleOption rather than
        # shadowing it: ToggleOption restores its persisted state silently (no
        # ``toggled`` emission), so a shadow dict seeded from the signal would
        # miss a field that reopened already-locked.
        def _is_locked(w):
            try:
                opt = w.option_box.find_option(ToggleOption)
            except Exception:
                return False
            return bool(opt and opt.is_on)

        # Last-seen value per field, so a change yields a delta. Re-baselined on
        # every change (locked or not) so toggling lock on mid-session doesn't
        # replay a stale delta.
        prev = {}
        # Re-entrancy guard: the equal-delta writes below emit ``valueChanged``
        # on the other fields, which must not recurse into another propagation.
        guard = {"active": False}

        def _make_handler(src):
            def _on_changed(val):
                if guard["active"]:
                    prev[src] = val
                    return
                last = prev.get(src, val)
                prev[src] = val
                # During a programmatic apply -- a state restore, a preset
                # load, a reset (``state.is_applying``) -- values land field by
                # field, not by a user gesture: re-baseline only. Otherwise
                # restoring a locked field would fire a spurious delta into its
                # locked siblings and corrupt their restored values.
                if state is not None and getattr(state, "is_applying", False):
                    return
                if not _is_locked(src):
                    return
                delta = val - last
                if not delta:
                    return
                guard["active"] = True
                try:
                    for other in widgets:
                        if other is src or not _is_locked(other):
                            continue
                        other.setValue(other.value() + delta)
                        prev[other] = other.value()
                finally:
                    guard["active"] = False

            return _on_changed

        def _apply(w):
            prev[w] = w.value()
            w.option_box.set_toggle(
                icon=icon,
                icon_off=icon_off,
                tooltip_on=tooltip_on,
                tooltip_off=tooltip_off,
                initial=initial,
                active_color=active_color,
                disabled_color=disabled_color,
                **set_toggle_kwargs,
            )
            w.valueChanged.connect(_make_handler(w))

        wired = []
        for widget in widgets:
            try:
                _apply(widget)
                wired.append(widget)
            except Exception as e:
                self.logger.debug(f"[link_spinboxes] skipped a widget: {e}")
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
