#!/usr/bin/python
# coding=utf-8
"""Tests for ``uitk.widgets.embeddedMenu`` (EmbeddedMenuWidget / PersistentMenu).

The classes were re-homed from ``mayatk.ui_utils.maya_native_menus`` (pure Qt,
Maya-flavored only by location); uitk now owns the public surface, so the
geometry math — content sizing, header reservation, window fit-lock — is pinned
here, offscreen. Determinism note: assertions avoid live ``actionGeometry``
values (platform-styled) and instead pin the *relationships* the wrapper
promises — rigid fit, per-row fallback estimates, floors, and chrome deltas.
"""
import unittest

from qtpy import QtCore, QtWidgets

from conftest import QtBaseTestCase
from uitk.widgets.embeddedMenu import EmbeddedMenuWidget, PersistentMenu


class TestPersistentMenu(QtBaseTestCase):
    def test_ignores_hide(self):
        menu = PersistentMenu()
        menu.addAction("a")
        menu.show()
        self.assertTrue(menu.isVisible())
        menu.setVisible(False)  # interaction-driven hides must be ignored
        self.assertTrue(menu.isVisible())
        menu.deleteLater()

    def test_show_still_works(self):
        menu = PersistentMenu()
        menu.setVisible(True)
        self.assertTrue(menu.isVisible())
        menu.deleteLater()


class TestEmbeddedMenuWidget(QtBaseTestCase):
    def _wrapper(self, n_actions=0, n_separators=0):
        menu = PersistentMenu()
        for i in range(n_actions):
            menu.addAction(f"action {i}")
        for _ in range(n_separators):
            menu.addSeparator()
        w = EmbeddedMenuWidget(menu)
        self.addCleanup(w.deleteLater)
        return w

    def test_menu_is_reparented_as_plain_widget(self):
        w = self._wrapper(n_actions=2)
        self.assertIs(w.menu.parent(), w)
        self.assertFalse(w.menu.windowFlags() & QtCore.Qt.Popup)

    def test_empty_menu_uses_height_floor(self):
        w = self._wrapper()
        size = w.content_size()
        self.assertEqual(size.height(), w._EMPTY_HEIGHT_FLOOR)
        self.assertGreaterEqual(size.width(), w._MIN_WIDTH)

    def test_content_height_grows_with_actions(self):
        few = self._wrapper(n_actions=3).content_size().height()
        many = self._wrapper(n_actions=12).content_size().height()
        self.assertGreater(many, few)

    def test_hidden_actions_do_not_count(self):
        w = self._wrapper(n_actions=6)
        full = w._menu_content_height()
        for action in w.menu.actions()[:3]:
            action.setVisible(False)
        self.assertLess(w._menu_content_height(), full)

    def test_separator_estimate_is_smaller_than_action_row(self):
        # The pre-show fallback estimates must keep separators cheaper than rows.
        self.assertLess(
            EmbeddedMenuWidget._SEPARATOR_PX, EmbeddedMenuWidget._ACTION_ROW_PX
        )

    def test_size_hints_are_rigid(self):
        # Rigid-fit contract: both hints are the exact content size.
        w = self._wrapper(n_actions=4)
        self.assertEqual(w.sizeHint(), w.content_size())
        self.assertEqual(w.minimumSizeHint(), w.content_size())

    def test_reserved_top_counts_layout_widgets(self):
        w = self._wrapper(n_actions=2)
        self.assertEqual(w._reserved_top(), 0)
        header = QtWidgets.QLabel("header")
        w.layout().insertWidget(0, header)
        self.assertGreater(w._reserved_top(), 0)
        self.assertGreaterEqual(w._reserved_top(), header.sizeHint().height())

    def test_reserved_top_raises_content_height(self):
        # Enough actions to clear _EMPTY_HEIGHT_FLOOR, else both sides clamp to it.
        w = self._wrapper(n_actions=8)
        bare = w.content_size().height()
        w.layout().insertWidget(0, QtWidgets.QLabel("header"))
        self.assertGreater(w.content_size().height(), bare)

    def test_resize_positions_menu_below_reserved_top(self):
        w = self._wrapper(n_actions=3)
        w.layout().insertWidget(0, QtWidgets.QLabel("header"))
        w.show()
        w.resize(300, 400)
        QtWidgets.QApplication.processEvents()
        margins = w.layout().contentsMargins()
        self.assertEqual(w.menu.geometry().x(), margins.left())
        self.assertGreaterEqual(
            w.menu.geometry().y(), w._reserved_top() + margins.top()
        )
        self.assertEqual(w.menu.width(), w.width() - margins.left() - margins.right())

    def test_fit_to_window_locks_window_to_content(self):
        host = QtWidgets.QMainWindow()
        self.addCleanup(host.deleteLater)
        w = self._wrapper(n_actions=5)
        host.setCentralWidget(w)
        host.show()
        QtWidgets.QApplication.processEvents()
        w.fit_to_window()
        self.assertEqual(host.minimumSize(), host.maximumSize())
        # The lock accounts for chrome, so the window is at least content-sized.
        self.assertGreaterEqual(host.minimumSize().width(), w.content_size().width())
        self.assertGreaterEqual(host.minimumSize().height(), w.content_size().height())

    def test_fit_to_window_noop_when_widget_is_top_level(self):
        w = self._wrapper(n_actions=2)
        w.fit_to_window()  # window() is self — must not raise or lock
        self.assertNotEqual(w.minimumSize(), w.maximumSize())


if __name__ == "__main__":
    unittest.main(verbosity=2)
