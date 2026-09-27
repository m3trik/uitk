# !/usr/bin/python
# coding=utf-8
"""Popup mechanics, pinned by ACTING on the widgets that share them.

``Menu``, ``ExpandableList``, ``MainWindow`` and the option-box value popups
(``RecentValuesPopup`` / ``PinnedValuesPopup``) each carried their own copy of
three popup mechanics: the screen clamp, the promotion of a widget to a
frameless top-level popup window, and the watchers that dismiss a popup when
its host moves, hides, or the user clicks elsewhere. They now share
``uitk.widgets.popup``.

The consumer tests below show the real widget, click it, press Escape, move or
hide its host, and assert what the gesture DID. They were written against the
pre-extraction code and pinned green there, so they are the proof that the
extraction changed no behaviour. The kit's own unit tests follow them.
"""

import unittest
from unittest import mock

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtTest import QTest

from uitk.widgets.menu import Menu
from uitk.widgets.expandableList import ExpandableList
from uitk.widgets.mainWindow import MainWindow
from uitk.widgets.optionBox.options.recent_values import RecentValuesPopup
from uitk.widgets.optionBox.options.pin_values import PinnedValuesPopup


def _process(passes=3):
    for _ in range(passes):
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 20)


def _available():
    return QtWidgets.QApplication.primaryScreen().availableGeometry()


class _BareSwitchboard:
    """Minimal stand-in so MainWindow.__init__ completes without a Switchboard."""

    def convert_to_legal_name(self, name):
        return name

    def get_base_name(self, name):
        return name

    def has_tags(self, *_a, **_k):
        return False

    def get_slots_instance(self, *_a, **_k):
        return None

    def center_widget(self, *_a, **_k):
        return None


class _KeyRecorder(QtWidgets.QPushButton):
    """A focusable widget that records the keys actually delivered to it."""

    def __init__(self, *args):
        super().__init__(*args)
        self.keys = []
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def keyPressEvent(self, event):
        self.keys.append(event.key())
        super().keyPressEvent(event)


def _window_type(widget):
    return widget.windowFlags() & QtCore.Qt.WindowType_Mask


# -----------------------------------------------------------------------------
# Consumer behaviour (pinned before the extraction)
# -----------------------------------------------------------------------------


class _PopupCase(QtBaseTestCase):
    def _menu_on_host(self, **kwargs):
        host = self.track_widget(QtWidgets.QWidget())
        host.resize(300, 200)
        anchor = QtWidgets.QPushButton("anchor", host)
        anchor.move(10, 10)
        anchor.resize(80, 24)
        host.show()
        _process()
        options = dict(
            parent=anchor,
            trigger_button="none",
            position="bottom",
            add_header=False,
            add_footer=False,
            add_apply_button=False,
            hide_on_leave=False,
        )
        options.update(kwargs)
        menu = self.track_widget(Menu(**options))
        menu.add(QtWidgets.QLabel("item one"))
        menu.add(QtWidgets.QLabel("item two"))
        return host, anchor, menu

    def _click_list(self, window, items=("Menu",)):
        """A click_menu list with one populated flyout per root item."""
        lw = ExpandableList(window, fixed_item_height=18)
        self.track_widget(lw)
        lw.apply_preset("click_menu")
        roots = []
        for text in items:
            root_item = lw.add(text)
            root_item.sublist.add([f"{text} A", f"{text} B"])
            roots.append(root_item)
        # A failing assertion mid-session must not leave the app-level dismiss
        # filter installed for later tests.
        self.addCleanup(lw._end_click_chain)
        return lw, roots

    def _host_window(self):
        window = self.track_widget(QtWidgets.QMainWindow())
        window.resize(240, 120)
        return window


