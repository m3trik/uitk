# !/usr/bin/python
# coding=utf-8
"""Tests for MarkingMenu show/hide behaviour when standalone windows are opened."""
import unittest
from qtpy import QtWidgets, QtCore

from conftest import QtBaseTestCase
from uitk.widgets.marking_menu._resolver import resolve_target_menu


class MarkingMenuStub(QtWidgets.QStackedWidget):
    """Minimal stub that replicates the MarkingMenu methods under test.

    Re-implements just enough of ``_show_window``, ``_sync_menu_to_state``,
    ``_on_activation_press``, ``_on_activation_release`` and ``hide`` to
    verify the standalone-window reshow guards without booting Switchboard.
    """

    key_show_release = QtCore.Signal()

    def __init__(self, parent=None, bindings=None):
        super().__init__(parent)
        self._activation_key_held = False
        self._activation_key_str = "Key_F12"
        self._standalone_suppress = False
        self._bindings = bindings or {"Key_F12": "startmenu"}
        self._suppress_default_on_reentry = False
        self._non_default_shown = False
        self._current_widget = None
        self._last_shown_ui = None

    def _sync_menu_to_state(self, *, buttons=0, modifiers=0, extra_key=None):
        # NOTE: deliberately NO isHidden() gate — production has none and must
        # not: _on_activation_press syncs while hidden to open the menu at all.
        # The reshow-after-_show_window protection is _activation_key_held
        # being cleared (the resolver returns None when the key isn't held).
        target = resolve_target_menu(
            activation_held=self._activation_key_held,
            activation_key_str=self._activation_key_str,
            buttons=int(buttons) if buttons else 0,
            modifiers=int(modifiers) if modifiers else 0,
            bindings=self._bindings,
            extra_key=extra_key,
        )
        if target:
            self._last_shown_ui = target

    def _show_window(self, widget, pos=None, force=False, **kwargs):
        if widget.parent() is self:
            widget.setParent(self.parent(), QtCore.Qt.Window)
        self._activation_key_held = False
        self._standalone_suppress = True
        self.hide()
        return widget

    def _on_activation_press(self):
        if self._standalone_suppress:
            return
        self._activation_key_held = True

    def _on_activation_release(self):
        self._activation_key_held = False
        self._standalone_suppress = False
        self.key_show_release.emit()
        self.hide()


