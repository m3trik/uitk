# !/usr/bin/python
# coding=utf-8
"""Shared input handling for spin-box widgets: the modifier-driven wheel
step (:class:`WheelStepMixin`) and the *adjusting* state a debounced slot
waits on (:class:`SpinBoxAdjustingMixin`).

Used by :class:`uitk.widgets.spinBox.SpinBox` and
:class:`uitk.widgets.doubleSpinBox.DoubleSpinBox`. Both widgets derive
from ``QDoubleSpinBox`` and previously duplicated the same dispatch +
helper methods; these mixins pull the contract into one place.

Modifier ladder (wheel scroll only) — symmetric: ``Ctrl`` scales the
step **up** ×10, ``Alt`` scales it **down** ×10, and stacking with
``Shift`` (on Ctrl) or stacking ``Ctrl`` (on Alt) amplifies to the
extremes::

    plain         singleStep                       (default Qt step)
    Ctrl          singleStep × 10                  (coarse)
    Ctrl+Shift    singleStep × 100                 (very coarse)
    Alt           singleStep / 10                  (fine)
    Ctrl+Alt      10 ** -decimals                  (smallest)

Mnemonic — *Ctrl scales up, Alt scales down; stacking amplifies.*
``Ctrl+Alt`` returns the smallest representable step at the widget's
configured precision; for ``decimals == 0`` (integer-style spin-boxes)
that bottoms out at ``1``, so ``Ctrl+Alt`` and the plain step agree.
``Alt`` on the same int spin-box would compute ``singleStep / 10``,
which is below the integer precision floor; :meth:`_step_value`
detects this and no-ops honestly (accepts the event to suppress Qt's
default stepping, but skips ``setValue`` and the HUD so the user
isn't told a step happened when none did).

Position gate (all wheels, modified or not) — inside something that can
scroll, a wheel only moves the value when it lands on the **drawn value**,
give or take ``WheelStepMixin.wheel_margin`` px. A field stretched wide by
its layout is mostly empty space, and a wheel out there is a user scrolling
the panel past the box rather than aiming at its number, so those events are
left *unaccepted* and Qt walks them up to the scroll area. With nothing above
the box to scroll there is nothing to give the wheel to, and the box keeps it
wherever it lands. Only a box with real room beside its value gives any of it
up (``_AIMABLE_FIELD_PX``), so an ordinary panel field is covered end to end
and behaves exactly as before.

Direction is read from whichever axis of ``event.angleDelta()`` carries
the delta — some platforms (X11, certain Qt6 builds) transpose
``angleDelta()`` from ``.y()`` to ``.x()`` when Alt is held, so a bare
``.y() > 0`` check would silently stop responding to Alt- and Ctrl+Alt-
wheel scrolls.
"""

from qtpy import QtCore, QtGui, QtWidgets

from uitk.widgets.mixins.spin_box_display import _TextMetrics


