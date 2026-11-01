# !/usr/bin/python
# coding=utf-8
"""``MarkingMenu(host=...)``: the menu asks its host, never a subclass, what an application
answers differently from a plain Qt app (``uitk.MarkingMenuHost``).

A fake host records each question the menu asks and answers it, so these tests pin the
seam itself: the main window the menu parents to, the shortcut owner it declares, its UI
handler, the host's half of the activation binding (at construction and on every rebind),
the mouse it reads, the windows it hands over for adoption, the key events it shows first,
the once-per-menu attach and the preload gate. :class:`PureMarkingMenuHost` -- the default
-- answers as a menu with no host always has.
"""

import unittest

from qtpy import QtCore, QtGui, QtWidgets

from conftest import QtBaseTestCase
from uitk.handlers.ui_handler import UiHandler
from uitk.managers.shortcut_manager import ShortcutManager
from uitk.widgets.marking_menu._marking_menu import MarkingMenu
from uitk.widgets.marking_menu.marking_menu_host import (
    MarkingMenuHost,
    PureMarkingMenuHost,
)


class _RecordingUiHandler(UiHandler):
    """A host's UI handler: the menu registers it as its ``"ui"`` handler."""


class _FakeHost(PureMarkingMenuHost):
    """Answers every question, and records each one asked."""

    preload_only_from_host_loop = True
    shortcut_window_name = "FakeHostMainWindow"
    ui_handler = _RecordingUiHandler

    def __init__(self, window):
        self.window = window
        self.calls = []
        self.buttons = QtCore.Qt.RightButton

    def start(self):
        self.calls.append(("start",))

    def defer(self, fn):
        self.calls.append(("defer",))
        self.deferred = fn
        return None

    def main_window(self):
        self.calls.append(("main_window",))
        return self.window

    def mouse_buttons(self):
        return self.buttons

    def bind_activation_key(self, menu, key):
        self.calls.append(("bind", menu, key))

    def adopt_window(self, widget):
        self.calls.append(("adopt", widget))

    def key_event(self, menu, event):
        self.calls.append(("key", event.type(), event.key()))

    def attach(self, menu):
        self.calls.append(("attach", menu))

    def asked(self, name):
        return [call for call in self.calls if call[0] == name]


class _HostCase(QtBaseTestCase):
    BINDINGS = {"Key_F12": "hud#startmenu", "Key_F12|RightButton": "main#startmenu"}

    def setUp(self):
        super().setUp()
        self._mms = []

    def tearDown(self):
        for mm in self._mms:
            try:
                mm.retire()
            except RuntimeError:
                pass
        super().tearDown()

    def _make_mm(self, context_tag, **kwargs):
        mm = MarkingMenu(
            bindings=dict(self.BINDINGS), context_tags={context_tag}, **kwargs
        )
        self.track_widget(mm)
        self._mms.append(mm)
        return mm

    def _host_window(self):
        window = QtWidgets.QMainWindow()
        window.setObjectName("FakeHostMainWindow")
        self.track_widget(window)
        return window


class TestTheProtocol(unittest.TestCase):
    def test_the_pure_host_is_a_marking_menu_host(self):
        self.assertIsInstance(PureMarkingMenuHost(), MarkingMenuHost)

    def test_the_pure_host_defers_by_running_now(self):
        """A plain Qt app has nothing to wait for: the launcher's build runs at once."""
        self.assertEqual(PureMarkingMenuHost().defer(lambda: "built"), "built")

    def test_the_pure_host_reports_qts_mouse(self):
        self.assertEqual(
            PureMarkingMenuHost().mouse_buttons(), QtWidgets.QApplication.mouseButtons()
        )

    def test_the_package_root_publishes_both(self):
        import uitk

        self.assertIs(uitk.MarkingMenuHost, MarkingMenuHost)
        self.assertIs(uitk.PureMarkingMenuHost, PureMarkingMenuHost)


class TestNoHost(_HostCase):
    def test_a_menu_without_a_host_answers_as_plain_qt(self):
        mm = self._make_mm("t_host_none")
        self.assertIsInstance(mm.host, PureMarkingMenuHost)
        self.assertIsNone(
            mm.parent(), "a plain Qt app's menu parents to what it is given"
        )
        self.assertIsInstance(mm.sb.handlers.ui, UiHandler)
        self.assertNotIsInstance(mm.sb.handlers.ui, _RecordingUiHandler)


