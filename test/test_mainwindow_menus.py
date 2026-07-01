# !/usr/bin/python
# coding=utf-8
"""Tests for MainWindow child-menu tracking and the marking-menu fade pass.

Covers:
- MainWindow.register_menu / MainWindow.menus(status filters)
- The lazy-creation invariant (reading menus never instantiates a menu)
- Menu self-registration on first show (real Menu -> real MainWindow)
- MarkingMenu.dim_other_windows / restore_other_windows fading a window's
  open menus, the once-per-hold snapshot guard, and surviving a deleted member

Run standalone: python -m test.test_mainwindow_menus
"""
import gc
import logging
import unittest
import weakref

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets
from uitk.widgets.mainWindow import MainWindow
from uitk.widgets.marking_menu._marking_menu import MarkingMenu
from test_mainwindow import MockSwitchboard


class FakeMenu:
    """Duck-typed stand-in for uitk Menu — the surface menus()/_set_dimmed use."""

    def __init__(self, visible=True, pinned=False, persistent=False):
        self._visible = visible
        self.is_pinned = pinned
        self.is_persistent_mode = persistent
        self.opacity = 1.0
        self.mouse_transparent = False

    def isVisible(self):
        return self._visible

    def setWindowOpacity(self, v):
        self.opacity = v

    def setAttribute(self, attr, on=True):
        self.mouse_transparent = bool(on)


