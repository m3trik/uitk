# !/usr/bin/python
# coding=utf-8
"""Blur behind a translucent top-level window, per window system.

Qt draws a window into its own backing store and never sees the desktop
behind it, so no Qt API can blur that; the compositor that blends the
windows can, and each window system asks for it differently. One backend
per window system, chosen from ``QGuiApplication.platformName()``:

- ``windows`` -- the DWM accent blur (Windows 10+).
- ``xcb`` -- KWin's ``_KDE_NET_WM_BLUR_BEHIND_REGION`` window property,
  through ``ptk.X11`` (KDE Plasma; other X11 window managers offer none).
- ``cocoa`` -- an ``NSVisualEffectView`` behind the window's content view.

Native Wayland and every other platform have no backend: there the blur is a
no-op and the window keeps its plain translucent background. Like
:mod:`uitk._bootstrap`, this module imports no widget or Switchboard module.
"""

import ctypes
import ctypes.util
import sys
from typing import Callable, Optional, Union

from qtpy import QtCore, QtGui, QtWidgets


class _DwmBlur:
    """Windows 10+: ``SetWindowCompositionAttribute(ACCENT_ENABLE_BLURBEHIND)``.

    Undocumented but stable since Windows 10, and the one call that blurs a
    frameless *layered* window -- what Qt makes of a frameless
    ``WA_TranslucentBackground`` window. (Windows 11's documented
    ``DWMWA_SYSTEMBACKDROP_TYPE`` is drawn in the non-client frame.) State 3,
    not 4 (acrylic): acrylic lags a dragged window on Windows 11.
    """

    PLATFORM = "windows"
    DEFERRED = False

    _WCA_ACCENT_POLICY = 19
    ACCENT_DISABLED = 0
    ACCENT_BLUR = 3

    #: ``(fn, AccentPolicy, WindowCompositionAttribData)``; False = unavailable.
    _api = None

    @classmethod
    def _resolve(cls):
        if cls._api is None:
            cls._api = False
            if sys.platform == "win32" and sys.getwindowsversion().major >= 10:
                from ctypes import wintypes

                fn = getattr(
                    ctypes.windll.user32, "SetWindowCompositionAttribute", None
                )
                if fn is not None:

                    class AccentPolicy(ctypes.Structure):
                        _fields_ = [
                            ("AccentState", ctypes.c_int),
                            ("AccentFlags", ctypes.c_int),
                            ("GradientColor", ctypes.c_uint),
                            ("AnimationId", ctypes.c_int),
                        ]

                    class WindowCompositionAttribData(ctypes.Structure):
                        _fields_ = [
                            ("Attribute", ctypes.c_int),
                            ("Data", ctypes.c_void_p),
                            ("SizeOfData", ctypes.c_size_t),
                        ]

                    fn.argtypes = [
                        wintypes.HWND,
                        ctypes.POINTER(WindowCompositionAttribData),
                    ]
                    fn.restype = wintypes.BOOL
                    cls._api = (fn, AccentPolicy, WindowCompositionAttribData)
        return cls._api or None

    @classmethod
    def available(cls) -> bool:
        return cls._resolve() is not None

    @classmethod
    def apply(cls, widget, on: bool) -> bool:
        fn, policy_t, data_t = cls._resolve()
        policy = policy_t(cls.ACCENT_BLUR if on else cls.ACCENT_DISABLED, 0, 0, 0)
        data = data_t(
            cls._WCA_ACCENT_POLICY,
            ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p),
            ctypes.sizeof(policy),
        )
        return bool(fn(int(widget.winId()), ctypes.byref(data))) and on


class _KWinBlur:
    """KDE Plasma on X11: an empty ``_KDE_NET_WM_BLUR_BEHIND_REGION`` (the
    whole window) on the client window, as ``KWindowEffects`` sets it.

    Available while KWin advertises the effect -- the atom present on the root
    window, which it is only while the blur effect is loaded. Deferred one
    event-loop turn: ``ptk.X11`` talks over its own connection, and Qt may not
    have flushed the window's creation on Qt's yet (the property would land on
    a window the server does not know, and the error is absorbed).
    """

    PLATFORM = "xcb"
    DEFERRED = True

    ATOM = "_KDE_NET_WM_BLUR_BEHIND_REGION"

    @classmethod
    def available(cls) -> bool:
        import pythontk as ptk

        return bool(ptk.X11.has_property(cls.ATOM))

    @classmethod
    def apply(cls, widget, on: bool) -> bool:
        import pythontk as ptk

        window = int(widget.winId())
        if on:
            return bool(ptk.X11.set_cardinal_property(window, cls.ATOM, []))
        ptk.X11.delete_property(window, cls.ATOM)
        return False


