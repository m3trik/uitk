# !/usr/bin/python
# coding=utf-8
"""Tests for uitk._window_blur (blur behind translucent windows, per window
system) and its public face, ``Bootstrap.set_blur`` / ``Bootstrap.blurs``.

The per-window contract runs against a recording backend, so it holds on every
platform and never touches a real window manager from the offscreen suite; each
native backend's calls are checked against a stand-in for its API.
"""

import ctypes
import unittest
from unittest.mock import patch

from conftest import BaseTestCase, setup_qt_application

setup_qt_application()

from qtpy import QtCore, QtWidgets  # noqa: E402

from uitk._bootstrap import Bootstrap  # noqa: E402
from uitk._window_blur import (  # noqa: E402
    _CocoaBlur,
    _DwmBlur,
    _KWinBlur,
    _WindowBlur,
)


class _RecordingBackend:
    """A backend that records each apply's ``on`` and is always available."""

    PLATFORM = "test"
    DEFERRED = False
    applied = []

    @classmethod
    def available(cls):
        return True

    @classmethod
    def apply(cls, widget, on):
        cls.applied.append(on)
        return on


class _Case(BaseTestCase):
    def _window(self, translucent=True):
        window = QtWidgets.QWidget(
            None, QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint
        )
        window.setAttribute(QtCore.Qt.WA_TranslucentBackground, translucent)
        self.addCleanup(window.deleteLater)
        return window


class TestSetBlur(_Case):
    """``Bootstrap.set_blur``: declarative, survives native-window recreation."""

    def setUp(self):
        super().setUp()
        self.states = _RecordingBackend.applied = []
        patcher = patch.object(_WindowBlur, "_backend", _RecordingBackend)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_window_blurs_from_its_first_show_and_survives_recreation(self):
        window = self._window()
        self.assertTrue(Bootstrap.set_blur(window))
        self.assertEqual(self.states, [], "must not create the native window early")
        window.show()
        self.assertEqual(self.states[-1], True)
        # setWindowFlags destroys the native window the blur lived on; the
        # next show re-applies it.
        n = len(self.states)
        window.setWindowFlags(window.windowFlags() | QtCore.Qt.Tool)
        window.show()
        self.assertGreater(len(self.states), n)
        self.assertEqual(self.states[-1], True)

    def test_setting_it_twice_keeps_one_keeper(self):
        window = self._window()
        Bootstrap.set_blur(window)
        Bootstrap.set_blur(window)
        keepers = [c for c in window.children() if c.objectName() == "uitk_blur_keeper"]
        self.assertEqual(len(keepers), 1)

    def test_turning_it_off_clears_it_and_stops_following(self):
        window = self._window()
        Bootstrap.set_blur(window)
        window.show()
        self.assertFalse(Bootstrap.set_blur(window, False))
        self.assertEqual(self.states[-1], False)
        n = len(self.states)
        window.hide()
        window.show()
        self.assertEqual(len(self.states), n)

    def test_an_opaque_window_is_not_blurred(self):
        window = self._window(translucent=False)
        Bootstrap.set_blur(window)
        window.show()
        self.assertEqual(self.states[-1], False)

    def test_a_child_widget_is_never_touched(self):
        parent = self._window()
        child = QtWidgets.QWidget(parent)
        Bootstrap.set_blur(child)
        parent.show()
        self.assertEqual(self.states, [])

    def test_a_resolver_is_read_at_every_show(self):
        window = self._window()
        wanted = {"on": True}
        Bootstrap.set_blur(window, lambda w: wanted["on"])
        window.show()
        self.assertEqual(self.states[-1], True)
        window.hide()
        wanted["on"] = False
        window.show()
        self.assertEqual(self.states[-1], False)

    def test_a_window_never_blurred_is_not_reset(self):
        """Off on a window this never blurred makes no native call -- the
        engine passes off for every styled window whose theme has it off."""
        window = self._window()
        window.show()
        self.assertFalse(Bootstrap.set_blur(window, False))
        self.assertEqual(self.states, [])

    def test_a_deferred_backend_applies_on_the_next_event_loop_turn(self):
        """KWin's: its property must not reach the server before Qt has
        flushed the window's creation on Qt's own connection."""
        window = self._window()
        window.show()
        with patch.object(_RecordingBackend, "DEFERRED", True):
            Bootstrap.set_blur(window)
            self.assertEqual(self.states, [])
            QtWidgets.QApplication.processEvents()
        self.assertEqual(self.states, [True])

    def test_a_failing_native_call_is_no_blur_not_a_crash(self):
        window = self._window()
        window.show()
        with patch.object(_RecordingBackend, "apply", side_effect=OSError("gone")):
            Bootstrap.set_blur(window)  # does not raise

    def test_it_is_a_no_op_where_the_platform_cannot_blur(self):
        with patch.object(_WindowBlur, "_backend", False):
            window = self._window()
            self.assertFalse(Bootstrap.blurs())
            self.assertFalse(Bootstrap.set_blur(window))
            window.show()
        self.assertEqual(self.states, [])
        self.assertEqual(window.children(), [])