class TestTheMenuAsksItsHost(_HostCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(ShortcutManager.unregister_host_window, "FakeHostMainWindow")
        self.window = self._host_window()
        self.host = _FakeHost(self.window)
        self.mm = self._make_mm("t_host_fake", host=self.host)

    def test_it_parents_to_the_hosts_main_window(self):
        self.assertEqual(len(self.host.asked("main_window")), 1)
        self.assertIs(self.mm.parent(), self.window)

    def test_an_explicit_parent_wins_over_the_host(self):
        other = self._host_window()
        host = _FakeHost(self.window)
        mm = self._make_mm("t_host_parent", host=host, parent=other)
        self.assertIs(mm.parent(), other)
        self.assertEqual(host.asked("main_window"), [])

    def test_it_declares_the_hosts_shortcut_owner(self):
        self.assertIn("FakeHostMainWindow", ShortcutManager.host_window_names())

    def test_it_registers_the_hosts_ui_handler(self):
        self.assertIsInstance(self.mm.sb.handlers.ui, _RecordingUiHandler)

    def test_the_host_binds_its_half_of_the_activation_key_once_built(self):
        self.assertEqual(self.host.asked("bind"), [("bind", self.mm, "Key_F12")])
        self.assertIsNotNone(
            self.mm._shortcut_instance,
            "the menu's own Qt shortcut is still the binding",
        )

    def test_every_rebind_reaches_the_host(self):
        self.mm.set_activation_key("F11")
        self.assertEqual(self.host.asked("bind")[-1], ("bind", self.mm, "Key_F11"))
        self.assertIn("Key_F11|RightButton", self.mm.bindings)

    def test_a_redundant_rebind_still_resyncs_the_hosts_half(self):
        """An unchanged key moves no Qt chord, but the host's half may have drifted."""
        before = len(self.host.asked("bind"))
        self.mm.set_activation_key("F12")
        self.assertEqual(len(self.host.asked("bind")), before + 1)

    def test_it_reads_the_mouse_from_its_host(self):
        self.assertEqual(self.mm._host_mouse_buttons(), QtCore.Qt.RightButton)
        self.host.buttons = QtCore.Qt.NoButton
        self.assertEqual(self.mm._host_mouse_buttons(), QtCore.Qt.NoButton)

    def test_it_hands_its_overlay_over_once_built_and_on_every_show(self):
        """Construction realizes the overlay off-screen (a show) and ends by adopting
        it: the host sees the overlay, and only the overlay, by then -- and again on
        every later show, since a re-created native window drops what a host set."""
        adopted = [call[1] for call in self.host.asked("adopt")]
        self.assertTrue(adopted, "construction must hand the overlay over")
        self.assertTrue(all(widget is self.mm for widget in adopted), adopted)
        self.assertIs(
            self.host.calls[-2], self.host.asked("adopt")[-1], "adopt, then attach"
        )
        before = len(adopted)
        self.mm.showEvent(QtGui.QShowEvent())
        self.assertEqual(len(self.host.asked("adopt")), before + 1)

    def test_it_hands_over_each_standalone_window_it_shows(self):
        tool = self.mm.sb.add_ui("t_host_tool", widget=QtWidgets.QWidget())
        self.track_widget(tool)
        self.mm._show_window(tool)
        self.assertIs(self.host.asked("adopt")[-1][1], tool)

    def test_the_host_sees_each_key_first(self):
        press = QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier
        )
        release = QtGui.QKeyEvent(
            QtCore.QEvent.KeyRelease, QtCore.Qt.Key_F12, QtCore.Qt.NoModifier
        )
        self.mm.keyPressEvent(press)
        self.mm.keyReleaseEvent(release)
        self.assertEqual(
            self.host.asked("key"),
            [
                ("key", QtCore.QEvent.KeyPress, QtCore.Qt.Key_Z),
                ("key", QtCore.QEvent.KeyRelease, QtCore.Qt.Key_F12),
            ],
        )

    def test_the_host_attaches_once_and_last(self):
        self.assertEqual(self.host.asked("attach"), [("attach", self.mm)])
        self.assertEqual(self.host.calls[-1], ("attach", self.mm))

    def test_the_hosts_loop_gates_the_preload(self):
        """``preload_only_from_host_loop``: a tick with a Python caller beneath it waits."""
        mm = self.mm
        page = mm.sb.add_ui(
            "hud#startmenu", widget=QtWidgets.QWidget(), tags={"startmenu"}
        )
        self.track_widget(page)
        mm.preload_menus()
        for _ in range(5):
            self._drain_qt_events()
        self.assertFalse(page.is_initialized, "a page was built inside a script")
        self.assertIsNotNone(mm._preload_queue, "the warm-up must wait, not end")

    def test_a_retired_menu_binds_nothing_more(self):
        before = len(self.host.asked("bind"))
        self.mm.retire()
        self.mm.set_activation_key("F10")
        self.assertEqual(len(self.host.asked("bind")), before)

    def test_a_failing_host_never_blocks_a_rebind(self):
        def broken(menu, key):
            raise RuntimeError("host keymap gone")

        self.host.bind_activation_key = broken
        self.mm.set_activation_key("F9")  # must not raise
        self.assertIn("Key_F9|RightButton", self.mm.bindings)


if __name__ == "__main__":
    unittest.main()