class WheelStepMixin:
    """Mixin: modifier-driven wheel handling for ``QAbstractSpinBox`` subclasses.

    Subclasses inherit from this *before* the Qt spin-box base so the
    mixin's ``wheelEvent`` wins in the MRO; the plain (no-modifier)
    branch calls ``super().wheelEvent(event)`` to fall through to Qt's
    default stepping.

    Subclasses can implement :meth:`show_feedback` (or inherit it from
    :class:`uitk.widgets.mixins.feedback.FeedbackMixin`) to surface a
    transient HUD with the step amount. If the method is absent, the
    mixin silently no-ops the feedback.
    """

    # Px of slack on either side of the drawn value within which a wheel
    # still counts as aimed at it (see :meth:`_wheel_targets_value`) -- a few
    # characters' worth, so the number stays an easy target without the
    # cursor having to be on it. Set it wider for a box whose value is a
    # small mark in a large field; set it to ``None`` to drop the gate
    # entirely, so any wheel landing anywhere on the box steps the value.
    # Readable as a class default (a subclass sets its own), per instance, or
    # declaratively -- ``SpinBox(wheel_margin=None)`` /
    # ``set_attributes(wheel_margin=64)``.
    wheel_margin = 32

    # Px of field that has to sit beside the value -- on its emptier side,
    # measured from the value's own edge -- before any of it is given up.
    # Under this, the box reads as ONE target and keeps every wheel. It is a
    # calibration, not a taste setting, so it is stated in px and does NOT
    # scale with ``wheel_margin``: widening the slack is a request for an
    # easier target, not for fewer boxes to be gated. Anchored on what the
    # ecosystem actually authors: the house spin box is 70 px (32 of them
    # across mayatk / tentacle / blendertk; the rest are sized by their
    # layout), which under the uitk theme -- whose QSS collapses the step
    # arrows to nothing -- leaves ~36 px of field beside a short value. 96 px
    # clears that with room, which keeps the house field and the next size up
    # (~110 px) live end to end; past there a box stops reading as one target
    # and starts having somewhere to scroll from. (Measured from the value's
    # edge on EITHER side, so a right-aligned value is gated like a left one;
    # measured past the margin, as it was, this read 64 and moved with it.)
    _AIMABLE_FIELD_PX = 96

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self._wheel_targets_value(event):
            # Leave it unaccepted: Qt walks an ignored wheel up the parent
            # chain, so the panel the box sits in scrolls instead of the
            # value moving under a cursor that was only passing through.
            event.ignore()
            return

        modifiers = event.modifiers()
        ctrl = bool(modifiers & QtCore.Qt.ControlModifier)
        alt = bool(modifiers & QtCore.Qt.AltModifier)
        shift = bool(modifiers & QtCore.Qt.ShiftModifier)

        if ctrl and alt:
            self._step_value(event, 10 ** -self.decimals())
        elif ctrl and shift:
            self._step_value(event, self.singleStep() * 100)
        elif ctrl:
            self._step_value(event, self.singleStep() * 10)
        elif alt:
            self._step_value(event, self.singleStep() / 10)
        else:
            super().wheelEvent(event)

    # -- position gate -------------------------------------------------------

    def _wheel_targets_value(self, event: QtGui.QWheelEvent) -> bool:
        """Whether *event* landed on the drawn value, or within its margin.

        Deliberately uniform: the modifier ladder picks the step *size*,
        position alone decides whether there is a step at all, so one spot on
        the field behaves the same way whatever is held. It is indifferent to
        focus too -- a wheel over empty field space reads as a scroll whether
        or not the box was the last thing clicked.

        Anything that cannot be measured (no embedded editor, nothing drawn)
        counts as on-value: an unmeasurable box behaves as it did before the
        gate rather than going deaf to the wheel. So does a box with no room
        to aim past its value -- see ``_AIMABLE_FIELD_PX`` -- and a box with
        nothing above it that could scroll the wheel instead: a wheel handed
        up to a panel that cannot scroll does nothing at all, and a dead wheel
        over most of a stretched field is worse than the step it replaced.
        """
        margin = self.wheel_margin
        if margin is None:
            return True
        if not self._wheel_scrolls_an_ancestor(event):
            return True
        measured = self._value_span()
        if measured is None:
            return True
        start, end, chrome, field = measured
        pos = event.position() if hasattr(event, "position") else event.pos()
        x = pos.x()
        # Past the editor lies the box's own chrome -- the step arrows, which
        # are as much a value affordance as the number, and which the theme
        # may have collapsed to nothing (then there is nothing out there to
        # hit and the test is moot).
        if x >= chrome:
            return True
        # Nothing beside the value worth aiming at: the box is one target and
        # keeps the wheel wherever it lands (see ``_AIMABLE_FIELD_PX``).
        if max(start - field, chrome - end) < self._AIMABLE_FIELD_PX:
            return True
        return (start - margin) <= x <= (end + margin)

    def _wheel_scrolls_an_ancestor(self, event: QtGui.QWheelEvent) -> bool:
        """Whether a scroll area above the box would take *event* instead.

        Qt hands an ignored wheel up the parent chain, and a scroll area sends
        it to its bar on the wheel's axis (the one with the larger delta) --
        so "somewhere to scroll" means an ancestor ``QAbstractScrollArea``
        whose bar on that axis has a range. A panel with none -- most of them
        -- has nowhere to hand the wheel.
        """
        delta = event.angleDelta()
        horizontal = abs(delta.x()) > abs(delta.y())
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QtWidgets.QAbstractScrollArea):
                bar = (
                    parent.horizontalScrollBar()
                    if horizontal
                    else parent.verticalScrollBar()
                )
                if bar is not None and bar.maximum() > bar.minimum():
                    return True
            if parent.isWindow():
                break
            parent = parent.parentWidget()
        return False

    def _value_span(self):
        """``(start, end, chrome, field)`` in widget px, or ``None`` if unmeasurable.

        ``start``/``end`` bound the value as drawn (suffix included, prefix
        excluded); ``chrome`` is where the editor stops and the step arrows
        begin, ``field`` where its text area starts. Measured through ``QTextLayout`` rather than ``QFontMetrics``
        because a tab-separated prefix (see
        :class:`uitk.widgets.mixins.spin_box_display.PrefixColumnMixin`) puts
        the value at a tab *stop* -- tens of px right of where the advance of
        the label alone would put it, which would leave the gate's zone
        sitting over the label instead of the number.
        """
        editor = self.lineEdit()
        if editor is None:
            return None
        text = self.text()
        if not text:
            return None
        prefix = self.prefix()
        if not text.startswith(prefix):
            # ``specialValueText`` replaces the whole string, prefix included.
            prefix = ""
        # The editor is what draws the text, so it is its font that decides
        # where the characters land (the box's own, propagated, in every
        # ordinary case).
        (start, end), width = _TextMetrics.x_positions(
            text, editor.font(), (len(prefix), len(text))
        )
        editor_x = editor.mapTo(self, QtCore.QPoint(0, 0)).x()
        margins = editor.textMargins()
        origin = editor_x + margins.left()
        # The editor lays its text out under the box's alignment; Qt's default
        # is left, which needs no offset.
        available = editor.width() - margins.left() - margins.right()
        alignment = self.alignment()
        if alignment & QtCore.Qt.AlignRight:
            origin += max(0, available - width)
        elif alignment & QtCore.Qt.AlignHCenter:
            origin += max(0, (available - width) / 2)
        field = editor_x + margins.left()
        return origin + start, origin + end, editor_x + editor.width(), field

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _wheel_direction(event: QtGui.QWheelEvent) -> int:
        """Return +1 / -1 / 0 for the wheel's net direction.

        Read both axes: under some Qt builds / platforms the Alt modifier
        transposes ``angleDelta`` onto ``.x()``. Picking whichever is
        non-zero keeps Alt and Ctrl+Alt scrolls responsive without caring
        which axis Qt routed the delta to.
        """
        delta = event.angleDelta()
        signed = delta.y() or delta.x()
        if signed > 0:
            return 1
        if signed < 0:
            return -1
        return 0

    def _step_value(self, event: QtGui.QWheelEvent, adjustment: float) -> None:
        direction = self._wheel_direction(event)
        if direction == 0:
            return
        # Consume the event even on no-op so Qt's default wheel handler
        # doesn't also step by ``singleStep`` underneath us.
        event.accept()
        # Qt's own wheel steps only where ``stepEnabled`` allows (never on a
        # read-only box, never past a bound): the modified wheels hold to the
        # same rule rather than writing the value around it.
        allowed = (
            QtWidgets.QAbstractSpinBox.StepUpEnabled
            if direction > 0
            else QtWidgets.QAbstractSpinBox.StepDownEnabled
        )
        if self.isReadOnly() or not (self.stepEnabled() & allowed):
            return
        # Honest no-op when ``adjustment`` is below the widget's display
        # precision: e.g. Alt on a ``decimals=0`` SpinBox gives
        # ``singleStep/10 == 0.1``, which would set an internal float
        # below the integer display threshold -- the user would see no
        # change *and* the HUD would lie about a step happening. Skipping
        # both keeps the display, the storage, and the feedback consistent.
        if adjustment < 10 ** -self.decimals():
            return
        self.setValue(self.value() + direction * adjustment)
        self._notify(adjustment)

    def _notify(self, adjustment: float) -> None:
        """Emit step feedback via :meth:`show_feedback` if the host has it."""
        notifier = getattr(self, "show_feedback", None)
        if notifier is None:
            return
        notifier(f"Step: <font color='yellow'>{adjustment:g}</font>")