class TestStandaloneWindowSuppression(QtBaseTestCase):
    """Verify the marking menu doesn't reshow after opening a standalone window."""

    def setUp(self):
        super().setUp()
        self.parent = QtWidgets.QWidget()
        self.track_widget(self.parent)
        self.mm = MarkingMenuStub(self.parent, bindings={"Key_F12": "startmenu"})
        self.track_widget(self.mm)

    # ----- _show_window guards -----

    def test_show_window_clears_activation_key_held(self):
        """_show_window must clear _activation_key_held so subsequent state
        syncs won't resolve any activation-keyed binding."""
        self.mm._activation_key_held = True
        child = QtWidgets.QWidget()
        self.track_widget(child)
        self.mm._show_window(child)
        self.assertFalse(self.mm._activation_key_held)

    def test_show_window_sets_standalone_suppress(self):
        """_show_window must set the suppression flag."""
        child = QtWidgets.QWidget()
        self.track_widget(child)
        self.mm._show_window(child)
        self.assertTrue(self.mm._standalone_suppress)

    def test_show_window_hides_marking_menu(self):
        """_show_window must hide the MarkingMenu."""
        self.mm.show()
        child = QtWidgets.QWidget()
        self.track_widget(child)
        self.mm._show_window(child)
        self.assertTrue(self.mm.isHidden())

    def test_show_window_reparents_child_widgets(self):
        """If the standalone window is a child of the MarkingMenu, it must be
        reparented before hiding so it isn't hidden alongside the overlay."""
        child = QtWidgets.QWidget(self.mm)
        self.track_widget(child)
        self.assertIs(child.parent(), self.mm)
        self.mm._show_window(child)
        self.assertIsNot(child.parent(), self.mm)

    def test_show_window_does_not_auto_pin(self):
        """Standalone windows must NOT be auto-pinned on open.

        Windows should hide when the activation key is released (unless
        the user has explicitly pinned or minimized them).
        Updated: 2025-07-17
        """
        child = QtWidgets.QMainWindow()
        child._pinned = False
        child.set_pinned = lambda v: setattr(child, "_pinned", v)
        self.track_widget(child)
        self.mm._show_window(child)
        self.assertFalse(child._pinned)

    # ----- _sync_menu_to_state guards -----

    def test_sync_menu_to_state_noop_after_show_window(self):
        """A sync after _show_window must not resolve a menu (no reshow).

        Bug: releasing all mouse buttons while F12 was held after _show_window
        reshowed the overlay via a stale state lookup. The production guard is
        _show_window clearing ``_activation_key_held`` — the resolver returns
        None when the activation key isn't held. (A prior version of this test
        asserted an ``isHidden()`` gate that existed only in this stub;
        production has no such gate and must not — ``_on_activation_press``
        syncs while hidden to open the menu at all.)
        """
        self.mm._activation_key_held = True
        self.mm.show()
        w = QtWidgets.QWidget()
        self.track_widget(w)
        self.mm._show_window(w)
        # _show_window cleared _activation_key_held: any subsequent sync — the
        # trailing all-buttons release — must resolve to nothing.
        self.mm._last_shown_ui = None
        self.mm._sync_menu_to_state(buttons=0, modifiers=0)
        self.assertIsNone(self.mm._last_shown_ui)
        self.assertTrue(self.mm.isHidden())

    def test_sync_menu_to_state_still_works_when_visible(self):
        """Normal sync (menu visible) should resolve and record the target."""
        self.mm._activation_key_held = True
        self.mm.show()
        self.mm._last_shown_ui = None
        self.mm._sync_menu_to_state(buttons=0, modifiers=0)
        self.assertEqual(self.mm._last_shown_ui, "startmenu")

    # ----- _on_activation_press / _on_activation_release guards -----

    def test_activation_press_suppressed_after_standalone_window(self):
        """If a standalone window was opened during this key-hold cycle,
        a spurious re-press must NOT reactivate the marking menu."""
        self.mm._activation_key_held = True
        self.mm.show()
        self.mm._show_window(QtWidgets.QWidget())
        self.assertTrue(self.mm._standalone_suppress)
        self.mm._on_activation_press()
        self.assertFalse(self.mm._activation_key_held)

    def test_suppression_cleared_on_real_release(self):
        """After the user actually releases the key, the suppression flag
        must clear so the next key press works normally."""
        self.mm._standalone_suppress = True
        self.mm._on_activation_release()
        self.assertFalse(self.mm._standalone_suppress)

    def test_full_cycle_reshow_after_release_and_repress(self):
        """After a standalone window is opened, releasing and re-pressing the
        key should show the marking menu normally."""
        self.mm._activation_key_held = True
        self.mm.show()
        self.mm._show_window(QtWidgets.QWidget())

        self.mm._on_activation_release()
        self.assertFalse(self.mm._standalone_suppress)

        self.mm._on_activation_press()
        self.assertTrue(self.mm._activation_key_held)

    def test_key_show_release_always_emitted(self):
        """key_show_release is always emitted on activation release, even
        after a standalone window open. This allows request_hide to close
        unpinned standalone windows when the key is released.
        Updated: 2025-07-17
        """
        received = []
        self.mm.key_show_release.connect(lambda: received.append(True))

        self.mm._standalone_suppress = True
        self.mm._on_activation_release()
        self.assertEqual(received, [True], "key_show_release should always fire")

    def test_key_show_release_emitted_on_normal_release(self):
        """key_show_release must still fire on a normal (non-standalone)
        activation release."""
        received = []
        self.mm.key_show_release.connect(lambda: received.append(True))

        self.mm._standalone_suppress = False
        self.mm._on_activation_release()
        self.assertEqual(received, [True])