class TestBackendChoice(BaseTestCase):
    def test_each_window_system_gets_its_backend(self):
        for platform, expected in (
            ("windows", _DwmBlur),
            ("xcb", _KWinBlur),
            ("cocoa", _CocoaBlur),
            ("wayland", None),
            ("offscreen", None),
        ):
            name = patch(
                "uitk._window_blur.QtGui.QGuiApplication.platformName",
                return_value=platform,
            )
            with self.subTest(platform=platform), name:
                with patch.object(_WindowBlur, "_backend", None):
                    self.assertIs(_WindowBlur.backend(), expected)


class TestBackendCache(BaseTestCase):
    def test_no_choice_is_cached_before_an_application_exists(self):
        """Asked before the QApplication (an import-time probe), the platform
        name is empty: that must not fix "no backend" for the process."""
        with patch.object(_WindowBlur, "_backend", None):
            with patch(
                "uitk._window_blur.QtGui.QGuiApplication.instance", return_value=None
            ):
                self.assertIsNone(_WindowBlur.backend())
            self.assertIsNone(_WindowBlur._backend)


class TestDwmBlur(_Case):
    """The accent struct ``SetWindowCompositionAttribute`` receives."""

    class _Policy(ctypes.Structure):
        _fields_ = [
            ("AccentState", ctypes.c_int),
            ("AccentFlags", ctypes.c_int),
            ("GradientColor", ctypes.c_uint),
            ("AnimationId", ctypes.c_int),
        ]

    class _Data(ctypes.Structure):
        _fields_ = [
            ("Attribute", ctypes.c_int),
            ("Data", ctypes.c_void_p),
            ("SizeOfData", ctypes.c_size_t),
        ]

    def test_on_and_off_send_the_blur_and_disabled_accents(self):
        sent = []

        def fn(hwnd, data_ref):
            data = data_ref._obj
            policy = ctypes.cast(data.Data, ctypes.POINTER(self._Policy)).contents
            sent.append((hwnd, data.Attribute, policy.AccentState))
            return 1

        window = self._window()
        window.show()
        with patch.object(_DwmBlur, "_api", (fn, self._Policy, self._Data)):
            self.assertTrue(_DwmBlur.apply(window, True))
            self.assertFalse(_DwmBlur.apply(window, False))
        hwnd = int(window.winId())
        self.assertEqual(
            sent,
            [
                (hwnd, 19, _DwmBlur.ACCENT_BLUR),
                (hwnd, 19, _DwmBlur.ACCENT_DISABLED),
            ],
        )


class TestKWinBlur(_Case):
    """KWin's whole-window blur region, through ``ptk.X11``."""

    def test_on_sets_an_empty_region_and_off_deletes_it(self):
        window = self._window()
        window.show()
        wid = int(window.winId())
        put = patch("pythontk.X11.set_cardinal_property", return_value=True)
        delete = patch("pythontk.X11.delete_property", return_value=True)
        with put as put, delete as delete:
            self.assertTrue(_KWinBlur.apply(window, True))
            self.assertFalse(_KWinBlur.apply(window, False))
        put.assert_called_once_with(wid, _KWinBlur.ATOM, [])
        delete.assert_called_once_with(wid, _KWinBlur.ATOM)

    def test_available_only_while_kwin_advertises_the_effect(self):
        for answer, expected in ((True, True), (False, False), (None, False)):
            probe = patch("pythontk.X11.has_property", return_value=answer)
            with self.subTest(answer=answer), probe as has:
                self.assertIs(_KWinBlur.available(), expected)
            has.assert_called_once_with(_KWinBlur.ATOM)