# ---------------------------------------------------------------------------
# MainWindow.menus() API
# ---------------------------------------------------------------------------
class TestMainWindowMenuTracking(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()
        self.win = self.track_widget(MainWindow("W", self.sb))
        # Hold strong refs so the WeakSet keeps them (the test owns lifetime).
        self.m_vis = FakeMenu(visible=True)
        self.m_hidden = FakeMenu(visible=False)
        self.m_pinned = FakeMenu(visible=True, pinned=True)
        self.m_persist = FakeMenu(visible=True, persistent=True)

    def test_register_and_enumerate(self):
        self.win.register_menu(self.m_vis)
        self.assertIn(self.m_vis, self.win.menus())

    def test_register_is_idempotent(self):
        self.win.register_menu(self.m_vis)
        self.win.register_menu(self.m_vis)
        self.assertEqual(len(self.win.menus()), 1)

    def test_filter_visible(self):
        for m in (self.m_vis, self.m_hidden):
            self.win.register_menu(m)
        self.assertEqual(self.win.menus(visible=True), [self.m_vis])
        self.assertEqual(self.win.menus(visible=False), [self.m_hidden])

    def test_filter_pinned_and_persistent(self):
        for m in (self.m_vis, self.m_pinned, self.m_persist):
            self.win.register_menu(m)
        self.assertEqual(self.win.menus(pinned=True), [self.m_pinned])
        self.assertEqual(self.win.menus(persistent=True), [self.m_persist])
        # Combined axes: visible AND not pinned AND not persistent
        plain = self.win.menus(visible=True, pinned=False, persistent=False)
        self.assertIn(self.m_vis, plain)
        self.assertNotIn(self.m_pinned, plain)

    def test_weakset_prunes_dropped_menu(self):
        m = FakeMenu(visible=True)
        wr = weakref.ref(m)
        self.win.register_menu(m)
        self.assertEqual(len(self.win.menus()), 1)
        del m
        gc.collect()
        self.assertIsNone(wr())
        self.assertEqual(self.win.menus(), [])

    def test_menus_does_not_trigger_lazy_creation(self):
        """Reading menus() must never instantiate a deferred menu."""
        from uitk.widgets.mixins.menu_mixin import MenuMixin

        class W(QtWidgets.QPushButton, MenuMixin):
            pass

        w = self.track_widget(W())
        self.win.register_widget(w) if w.objectName() else None
        self.assertFalse(w.has_menu)
        _ = self.win.menus()  # enumerate
        self.assertFalse(w.has_menu)  # still not created


class TestMenuSelfRegistration(QtBaseTestCase):
    """A real Menu shown under a MainWindow registers itself."""

    def setUp(self):
        super().setUp()
        self.sb = MockSwitchboard()
        self.win = self.track_widget(MainWindow("Host", self.sb))

    def test_menu_registers_with_owner_on_show(self):
        from uitk.widgets.menu import Menu

        menu = self.track_widget(Menu(parent=self.win))
        menu.add("QPushButton", setText="A")
        self.assertNotIn(menu, self.win.menus())  # not yet shown
        menu.show()
        app.processEvents()
        self.assertIn(menu, self.win.menus())
        self.assertIn(menu, self.win.menus(visible=True))


# ---------------------------------------------------------------------------
# MarkingMenu fade pass — real dim/restore logic, fake collaborators
# ---------------------------------------------------------------------------
class FakeWindow:
    """A backgrounded window: has_tags + isVisible + menus() + opacity, like
    MainWindow. ``visible`` defaults True; a hidden window can still own a
    visible (orphaned) menu — that menu must fade, the hidden window need not."""

    def __init__(self, tags=(), menus=(), visible=True):
        self._tags = set(tags)
        self._menus = list(menus)
        self._visible = visible
        self.opacity = 1.0
        self.mouse_transparent = False

    def isVisible(self):
        return self._visible

    def has_tags(self, tags):
        return bool(self._tags & set(tags))

    def menus(self, *, visible=None, **_):
        if visible is None:
            return list(self._menus)
        return [m for m in self._menus if m.isVisible() == visible]

    def setWindowOpacity(self, v):
        self.opacity = v

    def setAttribute(self, attr, on=True):
        self.mouse_transparent = bool(on)


class _LoadedUi:
    """Stand-in for Switchboard.loaded_ui — the dim pass only reads .values()."""

    def __init__(self, windows):
        self._windows = list(windows)

    def values(self):
        return list(self._windows)


class _FakeSb:
    """Mirrors the slice of the Switchboard surface the dim pass reads:
    ``loaded_ui`` (every loaded window, visible or not) — iterating it, rather
    than a visible-only subset, is what lets the fade reach the orphaned menus
    of hidden parents."""

    def __init__(self, windows):
        self._windows = list(windows)

    @property
    def loaded_ui(self):
        return _LoadedUi(self._windows)


class DimHarness:
    """Minimal carrier for the real dim/restore logic (stub pattern). Borrows
    the methods under test — including the ``_dim_targets`` discovery generator
    — so the behavior exercised is the real code, not a reimplementation. The
    ``_MARKING_MENU_TAGS`` skip set is a module global the borrowed methods
    resolve directly, so the carrier needs no copy of it."""

    dim_other_windows = MarkingMenu.dim_other_windows
    restore_other_windows = MarkingMenu.restore_other_windows
    _dim_targets = MarkingMenu._dim_targets
    _set_dimmed = MarkingMenu._set_dimmed

    def __init__(self, sb, visible=True):
        self.sb = sb
        self._visible = visible
        self._windows_to_restore = set()
        self._dim_snapshot_taken = False
        self.logger = logging.getLogger("dimtest")

    def isVisible(self):
        return self._visible


class TestMarkingMenuDim(QtBaseTestCase):
    def _harness(self, windows):
        return DimHarness(_FakeSb(windows))

    def test_dims_window_and_its_visible_menus(self):
        menu_open = FakeMenu(visible=True)
        menu_hidden = FakeMenu(visible=False)
        win = FakeWindow(menus=[menu_open, menu_hidden])
        h = self._harness([win])

        h.dim_other_windows()

        self.assertEqual(win.opacity, 0.15)
        self.assertEqual(menu_open.opacity, 0.15)  # open menu faded with window
        self.assertEqual(menu_hidden.opacity, 1.0)  # hidden menu untouched
        self.assertIn(win, h._windows_to_restore)
        self.assertIn(menu_open, h._windows_to_restore)

    def test_dims_orphaned_menu_of_hidden_parent(self):
        """Regression: orphaned menus are intentional — a window can be hidden
        while one of its menus stays open as a small floating tool. That menu
        must still fade during a hold even though its parent is absent from
        ``visible_windows``; the hidden parent itself needs no dim.

        Fails on the old ``visible_windows`` discovery (the orphan is never
        reached); passes once discovery spans ``loaded_ui``.
        """
        orphan = FakeMenu(visible=True)
        hidden_parent = FakeWindow(menus=[orphan], visible=False)
        visible_win = FakeWindow(menus=[FakeMenu(visible=True)], visible=True)
        h = self._harness([visible_win, hidden_parent])

        h.dim_other_windows()

        self.assertEqual(
            orphan.opacity, 0.15, "orphaned menu of a hidden parent was not faded"
        )
        self.assertIn(orphan, h._windows_to_restore)
        self.assertEqual(
            hidden_parent.opacity, 1.0, "a hidden window itself needs no dim"
        )
        self.assertNotIn(hidden_parent, h._windows_to_restore)

    def test_dims_option_menu_hosted_on_a_surface_window(self):
        """Regression: an option-box menu launched from a startmenu/submenu
        surface must fade on key_show exactly like one launched from a
        standalone window — a popup is never part of the radial gesture, even
        when its owner window carries a surface tag. The surface window itself
        still stays bright (it *is* the gesture surface).

        Fails when the surface-tag skip also skips the window's child menus;
        passes once the skip gates only the window's own dim.
        """
        option_menu = FakeMenu(visible=True)
        surface = FakeWindow(tags={"submenu"}, menus=[option_menu], visible=True)
        h = self._harness([surface])

        h.dim_other_windows()

        self.assertEqual(
            option_menu.opacity, 0.15, "option menu on a submenu surface did not fade"
        )
        self.assertIn(option_menu, h._windows_to_restore)
        self.assertEqual(
            surface.opacity, 1.0, "the radial surface window itself must stay bright"
        )
        self.assertNotIn(surface, h._windows_to_restore)

    def test_transient_surface_window_itself_is_not_dimmed(self):
        """A startmenu/submenu surface window is the active gesture surface and
        is never dimmed, even when visible. (Its *popups* still background — see
        ``test_dims_option_menu_hosted_on_a_surface_window``.)"""
        win = FakeWindow(tags={"submenu"}, visible=True)
        h = self._harness([win])
        h.dim_other_windows()
        self.assertEqual(win.opacity, 1.0)
        self.assertEqual(h._windows_to_restore, set())

    def test_snapshot_is_once_per_hold(self):
        win = FakeWindow(menus=[FakeMenu(visible=True)])
        h = self._harness([win])
        h.dim_other_windows()
        # A menu opened DURING the hold must stay bright on a re-run.
        late = FakeMenu(visible=True)
        win._menus.append(late)
        h.dim_other_windows()  # second call — guarded no-op
        self.assertEqual(late.opacity, 1.0)
        self.assertNotIn(late, h._windows_to_restore)

    def test_restore_resets_everything(self):
        menu_open = FakeMenu(visible=True)
        win = FakeWindow(menus=[menu_open])
        h = self._harness([win])
        h.dim_other_windows()
        h.restore_other_windows()
        self.assertEqual(win.opacity, 1.0)
        self.assertEqual(menu_open.opacity, 1.0)
        self.assertEqual(h._windows_to_restore, set())
        self.assertFalse(h._dim_snapshot_taken)  # next hold can snapshot again

    def test_restore_survives_deleted_member(self):
        class Exploding:
            def setWindowOpacity(self, v):
                raise RuntimeError("C++ object deleted")

            def setAttribute(self, *a):
                raise RuntimeError("C++ object deleted")

        h = self._harness([])
        h._windows_to_restore = {Exploding()}
        # Must not raise.
        h.restore_other_windows()
        self.assertEqual(h._windows_to_restore, set())


if __name__ == "__main__":
    unittest.main()