class TestScreenClamp(_PopupCase):
    """A popup (or window) shown past the screen edge lands inside it."""

    def test_menu_past_the_bottom_right_lands_inside(self):
        _host, anchor, menu = self._menu_on_host()
        avail = _available()
        menu.show_as_popup(
            anchor_widget=anchor,
            position=QtCore.QPoint(avail.right() + 300, avail.bottom() + 300),
        )
        frame = menu.frameGeometry()
        self.assertEqual(
            frame.topLeft(),
            QtCore.QPoint(
                avail.right() - frame.width(), avail.bottom() - frame.height()
            ),
        )

    def test_menu_past_the_top_left_lands_at_the_corner(self):
        _host, anchor, menu = self._menu_on_host()
        avail = _available()
        menu.show_as_popup(
            anchor_widget=anchor,
            position=QtCore.QPoint(avail.left() - 300, avail.top() - 300),
        )
        self.assertEqual(menu.frameGeometry().topLeft(), avail.topLeft())

    def test_menu_opted_out_of_the_clamp_stays_put(self):
        _host, anchor, menu = self._menu_on_host(ensure_on_screen=False)
        avail = _available()
        target = QtCore.QPoint(avail.right() + 300, avail.bottom() + 300)
        menu.show_as_popup(anchor_widget=anchor, position=target)
        self.assertEqual(menu.pos(), target)

    def test_main_window_shown_off_screen_is_pulled_back(self):
        win = self.track_widget(
            MainWindow(
                name="clamp_probe",
                switchboard_instance=_BareSwitchboard(),
                restore_window_size=False,
                fit_to_content_on_show=False,
            )
        )
        win.setCentralWidget(QtWidgets.QLabel("body"))
        win.resize(220, 140)
        avail = _available()
        win.move(avail.right() + 400, avail.bottom() + 400)
        win.show()
        _process()
        frame = win.frameGeometry()
        self.assertTrue(avail.intersects(frame), f"{frame} still off {avail}")
        self.assertEqual(
            frame.topLeft(),
            QtCore.QPoint(
                avail.right() - frame.width(), avail.bottom() - frame.height()
            ),
        )

    def test_click_flyout_near_the_screen_corner_is_clamped(self):
        window = self._host_window()
        lw, (root_item,) = self._click_list(window)
        avail = _available()
        window.move(avail.right() - 20, avail.bottom() - 20)
        window.show()
        _process()
        QTest.mouseClick(root_item, QtCore.Qt.LeftButton)
        sub = root_item.sublist
        self.assertTrue(sub.isVisible(), "the click must open the flyout")
        frame = sub.frameGeometry()
        self.assertEqual(
            frame.topLeft(),
            QtCore.QPoint(
                avail.right() - frame.width(), avail.bottom() - frame.height()
            ),
        )


class _FakeScreen:
    """A screen stand-in: the clamp reads only its two geometries."""

    def __init__(self, rect):
        self._rect = QtCore.QRect(rect)

    def geometry(self):
        return QtCore.QRect(self._rect)

    def availableGeometry(self):
        return QtCore.QRect(self._rect)


