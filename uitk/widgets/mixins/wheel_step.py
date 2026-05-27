# !/usr/bin/python
# coding=utf-8
"""Shared modifier-driven wheel-step handling for spin-box widgets.

Used by :class:`uitk.widgets.spinBox.SpinBox` and
:class:`uitk.widgets.doubleSpinBox.DoubleSpinBox`. Both widgets derive
from ``QDoubleSpinBox`` and previously duplicated the same dispatch +
helper methods; this mixin pulls the contract into one place.

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

Direction is read from whichever axis of ``event.angleDelta()`` carries
the delta — some platforms (X11, certain Qt6 builds) transpose
``angleDelta()`` from ``.y()`` to ``.x()`` when Alt is held, so a bare
``.y() > 0`` check would silently stop responding to Alt- and Ctrl+Alt-
wheel scrolls.
"""
from qtpy import QtCore, QtGui


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

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
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