class _FakeAppKit:
    """Just enough AppKit for ``_CocoaBlur``: views with subviews, a window
    whose content view sits in a frame view, NSString, NSVisualEffectView.

    Messages arrive through the backend's typed-``objc_msgSend`` factory, so
    this also checks each call's signature against the method's."""

    SIGNATURES = {
        b"window": (ctypes.c_void_p, ()),
        b"contentView": (ctypes.c_void_p, ()),
        b"superview": (ctypes.c_void_p, ()),
        b"subviews": (ctypes.c_void_p, ()),
        b"count": (ctypes.c_ulong, ()),
        b"objectAtIndex:": (ctypes.c_void_p, (ctypes.c_ulong,)),
        b"identifier": (ctypes.c_void_p, ()),
        b"isEqualToString:": (ctypes.c_byte, (ctypes.c_void_p,)),
        b"stringWithUTF8String:": (ctypes.c_void_p, (ctypes.c_char_p,)),
        b"retain": (ctypes.c_void_p, ()),
        b"alloc": (ctypes.c_void_p, ()),
        b"initWithFrame:": (ctypes.c_void_p, (_CocoaBlur._Rect,)),
        b"setBlendingMode:": (None, (ctypes.c_long,)),
        b"setState:": (None, (ctypes.c_long,)),
        b"setMaterial:": (None, (ctypes.c_long,)),
        b"setAutoresizingMask:": (None, (ctypes.c_ulong,)),
        b"setIdentifier:": (None, (ctypes.c_void_p,)),
        b"addSubview:positioned:relativeTo:": (
            None,
            (ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p),
        ),
        b"release": (None, ()),
        b"removeFromSuperview": (None, ()),
    }

    def __init__(self, qnsview):
        self.objects = {}
        self.calls = []
        self._next = 1000
        self.ns_string = self._new("class:NSString")
        self.effect_class = self._new("class:NSVisualEffectView")
        self.frame = self._new("view", subviews=[])
        self.content = self._new("view", subviews=[], superview=self.frame)
        self.frame_obj["subviews"].append(self.content)
        self.window = self._new("window", content=self.content)
        self.objects[qnsview] = {"kind": "view", "window": self.window}

    @property
    def frame_obj(self):
        return self.objects[self.frame]

    def _new(self, kind, **fields):
        self._next += 1
        self.objects[self._next] = {"kind": kind, **fields}
        return self._next

    # libobjc stand-ins
    def objc_getClass(self, name):
        return {b"NSString": self.ns_string, b"NSVisualEffectView": self.effect_class}[
            name
        ]

    def sel_registerName(self, name):
        return name

    def msg_send(self, restype, argtypes):
        def send(receiver, selector, *values):
            expected = self.SIGNATURES[selector]
            assert (restype, argtypes) == expected, (selector, restype, argtypes)
            self.calls.append(selector)
            if selector == b"retain":  # returns its receiver
                return receiver
            return self._dispatch(self.objects.get(receiver), selector, values)

        return send

    def _dispatch(self, obj, sel, values):
        if sel == b"window":
            return obj["window"]
        if sel == b"contentView":
            return obj["content"]
        if sel == b"superview":
            return obj.get("superview")
        if sel == b"subviews":
            return self._new("array", items=list(obj["subviews"]))
        if sel == b"count":
            return len(obj["items"])
        if sel == b"objectAtIndex:":
            return obj["items"][values[0]]
        if sel == b"identifier":
            return obj.get("identifier")
        if sel == b"isEqualToString:":
            return int(obj["text"] == self.objects[values[0]]["text"])
        if sel == b"stringWithUTF8String:":
            return self._new("string", text=values[0])
        if sel == b"release":
            return None
        if sel == b"alloc":
            return self._new("effect", subviews=[])
        if sel == b"initWithFrame:":
            obj["frame"] = (values[0].w, values[0].h)
            return [k for k, v in self.objects.items() if v is obj][0]
        if sel == b"setIdentifier:":
            obj["identifier"] = values[0]
            return None
        if sel.startswith(b"set"):
            obj[sel.decode()] = values[0]
            return None
        if sel == b"addSubview:positioned:relativeTo:":
            view, order, relative = values
            index = obj["subviews"].index(relative) + (0 if order < 0 else 1)
            obj["subviews"].insert(index, view)
            self.objects[view]["superview"] = [
                k for k, v in self.objects.items() if v is obj
            ][0]
            return None
        if sel == b"removeFromSuperview":
            parent = self.objects[obj["superview"]]
            parent["subviews"] = [
                v for v in parent["subviews"] if self.objects[v] is not obj
            ]
            return None
        raise AssertionError(sel)


class TestCocoaBlur(_Case):
    """The effect view's life in the window's frame view, against a fake
    AppKit (no Mac in the loop)."""

    def setUp(self):
        super().setUp()
        self.window = self._window()
        self.window.resize(200, 120)
        self.window.show()
        self.appkit = _FakeAppKit(int(self.window.winId()))
        for name, value in (
            ("_objc", self.appkit),
            ("_identifier", None),
            ("_msg_send", self.appkit.msg_send),
        ):
            patcher = patch.object(_CocoaBlur, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _subviews(self):
        return self.appkit.frame_obj["subviews"]

    def test_on_puts_one_effect_view_below_the_content_view(self):
        self.assertTrue(_CocoaBlur.apply(self.window, True))
        effect, content = self._subviews()
        self.assertEqual(content, self.appkit.content)
        fx = self.appkit.objects[effect]
        self.assertEqual(fx["frame"], (200.0, 120.0))
        self.assertEqual(fx["setBlendingMode:"], 0)  # behind the window
        self.assertEqual(fx["setState:"], 1)  # active even when unfocused
        self.assertEqual(fx["setAutoresizingMask:"], 18)
        self.assertIn(b"release", self.appkit.calls)  # the frame view owns it
        # Again (each show re-applies): still one.
        self.assertTrue(_CocoaBlur.apply(self.window, True))
        self.assertEqual(len(self._subviews()), 2)

    def test_off_removes_it_and_leaves_the_content_view(self):
        _CocoaBlur.apply(self.window, True)
        self.assertFalse(_CocoaBlur.apply(self.window, False))
        self.assertEqual(self._subviews(), [self.appkit.content])


if __name__ == "__main__":
    unittest.main()
