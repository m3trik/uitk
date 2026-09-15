# !/usr/bin/python
# coding=utf-8
"""A slider whose track shows the colour it is about to set."""

from typing import Optional

from qtpy import QtCore

from uitk.widgets.slider import Slider
from uitk.managers.color_model import ColorModel

#: Integer steps a channel is divided into. QSlider is integral, and a colour
#: channel is a float, so the widget works in thousandths: finer than the
#: 8-bit value anything downstream stores, so quantisation never shows up as a
#: slider that will not sit where it was dropped.
STEPS = 1000


class GradientSlider(Slider):
    """A :class:`Slider` whose groove is the live ramp of one colour channel.

    Bind it to a :class:`ColorModel` and name a channel; it then draws that
    channel's ramp THROUGH the model's current colour (the saturation track
    greys out at the model's own hue, the value track darkens the model's own
    colour) and writes back to the model as it is dragged.

    **The track is a stylesheet gradient, not a custom paint.** The theme
    already styles ``QAbstractSlider::groove`` with a solid colour and paints
    ``::sub-page``/``::add-page`` over it, so a ``paintEvent`` would be
    fighting three rules it cannot see. An attribute selector outranks the bare
    type rule, so the ramp is stated as QSS and the theme keeps its handle.

    The gradient depends on the live colour, so it CANNOT live in ``style.qss``
    and is set inline on the instance -- the same arrangement as
    ``ColorSwatch``, and with the same hazard: a stylesheet re-applied over the
    tree wipes it. :meth:`refresh` puts it back, and is called on every polish
    so a theme change repairs itself.
    """

    designer_spec = {"icon": "move", "object_name": "gradient_slider"}

    #: Emitted with the channel's new 0-1 value as the handle moves.
    valueChangedF = QtCore.Signal(float)

    #: How each channel draws, and how it reads and writes the model. Adding a
    #: channel is adding a row -- the widget branches on nothing.
    CHANNELS = ("hue", "saturation", "value", "alpha", "red", "green", "blue")

    def __init__(self, parent=None, channel: str = "value", model=None, **kwargs):
        super().__init__(parent)
        if channel not in self.CHANNELS:
            raise ValueError(
                f"Unknown colour channel {channel!r}. Known: {', '.join(self.CHANNELS)}."
            )
        self._channel = channel
        self._model: Optional[ColorModel] = None
        self._applying = False
        self.setRange(0, STEPS)
        self.setSingleStep(max(1, STEPS // 100))
        self.setPageStep(max(1, STEPS // 10))
        self.setProperty("class", self.__class__.__name__)
        super().valueChanged.connect(self._on_slider_moved)
        self.set_attributes(**kwargs)
        self.bind(model if model is not None else ColorModel())

    # ------------------------------------------------------------------
    # Binding
    # ------------------------------------------------------------------

    @property
    def channel(self) -> str:
        return self._channel

    @property
    def model(self) -> Optional[ColorModel]:
        return self._model

    def bind(self, model: ColorModel) -> None:
        """Drive (and be driven by) *model*, releasing any previous one."""
        if self._model is model:
            return
        if self._model is not None:
            self._model.unsubscribe(self.refresh)
        self._model = model
        if model is not None:
            model.subscribe(self.refresh)
            # The model outlives the widget -- that is the point of sharing it
            # -- so a slider that does not let go is a notification into a
            # deleted C++ object. Qt tells us when that happens; `self.refresh`
            # still resolves on the Python wrapper at that moment, and bound
            # methods compare equal, so the unsubscribe finds its entry.
            self.destroyed.connect(lambda _=None, m=model: m.unsubscribe(self.refresh))
        self.refresh()

    # ------------------------------------------------------------------
    # Channel access
    # ------------------------------------------------------------------

    def _read(self) -> float:
        """This channel's current 0-1 value, off the model."""
        m = self._model
        if m is None:
            return 0.0
        if self._channel == "hue":
            return m.hue
        if self._channel == "saturation":
            return m.saturation
        if self._channel == "value":
            return m.value
        if self._channel == "alpha":
            return m.alpha
        return m.rgbf[_RGB_INDEX[self._channel]]

    def _write(self, amount: float) -> None:
        """Set this channel to *amount* on the model, leaving the rest alone."""
        m = self._model
        if m is None:
            return
        if self._channel in ("hue", "saturation", "value", "alpha"):
            m.set_hsv(**{_HSV_KWARG[self._channel]: amount})
            return
        # An rgb channel is a partial write to a value the model stores as HSV,
        # so it has to round-trip the other two. Reading them back off the
        # model rather than off the widget is what keeps the hue the artist set
        # when a channel is dragged to zero.
        rgb = list(m.rgbf)
        rgb[_RGB_INDEX[self._channel]] = amount
        m.set_rgbf(*rgb)

    # ------------------------------------------------------------------
    # Painting (via the stylesheet)
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Re-read the model: move the handle and redraw the track.

        Guarded against its own C++ object being gone. Two paths reach here
        after deletion and neither is avoidable by ordering: a queued restyle
        (:meth:`event`) fires on the next turn of the loop, and ``destroyed``
        is emitted DURING destruction, so a sibling widget's notification can
        arrive between the two. It unsubscribes itself on the way out rather
        than raising into whoever happened to set the colour.
        """
        if self._model is None:
            return
        # `_applying` spans the STYLESHEET write as well as the handle move,
        # and that is load-bearing rather than tidy: `setStyleSheet` raises a
        # StyleChange, `event` answers a StyleChange by queueing a refresh, and
        # a refresh sets the stylesheet -- so a narrower guard makes this
        # function schedule itself forever. Measured before the fix: 5707
        # refreshes in 400 ms of an IDLE event loop, one core pegged for as
        # long as a picker is on screen. No unit test saw it because the queued
        # restyle only fires on a spinning loop.
        self._applying = True
        try:
            self.setValue(int(round(self._read() * STEPS)))
            qss = self._qss()
            # Compared against the widget's LIVE stylesheet rather than a
            # cached string: a theme applied over the tree replaces it, and a
            # cache would then agree with itself and skip the repair. Every
            # model change refreshes every bound slider, so on a hue drag the
            # saturation and value tracks re-polish each frame for nothing
            # without this.
            if self.styleSheet() != qss:
                self.setStyleSheet(qss)
        except RuntimeError:
            if not self._is_deleted():
                raise
            self._model.unsubscribe(self.refresh)
            self._model = None
        finally:
            self._applying = False

    def _is_deleted(self) -> bool:
        """Whether the C++ side is gone.

        Asked before swallowing a ``RuntimeError``: shiboken raises it for a
        deleted object, but so does plenty of honest Qt misuse, and treating
        those alike would silently unbind a live widget from its colour.
        """
        try:
            self.objectName()
            return False
        except RuntimeError:
            return True

    def _qss(self) -> str:
        stops = ", ".join(
            f"stop:{at:.4f} {_rgba(rgba)}" for at, rgba in self._gradient_stops()
        )
        name = self.__class__.__name__
        return (
            f'{name}[class="{name}"]::groove,\n'
            f'QSlider[class="{name}"]::groove {{\n'
            f"    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {stops});\n"
            f"}}\n"
            # The theme paints these solid OVER the groove; the ramp is the
            # whole point of this widget, so for this class they stand aside.
            f'{name}[class="{name}"]::sub-page,\n'
            f'{name}[class="{name}"]::add-page,\n'
            f'QSlider[class="{name}"]::sub-page,\n'
            f'QSlider[class="{name}"]::add-page {{\n'
            f"    background: transparent;\n"
            f"}}\n"
        )

    def _gradient_stops(self):
        """``[(position, (r, g, b, a)), ...]`` in 0-1, for this channel."""
        m = self._model
        h, s, v, a = m.hsva
        if self._channel == "hue":
            # Six segments, seven stops: fewer and the ramp visibly bends away
            # from the hues between them.
            return [
                (
                    i / 6.0,
                    _hsv(i / 6.0, max(s, 0.001) if s else 1.0, max(v, 0.25)) + (1.0,),
                )
                for i in range(7)
            ]
        if self._channel == "saturation":
            return [
                (0.0, _hsv(h, 0.0, max(v, 0.25)) + (1.0,)),
                (1.0, _hsv(h, 1.0, max(v, 0.25)) + (1.0,)),
            ]
        if self._channel == "value":
            return [(0.0, (0.0, 0.0, 0.0, 1.0)), (1.0, _hsv(h, s, 1.0) + (1.0,))]
        if self._channel == "alpha":
            rgb = _hsv(h, s, v)
            return [(0.0, rgb + (0.0,)), (1.0, rgb + (1.0,))]
        index = _RGB_INDEX[self._channel]
        low, high = list(m.rgbf), list(m.rgbf)
        low[index], high[index] = 0.0, 1.0
        return [(0.0, tuple(low) + (1.0,)), (1.0, tuple(high) + (1.0,))]

    # ------------------------------------------------------------------
    # Qt
    # ------------------------------------------------------------------

    def _on_slider_moved(self, raw: int) -> None:
        if self._applying:
            return
        amount = raw / float(STEPS)
        self._write(amount)
        self.valueChangedF.emit(amount)

    def event(self, event):
        # A theme applied over the tree replaces this widget's stylesheet with
        # the shared one, taking the ramp with it. Qt polishes the widget again
        # when that happens, so the ramp is restated there rather than left for
        # each caller to remember.
        if event.type() == QtCore.QEvent.StyleChange and not self._applying:
            # Deferred: setting the stylesheet from inside a style change would
            # re-enter. `refresh` tolerates the widget being gone by then.
            QtCore.QTimer.singleShot(0, self.refresh)
        return super().event(event)


_HSV_KWARG = {"hue": "h", "saturation": "s", "value": "v", "alpha": "a"}
_RGB_INDEX = {"red": 0, "green": 1, "blue": 2}


def _hsv(h: float, s: float, v: float):
    import colorsys

    return colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))


def _rgba(rgba) -> str:
    r, g, b, a = rgba
    return f"rgba({int(r * 255)}, {int(g * 255)}, {int(b * 255)}, {a:.3f})"