# ── Stacked-UI persistence opt-out (tier 2 of the geometry-loop fix) ──
#
# Tier 1 (test_mainwindow.TestMainWindowGeometry) verifies the primitive:
# restore_window_size=False blocks both save-on-hide and restore-on-show.
# Tier 2 (here) verifies MarkingMenu correctly opts stacked UIs out of
# that persistence — without which the primitive sits unused and the
# 200x100-cropped-cameras-menu regression returns.


from test_mainwindow import MockSwitchboard as _MockSwitchboard


class _NoopUiHandler:
    def apply_styles(self, ui):
        pass

    def setup_lifecycle(self, ui, **kwargs):
        pass


class _InitOnlyMarkingMenu(QtWidgets.QWidget):
    """Bypass MarkingMenu.__init__ so we can call the real _init_ui.

    The persistence opt-out lives in ``MarkingMenu._init_ui``, so the test
    must hit that exact code path. Booting the real ``__init__`` pulls in
    Switchboard / GlobalShortcut / EventFactoryFilter setup that's
    irrelevant to what we're verifying. We borrow ``_init_ui`` and
    ``addWidget`` from MarkingMenu itself and stub out only the bits
    ``_init_ui`` reaches into for non-persistence work.
    """

    key_show_release = QtCore.Signal()

    def __init__(self, parent=None):
        import logging

        from uitk.widgets.marking_menu._marking_menu import MarkingMenu

        super().__init__(parent=parent)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ui_handler = _NoopUiHandler()
        # Borrow the real implementations under test (the persistence
        # opt-out lives in _host_stacked, reached via _init_ui).
        self._init_ui = MarkingMenu._init_ui.__get__(self, type(self))
        self._host_stacked = MarkingMenu._host_stacked.__get__(self, type(self))
        self.addWidget = MarkingMenu.addWidget.__get__(self, type(self))

    def add_child_event_filter(self, widgets):
        # Real impl needs self.sb / self.child_event_filter; orthogonal to
        # the persistence behaviour under test.
        pass


