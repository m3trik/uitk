# !/usr/bin/python
# coding=utf-8
"""A soft drop shadow under a frameless top-level window.

Qt style sheets have no ``box-shadow``. Painting one inside the window would
need a transparent margin around every window, which shifts every placement,
hit test and saved geometry by that margin. The window's own blur
(:mod:`uitk._window_blur`) would also frost the margin, because the blur
covers the whole native window. So the shadow is a window of its own: a
companion ``QRasterWindow``, the size of its target plus the shadow's reach.
It ignores input, never takes focus, sits directly beneath its target, and
paints only outside the target's shape. A filter on the target
(:class:`_ShadowKeeper`) keeps it on the target's geometry, visibility,
opacity and stacking, and it dies with the target.

It is a ``QWindow``, not a ``QWidget``, so it never appears in
``QApplication.topLevelWidgets()`` or ``allWidgets()``, never inherits a
style sheet, and nothing that walks widgets can register, style or close it.

Stacking per window system, from ``QGuiApplication.platformName()``:

- ``windows`` -- one ``SetWindowPos(shadow, insertAfter=target)``, which puts
  the shadow directly beneath its target without moving the target.
- ``offscreen`` -- the shadow is raised, then its target. Nothing composites
  there, but the same contract still runs under test.

Elsewhere it is a no-op. The macOS window server already shadows every
frameless window. Native Wayland places windows itself, so a companion could
not follow one. X11 has no tested stacking path here yet. Like
:mod:`uitk._bootstrap`, this module imports no widget or Switchboard module.
"""

import ctypes
import functools
import sys
from typing import Callable, Optional, Tuple, Union

from qtpy import QtCore, QtGui, QtWidgets

#: ``(color, size, radius)``: the shadow's color (its alpha is the strength),
#: its reach beyond the window edge in px, and the window's corner radius in px.
ShadowSpec = Tuple[Union[QtGui.QColor, str], int, int]
#: A :data:`ShadowSpec` as :meth:`_WindowShadow.normalize` returns it.
_Spec = Tuple[QtGui.QColor, int, int]


class _Win32Stack:
    """Windows: ``SetWindowPos`` with the target as ``hWndInsertAfter``.

    This places the shadow directly beneath the target in one call, with no
    activation, no move or size change, and no reordering of the owner. The
    shadow and its target share an owner (see :meth:`_ShadowKeeper._present`),
    so raising the owner keeps the pair together.
    """

    PLATFORMS = ("windows",)

    _SWP_FLAGS = (
        0x0001 | 0x0002 | 0x0010 | 0x0200
    )  # NOSIZE|NOMOVE|NOACTIVATE|NOOWNERZORDER
    _fn = None

    @classmethod
    def available(cls) -> bool:
        return sys.platform == "win32"

    @classmethod
    def restack(cls, shadow: QtGui.QWindow, target: QtWidgets.QWidget) -> None:
        if cls._fn is None:
            from ctypes import wintypes

            fn = ctypes.windll.user32.SetWindowPos
            fn.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4
            fn.argtypes += [ctypes.c_uint]
            fn.restype = wintypes.BOOL
            cls._fn = fn
        cls._fn(int(shadow.winId()), int(target.winId()), 0, 0, 0, 0, cls._SWP_FLAGS)


class _RaiseStack:
    """Raise the shadow, then its target.

    Raises the target's ``QWindow`` rather than the widget, because
    ``QWidget.raise_`` sends the ``ZOrderChange`` that the keeper restacks on.
    """

    PLATFORMS = ("offscreen",)

    @classmethod
    def available(cls) -> bool:
        return True

    @classmethod
    def restack(cls, shadow: QtGui.QWindow, target: QtWidgets.QWidget) -> None:
        shadow.raise_()
        handle = target.windowHandle()
        if handle is not None:
            handle.raise_()


