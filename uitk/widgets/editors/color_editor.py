# !/usr/bin/python
# coding=utf-8
"""An embeddable colour editor, and the popup that is merely one of its hosts.

A colour picker is normally a dialog, which is why colour editing is normally
an interruption: the tool that needs the colour cannot show it. This is a plain
``QWidget`` first -- drop it into a panel, an option box, or a row beside a
second one so two ends of a ramp can be edited side by side -- and
:class:`ColorEditorPopup` is a thin host for the cases that genuinely want a
one-shot pick. It follows :class:`ColorMappingEditor` next door, which settled
the same shape.

**Sections are a registry, not a flag set.** "Simple by default, more when you
ask" is a real requirement, and spelling it as a set of feature names the
editor branches on means every new section edits this class. Instead each
section is a factory keyed by name, so a consumer -- a DCC that wants a
colour-management row, a tool that wants its own palette strip -- registers one
and names it, and nothing here changes.

Every section binds to the same :class:`ColorModel`, never to each other, so
adding one costs no wiring. The model stores float HSV: see its module for why
an 8-bit store would make the sliders unusable near black.
"""

import time
from typing import Callable, Dict, List, Optional, Sequence

from qtpy import QtCore, QtGui, QtWidgets

import pythontk as ptk
from uitk.managers.color_model import ColorModel
from uitk.widgets.gradient_slider import GradientSlider
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.separator import Separator