class TestStackedMenuPersistenceOptOut(QtBaseTestCase):
    """MarkingMenu must opt stacked UIs out of MainWindow's geometry persistence.

    Stacked menus (startmenu/submenu) hide on every transition and reshow on
    the next gesture. Without an opt-out, a transient bad size saved during
    a hide gets restored on the next show, locking the menu to that size.
    The fix: ``_init_ui`` sets ``restore_window_size = False`` and clears
    any previously-saved value.
    """

    def setUp(self):
        super().setUp()
        self.parent = QtWidgets.QWidget()
        self.parent.resize(400, 400)
        self.track_widget(self.parent)

        self.mm = self.track_widget(_InitOnlyMarkingMenu(self.parent))
        self.sb = _MockSwitchboard()

    def _make_ui(self, name, tags):
        from uitk.widgets.mainWindow import MainWindow

        return self.track_widget(MainWindow(name, self.sb, tags=list(tags)))

    def test_init_ui_disables_persistence_for_startmenu(self):
        """A startmenu UI must come out of _init_ui with restore_window_size=False."""
        ui = self._make_ui("StartMenuOptOutTest", tags=["startmenu"])
        self.assertTrue(ui.restore_window_size, "default must be True before _init_ui")

        self.mm._init_ui(ui)

        self.assertFalse(
            ui.restore_window_size,
            "stacked startmenu must be opted out of geometry persistence",
        )

    def test_init_ui_disables_persistence_for_submenu(self):
        """Submenu UIs must also be opted out — same hide/reshow lifecycle."""
        ui = self._make_ui("SubmenuOptOutTest", tags=["submenu"])

        self.mm._init_ui(ui)

        self.assertFalse(
            ui.restore_window_size,
            "stacked submenu must be opted out of geometry persistence",
        )

    def test_init_ui_clears_previously_saved_geometry(self):
        """Pre-existing bad geometry in QSettings must be wiped on init.

        This is the recovery path: a user who hit the loop before the fix
        landed has 200x100 in their registry. _init_ui must clear it so
        the next show isn't shrunk.
        """
        name = "ClearOnInitTest"

        seeder = self._make_ui(name, tags=["startmenu"])
        # Save a deliberately bad geometry as a prior buggy session would.
        seeder.show()
        QtWidgets.QApplication.processEvents()
        seeder.resize(180, 90)
        QtWidgets.QApplication.processEvents()
        # Force-save while restore_window_size is still True.
        seeder.save_window_geometry()
        saved_before = seeder.settings.getByteArray("window_geometry")
        self.assertTrue(saved_before, "test setup: seeder did not save geometry")
        seeder.hide()

        # New UI with same name — should find seeded value, then have
        # _init_ui clear it.
        recovered = self._make_ui(name, tags=["startmenu"])
        self.assertTrue(
            recovered.settings.getByteArray("window_geometry"),
            "new window with same name should see the seeded geometry",
        )

        self.mm._init_ui(recovered)

        cleared = recovered.settings.getByteArray("window_geometry")
        # settings.clear() may leave None or an empty QByteArray
        cleared_bytes = bytes(cleared) if cleared else b""
        self.assertFalse(
            cleared_bytes,
            f"_init_ui must wipe stale geometry; still got {cleared_bytes!r}",
        )

    def test_init_ui_does_not_disable_persistence_for_standalone(self):
        """Standalone windows (no startmenu/submenu tag) keep persistence enabled.

        The opt-out is intentionally narrow — pinned standalone windows
        rely on geometry persistence for their normal lifecycle.
        """
        ui = self._make_ui("StandaloneKeepsPersistTest", tags=[])

        self.mm._init_ui(ui)

        self.assertTrue(
            ui.restore_window_size,
            "standalone windows must keep geometry persistence enabled",
        )

    def test_init_ui_resizes_stacked_ui_to_minimum(self):
        """Stacked UIs are resized to at least 600x600 to survive the
        geometry-restore degenerate-size case."""
        ui = self._make_ui("ResizeFloorTest", tags=["startmenu"])
        ui.resize(100, 100)

        self.mm._init_ui(ui)

        self.assertGreaterEqual(ui.width(), 600)
        self.assertGreaterEqual(ui.height(), 600)


class _NavStubSb:
    """Switchboard stub for the nav-resolution methods. ``get_ui`` *raises* for an
    unregistered name — mirroring the real resolver ("Slot class '<name>' not found") —
    so the test pins that ``_cached_ui`` must guard it rather than let it propagate. The
    destination resolver is the REAL ``SwitchboardWidgetMixin.menu_button_target_name`` (the
    shared SSoT the click + auto-hide paths both use), exercised against this stub's
    ``is_registered_ui``."""

    from uitk.switchboard.widgets import SwitchboardWidgetMixin as _Mixin

    menu_button_target_name = _Mixin.menu_button_target_name
    # The resolver now routes through ui_name_resolves (file stem OR handler-backed).
    # With no ``handlers`` set on this stub it degrades to is_registered_ui.
    ui_name_resolves = _Mixin.ui_name_resolves

    def __init__(self, registered, handler=None):
        self._registered = dict(registered)  # name -> ui sentinel
        self.hidden = []
        if handler is not None:  # opt-in: a UI handler exposing can_resolve()
            self.handlers = type("H", (), {"ui": handler})()

    def is_registered_ui(self, name):
        return name in self._registered

    def get_ui(self, name):
        if name not in self._registered:
            raise AttributeError(f"Slot class '{name}' not found.")
        return self._registered[name]

    def hide_unmatched_groupboxes(self, menu, tags):
        self.hidden.append((menu, tuple(tags)))