class TestClampPicksTheOverlappedScreen(_PopupCase):
    """Two monitors side by side, the primary on the LEFT.

    A flyout that opens past the right monitor's far edge has its centre on no
    screen at all. The clamp must slide it back onto the monitor it overlaps
    (beside its trigger), never onto the primary one across the desk -- which
    is what ExpandableList's trimmed copy of the clamp did.
    """

    def _screens(self):
        left = _FakeScreen(QtCore.QRect(0, 0, 800, 800))
        right = _FakeScreen(QtCore.QRect(800, 0, 800, 800))
        patches = (
            mock.patch.object(QtWidgets.QApplication, "screenAt", return_value=None),
            mock.patch.object(
                QtWidgets.QApplication, "screens", return_value=[left, right]
            ),
            mock.patch.object(
                QtWidgets.QApplication, "primaryScreen", return_value=left
            ),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return left, right

    def test_click_flyout_off_the_right_monitor_stays_on_it(self):
        window = self._host_window()
        lw, (root_item,) = self._click_list(window)
        window.move(1590, 100)
        window.show()
        _process()
        _left, right = self._screens()
        QTest.mouseClick(root_item, QtCore.Qt.LeftButton)
        frame = root_item.sublist.frameGeometry()
        self.assertEqual(frame.x(), right.availableGeometry().right() - frame.width())

    def test_menu_off_the_right_monitor_stays_on_it(self):
        _host, anchor, menu = self._menu_on_host()
        _left, right = self._screens()
        menu.show_as_popup(anchor_widget=anchor, position=QtCore.QPoint(1590, 100))
        frame = menu.frameGeometry()
        self.assertEqual(frame.x(), right.availableGeometry().right() - frame.width())


class TestPopupWindowPromotion(_PopupCase):
    """The first open turns a plain child widget into a frameless popup window."""

    def test_menu_becomes_a_translucent_frameless_tool_window_of_its_parent(self):
        _host, anchor, menu = self._menu_on_host()
        menu.show_as_popup(anchor_widget=anchor, position="bottom")
        self.assertTrue(menu.isWindow())
        self.assertEqual(_window_type(menu), QtCore.Qt.Tool)
        self.assertTrue(menu.windowFlags() & QtCore.Qt.FramelessWindowHint)
        self.assertFalse(menu.windowFlags() & QtCore.Qt.WindowDoesNotAcceptFocus)
        self.assertTrue(menu.testAttribute(QtCore.Qt.WA_TranslucentBackground))
        self.assertTrue(menu.testAttribute(QtCore.Qt.WA_ShowWithoutActivating))
        self.assertIs(menu.parentWidget(), anchor)

    def test_parentless_menu_is_parented_to_the_active_window(self):
        host = self.track_widget(QtWidgets.QWidget())
        host.show()
        menu = self.track_widget(
            Menu(trigger_button="none", add_header=False, add_footer=False)
        )
        menu.add(QtWidgets.QLabel("item"))
        with mock.patch.object(
            QtWidgets.QApplication, "activeWindow", return_value=host
        ):
            menu.show()
        self.assertIs(menu.parentWidget(), host)
        self.assertEqual(_window_type(menu), QtCore.Qt.Tool)

    def test_parentless_menu_without_an_active_window_stays_parentless(self):
        menu = self.track_widget(
            Menu(trigger_button="none", add_header=False, add_footer=False)
        )
        menu.add(QtWidgets.QLabel("item"))
        with mock.patch.object(
            QtWidgets.QApplication, "activeWindow", return_value=None
        ):
            menu.show()
        self.assertIsNone(menu.parentWidget())
        self.assertEqual(_window_type(menu), QtCore.Qt.Tool)
        self.assertTrue(menu.windowFlags() & QtCore.Qt.FramelessWindowHint)

    def test_click_flyout_becomes_an_opaque_focusless_tool_window_once(self):
        window = self._host_window()
        lw, (root_item,) = self._click_list(window)
        window.show()
        _process()
        sub = root_item.sublist
        self.assertFalse(sub.isWindow(), "promotion is lazy: nothing before the open")

        QTest.mouseClick(root_item, QtCore.Qt.LeftButton)
        self.assertTrue(sub.isVisible())
        self.assertTrue(sub.isWindow())
        self.assertEqual(_window_type(sub), QtCore.Qt.Tool)
        self.assertTrue(sub.windowFlags() & QtCore.Qt.FramelessWindowHint)
        self.assertTrue(sub.windowFlags() & QtCore.Qt.WindowDoesNotAcceptFocus)
        self.assertTrue(sub.testAttribute(QtCore.Qt.WA_ShowWithoutActivating))
        self.assertFalse(sub.testAttribute(QtCore.Qt.WA_TranslucentBackground))
        self.assertIs(sub.parentWidget(), window)
        flags = sub.windowFlags()

        # Close and reopen: the promotion must not run again (it would recreate
        # the native window). Recorded, not raised: an exception inside the
        # list's eventFilter override would be a native fault, not a failure.
        QTest.mouseClick(root_item, QtCore.Qt.LeftButton)
        self.assertTrue(sub.isHidden())
        reparented = []
        original = sub.setParent

        def _spy(*args):
            reparented.append(args)
            return original(*args)

        with mock.patch.object(sub, "setParent", new=_spy):
            QTest.mouseClick(root_item, QtCore.Qt.LeftButton)
        self.assertTrue(sub.isVisible())
        self.assertEqual(reparented, [])
        self.assertEqual(sub.windowFlags(), flags)


class TestAncestorDismissal(_PopupCase):
    """A popup anchored in a window goes away when that window moves or hides."""

    def test_menu_hides_when_its_host_window_moves(self):
        host, anchor, menu = self._menu_on_host()
        menu.show_as_popup(anchor_widget=anchor, position="bottom")
        self.assertTrue(menu.isVisible())
        host.move(host.pos() + QtCore.QPoint(40, 30))
        _process()
        self.assertFalse(menu.isVisible())

    def test_menu_survives_its_anchor_moving_inside_the_window(self):
        _host, anchor, menu = self._menu_on_host()
        menu.show_as_popup(anchor_widget=anchor, position="bottom")
        anchor.move(anchor.pos() + QtCore.QPoint(5, 5))
        _process()
        self.assertTrue(menu.isVisible())

    def test_menu_stops_watching_once_hidden(self):
        host, anchor, menu = self._menu_on_host()
        menu.show_as_popup(anchor_widget=anchor, position="bottom")
        menu.hide()
        hidden = []
        menu.on_hidden.connect(lambda: hidden.append(True))
        host.move(host.pos() + QtCore.QPoint(40, 30))
        _process()
        self.assertEqual(hidden, [], "a hidden menu must not be hidden again")

    def _value_popup_host(self):
        host = self.track_widget(QtWidgets.QWidget())
        host.resize(300, 200)
        container = QtWidgets.QWidget(host)
        container.resize(200, 100)
        line = QtWidgets.QLineEdit(container)
        host.show()
        _process()
        return host, container, line

    def test_recent_values_popup_closes_when_an_ancestor_hides(self):
        _host, container, line = self._value_popup_host()
        popup = RecentValuesPopup(parent=line)
        self.track_widget(popup.menu)
        popup.add_recent_value("v1")
        popup.show()
        _process()
        self.assertTrue(popup.menu.isVisible())
        container.hide()
        _process()
        self.assertFalse(popup.menu.isVisible())

    def test_recent_values_popup_closes_when_its_window_moves(self):
        host, _container, line = self._value_popup_host()
        popup = RecentValuesPopup(parent=line)
        self.track_widget(popup.menu)
        popup.add_recent_value("v1")
        popup.show()
        _process()
        host.move(host.pos() + QtCore.QPoint(40, 30))
        _process()
        self.assertFalse(popup.menu.isVisible())

    def test_pinned_values_popup_closes_when_an_ancestor_hides(self):
        _host, container, line = self._value_popup_host()
        popup = PinnedValuesPopup(parent=line)
        self.track_widget(popup.menu)
        popup.add_current_value("cur", is_pinned=False)
        popup.show()
        _process()
        self.assertTrue(popup.menu.isVisible())
        container.hide()
        _process()
        self.assertFalse(popup.menu.isVisible())


class TestOutsideClickDismissal(_PopupCase):
    """A click-opened flyout chain closes on an outside press or Escape."""

    def setUp(self):
        super().setUp()
        # These tests park the (process-global) cursor over what they press;
        # later suites read QCursor.pos() for hover state, so put it back.
        home = QtGui.QCursor.pos()
        self.addCleanup(QtGui.QCursor.setPos, home)

    def _open_chain(self):
        window = self._host_window()
        lw, (root_item,) = self._click_list(window)
        other = _KeyRecorder("elsewhere", window)
        other.move(120, 80)
        other.resize(90, 24)
        window.show()
        # Focus BEFORE the open: a focus change pumped while the chain is up is
        # an activation change, and click mode (rightly) dismisses on
        # WindowDeactivate.
        other.setFocus()
        _process()
        QTest.mouseClick(root_item, QtCore.Qt.LeftButton)
        self.assertTrue(root_item.sublist.isVisible(), "the click must open it")
        return lw, root_item, other

    def test_outside_press_collapses_the_chain_and_still_lands(self):
        lw, root_item, other = self._open_chain()
        clicked = []
        other.clicked.connect(lambda *_: clicked.append(True))
        QtGui.QCursor.setPos(other.mapToGlobal(other.rect().center()))
        QTest.mouseClick(other, QtCore.Qt.LeftButton)
        self.assertTrue(root_item.sublist.isHidden())
        self.assertFalse(lw._click_chain_open)
        self.assertIsNone(lw._dismiss_filter)
        self.assertEqual(clicked, [True], "the outside press must reach its target")

    def test_press_inside_the_flyout_keeps_the_chain_open(self):
        lw, root_item, _other = self._open_chain()
        leaf = root_item.sublist.get_items()[0]
        QtGui.QCursor.setPos(leaf.mapToGlobal(leaf.rect().center()))
        QTest.mousePress(leaf, QtCore.Qt.LeftButton)
        self.assertTrue(root_item.sublist.isVisible())
        self.assertTrue(lw._click_chain_open)
        QTest.mouseRelease(leaf, QtCore.Qt.LeftButton)

    def test_escape_collapses_the_chain_and_is_consumed(self):
        lw, root_item, other = self._open_chain()
        QTest.keyClick(other, QtCore.Qt.Key_Escape)
        self.assertTrue(root_item.sublist.isHidden())
        self.assertFalse(lw._click_chain_open)
        self.assertNotIn(QtCore.Qt.Key_Escape, other.keys)
        # With the chain closed the filter is gone: Escape reaches the widget.
        QTest.keyClick(other, QtCore.Qt.Key_Escape)
        self.assertIn(QtCore.Qt.Key_Escape, other.keys)


# -----------------------------------------------------------------------------
# The kit's own units
# -----------------------------------------------------------------------------

from uitk.widgets.popup.dismissal import AncestorDismissal, OutsideClickDismissal
from uitk.widgets.popup.placement import PopupPlacement
from uitk.widgets.popup.window import PopupWindow


class TestPopupPlacementUnits(QtBaseTestCase):
    def test_screen_for_prefers_the_screen_under_the_centre(self):
        screen = QtWidgets.QApplication.primaryScreen()
        rect = QtCore.QRect(screen.geometry().center(), QtCore.QSize(10, 10))
        self.assertIs(PopupPlacement.screen_for(rect), screen)

    def test_screen_for_falls_back_to_most_overlap_then_primary(self):
        left = _FakeScreen(QtCore.QRect(0, 0, 800, 800))
        right = _FakeScreen(QtCore.QRect(800, 0, 800, 800))
        with (
            mock.patch.object(QtWidgets.QApplication, "screenAt", return_value=None),
            mock.patch.object(
                QtWidgets.QApplication, "screens", return_value=[left, right]
            ),
            mock.patch.object(
                QtWidgets.QApplication, "primaryScreen", return_value=left
            ),
        ):
            straddle = QtCore.QRect(700, 0, 300, 100)  # 100 left, 200 right
            self.assertIs(PopupPlacement.screen_for(straddle), right)
            nowhere = QtCore.QRect(5000, 5000, 50, 50)
            self.assertIs(PopupPlacement.screen_for(nowhere), left)

    def test_an_on_screen_surface_is_never_moved(self):
        w = self.track_widget(QtWidgets.QWidget())
        w.resize(100, 80)
        avail = _available()
        w.move(avail.left() + 20, avail.top() + 20)
        with mock.patch.object(w, "move", new=lambda *a: self.fail("moved")):
            PopupPlacement.clamp_to_screen(w)


class TestPopupWindowUnits(QtBaseTestCase):
    FLAGS = QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint

    def test_a_parented_widget_keeps_its_parent(self):
        host = self.track_widget(QtWidgets.QWidget())
        w = QtWidgets.QWidget(host)
        owner = PopupWindow.promote(w, self.FLAGS)
        self.assertIs(owner, host)
        self.assertIs(w.parentWidget(), host)
        self.assertTrue(w.isWindow())
        self.assertFalse(w.testAttribute(QtCore.Qt.WA_TranslucentBackground))
        self.assertTrue(w.testAttribute(QtCore.Qt.WA_ShowWithoutActivating))

    def test_a_failing_or_self_fallback_leaves_it_parentless(self):
        for fallback in (lambda: 1 / 0, None):
            w = self.track_widget(QtWidgets.QWidget())
            chosen = (lambda w=w: w) if fallback is None else fallback
            self.assertIsNone(
                PopupWindow.promote(w, self.FLAGS, parent_fallback=chosen)
            )
            self.assertIsNone(w.parentWidget())
            self.assertEqual(_window_type(w), QtCore.Qt.Tool)


class TestDismissalUnits(QtBaseTestCase):
    def _chain(self):
        window = self.track_widget(QtWidgets.QWidget())
        child = QtWidgets.QWidget(window)
        return window, child

    def test_ancestor_dismissal_honours_its_gate_and_hide_option(self):
        window, child = self._chain()
        dismissed = []
        gate = [False]
        flt = AncestorDismissal(
            child, dismiss=lambda: dismissed.append(True), when=lambda: gate[0]
        )
        self.addCleanup(flt.detach)
        QtWidgets.QApplication.sendEvent(window, QtCore.QEvent(QtCore.QEvent.Move))
        self.assertEqual(dismissed, [], "a closed gate must hold the popup")
        QtWidgets.QApplication.sendEvent(window, QtCore.QEvent(QtCore.QEvent.Hide))
        self.assertEqual(dismissed, [], "Hide dismisses only with on_hide")
        gate[0] = True
        QtWidgets.QApplication.sendEvent(child, QtCore.QEvent(QtCore.QEvent.Move))
        self.assertEqual(dismissed, [], "a non-window move is layout, not travel")
        QtWidgets.QApplication.sendEvent(window, QtCore.QEvent(QtCore.QEvent.Move))
        self.assertEqual(dismissed, [True])

    def test_outside_click_dismissal_only_watches_while_attached(self):
        window = self.track_widget(QtWidgets.QPushButton("x"))
        window.show()
        dismissed = []
        flt = OutsideClickDismissal(
            is_inside=lambda pos: False, dismiss=lambda: dismissed.append(True)
        )
        QTest.mouseClick(window, QtCore.Qt.LeftButton)
        self.assertEqual(dismissed, [])
        flt.attach()
        self.addCleanup(flt.detach)
        QTest.mouseClick(window, QtCore.Qt.LeftButton)
        self.assertEqual(dismissed, [True])
        flt.detach()
        QTest.mouseClick(window, QtCore.Qt.LeftButton)
        self.assertEqual(dismissed, [True])

    def test_outside_click_dismissal_detaches_when_its_popup_died(self):
        window = self.track_widget(QtWidgets.QPushButton("x"))
        window.show()
        calls = []

        def _dead(_pos):
            calls.append(True)
            raise RuntimeError("Internal C++ object already deleted")

        flt = OutsideClickDismissal(is_inside=_dead, dismiss=lambda: None)
        flt.attach()
        self.addCleanup(flt.detach)
        QTest.mouseClick(window, QtCore.Qt.LeftButton)
        QTest.mouseClick(window, QtCore.Qt.LeftButton)
        self.assertEqual(calls, [True], "the first failure must detach it")


if __name__ == "__main__":
    unittest.main()