class _CocoaBlur:
    """macOS: an ``NSVisualEffectView`` (behind-window blending, always
    active) inserted in the window's frame view, BELOW the content view.

    Not inside the content view: that view is Qt's own (``QNSView``,
    layer-backed), and a subview always draws over its parent's layer -- the
    effect would cover the window's widgets. Sized to the window and
    autoresized with it; tagged by identifier so a second apply finds it.
    Messages go through ``objc_msgSend`` cast to each method's exact
    signature (required on arm64; nothing here returns a struct, which x86_64
    would route through ``objc_msgSend_stret``).
    """

    PLATFORM = "cocoa"
    DEFERRED = False

    IDENTIFIER = b"uitk_blur_behind"
    _BEHIND_WINDOW = 0  # NSVisualEffectBlendingModeBehindWindow
    _ACTIVE = 1  # NSVisualEffectStateActive: not flat while the window is inactive
    _MATERIAL = 21  # NSVisualEffectMaterialUnderWindowBackground (follows appearance)
    _WIDTH_HEIGHT_SIZABLE = 2 | 16
    _BELOW = -1  # NSWindowBelow

    class _Rect(ctypes.Structure):
        _fields_ = [(n, ctypes.c_double) for n in ("x", "y", "w", "h")]

    #: libobjc, or False when unavailable (not macOS, or AppKit not loaded).
    _objc = None
    _identifier = None  # a retained NSString, made once
    _signatures = {}  # (restype, argtypes) -> typed objc_msgSend

    @classmethod
    def _resolve(cls):
        if cls._objc is None:
            cls._objc = False
            path = (
                ctypes.util.find_library("objc") if sys.platform == "darwin" else None
            )
            if path:
                objc = ctypes.cdll.LoadLibrary(path)
                objc.objc_getClass.argtypes = [ctypes.c_char_p]
                objc.objc_getClass.restype = ctypes.c_void_p
                objc.sel_registerName.argtypes = [ctypes.c_char_p]
                objc.sel_registerName.restype = ctypes.c_void_p
                if objc.objc_getClass(b"NSVisualEffectView"):  # AppKit is loaded
                    cls._objc = objc
        return cls._objc or None

    @classmethod
    def _msg_send(cls, restype, argtypes: tuple):
        """``objc_msgSend`` cast to ``(id, SEL, *argtypes) -> restype``, made
        once per signature."""
        key = (restype, argtypes)
        fn = cls._signatures.get(key)
        if fn is None:
            fn = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)(
                ("objc_msgSend", cls._objc)
            )
            cls._signatures[key] = fn
        return fn

    @classmethod
    def _send(cls, receiver, selector: bytes, restype=ctypes.c_void_p, *args):
        """``[receiver selector:args...]`` -- *args* are ``(ctype, value)``."""
        fn = cls._msg_send(restype, tuple(t for t, _ in args))
        return fn(receiver, cls._objc.sel_registerName(selector), *(v for _, v in args))

    @classmethod
    def _find(cls, frame_view) -> Optional[int]:
        """Our effect view among *frame_view*'s subviews, or None."""
        subviews = cls._send(frame_view, b"subviews")
        count = cls._send(subviews, b"count", ctypes.c_ulong) if subviews else 0
        for k in range(count):
            view = cls._send(
                subviews, b"objectAtIndex:", ctypes.c_void_p, (ctypes.c_ulong, k)
            )
            ident = cls._send(view, b"identifier")
            if ident and cls._send(
                ident,
                b"isEqualToString:",
                ctypes.c_byte,
                (ctypes.c_void_p, cls._identifier),
            ):
                return view
        return None

    @classmethod
    def available(cls) -> bool:
        return cls._resolve() is not None

    @classmethod
    def apply(cls, widget, on: bool) -> bool:
        objc = cls._resolve()
        V = ctypes.c_void_p
        if cls._identifier is None:
            string = cls._send(
                objc.objc_getClass(b"NSString"),
                b"stringWithUTF8String:",
                V,
                (ctypes.c_char_p, cls.IDENTIFIER),
            )
            cls._identifier = cls._send(string, b"retain")
        window = cls._send(int(widget.winId()), b"window")  # the QNSView's NSWindow
        content = cls._send(window, b"contentView") if window else None
        frame_view = cls._send(content, b"superview") if content else None
        if not frame_view:
            return False
        effect = cls._find(frame_view)
        if not on:
            if effect:
                cls._send(effect, b"removeFromSuperview", None)
            return False
        if effect:
            return True
        rect = cls._Rect(0.0, 0.0, float(widget.width()), float(widget.height()))
        effect = cls._send(
            cls._send(objc.objc_getClass(b"NSVisualEffectView"), b"alloc"),
            b"initWithFrame:",
            V,
            (cls._Rect, rect),
        )
        if not effect:
            return False
        for selector, value in (
            (b"setBlendingMode:", cls._BEHIND_WINDOW),
            (b"setState:", cls._ACTIVE),
            (b"setMaterial:", cls._MATERIAL),
        ):
            cls._send(effect, selector, None, (ctypes.c_long, value))
        cls._send(
            effect,
            b"setAutoresizingMask:",
            None,
            (ctypes.c_ulong, cls._WIDTH_HEIGHT_SIZABLE),
        )
        cls._send(effect, b"setIdentifier:", None, (V, cls._identifier))
        cls._send(
            frame_view,
            b"addSubview:positioned:relativeTo:",
            None,
            (V, effect),
            (ctypes.c_long, cls._BELOW),
            (V, content),
        )
        cls._send(effect, b"release", None)  # the frame view holds it now
        return True