class TestNavButtonMenuResolution(QtBaseTestCase):
    """Click-path nav resolution must mirror the hover path's ``submenu_name()`` SSoT.

    Regression: a bare-target nav launcher (``target="cameras"``, ``filterTags="lower"``)
    must resolve to its composed submenu ``"cameras#lower#submenu"`` — the same name hover
    uses — not the bare ``target`` (which isn't a registered UI, so resolving it raised
    ``AttributeError`` and the upper/lower submenus never launched on click). And
    ``_cached_ui`` must return ``None`` for an unregistered name instead of raising.
    """

    def setUp(self):
        super().setUp()
        from uitk.widgets.marking_menu._marking_menu import MarkingMenu

        self.parent = self.track_widget(QtWidgets.QWidget())

        class _NavMenu:
            _cached_ui = MarkingMenu._cached_ui
            _resolve_button_menu = MarkingMenu._resolve_button_menu

            def __init__(self, sb):
                self.sb = sb
                self._submenu_cache = {}

        self._NavMenu = _NavMenu

    def _button(self, target, filterTags=""):
        from uitk.widgets.menuButton import MenuButton

        return MenuButton(self.parent, target=target, filterTags=filterTags)

    def test_click_resolves_nav_launcher_via_submenu_name(self):
        ui = object()
        sb = _NavStubSb({"cameras#lower#submenu": ui})
        menu = self._NavMenu(sb)
        btn = self._button("cameras", "lower")  # bare target is NOT a registered UI

        resolved = menu._resolve_button_menu(btn)

        self.assertIs(resolved, ui)  # used submenu_name(), not bare "cameras" (would raise)
        self.assertEqual(sb.hidden, [(ui, ("lower",))])  # filter tags applied to the submenu

    def test_click_resolves_standalone_target_directly(self):
        ui = object()
        sb = _NavStubSb({"some_tool": ui})  # no "some_tool#submenu"
        menu = self._NavMenu(sb)
        btn = self._button("some_tool")

        self.assertIs(menu._resolve_button_menu(btn), ui)

    def test_click_prefers_handler_resolvable_base_over_submenu(self):
        """A nav button whose bare ``target`` is NOT a file stem but IS resolvable
        by the UI handler (a mayatk native Maya menu like ``"key"``, built on
        demand) must resolve to that base target on click — NOT fall back to its
        ``#submenu`` overlay.

        Regression (Phase-5, commit 2cc9858): the click resolver checked the
        file-stem-only ``is_registered_ui("key")`` (False, since the native menu
        is not a file), so it fell back to ``key#submenu`` and a release showed
        the overlay instead of opening the native key menu. ``ui_name_resolves``
        now also consults the handler's ``can_resolve`` hook.
        """
        native, overlay = object(), object()

        class _Handler:  # stands in for MayaUiHandler.can_resolve
            def can_resolve(self, name):
                return name == "key"

        # Both the native base ("key") and the overlay ("key#submenu") are loadable,
        # but only the overlay is a registered *file*; the base is handler-backed.
        sb = _NavStubSb({"key": native, "key#submenu": overlay}, handler=_Handler())
        sb.is_registered_ui = lambda name: name == "key#submenu"  # base is NOT a file
        menu = self._NavMenu(sb)
        btn = self._button("key")

        self.assertEqual(sb.menu_button_target_name(btn), "key")
        self.assertIs(menu._resolve_button_menu(btn), native)

    def test_click_falls_back_to_submenu_when_base_unresolvable(self):
        """No handler resolves the bare target → compose the submenu (unchanged)."""
        overlay = object()
        sb = _NavStubSb({"cameras#lower#submenu": overlay})  # no handler
        sb.is_registered_ui = lambda name: name == "cameras#lower#submenu"
        menu = self._NavMenu(sb)
        btn = self._button("cameras", "lower")

        self.assertIs(menu._resolve_button_menu(btn), overlay)

    def test_resolve_empty_target_returns_none(self):
        menu = self._NavMenu(_NavStubSb({}))
        self.assertIsNone(menu._resolve_button_menu(self._button("")))

    def test_cached_ui_returns_none_for_unregistered(self):
        menu = self._NavMenu(_NavStubSb({}))
        self.assertIsNone(menu._cached_ui("no_such_menu#submenu"))  # must not raise

    def test_cached_ui_returns_and_caches_registered(self):
        ui = object()
        menu = self._NavMenu(_NavStubSb({"x#submenu": ui}))
        self.assertIs(menu._cached_ui("x#submenu"), ui)
        self.assertIn("x#submenu", menu._submenu_cache)  # cached on first hit


