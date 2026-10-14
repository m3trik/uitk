# !/usr/bin/python
# coding=utf-8
"""Tests for uitk._window_shadow (the drop shadow under a frameless window)
and its public face, ``Bootstrap.set_shadow`` / ``Bootstrap.shadows``.

The per-window contract runs against a recording stacking backend, so it holds
on every platform and never restacks a real desktop from the offscreen suite.
The Windows backend's call is checked against a stand-in for ``SetWindowPos``.
"""

import unittest
from unittest.mock import patch

from conftest import BaseTestCase, setup_qt_application

setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402

from uitk._bootstrap import Bootstrap  # noqa: E402
from uitk._window_shadow import (  # noqa: E402
    _RaiseStack,
    _ShadowKeeper,
    _ShadowProfile,
    _ShadowWindow,
    _Win32Stack,
    _WindowShadow,
)

SPEC = (QtGui.QColor(0, 0, 0, 200), 18, 2)


def _settle():
    for _ in range(3):
        QtWidgets.QApplication.processEvents()


class _RecordingStack:
    """A stacking backend that records each restack and is always available."""

    PLATFORMS = ("test",)
    calls = []

    @classmethod
    def available(cls):
        return True

    @classmethod
    def restack(cls, shadow, target):
        cls.calls.append((shadow, target))