class _BlurKeeper(QtCore.QObject):
    """Re-applies a window's blur whenever it shows or its native window is
    replaced -- the blur lives on the native window, which ``setWindowFlags``
    and a re-parent destroy and recreate. A child of the window, so it dies
    with it and :meth:`_WindowBlur.set` finds it by name. ``on`` is True or a
    ``(window) -> bool`` resolver, read at each show."""

    NAME = "uitk_blur_keeper"

    def __init__(self, widget, on):
        super().__init__(widget)
        self.setObjectName(self.NAME)
        self.on = on
        widget.installEventFilter(self)

    def wants(self, widget) -> bool:
        return bool(self.on(widget) if callable(self.on) else self.on)

    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.Show, QtCore.QEvent.WinIdChange):
            _WindowBlur.apply(obj, self.wants(obj))
        return False


class _WindowBlur:
    """The backend for this window system, and the per-window bookkeeping
    behind :meth:`Bootstrap.set_blur` / :meth:`Bootstrap.blurs`."""

    BACKENDS = (_DwmBlur, _KWinBlur, _CocoaBlur)

    #: The backend class for this process's Qt platform, resolved once on
    #: first use with an application (the platform never changes after it
    #: starts); False = none.
    _backend = None

    @classmethod
    def backend(cls):
        if cls._backend is None:
            if QtGui.QGuiApplication.instance() is None:
                return None  # no platform yet: decide once there is one
            platform = QtGui.QGuiApplication.platformName()
            cls._backend = next(
                (b for b in cls.BACKENDS if b.PLATFORM == platform), False
            )
        return cls._backend or None

    @classmethod
    def available(cls) -> bool:
        backend = cls.backend()
        if backend is None:
            return False
        try:
            return bool(backend.available())
        except Exception:  # noqa: BLE001 -- a missing native library: no blur
            return False

    @classmethod
    def apply(cls, widget, on: bool) -> bool:
        """Blur *widget*'s native window, if it has one yet.

        Never creates the native window (``winId()`` would, freezing the
        attributes and flags it is created with): an uncreated window gets
        its blur from :class:`_BlurKeeper` when it shows. An opaque window is
        never blurred (its pixels would cover the blur anyway).
        """
        backend = cls.backend()
        if backend is None or not widget.isWindow():
            return False
        if not widget.testAttribute(QtCore.Qt.WA_WState_Created):
            return False
        on = on and widget.testAttribute(QtCore.Qt.WA_TranslucentBackground)
        if backend.DEFERRED:
            QtCore.QTimer.singleShot(0, widget, lambda: cls._run(backend, widget, on))
            return on
        return cls._run(backend, widget, on)

    @staticmethod
    def _run(backend, widget, on: bool) -> bool:
        try:
            if not widget.isWindow():  # re-hosted as a child meanwhile
                return False
            return backend.apply(widget, on)
        except Exception:  # noqa: BLE001 -- a native call failed: no blur, no crash
            return False

    @classmethod
    def set(
        cls,
        widget: QtWidgets.QWidget,
        on: Union[bool, Callable[[QtWidgets.QWidget], bool]] = True,
    ) -> bool:
        """See :meth:`Bootstrap.set_blur`."""
        keeper = widget.findChild(
            _BlurKeeper, _BlurKeeper.NAME, QtCore.Qt.FindDirectChildrenOnly
        )
        if not (callable(on) or on) or not cls.available():
            if keeper is not None:  # only a window this set blurring is reset
                widget.removeEventFilter(keeper)
                keeper.setParent(None)
                keeper.deleteLater()
                cls.apply(widget, False)
            return False
        if keeper is None:
            keeper = _BlurKeeper(widget, on)
        else:
            keeper.on = on
        wants = keeper.wants(widget)
        cls.apply(widget, wants)
        return wants