# ── Hosting claim (hosts_ui) — consumed by UiHandler.launch ──────────────────


def _write_ui_file(path, name, tags_csv=None):
    """Minimal QMainWindow .ui file (mirrors test_switchboard_browser)."""
    tag_block = ""
    if tags_csv is not None:
        tag_block = (
            f'<property name="uitk_tags" stdset="0">'
            f"<string>{tags_csv}</string></property>"
        )
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>QtUi</class>
 <widget class="QMainWindow" name="{name}">
  {tag_block}
 </widget>
</ui>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class TestMarkingMenuHostsUi(QtBaseTestCase):
    """``MarkingMenu.hosts_ui`` — the hosting claim ``UiHandler.launch`` consults.

    The claim must answer at the registry level (never force a UI load) and
    must agree with ``show()``'s stacked-vs-standalone dispatch, which reads
    the loaded widget's live tags: name-derived tags plus on-disk XML tags
    for unloaded UIs, live ``has_tags`` for loaded ones. A standalone launch
    of a claimed page would strip the stacked hosting invariants (the
    "browser-launched startmenu breaks the marking menu" bug).

    ``hosts_ui`` only reaches into ``self.sb``, so it's exercised unbound
    against a plain namespace — same pattern as ``_NavMenu`` above.
    """

    def setUp(self):
        super().setUp()
        import os
        import tempfile
        import types

        from uitk.switchboard import Switchboard

        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        _write_ui_file(os.path.join(d, "tool.ui"), "tool")
        _write_ui_file(os.path.join(d, "cameras#startmenu.ui"), "cameras_startmenu")
        _write_ui_file(os.path.join(d, "edit#submenu.ui"), "edit_submenu")
        # XML-tag-only page: no name tag, but show() would still dispatch it
        # as stacked once loaded (live tags include the XML tags).
        _write_ui_file(os.path.join(d, "oddmenu.ui"), "oddmenu", tags_csv="submenu")
        self.sb = Switchboard(ui_source=d, log_level="WARNING")
        self.host = types.SimpleNamespace(sb=self.sb)

    def tearDown(self):
        self.sb.deleteLater()
        self.tmp.cleanup()
        super().tearDown()

    def hosts(self, name):
        from uitk.widgets.marking_menu._marking_menu import MarkingMenu

        return MarkingMenu.hosts_ui(self.host, name)

    def test_claims_startmenu_and_submenu_names_unloaded(self):
        self.assertTrue(self.hosts("cameras#startmenu"))
        self.assertTrue(self.hosts("edit#submenu"))
        # Claiming must not have forced a load.
        self.assertIsNone(self.sb.loaded_ui.peek("cameras#startmenu"))

    def test_ignores_plain_names(self):
        self.assertFalse(self.hosts("tool"))

    def test_ignores_empty(self):
        self.assertFalse(self.hosts(""))
        self.assertFalse(self.hosts(None))

    def test_claims_xml_tagged_page_without_name_tag(self):
        """Claim parity with show()'s dispatch: XML uitk_tags count too."""
        self.assertTrue(self.hosts("oddmenu"))

    def test_claims_loaded_page_via_live_tags(self):
        ui = self.sb.get_ui("cameras#startmenu")
        self.track_widget(ui)
        self.assertTrue(self.hosts("cameras#startmenu"))

    def test_loaded_plain_tool_not_claimed(self):
        ui = self.sb.get_ui("tool")
        self.track_widget(ui)
        self.assertFalse(self.hosts("tool"))


