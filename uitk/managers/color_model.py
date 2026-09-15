# !/usr/bin/python
# coding=utf-8
"""The observable colour value a picker and its widgets share.

A colour editor is several widgets -- a square, a row of sliders, a hex field,
a swatch -- all showing and setting ONE value. Wiring them to each other is
what turns into signal spaghetti and recursive-update guards, so they bind to
this instead: each subscribes, each writes, and none of them knows the others
exist.

**The working value is float HSV, not RGB, and that is the whole point.** Hue
and saturation are undefined in RGB as value approaches zero, so a model that
stored 8-bit RGB and re-derived HSV for the sliders would destroy the state the
sliders are editing: measured on a blue at hue 0.58 / saturation 0.80, dragging
value to 0 and back returns WHITE, and saturation has already drifted to 0.67
by a value of 0.01. That is not a corner case for a two-ended highlight ramp,
whose dim end is expected to sit near black -- exactly the band where an 8-bit
model is least stable. ``pythontk.Color`` stays the boundary type, for
persistence and for handing the value out; it is never the store.

Deliberately Qt-free, like the other services here: it is the thing widgets
depend ON, and a model that cannot be tested without a QApplication is a model
every test has to build a window for.
"""

import colorsys
from typing import Callable, List, Optional, Tuple

import pythontk as ptk