class SpinBoxAdjustingMixin:
    """Mixin: the *adjusting* state of a ``QAbstractSpinBox`` subclass.

    ``adjusting`` is True while the user is still on the value -- a mouse
    button held on the box (an arrow auto-repeating, a drag) or an edit
    typed but not yet committed (Enter or focus-out interprets it). The
    switchboard's debounced dispatch (``widget.debounce``, see
    ``SlotWrapper``) holds a slot while its widget reports ``adjusting``,
    so a slot that re-renders something on every value runs once, when the
    user is done, instead of on each step of the way. Inherit *before* the
    Qt spin-box base so the event overrides win in the MRO.
    """

    _adjust_mouse_held = False

    @property
    def adjusting(self) -> bool:
        """True while a mouse button is held on the box or a typed edit is
        uncommitted -- a debounced slot waits for this to clear."""
        if self._adjust_mouse_held:
            # A release the box never saw (hidden or reparented mid-press)
            # must not hold a slot forever: trust the live button state.
            if QtWidgets.QApplication.mouseButtons() == QtCore.Qt.NoButton:
                self._adjust_mouse_held = False
            else:
                return True
        edit = self.lineEdit()
        return bool(edit is not None and self.hasFocus() and edit.isModified())

    def mousePressEvent(self, event) -> None:
        self._adjust_mouse_held = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._adjust_mouse_held = False
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        super().keyPressEvent(event)
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self._mark_committed()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._mark_committed()

    def _mark_committed(self) -> None:
        """Enter and focus-out interpret the text; Qt leaves the line edit
        flagged modified when the interpreted value did not change it, so
        clear the flag by hand or the edit reads as unfinished until the
        next programmatic set."""
        edit = self.lineEdit()
        if edit is not None:
            edit.setModified(False)