class _Case(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.restacks = _RecordingStack.calls = []
        patcher = patch.object(_WindowShadow, "_backend", _RecordingStack)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _window(
        self, flags=QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint, parent=None
    ):
        window = QtWidgets.QWidget(parent, flags)
        window.setGeometry(300, 200, 240, 140)
        self.addCleanup(window.deleteLater)
        return window

    @staticmethod
    def _shadow(window):
        keeper = window.findChild(
            _ShadowKeeper, _ShadowKeeper.NAME, QtCore.Qt.FindDirectChildrenOnly
        )
        return keeper.window if keeper is not None else None

    def _shown(self, window, spec=SPEC):
        Bootstrap.set_shadow(window, spec)
        window.show()
        _settle()
        return self._shadow(window)


class TestSetShadow(_Case):
    """``Bootstrap.set_shadow``: declarative; follows its window everywhere."""

    def test_it_waits_for_the_first_show_then_covers_the_window_plus_its_reach(self):
        window = self._window()
        self.assertTrue(Bootstrap.set_shadow(window, SPEC))
        self.assertIsNone(self._shadow(window), "nothing is made before a show")
        window.show()
        _settle()
        shadow = self._shadow(window)
        self.assertTrue(shadow.isVisible())
        margins = _ShadowWindow.margins(SPEC[1])
        self.assertEqual(shadow.geometry(), window.geometry().marginsAdded(margins))
        self.assertGreater(margins.bottom(), margins.top(), "the shadow drops")

    def test_it_follows_moves_resizes_and_visibility(self):
        window = self._window()
        shadow = self._shown(window)
        margins = _ShadowWindow.margins(SPEC[1])
        window.move(420, 260)
        window.resize(300, 90)
        self.assertEqual(shadow.geometry(), window.geometry().marginsAdded(margins))
        window.hide()
        self.assertFalse(shadow.isVisible())
        window.show()
        _settle()
        self.assertTrue(shadow.isVisible())

    def test_it_hides_when_the_native_window_hides_without_a_hide_event(self):
        """A shadow left behind is a dark rectangle over the desktop, so the
        native window's visibility is followed, not just ``hideEvent``."""
        window = self._window()
        shadow = self._shown(window)
        window.windowHandle().visibleChanged.emit(False)
        self.assertFalse(shadow.isVisible())

    def test_it_is_stacked_after_the_window_maps_and_again_when_it_rises(self):
        window = self._window()
        shadow = self._shown(window)
        self.assertTrue(self.restacks)
        self.assertEqual(self.restacks[-1], (shadow, window))
        n = len(self.restacks)
        window.raise_()
        self.assertEqual(len(self.restacks), n + 1)
        QtWidgets.QApplication.sendEvent(
            window, QtCore.QEvent(QtCore.QEvent.WindowActivate)
        )
        self.assertEqual(len(self.restacks), n + 2)

    def test_its_opacity_follows_the_window(self):
        """The marking menu dims background windows with setWindowOpacity."""
        window = self._window()
        shadow = self._shown(window)
        window.setWindowOpacity(0.15)
        self.assertAlmostEqual(shadow.opacity(), 0.15, places=2)
        window.setWindowOpacity(1.0)
        self.assertAlmostEqual(shadow.opacity(), 1.0, places=2)

    def test_setting_it_twice_keeps_one_keeper_and_one_shadow(self):
        window = self._window()
        first = self._shown(window)
        Bootstrap.set_shadow(window, SPEC)
        _settle()
        keepers = [c for c in window.children() if c.objectName() == _ShadowKeeper.NAME]
        self.assertEqual(len(keepers), 1)
        self.assertIs(self._shadow(window), first)

    def test_turning_it_off_drops_the_shadow_and_stops_following(self):
        window = self._window()
        shadow = self._shown(window)
        self.assertFalse(Bootstrap.set_shadow(window, None))
        self.assertFalse(shadow.isVisible())
        _settle()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertEqual(
            [c for c in window.children() if c.objectName() == _ShadowKeeper.NAME], []
        )

    def test_a_resolver_is_read_at_every_show(self):
        window = self._window()
        wanted = {"spec": SPEC}
        shadow = self._shown(window, lambda w: wanted["spec"])
        self.assertTrue(shadow.isVisible())
        window.hide()
        wanted["spec"] = None
        window.show()
        _settle()
        self.assertFalse(shadow.isVisible())

    def test_a_failing_resolver_is_no_shadow_not_a_crash(self):
        def boom(_w):
            raise RuntimeError("theme gone")

        window = self._window()
        self.assertIsNone(self._shown(window, boom))

    def test_a_failing_native_call_is_not_a_crash(self):
        window = self._window()
        with patch.object(_RecordingStack, "restack", side_effect=OSError("gone")):
            self.assertTrue(self._shown(window).isVisible())

    def test_windows_without_an_edge_to_shadow_cast_none(self):
        """Framed windows (the window manager shadows them), child widgets, and
        windows that are maximized or cover their screen."""
        framed = self._window(QtCore.Qt.Tool)
        self.assertFalse(Bootstrap.set_shadow(framed, SPEC))
        host = self._window(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        child = QtWidgets.QWidget(host)
        self.assertFalse(Bootstrap.set_shadow(child, SPEC))
        big = self._window(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        big.setGeometry(big.screen().geometry())
        self.assertFalse(Bootstrap.set_shadow(big, SPEC))
        for window in (framed, host, big):
            window.show()
        _settle()
        for window in (framed, big):
            shadow = self._shadow(window)
            self.assertTrue(shadow is None or not shadow.isVisible())

    def test_a_clear_or_zero_size_spec_casts_none(self):
        window = self._window()
        self.assertFalse(
            Bootstrap.set_shadow(window, (QtGui.QColor(0, 0, 0, 0), 18, 0))
        )
        self.assertFalse(Bootstrap.set_shadow(window, ("black", 0, 0)))
        self.assertTrue(Bootstrap.set_shadow(window, ("#80000000", 12, 0)))

    def test_it_is_no_widget(self):
        """A QWindow: invisible to the widget walks that register, style,
        close or pick windows (shortcut owners, the app-hub quit check)."""
        window = self._window()
        shadow = self._shown(window)
        self.assertNotIsInstance(shadow, QtWidgets.QWidget)
        self.assertNotIn(
            _ShadowWindow.NAME,
            [w.objectName() for w in QtWidgets.QApplication.topLevelWidgets()],
        )

    def test_it_shares_the_windows_owner_never_the_window(self):
        """Owned by the window's owner, so raising the owner keeps the pair
        together; never by the window itself, which would put it on top."""
        owner = self._window(QtCore.Qt.Window)
        owner.show()
        window = self._window(parent=owner)
        shadow = self._shown(window)
        self.assertIs(shadow.transientParent(), window.windowHandle().transientParent())
        self.assertIsNot(shadow.transientParent(), window.windowHandle())

    def test_a_topmost_window_gets_a_topmost_shadow(self):
        on_top = self._window(
            QtCore.Qt.Tool
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
        )
        plain = self._window()
        self.assertTrue(self._shown(on_top).flags() & QtCore.Qt.WindowStaysOnTopHint)
        self.assertFalse(self._shown(plain).flags() & QtCore.Qt.WindowStaysOnTopHint)
        self.assertTrue(
            self._shadow(on_top).flags() & QtCore.Qt.WindowTransparentForInput
        )

    def test_a_popup_drops_its_native_shadow_only_before_it_exists(self):
        """Setting the hint on a created window would recreate it."""
        fresh = self._window(QtCore.Qt.Popup)
        Bootstrap.set_shadow(fresh, SPEC)
        self.assertTrue(fresh.windowFlags() & QtCore.Qt.NoDropShadowWindowHint)
        live = self._window(QtCore.Qt.Popup)
        live.winId()
        Bootstrap.set_shadow(live, SPEC)
        self.assertFalse(live.windowFlags() & QtCore.Qt.NoDropShadowWindowHint)

    def test_the_shadow_dies_with_its_window(self):
        from qtpy import shiboken

        window = QtWidgets.QWidget(None, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        shadow = self._shown(window)
        window.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertFalse(shiboken.isValid(shadow))

    def test_it_is_a_no_op_where_the_platform_cannot_shadow(self):
        with patch.object(_WindowShadow, "_backend", False):
            window = self._window()
            self.assertFalse(Bootstrap.shadows())
            self.assertFalse(Bootstrap.set_shadow(window, SPEC))
            window.show()
            _settle()
        self.assertEqual(window.children(), [])


class _FocusOutRecorder(QtCore.QObject):
    def __init__(self, sink, parent=None):
        super().__init__(parent)
        self.sink = sink

    def eventFilter(self, obj, event):  # noqa: N802 -- Qt override
        if event.type() == QtCore.QEvent.FocusOut:
            self.sink.append(event.reason())
        return False


class TestShadowFocus(BaseTestCase):
    """The shadow never holds the focus, on the platform's own stacking."""

    def test_the_shadow_never_keeps_the_focus_its_window_had(self):
        """A platform that activates every window it shows (the offscreen one
        ignores ``WindowDoesNotAcceptFocus``) handed the focus to the shadow,
        so a cell editor open in the shadowed panel closed under the user."""
        window = QtWidgets.QWidget(None, QtCore.Qt.FramelessWindowHint)
        window.setGeometry(300, 200, 240, 140)
        self.addCleanup(window.deleteLater)
        edit = QtWidgets.QLineEdit(window)
        lost = []
        edit.installEventFilter(_FocusOutRecorder(lost, parent=edit))
        Bootstrap.set_shadow(window, SPEC)
        window.show()  # the shadow maps after the window, from its show event
        window.activateWindow()
        edit.setFocus()
        _settle()
        focus = QtGui.QGuiApplication.focusWindow()
        self.assertNotEqual(focus.objectName() if focus else "", _ShadowWindow.NAME)
        self.assertIs(QtWidgets.QApplication.focusWidget(), edit)
        self.assertEqual(lost, [], "the editor never lost the focus")

    def test_only_the_offscreen_platform_retypes_the_shadow(self):
        """Real window systems keep the stacking ``Tool`` type (Win32 restacks
        it beneath its window); only offscreen gets ``ToolTip``."""
        mask = int(QtCore.Qt.WindowType_Mask)
        for platform in ("windows", "xcb", "cocoa"):
            self.assertEqual(_ShadowWindow.flags_for(platform), _ShadowWindow.FLAGS)
        offscreen = int(_ShadowWindow.flags_for("offscreen"))
        self.assertEqual(offscreen & mask, int(QtCore.Qt.ToolTip))
        self.assertEqual(offscreen & ~mask, int(_ShadowWindow.FLAGS) & ~mask)


class TestShadowPaint(BaseTestCase):
    """What the shadow window paints: only outside its window, fading out."""

    @staticmethod
    def _render(size, spec=SPEC):
        shadow = _ShadowWindow(QtCore.QObject())
        shadow.spec, shadow._target = _WindowShadow.normalize(spec), size
        m = _ShadowWindow.margins(spec[1])
        img = QtGui.QImage(
            size.width() + m.left() + m.right(),
            size.height() + m.top() + m.bottom(),
            QtGui.QImage.Format_ARGB32_Premultiplied,
        )
        img.fill(0)
        painter = QtGui.QPainter(img)
        shadow.paint(painter, img.size())
        painter.end()

        def alpha(x, y):
            return QtGui.QColor.fromRgba(img.pixel(x, y)).alpha()

        return alpha, m, img

    def test_nothing_is_painted_beneath_the_window(self):
        """A translucent, blurred window must not be darkened from below."""
        alpha, m, _img = self._render(QtCore.QSize(200, 100))
        for x, y in ((100, 50), (3, 3), (196, 96)):
            self.assertEqual(alpha(m.left() + x, m.top() + y), 0, (x, y))

    def test_it_is_strongest_at_the_edge_fades_out_and_drops(self):
        alpha, m, img = self._render(QtCore.QSize(200, 100))
        cy = m.top() + 50
        left, right = alpha(m.left() - 1, cy), alpha(m.left() + 200, cy)
        self.assertGreater(left, 40)
        self.assertEqual(left, right, "symmetric left/right")
        self.assertLess(alpha(1, cy), left // 4, "fades toward its reach")
        self.assertEqual(alpha(0, 0), 0)
        top, bottom = (
            alpha(m.left() + 100, m.top() - 1),
            alpha(m.left() + 100, m.top() + 100),
        )
        self.assertGreater(bottom, top, "light from above: more shadow below")
        self.assertEqual(img.width(), 200 + 2 * _ShadowProfile.reach(SPEC[1]))

    def test_a_window_smaller_than_the_reach_still_gets_a_whole_shadow(self):
        alpha, m, _img = self._render(QtCore.QSize(10, 6))
        self.assertGreater(alpha(m.left() - 1, m.top() + 3), 0)
        self.assertEqual(alpha(m.left() + 5, m.top() + 3), 0)


class TestShadowProfile(unittest.TestCase):
    def test_a_long_step_is_half_at_the_edge_and_zero_at_its_reach(self):
        values = _ShadowProfile.values(100, 18)
        reach = _ShadowProfile.reach(18)
        self.assertEqual(len(values), 100 + 2 * reach)
        self.assertAlmostEqual(values[len(values) // 2], 1.0)
        self.assertAlmostEqual(values[0], 0.0, places=3)
        self.assertAlmostEqual((values[reach - 1] + values[reach]) / 2, 0.5, places=2)
        self.assertEqual(values, tuple(reversed(values)))

    def test_any_length_paints_the_exact_profile_from_shared_edges(self):
        """A long window paints from one cached edge per size, its edges as
        gradients of their own: exact at every length (a single gradient
        across a long window stepped by up to 5/255 through Qt's color
        table), and no more bands for a longer window."""
        color = QtGui.QColor(0, 0, 0, 200)
        reach = _ShadowProfile.reach(18)
        for length in (10, 2 * reach + 1, 2 * reach + 2, 300, 2000):
            n = length + 2 * reach
            img = QtGui.QImage(n, 1, QtGui.QImage.Format_ARGB32_Premultiplied)
            img.fill(0)
            painter = QtGui.QPainter(img)
            _ShadowProfile.fill(painter, img.size(), length, 18, color, horizontal=True)
            painter.end()
            painted = [QtGui.QColor.fromRgba(img.pixel(x, 0)).alpha() for x in range(n)]
            exact = [round(200 * v) for v in _ShadowProfile.values(length, 18)]
            worst = max(abs(a - b) for a, b in zip(exact, painted))
            self.assertLessEqual(worst, 1, length)
        self.assertEqual(
            len(_ShadowProfile.bands(300, 18)), len(_ShadowProfile.bands(4000, 18))
        )


class TestBackendChoice(BaseTestCase):
    def test_each_window_system_gets_its_backend(self):
        for platform, expected in (
            ("windows", _Win32Stack),
            ("offscreen", _RaiseStack),
            ("cocoa", None),
            ("xcb", None),
            ("wayland", None),
        ):
            with (
                patch.object(_WindowShadow, "_backend", None),
                patch.object(
                    QtGui.QGuiApplication, "platformName", return_value=platform
                ),
            ):
                self.assertIs(_WindowShadow.backend(), expected, platform)


class TestWin32Stack(BaseTestCase):
    def test_the_shadow_goes_directly_beneath_its_window_without_activation(self):
        calls = []

        class _Native:
            def __init__(self, hwnd):
                self.hwnd = hwnd

            def winId(self):  # noqa: N802 -- Qt name
                return self.hwnd

        with patch.object(_Win32Stack, "_fn", lambda *a: calls.append(a) or 1):
            _Win32Stack.restack(_Native(11), _Native(22))
        ((hwnd, after, _x, _y, _cx, _cy, flags),) = calls
        self.assertEqual((hwnd, after), (11, 22))
        for flag in (0x0001, 0x0002, 0x0010, 0x0200):  # no size/move/activate/owner
            self.assertTrue(flags & flag, hex(flag))


if __name__ == "__main__":
    unittest.main()