class _ShadowProfile:
    """The shadow's alpha across one axis: a step the target's length, blurred.

    The blur is three box blurs of radius ``k``, which closely approximates a
    gaussian and reaches exactly ``3k`` px past each end of the step. The value
    at the target's edge is one half, as with CSS ``box-shadow``. The shadow is
    separable: its alpha is the product of the x and y profiles, each painted
    as :meth:`bands` (see :meth:`_ShadowWindow.paint`), exact at any window
    size, small tooltips included.
    """

    PASSES = 3

    @staticmethod
    def kernel(size: int) -> int:
        """The box radius for a shadow *size* px long (at least 1)."""
        return max(1, round(size / _ShadowProfile.PASSES))

    @staticmethod
    def reach(size: int) -> int:
        """How far, in px, a shadow of *size* actually reaches past the edge."""
        return _ShadowProfile.kernel(size) * _ShadowProfile.PASSES

    @staticmethod
    def values(length: int, size: int) -> Tuple[float, ...]:
        """Alpha (0-1) at each px of ``length + 2 * reach(size)``: the exact
        profile, in O(length). Painting reads :meth:`bands`, which needs it
        only for a window too short for its two edges to stay apart."""
        k = _ShadowProfile.kernel(size)
        reach = k * _ShadowProfile.PASSES
        values = [0.0] * reach + [1.0] * max(0, length) + [0.0] * reach
        for _ in range(_ShadowProfile.PASSES):
            values = _ShadowProfile._box(values, k)
        # Rounded off the float noise of the running sums: exactly symmetric,
        # and a constant run stays constant (see :meth:`stops`).
        return tuple(round(v, 6) for v in values)

    @staticmethod
    def _box(values: list, k: int) -> list:
        """One box blur of radius *k*, zero beyond both ends."""
        n, width = len(values), 2 * k + 1
        prefix = [0.0]
        for v in values:
            prefix.append(prefix[-1] + v)
        return [
            (prefix[min(n, i + k + 1)] - prefix[max(0, i - k)]) / width
            for i in range(n)
        ]

    @staticmethod
    @functools.lru_cache(maxsize=32)
    def _edge(size: int) -> Tuple[float, ...]:
        """A long step's rising edge, from ``reach`` px outside it to ``reach``
        px inside, where it is exactly 1: what every window long enough
        shares, so one per size is all that is kept."""
        reach = _ShadowProfile.reach(size)
        return _ShadowProfile.values(2 * reach + 1, size)[: 2 * reach + 1]

    @staticmethod
    def bands(length: int, size: int) -> list:
        """The profile for a window *length* px long, as ``(start, end,
        values)`` spans covering ``length + 2 * reach``: one alpha per px, or
        ``None`` for a run that is exactly 1.

        A window long enough that its two edges never meet is the shared
        :meth:`_edge` at each end and a solid run between, so nothing is kept
        per length. Each
        edge is painted as a gradient of its own: a gradient spanning a whole
        window resolves through Qt's 1024-entry color table, a step of
        several px on a long window's steep edges.
        """
        reach = _ShadowProfile.reach(size)
        n = length + 2 * reach
        if length > 2 * reach + 1:  # else the edges share a px (or overlap)
            edge = _ShadowProfile._edge(size)
            e = len(edge)
            return [(0, e, edge), (e, n - e, None), (n - e, n, edge[::-1])]
        return [(0, n, _ShadowProfile.values(length, size))]

    @staticmethod
    def fill(
        painter: QtGui.QPainter,
        size: QtCore.QSize,
        length: int,
        shadow_size: int,
        color: QtGui.QColor,
        horizontal: bool,
    ) -> None:
        """Fill a *size* window with *color* along one axis's profile: across
        its width when *horizontal*, else down its height."""
        alpha = color.alphaF()
        across = size.height() if horizontal else size.width()
        for start, end, values in _ShadowProfile.bands(length, shadow_size):
            if end <= start:
                continue
            if horizontal:
                rect = QtCore.QRectF(start, 0, end - start, across)
            else:
                rect = QtCore.QRectF(0, start, across, end - start)
            if values is None:
                painter.fillRect(rect, color)
                continue
            line = rect.topRight() if horizontal else rect.bottomLeft()
            gradient = QtGui.QLinearGradient(rect.topLeft(), line)
            stops = []
            for i, v in enumerate(values):
                c = QtGui.QColor(color)
                c.setAlphaF(max(0.0, min(1.0, alpha * v)))
                stops.append(((i + 0.5) / len(values), c))
            gradient.setStops(stops)
            painter.fillRect(rect, gradient)


