# !/usr/bin/python
# coding=utf-8
"""Unit tests for dismiss-on-ancestor-move popup behavior.

Covers:
- Menu.show_as_popup hides when a window-ancestor of the anchor moves.
- A pinned Menu does NOT hide on ancestor move.
- Moves of intermediate (non-window) child widgets do NOT dismiss.
- RecentValuesPopup closes on window-ancestor move.
- PinnedValuesPopup closes on window-ancestor move.
- Filter detaches on hide so subsequent host moves don't act on stale targets.
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets

from uitk.widgets.menu import Menu, _DismissOnAncestorMove
from uitk.widgets.optionBox.options.recent_values import RecentValuesPopup
from uitk.widgets.optionBox.options.pin_values import PinnedValuesPopup


def _process():
    QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)


def _send_move(widget):
    """Synthesize a QEvent.Move directly to the widget's event filter chain.

    Uses sendEvent rather than relying on actual window-manager motion so the
    test is deterministic on offscreen QPA backends.
    """
    ev = QtCore.QEvent(QtCore.QEvent.Move)
    QtWidgets.QApplication.sendEvent(widget, ev)


class TestMenuDismissOnMove(QtBaseTestCase):
    """Menu shown via show_as_popup hides when a window-ancestor moves."""

    def _build(self):
        host = self.track_widget(QtWidgets.QWidget())
        host.resize(300, 200)
        anchor = self.track_widget(QtWidgets.QPushButton("anchor", host))
        anchor.move(10, 10)
        anchor.resize(80, 24)
        host.show()
        _process()

        menu = self.track_widget(
            Menu(
                parent=anchor,
                trigger_button="none",
                position="bottom",
                add_header=False,
                add_footer=False,
                add_apply_button=False,
                hide_on_leave=False,
                ensure_on_screen=False,
            )
        )
        menu.add(QtWidgets.QLabel("item"))
        return host, anchor, menu

    def test_show_as_popup_installs_filter(self):
        host, anchor, menu = self._build()
        menu.show_as_popup(anchor_widget=anchor, position="bottom")
        _process()
        self.assertTrue(menu.isVisible())
        self.assertIsNotNone(menu._dismiss_on_move_filter)

    def test_window_ancestor_move_hides_menu(self):
        host, anchor, menu = self._build()
        menu.show_as_popup(anchor_widget=anchor, position="bottom")
        _process()
        self.assertTrue(menu.isVisible())

        _send_move(host)
        _process()
        self.assertFalse(menu.isVisible())

    def test_intermediate_child_move_does_not_dismiss(self):
        """Move events on non-window widgets must not dismiss the menu."""
        host, anchor, menu = self._build()
        menu.show_as_popup(anchor_widget=anchor, position="bottom")
        _process()
        self.assertTrue(menu.isVisible())

        # anchor is a child widget, not a window — its move() fires Move
        # events but the filter must skip them.
        _send_move(anchor)
        _process()
        self.assertTrue(menu.isVisible())

    def test_pinned_menu_survives_ancestor_move(self):
        host, anchor, menu = self._build()
        menu.show_as_popup(anchor_widget=anchor, position="bottom")
        _process()

        # Pin the menu via prevent_hide (one of two backing flags for is_pinned).
        # Menu.hide(force=False) and the dismiss filter both honor this.
        menu.prevent_hide = True
        self.assertTrue(menu.is_pinned)

        _send_move(host)
        _process()
        self.assertTrue(menu.isVisible())

        menu.prevent_hide = False

    def test_filter_detached_after_hide(self):
        host, anchor, menu = self._build()
        menu.show_as_popup(anchor_widget=anchor, position="bottom")
        _process()
        self.assertIsNotNone(menu._dismiss_on_move_filter)

        menu.hide()
        _process()
        self.assertIsNone(menu._dismiss_on_move_filter)

        # A second move on host with no live filter must be a no-op
        # (i.e., no exception, menu stays hidden).
        _send_move(host)
        _process()
        self.assertFalse(menu.isVisible())

    def test_reshow_replaces_filter_without_leak(self):
        host, anchor, menu = self._build()
        menu.show_as_popup(anchor_widget=anchor, position="bottom")
        _process()
        first = menu._dismiss_on_move_filter

        menu.hide()
        _process()
        menu.show_as_popup(anchor_widget=anchor, position="bottom")
        _process()
        second = menu._dismiss_on_move_filter

        self.assertIsNotNone(second)
        self.assertIsNot(first, second)


class TestRecentValuesPopupDismissOnMove(QtBaseTestCase):
    """RecentValuesPopup closes when a window-ancestor moves."""

    def test_window_move_closes_popup(self):
        host = self.track_widget(QtWidgets.QWidget())
        host.resize(300, 200)
        line = self.track_widget(QtWidgets.QLineEdit(host))
        line.move(10, 10)
        host.show()
        _process()

        popup = RecentValuesPopup(parent=line)
        self.track_widget(popup.menu)
        popup.add_recent_value("v1")
        popup.show()
        _process()
        self.assertTrue(popup.menu.isVisible())

        _send_move(host)
        _process()
        self.assertFalse(popup.menu.isVisible())

    def test_intermediate_widget_move_does_not_close(self):
        host = self.track_widget(QtWidgets.QWidget())
        host.resize(300, 200)
        line = self.track_widget(QtWidgets.QLineEdit(host))
        host.show()
        _process()

        popup = RecentValuesPopup(parent=line)
        self.track_widget(popup.menu)
        popup.add_recent_value("v1")
        popup.show()
        _process()

        _send_move(line)  # not a window
        _process()
        self.assertTrue(popup.menu.isVisible())


class TestPinnedValuesPopupDismissOnMove(QtBaseTestCase):
    """PinnedValuesPopup closes when a window-ancestor moves."""

    def test_window_move_closes_popup(self):
        host = self.track_widget(QtWidgets.QWidget())
        host.resize(300, 200)
        line = self.track_widget(QtWidgets.QLineEdit(host))
        host.show()
        _process()

        popup = PinnedValuesPopup(parent=line)
        self.track_widget(popup.menu)
        popup.add_current_value("cur", is_pinned=False)
        popup.show()
        _process()
        self.assertTrue(popup.menu.isVisible())

        _send_move(host)
        _process()
        self.assertFalse(popup.menu.isVisible())


class TestDismissOnAncestorMoveDirect(QtBaseTestCase):
    """Direct unit tests for the filter class itself."""

    def test_walks_full_ancestor_chain(self):
        a = self.track_widget(QtWidgets.QWidget())
        b = self.track_widget(QtWidgets.QWidget(a))
        c = self.track_widget(QtWidgets.QWidget(b))

        target = self.track_widget(QtWidgets.QWidget())
        flt = _DismissOnAncestorMove(target_menu=target, anchor_widget=c)

        self.assertIn(a, flt._watched)
        self.assertIn(b, flt._watched)
        self.assertIn(c, flt._watched)
        flt.detach()
        self.assertEqual(flt._watched, [])

    def test_detach_idempotent(self):
        a = self.track_widget(QtWidgets.QWidget())
        target = self.track_widget(QtWidgets.QWidget())
        flt = _DismissOnAncestorMove(target_menu=target, anchor_widget=a)
        flt.detach()
        flt.detach()  # must not raise
        self.assertIsNone(flt._target)


if __name__ == "__main__":
    unittest.main()
