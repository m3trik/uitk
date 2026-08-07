# !/usr/bin/python
# coding=utf-8
import re
import traceback
import contextlib
from typing import Callable, List, Optional, Union
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk


class OverrideCursorGuard(QtCore.QObject):
    """Owns one application override cursor and guarantees its removal.

    ``QApplication.setOverrideCursor`` / ``restoreOverrideCursor`` are a
    balanced pair, so an override is only ever as reliable as the event that is
    supposed to pop it. A cursor pushed for the duration of an interaction —
    the marking menu's gesture ``CrossCursor`` — strands itself over the whole
    application whenever that pop is missed, and nothing notices:

      * the release lands somewhere else (a child widget holding the mouse
        grab, the host DCC, another window), so the pushing widget never sees
        the event that ends the interaction;
      * the widget is *destroyed* rather than hidden — Qt sends no hide event
        to a child in that case (only a parent ``hide()`` while visible does);
      * a third party snapshots the stack and restores it afterwards
        (:meth:`SwitchboardUtilsMixin._suspend_override_cursor`, the slot
        dispatcher's modal filter). If the owner released its cursor while the
        stack was suspended, the restore re-pushes an entry that now has no
        owner at all.

    This guard replaces balanced-call bookkeeping with an INVARIANT — *an
    override of ``shape`` exists only while ``is_live()`` says it should* —
    enforced from three sides:

      * :meth:`apply` / :meth:`clear` — the ordinary, immediate path.
      * a watchdog timer, running ONLY while the guard holds the override,
        that clears it as soon as ``is_live()`` turns False. This is what
        covers the missed events: no event has to arrive for the cursor to
        come back. A predicate that raises (the owner's C++ object is gone)
        counts as not-live, and the class keeps the guard — and therefore its
        timer — alive while it holds a push, so even a destroyed owner is
        cleaned up.
      * :meth:`reconcile` — drops any stack entry whose shape a guard claims
        but no guard holds (the snapshot/restore case). Run before every
        apply, and applied as a filter inside
        :meth:`SwitchboardUtilsMixin.push_override_cursor_stack` so a stale
        entry is never re-pushed in the first place.

    The claimed shape must be EXCLUSIVE to the guard: nothing else in the
    process may push it, or reconcile would drop a stranger's cursor.

    Parameters:
        shape (Qt.CursorShape): The cursor this guard owns, exclusively.
        is_live (callable): Zero-arg predicate — True while the override is
            legitimate (e.g. ``widget.isVisible``). Raising counts as False.
        interval_ms (int): Watchdog period while the override is held.
    """

    #: Shapes any guard has ever claimed — the set :meth:`is_stale` filters on.
    _CLAIMED_SHAPES = set()
    #: Guards currently holding a push. A strong ref, so a guard whose owner
    #: was destroyed still gets ticked (and cleaned up) by its own timer.
    _HOLDERS = set()

    def __init__(self, shape, is_live: Callable[[], bool], interval_ms: int = 250):
        super().__init__()
        self._shape = shape
        self._is_live = is_live
        self._holding = False
        # Explicitly the base class's registries: they are process-global by
        # design (any subclass shares them), and mutating through ``type(self)``
        # would read as per-subclass state.
        OverrideCursorGuard._CLAIMED_SHAPES.add(shape)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._on_tick)

    @property
    def shape(self):
        """The cursor shape this guard owns."""
        return self._shape

    @property
    def holding(self) -> bool:
        """True while this guard holds an application override cursor."""
        return self._holding

    def apply(self) -> None:
        """Push the override (idempotent) and start the watchdog."""
        app = QtWidgets.QApplication.instance()
        if app is None or self._holding:
            return
        # Anything of our shape still on the stack is by definition stale —
        # we hold nothing. Clear it so a leak can never accumulate a second
        # entry that would outlive this interaction too.
        self.reconcile()
        app.setOverrideCursor(QtGui.QCursor(self._shape))
        self._holding = True
        OverrideCursorGuard._HOLDERS.add(self)
        self._timer.start()

    def clear(self) -> None:
        """Remove the override (idempotent) and stop the watchdog."""
        if not self._holding:
            return
        # Order matters: dropping ownership FIRST is what lets the removal
        # below reuse the generic stale-entry filter for the buried case.
        self._holding = False
        OverrideCursorGuard._HOLDERS.discard(self)
        self._timer.stop()

        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        top = app.overrideCursor()
        if top is None:
            # Nothing to remove — the stack is currently suspended by someone
            # else (their restore now drops our entry via is_stale).
            return
        if top.shape() == self._shape:
            app.restoreOverrideCursor()
        else:
            # Buried under a later push (e.g. a slot's busy cursor): rebuild
            # the stack without our entry rather than popping theirs.
            self.reconcile()

    def _on_tick(self) -> None:
        """Watchdog: enforce the invariant without needing any event."""
        if self._live():
            return
        self.clear()

    def _live(self) -> bool:
        """``is_live()``, fail-safe. Any failure — including a deleted C++
        owner (``RuntimeError``) — means *not* live: an override that cannot
        prove it is still wanted must go."""
        try:
            return bool(self._is_live())
        except Exception:
            return False

    @classmethod
    def holds(cls, shape) -> bool:
        """True if any live guard currently holds ``shape``.

        Snapshots the holder set: a guard released mid-iteration (a watchdog
        tick landing inside a stack rebuild) mutates it.
        """
        return any(g.holding and g.shape == shape for g in tuple(cls._HOLDERS))

    @classmethod
    def is_stale(cls, cursor) -> bool:
        """True if ``cursor`` is a guard-owned shape that no guard holds —
        an orphan that must not be (re-)pushed onto the stack."""
        shape = cursor.shape()
        return shape in cls._CLAIMED_SHAPES and not cls.holds(shape)

    @classmethod
    def notify_stack_drained(cls) -> None:
        """Drop every guard's ownership because the whole stack was dropped
        out from under them (see :meth:`SwitchboardUtilsMixin._drain_override_cursor`).

        Without this a guard keeps claiming an entry that no longer exists:
        ``holds`` then reports True for an orphaned shape, and — the visible
        part — :meth:`apply` short-circuits, so the interaction runs out its
        life with no cursor instead of re-asserting one. Only the ownership
        flag is cleared; there is nothing left to pop.
        """
        for guard in tuple(cls._HOLDERS):
            guard._holding = False
            guard._timer.stop()
        cls._HOLDERS.clear()

    @classmethod
    def reconcile(cls) -> None:
        """Drop every orphaned guard cursor from the application stack,
        wherever it sits, leaving all other entries in their original order.
        No-op when no override is active."""
        app = QtWidgets.QApplication.instance()
        if app is None or app.overrideCursor() is None:
            return
        saved = SwitchboardUtilsMixin.pop_override_cursor_stack(app)
        # The re-push drops stale entries (see push_override_cursor_stack).
        SwitchboardUtilsMixin.push_override_cursor_stack(app, saved)