class _ShadowWindow(QtGui.QRasterWindow):
    """The companion window that paints one target's shadow.

    It is top-level and input-transparent, never takes focus, and has no
    native shadow of its own. Its ``QObject`` parent is the keeper, so it is
    deleted with its target. That parent is set only on the ``QObject`` side,
    so the window stays top-level rather than becoming a child window.
    """

    NAME = "uitk_window_shadow"
    FLAGS = (
        QtCore.Qt.Tool
        | QtCore.Qt.FramelessWindowHint
        | QtCore.Qt.WindowTransparentForInput
        | QtCore.Qt.WindowDoesNotAcceptFocus
        | QtCore.Qt.NoDropShadowWindowHint
    )
    #: How far the shadow drops below the window, as a share of its reach:
    #: light from just above, the modern elevation look.
    DROP = 0.25

    @classmethod
    def flags_for(cls, platform: str) -> QtCore.Qt.WindowFlags:
        """:attr:`FLAGS`, typed ``ToolTip`` on the offscreen platform: it
        activates every window it shows but a tooltip, ignoring
        ``WindowDoesNotAcceptFocus``, so a shadow there took the focus and
        closed a cell editor open in its window. Stacking means nothing there.
        """
        if platform != "offscreen":
            return cls.FLAGS
        mask = int(QtCore.Qt.WindowType_Mask)  # PySide's ~ on a flag mangles it
        kept = int(cls.FLAGS) & ~mask
        return QtCore.Qt.WindowType(kept | int(QtCore.Qt.ToolTip))

    def __init__(self, keeper: QtCore.QObject):
        super().__init__()
        QtCore.QObject.setParent(self, keeper)
        self.setObjectName(self.NAME)
        fmt = self.format()
        fmt.setAlphaBufferSize(8)
        self.setFormat(fmt)
        self.setFlags(self.FLAGS)  # retyped per platform at each show (_present)
        self.setProperty("_q_showWithoutActivating", True)
        self.spec: Optional[_Spec] = None
        self._target = QtCore.QSize()

    @classmethod
    def margins(cls, size: int) -> QtCore.QMargins:
        """Space the shadow takes around its target: ``reach`` on each side,
        less the drop at the top and more at the bottom."""
        reach = _ShadowProfile.reach(size)
        drop = min(reach, round(reach * cls.DROP))
        return QtCore.QMargins(reach, reach - drop, reach, reach + drop)

    def fit(self, target: QtCore.QRect, spec: _Spec) -> None:
        """Cover *target* (global geometry) plus the shadow *spec* reaches."""
        if spec != self.spec or target.size() != self._target:
            self.spec, self._target = spec, target.size()
            self.update()
        self.setGeometry(target.marginsAdded(self.margins(spec[1])))

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override
        painter = QtGui.QPainter(self)
        try:
            self.paint(painter, self.size())
        finally:
            painter.end()

    def paint(self, painter: QtGui.QPainter, size: QtCore.QSize) -> None:
        """Paint the shadow for a window of *size*.

        The y profile is painted, the x profile multiplied in with
        ``DestinationIn``, and the target's rounded shape cleared, so nothing
        is painted beneath a translucent target.
        """
        if self.spec is None or self._target.isEmpty():
            return
        color, shadow_size, radius = self.spec
        m = self.margins(shadow_size)
        tw, th = self._target.width(), self._target.height()

        painter.setPen(QtCore.Qt.NoPen)
        _ShadowProfile.fill(painter, size, th, shadow_size, color, horizontal=False)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_DestinationIn)
        _ShadowProfile.fill(
            painter, size, tw, shadow_size, QtGui.QColor(0, 0, 0), horizontal=True
        )
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_Clear)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(QtCore.Qt.black)
        painter.drawRoundedRect(
            QtCore.QRectF(m.left(), m.top(), tw, th), radius, radius
        )