class TestMarkingMenuBrowserEntryFilter(QtBaseTestCase):
    """The menu's gesture pages are hidden from the launcher surface.

    ``_setup_registry`` registers an editors post-build hook that applies
    ``HOSTED_PAGE_PATTERNS`` as the browser's structural exclude filter —
    startmenu/submenu pages are gesture surfaces this menu hosts, not
    standalone tools, and their show/hide traffic during gestures would
    otherwise churn an open browser (per-signal model resets = the
    "marking menu runs sluggish after the browser was used" report).
    Policy is class-level and overridable: a subclass can opt out with
    ``HOSTED_PAGE_PATTERNS = ()``; a user can clear it at runtime via the
    browser's public ``set_entry_filter()``.
    """

    def setUp(self):
        super().setUp()
        import os
        import tempfile
        import types

        from uitk.switchboard import Switchboard
        from uitk.widgets.marking_menu._marking_menu import MarkingMenu

        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        _write_ui_file(os.path.join(d, "tool.ui"), "tool")
        _write_ui_file(os.path.join(d, "cameras#startmenu.ui"), "cameras_startmenu")
        _write_ui_file(os.path.join(d, "uv#submenu.ui"), "uv_submenu")
        self.sb = Switchboard(ui_source=d, log_level="WARNING")
        self.sb.settings.branch("ui_browser").clear()
        # _register_browser_entry_filter only reaches self.sb and the
        # class-level patterns — exercised unbound, same as hosts_ui above.
        self.MarkingMenu = MarkingMenu
        self.menu_stub = types.SimpleNamespace(
            sb=self.sb, HOSTED_PAGE_PATTERNS=MarkingMenu.HOSTED_PAGE_PATTERNS
        )

    def tearDown(self):
        from qtpy import QtCore, QtWidgets

        self.sb.deleteLater()
        for _ in range(3):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
        self.tmp.cleanup()
        super().tearDown()

    def test_patterns_cover_both_marking_menu_tags(self):
        pats = self.MarkingMenu.HOSTED_PAGE_PATTERNS
        self.assertIn("*#startmenu*", pats)
        self.assertIn("*#submenu*", pats)

    def test_hook_excludes_gesture_pages_from_built_browser(self):
        """Register the policy, build the browser via the editors registry,
        and verify the gesture pages never materialise in its model."""
        self.MarkingMenu._register_browser_entry_filter(self.menu_stub)

        browser = self.sb.editors.get("browser")
        self.track_widget(browser)

        self.assertEqual(browser._model._names, ["tool"])

    def test_empty_patterns_register_nothing(self):
        """Opt-out: a subclass with no patterns leaves the browser unfiltered."""
        self.menu_stub.HOSTED_PAGE_PATTERNS = ()
        self.MarkingMenu._register_browser_entry_filter(self.menu_stub)

        browser = self.sb.editors.get("browser")
        self.track_widget(browser)

        self.assertEqual(
            sorted(browser._model._names),
            ["cameras#startmenu", "tool", "uv#submenu"],
        )

    def test_registration_tolerates_stub_switchboard(self):
        """A switchboard without an editors registry (test stubs, minimal
        hosts) must not crash policy registration."""
        import types

        bare = types.SimpleNamespace(
            sb=types.SimpleNamespace(),  # no .editors
            HOSTED_PAGE_PATTERNS=self.MarkingMenu.HOSTED_PAGE_PATTERNS,
        )
        self.MarkingMenu._register_browser_entry_filter(bare)  # must not raise


if __name__ == "__main__":
    unittest.main()
