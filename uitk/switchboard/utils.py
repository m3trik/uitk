# !/usr/bin/python
# coding=utf-8
import re
import traceback
import warnings
from typing import Any, Callable, Dict, List, Optional, Union
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk

from uitk.managers.value_manager import ValueManager
from uitk.managers.cursor_manager import CursorManager

# Compatibility re-export (2026-09, one release): ``uitk.switchboard`` still
# publishes ``OverrideCursorGuard`` through this module. New code imports it
# from ``uitk`` (or ``uitk.managers.cursor_manager``).
from uitk.managers.cursor_manager import OverrideCursorGuard  # noqa: F401


# Lock-toggle tints used by :meth:`SwitchboardUtilsMixin.link_spinboxes`, taken
# from the channel-box lock column so every lock in the ecosystem reads the
# same: desaturated blue while locked, dim grey while unlocked. Unlocked is a
# perfectly normal state, so it must NOT use ToggleOption's error-red default
# (which is there to flag the control that stopped something working).
_LOCK_ACTIVE_COLOR = "#8A9BB0"
_LOCK_INACTIVE_COLOR = "#555555"


class SwitchboardUtilsMixin:
    """Utility methods for widget positioning, centering, and screen geometry."""

    @staticmethod
    def _enable_when_key(condition, invert):
        """Comparable identity of a non-callable ``enable_when`` rule.

        A set / list / tuple is normalized the way the membership branch itself
        normalizes it, so the same rule spelled ``{1, 2}`` and ``[1, 2]`` compares
        equal and is not reported as a conflict. Callables have no usable identity
        here (a re-run ``_init`` builds a fresh lambda every time), so the caller
        only compares when both conditions are non-callable.
        """
        if isinstance(condition, (set, frozenset, list, tuple)):
            return ("membership", frozenset(condition), invert)
        return ("value", condition, invert)

    @staticmethod
    def busy_cursor(shape=QtCore.Qt.WaitCursor):
        """Application busy cursor for the duration of a ``with`` block.

        :meth:`CursorManager.busy` reached through the switchboard, for slot
        code that runs OUTSIDE dispatch (a worker callback, a method called
        directly). Every dispatched slot is already bracketed in one, so a
        slot body never needs it — and never touches
        ``QApplication.setOverrideCursor`` directly: the raw pair pops the top
        of the stack rather than its own entry.
        """
        return CursorManager.busy(shape)

    @staticmethod
    def pop_override_cursor_stack(app):
        """Deprecated alias of :meth:`CursorManager.pop_stack` (2026-09; removed
        in the release after). The new home takes ``pop_stack(app)``."""
        warnings.warn(
            "SwitchboardUtilsMixin.pop_override_cursor_stack is deprecated; "
            "use uitk.CursorManager.pop_stack(app).",
            DeprecationWarning,
            stacklevel=2,
        )
        return CursorManager.pop_stack(app)

    @staticmethod
    def push_override_cursor_stack(app, saved):
        """Deprecated alias of :meth:`CursorManager.push_stack` (2026-09; removed
        in the release after). The new home takes ``push_stack(saved, app)``."""
        warnings.warn(
            "SwitchboardUtilsMixin.push_override_cursor_stack is deprecated; "
            "use uitk.CursorManager.push_stack(saved, app).",
            DeprecationWarning,
            stacklevel=2,
        )
        CursorManager.push_stack(saved, app)

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
            padding_x (int, optional): Additional width from the widget's minimum size or relative widget. If not specified, the widget's current width is used. A maximumWidth too small to fit the result is raised to fit, unless minimumWidth == maximumWidth (a deliberate fixed-size lock, left untouched).
            padding_y (int, optional): Additional height from the widget's minimum size or relative widget. If not specified, the widget's current height is used. Same maximumHeight handling as padding_x.
            relative (QWidget, optional): If given, use this widget's current size as the base size for resizing.
        """
        # Resize the widget if padding values are provided
        if padding_x is not None or padding_y is not None:
            p1 = widget.rect().center()

            w = widget if not relative else relative
            x = w.minimumSizeHint().width() if padding_x is not None else w.width()
            y = w.minimumSizeHint().height() if padding_y is not None else w.height()

            target_w = x + (padding_x if padding_x is not None else 0)
            target_h = y + (padding_y if padding_y is not None else 0)

            # padding_x/padding_y request a content-fit size; a stale
            # Designer-authored maximumSize (sized for different/shorter
            # text) would otherwise silently truncate widget.resize() below,
            # defeating that request. Raise the ceiling rather than let it --
            # but only where maximumWidth/Height is acting as a loose ceiling
            # (minimum < maximum). Where the two are equal, that's a
            # deliberate fixed-size lock (e.g. a square icon tile) rather
            # than a stale leftover, and must not be widened out from under it.
            if (
                padding_x is not None
                and target_w > widget.maximumWidth()
                and widget.maximumWidth() > widget.minimumWidth()
            ):
                widget.setMaximumWidth(target_w)
            if (
                padding_y is not None
                and target_h > widget.maximumHeight()
                and widget.maximumHeight() > widget.minimumHeight()
            ):
                widget.setMaximumHeight(target_h)

            widget.resize(target_w, target_h)
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

        def extract_parts(name):
            """Extract alphabetic and numeric parts from a given name using regular expressions."""
            return re.findall(r"([a-zA-Z]+)|(\d+)", name)

        names = re.split(r",\s*", name_string)
        unpacked_names = []
        last_prefix = None
        last_width = 3  # zero-pad width for bare-number continuations

        for name in names:
            parts = extract_parts(name)
            # Keep the raw numeric tokens so the zero-pad width can be derived
            # from the source string rather than hard-coded.
            digit_tokens = [p[1] for p in parts if p[1]]

            if not digit_tokens:
                # A name with no numeric token passes through verbatim (e.g.
                # 'grp_basic'); a purely non-alphanumeric token is skipped.
                if parts:
                    unpacked_names.append(name)
                    if parts[0][0]:
                        last_prefix = parts[0][0]
                continue

            prefix = parts[0][0]
            width = len(digit_tokens[0])

            if len(digit_tokens) >= 2:
                # Range notation, e.g. 'chk000-2' (reverse ranges yield nothing).
                start, stop = int(digit_tokens[0]), int(digit_tokens[1])
                unpacked_names.extend(
                    prefix + str(num).zfill(width) for num in range(start, stop + 1)
                )
                last_prefix, last_width = prefix, width
            elif not prefix:
                # Bare number — continuation of the previous prefix, e.g. the
                # '1' in 'chk000, 1'.
                unpacked_names.append(
                    (last_prefix or "") + digit_tokens[0].zfill(last_width)
                )
            else:
                # Single prefixed name, e.g. 'chk000'.
                unpacked_names.append(name)
                last_prefix, last_width = prefix, width

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

    # ------------------------------------------------------------------
    # Widget value / signal plumbing shared by toggle_multi and enable_when
    # ------------------------------------------------------------------

    #: (widget type, value getter) — most-specific first. The one table behind
    #: ``toggle_multi``'s initial apply and ``enable_when``'s reads, so "what
    #: does this control's value mean" is decided once. A leading underscore
    #: names a reader on this mixin; anything else is a zero-arg widget method.
    #: signal name -> zero-arg widget getter that yields what that signal would
    #: deliver for the CURRENT state (an initial apply runs before any signal).
    _SIGNAL_VALUE_READERS = {
        "toggled": "isChecked",
        "clicked": "isChecked",
        "stateChanged": "checkState",
        "currentIndexChanged": "currentIndex",
        "currentTextChanged": "currentText",
        "textChanged": "text",
        "valueChanged": "value",
    }

    _WIDGET_VALUE_READERS = (
        (QtWidgets.QComboBox, "_combo_value"),
        (QtWidgets.QAbstractButton, "isChecked"),
        (QtWidgets.QGroupBox, "isChecked"),
        (QtWidgets.QSpinBox, "value"),
        (QtWidgets.QDoubleSpinBox, "value"),
        (QtWidgets.QAbstractSlider, "value"),
        (QtWidgets.QLineEdit, "text"),
        (QtWidgets.QPlainTextEdit, "toPlainText"),
        (QtWidgets.QTextEdit, "toPlainText"),
    )

    #: What :meth:`value_from` may WRITE — DERIVED from the reader table above,
    #: so the pair cannot drift: a rule can always write back what
    #: :meth:`enable_when` / :meth:`text_from` read. The setters themselves are
    #: NOT restated here — ``ValueManager.set_value`` already owns "how do I set
    #: this widget's value" for every one of these types (and coerces sensibly:
    #: ``"8"`` into a spin box, a truthy value into a checkable button, never a
    #: button's LABEL). Only combos are written locally, and for a reason that
    #: is combo-specific rather than a flaw in the manager — see
    #: :meth:`_set_combo_value`.
    #:
    #: Deriving it, rather than gating on ``ValueManager.is_supported_widget``,
    #: is what makes reader/writer symmetry STRUCTURAL: the two agree today
    #: (that list was corrected in the same pass), but only the derivation
    #: keeps them agreeing when a type is added to the reader table.
    _WIDGET_VALUE_WRITABLE = tuple(t for t, _ in _WIDGET_VALUE_READERS)

    #: Change signals for types the Switchboard's ``default_signals`` table
    #: (the slot-wiring SSoT) doesn't name, or names with a click-only signal
    #: (``QPushButton: clicked`` never fires on a programmatic ``setChecked``,
    #: which is exactly what a dependency rule has to see).
    _VALUE_CHANGE_SIGNALS = (
        (QtWidgets.QAbstractButton, "toggled"),
        (QtWidgets.QGroupBox, "toggled"),
        (QtWidgets.QPlainTextEdit, "textChanged"),
    )

    @staticmethod
    def _combo_value(combo):
        """A combo's value is its ``currentData`` when items carry data, else
        its index — the same reading a slot's ``currentData()`` gives, so a
        condition can be written against the payload ("fbx") not a position."""
        data = combo.currentData()
        return combo.currentIndex() if data is None else data

    def _widget_value_reader(self, widget):
        """``getter(widget) -> value`` for *widget*, or ``None`` if untabled."""
        for wtype, getter in self._WIDGET_VALUE_READERS:
            if isinstance(widget, wtype):
                if getter.startswith("_"):
                    return getattr(self, getter)
                return lambda w, g=getter: getattr(w, g)()
        return None

    def _set_combo_value(self, combo, value) -> None:
        """Select the item *value* names — the inverse of :meth:`_combo_value`.

        Resolution mirrors how a combo's value is READ: item data first (the
        payload a data-backed combo reports), then the display label, then a
        plain row index. uitk's ``ComboBox`` can display RICH text, which Qt's
        ``findText`` (DisplayRole only) misses, so its own matcher gets the last
        word before the write is abandoned.

        Two deliberate departures from the combo API next door:

          * a value matching NOTHING leaves the combo untouched (and says so)
            rather than falling back to row 0 the way ``setAsCurrent`` does — a
            derived rule must never silently rewrite the user's selection to
            something its resolver did not ask for;
          * the write goes through ``setCurrentIndex``, not ``setCurrentText``,
            which is ``@Signals.blockSignals``-decorated on uitk's ``ComboBox``
            and would move the display without telling anything downstream.
        """
        # ``findData(None)`` matches the first data-less item, so a None value
        # would silently select row 0 -- and None is a non-answer, not a choice.
        if value is None:
            return
        text = str(value)
        index = combo.findData(value)
        if index < 0:
            index = combo.findText(text)
        if index < 0:
            matcher = getattr(combo, "_index_of_text", None)  # uitk rich text
            if callable(matcher):
                match = matcher(text)
                index = -1 if match is None else match
        # ``isinstance(True, int)`` is True, so without the bool guard a
        # resolver returning False would land on ROW 0 — a silent wrong
        # selection. A bool is an answer about a checkbox, never a row.
        if (
            index < 0
            and isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value < combo.count()
        ):
            index = value  # symmetric with _combo_value's index reading
        if index < 0:
            self.logger.warning(
                f"[value_from] {combo.objectName()!r} has no item for {value!r}; "
                f"selection left unchanged"
            )
            return
        combo.setCurrentIndex(index)

    def _widget_value_writer(self, widget):
        """``setter(widget, value)`` for *widget*, or ``None`` if unwritable.

        A combo is written here — :meth:`_set_combo_value` matches by item DATA
        the way :meth:`_combo_value` READS it, and goes through
        ``setCurrentIndex`` because uitk's ``ComboBox.setCurrentText`` is
        ``@Signals.blockSignals``-decorated. Everything else delegates to
        ``ValueManager.set_value``, the ecosystem's one answer to "set this
        widget's value"; the combo family is the ONLY place a uitk widget
        silences a setter, so nothing else can be surprised that way.
        """
        if isinstance(widget, QtWidgets.QComboBox):
            return self._set_combo_value
        if isinstance(widget, self._WIDGET_VALUE_WRITABLE):
            return ValueManager.set_value
        return None

    def _value_change_signal(self, widget):
        """Name of the signal announcing a value change on *widget*: the
        override table first, then the Switchboard's ``default_signals``."""
        for wtype, name in self._VALUE_CHANGE_SIGNALS:
            if isinstance(widget, wtype) and hasattr(widget, name):
                return name
        for wtype, name in getattr(self, "default_signals", {}).items():
            if isinstance(widget, wtype) and hasattr(widget, name):
                return name
        return None

    def _resolve_ui_widget(self, ui, ref):
        """Resolve a widget reference — an instance or an objectName on *ui*."""
        if isinstance(ref, QtWidgets.QWidget):
            return ref
        return getattr(ui, ref, None) if isinstance(ref, str) else None

    def _read_signal_value(self, widget, signal):
        """The value a *signal* would deliver for the widget's CURRENT state —
        what an initial apply needs, since no signal has fired yet."""
        reader = self._SIGNAL_VALUE_READERS.get(signal)
        if reader and hasattr(widget, reader):
            value = getattr(widget, reader)()
            # PySide6 hands ``checkState()`` back as a Qt.CheckState enum while
            # ``stateChanged`` delivers the int — match what the signal sends.
            return getattr(value, "value", value)
        getter = self._widget_value_reader(widget)
        return getter(widget) if getter is not None else None

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
                self.logger.error(f"Failed to connect toggle: {e}")
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

    @staticmethod
    def _rule_ref_name(ref) -> str:
        """A rule reference's stable identity: a widget's objectName, or the name
        as given. Rules key on these, so re-wiring the same pair is recognisable."""
        return ref.objectName() if isinstance(ref, QtWidgets.QWidget) else str(ref)

    @staticmethod
    def _is_name_pattern(ref: str) -> bool:
        """True when *ref* is shorthand for several widgets — ``'b000-3'``, ``'a,b'``."""
        return any(c in ref for c in ",-")

    def _resolve_rule_refs(self, ui, refs) -> list:
        """Widgets for a rule's references: widget instances pass through, strings
        (single names or patterns) resolve against *ui*. A name that has not been
        registered yet simply contributes nothing — the caller decides whether that
        means "wait" or "wrong container"."""
        out = []
        for ref in refs:
            if isinstance(ref, QtWidgets.QWidget):
                out.append(ref)
            elif isinstance(ref, str):
                out.extend(self.get_widgets_by_string_pattern(ui, ref))
        return out

    def _watched_rule_names(self, *ref_groups) -> set:
        """Every objectName a rule cares about, patterns unpacked — the set an
        ``on_child_registered`` handler filters against before re-applying."""
        watched = set()
        for group in ref_groups:
            for name in group:
                watched.update(
                    self.unpack_names(name) if self._is_name_pattern(name) else [name]
                )
        return watched

    @staticmethod
    def _registration_signal(ui):
        """``ui``'s "a child registered" signal, or None if it has none.

        A ``MainWindow`` has one, so a declarative rule can wait for a name that has
        not arrived yet. An option box's ``Menu`` does not: whatever is on it at wire
        time is all there will ever be.
        """
        signal = getattr(ui, "on_child_registered", None)
        return signal if callable(getattr(signal, "connect", None)) else None

    def _warn_if_rule_is_dead(self, ui, rule, **roles):
        """Warn when a declarative rule can never fire.

        Resolving nothing is normal *while* a name is still unregistered — that is
        the order-independence :meth:`enable_when` and :meth:`text_from` are built
        on, and :meth:`_registration_signal` is what eventually delivers. Against a
        container with no such signal there is nothing left to arrive, so a rule that
        resolved nothing is not waiting, it is pointed at the wrong container.

        Worth a warning rather than silence because the failure has no symptom to
        follow: tentacle's Constrain / Snap buttons named ``widget.menu`` (the
        ``MenuMixin`` context menu) where their checkboxes were on
        ``widget.option_box.menu``, resolved to nothing, and relabelled never — with
        no exception, and nothing above DEBUG to say why.
        """
        if self._registration_signal(ui) is not None:
            return
        for role, widgets in roles.items():
            if not widgets:
                self.logger.warning(
                    f"[{rule}] could not resolve its {role} against "
                    f"{ui.objectName() or type(ui).__name__}, which has no "
                    f"on_child_registered — nothing further can arrive, so this rule "
                    f"can never fire. Are the names on a different container "
                    f"(widget.menu vs widget.option_box.menu)?"
                )

    def _rule_value_reader(self, value):
        """``read(widget) -> value`` for a declarative rule, honouring *value*.

        Shared by :meth:`enable_when`, :meth:`text_from` and :meth:`value_from`
        so "what does this control's value mean" keeps ONE answer: the
        ``_WIDGET_VALUE_READERS`` table, overridable per rule with a callable
        (applied to every source) or a ``{objectName: callable}`` mapping (for a
        mixed set — unlisted sources keep the default reader).
        """

        def read(widget):
            reader = (
                value.get(widget.objectName()) if isinstance(value, dict) else value
            )
            if callable(reader):
                return reader(widget)
            getter = self._widget_value_reader(widget)
            return getter(widget) if getter is not None else None

        return read

    def _rule_source_resolver(self, ui, refs, unpack: bool):
        """``resolve() -> [widget] | None`` for a rule's source references.

        Widget instances pass through; a string resolves against *ui*. An exact
        name that has not been registered yet returns ``None`` — the whole rule
        HOLDS rather than deciding on a partial reading — and so does a
        reference that is neither a widget nor a name.

        *unpack* decides what a pattern (``'chk024-26'``) means: one value per
        matched widget (:meth:`text_from`, :meth:`value_from`, whose sources
        feed a callable positionally), or a single lookup that simply will not
        resolve (:meth:`enable_when`, whose triggers are one-ref-one-value).
        """

        def resolve():
            out = []
            for ref in refs:
                if isinstance(ref, QtWidgets.QWidget):
                    out.append(ref)
                elif isinstance(ref, str) and unpack and self._is_name_pattern(ref):
                    out.extend(self.get_widgets_by_string_pattern(ui, ref))
                elif isinstance(ref, str):
                    widget = self._resolve_ui_widget(ui, ref)
                    if widget is None:
                        return None
                    out.append(widget)
                else:
                    return None
            return out

        return resolve

    def _wire_rule(
        self,
        ui,
        rule: str,
        registry: str,
        key,
        resolve_sources: Callable[[], Optional[list]],
        resolve_targets: Callable[[], list],
        apply: Callable[..., None],
        signal: Optional[str] = None,
        role: str = "sources",
    ):
        """Connect *apply* to its sources, keep it order-independent, register it.

        The machinery every declarative rule shares. :meth:`enable_when`,
        :meth:`text_from` and :meth:`value_from` differ only in what ``apply``
        READS its verdict from and what it WRITES; the wiring around that is
        identical, and lives here once:

          * connect each source's natural change signal (or *signal*, for a
            single source) to ``apply``, then apply immediately — a rule that is
            only connected leaves whatever the ``.ui`` shipped standing until the
            user touches something, which is already wrong for a source that
            starts non-default or was restored from session state;
          * re-connect and re-apply when ``ui.on_child_registered`` announces a
            watched name, plus once more after the current event (registration
            restores session state with signals blocked, so the first read can be
            pre-restore);
          * report a rule that can never fire (:meth:`_warn_if_rule_is_dead`);
          * store it in *registry* so :meth:`refresh_dependencies` re-applies it
            for bulk changes no signal announced.

        *role* names the sources in that report ("triggers" for
        :meth:`enable_when`), so the warning reads in the caller's own vocabulary.

        Returns:
            The rule's ``apply`` callable.
        """
        connected = set()

        def connect_sources():
            widgets = resolve_sources()
            if widgets is None:
                return
            for widget in widgets:
                if id(widget) in connected:
                    continue
                name = signal if (signal and len(widgets) == 1) else None
                name = name or self._value_change_signal(widget)
                sig = getattr(widget, name, None) if name else None
                if sig is None or not callable(getattr(sig, "connect", None)):
                    self.logger.warning(
                        f"[{rule}] no change signal for {widget.objectName()!r}"
                    )
                    continue
                sig.connect(apply)
                connected.add(id(widget))
            apply()

        # Pattern refs ('b000-3') can't be matched by exact name — unpack them.
        watched = self._watched_rule_names(*key)

        def on_registered(widget):
            if widget.objectName() not in watched:
                return
            connect_sources()
            apply()
            QtCore.QTimer.singleShot(0, apply)

        connect_sources()
        on_reg = self._registration_signal(ui)
        if on_reg is not None:
            on_reg.connect(on_registered)
        self._warn_if_rule_is_dead(
            ui, rule, **{role: resolve_sources(), "targets": resolve_targets()}
        )

        ui.__dict__.setdefault(registry, {})[key] = apply
        return apply

    def enable_when(
        self,
        ui,
        targets,
        trigger,
        condition=True,
        signal=None,
        value=None,
        invert=False,
    ):
        """Keep *targets* enabled exactly while *trigger*'s value satisfies
        *condition* — a declarative dependency, wired once.

        The one-line answer to "grey this out when it can't apply": a lower-level
        choice (output format, a master checkbox, a mode combo) makes some other
        control irrelevant, and the panel should say so instead of leaving a
        live dial the export ignores. Replaces the pattern of a per-trigger slot
        + a ``_sync_*`` helper + a mirrored ``toggle_multi`` ``on_True`` /
        ``on_False`` pair with one rule that reads as the sentence it encodes::

            sb.enable_when(ui, "cmb006", "cmb004", lambda fmt: fmt != "fbx")
            sb.enable_when(ui, "texture_max_size", "optimize_textures")
            sb.enable_when(ui, "s001,chk002", "cmb035", 0)           # index / data == 0
            sb.enable_when(ui, "d000", "cmb035", 0, invert=True)     # the other branch
            sb.enable_when(ui, "texture_write_back",
                           ["optimize_textures", "cmb005"], lambda opt, tpl: opt or tpl)

        Parameters:
            ui: The loaded UI (widgets resolve by objectName on it).
            targets: Widget(s) to enable/disable — an objectName pattern string
                (``'s000,b004-7'``), a widget, or a list of either.
            trigger: The controlling widget(s) — objectName / widget, or a list
                (the condition then receives one value per trigger, in order).
            condition: What "on" means for the trigger's value: a callable
                ``(value, …) -> bool``; a plain value (equality); a set / list /
                tuple of values (membership); or ``True`` (default: truthiness —
                the master-checkbox case). With MULTIPLE triggers every
                non-callable form is **all-of**: equality, membership and
                truthiness each have to hold for every trigger. A callable is
                handed one value per trigger and decides for itself, which is
                where any-of lives.
            signal: Change signal name (single trigger). Default: the widget's
                natural signal from the value table.
            value: Reader override — a callable ``(widget) -> value`` used for
                every trigger, or a ``{objectName: callable}`` mapping for a
                mixed set (unlisted triggers keep the default reader, which
                reads a combo's ``currentData`` when items carry data, else
                ``currentIndex``; buttons ``isChecked``; …).
            invert: Enable when the condition is NOT met.

        A rule that resolves nothing against a container that HAS no
        ``on_child_registered`` is reported (see :meth:`_warn_if_rule_is_dead`):
        nothing further can arrive there, so it is not waiting — the names are on
        another container.

        Order-independent by design: a target (or trigger) that isn't
        registered on *ui* yet — a ``WidgetComboBox`` row, an option-box menu
        item — is picked up when ``ui.on_child_registered`` announces it, and
        the rule is (re)applied then and once more after the current event
        (registration restores session state with signals blocked, so the
        first read can be pre-restore). Every rule is also re-applied by
        :meth:`refresh_dependencies` for bulk state changes made with signals
        blocked (a preset load). Wiring the same targets to the same triggers
        twice is a no-op, so an ``_init`` slot that re-runs can't stack rules.

        Returns:
            The rule's ``apply`` callable (handy as an ``on_loaded`` hook).
        """
        trigger_refs = (
            list(trigger) if isinstance(trigger, (list, tuple)) else [trigger]
        )
        target_refs = list(targets) if isinstance(targets, (list, tuple)) else [targets]

        key = (
            tuple(map(self._rule_ref_name, trigger_refs)),
            tuple(map(self._rule_ref_name, target_refs)),
        )
        rules = ui.__dict__.setdefault("_enable_when_rules", {})
        if key in rules:
            # Re-wiring the same pair is a deliberate no-op so an ``_init`` slot
            # that re-runs cannot stack rules. A rule with DIFFERENT semantics
            # is a different matter: it used to vanish silently, leaving the
            # first rule in force and the caller none the wiser. Only report
            # when the difference is PROVABLE -- a re-run ``_init`` builds a new
            # lambda every time, so comparing callables by identity would cry
            # wolf on the very case the no-op exists for.
            prior = getattr(rules[key], "_enable_when_spec", None)
            if prior is not None and not callable(condition) and not callable(prior[0]):
                if self._enable_when_key(*prior) != self._enable_when_key(
                    condition, invert
                ):
                    self.logger.warning(
                        f"enable_when: a rule for {key[1]} on {key[0]} already "
                        f"exists with condition={prior[0]!r} invert={prior[1]}; "
                        f"the new condition={condition!r} invert={invert} was "
                        f"DROPPED. Wire one rule per (trigger, target) pair, or "
                        f"express both in a single callable condition."
                    )
            return rules[key]

        if callable(condition):
            predicate = condition
        elif isinstance(condition, (set, frozenset, list, tuple)):
            allowed = set(condition)
            # All-of, one value per trigger. This branch (and the equality one
            # below) used to read `v` and discard `*rest`, so a multi-trigger
            # rule was decided by the FIRST trigger alone. `condition is True`
            # was already all-of, so all-of is what makes the non-callable
            # family consistent; any-of stays expressible as a callable.
            predicate = lambda *vals: all(v in allowed for v in vals)  # noqa: E731
        elif condition is True:
            predicate = lambda *vals: all(bool(v) for v in vals)  # noqa: E731
        else:
            predicate = lambda *vals: all(v == condition for v in vals)  # noqa: E731

        resolve_triggers = self._rule_source_resolver(ui, trigger_refs, unpack=False)

        def resolve_targets():
            return self._resolve_rule_refs(ui, target_refs)

        read = self._rule_value_reader(value)

        def apply(*_):
            triggers = resolve_triggers()
            if triggers is None:
                return
            try:
                on = bool(predicate(*[read(w) for w in triggers]))
            except Exception as e:  # a half-built trigger; try again on the next signal
                self.logger.debug(f"[enable_when] condition raised: {e}")
                return
            if invert:
                on = not on
            for w in resolve_targets():
                w.setEnabled(on)

        # Carried so a later conflicting wire-up can be named rather than
        # dropped in silence (see the duplicate-key branch above).
        apply._enable_when_spec = (condition, invert)
        return self._wire_rule(
            ui,
            "enable_when",
            "_enable_when_rules",
            key,
            resolve_triggers,
            resolve_targets,
            apply,
            signal,
            role="triggers",
        )

    def text_from(
        self,
        ui,
        targets: Union[str, Any, List[Any]],
        sources: Union[str, Any, List[Any]],
        formatter: Callable[..., str],
        signal: Optional[str] = None,
        value: Optional[
            Union[Callable[[Any], Any], Dict[str, Callable[[Any], Any]]]
        ] = None,
    ) -> Callable[[], None]:
        """Keep *targets*' text derived from *sources* — a self-labelling widget,
        wired once.

        The text counterpart of :meth:`enable_when`: that one answers "grey this out
        when it can't apply", this one answers "say what this will do". A control
        whose behaviour is configured elsewhere — an option box, a mode combo —
        reads as a mystery until it names its own outcome, and on a marking menu
        there is no dialog to read first::

            sb.text_from(menu, widget, "s003", "Crease {}".format)
            sb.text_from(menu, widget, "chk024-26",
                         lambda *on: f"Constrain: {'ON' if any(on) else 'OFF'}")
            sb.text_from(menu, widget, ["cmb_scope", "cmb_save", "cmb_format"],
                         self._export_button_text,
                         value={"cmb_format": lambda w: w.currentText()})

        Hand-wiring this is three steps — read, format, ``setText`` — plus a fourth
        that is easy to forget: applying it at WIRE TIME. A rule that is only
        connected leaves whatever text the ``.ui`` shipped standing until the user
        touches something, which is already wrong whenever a source starts
        non-default or was restored from session state.

        Parameters:
            ui: The loaded UI, or whatever the names resolve against — an option
                box's ``menu`` is the common one.
            targets: Widget(s) to relabel — an objectName pattern string
                (``'tb003'``, ``'b004-7'``), a widget, or a list of either. Every
                resolved target gets the same text.
            sources: The widget(s) the text is derived from — objectName / pattern
                / widget, or a list of those. Patterns UNPACK here (unlike
                :meth:`enable_when`'s trigger), so ``'chk024-26'`` feeds the
                formatter three values.
            formatter: ``callable(*values) -> str``, one value per resolved source
                in order. ``"Crease {}".format`` is a formatter.
            signal: Change signal name (single source). Default: the widget's
                natural signal from the value table.
            value: Reader override — a callable ``(widget) -> value`` used for every
                source, or a ``{objectName: callable}`` mapping for a mixed set
                (unlisted sources keep the default reader). The default reads a
                combo's ``currentData`` when its items carry data, else
                ``currentIndex``; pass ``currentText`` when the item's LABEL is what
                the text should say.

        Order-independent, idempotent and bulk-refreshable exactly as
        :meth:`enable_when` — they share the machinery and the notes there apply,
        including the report when a rule can never fire. A source named EXACTLY that
        hasn't been registered yet holds the whole rule rather than formatting a
        partial reading; a pattern contributes whatever it matches so far, and is
        re-applied when the rest arrive.

        A target that is also a source is safe: the write-back cannot re-enter the
        rule. A formatter that raises leaves the current text standing rather than
        blanking it, so a half-built source costs nothing.

        Returns:
            The rule's ``apply`` callable (handy as an ``on_loaded`` hook).
        """
        source_refs = list(sources) if isinstance(sources, (list, tuple)) else [sources]
        target_refs = list(targets) if isinstance(targets, (list, tuple)) else [targets]

        key = (
            tuple(map(self._rule_ref_name, source_refs)),
            tuple(map(self._rule_ref_name, target_refs)),
        )
        rules = ui.__dict__.setdefault("_text_from_rules", {})
        if key in rules:
            # Re-wiring the same pair is a deliberate no-op so an ``_init`` slot that
            # re-runs cannot stack rules. No conflict warning like enable_when's: a
            # formatter is a fresh callable every run, so a genuine difference is
            # never provable and the check could only cry wolf.
            return rules[key]

        resolve_sources = self._rule_source_resolver(ui, source_refs, unpack=True)

        def resolve_targets():
            return self._resolve_rule_refs(ui, target_refs)

        read = self._rule_value_reader(value)

        # A target that is ALSO a source (a line edit that reformats itself) would
        # have setText re-enter apply through textChanged and never stop. A hang is
        # the one failure mode a UI helper must not have, so the write is fenced.
        writing = []

        def apply(*_):
            if writing:
                return
            widgets = resolve_sources()
            if not widgets:
                return
            try:
                text = formatter(*[read(w) for w in widgets])
            except Exception as e:  # a half-built source; try again on the next signal
                self.logger.debug(f"[text_from] formatter raised: {e}")
                return
            writing.append(True)
            try:
                for widget in resolve_targets():
                    setter = getattr(widget, "setText", None)
                    if callable(setter):
                        setter(text)
                    else:
                        self.logger.warning(
                            f"[text_from] {widget.objectName()!r} has no setText"
                        )
            finally:
                writing.clear()

        return self._wire_rule(
            ui,
            "text_from",
            "_text_from_rules",
            key,
            resolve_sources,
            resolve_targets,
            apply,
            signal,
        )

    def value_from(
        self,
        ui,
        targets: Union[str, Any, List[Any]],
        sources: Union[str, Any, List[Any]],
        resolver: Callable[..., Any],
        signal: Optional[str] = None,
        value: Optional[
            Union[Callable[[Any], Any], Dict[str, Callable[[Any], Any]]]
        ] = None,
    ) -> Callable[[], None]:
        """Keep *targets*' VALUE derived from *sources* — a control that follows
        the dials it stands for, wired once.

        The third of the declarative family: :meth:`enable_when` answers "grey
        this out when it can't apply", :meth:`text_from` "say what this will
        do", and this one "say WHICH of my presets you are on". The case it
        exists for is a summary control the user can also drive around: a
        Quality combo that fills Resolution / Samples has to fall back to
        *Custom* the moment either dial stops matching a preset, or it keeps
        naming a tier the bake is no longer using::

            sb.value_from(ui, "cmb000", ["cmb_resolution", "spn_samples"],
                          self._preset_for_dials)      # -> "quest" | "Custom"

            sb.value_from(m, "cmb_mode", "chk_advanced",
                          lambda on: "advanced" if on else "basic")

        Hand-wiring this is the same four steps as :meth:`text_from` — read,
        resolve, write, and apply at WIRE TIME — plus a fifth that only bites
        here: a naive write-back re-enters through the target's own change
        signal. The write is fenced, so a target may be its own source.

        Parameters:
            ui: The loaded UI, or whatever the names resolve against — an option
                box's ``menu`` is the common one.
            targets: Widget(s) to drive — an objectName pattern string
                (``'cmb000'``, ``'s004-7'``), a widget, or a list of either.
                Every resolved target gets the same value.
            sources: The widget(s) the value is derived from — objectName /
                pattern / widget, or a list of those. Patterns UNPACK (as in
                :meth:`text_from`), so ``'chk024-26'`` feeds three values.
            resolver: ``callable(*values) -> value``, one value per resolved
                source in order. Returning ``None`` DECLINES — the target is
                left exactly as the user left it — so "I have no opinion about
                this combination" needs no sentinel.
            signal: Change signal name (single source). Default: the widget's
                natural signal from the value table.
            value: Reader override for the SOURCES — a callable ``(widget) ->
                value`` for every one, or a ``{objectName: callable}`` mapping
                for a mixed set. (Writes are dispatched by widget type; see
                :meth:`_widget_value_writer`.)

        The write is the mirror of the read: a combo takes the item whose DATA,
        then whose LABEL, then whose ROW matches (a value matching none of the
        three is reported and skipped, never coerced to row 0); every other type
        goes to ``ValueManager.set_value``, which coerces where that is
        unambiguous (``"8"`` into a spin box) and leaves the widget alone where
        it is not. Writes are NOT signal-blocked — a derived value is a real
        change and the target's own slot is entitled to see it (that is what
        lets a preset combo re-apply the rest of its preset).

        Order-independent, idempotent and bulk-refreshable exactly as
        :meth:`enable_when` and :meth:`text_from` — they share the machinery
        (:meth:`_wire_rule`) and the notes there apply, including the report
        when a rule can never fire.

        Returns:
            The rule's ``apply`` callable (handy as an ``on_loaded`` hook).
        """
        source_refs = list(sources) if isinstance(sources, (list, tuple)) else [sources]
        target_refs = list(targets) if isinstance(targets, (list, tuple)) else [targets]

        key = (
            tuple(map(self._rule_ref_name, source_refs)),
            tuple(map(self._rule_ref_name, target_refs)),
        )
        rules = ui.__dict__.setdefault("_value_from_rules", {})
        if key in rules:
            # Re-wiring the same pair is a deliberate no-op so an ``_init`` slot
            # that re-runs cannot stack rules (no conflict warning, for the same
            # reason as text_from's: a resolver is a fresh callable every run).
            return rules[key]

        resolve_sources = self._rule_source_resolver(ui, source_refs, unpack=True)

        def resolve_targets():
            return self._resolve_rule_refs(ui, target_refs)

        read = self._rule_value_reader(value)

        # A target is very often ALSO the thing whose change re-enters here (a
        # preset combo that writes its dials back), and writes are deliberately
        # not signal-blocked — so the fence, not silence, is what bounds it.
        writing = []

        def apply(*_):
            if writing:
                return
            widgets = resolve_sources()
            if not widgets:
                return
            try:
                derived = resolver(*[read(w) for w in widgets])
            except Exception as e:  # a half-built source; retry on the next signal
                self.logger.debug(f"[value_from] resolver raised: {e}")
                return
            if derived is None:  # the resolver declined — leave the target alone
                return
            writing.append(True)
            try:
                for widget in resolve_targets():
                    writer = self._widget_value_writer(widget)
                    if writer is None:
                        self.logger.warning(
                            f"[value_from] no value setter for "
                            f"{widget.objectName()!r} ({type(widget).__name__})"
                        )
                        continue
                    try:
                        writer(widget, derived)
                    except Exception as e:
                        self.logger.warning(
                            f"[value_from] {widget.objectName()!r} rejected "
                            f"{derived!r}: {e}"
                        )
            finally:
                writing.clear()

        return self._wire_rule(
            ui,
            "value_from",
            "_value_from_rules",
            key,
            resolve_sources,
            resolve_targets,
            apply,
            signal,
        )

    #: The declarative-rule registries :meth:`refresh_dependencies` re-applies.
    _DEPENDENCY_REGISTRIES = (
        "_enable_when_rules",
        "_text_from_rules",
        "_value_from_rules",
    )

    def refresh_dependencies(self, ui) -> None:
        """Re-apply every declarative rule on *ui* — :meth:`enable_when`'s,
        :meth:`text_from`'s and :meth:`value_from`'s — for bulk value changes
        made with signals blocked (a preset load, a programmatic restore) that
        no trigger signal announced."""
        for registry in self._DEPENDENCY_REGISTRIES:
            for apply in list(ui.__dict__.get(registry, {}).values()):
                apply()

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
                # During a programmatic state restore / preset load (saves
                # suppressed) values are applied field-by-field, not by a user
                # gesture — re-baseline only. Otherwise restoring a locked field
                # would fire a spurious delta into its locked siblings and
                # corrupt their restored values (order-dependent). Mirrors how
                # MainWindow.sync_widget_values gates on the same flag.
                if state is not None and getattr(state, "_save_suppressed", 0):
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
        busy: Optional[bool] = None,
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
            busy: Show the footer's busy spinner beside the text. ``None``
                (default) shows it for indeterminate work only; ``True``
                keeps it on a determinate bar whose single steps are long
                (see ``Footer.set_busy``); ``False`` never shows it.

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
            return footer.progress(total=total, text=text, busy=busy)
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
            # Modal: suspend any slot busy-cursor so buttons show an arrow.
            with CursorManager.suspend():
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

        # Non-modal: this returns while the slot dispatcher still holds a
        # WaitCursor override (popped only in its ``finally``). Unlike the
        # modal dialogs above we cannot suspend-and-restore around a
        # bounded event loop, so cancel the busy cursor outright — the
        # report is on screen and the user is meant to interact with it.
        CursorManager.drain()
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
        if isinstance(file_types, str):
            file_types = [file_types]

        options = QtWidgets.QFileDialog.Options()
        file_types_string = f"{filter_description} ({' '.join(file_types)})"

        with CursorManager.suspend():
            if allow_multiple:
                files, _ = QtWidgets.QFileDialog.getOpenFileNames(
                    None, title, start_dir, file_types_string, options=options
                )
                return files
            file, _ = QtWidgets.QFileDialog.getOpenFileName(
                None, title, start_dir, file_types_string, options=options
            )
            return file or None

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
        with CursorManager.suspend():
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

        with CursorManager.suspend():
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

        # Modal: suspend any slot busy-cursor so the line edit shows an
        # I-beam and the buttons an arrow instead of the busy hourglass.
        with CursorManager.suspend():
            accepted = dlg.exec_() == QtWidgets.QDialog.Accepted
        if accepted:
            result = line.text().strip()
            return result if result else None
        return None

    @staticmethod
    def list_input_dialog(
        items,
        title: str = "Select",
        label: str = "Select item(s):",
        parent: QtWidgets.QWidget = None,
        multi: bool = True,
        selected=None,
    ) -> list:
        """Show a modal list picker and return the chosen entries.

        The list twin of :meth:`input_dialog` — same parenting, host-theme
        inheritance, and busy-cursor suspension, so a panel needing "pick some
        of these" doesn't hand-roll a ``QDialog`` that misses all three.

        Parameters:
            items: Iterable of entries. Non-strings are rendered with ``str``;
                the returned values are the rendered strings.
            title: Window title.
            label: Descriptive label above the list.
            parent: Optional parent widget for correct modality and position.
            multi: Allow selecting several entries (default). False restricts
                to one.
            selected: Optional iterable of entries to pre-select.

        Returns:
            list[str]: The selected entries, or ``[]`` if the dialog was
                cancelled or nothing was picked.
        """
        entries = [str(i) for i in (items or [])]
        preselect = {str(s) for s in (selected or [])}

        dlg = QtWidgets.QDialog(parent)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(280)

        layout = QtWidgets.QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(6)
        layout.addWidget(QtWidgets.QLabel(label))

        listing = QtWidgets.QListWidget()
        listing.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
            if multi
            else QtWidgets.QAbstractItemView.SingleSelection
        )
        listing.addItems(entries)
        for row in range(listing.count()):
            if listing.item(row).text() in preselect:
                listing.item(row).setSelected(True)
        # Double-click is the expected commit gesture in a picker list.
        listing.itemDoubleClicked.connect(dlg.accept)
        layout.addWidget(listing)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        # Inherit parent stylesheet so the dialog matches the host theme.
        if parent is not None:
            ss = parent.styleSheet()
            if ss:
                dlg.setStyleSheet(ss)

        # Modal: suspend any slot busy-cursor so the list shows a normal
        # pointer instead of the busy hourglass.
        with CursorManager.suspend():
            accepted = dlg.exec_() == QtWidgets.QDialog.Accepted

        return [i.text() for i in listing.selectedItems()] if accepted else []

    @staticmethod
    def form_dialog(
        fields,
        title: str = "Options",
        parent: QtWidgets.QWidget = None,
        ok_text: Union[str, Callable] = "OK",
        validate: Callable = None,
        message: str = "",
    ) -> Optional[dict]:
        """Show a modal form of labelled rows and return ``{name: value}``.

        The multi-field twin of :meth:`input_dialog`, for the case a sequence
        of single-purpose dialogs handles badly: **two or more answers the
        user has to tell apart**. A pair of native folder pickers shown back
        to back are the same widget with different captions, so which one is
        "search here" and which is "write here" lives entirely in a title
        bar — and the answer changes when one of them is skipped. Side by
        side and labelled, there is nothing to confuse and no order to
        remember.

        The window is a :class:`~uitk.widgets.formPanel.FormPanel`, so it
        wears the toolset's own chrome (Header, Footer, theme) rather than a
        bare dialog's host default, and every row's ``hint`` is a formatted
        tooltip. See :meth:`FormPanel.set_fields` for the full field spec.

        Use this when the caller does the work AFTER the answers are in.
        When the work belongs on the form — a verb button, a log to watch,
        a second run with one value changed — use :meth:`form_panel`, which
        stays open and keeps its output pane.

        Parameters:
            fields: Iterable of row specs (dicts). See
                :meth:`FormPanel.set_fields`.
            title: Window title.
            parent: Optional parent for correct modality and position.
            ok_text: Accept-button text. Say what will happen ("Copy 12
                files") — the button is the last thing read before
                committing. A ``callable(values) -> str`` is re-evaluated on
                every edit, so a verb chosen ON the form (a Copy/Move row)
                reaches the button that names the operation.
            validate: Optional ``callable(values: dict) -> str``. Return ""
                (or None) when the form is valid, else the message to show in
                the footer; OK stays disabled while it is non-empty.
            message: Optional line above the rows.

        Returns:
            dict|None: ``{name: value}`` for every row, or None when the
            dialog was cancelled or closed.

        Example:
            paths = sb.form_dialog(
                [
                    {"name": "src", "kind": "dir", "label": "Search in",
                     "hint": "3 unresolved texture(s), searched recursively"},
                    {"name": "dest", "kind": "dir", "label": "Copy into",
                     "value": sourceimages, "hint": "12 file(s) land here"},
                ],
                title="Find & Copy Textures",
                ok_text="Copy 12 files",
                validate=lambda v: (
                    "Destination is the search folder — nothing would move."
                    if v["src"] and v["src"] == v["dest"] else ""
                ),
            )
        """
        panel = SwitchboardUtilsMixin.form_panel(
            fields,
            title=title,
            parent=parent,
            ok_text=ok_text,
            validate=validate,
            message=message,
            # A modal that closes before the work starts has nothing to
            # stream, so it carries no output pane.
            output=False,
        )
        accepted = panel.exec_panel()
        values = panel.values() if accepted else None
        panel.deleteLater()
        return values

    @staticmethod
    def form_panel(
        fields,
        title: str = "Options",
        parent: QtWidgets.QWidget = None,
        ok_text: Union[str, Callable] = "OK",
        cancel_text: str = None,
        validate: Callable = None,
        message: str = "",
        help_text: str = "",
        on_run: Callable = None,
        apply_text: str = "Apply",
        output: bool = True,
        min_width: int = 560,
        settings=None,
        settings_key: str = "window_geometry",
    ):
        """Build a :class:`~uitk.widgets.formPanel.FormPanel` — the modeless twin.

        The same rows as :meth:`form_dialog`, in a window that STAYS OPEN and
        runs the operation itself: the accept button calls ``on_run(values)``
        with the panel still up, the operation's log streams into the single
        output pane at the bottom, and the footer carries the status. That is
        the shape every other tool window in the toolset has, and it is what a
        modal cannot be — a modal that has closed can neither show what it did
        nor be re-run with one value changed.

        Does NOT show the panel: the caller decides, because a caller that
        keeps the panel (to re-seed it from live state on the next invocation
        rather than stacking a second window) needs the reference before the
        first show. Call ``panel.present()``. It is a ``WindowPanel``, so
        anything beyond the field specs is added the way a Menu item is —
        ``panel.add("PushButton", setText=..., clicked=...)``.

        Parameters:
            fields: Iterable of row specs (dicts). See
                :meth:`FormPanel.set_fields`.
            title: Header text.
            parent: Anchor widget; the panel reparents to ``parent.window()``.
            ok_text: Accept-button text, or ``callable(values) -> str``.
            cancel_text: Reject-button text. A run-in-place panel gets no
                reject button by default (the header carries the window's
                close); pass a string to force one.
            validate: ``callable(values: dict) -> str`` — "" when valid.
            message: Optional rich-text line above the rows.
            help_text: Rich text for the header's ``?`` button. Build it with
                ``sb.tooltip.fmt(...)``.
            on_run: ``callable(values: dict)`` run in place by the accept
                button. Return a ``callable()`` to say "this was a preview" —
                the panel arms Apply with it (the naming panel's dry-run
                contract). Omit for a panel the caller drives itself.
            apply_text: Text of the armed-preview button.
            output: Show the collapsable output pane (default True).
            min_width: Minimum window width.
            settings: Optional store (``sb.settings.branch("<tool>")``) the
                window's size and position survive across sessions in.
            settings_key: Settings key holding the serialized geometry.

        Returns:
            FormPanel: the (unshown) panel.

        Example:
            panel = sb.form_panel(
                fields,
                title="Find & Copy Textures",
                parent=self.ui,
                on_run=self._execute_find_and_copy,
                validate=self._validate_find_and_copy,
            )
            panel.present()
        """
        from uitk.widgets.formPanel import FormPanel

        return FormPanel(
            fields,
            title=title,
            parent=parent,
            ok_text=ok_text,
            cancel_text=cancel_text,
            validate=validate,
            message=message,
            help_text=help_text,
            on_run=on_run,
            apply_text=apply_text,
            output=output,
            min_width=min_width,
            settings=settings,
            settings_key=settings_key,
        )

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