class _ShadowKeeper(QtCore.QObject):
    """Keeps a window's shadow on it. It is a child of the window, so it dies
    with it, and :meth:`_WindowShadow.set` finds it by name.

    ``shadow`` is a :data:`ShadowSpec` or a ``(window) -> ShadowSpec | None``
    resolver, read each time the shadow is presented. The shadow window is made
    on first need. It is presented one event-loop turn after the target shows,
    because Qt sends ``Show`` before it maps the native window, and stacking
    beneath an unmapped window does not hold.
    """

    NAME = "uitk_shadow_keeper"

    def __init__(self, widget: QtWidgets.QWidget, shadow):
        super().__init__(widget)
        self.setObjectName(self.NAME)
        self.shadow = shadow
        self.window: Optional[_ShadowWindow] = None
        self._handle: Optional[QtGui.QWindow] = None
        self._restacking = False
        # A child timer rather than singleShot(ms, context, fn), which PySide
        # 6.5.3 (Maya 2025) lacks.
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._present)
        widget.installEventFilter(self)

    def spec(self, widget: QtWidgets.QWidget):
        """The normalized spec *widget* casts now, or None."""
        if not _WindowShadow.casts(widget):
            return None
        try:
            spec = self.shadow(widget) if callable(self.shadow) else self.shadow
        except Exception:  # noqa: BLE001 -- a failing resolver: no shadow, no crash
            return None
        return _WindowShadow.normalize(spec)

    def refresh(self) -> None:
        """Re-read the spec: present the shadow if the window shows, else hide it."""
        widget = self.parent()
        if widget is not None and widget.isVisible():
            self._watch(widget)
            self._timer.start(0)
        else:
            self._hide()

    def retire(self) -> None:
        """Stop following the window and drop its shadow."""
        widget = self.parent()
        if widget is not None:
            widget.removeEventFilter(self)
        self._timer.stop()
        self._watch(None)
        if self.window is not None:
            self.window.setVisible(False)
            self.window.deleteLater()
            self.window = None
        self.setParent(None)
        self.deleteLater()

    def eventFilter(self, obj, event):  # noqa: N802 -- Qt override
        t = event.type()
        if t in (QtCore.QEvent.Show, QtCore.QEvent.WinIdChange):
            self.refresh()
        elif t == QtCore.QEvent.Hide:
            self._hide()
        elif t in (QtCore.QEvent.Move, QtCore.QEvent.Resize):
            self._fit(obj)
        elif t in (QtCore.QEvent.WindowActivate, QtCore.QEvent.ZOrderChange):
            self._restack(obj)
        elif t == QtCore.QEvent.WindowStateChange:
            self.refresh()
        return False

    def _watch(self, widget: Optional[QtWidgets.QWidget]) -> None:
        """Follow *widget*'s native window's visibility and opacity.

        ``Hide`` alone is not trusted: the native window can hide without the
        widget's ``hideEvent`` reaching this filter, and a shadow left behind
        is a dark rectangle over the desktop.
        """
        handle = widget.windowHandle() if widget is not None else None
        if handle is self._handle:
            return
        if self._handle is not None:
            try:
                self._handle.visibleChanged.disconnect(self._on_visible)
                self._handle.opacityChanged.disconnect(self._on_opacity)
            except (RuntimeError, TypeError):  # gone with its native window
                pass
        self._handle = handle
        if handle is not None:
            handle.visibleChanged.connect(self._on_visible)
            handle.opacityChanged.connect(self._on_opacity)

    def _on_visible(self, visible: bool) -> None:
        if visible:
            self._timer.start(0)
        else:
            self._hide()

    def _on_opacity(self, level: float) -> None:
        if self.window is not None:
            self.window.setOpacity(level)

    def _present(self) -> None:
        widget = self.parent()
        spec = self.spec(widget) if widget is not None and widget.isVisible() else None
        if spec is None:
            self._hide()
            return
        if self.window is None:
            self.window = _ShadowWindow(self)
        window = self.window
        flags = _ShadowWindow.flags_for(QtGui.QGuiApplication.platformName())
        if _WindowShadow.topmost(widget):
            flags |= QtCore.Qt.WindowStaysOnTopHint
        if window.flags() != flags:
            window.setFlags(flags)
        # The target's owner, so the pair stays together when the owner is
        # raised. Never the target itself: an owned window sits above its owner.
        handle = widget.windowHandle()
        owner = handle.transientParent() if handle is not None else None
        if window.transientParent() is not owner:
            window.setTransientParent(owner)
        window.fit(widget.geometry(), spec)
        window.setOpacity(widget.windowOpacity())
        if not window.isVisible():
            # Stacked once before it maps as well as after, so its first frame
            # never lands above the target.
            window.create()
            self._restack(widget, force=True)
            window.setVisible(True)
        self._restack(widget)

    def _fit(self, widget: QtWidgets.QWidget) -> None:
        window = self.window
        if window is not None and window.isVisible() and window.spec is not None:
            window.fit(widget.geometry(), window.spec)

    def _restack(self, widget: QtWidgets.QWidget, force: bool = False) -> None:
        window = self.window
        if self._restacking or window is None or not (force or window.isVisible()):
            return
        self._restacking = True
        try:
            _WindowShadow.restack(window, widget)
        except Exception:  # noqa: BLE001 -- a native call failed: keep going
            pass
        finally:
            self._restacking = False

    def _hide(self) -> None:
        self._timer.stop()
        if self.window is not None:
            self.window.setVisible(False)


