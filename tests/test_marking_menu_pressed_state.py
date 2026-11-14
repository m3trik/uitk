# !/usr/bin/python
# coding=utf-8
"""Regression tests for the stuck ``:pressed`` (checked-orange) MenuButton.

Live symptom (tentacle ``polygons#submenu``, button ``i010`` 'Polygons'): after
interacting with the submenu, the button paints the checked-orange tint whenever
the cursor is NOT over it — hover looks correct (the ``QAbstractButton:hover``
rule outranks ``.MenuButton:pressed`` by specificity), but on hover-leave the
orange shows.

Root cause: a press over an owned menu item is deliberately passed through to
the button itself (``mousePressEvent``'s ``_is_menu_item_press`` early return /
the child holding the migrated grab), so Qt sets the button ``down``. The
matching RELEASE, however, is dispatched through ``_handle_menu_item_release``
and CONSUMED — it never reaches the button's own ``mouseReleaseEvent``, the only
thing that would clear ``down`` again. ``i010`` is the only MenuButton that
exposes it because its hover-nav is a no-op (its ``submenu_name()`` is the UI it
lives on), so it's the only nav button a user ever presses while it stays
visible.

Fix under test: ``MarkingMenu._clear_button_down`` on every release-consume
path, plus the ``MenuButton.hideEvent`` backstop.
"""
import unittest
from unittest import mock

from qtpy import QtCore, QtGui, QtWidgets

from conftest import QtBaseTestCase
from test_marking_menu_integration import (
    DriveableMarkingMenu,
    StubUi,
    DEFAULT_BINDINGS,
)
from uitk.widgets.menuButton import MenuButton


def _release_event(pos=QtCore.QPointF(10, 10), button=QtCore.Qt.LeftButton):
    return QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonRelease,
        pos,
        pos,
        button,
        QtCore.Qt.NoButton,
        QtCore.Qt.NoModifier,
    )


class ConsumedReleaseClearsDown(QtBaseTestCase):
    """A release the menu dispatches-and-consumes must clear the pass-through
    press's ``down`` state on the button (the stuck-orange root cause)."""

    def setUp(self):
        super().setUp()
        self._drain_qt_events()

        self.parent = QtWidgets.QWidget()
        self.parent.resize(400, 400)
        self.parent.show()
        self.track_widget(self.parent)

        self.mm = DriveableMarkingMenu(self.parent, dict(DEFAULT_BINDINGS))
        QtWidgets.QWidget.show(self.mm)
        self.track_widget(self.mm)

        # The i010 situation: a 'polygons#submenu' surface holding a MenuButton
        # whose click-target is the standalone 'polygons' window.
        self.submenu = StubUi("polygons#submenu", parent=self.mm)
        self.submenu._tags = {"submenu"}
        self.submenu.tags = ["submenu"]
        self.mm.sb.register_ui(self.submenu)
        self.track_widget(self.submenu)

        self.polygons = StubUi("polygons", parent=self.mm)  # untagged: standalone
        self.mm.sb.register_ui(self.polygons)
        self.track_widget(self.polygons)

        self.btn = MenuButton(self.submenu, target="polygons", setText="Polygons")
        self.btn.setObjectName("i010")
        self.btn.resize(66, 21)  # the .ui-authored geometry
        self.btn.ui = self.submenu
        self.btn.base_name = lambda: "i"
        self.track_widget(self.btn)

        # The stub Switchboard has no MenuButton target resolver — mirror the
        # real one's contract (bare target name), and let get_ui accept a
        # widget instance the way the real Switchboard does.
        self.mm.sb.menu_button_target_name = lambda w: w.target or None
        _orig_get_ui = self.mm.sb.get_ui
        self.mm.sb.get_ui = lambda n: (
            n if isinstance(n, QtWidgets.QWidget) else _orig_get_ui(n)
        )

        self.mm._activation_key_held = True
        self.mm.sb.current_ui = self.submenu
        self.mm._current_widget = self.submenu

    def test_child_grab_release_clears_pass_through_down(self):
        """Press passes through to the button (Qt sets it down); the grab-
        migrated release is consumed by child_mouseButtonReleaseEvent → the
        button must NOT be left ``down`` (it would paint the checked-orange
        ``.MenuButton:pressed`` on hover-leave forever)."""
        # The pass-through press: delivered to the button itself, as happens
        # live when _is_menu_item_press lets the button consume the press.
        press = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(5, 5),
            QtCore.QPointF(5, 5),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(self.btn, press)
        self.assertTrue(
            self.btn.isDown(), "precondition: the pass-through press sets down"
        )

        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=self.btn
        ):
            consumed = self.mm.child_mouseButtonReleaseEvent(
                self.btn, _release_event()
            )

        self.assertTrue(consumed, "precondition: the release was dispatched")
        self.assertFalse(
            self.btn.isDown(),
            "consumed release left the button down — it will paint the "
            "checked-orange :pressed tint on hover-leave (the i010 regression)",
        )

    def test_trailing_chord_release_clears_down(self):
        """The swallowed trailing release of a chord pair must also clear a
        residual down state on whatever button it resolves to."""
        self.btn.setDown(True)
        self.mm._action_dispatched = True  # first release already fired

        with mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=self.btn
        ):
            consumed = self.mm.child_mouseButtonReleaseEvent(
                self.btn, _release_event()
            )

        self.assertTrue(consumed)
        self.assertFalse(self.btn.isDown())

    def test_deferred_partial_release_clears_down(self):
        """A partial chord release (other button still held, not over an owned
        item) keeps the child's grab — but must not leave the child painted
        pressed while the tolerance window runs."""
        self.btn.setDown(True)

        with mock.patch.object(QtWidgets.QApplication, "widgetAt", return_value=None):
            # Release L while R is still held → deferred; the child keeps the grab.
            ev = QtGui.QMouseEvent(
                QtCore.QEvent.MouseButtonRelease,
                QtCore.QPointF(300, 300),
                QtCore.QPointF(300, 300),
                QtCore.Qt.LeftButton,
                QtCore.Qt.RightButton,
                QtCore.Qt.NoModifier,
            )
            consumed = self.mm.child_mouseButtonReleaseEvent(self.btn, ev)

        self.assertTrue(consumed)
        self.assertFalse(self.btn.isDown())

    def test_clear_button_down_ignores_non_buttons_and_dead_refs(self):
        """The helper is defensive: non-buttons and None are no-ops."""
        label = QtWidgets.QLabel("x")
        self.track_widget(label)
        self.mm._clear_button_down(label, None)  # must not raise