class ColorEditor(QtWidgets.QWidget, AttributesMixin):
    """A colour editor built from named sections, bound to one shared model.

    Parameters:
        color: Initial colour -- anything :meth:`ColorModel.to_rgbaf` reads.
        model: An existing :class:`ColorModel` to bind to instead of making
            one. Two editors sharing a model edit one colour; two editors with
            their own models are the two ends of a ramp.
        sections: Ordered section names always shown. ``None`` takes
            :attr:`DEFAULT_SECTIONS`.
        advanced: Ordered section names shown only when the disclosure is
            open. ``None`` takes :attr:`DEFAULT_ADVANCED`; an empty sequence
            removes the disclosure entirely.
        additive: The colour is LIGHT ADDED over an object (an emissive glow),
            not a colour the object becomes. The swatch draws it over the
            transparency board at an alpha of its brightness, so black reads
            as nothing added rather than as a black surface -- which an
            additive channel can never produce.
    """

    #: Live as the value is dragged.
    colorChanged = QtCore.Signal(QtGui.QColor)
    #: Once per finished edit -- what a caller should WRITE on: a drag on its
    #: release, a key, wheel or groove step as it lands, a hex entry, a palette
    #: click. Never for a value set on the model.
    colorCommitted = QtCore.Signal(QtGui.QColor)

    #: ``{name: (editor) -> QWidget}``. Extend with :meth:`register_section`.
    SECTIONS: Dict[str, Callable[["ColorEditor"], QtWidgets.QWidget]] = {}

    DEFAULT_SECTIONS = ("swatch", "hsv", "hex")
    DEFAULT_ADVANCED = ("rgb", "alpha")
    #: Caption of the disclosure the advanced sections open under.
    ADVANCED_TITLE = "Advanced"

    def __init__(
        self,
        color=None,
        model: Optional[ColorModel] = None,
        sections: Optional[Sequence[str]] = None,
        advanced: Optional[Sequence[str]] = None,
        parent=None,
        additive: bool = False,
        **kwargs,
    ):
        super().__init__(parent)
        #: See the class docstring; read by the swatch when it paints.
        self.additive = bool(additive)
        self._model = model if model is not None else ColorModel(color)
        if model is not None and color is not None:
            self._model.set_color(color)
        self._sliders: List[GradientSlider] = []
        self._built: Dict[str, QtWidgets.QWidget] = {}
        self._syncing = False

        self._names = tuple(self.DEFAULT_SECTIONS if sections is None else sections)
        self._advanced_names = tuple(
            self.DEFAULT_ADVANCED if advanced is None else advanced
        )
        self._build()
        self._model.subscribe(self._on_model_changed)
        # A model shared with another editor outlives this one; let go of it
        # rather than notify into a deleted widget. See GradientSlider.refresh.
        self.destroyed.connect(
            lambda _=None, m=self._model: m.unsubscribe(self._on_model_changed)
        )
        self.set_attributes(**kwargs)

    # ------------------------------------------------------------------
    # Value
    # ------------------------------------------------------------------

    @property
    def model(self) -> ColorModel:
        """The shared value. Bind a swatch or a second widget to this."""
        return self._model

    @property
    def color(self) -> ptk.Color:
        """The current colour as a :class:`pythontk.Color`."""
        return self._model.color

    @color.setter
    def color(self, value) -> None:
        self._model.set_color(value)

    def qcolor(self) -> QtGui.QColor:
        """The current colour as a ``QColor`` -- the Qt boundary.

        Quantised THROUGH :attr:`color` rather than from the raw floats, so the
        two ways out of this widget cannot disagree. ``QColor.fromRgbF`` and
        ``Color.from_rgbf`` round halves differently, which put the hex field
        and the Qt signal one unit apart on some values -- invisible on screen
        and a real mismatch for anything comparing what it wrote to what it
        reads back.
        """
        return QtGui.QColor(*self._model.color.rgba)

    def set_mixed(self, mixed: bool = True) -> None:
        """Show as indeterminate, for a selection whose colours disagree."""
        self._model.set_mixed(mixed)

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    @classmethod
    def register_section(
        cls, name: str, factory: Callable[["ColorEditor"], QtWidgets.QWidget]
    ) -> None:
        """Add (or replace) a section builder under *name*.

        The extension point: a consumer registers its own row and names it in
        ``sections=``/``advanced=`` without this class learning about it.
        """
        cls.SECTIONS[name] = factory

    def section(self, name: str) -> Optional[QtWidgets.QWidget]:
        """The built widget for *name*, or ``None`` if it was not asked for."""
        return self._built.get(name)

    def _build(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        for name in self._names:
            widget = self._make(name)
            if widget is not None:
                layout.addWidget(widget)

        if not self._advanced_names:
            return
        # A section header with its lid down, not a "More" button: the
        # advanced rows are a section of this editor, and a titled rule is how
        # every other section in a uitk column is captioned.
        self._disclosure = Separator(self, title=self.ADVANCED_TITLE, checkable=True)
        self._disclosure.setObjectName("advanced_toggle")
        self._disclosure.setToolTip("Show or hide the advanced colour controls.")
        layout.addWidget(self._disclosure)

        self._advanced_box = QtWidgets.QWidget(self)
        inner = QtWidgets.QVBoxLayout(self._advanced_box)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(2)
        for name in self._advanced_names:
            widget = self._make(name)
            if widget is not None:
                inner.addWidget(widget)
        self._advanced_box.setHidden(True)
        layout.addWidget(self._advanced_box)
        self._disclosure.toggled.connect(self._on_advanced_toggled)

    def _on_advanced_toggled(self, shown: bool) -> None:
        self._advanced_box.setHidden(not shown)

    def _make(self, name: str) -> Optional[QtWidgets.QWidget]:
        factory = self.SECTIONS.get(name)
        if factory is None:
            # An unknown name is a caller's typo or a section whose package is
            # not installed. Dropping it silently would leave a picker missing
            # a control with nothing to say why.
            import warnings

            warnings.warn(
                f"ColorEditor: no section registered as {name!r}; skipped. "
                f"Known: {', '.join(sorted(self.SECTIONS))}.",
                RuntimeWarning,
                stacklevel=3,
            )
            return None
        widget = factory(self)
        self._built[name] = widget
        return widget

    def add_slider(self, channel: str) -> GradientSlider:
        """A :class:`GradientSlider` on *channel*, bound and tracked.

        Sections build their sliders through this so the editor commits for
        every one of them without each section wiring it: a drag once, on its
        release; a key, wheel or groove step as it lands, since those send no
        release to wait for.
        """
        slider = GradientSlider(channel=channel, model=self._model, parent=self)
        slider.setObjectName(f"slider_{channel}")
        slider.sliderReleased.connect(self._emit_committed)
        # On the LANDED value, not on ``actionTriggered``: Qt emits that before
        # the step is applied, so a commit there hands out the colour being
        # left. A value set on the model emits no ``valueChangedF`` at all.
        slider.valueChangedF.connect(lambda _value, s=slider: self._commit_step(s))
        self._sliders.append(slider)
        return slider

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _on_model_changed(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            for _name, widget in self._built.items():
                sync = getattr(widget, "sync_from_model", None)
                if callable(sync):
                    sync()
            self.colorChanged.emit(self.qcolor())
        except RuntimeError:
            # Only OUR deletion is swallowed. A listener on `colorChanged` can
            # raise RuntimeError for reasons of its own, and treating those
            # alike would silently unbind a live editor from its colour.
            if not self._is_deleted():
                raise
            self._model.unsubscribe(self._on_model_changed)
        finally:
            self._syncing = False

    def _is_deleted(self) -> bool:
        """Whether the C++ side is gone (see :meth:`_on_model_changed`)."""
        try:
            self.objectName()
            return False
        except RuntimeError:
            return True

    def _emit_committed(self) -> None:
        self.colorCommitted.emit(self.qcolor())

    def _commit_step(self, slider: GradientSlider) -> None:
        """A slider's value landed: commit, unless it is mid-drag (add_slider)."""
        if not slider.isSliderDown():
            self._emit_committed()


# ----------------------------------------------------------------------
# Built-in sections
# ----------------------------------------------------------------------


class _Swatch(QtWidgets.QFrame):
    """A flat preview of the colour, striped when the value is mixed."""

    def __init__(self, editor: ColorEditor):
        super().__init__(editor)
        self._editor = editor
        self._checker = None  # the transparency board, built on first paint
        self.setMinimumHeight(22)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.sync_from_model()

    def sync_from_model(self) -> None:
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        model = self._editor.model
        rect = self.rect().adjusted(0, 0, -1, -1)
        if model.mixed:
            # Not the first object's colour: a selection that disagrees has no
            # single colour to show, and showing one invites overwriting the
            # rest with it.
            painter.fillRect(rect, QtGui.QColor(60, 60, 60))
            pen = QtGui.QPen(QtGui.QColor(140, 140, 140))
            pen.setWidth(1)
            painter.setPen(pen)
            step = 6
            for x in range(-rect.height(), rect.width(), step):
                painter.drawLine(
                    rect.left() + x,
                    rect.bottom(),
                    rect.left() + x + rect.height(),
                    rect.top(),
                )
        elif self._editor.additive:
            # Light added over the object: how MUCH is the alpha, so a dim
            # glow shows the board through it and none shows only the board.
            # A flat black would read as a black surface, which an additive
            # channel cannot produce.
            _paint_transparency_board(painter, rect, self)
            painter.fillRect(rect, _additive_color(model.rgbf))
        else:
            painter.fillRect(rect, QtGui.QColor.fromRgbF(*model.rgbf))
        painter.setPen(QtGui.QColor(0, 0, 0))
        painter.drawRect(rect)
        painter.end()


def _additive_color(rgb) -> QtGui.QColor:
    """*rgb* (display-encoded) as its hue at full strength, at an alpha of its
    brightness -- what an additive glow looks like over a transparency board."""
    r, g, b = (min(1.0, max(0.0, float(c))) for c in rgb[:3])
    brightest = max(r, g, b)
    if brightest <= 0.0:
        return QtGui.QColor(0, 0, 0, 0)
    return QtGui.QColor.fromRgbF(r / brightest, g / brightest, b / brightest, brightest)


def _paint_transparency_board(painter, rect, host, size: int = 8) -> None:
    """The board every compositor draws behind alpha, tiled into *rect*.

    One tiled fill, not a square per cell: a ramp preview repaints 30 times
    a second for as long as an option box is open, and a loop over the rect
    was a few hundred ``fillRect`` calls per frame to draw a constant. The
    brush is cached on *host* (``host._checker``) PER INSTANCE rather than
    at module level: a QPixmap belongs to the QApplication that was running
    when it was built, and one held past that app is how this codebase gets
    an access violation rather than an exception.
    """
    if host._checker is None:
        tile = QtGui.QPixmap(size * 2, size * 2)
        tile.fill(QtGui.QColor(120, 120, 120))
        marker = QtGui.QPainter(tile)
        dark = QtGui.QColor(90, 90, 90)
        marker.fillRect(0, 0, size, size, dark)
        marker.fillRect(size, size, size, size, dark)
        marker.end()
        host._checker = QtGui.QBrush(tile)
    painter.fillRect(rect, host._checker)


def _swatch_section(editor: ColorEditor) -> QtWidgets.QWidget:
    return _Swatch(editor)


def _slider_row(editor: ColorEditor, channels, labels) -> QtWidgets.QWidget:
    box = QtWidgets.QWidget(editor)
    grid = QtWidgets.QGridLayout(box)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(4)
    grid.setVerticalSpacing(2)
    for row, (channel, label) in enumerate(zip(channels, labels)):
        text = QtWidgets.QLabel(label, box)
        text.setMinimumWidth(12)
        grid.addWidget(text, row, 0)
        grid.addWidget(editor.add_slider(channel), row, 1)
    grid.setColumnStretch(1, 1)
    return box


def _hsv_section(editor: ColorEditor) -> QtWidgets.QWidget:
    return _slider_row(editor, ("hue", "saturation", "value"), ("H", "S", "V"))


def _rgb_section(editor: ColorEditor) -> QtWidgets.QWidget:
    return _slider_row(editor, ("red", "green", "blue"), ("R", "G", "B"))


def _alpha_section(editor: ColorEditor) -> QtWidgets.QWidget:
    return _slider_row(editor, ("alpha",), ("A",))


class _HexField(QtWidgets.QLineEdit):
    """A ``#RRGGBB`` field that only writes back when it parses."""

    def __init__(self, editor: ColorEditor):
        super().__init__(editor)
        self._editor = editor
        self.setObjectName("hex_field")
        self.setMaxLength(9)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.editingFinished.connect(self._commit)
        self.sync_from_model()

    def sync_from_model(self) -> None:
        model = self._editor.model
        text = "" if model.mixed else model.hex
        if text != self.text():
            self.blockSignals(True)
            self.setText(text)
            self.blockSignals(False)
        self.setPlaceholderText("mixed" if model.mixed else "")

    def _commit(self) -> None:
        # Typing a partial value is normal; snapping the field back on every
        # keystroke would make it unusable. An unparseable value is simply not
        # written, and the next sync restores the real one.
        if self._editor.model.set_color(self.text()):
            self._editor.colorCommitted.emit(self._editor.qcolor())
        else:
            self.sync_from_model()


def _hex_section(editor: ColorEditor) -> QtWidgets.QWidget:
    return _HexField(editor)


class _PaletteStrip(QtWidgets.QWidget):
    """A row of one-click preset colours."""

    def __init__(self, editor: ColorEditor, palette=None):
        super().__init__(editor)
        self._editor = editor
        # Built per instance, not held as a class attribute: ``Palette`` is a
        # dict subclass, so one shared on the class is shared MUTABLE state --
        # a caller that edited it would change every strip in the process.
        palette = palette if palette is not None else ptk.Palette.ui()
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        for key, value in palette.items():
            color = value.hex if hasattr(value, "hex") else value
            if ColorModel.to_rgbaf(color) is None:
                continue
            button = QtWidgets.QPushButton(self)
            button.setFixedSize(16, 16)
            button.setToolTip(str(key))
            button.setStyleSheet(
                f"QPushButton {{ background-color: {color};"
                f" border: 1px solid black; border-radius: 2px; }}"
            )
            button.clicked.connect(lambda _=False, c=color: self._pick(c))
            row.addWidget(button)
        row.addStretch(1)

    def _pick(self, color) -> None:
        self._editor.model.set_color(color)
        self._editor.colorCommitted.emit(self._editor.qcolor())

    def sync_from_model(self) -> None:
        """Nothing to show: the strip states presets, not the current value."""


def _palette_section(editor: ColorEditor) -> QtWidgets.QWidget:
    return _PaletteStrip(editor)


ColorEditor.SECTIONS.update(
    {
        "swatch": _swatch_section,
        "hsv": _hsv_section,
        "rgb": _rgb_section,
        "alpha": _alpha_section,
        "hex": _hex_section,
        "palette": _palette_section,
    }
)


# ----------------------------------------------------------------------
# Ramp preview
# ----------------------------------------------------------------------

#: One origin for every preview in the process. See :attr:`RampPreview.elapsed`.
_CLOCK_ORIGIN = time.monotonic()


class PulseWaveform:
    """A repeating cycle: hold high, ramp down, hold low, ramp up.

    The four keys a pulse keyer writes, read LINEARLY -- which is how the
    published ramp is read, so a spline here would show a curve the deliverable
    does not have.

    Parameters:
        period: Seconds for one whole cycle.
        duty: Share of the cycle spent at the high end.
        ramp: Share of the cycle each transition takes.
    """

    def __init__(self, period: float = 2.86, duty: float = 0.59, ramp: float = 0.25):
        self._period, self._duty, self._ramp = 2.86, 0.59, 0.25
        self.set_shape(period=period, duty=duty, ramp=ramp)

    def set_shape(self, period=None, duty=None, ramp=None) -> None:
        if period is not None:
            self._period = max(0.05, float(period))
        if duty is not None:
            self._duty = min(1.0, max(0.0, float(duty)))
        if ramp is not None:
            self._ramp = min(0.5, max(0.0, float(ramp)))

    @property
    def shape(self) -> dict:
        return {"period": self._period, "duty": self._duty, "ramp": self._ramp}

    @property
    def period(self) -> float:
        """Seconds the whole cycle takes -- what the phase tick measures."""
        return self._period

    def __call__(self, seconds: float) -> float:
        period = self._period
        ramp = self._ramp * period
        high = self._duty * period
        high_hold = max(0.0, high - ramp)
        low_hold = max(0.0, (period - high) - ramp)
        t = seconds % period
        if t < high_hold:
            return 1.0
        t -= high_hold
        if t < ramp:
            return 1.0 - (t / ramp) if ramp else 0.0
        t -= ramp
        if t < low_hold:
            return 0.0
        t -= low_hold
        return (t / ramp) if ramp else 1.0


class FadeWaveform:
    """One linear ramp between two holds -- what a two-key fade actually is.

    The holds are not padding. An animation curve holds its first value
    backwards and its last forwards, so either side of the ramp the object
    genuinely SITS at a value; showing the ramp alone would suggest a pulse.
    The loop's restart is a cut back to the origin, which is why the phase tick
    matters more here than on a cycle that closes on itself.

    ``direction="auto"`` ramps BOTH ways, because auto resolves per object at
    apply time from that object's last key. A preview that picked one would be
    claiming to know something it has not read.

    Parameters:
        duration: Seconds the ramp itself takes -- the keyed part.
        hold: Seconds held at each end before and after it.
        direction: ``"in"`` (0 to 1), ``"out"`` (1 to 0), or ``"auto"``.
    """

    DIRECTIONS = ("in", "out", "auto")

    def __init__(self, duration: float = 0.5, hold: float = 0.6, direction: str = "in"):
        self._duration, self._hold, self._direction = 0.5, 0.6, "in"
        self.set_shape(duration=duration, hold=hold, direction=direction)

    def set_shape(self, duration=None, hold=None, direction=None) -> None:
        if duration is not None:
            self._duration = max(0.05, float(duration))
        if hold is not None:
            self._hold = max(0.0, float(hold))
        if direction is not None:
            # An unknown direction reads as auto rather than raising: this is
            # driven by a combo box, and a preview must never be what stops an
            # option box from building.
            lowered = str(direction).lower()
            self._direction = lowered if lowered in self.DIRECTIONS else "auto"

    @property
    def shape(self) -> dict:
        return {
            "duration": self._duration,
            "hold": self._hold,
            "direction": self._direction,
        }

    @property
    def period(self) -> float:
        # TWO holds, always: the curve holds backwards before the ramp and
        # forwards after it. Counting one gave the destination hold zero
        # length, so a fade-in never showed the state it fades IN to.
        ramps = 2 if self._direction == "auto" else 1
        return self._hold * 2 + self._duration * ramps

    def __call__(self, seconds: float) -> float:
        t = seconds % self.period
        rising = self._direction != "out"
        if t < self._hold:  # the value the curve holds BACKWARDS
            return 0.0 if rising else 1.0
        t -= self._hold
        if t < self._duration:
            travelled = t / self._duration
            return travelled if rising else 1.0 - travelled
        if self._direction != "auto":  # held FORWARDS to the end of time
            return 1.0 if rising else 0.0
        # auto: back down again, because either direction is still on the table
        t -= self._duration
        if t < self._hold:
            return 1.0
        return 1.0 - ((t - self._hold) / self._duration)


class RampPreview(QtWidgets.QFrame):
    """Animates what a keyed channel does, as a flat 2D fill.

    Deliberately 2D and deliberately the EXPORTER's arithmetic rather than a
    lit 3D sphere: what ships is one value per frame, so a flat fill of exactly
    that value is not an approximation of the deliverable -- it IS the
    deliverable's value. A shaded preview would add lighting and a material the
    export does not have, which is the "preview that disagrees with the export"
    this repo has been bitten by before; the honest preview here is the cheap
    one.

    Both halves of that are INJECTED, so previewing a second channel is
    configuration rather than a second widget: *waveform* is how the keyer
    shapes time, and *values* is the channel's own ``(base, sample, stops) ->
    components`` -- hand it the exporter's function and the two cannot
    disagree by construction. How many components come back decides how the
    result is painted, exactly as it decides the glTF accessor type: three is
    an opaque colour, four carries alpha and is drawn over a checkerboard so
    transparency reads as transparency.

    The defaults are a repeating pulse over a generic ramp, which is what a
    consumer with no channel of its own means by "preview this ramp".

    Parameters:
        linear: The composite is LINEAR light -- a glTF factor, a DCC colour
            attribute -- and is painted display-encoded
            (``ptk.Color.srgb_from_linear``), so a mid value reads as the mid
            grey a page shows rather than the darker one raw numbers paint.
            Off, the components are painted as given: a ramp of display
            colours. See :meth:`display`.
        additive: A three-lane result is light ADDED over the object, so it
            is painted over the transparency board at an alpha of its
            brightness: none shows only the board, never a black surface.
    """

    #: Frames per second the preview animates at. Fast enough to read as
    #: motion, slow enough not to matter next to the panel it sits in.
    FPS = 30

    def __init__(
        self,
        stops=None,
        period=2.86,
        duty=0.59,
        ramp=0.25,
        parent=None,
        waveform=None,
        values=None,
        linear: bool = False,
        additive: bool = False,
    ):
        super().__init__(parent)
        self._linear = bool(linear)
        self._additive = bool(additive)
        self._stops = list(stops or [(0.2, 0.5, 1.0), (0.0, 0.0, 0.0)])
        self._wave = (
            waveform if waveform is not None else PulseWaveform(period, duty, ramp)
        )
        self._values = values
        self._base = (0.0, 0.0, 0.0)
        # The tiled transparency board, built on the first alpha paint. PER
        # INSTANCE rather than cached on the class: a QPixmap belongs to the
        # QApplication that was running when it was built, and one held on the
        # class outlives that app -- which in this codebase is how you get an
        # access violation rather than an exception. One 16 px tile per preview
        # is nothing; the cost this avoids was the per-cell loop, not the
        # allocation.
        self._checker = None
        self.setMinimumHeight(46)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._timer = QtCore.QTimer(self)
        # Straight to `update`: the clock is read in `paintEvent`, so a tick
        # has nothing to advance.
        self._timer.timeout.connect(self.update)

    # -- configuration --------------------------------------------------

    def set_stops(self, stops) -> None:
        """``[(r, g, b), ...]`` -- high end first."""
        self._stops = [tuple(float(c) for c in rgb[:3]) for rgb in stops]
        self.update()

    def set_shape(self, **shape) -> None:
        """Re-state the cadence, so the preview tracks the option box.

        Forwarded verbatim to the waveform, which is what names the arguments:
        a pulse takes ``period``/``duty``/``ramp``, a fade takes
        ``duration``/``hold``/``direction``.
        """
        self._wave.set_shape(**shape)

    @property
    def shape(self) -> dict:
        """The cadence this preview runs at, as :meth:`set_shape` takes it."""
        return self._wave.shape

    @property
    def waveform(self):
        """How this preview shapes time. See :class:`PulseWaveform`."""
        return self._wave

    @property
    def elapsed(self) -> float:
        """Seconds into the cycle, read off a clock shared by every preview.

        Shared rather than accumulated per widget for two reasons. Two previews
        shown side by side as a before/after must stay in PHASE, or the
        comparison is between two different moments of the cycle and says
        nothing. And an accumulating counter advances by a nominal frame
        regardless of when the timer actually fired, so a preview in a busy DCC
        ran slower than the seconds the artist typed.
        """
        return time.monotonic() - _CLOCK_ORIGIN

    def set_base(self, rgb) -> None:
        """The material's own emissive the channel composes OVER."""
        self._base = tuple(float(c) for c in rgb[:3])
        self.update()

    # -- the waveform ---------------------------------------------------

    def sample(self, seconds: float) -> float:
        """The channel's 0-1 value at *seconds* in, per this waveform."""
        return self._wave(seconds)

    def composite(self, sample: float):
        """The components the channel would carry at this *sample*.

        Three for a colour, four when the fourth is alpha -- whatever the
        injected ``values`` returns, which for an exporter's own function is
        whatever it writes.
        """
        if self._values is not None:
            return tuple(self._values(list(self._base), sample, tuple(self._stops)))
        hi = self._stops[0] if self._stops else (1.0, 1.0, 1.0)
        lo = self._stops[1] if len(self._stops) > 1 else (0.0, 0.0, 0.0)
        return tuple(
            min(1.0, max(0.0, self._base[i] + lo[i] + (hi[i] - lo[i]) * sample))
            for i in range(3)
        )

    def display(self, sample: float):
        """``(r, g, b, a)`` as PAINTED for *sample* -- see :meth:`composite`.

        The composite, display-encoded when the channel is linear, with the
        alpha the board shows through: a four-lane result carries its own (a
        fade); a three-lane one is opaque unless *additive*, where the alpha
        is the brightness and the colour its hue at full strength. Exposed so
        a test can assert what is painted without sampling pixels at an
        unknown phase of the clock.
        """
        return self._display(self.composite(sample))

    def _display(self, parts):
        rgb = [min(1.0, max(0.0, float(c))) for c in parts[:3]]
        if self._linear:
            rgb = [min(1.0, c) for c in ptk.Color.srgb_from_linear(rgb)]
        if len(parts) > 3:
            return (rgb[0], rgb[1], rgb[2], min(1.0, max(0.0, float(parts[3]))))
        if not self._additive:
            return (rgb[0], rgb[1], rgb[2], 1.0)
        color = _additive_color(rgb)
        return (color.redF(), color.greenF(), color.blueF(), color.alphaF())

    # -- Qt -------------------------------------------------------------

    def showEvent(self, event):
        # Runs only while visible: an animation behind a closed option box is
        # a timer nobody asked for.
        super().showEvent(event)
        self._timer.start(int(1000 / self.FPS))

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        rect = self.rect().adjusted(0, 0, -1, -1)
        elapsed = self.elapsed
        parts = self.composite(self.sample(elapsed))
        if self._additive or len(parts) > 3:
            # Alpha means the value is a transparency (or an amount of light
            # added), and a flat fill of a translucent colour on a panel reads
            # as a DARKER colour. The checkerboard makes it read as see-through.
            _paint_transparency_board(painter, rect, self)
        painter.fillRect(rect, QtGui.QColor.fromRgbF(*self._display(parts)))
        # A tick showing where in the cycle this is, so a slow pulse still
        # reads as running rather than as a widget that failed to paint.
        period = self._wave.period
        phase = (elapsed % period) / period
        painter.fillRect(
            QtCore.QRect(rect.left(), rect.bottom() - 2, int(rect.width() * phase), 3),
            QtGui.QColor(255, 255, 255, 70),
        )
        painter.setPen(QtGui.QColor(0, 0, 0))
        painter.drawRect(rect)
        painter.end()


# ----------------------------------------------------------------------
# Several ends of one ramp
# ----------------------------------------------------------------------


class ColorRampEditor(QtWidgets.QWidget):
    """One :class:`ColorEditor` per named end of a ramp, side by side.

    A channel that rides BETWEEN two colours is edited badly one colour at a
    time: the artist is choosing a RELATIONSHIP -- how far the bright end reads
    from the dim one -- and a modal that shows one end at a time hides exactly
    that. Both ends on screen is the affordance.

    Generic in the number of ends, because the thing it edits is
    :class:`pythontk.ColorStops` and a ramp is not inherently two-ended.

    **Columns run from the LOW end to the HIGH end, left to right**, the way
    a ramp is read; indices, ``labels``, ``colors`` and :meth:`decided` keep
    :class:`~pythontk.ColorStops` order (high first), so a consumer that
    reads ``bright, dim = ramp.decided()`` is unaffected by where each is drawn.

    Parameters:
        labels: One label per end, in :class:`~pythontk.ColorStops` order
            (high first). Two by default.
        colors: Initial colour per end; short sequences leave the rest alone.
        preview: Show a :class:`RampPreview` above the stops, animating the
            ramp with the pulse's own waveform.
        values: The channel's ``(base, sample, stops) -> components``, handed
            to every preview. Pass the EXPORTER's own function and the preview
            cannot drift from what ships.
        linear: Every channel value in and out of this widget -- the
            ``colors=`` argument, :meth:`set_colors`, :meth:`decided`,
            :meth:`set_reference` -- is LINEAR light, the channel's own space
            (a DCC colour attribute, a glTF factor). The editors show it
            display-encoded and hand back what the artist picked as linear,
            and the previews encode the same way; only the :attr:`colors`
            read-out stays what is displayed. What a picker shows is a display
            colour; an editor that hands those numbers to a linear channel
            reads a mid grey as a bright one, and the page then shows the glow
            brighter than the box did.
        additive: The channel is light ADDED over the object: the swatches and
            previews draw it over the transparency board at an alpha of its
            brightness, so a black end reads as nothing added rather than as
            a black surface (:class:`ColorEditor`, :class:`RampPreview`).
        editor_kwargs: Forwarded to every :class:`ColorEditor` -- pass
            ``advanced=()`` for a compact embedded row.
    """

    #: Live, as any end is dragged: ``(QColor, ...)`` in label order.
    colorsChanged = QtCore.Signal(tuple)
    #: Once an edit on any end finishes: every end, in label order.
    colorsCommitted = QtCore.Signal(tuple)
    #: The same commit, naming the end that was edited: ``(index, QColor)``.
    #: A consumer that WRITES on commit wants this one -- ``colorsCommitted``
    #: carries ends the artist never touched, and writing those through is how
    #: a nudge to Bright silently overwrites an authored Dim.
    stopCommitted = QtCore.Signal(int, QtGui.QColor)

    def __init__(
        self,
        labels: Sequence[str] = ("Bright", "Dim"),
        colors: Optional[Sequence] = None,
        parent=None,
        preview: bool = False,
        values=None,
        linear: bool = False,
        additive: bool = False,
        **editor_kwargs,
    ):
        super().__init__(parent)
        self._labels = tuple(labels)
        self._values = values
        self._linear = bool(linear)
        self._additive = bool(additive)
        self._editors: List[ColorEditor] = []
        #: Per end, the channel value it was set to and the model state that
        #: produced -- see :meth:`_channel_value`.
        self._authored: List[Optional[tuple]] = []
        colors = tuple(colors or ())

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        #: The live preview of what is being edited, or ``None``.
        self.preview: Optional[RampPreview] = None
        #: The look being replaced, shown beside it by :meth:`set_reference`.
        self.reference: Optional[RampPreview] = None
        if preview:
            previews = QtWidgets.QHBoxLayout()
            previews.setContentsMargins(0, 0, 0, 0)
            previews.setSpacing(6)
            outer.addLayout(previews)
            # Built up front rather than on the first comparison: a preview
            # created later would start its own layout pass inside whatever
            # popup is already on screen, and the pair has to be in phase
            # anyway, which a shared clock -- not a shared birthday -- gives.
            self._before, self._before_caption, self.reference = self._preview_column(
                "Current"
            )
            self._before.setVisible(False)
            previews.addWidget(self._before)
            self._after, self._after_caption, self.preview = self._preview_column(
                "Revised"
            )
            # Unlabelled until there is something to contrast it WITH: on its
            # own it is simply the preview, and "Revised" would be a claim
            # about a comparison that is not on screen.
            self._after_caption.setVisible(False)
            previews.addWidget(self._after)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        outer.addLayout(row)
        for index, label in enumerate(self._labels):
            column = QtWidgets.QVBoxLayout()
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(1)
            caption = QtWidgets.QLabel(label, self)
            caption.setAlignment(QtCore.Qt.AlignCenter)
            column.addWidget(caption)
            seed = colors[index] if index < len(colors) else None
            editor = ColorEditor(
                color=self._to_display(seed),
                parent=self,
                additive=self._additive,
                **editor_kwargs,
            )
            editor.setObjectName(f"editor_{label.lower()}")
            editor.colorChanged.connect(self._emit_changed)
            editor.colorCommitted.connect(
                lambda color, i=index: self._emit_committed(i, color)
            )
            column.addWidget(editor)
            # Inserted at the FRONT: the stops arrive high first, and a ramp
            # is read from its low end, so the last stop lands leftmost.
            row.insertLayout(0, column)
            self._editors.append(editor)
            self._authored.append(self._authored_state(editor, seed))

        if self.preview is not None:
            # The preview reads the stops rather than being pushed them, so a
            # change made anywhere -- a slider, the hex field, a palette click
            # -- reaches it by the one path every other widget here uses.
            for editor in self._editors:
                editor.colorChanged.connect(self._sync_preview)
            self._sync_preview()

    def _preview_column(self, caption: str):
        """``(container, caption label, preview)`` -- one captioned preview."""
        # Both halves run the same arithmetic, or the comparison is between
        # two different channels rather than two colourways of one.
        column = QtWidgets.QWidget(self)
        box = QtWidgets.QVBoxLayout(column)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(1)
        label = QtWidgets.QLabel(caption, column)
        label.setAlignment(QtCore.Qt.AlignCenter)
        box.addWidget(label)
        preview = RampPreview(
            parent=column,
            values=self._values,
            linear=self._linear,
            additive=self._additive,
        )
        box.addWidget(preview)
        return column, label, preview

    def _sync_preview(self, *_args) -> None:
        if self.preview is not None:
            self.preview.set_stops(
                [self._channel_value(i) for i in range(len(self._editors))]
            )

    # -- the channel's space vs the display's -------------------------------

    def _read_channel(self, value):
        """*value* as channel-space ``(r, g, b, a)`` floats, unclamped, or None.

        Linear, a bare sequence is floats whatever its range: a linear
        attribute may hold more than 1 (HDR emission), and bytes are a display
        encoding no linear channel uses. :meth:`ColorModel.to_rgbaf` reads
        anything over 1 as a byte, which divided ``(1.5, 0.75, 0.1)`` down to
        near-black.
        """
        if self._linear and isinstance(value, (list, tuple)) and len(value) in (3, 4):
            try:
                parts = [float(c) for c in value]
            except (TypeError, ValueError):
                return None
            return tuple(parts) if len(parts) == 4 else (*parts, 1.0)
        return ColorModel.to_rgbaf(value)

    def _to_display(self, value):
        """A channel value as the editor shows it (encoded when *linear*).

        Clamped to what a picker can show; the value as set is kept apart
        (:meth:`_channel_value`) rather than read back through the clamp.
        """
        if value is None or not self._linear:
            return value
        rgba = self._read_channel(value)
        if rgba is None:  # unreadable: let the model report it, not a slice
            return value
        rgb = [min(1.0, max(0.0, c)) for c in rgba[:3]]
        return (*ptk.Color.srgb_from_linear(rgb), min(1.0, max(0.0, rgba[3])))

    def _to_channel(self, rgbf):
        """An editor's display colour as the channel's value (linear when *linear*)."""
        rgb = tuple(float(c) for c in rgbf[:3])
        return ptk.Color.linear_from_srgb(rgb) if self._linear else rgb

    def _authored_state(self, editor, value) -> Optional[tuple]:
        """``(channel rgb, model hsva)`` for an end just set to *value*, or None."""
        rgba = None if value is None else self._read_channel(value)
        return None if rgba is None else (tuple(rgba[:3]), editor.model.hsva)

    def _channel_value(self, index: int) -> tuple:
        """End *index* in the channel's space: as SET, while nobody has edited it.

        An end whose model still holds the state its value produced hands that
        value back exactly: an over-range linear colour is SHOWN clamped, and
        a revision that only touched the other end must not write the clamp
        over it. Once edited, it is what the artist picked.
        """
        authored = self._authored[index]
        model = self._editors[index].model
        if authored is not None and authored[1] == model.hsva:
            return authored[0]
        return self._to_channel(model.rgbf)

    def set_shape(self, **shape) -> None:
        """Re-state the cadence on every preview, live one and reference both.

        Both, always: a comparison whose halves run at different cadences is
        showing two effects rather than two colourways of one.
        """
        for preview in (self.preview, self.reference):
            if preview is not None:
                preview.set_shape(**shape)

    def set_reference(self, stops) -> None:
        """Show *stops* (in the channel's space) beside the live ramp as the look being replaced.

        ``None`` hides it, which is the right answer twice over: when nothing
        is being replaced (a look is being authored, not revised), and when the
        targets DISAGREE -- there is no single current look to hold up, and
        picking one of them to show would be a lie about what is there.
        """
        if self.preview is None:
            return
        showing = stops is not None
        if showing:
            self.reference.set_stops(stops)
            self.reference.set_shape(**self.preview.shape)
        self._before.setVisible(showing)
        self._after_caption.setVisible(showing)

    # ------------------------------------------------------------------

    @property
    def labels(self) -> tuple:
        return self._labels

    @property
    def editors(self) -> tuple:
        return tuple(self._editors)

    def editor(self, which) -> ColorEditor:
        """The editor at an index, or under a label (case-insensitive)."""
        if isinstance(which, int):
            return self._editors[which]
        lowered = [label.lower() for label in self._labels]
        return self._editors[lowered.index(str(which).lower())]

    @property
    def colors(self) -> tuple:
        """The DISPLAYED colours, ``(pythontk.Color, ...)`` in label order.

        A read-out of the swatches (8-bit, display-encoded), whatever space
        the channel is in. A writer reads :meth:`decided`, which is in the
        channel's space and off the model's floats.
        """
        return tuple(editor.color for editor in self._editors)

    def decided(self) -> tuple:
        """One entry per end: its ``(r, g, b)``, or ``None`` if left MIXED.

        What a WRITER should read, in the channel's space (linear when the
        editor is). An end nobody decided is not a colour to write: an artist
        who only touched Bright must not flatten every object's Dim to
        whatever this widget happened to be seeded with. Read off the model's
        floats rather than the 8-bit swatch, so a dark linear value is not
        quantised on its way back to the channel -- and an end nobody EDITED
        comes back exactly as it was set, so an over-range value shown clamped
        is not written back clamped (:meth:`_channel_value`).
        """
        return tuple(
            None if editor.model.mixed else self._channel_value(index)
            for index, editor in enumerate(self._editors)
        )

    def set_colors(self, colors: Sequence) -> None:
        """Set each end, in the channel's space. ``None`` leaves that end alone.

        ``None`` is not "no colour" here: it is what an object that never
        authored that end reads as, and overwriting it with a default would
        turn "unstated" into a deliberate choice the artist did not make.
        """
        for index, (editor, color) in enumerate(zip(self._editors, colors)):
            if color is not None:
                editor.color = self._to_display(color)
                self._authored[index] = self._authored_state(editor, color)
        # Again, now the values are recorded: the change notification ran
        # before they were, and fed the preview the clamped display value.
        self._sync_preview()

    def set_mixed(self, which, mixed: bool = True) -> None:
        """Show one end as indeterminate (a selection that disagrees)."""
        self.editor(which).set_mixed(mixed)

    def _emit_changed(self, _color) -> None:
        self.colorsChanged.emit(tuple(e.qcolor() for e in self._editors))

    def _emit_committed(self, index: int, color) -> None:
        self.stopCommitted.emit(index, color)
        self.colorsCommitted.emit(tuple(e.qcolor() for e in self._editors))


# ----------------------------------------------------------------------
# Popup host
# ----------------------------------------------------------------------


class ColorEditorPopup(QtWidgets.QDialog):
    """A frameless host for ONE :class:`ColorEditor`.

    The only popup path in this module, so the editor never has to know
    whether it is in a dialog. Mirrors ``ColorMappingDialog`` next door.
    """

    def __init__(self, color=None, parent=None, title="Colour", **editor_kwargs):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(QtCore.Qt.Popup)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.editor = ColorEditor(color=color, parent=self, **editor_kwargs)
        layout.addWidget(self.editor)
        self._initial = self.editor.color

    def keyPressEvent(self, event):
        """Escape reverts to the colour the popup opened on.

        A live picker has no OK button to press, so what is on screen when it
        closes IS the answer -- clicking away accepts. That leaves no way to
        back out of an experiment, which the dialog this replaced had as its
        Cancel, so Escape restores the opening colour BEFORE closing. The
        editor is live, so the restore reaches whoever is bound to it too.
        """
        if event.key() == QtCore.Qt.Key_Escape:
            self.editor.color = self._initial
        super().keyPressEvent(event)

    @property
    def color(self) -> ptk.Color:
        return self.editor.color

    def qcolor(self) -> QtGui.QColor:
        return self.editor.qcolor()

    @classmethod
    def get_color(cls, initial=None, parent=None, title="Colour", **editor_kwargs):
        """Open on *initial* and answer the chosen ``QColor``, or ``None``.

        A drop-in for ``QColorDialog.getColor``, so a call site swaps one line.
        A live popup has no OK button, so what is on screen when it closes IS
        the answer: clicking away accepts, and Escape reverts to the colour it
        opened on (see :meth:`keyPressEvent`). ``None`` is the answer when there
        is nothing to write -- Escape, or a close on the opening colour -- so a
        caller that writes on an answer leaves the value, and whatever writing
        it would dirty, alone.
        """
        popup = cls(color=initial, parent=parent, title=title, **editor_kwargs)
        if parent is not None:
            popup.move(parent.mapToGlobal(parent.rect().bottomLeft()))
        popup.exec_() if hasattr(popup, "exec_") else popup.exec()
        chosen = None if popup.color == popup._initial else popup.qcolor()
        # A parent keeps the popup alive: one hidden dialog per pick, otherwise.
        popup.deleteLater()
        return chosen