class SwitchboardUtilsMixin:
    """Utility methods for widget positioning, centering, and screen geometry."""

    @staticmethod
    def pop_override_cursor_stack(app):
        """Pop the whole application override-cursor stack.

        Shared primitive for the cursor-suspension helpers below and the
        dispatcher's modal guard. Returns the popped cursors **top-first** so
        they can be re-pushed in the original order via
        :meth:`push_override_cursor_stack`. No-op (empty list) when no
        override is active or ``app`` is ``None``.
        """
        saved = []
        if app is not None:
            while True:
                current = app.overrideCursor()
                if current is None:
                    break
                saved.append(QtGui.QCursor(current))
                app.restoreOverrideCursor()
        return saved

    @staticmethod
    def push_override_cursor_stack(app, saved):
        """Re-push cursors captured by :meth:`pop_override_cursor_stack`,
        restoring the original stack order. No-op when ``app`` is ``None``.

        An entry belonging to an :class:`OverrideCursorGuard` that has since
        released it is skipped: restoring it would strand a cursor whose owner
        is gone (the pop/push pair brackets an unbounded wait — a modal dialog
        — during which the owning interaction can easily end).
        """
        if app is not None:
            for cursor in reversed(saved):
                if OverrideCursorGuard.is_stale(cursor):
                    continue
                app.setOverrideCursor(cursor)

    @staticmethod
    @contextlib.contextmanager
    def _suspend_override_cursor():
        """Temporarily clear the application override-cursor stack.

        The slot dispatcher pushes a :data:`Qt.WaitCursor` override for the
        duration of every slot (see ``SlotWrapper._invoke``). A
        ``QApplication`` override cursor takes precedence over *every* widget
        cursor, so any dialog a slot spawns inherits the busy hourglass —
        even over its buttons, text fields, and file lists, where the user is
        expected to interact. A per-widget ``setCursor`` cannot win against an
        active override, so the only correct fix is to suspend the override
        for the dialog's (modal) lifetime, letting each widget show its
        natural cursor (arrow on buttons, I-beam in line edits), then restore
        the exact stack afterward so the slot's busy feedback resumes.

        No-op when no override is active (dialogs opened outside a slot).
        """
        app = QtWidgets.QApplication.instance()
        saved = SwitchboardUtilsMixin.pop_override_cursor_stack(app)
        try:
            yield
        finally:
            SwitchboardUtilsMixin.push_override_cursor_stack(app, saved)

    @staticmethod
    def _drain_override_cursor():
        """Pop the entire application override-cursor stack.

        Counterpart to :meth:`_suspend_override_cursor` for *non-modal*
        windows. A modal dialog can suspend the slot's busy cursor for the
        bounded lifetime of its event loop and restore it on close. A
        non-modal viewer (see :meth:`text_view_dialog`) outlives the slot
        that spawned it — by the time the user closes it the dispatcher's
        ``finally`` has long since restored the cursor, so there is nothing
        to restore *to*. Re-pushing a ``WaitCursor`` on the window's close
        would strand a busy hourglass with no matching pop (the reported
        "cursor stays active" symptom). The correct behaviour is therefore
        to *cancel* the busy cursor outright when the window appears: the
        slot's work product is on screen and the user is now meant to
        interact with it. Draining the whole stack also leaves the
        dispatcher's matching ``restoreOverrideCursor`` a harmless no-op,
        keeping the override stack balanced.

        No-op when no override is active (window opened outside a slot).

        A drain takes *every* owner's entry, guards included — so they are
        told, or a guard would keep claiming an entry that no longer exists
        (see :meth:`OverrideCursorGuard.notify_stack_drained`).
        """
        SwitchboardUtilsMixin.pop_override_cursor_stack(
            QtWidgets.QApplication.instance()
        )
        OverrideCursorGuard.notify_stack_drained()

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
            # Modal: suspend any slot busy-cursor so buttons show an arrow.
            with SwitchboardUtilsMixin._suspend_override_cursor():
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
        SwitchboardUtilsMixin._drain_override_cursor()
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
        file_types_string = f"{filter_description} ({' '.join(file_types)})"

        with SwitchboardUtilsMixin._suspend_override_cursor():
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
        with SwitchboardUtilsMixin._suspend_override_cursor():
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

        with SwitchboardUtilsMixin._suspend_override_cursor():
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
        with SwitchboardUtilsMixin._suspend_override_cursor():
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
        with SwitchboardUtilsMixin._suspend_override_cursor():
            accepted = dlg.exec_() == QtWidgets.QDialog.Accepted

        return [i.text() for i in listing.selectedItems()] if accepted else []

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