class _WindowShadow:
    """The stacking backend for this window system, and the per-window
    bookkeeping behind :meth:`Bootstrap.set_shadow` / :meth:`Bootstrap.shadows`."""

    BACKENDS = (_Win32Stack, _RaiseStack)

    #: Window types that are frameless whatever their flags say.
    _BARE_TYPES = (QtCore.Qt.Popup, QtCore.Qt.ToolTip, QtCore.Qt.SplashScreen)
    #: Window types that float above everything else (Qt makes them topmost).
    _TOPMOST_TYPES = (QtCore.Qt.Popup, QtCore.Qt.ToolTip)
    #: Window types never shadowed: not a floating surface.
    _SKIP_TYPES = (
        QtCore.Qt.Widget,
        QtCore.Qt.Desktop,
        QtCore.Qt.SubWindow,
        QtCore.Qt.ForeignWindow,
    )

    #: The backend class for this process's Qt platform, resolved once on
    #: first use with an application; False = none.
    _backend = None

    @classmethod
    def backend(cls):
        if cls._backend is None:
            if QtGui.QGuiApplication.instance() is None:
                return None  # no platform yet: decide once there is one
            platform = QtGui.QGuiApplication.platformName()
            cls._backend = next(
                (b for b in cls.BACKENDS if platform in b.PLATFORMS), False
            )
        return cls._backend or None

    @classmethod
    def available(cls) -> bool:
        backend = cls.backend()
        return bool(backend and backend.available())

    @classmethod
    def restack(cls, shadow: QtGui.QWindow, target: QtWidgets.QWidget) -> None:
        backend = cls.backend()
        if backend is not None:
            backend.restack(shadow, target)

    @classmethod
    def casts(cls, widget: QtWidgets.QWidget) -> bool:
        """Whether *widget* is a window a shadow belongs under.

        It must be a frameless top-level, since a framed window gets the
        window manager's shadow with its frame. It must not be minimized,
        maximized, full screen, or covering its whole screen, since then no
        edge shows anything behind it.
        """
        if not widget.isWindow():
            return False
        wtype = widget.windowType()
        if wtype in cls._SKIP_TYPES:
            return False
        if wtype not in cls._BARE_TYPES and not (
            widget.windowFlags() & QtCore.Qt.FramelessWindowHint
        ):
            return False
        if widget.windowState() & (
            QtCore.Qt.WindowMinimized
            | QtCore.Qt.WindowMaximized
            | QtCore.Qt.WindowFullScreen
        ):
            return False
        screen = widget.screen()
        return screen is None or not widget.geometry().contains(screen.geometry())

    @classmethod
    def topmost(cls, widget: QtWidgets.QWidget) -> bool:
        """Whether *widget* stays above ordinary windows, so its shadow must too."""
        return widget.windowType() in cls._TOPMOST_TYPES or bool(
            widget.windowFlags() & QtCore.Qt.WindowStaysOnTopHint
        )

    @staticmethod
    def normalize(spec) -> Optional[_Spec]:
        """*spec* as ``(QColor, size, radius)``, or None when it casts nothing
        (no spec, a size under 1 px, or an invalid or fully clear color)."""
        if not spec:
            return None
        color, size, radius = spec
        color = QtGui.QColor(color)
        size, radius = int(size), max(0, int(radius))
        if size < 1 or not color.isValid() or color.alpha() == 0:
            return None
        return color, size, radius

    @classmethod
    def set(
        cls,
        widget: QtWidgets.QWidget,
        shadow: Union[
            ShadowSpec, None, Callable[[QtWidgets.QWidget], Optional[ShadowSpec]]
        ],
    ) -> bool:
        """See :meth:`Bootstrap.set_shadow`."""
        keeper = widget.findChild(
            _ShadowKeeper, _ShadowKeeper.NAME, QtCore.Qt.FindDirectChildrenOnly
        )
        if not (callable(shadow) or shadow) or not cls.available():
            if keeper is not None:  # only a window this set shadows is reset
                keeper.retire()
            return False
        # A popup gets Qt's native drop shadow on Windows (CS_DROPSHADOW).
        # This shadow replaces it, so the theme is the one source of truth.
        # The hint is set only before the native window exists: setting it
        # afterwards would recreate the window. setWindowFlags, not
        # setWindowFlag: on a popup PySide 6.10 drops the hint from the latter.
        flags = widget.windowFlags()
        if (
            widget.isWindow()
            and widget.windowType() == QtCore.Qt.Popup
            and not widget.testAttribute(QtCore.Qt.WA_WState_Created)
            and not flags & QtCore.Qt.NoDropShadowWindowHint
        ):
            widget.setWindowFlags(flags | QtCore.Qt.NoDropShadowWindowHint)
        if keeper is None:
            keeper = _ShadowKeeper(widget, shadow)
        else:
            keeper.shadow = shadow
        keeper.refresh()
        return keeper.spec(widget) is not None