class ColorModel:
    """One observable colour, stored as float HSVA with the authored hue kept.

    Subscribe with :meth:`subscribe`; mutate with :meth:`set_hsv`,
    :meth:`set_rgbf` or :meth:`set_color`. Every mutation that changes the value
    notifies once.
    """

    def __init__(self, color=None, mixed: bool = False) -> None:
        self._h = 0.0
        self._s = 0.0
        self._v = 1.0
        self._a = 1.0
        self._mixed = False
        self._subscribers: List[Callable[[], None]] = []
        self._muted = 0
        self._dirty = False
        if color is not None:
            self.set_color(color, notify=False)
        # After the colour, not before: every setter clears the flag, so a
        # model constructed as mixed-with-a-seed would come back determinate.
        self._mixed = bool(mixed)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    @property
    def hsva(self) -> Tuple[float, float, float, float]:
        """``(h, s, v, a)`` in 0-1 -- the stored value, exactly as authored."""
        return (self._h, self._s, self._v, self._a)

    @property
    def hue(self) -> float:
        """The AUTHORED hue, which survives a trip through black or grey.

        Reading it back off the rgb would answer 0.0 there, which is what makes
        a value slider jump to red on the way up.
        """
        return self._h

    @property
    def saturation(self) -> float:
        return self._s

    @property
    def value(self) -> float:
        return self._v

    @property
    def alpha(self) -> float:
        return self._a

    @property
    def rgbf(self) -> Tuple[float, float, float]:
        """``(r, g, b)`` in 0-1 -- what a DCC attribute or shader wants."""
        return colorsys.hsv_to_rgb(self._h, self._s, self._v)

    @property
    def rgbaf(self) -> Tuple[float, float, float, float]:
        return self.rgbf + (self._a,)

    @property
    def color(self) -> ptk.Color:
        """The value as a :class:`pythontk.Color` -- the boundary type.

        Quantised to 8 bits per channel, so it is what you PERSIST or hand out,
        never what you edit through.
        """
        return ptk.Color.from_rgbf(*self.rgbf, self._a)

    @property
    def hex(self) -> str:
        return self.color.hex

    @property
    def mixed(self) -> bool:
        """Whether this stands for several values that disagree.

        A multi-object edit that silently shows the first object's colour is
        telling the artist something untrue, and the first drag then writes it
        to every object. A mixed model displays as indeterminate and clears on
        the first committed edit.
        """
        return self._mixed

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def set_hsv(
        self,
        h: Optional[float] = None,
        s: Optional[float] = None,
        v: Optional[float] = None,
        a: Optional[float] = None,
        notify: bool = True,
    ) -> bool:
        """Set any subset of the components. Returns whether anything changed.

        Hue wraps; the rest clamp. Omitted components are left alone, which is
        what lets a value slider drive V without touching the hue it is drawn
        against.
        """
        before = (self._h, self._s, self._v, self._a, self._mixed)
        if h is not None:
            self._h = float(h) % 1.0
        if s is not None:
            self._s = _clamp(s)
        if v is not None:
            self._v = _clamp(v)
        if a is not None:
            self._a = _clamp(a)
        self._mixed = False
        return self._changed(before, notify)

    def set_rgbf(self, r, g, b, a: Optional[float] = None, notify: bool = True) -> bool:
        """Set from 0-1 floats, KEEPING the authored hue where rgb cannot say.

        Black and grey carry no hue, so taking the converted 0.0 would throw
        away what the artist set the moment a colour passes through them. The
        same holds for saturation at black.
        """
        h, s, v = colorsys.rgb_to_hsv(_clamp(r), _clamp(g), _clamp(b))
        before = (self._h, self._s, self._v, self._a, self._mixed)
        self._v = v
        # s == 0 means "grey": the rgb states no hue, so the stored one stands.
        if s > 0.0:
            self._h = h
            self._s = s
        elif v > 0.0:
            # A deliberate grey: saturation really is zero, hue still unstated.
            self._s = 0.0
        if a is not None:
            self._a = _clamp(a)
        self._mixed = False
        return self._changed(before, notify)

    def set_color(self, value, notify: bool = True) -> bool:
        """Set from anything :meth:`to_rgbaf` understands.

        Accepts a :class:`pythontk.Color`, a ``#RRGGBB[AA]`` string, a 3- or
        4-sequence of 0-1 floats or 0-255 ints, or another :class:`ColorModel`.
        """
        rgba = self.to_rgbaf(value)
        if rgba is None:
            return False
        return self.set_rgbf(*rgba[:3], a=rgba[3], notify=notify)

    @classmethod
    def to_rgbaf(cls, value) -> Optional[Tuple[float, float, float, float]]:
        """Read a colour in any shape this package passes around into 0-1 floats.

        One reader rather than one per widget: a picker is handed colours by Qt, by
        a ``.ui`` file, by a DCC attribute and by persisted settings, and each
        spells them differently. Returns ``None`` for anything unreadable, so a
        caller can decline rather than invent a colour.
        """
        if value is None:
            return None
        if isinstance(value, ColorModel):
            return value.rgbaf
        if isinstance(value, ptk.Color):
            return value.rgbaf
        if isinstance(value, str):
            try:
                return ptk.Color.from_hex(value).rgbaf
            except (ValueError, AttributeError):
                return None
        # A QColor (duck-typed, so this module stays Qt-free).
        getter = getattr(value, "getRgbF", None)
        if callable(getter):
            try:
                return tuple(float(c) for c in getter()[:4])
            except (TypeError, ValueError, IndexError):
                return None
        if isinstance(value, (list, tuple)) and len(value) in (3, 4):
            try:
                nums = [float(c) for c in value]
            except (TypeError, ValueError):
                return None
            # 0-255 ints and 0-1 floats are both in use, and nothing in the value
            # says which. Anything over 1 can only be the byte range; below that
            # the reading is FLOATS, because that is what the DCCs this feeds hand
            # out (Maya and Blender both state colour as 0-1) and what every other
            # branch above produces. The ambiguity is real rather than harmless --
            # ``(1, 1, 1)`` is white as floats and near-black as bytes -- so a
            # caller holding bytes should say so by passing a value over 1 in some
            # channel, or hand over a ``Color``/hex string instead of a bare tuple.
            if any(n > 1.0 for n in nums):
                nums = [n / 255.0 for n in nums]
            if len(nums) == 3:
                nums.append(1.0)
            return tuple(_clamp(n) for n in nums)
        return None

    def set_mixed(self, mixed: bool = True, notify: bool = True) -> bool:
        """Mark (or clear) the indeterminate state without touching the value."""
        before = (self._h, self._s, self._v, self._a, self._mixed)
        self._mixed = bool(mixed)
        return self._changed(before, notify)

    # ------------------------------------------------------------------
    # Observer
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable[[], None]) -> None:
        """Register *callback* (no args) to run after any change."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[], None]) -> None:
        """Remove a callback (no-op if absent)."""
        try:
            self._subscribers.remove(callback)
        except ValueError:
            pass

    def muted(self) -> "_Mute":
        """Context manager coalescing every change inside it into ONE notify.

        A slider that sets hue and saturation together should repaint the
        square once, not twice.
        """
        return _Mute(self)

    def _changed(self, before, notify: bool) -> bool:
        after = (self._h, self._s, self._v, self._a, self._mixed)
        if after == before:
            return False
        if notify:
            self._notify()
        else:
            self._dirty = True
        return True

    def _notify(self) -> None:
        if self._muted:
            self._dirty = True
            return
        self._dirty = False
        for cb in list(self._subscribers):
            try:
                cb()
            except Exception:
                # A misbehaving presenter must not break the model or the
                # other subscribers.
                pass

    def __repr__(self) -> str:
        state = " mixed" if self._mixed else ""
        return f"ColorModel({self.hex!r}{state})"


class _Mute:
    """Suspends notification for a block; fires once on the way out."""

    def __init__(self, model: ColorModel) -> None:
        self._model = model

    def __enter__(self) -> ColorModel:
        self._model._muted += 1
        return self._model

    def __exit__(self, *exc) -> bool:
        self._model._muted -= 1
        if not self._model._muted and self._model._dirty:
            self._model._notify()
        return False


def _clamp(value) -> float:
    return max(0.0, min(1.0, float(value)))
