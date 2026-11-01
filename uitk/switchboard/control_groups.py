# !/usr/bin/python
# coding=utf-8
import re
from typing import List
from qtpy import QtWidgets, QtCore
import pythontk as ptk

# Lock-toggle tints used by :meth:`Switchboard.link_spinboxes`, taken
# from the channel-box lock column so every lock in the ecosystem reads the
# same: desaturated blue while locked, dim grey while unlocked. Unlocked is a
# perfectly normal state, so it must NOT use ToggleOption's error-red default
# (which is there to flag the control that stopped something working).
_LOCK_ACTIVE_COLOR = "#8A9BB0"
_LOCK_INACTIVE_COLOR = "#555555"


class _ControlGroups:
    """Builders that wire a set of controls as one group, behind the Switchboard:
    button groups, multi-toggles, batch connects, reset buttons, linked spin boxes,
    axis check boxes and tag-matched group boxes. Stateless; reads the
    Switchboard (its current UI, ``STATE_PREFIX``, name patterns) at call time.
    """

    def __init__(self, sb, values):
        self._sb = sb
        self._values = values  # what a control's value and change signal are

    def create_button_groups(
        self,
        ui: QtWidgets.QWidget,
        *args: str,
        allow_deselect: bool = False,
        allow_multiple: bool = False,
    ) -> List[QtWidgets.QButtonGroup]:
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
            widgets = self._sb.get_widgets_by_string_pattern(ui, buttons)
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
        # Extract state mapping kwargs (those starting with 'on_')
        state_map = {}
        immediate_kwargs = {}

        for key, value in list(kwargs.items()):
            if key.startswith(self._sb.STATE_PREFIX):
                state_value = key[len(self._sb.STATE_PREFIX) :]  # Remove 'on_' prefix
                # Store the string representation as key - will match against actual signal values
                state_map[state_value] = value
            else:
                immediate_kwargs[key] = value

        # If trigger provided, set up connection
        if trigger is not None:
            trigger_widget = self._values.resolve_ui_widget(ui, trigger)
            if trigger_widget is None:
                self._sb.logger.warning(
                    f"Widget '{trigger}' not found in UI, cannot connect toggle."
                )
                return

            # Default to the widget's natural change signal ('toggled' if unknown).
            if signal is None:
                signal = self._values.value_change_signal(trigger_widget) or "toggled"

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
                    self._sb.toggle_multi(ui, **toggle_kwargs)

            # Connect the signal
            try:
                signal_obj = getattr(trigger_widget, signal, None)
                if signal_obj and callable(getattr(signal_obj, "connect", None)):
                    signal_obj.connect(toggle_callback)
                else:
                    self._sb.logger.warning(
                        f"Signal '{signal}' not found on widget '{trigger_widget}'"
                    )
                    return
            except Exception as e:
                self._sb.logger.error(f"Failed to connect toggle: {e}", exc_info=True)
                return
            if apply_now:
                toggle_callback(self._values.read_signal_value(trigger_widget, signal))
            return

        # Original immediate toggle behavior
        for k in immediate_kwargs:  # property_ ie. setUnChecked
            # get_widgets_by_string_pattern returns a widget list from a string of object_names.
            widgets = self._sb.get_widgets_by_string_pattern(ui, immediate_kwargs[k])

            state = True
            # strips 'Un' and sets the state from True to False. ie. 'setUnChecked' becomes 'setChecked' (False)
            if "Un" in k:
                k = k.replace("Un", "")
                state = False

            # set the property state for each widget in the list.
            for w in widgets:
                getattr(w, k)(state)

    def connect_multi(self, ui, widgets, signals, slots):
        if isinstance(widgets, str):
            widgets = self._sb.get_widgets_by_string_pattern(ui, widgets)
        else:
            widgets = ptk.make_iterable(widgets)

        # Ensure the other arguments are iterable
        signals = ptk.make_iterable(signals)
        slots = ptk.make_iterable(slots)

        self._sb.logger.debug(
            f"[connect_multi] Connecting: {widgets} to {signals} -> {slots}"
        )

        for widget in widgets:
            if not widget:
                self._sb.logger.warning(f"Skipped: Invalid widget '{widget}'")
                continue

            for signal_name in signals:
                try:
                    signal = getattr(widget, signal_name, None)
                    if not signal:
                        self._sb.logger.warning(
                            f"Skipped: Widget '{widget}' has no signal '{signal_name}'"
                        )
                        continue

                    for slot in slots:
                        if not callable(slot):
                            self._sb.logger.warning(
                                f"Skipped: Slot '{slot}' is not callable"
                            )
                            continue

                        signal.connect(slot)

                except Exception as e:
                    # ``slots``, not the loop's ``slot``: a failure before the
                    # slot loop (the getattr) would leave it unbound, and the
                    # report itself would raise NameError out of the method.
                    self._sb.logger.error(
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
        wired = []
        for widget in self._resolve_option_widgets(ui, widgets, types, skip):
            try:
                widget.option_box.set_reset(**set_reset_kwargs)
                wired.append(widget)
            except Exception as e:
                self._sb.logger.debug(f"[add_reset_buttons] skipped a widget: {e}")
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
            widgets = self._sb.get_widgets_by_string_pattern(ui, widgets)
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
                self._sb.logger.debug(f"[link_spinboxes] skipped a widget: {e}")
        return wired

    def set_axis_for_checkboxes(self, checkboxes, axis, ui=None):
        if isinstance(checkboxes, (str)):
            if ui is None:
                ui = self._sb.current_ui
            checkboxes = self._sb.get_widgets_by_string_pattern(ui, checkboxes)

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
        if isinstance(checkboxes, str):
            if ui is None:
                ui = self._sb.current_ui
            checkboxes = self._sb.get_widgets_by_string_pattern(ui, checkboxes)

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