class MenuButtonHideClearsPressed(QtBaseTestCase):
    """Widget-level backstop: hiding a MenuButton drops a latched down state
    (the click that dispatched typically hides the button's UI)."""

    def test_hide_clears_down(self):
        btn = MenuButton(None, target="polygons", setText="Polygons")
        self.track_widget(btn)
        btn.show()
        btn.setDown(True)
        btn.hide()
        self.assertFalse(
            btn.isDown(),
            "hidden-while-down MenuButton must not repaint :pressed on reshow",
        )


class NavOnlyContentFit(QtBaseTestCase):
    """add_child_event_filter fits ONLY MenuButtons to their content — regular
    slot buttons/labels keep their Designer-authored geometry (fit-to-content
    for wrapped widgets is the OptionBoxContainer's job)."""

    def setUp(self):
        super().setUp()
        self._drain_qt_events()

        self.parent = QtWidgets.QWidget()
        self.parent.resize(400, 400)
        self.parent.show()
        self.track_widget(self.parent)

        self.mm = DriveableMarkingMenu(self.parent, dict(DEFAULT_BINDINGS))
        self.track_widget(self.mm)

        self.submenu = StubUi("polygons#submenu", parent=self.mm)
        self.submenu._tags = {"submenu"}
        self.submenu.tags = ["submenu"]
        self.mm.sb.register_ui(self.submenu)
        self.track_widget(self.submenu)

        self.centered = []
        self.mm.sb.center_widget = lambda w, **kw: self.centered.append(w)

    def _make(self, cls, name, **kwargs):
        w = cls(self.submenu, **kwargs) if kwargs else cls(self.submenu)
        w.setObjectName(name)
        w.ui = self.submenu
        w.base_name = lambda: name.rstrip("0123456789")
        w.derived_type = (
            QtWidgets.QPushButton
            if isinstance(w, QtWidgets.QPushButton)
            else type(w)
        )
        w.type = type(w)
        self.track_widget(w)
        return w

    def test_only_menubuttons_are_content_fit(self):
        nav = self._make(MenuButton, "i010", target="polygons", setText="Polygons")
        leaf = self._make(QtWidgets.QPushButton, "b001")
        label = self._make(QtWidgets.QLabel, "lbl000")

        self.mm.add_child_event_filter([nav, leaf, label])

        self.assertIn(nav, self.centered, "MenuButton must be fit to content")
        self.assertNotIn(
            leaf, self.centered, "plain slot button must keep Designer geometry"
        )
        self.assertNotIn(
            label, self.centered, "label must keep Designer geometry"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
